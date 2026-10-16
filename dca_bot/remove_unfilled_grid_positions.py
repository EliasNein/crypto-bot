"""
Entfernt Grid-Positionen OHNE Bestand aus dem Ledger (16.10.2026, siehe
trading-bot-projekt.md, Log ab 29.09.2026).

**Warum.** Bis zum Fix A1 buchte der Bot eine Market-Kauf-Order, die die
Boerse mit `EXPIRED` und ausgefuehrt 0 beendet hatte, trotzdem als offene
Position - Menge 0, Einsatz 0, Ticker-Preis. Auf dem Homeserver standen
elf solche Eintraege (09.10. und 11.10.2026). Sie belegen ihre Stufe, und
jeder Zyklus versucht einen Verkauf ueber Menge 0, der vor der Boerse
abbricht. Der Code laesst seither keine neuen mehr entstehen; die alten
entfernt dieses Werkzeug (Entscheidung B1 vom 16.10.2026).

**Nur Eintraege ohne Bestand.** Kandidat ist ausschliesslich ein Eintrag,
der offen und echt ist (`dry_run` False) und dessen Menge UND Einsatz als
Zahl genau 0 sind (`grid_risk.is_unfilled_position`). Alles andere wird
nicht angefasst - eine Position mit Bestand schon gar nicht.

**Online gegengeprueft.** Jede `client_order_id` wird bei Binance
nachgeschlagen (`get_order_by_client_id`, nur lesender Client wie im
Positions-Audit). Entfernt wird nur, was die Boerse als beendet OHNE
Ausfuehrung meldet. Nicht gefunden, Abfrage gescheitert, noch aktiv,
unlesbar oder gar ausgefuehrt > 0: dieser Eintrag wird verweigert.

Sicherheitseigenschaften (Muster wie close_dry_run_trend.py):

- **Bericht ist der Default.** Ohne `--apply` wird nichts geschrieben und
  kein Lock geholt.
- **Einzeln verweigert** wird ein Kandidat, der sich nicht eindeutig
  belegen laesst (siehe oben, dazu: ohne client_order_id, fremdes Symbol,
  Verkaufsfelder oder Teilverkauf/Staub gesetzt). Er bleibt im Ledger; die
  uebrigen koennen trotzdem entfernt werden.
- **`--expect N` ist fuer `--apply` Pflicht.** Geschrieben wird nur, wenn
  genau N Kandidaten an der Boerse als ohne Wirkung belegt sind - jede
  Abweichung ist eine Weigerung.
- **Weigerung insgesamt**, wenn das Ledger fehlt oder unlesbar ist, die
  Pending-Datei Eintraege hat oder unlesbar ist, die Symbolpruefung nicht
  passt, kein Binance-Zugang besteht, oder ein echter offener Eintrag halb
  leer ist (nur Menge oder nur Einsatz 0) bzw. keine Zahlen traegt - das
  ist ein anderer Fehler und gehoert in die Hand eines Menschen.
- **Lock zuerst, dann lesen und neu pruefen.** Laeuft der Grid-Bot, bricht
  das Werkzeug ab (Exit-Code 2).
- **Zeitgestempelte Kopie** vor dem Schreiben, **atomarer Write** ueber
  `GridLedger.remove_unfilled_positions()` (die sich selbst noch einmal
  weigert, etwas anderes als Eintraege ohne Bestand zu entfernen), danach
  Kontrolle: Es fehlen genau diese Eintraege, alle anderen sind unveraendert.

Aufruf (Pfade und Symbol aus .env bzw. Umgebung, wie beim Bot):

    python -m dca_bot.remove_unfilled_grid_positions                     # Bericht
    python -m dca_bot.remove_unfilled_grid_positions --apply --expect 11

Exit-Codes: 0 entfernt bzw. Bericht ohne Einwand bzw. nichts zu tun,
1 Weigerung, 2 Bot laeuft, 3 Kontrolle nach dem Schreiben fehlgeschlagen.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from . import symbol_guard
from .grid_config import GridConfig
from .grid_risk import GridLedger, is_unfilled_position
from .pending_orders import (
    LOOKUP_FAILED,
    LOOKUP_NOT_FOUND,
    ORDER_LIFECYCLE_DEAD,
    ORDER_LIFECYCLE_FILLED,
    ORDER_LIFECYCLE_LIVE,
    executed_quantity,
    order_lifecycle_state,
)
from .process_lock import BotAlreadyRunning, ProcessLock

BACKUP_INFIX = "pre-remove"

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_BOT_RUNNING = 2
EXIT_VERIFY_FAILED = 3

# Felder, die nur ein Verkauf setzt - ein Kandidat mit einem davon ist
# kein reiner Kauf ohne Ausfuehrung.
SELL_FIELDS = ("sell_price", "sold_at", "realized_pnl", "sell_client_order_id")


@dataclass(frozen=True)
class Paths:
    ledger: str
    pending: str
    lock: str
    symbol: str


def resolve_paths() -> Paths:
    """Dieselben Variablen und Defaults wie GridConfig - und damit dieselben Dateien."""
    defaults = {f.name: f.default for f in fields(GridConfig)}

    def env(var: str, name: str) -> str:
        raw = os.getenv(var)
        return (defaults[name] if raw is None else raw).strip()

    return Paths(
        ledger=env("GRID_STATE_FILE", "state_file"),
        pending=env("GRID_PENDING_ORDERS_FILE", "pending_orders_file"),
        lock=env("GRID_LOCK_FILE", "lock_file"),
        symbol=env("GRID_SYMBOL", "symbol"),
    )


@dataclass
class Candidate:
    record: dict
    exchange_status: str = "nicht geprueft"
    refusal: tuple[str, str] | None = None

    @property
    def verified(self) -> bool:
        return self.refusal is None and self.exchange_status.startswith("ohne Wirkung")


@dataclass
class Assessment:
    """Ergebnis aller Pruefungen - ausser der Boersen-Abfrage ohne Seiteneffekte."""

    records: list[dict] | None = None
    candidates: list[Candidate] = field(default_factory=list)
    refusals: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def refuse(self, code: str, text: str) -> None:
        self.refusals.append((code, text))

    @property
    def refusal_codes(self) -> list[str]:
        return [code for code, _ in self.refusals]

    @property
    def verified(self) -> list[Candidate]:
        return [c for c in self.candidates if c.verified]


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _read_ledger(path: Path, a: Assessment) -> list[dict] | None:
    if not path.exists():
        a.refuse("ledger_missing", f"Grid-Ledger '{path}' existiert nicht.")
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        a.refuse("ledger_unreadable", f"Grid-Ledger '{path}' ist nicht lesbar: {exc}")
        return None
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        a.refuse("ledger_unreadable", f"Grid-Ledger '{path}' ist keine Liste von Eintraegen.")
        return None
    if not all("id" in r and "status" in r for r in data):
        a.refuse("ledger_unreadable", f"Grid-Ledger '{path}' hat Eintraege ohne id/status.")
        return None
    return data


def _check_pending(path: Path, a: Assessment) -> None:
    """Wie close_dry_run_trend: jede offene Order-Frage ist ein Grund, nichts zu tun."""
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        a.refuse("pending_unreadable", f"Pending-Datei '{path}' ist nicht lesbar: {exc}")
        return
    if not isinstance(data, dict) or not isinstance(data.get("orders"), list):
        a.refuse("pending_unreadable", f"Pending-Datei '{path}' hat ein unerwartetes Format.")
        return
    if data["orders"]:
        ids = ", ".join(str(o.get("client_order_id", "?")) for o in data["orders"]
                        if isinstance(o, dict))
        a.refuse(
            "pending_entries",
            f"Pending-Datei hat {len(data['orders'])} offene Order-Frage(n) ({ids}) - "
            "erst klaeren (Bot-Start mit Reconciliation oder check_orders).",
        )


def _check_symbols(a: Assessment) -> None:
    """Dieselbe Pruefung wie `symbol_guard --report` fuer den Grid-Bot."""
    spec = next(s for s in symbol_guard.BOT_SPECS if s.symbol_var == "GRID_SYMBOL")
    expected, findings = symbol_guard.report_bot(spec, symbol_guard._defaults())
    if not expected:
        a.refuse("symbol", "GRID_SYMBOL ist leer.")
        return
    for f in findings:
        allowed = {symbol_guard.STATUS_OK}
        if f.source != spec.ledger_label:
            allowed.add(symbol_guard.STATUS_ABSENT)
        if f.status not in allowed:
            a.refuse("symbol", f"Symbolpruefung: {f.source} meldet '{f.status}' - {f.detail}")
        else:
            a.notes.append(f"Symbolpruefung: {f.source} {f.status} ({f.detail})")


def _check_half_empty(records: list[dict], a: Assessment) -> None:
    """
    Ein echter offener Eintrag, bei dem nur EINE der beiden Zahlen 0 ist
    oder die Werte keine Zahlen sind, passt zu keinem bekannten Fehlerbild.
    Dann wird gar nichts entfernt - auch nicht die eindeutigen Kandidaten.
    """
    for r in records:
        if r.get("status") != "open" or r.get("dry_run") is not False:
            continue
        quantity, spent = r.get("quantity"), r.get("quote_spent")
        if not (_is_number(quantity) and _is_number(spent)):
            a.refuse(
                "unusable",
                f"Eintrag {r.get('id')}: Menge {quantity!r} / Einsatz {spent!r} sind "
                "keine Zahlen - bitte von Hand pruefen.",
            )
        elif (quantity == 0) != (spent == 0):
            a.refuse(
                "half_empty",
                f"Eintrag {r.get('id')} (Stufe {r.get('level_index')}): Menge {quantity!r}, "
                f"Einsatz {spent!r} - nur einer der beiden Werte ist 0. Das ist kein "
                "Kauf ohne Ausfuehrung, bitte von Hand pruefen.",
            )


def _pre_check(c: Candidate, symbol: str) -> None:
    """Pruefungen am Eintrag selbst, vor jeder Boersen-Abfrage."""
    r = c.record
    if not isinstance(r.get("client_order_id"), str) or not r.get("client_order_id"):
        c.refusal = ("no_client_order_id",
                     "keine client_order_id - an der Boerse nicht nachpruefbar")
        return
    entry_symbol = symbol_guard.effective_symbol(r)
    if entry_symbol != symbol:
        c.refusal = ("foreign_symbol",
                     f"Symbol {entry_symbol} statt {symbol}")
        return
    for name in SELL_FIELDS:
        if r.get(name) is not None:
            c.refusal = ("sell_field", f"{name}={r.get(name)!r} gesetzt - kein reiner Kauf")
            return
    if float(r.get("partial_exit_qty") or 0.0) > 0 or float(r.get("dust_qty") or 0.0) > 0:
        c.refusal = ("partial", "Teilverkauf oder Staub verbucht - nicht anfassen")


def _check_exchange(c: Candidate, client, symbol: str) -> None:
    """
    Fragt die Boerse. Nur `beendet, ausgefuehrt 0` gibt den Eintrag frei.
    Die Bewertung kommt aus order_lifecycle_state() - derselben Regel wie
    im Bot.
    """
    lookup, order = client.get_order_by_client_id(symbol, c.record["client_order_id"])
    if lookup == LOOKUP_NOT_FOUND:
        c.exchange_status = "nicht gefunden (-2013)"
        c.refusal = ("not_found", "Binance kennt die Order nicht - nicht belegbar")
        return
    if lookup == LOOKUP_FAILED or not isinstance(order, dict):
        c.exchange_status = "Abfrage gescheitert"
        c.refusal = ("lookup_failed", "Abfrage gescheitert - daraus folgt nichts")
        return

    status = order.get("status")
    executed = order.get("executedQty")
    c.exchange_status = f"{status}, ausgefuehrt {executed}"
    side = str(order.get("side", "BUY")).upper()
    if side != "BUY":
        c.refusal = ("side", f"Order-Seite {side} statt BUY")
        return
    state = order_lifecycle_state(order)
    if state == ORDER_LIFECYCLE_DEAD and executed_quantity(order) == 0:
        c.exchange_status = f"ohne Wirkung: {status}, ausgefuehrt {executed}"
        return
    if state == ORDER_LIFECYCLE_FILLED:
        c.refusal = ("filled",
                     "ACHTUNG: Die Order HAT an der Boerse ausgefuehrt - Bestand existiert, "
                     "Eintrag wird nicht entfernt. Bitte von Hand klaeren.")
    elif state == ORDER_LIFECYCLE_LIVE:
        c.refusal = ("live", "Order ist an der Boerse noch aktiv")
    else:
        c.refusal = ("unreadable", f"Status {status!r} nicht auswertbar")


def assess(paths: Paths, client) -> Assessment:
    """Alle Pruefungen. Schreibt nichts; fragt die Boerse nur lesend."""
    a = Assessment()
    records = _read_ledger(Path(paths.ledger), a)
    a.records = records
    _check_pending(Path(paths.pending), a)
    _check_symbols(a)
    if records is None:
        return a
    _check_half_empty(records, a)

    a.candidates = [Candidate(r) for r in records if is_unfilled_position(r)]
    for c in a.candidates:
        _pre_check(c, paths.symbol)

    if a.candidates and client is None:
        a.refuse("no_client", "Kein Binance-Zugang - die Kandidaten sind nicht nachpruefbar.")
        return a
    for c in a.candidates:
        if c.refusal is None:
            _check_exchange(c, client, paths.symbol)
    return a


def _verify(path: Path, before: list[dict], removed: set[str]) -> str | None:
    """Liest das Ledger neu: genau diese Eintraege fehlen, alle anderen unveraendert."""
    with path.open("r", encoding="utf-8") as fh:
        after = json.load(fh)
    expected = [r for r in before if r.get("id") not in removed]
    if after != expected:
        return (
            f"Ledger hat {len(after)} Eintraege, erwartet {len(expected)} "
            "(oder ein verbliebener Eintrag hat sich veraendert)."
        )
    return None


def _print_assessment(a: Assessment) -> None:
    for note in a.notes:
        print(f"  {note}")
    print()
    print(f"  Kandidaten (offen, echt, Menge 0, Einsatz 0): {len(a.candidates)}")
    for c in a.candidates:
        r = c.record
        if c.verified:
            verdict = "ohne Bestand belegt, wird entfernt"
        elif c.refusal:
            verdict = f"VERWEIGERT [{c.refusal[0]}] {c.refusal[1]} - bleibt im Ledger"
        else:
            verdict = "nicht geprueft"
        print(
            f"    Stufe {r.get('level_index')!s:>3}  {r.get('bought_at')}  {r.get('id')}  "
            f"{r.get('client_order_id')}"
        )
        print(f"           Boerse: {c.exchange_status}  ->  {verdict}")
    print(f"  Davon an der Boerse belegt ohne Wirkung: {len(a.verified)}")
    if a.refusals:
        print()
        print("  WEIGERUNG - es wird nichts geschrieben:")
        for code, text in a.refusals:
            print(f"    [{code}] {text}")


def run(apply_changes: bool, expect: int | None, paths: Paths, client_factory) -> int:
    print("Entfernen von Grid-Positionen ohne Bestand")
    print(f"Modus: {'SCHREIBEN (--apply)' if apply_changes else 'nur Bericht'}")
    print(f"Zeitpunkt: {datetime.now(timezone.utc).isoformat()}")
    print(f"Ledger: {paths.ledger}  (Symbol {paths.symbol})")

    if apply_changes and (expect is None or expect < 1):
        print("  WEIGERUNG: --apply braucht --expect N (N >= 1, die Zahl aus dem Bericht).")
        return EXIT_REFUSED

    client, reason = client_factory()
    if client is None:
        print(f"  Hinweis: kein Binance-Zugang ({reason}).")

    if not apply_changes:
        a = assess(paths, client)
        _print_assessment(a)
        print()
        if a.refusals:
            return EXIT_REFUSED
        if not a.candidates:
            print("Keine Eintraege ohne Bestand - nichts zu tun.")
            return EXIT_OK
        print("Bericht - es wurde nichts geschrieben.")
        if not a.verified:
            print("Kein Kandidat ist an der Boerse als ohne Wirkung belegt - nichts zu entfernen.")
            return EXIT_REFUSED
        print(f"Zum Entfernen: --apply --expect {len(a.verified)} (Grid-Bot vorher stoppen).")
        return EXIT_OK

    lock = ProcessLock(paths.lock, "grid")
    try:
        lock.acquire()
    except BotAlreadyRunning as exc:
        print(f"  ABGEBROCHEN: {exc}")
        print("  Der Grid-Bot laeuft noch. Erst stoppen (systemctl stop grid-bot).")
        return EXIT_BOT_RUNNING
    try:
        a = assess(paths, client)
        _print_assessment(a)
        print()
        if a.refusals:
            return EXIT_REFUSED
        if len(a.verified) != expect:
            print(
                f"  WEIGERUNG [expect_mismatch]: --expect {expect}, aber {len(a.verified)} "
                f"von {len(a.candidates)} Kandidaten an der Boerse ohne Wirkung belegt. "
                "Es wird nichts geschrieben."
            )
            return EXIT_REFUSED

        ledger_path = Path(paths.ledger)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = ledger_path.with_name(f"{ledger_path.name}.{BACKUP_INFIX}-{stamp}")
        shutil.copy2(ledger_path, backup)

        ids = {c.record["id"] for c in a.verified}
        removed = GridLedger(paths.ledger).remove_unfilled_positions(ids)

        problem = _verify(ledger_path, a.records, ids)
        if problem or removed != len(ids):
            print(f"  FEHLER bei der Kontrolle nach dem Schreiben: {problem or removed}")
            print(f"  Alter Stand liegt in {backup} - bitte pruefen, Bot NICHT starten.")
            return EXIT_VERIFY_FAILED

        print(f"GESCHRIEBEN: {removed} Eintraege ohne Bestand entfernt.")
        kept = [c for c in a.candidates if not c.verified]
        if kept:
            print(f"Verweigert und im Ledger geblieben: {len(kept)} - siehe oben.")
        print(f"Kopie des alten Standes: {backup}")
        print("Kontrolle: python -m dca_bot.audit_positions")
        return EXIT_OK
    finally:
        lock.release()


def _default_client_factory():
    # Import erst hier: audit_positions zieht python-binance nur bei Bedarf nach.
    from .audit_positions import _build_read_only_client

    return _build_read_only_client()


def main(argv: list[str] | None = None, client_factory=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Entfernt offene, echte Grid-Positionen ohne Bestand (Menge und Einsatz 0) "
            "aus dem Ledger, nachdem jede ihrer Orders an der Boerse als beendet ohne "
            "Ausfuehrung belegt ist. Ohne --apply wird nur berichtet."
        )
    )
    parser.add_argument("--apply", action="store_true",
                        help="Tatsaechlich schreiben (Grid-Bot muss gestoppt sein).")
    parser.add_argument("--expect", type=int,
                        help="Erwartete Zahl zu entfernender Eintraege - fuer --apply Pflicht.")
    args = parser.parse_args(argv)

    load_dotenv()
    return run(args.apply, args.expect, resolve_paths(),
               client_factory or _default_client_factory)


if __name__ == "__main__":
    sys.exit(main())

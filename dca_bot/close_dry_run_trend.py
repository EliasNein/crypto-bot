"""
Schliesst die offene DRY-RUN-Position des Trend-Bots kontrolliert im
Ledger (07.10.2026, siehe trading-bot-projekt.md, Log ab 29.09.2026).

**Warum.** Die Dry-Run-Position vom 15.09.2026 belegt den einzigen
Trend-Slot. Sie schliesst nur bei einem bestaetigten Abwaertssignal oder
10 % unter dem Einstieg - einen Take-Profit gibt es nicht. Solange sie
offen ist, gibt es im Testnet keinen echten Trend-Einstieg, keine echte
Stop-Order und keinen echten Ausstieg. Dieses Werkzeug schliesst sie mit
`exit_reason` = "manual_close", damit der Bot beim naechsten Start echt
einsteigen kann.

**Nur Ledger, keine Boerse.** Eine Dry-Run-Position existiert an der
Boerse nicht (K4) - es gibt nichts zu verkaufen und nichts zu stornieren.
Das Werkzeug braucht deshalb weder Zugangsdaten noch Netz; den
Ausstiegspreis gibt der Aufrufer vor (`--exit-price`, Entscheidung vom
07.10.2026: ehrlicher Mainnet-Preis statt des Testnet-Tickers mit seinen
Ausreissern). Die daraus berechnete `realized_pnl` ist simuliert und
zaehlt nirgends als Ergebnis - Positions-Audit, Dashboard und Export
werten nur `dry_run: false` aus.

**Die Sperre wird NICHT gesetzt.** Der Stop-Loss-Latch entsteht nur in
trend_strategy.py, und nur bei `reason == "stop_loss"`. Dieses Werkzeug
importiert weder die Strategie noch `TrendStopLoss`, und der Grund ist
fest "manual_close". Eine Sperre wuerde genau den Einstieg blockieren, um
den es geht.

Sicherheitseigenschaften (Muster wie fix_dry_run_quote_spent.py):

- **Bericht ist der Default.** Ohne `--apply` wird nichts geschrieben -
  auch kein Lock geholt, denn das Lock schreibt die PID in seine Datei.
- **Lock zuerst, dann lesen.** Mit `--apply` wird das Lock des Trend-Bots
  geholt, BEVOR das Ledger gelesen wird. Laeuft der Bot, bricht das
  Werkzeug ab (Exit-Code 2).
- **Weigerung statt Raten.** Geschrieben wird nur, wenn genau EINE offene
  Position existiert, sie `dry_run: true` hat und kein einziges Feld auf
  die Boerse verweist (Stop-Order, clientOrderIds, Teilfuellungen), die
  Pending-Datei leer ist, keine Sperre aktiv ist und die Symbolpruefung
  passt. Eine echte Position wird unter keinen Umstaenden angefasst.
- **`--trade-id` ist fuer `--apply` Pflicht** - geschlossen wird genau die
  Position, die der Bericht gezeigt hat.
- **Zeitgestempelte Kopie** vor dem Schreiben, **atomarer Write** ueber
  `TrendLedger.record_exit()` (derselbe Weg wie im Bot), danach
  Kontrolle: Nur dieser eine Eintrag darf sich geaendert haben.
- **Idempotent.** Ist die Position mit dieser ID bereits mit
  "manual_close" geschlossen, passiert nichts (Exit-Code 0).

Aufruf (Pfade und Symbol aus .env bzw. Umgebung, wie beim Bot):

    python -m dca_bot.close_dry_run_trend                                  # Bericht
    python -m dca_bot.close_dry_run_trend --exit-price 86000               # Bericht mit PnL
    python -m dca_bot.close_dry_run_trend --apply --trade-id <id> --exit-price 86000

Exit-Codes: 0 geschlossen bzw. Bericht ohne Einwand bzw. schon erledigt,
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
from .process_lock import BotAlreadyRunning, ProcessLock
from .trend_config import TrendConfig
from .trend_risk import TrendLedger, open_quantity

EXIT_REASON_MANUAL_CLOSE = "manual_close"
BACKUP_INFIX = "pre-close"

# Ab dieser Abweichung des Ausstiegspreises vom Einstiegspreis wird
# gewarnt (nicht verweigert): schuetzt vor einem Tippfehler wie 8600 statt
# 86000, ohne einen echten Kursverlauf zu verbieten.
EXIT_PRICE_WARN_PCT = 30.0

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_BOT_RUNNING = 2
EXIT_VERIFY_FAILED = 3

# Felder, die auf eine Order an der Boerse verweisen. Ist eines davon
# gesetzt, ist die Position (auch) echt - egal, was `dry_run` sagt.
EXCHANGE_FIELDS = ("client_order_id", "stop_loss_order_id", "exit_client_order_id")


@dataclass(frozen=True)
class Paths:
    ledger: str
    pending: str
    latch: str
    lock: str


def resolve_paths() -> Paths:
    """
    Dieselben Variablen und Defaults wie TrendConfig - und damit dieselben
    Dateien, die symbol_guard.report_bot() prueft.
    """
    defaults = {f.name: f.default for f in fields(TrendConfig)}

    def env(var: str, name: str) -> str:
        raw = os.getenv(var)
        return (defaults[name] if raw is None else raw).strip()

    return Paths(
        ledger=env("TREND_STATE_FILE", "state_file"),
        pending=env("TREND_PENDING_ORDERS_FILE", "pending_orders_file"),
        latch=env("TREND_STOP_LOSS_STATE_FILE", "stop_loss_state_file"),
        lock=env("TREND_LOCK_FILE", "lock_file"),
    )


@dataclass
class Assessment:
    """Ergebnis aller Pruefungen - ohne Seiteneffekte ermittelt."""

    records: list[dict] | None = None
    trade: dict | None = None
    refusals: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    already_closed: bool = False

    def refuse(self, code: str, text: str) -> None:
        self.refusals.append((code, text))

    @property
    def refusal_codes(self) -> list[str]:
        return [code for code, _ in self.refusals]


def _read_ledger(path: Path, a: Assessment) -> list[dict] | None:
    if not path.exists():
        a.refuse("ledger_missing", f"Trend-Ledger '{path}' existiert nicht.")
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        a.refuse("ledger_unreadable", f"Trend-Ledger '{path}' ist nicht lesbar: {exc}")
        return None
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        a.refuse("ledger_unreadable", f"Trend-Ledger '{path}' ist keine Liste von Eintraegen.")
        return None
    # Der Bot (und record_exit) greift mit r["id"] und r["status"] zu - ein
    # Eintrag ohne diese Felder liesse das Schreiben mittendrin scheitern.
    if not all("id" in r and "status" in r for r in data):
        a.refuse("ledger_unreadable", f"Trend-Ledger '{path}' hat Eintraege ohne id/status.")
        return None
    return data


def _check_pending(path: Path, a: Assessment) -> None:
    """
    Strenger als der Bot: Der liest eine unlesbare Pending-Datei als leer
    und warnt. Hier ist jede offene Order-Frage - und jede, die sich nicht
    ausschliessen laesst - ein Grund, nichts zu tun.
    """
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
    """
    Dieselbe Pruefung wie `python -m dca_bot.symbol_guard --report` fuer den
    Trend-Bot. Das Ledger muss "passt" melden; Pending-Datei, Sperre und
    Allocator-Zustand duerfen auch "nicht vorhanden" sein.
    """
    spec = next(s for s in symbol_guard.BOT_SPECS if s.symbol_var == "TREND_SYMBOL")
    expected, findings = symbol_guard.report_bot(spec, symbol_guard._defaults())
    if not expected:
        a.refuse("symbol", "TREND_SYMBOL ist leer.")
        return
    for f in findings:
        allowed = {symbol_guard.STATUS_OK}
        if f.source != spec.ledger_label:
            allowed.add(symbol_guard.STATUS_ABSENT)
        if f.status not in allowed:
            a.refuse("symbol", f"Symbolpruefung: {f.source} meldet '{f.status}' - {f.detail}")
        else:
            a.notes.append(f"Symbolpruefung: {f.source} {f.status} ({f.detail})")


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _check_position(records: list[dict], trade_id: str | None, a: Assessment) -> None:
    if trade_id:
        for r in records:
            if (
                r.get("id") == trade_id
                and r.get("status") == "closed"
                and r.get("exit_reason") == EXIT_REASON_MANUAL_CLOSE
            ):
                a.already_closed = True
                a.trade = r
                return

    open_records = [r for r in records if r.get("status") == "open"]
    if len(open_records) != 1:
        a.refuse(
            "open_count",
            f"{len(open_records)} offene Position(en) im Ledger - erwartet ist genau eine.",
        )
        return
    trade = open_records[0]
    a.trade = trade

    if trade_id is not None and trade.get("id") != trade_id:
        a.refuse(
            "trade_id",
            f"--trade-id {trade_id} passt nicht zur offenen Position {trade.get('id')}.",
        )
    if trade.get("dry_run") is not True:
        a.refuse(
            "not_dry_run",
            f"Position {trade.get('id')} hat dry_run={trade.get('dry_run')!r} - "
            "nur eine Dry-Run-Position darf so geschlossen werden.",
        )
    for name in EXCHANGE_FIELDS:
        if trade.get(name):
            a.refuse(
                "exchange_link",
                f"Position {trade.get('id')} hat {name}={trade.get(name)!r} - sie verweist "
                "auf eine Order an der Boerse und wird nicht angefasst.",
            )
    if float(trade.get("partial_exit_qty") or 0.0) > 0 or trade.get("partial_exit_order_ids"):
        a.refuse(
            "exchange_link",
            f"Position {trade.get('id')} hat verbuchte Teilfuellungen - nicht anfassen.",
        )
    for name in ("entry_price", "quantity", "quote_spent"):
        if not _is_number(trade.get(name)):
            a.refuse("unusable", f"Feld {name} fehlt oder ist keine Zahl: {trade.get(name)!r}")


def assess(paths: Paths, trade_id: str | None) -> Assessment:
    """Alle Pruefungen, nur lesend. Wird im Bericht und unter dem Lock genutzt."""
    a = Assessment()
    records = _read_ledger(Path(paths.ledger), a)
    a.records = records
    if records is not None:
        _check_position(records, trade_id, a)
    if a.already_closed:
        return a
    _check_pending(Path(paths.pending), a)
    if Path(paths.latch).exists():
        a.refuse(
            "latch_active",
            f"Stop-Loss-Sperre '{paths.latch}' ist aktiv - ein Einstieg waere ohnehin "
            "blockiert. Erst bewerten und bewusst zuruecksetzen "
            "(python -m dca_bot.reset_trend_stop_loss).",
        )
    _check_symbols(a)
    return a


def compute_pnl(trade: dict, exit_price: float) -> float:
    """Wie der Bot im Dry-Run: Erloes = offene Menge * Preis, ohne Gebuehr."""
    return open_quantity(trade) * exit_price - float(trade["quote_spent"])


def _exit_price_problem(exit_price: float | None) -> str | None:
    if exit_price is None:
        return None
    if not _is_number(exit_price) or exit_price <= 0:
        return f"--exit-price {exit_price!r} ist kein gueltiger Preis (> 0)."
    return None


def _verify(path: Path, before: list[dict], trade_id: str, expected: dict) -> str | None:
    """Liest das Ledger neu: nur der eine Eintrag darf sich geaendert haben."""
    with path.open("r", encoding="utf-8") as fh:
        after = json.load(fh)
    if len(after) != len(before):
        return f"Anzahl der Eintraege {len(before)} -> {len(after)}."
    for old, new in zip(before, after):
        if old.get("id") != trade_id:
            if old != new:
                return f"Eintrag {old.get('id')} hat sich veraendert."
            continue
        wanted = {**old, **expected}
        if new != wanted:
            diff = sorted(k for k in set(new) | set(wanted) if new.get(k) != wanted.get(k))
            return f"Eintrag {trade_id} weicht ab in: {', '.join(diff)}."
    return None


def _print_assessment(a: Assessment, exit_price: float | None) -> None:
    for note in a.notes:
        print(f"  {note}")
    t = a.trade
    if t is not None:
        print()
        print(f"  Position:        {t.get('id')}")
        print(f"  Status:          {t.get('status')}")
        print(f"  Modus:           dry_run={t.get('dry_run')!r}")
        print(f"  Einstieg:        {t.get('entry_price')} am {t.get('entry_time')}")
        print(f"  Menge/Einsatz:   {t.get('quantity')} / {t.get('quote_spent')}")
        print(f"  Stop-Order:      {t.get('stop_loss_order_id')!r}")
        print(f"  Symbol-Feld:     {t.get('symbol')!r}")
        if exit_price is not None and not a.already_closed and not _exit_price_problem(exit_price):
            entry = t.get("entry_price")
            if _is_number(t.get("quantity")) and _is_number(t.get("quote_spent")):
                print(
                    f"  Ausstieg zu {exit_price}: simulierte realized_pnl "
                    f"{compute_pnl(t, exit_price):+.8f} (zaehlt nirgends als Ergebnis)"
                )
            if _is_number(entry) and entry > 0:
                deviation = abs(exit_price / entry - 1) * 100
                if deviation > EXIT_PRICE_WARN_PCT:
                    print(
                        f"  WARNUNG: Ausstiegspreis weicht {deviation:.1f} % vom Einstieg ab - "
                        "Tippfehler?"
                    )
    if a.refusals:
        print()
        print("  WEIGERUNG - es wird nichts geschrieben:")
        for code, text in a.refusals:
            print(f"    [{code}] {text}")


def run(apply_changes: bool, trade_id: str | None, exit_price: float | None,
        paths: Paths) -> int:
    print("Schliessen der Dry-Run-Trend-Position im Ledger")
    print(f"Modus: {'SCHREIBEN (--apply)' if apply_changes else 'nur Bericht'}")
    print(f"Zeitpunkt: {datetime.now(timezone.utc).isoformat()}")
    print(f"Ledger: {paths.ledger}")

    price_problem = _exit_price_problem(exit_price)

    if not apply_changes:
        a = assess(paths, trade_id)
        if price_problem:
            a.refuse("exit_price", price_problem)
        _print_assessment(a, exit_price)
        print()
        if a.already_closed:
            print("Bereits mit manual_close geschlossen - nichts zu tun.")
            return EXIT_OK
        if a.refusals:
            return EXIT_REFUSED
        print("Keine Einwaende. Bericht - es wurde nichts geschrieben.")
        print("Zum Schliessen: --apply --trade-id <id> --exit-price <preis> (Trend-Bot vorher stoppen).")
        return EXIT_OK

    if not trade_id or exit_price is None:
        print("  WEIGERUNG: --apply braucht --trade-id und --exit-price.")
        return EXIT_REFUSED
    if price_problem:
        print(f"  WEIGERUNG: {price_problem}")
        return EXIT_REFUSED

    lock = ProcessLock(paths.lock, "trend")
    try:
        lock.acquire()
    except BotAlreadyRunning as exc:
        print(f"  ABGEBROCHEN: {exc}")
        print("  Der Trend-Bot laeuft noch. Erst stoppen (systemctl stop trend-bot).")
        return EXIT_BOT_RUNNING
    try:
        a = assess(paths, trade_id)
        _print_assessment(a, exit_price)
        print()
        if a.already_closed:
            print("Bereits mit manual_close geschlossen - nichts zu tun, nichts geschrieben.")
            return EXIT_OK
        if a.refusals:
            return EXIT_REFUSED

        ledger_path = Path(paths.ledger)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = ledger_path.with_name(f"{ledger_path.name}.{BACKUP_INFIX}-{stamp}")
        shutil.copy2(ledger_path, backup)

        trade = a.trade
        exit_time = datetime.now(timezone.utc).isoformat()
        pnl = compute_pnl(trade, exit_price)
        TrendLedger(paths.ledger).record_exit(
            trade["id"], exit_price, exit_time, EXIT_REASON_MANUAL_CLOSE, pnl
        )

        problem = _verify(
            ledger_path,
            a.records,
            trade["id"],
            {
                "status": "closed",
                "exit_price": exit_price,
                "exit_time": exit_time,
                "exit_reason": EXIT_REASON_MANUAL_CLOSE,
                "realized_pnl": pnl,
                "exit_client_order_id": None,
            },
        )
        if problem:
            print(f"  FEHLER bei der Kontrolle nach dem Schreiben: {problem}")
            print(f"  Alter Stand liegt in {backup} - bitte pruefen, Bot NICHT starten.")
            return EXIT_VERIFY_FAILED

        print(f"GESCHRIEBEN: Position {trade['id']} geschlossen (manual_close, "
              f"Ausstieg {exit_price}, simulierte PnL {pnl:+.8f}).")
        print(f"Kopie des alten Standes: {backup}")
        print("Keine Stop-Loss-Sperre gesetzt. Kontrolle: python -m dca_bot.audit_positions")
        return EXIT_OK
    finally:
        lock.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Schliesst die offene Dry-Run-Position des Trend-Bots im Ledger "
            "(exit_reason manual_close), ohne Boerse und ohne Stop-Loss-Sperre. "
            "Ohne --apply wird nur berichtet."
        )
    )
    parser.add_argument("--apply", action="store_true",
                        help="Tatsaechlich schreiben (Trend-Bot muss gestoppt sein).")
    parser.add_argument("--trade-id",
                        help="Volle ID der offenen Position - fuer --apply Pflicht.")
    parser.add_argument("--exit-price", type=float,
                        help="Ausstiegspreis (z.B. Mainnet-Kurs) - fuer --apply Pflicht.")
    args = parser.parse_args(argv)

    # Wie audit_positions: Pfade und TREND_SYMBOL aus der .env, damit
    # Werkzeug und Symbolpruefung dieselben Dateien sehen wie der Bot.
    load_dotenv()
    return run(args.apply, args.trade_id, args.exit_price, resolve_paths())


if __name__ == "__main__":
    sys.exit(main())

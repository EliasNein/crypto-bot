"""
Symbolbindung der Zustandsdateien (28.09.2026): Leseregel fuer
Altbestand, Pruefung beim Bot-Start und ein Bericht ohne Start.

**Das Problem.** Binance hat fuer Kunden im EWR alle USDT-Spot-Paare
entfernt; fuer echtes Geld wird BTCEUR gehandelt (Entscheidung vom
28.09.2026, trading-bot-projekt.md 6g/6h). Fuer einen frischen Start mit
leeren Ledgern reicht dafuer die Konfiguration. Gefaehrlich war der
Versehens-Fall "neues Symbol auf altem Ledger": Grid- und Trend-Ledger,
der Allocator-Zustand und die Stop-Loss-Sperren wussten nicht, zu welchem
Paar sie gehoeren, und ein Bot haette alte Positionen still als Positionen
des neuen Paars weitergefuehrt. Beim DCA-Bot, dessen Eintraege schon
immer ein Symbol trugen, wurden Kaeufe eines anderen Paars still
ignoriert - und fielen damit aus Tageslimit, Stop-Loss-Kostenbasis und
Bestandsabgleich heraus.

**Altbestand (Entscheidung E1 vom 28.09.2026, Option c).** Eintraege aus
der Zeit vor der Symbolbindung haben kein Feld `symbol`. Sie gelten als
`LEGACY_SYMBOL` = BTCUSDT. Das ist keine Annahme, sondern die
Projektgeschichte: Jedes Ledger, das es bis zu diesem Tag gibt - Desktop,
Laptop, VPS und Homeserver -, stammt aus BTCUSDT-Laeufen (siehe 6a-6h).
Bewusst NICHT gewaehlt:

- "Fehlendes Feld gilt als das konfigurierte Symbol": Stuende beim ersten
  Start schon das neue Paar in der .env, wuerde genau der Irrtum
  festgeschrieben, gegen den diese Pruefung gebaut ist.
- Ein Stempel-Skript als Voraussetzung: Der Deploy haette dann eine
  zwingende Reihenfolge bekommen, und ein Neustart vor dem Skript liesse
  die Bots still aus.

Alte Eintraege werden auch nicht nachtraeglich gestempelt - die Regel
gilt beim Lesen, die Dateien bleiben unveraendert.

**Die Startpruefung.** Jeder Bot prueft beim Start, VOR der
Reconciliation, ob Ledger, Pending-Datei, Stop-Loss-Sperre und (bei
aktivem Opt-in) der Allocator-Zustand zu seinem konfigurierten Paar
gehoeren. Gehoert etwas zu einem anderen Paar, startet er nicht
(`SymbolMismatch`, Exit-Code 0 wie bei Konfigurationsfehlern - keine
systemd-Neustartschleife). Eine Sperrdatei mit unlesbarem Inhalt ist die
Ausnahme (Entscheidung E2): Sie wird bewusst nicht atomar geschrieben,
ihr Inhalt ist rein informativ, und eine Sperre verhindert ohnehin nur
Kaeufe. Sie ergibt deshalb eine Warnung (Log und einmal Telegram), keinen
Abbruch.

**Der Bericht** (`python -m dca_bot.symbol_guard --report`). Ein
Startabbruch laesst den Dienst still aus - ohne Heartbeat, und offene
Grid-Positionen sind dann ungeschuetzt. Deshalb laesst sich dieselbe
Pruefung VOR einem Neustart gegen die echten Dateien ausfuehren: nur
lesend, kein Lock, keine Zugangsdaten, ohne irgendeine Datei anzulegen.
Er nutzt dieselben Pruef-Funktionen wie der Start.

Der obere Teil dieses Moduls ist bewusst rein und ohne Projekt-Importe:
allocator_signals.py (das DCA und Trend vor jeder Order lesen) braucht
die Leseregel ebenso wie das Positions-Audit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

# Das Paar, dem ein Eintrag ohne `symbol`-Feld zugerechnet wird - siehe
# Modul-Docstring. Nicht aendern: Die Konstante beschreibt Vergangenheit.
LEGACY_SYMBOL = "BTCUSDT"

REPORT_COMMAND = "python -m dca_bot.symbol_guard --report"


def effective_symbol(entry: object) -> str:
    """
    Das Paar, zu dem ein Eintrag gehoert.

    - Feld fehlt oder ist `None` (Altbestand): `LEGACY_SYMBOL`.
    - Feld ist ein nicht-leerer Text: dieser Text.
    - Alles andere (leerer Text, Zahl, Liste - praktisch nur durch
      manuelles Editieren): eine Darstellung des Werts, die zu keinem
      konfigurierten Symbol passt. Ein kaputtes Feld wird also nicht als
      Altbestand durchgewunken, sondern faellt bei der Pruefung auf.
    """
    value = entry.get("symbol") if isinstance(entry, Mapping) else None
    if value is None:
        return LEGACY_SYMBOL
    if isinstance(value, str) and value.strip():
        return value.strip()
    return f"<unbrauchbar: {value!r}>"


def is_legacy(entry: object) -> bool:
    """Ob ein Eintrag aus der Zeit vor der Symbolbindung stammt (kein Feld)."""
    return not isinstance(entry, Mapping) or entry.get("symbol") is None


# --- Befunde ---------------------------------------------------------------

STATUS_ABSENT = "nicht vorhanden"
STATUS_OK = "passt"
STATUS_MISMATCH = "FREMDES PAAR"
STATUS_UNREADABLE = "UNLESBAR"


@dataclass(frozen=True)
class Finding:
    """
    Das Ergebnis fuer EINE Datei. `blocking` heisst: der Bot startet nicht.
    Eine unlesbare Datei ist je nach Art blockierend (Ledger - der Start
    bricht dort ohnehin mit LedgerUnreadable ab) oder nur eine Warnung
    (Sperre, Allocator-Zustand, Pending-Datei - siehe die check_*-
    Funktionen).
    """

    source: str
    path: str
    status: str
    detail: str
    blocking: bool = False
    hint: str = ""

    @property
    def is_warning(self) -> bool:
        return self.status == STATUS_UNREADABLE and not self.blocking

    def line(self) -> str:
        text = f"{self.source} ({self.path}): {self.detail}"
        return f"{text} {self.hint}".strip() if self.blocking else text


def _describe(entries: list, expected: str) -> tuple[str, bool]:
    """Zusammenfassung der Symbole einer Eintragsliste und ob eins fremd ist."""
    counts = Counter(effective_symbol(e) for e in entries)
    legacy = sum(1 for e in entries if is_legacy(e))
    parts = []
    for symbol, count in sorted(counts.items()):
        text = f"{count} {'Eintrag' if count == 1 else 'Eintraege'} {symbol}"
        if symbol == LEGACY_SYMBOL and legacy:
            text += f" (davon {legacy} ohne Feld, gelten als {LEGACY_SYMBOL})"
        parts.append(text)
    foreign = any(symbol != expected for symbol in counts)
    return ", ".join(parts), foreign


def check_entries(
    source: str, path: str, entries: list, expected: str, hint: str
) -> Finding:
    """Ein Ledger oder eine Pending-Datei: jeder Eintrag muss zum Paar gehoeren."""
    if not entries:
        return Finding(source, path, STATUS_OK, "keine Eintraege")
    detail, foreign = _describe(entries, expected)
    if foreign:
        return Finding(source, path, STATUS_MISMATCH, detail, blocking=True, hint=hint)
    return Finding(source, path, STATUS_OK, detail)


def _read_json(path: Path) -> tuple[object, str | None]:
    """Liest JSON nur lesend. (Inhalt, None) oder (None, Grund)."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as exc:
        return None, f"kein gueltiges JSON ({exc})"
    except OSError as exc:
        return None, f"nicht lesbar ({type(exc).__name__})"


def check_ledger_file(source: str, path: str, expected: str, hint: str) -> Finding:
    """Fuer den Bericht: ein Ledger aus der Datei. Unlesbar blockiert (LedgerUnreadable)."""
    p = Path(path)
    if not p.exists():
        return Finding(source, path, STATUS_ABSENT, "noch kein Ledger (frischer Start)")
    data, error = _read_json(p)
    if error is None and not isinstance(data, list):
        error = "unerwartetes Format (keine Liste)"
    if error is not None:
        return Finding(
            source, path, STATUS_UNREADABLE, error, blocking=True,
            hint="Der Bot startet damit nicht (LedgerUnreadable) - Datei pruefen oder aus "
            "einem Backup wiederherstellen.",
        )
    return check_entries(source, path, [e for e in data if isinstance(e, dict)], expected, hint)


def check_pending_file(source: str, path: str, expected: str, hint: str) -> Finding:
    """
    Fuer den Bericht: die Pending-Datei. Unlesbar ist hier eine Warnung -
    genau so behandelt sie der Bot selbst (PendingOrderStore liest sie als
    leer und warnt).
    """
    p = Path(path)
    if not p.exists():
        return Finding(source, path, STATUS_ABSENT, "keine offenen Order-Fragen")
    data, error = _read_json(p)
    if error is None and not (isinstance(data, dict) and isinstance(data.get("orders"), list)):
        error = "unerwartetes Format"
    if error is not None:
        return Finding(source, path, STATUS_UNREADABLE,
                       f"{error} - der Bot liest sie als leer und warnt")
    return check_entries(
        source, path, [o for o in data["orders"] if isinstance(o, dict)], expected, hint
    )


def check_latch_file(source: str, path: str, expected: str, hint: str) -> Finding:
    """
    Eine Stop-Loss-Sperre. Das Feld `symbol` steht dort schon immer - neu
    ist nur, dass es gelesen wird. Unlesbarer Inhalt ist eine Warnung
    (Entscheidung E2), keine Blockade: Die Datei wird bewusst nicht atomar
    geschrieben, und sie verhindert ohnehin nur Kaeufe.
    """
    p = Path(path)
    if not p.exists():
        return Finding(source, path, STATUS_ABSENT, "keine Sperre aktiv")
    data, error = _read_json(p)
    if error is None and not isinstance(data, dict):
        error = "unerwartetes Format"
    if error is not None:
        return Finding(
            source, path, STATUS_UNREADABLE,
            f"Sperre aktiv, Inhalt {error} - zu welchem Paar sie gehoert, ist nicht "
            "feststellbar. Die Sperre wirkt weiter (sie blockiert Kaeufe).",
        )
    symbol = effective_symbol(data)
    detail = f"Sperre aktiv fuer {symbol}" + (" (ohne Feld)" if is_legacy(data) else "")
    if symbol != expected:
        return Finding(source, path, STATUS_MISMATCH, detail, blocking=True, hint=hint)
    return Finding(source, path, STATUS_OK, detail)


def check_allocator_file(source: str, path: str, expected: str, hint: str) -> Finding:
    """
    Der Allocator-Zustand. Unlesbar ist eine Warnung: DCA und Trend fallen
    dann zur Laufzeit ohnehin auf 100 % DCA zurueck (allocator_signals.py),
    und der Allocator selbst beginnt mit leerem Zustand.
    """
    p = Path(path)
    if not p.exists():
        return Finding(source, path, STATUS_ABSENT, "noch kein Zustand geschrieben")
    data, error = _read_json(p)
    if error is None and not isinstance(data, dict):
        error = "unerwartetes Format"
    if error is not None:
        return Finding(source, path, STATUS_UNREADABLE,
                       f"{error} - zur Laufzeit gilt der Rueckfall auf 100 % DCA")
    symbol = effective_symbol(data)
    detail = f"gerechnet fuer {symbol}" + (" (ohne Feld)" if is_legacy(data) else "")
    if symbol != expected:
        return Finding(source, path, STATUS_MISMATCH, detail, blocking=True, hint=hint)
    return Finding(source, path, STATUS_OK, detail)


# --- Loesungshinweise, je Art ----------------------------------------------


def ledger_hint(symbol_var: str) -> str:
    return (
        f"Loesung: {symbol_var} auf das Paar des Ledgers zurueckstellen - oder, nachdem "
        "offene Positionen geklaert sind (python -m dca_bot.audit_positions), das Ledger "
        "archivieren (umbenennen) und mit leerem Ledger starten."
    )


def pending_hint(symbol_var: str) -> str:
    return (
        f"Loesung: mit dem bisherigen {symbol_var} starten, bis die Reconciliation die "
        "Eintraege geklaert hat (Datei leer), oder einzeln nachschlagen: python -m "
        "dca_bot.check_orders --client-order-id <id> --symbol <paar>."
    )


def latch_hint(reset_command: str) -> str:
    return (
        "Loesung: Die Sperre stammt aus dem Betrieb mit einem anderen Paar - nach Pruefung "
        f"aufheben ({reset_command}) oder die Datei loeschen."
    )


ALLOCATOR_CONSUMER_HINT = (
    "Loesung: ALLOCATOR_SYMBOL auf dasselbe Paar stellen und den Allocator mit erneuertem "
    "Zustand starten (siehe dessen Meldung), oder das Opt-in (*_ALLOCATOR_STATE_FILE) "
    "voruebergehend leeren."
)
ALLOCATOR_OWN_HINT = (
    "Loesung: Der Zustand gehoert zu einem anderen Paar. Datei archivieren (umbenennen); der "
    "Allocator rechnet aus Tageskerzen neu, die Glaettung beginnt dann beim Rohwert."
)


def bot_findings(
    *,
    symbol_var: str,
    expected: str,
    ledger_label: str,
    ledger_path: str,
    ledger_records: list,
    pending_store,
    latch_path: str,
    latch_reset: str,
    allocator_path: str = "",
) -> list[Finding]:
    """
    Die Befunde eines handelnden Bots beim Start. Das Ledger ist zu diesem
    Zeitpunkt bereits als lesbar geprueft (verify_state_readable), die
    Pending-Eintraege kommen aus der Ablage des Clients. Sperre und
    Allocator-Zustand werden wie im Bericht aus der Datei gelesen -
    dieselben Funktionen, also dieselbe Regel.
    """
    findings = [
        check_entries(ledger_label, ledger_path, ledger_records, expected,
                      ledger_hint(symbol_var)),
        check_entries("Pending-Datei", str(pending_store.path),
                      [{"symbol": p.symbol} for p in pending_store.all()], expected,
                      pending_hint(symbol_var)),
        check_latch_file("Stop-Loss-Sperre", latch_path, expected, latch_hint(latch_reset)),
    ]
    if allocator_path:
        findings.append(check_allocator_file("Allocator-Zustand", allocator_path, expected,
                                             ALLOCATOR_CONSUMER_HINT))
    return findings


# --- Durchsetzen beim Start -------------------------------------------------


class SymbolMismatch(Exception):
    """
    Eine Zustandsdatei gehoert zu einem anderen Paar als konfiguriert - der
    Bot startet nicht. Die Meldung nennt jede betroffene Datei samt Loesung
    und ist fuer Log und Telegram formuliert.
    """

    def __init__(self, bot_label: str, symbol_var: str, expected: str, findings: list[Finding]):
        self.findings = findings
        lines = [
            f"{bot_label} startet NICHT: konfiguriert ist {symbol_var}={expected}, aber "
            "folgende Dateien gehoeren zu einem anderen Paar (bzw. sind unlesbar):"
        ]
        lines += [f"- {f.line()}" for f in findings]
        lines.append(f"Bericht ohne Start: {REPORT_COMMAND}")
        super().__init__("\n".join(lines))


def enforce(
    findings: list[Finding],
    *,
    bot_label: str,
    symbol_var: str,
    expected: str,
    logger,
    notify: Callable[[str], None],
) -> None:
    """
    Protokolliert jeden Befund und setzt ihn durch: Warnungen (unlesbare
    Sperre bzw. Allocator-Zustand) gehen ins Log und einmal per Telegram -
    die Pruefung laeuft nur beim Start, "einmal" ist damit "einmal pro
    Start". Blockierende Befunde werfen `SymbolMismatch`.
    """
    for f in findings:
        if f.blocking:
            continue
        if f.is_warning:
            logger.warning("Symbolpruefung (%s): %s", bot_label, f.line())
            notify(f"[SYMBOL-WARNUNG] {bot_label}: {f.line()}")
        else:
            logger.info("Symbolpruefung (%s=%s): %s - %s", symbol_var, expected, f.line(), f.status)
    blocking = [f for f in findings if f.blocking]
    if blocking:
        raise SymbolMismatch(bot_label, symbol_var, expected, blocking)


# --- Bericht ohne Start -----------------------------------------------------


@dataclass(frozen=True)
class BotSpec:
    """Welche Dateien ein Bot hat - dieselben Variablen wie in seiner Config."""

    label: str
    symbol_var: str
    ledger_var: str | None = None
    ledger_label: str = ""
    pending_var: str | None = None
    latch_var: str | None = None
    latch_reset: str = ""
    allocator_var: str | None = None
    own_allocator: bool = False


BOT_SPECS = (
    BotSpec("DCA-Bot", "DCA_SYMBOL", "DCA_BOT_STATE_FILE", "DCA-Ledger", "DCA_PENDING_ORDERS_FILE",
            "DCA_BOT_STOP_LOSS_STATE_FILE", "python -m dca_bot.reset_stop_loss",
            "DCA_ALLOCATOR_STATE_FILE"),
    BotSpec("Grid-Bot", "GRID_SYMBOL", "GRID_STATE_FILE", "Grid-Ledger", "GRID_PENDING_ORDERS_FILE",
            "GRID_STOP_LOSS_STATE_FILE", "python -m dca_bot.reset_grid_stop_loss"),
    BotSpec("Trend-Following-Bot", "TREND_SYMBOL", "TREND_STATE_FILE", "Trend-Ledger",
            "TREND_PENDING_ORDERS_FILE", "TREND_STOP_LOSS_STATE_FILE",
            "python -m dca_bot.reset_trend_stop_loss", "TREND_ALLOCATOR_STATE_FILE"),
    BotSpec("Kapital-Allocator", "ALLOCATOR_SYMBOL", allocator_var="ALLOCATOR_STATE_FILE",
            own_allocator=True),
)


def _defaults() -> dict[str, str]:
    """
    Die Default-Werte der Variablen, direkt aus den Config-Dataclasses -
    damit der Bericht nicht eine zweite, womoeglich abweichende Liste
    fuehrt. Import erst hier: Der obere Teil des Moduls bleibt importfrei.
    """
    from dataclasses import fields

    from .allocator_config import AllocatorConfig
    from .config import Config
    from .grid_config import GridConfig
    from .trend_config import TrendConfig

    mapping = {
        Config: {"DCA_SYMBOL": "symbol", "DCA_BOT_STATE_FILE": "state_file",
                 "DCA_PENDING_ORDERS_FILE": "pending_orders_file",
                 "DCA_BOT_STOP_LOSS_STATE_FILE": "stop_loss_state_file",
                 "DCA_ALLOCATOR_STATE_FILE": "allocator_state_file"},
        GridConfig: {"GRID_SYMBOL": "symbol", "GRID_STATE_FILE": "state_file",
                     "GRID_PENDING_ORDERS_FILE": "pending_orders_file",
                     "GRID_STOP_LOSS_STATE_FILE": "stop_loss_state_file"},
        TrendConfig: {"TREND_SYMBOL": "symbol", "TREND_STATE_FILE": "state_file",
                      "TREND_PENDING_ORDERS_FILE": "pending_orders_file",
                      "TREND_STOP_LOSS_STATE_FILE": "stop_loss_state_file",
                      "TREND_ALLOCATOR_STATE_FILE": "allocator_state_file"},
        AllocatorConfig: {"ALLOCATOR_SYMBOL": "symbol", "ALLOCATOR_STATE_FILE": "state_file"},
    }
    result = {}
    for cls, names in mapping.items():
        defaults = {f.name: f.default for f in fields(cls)}
        for var, field_name in names.items():
            result[var] = defaults[field_name]
    return result


def _env(var: str, defaults: dict[str, str]) -> str:
    raw = os.getenv(var)
    return (defaults[var] if raw is None else raw).strip()


def report_bot(spec: BotSpec, defaults: dict[str, str]) -> tuple[str, list[Finding]]:
    """Das erwartete Symbol eines Bots und seine Befunde - gegen die echten Dateien."""
    expected = _env(spec.symbol_var, defaults)
    findings: list[Finding] = []
    if spec.ledger_var:
        findings.append(check_ledger_file(
            spec.ledger_label, _env(spec.ledger_var, defaults), expected,
            ledger_hint(spec.symbol_var)))
    if spec.pending_var:
        findings.append(check_pending_file(
            "Pending-Datei", _env(spec.pending_var, defaults), expected,
            pending_hint(spec.symbol_var)))
    if spec.latch_var:
        findings.append(check_latch_file(
            "Stop-Loss-Sperre", _env(spec.latch_var, defaults), expected,
            latch_hint(spec.latch_reset)))
    if spec.allocator_var:
        path = _env(spec.allocator_var, defaults)
        if path:
            findings.append(check_allocator_file(
                "Allocator-Zustand", path, expected,
                ALLOCATOR_OWN_HINT if spec.own_allocator else ALLOCATOR_CONSUMER_HINT))
    return expected, findings


def run_report(out=None) -> int:
    """
    Druckt den Bericht und gibt 0 zurueck, wenn jeder Bot starten wuerde
    (Warnungen eingeschlossen), sonst 1. Liest nur - siehe Modul-Docstring.
    """
    out = out or sys.stdout
    from .config_guard import ConfigError, allocator_symbol_conflict

    defaults = _defaults()
    print("Symbolpruefung - nur lesend, es wird nichts veraendert und nichts gestartet.", file=out)
    print(f"Altbestand ohne Feld 'symbol' gilt als {LEGACY_SYMBOL} (LEGACY_SYMBOL).", file=out)
    print("Geprueft wird nur die Symbolbindung, nicht die uebrige Startpruefung "
          "(Zugangsdaten, Werte).", file=out)

    all_start = True
    for spec in BOT_SPECS:
        expected, findings = report_bot(spec, defaults)
        print(file=out)
        print(f"{spec.label}  ({spec.symbol_var}={expected or '<leer>'})", file=out)
        for f in findings:
            print(f"  {f.source:<18} {f.status:<16} {f.path}", file=out)
            print(f"  {'':<18} {f.detail}", file=out)
            if f.blocking and f.hint:
                print(f"  {'':<18} {f.hint}", file=out)
        blocking = [f for f in findings if f.blocking]
        reasons = []
        if not expected:
            reasons.append(f"{spec.symbol_var} ist leer (Konfigurationsfehler)")
        conflict = allocator_symbol_conflict(spec.symbol_var)
        if conflict:
            reasons.append(conflict)
        if blocking:
            reasons.append("Datei(en) eines anderen Paars bzw. unlesbar (siehe oben)")
        if reasons:
            all_start = False
            print(f"  -> Start: wuerde NICHT starten - {'; '.join(reasons)}", file=out)
        elif any(f.is_warning for f in findings):
            print("  -> Start: wuerde starten, mit Warnung (Log und einmal Telegram)", file=out)
        else:
            print("  -> Start: wuerde starten", file=out)
    return 0 if all_start else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prueft, ob Ledger, Pending-Dateien, Stop-Loss-Sperren und Allocator-Zustand zu "
            "den konfigurierten Paaren gehoeren - dieselbe Pruefung wie beim Bot-Start, aber "
            "nur lesend und ohne Start. Exit-Code 0: jeder Bot wuerde starten, 1: mindestens "
            "einer nicht."
        )
    )
    parser.add_argument("--report", action="store_true", required=True,
                        help="Bericht ausgeben (derzeit der einzige Modus).")
    parser.parse_args(argv)
    return run_report()


if __name__ == "__main__":
    sys.exit(main())

"""
Einmalige Korrektur verfälschter `quote_spent`/`realized_pnl`-Werte in
DRY-RUN-Ledger-Einträgen (Fund vom 22.09.2026, siehe
trading-bot-projekt.md Abschnitt 6g).

**Der Fehler:** Seit dem K3-Fix (16.09.2026) quantisieren alle drei
Strategien im Dry-Run die Kaufmenge auf die `stepSize` des Symbols, haben
den dazugehörenden Betrag aber weiterhin als konfigurierten Rohbetrag
gebucht:

    quantity    = quantize_quantity(amount / price, step)   # abgerundet
    quote_spent = amount                                    # NICHT abgerundet

Die weggerundete Teilmenge wurde nie gekauft - sie stand trotzdem in der
Kostenbasis. Bei 15 USDT und `stepSize` 1e-5 ist eine Mengenstufe bei
BTC ~80.000 rund 0,80 USDT, also ~5 % des Auftrags und damit MEHR als der
Grid-Stufenabstand von 1,5 %. Die realisierte PnL einer geschlossenen
Dry-Run-Position wurde dadurch systematisch zu negativ und konnte trotz
gestiegenem Kurs im Minus landen - genau so ist der Fehler aufgefallen.

**Nur der Dry-Run-Pfad ist betroffen.** Bei einer echten Order liefert
Binance mit `cummulativeQuoteQty` den tatsächlich belasteten Betrag; dort
gibt es nichts nachzurechnen. Ein glatter `quote_spent` neben einer
quantisierten Menge ist deshalb selbst schon das Symptom.

**Was dieses Skript tut:** Es berechnet für Einträge mit `dry_run: true`
den Betrag aus der tatsächlich gehaltenen Menge neu (`quantity *
Kaufpreis`) und - bei geschlossenen Positionen - daraus die realisierte
PnL (`quantity * Verkaufspreis - quote_spent`). Für simulierte Positionen
gilt damit wieder exakt `realized_pnl = quantity * (Verkauf - Kauf)`;
beide Seiten rechnen mit derselben Menge. Genau diese Invariante war
verletzt.

Sicherheitseigenschaften, bewusst so gebaut:

- **Bericht ist der Default.** Ohne `--apply` wird nichts geschrieben,
  nur gezeigt, was sich ändern würde - gleiche Haltung wie
  audit_positions.py.
- **`dry_run` wird nie geraten.** `false` bleibt unangetastet (dort ist
  `quote_spent` die Ground Truth der Börse und darf unter keinen
  Umständen überschrieben werden); ein fehlendes Feld ebenfalls, mit
  lauter Meldung - dieselbe Regel wie `[GRID-POSITION-UNKLAR]` im
  Produktivcode.
- **Idempotent per Konstruktion.** Geschrieben wird nur bei einer
  Abweichung oberhalb von TOLERANCE. Für Einträge von VOR dem K3-Fix ist
  die Neuberechnung ein No-op bis auf Fließkomma-Rauschen, das die
  Toleranz abfängt. Es braucht deshalb weder einen Datumsfilter noch eine
  "schon korrigiert"-Markierung, und ein zweiter Lauf ändert nichts.
- **Läuft nicht neben einem laufenden Bot.** Vor dem Schreiben wird
  dasselbe Lock geholt, das der jeweilige Bot hält (process_lock.py).
  Sonst überschriebe der nächste Zyklus des Grid-Bots die Korrektur mit
  seinem eigenen Stand - der wahrscheinlichste Weg, sich hier Daten zu
  zerschießen.
- **Zeitgestempelte Kopie vor dem Schreiben.** Das weicht bewusst von der
  Entscheidung in 6i ab, auf `.bak`-Kopien zu verzichten: die galt dem
  LAUFENDEN Schreibpfad, der durch atomare Writes, VM-Snapshots und Git
  abgedeckt ist. Hier schreibt ein einmaliges Skript Historie um, die
  sich aus nichts anderem rekonstruieren lässt.
- **Atomarer Write** (tmp + fsync + os.replace), wie die Ledger selbst.

Aufruf (Pfade wie bei audit_positions.py aus den Umgebungsvariablen):

    python -m dca_bot.fix_dry_run_quote_spent            # nur Bericht
    python -m dca_bot.fix_dry_run_quote_spent --apply    # schreibt

Braucht keine Binance-Zugangsdaten - es werden ausschließlich lokale
Dateien gelesen und geschrieben.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .process_lock import BotAlreadyRunning, ProcessLock

# Unterhalb dieser Abweichung gilt ein Eintrag als bereits korrekt. Deckt
# das Fließkomma-Rauschen ab, das bei vor-K3-Einträgen entsteht
# (quantity war dort exakt amount/price, die Rückrechnung trifft den
# Ausgangswert nur bis auf die letzte Stelle).
TOLERANCE = 1e-9


@dataclass
class EntryChange:
    """Eine einzelne vorgeschlagene bzw. durchgeführte Korrektur."""

    entry_id: str
    old_quote_spent: float
    new_quote_spent: float
    old_realized_pnl: float | None = None
    new_realized_pnl: float | None = None

    @property
    def quote_spent_delta(self) -> float:
        return self.new_quote_spent - self.old_quote_spent

    @property
    def flips_sign(self) -> bool:
        """PnL wechselt durch die Korrektur das Vorzeichen ins Positive."""
        if self.old_realized_pnl is None or self.new_realized_pnl is None:
            return False
        return self.old_realized_pnl < 0 <= self.new_realized_pnl


@dataclass
class LedgerReport:
    """Ergebnis für eine Ledger-Datei."""

    name: str
    path: Path
    exists: bool = True
    total_entries: int = 0
    dry_run_entries: int = 0
    real_entries_skipped: int = 0
    unknown_flag_skipped: list[str] = field(default_factory=list)
    unusable_entries: list[str] = field(default_factory=list)
    changes: list[EntryChange] = field(default_factory=list)
    written: bool = False
    backup_path: Path | None = None

    @property
    def sign_flips(self) -> int:
        return sum(1 for c in self.changes if c.flips_sign)


def _as_float(value: object) -> float | None:
    """float() ohne Exception - unlesbare Werte ergeben None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_atomic(path: Path, records: list[dict]) -> None:
    """Identisches Muster wie die Ledger selbst (siehe grid_risk._write)."""
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def correct_records(
    records: list[dict],
    report: LedgerReport,
    *,
    id_key: str,
    buy_price_key: str,
    sell_price_key: str | None,
) -> bool:
    """
    Rechnet `quote_spent` (und ggf. `realized_pnl`) aller Dry-Run-Einträge
    neu. Verändert `records` in-place und gibt zurück, ob etwas geändert
    wurde.

    Bewusst rein auf der Datenstruktur und ohne Dateizugriff - so ist die
    eigentliche Regel testbar, ohne dass ein Test Dateien anfassen muss,
    und die Datei-Ebene darüber bleibt dünn genug, um sie zu überblicken.
    """
    changed = False
    for index, record in enumerate(records):
        report.total_entries += 1
        entry_id = str(record.get(id_key, f"#{index}"))

        dry_run = record.get("dry_run")
        if dry_run is False:
            # Echter Trade: `quote_spent` kommt von der Börse
            # (cummulativeQuoteQty) und ist die Quelle der Wahrheit. Hier
            # etwas nachzurechnen wäre genau der umgekehrte Fehler.
            report.real_entries_skipped += 1
            continue
        if dry_run is not True:
            # Kein Feld oder ein unerwarteter Wert - nicht raten, melden.
            # Gleiche Haltung wie [GRID-POSITION-UNKLAR] im Produktivcode.
            report.unknown_flag_skipped.append(entry_id)
            continue

        report.dry_run_entries += 1

        quantity = _as_float(record.get("quantity"))
        buy_price = _as_float(record.get(buy_price_key))
        old_quote_spent = _as_float(record.get("quote_spent"))
        if quantity is None or buy_price is None or old_quote_spent is None:
            report.unusable_entries.append(entry_id)
            continue

        new_quote_spent = quantity * buy_price

        # Die realisierte PnL nur anfassen, wenn die Position wirklich
        # geschlossen ist UND ein brauchbarer Verkaufspreis dasteht.
        old_pnl = new_pnl = None
        sell_price = (
            _as_float(record.get(sell_price_key)) if sell_price_key else None
        )
        has_pnl = sell_price is not None and record.get("realized_pnl") is not None
        if has_pnl:
            old_pnl = _as_float(record.get("realized_pnl"))
            if old_pnl is None:
                report.unusable_entries.append(entry_id)
                continue
            new_pnl = quantity * sell_price - new_quote_spent

        quote_spent_differs = abs(new_quote_spent - old_quote_spent) > TOLERANCE
        pnl_differs = (
            old_pnl is not None
            and new_pnl is not None
            and abs(new_pnl - old_pnl) > TOLERANCE
        )
        if not quote_spent_differs and not pnl_differs:
            # Vor-K3-Eintrag (Menge war unquantisiert) oder bereits
            # korrigiert - beides ohne Handlungsbedarf.
            continue

        record["quote_spent"] = new_quote_spent
        if new_pnl is not None:
            record["realized_pnl"] = new_pnl
        report.changes.append(
            EntryChange(
                entry_id=entry_id,
                old_quote_spent=old_quote_spent,
                new_quote_spent=new_quote_spent,
                old_realized_pnl=old_pnl,
                new_realized_pnl=new_pnl,
            )
        )
        changed = True

    return changed


def process_ledger(
    name: str,
    path_str: str,
    *,
    id_key: str,
    buy_price_key: str,
    sell_price_key: str | None,
    lock_file: str | None,
    apply_changes: bool,
) -> LedgerReport:
    """Liest eine Ledger-Datei, korrigiert sie und schreibt sie ggf. zurück."""
    path = Path(path_str)
    report = LedgerReport(name=name, path=path)

    if not path.exists():
        # Wie im Produktivcode: eine FEHLENDE Datei ist der normale Fall
        # "frisches Deployment", kein Fehler.
        report.exists = False
        return report

    with path.open(encoding="utf-8") as fh:
        records = json.load(fh)
    if not isinstance(records, list):
        raise ValueError(f"{path} enthält keine Liste - Datei nicht anfassen.")

    changed = correct_records(
        records,
        report,
        id_key=id_key,
        buy_price_key=buy_price_key,
        sell_price_key=sell_price_key,
    )

    if not changed or not apply_changes:
        return report

    # Erst jetzt das Lock - ein reiner Bericht soll auch neben einem
    # laufenden Bot möglich sein.
    lock = ProcessLock(lock_file, name) if lock_file else None
    if lock is not None:
        lock.acquire()
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"{path.name}.pre-fix-{stamp}")
        shutil.copy2(path, backup)
        report.backup_path = backup
        _write_atomic(path, records)
        report.written = True
    finally:
        if lock is not None:
            lock.release()
    return report


def _print_report(report: LedgerReport, apply_changes: bool) -> None:
    print()
    print(f"=== {report.name.upper()}: {report.path} ===")
    if not report.exists:
        print("  Datei existiert nicht - übersprungen (normaler Fall bei frischem Deployment).")
        return

    print(
        f"  Einträge gesamt: {report.total_entries}  "
        f"| davon Dry-Run: {report.dry_run_entries}  "
        f"| echte (unangetastet): {report.real_entries_skipped}"
    )

    for entry_id in report.unknown_flag_skipped:
        print(
            f"  ÜBERSPRUNGEN {entry_id}: kein bzw. unklares dry_run-Feld - "
            "wird NICHT geraten, bitte manuell prüfen."
        )
    for entry_id in report.unusable_entries:
        print(
            f"  ÜBERSPRUNGEN {entry_id}: quantity/Preis/quote_spent fehlt oder "
            "ist unlesbar - keine Korrektur möglich."
        )

    if not report.changes:
        print("  Keine Abweichung gefunden - nichts zu korrigieren.")
        return

    print(f"  Korrekturen: {len(report.changes)}")
    for change in report.changes:
        print(
            f"    {change.entry_id}: quote_spent "
            f"{change.old_quote_spent:.8f} -> {change.new_quote_spent:.8f} "
            f"({change.quote_spent_delta:+.8f})"
        )
        if change.old_realized_pnl is not None:
            marker = "  <-- VORZEICHENWECHSEL" if change.flips_sign else ""
            print(
                f"      realized_pnl {change.old_realized_pnl:+.8f} -> "
                f"{change.new_realized_pnl:+.8f}{marker}"
            )

    total_delta = sum(c.quote_spent_delta for c in report.changes)
    print(f"  Summe Korrektur quote_spent: {total_delta:+.8f}")
    if report.sign_flips:
        print(
            f"  Davon {report.sign_flips} Position(en) mit falsch negativer "
            "realisierter PnL."
        )

    if report.written:
        print(f"  GESCHRIEBEN. Kopie des alten Standes: {report.backup_path}")
    elif not apply_changes:
        print("  (Bericht - es wurde nichts geschrieben. Mit --apply ausführen.)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Einmalige Korrektur von quote_spent/realized_pnl in "
            "DRY-RUN-Ledger-Einträgen (Fund vom 22.09.2026, siehe "
            "trading-bot-projekt.md 6g). Ohne --apply wird nur berichtet."
        )
    )
    parser.add_argument(
        "--dca-file",
        default=os.getenv("DCA_BOT_STATE_FILE", "data/trade_ledger.json"),
        help="Pfad zum DCA-Ledger (Default: DCA_BOT_STATE_FILE bzw. data/trade_ledger.json)",
    )
    parser.add_argument(
        "--grid-file",
        default=os.getenv("GRID_STATE_FILE", "data/grid_positions.json"),
        help="Pfad zum Grid-Ledger (Default: GRID_STATE_FILE bzw. data/grid_positions.json)",
    )
    parser.add_argument(
        "--trend-file",
        default=os.getenv("TREND_STATE_FILE", "data/trend_ledger.json"),
        help="Pfad zum Trend-Ledger (Default: TREND_STATE_FILE bzw. data/trend_ledger.json)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Änderungen tatsächlich schreiben. Ohne diese Option wird nur "
            "berichtet, was sich ändern würde."
        ),
    )
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help=(
            "Bot-Lock nicht holen. NUR verwenden, wenn sicher ist, dass kein "
            "Bot läuft (z.B. in einem Container ohne die .lock-Dateien) - "
            "sonst kann der nächste Bot-Zyklus die Korrektur überschreiben."
        ),
    )
    args = parser.parse_args(argv)

    ledgers = [
        # (Name, Pfad, ID-Feld, Kaufpreis-Feld, Verkaufspreis-Feld, Lock-Datei)
        # Der DCA-Bot verkauft nie - dort gibt es kein realized_pnl und
        # keinen Verkaufspreis, deshalb None.
        (
            "dca",
            args.dca_file,
            "timestamp",
            "price",
            None,
            os.getenv("DCA_LOCK_FILE", "data/dca_bot.lock"),
        ),
        (
            "grid",
            args.grid_file,
            "id",
            "buy_price",
            "sell_price",
            os.getenv("GRID_LOCK_FILE", "data/grid_bot.lock"),
        ),
        (
            "trend",
            args.trend_file,
            "id",
            "entry_price",
            "exit_price",
            os.getenv("TREND_LOCK_FILE", "data/trend_bot.lock"),
        ),
    ]

    print("Korrektur verfälschter quote_spent-Werte in Dry-Run-Einträgen")
    print(f"Modus: {'SCHREIBEN (--apply)' if args.apply else 'nur Bericht'}")
    print(f"Zeitpunkt: {datetime.now(timezone.utc).isoformat()}")

    reports: list[LedgerReport] = []
    for name, path_str, id_key, buy_key, sell_key, lock_file in ledgers:
        try:
            report = process_ledger(
                name,
                path_str,
                id_key=id_key,
                buy_price_key=buy_key,
                sell_price_key=sell_key,
                lock_file=None if args.no_lock else lock_file,
                apply_changes=args.apply,
            )
        except BotAlreadyRunning as exc:
            print()
            print(f"=== {name.upper()}: {path_str} ===")
            print(f"  ABGEBROCHEN: {exc}")
            print(
                "  Der Bot läuft noch. Erst stoppen, sonst überschreibt sein "
                "nächster Zyklus die Korrektur."
            )
            return 2
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print()
            print(f"=== {name.upper()}: {path_str} ===")
            print(f"  FEHLER: {type(exc).__name__}: {exc}")
            print("  Datei wurde NICHT verändert.")
            return 1
        reports.append(report)
        _print_report(report, args.apply)

    total_changes = sum(len(r.changes) for r in reports)
    total_flips = sum(r.sign_flips for r in reports)
    print()
    print("--- Zusammenfassung ---")
    print(f"Korrigierte Einträge: {total_changes} (davon {total_flips} mit Vorzeichenwechsel)")
    if total_changes and not args.apply:
        print("Nichts geschrieben. Zum Anwenden erneut mit --apply aufrufen.")
    elif not total_changes:
        print("Nichts zu tun - alle Dry-Run-Einträge sind bereits konsistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

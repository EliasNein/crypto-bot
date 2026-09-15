"""
Einmalig/bei Bedarf ausführbares Audit der offenen Positionen von Grid-
und Trend-Bot.

REIN INFORMATIV: dieses Skript liest nur, es ändert nichts an den
Ledger-Dateien und platziert keine Orders. Gedacht, um vor dem Wieder-
Freischalten pausierter Bots einen klaren Überblick zu haben, was gerade
offen ist - und vor allem, welche dieser Positionen im Dry-Run eröffnet
wurden und an der Börse deshalb gar nicht existieren.

Hintergrund (Sicherheitsreview-Punkte K1/K4, siehe
trading-bot-projekt.md Abschnitt 6g): vor dem Fix hätte ein Umschalten
von *_BOT_ENABLE_TRADING auf true dazu geführt, dass der Bot beim
nächsten Verkaufssignal versucht, Assets einer Dry-Run-Position real zu
verkaufen, die nie gekauft wurden. Seit dem Fix prüfen beide Bots das
`dry_run`-Flag des jeweiligen Ledger-Eintrags und halten den Verkauf
einer Dry-Run-Position in jedem Fall simuliert - dieses Skript macht den
Bestand vorab sichtbar.

Braucht bewusst KEINE Binance-API-Keys: es liest nur die lokalen
Ledger-Dateien und ermittelt deren Pfade direkt aus den Umgebungs-
variablen (mit denselben Defaults wie grid_config.py/trend_config.py),
statt über load_grid_config()/load_trend_config(), die ohne gültige Keys
eine Exception werfen würden.

Ausführen mit:  python -m dca_bot.audit_positions
Optional:       python -m dca_bot.audit_positions --grid-file ... --trend-file ...
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# Textmarker für einen Ledger-Eintrag ohne `dry_run`-Feld. Praktisch nur
# durch manuelles Editieren möglich (GridPosition/TrendTrade schreiben das
# Feld immer) - beide Bots verweigern für solche Einträge bewusst jeden
# Verkaufsversuch, statt den Modus zu raten, deshalb wird der Fall hier
# eigens ausgewiesen statt stillschweigend als "echt" oder "Dry-Run"
# einsortiert zu werden.
UNKNOWN = "UNBEKANNT"


def _load_records(path: Path) -> tuple[list[dict], str | None]:
    """
    Liest eine Ledger-Datei. Gibt (Einträge, Fehlertext) zurück - bei
    einem Problem eine leere Liste plus eine erklärende Meldung, statt
    eine Exception zu werfen: das Audit soll auch dann noch für die
    jeweils andere Datei etwas Sinnvolles ausgeben.
    """
    if not path.exists():
        return [], f"Datei nicht vorhanden ({path}) - noch nie ein Trade gelaufen?"
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        return [], f"Datei ist kein gültiges JSON ({path}): {exc}"
    except OSError as exc:
        return [], f"Datei nicht lesbar ({path}): {exc}"

    if not isinstance(data, list):
        return [], f"Unerwartetes Format in {path} (erwartet: JSON-Liste)."
    return [r for r in data if isinstance(r, dict)], None


def _dry_run_label(record: dict) -> str:
    value = record.get("dry_run")
    if value is None:
        return UNKNOWN
    return "DRY-RUN" if value else "ECHT"


def _open_records(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("status") == "open"]


def _print_header(title: str, path: Path) -> None:
    print()
    print("=" * 78)
    print(title)
    print(f"Datei: {path}")
    print("=" * 78)


def _print_counts(records: list[dict], open_records: list[dict]) -> None:
    print(
        f"{len(records)} Einträge insgesamt, davon {len(open_records)} offen "
        f"({len(records) - len(open_records)} geschlossen)."
    )


def _summarize_dry_run(open_records: list[dict]) -> None:
    """Zählt die offenen Positionen nach Dry-Run-Status und ordnet ein."""
    if not open_records:
        return

    labels = [_dry_run_label(r) for r in open_records]
    dry = labels.count("DRY-RUN")
    real = labels.count("ECHT")
    unknown = labels.count(UNKNOWN)

    print()
    print(f"  -> {dry} von {len(open_records)} offenen Positionen sind Dry-Run-Positionen.")
    if dry:
        print(
            "     Diese existieren an der Börse NICHT. Sie werden auch bei "
            "aktiviertem\n"
            "     Trading ausschließlich simuliert verkauft (Log-Marker "
            "[DRY-RUN-POSITION])."
        )
    if real:
        print(
            f"     {real} echte Position(en) - diese werden bei aktiviertem "
            "Trading real verkauft."
        )
    if unknown:
        print(
            f"     ACHTUNG: {unknown} Eintrag/Einträge ohne dry_run-Feld. Für "
            "diese verweigern\n"
            "     beide Bots jeden Verkauf, bis das Feld manuell ergänzt ist."
        )


def _fmt(value: Any, spec: str) -> str:
    """Formatiert einen Zahlenwert, fällt bei fehlendem/kaputtem Wert auf '?' zurück."""
    if value is None:
        return "?"
    try:
        return format(float(value), spec)
    except (TypeError, ValueError):
        return str(value)


def audit_grid(path: Path) -> None:
    _print_header("GRID-BOT - offene Positionen", path)
    records, error = _load_records(path)
    if error:
        print(error)
        return

    open_records = _open_records(records)
    _print_counts(records, open_records)
    if not open_records:
        return

    print()
    print(
        f"{'Stufe':>5}  {'Kaufpreis':>12}  {'Ziel-Verkauf':>13}  {'Menge':>14}  "
        f"{'Einsatz':>8}  {'Modus':>9}  Gekauft am"
    )
    print("-" * 110)
    for r in sorted(open_records, key=lambda x: x.get("level_index", -1)):
        print(
            f"{str(r.get('level_index', '?')):>5}  "
            f"{_fmt(r.get('buy_price'), '12.2f')}  "
            f"{_fmt(r.get('target_sell_price'), '13.2f')}  "
            f"{_fmt(r.get('quantity'), '14.8f')}  "
            f"{_fmt(r.get('quote_spent'), '8.2f')}  "
            f"{_dry_run_label(r):>9}  "
            f"{r.get('bought_at', '?')}"
        )
        print(f"{'':>5}  ID: {r.get('id', '?')}")

    _summarize_dry_run(open_records)


def audit_trend(path: Path) -> None:
    _print_header("TREND-BOT - offene Position", path)
    records, error = _load_records(path)
    if error:
        print(error)
        return

    open_records = _open_records(records)
    _print_counts(records, open_records)
    if not open_records:
        return

    if len(open_records) > 1:
        # Der Trend-Bot kennt per Design nur einen Slot (siehe TrendLedger)
        # und arbeitet mit dem ERSTEN offenen Eintrag - mehrere offene
        # Einträge wären ein echter Datenfehler, den man sehen muss.
        print(
            f"\nACHTUNG: {len(open_records)} offene Einträge, der Trend-Bot "
            "erwartet höchstens einen.\n"
            "Er würde nur den ersten verarbeiten - bitte manuell prüfen."
        )

    for r in open_records:
        print()
        print(f"  ID:              {r.get('id', '?')}")
        print(f"  Einstiegspreis:  {_fmt(r.get('entry_price'), '.2f')}")
        print(f"  Menge:           {_fmt(r.get('quantity'), '.8f')}")
        print(f"  Einsatz:         {_fmt(r.get('quote_spent'), '.2f')}")
        print(f"  Modus:           {_dry_run_label(r)}")
        print(f"  Eingestiegen am: {r.get('entry_time', '?')}")

        # Die folgenden Felder wurden erst mit dem exchange-seitigen
        # Stop-Loss eingeführt (siehe trading-bot-projekt.md 6f) - ältere
        # Ledger-Einträge haben sie gar nicht, deshalb durchgängig .get().
        order_id = r.get("stop_loss_order_id")
        if order_id:
            print(f"  Stop-Loss-Order: {order_id} (Limit {_fmt(r.get('stop_limit_price'), '.2f')})")
        elif _dry_run_label(r) == "DRY-RUN":
            print("  Stop-Loss-Order: keine (Dry-Run platziert nie eine echte Order)")
        else:
            print(
                "  Stop-Loss-Order: KEINE hinterlegt - Position ist nur "
                "software-intern abgesichert!"
            )

        uncertain = r.get("uncertain_cycles", 0)
        if uncertain:
            print(f"  ACHTUNG:         {uncertain} Zyklen mit unklarem Stop-Order-Status in Folge.")

        unprotected = r.get("unprotected_cycles", 0)
        if unprotected:
            print(
                f"  ACHTUNG:         seit {unprotected} Zyklen ohne exchange-seitige "
                "Absicherung (Neuplatzierung scheitert)."
            )

    _summarize_dry_run(open_records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Listet die offenen Positionen von Grid- und Trend-Bot samt "
            "ihrem Dry-Run-Status auf. Rein informativ - ändert nichts."
        )
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
    args = parser.parse_args()

    print("Positions-Audit (nur lesend, es wird nichts verändert)")

    audit_grid(Path(args.grid_file))
    audit_trend(Path(args.trend_file))

    print()
    print("=" * 78)
    print(
        "Hinweis: Dry-Run-Positionen werden von beiden Bots seit dem K1/K4-Fix\n"
        "niemals real verkauft, unabhängig von *_BOT_ENABLE_TRADING. Ein\n"
        "Bereinigen der Ledger-Dateien ist dafür nicht nötig."
    )
    print("=" * 78)


if __name__ == "__main__":
    main()

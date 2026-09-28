"""
Einmalig/bei Bedarf ausführbares Audit der offenen Positionen von DCA-,
Grid- und Trend-Bot, optional samt bot-übergreifendem Abgleich gegen den
tatsächlichen Kontostand.

REIN INFORMATIV: dieses Skript liest nur, es ändert nichts an den
Ledger-Dateien und platziert keine Orders. Gedacht, um vor dem Wieder-
Freischalten pausierter Bots einen klaren Überblick zu haben, was gerade
offen ist - und vor allem, welche dieser Positionen im Dry-Run eröffnet
wurden und an der Börse deshalb gar nicht existieren.

**Der bot-übergreifende Gesamtabgleich** (Stufe 2 der
Verbesserungsvorschläge, Punkt 3 - Teil B) gehört ausdrücklich HIERHER
und in keinen der Bots: Jeder Bot führt sein eigenes Ledger, und keiner
darf ein fremdes lesen - diese Trennung ist ein Grundprinzip des
Projekts. Deshalb kann auch keiner von ihnen die eigentlich
entscheidende Frage beantworten: Passt die SUMME dessen, was alle drei
als offen führen, überhaupt auf das eine geteilte Konto? Ein rein
lesendes Werkzeug darf alles einsehen und ist damit der einzige Ort, an
dem diese Frage überhaupt gestellt werden kann.

Jeder einzelne Bot prüft dagegen nur, ob SEIN Anspruch allein noch
gedeckt wäre (siehe balance_guard.py) - eine Prüfung ohne Fehlalarme,
die dafür genau den Fall nicht sieht, in dem erst die Summe zu groß
wird.

Hintergrund (Sicherheitsreview-Punkte K1/K4, siehe
trading-bot-projekt.md Abschnitt 6g): vor dem Fix hätte ein Umschalten
von *_BOT_ENABLE_TRADING auf true dazu geführt, dass der Bot beim
nächsten Verkaufssignal versucht, Assets einer Dry-Run-Position real zu
verkaufen, die nie gekauft wurden. Seit dem Fix prüfen beide Bots das
`dry_run`-Flag des jeweiligen Ledger-Eintrags und halten den Verkauf
einer Dry-Run-Position in jedem Fall simuliert - dieses Skript macht den
Bestand vorab sichtbar.

Der Ledger-Teil braucht bewusst weiterhin KEINE Binance-API-Keys: er
liest nur die lokalen Dateien und ermittelt deren Pfade direkt aus den
Umgebungsvariablen (mit denselben Defaults wie config.py/grid_config.py/
trend_config.py), statt über load_*_config(), die ohne gültige Keys eine
Exception werfen würden.

Der Kontoabgleich ist eine OPTIONALE Zugabe: Sind Zugangsdaten
vorhanden, wird er ausgeführt, sonst übersprungen - mit einem Hinweis,
was fehlt. Das Skript bleibt damit auf jedem Rechner lauffähig, auch
ohne `.env`.

Ausführen mit:  python -m dca_bot.audit_positions
Optional:       python -m dca_bot.audit_positions --grid-file ... --trend-file ...
                python -m dca_bot.audit_positions --offline
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .balance_guard import FOREIGN_ORDERS, split_locked_by_bot, tolerance_for
from .config_guard import DEFAULT_SYMBOL, ConfigError, load_api_credentials, load_use_testnet
from .symbol_guard import LEGACY_SYMBOL, REPORT_COMMAND, effective_symbol, is_legacy

load_dotenv()

# Reihenfolge der Bots in der Ausgabe - dieselbe wie in der README und im
# Projektdokument (DCA zuerst, dann Grid, dann Trend).
BOT_NAMES = ["dca", "grid", "trend"]

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


def _closed_records(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("status") == "closed"]


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


def symbol_lines(records: list[dict], configured_symbol: str | None) -> list[str]:
    """
    Welche Paare ein Ledger führt (Symbolbindung vom 28.09.2026) - und ein
    deutlicher Hinweis, wenn eines davon nicht das konfigurierte ist. Der
    Bot startet in diesem Fall nicht (symbol_guard.py); das Audit sagt,
    warum, statt die fremden Einträge still mitzuzählen oder wegzulassen.
    """
    if not records:
        return []
    counts: dict[str, int] = {}
    for record in records:
        symbol = effective_symbol(record)
        counts[symbol] = counts.get(symbol, 0) + 1
    legacy = sum(1 for r in records if is_legacy(r))
    parts = []
    for symbol, count in sorted(counts.items()):
        text = f"{symbol}: {count}"
        if symbol == LEGACY_SYMBOL and legacy:
            text += f" (davon {legacy} ohne Feld, gelten als {LEGACY_SYMBOL})"
        parts.append(text)
    lines = [f"Paare im Ledger: {', '.join(parts)}"]
    if configured_symbol is not None and any(s != configured_symbol for s in counts):
        lines.append(
            f"ACHTUNG: Das Ledger führt Einträge eines anderen Paars als konfiguriert "
            f"({configured_symbol}) - der Bot startet so nicht. Details: {REPORT_COMMAND}"
        )
    return lines


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


def _quantity_of(record: dict) -> float:
    """
    Offene Menge eines Eintrags. Bei Trend-Trades abzueglich bereits
    verbuchter Teilfuellungen der Stop-Order (`partial_exit_qty`, seit dem
    Systemcheck vom 27.09.2026) - `quantity` ist dort die Menge beim
    Einstieg. DCA- und Grid-Eintraege haben das Feld nicht.
    """
    try:
        quantity = float(record.get("quantity", 0.0) or 0.0)
        partial = float(record.get("partial_exit_qty", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(round(quantity - partial, 12), 0.0)


def _float_or_none(value: object) -> float | None:
    """
    Wie `_quantity_of`, aber ohne Ersatzwert: Hier ist der Unterschied
    zwischen "steht nicht drin" und "steht als 0.0 drin" wichtig, weil
    auf dem Ergebnis ein Vorzeichenvergleich beruht.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class NegativePnlFinding:
    """Eine geschlossene Dry-Run-Grid-Position mit negativer realisierter PnL."""

    position_id: str
    level_index: Any
    buy_price: float | None
    sell_price: float | None
    quantity: float | None
    quote_spent: float | None
    realized_pnl: float


def negative_dry_run_pnl(records: list[dict]) -> list[NegativePnlFinding]:
    """
    Sucht geschlossene Dry-Run-Positionen, deren `realized_pnl` negativ
    ist. Das ist beim Grid-Bot strukturell unmöglich - ein Treffer
    bedeutet also, dass die Daten nicht zur Logik passen.

    **Warum es unmöglich sein sollte.** Der Grid-Bot verkauft eine
    Position ausschließlich, wenn ihr individuelles Ziel erreicht ist
    (`is_sell_target_hit(price, target_sell_price)`, also
    `price >= target_sell_price`), und `target_sell_price` ist die
    nächsthöhere Grid-Stufe, liegt per Konstruktion also ÜBER dem
    Kaufpreis. Im Dry-Run gibt es keinen Fill und damit keine Gebühr, die
    etwas abziehen könnte: der Erlös ist `quantity * price`, und seit dem
    Folgefund aus K3 (22.09.2026, siehe trading-bot-projekt.md 6g) ist
    die Kostenbasis `quantity * buy_price`. Damit gilt
    `realized_pnl = quantity * (price - buy_price)` mit
    `price >= target_sell_price > buy_price` - der Wert kann nicht
    negativ werden.

    Genau diese Invariante war vor dem Fix verletzt: `quote_spent` folgte
    dem Rohbetrag statt der quantisierten Menge, wodurch geschlossene
    Positionen trotz gestiegenem Kurs im Minus landeten. Der Check ist
    die Sichtbarmachung dieses Musters - er findet sowohl noch nicht
    korrigierte Altdaten als auch eine künftige Regression derselben Art.

    **Bewusst nur Dry-Run, und bewusst nur Grid.** Bei einer ECHTEN
    Position wird die in USDT abgerechnete Verkaufsgebühr vom Erlös
    abgezogen (`net_proceeds`), ein knapp erreichtes Ziel kann dort also
    legitim im Minus enden - dasselbe Ergebnis wäre kein Befund. Und beim
    Trend-Bot ist ein Verlust der Normalfall eines Stop-Loss-Exits, dort
    existiert die Invariante überhaupt nicht. Einträge ohne
    `dry_run`-Feld bleiben ebenfalls draußen: deren Modus wird im ganzen
    Projekt nie geraten (siehe `_dry_run_label` und
    `fix_dry_run_quote_spent.py`).

    Rein informativ wie der Rest des Skripts: Es wird gemeldet, nicht
    korrigiert. Das Korrektur-Werkzeug dafür ist
    `python -m dca_bot.fix_dry_run_quote_spent`.
    """
    findings: list[NegativePnlFinding] = []
    for record in _closed_records(records):
        if record.get("dry_run") is not True:
            continue
        realized_pnl = _float_or_none(record.get("realized_pnl"))
        if realized_pnl is None or realized_pnl >= 0:
            continue
        findings.append(
            NegativePnlFinding(
                position_id=str(record.get("id", "?")),
                level_index=record.get("level_index", "?"),
                buy_price=_float_or_none(record.get("buy_price")),
                sell_price=_float_or_none(record.get("sell_price")),
                quantity=_float_or_none(record.get("quantity")),
                quote_spent=_float_or_none(record.get("quote_spent")),
                realized_pnl=realized_pnl,
            )
        )
    return findings


@dataclass(frozen=True)
class LedgerClaim:
    """
    Was EIN Bot laut seinem Ledger an Base-Asset offen hält.

    `quantity` zählt ausschließlich ECHTE offene Mengen. Dry-Run-Einträge
    und Einträge ohne `dry_run`-Feld bleiben draußen und werden separat
    gezählt - exakt dieselbe Regel, nach der die Bots selbst rechnen
    (`not r.get("dry_run", True)`). Wer hier anders zählte, bekäme eine
    Zahl, die zu keiner der Warnungen der Bots passt.
    """

    bot: str
    symbol: str
    quantity: float = 0.0
    open_entries: int = 0
    dry_run_entries: int = 0
    unknown_entries: int = 0
    error: str | None = None


def _claim_from_open_records(
    bot: str, symbol: str, open_records: list[dict], error: str | None
) -> LedgerClaim:
    """Gemeinsame Auswertung für alle drei Ledger - sie unterscheiden sich
    nur darin, WELCHE Einträge als offen gelten (siehe die Aufrufer)."""
    if error:
        return LedgerClaim(bot=bot, symbol=symbol, error=error)

    quantity = 0.0
    dry_run_entries = 0
    unknown_entries = 0
    for record in open_records:
        flag = record.get("dry_run")
        if flag is None:
            unknown_entries += 1
        elif flag:
            dry_run_entries += 1
        else:
            quantity += _quantity_of(record)

    return LedgerClaim(
        bot=bot,
        symbol=symbol,
        quantity=quantity,
        open_entries=len(open_records),
        dry_run_entries=dry_run_entries,
        unknown_entries=unknown_entries,
    )


def dca_claim(path: Path, symbol: str) -> LedgerClaim:
    """
    Der DCA-Bot **verkauft nie** - sein Ledger ist eine reine
    append-only-Liste von Käufen ohne `status`-Feld. Jeder echte Kauf ist
    damit dauerhaft Bestand, und die Summe aller echten Käufe ist das,
    was er beansprucht.

    Gezählt werden nur Einträge dieses Paars. Einträge anderer Paare
    verschwinden damit aber nicht aus dem Abgleich: `ledger_claims()`
    bildet für sie eigene Ansprüche (Symbolbindung vom 28.09.2026).
    """
    records, error = _load_records(path)
    matching = [r for r in records if effective_symbol(r) == symbol]
    return _claim_from_open_records("dca", symbol, matching, error)


def grid_claim(path: Path, symbol: str) -> LedgerClaim:
    """
    Offene Grid-Positionen dieses Paars. Einträge ohne Feld `symbol`
    stammen aus der Zeit vor der Symbolbindung und gelten als
    symbol_guard.LEGACY_SYMBOL.
    """
    records, error = _load_records(path)
    matching = [r for r in _open_records(records) if effective_symbol(r) == symbol]
    return _claim_from_open_records("grid", symbol, matching, error)


def trend_claim(path: Path, symbol: str) -> LedgerClaim:
    """Wie grid_claim, für die (höchstens eine) offene Trend-Position."""
    records, error = _load_records(path)
    matching = [r for r in _open_records(records) if effective_symbol(r) == symbol]
    return _claim_from_open_records("trend", symbol, matching, error)


def ledger_claims(bot: str, path: Path, configured_symbol: str) -> list[LedgerClaim]:
    """
    Alle Ansprüche eines Ledgers - einer je Paar, das darin offen
    vorkommt (Symbolbindung vom 28.09.2026).

    Bis dahin bekam jedes Grid- und Trend-Ledger pauschal das konfigurierte
    Symbol, und DCA-Käufe eines anderen Paars fielen still heraus. Nach
    einem Paarwechsel hätte der Abgleich damit alten BTCUSDT-Bestand
    entweder falsch zugeordnet oder gar nicht gesehen. Welches Paar ein
    Eintrag hat, steht jetzt in ihm selbst (Altbestand: LEGACY_SYMBOL).
    Führt ein Ledger gar nichts Offenes, bleibt ein leerer Anspruch unter
    dem konfigurierten Symbol, damit der Bot in der Tabelle erscheint.
    """
    records, error = _load_records(path)
    if error:
        return [LedgerClaim(bot=bot, symbol=configured_symbol, error=error)]
    relevant = records if bot == "dca" else _open_records(records)
    by_symbol: dict[str, list[dict]] = {}
    for record in relevant:
        by_symbol.setdefault(effective_symbol(record), []).append(record)
    if not by_symbol:
        by_symbol[configured_symbol] = []
    return [
        _claim_from_open_records(bot, symbol, entries, None)
        for symbol, entries in sorted(by_symbol.items())
    ]


@dataclass(frozen=True)
class AccountComparison:
    """Ergebnis des bot-übergreifenden Abgleichs für EIN Symbol."""

    symbol: str
    base_asset: str
    claims: list[LedgerClaim]
    total_claimed: float
    free: float
    locked: float
    tolerance: float
    discrepancy: bool
    locked_by_bot: dict[str, float] | None = field(default=None)

    @property
    def on_account(self) -> float:
        """Alles, was von diesem Asset da ist - frei oder gebunden."""
        return self.free + self.locked

    @property
    def difference(self) -> float:
        """Positiv = mehr auf dem Konto als beansprucht."""
        return self.on_account - self.total_claimed


def compare_with_account(
    *,
    symbol: str,
    base_asset: str,
    claims: list[LedgerClaim],
    balance: tuple[float, float],
    open_orders: list[dict] | None,
    step_size: float,
) -> AccountComparison:
    """
    Stellt die Summe aller Ledger-Ansprüche dem tatsächlichen Bestand
    gegenüber.

    Verglichen wird gegen `free + locked`, also den GESAMTEN Bestand des
    Base-Assets - nicht gegen das freie Guthaben allein. Eine Menge, die
    gerade in einer offenen Verkaufs-Order steckt, existiert ja noch; sie
    ist nur momentan nicht verkäuflich. Für die Frage "ist überhaupt
    alles da, was die drei Ledger behaupten?" zählt sie mit.

    Die Toleranz kommt aus `balance_guard.tolerance_for()` - dieselbe
    Regel, nach der die Bots selbst entscheiden, ob eine Abweichung
    berichtenswert ist. Zwei verschiedene Toleranzen für dieselbe Frage
    wären der sichere Weg zu einem Audit, das einem Bot widerspricht.

    Ein Überschuss (Konto hält MEHR als alle Ledger beanspruchen) ist
    ausdrücklich KEIN Befund: Das kann manueller Bestand sein, eine
    Altlast oder schlicht ein Bot, der hier nicht mitgezählt wird. Nur
    die andere Richtung ist ein Problem.
    """
    free, locked = balance
    total_claimed = sum(c.quantity for c in claims)
    tolerance = tolerance_for(total_claimed, step_size)

    return AccountComparison(
        symbol=symbol,
        base_asset=base_asset,
        claims=claims,
        total_claimed=total_claimed,
        free=free,
        locked=locked,
        tolerance=tolerance,
        discrepancy=total_claimed > free + locked + tolerance,
        locked_by_bot=split_locked_by_bot(open_orders, BOT_NAMES),
    )


def _fmt(value: Any, spec: str) -> str:
    """Formatiert einen Zahlenwert, fällt bei fehlendem/kaputtem Wert auf '?' zurück."""
    if value is None:
        return "?"
    try:
        return format(float(value), spec)
    except (TypeError, ValueError):
        return str(value)


def audit_dca(path: Path, symbol: str) -> None:
    """
    Der DCA-Bestand. Kürzer als die anderen beiden, weil es nichts
    "Offenes" im Sinne einer Position gibt: Der Bot verkauft nie, also
    ist die Summe aller echten Käufe der Bestand.

    Diese Zahl ist zugleich die Kostenbasis des Portfolio-Stop-Loss -
    wenn sie nicht stimmt, löst der zu spät aus (siehe
    PortfolioStopLoss in risk.py).
    """
    _print_header(f"DCA-BOT - Bestand aus echten Käufen ({symbol})", path)
    records, error = _load_records(path)
    if error:
        print(error)
        return

    matching = [r for r in records if effective_symbol(r) == symbol]
    claim = _claim_from_open_records("dca", symbol, matching, None)
    other_symbols = len(records) - len(matching)

    print(
        f"{len(records)} Einträge insgesamt, davon {len(matching)} für {symbol}"
        + (f" ({other_symbols} für andere Symbole)." if other_symbols else ".")
    )
    for line in symbol_lines(records, symbol):
        print(line)
    if not matching:
        return

    real_entries = claim.open_entries - claim.dry_run_entries - claim.unknown_entries
    total_spent = 0.0
    for r in matching:
        if r.get("dry_run") is False:
            try:
                total_spent += float(r.get("quote_spent", 0.0) or 0.0)
            except (TypeError, ValueError):
                pass

    print()
    print(f"  Echte Käufe:      {real_entries}")
    print(f"  Menge gesamt:     {claim.quantity:.8f}")
    print(f"  Eingesetzt:       {total_spent:.2f}")
    if claim.quantity > 0:
        print(f"  Ø Einstandspreis: {total_spent / claim.quantity:.2f}")
    if claim.dry_run_entries:
        print(
            f"  {claim.dry_run_entries} simulierte Käufe - zählen nicht als "
            "Bestand (existieren an der Börse nicht)."
        )
    if claim.unknown_entries:
        print(
            f"  ACHTUNG: {claim.unknown_entries} Eintrag/Einträge ohne "
            "dry_run-Feld, nicht mitgezählt."
        )


def _print_negative_pnl_findings(findings: list[NegativePnlFinding]) -> None:
    """
    Gibt die Treffer des Invarianten-Checks aus (siehe
    `negative_dry_run_pnl` für die Begründung, warum das gar nicht
    vorkommen kann). Rein informativ - das Skript ändert nichts.
    """
    if not findings:
        return

    print()
    print(
        f"  *** BEFUND: {len(findings)} geschlossene Dry-Run-Position(en) mit "
        "negativer realisierter PnL. ***"
    )
    for f in findings:
        print(
            f"    Stufe {str(f.level_index):>3}  "
            f"Kauf {_fmt(f.buy_price, '.2f')} -> Verkauf {_fmt(f.sell_price, '.2f')}  "
            f"Menge {_fmt(f.quantity, '.8f')}  Einsatz {_fmt(f.quote_spent, '.2f')}  "
            f"realisiert {f.realized_pnl:+.8f}"
        )
        print(f"      ID: {f.position_id}")
    print(
        "\n  Der Grid-Bot verkauft nur, wenn der Preis das Ziel der Position\n"
        "  erreicht - und das ist die nächsthöhere Grid-Stufe, liegt also über\n"
        "  dem Kaufpreis. Im Dry-Run gibt es keine Gebühr, die etwas abziehen\n"
        "  könnte. Ein Minus ist hier deshalb kein schlechter Trade, sondern\n"
        "  ein Datenfehler.\n"
        "  Bekannte Ursache: der Folgefund aus K3 (siehe trading-bot-projekt.md\n"
        "  Abschnitt 6g) - `quote_spent` folgte im Dry-Run dem Rohbetrag statt\n"
        "  der quantisierten Menge. Korrigieren mit:\n"
        "      python -m dca_bot.fix_dry_run_quote_spent          # nur Bericht\n"
        "      python -m dca_bot.fix_dry_run_quote_spent --apply  # schreibt"
    )


def audit_grid(path: Path, symbol: str | None = None) -> None:
    _print_header("GRID-BOT - offene Positionen", path)
    records, error = _load_records(path)
    if error:
        print(error)
        return

    open_records = _open_records(records)
    _print_counts(records, open_records)
    for line in symbol_lines(records, symbol):
        print(line)

    # Bewusst VOR dem Abbruch bei "nichts offen": Der Check gilt
    # geschlossenen Positionen, und ein Ledger ohne eine einzige offene
    # Position ist gerade der Fall, in dem er etwas zu sagen hat.
    _print_negative_pnl_findings(negative_dry_run_pnl(records))

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


def audit_trend(path: Path, symbol: str | None = None) -> None:
    _print_header("TREND-BOT - offene Position", path)
    records, error = _load_records(path)
    if error:
        print(error)
        return

    open_records = _open_records(records)
    _print_counts(records, open_records)
    for line in symbol_lines(records, symbol):
        print(line)
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
        if r.get("partial_exit_qty"):
            print(
                f"  Teilfüllung:     {_fmt(r.get('partial_exit_qty'), '.8f')} bereits "
                f"verkauft, offen {_quantity_of(r):.8f}"
            )
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


@dataclass(frozen=True)
class _ReadOnlyClientConfig:
    """
    Das Minimum, das `TradingClient.__init__` liest - mehr braucht dieses
    Skript nicht.

    `pending_orders_file` ist bewusst LEER: Damit legt der Client gar
    keinen Pending-Store an, und seine `place_*`-Methoden weisen jede
    Order aktiv zurück (siehe binance_client.py). Die Zusage "dieses
    Skript platziert keine Orders" hängt damit nicht an Disziplin beim
    Programmieren, sondern ist strukturell abgesichert.
    """

    api_key: str
    api_secret: str
    use_testnet: bool
    bot_name: str = "audit"
    pending_orders_file: str = ""


def _build_read_only_client():
    """
    Baut einen nur lesenden Binance-Client, falls Zugangsdaten vorhanden
    sind. Gibt `(client, None)` oder `(None, Grund)` zurück.

    Fehlende oder unbrauchbare Zugangsdaten sind hier ausdrücklich KEIN
    Fehler, sondern der dokumentierte Normalfall auf einem Rechner ohne
    `.env` - das Skript soll dort weiterhin seinen Ledger-Teil leisten.
    """
    try:
        use_testnet = load_use_testnet()
        api_key, api_secret = load_api_credentials(use_testnet=use_testnet)
    except ConfigError as exc:
        return None, str(exc)

    # Import bewusst erst hier: `binance_client` zieht `python-binance`
    # nach, und der Ledger-Teil dieses Skripts soll auch dann laufen,
    # wenn die Abhängigkeit fehlt.
    from .binance_client import TradingClient

    try:
        client = TradingClient(
            _ReadOnlyClientConfig(
                api_key=api_key, api_secret=api_secret, use_testnet=use_testnet
            )
        )
    except Exception as exc:  # pragma: no cover - nur bei kaputter Umgebung
        return None, f"Binance-Client nicht aufbaubar: {type(exc).__name__}: {exc}"
    return client, None


@dataclass(frozen=True)
class BaseAssetGroup:
    """Alle Ansprüche auf EIN Base-Asset - über alle Paare hinweg."""

    base_asset: str
    symbols: tuple[str, ...]
    claims: list[LedgerClaim]
    step_size: float


def group_claims_by_base_asset(
    client, claims: list[LedgerClaim]
) -> tuple[list[BaseAssetGroup], list[str]]:
    """
    Gruppiert die Ansprüche nach dem Base-Asset ihres Paars (aus
    exchangeInfo) und gibt die Gruppen plus eine Liste von Problemen
    zurück.

    **Warum nach Base-Asset und nicht nach Symbol** (Symbolbindung vom
    28.09.2026): BTCUSDT und BTCEUR handeln dasselbe BTC auf demselben
    Konto. Bis dahin wurde nach Symbol gruppiert - mit DCA auf BTCUSDT
    (0,3 BTC) und Grid auf BTCEUR (0,2 BTC) hätte jede Gruppe für sich
    gegen die 0,4 BTC des Kontos gedeckt ausgesehen, und der Fehlbetrag von
    0,1 BTC wäre unsichtbar geblieben. Die Summe über Paare mit
    verschiedenen Base-Assets bleibt dagegen weiterhin getrennt - sie
    addierte verschiedene Assets.

    Ist für ein Paar keine Handelsregel abrufbar, fehlen seine Ansprüche in
    ihrer Gruppe - das steht dann als Problem in der Liste, damit ein
    "In Ordnung" nicht auf einer unvollständigen Summe beruht.
    """
    rules_by_symbol = {}
    problems: list[str] = []
    for symbol in sorted({c.symbol for c in claims}):
        try:
            rules_by_symbol[symbol] = client.get_symbol_trading_rules(symbol)
        except Exception as exc:
            affected = ", ".join(sorted(c.bot for c in claims if c.symbol == symbol))
            problems.append(
                f"Handelsregeln für {symbol} nicht abrufbar ({type(exc).__name__}) - die "
                f"Ansprüche in {symbol} ({affected}) fehlen im Abgleich, er ist UNVOLLSTÄNDIG."
            )

    grouped: dict[str, dict] = {}
    for claim in claims:
        rules = rules_by_symbol.get(claim.symbol)
        if rules is None:
            continue
        group = grouped.setdefault(rules.base_asset, {"symbols": set(), "claims": [], "step": 0.0})
        group["symbols"].add(claim.symbol)
        group["claims"].append(claim)
        group["step"] = max(group["step"], rules.step_size)

    groups = [
        BaseAssetGroup(base, tuple(sorted(g["symbols"])), g["claims"], g["step"])
        for base, g in sorted(grouped.items())
    ]
    return groups, problems


def compare_group(client, group: BaseAssetGroup) -> AccountComparison | None:
    """
    Der Abgleich für eine Gruppe: Guthaben EINMAL je Base-Asset, offene
    Orders aus ALLEN Paaren der Gruppe (Binance liefert sie nur je Symbol,
    gebunden wird aber dasselbe Asset). `None`, wenn das Guthaben nicht
    abrufbar ist - kein Befund. Scheitert der Abruf der Orders für eines
    der Paare, bleibt die Zuordnung der gebundenen Menge unbekannt; das
    Urteil über die Deckung kommt trotzdem zustande.
    """
    balance = client.get_asset_balance(group.base_asset)
    if balance is None:
        return None
    open_orders: list[dict] | None = []
    for symbol in group.symbols:
        orders = client.get_open_orders(symbol)
        if orders is None:
            open_orders = None
            break
        open_orders.extend(orders)
    return compare_with_account(
        symbol=" + ".join(group.symbols),
        base_asset=group.base_asset,
        claims=group.claims,
        balance=balance,
        open_orders=open_orders,
        step_size=group.step_size,
    )


def audit_account(client, claims: list[LedgerClaim]) -> None:
    """
    Der bot-übergreifende Gesamtabgleich - das, was kein einzelner Bot
    leisten kann (siehe Modul-Docstring). Gruppiert nach Base-Asset, siehe
    group_claims_by_base_asset().
    """
    groups, problems = group_claims_by_base_asset(client, claims)
    for problem in problems:
        print()
        print(f"ACHTUNG: {problem}")

    for group in groups:
        print()
        print("=" * 78)
        pairs = "; ".join(
            f"{symbol}: {', '.join(c.bot for c in group.claims if c.symbol == symbol)}"
            for symbol in group.symbols
        )
        print(f"KONTOABGLEICH {group.base_asset} ({pairs}) - alle Bots gegen den Bestand")
        print("=" * 78)

        comparison = compare_group(client, group)
        if comparison is None:
            print(
                f"Guthaben für {group.base_asset} nicht abrufbar - Abgleich "
                "übersprungen. (Ein gescheiterter Abruf ist keine Aussage "
                "über das Konto.)"
            )
            continue
        _print_comparison(comparison)


def _print_comparison(c: AccountComparison) -> None:
    print()
    print(f"{'Bot':<8} {'Paar':<10} {'laut Ledger offen':>20}  Hinweis")
    print("-" * 78)
    for claim in c.claims:
        if claim.error:
            print(f"{claim.bot:<8} {claim.symbol:<10} {'?':>20}  {claim.error}")
            continue
        notes = []
        if claim.dry_run_entries:
            notes.append(f"{claim.dry_run_entries} Dry-Run (zählt nicht)")
        if claim.unknown_entries:
            notes.append(f"{claim.unknown_entries} ohne dry_run-Feld (zählt nicht)")
        print(f"{claim.bot:<8} {claim.symbol:<10} {claim.quantity:>20.8f}  {', '.join(notes)}")
    print("-" * 78)
    print(f"{'SUMME':<8} {'':<10} {c.total_claimed:>20.8f}")

    print()
    print(f"Tatsächlich auf dem Konto ({c.base_asset}):")
    print(f"  frei:            {c.free:.8f}")
    print(f"  gebunden:        {c.locked:.8f}")
    print(f"  gesamt:          {c.on_account:.8f}")

    if c.locked_by_bot is None:
        print(
            "\n  Offene Orders nicht abrufbar - die gebundene Menge konnte "
            "keinem Bot zugeordnet werden."
        )
    elif c.locked > 0:
        print()
        print("  Gebundene Menge nach Verursacher (über das clientOrderId-Präfix):")
        for name in BOT_NAMES + [FOREIGN_ORDERS]:
            amount = c.locked_by_bot.get(name, 0.0)
            if amount > 0:
                print(f"    {name:<16} {amount:.8f}")

    print()
    if c.discrepancy:
        print("  *** BEFUND: Die Ledger beanspruchen mehr, als da ist. ***")
        print(
            f"  Fehlbetrag: {-c.difference:.8f} {c.base_asset} "
            f"(Toleranz: {c.tolerance:.8f})"
        )
        print(
            "  Mögliche Ursachen: ein manueller Trade über die Börsen-"
            "Oberfläche, ein\n"
            "  Bot, der auf einem anderen Rechner mit demselben Konto "
            "läuft, oder ein\n"
            "  Verkauf, der nicht ins Ledger zurückgeschrieben wurde. Die "
            "Ledger-Dateien\n"
            "  NICHT blind anpassen - erst klären, welche Seite recht hat."
        )
    else:
        print(f"  In Ordnung: Der Bestand deckt alle Ledger-Ansprüche ab.")
        if c.difference > c.tolerance:
            print(
                f"  Hinweis: {c.difference:.8f} {c.base_asset} mehr auf dem "
                "Konto als beansprucht.\n"
                "  Das ist kein Befund - z.B. manueller Bestand oder eine "
                "Altlast."
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Listet den Bestand von DCA-, Grid- und Trend-Bot samt "
            "Dry-Run-Status auf und gleicht ihn - falls API-Keys "
            "vorhanden sind - bot-übergreifend gegen den tatsächlichen "
            "Kontostand ab. Rein informativ, ändert nichts."
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
        "--offline",
        action="store_true",
        help=(
            "Nur die Ledger-Dateien auswerten, keinen Kontoabgleich "
            "versuchen (auch wenn API-Keys vorhanden sind)."
        ),
    )
    args = parser.parse_args()

    # Die Symbole kommen aus denselben Variablen und Defaults wie in den
    # Configs. Grid- und Trend-Ledger tragen selbst KEIN Symbol-Feld
    # (siehe GridPosition/TrendTrade) - ihr Symbol ist eine Eigenschaft
    # der Konfiguration, nicht des Eintrags.
    dca_symbol = os.getenv("DCA_SYMBOL", DEFAULT_SYMBOL).strip()
    grid_symbol = os.getenv("GRID_SYMBOL", DEFAULT_SYMBOL).strip()
    trend_symbol = os.getenv("TREND_SYMBOL", DEFAULT_SYMBOL).strip()

    print("Positions-Audit (nur lesend, es wird nichts verändert)")

    audit_dca(Path(args.dca_file), dca_symbol)
    audit_grid(Path(args.grid_file), grid_symbol)
    audit_trend(Path(args.trend_file), trend_symbol)

    # Seit der Symbolbindung (28.09.2026) je Paar, das im Ledger offen
    # vorkommt - nicht mehr pauschal das konfigurierte Symbol.
    claims = (
        ledger_claims("dca", Path(args.dca_file), dca_symbol)
        + ledger_claims("grid", Path(args.grid_file), grid_symbol)
        + ledger_claims("trend", Path(args.trend_file), trend_symbol)
    )

    if args.offline:
        print()
        print("=" * 78)
        print("Kontoabgleich übersprungen (--offline).")
        print("=" * 78)
    else:
        client, reason = _build_read_only_client()
        if client is None:
            print()
            print("=" * 78)
            print("KONTOABGLEICH ÜBERSPRUNGEN")
            print("=" * 78)
            print(f"Grund: {reason}")
            print(
                "\nDer bot-übergreifende Abgleich braucht lesenden Zugriff auf "
                "das Konto\n(Guthaben + offene Orders). Ohne ihn zeigt dieses "
                "Skript nur, was die\nLedger-Dateien behaupten - nicht, ob es "
                "auch da ist. Zum Aktivieren\nBINANCE_API_KEY/"
                "BINANCE_API_SECRET in der .env setzen."
            )
        else:
            audit_account(client, claims)

    print()
    print("=" * 78)
    print(
        "Hinweis: Dry-Run-Positionen werden von Grid und Trend seit dem "
        "K1/K4-Fix\n"
        "niemals real verkauft, unabhängig von *_BOT_ENABLE_TRADING. Ein\n"
        "Bereinigen der Ledger-Dateien ist dafür nicht nötig."
    )
    print("=" * 78)


if __name__ == "__main__":
    main()

"""
Backtesting für die Spot-Grid-Trading-Strategie.

Nutzt dieselbe Entscheidungslogik (grid_signals.py) wie die Live-Strategie
(grid_strategy.py) - siehe dort für die Begründung, warum das wichtig ist
(gleiches Muster wie beim Trend-Following-Backtest, trend_backtest.py).
Nutzt außerdem denselben historischen Daten-Loader wie der DCA-Backtest
(backtest.py) und dieselben drei Referenz-Zeiträume wie der Trend-Backtest
(trend_backtest.py), damit die Ergebnisse über alle drei Strategien
vergleichbar bleiben.

Auflösung: STUNDENKERZEN ("1h"), nicht Tageskerzen. Der Live-Bot prüft
alle GRID_INTERVAL_MINUTES (Default 5 Minuten) auf durchquerte Stufen -
mit Tageskerzen würden die meisten Grid-Durchquerungen innerhalb eines
Tages komplett unsichtbar bleiben und die Strategie systematisch
schlechter aussehen lassen, als sie ist. Stundenkerzen sind ein
praktikabler Kompromiss (vertretbare Datenmenge, ca. 8.760 Kerzen/Jahr),
bleiben aber immer noch gröber als die Live-Auflösung - schnelle
Durchquerungen mehrerer Stufen innerhalb einer Stunde werden weiterhin
wie eine einzige Bewegung behandelt. Das Ergebnis ist daher eine
Näherung, kein exaktes Abbild des Live-Verhaltens.

Recherche-Hintergrund (siehe trading-bot-projekt.md, Chen/Chen/Jang,
arXiv 2506.11921): Der Erwartungswert von Grid-Trading ist vor Gebühren
mathematisch null - der Sinn der Strategie liegt in der einfachen,
latenzunkritischen Umsetzung in Seitwärtsmärkten, nicht in überlegener
Rendite. Dieser Backtest prüft genau das: Funktioniert die Strategie in
einem Seitwärtsmarkt wie erwartet, und wie stark schadet ein Trendbruch
(Bärenmarkt) trotz Stop-Loss?

Parameter sind unveränderte Live-Defaults (grid_config.py), NICHT gegen
die unten getesteten Zeiträume optimiert - gleiches Prinzip wie beim
Trend-Backtest.

WICHTIGER UNTERSCHIED zu DCA/Trend: Deren Parameter (Kaufbetrag in USD,
EMA-Perioden, Prozent-Abstände) sind skaleninvariant - sie sind bei jedem
Kursniveau gleich sinnvoll. Die Grid-Spanne (lower_limit/upper_limit) ist
dagegen ein ABSOLUTER Preisbereich in USD, an das heutige Kursniveau
(2026) gekoppelt. Gegen 2021-2023-Daten getestet (BTC damals deutlich
niedriger) würde die unveränderte Live-Spanne in JEDEM der drei
Zeiträume sofort außerhalb liegen -> 0 Trades, sofortiger Trendbruch-
Stop-Loss. Das ist selbst ein reales, meldenswertes Ergebnis (die
heutige Config hätte damals nie gegriffen), sagt aber nichts über die
Crossing-/PnL-Mechanik der Strategie selbst aus.

Deshalb läuft standardmäßig zusätzlich ein klar gekennzeichneter
ANALYSE-Modus: Die Spanne wird (nur für diese Analyse, NICHT das Live-
Verhalten) symmetrisch um den tatsächlichen Startpreis der jeweiligen
Periode skaliert - gleiche relative Breite (upper/lower-Verhältnis) und
gleicher Grid-Abstand wie in der Live-Config, nur der Anker verschoben.
Das entspricht genau dem realen Vorgehen beim Aufsetzen des Live-Grids
("symmetrisch um den aktuellen Preis", siehe trading-bot-projekt.md) -
nur eben rückblickend für historische Startpreise statt für heute.

Ausführen mit:  python -m dca_bot.grid_backtest
(ohne Argumente: läuft automatisch über drei Referenz-Zeiträume -
2022 Bärenmarkt, 2023 Erholung, 2021 Seitwärts/Konsolidierung)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime

from .backtest import fetch_historical_klines
from .grid_signals import (
    compute_grid_levels,
    find_triggered_buy_levels,
    is_sell_target_hit,
    is_trend_break_stop_loss_hit,
)
from .trend_backtest import DEFAULT_PERIODS, compute_max_drawdown


@dataclass
class GridBacktestResult:
    symbol: str
    start_date: str
    end_date: str
    lower_limit: float
    upper_limit: float
    grid_spacing_pct: float
    amount_per_level: float
    stop_loss_pct: float
    num_levels: int
    num_trades: int  # abgeschlossene Kauf-Verkauf-Paare (realisiert)
    realized_pnl: float
    open_positions_unrealized_pnl: float
    num_open_positions_at_end: int
    max_drawdown: float
    buy_and_hold_return_pct: float
    stop_loss_paused_at_end: bool
    trade_log: list[dict] = field(default_factory=list)


def run_grid_backtest(
    klines: list[dict],
    symbol: str,
    lower_limit: float,
    upper_limit: float,
    grid_spacing_pct: float,
    amount_per_level: float,
    stop_loss_pct: float,
    fee_pct: float,
) -> GridBacktestResult:
    """
    Simuliert die exakt gleiche Entscheidungslogik wie die Live-Strategie
    (find_triggered_buy_levels() + is_sell_target_hit() +
    is_trend_break_stop_loss_hit() aus grid_signals.py) über historische
    Kerzen. Positionen werden rein im Speicher verwaltet (kein Ledger-
    File, kein echter Client) - analog zum in-memory `open_trade` im
    Trend-Backtest, hier aber als Liste mehrerer gleichzeitig offener
    Positionen (eine je Grid-Stufe).
    """
    if not klines:
        raise ValueError("Keine Kursdaten zum Backtesten vorhanden.")

    levels = compute_grid_levels(lower_limit, upper_limit, grid_spacing_pct)

    open_positions: dict[int, dict] = {}  # level_index -> Position
    stop_loss_paused = False
    last_seen_price: float | None = None
    realized_total = 0.0
    trade_log: list[dict] = []
    equity_curve: list[float] = []
    first_price = klines[0]["close_price"]
    last_price = klines[-1]["close_price"]

    for candle in klines:
        price = candle["close_price"]
        date_str = datetime.fromtimestamp(candle["open_time"] / 1000).strftime("%Y-%m-%d %H:%M")

        # Reihenfolge identisch zu GridTradingStrategy.execute_once(): erst
        # Stop-Loss-Status ermitteln, dann Verkäufe (unabhängig davon),
        # dann - falls kein Stop-Loss aktiv - Käufe, zuletzt Referenzpreis
        # aktualisieren.
        if not stop_loss_paused and is_trend_break_stop_loss_hit(lower_limit, stop_loss_pct, price):
            stop_loss_paused = True

        for level_index in list(open_positions.keys()):
            position = open_positions[level_index]
            if not is_sell_target_hit(price, position["target_sell_price"]):
                continue
            proceeds = position["quantity"] * price * (1 - fee_pct / 100)
            pnl = proceeds - position["quote_spent"]
            realized_total += pnl
            trade_log.append(
                {
                    "level_index": level_index,
                    "buy_date": position["buy_date"],
                    "buy_price": position["buy_price"],
                    "sell_date": date_str,
                    "sell_price": price,
                    "pnl": pnl,
                }
            )
            del open_positions[level_index]

        if not stop_loss_paused:
            occupied_levels = set(open_positions.keys())
            triggered_levels = find_triggered_buy_levels(levels, last_seen_price, price, occupied_levels)
            for level_index in triggered_levels:
                quantity = (amount_per_level * (1 - fee_pct / 100)) / price
                open_positions[level_index] = {
                    "buy_price": price,
                    "buy_date": date_str,
                    "target_sell_price": levels[level_index + 1],
                    "quantity": quantity,
                    "quote_spent": amount_per_level,
                }

        last_seen_price = price

        unrealized = sum(
            p["quantity"] * price - p["quote_spent"] for p in open_positions.values()
        )
        equity_curve.append(realized_total + unrealized)

    open_positions_unrealized_pnl = sum(
        p["quantity"] * last_price - p["quote_spent"] for p in open_positions.values()
    )

    buy_and_hold_return_pct = (last_price - first_price) / first_price * 100

    return GridBacktestResult(
        symbol=symbol,
        start_date=datetime.fromtimestamp(klines[0]["open_time"] / 1000).strftime("%Y-%m-%d"),
        end_date=datetime.fromtimestamp(klines[-1]["open_time"] / 1000).strftime("%Y-%m-%d"),
        lower_limit=lower_limit,
        upper_limit=upper_limit,
        grid_spacing_pct=grid_spacing_pct,
        amount_per_level=amount_per_level,
        stop_loss_pct=stop_loss_pct,
        num_levels=len(levels),
        num_trades=len(trade_log),
        realized_pnl=realized_total,
        open_positions_unrealized_pnl=open_positions_unrealized_pnl,
        num_open_positions_at_end=len(open_positions),
        max_drawdown=compute_max_drawdown(equity_curve),
        buy_and_hold_return_pct=buy_and_hold_return_pct,
        stop_loss_paused_at_end=stop_loss_paused,
        trade_log=trade_log,
    )


def scale_grid_range(start_price: float, lower_limit: float, upper_limit: float) -> tuple[float, float]:
    """
    NUR für die Analyse (siehe Modul-Docstring), NICHT das Live-Verhalten:
    verschiebt die Grid-Spanne so, dass sie symmetrisch (geometrisches
    Mittel) um `start_price` liegt, bei gleichbleibendem Breiten-
    Verhältnis (upper_limit / lower_limit) wie in der Live-Config.
    """
    ratio = upper_limit / lower_limit
    half_ratio = ratio ** 0.5
    return start_price / half_ratio, start_price * half_ratio


def print_report(result: GridBacktestResult, label: str, scaled: bool = False) -> None:
    print(f"\n{'=' * 60}")
    print(f"Grid-Trading-Backtest: {result.symbol} - {label}")
    print(f"Zeitraum: {result.start_date} bis {result.end_date}")
    print(
        f"Parameter: Grid {result.lower_limit:.2f}-{result.upper_limit:.2f} "
        f"({result.num_levels} Stufen, Abstand {result.grid_spacing_pct}%), "
        f"{result.amount_per_level:.2f}/Stufe, Stop-Loss-Puffer {result.stop_loss_pct}%"
    )
    print(f"{'=' * 60}")
    print(f"Anzahl abgeschlossener Trades: {result.num_trades}")
    print(f"Realisierter Gewinn/Verlust:   {result.realized_pnl:+,.2f}")
    print(
        f"Offene Positionen am Ende:     {result.num_open_positions_at_end} "
        f"(unrealisiert: {result.open_positions_unrealized_pnl:+,.2f})"
    )
    print(f"Max. Drawdown:                 {result.max_drawdown:,.2f}")
    print(f"{'-' * 60}")
    print(f"Vergleich - Buy & Hold über denselben Zeitraum: {result.buy_and_hold_return_pct:+.2f}%")
    print(f"{'=' * 60}")

    if result.stop_loss_paused_at_end:
        print(
            "WICHTIG: Der Trendbruch-Stop-Loss war am Ende dieses Zeitraums\n"
            "ausgelöst/pausiert (kein automatischer Reset) - neue Käufe wären\n"
            "ohne manuellen Reset für den Rest des Zeitraums blockiert geblieben.\n"
            "Bereits offene Positionen wurden weiterhin normal verkauft. Das ist\n"
            "genau das reale Verhalten des Live-Bots."
        )
    if scaled:
        print(
            "Hinweis: ANALYSE-MODUS - die Grid-Spanne wurde nur für diesen Lauf\n"
            "symmetrisch um den tatsächlichen Startpreis dieser Periode skaliert\n"
            "(gleiches Breiten-Verhältnis/Abstand wie die Live-Config). Das ist\n"
            "NICHT das Verhalten des Live-Bots (der nutzt eine feste, an das\n"
            "heutige Kursniveau gekoppelte Spanne) - dient nur dazu, die Crossing-/\n"
            "PnL-Mechanik selbst unter diesem Marktregime zu prüfen. Kerzen-\n"
            "auflösung: 1h (siehe Modul-Docstring) - gröber als die Live-Prüfung\n"
            "alle paar Minuten, das Ergebnis ist eine Näherung."
        )
    else:
        print(
            "Hinweis: Parameter sind unveränderte Live-Defaults (grid_config.py),\n"
            "nicht gegen diesen Zeitraum optimiert. Kerzenauflösung: 1h (siehe\n"
            "Modul-Docstring) - gröber als die Live-Prüfung alle paar Minuten,\n"
            "das Ergebnis ist eine Näherung."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Grid-Trading-Strategie-Backtest")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--start", default=None, help="Format: YYYY-MM-DD (überschreibt die 3 Standard-Zeiträume)")
    parser.add_argument("--end", default=None, help="Format: YYYY-MM-DD")
    parser.add_argument("--lower-limit", type=float, default=70000.0)
    parser.add_argument("--upper-limit", type=float, default=90000.0)
    parser.add_argument("--spacing-pct", type=float, default=1.5)
    parser.add_argument("--amount", type=float, default=15.0, help="Betrag pro Grid-Stufe (Quote-Währung)")
    parser.add_argument("--stop-loss-pct", type=float, default=15.0)
    parser.add_argument("--fee-pct", type=float, default=0.1, help="Gebühr pro Seite (Kauf/Verkauf) in %%")
    parser.add_argument(
        "--no-scaled-analysis",
        action="store_true",
        help=(
            "Überspringt den zusätzlichen ANALYSE-Modus mit periodenspezifisch "
            "skalierter Grid-Spanne (siehe Modul-Docstring) - nur das literale "
            "Ergebnis mit den unveränderten Live-Parametern anzeigen."
        ),
    )
    args = parser.parse_args()

    if args.start and args.end:
        periods = [(f"{args.start} bis {args.end}", args.start, args.end)]
    else:
        periods = DEFAULT_PERIODS

    for label, start, end in periods:
        print(f"\n\n{'#' * 60}")
        print(f"# Zeitraum: {label}")
        print(f"{'#' * 60}")

        print(f"Lade historische Stundenkerzen für {args.symbol} ({start} bis {end}) ...")
        klines = fetch_historical_klines(args.symbol, "1h", start, end)
        print(f"{len(klines)} Stundenkerzen geladen.")

        if not klines:
            print(f"Übersprungen: keine Kerzen im Zeitraum ab {start} gefunden.")
            continue

        try:
            literal_result = run_grid_backtest(
                klines,
                symbol=args.symbol,
                lower_limit=args.lower_limit,
                upper_limit=args.upper_limit,
                grid_spacing_pct=args.spacing_pct,
                amount_per_level=args.amount,
                stop_loss_pct=args.stop_loss_pct,
                fee_pct=args.fee_pct,
            )
            print_report(literal_result, f"{label} - Live-Parameter (absolute Spanne)")
        except ValueError as exc:
            print(f"Übersprungen (Live-Parameter): {exc}")

        if args.no_scaled_analysis:
            continue

        start_price = klines[0]["close_price"]
        scaled_lower, scaled_upper = scale_grid_range(start_price, args.lower_limit, args.upper_limit)
        try:
            scaled_result = run_grid_backtest(
                klines,
                symbol=args.symbol,
                lower_limit=scaled_lower,
                upper_limit=scaled_upper,
                grid_spacing_pct=args.spacing_pct,
                amount_per_level=args.amount,
                stop_loss_pct=args.stop_loss_pct,
                fee_pct=args.fee_pct,
            )
            print_report(scaled_result, f"{label} - ANALYSE: Spanne skaliert auf Periodenstart", scaled=True)
        except ValueError as exc:
            print(f"Übersprungen (skalierte Analyse): {exc}")


if __name__ == "__main__":
    main()

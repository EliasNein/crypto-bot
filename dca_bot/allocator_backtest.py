"""
Backtesting für den Kapital-Allocator (stufenlose Umschichtung zwischen
DCA-Bot und Trend-Following-Bot je nach Trendstärke).

Nutzt dieselbe Entscheidungslogik wie die Live-Komponenten - keine
Doppelimplementierung:
- `TrendSignalGenerator`, `decide_action`, `is_stop_loss_hit` aus
  trend_signals.py für die Trend-Bot-Seite (identisch zu trend_backtest.py)
- `derive_trend_strength`, `compute_target_fraction`, `smooth_fraction`
  aus allocator_signals.py für die Allocator-Seite (identisch zu allocator.py)
- `fetch_historical_klines` aus backtest.py für die historischen Daten
- `run_dca_backtest` aus backtest.py und `run_trend_backtest` aus
  trend_backtest.py für die isolierten Vergleichswerte

Läuft über dieselben drei Referenz-Zeiträume wie DCA- und Trend-Backtest
(DEFAULT_PERIODS aus trend_backtest.py), damit die Ergebnisse
vergleichbar bleiben.

WICHTIG zur Glättungsperiode: Der Live-Allocator glättet über
ALLOCATOR_SMOOTHING_PERIOD Zyklen à ALLOCATOR_INTERVAL_MINUTES (Default:
24 Zyklen à 60 Minuten). Dieser Backtest arbeitet auf Tageskerzen - eine
"Glättungsperiode" hier ist ein eigener, separat konfigurierbarer
Tages-Parameter (`--smoothing-period-days`), KEINE Einheiten-Umrechnung
der Live-Zyklen. Das ist eine bewusste Näherung (gleiches Prinzip wie
die 1h-Kerzenauflösung im Grid-Backtest), kein exaktes Abbild.

Parameter sind unveränderte Live-Defaults, NICHT gegen die unten
getesteten Zeiträume optimiert - gleiches Prinzip wie bei DCA-/Trend-Backtest.

Ausführen mit:  python -m dca_bot.allocator_backtest
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime

from .allocator_signals import (
    MIN_EFFECTIVE_QUOTE_AMOUNT,
    compute_target_fraction,
    derive_trend_strength,
    smooth_fraction,
)
from .backtest import fetch_historical_klines, run_dca_backtest
from .trend_backtest import DEFAULT_PERIODS, _extended_start_date, compute_max_drawdown, run_trend_backtest
from .trend_signals import TrendSignalGenerator, decide_action, is_stop_loss_hit


@dataclass
class AllocatedBacktestResult:
    symbol: str
    start_date: str
    end_date: str
    dca_num_buys: int
    dca_total_invested: float
    dca_final_value: float
    trend_num_trades: int
    trend_total_invested: float
    trend_realized_pnl: float
    trend_open_unrealized_pnl: float | None
    combined_total_invested: float
    combined_pnl: float
    combined_return_pct: float
    max_drawdown: float
    buy_and_hold_return_pct: float
    trade_log: list[dict] = field(default_factory=list)


def run_allocated_backtest(
    klines: list[dict],
    symbol: str,
    start_date: str,
    ema_fast_period: int,
    ema_slow_period: int,
    zero_anchor_pct: float,
    full_anchor_pct: float,
    smoothing_period_days: float,
    dca_amount: float,
    trend_amount: float,
    trend_min_gap_pct: float,
    trend_stop_loss_pct: float,
    fee_pct: float,
) -> AllocatedBacktestResult:
    """
    Simuliert DCA- und Trend-Following-Seite TAG FÜR TAG gemeinsam, mit
    dem jeweils vom Allocator zugeteilten Kapitalanteil. `klines` sollte
    bereits die erweiterte Vorlaufzeit enthalten (siehe
    `_extended_start_date` aus trend_backtest.py) - sowohl die EMAs als
    auch die geglättete Zuteilung selbst wärmen sich während dieser
    Vorlaufzeit ein, damit am eigentlichen Teststart kein künstlicher
    Kaltstart-Sprung entsteht. Offene Positionen (Trend-Seite) laufen
    unabhängig von der aktuellen Zuteilung weiter - nur NEUE Käufe/
    Einstiege werden mit dem jeweils aktuellen Anteil skaliert, exakt wie
    im Live-Allocator.
    """
    if not klines:
        raise ValueError("Keine Kursdaten zum Backtesten vorhanden.")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")

    # Zwei getrennte Generatoren, genau wie live: einer liefert den rohen
    # EMA-Abstand für die Allocator-Kurve (min_gap_pct=0), der andere die
    # bestätigten Ein-/Ausstiegssignale für die Trend-Bot-eigene Logik
    # (mit dem echten TREND_MIN_GAP_PCT) - siehe allocator.py/trend_strategy.py.
    strength_gen = TrendSignalGenerator(ema_fast_period, ema_slow_period, 0.0)
    decision_gen = TrendSignalGenerator(ema_fast_period, ema_slow_period, trend_min_gap_pct)

    smoothed: float | None = None
    dca_total_invested = 0.0
    dca_total_units = 0.0
    dca_num_buys = 0

    trend_open: dict | None = None
    trend_realized_total = 0.0
    trend_total_invested = 0.0
    trade_log: list[dict] = []

    equity_curve: list[float] = []
    first_traded_price: float | None = None
    last_price = klines[-1]["close_price"]

    for candle in klines:
        price = candle["close_price"]
        candle_dt = datetime.fromtimestamp(candle["open_time"] / 1000)

        strength_state = strength_gen.feed(price)
        decision_state = decision_gen.feed(price)
        strength = derive_trend_strength(strength_state)
        raw_target = compute_target_fraction(strength, zero_anchor_pct, full_anchor_pct)
        # Glättung läuft schon während der Vorlaufzeit mit, damit sie am
        # Teststart eingeschwungen ist statt bei 0 zu starten.
        smoothed = smooth_fraction(smoothed, raw_target, smoothing_period_days)

        if candle_dt < start_dt:
            continue  # Vorlaufzeit: nur EMAs/Glättung aufbauen, nicht handeln

        if first_traded_price is None:
            first_traded_price = price
        date_str = candle_dt.strftime("%Y-%m-%d")

        # --- DCA-Seite: taeglicher Kauf, skaliert mit (1 - smoothed) ---
        dca_effective_amount = dca_amount * (1 - smoothed)
        if dca_effective_amount >= MIN_EFFECTIVE_QUOTE_AMOUNT:
            dca_total_units += dca_effective_amount / price
            dca_total_invested += dca_effective_amount
            dca_num_buys += 1

        # --- Trend-Seite: exakt dieselbe Entscheidungslogik wie run_trend_backtest ---
        confirmed = decision_state["confirmed_direction"]
        if trend_open is not None and is_stop_loss_hit(trend_open["entry_price"], price, trend_stop_loss_pct):
            proceeds = trend_open["quantity"] * price * (1 - fee_pct / 100)
            pnl = proceeds - trend_open["quote_spent"]
            trend_realized_total += pnl
            trade_log.append(
                {"entry_date": trend_open["entry_date"], "exit_date": date_str, "exit_reason": "stop_loss", "pnl": pnl}
            )
            trend_open = None
        else:
            action = decide_action(confirmed, trend_open is not None, stop_loss_paused=False)
            if action == "EXIT_SIGNAL" and trend_open is not None:
                proceeds = trend_open["quantity"] * price * (1 - fee_pct / 100)
                pnl = proceeds - trend_open["quote_spent"]
                trend_realized_total += pnl
                trade_log.append(
                    {"entry_date": trend_open["entry_date"], "exit_date": date_str, "exit_reason": "signal", "pnl": pnl}
                )
                trend_open = None
            elif action == "ENTER":
                trend_effective_amount = trend_amount * smoothed
                if trend_effective_amount >= MIN_EFFECTIVE_QUOTE_AMOUNT:
                    quantity = (trend_effective_amount * (1 - fee_pct / 100)) / price
                    trend_open = {
                        "entry_price": price,
                        "quantity": quantity,
                        "quote_spent": trend_effective_amount,
                        "entry_date": date_str,
                    }
                    trend_total_invested += trend_effective_amount
                # sonst: Signal ignoriert, da der Allocator dem Trend-Bot
                # aktuell zu wenig Kapital fuer eine sinnvolle Position
                # zuteilt - kein Fehler, entspricht dem Live-Verhalten.

        dca_unrealized_pnl = dca_total_units * price - dca_total_invested
        trend_unrealized = 0.0
        if trend_open is not None:
            trend_unrealized = trend_open["quantity"] * price - trend_open["quote_spent"]
        combined_equity = dca_unrealized_pnl + trend_realized_total + trend_unrealized
        equity_curve.append(combined_equity)

    if first_traded_price is None:
        raise ValueError(f"Keine Kerzen im Zeitraum ab {start_date} gefunden - Zeitraum/Daten prüfen.")

    dca_final_value = dca_total_units * last_price

    trend_open_unrealized_pnl = None
    if trend_open is not None:
        trend_open_unrealized_pnl = trend_open["quantity"] * last_price - trend_open["quote_spent"]

    combined_total_invested = dca_total_invested + trend_total_invested
    combined_pnl = (
        (dca_final_value - dca_total_invested)
        + trend_realized_total
        + (trend_open_unrealized_pnl or 0.0)
    )
    combined_return_pct = (
        combined_pnl / combined_total_invested * 100 if combined_total_invested > 0 else 0.0
    )
    buy_and_hold_return_pct = (last_price - first_traded_price) / first_traded_price * 100

    return AllocatedBacktestResult(
        symbol=symbol,
        start_date=start_date,
        end_date=datetime.fromtimestamp(klines[-1]["open_time"] / 1000).strftime("%Y-%m-%d"),
        dca_num_buys=dca_num_buys,
        dca_total_invested=dca_total_invested,
        dca_final_value=dca_final_value,
        trend_num_trades=len(trade_log),
        trend_total_invested=trend_total_invested,
        trend_realized_pnl=trend_realized_total,
        trend_open_unrealized_pnl=trend_open_unrealized_pnl,
        combined_total_invested=combined_total_invested,
        combined_pnl=combined_pnl,
        combined_return_pct=combined_return_pct,
        max_drawdown=compute_max_drawdown(equity_curve),
        buy_and_hold_return_pct=buy_and_hold_return_pct,
        trade_log=trade_log,
    )


def print_report(
    allocated: AllocatedBacktestResult,
    dca_isolated_invested: float,
    dca_isolated_return_pct: float,
    trend_isolated_invested: float,
    trend_isolated_return_pct: float,
    label: str,
) -> None:
    print(f"\n{'=' * 60}")
    print(f"Allocator-Backtest: {allocated.symbol} - {label}")
    print(f"Zeitraum: {allocated.start_date} bis {allocated.end_date}")
    print(f"{'=' * 60}")
    print(f"DCA-Seite:   {allocated.dca_num_buys} Käufe, investiert {allocated.dca_total_invested:,.2f}, "
          f"Endwert {allocated.dca_final_value:,.2f}")
    print(f"Trend-Seite: {allocated.trend_num_trades} abgeschlossene Trades, "
          f"investiert {allocated.trend_total_invested:,.2f}, realisiert {allocated.trend_realized_pnl:+,.2f}")
    if allocated.trend_open_unrealized_pnl is not None:
        print(f"  + am Ende noch OFFENE Trend-Position, unrealisiert: {allocated.trend_open_unrealized_pnl:+,.2f}")
    print(f"{'-' * 60}")
    print(f"KOMBINIERT (mit Allocator): investiert {allocated.combined_total_invested:,.2f}, "
          f"PnL {allocated.combined_pnl:+,.2f} ({allocated.combined_return_pct:+.2f}%)")
    print(f"Max. Drawdown (kombiniert): {allocated.max_drawdown:,.2f}")
    print(f"{'-' * 60}")
    print(f"Vergleich - isoliert DCA:   investiert {dca_isolated_invested:,.2f}, Rendite {dca_isolated_return_pct:+.2f}%")
    print(f"Vergleich - isoliert Trend: investiert {trend_isolated_invested:,.2f}, Rendite {trend_isolated_return_pct:+.2f}%")
    print(f"Vergleich - Buy & Hold über denselben Zeitraum: {allocated.buy_and_hold_return_pct:+.2f}%")
    print(f"{'=' * 60}")
    print(
        "WICHTIG zur Vergleichbarkeit: Die investierten Beträge sind NICHT gleich groß\n"
        "(siehe Zahlen oben)! DCA wird täglich um den aktuellen Trend-Anteil reduziert,\n"
        "aber das dadurch \"freiwerdende\" Kapital fließt nicht automatisch zum Trend-Bot -\n"
        "der investiert nur an seinen eigenen, seltenen Einstiegstagen. An allen anderen\n"
        "Tagen bleibt der reduzierte DCA-Betrag schlicht uninvestiert (exakt wie im\n"
        "Live-Design: additive, unabhängige Skalierung je Seite, kein gemeinsamer Topf).\n"
        "Die Prozentwerte sind daher jeweils eine Rendite-pro-eingesetztem-Euro-Kennzahl\n"
        "der jeweiligen Strategie, KEIN Vergleich bei identischem Gesamtbudget - ein\n"
        "höherer Prozentwert bei 'Kombiniert' bedeutet nicht zwangsläufig einen höheren\n"
        "absoluten Gewinn als 'Isoliert DCA' bei gleichem Kapitaleinsatz."
    )
    print(
        "Hinweis: Parameter sind unveränderte Live-Defaults, nicht gegen diesen\n"
        "Zeitraum optimiert. Die Glättungsperiode ist ein eigener Tages-Parameter,\n"
        "keine Einheiten-Umrechnung der Live-Zyklen (siehe Modul-Docstring)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Kapital-Allocator-Backtest (DCA <-> Trend-Following)")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--start", default=None, help="Format: YYYY-MM-DD (überschreibt die 3 Standard-Zeiträume)")
    parser.add_argument("--end", default=None, help="Format: YYYY-MM-DD")
    parser.add_argument("--ema-fast", type=int, default=20)
    parser.add_argument("--ema-slow", type=int, default=50)
    parser.add_argument("--zero-anchor-pct", type=float, default=0.0)
    parser.add_argument("--full-anchor-pct", type=float, default=3.0)
    parser.add_argument("--smoothing-period-days", type=float, default=3.0)
    parser.add_argument("--dca-amount", type=float, default=15.0)
    parser.add_argument("--trend-amount", type=float, default=15.0)
    parser.add_argument("--trend-min-gap-pct", type=float, default=1.0)
    parser.add_argument("--trend-stop-loss-pct", type=float, default=10.0)
    parser.add_argument("--fee-pct", type=float, default=0.1, help="Gebühr pro Seite (Kauf/Verkauf) in %%")
    args = parser.parse_args()

    if args.start and args.end:
        periods = [(f"{args.start} bis {args.end}", args.start, args.end)]
    else:
        periods = DEFAULT_PERIODS

    for label, start, end in periods:
        print(f"\n\n{'#' * 60}")
        print(f"# Zeitraum: {label}")
        print(f"{'#' * 60}")

        fetch_start = _extended_start_date(start, args.ema_slow)
        print(f"Lade historische Daten für {args.symbol} ({fetch_start} bis {end}, inkl. EMA-Vorlauf) ...")
        klines = fetch_historical_klines(args.symbol, "1d", fetch_start, end)
        print(f"{len(klines)} Tageskerzen geladen.")

        try:
            allocated = run_allocated_backtest(
                klines,
                symbol=args.symbol,
                start_date=start,
                ema_fast_period=args.ema_fast,
                ema_slow_period=args.ema_slow,
                zero_anchor_pct=args.zero_anchor_pct,
                full_anchor_pct=args.full_anchor_pct,
                smoothing_period_days=args.smoothing_period_days,
                dca_amount=args.dca_amount,
                trend_amount=args.trend_amount,
                trend_min_gap_pct=args.trend_min_gap_pct,
                trend_stop_loss_pct=args.trend_stop_loss_pct,
                fee_pct=args.fee_pct,
            )

            # Isolierte Vergleichswerte: exakt dieselben wiederverwendeten
            # Backtest-Funktionen wie backtest.py/trend_backtest.py selbst.
            test_range_klines = [
                k for k in klines
                if datetime.fromtimestamp(k["open_time"] / 1000) >= datetime.strptime(start, "%Y-%m-%d")
            ]
            dca_isolated = run_dca_backtest(
                test_range_klines, symbol=args.symbol, quote_amount=args.dca_amount, buy_every_n_candles=1
            )
            trend_isolated = run_trend_backtest(
                klines,
                symbol=args.symbol,
                start_date=start,
                ema_fast_period=args.ema_fast,
                ema_slow_period=args.ema_slow,
                min_gap_pct=args.trend_min_gap_pct,
                amount_per_trade=args.trend_amount,
                stop_loss_pct=args.trend_stop_loss_pct,
                fee_pct=args.fee_pct,
            )

            trend_isolated_invested = args.trend_amount * (
                len(trend_isolated.trade_log) + (1 if trend_isolated.open_position_unrealized_pnl is not None else 0)
            )
            print_report(
                allocated,
                dca_isolated.total_invested,
                dca_isolated.dca_return_pct,
                trend_isolated_invested,
                trend_isolated.total_pnl_pct,
                label,
            )
        except ValueError as exc:
            print(f"Übersprungen: {exc}")


if __name__ == "__main__":
    main()

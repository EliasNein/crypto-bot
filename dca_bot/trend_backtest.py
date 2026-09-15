"""
Backtesting für die Trend-Following-Strategie (EMA-Crossover mit
Trendstärke-Filter).

Nutzt dieselbe Signal-Logik (trend_signals.py) wie die Live-Strategie
(trend_strategy.py) - siehe dort für die Begründung, warum das wichtig
ist. Nutzt außerdem denselben historischen Daten-Loader wie der
DCA-Backtest (backtest.py), um Code nicht zu duplizieren.

Overfitting-Vorsicht (siehe trading-bot-projekt.md, Gort et al.):
Die Default-Parameter (20/50-Tage-EMA, 1,0% Mindestabstand) sind
Standardwerte aus der Literatur, NICHT gegen die unten getesteten
Zeiträume optimiert. Sie werden hier bewusst nicht automatisch
nachjustiert - Ziel ist zu prüfen, ob ein unoptimierter Parametersatz
über verschiedene Marktphasen hinweg überhaupt robust funktioniert,
nicht die bestmögliche Kurve für genau diese drei Zeiträume zu finden.

Ausführen mit:  python -m dca_bot.trend_backtest
(ohne Argumente: läuft automatisch über drei Referenz-Zeiträume -
2022 Bärenmarkt, 2023 Erholung, 2021 Seitwärts/Konsolidierung)
"""

from __future__ import annotations

import argparse
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .backtest import fetch_historical_klines
from .trend_signals import TrendSignalGenerator, decide_action, is_stop_loss_hit

DEFAULT_PERIODS = [
    ("2022 Bärenmarkt", "2022-01-01", "2022-12-31"),
    ("2023 Erholung", "2023-01-01", "2023-12-31"),
    ("2021 Seitwärts/Konsolidierung", "2021-06-01", "2021-10-01"),
]


@dataclass
class TrendBacktestResult:
    symbol: str
    start_date: str
    end_date: str
    ema_fast_period: int
    ema_slow_period: int
    min_gap_pct: float
    stop_loss_pct: float
    num_trades: int
    num_wins: int
    total_pnl: float  # nur realisierte (geschlossene) Trades
    total_pnl_pct: float  # relativ zu amount_per_trade
    open_position_unrealized_pnl: float | None  # None = am Ende keine Position offen
    max_drawdown: float
    sharpe_like_ratio: float
    buy_and_hold_return_pct: float
    stop_loss_paused_at_end: bool
    trade_log: list[dict] = field(default_factory=list)


def _extended_start_date(start_date: str, slow_period: int) -> str:
    """
    Startdatum für den Daten-Abruf, ausreichend vor dem eigentlichen
    Test-Start, damit die EMAs bis zum Beginn des Testzeitraums bereits
    eingeschwungen sind (sonst würden die ersten `slow_period` Tage des
    Testzeitraums für nichts als EMA-Aufwärmen verbraucht). Krypto
    handelt 24/7, also ein Kalendertag = eine Tageskerze, kein
    Wochenend-Puffer nötig.
    """
    buffer_days = slow_period + 30
    dt = datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=buffer_days)
    return dt.strftime("%Y-%m-%d")


def compute_max_drawdown(equity_curve: list[float]) -> float:
    """Größter Rückgang von einem bisherigen Hoch der kumulierten PnL-Kurve
    (in absoluten Quote-Einheiten, nicht Prozent - siehe print_report)."""
    peak = 0.0
    max_dd = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown = peak - equity
        max_dd = max(max_dd, drawdown)
    return max_dd


def compute_sharpe_like_ratio(daily_pnl_changes: list[float]) -> float:
    """
    Einfaches, annualisiertes Sharpe-artiges Maß auf Basis der täglichen
    Änderung der kumulierten PnL (realisiert + unrealisiert). Bewusst
    vereinfacht (keine risikofreie Rate abgezogen) - für einen groben
    Vergleich zwischen Zeiträumen ausreichend, kein akademisch strenger
    Sharpe Ratio.
    """
    if len(daily_pnl_changes) < 2:
        return 0.0
    stdev = statistics.pstdev(daily_pnl_changes)
    if stdev == 0:
        return 0.0
    mean = statistics.mean(daily_pnl_changes)
    return (mean / stdev) * (365 ** 0.5)


@dataclass
class StopLimitReliabilityResult:
    """
    NÄHERUNG basierend auf Tageskerzen-Low, KEIN exaktes Intraday-Ergebnis
    (siehe analyze_stop_limit_reliability für die Methodik) - nur zur
    groben Einordnung, wie zuverlässig die echte, exchange-seitige
    STOP_LOSS_LIMIT-Order (siehe trend_strategy.py/binance_client.py) im
    Vergleich zum bisher simulierten Market-Sell-Exit gewesen wäre.
    """
    num_stop_loss_exits: int
    # offset_pct -> Anzahl Fälle, in denen die Order NICHT am Exit-Tag
    # selbst gefüllt worden wäre (Low der Exit-Kerze über dem Limit-Preis).
    unfilled_counts: dict[float, int]
    # offset_pct -> größter einzelner Zusatzverlust unter den ungefüllten
    # Fällen (kann rechnerisch auch negativ sein = ein Vorteil, falls sich
    # der Kurs bis zur tatsächlichen Füllung erholt hat).
    worst_extra_loss: dict[float, float]
    worst_extra_loss_detail: dict[float, str | None]


def analyze_stop_limit_reliability(
    trade_log: list[dict],
    klines: list[dict],
    stop_loss_pct: float,
    offsets_pct: list[float],
    fee_pct: float,
) -> StopLimitReliabilityResult:
    """
    NÄHERUNG basierend auf Tageskerzen-Low - der Bot prüft/handelt live
    alle 24h auf Tageskerzen (siehe trend_strategy.py), Tageskerzen zeigen
    aber nicht den exakten Intraday-Verlauf. KEIN Ersatz für ein echtes
    Orderbuch-/Tick-Backtest, nur eine grobe erste Einordnung.

    Für jeden simulierten Stop-Loss-Exit in `trade_log` (exit_reason ==
    "stop_loss"): berechnet stop_price = entry_price * (1 -
    stop_loss_pct/100) (exakt wie beim echten Entry, siehe
    trend_strategy.py._open_position) und für jeden offset_pct den
    zugehörigen limit_price = stop_price * (1 - offset_pct/100).

    Eine echte STOP_LOSS_LIMIT-Order gilt als am Exit-Tag gefüllt, wenn
    das Low dieser Kerze auf/unter limit_price fällt (die Order kann bei
    einem Limit-Sell nie schlechter als der Limit-Preis gefüllt werden -
    berührt/unterschreitet der Kurs ihn, wäre sie dort gefüllt worden).
    Falls nicht: sucht die nächste spätere Kerze, deren Low unter
    limit_price fällt (dort angenommener Füllpreis = limit_price selbst)
    und vergleicht das mit dem ursprünglich simulierten Exit-Preis
    (Zusatzverlust = wie viel schlechter/besser der spätere Fill
    gegenüber dem sofortigen Market-Sell gewesen wäre). Bleibt die Order
    bis zum Ende der verfügbaren Daten ungefüllt, wird ersatzweise der
    letzte verfügbare Schlusskurs verwendet (klar als Näherung markiert -
    kann auch einen "negativen Zusatzverlust", also einen Vorteil,
    ergeben, falls sich der Kurs bis dahin erholt hätte).
    """
    by_date_low: dict[str, float] = {}
    by_date_close: dict[str, float] = {}
    for candle in klines:
        date_str = datetime.fromtimestamp(candle["open_time"] / 1000).strftime("%Y-%m-%d")
        by_date_low[date_str] = candle["low_price"]
        by_date_close[date_str] = candle["close_price"]
    sorted_dates = sorted(by_date_low.keys())
    last_date = sorted_dates[-1] if sorted_dates else None
    last_close = by_date_close[last_date] if last_date is not None else None

    stop_loss_trades = [t for t in trade_log if t["exit_reason"] == "stop_loss"]

    unfilled_counts = {offset: 0 for offset in offsets_pct}
    worst_extra_loss = {offset: 0.0 for offset in offsets_pct}
    worst_extra_loss_detail: dict[float, str | None] = {offset: None for offset in offsets_pct}

    for trade in stop_loss_trades:
        stop_price = trade["entry_price"] * (1 - stop_loss_pct / 100)
        exit_date = trade["exit_date"]
        exit_low = by_date_low.get(exit_date)

        for offset in offsets_pct:
            limit_price = stop_price * (1 - offset / 100)

            if exit_low is not None and exit_low <= limit_price:
                continue  # gilt als am Exit-Tag selbst gefüllt, kein Zusatzverlust

            unfilled_counts[offset] += 1

            fill_date = None
            for date_str in sorted_dates:
                if date_str <= exit_date:
                    continue
                if by_date_low[date_str] <= limit_price:
                    fill_date = date_str
                    break

            if fill_date is not None:
                fallback_price = limit_price
                note = f"gefüllt am {fill_date}"
            else:
                fallback_price = last_close
                note = f"bis Datenende ({last_date}) ungefüllt, Näherung mit letztem Schlusskurs"

            if fallback_price is None:
                continue  # keine Daten vorhanden - überspringen

            extra_loss = (trade["exit_price"] - fallback_price) * trade["quantity"] * (1 - fee_pct / 100)
            if extra_loss > worst_extra_loss[offset]:
                worst_extra_loss[offset] = extra_loss
                worst_extra_loss_detail[offset] = f"Einstieg {trade['entry_date']}, Exit {exit_date} ({note})"

    return StopLimitReliabilityResult(
        num_stop_loss_exits=len(stop_loss_trades),
        unfilled_counts=unfilled_counts,
        worst_extra_loss=worst_extra_loss,
        worst_extra_loss_detail=worst_extra_loss_detail,
    )


def run_trend_backtest(
    klines: list[dict],
    symbol: str,
    start_date: str,
    ema_fast_period: int,
    ema_slow_period: int,
    min_gap_pct: float,
    amount_per_trade: float,
    stop_loss_pct: float,
    fee_pct: float,
    reset_cooldown_days: int | None = None,
) -> TrendBacktestResult:
    """
    Simuliert die exakt gleiche Entscheidungslogik wie die Live-Strategie
    (decide_action() + is_stop_loss_hit() aus trend_signals.py) über
    historische Tageskerzen. `klines` sollte bereits die erweiterte
    Vorlaufzeit (siehe _extended_start_date) enthalten - Kerzen vor
    `start_date` werden nur zum EMA-Aufwärmen genutzt, nicht gehandelt.

    `reset_cooldown_days`: NUR für Analysezwecke, NICHT das Live-Verhalten
    des Bots (der macht bewusst keinen automatischen Reset, siehe
    trend_risk.py). Wenn gesetzt, wird eine ausgelöste Stop-Loss-Pause
    nach so vielen Tagen automatisch aufgehoben - simuliert einen
    Menschen, der periodisch auf die Telegram-Nachricht reagiert und
    manuell zurücksetzt. Default None = exaktes Live-Verhalten (Pause
    hält bis zum Ende des Backtest-Zeitraums an).
    """
    if not klines:
        raise ValueError("Keine Kursdaten zum Backtesten vorhanden.")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    generator = TrendSignalGenerator(ema_fast_period, ema_slow_period, min_gap_pct)

    open_trade: dict | None = None
    stop_loss_paused = False
    days_since_pause = 0
    realized_total = 0.0
    trade_log: list[dict] = []
    equity_curve: list[float] = []
    daily_pnl_changes: list[float] = []
    prev_equity = 0.0
    first_traded_price: float | None = None
    last_price: float = klines[-1]["close_price"]

    for candle in klines:
        price = candle["close_price"]
        candle_dt = datetime.fromtimestamp(candle["open_time"] / 1000)
        state = generator.feed(price)  # immer füttern, auch während der Aufwärmphase

        if candle_dt < start_dt:
            continue  # Aufwärmphase: nur EMAs aufbauen, nicht handeln

        if first_traded_price is None:
            first_traded_price = price

        date_str = candle_dt.strftime("%Y-%m-%d")
        confirmed = state["confirmed_direction"]

        # NUR Analyse-Modus (siehe Docstring): simulierter periodischer
        # manueller Reset nach `reset_cooldown_days` Tagen Pause.
        if stop_loss_paused and reset_cooldown_days is not None:
            days_since_pause += 1
            if days_since_pause >= reset_cooldown_days:
                stop_loss_paused = False
                days_since_pause = 0

        # Stop-Loss hat Priorität bei Gleichzeitigkeit, analog zur Live-Strategie.
        if open_trade is not None and is_stop_loss_hit(open_trade["entry_price"], price, stop_loss_pct):
            proceeds = open_trade["quantity"] * price * (1 - fee_pct / 100)
            pnl = proceeds - open_trade["quote_spent"]
            realized_total += pnl
            trade_log.append(
                {
                    "entry_date": open_trade["entry_date"],
                    "entry_price": open_trade["entry_price"],
                    "exit_date": date_str,
                    "exit_price": price,
                    "exit_reason": "stop_loss",
                    "pnl": pnl,
                    "quantity": open_trade["quantity"],
                }
            )
            open_trade = None
            stop_loss_paused = True
            days_since_pause = 0
        else:
            action = decide_action(confirmed, open_trade is not None, stop_loss_paused)
            if action == "EXIT_SIGNAL" and open_trade is not None:
                proceeds = open_trade["quantity"] * price * (1 - fee_pct / 100)
                pnl = proceeds - open_trade["quote_spent"]
                realized_total += pnl
                trade_log.append(
                    {
                        "entry_date": open_trade["entry_date"],
                        "entry_price": open_trade["entry_price"],
                        "exit_date": date_str,
                        "exit_price": price,
                        "exit_reason": "signal",
                        "pnl": pnl,
                        "quantity": open_trade["quantity"],
                    }
                )
                open_trade = None
            elif action == "ENTER":
                quantity = (amount_per_trade * (1 - fee_pct / 100)) / price
                open_trade = {
                    "entry_price": price,
                    "quantity": quantity,
                    "quote_spent": amount_per_trade,
                    "entry_date": date_str,
                }

        unrealized = 0.0
        if open_trade is not None:
            unrealized = open_trade["quantity"] * price - open_trade["quote_spent"]
        current_equity = realized_total + unrealized
        equity_curve.append(current_equity)
        daily_pnl_changes.append(current_equity - prev_equity)
        prev_equity = current_equity

    if first_traded_price is None:
        raise ValueError(
            f"Keine Kerzen im Zeitraum ab {start_date} gefunden - Zeitraum/Daten prüfen."
        )

    num_trades = len(trade_log)
    num_wins = sum(1 for t in trade_log if t["pnl"] > 0)
    total_pnl_pct = realized_total / amount_per_trade * 100

    buy_and_hold_return_pct = (last_price - first_traded_price) / first_traded_price * 100

    # Falls am Ende des Zeitraums noch eine Position offen ist (kein Exit-
    # Signal/Stop-Loss innerhalb des Testfensters), zählt sie NICHT als
    # abgeschlossener Trade in trade_log/total_pnl - sonst würde ein noch
    # laufender Gewinn/Verlust stillschweigend unter den Tisch fallen.
    open_position_unrealized_pnl = None
    if open_trade is not None:
        open_position_unrealized_pnl = open_trade["quantity"] * last_price - open_trade["quote_spent"]

    return TrendBacktestResult(
        symbol=symbol,
        start_date=start_date,
        end_date=datetime.fromtimestamp(klines[-1]["open_time"] / 1000).strftime("%Y-%m-%d"),
        ema_fast_period=ema_fast_period,
        ema_slow_period=ema_slow_period,
        min_gap_pct=min_gap_pct,
        stop_loss_pct=stop_loss_pct,
        num_trades=num_trades,
        num_wins=num_wins,
        total_pnl=realized_total,
        total_pnl_pct=total_pnl_pct,
        open_position_unrealized_pnl=open_position_unrealized_pnl,
        max_drawdown=compute_max_drawdown(equity_curve),
        sharpe_like_ratio=compute_sharpe_like_ratio(daily_pnl_changes),
        buy_and_hold_return_pct=buy_and_hold_return_pct,
        stop_loss_paused_at_end=stop_loss_paused,
        trade_log=trade_log,
    )


def print_report(result: TrendBacktestResult, label: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"Trend-Following-Backtest: {result.symbol} - {label}")
    print(f"Zeitraum: {result.start_date} bis {result.end_date}")
    print(
        f"Parameter: EMA {result.ema_fast_period}/{result.ema_slow_period}, "
        f"Mindestabstand {result.min_gap_pct}%, Stop-Loss {result.stop_loss_pct}%"
    )
    print(f"{'=' * 60}")
    print(f"Anzahl Trades:             {result.num_trades}")
    if result.num_trades > 0:
        win_rate = result.num_wins / result.num_trades * 100
        print(f"Gewinn-Trades:             {result.num_wins} ({win_rate:.1f}% Trefferquote)")
    print(f"Gesamt-PnL (realisiert):   {result.total_pnl:+,.2f} ({result.total_pnl_pct:+.2f}% ggü. Positionsgröße)")
    if result.open_position_unrealized_pnl is not None:
        print(
            f"  + am Ende noch OFFENE Position, unrealisiert: {result.open_position_unrealized_pnl:+,.2f} "
            "(NICHT oben enthalten, da im Zeitraum nicht geschlossen)"
        )
    print(f"Max. Drawdown:             {result.max_drawdown:,.2f}")
    print(f"Sharpe-artiges Maß:        {result.sharpe_like_ratio:.2f}")
    print(f"{'-' * 60}")
    print(f"Vergleich - Buy & Hold über denselben Zeitraum: {result.buy_and_hold_return_pct:+.2f}%")
    print(f"{'=' * 60}")

    if result.stop_loss_paused_at_end:
        print(
            "WICHTIG: Der Stop-Loss war am Ende dieses Zeitraums noch ausgelöst/\n"
            "pausiert (kein automatischer Reset, siehe grid_risk.py-Pattern) - die\n"
            "Strategie hätte ohne manuellen Reset für den Rest des Zeitraums keine\n"
            "neuen Trades mehr eröffnet. Das drückt das Ergebnis möglicherweise\n"
            "künstlich, ist aber genau das reale Verhalten des Live-Bots."
        )
    print(
        "Hinweis: Parameter sind unveränderte Literatur-Defaults, nicht gegen\n"
        "diesen Zeitraum optimiert (siehe Modul-Docstring, Overfitting-Vorsicht)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Trend-Following-Strategie-Backtest")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--start", default=None, help="Format: YYYY-MM-DD (überschreibt die 3 Standard-Zeiträume)")
    parser.add_argument("--end", default=None, help="Format: YYYY-MM-DD")
    parser.add_argument("--ema-fast", type=int, default=20)
    parser.add_argument("--ema-slow", type=int, default=50)
    parser.add_argument("--min-gap-pct", type=float, default=1.0)
    parser.add_argument("--amount", type=float, default=15.0, help="Positionsgröße pro Trade (Quote-Währung)")
    parser.add_argument("--stop-loss-pct", type=float, default=10.0)
    parser.add_argument("--fee-pct", type=float, default=0.1, help="Gebühr pro Seite (Kauf/Verkauf) in %%")
    parser.add_argument(
        "--simulate-reset-after-days",
        type=int,
        default=None,
        help=(
            "NUR Analyse, NICHT das Live-Verhalten: hebt eine Stop-Loss-"
            "Pause nach so vielen Tagen automatisch auf, um zu simulieren, "
            "dass ein Mensch periodisch manuell zurücksetzt."
        ),
    )
    parser.add_argument(
        "--analyze-stop-limit-reliability",
        action="store_true",
        help=(
            "NUR Analyse, NICHT das Live-Verhalten: prüft näherungsweise "
            "(Tageskerzen-Low als Fill-Proxy), wie oft die echte, "
            "exchange-seitige STOP_LOSS_LIMIT-Order (siehe "
            "TREND_STOP_LIMIT_OFFSET_PCT) am simulierten Exit-Tag NICHT "
            "gefüllt worden wäre, für mehrere Offset-Werte."
        ),
    )
    parser.add_argument(
        "--stop-limit-offsets",
        default="0.5,1.0,2.0",
        help="Kommagetrennte Offset-Werte in %% für --analyze-stop-limit-reliability.",
    )
    args = parser.parse_args()

    if args.simulate_reset_after_days is not None:
        print(
            "\n*** ANALYSE-MODUS: simulierter automatischer Reset alle "
            f"{args.simulate_reset_after_days} Tage nach einem Stop-Loss. "
            "Das ist NICHT das Live-Verhalten des Bots (der resettet nie "
            "automatisch) - nur zur Einordnung, wie viel der Rendite-"
            "Differenz auf die Pause-Dauer zurückzuführen ist. ***"
        )

    if args.start and args.end:
        periods = [(f"{args.start} bis {args.end}", args.start, args.end)]
    else:
        periods = DEFAULT_PERIODS

    if args.analyze_stop_limit_reliability:
        print(
            "\n*** ANALYSE-MODUS: Stop-Limit-Zuverlässigkeit (NÄHERUNG "
            "basierend auf Tageskerzen-Low, KEIN exaktes Intraday-"
            "Ergebnis). Prüft für die Offsets "
            f"{args.stop_limit_offsets}%, wie oft die echte STOP_LOSS_LIMIT-"
            "Order am simulierten Exit-Tag NICHT gefüllt worden wäre. ***"
        )
    stop_limit_offsets = [float(v) for v in args.stop_limit_offsets.split(",")]
    reliability_rows: list[tuple[str, StopLimitReliabilityResult]] = []

    for label, start, end in periods:
        print(f"\n\n{'#' * 60}")
        print(f"# Zeitraum: {label}")
        print(f"{'#' * 60}")

        fetch_start = _extended_start_date(start, args.ema_slow)
        print(f"Lade historische Daten für {args.symbol} ({fetch_start} bis {end}, inkl. EMA-Vorlauf) ...")
        klines = fetch_historical_klines(args.symbol, "1d", fetch_start, end)
        print(f"{len(klines)} Tageskerzen geladen.")

        try:
            result = run_trend_backtest(
                klines,
                symbol=args.symbol,
                start_date=start,
                ema_fast_period=args.ema_fast,
                ema_slow_period=args.ema_slow,
                min_gap_pct=args.min_gap_pct,
                amount_per_trade=args.amount,
                stop_loss_pct=args.stop_loss_pct,
                fee_pct=args.fee_pct,
                reset_cooldown_days=args.simulate_reset_after_days,
            )
            print_report(result, label)

            if args.analyze_stop_limit_reliability:
                reliability = analyze_stop_limit_reliability(
                    result.trade_log, klines, args.stop_loss_pct, stop_limit_offsets, args.fee_pct
                )
                reliability_rows.append((label, reliability))
        except ValueError as exc:
            print(f"Übersprungen: {exc}")

    if args.analyze_stop_limit_reliability:
        print_stop_limit_reliability_table(reliability_rows, stop_limit_offsets)


def print_stop_limit_reliability_table(
    rows: list[tuple[str, "StopLimitReliabilityResult"]], offsets_pct: list[float]
) -> None:
    print(f"\n\n{'#' * 70}")
    print("# Stop-Limit-Zuverlässigkeit - NÄHERUNG basierend auf Tageskerzen-Low")
    print(f"{'#' * 70}")
    print(
        "ACHTUNG: Näherung, KEIN exaktes Intraday-Ergebnis. Eine Order gilt als\n"
        "am Exit-Tag gefüllt, wenn das Low dieser Tageskerze auf/unter den\n"
        "Limit-Preis fällt - Tageskerzen zeigen aber nicht den echten\n"
        "Intraday-Verlauf (z.B. ein kurzes Unterschreiten, das die Tageskerze\n"
        "nicht auflöst, oder umgekehrt ein Low, das nur für Sekunden erreicht\n"
        "wurde). Nur zur groben ersten Einordnung, kein Ersatz für ein echtes\n"
        "Orderbuch-/Tick-Backtest."
    )

    header = (
        f"{'Zeitraum':<32} | {'Exits':>5} | "
        + " | ".join(f"ungef. {o:g}%".rjust(11) for o in offsets_pct)
        + " | Größter Zusatzverlust"
    )
    print(f"\n{header}")
    print("-" * len(header))

    worst_overall: dict[float, tuple[float, str, str]] = {}  # offset -> (loss, period, detail)
    for label, reliability in rows:
        unfilled_str = " | ".join(
            str(reliability.unfilled_counts[o]).rjust(11) for o in offsets_pct
        )
        worst_offset = max(offsets_pct, key=lambda o: reliability.worst_extra_loss[o])
        worst_value = reliability.worst_extra_loss[worst_offset]
        print(
            f"{label:<32} | {reliability.num_stop_loss_exits:>5} | {unfilled_str} | "
            f"{worst_value:+,.2f} (@ {worst_offset:g}%)"
        )

        for o in offsets_pct:
            loss = reliability.worst_extra_loss[o]
            if o not in worst_overall or loss > worst_overall[o][0]:
                detail = reliability.worst_extra_loss_detail[o] or "-"
                worst_overall[o] = (loss, label, detail)

    print(f"\n{'-' * 70}")
    print("Details zum jeweils größten Zusatzverlust je Offset (über alle Zeiträume):")
    for o in offsets_pct:
        loss, label, detail = worst_overall[o]
        print(f"  {o:g}%: {loss:+,.2f} in '{label}' - {detail}")
    print(
        "\nHinweis: Ein Zusatzverlust von 0,00 heißt entweder 'immer am Exit-Tag\n"
        "selbst gefüllt' ODER 'kein einziger ungefüllter Fall in diesem\n"
        "Zeitraum/Offset' - siehe die 'ungef.'-Spalten für die genaue Anzahl."
    )
    print(f"{'#' * 70}")


if __name__ == "__main__":
    main()

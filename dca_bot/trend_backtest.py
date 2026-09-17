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

Zwei zusätzliche ANALYSE-Modi, die beide NICHT das Live-Verhalten
abbilden und es auch nicht verändern (gleiches Muster: eigener Schalter,
eigene Tabelle, klar als Analyse gekennzeichnet):

- `--analyze-stop-limit-reliability` (aus dem K3-Fix, siehe
  analyze_stop_limit_reliability)
- `--analyze-auto-reset` (siehe AutoResetParams und
  print_auto_reset_table): spielt einen ECHTEN automatischen
  Stop-Loss-Reset mit Erholungsschwelle und Cooldown durch. Der
  Live-Bot resettet weiterhin NIE automatisch (siehe TrendStopLoss in
  trend_risk.py) - das hier ist die Recherche zu Punkt 16 der
  Verbesserungsvorschläge, keine Implementierung.
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
    # Nur gesetzt, wenn der Lauf mit `auto_reset` lief (siehe
    # AutoResetParams) - sonst None, also unverändert für jeden
    # bisherigen Aufrufer.
    auto_reset_stats: "AutoResetStats | None" = None


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


@dataclass(frozen=True)
class AutoResetParams:
    """
    Parameter eines ECHTEN automatischen Stop-Loss-Resets - NUR für die
    Analyse (`--analyze-auto-reset`), NICHT das Live-Verhalten.

    Der Live-Bot hebt seinen Stop-Loss-Latch ausschließlich manuell auf
    (`python -m dca_bot.reset_trend_stop_loss`, siehe TrendStopLoss in
    trend_risk.py). Diese Klasse verändert daran nichts - sie
    parametrisiert nur die Simulation eines Mechanismus, den es im
    Produktivcode bewusst nicht gibt.

    Abgrenzung zum älteren `reset_cooldown_days` (siehe
    run_trend_backtest): Das simuliert einen MENSCHEN, der stur alle X
    Tage manuell zurücksetzt - eine rein zeitliche Regel ohne jeden
    Bezug zum Kurs. Genau daraus stammt die Zahl in
    trading-bot-projekt.md Abschnitt 6 (2023: ~55 % statt ~13 % bei
    14 Tagen). Sie beantwortet aber nicht die eigentliche Frage, denn
    "der Mensch schaut alle zwei Wochen drauf" ist kein Mechanismus mit
    Parametern, die man begründen könnte.

    Hier dagegen zwei konkrete, konfigurierbare Bedingungen:

    - `recovery_threshold_pct`: Der Preis muss um X % ÜBER den
      Auslösepreis des Stop-Loss gestiegen sein.
    - `cooldown_days`: Seit dem Stop-Loss-Exit müssen mindestens so
      viele Tage vergangen sein, bevor der Latch überhaupt geprüft wird.

    **Beide Bedingungen müssen erfüllt sein (UND, nicht ODER)** - siehe
    `_auto_reset_is_due`. Das ist der eigentliche Punkt des Experiments:
    Jede Bedingung für sich hat eine offensichtliche Lücke. Eine reine
    Erholungsschwelle greift auch bei einem Ein-Tages-Sprung direkt nach
    dem Exit (klassischer Dead-Cat-Bounce), ein reiner Cooldown ist
    wieder nur die Zeitregel von oben, bloß mit anderem Namen. Erst die
    Kombination ist die Whipsaw-Absicherung, um die es bei der
    Latch-Entscheidung überhaupt geht.
    """

    recovery_threshold_pct: float
    cooldown_days: int


@dataclass
class AutoResetStats:
    """
    Was der simulierte Auto-Reset in einem Lauf tatsächlich ausgelöst hat.

    `num_reentries` zählt Einstiege, die es OHNE Auto-Reset nicht
    gegeben hätte. Die Zuordnung ist dabei exakt und keine Schätzung:
    Ohne automatischen Reset hält der Latch bis zum Ende des
    Backtest-Zeitraums (er wird nie aufgehoben, es gibt in der
    Simulation keinen Menschen). Nach dem ERSTEN Stop-Loss-Exit ist
    damit jeder weitere Einstieg zwangsläufig einer, den erst der
    Auto-Reset ermöglicht hat.

    Die drei folgenden Zahlen teilen diese Wiedereinstiege nach ihrem
    Ausgang auf - und `num_reentries_stopped_out` ist die Zahl, um die
    es geht: der WHIPSAW-Fall.

    **Definition "falscher Wiedereinstieg": ein Wiedereinstieg, der
    selbst wieder im Stop-Loss endet** (`exit_reason == "stop_loss"`),
    statt regulär per Signal-Umkehr geschlossen zu werden. Das ist
    bewusst keine Näherung, sondern genau der befürchtete Vorgang: Der
    Bot steigt in eine Erholung ein, die keine war, und der Kurs fällt
    weiter, bis der Stop-Loss erneut greift. Ein Wiedereinstieg, der
    dagegen per Signal-Umkehr endet, hat sich als richtige Entscheidung
    erwiesen - unabhängig davon, wie kurz er lief und ob er Gewinn
    gemacht hat. Ein Verlust allein macht ihn nicht "falsch"; die Frage
    des Latches ist nicht "hat sich der Trade gelohnt", sondern "war der
    Wiedereinstieg in einen noch laufenden Abwärtstrend hinein".

    `num_reentries_still_open` wird eigens ausgewiesen, statt still bei
    den unauffälligen mitzulaufen: Ein am Periodenende offener
    Wiedereinstieg hat schlicht noch keinen Ausgang, und ihn als
    "nicht falsch" zu zählen wäre eine Aussage, die die Daten nicht
    hergeben. Die drei Zahlen summieren sich zu `num_reentries`.
    """

    num_auto_resets: int = 0
    num_reentries: int = 0
    num_reentries_stopped_out: int = 0
    num_reentries_exited_by_signal: int = 0
    num_reentries_still_open: int = 0


def _auto_reset_is_due(
    params: AutoResetParams,
    days_since_exit: int,
    anchor_price: float | None,
    price: float,
) -> bool:
    """
    Ob der Latch nach einem Stop-Loss-Exit automatisch aufgehoben würde -
    NUR Analyse, siehe AutoResetParams.

    `anchor_price` ist der Auslösepreis des letzten Stop-Loss-Exits, also
    der Kurs, zu dem die Position tatsächlich geschlossen wurde - NICHT
    die rechnerische Schwelle `entry_price * (1 - stop_loss_pct/100)`.
    Beide fallen im Backtest oft, aber nicht immer zusammen: Fällt der
    Tagesschlusskurs unter die Schwelle durch, liegt der tatsächliche
    Ausstieg darunter. Der Ausstiegskurs ist hier die richtige Wahl, und
    zwar aus einem praktischen Grund: Eine spätere Live-Umsetzung müsste
    denselben Anker verwenden können, und `TrendStopLoss.pause()`
    (trend_risk.py) schreibt genau diesen Wert bereits als `exit_price`
    in die Latch-Datei. Der Mechanismus bräuchte also keinen neuen
    Zustand - nur eine Auswertung dessen, was ohnehin schon dasteht.

    Die UND-Verknüpfung steht bewusst hier als eigene, testbare Funktion
    und nicht als Bedingung mitten in der Backtest-Schleife: Sie IST die
    Frage des Experiments, und sie später versehentlich zu einem ODER zu
    verschieben wäre eine stille, im Ergebnis aber gravierende Änderung.
    """
    if anchor_price is None or anchor_price <= 0:
        return False
    if days_since_exit < params.cooldown_days:
        return False
    return price >= anchor_price * (1 + params.recovery_threshold_pct / 100)


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
    auto_reset: AutoResetParams | None = None,
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

    `auto_reset`: ebenfalls NUR Analyse (siehe AutoResetParams) - ein
    echter, parametrisierter Auto-Reset-Mechanismus statt der reinen
    Zeitregel oben. Default None = unverändertes Live-Verhalten.

    Beide Reset-Parameter gleichzeitig zu setzen ist ein Fehler und
    wird abgewiesen: Es wären zwei konkurrierende Regeln für denselben
    Latch, und jede Zahl aus so einem Lauf ließe sich keiner von beiden
    zuordnen.
    """
    if not klines:
        raise ValueError("Keine Kursdaten zum Backtesten vorhanden.")

    if reset_cooldown_days is not None and auto_reset is not None:
        raise ValueError(
            "reset_cooldown_days und auto_reset schließen sich aus - der "
            "eine simuliert einen periodisch manuell zurücksetzenden "
            "Menschen, der andere einen echten Mechanismus. Zusammen "
            "wäre das Ergebnis keiner von beiden Regeln zuzuordnen."
        )

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    generator = TrendSignalGenerator(ema_fast_period, ema_slow_period, min_gap_pct)

    open_trade: dict | None = None
    stop_loss_paused = False
    # Tage seit dem letzten Stop-Loss-Exit. Wird von BEIDEN Analyse-Modi
    # genutzt - unkritisch, weil sie sich oben gegenseitig ausschließen.
    days_since_pause = 0
    # Auslösepreis des letzten Stop-Loss-Exits, Anker der
    # Erholungsschwelle (siehe _auto_reset_is_due).
    auto_reset_anchor_price: float | None = None
    auto_reset_stats = AutoResetStats() if auto_reset is not None else None
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

        # NUR Analyse-Modus (siehe AutoResetParams): echter automatischer
        # Reset aus Erholungsschwelle UND Cooldown. Bewusst an derselben
        # Stelle wie der simulierte manuelle Reset oben, also VOR der
        # Stop-Loss- und Signalauswertung dieses Tages: Ein Mensch, der
        # morgens zurücksetzt, gibt den Zyklus desselben Tages ebenfalls
        # frei - der Einstieg darf also noch in dieser Kerze fallen.
        if stop_loss_paused and auto_reset is not None:
            days_since_pause += 1
            if _auto_reset_is_due(
                auto_reset, days_since_pause, auto_reset_anchor_price, price
            ):
                stop_loss_paused = False
                days_since_pause = 0
                auto_reset_stats.num_auto_resets += 1

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
                    "is_reentry": open_trade["is_reentry"],
                }
            )
            if open_trade["is_reentry"]:
                auto_reset_stats.num_reentries_stopped_out += 1
            open_trade = None
            stop_loss_paused = True
            days_since_pause = 0
            # Anker der Erholungsschwelle ist der tatsächliche
            # Ausstiegskurs, nicht die rechnerische Schwelle - siehe
            # _auto_reset_is_due.
            auto_reset_anchor_price = price
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
                        "is_reentry": open_trade["is_reentry"],
                    }
                )
                if open_trade["is_reentry"]:
                    auto_reset_stats.num_reentries_exited_by_signal += 1
                open_trade = None
            elif action == "ENTER":
                quantity = (amount_per_trade * (1 - fee_pct / 100)) / price
                # Ohne Auto-Reset hält der Latch nach dem ersten
                # Stop-Loss-Exit bis zum Periodenende - jeder Einstieg
                # nach einem Auto-Reset ist deshalb per Konstruktion
                # einer, den es sonst nicht gegeben hätte (siehe
                # AutoResetStats).
                is_reentry = (
                    auto_reset_stats is not None
                    and auto_reset_stats.num_auto_resets > 0
                )
                open_trade = {
                    "entry_price": price,
                    "quantity": quantity,
                    "quote_spent": amount_per_trade,
                    "entry_date": date_str,
                    "is_reentry": is_reentry,
                }
                if is_reentry:
                    auto_reset_stats.num_reentries += 1

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
        # Ein am Periodenende offener Wiedereinstieg hat noch keinen
        # Ausgang - er zählt weder als falsch noch als bestätigt, sondern
        # eigens (siehe AutoResetStats).
        if open_trade["is_reentry"]:
            auto_reset_stats.num_reentries_still_open += 1

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
        auto_reset_stats=auto_reset_stats,
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
    parser.add_argument(
        "--analyze-auto-reset",
        action="store_true",
        help=(
            "NUR Analyse, NICHT das Live-Verhalten: spielt einen echten "
            "automatischen Stop-Loss-Reset mit Erholungsschwelle UND "
            "Cooldown über eine kleine Parameter-Grid-Suche durch und "
            "stellt das Ergebnis dem unveränderten Verhalten ohne "
            "Auto-Reset gegenüber (siehe AutoResetParams)."
        ),
    )
    parser.add_argument(
        "--auto-reset-recovery-pcts",
        default="2,5,10",
        help=(
            "Kommagetrennte Erholungsschwellen in %% über dem "
            "Stop-Loss-Auslösepreis für --analyze-auto-reset."
        ),
    )
    parser.add_argument(
        "--auto-reset-cooldown-days",
        default="3,7,14",
        help=(
            "Kommagetrennte Cooldown-Werte in Tagen seit dem "
            "Stop-Loss-Exit für --analyze-auto-reset."
        ),
    )
    args = parser.parse_args()

    if args.analyze_auto_reset and args.simulate_reset_after_days is not None:
        parser.error(
            "--analyze-auto-reset und --simulate-reset-after-days schließen "
            "sich aus: Der Referenzwert 'Rendite ohne Auto-Reset' muss das "
            "unveränderte Live-Verhalten sein (Latch hält bis zum "
            "Periodenende). Mit einem gleichzeitig simulierten periodischen "
            "Reset wäre er das nicht mehr."
        )

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

    auto_reset_grid: list[AutoResetParams] = []
    auto_reset_rows: list[AutoResetRow] = []
    if args.analyze_auto_reset:
        auto_reset_grid = [
            AutoResetParams(recovery_threshold_pct=recovery, cooldown_days=cooldown)
            for recovery in (
                float(v) for v in args.auto_reset_recovery_pcts.split(",")
            )
            for cooldown in (
                int(v) for v in args.auto_reset_cooldown_days.split(",")
            )
        ]
        print(
            "\n*** ANALYSE-MODUS: automatischer Stop-Loss-Reset "
            f"({len(auto_reset_grid)} Parameter-Kombinationen je Zeitraum). "
            "Das ist ein EXPERIMENT und NICHT das Live-Verhalten - der Bot "
            "resettet seinen Stop-Loss-Latch weiterhin nie automatisch "
            "(siehe TrendStopLoss in trend_risk.py). Die Spalte 'ohne "
            "Auto-Reset' ist dieses unveränderte Verhalten. ***"
        )

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

            # `result` ist hier per Konstruktion der Referenzlauf: Der
            # Modus verträgt sich nicht mit --simulate-reset-after-days
            # (siehe parser.error oben), also lief er ohne jeden Reset -
            # genau das unveränderte Live-Verhalten. Ihn ein zweites Mal
            # zu rechnen wäre nicht nur überflüssig, sondern eine zweite
            # Gelegenheit, versehentlich etwas anderes zu vergleichen.
            for params in auto_reset_grid:
                with_reset = run_trend_backtest(
                    klines,
                    symbol=args.symbol,
                    start_date=start,
                    ema_fast_period=args.ema_fast,
                    ema_slow_period=args.ema_slow,
                    min_gap_pct=args.min_gap_pct,
                    amount_per_trade=args.amount,
                    stop_loss_pct=args.stop_loss_pct,
                    fee_pct=args.fee_pct,
                    auto_reset=params,
                )
                auto_reset_rows.append(
                    AutoResetRow(
                        label=label,
                        params=params,
                        realized_pct_with=with_reset.total_pnl_pct,
                        unrealized_pct_with=_unrealized_pct(with_reset, args.amount),
                        realized_pct_without=result.total_pnl_pct,
                        unrealized_pct_without=_unrealized_pct(result, args.amount),
                        stats=with_reset.auto_reset_stats,
                    )
                )
        except ValueError as exc:
            print(f"Übersprungen: {exc}")

    if args.analyze_stop_limit_reliability:
        print_stop_limit_reliability_table(reliability_rows, stop_limit_offsets)

    if args.analyze_auto_reset:
        print_auto_reset_table(auto_reset_rows)


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


def _unrealized_pct(result: TrendBacktestResult, amount_per_trade: float) -> float:
    """
    Unrealisierte PnL einer am Periodenende offenen Position, relativ zur
    Positionsgröße - also auf derselben Basis wie `total_pnl_pct`, damit
    sich beide addieren lassen.

    Keine offene Position ergibt 0.0 und nicht None: Hier wird addiert,
    und "es steht nichts mehr offen" ist wirtschaftlich genau ein
    Beitrag von null.
    """
    if result.open_position_unrealized_pnl is None or amount_per_trade <= 0:
        return 0.0
    return result.open_position_unrealized_pnl / amount_per_trade * 100


@dataclass
class AutoResetRow:
    """
    Eine Zeile der Auto-Reset-Tabelle: ein Zeitraum, eine
    Parameter-Kombination, plus der unveränderte Referenzwert.

    Realisierter und unrealisierter Anteil werden GETRENNT gehalten und
    erst in der Ausgabe addiert. Das ist hier kein Detail, sondern die
    Voraussetzung dafür, dass die Tabelle überhaupt etwas zeigt: Der
    gesamte Effekt des Auto-Resets in 2023 steckt in einer am
    Periodenende noch OFFENEN Position. Eine Tabelle, die wie
    `print_report` nur die realisierte PnL ausweist, zeigt für jede
    Parameter-Kombination denselben Wert wie ohne Reset - und damit das
    glatte Gegenteil des tatsächlichen Ergebnisses.

    Die Summe ist zugleich die Größe, auf die sich die bereits
    dokumentierte Zahl aus trading-bot-projekt.md Abschnitt 6 bezieht
    (2023: ~55 %) - nur so sind die Spalten mit ihr vergleichbar.
    """

    label: str
    params: AutoResetParams
    realized_pct_with: float
    unrealized_pct_with: float
    realized_pct_without: float
    unrealized_pct_without: float
    stats: AutoResetStats

    @property
    def total_pct_with(self) -> float:
        return self.realized_pct_with + self.unrealized_pct_with

    @property
    def total_pct_without(self) -> float:
        return self.realized_pct_without + self.unrealized_pct_without


def print_auto_reset_table(rows: list[AutoResetRow]) -> None:
    print(f"\n\n{'#' * 100}")
    print("# Automatischer Stop-Loss-Reset - EXPERIMENT, NICHT das Live-Verhalten")
    print(f"{'#' * 100}")
    print(
        "Der Live-Bot hebt seinen Stop-Loss-Latch weiterhin AUSSCHLIESSLICH manuell auf\n"
        "(python -m dca_bot.reset_trend_stop_loss, siehe TrendStopLoss in trend_risk.py).\n"
        "Diese Tabelle beantwortet nur die Frage, was ein automatischer Reset gebracht\n"
        "hätte - sie ändert nichts am Produktivcode und ist keine Empfehlung.\n"
        "\n"
        "Der Latch wird aufgehoben, sobald BEIDE Bedingungen erfüllt sind (UND, nicht ODER):\n"
        "  - Erholung: Preis >= Auslösepreis des Stop-Loss * (1 + Erholung%/100)\n"
        "  - Cooldown: mindestens so viele Tage seit dem Stop-Loss-Exit\n"
        "\n"
        "'Rendite' ist realisierte PLUS unrealisierte PnL relativ zur Positionsgröße - und\n"
        "das ist hier wesentlich, nicht kosmetisch: Der gesamte Effekt des Auto-Resets in\n"
        "2023 steckt in einer am Periodenende noch offenen Position. Nur die realisierte\n"
        "PnL auszuweisen (wie im Hauptreport oben) zeigte für jede Kombination denselben\n"
        "Wert wie ohne Reset. Die Aufteilung steht je Zeitraum unter der Tabelle.\n"
        "\n"
        "'Resets' ist, wie oft der Latch automatisch aufgehoben wurde. Die Spalte steht\n"
        "neben den Wiedereinstiegen, weil sie zwei sehr verschiedene Nullen unterscheidet:\n"
        "'Latch nie aufgehoben' gegen 'aufgehoben, aber danach kam kein Einstiegssignal'.\n"
        "\n"
        "'Wiedereinstiege' sind Einstiege, die es ohne Auto-Reset nicht gegeben hätte (ohne\n"
        "ihn hält der Latch bis zum Periodenende). 'davon falsch' = Wiedereinstiege, die\n"
        "selbst wieder im Stop-Loss endeten statt per Signal-Umkehr - genau der Whipsaw,\n"
        "gegen den der Latch gebaut ist. Ein Wiedereinstieg, der per Signal-Umkehr endet,\n"
        "war die richtige Entscheidung, auch wenn er Verlust gemacht hat. Ein am Ende noch\n"
        "offener Wiedereinstieg hat keinen Ausgang und wird eigens als 'offen' ausgewiesen."
    )

    header = (
        f"{'Zeitraum':<32} | {'Erhol.':>6} | {'Cool.':>5} | {'Resets':>6} | "
        f"{'Rendite m. Reset':>16} | {'Rendite o. Reset':>16} | "
        f"{'Wiedereinst.':>12} | {'davon falsch':>13}"
    )
    print(f"\n{header}")
    print("-" * len(header))

    previous_label: str | None = None
    for row in rows:
        if previous_label is not None and row.label != previous_label:
            print("-" * len(header))
        previous_label = row.label

        open_note = ""
        if row.stats.num_reentries_still_open:
            open_note = f" ({row.stats.num_reentries_still_open} offen)"

        print(
            f"{row.label:<32} | {row.params.recovery_threshold_pct:>5.1f}% | "
            f"{row.params.cooldown_days:>5} | {row.stats.num_auto_resets:>6} | "
            f"{row.total_pct_with:>+15.2f}% | {row.total_pct_without:>+15.2f}% | "
            f"{row.stats.num_reentries:>12} | "
            f"{str(row.stats.num_reentries_stopped_out) + open_note:>13}"
        )

    print("-" * len(header))

    # Aufteilung realisiert/unrealisiert - bewusst je ZEITRAUM und nicht
    # je Zeile: Die Werte wiederholen sich innerhalb eines Zeitraums, und
    # 27 identische Fußnoten würden die eine Aussage begraben, auf die es
    # ankommt.
    print("\nAufteilung realisiert / unrealisiert (am Periodenende offene Position):")
    seen: set[str] = set()
    for row in rows:
        key = (
            f"{row.label}|{row.realized_pct_with:.4f}|{row.unrealized_pct_with:.4f}"
            f"|{row.realized_pct_without:.4f}|{row.unrealized_pct_without:.4f}"
        )
        if key in seen:
            continue
        seen.add(key)
        print(
            f"  {row.label:<32} mit Reset: {row.realized_pct_with:+.2f}% realisiert "
            f"{row.unrealized_pct_with:+.2f}% unrealisiert | ohne Reset: "
            f"{row.realized_pct_without:+.2f}% realisiert "
            f"{row.unrealized_pct_without:+.2f}% unrealisiert"
        )

    print(
        "\nLesehilfe: 0 Resets heißt, dass der Stop-Loss im Zeitraum nie ausgelöst hat oder\n"
        "die beiden Bedingungen nie gemeinsam erfüllt waren - dann ist die Rendite\n"
        "zwangsläufig identisch zum Referenzwert. 0 Wiedereinstiege bei Resets > 0 heißt\n"
        "dagegen, dass der Latch zwar fiel, danach aber kein bestätigtes Aufwärtssignal kam."
    )
    print(f"{'#' * 100}")


if __name__ == "__main__":
    main()

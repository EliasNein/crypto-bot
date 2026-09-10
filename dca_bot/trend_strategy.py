"""
Trend-Following-Strategie (EMA-Crossover mit Trendstärke-Filter,
long-only, Spot).

Nutzt EXAKT dieselbe Entscheidungslogik (TrendSignalGenerator,
decide_action, is_stop_loss_hit aus trend_signals.py) wie der Backtest
(trend_backtest.py) - siehe dort für die Begründung, warum das wichtig
ist. Siehe trading-bot-projekt.md Abschnitt 5 für die Recherche dazu:
Trend-Following ist die am besten akademisch belegte Alpha-Strategie
(Liu & Tsyvinski, Gbadebo), Hauptrisiko sind Overfitting und
Momentum-Crashes - siehe GridStopLoss/PortfolioStopLoss-Pattern für den
latched Stop-Loss dagegen.

Komplett eigenständig von strategy.py (DCA) und grid_strategy.py (Grid) -
kein geteilter Zustand.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .backtest import fetch_historical_klines
from .binance_client import TradingClient
from .notifier import send_notification
from .risk import KillSwitch
from .trend_config import TrendConfig
from .trend_risk import TrendLedger, TrendStopLoss, TrendTrade
from .trend_signals import TrendSignalGenerator, decide_action, is_stop_loss_hit

logger = logging.getLogger("trend_bot")


class TrendFollowingStrategy:
    def __init__(self, config: TrendConfig, client: TradingClient):
        self._config = config
        self._client = client
        self._ledger = TrendLedger(config.state_file)
        self._kill_switch = KillSwitch(config.kill_switch_file, env_var_name="TREND_BOT_HALT")
        self._stop_loss = TrendStopLoss(config.stop_loss_state_file)
        self._signal_gen = TrendSignalGenerator(
            config.ema_fast_period, config.ema_slow_period, config.min_gap_pct
        )
        self._seeded = False

    def _seed_with_history(self) -> None:
        """
        Lädt einmalig beim Start echte historische Tageskerzen (öffentliche
        Binance-API, wie im Backtest), damit die EMAs nicht bei Null
        anfangen - sonst bräuchte es z.B. 50 Live-Tage, bevor überhaupt
        ein Signal möglich wäre. Zieht Daten bis zum letzten VOLLSTÄNDIG
        abgeschlossenen Tag (gestern), da die heutige Kerze noch läuft.
        """
        end_dt = datetime.now(timezone.utc).date() - timedelta(days=1)
        start_dt = end_dt - timedelta(days=self._config.ema_slow_period + 30)
        klines = fetch_historical_klines(
            self._config.symbol, "1d", start_dt.isoformat(), end_dt.isoformat()
        )
        for candle in klines:
            self._signal_gen.feed(candle["close_price"])
        logger.info(
            "Historie geladen: %d Tageskerzen bis %s (EMA-Vorlauf).",
            len(klines),
            end_dt.isoformat(),
        )
        self._seeded = True

    def _open_position(self, price: float) -> None:
        amount = self._config.amount_per_trade
        order = self._client.place_market_buy(self._config.symbol, amount)

        if order is None and self._config.trading_enabled:
            logger.error(
                "Echter Trend-Einstieg fehlgeschlagen für %s (Preis ~%.2f).",
                self._config.symbol,
                price,
            )
            send_notification(
                f"[TREND-FEHLER] Echter Einstieg fehlgeschlagen für "
                f"{self._config.symbol} (Preis ~{price:.2f}). Siehe Bot-Log."
            )
            return

        if order is not None:
            quantity = float(order.get("executedQty", amount / price))
            quote_spent = float(order.get("cummulativeQuoteQty", amount))
        else:
            quantity = amount / price
            quote_spent = amount

        trade = TrendTrade.new(
            entry_price=price,
            quantity=quantity,
            quote_spent=quote_spent,
            dry_run=not self._config.trading_enabled,
        )
        self._ledger.record_entry(trade)

        logger.info("Trend-Einstieg: %s @ %.2f (Menge: %.8f)", self._config.symbol, price, quantity)
        tag = "[TREND-EINSTIEG]" if order is not None else "[TREND-EINSTIEG DRY-RUN]"
        send_notification(
            f"{tag} Long {quantity:.8f} {self._config.symbol} @ {price:.2f}"
        )

    def _close_position(self, open_trade: dict, price: float, reason: str) -> None:
        order = self._client.place_market_sell(self._config.symbol, open_trade["quantity"])
        if order is not None:
            proceeds = float(order.get("cummulativeQuoteQty", open_trade["quantity"] * price))
        else:
            proceeds = open_trade["quantity"] * price
        realized_pnl = proceeds - open_trade["quote_spent"]

        exit_time = datetime.now(timezone.utc).isoformat()
        self._ledger.record_exit(open_trade["id"], price, exit_time, reason, realized_pnl)

        reason_label = "Stop-Loss" if reason == "stop_loss" else "Signal-Umkehr"
        logger.info(
            "Trend-Ausstieg (%s): %s @ %.2f (Einstieg @ %.2f), realisiert %.2f",
            reason_label,
            self._config.symbol,
            price,
            open_trade["entry_price"],
            realized_pnl,
        )
        tag = "[TREND-AUSSTIEG]" if order is not None else "[TREND-AUSSTIEG DRY-RUN]"
        send_notification(
            f"{tag} ({reason_label}): {open_trade['quantity']:.8f} {self._config.symbol} "
            f"@ {price:.2f} (Einstieg @ {open_trade['entry_price']:.2f}), "
            f"realisiert: {realized_pnl:+.2f}"
        )

        if reason == "stop_loss":
            loss_pct = (1 - price / open_trade["entry_price"]) * 100
            self._stop_loss.pause(self._config.symbol, open_trade["entry_price"], price, loss_pct)

    def execute_once(self) -> None:
        """
        Führt genau einen Trend-Following-Zyklus aus. Der aktuell
        abgefragte Preis wird als Näherung für die Tagesschlusskerze
        verwendet (der Bot läuft einmal täglich, siehe interval_hours) -
        für eine exaktere Umsetzung müsste man auf den echten
        Tagesabschluss warten, das wäre für diesen Bot unnötig komplex.
        """
        self._kill_switch.check()

        if not self._seeded:
            self._seed_with_history()

        price = self._client.get_current_price(self._config.symbol)
        logger.info(
            "Aktueller Preis für %s: %.2f (Näherung für Tagesschlusskurs)",
            self._config.symbol,
            price,
        )

        state = self._signal_gen.feed(price)
        confirmed = state["confirmed_direction"]
        open_trade = self._ledger.open_position()

        if open_trade is not None:
            if is_stop_loss_hit(open_trade["entry_price"], price, self._config.stop_loss_pct):
                self._close_position(open_trade, price, reason="stop_loss")
                return

            action = decide_action(confirmed, has_open_position=True, stop_loss_paused=False)
            if action == "EXIT_SIGNAL":
                self._close_position(open_trade, price, reason="signal")
            return

        if self._stop_loss.is_paused():
            logger.warning(
                "Trend-Stop-Loss weiterhin pausiert - neue Einstiege für %s werden "
                "übersprungen, bis manuell zurückgesetzt (siehe reset_trend_stop_loss.py).",
                self._config.symbol,
            )
            return

        # Erneute Prüfung unmittelbar vor einem neuen Einstieg, damit ein
        # Notaus, der während Preisabfrage/Signalauswertung ausgelöst
        # wurde, ihn noch verhindert statt erst im nächsten Zyklus zu greifen.
        self._kill_switch.check()

        action = decide_action(confirmed, has_open_position=False, stop_loss_paused=False)
        if action == "ENTER":
            self._open_position(price)

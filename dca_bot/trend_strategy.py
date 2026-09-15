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

from .allocator_signals import MIN_EFFECTIVE_QUOTE_AMOUNT, read_allocation_fraction
from .backtest import fetch_historical_klines
from .binance_client import TradingClient
from .notifier import send_notification
from .risk import KillSwitch
from .trend_config import TrendConfig
from .trend_risk import TrendLedger, TrendStopLoss, TrendTrade
from .trend_signals import TrendSignalGenerator, decide_action, is_stop_loss_hit

logger = logging.getLogger("trend_bot")

# Ab wie vielen aufeinanderfolgenden Zyklen mit unklarem Stop-Order-Status
# (siehe _resolve_stop_order_before_close) eine explizite
# Telegram-Warnung ausgelöst wird - ein einzelner unklarer Zyklus ist
# noch kein Grund zur Sorge (kann ein einmaliger Netzwerk-Hänger sein),
# mehrere in Folge deuten auf ein anhaltendes Problem hin.
UNCERTAIN_CYCLES_WARNING_THRESHOLD = 3


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

        # Optionale Kapital-Allocator-Anbindung (siehe allocator.py): nur
        # aktiv, wenn TREND_ALLOCATOR_STATE_FILE explizit gesetzt ist -
        # sonst read_allocation_fraction() -> None und amount bleibt
        # unverändert (exakt das Verhalten ohne Allocator).
        trend_fraction = read_allocation_fraction(self._config.allocator_state_file)
        if trend_fraction is not None:
            amount = self._config.amount_per_trade * trend_fraction
            logger.info(
                "Allocator aktiv: Trend-Anteil %.1f%% -> effektiver Einstiegsbetrag %.2f (Basis %.2f).",
                trend_fraction * 100,
                amount,
                self._config.amount_per_trade,
            )
            if amount < MIN_EFFECTIVE_QUOTE_AMOUNT:
                logger.info(
                    "Effektiver Einstiegsbetrag %.2f unter Mindestbetrag (%.2f) - "
                    "Einstieg übersprungen (Allocator weist Trend aktuell kaum Kapital zu).",
                    amount,
                    MIN_EFFECTIVE_QUOTE_AMOUNT,
                )
                return

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

        # Echte, exchange-seitige Stop-Loss-Order (STOP_LOSS_LIMIT) direkt
        # nach dem Entry platzieren - schützt die Position auch, wenn der
        # Bot-Prozess danach ausfällt (Strom-/Internetausfall). Im
        # Dry-Run platziert place_stop_loss_limit_sell selbst keine echte
        # Order (siehe binance_client.py) und gibt None zurück - die
        # Position bleibt dann wie bisher rein per is_stop_loss_hit()
        # software-intern überwacht.
        stop_price = price * (1 - self._config.stop_loss_pct / 100)
        limit_price = stop_price * (1 - self._config.stop_limit_offset_pct / 100)
        stop_order = self._client.place_stop_loss_limit_sell(
            self._config.symbol, quantity, stop_price, limit_price
        )
        if stop_order is not None:
            trade.stop_loss_order_id = str(stop_order["orderId"])
            trade.stop_limit_price = limit_price
        elif self._config.trading_enabled:
            # Echter Trading-Modus, aber die Stop-Loss-Order konnte nicht
            # platziert werden (siehe Fehler-Log in binance_client.py) -
            # die Position ist jetzt NUR noch software-intern geschützt
            # (is_stop_loss_hit in execute_once), also genau der Zustand,
            # den diese Funktion eigentlich vermeiden soll. Muss sichtbar
            # sein, nicht nur im Log verschwinden.
            logger.warning(
                "Stop-Loss-Order für %s konnte nicht platziert werden - "
                "Position ist bis zum nächsten erfolgreichen Versuch nur "
                "noch software-intern abgesichert (kein Schutz bei "
                "Bot-Ausfall).",
                self._config.symbol,
            )
            send_notification(
                f"[TREND-FEHLER] Exchange-seitige Stop-Loss-Order für "
                f"{self._config.symbol} konnte NICHT platziert werden - "
                "Position aktuell nur software-intern abgesichert."
            )

        self._ledger.record_entry(trade)

        logger.info("Trend-Einstieg: %s @ %.2f (Menge: %.8f)", self._config.symbol, price, quantity)
        tag = "[TREND-EINSTIEG]" if order is not None else "[TREND-EINSTIEG DRY-RUN]"
        send_notification(
            f"{tag} Long {quantity:.8f} {self._config.symbol} @ {price:.2f}"
        )

    def _resolve_stop_order_before_close(self, open_trade: dict) -> str:
        """
        Storniert eine noch offene, exchange-seitige Stop-Loss-Order,
        BEVOR der Bot selbst per Market-Order verkauft (Signal-Exit oder
        interner Stop-Loss-Trigger) - sonst bliebe nach dem Verkauf eine
        verwaiste Sell-Order an der Börse zurück, die die Position
        theoretisch ein zweites Mal verkaufen würde.

        RACE CONDITION: Zwischen dem letzten Order-Status-Check
        (_check_exchange_stop_loss_fill, noch "NEW") und diesem
        cancel_order()-Aufruf kann die Order an der Börse tatsächlich
        gefüllt worden sein - dann schlägt das Stornieren fehl, und ein
        anschließender Market-Sell würde eine bereits verkaufte Position
        ein zweites Mal zu verkaufen versuchen. cancel_order() selbst
        unterscheidet NICHT, warum die Stornierung fehlschlug (jeder
        API-/Order-Fehler wird dort einheitlich behandelt, siehe
        binance_client.py) - deshalb wird hier bei jedem Fehlschlag die
        tatsächliche Ground Truth per get_order_status() nachgeprüft,
        statt sich auf einen bestimmten Fehlercode zu verlassen:

        - Stornierung erfolgreich -> "safe_to_sell" (Order bestätigt weg).
        - Stornierung fehlgeschlagen, Order laut Status FILLED -> Position
          wird hier direkt anhand der Fülldaten geschlossen (KEIN
          Market-Sell), "already_closed".
        - Stornierung fehlgeschlagen, Order laut Status CANCELED/EXPIRED/
          REJECTED (schon anderweitig terminiert, ohne Fill) ->
          "safe_to_sell" (kein Risiko einer Doppel-Order mehr).
        - Stornierung fehlgeschlagen UND Order laut Status weiterhin NEW/
          PARTIALLY_FILLED, oder die Status-Abfrage selbst schlägt fehl ->
          echter transienter Fehler (z.B. Netzwerk), Ground Truth bleibt
          unklar. Bewusst WEDER als geschlossen markieren NOCH verkaufen
          (Doppel-Order-Risiko) - "uncertain", der Exit wird im nächsten
          Zyklus erneut versucht. Ein Zähler (TrendTrade.uncertain_cycles)
          zählt aufeinanderfolgende "uncertain"-Zyklen für dieselbe
          Position; ab UNCERTAIN_CYCLES_WARNING_THRESHOLD in Folge löst
          das eine explizite Telegram-Warnung aus (manuelle Prüfung
          empfohlen - der Bot kann diesen Zustand allein nicht auflösen).
          Bei jedem eindeutigen Ergebnis wird der Zähler zurückgesetzt.
        """
        order_id = open_trade.get("stop_loss_order_id")
        if not order_id:
            return "safe_to_sell"  # keine Stop-Order vorhanden (Dry-Run o.ä.)

        if self._client.cancel_order(self._config.symbol, order_id) is not None:
            self._reset_uncertain_cycles(open_trade)
            return "safe_to_sell"

        status = self._client.get_order_status(self._config.symbol, order_id)
        order_state = status.get("status") if status is not None else None

        if order_state == "FILLED":
            self._close_from_filled_stop_order(open_trade, status)
            return "already_closed"

        if order_state in ("CANCELED", "EXPIRED", "REJECTED"):
            self._reset_uncertain_cycles(open_trade)
            return "safe_to_sell"

        self._register_uncertain_cycle(open_trade, order_id, order_state)
        return "uncertain"

    def _reset_uncertain_cycles(self, open_trade: dict) -> None:
        if open_trade.get("uncertain_cycles", 0) != 0:
            self._ledger.set_uncertain_cycles(open_trade["id"], 0)

    def _register_uncertain_cycle(self, open_trade: dict, order_id: str, order_state: str | None) -> None:
        count = open_trade.get("uncertain_cycles", 0) + 1
        self._ledger.set_uncertain_cycles(open_trade["id"], count)

        logger.warning(
            "Stornieren der Stop-Loss-Order %s fehlgeschlagen und Status "
            "unklar (%s) - vermutlich transienter Fehler (%d. Zyklus in "
            "Folge). Verkaufe JETZT nicht (Risiko einer Doppel-Order) und "
            "markiere die Position NICHT als geschlossen - wird im "
            "nächsten Zyklus erneut geprüft.",
            order_id,
            order_state,
            count,
        )

        if count >= UNCERTAIN_CYCLES_WARNING_THRESHOLD:
            logger.warning(
                "Stop-Order-Status für %s seit %d Zyklen in Folge unklar - "
                "manuelle Prüfung empfohlen (der Bot kann diesen Zustand "
                "allein nicht auflösen).",
                self._config.symbol,
                count,
            )
            send_notification(
                f"[TREND-WARNUNG] {self._config.symbol}: Stop-Order-Status "
                f"seit {count} Zyklen unklar, manuelle Prüfung empfohlen."
            )

    def _close_position(self, open_trade: dict, price: float, reason: str) -> None:
        outcome = self._resolve_stop_order_before_close(open_trade)
        if outcome == "already_closed":
            return  # per _close_from_filled_stop_order bereits erledigt
        if outcome == "uncertain":
            return  # nichts tun, naechster Zyklus prueft erneut

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

    def _close_from_filled_stop_order(
        self, open_trade: dict, order_status: dict, log_prefix: str = ""
    ) -> None:
        """
        Schließt eine Position im Ledger, nachdem festgestellt wurde, dass
        ihre echte, exchange-seitige Stop-Loss-Order bereits FILLED ist -
        die Börse hat den Verkauf also schon durchgeführt, OHNE dass der
        Bot etwas tun musste (das ist der ganze Sinn der Absicherung, z.B.
        wenn die Order während einer Bot-Downtime auslöste). Es wird
        NICHT nochmal verkauft, nur der Ledger anhand der tatsächlichen
        Fülldaten der Order korrigiert.

        `log_prefix` erlaubt main_trend.py, denselben Ablauf für den
        Reconciliation-Schritt beim Bot-Start mit einem eigenen,
        gut auffindbaren Log-Tag ("[REKONZILIATION]") wiederzuverwenden.
        """
        executed_qty = float(order_status.get("executedQty", open_trade["quantity"]))
        cumulative_quote = float(order_status.get("cummulativeQuoteQty", 0.0))
        if executed_qty > 0 and cumulative_quote > 0:
            exit_price = cumulative_quote / executed_qty
            proceeds = cumulative_quote
        else:
            exit_price = float(order_status.get("price", open_trade["entry_price"]))
            proceeds = open_trade["quantity"] * exit_price
        realized_pnl = proceeds - open_trade["quote_spent"]

        exit_time = datetime.now(timezone.utc).isoformat()
        self._ledger.record_exit(open_trade["id"], exit_price, exit_time, "stop_loss", realized_pnl)

        logger.warning(
            "%sExchange-seitige Stop-Loss-Order bereits gefüllt: %s @ %.2f "
            "(Einstieg @ %.2f), realisiert %.2f - Position im Ledger als "
            "geschlossen markiert, kein weiterer Verkaufsversuch.",
            log_prefix,
            self._config.symbol,
            exit_price,
            open_trade["entry_price"],
            realized_pnl,
        )
        self._log_stop_fill_analysis(open_trade, exit_price, log_prefix)
        send_notification(
            f"{log_prefix}[TREND-AUSSTIEG] (Stop-Loss, Exchange-Order gefüllt): "
            f"{open_trade['quantity']:.8f} {self._config.symbol} @ {exit_price:.2f} "
            f"(Einstieg @ {open_trade['entry_price']:.2f}), realisiert: {realized_pnl:+.2f}"
        )

    def _log_stop_fill_analysis(self, open_trade: dict, exit_price: float, log_prefix: str) -> None:
        """
        Dediziertes, leicht auffindbares Logging für das tatsächliche
        Füllverhalten der echten Stop-Loss-Order (eigenes Log-Tag
        "[STOP-FILL-ANALYSE]", getrennt von der normalen Ausstiegs-
        Meldung) - sammelt über die Paper-Trade-Phase automatisch echte
        Daten dazu, wie zuverlässig TREND_STOP_LIMIT_OFFSET_PCT in der
        Praxis ist (der bisherige Backtest dazu hatte nur eine sehr
        kleine Stichprobe, siehe trading-bot-projekt.md). Kein manuelles
        Nachhalten nötig - einfach `grep STOP-FILL-ANALYSE logs/trend_bot.log`
        nach ein paar Monaten Live-Betrieb.

        Nur möglich, wenn stop_limit_price bekannt ist (echter Trading-
        Modus, Stop-Order wurde erfolgreich platziert) - im Dry-Run oder
        nach einem fehlgeschlagenen Order-Platzierungsversuch (siehe
        _open_position) fehlt der Vergleichswert, dann wird nichts geloggt.
        """
        limit_price = open_trade.get("stop_limit_price")
        if limit_price is None:
            return

        diff_pct = (exit_price - limit_price) / limit_price * 100
        logger.info(
            "%s[STOP-FILL-ANALYSE] Limit: %.2f, gefüllt bei: %.2f, Differenz: %+.3f%%",
            log_prefix,
            limit_price,
            exit_price,
            diff_pct,
        )

        loss_pct = (1 - exit_price / open_trade["entry_price"]) * 100
        self._stop_loss.pause(self._config.symbol, open_trade["entry_price"], exit_price, loss_pct)

    def _check_exchange_stop_loss_fill(self, open_trade: dict, log_prefix: str = "") -> bool:
        """
        Fragt für eine offene Position mit gespeicherter
        stop_loss_order_id den aktuellen Order-Status ab und schließt die
        Position im Ledger, falls die Stop-Loss-Order bereits FILLED ist.
        Gibt True zurück, falls das der Fall war (der aufrufende Zyklus
        soll dann nicht mehr normal weiterlaufen), sonst False - auch
        wenn keine stop_loss_order_id vorliegt (Dry-Run, oder die Order
        konnte beim Entry nicht platziert werden).

        Wird sowohl vom regulären Zyklus (execute_once) als auch vom
        Reconciliation-Schritt beim Bot-Start (reconcile_on_startup)
        verwendet - `log_prefix` erlaubt Letzterem, dieselbe Logik mit
        einem eigenen, gut auffindbaren Log-Tag ("[REKONZILIATION]") zu
        markieren.
        """
        order_id = open_trade.get("stop_loss_order_id")
        if not order_id:
            return False

        status = self._client.get_order_status(self._config.symbol, order_id)
        if status is not None and status.get("status") == "FILLED":
            self._close_from_filled_stop_order(open_trade, status, log_prefix=log_prefix)
            return True
        return False

    def reconcile_on_startup(self) -> None:
        """
        Wird einmalig beim Bot-Start VOR dem ersten regulären Zyklus
        aufgerufen (siehe main_trend.py): gleicht eine im Ledger offene
        Position gegen den tatsächlichen Status ihrer Stop-Loss-Order bei
        Binance ab. Falls die Order während einer Downtime des
        Bot-Prozesses (Absturz, Stromausfall, Server-Neustart) gefüllt
        wurde, wäre der Ledger sonst bis zum nächsten Zyklus falsch (zeigt
        fälschlich noch eine offene Position) - das wird hier VOR dem
        ersten Zyklus korrigiert, klar geloggt und per Telegram gemeldet.
        """
        open_trade = self._ledger.open_position()
        if open_trade is None:
            return

        if self._check_exchange_stop_loss_fill(open_trade, log_prefix="[REKONZILIATION] "):
            return
        logger.info(
            "Reconciliation: offene Position für %s unverändert (Stop-Loss-Order "
            "nicht gefüllt oder keine Order hinterlegt).",
            self._config.symbol,
        )

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
            # ZUERST prüfen, ob die echte, exchange-seitige Stop-Loss-Order
            # bereits gefüllt wurde (z.B. weil der Preis zwischen zwei
            # Zyklen durchgerauscht ist) - dann hat die Börse die Position
            # bereits verkauft, ein eigener Market-Sell-Versuch würde auf
            # ein zu niedriges/fehlendes Guthaben laufen.
            if self._check_exchange_stop_loss_fill(open_trade):
                return

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

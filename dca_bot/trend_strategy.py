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
import time
from datetime import datetime, timedelta, timezone

from .allocator_signals import MIN_EFFECTIVE_QUOTE_AMOUNT, read_allocation_fraction
from .backtest import fetch_historical_klines
from .balance_guard import (
    SELL_INSUFFICIENT,
    BalanceSnapshot,
    build_snapshot,
    check_sell_coverage,
    describe,
    ledger_exceeds_account,
)
from .binance_client import TradingClient
from .notifier import send_notification
from .order_utils import (
    average_fill_price,
    net_executed_quantity,
    net_proceeds,
    quantize_quantity,
)
from .pending_orders import (
    KIND_MARKET,
    KIND_STOP_LOSS_LIMIT,
    ManualReviewRequired,
    ORDER_CONFIRMED,
    ORDER_LIFECYCLE_DEAD,
    ORDER_LIFECYCLE_FILLED,
    ORDER_LIFECYCLE_LIVE,
    ORDER_UNKNOWN,
    ORDER_WITHOUT_EFFECT,
    RECONCILIATION_PREFIX,
    PendingOrder,
    executed_quantity,
    order_lifecycle_state,
    reconcile_pending_orders,
    resolve_pending_order,
)
from .risk import KillSwitch
from .startup_checks import report_ledger_vs_account
from .trend_config import TrendConfig
from .trend_risk import TrendLedger, TrendStopLoss, TrendTrade, open_quantity
from .trend_signals import TrendSignalGenerator, decide_action, is_stop_loss_hit

logger = logging.getLogger("trend_bot")

# Ab wie vielen aufeinanderfolgenden Zyklen mit unklarem Stop-Order-Status
# (siehe _resolve_stop_order_before_close) eine explizite
# Telegram-Warnung ausgelöst wird - ein einzelner unklarer Zyklus ist
# noch kein Grund zur Sorge (kann ein einmaliger Netzwerk-Hänger sein),
# mehrere in Folge deuten auf ein anhaltendes Problem hin.
UNCERTAIN_CYCLES_WARNING_THRESHOLD = 3

# Ab wie vielen aufeinanderfolgenden Zyklen gewarnt wird, in denen eine
# offene Position keine exchange-seitige Stop-Loss-Order hatte und auch
# keine neue platziert werden konnte (siehe
# _ensure_stop_loss_protection). Gleiche Schwelle und gleiche Begruendung
# wie oben: ein einzelner Fehlschlag kann transient sein, mehrere in
# Folge deuten auf ein anhaltendes Problem hin.
UNPROTECTED_CYCLES_WARNING_THRESHOLD = 3

# Platzhalter in Meldungen, wenn der Status einer Order nicht ermittelt
# werden konnte (siehe _describe_stop_order_status). Bewusst ein
# eigener, ausformulierter Text statt "?" oder eines weggelassenen
# Feldes: "nicht abrufbar" heisst "der Bot konnte es nicht klaeren" und
# ist fuer die manuelle Pruefung eine andere Aussage als jeder echte
# Order-Status.
STOP_ORDER_STATUS_UNAVAILABLE = "nicht abrufbar"

# Nachfrage nach einem Verkauf mit unklarem Ausgang (Systemcheck vom
# 27.09.2026, K-B, Entscheidung 2): bis zu 3 Rueckfragen im Abstand von
# 20 s, zusammen etwa eine Minute. Der Trend-Bot laeuft nur einmal am Tag -
# ohne diese Nachfrage laege bis zum naechsten Zyklus weder eine
# Stop-Order an der Boerse noch waere klar, ob die Position ueberhaupt noch
# existiert. Eine Minute deckt die naechtliche Zwangstrennung (wenige
# Sekunden) ab und reicht, damit "Order unbekannt" endgueltig wird (siehe
# pending_orders.UNKNOWN_FINAL_AFTER_SECONDS). Der Notaus reagiert in dieser
# Zeit verzoegert.
UNCLEAR_SELL_RECHECKS = 3
UNCLEAR_SELL_RECHECK_SECONDS = 20.0

# Eigener Name statt time.sleep direkt - die Tests ersetzen ihn.
_sleep = time.sleep


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
        # clientOrderIds, zu denen die laufende Reconciliation bereits per
        # Telegram eskaliert hat - jede nur einmal pro Prozesslauf.
        self._pending_escalated: set[str] = set()

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

        # Handelsregeln bewusst VOR dem Kauf holen (danach aus dem Cache):
        # schlägt der Abruf fehl, bricht der Zyklus ab, ohne dass eine
        # Order existiert. Nach einem ausgeführten Kauf hier eine Exception
        # zu riskieren, würde den Trade unverbucht lassen.
        rules = self._client.get_symbol_trading_rules(self._config.symbol)

        order = self._client.place_market_buy(
            self._config.symbol, amount, context={"price": price, "amount": amount}
        )

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
            # Tatsaechlicher Fuellpreis aus der Order-Antwort
            # (cummulativeQuoteQty / executedQty), nicht der vor der Order
            # abgefragte Ticker - gleiche Quelle wie im Reconciliation-Pfad
            # (_record_reconciled_entry). Hier zaehlt das mehr als beim
            # Grid-Bot, wo es "nur" die Anzeige betraf: aus entry_price
            # entsteht die Stop-Loss-Schwelle - fuer die Order an der Boerse
            # unten, fuer is_stop_loss_hit() und fuer jede spaeter neu
            # platzierte Absicherung. Bis zum 25.09.2026 stand hier der
            # Ticker, die Schwelle lag also um die Slippage des Kaufs daneben.
            entry_price = average_fill_price(order, fallback=price)
            # Menge abzüglich der in BTC abgezogenen Kaufgebühr. Das ist
            # hier besonders wichtig: mit dieser Menge wird gleich die
            # exchange-seitige Stop-Loss-Order platziert - über die
            # ungekürzte Menge würde die Börse sie ablehnen, und die
            # Position bliebe ungeschützt.
            quantity = net_executed_quantity(order, rules, fallback=amount / price)
            quote_spent = float(order.get("cummulativeQuoteQty", amount))
        else:
            # Dry-Run: der beobachtete Preis IST der simulierte Fill.
            entry_price = price
            # Dry-Run: keine echte Gebühr bekannt, deshalb keine geschätzte
            # abgezogen - die Menge wird aber quantisiert, damit simulierte
            # und echte Werte vergleichbar bleiben.
            quantity = quantize_quantity(amount / price, rules.step_size)
            # Der Betrag muss der quantisierten Menge folgen: die
            # weggerundete Teilmenge wurde nie gekauft. Ein echter Fill
            # liefert oben cummulativeQuoteQty, also den tatsaechlich
            # belasteten Betrag - `quantity * price` ist dessen
            # Entsprechung im Dry-Run. Sonst stuende eine zu hohe
            # Kostenbasis im Ledger und die realisierte PnL dieses Trades
            # waere um die Differenz zu negativ. Mit aktivem Allocator
            # wiegt das zusaetzlich schwerer, weil `amount` dann kleiner
            # ist und dieselbe Mengenstufe relativ mehr ausmacht.
            quote_spent = quantity * price

        trade = TrendTrade.new(
            entry_price=entry_price,
            quantity=quantity,
            quote_spent=quote_spent,
            dry_run=not self._config.trading_enabled,
            client_order_id=order.get("clientOrderId") if order else None,
        )

        # Ledger-Eintrag SOFORT nach dem bestätigten Kauf - bewusst VOR
        # der Stop-Loss-Order (Sicherheitsreview-Punkt K2). Vorher stand
        # record_entry() am Ende dieser Methode, und dazwischen lagen ein
        # kompletter zweiter API-Call plus Telegram-Sendeversuche: ein
        # Prozess-Kill in diesem Fenster (mehrere Sekunden) hätte einen
        # real gekauften, ungeschützten Trade hinterlassen, von dem das
        # Ledger nichts weiß - der nächste Zyklus hätte "keine offene
        # Position" gesehen und bei weiter bestätigtem Aufwärtstrend
        # erneut gekauft. Die Stop-Order wird jetzt nachträglich am
        # bereits bestehenden Eintrag hinterlegt.
        self._ledger.record_entry(trade)
        # Erst mit dem Einstieg im Ledger ist die Order-Frage erledigt (W-A).
        self._client.confirm_booked(trade.client_order_id)

        # Echte, exchange-seitige Stop-Loss-Order (STOP_LOSS_LIMIT) direkt
        # nach dem Entry platzieren - schützt die Position auch, wenn der
        # Bot-Prozess danach ausfällt (Strom-/Internetausfall). Im
        # Dry-Run platziert place_stop_loss_limit_sell selbst keine echte
        # Order (siehe binance_client.py) und gibt None zurück - die
        # Position bleibt dann wie bisher rein per is_stop_loss_hit()
        # software-intern überwacht.
        stop_price = entry_price * (1 - self._config.stop_loss_pct / 100)
        limit_price = stop_price * (1 - self._config.stop_limit_offset_pct / 100)
        stop_order = self._client.place_stop_loss_limit_sell(
            self._config.symbol,
            quantity,
            stop_price,
            limit_price,
            context={"trade_id": trade.id, "limit_price": limit_price},
        )
        if stop_order is not None:
            trade.stop_loss_order_id = str(stop_order["orderId"])
            trade.stop_limit_price = limit_price
            self._ledger.set_stop_loss_order(
                trade.id, trade.stop_loss_order_id, limit_price
            )
            self._client.confirm_booked(stop_order.get("clientOrderId"))
        elif self._config.trading_enabled:
            # Echter Trading-Modus, aber die Stop-Loss-Order konnte nicht
            # platziert werden (siehe Fehler-Log in binance_client.py) -
            # die Position ist jetzt NUR noch software-intern geschützt
            # (is_stop_loss_hit in execute_once), also genau der Zustand,
            # den diese Funktion eigentlich vermeiden soll. Muss sichtbar
            # sein, nicht nur im Log verschwinden.
            #
            # "Bis zum nächsten erfolgreichen Versuch" ist seit
            # _ensure_stop_loss_protection() auch tatsächlich eingelöst:
            # jeder folgende Zyklus (und der Reconciliation-Schritt beim
            # Start) versucht die fehlende Order neu zu platzieren und
            # eskaliert per unprotected_cycles, falls das dauerhaft
            # scheitert. Vorher behauptete dieser Text einen
            # Wiederholungsversuch, den es im Code nirgends gab.
            logger.warning(
                "Stop-Loss-Order für %s konnte nicht platziert werden - "
                "Position ist bis zum nächsten erfolgreichen Versuch nur "
                "noch software-intern abgesichert (kein Schutz bei "
                "Bot-Ausfall). Der nächste Zyklus versucht es erneut.",
                self._config.symbol,
            )
            send_notification(
                f"[TREND-FEHLER] Exchange-seitige Stop-Loss-Order für "
                f"{self._config.symbol} konnte NICHT platziert werden - "
                "Position aktuell nur software-intern abgesichert."
            )

        logger.info(
            "Trend-Einstieg: %s @ %.2f (Menge: %.8f)", self._config.symbol, entry_price, quantity
        )
        tag = "[TREND-EINSTIEG]" if order is not None else "[TREND-EINSTIEG DRY-RUN]"
        send_notification(
            f"{tag} Long {quantity:.8f} {self._config.symbol} @ {entry_price:.2f}"
        )

    def _resolve_stop_order_before_close(self, open_trade: dict, rules=None) -> str:
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

        TEILFÜLLUNG (Systemcheck vom 27.09.2026, K-A): Binance storniert
        auch eine PARTIALLY_FILLED-Order, und die Antwort trägt
        `executedQty`. Bis zu diesem Fix wurde nur geprüft, ob die Antwort
        None ist - danach verkaufte der Bot die VOLLE Menge, obwohl ein Teil
        schon weg war. Die Deckungsprüfung ließ das durch, weil auf dem
        geteilten Konto das freie BTC des DCA-Bots den Fehlbetrag deckte.
        Jetzt wird die Teilfüllung verbucht (_book_stop_fill) und danach
        nur noch der Rest verkauft. Der Status wird dabei ausschließlich
        über `order_lifecycle_state()` bewertet (W8) - die früheren
        String-Vergleiche kannten "beendet MIT Teilfüllung" nicht.
        """
        order_id = open_trade.get("stop_loss_order_id")
        if not order_id:
            return "safe_to_sell"  # keine Stop-Order vorhanden (Dry-Run o.ä.)

        cancelled = self._client.cancel_order(self._config.symbol, order_id)
        if cancelled is not None:
            self._reset_uncertain_cycles(open_trade)
            if executed_quantity(cancelled) > 0:
                if self._book_stop_fill(open_trade, cancelled, rules) == "already_closed":
                    return "already_closed"
            return "safe_to_sell"

        status = self._client.get_order_status(self._config.symbol, order_id)
        state = order_lifecycle_state(status)

        if state == ORDER_LIFECYCLE_FILLED:
            self._reset_uncertain_cycles(open_trade)
            if self._book_stop_fill(open_trade, status, rules) == "already_closed":
                return "already_closed"
            return "safe_to_sell"  # Teilfüllung verbucht, Order beendet

        if state == ORDER_LIFECYCLE_DEAD:
            self._reset_uncertain_cycles(open_trade)
            return "safe_to_sell"

        order_state = status.get("status") if isinstance(status, dict) else None
        self._register_uncertain_cycle(open_trade, order_id, order_state)
        return "uncertain"

    def _book_stop_fill(
        self, open_trade: dict, order: dict, rules=None, log_prefix: str = ""
    ) -> str:
        """
        Verbucht eine BEENDETE Stop-Order, die Menge bewegt hat (K-A).

        - Hat sie die offene Menge (bis auf weniger als eine stepSize)
          verkauft, ist die Position geschlossen: _close_from_filled_stop_order,
          Rückgabe "already_closed".
        - Sonst war es eine Teilfüllung: Menge und Erlös kommen an die
          Position (record_partial_stop_fill, idempotent über die orderId),
          die Stop-Zuordnung wird gelöst, Rückgabe "partial". Der Aufrufer
          verkauft danach den Rest.

        Bewusst über die Menge und nicht über den Status "FILLED"
        entschieden: eine Stop-Order über eine auf die stepSize
        abgerundete Menge ist FILLED, obwohl ein Rest unterhalb einer
        stepSize im Ledger steht - und eine stornierte Order kann trotzdem
        fast alles verkauft haben.

        Ohne Handelsregeln (Abruf gescheitert) gilt als Toleranz 0 - im
        Zweifel wird also eine Teilfüllung verbucht und der Rest später
        als Staub geschlossen, statt einen offenen Rest zu verschweigen.
        """
        if rules is None:
            try:
                rules = self._client.get_symbol_trading_rules(self._config.symbol)
            except Exception as exc:
                logger.warning(
                    "%sHandelsregeln nicht abrufbar (%s) - Teilfüllung wird "
                    "ohne stepSize-Toleranz bewertet.",
                    log_prefix,
                    type(exc).__name__,
                )
        step_size = rules.step_size if rules is not None else 0.0

        executed = executed_quantity(order)
        remainder = open_quantity(open_trade) - executed
        if remainder < step_size or remainder <= 1e-12:
            self._close_from_filled_stop_order(open_trade, order, log_prefix=log_prefix)
            return "already_closed"

        order_id = str(order.get("orderId", ""))
        gross = float(order.get("cummulativeQuoteQty", 0.0) or 0.0)
        proceeds = gross
        try:
            enriched = self._client.get_order_with_fills(self._config.symbol, order)
            if rules is not None:
                proceeds = net_proceeds(enriched, rules, fallback=gross)
        except Exception as exc:
            # Gleiche Abwägung wie in _close_from_filled_stop_order: der
            # Verkauf hat stattgefunden, er MUSS ins Ledger - notfalls brutto.
            logger.warning(
                "%sGebührendaten zur Teilfüllung von Order %s nicht abrufbar "
                "(%s) - verbucht wird der Brutto-Erlös.",
                log_prefix,
                order_id,
                type(exc).__name__,
            )

        limit_price = open_trade.get("stop_limit_price")
        booked = self._ledger.record_partial_stop_fill(
            open_trade["id"], order_id, executed, gross, proceeds
        )
        if not booked:
            logger.info(
                "%sTeilfüllung von Stop-Order %s ist bereits verbucht.",
                log_prefix,
                order_id,
            )
        # Den Dict mitziehen - der laufende Zyklus arbeitet mit ihm weiter.
        refreshed = self._ledger.trade_by_id(open_trade["id"]) or {}
        for key in (
            "partial_exit_qty",
            "partial_exit_quote",
            "partial_exit_proceeds",
            "partial_exit_order_ids",
            "stop_loss_order_id",
            "stop_limit_price",
        ):
            open_trade[key] = refreshed.get(key)
        if not booked:
            return "partial"

        fill_price = gross / executed if executed > 0 else 0.0
        logger.warning(
            "%s[TREND-TEILFUELLUNG] Stop-Loss-Order %s hat %.8f von %.8f "
            "verkauft (@ %.2f, Erlös netto %.2f) und ist beendet. Verbucht; "
            "offen bleiben %.8f.",
            log_prefix,
            order_id,
            executed,
            float(open_trade["quantity"]),
            fill_price,
            proceeds,
            open_quantity(open_trade),
        )
        if limit_price:
            diff_pct = (fill_price - limit_price) / limit_price * 100
            logger.info(
                "%s[STOP-FILL-ANALYSE] Limit: %.2f, gefüllt bei: %.2f, "
                "Differenz: %+.3f%% (Teilfüllung %.8f)",
                log_prefix,
                limit_price,
                fill_price,
                diff_pct,
                executed,
            )
        send_notification(
            f"{log_prefix}[TREND-TEILFUELLUNG] {self._config.symbol}: Stop-Loss-"
            f"Order {order_id} hat {executed:.8f} von "
            f"{float(open_trade['quantity']):.8f} @ {fill_price:.2f} verkauft. "
            f"Verbucht - der Rest ({open_quantity(open_trade):.8f}) wird als "
            "Stop-Loss-Ausstieg abgeschlossen."
        )
        return "partial"

    def _with_partial_fill(
        self, open_trade: dict, exit_price: float, sold_qty: float, proceeds: float
    ) -> tuple[float, float]:
        """
        Rechnet eine verbuchte Teilfüllung in den Ausstieg ein (K-A):
        exit_price als mengengewichteter Durchschnitt beider Teile,
        Erlös als Summe. Ohne Teilfüllung unverändert.
        """
        partial_qty = float(open_trade.get("partial_exit_qty") or 0.0)
        if partial_qty <= 0:
            return exit_price, proceeds
        partial_quote = float(open_trade.get("partial_exit_quote") or 0.0)
        partial_proceeds = float(open_trade.get("partial_exit_proceeds") or 0.0)
        total_qty = partial_qty + sold_qty
        weighted = (partial_quote + exit_price * sold_qty) / total_qty if total_qty else exit_price
        return weighted, proceeds + partial_proceeds

    def _remainder_is_dust(self, quantity: float, price: float, rules) -> bool:
        """
        Ob sich der Rest einer teilgefüllten Position noch verkaufen lässt:
        weniger als eine stepSize oder unter dem Mindestvolumen lehnt
        Binance jede Order ab.
        """
        sellable = quantize_quantity(quantity, rules.step_size)
        return sellable <= 0 or sellable * price < rules.min_notional

    def _close_with_dust(self, open_trade: dict, price: float, log_prefix: str = "") -> None:
        """
        Schließt eine Position, deren Rest nach einer Teilfüllung nicht mehr
        verkaufbar ist (K-A, Entscheidung 3 vom 27.09.2026). Ohne diese
        Regel käme der abgelehnte Verkauf jeden Zyklus als K1-Fehlschlag
        wieder - oder, schlimmer, eine neue Stop-Order über den Rest würde
        ebenfalls abgelehnt und die Position gälte als ungeschützt.

        Der Rest bleibt als Staub auf dem Konto und steht als `dust_qty` im
        Ledger; gemeldet wird er per Log und Telegram. Der Erlös ist allein
        der der Teilfüllung(en). Ausstiegsgrund stop_loss mit Latch - es
        hat ein Stop-Loss-Ereignis stattgefunden.
        """
        dust = open_quantity(open_trade)
        partial_qty = float(open_trade.get("partial_exit_qty") or 0.0)
        partial_quote = float(open_trade.get("partial_exit_quote") or 0.0)
        proceeds = float(open_trade.get("partial_exit_proceeds") or 0.0)
        exit_price = partial_quote / partial_qty if partial_qty > 0 else price
        realized_pnl = proceeds - open_trade["quote_spent"]

        self._ledger.record_exit(
            open_trade["id"],
            exit_price,
            datetime.now(timezone.utc).isoformat(),
            "stop_loss",
            realized_pnl,
            None,
            dust_qty=dust,
        )
        logger.warning(
            "%s[TREND-STAUB] Position %s geschlossen: nach der Teilfüllung "
            "bleiben %.8f %s (~%.2f USDT), unter dem Mindestvolumen und damit "
            "nicht verkaufbar. Der Rest bleibt als Staub auf dem Konto "
            "(dust_qty im Ledger). Realisiert %.2f.",
            log_prefix,
            open_trade["id"],
            dust,
            self._config.symbol,
            dust * price,
            realized_pnl,
        )
        send_notification(
            f"{log_prefix}[TREND-AUSSTIEG] (Stop-Loss, Teilfüllung): "
            f"{partial_qty:.8f} {self._config.symbol} @ {exit_price:.2f} verkauft, "
            f"realisiert: {realized_pnl:+.2f}. Rest {dust:.8f} (~{dust * price:.2f} "
            "USDT) liegt unter dem Mindestvolumen und bleibt als Staub auf dem "
            "Konto."
        )
        loss_pct = (1 - exit_price / open_trade["entry_price"]) * 100
        self._stop_loss.pause(
            self._config.symbol, open_trade["entry_price"], exit_price, loss_pct
        )

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
        """
        Schließt die offene Position per eigenem Market-Sell (Signal-Exit
        oder interner Stop-Loss-Trigger).

        Ob dabei tatsächlich eine echte Order platziert wird, hängt NICHT
        nur am aktuellen Trading-Modus, sondern zusätzlich am `dry_run`-Flag
        des Ledger-Eintrags (siehe trading-bot-projekt.md 7.3): eine im
        Dry-Run "gekaufte" Position existiert an der Börse gar nicht und
        darf deshalb auch nach einem Umschalten auf echtes Trading niemals
        real verkauft werden. Umgekehrt wird eine ECHTE Position bei
        deaktiviertem Trading gar nicht angefasst - weder ihre Stop-Order
        storniert noch simuliert geschlossen (siehe
        _report_exit_blocked_by_dry_run).
        """
        position_dry_run = open_trade.get("dry_run")
        if position_dry_run is None:
            # Ledger-Eintrag ohne dry_run-Feld (praktisch nur durch
            # manuelles Editieren möglich - TrendTrade schreibt es immer).
            # Hier wird bewusst NICHT geraten, gleiche Begründung wie in
            # grid_strategy.py._process_sells.
            logger.warning(
                "[TREND-POSITION-UNKLAR] Position %s hat kein dry_run-Feld im "
                "Ledger - Ausstieg (%s) wird NICHT ausgeführt, Position bleibt "
                "offen. Bitte manuell prüfen "
                "(python -m dca_bot.audit_positions).",
                open_trade["id"],
                reason,
            )
            return

        if not position_dry_run and not self._config.trading_enabled:
            # Spiegelbild zu K4 (siehe unten): eine ECHTE Position,
            # waehrend der Bot im Dry-Run laeuft. Bis zu diesem Fix lief der
            # Ausstieg hier einfach weiter - _resolve_stop_order_before_close()
            # stornierte die ECHTE Stop-Order an der Boerse (cancel_order
            # pruefte trading_enabled damals nicht - seither wirft es dort,
            # als zweite Sicherung hinter dieser), place_market_sell() simulierte
            # nur, und die Position wurde mit erfundenem Erloes geschlossen.
            # Ergebnis: echtes BTC, weder im Ledger noch durch eine
            # Stop-Order abgesichert.
            #
            # Deshalb bewusst VOR jeder Aktion an der Boerse und vor dem
            # Regel-Abruf: kein Stornieren, kein Verkauf, kein record_exit
            # und kein Stop-Loss-Latch (es hat kein Ausstieg
            # stattgefunden - gleiche Logik wie bei K1). Die Stop-Order an
            # der Boerse bleibt liegen und schuetzt die Position weiter.
            self._report_exit_blocked_by_dry_run(open_trade, price, reason)
            # Die Position ueberlebt diesen Zyklus - also dieselbe Pruefung
            # wie in execute_once() fuer eine offene Position: fehlt die
            # Stop-Order, wird gezaehlt und ab der Schwelle gemeldet. Der
            # Grund, warum sie dort erst NACH den Ausstiegs-Entscheidungen
            # laeuft (eine neue Order laege bei ausgeloestem Stop-Loss
            # unter der Schwelle und wuerde abgelehnt), gilt hier nicht:
            # bei deaktiviertem Trading wird ohnehin nichts platziert.
            self._ensure_stop_loss_protection(open_trade)
            return

        # Sperre (Systemcheck vom 27.09.2026, K-B): Steht fuer diesen Trade
        # noch ein Verkauf oder eine Stop-Order mit ungeklaertem Ausgang in
        # der Pending-Datei, wird NICHT erneut ausgestiegen. War die fruehere
        # Order durchgegangen, kaeme ein zweiter Verkauf aus dem Bestand
        # eines anderen Bots - die Deckungspruefung sieht nur `free`, nicht,
        # wem es gehoert. Die Reconciliation zu Beginn jedes Zyklus klaert
        # den Eintrag, sobald Binance wieder antwortet.
        pending = self._pending_sells(open_trade)
        if pending:
            logger.warning(
                "[TREND-AUSSTIEG-UNGEKLAERT] Ausstieg (%s) fuer Trade %s waere "
                "faellig, aber die Order(s) %s haben noch keinen geklaerten "
                "Ausgang - es wird NICHT erneut verkauft.",
                reason,
                open_trade["id"],
                ", ".join(p.client_order_id for p in pending),
            )
            self._ensure_stop_loss_protection(open_trade)
            return

        # Siehe _open_position: Regeln vor der ersten Order holen, damit
        # ein Fehlschlag folgenlos abbricht statt einen bereits
        # ausgeführten Verkauf unverbucht zu lassen.
        rules = self._client.get_symbol_trading_rules(self._config.symbol)

        outcome = self._resolve_stop_order_before_close(open_trade, rules)
        if outcome == "already_closed":
            return  # per _close_from_filled_stop_order bereits erledigt
        if outcome == "uncertain":
            return  # nichts tun, naechster Zyklus prueft erneut

        # Hat die Stop-Order schon teilweise verkauft (K-A), ist ein
        # Stop-Loss-Ereignis eingetreten - auch wenn dieser Ausstieg vom
        # Signal kam. Grund und Latch folgen dem, wie bei einer komplett
        # gefuellten Stop-Order (Entscheidung 1 vom 27.09.2026).
        if float(open_trade.get("partial_exit_qty") or 0.0) > 0:
            reason = "stop_loss"
            if self._remainder_is_dust(open_quantity(open_trade), price, rules):
                self._close_with_dust(open_trade, price)
                return
        sell_quantity = open_quantity(open_trade)

        if position_dry_run and self._config.trading_enabled:
            # place_market_sell() prüft nur config.trading_enabled, NICHT
            # das Positions-Flag - ein Aufruf wäre hier also eine echte
            # Order für eine nie gekaufte Position. Deshalb gar nicht erst
            # aufrufen, sondern direkt simulieren. (Eine Dry-Run-Position
            # hat per Konstruktion auch keine stop_loss_order_id, der
            # _resolve_stop_order_before_close-Aufruf oben ist für sie ein
            # No-op ohne API-Zugriff.)
            logger.warning(
                "[DRY-RUN-POSITION] Position %s wurde im Dry-Run eröffnet, "
                "Verkauf bleibt simuliert, unabhängig vom aktuellen "
                "Trading-Modus.",
                open_trade["id"],
            )
            order = None
        else:
            # Konsistenz-Check vor dem Verkauf (W11, siehe
            # balance_guard.py). Bewusst genau HIER: Bis
            # _resolve_stop_order_before_close() oben gelaufen ist, bindet
            # die eigene Stop-Loss-Order die komplette Positionsmenge -
            # das freie Guthaben wäre also systematisch zu klein und jede
            # Prüfung liefe ins Leere.
            if not self._sell_is_covered(open_trade):
                # Die Stop-Order ist zu diesem Zeitpunkt bereits
                # storniert. Ein einfaches `return` ließe die Position
                # damit ungeschützt zurück - genau der K1-Folgefund.
                # _handle_failed_real_sell() platziert sie neu.
                self._handle_failed_real_sell(
                    open_trade,
                    price,
                    cause="Verkauf mangels Deckung nicht versucht",
                )
                return

            order = self._client.place_market_sell(
                self._config.symbol,
                sell_quantity,
                context={
                    "trade_id": open_trade["id"],
                    "reason": reason,
                    "price": price,
                },
            )
            if order is None and self._config.trading_enabled:
                # Echter Verkaufsversuch bei der Börse fehlgeschlagen -
                # anders als im Dry-Run (wo None der Normalfall ist).
                # Kein erfundener Erlös, kein record_exit(): die Position
                # bleibt OFFEN und wird im nächsten Zyklus erneut versucht.
                self._handle_failed_real_sell(open_trade, price)
                return

        if order is not None:
            # Tatsaechlicher Fuellpreis statt des vorher abgefragten
            # Tickers - siehe _open_position; _record_reconciled_exit macht
            # es schon immer so. Er landet auch als exit_price in der
            # Latch-Datei, dem vorgesehenen Anker eines spaeteren
            # automatischen Resets (trading-bot-projekt.md 6i, Punkt 16).
            exit_price = average_fill_price(order, fallback=price)
            # Netto, also abzüglich der in USDT abgerechneten
            # Verkaufsgebühr - cummulativeQuoteQty ist der Bruttoerlös.
            proceeds = net_proceeds(order, rules, fallback=sell_quantity * price)
        else:
            exit_price = price
            proceeds = sell_quantity * price
        exit_price, proceeds = self._with_partial_fill(
            open_trade, exit_price, sell_quantity, proceeds
        )
        realized_pnl = proceeds - open_trade["quote_spent"]

        exit_time = datetime.now(timezone.utc).isoformat()
        exit_client_order_id = order.get("clientOrderId") if order else None
        self._ledger.record_exit(
            open_trade["id"], exit_price, exit_time, reason, realized_pnl, exit_client_order_id
        )
        # Erst mit dem Ausstieg im Ledger ist die Order-Frage erledigt (W-A).
        self._client.confirm_booked(exit_client_order_id)

        reason_label = "Stop-Loss" if reason == "stop_loss" else "Signal-Umkehr"
        logger.info(
            "Trend-Ausstieg (%s): %s @ %.2f (Einstieg @ %.2f), realisiert %.2f",
            reason_label,
            self._config.symbol,
            exit_price,
            open_trade["entry_price"],
            realized_pnl,
        )
        tag = "[TREND-AUSSTIEG]" if order is not None else "[TREND-AUSSTIEG DRY-RUN]"
        send_notification(
            f"{tag} ({reason_label}): {open_trade['quantity']:.8f} {self._config.symbol} "
            f"@ {exit_price:.2f} (Einstieg @ {open_trade['entry_price']:.2f}), "
            f"realisiert: {realized_pnl:+.2f}"
        )

        if reason == "stop_loss":
            loss_pct = (1 - exit_price / open_trade["entry_price"]) * 100
            self._stop_loss.pause(
                self._config.symbol, open_trade["entry_price"], exit_price, loss_pct
            )

    def _sell_is_covered(self, open_trade: dict) -> bool:
        """
        Deckungsprüfung vor einem echten Verkauf (W11, siehe
        balance_guard.py): Reicht das freie Guthaben für die Menge dieser
        Position?

        Zusätzlich läuft hier die weiche Buchhaltungsprüfung. Anders als
        beim Grid-Bot braucht es dafür keinen Anti-Spam-Zähler: Der
        Trend-Bot hält höchstens eine offene Position und läuft im
        24-Stunden-Takt - eine Meldung pro Tag ist keine Flut, und sie
        blockiert ohnehin nichts.

        Ein nicht abrufbares Guthaben (`None`) lässt den Verkauf zu.
        Einen Stop-Loss-Ausstieg wegen eines Netzwerk-Hängers zu
        verweigern wäre die deutlich gefährlichere Richtung - siehe die
        gleiche Abwägung in binance_client.get_asset_balance().
        """
        if not self._config.trading_enabled:
            return True

        rules = self._client.get_symbol_trading_rules(self._config.symbol)
        snapshot = build_snapshot(
            self._client.get_asset_balance(rules.base_asset),
            self._client.get_open_orders(self._config.symbol),
            self._config.bot_name,
        )
        if snapshot is None:
            return True

        quantity = open_quantity(open_trade)

        if ledger_exceeds_account(snapshot, quantity, rules.step_size):
            logger.error(
                "[TREND-BESTAND-DISKREPANZ] Das Trend-Ledger führt eine "
                "offene Position über mehr %s, als auf dem Konto für diesen "
                "Bot vorhanden sein kann. %s. Da sich DCA, Grid und Trend "
                "ein Konto teilen, kann ein anderer Bot oder ein manueller "
                "Trade Bestand verkauft haben, der hier noch als offen "
                "geführt wird.",
                rules.base_asset,
                describe(snapshot, quantity),
            )
            send_notification(
                f"[TREND-BESTAND-DISKREPANZ] Offene Position über "
                f"{quantity:.8f} {rules.base_asset}, aber so viel kann für "
                f"diesen Bot nicht auf dem Konto sein. "
                f"{describe(snapshot, quantity)}. Geteiltes Konto - bitte "
                "prüfen (python -m dca_bot.audit_positions)."
            )

        if check_sell_coverage(snapshot, quantity, rules.step_size) != SELL_INSUFFICIENT:
            return True

        logger.error(
            "[TREND-VERKAUF-UNGEDECKT] Verkauf über %.8f %s wird NICHT "
            "versucht - frei verfügbar sind nur %.8f. %.8f stecken in "
            "offenen Orders (davon %.8f aus anderen Bots bzw. manuellem "
            "Handel). Die Börse würde die Order ablehnen.",
            quantity,
            rules.base_asset,
            snapshot.free,
            snapshot.locked,
            snapshot.foreign_locked,
        )
        return False

    def _report_exit_blocked_by_dry_run(
        self, open_trade: dict, price: float, reason: str
    ) -> None:
        """
        Meldet, dass fuer eine ECHTE Position ein Ausstieg faellig waere,
        der Bot ihn aber nicht ausfuehren kann, weil
        TREND_BOT_ENABLE_TRADING=false ist (siehe _close_position).

        Telegram bei jedem Versuch: beim 24-Stunden-Takt ist das hoechstens
        eine Nachricht pro Tag und damit eine Erinnerung, dass eine echte
        Position ohne handlungsfaehigen Bot an der Boerse liegt - gleiche
        Ueberlegung wie bei _warn_on_partially_filled_stop_order().
        """
        reason_label = "Stop-Loss" if reason == "stop_loss" else "Signal-Umkehr"
        stop_order_id = open_trade.get("stop_loss_order_id")
        protection = (
            f"Stop-Order {stop_order_id} an der Boerse bleibt bestehen"
            if stop_order_id
            else "KEINE Stop-Order an der Boerse hinterlegt"
        )
        logger.warning(
            "[TREND-AUSSTIEG-GESPERRT] Ausstieg (%s) fuer die echte Position %s "
            "waere faellig (Preis ~%.2f), aber TREND_BOT_ENABLE_TRADING ist "
            "false - es wird NICHTS storniert, verkauft oder gebucht. Position "
            "bleibt offen (%s). Zum Aussteigen Trading wieder aktivieren.",
            reason_label,
            open_trade["id"],
            price,
            protection,
        )
        send_notification(
            f"[TREND-AUSSTIEG-GESPERRT] {self._config.symbol}: Ausstieg "
            f"({reason_label}) @ {price:.2f} waere faellig, Trading ist aber "
            f"deaktiviert. Echte Position bleibt offen ({protection}). Zum "
            "Aussteigen TREND_BOT_ENABLE_TRADING=true setzen."
        )

    def _pending_sells(self, open_trade: dict) -> list[PendingOrder]:
        """
        Verkaufs- und Stop-Orders dieses Trades, deren Ausgang noch nicht
        geklaert ist (Pending-Eintrag steht noch). Solange es welche gibt,
        platziert der Bot fuer den Trade keine weitere Sell-Order
        (Systemcheck vom 27.09.2026, K-B/W-B).
        """
        return self._client.pending_orders.entries_for(
            side="SELL", trade_id=open_trade["id"]
        )

    def _settle_unclear_sell(
        self, open_trade: dict, unclear: list[PendingOrder]
    ) -> bool:
        """
        Klaert einen Market-Sell mit unklarem Ausgang durch bis zu
        UNCLEAR_SELL_RECHECKS Nachpruefungen im Abstand von
        UNCLEAR_SELL_RECHECK_SECONDS (zusammen 60 s - die Altersgrenze,
        ab der -2013 endgueltig ist, siehe pending_orders.py).

        Rueckgabe True: der Fall ist hier erledigt - entweder wurde der
        Verkauf als ausgefuehrt verbucht, oder sein Ausgang bleibt unklar
        und es wird bewusst KEINE neue Stop-Order platziert. False: der
        Verkauf hat nachweislich nichts bewirkt, der Aufrufer stellt die
        Absicherung wie bei einer eindeutigen Ablehnung wieder her.

        Warum warten statt gleich den naechsten Zyklus: der Trend-Bot
        laeuft im 24-Stunden-Takt. Eine Minute Nachpruefung ist gegen einen
        Tag ohne exchange-seitigen Schutz der deutlich kleinere Preis.
        """
        store = self._client.pending_orders
        remaining = list(unclear)
        for _ in range(UNCLEAR_SELL_RECHECKS):
            _sleep(UNCLEAR_SELL_RECHECK_SECONDS)
            still_open = []
            for pending in remaining:
                state, order = resolve_pending_order(self._client, pending)
                if state == ORDER_CONFIRMED:
                    self._record_reconciled_exit(pending, order)
                    store.remove(pending.client_order_id)
                    return True
                if state == ORDER_WITHOUT_EFFECT or (
                    state == ORDER_UNKNOWN and pending.unknown_is_final()
                ):
                    store.remove(pending.client_order_id)
                    continue
                still_open.append(pending)
            remaining = still_open
            if not remaining:
                return False

        # Die stornierte Stop-Order ist nicht mehr da - die alte ID stehen
        # zu lassen waere eine Falschangabe (siehe unten im Aufrufer).
        self._ledger.set_stop_loss_order(open_trade["id"], None, None)
        open_trade["stop_loss_order_id"] = None
        ids = ", ".join(p.client_order_id for p in remaining)
        logger.warning(
            "[TREND-VERKAUF-UNGEKLAERT] Ausgang des Verkaufs %s fuer Position "
            "%s auch nach %d Nachpruefungen unklar - es wird KEINE neue "
            "Stop-Order platziert (waere der Verkauf durchgegangen, liefe sie "
            "gegen den Bestand eines anderen Bots). Die Reconciliation zu "
            "Beginn jedes Zyklus prueft weiter.",
            ids,
            open_trade["id"],
            UNCLEAR_SELL_RECHECKS,
        )
        send_notification(
            f"[TREND-WARNUNG] {self._config.symbol}: Ausgang des Verkaufs {ids} "
            "ungeklaert. Die Stop-Order war dafuer bereits storniert - die "
            "Position ist moeglicherweise UNGESCHUETZT, falls der Verkauf nicht "
            "durchging. Keine neue Order, bis Binance den Ausgang bestaetigt. "
            "Bitte pruefen."
        )
        return True

    def _handle_failed_real_sell(
        self, open_trade: dict, price: float, cause: str | None = None
    ) -> None:
        """
        Behandelt einen ECHTEN Market-Sell, der nicht zustande gekommen
        ist (siehe _close_position): die Position bleibt OFFEN im Ledger,
        es wird KEIN Erlös aus quantity*price erfunden und KEIN
        Stop-Loss-Latch gesetzt - es hat schlicht kein Ausstieg
        stattgefunden.

        `cause` unterscheidet die beiden Wege hierher, weil sie im Log
        nicht gleich aussehen dürfen: Entweder die Börse hat die Order
        abgelehnt (Default), oder der Verkauf wurde wegen fehlender
        Deckung gar nicht erst versucht (W11). Die Wiederherstellung der
        Absicherung ist in beiden Fällen identisch und deshalb hier
        zusammengefasst.

        Zusätzlich muss hier die Absicherung wiederhergestellt werden:
        _resolve_stop_order_before_close() hat die exchange-seitige
        Stop-Loss-Order bereits storniert, BEVOR dieser Verkauf versucht
        wurde. Ohne eine neue Order bliebe die weiterhin offene Position
        also komplett ungeschützt, sobald der Bot-Prozess ausfällt - genau
        der Zustand, den die Stop-Order verhindern soll.

        Die Stop-Schwelle wird wie beim Entry aus entry_price berechnet
        (siehe _open_position), ist also identisch zur ursprünglichen. Der
        limit_price entsteht mit dem AKTUELLEN stop_limit_offset_pct und
        wird auch so im Ledger hinterlegt: für eine neu platzierte Order
        ist der aktuelle Config-Wert die Wahrheit. Das widerspricht nicht
        dem Kommentar zu TrendTrade.stop_limit_price in trend_risk.py -
        dort geht es darum, eine BESTEHENDE Order nicht rückwirkend mit
        einem geänderten Config-Wert zu verfälschen.
        """
        # Ausgang des Verkaufs unklar (Systemcheck vom 27.09.2026, K-B)?
        # Erkennbar daran, dass sein Pending-Eintrag noch steht - bei einer
        # eindeutigen Ablehnung hat der Client ihn bereits entfernt. Dann
        # wird hier KEINE neue Stop-Order ueber die volle Menge platziert:
        # war der Verkauf durchgegangen, waere sie aus fremdem Bestand
        # gedeckt, und der naechste Zyklus verkaufte ein zweites Mal.
        if cause is None:
            unclear = [
                p for p in self._pending_sells(open_trade) if p.kind == KIND_MARKET
            ]
            if unclear and self._settle_unclear_sell(open_trade, unclear):
                return
            if self._pending_sells(open_trade):
                # Kein Market-Sell mehr offen, wohl aber eine Stop-Order
                # mit unklarem Ausgang - auch dann keine zweite Order.
                self._ledger.set_stop_loss_order(open_trade["id"], None, None)
                open_trade["stop_loss_order_id"] = None
                self._ensure_stop_loss_protection(open_trade)
                return

        headline = cause or "Echter Verkauf fehlgeschlagen"
        logger.warning(
            "[TREND-VERKAUF-FEHLGESCHLAGEN] %s für %s (Position %s, Preis "
            "~%.2f) - Position bleibt OFFEN im Ledger, kein Erlös verbucht, "
            "kein Stop-Loss-Latch. Der nächste Zyklus versucht es erneut.",
            headline,
            self._config.symbol,
            open_trade["id"],
            price,
        )

        stop_price = open_trade["entry_price"] * (1 - self._config.stop_loss_pct / 100)
        limit_price = stop_price * (1 - self._config.stop_limit_offset_pct / 100)
        stop_order = self._client.place_stop_loss_limit_sell(
            self._config.symbol,
            open_quantity(open_trade),
            stop_price,
            limit_price,
            context={"trade_id": open_trade["id"], "limit_price": limit_price},
        )

        if stop_order is not None:
            self._ledger.set_stop_loss_order(
                open_trade["id"], str(stop_order["orderId"]), limit_price
            )
            self._client.confirm_booked(stop_order.get("clientOrderId"))
            logger.warning(
                "Neue Stop-Loss-Order %s für die weiterhin offene Position "
                "platziert (Stop %.2f, Limit %.2f) - die vor dem "
                "fehlgeschlagenen Verkauf stornierte Absicherung ist damit "
                "wiederhergestellt.",
                stop_order["orderId"],
                stop_price,
                limit_price,
            )
            send_notification(
                f"[TREND-VERKAUF-FEHLGESCHLAGEN] {self._config.symbol}: "
                f"{headline} @ {price:.2f}. Position bleibt offen, wurde aber "
                "durch eine NEUE Stop-Loss-Order wieder abgesichert. Siehe "
                "Bot-Log."
            )
            return

        # Die alte ID zeigt auf die bereits stornierte Order - sie stehen
        # zu lassen wäre eine Falschangabe im Ledger (und würde beim
        # nächsten Zyklus einen Status-Check auf eine tote Order auslösen).
        self._ledger.set_stop_loss_order(open_trade["id"], None, None)
        logger.error(
            "[TREND-VERKAUF-FEHLGESCHLAGEN] Zusätzlich konnte auch KEINE neue "
            "Stop-Loss-Order platziert werden: Position %s ist jetzt weder "
            "verkauft noch exchange-seitig abgesichert - nur noch "
            "software-intern, und das auch nur, solange dieser Prozess "
            "läuft. Manueller Eingriff dringend empfohlen.",
            open_trade["id"],
        )
        send_notification(
            f"[TREND-FEHLER] {self._config.symbol}: {headline} @ {price:.2f} "
            "UND keine neue Stop-Loss-Order platzierbar - Position weder "
            "verkauft noch exchange-seitig abgesichert. Manuelle Prüfung "
            "nötig."
        )

    def _ensure_stop_loss_protection(self, open_trade: dict, log_prefix: str = "") -> None:
        """
        Stellt sicher, dass eine offene, echte Position eine exchange-
        seitige Stop-Loss-Order hat - und platziert sonst eine neue.

        Ohne diesen Schritt konnte eine Position dauerhaft ungeschützt
        bleiben, ohne dass es jemals auffiel. Es gibt genau zwei Wege in
        diesen Zustand, und beide waren bisher Sackgassen:

        1. Die Stop-Order konnte schon beim Entry nicht platziert werden
           (siehe _open_position). Der Kommentar dort sprach von "bis zum
           nächsten erfolgreichen Versuch" - einen solchen Versuch gab es
           aber nirgends im Code.
        2. Der eigene Market-Sell schlug fehl, nachdem die Stop-Order
           dafür bereits storniert war, UND die sofortige Neuplatzierung
           schlug ebenfalls fehl (siehe _handle_failed_real_sell). Dreht
           `confirmed_direction` danach zurück auf "up", entfällt der
           Exit-Grund - der Bot hätte die Position dann nie wieder
           angefasst und damit auch nie wieder abgesichert.

        In beiden Fällen wirkte nur noch der software-interne Stop-Loss,
        also genau so lange, wie der Bot-Prozess läuft - der Schutz bei
        Bot-/Internet-/Stromausfall, der der ganze Sinn der
        exchange-seitigen Order ist, fehlte.

        Die Stop-Schwelle entsteht wie beim Entry aus `entry_price`, ist
        also identisch zur ursprünglich vorgesehenen. Schlägt auch dieser
        Versuch fehl, zählt `unprotected_cycles` hoch; ab
        UNPROTECTED_CYCLES_WARNING_THRESHOLD aufeinanderfolgenden Zyklen
        gibt es eine explizite Telegram-Warnung (gleiches Muster wie
        `uncertain_cycles`). Bei Erfolg wird der Zähler zurückgesetzt.

        Bewusst NICHT betroffen: Dry-Run-Positionen (existieren an der
        Börse nicht, siehe K4). Eine Position OHNE `dry_run`-Feld wird
        ebenfalls nicht angefasst, sondern als `[TREND-POSITION-UNKLAR]`
        gemeldet - bis zum 25.09.2026 galt sie hier als echt und hätte
        mit Trading an eine echte Stop-Order für eine Position
        unbekannter Art bekommen.

        Im Dry-Run-MODUS (Trading aus) wird für eine ECHTE Position zwar
        keine Order platziert, der Zustand aber trotzdem gezählt und ab
        der Schwelle gemeldet. Bis zum 25.09.2026 stieg die Methode dort
        sofort aus - verschwand die Stop-Order einer echten Position,
        während der Bot auf Dry-Run stand, blieb das ungezählt und
        ungemeldet.
        """
        position_dry_run = open_trade.get("dry_run")
        if position_dry_run is None:
            logger.warning(
                "%s[TREND-POSITION-UNKLAR] Position %s hat kein dry_run-Feld im "
                "Ledger - es wird keine Stop-Loss-Order platziert und nichts "
                "gezählt. Bitte manuell prüfen (python -m dca_bot.audit_positions).",
                log_prefix,
                open_trade["id"],
            )
            return
        if position_dry_run:
            return
        if open_trade.get("stop_loss_order_id"):
            return  # bereits abgesichert, nichts zu tun

        previous_count = open_trade.get("unprotected_cycles", 0)

        # Sperre (Systemcheck vom 27.09.2026, W-B): Hat eine fruehere
        # Stop-Order oder ein Verkauf dieses Trades noch keinen geklaerten
        # Ausgang, wird keine neue Order platziert. Die fruehere kann an der
        # Boerse liegen - eine zweite waere dann aus dem Bestand eines
        # anderen Bots gedeckt. Gezaehlt und gemeldet wird trotzdem, denn
        # ob die Position abgesichert ist, weiss der Bot in dieser Lage nicht.
        pending = self._pending_sells(open_trade)
        if pending:
            self._count_unprotected_cycle(
                open_trade,
                previous_count,
                log_prefix,
                cause=(
                    "der Ausgang einer frueheren Order ("
                    + ", ".join(p.client_order_id for p in pending)
                    + ") ist ungeklaert, eine neue Stop-Order waere womoeglich "
                    "aus fremdem Bestand gedeckt"
                ),
            )
            return

        if not self._config.trading_enabled:
            # Keine Platzierung (der Bot darf im Dry-Run keine echte Order
            # setzen), aber dieselbe Zählung und dieselbe Schwelle wie im
            # Fehlschlag-Pfad unten. Die Schwelle bleibt bewusst bei 3: Der
            # realistischste Weg in diesen Zustand - eine verschwundene
            # Stop-Order - meldet sich in _forget_dead_stop_order() ohnehin
            # sofort per Telegram.
            self._count_unprotected_cycle(
                open_trade,
                previous_count,
                log_prefix,
                cause="Trading ist deaktiviert, eine neue Order kann nicht "
                "platziert werden",
            )
            return

        stop_price = open_trade["entry_price"] * (1 - self._config.stop_loss_pct / 100)
        limit_price = stop_price * (1 - self._config.stop_limit_offset_pct / 100)

        # Rest einer Teilfuellung unter dem Mindestvolumen (K-A): Binance
        # wuerde auch die Stop-Order darueber ablehnen, die Position gaelte
        # Zyklus fuer Zyklus als ungeschuetzt. Stattdessen schliessen und
        # den Rest als Staub melden - wie im Ausstiegspfad.
        if float(open_trade.get("partial_exit_qty") or 0.0) > 0:
            rules = self._client.get_symbol_trading_rules(self._config.symbol)
            if self._remainder_is_dust(open_quantity(open_trade), limit_price, rules):
                price = self._client.get_current_price(self._config.symbol)
                self._close_with_dust(open_trade, price, log_prefix)
                return

        stop_order = self._client.place_stop_loss_limit_sell(
            self._config.symbol,
            open_quantity(open_trade),
            stop_price,
            limit_price,
            context={"trade_id": open_trade["id"], "limit_price": limit_price},
        )

        if stop_order is not None:
            order_id = str(stop_order["orderId"])
            self._ledger.set_stop_loss_order(open_trade["id"], order_id, limit_price)
            self._client.confirm_booked(stop_order.get("clientOrderId"))
            # Den uebergebenen Dict mitziehen, damit der laufende Zyklus
            # (und die aufrufende Seite) nicht mit einem veralteten Stand
            # weiterarbeitet.
            open_trade["stop_loss_order_id"] = order_id
            open_trade["stop_limit_price"] = limit_price
            if previous_count:
                self._ledger.set_unprotected_cycles(open_trade["id"], 0)
                open_trade["unprotected_cycles"] = 0

            logger.info(
                "%s[TREND-ABSICHERUNG-WIEDERHERGESTELLT] Offene Position %s "
                "hatte keine exchange-seitige Stop-Loss-Order - neue Order %s "
                "platziert (Stop %.2f, Limit %.2f).",
                log_prefix,
                open_trade["id"],
                order_id,
                stop_price,
                limit_price,
            )
            if previous_count >= UNPROTECTED_CYCLES_WARNING_THRESHOLD:
                # Es ging bereits eine Warnung raus - dann gehoert auch die
                # Entwarnung in denselben Kanal, sonst bleibt der letzte
                # Stand dort "ungeschuetzt".
                send_notification(
                    f"{log_prefix}[TREND-ABSICHERUNG-WIEDERHERGESTELLT] "
                    f"{self._config.symbol}: die offene Position hat wieder "
                    f"eine exchange-seitige Stop-Loss-Order (Stop {stop_price:.2f})."
                )
            return

        self._count_unprotected_cycle(
            open_trade,
            previous_count,
            log_prefix,
            cause="eine neue konnte nicht platziert werden",
        )

    def _count_unprotected_cycle(
        self, open_trade: dict, previous_count: int, log_prefix: str, cause: str
    ) -> None:
        """
        Zählt einen weiteren Zyklus, in dem eine offene, echte Position
        ohne exchange-seitige Stop-Loss-Order bleibt, und meldet ab
        UNPROTECTED_CYCLES_WARNING_THRESHOLD per Telegram.

        Gemeinsam für beide Ursachen - Neuplatzierung gescheitert, oder
        Trading deaktiviert -, damit Zählung, Schwelle und Entwarnung
        (siehe _ensure_stop_loss_protection) für beide identisch sind.
        `cause` steht wörtlich in Log und Telegram: ob sich der Zustand
        mit dem nächsten Versuch von selbst beheben kann oder erst mit
        wieder eingeschaltetem Trading, ist für die manuelle Prüfung der
        entscheidende Unterschied.
        """
        count = previous_count + 1
        self._ledger.set_unprotected_cycles(open_trade["id"], count)
        open_trade["unprotected_cycles"] = count

        logger.warning(
            "%sOffene Position %s hat KEINE exchange-seitige Stop-Loss-Order "
            "und %s (%d. Zyklus in Folge) - sie ist nur software-intern "
            "abgesichert, also nur solange dieser Prozess laeuft.",
            log_prefix,
            open_trade["id"],
            cause,
            count,
        )

        if count >= UNPROTECTED_CYCLES_WARNING_THRESHOLD:
            logger.warning(
                "%sPosition fuer %s seit %d Zyklen in Folge ohne exchange-"
                "seitige Absicherung - manuelle Pruefung empfohlen.",
                log_prefix,
                self._config.symbol,
                count,
            )
            send_notification(
                f"{log_prefix}[TREND-WARNUNG] {self._config.symbol}: offene "
                f"Position seit {count} Zyklen ohne exchange-seitige "
                f"Stop-Loss-Order (kein Schutz bei Bot-Ausfall) - {cause}. "
                "Manuelle Pruefung empfohlen."
            )

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

        Der Erlös wird um die in Quote-Währung abgerechnete
        Verkaufsgebühr bereinigt - das war die letzte offene Stelle der
        K3-Restlücke (siehe unten).
        """
        # Gebührenkorrektur (K3-Restlücke). `get_order()`-Antworten
        # enthalten keine `fills`; ohne sie ist `cummulativeQuoteQty` der
        # BRUTTO-Erlös, und der realisierte Gewinn genau dieses Pfads
        # bliebe systematisch um die Verkaufsgebühr zu optimistisch.
        # `get_order_with_fills()` lädt die fehlenden Gebührendaten über
        # `myTrades` nach - dasselbe Muster, das die fünf
        # Reconciliation-Pfade schon verwenden.
        #
        # Beide Aufrufe sind bewusst GEKAPSELT, und das ist hier der
        # eigentliche Punkt: Diese Methode trägt einen Verkauf nach, den
        # die Börse BEREITS AUSGEFÜHRT hat. Scheitert das Nachladen
        # (Netzwerk, Rate-Limit, exchangeInfo nicht erreichbar), darf das
        # die Ledger-Korrektur nicht verhindern - die Position stünde
        # sonst weiterhin als "offen" im Ledger, obwohl die Assets an der
        # Börse längst verkauft sind, und der nächste Zyklus würde sie
        # erneut zu verkaufen versuchen. Ein um die Gebühr zu
        # optimistischer Eintrag ist dagegen folgenlos. Gleiche Abwägung
        # wie im Docstring von get_order_with_fills() selbst.
        rules = None
        try:
            rules = self._client.get_symbol_trading_rules(self._config.symbol)
            order_status = self._client.get_order_with_fills(
                self._config.symbol, order_status
            )
        except Exception as exc:
            # Bewusst breit gefangen: Was hier schiefgeht, ist für die
            # Ledger-Korrektur zweitrangig (siehe oben). Der Exception-Typ
            # genügt, um den Fall im Log wiederzufinden.
            logger.warning(
                "%sGebührendaten zur gefüllten Stop-Loss-Order konnten nicht "
                "geholt werden (%s) - der Ausstieg wird mit dem BRUTTO-Erlös "
                "verbucht und ist damit um die Verkaufsgebühr zu optimistisch. "
                "Die Position wird trotzdem regulär geschlossen.",
                log_prefix,
                type(exc).__name__,
            )

        executed_qty = float(order_status.get("executedQty", open_quantity(open_trade)))
        cumulative_quote = float(order_status.get("cummulativeQuoteQty", 0.0))
        if executed_qty > 0 and cumulative_quote > 0:
            exit_price = cumulative_quote / executed_qty
            # Ohne `rules` (Abruf oben gescheitert) bleibt es beim
            # Bruttowert - das ist exakt das Verhalten vor diesem Fix.
            proceeds = (
                net_proceeds(order_status, rules, fallback=cumulative_quote)
                if rules is not None
                else cumulative_quote
            )
        else:
            exit_price = float(order_status.get("price", open_trade["entry_price"]))
            proceeds = open_quantity(open_trade) * exit_price
        # Eine frueher verbuchte Teilfuellung (K-A) gehoert zum Ausstieg dazu.
        stop_fill_price = exit_price
        exit_price, proceeds = self._with_partial_fill(
            open_trade, exit_price, open_quantity(open_trade), proceeds
        )
        realized_pnl = proceeds - open_trade["quote_spent"]

        exit_time = datetime.now(timezone.utc).isoformat()
        # Eine Storno-Antwort traegt die ID der Stornierung in
        # `clientOrderId`, die der Order selbst in `origClientOrderId`.
        self._ledger.record_exit(
            open_trade["id"],
            exit_price,
            exit_time,
            "stop_loss",
            realized_pnl,
            order_status.get("origClientOrderId") or order_status.get("clientOrderId"),
        )

        # Der Stop-Loss-Latch gehört zum Ausstieg, nicht zum Logging
        # (Sicherheitsreview-Punkt W6). Er stand bis hierher am Ende von
        # _log_stop_fill_analysis() - hinter einem `return`, das greift,
        # wenn kein stop_limit_price hinterlegt ist. Eine Position, die
        # über einen Exchange-Fill ohne bekannten Limitpreis geschlossen
        # wurde, bekam dadurch KEINEN Latch, obwohl es ein regulärer
        # Stop-Loss-Exit war - der Bot hätte im nächsten Zyklus sofort
        # wieder einsteigen dürfen, also genau der Whipsaw, gegen den der
        # Latch gebaut ist. Ob eine Analyse-Zeile geschrieben werden kann,
        # darf über eine Sicherheitssperre nicht entscheiden.
        loss_pct = (1 - exit_price / open_trade["entry_price"]) * 100
        self._stop_loss.pause(
            self._config.symbol, open_trade["entry_price"], exit_price, loss_pct
        )

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
        self._log_stop_fill_analysis(open_trade, stop_fill_price, log_prefix)
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

        Diese Funktion tut seit dem W6-Fix ausschließlich das, was ihr
        Name sagt: loggen. Der Stop-Loss-Latch, der früher hier am Ende
        stand, sitzt jetzt im Exit-Pfad selbst (siehe
        _close_from_filled_stop_order) und hängt damit nicht mehr daran,
        ob diese Zeile überhaupt geschrieben werden kann.
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

        Die Bewertung des Order-Status kommt seit den Punkten W7/W8 aus
        `order_lifecycle_state()` (pending_orders.py) - derselben
        Funktion, auf der auch der Pending-Pfad aufsetzt. Vorher stand
        hier eine eigene Regel (`status == "FILLED"`), und die kannte nur
        zwei der vier möglichen Ausgänge:

        - ORDER_LIFECYCLE_FILLED: die Börse hat verkauft -> Position im
          Ledger schließen, kein eigener Verkaufsversuch. (Wie bisher.)
        - ORDER_LIFECYCLE_DEAD (W7): die Order ist beendet, ohne etwas
          bewegt zu haben - storniert, abgelaufen oder abgelehnt. Die
          Position ist damit UNGESCHÜTZT, aber das Ledger führte
          weiterhin eine Order-ID; `_ensure_stop_loss_protection()`
          steigt bei jeder vorhandenen ID sofort aus und hätte deshalb
          nie Ersatz platziert. Die Position wäre dauerhaft ohne
          exchange-seitige Absicherung geblieben - genau der Zustand, den
          der Fix aus 6f/K1-Folgefund verhindern soll, nur über einen
          anderen Weg hinein.
        - ORDER_LIFECYCLE_LIVE (W8): die Order lebt noch. Normalfall,
          nichts zu tun - bei einer TEILFÜLLUNG wird das aber sichtbar
          gemacht, siehe _warn_on_partially_filled_stop_order().
        - ORDER_LIFECYCLE_UNREADABLE: die Abfrage hat versagt. Das ist
          KEINE Aussage über die Order, also wird nichts angefasst.
        """
        order_id = open_trade.get("stop_loss_order_id")
        if not order_id:
            return False

        status = self._client.get_order_status(self._config.symbol, order_id)
        state = order_lifecycle_state(status)

        if state == ORDER_LIFECYCLE_FILLED:
            if self._book_stop_fill(open_trade, status, log_prefix=log_prefix) == "already_closed":
                return True
            # Beendet MIT Teilfuellung (K-A, z.B. waehrend einer Downtime
            # abgelaufen): verbucht - jetzt den Rest als Stop-Loss-Ausstieg
            # abschliessen. Bis zum Fix wurde hier die GANZE Position mit
            # dem Teilerloes geschlossen, der Rest lag danach ohne Ledger
            # auf dem Konto.
            price = self._client.get_current_price(self._config.symbol)
            self._close_position(open_trade, price, reason="stop_loss")
            return True

        if state == ORDER_LIFECYCLE_DEAD:
            self._forget_dead_stop_order(open_trade, order_id, status, log_prefix)
            return False

        if state == ORDER_LIFECYCLE_LIVE:
            self._warn_on_partially_filled_stop_order(
                open_trade, order_id, status, log_prefix
            )
        return False

    def _forget_dead_stop_order(
        self, open_trade: dict, order_id: str, status: dict, log_prefix: str
    ) -> None:
        """
        Löst die Zuordnung einer Stop-Loss-Order, die an der Börse
        beendet wurde, ohne etwas bewegt zu haben (W7).

        Eine solche Order schützt nichts mehr. Sie im Ledger stehen zu
        lassen wäre eine Falschangabe - und schlimmer: sie würde
        `_ensure_stop_loss_protection()` dauerhaft blockieren, das bei
        jeder vorhandenen `stop_loss_order_id` sofort aussteigt. Nach dem
        Leeren platziert derselbe Zyklus (bzw. der Reconciliation-Schritt
        beim Start) automatisch Ersatz - bei deaktiviertem Trading nicht,
        dann wird nur gezählt und ab der Schwelle gemeldet.

        Der `open_trade`-Dict wird mitgezogen, damit die aufrufende Seite
        im laufenden Zyklus nicht mit einem veralteten Stand
        weiterarbeitet - gleiches Muster wie in
        _ensure_stop_loss_protection().

        Gemeldet wird das bewusst per Telegram: eine Stop-Order
        verschwindet nicht von selbst. Entweder hat jemand sie manuell
        storniert, oder die Börse hat sie abgelehnt/verfallen lassen -
        beides gehört gesehen.
        """
        self._ledger.set_stop_loss_order(open_trade["id"], None, None)
        open_trade["stop_loss_order_id"] = None
        open_trade["stop_limit_price"] = None

        order_state = status.get("status") if isinstance(status, dict) else None
        # Im Dry-Run-Modus kann KEIN Ersatz platziert werden (siehe
        # _ensure_stop_loss_protection) - die Meldung darf dann nicht das
        # Gegenteil behaupten.
        if self._config.trading_enabled:
            log_next_step = (
                "Die Zuordnung im Ledger wurde gelöst, damit noch in diesem "
                "Durchlauf eine neue Order platziert wird."
            )
            notify_next_step = "Der Bot platziert automatisch Ersatz"
        else:
            log_next_step = (
                "Die Zuordnung im Ledger wurde gelöst. Ersatz kann NICHT "
                "platziert werden, solange TREND_BOT_ENABLE_TRADING=false ist."
            )
            notify_next_step = (
                "Ersatz ist NICHT möglich, solange Trading deaktiviert ist "
                "(TREND_BOT_ENABLE_TRADING=false) - die Position ist bis dahin "
                "an der Börse ungeschützt"
            )
        logger.warning(
            "%sExchange-seitige Stop-Loss-Order %s existiert nicht mehr "
            "(Status %s, ohne ausgeführte Menge) - die Position %s ist damit "
            "aktuell NUR software-intern abgesichert. %s",
            log_prefix,
            order_id,
            order_state,
            open_trade["id"],
            log_next_step,
        )
        send_notification(
            f"{log_prefix}[TREND-WARNUNG] {self._config.symbol}: die "
            f"exchange-seitige Stop-Loss-Order {order_id} ist beendet "
            f"(Status {order_state}), ohne verkauft zu haben. {notify_next_step} "
            "- falls die Order manuell storniert wurde, bitte beachten."
        )

    def _warn_on_partially_filled_stop_order(
        self, open_trade: dict, order_id: str, status: dict, log_prefix: str
    ) -> None:
        """
        Macht eine teilweise gefüllte, noch offene Stop-Loss-Order
        sichtbar (W8).

        Bewusst OHNE Ledger-Korrektur: die Order lebt noch und kann
        vollständig füllen, jede jetzt notierte Teilmenge wäre im
        nächsten Moment falsch. Sobald sie einen terminalen Status
        erreicht, greift der reguläre FILLED-Pfad mit den echten
        Fülldaten.

        Was hier zählt, ist die Sichtbarkeit: ein Teil der Position ist an
        der Börse bereits verkauft, während das Ledger die volle Menge
        führt.

        Korrektur (Systemcheck vom 27.09.2026, K-A): Hier stand bis dahin,
        ein eigener Market-Sell über die volle Menge "würde scheitern".
        Auf dem geteilten Konto stimmt das nicht - das freie BTC des
        DCA-Bots deckt den Fehlbetrag, der Verkauf geht durch und
        verkauft fremden Bestand. Seit dem Fix storniert der Ausstieg die
        Order zuerst, verbucht deren `executedQty` und verkauft nur den
        Rest (_resolve_stop_order_before_close, _book_stop_fill).

        Die Meldung geht bewusst in JEDEM Zyklus raus -
        beim 24-Stunden-Takt des Trend-Bots ist das höchstens eine
        Erinnerung pro Tag, dass der Zustand weiter besteht, und keine
        Spam-Gefahr (anders als bei uncertain_cycles, wo der Takt
        deutlich kürzer sein kann).
        """
        filled_qty = executed_quantity(status)
        if filled_qty <= 0:
            return  # normale, unberührte Stop-Order - der Regelfall

        logger.warning(
            "%sExchange-seitige Stop-Loss-Order %s ist TEILWEISE gefüllt "
            "(%.8f von %.8f, Status %s) und weiterhin offen. Das Ledger führt "
            "bis zum Abschluss der Order die offene Menge unverändert - bei "
            "einem Ausstieg wird die Order zuerst storniert und nur der Rest "
            "verkauft. Es wird bewusst nichts korrigiert, solange die Order "
            "noch füllen kann.",
            log_prefix,
            order_id,
            filled_qty,
            open_quantity(open_trade),
            status.get("status"),
        )
        send_notification(
            f"{log_prefix}[TREND-WARNUNG] {self._config.symbol}: Stop-Loss-Order "
            f"{order_id} ist teilweise gefüllt ({filled_qty:.8f} von "
            f"{open_quantity(open_trade):.8f}) und noch offen. Position im Ledger "
            "unverändert, bitte im Auge behalten."
        )

    def verify_state_readable(self) -> None:
        """
        Prueft beim Bot-Start, ob das Ledger lesbar ist
        (Sicherheitsreview-Punkt W5). Wirft `LedgerUnreadable`.

        Bewusst ein eigener Schritt und NICHT in
        safe_startup_reconciliation() gekapselt: deren Zweck ist "der
        Start darf nicht scheitern", und genau das waere hier falsch
        herum. Ein beschaedigtes Ledger MUSS den Start verhindern.
        """
        self._ledger.verify_readable()

    def check_balance_on_startup(self) -> None:
        """
        Gleicht beim Bot-Start die offene Position gegen den
        tatsächlichen Kontostand ab (Stufe 2, Punkt 3 - siehe
        startup_checks.py). Laut, aber nicht blockierend.

        Beim Trend-Bot ist die Lücke am größten, die das schließt: Die
        bestehende Prüfung in `_sell_is_covered()` läuft nur bei einem
        tatsächlichen Exit, und zwischen zwei Signalen können Monate
        liegen (Tageskerzen, EMA 20/50). Eine Position konnte also
        beliebig lange mit einer Buchhaltung dastehen, die niemand je
        gegen die Realität gehalten hat.

        **Kein Fehlalarm durch die eigene Stop-Loss-Order:** Sie bindet
        die komplette Positionsmenge, `free` wäre also systematisch zu
        klein. Sie trägt aber seit dem K2-Fix das `trend-`Präfix in ihrer
        `clientOrderId` und zählt damit in `own_locked` - und
        `own_upper_bound` ist `free + own_locked`. Genau dafür ist die
        Obergrenze so gebaut (siehe balance_guard.py). Der Aufruf liegt
        deshalb auch NACH `reconcile_on_startup()`, das eine fehlende
        Absicherung erst wiederherstellt.

        Dry-Run-Positionen zählen nicht mit - sie existieren an der
        Börse nicht (K4). Ein Eintrag ohne `dry_run`-Feld gilt über den
        Default `True` als simuliert, die konservative Richtung.
        """
        open_trade = self._ledger.open_position()
        quantity = 0.0
        if open_trade is not None and not open_trade.get("dry_run", True):
            quantity = open_quantity(open_trade)
        report_ledger_vs_account(
            client=self._client,
            logger=logger,
            symbol=self._config.symbol,
            bot_name=self._config.bot_name,
            own_open_quantity=quantity,
            notify_tag="[TREND-BESTAND-DISKREPANZ]",
            ledger_label="Das Trend-Ledger",
        )

    def reconcile_pending_orders(self) -> None:
        """
        Trägt beim Bot-Start Orders nach, deren Ausgang beim letzten Lauf
        offen geblieben ist (Sicherheitsreview-Punkt K2, Teil B - siehe
        pending_orders.py).

        Wird von main_trend.py VOR `reconcile_on_startup()` aufgerufen,
        und diese Reihenfolge ist keine Geschmacksfrage: Ein hier
        nachgetragener Einstieg erzeugt eine offene Position OHNE
        exchange-seitige Stop-Loss-Order. `reconcile_on_startup()` findet
        sie unmittelbar danach vor und lässt `_ensure_stop_loss_protection()`
        die fehlende Order platzieren. Andersherum liefe die Absicherung
        ins Leere - zum Zeitpunkt ihres Laufs gäbe es die Position noch
        gar nicht, und sie bliebe bis zum nächsten Zyklus ungeschützt.

        Der gefährlichste Fall des ganzen Fixes landet damit auf einem
        bereits vorhandenen Mechanismus: ein real gekaufter, aber
        unverbuchter Trend-Einstieg wäre sonst eine ungeschützte
        Position, von der der Bot nichts weiß - und bei weiter
        bestätigtem Aufwärtstrend hätte der nächste Zyklus ein zweites
        Mal gekauft.
        """
        reconcile_pending_orders(
            client=self._client,
            store=self._client.pending_orders,
            bot_logger=logger,
            apply_confirmed=self._apply_reconciled_order,
        )

    def _reconcile_pending_at_runtime(self) -> None:
        """
        Dieselbe Reconciliation zu Beginn JEDES Zyklus (Systemcheck vom
        27.09.2026, K-B/W-A/W-B). Eine Stop-Order, deren Antwort verloren
        ging, haengt sie wieder an ihren Trade, BEVOR
        `_ensure_stop_loss_protection()` eine zweite platzieren koennte; ein
        Verkauf mit unklarem Ausgang wird verbucht, BEVOR der Bot dieselbe
        Position ein zweites Mal verkauft.
        """
        reconcile_pending_orders(
            client=self._client,
            store=self._client.pending_orders,
            bot_logger=logger,
            apply_confirmed=self._apply_reconciled_order,
            escalated=self._pending_escalated,
        )

    def _apply_reconciled_order(self, pending: PendingOrder, order: dict) -> None:
        if pending.kind == KIND_STOP_LOSS_LIMIT:
            self._attach_reconciled_stop_order(pending, order)
        elif pending.side == "BUY":
            self._record_reconciled_entry(pending, order)
        elif pending.side == "SELL":
            self._record_reconciled_exit(pending, order)
        else:
            raise ValueError(
                f"Unerwartete Order-Seite '{pending.side}' in der "
                "Pending-Orders-Datei des Trend-Bots."
            )

    def _record_reconciled_entry(self, pending: PendingOrder, order: dict) -> None:
        if self._ledger.has_client_order_id(pending.client_order_id):
            logger.info(
                "%sEinstieg zu Order %s ist bereits im Ledger - nichts "
                "nachzutragen.",
                RECONCILIATION_PREFIX,
                pending.client_order_id,
            )
            return

        existing = self._ledger.open_position()
        if existing is not None:
            # Der Trend-Bot hat genau EINEN Slot - open_position() gibt
            # den ersten offenen Eintrag zurück. Einen zweiten
            # anzulegen würde diese Invariante brechen und den Bot in
            # einen Zustand bringen, aus dem er allein nicht mehr
            # herausfindet. Also nicht verbuchen, sondern laut melden:
            # die Exception hält den Pending-Eintrag fest (siehe
            # reconcile_pending_orders), damit die Frage nicht verloren
            # geht, bis ein Mensch sie auflöst.
            raise ValueError(
                f"Order {pending.client_order_id} wäre ein zweiter offener "
                f"Trend-Einstieg neben Position {existing['id']} - der Bot "
                "hält bewusst nur eine Position gleichzeitig. Bitte manuell "
                "auflösen (python -m dca_bot.audit_positions)."
            )

        symbol = pending.symbol or self._config.symbol
        amount = float(pending.context.get("amount", self._config.amount_per_trade))

        rules = self._client.get_symbol_trading_rules(symbol)
        order = self._client.get_order_with_fills(symbol, order)

        entry_price = average_fill_price(
            order, fallback=float(pending.context.get("price", 0.0)) or 0.0
        )
        if entry_price <= 0:
            raise ValueError(
                f"Kein brauchbarer Einstiegspreis für Order "
                f"{pending.client_order_id} ermittelbar - Stop-Loss-Schwelle "
                "und PnL wären daraus nicht berechenbar."
            )

        quantity = net_executed_quantity(order, rules, fallback=amount / entry_price)
        quote_spent = float(order.get("cummulativeQuoteQty", amount))

        trade = TrendTrade.new(
            entry_price=entry_price,
            quantity=quantity,
            quote_spent=quote_spent,
            dry_run=False,
            client_order_id=pending.client_order_id,
        )
        self._ledger.record_entry(trade)

        logger.warning(
            "%sTrend-Einstieg nachgetragen: %s @ %.2f (Menge %.8f, Order %s). "
            "Die Position hat noch KEINE exchange-seitige Stop-Loss-Order - "
            "der anschließende Reconciliation-Schritt platziert sie.",
            RECONCILIATION_PREFIX,
            symbol,
            entry_price,
            quantity,
            pending.client_order_id,
        )
        send_notification(
            f"[REKONZILIATION] Nachgetragener Trend-Einstieg: {quantity:.8f} "
            f"{symbol} @ {entry_price:.2f}. Die Order lief beim letzten "
            "Bot-Lauf durch, ihr Ergebnis kam aber nicht mehr an - die "
            "Absicherung wird jetzt nachgeholt."
        )

    def _record_reconciled_exit(self, pending: PendingOrder, order: dict) -> None:
        trade_id = pending.context.get("trade_id")
        open_trade = self._ledger.trade_by_id(trade_id) if trade_id else None

        if open_trade is None:
            raise ValueError(
                f"Verkaufs-Order {pending.client_order_id} verweist auf den "
                f"unbekannten Trade '{trade_id}' - der Verkauf hat real "
                "stattgefunden, lässt sich aber keiner Position zuordnen."
            )

        if open_trade["status"] != "open":
            if open_trade.get("exit_client_order_id") == pending.client_order_id:
                logger.info(
                    "%sTrade %s ist bereits geschlossen (mit Order %s) - nichts "
                    "nachzutragen.",
                    RECONCILIATION_PREFIX,
                    trade_id,
                    pending.client_order_id,
                )
                return
            # Mit einer ANDEREN Order geschlossen: diese hier lief
            # zusätzlich - ein Doppelverkauf aus fremdem Bestand
            # (Systemcheck vom 27.09.2026, K-B). Stehen lassen und melden.
            raise ManualReviewRequired(
                f"[TREND-DOPPELVERKAUF] {self._config.symbol}: Trade {trade_id} "
                f"ist bereits mit Order "
                f"{open_trade.get('exit_client_order_id') or 'unbekannt'} "
                f"geschlossen, Order {pending.client_order_id} hat an der Boerse "
                f"ZUSAETZLICH {order.get('executedQty', '?')} verkauft "
                f"(Erloes {order.get('cummulativeQuoteQty', '?')}). Das stammt "
                "aus dem Bestand eines anderen Bots - bitte manuell klaeren "
                "(python -m dca_bot.audit_positions)."
            )

        symbol = pending.symbol or self._config.symbol
        reason = str(pending.context.get("reason", "signal"))

        rules = self._client.get_symbol_trading_rules(symbol)
        order = self._client.get_order_with_fills(symbol, order)

        exit_price = average_fill_price(
            order, fallback=float(pending.context.get("price", 0.0)) or 0.0
        )
        sold_qty = open_quantity(open_trade)
        proceeds = net_proceeds(order, rules, fallback=sold_qty * exit_price)
        exit_price, proceeds = self._with_partial_fill(
            open_trade, exit_price, sold_qty, proceeds
        )
        realized_pnl = proceeds - open_trade["quote_spent"]

        self._ledger.record_exit(
            open_trade["id"],
            exit_price,
            datetime.now(timezone.utc).isoformat(),
            reason,
            realized_pnl,
            pending.client_order_id,
        )

        reason_label = "Stop-Loss" if reason == "stop_loss" else "Signal-Umkehr"
        logger.warning(
            "%sTrend-Ausstieg nachgetragen (%s): %s @ %.2f (Einstieg @ %.2f), "
            "realisiert %.2f (Order %s).",
            RECONCILIATION_PREFIX,
            reason_label,
            symbol,
            exit_price,
            open_trade["entry_price"],
            realized_pnl,
            pending.client_order_id,
        )
        send_notification(
            f"[REKONZILIATION] Nachgetragener Trend-Ausstieg ({reason_label}): "
            f"{open_trade['quantity']:.8f} {symbol} @ {exit_price:.2f} "
            f"(Einstieg @ {open_trade['entry_price']:.2f}), realisiert: "
            f"{realized_pnl:+.2f}."
        )

        if reason == "stop_loss":
            # Der Latch gehört zum Ausstieg dazu - ohne ihn würde der Bot
            # nach einem Stop-Loss-Exit sofort wieder einsteigen dürfen,
            # obwohl der Exit real stattgefunden hat.
            loss_pct = (1 - exit_price / open_trade["entry_price"]) * 100
            self._stop_loss.pause(
                symbol, open_trade["entry_price"], exit_price, loss_pct
            )

    def _attach_reconciled_stop_order(self, pending: PendingOrder, order: dict) -> None:
        """
        Hängt eine Stop-Loss-Order, die an der Börse liegt, im Ledger
        wieder an ihren Trade.

        Ohne diesen Schritt wüsste das Ledger nichts von der Order, und
        `_ensure_stop_loss_protection()` würde im nächsten Zyklus eine
        ZWEITE Stop-Order über dieselbe Menge platzieren - eine davon
        muss scheitern oder Menge verkaufen, die nach dem Fill der
        anderen nicht mehr da ist.

        Findet sich am Trade bereits eine ANDERE Order-ID, liegen
        tatsächlich zwei Stop-Orders an der Börse. Der Bot storniert die
        verwaiste hier bewusst NICHT: das wäre seine erste autonome,
        destruktive Aktion auf Basis eines abgeleiteten Zustands, und es
        widerspräche dem sonst durchgehaltenen Prinzip, bei unklarer
        Lage nicht zu handeln (siehe den "uncertain"-Pfad in
        _resolve_stop_order_before_close). Stattdessen: deutlich melden
        und einen Menschen draufschauen lassen.
        """
        trade_id = pending.context.get("trade_id")
        trade = self._ledger.trade_by_id(trade_id) if trade_id else None
        order_id = str(order.get("orderId", "")) or None
        limit_price = pending.context.get("limit_price")

        if trade is None:
            raise ValueError(
                f"Stop-Loss-Order {pending.client_order_id} verweist auf den "
                f"unbekannten Trade '{trade_id}'."
            )

        if trade["status"] != "open":
            if trade.get("exit_client_order_id") == pending.client_order_id:
                # Genau diese Stop-Order hat den Trade geschlossen - sie ist
                # also nicht verwaist, nur ihr Pending-Eintrag war noch da.
                logger.info(
                    "%sStop-Loss-Order %s hat Trade %s bereits geschlossen - "
                    "nichts zu tun.",
                    RECONCILIATION_PREFIX,
                    order_id,
                    trade_id,
                )
                return
            logger.error(
                "%sStop-Loss-Order %s (clientOrderId %s) liegt an der Börse, "
                "ihr Trade %s ist aber bereits geschlossen - es handelt sich "
                "um eine VERWAISTE Order. Sie wird bewusst nicht automatisch "
                "storniert; bitte manuell bei Binance prüfen und ggf. "
                "entfernen.",
                RECONCILIATION_PREFIX,
                order_id,
                pending.client_order_id,
                trade_id,
            )
            send_notification(
                f"[REKONZILIATION] {self._config.symbol}: verwaiste "
                f"Stop-Loss-Order {order_id} an der Börse - der zugehörige "
                "Trade ist bereits geschlossen. Sie wurde NICHT automatisch "
                "storniert, bitte manuell prüfen."
            )
            return

        existing_order_id = trade.get("stop_loss_order_id")
        if existing_order_id and str(existing_order_id) != order_id:
            self._report_duplicate_stop_order(
                trade_id, str(existing_order_id), order_id, pending.client_order_id
            )
            return

        if str(existing_order_id or "") == (order_id or ""):
            logger.info(
                "%sStop-Loss-Order %s ist bereits am Trade %s hinterlegt.",
                RECONCILIATION_PREFIX,
                order_id,
                trade_id,
            )
            return

        self._ledger.set_stop_loss_order(trade["id"], order_id, limit_price)
        logger.warning(
            "%sStop-Loss-Order %s wieder an Trade %s gehängt - sie lag an der "
            "Börse, war dem Ledger aber unbekannt. Ohne diesen Schritt hätte "
            "der nächste Zyklus eine zweite Order über dieselbe Menge "
            "platziert.",
            RECONCILIATION_PREFIX,
            order_id,
            trade_id,
        )
        send_notification(
            f"[REKONZILIATION] {self._config.symbol}: exchange-seitige "
            f"Stop-Loss-Order {order_id} war dem Ledger unbekannt und wurde "
            "wieder zugeordnet. Die Position ist abgesichert."
        )

    def _describe_stop_order_status(self, order_id: str | None) -> str:
        """
        Aktueller Börsen-Status einer Stop-Order als kurzer Text für
        Log- und Telegram-Meldungen ("NEW", "FILLED", "CANCELED", ...).

        Schlägt die Abfrage fehl oder liefert sie keinen verwertbaren
        Status, wird das ausdrücklich als "nicht abrufbar" ausgewiesen -
        NICHT geraten und nicht weggelassen. Ein fehlender Status ist
        eine eigene, für die manuelle Prüfung wichtige Information: er
        bedeutet "der Bot konnte es nicht klären", nicht "die Order ist
        weg". Genau dieselbe Haltung wie im uncertain-Pfad von
        _resolve_stop_order_before_close().

        Der Fehlerfall wird hier bewusst nicht noch einmal geloggt -
        get_order_status() tut das bereits (siehe binance_client.py).
        """
        if not order_id:
            return STOP_ORDER_STATUS_UNAVAILABLE

        status = self._client.get_order_status(self._config.symbol, order_id)
        if status is None:
            return STOP_ORDER_STATUS_UNAVAILABLE

        value = str(status.get("status") or "").strip()
        return value or STOP_ORDER_STATUS_UNAVAILABLE

    def _report_duplicate_stop_order(
        self,
        trade_id: str,
        ledger_order_id: str,
        pending_order_id: str | None,
        client_order_id: str,
    ) -> None:
        """
        Meldet zwei exchange-seitige Stop-Orders für dieselbe Position.

        Es wird weiterhin NICHTS automatisch storniert (bewusste
        Entscheidung, siehe _attach_reconciled_stop_order): das wäre die
        erste autonome, destruktive Aktion des Bots auf Basis eines
        abgeleiteten Zustands. Hier wird die Meldung lediglich um den
        tatsächlichen Börsen-Status BEIDER Orders angereichert - reine
        Information, kein Verhaltenswechsel.

        Der Nutzen ist praktisch: ohne die beiden Status müsste man nach
        der Telegram-Nachricht erst manuell nachsehen, ob überhaupt noch
        beide offen sind. Oft ist eine davon längst CANCELED oder
        FILLED, und dann ist gar nichts zu tun - das steht jetzt direkt
        in der Meldung.
        """
        ledger_status = self._describe_stop_order_status(ledger_order_id)
        pending_status = self._describe_stop_order_status(pending_order_id)

        logger.error(
            "%s[TREND-WARNUNG] Doppelte Stop-Order erkannt für Position %s. "
            "Ledger-Order %s: Status %s. Pending-Order %s: Status %s "
            "(clientOrderId %s). Liegen beide noch offen, wird eine davon "
            "scheitern oder Menge verkaufen wollen, die nach dem Fill der "
            "anderen nicht mehr da ist. Es wurde nichts automatisch "
            "storniert - manuelle Prüfung/Stornierung empfohlen.",
            RECONCILIATION_PREFIX,
            trade_id,
            ledger_order_id,
            ledger_status,
            pending_order_id,
            pending_status,
            client_order_id,
        )
        send_notification(
            f"[TREND-WARNUNG] Doppelte Stop-Order erkannt für Position "
            f"{trade_id}. Ledger-Order {ledger_order_id}: Status "
            f"{ledger_status}. Pending-Order {pending_order_id}: Status "
            f"{pending_status}. Es wurde nichts automatisch storniert - "
            "manuelle Prüfung/Stornierung empfohlen."
        )

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
            "Reconciliation: offene Position für %s bleibt bestehen (die "
            "Stop-Loss-Order hat nicht verkauft). Die Absicherung wird jetzt "
            "geprüft - falls die Order zwischenzeitlich storniert wurde oder "
            "nie zustande kam, platziert der nächste Schritt Ersatz.",
            self._config.symbol,
        )

        # Falls gar keine Stop-Order hinterlegt ist (z.B. weil sie beim
        # Entry nicht platziert werden konnte oder nach einem
        # fehlgeschlagenen Verkauf nicht wiederhergestellt wurde), wird
        # das hier direkt beim Start repariert - nicht erst beim nächsten
        # Exit-Signal, das u.U. nie kommt.
        self._ensure_stop_loss_protection(open_trade, log_prefix="[REKONZILIATION] ")

    def execute_once(self) -> None:
        """
        Führt genau einen Trend-Following-Zyklus aus. Der aktuell
        abgefragte Preis wird als Näherung für die Tagesschlusskerze
        verwendet (der Bot läuft einmal täglich, siehe interval_hours) -
        für eine exaktere Umsetzung müsste man auf den echten
        Tagesabschluss warten, das wäre für diesen Bot unnötig komplex.
        """
        self._kill_switch.check()
        self._reconcile_pending_at_runtime()

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

            # Die Position bleibt diesen Zyklus offen - also sicherstellen,
            # dass sie exchange-seitig abgesichert ist. Bewusst erst HIER
            # und nicht am Anfang des Zyklus: wird die Position ohnehin
            # gerade geschlossen, waere eine neue Stop-Order sofort wieder
            # zu stornieren, und bei einem ausgeloesten Stop-Loss laege der
            # Preis bereits unter der Stop-Schwelle - die Boerse wuerde eine
            # solche Order zurueckweisen ("would immediately trigger") und
            # der Zaehler unten fehlerhaft hochlaufen.
            self._ensure_stop_loss_protection(open_trade)
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
            # Ein Einstieg mit ungeklaertem Ausgang kann eine offene Position
            # sein, die das Ledger noch nicht kennt - ein zweiter Kauf braeche
            # die Ein-Positions-Regel (Systemcheck vom 27.09.2026, K-B).
            unclear_buys = self._client.pending_orders.entries_for(side="BUY")
            if unclear_buys:
                logger.warning(
                    "[TREND-EINSTIEG-UNGEKLAERT] Einstiegssignal fuer %s, aber "
                    "der Ausgang von Kauf-Order(s) %s ist noch ungeklaert - kein "
                    "neuer Einstieg, bis die Reconciliation sie geklaert hat.",
                    self._config.symbol,
                    ", ".join(p.client_order_id for p in unclear_buys),
                )
                return
            self._open_position(price)

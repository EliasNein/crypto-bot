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
    KIND_STOP_LOSS_LIMIT,
    ORDER_LIFECYCLE_DEAD,
    ORDER_LIFECYCLE_FILLED,
    ORDER_LIFECYCLE_LIVE,
    RECONCILIATION_PREFIX,
    PendingOrder,
    executed_quantity,
    order_lifecycle_state,
    reconcile_pending_orders,
)
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
            # Menge abzüglich der in BTC abgezogenen Kaufgebühr. Das ist
            # hier besonders wichtig: mit dieser Menge wird gleich die
            # exchange-seitige Stop-Loss-Order platziert - über die
            # ungekürzte Menge würde die Börse sie ablehnen, und die
            # Position bliebe ungeschützt.
            quantity = net_executed_quantity(order, rules, fallback=amount / price)
            quote_spent = float(order.get("cummulativeQuoteQty", amount))
        else:
            # Dry-Run: keine echte Gebühr bekannt, deshalb keine geschätzte
            # abgezogen - die Menge wird aber quantisiert, damit simulierte
            # und echte Werte vergleichbar bleiben.
            quantity = quantize_quantity(amount / price, rules.step_size)
            quote_spent = amount

        trade = TrendTrade.new(
            entry_price=price,
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
        """
        Schließt die offene Position per eigenem Market-Sell (Signal-Exit
        oder interner Stop-Loss-Trigger).

        Ob dabei tatsächlich eine echte Order platziert wird, hängt NICHT
        nur am aktuellen Trading-Modus, sondern zusätzlich am `dry_run`-Flag
        des Ledger-Eintrags (siehe README.md Abschnitt 9.5): eine im
        Dry-Run "gekaufte" Position existiert an der Börse gar nicht und
        darf deshalb auch nach einem Umschalten auf echtes Trading niemals
        real verkauft werden.
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

        # Siehe _open_position: Regeln vor der ersten Order holen, damit
        # ein Fehlschlag folgenlos abbricht statt einen bereits
        # ausgeführten Verkauf unverbucht zu lassen.
        rules = self._client.get_symbol_trading_rules(self._config.symbol)

        outcome = self._resolve_stop_order_before_close(open_trade)
        if outcome == "already_closed":
            return  # per _close_from_filled_stop_order bereits erledigt
        if outcome == "uncertain":
            return  # nichts tun, naechster Zyklus prueft erneut

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
                open_trade["quantity"],
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
            # Netto, also abzüglich der in USDT abgerechneten
            # Verkaufsgebühr - cummulativeQuoteQty ist der Bruttoerlös.
            proceeds = net_proceeds(order, rules, fallback=open_trade["quantity"] * price)
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

        quantity = float(open_trade["quantity"])

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
            open_trade["quantity"],
            stop_price,
            limit_price,
            context={"trade_id": open_trade["id"], "limit_price": limit_price},
        )

        if stop_order is not None:
            self._ledger.set_stop_loss_order(
                open_trade["id"], str(stop_order["orderId"]), limit_price
            )
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
        Börse nicht, siehe K4) und der Dry-Run-Modus selbst (dort wird nie
        eine echte Order platziert).
        """
        if not self._config.trading_enabled or open_trade.get("dry_run"):
            return
        if open_trade.get("stop_loss_order_id"):
            return  # bereits abgesichert, nichts zu tun

        previous_count = open_trade.get("unprotected_cycles", 0)

        stop_price = open_trade["entry_price"] * (1 - self._config.stop_loss_pct / 100)
        limit_price = stop_price * (1 - self._config.stop_limit_offset_pct / 100)
        stop_order = self._client.place_stop_loss_limit_sell(
            self._config.symbol,
            open_trade["quantity"],
            stop_price,
            limit_price,
            context={"trade_id": open_trade["id"], "limit_price": limit_price},
        )

        if stop_order is not None:
            order_id = str(stop_order["orderId"])
            self._ledger.set_stop_loss_order(open_trade["id"], order_id, limit_price)
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

        count = previous_count + 1
        self._ledger.set_unprotected_cycles(open_trade["id"], count)
        open_trade["unprotected_cycles"] = count

        logger.warning(
            "%sOffene Position %s hat KEINE exchange-seitige Stop-Loss-Order "
            "und eine neue konnte nicht platziert werden (%d. Zyklus in "
            "Folge) - sie ist nur software-intern abgesichert, also nur "
            "solange dieser Prozess laeuft.",
            log_prefix,
            open_trade["id"],
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
                "Stop-Loss-Order (kein Schutz bei Bot-Ausfall), "
                "Neuplatzierung schlaegt weiterhin fehl. Manuelle Pruefung "
                "empfohlen."
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

        executed_qty = float(order_status.get("executedQty", open_trade["quantity"]))
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
            proceeds = open_trade["quantity"] * exit_price
        realized_pnl = proceeds - open_trade["quote_spent"]

        exit_time = datetime.now(timezone.utc).isoformat()
        self._ledger.record_exit(open_trade["id"], exit_price, exit_time, "stop_loss", realized_pnl)

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
            self._close_from_filled_stop_order(open_trade, status, log_prefix=log_prefix)
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
        beim Start) automatisch Ersatz.

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
        logger.warning(
            "%sExchange-seitige Stop-Loss-Order %s existiert nicht mehr "
            "(Status %s, ohne ausgeführte Menge) - die Position %s ist damit "
            "aktuell NUR software-intern abgesichert. Die Zuordnung im Ledger "
            "wurde gelöst, damit noch in diesem Durchlauf eine neue Order "
            "platziert wird.",
            log_prefix,
            order_id,
            order_state,
            open_trade["id"],
        )
        send_notification(
            f"{log_prefix}[TREND-WARNUNG] {self._config.symbol}: die "
            f"exchange-seitige Stop-Loss-Order {order_id} ist beendet "
            f"(Status {order_state}), ohne verkauft zu haben. Der Bot "
            "platziert automatisch Ersatz - falls die Order manuell "
            "storniert wurde, bitte beachten."
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
        führt. Ein späterer eigener Market-Sell über diese volle Menge
        würde scheitern. Die Meldung geht bewusst in JEDEM Zyklus raus -
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
            "bis zum Abschluss der Order die volle Menge - ein eigener "
            "Verkauf über diese Menge würde derzeit scheitern. Es wird "
            "bewusst nichts korrigiert, solange die Order noch füllen kann.",
            log_prefix,
            order_id,
            filled_qty,
            open_trade["quantity"],
            status.get("status"),
        )
        send_notification(
            f"{log_prefix}[TREND-WARNUNG] {self._config.symbol}: Stop-Loss-Order "
            f"{order_id} ist teilweise gefüllt ({filled_qty:.8f} von "
            f"{open_trade['quantity']:.8f}) und noch offen. Position im Ledger "
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
            logger.info(
                "%sTrade %s ist bereits geschlossen - Verkauf zu Order %s war "
                "schon verbucht.",
                RECONCILIATION_PREFIX,
                trade_id,
                pending.client_order_id,
            )
            return

        symbol = pending.symbol or self._config.symbol
        reason = str(pending.context.get("reason", "signal"))

        rules = self._client.get_symbol_trading_rules(symbol)
        order = self._client.get_order_with_fills(symbol, order)

        exit_price = average_fill_price(
            order, fallback=float(pending.context.get("price", 0.0)) or 0.0
        )
        proceeds = net_proceeds(
            order, rules, fallback=open_trade["quantity"] * exit_price
        )
        realized_pnl = proceeds - open_trade["quote_spent"]

        self._ledger.record_exit(
            open_trade["id"],
            exit_price,
            datetime.now(timezone.utc).isoformat(),
            reason,
            realized_pnl,
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
            self._open_position(price)

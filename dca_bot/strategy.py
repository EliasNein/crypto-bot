"""
DCA (Dollar-Cost-Averaging) Strategie.

Kauft in regelmäßigen Abständen einen festen Betrag eines Assets,
unabhängig vom aktuellen Preis. Bewusst die einfachste sinnvolle
Einstiegsstrategie (siehe Projekt-Recherche in trading-bot-projekt.md):
keine Timing-Logik, kein Overfitting-Risiko, leicht nachvollziehbar.

Risikomanagement (Notaus, Tageslimit, Portfolio-Stop-Loss) lebt in
risk.py und wird hier nur eingebunden - siehe dort für Details.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .allocator_signals import MIN_EFFECTIVE_QUOTE_AMOUNT, read_allocation_fraction
from .binance_client import TradingClient
from .config import Config
from .notifier import send_notification
from .order_utils import average_fill_price, net_executed_quantity, quantize_quantity
from .pending_orders import (
    RECONCILIATION_PREFIX,
    PendingOrder,
    reconcile_pending_orders,
)
from .risk import KillSwitch, PortfolioStopLoss, TradeLedger, TradeRecord, utc_today
from .startup_checks import report_ledger_vs_account

logger = logging.getLogger("dca_bot")


class DCAStrategy:
    def __init__(self, config: Config, client: TradingClient):
        self._config = config
        self._client = client
        self._ledger = TradeLedger(config.state_file)
        self._kill_switch = KillSwitch(config.kill_switch_file)
        self._stop_loss = PortfolioStopLoss(
            self._ledger, config.stop_loss_pct, config.stop_loss_state_file
        )

    def _within_daily_limit(self, amount: float) -> bool:
        # Aus der persistenten Ledger-Datei berechnet statt In-Memory-Zähler,
        # damit das Limit auch nach einem Neustart des Bots noch gilt.
        # UTC, nicht lokale Serverzeit (W3): die Ledger-Zeitstempel sind
        # UTC, ein lokales Tagesfenster wuerde das Limit gegenueber den
        # Daten verschieben. Siehe utc_today() in risk.py.
        spent_today = self._ledger.spent_on_day(self._config.symbol, utc_today())
        if spent_today + amount > self._config.max_daily_spend:
            logger.warning(
                "Tageslimit erreicht: %.2f von max. %.2f bereits ausgegeben. "
                "Kauf über %.2f wird übersprungen.",
                spent_today,
                self._config.max_daily_spend,
                amount,
            )
            return False
        return True

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
        Gleicht beim Bot-Start die eigene Kostenbasis gegen den
        tatsächlichen Kontostand ab (Stufe 2, Punkt 3 - siehe
        startup_checks.py). Laut, aber nicht blockierend.

        **Der DCA-Bot verkauft nie** - er hatte deshalb bis hierher gar
        keinen Moment, in dem seine Buchhaltung je gegen die Realität
        geprüft wurde, und band als einziger der drei `balance_guard`
        überhaupt nicht ein. Nötig ist es trotzdem: `TradeLedger.position()`
        ist die Kostenbasis des Portfolio-Stop-Loss, und der bewertet die
        Position mit `quantity * current_price`. Steht dort eine Menge,
        die es real nicht (mehr) gibt - weil Grid oder Trend auf dem
        geteilten Konto verkauft haben oder jemand manuell gehandelt hat -,
        fällt der Portfoliowert zu hoch aus und der Stop-Loss löst zu spät
        aus.

        `position()` schließt Dry-Run-Käufe bereits aus, die Menge ist
        also per Konstruktion die der echten Käufe.
        """
        _, quantity = self._ledger.position(self._config.symbol)
        report_ledger_vs_account(
            client=self._client,
            logger=logger,
            symbol=self._config.symbol,
            bot_name=self._config.bot_name,
            own_open_quantity=quantity,
            # Der DCA-Bot führt seine Telegram-Marker ohne Bot-Präfix
            # (siehe [KAUF]/[FEHLER]/[NOTAUS]) - anders als Grid und
            # Trend, die ihren Namen mitschreiben, weil sie sich den
            # Kanal mit ihm teilen.
            notify_tag="[BESTAND-DISKREPANZ]",
            ledger_label="Das DCA-Ledger",
        )

    def reconcile_pending_orders(self) -> None:
        """
        Trägt beim Bot-Start Käufe nach, deren Ausgang beim letzten Lauf
        offen geblieben ist (Sicherheitsreview-Punkt K2, Teil B - siehe
        pending_orders.py und main.py, das diese Methode vor der
        Hauptschleife aufruft).

        Ohne diesen Schritt fehlte die gekaufte Menge dauerhaft im
        Ledger: Tageslimit und Stop-Loss-Kostenbasis wären für immer zu
        niedrig, und zwar ohne dass irgendetwas darauf hinweist.
        """
        reconcile_pending_orders(
            client=self._client,
            store=self._client.pending_orders,
            bot_logger=logger,
            apply_confirmed=self._record_reconciled_buy,
        )

    def _record_reconciled_buy(self, pending: PendingOrder, order: dict) -> None:
        """
        Schreibt einen nachträglich bestätigten Kauf ins Ledger.

        Idempotent über `client_order_id`: stirbt der Prozess zwischen
        diesem Ledger-Eintrag und dem Entfernen des Pending-Eintrags,
        landet derselbe Kauf beim nächsten Start sonst ein zweites Mal
        im append-only Ledger - und verfälscht damit genau die beiden
        Größen, die der Eintrag eigentlich korrigieren soll (siehe
        TradeRecord.client_order_id in risk.py).
        """
        if self._ledger.has_client_order_id(pending.client_order_id):
            logger.info(
                "%sKauf zu Order %s ist bereits im Ledger - nichts nachzutragen.",
                RECONCILIATION_PREFIX,
                pending.client_order_id,
            )
            return

        if pending.side != "BUY":
            # Der DCA-Bot verkauft nie. Ein SELL-Eintrag kann hier nur
            # durch eine manuell veränderte Datei entstehen - dann lieber
            # laut abbrechen als etwas Erfundenes verbuchen (die
            # Exception hält den Pending-Eintrag fest, siehe
            # reconcile_pending_orders).
            raise ValueError(
                f"Unerwartete Order-Seite '{pending.side}' in der "
                "Pending-Orders-Datei des DCA-Bots - er platziert nur Käufe."
            )

        symbol = pending.symbol or self._config.symbol
        amount = float(pending.context.get("amount", self._config.quote_amount))

        rules = self._client.get_symbol_trading_rules(symbol)
        # get_order()-Antworten enthalten keine Fills und damit keine
        # Gebühren - ohne diesen Schritt käme die BRUTTO-Menge ins
        # Ledger und würde den Portfoliowert überschätzen (K3).
        order = self._client.get_order_with_fills(symbol, order)

        price = average_fill_price(
            order, fallback=float(pending.context.get("price", 0.0)) or 0.0
        )
        if price <= 0:
            raise ValueError(
                f"Kein brauchbarer Preis für Order {pending.client_order_id} "
                "ermittelbar - Ledger-Eintrag wäre wertlos."
            )

        quantity = net_executed_quantity(order, rules, fallback=amount / price)
        quote_spent = float(order.get("cummulativeQuoteQty", amount))

        self._ledger.record(
            TradeRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                symbol=symbol,
                quote_spent=quote_spent,
                quantity=quantity,
                price=price,
                dry_run=False,
                client_order_id=pending.client_order_id,
            )
        )

        logger.warning(
            "%sKauf nachgetragen: %.2f %s @ %.2f (Menge %.8f, Order %s). Der "
            "Trade wurde beim letzten Lauf ausgeführt, konnte aber nicht mehr "
            "verbucht werden.",
            RECONCILIATION_PREFIX,
            quote_spent,
            symbol,
            price,
            quantity,
            pending.client_order_id,
        )
        send_notification(
            f"[REKONZILIATION] Nachgetragener DCA-Kauf: {quote_spent:.2f} "
            f"{symbol} @ {price:.2f} (Menge: {quantity:.8f}). Die Order lief "
            "beim letzten Bot-Lauf durch, ihr Ergebnis kam aber nicht mehr an."
        )

    def execute_once(self) -> None:
        """Führt genau einen DCA-Kaufzyklus aus."""
        self._kill_switch.check()

        symbol = self._config.symbol
        amount = self._config.quote_amount

        # Optionale Kapital-Allocator-Anbindung (siehe allocator.py):
        # nur aktiv, wenn DCA_ALLOCATOR_STATE_FILE explizit gesetzt ist -
        # sonst read_allocation_fraction() -> None und amount bleibt
        # unverändert (exakt das Verhalten ohne Allocator).
        trend_fraction = read_allocation_fraction(self._config.allocator_state_file)
        if trend_fraction is not None:
            amount = self._config.quote_amount * (1 - trend_fraction)
            logger.info(
                "Allocator aktiv: DCA-Anteil %.1f%% -> effektiver Kaufbetrag %.2f (Basis %.2f).",
                (1 - trend_fraction) * 100,
                amount,
                self._config.quote_amount,
            )

        # Stop-Loss bewusst VOR dem Tageslimit geprüft: Er soll in jedem
        # Zyklus ausgewertet werden und pausieren/benachrichtigen können,
        # auch wenn das Tageslimit an diesem Tag bereits ausgeschöpft ist.
        # Andernfalls würde ein tagesübergreifend ausgeschöpftes Limit die
        # Stop-Loss-Prüfung (und damit die Benachrichtigung) bis zum
        # nächsten Tag verzögern, obwohl kein Kauf mehr stattfindet.
        price = self._client.get_current_price(symbol)
        logger.info("Aktueller Preis für %s: %.2f", symbol, price)

        if self._stop_loss.is_triggered(symbol, price):
            return

        if trend_fraction is not None and amount < MIN_EFFECTIVE_QUOTE_AMOUNT:
            logger.info(
                "Effektiver Kaufbetrag %.2f unter Mindestbetrag (%.2f) - Kauf heute "
                "übersprungen (Allocator weist DCA aktuell kaum/kein Kapital zu).",
                amount,
                MIN_EFFECTIVE_QUOTE_AMOUNT,
            )
            return

        if not self._within_daily_limit(amount):
            return

        # Erneute Prüfung unmittelbar vor der Orderplatzierung, damit ein
        # Notaus, der während der Preisabfrage ausgelöst wurde, den Kauf
        # noch verhindert statt erst im nächsten Zyklus zu greifen.
        self._kill_switch.check()

        # Handelsregeln bewusst VOR dem Kauf holen (danach aus dem Cache):
        # schlägt der Abruf fehl, bricht der Zyklus ab, ohne dass eine
        # Order existiert. Würde man sie erst nach dem Kauf brauchen,
        # könnte ein Fehler hier einen real ausgeführten Kauf unverbucht
        # lassen - siehe get_symbol_trading_rules in binance_client.py.
        rules = self._client.get_symbol_trading_rules(symbol)

        # `context` landet VOR dem Netzwerk-Call in der
        # Pending-Orders-Datei (siehe binance_client._place_order) und
        # enthält genau das, was reconcile_pending_orders() braucht, um
        # diesen Kauf später nachzutragen, falls die Antwort der Börse
        # nie ankommt oder der Prozess dazwischen stirbt.
        order = self._client.place_market_buy(
            symbol, amount, context={"price": price, "amount": amount}
        )

        if order is None and self._config.trading_enabled:
            # Echter Kaufversuch, der bei der Börse fehlgeschlagen ist
            # (siehe vorherige Fehlermeldung aus binance_client.py) - das
            # ist etwas anderes als ein Dry-Run und darf NICHT wie ein
            # ausgeführter Trade ins Ledger, sonst verfälscht die
            # geschätzte Menge Stop-Loss- und Tageslimit-Berechnung.
            logger.error(
                "Echter Kaufversuch für %s fehlgeschlagen (Preis ~%.2f) - "
                "kein Ledger-Eintrag, Betrag zählt nicht gegen das Tageslimit.",
                symbol,
                price,
            )
            send_notification(
                f"[FEHLER] Echter Kauf fehlgeschlagen für {symbol} "
                f"(Preis ~{price:.2f}). Siehe Bot-Log für Details."
            )
            return

        if order is not None:
            # Tatsaechlicher Fuellpreis aus der Order-Antwort
            # (cummulativeQuoteQty / executedQty), nicht der vor der Order
            # abgefragte Ticker - gleiche Quelle wie im Reconciliation-Pfad
            # (_record_reconciled_buy) und seit dem 25.09.2026 auch bei
            # Grid und Trend. Im Bot selbst liest niemand diesen Preis
            # (Stop-Loss und Tageslimit rechnen mit quantity/quote_spent),
            # wohl aber Dashboard und Steuer-Export. Der Ticker `price`
            # bleibt oben richtig: der Stop-Loss-Check braucht den
            # aktuellen Marktwert, nicht einen Fill.
            buy_price = average_fill_price(order, fallback=price)
            # Echte Order: tatsächlich ausgeführte Menge/Betrag verwenden,
            # falls die Börse abweichend vom angefragten Betrag gefüllt hat.
            # Die Menge wird dabei um die in BTC abgezogene Handelsgebühr
            # bereinigt (siehe order_utils). Der DCA-Bot verkauft zwar nie,
            # aber PortfolioStopLoss bewertet die Position mit
            # `quantity * current_price` - eine zu hohe Menge würde den
            # Portfoliowert überschätzen und den Stop-Loss zu spät auslösen.
            quantity = net_executed_quantity(order, rules, fallback=amount / price)
            quote_spent = float(order.get("cummulativeQuoteQty", amount))
        else:
            # Dry-Run: der beobachtete Preis IST der simulierte Fill.
            buy_price = price
            # Im Dry-Run gibt es keinen Fill und damit keine bekannte Gebühr -
            # sie wird bewusst NICHT geschätzt (das wäre erfundene Zahl),
            # die Menge aber trotzdem quantisiert, damit simulierte und
            # echte Werte vergleichbar bleiben.
            quantity = quantize_quantity(amount / price, rules.step_size)
            # Der Betrag muss der quantisierten Menge folgen: die
            # weggerundete Teilmenge wurde nie gekauft. Ein echter Fill
            # liefert oben cummulativeQuoteQty, also den tatsaechlich
            # belasteten Betrag - `quantity * price` ist dessen
            # Entsprechung im Dry-Run. Beim DCA-Bot gibt es zwar keine
            # realisierte PnL (er verkauft nie) und der Portfolio-
            # Stop-Loss sieht Dry-Run-Kaeufe gar nicht erst
            # (TradeLedger.position filtert sie heraus) - day_summary()
            # summiert aber ueber ALLE Kaeufe inklusive der simulierten.
            # Der Rohbetrag liess den Bot also einen Betrag gegen sein
            # Tageslimit buchen, den er in der Simulation nie ausgegeben
            # hat, und meldete ihn so auch in der Tageszusammenfassung.
            quote_spent = quantity * price

        self._ledger.record(
            TradeRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                symbol=symbol,
                quote_spent=quote_spent,
                quantity=quantity,
                price=buy_price,
                dry_run=not self._config.trading_enabled,
                # Ohne diese ID könnte die Reconciliation beim nächsten
                # Start nicht erkennen, dass dieser Kauf bereits
                # verbucht ist (siehe TradeRecord in risk.py).
                client_order_id=order.get("clientOrderId") if order else None,
            )
        )

        if order is not None:
            logger.info(
                "DCA-Kauf ausgeführt: %.2f %s zu Preis %.2f",
                amount,
                symbol,
                buy_price,
            )
            send_notification(
                f"[KAUF] Echter DCA-Kauf ausgeführt: {amount:.2f} {symbol} "
                f"@ {buy_price:.2f} (Menge: {quantity:.8f})"
            )
        else:
            send_notification(
                f"[DRY-RUN] Simulierter Kauf: {amount:.2f} {symbol} "
                f"@ {buy_price:.2f} (Menge: {quantity:.8f})"
            )

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
from datetime import date, datetime, timezone

from .allocator_signals import MIN_EFFECTIVE_QUOTE_AMOUNT, read_allocation_fraction
from .binance_client import TradingClient
from .config import Config
from .notifier import send_notification
from .order_utils import net_executed_quantity, quantize_quantity
from .risk import KillSwitch, PortfolioStopLoss, TradeLedger, TradeRecord

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
        spent_today = self._ledger.spent_on_day(self._config.symbol, date.today())
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

        order = self._client.place_market_buy(symbol, amount)

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
            # Im Dry-Run gibt es keinen Fill und damit keine bekannte Gebühr -
            # sie wird bewusst NICHT geschätzt (das wäre erfundene Zahl),
            # die Menge aber trotzdem quantisiert, damit simulierte und
            # echte Werte vergleichbar bleiben.
            quantity = quantize_quantity(amount / price, rules.step_size)
            quote_spent = amount

        self._ledger.record(
            TradeRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                symbol=symbol,
                quote_spent=quote_spent,
                quantity=quantity,
                price=price,
                dry_run=not self._config.trading_enabled,
            )
        )

        if order is not None:
            logger.info(
                "DCA-Kauf ausgeführt: %.2f %s zu Preis ~%.2f",
                amount,
                symbol,
                price,
            )
            send_notification(
                f"[KAUF] Echter DCA-Kauf ausgeführt: {amount:.2f} {symbol} "
                f"@ {price:.2f} (Menge: {quantity:.8f})"
            )
        else:
            send_notification(
                f"[DRY-RUN] Simulierter Kauf: {amount:.2f} {symbol} "
                f"@ {price:.2f} (Menge: {quantity:.8f})"
            )

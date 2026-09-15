"""
Dünner Wrapper um die python-binance-Bibliothek.

Kapselt den Verbindungsaufbau zum Testnet und die eigentliche Order-Platzierung,
damit strategy.py sich nicht um API-Details kümmern muss und wir die
Trading-Logik einfacher testen/mocken können.
"""

from __future__ import annotations

import logging

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

from .config import Config

logger = logging.getLogger("dca_bot")


class TradingClient:
    def __init__(self, config: Config):
        self._config = config
        self._client = Client(
            config.api_key,
            config.api_secret,
            testnet=config.use_testnet,
        )
        logger.info(
            "Binance-Client initialisiert (testnet=%s)", config.use_testnet
        )

    def get_current_price(self, symbol: str) -> float:
        """Aktuellen Preis für ein Symbol abfragen (z.B. BTCUSDT)."""
        ticker = self._client.get_symbol_ticker(symbol=symbol)
        return float(ticker["price"])

    def get_quote_balance(self, quote_asset: str) -> float:
        """Verfügbares Guthaben der Quote-Währung (z.B. USDT) abfragen."""
        balance = self._client.get_asset_balance(asset=quote_asset)
        return float(balance["free"]) if balance else 0.0

    def place_market_buy(self, symbol: str, quote_order_qty: float) -> dict | None:
        """
        Platziert einen Market-Buy über einen festen Quote-Betrag
        (z.B. "kaufe für 15 USDT Bitcoin", unabhängig vom aktuellen Preis).

        Gibt None zurück, wenn Trading deaktiviert ist (Sicherheits-Schalter)
        oder ein Fehler auftritt - der Bot soll nie wegen eines API-Fehlers
        abstürzen, sondern sauber loggen und weiterlaufen/abbrechen können.
        """
        if not self._config.trading_enabled:
            logger.info(
                "[DRY-RUN] Würde Market-Buy platzieren: %s für %.2f Quote-Einheiten",
                symbol,
                quote_order_qty,
            )
            return None

        try:
            order = self._client.order_market_buy(
                symbol=symbol,
                quoteOrderQty=quote_order_qty,
            )
            logger.info("Order erfolgreich platziert: %s", order)
            return order
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.error("Fehler beim Platzieren der Order: %s", exc)
            return None

    def place_market_sell(self, symbol: str, quantity: float) -> dict | None:
        """
        Platziert einen Market-Sell über eine exakte Menge des Base-Assets
        (z.B. "verkaufe 0.0002 BTC") - z.B. zum Schließen einer einzelnen
        Grid-Position. Gleiche Sicherheits-/Fehlerlogik wie place_market_buy:
        Dry-Run-Schalter und niemals ein Absturz wegen eines API-Fehlers.
        """
        if not self._config.trading_enabled:
            logger.info(
                "[DRY-RUN] Würde Market-Sell platzieren: %s, Menge %.8f",
                symbol,
                quantity,
            )
            return None

        try:
            order = self._client.order_market_sell(
                symbol=symbol,
                quantity=quantity,
            )
            logger.info("Sell-Order erfolgreich platziert: %s", order)
            return order
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.error("Fehler beim Platzieren der Sell-Order: %s", exc)
            return None

    def place_stop_loss_limit_sell(
        self, symbol: str, quantity: float, stop_price: float, limit_price: float
    ) -> dict | None:
        """
        Platziert eine echte, exchange-seitige STOP_LOSS_LIMIT-Sell-Order:
        löst aus, sobald der Marktpreis `stop_price` erreicht, wird dann
        als Limit-Order zu `limit_price` (leicht unter `stop_price`, siehe
        TREND_STOP_LIMIT_OFFSET_PCT) ins Orderbuch gelegt. Anders als der
        software-interne Stop-Loss (der nur wirkt, solange der Bot-Prozess
        läuft) übernimmt die Börse selbst die Überwachung - schützt eine
        offene Position auch bei Bot-/Internet-/Stromausfall.

        Gleiche Sicherheits-/Fehlerlogik wie die übrigen place_*-Methoden:
        Dry-Run-Schalter und niemals ein Absturz wegen eines API-Fehlers.
        """
        # TODO vor echtem Geld: stop_price/limit_price werden hier nur auf
        # 2 Nachkommastellen gerundet, nicht gegen die tatsächliche
        # PRICE_FILTER-Tick-Size des Symbols validiert. Vor dem Live-Start
        # unbedingt durch eine echte Abfrage von Client.get_symbol_info()
        # /exchangeInfo (PRICE_FILTER.tickSize) ersetzen - sonst kann die
        # Order von der Börse mit "Filter failure: PRICE_FILTER" abgelehnt
        # werden, je nach Symbol.
        stop_price = round(stop_price, 2)
        limit_price = round(limit_price, 2)

        if not self._config.trading_enabled:
            logger.info(
                "[DRY-RUN] Würde Stop-Loss-Order platzieren: %s, Menge %.8f, "
                "Stop %.2f, Limit %.2f",
                symbol,
                quantity,
                stop_price,
                limit_price,
            )
            return None

        try:
            order = self._client.create_order(
                symbol=symbol,
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_STOP_LOSS_LIMIT,
                timeInForce=Client.TIME_IN_FORCE_GTC,
                quantity=quantity,
                stopPrice=stop_price,
                price=limit_price,
            )
            logger.info("Stop-Loss-Order erfolgreich platziert: %s", order)
            return order
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.error("Fehler beim Platzieren der Stop-Loss-Order: %s", exc)
            return None

    def cancel_order(self, symbol: str, order_id: str) -> dict | None:
        """
        Storniert eine offene Order (z.B. eine Stop-Loss-Order vor einem
        Signal-basierten Exit). Ein Fehlschlag - z.B. weil die Order
        zwischenzeitlich bereits gefüllt oder storniert wurde (Binance
        liefert dafür typischerweise Fehlercode -2011 "Unknown order
        sent"), aber auch ein echter transienter Fehler - wird hier
        bewusst NICHT unterschieden (jeder Fehler wird einheitlich als
        Warnung geloggt, nicht als Fehler, und gibt None zurück). Der
        Grund: der numerische Fehlercode allein ist keine zuverlässige
        Grundlage für eine Sell/Nicht-Sell-Entscheidung (z.B. ob die
        Position bereits verkauft ist) - das übernimmt die aufrufende
        Seite (trend_strategy.py, _resolve_stop_order_before_close)
        robuster per erneuter get_order_status()-Abfrage der tatsächlichen
        Order-Ground-Truth statt Code-Interpretation hier. Der Code wird
        hier nur mitgeloggt, für die Fehlersuche im Log.
        """
        try:
            result = self._client.cancel_order(symbol=symbol, orderId=order_id)
            logger.info("Order %s storniert: %s", order_id, result)
            return result
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.warning(
                "Stornieren der Order %s fehlgeschlagen (Code %s, evtl. "
                "bereits gefüllt/storniert, evtl. transient): %s",
                order_id,
                getattr(exc, "code", "?"),
                exc,
            )
            return None

    def get_order_status(self, symbol: str, order_id: str) -> dict | None:
        """
        Fragt den aktuellen Status einer Order ab (z.B. um zu prüfen, ob
        eine Stop-Loss-Order zwischenzeitlich - auch während einer
        Bot-Downtime - gefüllt wurde). Gibt None zurück statt einer
        Exception, falls die Abfrage fehlschlägt.
        """
        try:
            return self._client.get_order(symbol=symbol, orderId=order_id)
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.error("Fehler beim Abfragen des Order-Status für %s: %s", order_id, exc)
            return None

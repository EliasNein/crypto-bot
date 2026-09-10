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

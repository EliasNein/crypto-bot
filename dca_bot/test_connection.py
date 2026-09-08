"""
Schneller Verbindungs- und Funktionstest, unabhängig vom 24h-Intervall
des eigentlichen Bots.

Ausführen mit:  python -m dca_bot.test_connection
"""

from __future__ import annotations

import logging

from .binance_client import TradingClient
from .config import load_config
from .strategy import DCAStrategy


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("dca_bot")

    logger.info("Lade Konfiguration ...")
    config = load_config()

    logger.info("Baue Verbindung zur Binance Testnet API auf ...")
    client = TradingClient(config)

    # 1) Reiner Verbindungstest: aktuellen Preis abfragen
    price = client.get_current_price(config.symbol)
    logger.info("✓ Verbindung erfolgreich. Aktueller Preis %s: %.2f",
                config.symbol, price)

    # 2) Kontostand der Quote-Währung abfragen (z.B. USDT-Testguthaben)
    quote_asset = config.symbol.replace("BTC", "")  # simple Ableitung, z.B. "USDT"
    balance = client.get_quote_balance(quote_asset)
    logger.info("✓ Testnet-Guthaben %s: %.2f", quote_asset, balance)

    # 3) Einen einzelnen DCA-Zyklus ausführen (Dry-Run, falls Trading aus ist)
    logger.info("Führe einen einzelnen DCA-Testzyklus aus ...")
    strategy = DCAStrategy(config, client)
    strategy.execute_once()

    logger.info("Test abgeschlossen. Trading aktiv war: %s",
                config.trading_enabled)


if __name__ == "__main__":
    main()

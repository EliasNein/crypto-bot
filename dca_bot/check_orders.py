"""
Zeigt die letzten Orders für ein Symbol an - Ersatz für eine Web-Oberfläche,
da testnet.binance.vision nur zur API-Key-Verwaltung dient, nicht zur
Anzeige von Guthaben/Trades.

Ausführen mit:  python -m dca_bot.check_orders
"""

from __future__ import annotations

from .binance_client import TradingClient
from .config import load_config


def main() -> None:
    config = load_config()
    client = TradingClient(config)

    print(f"\n--- Letzte Orders für {config.symbol} ---")
    orders = client._client.get_all_orders(symbol=config.symbol, limit=10)

    if not orders:
        print("Keine Orders gefunden. Es wurde noch kein Trade ausgeführt.")
        return

    for order in orders:
        print(
            f"ID: {order['orderId']} | "
            f"Status: {order['status']} | "
            f"Seite: {order['side']} | "
            f"Menge: {order['executedQty']} | "
            f"Ausgegeben: {order['cummulativeQuoteQty']} | "
            f"Zeit: {order['time']}"
        )

    print(f"\n--- Aktuelle Guthaben ---")
    quote_asset = config.symbol.replace("BTC", "")
    base_asset = config.symbol.replace(quote_asset, "")
    print(f"{base_asset}: {client._client.get_asset_balance(asset=base_asset)}")
    print(f"{quote_asset}: {client._client.get_asset_balance(asset=quote_asset)}")


if __name__ == "__main__":
    main()

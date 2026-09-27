"""
Pending-Orders-Ablage im Speicher, fuer die Fake-Clients der Testdateien.

Seit dem Systemcheck vom 27.09.2026 greifen die Strategien auch zur
Laufzeit auf die Pending-Datei zu: Reconciliation zu Beginn jedes Zyklus,
`confirm_booked()` nach jedem Ledger-Eintrag (W-A) und die Sperre fuer
Positionen mit offener Order-Frage (K-B). Die Fakes, die den
`TradingClient` als Ganzes ersetzen, brauchen dafuer dieselbe
Schnittstelle - mit echter Logik (es ist eine echte `PendingOrderStore`,
nur ohne Datei), damit sie nicht still anders funktionieren als der
Produktivcode.
"""

from __future__ import annotations

import copy
from pathlib import Path

from dca_bot.pending_orders import PENDING_FILE_VERSION, PendingOrderStore


class InMemoryPendingOrderStore(PendingOrderStore):
    def __init__(self, bot_name: str = "test"):
        # Bewusst ohne super().__init__(): der legt ein Verzeichnis an.
        self._path = Path(f"<speicher:{bot_name}>")
        self._bot_name = bot_name
        self._payload = {"version": PENDING_FILE_VERSION, "bot": bot_name, "orders": []}

    def _read_payload(self) -> dict:
        return copy.deepcopy(self._payload)

    def _write_payload(self, orders: list[dict]) -> None:
        self._payload = {
            "version": PENDING_FILE_VERSION,
            "bot": self._bot_name,
            "orders": copy.deepcopy(orders),
        }


class PendingOrdersMixin:
    """
    Fuer Fake-Clients: `pending_orders` und `confirm_booked()` wie beim
    echten TradingClient. `_init_pending()` im Konstruktor aufrufen.
    """

    def _init_pending(self, bot_name: str) -> None:
        self.pending_orders = InMemoryPendingOrderStore(bot_name)
        self.confirmed_client_order_ids: list[str] = []

    def confirm_booked(self, client_order_id: str | None) -> None:
        if client_order_id:
            self.confirmed_client_order_ids.append(client_order_id)
            self.pending_orders.remove(client_order_id)

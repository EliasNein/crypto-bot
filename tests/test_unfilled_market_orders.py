"""
Market-Orders ohne oder mit nur teilweiser Ausfuehrung (16.10.2026, Runde 1).

Befund vom Homeserver: Elf Grid-Eintraege vom 09.10. und 11.10.2026 standen
als offene Positionen mit Menge 0 im Ledger. Die Boerse hatte die
Kauf-Orders mit `EXPIRED` und ausgefuehrt 0 beendet, der Bot buchte sie
trotzdem - der regulaere Antwortweg pruefte weder Status noch Menge.

Geprueft wird hier:

- A1: `_place_order` bewertet die regulaere Antwort einer Market-Order
  (ohne Wirkung -> None und Eintrag weg; unklar -> None, Eintrag bleibt,
  [ORDER-UNKLAR]; Stop-Orders unveraendert).
- A3: Kein Ledger nimmt einen echten Eintrag ohne Menge oder Einsatz an -
  und alte Eintraege ohne Bestand blockieren das Schreiben nicht.
- T2: Ein nur teilweise ausgefuehrter Kauf wird mit der echten Menge
  gebucht; liegt sie unter dem Mindestvolumen, als Staub geschlossen.
- Runde 1 beim Verkauf: Teilfuellung wurde laut gemeldet und wie bisher
  gebucht. Seit Runde 2 (19.10.2026) bucht die Strategie die ausgefuehrte
  Menge, die Meldung entfaellt - geprueft hier, dass sie nicht mehr kommt;
  das Buchen pruefen tests/test_partial_sell_grid.py und
  tests/test_partial_sell_trend.py.

Jede neue Pruefung hat hier mindestens einen Test, der bei ihrer Mutation
rot wird (Mutationsprobe vom 16.10.2026, siehe trading-bot-projekt.md).

Ausfuehren mit:  python -m unittest tests.test_unfilled_market_orders -v
"""

from __future__ import annotations

import json
import logging
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dca_bot.binance_client import TradingClient
from dca_bot.grid_risk import GridLedger, GridPosition
from dca_bot.order_utils import SymbolTradingRules, is_dust, received_base_quantity
from dca_bot.pending_orders import (
    KIND_MARKET,
    LOOKUP_FOUND,
    PendingOrder,
    PendingOrderStore,
    is_partial_fill,
    reconcile_pending_orders,
)
from dca_bot.risk import ImplausibleLedgerEntry, TradeLedger, TradeRecord
from dca_bot.trend_risk import TrendLedger, TrendTrade

from tests.test_pending_orders import FakeLookupClient, FakeRawBinanceClient, TradingClientTestBase
from tests.test_shared_account import SYMBOL, SharedAccountTestBase

RULES = SymbolTradingRules(
    symbol="BTCUSDT", tick_size=0.01, step_size=0.00001, min_notional=5.0,
    base_asset="BTC", quote_asset="USDT", quote_precision=8,
)

ENDED_WITHOUT_FILL = ("EXPIRED", "CANCELED", "REJECTED", "EXPIRED_IN_MATCH")


class PatchedRawClient(FakeRawBinanceClient):
    """Wie FakeRawBinanceClient, aber jede Order-Antwort laesst sich ueberschreiben."""

    def __init__(self):
        super().__init__()
        self.response_patch: dict = {}
        self.drop_status = False

    def _order_response(self, params: dict, executed_qty: float, quote: float) -> dict:
        response = super()._order_response(params, executed_qty, quote)
        response.update(self.response_patch)
        if self.drop_status:
            response.pop("status", None)
        return response

    def create_order(self, **params):
        response = super().create_order(**params)
        if self.drop_status:
            response.pop("status", None)
        return response


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------


class BuildingBlocksTestCase(unittest.TestCase):
    def test_is_partial_fill(self):
        self.assertTrue(is_partial_fill({"status": "EXPIRED", "executedQty": "0.0001"}))
        self.assertTrue(is_partial_fill({"status": "CANCELED", "executedQty": "0.0001"}))
        self.assertFalse(is_partial_fill({"status": "FILLED", "executedQty": "0.0001"}))
        self.assertFalse(is_partial_fill({"status": "EXPIRED", "executedQty": "0.00000000"}))
        self.assertFalse(is_partial_fill({"status": "PARTIALLY_FILLED", "executedQty": "0.0001"}))
        self.assertFalse(is_partial_fill(None))

    def test_is_dust_uses_step_size_and_min_notional(self):
        self.assertTrue(is_dust(0.000009, 50_000.0, RULES), "unter einer stepSize")
        self.assertTrue(is_dust(0.00009, 50_000.0, RULES), "4,50 < Mindestvolumen 5")
        self.assertFalse(is_dust(0.0001, 50_000.0, RULES), "genau 5,00 ist erlaubt")
        self.assertFalse(is_dust(0.0002, 50_000.0, RULES))

    def test_received_base_quantity_is_not_rounded(self):
        order = {"executedQty": "0.00001", "fills": [
            {"commission": "0.0000000100", "commissionAsset": "BTC"}]}
        self.assertAlmostEqual(received_base_quantity(order, RULES), 0.00000999, places=12)


# ---------------------------------------------------------------------------
# A1: regulaere Antwort einer Market-Order
# ---------------------------------------------------------------------------


class DirectMarketResponseTestCase(TradingClientTestBase):
    def _make(self):
        # Je Aufruf eine eigene Pending-Datei - die Unter-Tests duerfen sich
        # nicht gegenseitig Eintraege hinterlassen.
        self._count = getattr(self, "_count", 0) + 1
        self.pending_file = str(Path(self._tmpdir.name) / f"pending_{self._count}.json")
        client, _ = self._make_client()
        raw = PatchedRawClient()
        client._client = raw
        return client, raw

    def _place(self, client, side: str):
        if side == "BUY":
            return client.place_market_buy("BTCUSDT", 15.0)
        return client.place_market_sell("BTCUSDT", 0.0002)

    def test_market_order_ended_without_fill_is_not_returned(self):
        for side in ("BUY", "SELL"):
            for status in ENDED_WITHOUT_FILL:
                with self.subTest(side=side, status=status):
                    client, raw = self._make()
                    raw.response_patch = {"status": status, "executedQty": "0.00000000",
                                          "cummulativeQuoteQty": "0.00000000", "fills": []}
                    with mock.patch("dca_bot.binance_client.send_notification") as notify:
                        with self.assertLogs("dca_bot", level="ERROR") as logs:
                            order = self._place(client, side)
                    self.assertIsNone(order)
                    self.assertEqual(self._pending_ids(), [], "Eintrag muss weg sein")
                    notify.assert_not_called()
                    text = "\n".join(logs.output)
                    self.assertIn("[ORDER-OHNE-AUSFUEHRUNG]", text)
                    self.assertIn(f"Boerse meldet Status {status}", text)
                    self.assertNotIn("Verbindungs", text)
                    self.assertNotIn("erfolgreich platziert", text)

    def test_partially_filled_market_buy_is_returned_and_entry_stays(self):
        client, raw = self._make()
        raw.response_patch = {"status": "EXPIRED", "executedQty": "0.00010000",
                              "cummulativeQuoteQty": "7.70000000"}
        order = client.place_market_buy("BTCUSDT", 15.0)
        self.assertIsNotNone(order)
        self.assertEqual(self._pending_ids(), [order["clientOrderId"]],
                         "bis confirm_booked() bleibt der Eintrag (W-A)")

    def test_filled_market_buy_is_returned(self):
        client, _ = self._make()
        with self.assertLogs("dca_bot", level="INFO") as logs:
            order = client.place_market_buy("BTCUSDT", 15.0)
        self.assertIsNotNone(order)
        self.assertIn("Boerse meldet Status FILLED", "\n".join(logs.output))

    def test_live_unknown_or_missing_status_is_unclear(self):
        cases = (
            ("NEW", {"status": "NEW", "executedQty": "0"}),
            ("PARTIALLY_FILLED", {"status": "PARTIALLY_FILLED", "executedQty": "0.0001"}),
            ("unbekannt", {"status": "SOMETHING_NEW", "executedQty": "0.0002"}),
            ("fehlt", None),
        )
        for side in ("BUY", "SELL"):
            for name, patch in cases:
                with self.subTest(side=side, status=name):
                    client, raw = self._make()
                    if patch is None:
                        raw.drop_status = True
                    else:
                        raw.response_patch = patch
                    with mock.patch("dca_bot.binance_client.send_notification") as notify:
                        with self.assertLogs("dca_bot", level="ERROR") as logs:
                            order = self._place(client, side)
                    self.assertIsNone(order)
                    self.assertEqual(len(self._pending_ids()), 1, "Eintrag bleibt fuer K-B")
                    notify.assert_called_once()
                    self.assertIn("[ORDER-UNKLAR]", notify.call_args.args[0])
                    self.assertIn("Boerse meldet Status", notify.call_args.args[0])
                    self.assertIn("UNKLARER ORDER-ZUSTAND", "\n".join(logs.output))

    def test_stop_orders_are_not_evaluated(self):
        """E1: Stop-Orders laufen unveraendert durch - auch ohne Statusfeld."""
        for drop in (False, True):
            with self.subTest(ohne_status=drop):
                client, raw = self._make()
                raw.drop_status = drop
                order = client.place_stop_loss_limit_sell("BTCUSDT", 0.0002, 69_000.0, 68_655.0)
                self.assertIsNotNone(order)
                self.assertEqual(len(self._pending_ids()), 1)

    def test_partial_market_sell_is_returned_without_the_round_1_report(self):
        """Runde 2 (19.10.2026): Die Strategie bucht die Teilmenge selbst - der
        Client gibt die Order zurueck, haelt den Eintrag bis confirm_booked()
        und meldet nichts mehr als TEILFUELLUNG-UNGEBUCHT."""
        for patch in ({"status": "EXPIRED", "executedQty": "0.00010000",
                       "cummulativeQuoteQty": "7.70000000"}, {}):
            with self.subTest(teilweise=bool(patch)):
                client, raw = self._make()
                raw.response_patch = patch
                with mock.patch("dca_bot.pending_orders.send_notification") as notify_p, \
                        mock.patch("dca_bot.binance_client.send_notification") as notify_c:
                    with self.assertLogs("dca_bot", level="INFO") as logs:
                        order = client.place_market_sell("BTCUSDT", 0.0002)
                self.assertIsNotNone(order)
                self.assertEqual(self._pending_ids(), [order["clientOrderId"]],
                                 "bis confirm_booked() bleibt der Eintrag (W-A)")
                notify_p.assert_not_called()
                notify_c.assert_not_called()
                self.assertNotIn("TEILFUELLUNG", "\n".join(logs.output))


class ReconciledPartialSellTestCase(unittest.TestCase):
    """Auch beim Nachtragen keine Runde-1-Meldung mehr - das Buchen und Melden
    uebernimmt seit Runde 2 die Strategie (apply_confirmed)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = PendingOrderStore(str(Path(self._tmp.name) / "p.json"), "grid")

    def _run(self, side: str, order: dict) -> mock.Mock:
        self.store.add(PendingOrder.new("grid-x", KIND_MARKET, "BTCUSDT", side, {}))
        apply_confirmed = mock.Mock()
        with mock.patch("dca_bot.pending_orders.send_notification") as notify:
            with self.assertLogs("dca_bot", level="INFO"):
                reconcile_pending_orders(FakeLookupClient((LOOKUP_FOUND, order)), self.store,
                                         logging.getLogger("dca_bot"), apply_confirmed, set())
        apply_confirmed.assert_called_once()
        return notify

    def test_nothing_is_reported_as_unbooked(self):
        for side, order in (("BUY", {"status": "EXPIRED", "executedQty": "0.0001"}),
                            ("SELL", {"status": "EXPIRED", "executedQty": "0.0001", "origQty": "0.0002"}),
                            ("SELL", {"status": "FILLED", "executedQty": "0.0002"})):
            with self.subTest(side=side, status=order["status"]):
                self.store = PendingOrderStore(
                    str(Path(self._tmp.name) / f"{side}-{order['status']}.json"), "grid"
                )
                notify = self._run(side, order)
                self.assertFalse(any("TEILFUELLUNG" in c.args[0] for c in notify.call_args_list))


# ---------------------------------------------------------------------------
# A3: Ledger-Schutz
# ---------------------------------------------------------------------------


class LedgerGuardTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    @staticmethod
    def _grid(quantity=0.0002, quote_spent=15.0, dry_run=False):
        return GridPosition.new(level_index=3, buy_price=75_000.0, target_sell_price=76_125.0,
                                quantity=quantity, quote_spent=quote_spent, dry_run=dry_run,
                                client_order_id="grid-a", symbol="BTCUSDT")

    @staticmethod
    def _trend(quantity=0.0002, quote_spent=15.0, dry_run=False):
        return TrendTrade.new(entry_price=75_000.0, quantity=quantity, quote_spent=quote_spent,
                              dry_run=dry_run, client_order_id="trend-a", symbol="BTCUSDT")

    @staticmethod
    def _dca(quantity=0.0002, quote_spent=15.0, dry_run=False):
        return TradeRecord(timestamp="2026-10-16T10:00:00+00:00", symbol="BTCUSDT",
                           quote_spent=quote_spent, quantity=quantity, price=75_000.0,
                           dry_run=dry_run, client_order_id="dca-a")

    def _ledgers(self):
        return (
            ("grid", GridLedger(str(self.dir / "g.json")), self._grid, "record_buy"),
            ("trend", TrendLedger(str(self.dir / "t.json")), self._trend, "record_entry"),
            ("dca", TradeLedger(str(self.dir / "d.json")), self._dca, "record"),
        )

    def test_real_entry_without_quantity_or_spend_is_refused(self):
        bad = ({"quantity": 0.0}, {"quantity": -0.0001}, {"quantity": math.nan},
               {"quote_spent": 0.0}, {"quote_spent": -1.0}, {"quantity": 0.0, "quote_spent": 0.0})
        for name, ledger, make, method in self._ledgers():
            for values in bad:
                with self.subTest(ledger=name, werte=values):
                    with mock.patch(f"dca_bot.{'risk' if name == 'dca' else name + '_risk'}.logger"):
                        with self.assertRaises(ImplausibleLedgerEntry):
                            getattr(ledger, method)(make(**values))
                    self.assertEqual(ledger._read(), [], "nichts geschrieben")

    def test_dry_run_and_normal_entries_are_accepted(self):
        for name, ledger, make, method in self._ledgers():
            with self.subTest(ledger=name):
                getattr(ledger, method)(make(quantity=0.0, quote_spent=0.0, dry_run=True))
                getattr(ledger, method)(make())
                self.assertEqual(len(ledger._read()), 2)

    def test_existing_unfilled_entries_do_not_block_writing(self):
        """Der Altbestand vom Homeserver darf bis zur Bereinigung nichts blockieren."""
        for name, ledger, make, method in self._ledgers():
            with self.subTest(ledger=name):
                phantom = make()
                record = phantom.__dict__ | {"quantity": 0.0, "quote_spent": 0.0}
                ledger._write([record])
                getattr(ledger, method)(make())
                self.assertEqual(len(ledger._read()), 2)


# ---------------------------------------------------------------------------
# Ende zu Ende auf dem geteilten Konto: Kauf
# ---------------------------------------------------------------------------


class UnfilledBuyEndToEndTestCase(SharedAccountTestBase):
    PRICE = 75_000.0

    def _trigger_grid_buy(self, grid, level: int = 3) -> None:
        level_price = grid._levels[level]
        self.exchange.price = round(level_price - 1.0, 2)
        grid._last_seen_price = level_price + 1.0

    def _tags(self, prefix: str) -> list[str]:
        return [m for m in self.messages if m.startswith(prefix)]

    # -- Grid --

    def test_grid_buy_without_fill_books_nothing_and_keeps_the_level_free(self):
        grid = self.start_grid()
        self._trigger_grid_buy(grid)
        self.exchange.set_liquidity("order_market_buy", 0.0)
        grid.execute_once()

        self.assertEqual(grid._ledger._read(), [], "keine Position mit Menge 0")
        self.assertEqual(grid._client.pending_orders.all(), [])
        self.assertEqual(self._tags("[GRID-KAUF]"), [])
        self.assertEqual(len(self._tags("[GRID-FEHLER]")), 1)
        self.assertIn("nicht verbucht", self._tags("[GRID-FEHLER]")[0])
        self.assert_ownership()

        # Die Stufe ist frei: beim naechsten Durchqueren wird regulaer gekauft.
        self._trigger_grid_buy(grid)
        grid.execute_once()
        self.assertEqual(len(grid._ledger.open_positions()), 1)
        self.assert_ownership()

    def test_grid_buy_partially_filled_is_booked_with_the_real_quantity(self):
        grid = self.start_grid()
        self._trigger_grid_buy(grid)
        self.exchange.set_liquidity("order_market_buy", 0.6)
        grid.execute_once()

        [position] = grid._ledger.open_positions()
        net = self.exchange.net_base("grid")
        self.assertGreater(net, 0)
        self.assertAlmostEqual(position["quantity"], net, places=9)
        self.assertLess(position["quote_spent"], 15.0)
        self.assertIsNone(position["close_reason"])
        [message] = self._tags("[GRID-KAUF]")
        self.assertIn("Teilfüllung", message)
        self.assert_ownership()

    def test_grid_buy_partially_filled_below_min_notional_is_closed_as_dust(self):
        grid = self.start_grid()
        self._trigger_grid_buy(grid)
        self.exchange.set_liquidity("order_market_buy", 0.3)  # ~4,50 < 5
        grid.execute_once()

        self.assertEqual(grid._ledger.open_positions(), [], "Stufe ist frei")
        [record] = grid._ledger._read()
        self.assertEqual(record["status"], "closed")
        self.assertEqual(record["close_reason"], "dust")
        self.assertAlmostEqual(record["dust_qty"], self.exchange.net_base("grid"), places=9)
        self.assertGreater(record["quantity"], 0)
        self.assertAlmostEqual(record["realized_pnl"], -record["quote_spent"], places=9)
        self.assertIsNone(record["sell_price"])
        self.assertEqual(self._tags("[GRID-KAUF]"), [])
        self.assertEqual(len(self._tags("[GRID-STAUB]")), 1)
        self.assertEqual(grid._client.pending_orders.all(), [])
        self.assertFalse(grid._stop_loss.is_paused(), "Staub setzt keine Sperre")
        self.assert_ownership()

    def test_grid_dust_is_measured_at_the_fill_price(self):
        """
        0.00007 BTC auf Stufe 1: zum Fuellpreis (~71.049) knapp unter dem
        Mindestvolumen (4,97), zum Verkaufsziel (~72.116) knapp darueber
        (5,05). Massgeblich ist der Fuellpreis (Plan vom 16.10.2026).
        """
        grid = self.start_grid()
        self._trigger_grid_buy(grid, level=1)
        self.exchange.set_liquidity("order_market_buy", 0.334)  # 0.00021 x 0.334 -> 0.00007
        grid.execute_once()
        [record] = grid._ledger._read()
        self.assertAlmostEqual(record["quantity"], 0.00007, places=12)
        self.assertLess(record["quantity"] * record["buy_price"], 5.0)
        self.assertGreaterEqual(record["quantity"] * record["target_sell_price"], 5.0)
        self.assertEqual(record["close_reason"], "dust")
        self.assert_ownership()

    def test_grid_reconciled_buy_without_fill_is_discarded(self):
        """Antwort verloren, die Order lief ohne Ausfuehrung ab - nichts nachtragen."""
        grid = self.start_grid()
        self._trigger_grid_buy(grid)
        self.exchange.set_liquidity("order_market_buy", 0.0)
        self.exchange.inject("order_market_buy", "lost")
        grid.execute_once()
        grid.execute_once()  # Reconciliation zu Beginn des Zyklus
        self.assertEqual(grid._ledger._read(), [])
        self.assertEqual(grid._client.pending_orders.all(), [])
        self.assert_ownership()

    def test_grid_reconciled_partial_buy_below_min_notional_is_closed_as_dust(self):
        grid = self.start_grid()
        self._trigger_grid_buy(grid)
        self.exchange.set_liquidity("order_market_buy", 0.3)
        self.exchange.inject("order_market_buy", "lost")
        self.exchange.lookup_down = True
        grid.execute_once()  # Kauf teilweise ausgefuehrt, Antwort verloren, Rueckfrage scheitert
        self.exchange.lookup_down = False
        grid.execute_once()  # Reconciliation traegt nach

        [record] = grid._ledger._read()
        self.assertEqual(record["close_reason"], "dust")
        self.assertEqual(grid._ledger.open_positions(), [])
        self.assertTrue(any("[GRID-STAUB]" in m for m in self.messages))
        self.assert_ownership()

    def test_ledger_guard_catches_what_slips_past_a1(self):
        """
        A3 allein: Ohne A1 kaeme die Antwort `EXPIRED`/0 bis in die Strategie.
        Dann darf nichts gebucht und nichts gemeldet werden, und die
        Reconciliation im naechsten Zyklus verwirft den Eintrag.
        """
        grid = self.start_grid()
        self._trigger_grid_buy(grid)
        self.exchange.set_liquidity("order_market_buy", 0.0)
        with mock.patch.object(TradingClient, "_settle_market_response",
                               lambda self, pending, label, order: order):
            with self.assertRaises(ImplausibleLedgerEntry):
                grid.execute_once()
        self.assertEqual(grid._ledger._read(), [])
        self.assertEqual(self._tags("[GRID-KAUF]"), [])
        self.assertEqual(len(grid._client.pending_orders.all()), 1, "Eintrag bleibt stehen")

        # Kein neues Durchqueren - nur die Reconciliation soll laufen.
        grid._last_seen_price = self.exchange.price
        grid.execute_once()
        self.assertEqual(grid._client.pending_orders.all(), [], "Reconciliation raeumt auf")
        self.assertEqual(grid._ledger._read(), [])
        self.assert_ownership()

    # -- Trend --

    def test_trend_entry_without_fill_books_nothing_and_places_no_stop(self):
        trend = self.start_trend()
        self.exchange.set_liquidity("order_market_buy", 0.0)
        trend._open_position(self.PRICE)

        self.assertEqual(trend._ledger._read(), [])
        self.assertEqual(self.exchange.locked_by("trend"), 0.0)
        self.assertEqual(self._tags("[TREND-EINSTIEG]"), [])
        self.assertTrue(any("nicht verbucht" in m for m in self._tags("[TREND-FEHLER]")))
        self.assert_ownership()

    def test_trend_entry_partially_filled_is_protected_with_the_real_quantity(self):
        trend = self.start_trend()
        self.exchange.set_liquidity("order_market_buy", 0.6)  # ~9 USDT
        trend._open_position(self.PRICE)

        trade = trend._ledger.open_position()
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(trade["quantity"], self.exchange.net_base("trend"), places=9)
        self.assertIsNotNone(trade["stop_loss_order_id"])
        self.assertAlmostEqual(self.exchange.locked_by("trend"), trade["quantity"], places=9)
        self.assertTrue(any("Teilfüllung" in m for m in self._tags("[TREND-EINSTIEG]")))
        self.assert_ownership()

    def test_trend_entry_partially_filled_below_min_notional_is_closed_as_dust(self):
        trend = self.start_trend()
        self.exchange.set_liquidity("order_market_buy", 0.3)  # ~4,50
        trend._open_position(self.PRICE)

        self.assertIsNone(trend._ledger.open_position())
        [trade] = trend._ledger._read()
        self.assertEqual(trade["exit_reason"], "dust_on_entry")
        self.assertAlmostEqual(trade["dust_qty"], self.exchange.net_base("trend"), places=9)
        self.assertAlmostEqual(trade["realized_pnl"], -trade["quote_spent"], places=9)
        self.assertIsNone(trade["stop_loss_order_id"])
        self.assertEqual(self.exchange.locked_by("trend"), 0.0, "keine Stop-Order")
        self.assertFalse(trend._stop_loss.is_paused(), "keine Sperre")
        self.assertEqual(self._tags("[TREND-EINSTIEG]"), [])
        self.assertEqual(len(self._tags("[TREND-STAUB]")), 1)
        self.assert_ownership()

    def test_trend_dust_is_measured_at_the_stop_limit_price(self):
        """
        5,25 USDT gekauft: zum Einstiegspreis ueber dem Mindestvolumen, zum
        Limit-Preis der Stop-Order (Einstieg x 0,90 x 0,995) darunter - die
        Stop-Order wuerde abgelehnt, also Staub.
        """
        trend = self.start_trend()
        self.exchange.set_liquidity("order_market_buy", 0.35)
        trend._open_position(self.PRICE)
        [trade] = trend._ledger._read()
        self.assertAlmostEqual(trade["quantity"] * self.PRICE, 5.25, places=6)
        self.assertEqual(trade["exit_reason"], "dust_on_entry")
        self.assertEqual(self.exchange.locked_by("trend"), 0.0)
        self.assert_ownership()

    def test_trend_reconciled_partial_entry_below_min_notional_is_closed_as_dust(self):
        trend = self.start_trend()
        self.exchange.set_liquidity("order_market_buy", 0.3)
        self.exchange.inject("order_market_buy", "lost")
        self.exchange.lookup_down = True
        trend._open_position(self.PRICE)
        self.exchange.lookup_down = False
        trend.reconcile_pending_orders()

        [trade] = trend._ledger._read()
        self.assertEqual(trade["exit_reason"], "dust_on_entry")
        self.assertEqual(trend._client.pending_orders.all(), [])
        self.assertEqual(self.exchange.locked_by("trend"), 0.0)
        self.assert_ownership()

    # -- DCA --

    def test_dca_buy_without_fill_books_nothing(self):
        dca = self.start_dca()
        self.exchange.set_liquidity("order_market_buy", 0.0)
        dca.execute_once()
        self.assertEqual(dca._ledger._read(), [])
        self.assertEqual(self._tags("[KAUF]"), [])
        self.assertTrue(any("nicht verbucht" in m for m in self._tags("[FEHLER]")))
        self.assert_ownership()

    def test_dca_buy_partially_filled_is_booked_with_the_real_quantity(self):
        dca = self.start_dca()
        self.exchange.set_liquidity("order_market_buy", 0.5)
        dca.execute_once()
        [record] = dca._ledger._read()
        self.assertAlmostEqual(record["quantity"], self.exchange.net_base("dca"), places=9)
        self.assertLess(record["quote_spent"], 500.0)
        self.assertTrue(any("Teilfüllung" in m for m in self._tags("[KAUF]")))
        self.assert_ownership()


# ---------------------------------------------------------------------------
# Ende zu Ende: Verkauf
# ---------------------------------------------------------------------------


class UnfilledSellEndToEndTestCase(SharedAccountTestBase):
    PRICE = 75_000.0

    def _grid_with_position(self):
        grid = self.start_grid()
        level_price = grid._levels[3]
        self.exchange.price = round(level_price - 1.0, 2)
        grid._last_seen_price = level_price + 1.0
        grid.execute_once()
        [position] = grid._ledger.open_positions()
        return grid, position

    def test_grid_sell_without_fill_keeps_the_position_open(self):
        grid, position = self._grid_with_position()
        btc_before = self.exchange.net_base("grid")
        self.exchange.price = position["target_sell_price"] * 1.0001
        self.exchange.set_liquidity("order_market_sell", 0.0)
        grid.execute_once()

        [still_open] = grid._ledger.open_positions()
        self.assertEqual(still_open["id"], position["id"])
        self.assertEqual(still_open["quantity"], position["quantity"])
        self.assertEqual(self.exchange.net_base("grid"), btc_before)
        self.assertTrue(any(m.startswith("[GRID-VERKAUF-FEHLGESCHLAGEN]") for m in self.messages))
        self.assertEqual(grid._client.pending_orders.all(), [])
        self.assert_ownership()

        grid.execute_once()  # naechster Zyklus verkauft regulaer
        self.assertEqual(grid._ledger.open_positions(), [])
        self.assert_ownership()

    def test_grid_partial_sell_is_booked_with_the_executed_quantity(self):
        """Runde 1 buchte die volle Menge und meldete nur laut. Seit Runde 2
        bleibt die Position mit dem Rest offen - und die Eigentums-Invariante
        haelt (Details: tests/test_partial_sell_grid.py)."""
        grid, position = self._grid_with_position()
        self.exchange.price = position["target_sell_price"] * 1.0001
        self.exchange.set_liquidity("order_market_sell", 0.5)
        grid.execute_once()

        [still_open] = grid._ledger.open_positions()
        self.assertAlmostEqual(still_open["partial_exit_qty"], position["quantity"] / 2, places=12)
        self.assertFalse(any("TEILFUELLUNG-UNGEBUCHT" in m for m in self.messages))
        self.assert_ownership()

    def test_trend_sell_without_fill_keeps_the_position_and_restores_protection(self):
        trend = self.start_trend()
        trend._open_position(self.PRICE)
        trade = trend._ledger.open_position()
        self.exchange.set_liquidity("order_market_sell", 0.0)
        trend._close_position(trade, self.PRICE, "signal")

        still_open = trend._ledger.open_position()
        self.assertIsNotNone(still_open)
        self.assertEqual(still_open["quantity"], trade["quantity"])
        self.assertIsNotNone(still_open["stop_loss_order_id"], "neue Stop-Order")
        self.assertAlmostEqual(self.exchange.locked_by("trend"), trade["quantity"], places=9)
        self.assertFalse(trend._stop_loss.is_paused())
        self.assert_ownership()


if __name__ == "__main__":
    unittest.main()

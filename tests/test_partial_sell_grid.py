"""
Teilverkauf beim Grid-Bot (Runde 2, 19.10.2026, Vorbedingung 8).

Endet ein Market-Verkauf, nachdem er nur einen Teil ausgefuehrt hat (laut
Binance Spot API Enums mit Status EXPIRED), buchte der Grid-Bot bis Runde 2
trotzdem die volle Menge und meldete nur [GRID-TEILFUELLUNG-UNGEBUCHT]. Der
Rest lag danach ohne Ledger auf dem Konto. Seit Runde 2:

- Die ausgefuehrte Menge wird als Teilverkauf verbucht (partial_exit_*,
  idempotent ueber die orderId), die Position bleibt mit dem Rest offen und
  wird verkauft, solange das Ziel erreicht ist.
- Ein Rest unter dem Mindestvolumen schliesst die Position sofort
  (close_reason "dust_after_sell", realized_pnl = Erloes der Teile -
  quote_spent).
- Verkauf, Deckungspruefung, Bestandsabgleich und Startpruefung rechnen mit
  der offenen Menge (order_utils.open_quantity).
- Die Reconciliation bucht nach derselben Regel - und haelt einen bereits
  verbuchten Teilverkauf nicht fuer einen Doppelverkauf.

Die Ende-zu-Ende-Faelle laufen auf dem geteilten Konto aus
test_shared_account (echter TradingClient gegen FakeExchange mit
einstellbarer Liquiditaet) und pruefen jeweils die Eigentums-Invariante.
Jede neue Pruefung hat mindestens einen Test, der bei ihrer Mutation rot
wird (Mutationsprobe vom 19.10.2026, siehe trading-bot-projekt.md).

Ausfuehren mit:  python -m unittest tests.test_partial_sell_grid -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

from dca_bot import check_orders
from dca_bot.grid_risk import GridLedger, GridPosition
from dca_bot.order_utils import SymbolTradingRules, open_quantity, sold_fully
from dca_bot.pending_orders import KIND_MARKET, PendingOrder

from tests.test_shared_account import SYMBOL, SharedAccountTestBase

RULES = SymbolTradingRules(
    symbol="BTCUSDT", tick_size=0.01, step_size=0.00001, min_notional=5.0,
    base_asset="BTC", quote_asset="USDT", quote_precision=8,
)


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------


class BuildingBlocksTestCase(unittest.TestCase):
    def test_open_quantity(self):
        self.assertEqual(open_quantity({"quantity": 0.0002}), 0.0002, "Altbestand ohne Feld")
        self.assertEqual(open_quantity({"quantity": 0.0003, "partial_exit_qty": 0.00015}), 0.00015)
        self.assertEqual(open_quantity({"quantity": 0.0001, "partial_exit_qty": 0.0002}), 0.0)

    def test_sold_fully_decides_by_quantity_with_step_size_tolerance(self):
        self.assertTrue(sold_fully(0.0002, 0.0002, RULES))
        self.assertTrue(sold_fully(0.000205, 0.0002, RULES),
                        "Rest unter einer stepSize gilt als verkauft (D8)")
        # Genau eine stepSize offen: in Fliesskomma ist 0.0002 - 0.00019
        # knapp kleiner als 1e-05 - der Rest ist trotzdem verkaufbar.
        self.assertFalse(sold_fully(0.0002, 0.0001, RULES))
        self.assertFalse(sold_fully(0.0002, 0.00019, RULES), "eine ganze stepSize offen")
        self.assertTrue(sold_fully(0.0002, 0.0002, None), "ohne Regeln: Rest praktisch 0")
        self.assertFalse(sold_fully(0.0002, 0.000199, None))


class GridLedgerPartialExitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger = GridLedger(str(Path(self._tmp.name) / "grid.json"))
        self.position = GridPosition.new(
            level_index=3, buy_price=73_000.0, target_sell_price=74_100.0, quantity=0.0003,
            quote_spent=21.9, dry_run=False, client_order_id="grid-buy", symbol=SYMBOL,
        )
        self.ledger.record_buy(self.position)

    def test_new_positions_carry_the_fields(self):
        record = asdict(self.position)
        self.assertEqual(record["partial_exit_qty"], 0.0)
        self.assertEqual(record["partial_exit_quote"], 0.0)
        self.assertEqual(record["partial_exit_proceeds"], 0.0)
        self.assertEqual(record["partial_exit_order_ids"], [])

    def test_partial_exits_add_up_and_are_idempotent_per_order_id(self):
        self.assertTrue(self.ledger.record_partial_exit(self.position.id, "11", 0.0001, 7.4, 7.39))
        self.assertTrue(self.ledger.record_partial_exit(self.position.id, "12", 0.00005, 3.8, 3.79))
        self.assertFalse(self.ledger.record_partial_exit(self.position.id, "11", 0.0001, 7.4, 7.39))

        record = self.ledger.position_by_id(self.position.id)
        self.assertEqual(record["status"], "open")
        self.assertAlmostEqual(record["partial_exit_qty"], 0.00015, places=12)
        self.assertAlmostEqual(record["partial_exit_quote"], 11.2, places=9)
        self.assertAlmostEqual(record["partial_exit_proceeds"], 11.18, places=9)
        self.assertEqual(record["partial_exit_order_ids"], ["11", "12"])
        self.assertEqual(record["quantity"], 0.0003, "quantity bleibt die Kaufmenge")
        self.assertAlmostEqual(open_quantity(record), 0.00015, places=12)

    def test_partial_exit_on_a_closed_or_unknown_position_or_without_quantity_is_refused(self):
        for quantity in (0.0, -0.0001, float("nan"), "0.0001", True):
            with self.subTest(menge=quantity):
                with self.assertRaises(ValueError):
                    self.ledger.record_partial_exit(self.position.id, "13", quantity, 1.0, 1.0)
        with self.assertRaises(ValueError):
            self.ledger.record_partial_exit("gibt-es-nicht", "13", 0.0001, 7.4, 7.39)
        self.ledger.record_sell(self.position.id, 74_100.0, "2026-10-19T10:00:00+00:00", 0.3, "grid-s")
        with self.assertRaises(ValueError):
            self.ledger.record_partial_exit(self.position.id, "13", 0.0001, 7.4, 7.39)
        self.assertEqual(self.ledger.position_by_id(self.position.id)["partial_exit_order_ids"], [])

    def test_record_sell_writes_dust_fields_only_when_given(self):
        self.ledger.record_sell(self.position.id, 74_100.0, "2026-10-19T10:00:00+00:00", -3.0,
                                "grid-s", dust_qty=0.00006, close_reason="dust_after_sell")
        record = self.ledger.position_by_id(self.position.id)
        self.assertEqual(record["dust_qty"], 0.00006)
        self.assertEqual(record["close_reason"], "dust_after_sell")

        other = GridPosition.new(
            level_index=4, buy_price=74_000.0, target_sell_price=75_110.0, quantity=0.0002,
            quote_spent=14.8, dry_run=False, client_order_id="grid-buy-2", symbol=SYMBOL,
        )
        self.ledger.record_buy(other)
        self.ledger.record_sell(other.id, 75_110.0, "2026-10-19T10:00:00+00:00", 0.2, "grid-s2")
        record = self.ledger.position_by_id(other.id)
        self.assertEqual(record["dust_qty"], 0.0)
        self.assertIsNone(record["close_reason"])


class CheckOrdersPartialIdsTestCase(unittest.TestCase):
    """D5: check_orders findet einen verbuchten Teilverkauf ueber seine orderId."""

    def test_order_id_in_partial_exit_order_ids_counts_as_booked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "grid.json"
            path.write_text(json.dumps([
                {"id": "p1", "status": "open", "client_order_id": "grid-buy",
                 "partial_exit_order_ids": ["1234", 5678]},
            ]), encoding="utf-8")
            self.assertEqual(
                check_orders._find_in_ledger(path, "grid-sell-a", "1234"),
                ("partial_exit_order_ids", None),
            )
            self.assertEqual(
                check_orders._find_in_ledger(path, "grid-sell-b", "5678"),
                ("partial_exit_order_ids", None),
            )
            self.assertEqual(check_orders._find_in_ledger(path, "grid-sell-c", "9999"), (None, None))


# ---------------------------------------------------------------------------
# Ende zu Ende auf dem geteilten Konto
# ---------------------------------------------------------------------------


class GridPartialSellEndToEndTestCase(SharedAccountTestBase):
    PRICE = 75_000.0

    def setUp(self) -> None:
        super().setUp()
        # Verkaufsgebuehr in USDT, damit sich brutto und netto unterscheiden.
        self.exchange.fee_rate = 0.001

    def _grid_with_position(self, levels: tuple[int, ...] = (3,)):
        grid = self.start_grid()
        low = min(levels)
        high = max(levels)
        self.exchange.price = round(grid._levels[low] - 1.0, 2)
        grid._last_seen_price = grid._levels[high] + 1.0
        grid.execute_once()
        positions = grid._ledger.open_positions()
        self.assertEqual(sorted(p["level_index"] for p in positions), sorted(levels))
        return grid, sorted(positions, key=lambda p: p["level_index"])

    def _sell_fills(self, client_order_ids=None):
        return [f for f in self.exchange.fills_of("grid", "SELL")
                if client_order_ids is None or f["clientOrderId"] in client_order_ids]

    def test_partial_sell_then_remainder_closes_with_the_sum_of_both_parts(self):
        grid, [position] = self._grid_with_position()
        target = position["target_sell_price"]
        quantity = position["quantity"]

        self.exchange.price = round(target * 1.0001, 2)
        self.exchange.set_liquidity("order_market_sell", 0.5)
        grid.execute_once()

        [still_open] = grid._ledger.open_positions()
        self.assertEqual(still_open["id"], position["id"])
        self.assertEqual(still_open["quantity"], quantity, "quantity bleibt die Kaufmenge")
        self.assertAlmostEqual(still_open["partial_exit_qty"], quantity / 2, places=12)
        self.assertEqual(len(still_open["partial_exit_order_ids"]), 1)
        self.assertEqual(grid._client.pending_orders.all(), [], "Teil verbucht, Eintrag weg")
        self.assertTrue(any("[GRID-TEILVERKAUF]" in m for m in self.messages))
        self.assertFalse(any("TEILFUELLUNG-UNGEBUCHT" in m for m in self.messages))
        self.assert_ownership()

        # Rest zu einem anderen Kurs - der Verkaufspreis ist dann ein
        # gewichteter Durchschnitt, nicht der Preis des letzten Teils.
        self.exchange.price = round(target * 1.01, 2)
        grid.execute_once()

        self.assertEqual(grid._ledger.open_positions(), [])
        closed = grid._ledger.position_by_id(position["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertIsNone(closed["close_reason"])
        fills = self._sell_fills()
        self.assertEqual(len(fills), 2)
        self.assertAlmostEqual(sum(f["qty"] for f in fills), quantity, places=12)
        net = sum(f["quote"] - f["commission"] for f in fills)
        gross = sum(f["quote"] for f in fills)
        self.assertAlmostEqual(closed["realized_pnl"], net - closed["quote_spent"], places=7)
        self.assertAlmostEqual(closed["sell_price"], gross / quantity, places=6)
        self.assertNotAlmostEqual(closed["sell_price"], fills[-1]["price"], places=2)
        self.assertEqual(closed["sell_client_order_id"], fills[-1]["clientOrderId"])
        self.assertTrue(any(m.startswith("[GRID-VERKAUF]") and f"{quantity:.8f}" in m
                            for m in self.messages))
        self.assertFalse(any("DISKREPANZ" in m or "UNGEDECKT" in m for m in self.messages))
        self.assert_ownership()

    def test_remainder_below_min_notional_closes_the_position_as_dust(self):
        grid, [position] = self._grid_with_position()
        self.exchange.price = round(position["target_sell_price"] * 1.0001, 2)
        self.exchange.set_liquidity("order_market_sell", 0.7)  # Rest 0.00006, ~4,46 < 5
        grid.execute_once()

        self.assertEqual(grid._ledger.open_positions(), [], "Stufe ist wieder frei")
        closed = grid._ledger.position_by_id(position["id"])
        self.assertEqual(closed["close_reason"], "dust_after_sell")
        self.assertAlmostEqual(closed["dust_qty"], 0.00006, places=12)
        [fill] = self._sell_fills()
        self.assertAlmostEqual(closed["partial_exit_qty"], fill["qty"], places=12)
        self.assertAlmostEqual(
            closed["realized_pnl"], fill["quote"] - fill["commission"] - closed["quote_spent"], places=7
        )
        self.assertAlmostEqual(closed["sell_price"], fill["price"], places=6)
        self.assertTrue(any("[GRID-STAUB]" in m and "Teilverkauf" in m for m in self.messages))
        self.assertEqual(grid._client.pending_orders.all(), [])
        self.assert_ownership()

    def test_three_partial_sells_in_a_row(self):
        grid, [position] = self._grid_with_position()
        quantity = position["quantity"]
        self.exchange.price = round(position["target_sell_price"] * 1.0001, 2)
        self.exchange.set_liquidity("order_market_sell", 0.25, 0.5, 1.0)
        for _ in range(3):
            grid.execute_once()
            self.assert_ownership()

        closed = grid._ledger.position_by_id(position["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(len(closed["partial_exit_order_ids"]), 2)
        fills = self._sell_fills()
        self.assertEqual(len(fills), 3)
        self.assertAlmostEqual(sum(f["qty"] for f in fills), quantity, places=12)
        net = sum(f["quote"] - f["commission"] for f in fills)
        self.assertAlmostEqual(closed["realized_pnl"], net - closed["quote_spent"], places=7)

    def test_partial_sell_with_lost_response_is_booked_by_the_reconciliation(self):
        grid, [position] = self._grid_with_position()
        self.exchange.price = round(position["target_sell_price"] * 1.0001, 2)
        self.exchange.set_liquidity("order_market_sell", 0.5)
        self.exchange.inject("order_market_sell", "lost")
        self.exchange.lookup_down = True
        grid.execute_once()

        [pending] = grid._client.pending_orders.all()
        [still_open] = grid._ledger.open_positions()
        self.assertFalse(still_open.get("partial_exit_qty"), "Ausgang unklar - nichts gebucht")
        self.assert_ownership()

        self.exchange.lookup_down = False
        grid._reconcile_pending_at_runtime()
        [booked] = grid._ledger.open_positions()
        self.assertAlmostEqual(booked["partial_exit_qty"], position["quantity"] / 2, places=12)
        self.assertEqual(grid._client.pending_orders.all(), [])
        self.assert_ownership()

        # Derselbe Eintrag ein zweites Mal (Neustart zwischen Ledger-Eintrag
        # und Aufraeumen): nichts doppelt.
        order = self.exchange.get_order(SYMBOL, origClientOrderId=pending.client_order_id)
        grid._apply_reconciled_order(pending, order)
        [again] = grid._ledger.open_positions()
        self.assertAlmostEqual(again["partial_exit_qty"], booked["partial_exit_qty"], places=12)
        self.assertEqual(again["partial_exit_order_ids"], booked["partial_exit_order_ids"])

        grid.execute_once()  # der Rest
        self.assertEqual(grid._ledger.open_positions(), [])
        self.assert_ownership()

    def test_booked_partial_is_no_double_sale_after_the_position_closed(self):
        """A verkauft teilweise, B schliesst - ein spaeter nachgetragener A ist
        kein [GRID-DOPPELVERKAUF]."""
        grid, [position] = self._grid_with_position()
        self.exchange.price = round(position["target_sell_price"] * 1.0001, 2)
        self.exchange.set_liquidity("order_market_sell", 0.5)
        grid.execute_once()
        grid.execute_once()
        closed = grid._ledger.position_by_id(position["id"])
        self.assertEqual(closed["status"], "closed")

        [order_id_a] = closed["partial_exit_order_ids"]
        client_id_a = self.exchange.orders[int(order_id_a)]["clientOrderId"]
        self.assertNotEqual(client_id_a, closed["sell_client_order_id"])
        grid._client.pending_orders.add(PendingOrder.new(
            client_id_a, KIND_MARKET, SYMBOL, "SELL",
            {"position_id": position["id"], "price": self.exchange.price},
        ))
        before = list(self.messages)
        grid._reconcile_pending_at_runtime()

        self.assertEqual(grid._client.pending_orders.all(), [])
        new = self.messages[len(before):]
        self.assertFalse(any("DOPPELVERKAUF" in m for m in new), new)
        self.assertEqual(grid._ledger.position_by_id(position["id"]), closed)
        self.assert_ownership()

    def test_restart_before_the_dust_close_completes_it_via_the_reconciliation(self):
        """Neustart zwischen record_partial_exit und confirm_booked: Der Teil
        steht im Ledger, der Pending-Eintrag auch noch - der Staub-Rest wird
        beim Nachtragen geschlossen, nichts doppelt gebucht."""
        grid, [position] = self._grid_with_position()
        self.exchange.price = round(position["target_sell_price"] * 1.0001, 2)
        self.exchange.set_liquidity("order_market_sell", 0.7)
        with mock.patch.object(grid, "_report_partial_sell", side_effect=RuntimeError("Absturz")):
            with self.assertRaises(RuntimeError):
                grid.execute_once()
        self.assertEqual(len(grid._client.pending_orders.all()), 1)
        [still_open] = grid._ledger.open_positions()
        self.assertTrue(still_open["partial_exit_qty"] > 0)

        restarted = self.start_grid()
        restarted.reconcile_pending_orders()

        self.assertEqual(restarted._ledger.open_positions(), [])
        closed = restarted._ledger.position_by_id(position["id"])
        self.assertEqual(closed["close_reason"], "dust_after_sell")
        self.assertEqual(len(closed["partial_exit_order_ids"]), 1)
        self.assertEqual(restarted._client.pending_orders.all(), [])
        self.assert_ownership()

    def test_dust_remainder_left_open_is_closed_by_the_next_cycle(self):
        """Wurde der Staub-Rest nicht sofort geschlossen, holt der naechste
        Zyklus das nach, statt einen Verkauf zu versuchen, den die Boerse
        ablehnen muss."""
        grid, [position] = self._grid_with_position()
        self.exchange.price = round(position["target_sell_price"] * 1.0001, 2)
        self.exchange.set_liquidity("order_market_sell", 0.7)
        real_close = grid._close_rest_if_dust
        calls = []

        def skip_first(record, *args, **kwargs):
            # Der erste Aufruf MIT verbuchtem Teil ist der in _book_sell - ihn
            # auslassen, als waere der Prozess davor gestorben.
            if record.get("partial_exit_qty") and not calls:
                calls.append(record["id"])
                return False
            return real_close(record, *args, **kwargs)

        with mock.patch.object(grid, "_close_rest_if_dust", side_effect=skip_first):
            grid.execute_once()
            [still_open] = grid._ledger.open_positions()
            self.assertTrue(still_open["partial_exit_qty"] > 0)
            grid.execute_once()

        self.assertEqual(grid._ledger.open_positions(), [])
        self.assertEqual(
            grid._ledger.position_by_id(position["id"])["close_reason"], "dust_after_sell"
        )
        self.assertEqual(len(self._sell_fills()), 1, "kein Verkaufsversuch fuer den Staub")
        self.assertFalse(any("FEHLGESCHLAGEN" in m for m in self.messages))
        self.assert_ownership()

    def test_book_sell_refuses_an_order_without_fill_or_a_partial_without_order_id(self):
        """Nach A1 erreicht keine Order ohne Ausfuehrung _book_sell - falls doch,
        wird nichts gebucht. Ein Teilverkauf ohne orderId liesse sich nicht
        idempotent verbuchen und wird ebenfalls abgelehnt."""
        grid, [position] = self._grid_with_position()
        rules = grid._client.get_symbol_trading_rules(SYMBOL)
        # Die Meldung zeigt, welche Schicht greift: _book_sell selbst, nicht
        # erst die Mengenpruefung im Ledger (die hat einen eigenen Test).
        cases = (
            ({"orderId": 1, "clientOrderId": "grid-a", "status": "EXPIRED",
              "executedQty": "0.00000000", "cummulativeQuoteQty": "0.00000000"},
             "ohne ausgefuehrte Menge"),
            ({"clientOrderId": "grid-b", "status": "EXPIRED",
              "executedQty": "0.00010000", "cummulativeQuoteQty": "7.50000000"},
             "ohne orderId"),
        )
        for order, message in cases:
            with self.subTest(order=order["clientOrderId"]):
                with self.assertRaisesRegex(ValueError, message):
                    grid._book_sell(position, order, rules, 75_000.0)
                self.assertEqual(grid._ledger.position_by_id(position["id"]), position)

    def test_startup_check_uses_the_open_quantity(self):
        grid, [position] = self._grid_with_position()
        self.exchange.price = round(position["target_sell_price"] * 1.0001, 2)
        self.exchange.set_liquidity("order_market_sell", 0.5)
        grid.execute_once()
        # Kurs unter das Ziel: der Rest bleibt offen.
        self.exchange.price = round(position["buy_price"], 2)

        restarted = self.start_grid()
        before = len(self.messages)
        restarted.check_balance_on_startup()
        self.assertFalse(any("DISKREPANZ" in m for m in self.messages[before:]),
                         self.messages[before:])

    def test_cycle_counts_the_executed_not_the_ordered_quantity(self):
        self._assert_cycle_counts_executed(first_ratio=0.5)

    def test_cycle_counts_the_executed_quantity_also_when_the_rest_is_dust(self):
        self._assert_cycle_counts_executed(first_ratio=0.7)

    def _assert_cycle_counts_executed(self, first_ratio: float) -> None:
        """Erste Position teilweise verkauft (bei 0.7 mit Staub-Rest geschlossen),
        die zweite sieht in der Deckungspruefung genau die ausgefuehrte Menge."""
        grid, positions = self._grid_with_position((3, 4))
        self.exchange.price = round(max(p["target_sell_price"] for p in positions) * 1.0001, 2)
        self.exchange.set_liquidity("order_market_sell", first_ratio, 1.0)
        real_check = grid._sell_is_covered
        seen = []

        def record(record_, snapshot, sold_this_cycle, rules):
            seen.append(sold_this_cycle)
            return real_check(record_, snapshot, sold_this_cycle, rules)

        with mock.patch.object(grid, "_sell_is_covered", side_effect=record):
            grid.execute_once()

        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0], 0.0)
        first_fill = self._sell_fills()[0]
        self.assertAlmostEqual(seen[1], first_fill["qty"], places=12)
        self.assertLess(seen[1], positions[0]["quantity"], "nicht die bestellte Menge")
        first = grid._ledger.position_by_id(positions[0]["id"])
        self.assertAlmostEqual(first["partial_exit_qty"], first_fill["qty"], places=12)
        if first_ratio == 0.7:
            self.assertEqual(first["close_reason"], "dust_after_sell")
        self.assert_ownership()


if __name__ == "__main__":
    unittest.main()

"""
Teilverkauf beim Trend-Bot (Runde 2, 19.10.2026, Vorbedingung 8).

Endet ein eigener Market-Verkauf des Trend-Bots (Signal-Ausstieg oder
interner Stop-Loss), nachdem er nur einen Teil ausgefuehrt hat, buchte der
Bot bis Runde 2 trotzdem den ganzen Ausstieg und meldete nur
[TREND-TEILFUELLUNG-UNGEBUCHT]. Seit Runde 2:

- Der Teil wird ueber record_partial_exit verbucht, idempotent ueber die
  orderId. `partial_exit_from_stop` ist True bei Grund "stop_loss"
  (Entscheidung D2) und bleibt dann True.
- Die vor dem Verkauf stornierte Stop-Order wird fuer den Rest neu gesetzt;
  verkauft wird der Rest im naechsten Tageszyklus (D1). Wird die neue
  Stop-Order nicht platziert, kommt sofort "Rest ungeschuetzt" (Auflage D1).
- Ein Rest unter dem Mindestvolumen schliesst die Position als Staub, mit
  Grund und Sperre nach E8/D2.
- Grund stop_loss samt Sperre wird nur noch erzwungen, wenn ein Teil aus
  einem Stop-Loss-Ereignis stammt; Altbestand mit Teilmenge ohne das Feld
  gilt wie bisher als solcher.
- Reconciliation und Klaerung eines unklaren Verkaufs buchen nach derselben
  Regel und halten einen verbuchten Teil nicht fuer einen Doppelverkauf.
- Die Mengenregel aus K-A (_book_stop_fill) laeuft ueber
  order_utils.sold_fully: Ein Rest von genau einer stepSize galt dort wegen
  Fliesskomma als verkauft und blieb unverbucht.

Ende zu Ende auf dem geteilten Konto aus test_shared_account, jeweils mit
der Eigentums-Invariante. Mutationsprobe vom 19.10.2026, siehe
trading-bot-projekt.md.

Ausfuehren mit:  python -m unittest tests.test_partial_sell_trend -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dca_bot import order_utils, trend_risk
from dca_bot.pending_orders import KIND_MARKET, PendingOrder
from dca_bot.trend_risk import TrendLedger, TrendTrade, partial_from_stop

from tests.test_shared_account import SYMBOL, SharedAccountTestBase


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------


class PartialFromStopTestCase(unittest.TestCase):
    def test_rule(self):
        self.assertFalse(partial_from_stop({}))
        self.assertFalse(partial_from_stop({"partial_exit_qty": 0.0, "partial_exit_from_stop": True}))
        self.assertTrue(partial_from_stop({"partial_exit_qty": 0.0001}),
                        "Altbestand mit Teilmenge ohne Feld: wie bisher Stop-Loss")
        self.assertTrue(partial_from_stop({"partial_exit_qty": 0.0001, "partial_exit_from_stop": None}))
        self.assertTrue(partial_from_stop({"partial_exit_qty": 0.0001, "partial_exit_from_stop": True}))
        self.assertFalse(partial_from_stop({"partial_exit_qty": 0.0001, "partial_exit_from_stop": False}))

    def test_open_quantity_is_the_same_function(self):
        self.assertIs(trend_risk.open_quantity, order_utils.open_quantity)


class TrendLedgerPartialExitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "trend.json"
        self.ledger = TrendLedger(str(self.path))
        self.trade = TrendTrade.new(entry_price=50_000.0, quantity=0.0004, quote_spent=20.0,
                                    dry_run=False, client_order_id="trend-in", symbol=SYMBOL)
        self.ledger.record_entry(self.trade)
        self.ledger.set_stop_loss_order(self.trade.id, "900", 44_775.0)

    def _record(self):
        return self.ledger.trade_by_id(self.trade.id)

    def test_new_trades_have_no_flag(self):
        self.assertIsNone(self._record()["partial_exit_from_stop"])

    def test_market_partial_without_stop_loss_reason_is_not_from_stop(self):
        self.assertTrue(self.ledger.record_partial_exit(self.trade.id, "1", 0.0001, 5.0, 4.99, from_stop=False))
        record = self._record()
        self.assertIs(record["partial_exit_from_stop"], False)
        self.assertIsNone(record["stop_loss_order_id"], "Zuordnung geloest")
        self.assertFalse(self.ledger.record_partial_exit(self.trade.id, "1", 0.0001, 5.0, 4.99, from_stop=False))
        self.assertAlmostEqual(self._record()["partial_exit_qty"], 0.0001, places=12)

    def test_from_stop_is_sticky(self):
        self.ledger.record_partial_exit(self.trade.id, "1", 0.0001, 5.0, 4.99, from_stop=True)
        self.ledger.record_partial_exit(self.trade.id, "2", 0.0001, 5.0, 4.99, from_stop=False)
        self.assertIs(self._record()["partial_exit_from_stop"], True)

    def test_legacy_partial_without_flag_stays_from_stop(self):
        records = json.loads(self.path.read_text(encoding="utf-8"))
        records[0]["partial_exit_qty"] = 0.0001
        records[0].pop("partial_exit_from_stop")
        self.path.write_text(json.dumps(records), encoding="utf-8")
        self.ledger.record_partial_exit(self.trade.id, "2", 0.0001, 5.0, 4.99, from_stop=False)
        self.assertIs(self._record()["partial_exit_from_stop"], True)

    def test_old_name_books_a_stop_fill(self):
        self.assertTrue(self.ledger.record_partial_stop_fill(self.trade.id, "7", 0.0001, 4.5, 4.4))
        self.assertIs(self._record()["partial_exit_from_stop"], True)
        self.assertEqual(self._record()["partial_exit_order_ids"], ["7"])


# ---------------------------------------------------------------------------
# Ende zu Ende auf dem geteilten Konto
# ---------------------------------------------------------------------------


class TrendPartialSellEndToEndTestCase(SharedAccountTestBase):
    QTY = 0.0003  # 15 USDT bei 50.000

    def setUp(self) -> None:
        super().setUp()
        self.exchange.fee_rate = 0.001

    def _open(self, **overrides):
        trend = self.start_trend(**overrides)
        trend._open_position(self.PRICE)
        trade = trend._ledger.open_position()
        self.assertAlmostEqual(trade["quantity"], self.QTY, places=12)
        self.assertIsNotNone(trade["stop_loss_order_id"])
        return trend, trade

    def _sells(self):
        return self.exchange.fills_of("trend", "SELL")

    def _latch(self) -> dict | None:
        path = Path(self.trend_config().stop_loss_state_file)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def test_signal_exit_partial_protects_the_rest_and_sells_it_next_cycle(self):
        trend, trade = self._open()
        old_stop = trade["stop_loss_order_id"]
        self.exchange.set_liquidity("order_market_sell", 0.5)
        trend._close_position(trade, self.PRICE, "signal")

        still_open = trend._ledger.open_position()
        self.assertIsNotNone(still_open)
        self.assertAlmostEqual(still_open["partial_exit_qty"], self.QTY / 2, places=12)
        self.assertIs(still_open["partial_exit_from_stop"], False)
        self.assertIsNotNone(still_open["stop_loss_order_id"])
        self.assertNotEqual(still_open["stop_loss_order_id"], old_stop)
        self.assertAlmostEqual(self.exchange.locked_by("trend"), self.QTY / 2, places=12)
        self.assertEqual(trend._client.pending_orders.all(), [])
        self.assertFalse(trend._stop_loss.is_paused())
        self.assertTrue(any("[TREND-TEILVERKAUF]" in m for m in self.messages))
        self.assertFalse(any("TEILFUELLUNG-UNGEBUCHT" in m or "ungeschuetzt" in m
                             for m in self.messages))
        self.assert_ownership()

        self.exchange.price = 51_000.0
        trend._close_position(trend._ledger.open_position(), 51_000.0, "signal")

        closed = trend._ledger.trade_by_id(trade["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "signal")
        self.assertFalse(trend._stop_loss.is_paused())
        sells = self._sells()
        self.assertEqual(len(sells), 2)
        self.assertAlmostEqual(sum(f["qty"] for f in sells), self.QTY, places=12)
        net = sum(f["quote"] - f["commission"] for f in sells)
        self.assertAlmostEqual(closed["realized_pnl"], net - closed["quote_spent"], places=7)
        self.assertAlmostEqual(closed["exit_price"], sum(f["quote"] for f in sells) / self.QTY, places=6)
        self.assertEqual(self.exchange.locked_by("trend"), 0.0)
        self.assert_ownership()

    def test_rejected_stop_for_the_rest_is_reported_immediately(self):
        """Interner Stop-Loss: Kurs schon unter der Schwelle. Dass Binance die
        Stop-Order dann ablehnt, ist eine Annahme - hier eingespielt."""
        trend, trade = self._open()
        self.exchange.price = 44_000.0
        self.exchange.set_liquidity("order_market_sell", 0.5)
        with mock.patch.object(trend._client, "place_stop_loss_limit_sell", return_value=None):
            trend._close_position(trade, 44_000.0, "stop_loss")

        still_open = trend._ledger.open_position()
        self.assertAlmostEqual(still_open["partial_exit_qty"], self.QTY / 2, places=12)
        self.assertIs(still_open["partial_exit_from_stop"], True)
        self.assertIsNone(still_open["stop_loss_order_id"])
        self.assertEqual(still_open["unprotected_cycles"], 1)
        warnings = [m for m in self.messages if "Rest ungeschuetzt" in m]
        self.assertEqual(len(warnings), 1, self.messages)
        self.assertIn(f"{self.QTY / 2:.8f}", warnings[0])
        self.assertIn("44000.00", warnings[0])
        self.assertIsNone(self._latch(), "Sperre erst mit dem Abschluss des Rests")
        self.assert_ownership()

        # Naechster Tageszyklus, Kurs weiter unter der Schwelle: der Rest geht weg.
        trend.execute_once()
        closed = trend._ledger.trade_by_id(trade["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "stop_loss")
        latch = self._latch()
        self.assertIsNotNone(latch)
        self.assertAlmostEqual(latch["exit_price"], closed["exit_price"], places=6)
        self.assert_ownership()

    def test_stop_loss_partial_keeps_reason_and_latch_after_recovery(self):
        """D2: Erholt sich der Kurs bis zum Abschluss, bleibt es ein Stop-Loss."""
        trend, trade = self._open()
        self.exchange.price = 44_000.0
        self.exchange.set_liquidity("order_market_sell", 0.5)
        with mock.patch.object(trend._client, "place_stop_loss_limit_sell", return_value=None):
            trend._close_position(trade, 44_000.0, "stop_loss")

        self.exchange.price = 52_000.0
        trend._close_position(trend._ledger.open_position(), 52_000.0, "signal")
        closed = trend._ledger.trade_by_id(trade["id"])
        self.assertEqual(closed["exit_reason"], "stop_loss")
        self.assertTrue(trend._stop_loss.is_paused())
        self.assert_ownership()

    def test_partial_with_dust_rest_closes_with_the_reason_of_the_exit(self):
        for reason, price, paused in (("signal", 50_000.0, False), ("stop_loss", 44_000.0, True)):
            with self.subTest(grund=reason):
                self.setUp()
                trend, trade = self._open()
                self.exchange.price = price
                # 0.0003 x 0.8 rundet die Boerse auf 0.00023 ab - Rest 0.00007,
                # zum Limit-Preis ~3,13 und damit unter dem Mindestvolumen.
                self.exchange.set_liquidity("order_market_sell", 0.8)
                trend._close_position(trade, price, reason)

                closed = trend._ledger.trade_by_id(trade["id"])
                self.assertEqual(closed["status"], "closed")
                self.assertEqual(closed["exit_reason"], reason)
                [fill] = self._sells()
                self.assertAlmostEqual(closed["dust_qty"], self.QTY - fill["qty"], places=12)
                self.assertGreater(closed["dust_qty"], 0.0)
                self.assertEqual(trend._stop_loss.is_paused(), paused)
                self.assertEqual(self.exchange.locked_by("trend"), 0.0)
                self.assert_ownership()

    def test_signal_partial_with_dust_rest_leaves_no_latch_and_allows_a_new_entry(self):
        """E8: Ein Signal-Ausstieg mit Teilfuellung und Staub-Rest schliesst mit
        exit_reason "signal", schreibt KEINE Sperrdatei, und der naechste Zyklus
        mit Einstiegssignal steigt wieder ein. Gegenprobe Stop-Loss: Sperre,
        kein neuer Einstieg."""
        for reason, price, may_enter in (("signal", 50_000.0, True), ("stop_loss", 44_000.0, False)):
            with self.subTest(grund=reason):
                self.setUp()
                trend, trade = self._open()
                self.exchange.price = price
                self.exchange.set_liquidity("order_market_sell", 0.8)  # Rest ist Staub
                trend._close_position(trade, price, reason)

                closed = trend._ledger.trade_by_id(trade["id"])
                self.assertEqual(closed["status"], "closed")
                self.assertEqual(closed["exit_reason"], reason)
                self.assertGreater(closed["dust_qty"], 0.0)
                self.assertEqual(self._latch() is None, may_enter)

                self.exchange.price = 50_000.0
                with mock.patch.object(trend._signal_gen, "feed",
                                       return_value={"confirmed_direction": "up"}):
                    trend.execute_once()
                opened = trend._ledger.open_position()
                if may_enter:
                    self.assertIsNotNone(opened, "nach dem Signal-Ausstieg darf er wieder einsteigen")
                    self.assertNotEqual(opened["id"], trade["id"])
                    self.assertIsNotNone(opened["stop_loss_order_id"])
                else:
                    self.assertIsNone(opened, "nach dem Stop-Loss bleibt der Einstieg gesperrt")
                self.assert_ownership()

    def test_legacy_partial_without_flag_still_forces_stop_loss(self):
        trend, trade = self._open()
        stop_id = trade["stop_loss_order_id"]
        self.exchange.fill_stop(stop_id, 0.00015)
        self.exchange.expire(stop_id)
        rules = trend._client.get_symbol_trading_rules(SYMBOL)
        self.assertEqual(trend._book_stop_fill(trade, self.exchange.get_order(SYMBOL, orderId=stop_id),
                                               rules), "partial")
        path = Path(trend._config.state_file)
        records = json.loads(path.read_text(encoding="utf-8"))
        records[0].pop("partial_exit_from_stop")  # wie ein Eintrag von vor Runde 2
        path.write_text(json.dumps(records), encoding="utf-8")

        self.exchange.price = 52_000.0
        trend._close_position(trend._ledger.open_position(), 52_000.0, "signal")
        closed = trend._ledger.trade_by_id(trade["id"])
        self.assertEqual(closed["exit_reason"], "stop_loss")
        self.assertTrue(trend._stop_loss.is_paused())
        self.assert_ownership()

    def test_unclear_partial_sell_settled_by_recheck_protects_the_rest(self):
        trend, trade = self._open()
        self.exchange.set_liquidity("order_market_sell", 0.5)
        self.exchange.inject("order_market_sell", "lost")
        self.exchange.lookup_down = True

        def recheck(_seconds):
            self.exchange.lookup_down = False

        with mock.patch("dca_bot.trend_strategy._sleep", recheck):
            trend._close_position(trade, self.PRICE, "signal")

        still_open = trend._ledger.open_position()
        self.assertAlmostEqual(still_open["partial_exit_qty"], self.QTY / 2, places=12)
        self.assertIsNotNone(still_open["stop_loss_order_id"])
        self.assertAlmostEqual(self.exchange.locked_by("trend"), self.QTY / 2, places=12)
        self.assertEqual(trend._client.pending_orders.all(), [])
        self.assertFalse(any("VERKAUF-FEHLGESCHLAGEN" in m for m in self.messages))
        self.assert_ownership()

    def test_partial_sell_booked_by_the_reconciliation_once(self):
        trend, trade = self._open()
        self.exchange.set_liquidity("order_market_sell", 0.5)
        self.exchange.inject("order_market_sell", "lost")
        self.exchange.lookup_down = True
        trend._close_position(trade, self.PRICE, "signal")  # bleibt unklar

        [pending] = trend._client.pending_orders.all()
        self.assertFalse(trend._ledger.open_position().get("partial_exit_qty"))
        self.assert_ownership()

        self.exchange.lookup_down = False
        trend._reconcile_pending_at_runtime()
        booked = trend._ledger.open_position()
        self.assertAlmostEqual(booked["partial_exit_qty"], self.QTY / 2, places=12)
        self.assertIsNotNone(booked["stop_loss_order_id"], "Rest sofort wieder abgesichert")
        self.assertEqual(trend._client.pending_orders.all(), [])
        self.assert_ownership()

        order = self.exchange.get_order(SYMBOL, origClientOrderId=pending.client_order_id)
        trend._apply_reconciled_order(pending, order)
        again = trend._ledger.open_position()
        self.assertAlmostEqual(again["partial_exit_qty"], booked["partial_exit_qty"], places=12)
        self.assertEqual(again["stop_loss_order_id"], booked["stop_loss_order_id"])
        self.assert_ownership()

    def test_no_second_stop_for_the_rest_while_a_stop_order_is_unclear(self):
        """W-B auch fuer den Rest nach einem nachgetragenen Teil: Steht noch eine
        Stop-Order mit ungeklaertem Ausgang in der Pending-Datei, wird keine
        zweite platziert - die Meldung sagt "ungeklaert" statt "abgelehnt"."""
        trend, trade = self._open()
        self.exchange.set_liquidity("order_market_sell", 0.5)
        self.exchange.inject("order_market_sell", "lost")
        self.exchange.lookup_down = True
        trend._close_position(trade, self.PRICE, "signal")  # Verkauf bleibt unklar
        trend._client.pending_orders.add(PendingOrder.new(
            "trend-unklarer-stop", "stop_loss_limit", SYMBOL, "SELL",
            {"trade_id": trade["id"], "limit_price": 44_775.0},
        ))

        self.exchange.lookup_down = False
        trend._reconcile_pending_at_runtime()

        booked = trend._ledger.open_position()
        self.assertAlmostEqual(booked["partial_exit_qty"], self.QTY / 2, places=12)
        self.assertIsNone(booked["stop_loss_order_id"])
        self.assertEqual(self.exchange.locked_by("trend"), 0.0, "keine zweite Stop-Order")
        warnings = [m for m in self.messages if "Rest ungeschuetzt" in m]
        self.assertEqual(len(warnings), 1)
        self.assertIn("trend-unklarer-stop", warnings[0])
        self.assertIn("ungeklaert", warnings[0])

    def test_booked_partial_is_no_double_sale_after_the_trade_closed(self):
        trend, trade = self._open()
        self.exchange.set_liquidity("order_market_sell", 0.5)
        trend._close_position(trade, self.PRICE, "signal")
        trend._close_position(trend._ledger.open_position(), self.PRICE, "signal")
        closed = trend._ledger.trade_by_id(trade["id"])
        self.assertEqual(closed["status"], "closed")

        [order_id_a] = closed["partial_exit_order_ids"]
        client_id_a = self.exchange.orders[int(order_id_a)]["clientOrderId"]
        trend._client.pending_orders.add(PendingOrder.new(
            client_id_a, KIND_MARKET, SYMBOL, "SELL",
            {"trade_id": trade["id"], "reason": "signal", "price": self.PRICE},
        ))
        before = len(self.messages)
        trend._reconcile_pending_at_runtime()

        self.assertEqual(trend._client.pending_orders.all(), [])
        self.assertFalse(any("DOPPELVERKAUF" in m for m in self.messages[before:]))
        self.assertEqual(trend._ledger.trade_by_id(trade["id"]), closed)
        self.assert_ownership()

    def test_restart_before_confirm_protects_the_rest_via_the_reconciliation(self):
        """Neustart zwischen record_partial_exit und confirm_booked: Der Teil ist
        verbucht, der Pending-Eintrag steht noch, die Absicherung fehlt - die
        Reconciliation bucht nichts doppelt und setzt die Stop-Order fuer den Rest."""
        trend, trade = self._open()
        self.exchange.set_liquidity("order_market_sell", 0.5)
        real_confirm = trend._client.confirm_booked

        def crash_on_market_sell(client_order_id):
            if client_order_id and client_order_id.startswith("trend-") and any(
                o["clientOrderId"] == client_order_id and o["type"] == "MARKET"
                and o["side"] == "SELL" for o in self.exchange.orders.values()
            ):
                raise RuntimeError("Absturz")
            real_confirm(client_order_id)

        with mock.patch.object(trend._client, "confirm_booked", side_effect=crash_on_market_sell):
            with self.assertRaises(RuntimeError):
                trend._close_position(trade, self.PRICE, "signal")
        self.assertEqual(len(trend._client.pending_orders.all()), 1)
        self.assertIsNone(trend._ledger.open_position()["stop_loss_order_id"])

        restarted = self.start_trend()
        restarted.reconcile_pending_orders()

        booked = restarted._ledger.open_position()
        self.assertAlmostEqual(booked["partial_exit_qty"], self.QTY / 2, places=12)
        self.assertEqual(len(booked["partial_exit_order_ids"]), 1)
        self.assertIsNotNone(booked["stop_loss_order_id"])
        self.assertEqual(restarted._client.pending_orders.all(), [])
        self.assertAlmostEqual(self.exchange.locked_by("trend"), self.QTY / 2, places=12)
        self.assert_ownership()

    def test_dust_rest_found_by_the_protection_check_closes_with_signal_after_a_signal_partial(self):
        """Ist der Rest nach einem Signal-Teil zum Limit-Preis Staub und ohne
        Stop-Order (etwa nach einem Absturz), schliesst _ensure_stop_loss_protection
        ihn mit Grund signal und ohne Sperre (E8). Nur Ledger-Ebene, keine Boerse."""
        trend, trade = self._open()
        trend._client.cancel_order(SYMBOL, trade["stop_loss_order_id"])
        trend._ledger.set_stop_loss_order(trade["id"], None, None)
        trend._ledger.record_partial_exit(trade["id"], "55", 0.00023, 11.5, 11.49, from_stop=False)

        trend._ensure_stop_loss_protection(trend._ledger.open_position())

        closed = trend._ledger.trade_by_id(trade["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "signal")
        self.assertFalse(trend._stop_loss.is_paused())

    def test_partial_without_order_id_is_refused(self):
        """Ohne orderId liesse sich ein Teilverkauf nicht idempotent verbuchen."""
        trend, trade = self._open()
        rules = trend._client.get_symbol_trading_rules(SYMBOL)
        order = {"clientOrderId": "trend-x", "status": "EXPIRED",
                 "executedQty": "0.00015000", "cummulativeQuoteQty": "7.50000000"}
        before = trend._ledger.trade_by_id(trade["id"])
        with self.assertRaisesRegex(ValueError, "ohne orderId"):
            trend._book_market_partial(dict(trade), order, rules, "signal", self.PRICE)
        self.assertEqual(trend._ledger.trade_by_id(trade["id"]), before)

    def test_stop_fill_leaving_exactly_one_step_is_booked(self):
        """K-A-Mengenregel ueber sold_fully: 0.0003 - 0.00029 ist in Fliesskomma
        kleiner als 1e-05. Bisher galt die Stop-Order damit als ganz gefuellt,
        der Rest von einer stepSize blieb unverbucht auf dem Konto."""
        trend, trade = self._open()
        stop_id = trade["stop_loss_order_id"]
        self.exchange.fill_stop(stop_id, 0.00029)
        self.exchange.expire(stop_id)
        self.exchange.price = 46_000.0

        restarted = self.start_trend()
        restarted.reconcile_on_startup()

        closed = restarted._ledger.trade_by_id(trade["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertAlmostEqual(closed["partial_exit_qty"], 0.00029, places=12)
        self.assertAlmostEqual(closed["dust_qty"], 0.00001, places=12)
        self.assertEqual(closed["exit_reason"], "stop_loss")
        self.assert_ownership()


if __name__ == "__main__":
    unittest.main()

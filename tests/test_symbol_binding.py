"""
Tests fuer die Bindung der Zustandsdateien an ein Handelspaar
(Symbolbindung vom 28.09.2026, siehe trading-bot-projekt.md 6g).

Hintergrund: Binance hat im EWR alle USDT-Spot-Paare entfernt, fuer echtes
Geld wird BTCEUR gehandelt. Fuer einen frischen Start reicht dafuer die
Konfiguration. Gefaehrlich war der Versehens-Fall "neues Symbol auf altem
Ledger": Grid- und Trend-Ledger, der Allocator-Zustand und die Pending-
Sperre wussten nicht, zu welchem Paar sie gehoeren.

Diese Datei prueft die Formatseite: Jeder NEUE Eintrag traegt sein Paar,
und Pending-Eintraege eines anderen Paars sperren nichts. Die
Startpruefung selbst steht in tests/test_symbol_guard.py.

Kein Netzwerk, keine Zugangsdaten, temporaere Dateien.

Ausfuehren mit:  python -m unittest tests.test_symbol_binding -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dca_bot import allocator as allocator_module
from dca_bot.allocator import Allocator
from dca_bot.allocator_config import AllocatorConfig
from dca_bot.grid_config import GridConfig
from dca_bot.grid_strategy import GridTradingStrategy
from dca_bot.pending_orders import KIND_MARKET, PendingOrder, PendingOrderStore
from dca_bot.trend_config import TrendConfig
from dca_bot.trend_strategy import TrendFollowingStrategy

from tests.test_grid_sell_safety import FakeGridClient
from tests.test_order_reconciliation import (
    FakeReconcileClient,
    ReconciliationTestBase,
    filled_order,
)
from tests.test_trend_stop_loss import FakeTradingClient

# Bewusst NICHT das Symbol, das die Fakes und Tests sonst ueberall
# verwenden: Nur so ist unterscheidbar, ob ein Eintrag das Symbol aus der
# Konfiguration bekommt oder ein fest eingetragenes "BTCUSDT".
CONFIGURED = "BTCEUR"
OTHER = "BTCUSDT"


class _TmpDir(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _path(self, name: str) -> str:
        return str(self.tmp / name)


class EntriesForSymbolTestCase(_TmpDir):
    """Der Filter in PendingOrderStore.entries_for()."""

    def _store(self) -> PendingOrderStore:
        store = PendingOrderStore(self._path("pending.json"), "grid")
        for cid, symbol in (("grid-a", OTHER), ("grid-b", CONFIGURED)):
            store.add(PendingOrder.new(cid, KIND_MARKET, symbol, "BUY", {"level_index": 3}))
        return store

    def test_symbol_filter_returns_only_entries_of_that_pair(self):
        entries = self._store().entries_for(side="BUY", symbol=CONFIGURED, level_index=3)
        self.assertEqual([e.client_order_id for e in entries], ["grid-b"])

    def test_without_symbol_nothing_is_filtered(self):
        """Rueckwaertskompatibel: ohne `symbol` verhaelt sich die Methode wie bisher."""
        entries = self._store().entries_for(side="BUY", level_index=3)
        self.assertEqual([e.client_order_id for e in entries], ["grid-a", "grid-b"])


class GridSymbolTestCase(_TmpDir):
    def _strategy(self, trading_enabled: bool = True):
        config = GridConfig(
            api_key="test",
            api_secret="test",
            symbol=CONFIGURED,
            lower_limit=70_000.0,
            upper_limit=90_000.0,
            grid_spacing_pct=1.5,
            amount_per_level=15.0,
            trading_enabled=trading_enabled,
            kill_switch_file=self._path("STOP_GRID_UNUSED"),
            state_file=self._path("grid_positions.json"),
            stop_loss_state_file=self._path("grid_stop_loss.json"),
        )
        client = FakeGridClient(trading_enabled, 77_000.0)
        return GridTradingStrategy(config, client), client

    def _cross_level(self, strategy, client, level_index: int = 3) -> None:
        level_price = strategy._levels[level_index]
        client.price = level_price
        strategy._last_seen_price = level_price * 1.0001
        strategy._process_buys(level_price)

    def test_real_buy_carries_the_configured_symbol(self):
        strategy, client = self._strategy(trading_enabled=True)
        self._cross_level(strategy, client)
        (position,) = strategy._ledger.open_positions()
        self.assertEqual(position["symbol"], CONFIGURED)

    def test_dry_run_buy_carries_the_configured_symbol(self):
        strategy, client = self._strategy(trading_enabled=False)
        self._cross_level(strategy, client)
        (position,) = strategy._ledger.open_positions()
        self.assertEqual(position["symbol"], CONFIGURED)

    def test_unclear_buy_of_another_pair_does_not_occupy_the_level(self):
        """
        Eine alte BTCUSDT-Kaufstufe 3 ist nicht die Stufe 3 dieses Grids.
        Ohne den Symbolfilter gaelte sie als belegt und wuerde nie gekauft.
        """
        strategy, client = self._strategy()
        client.pending_orders.add(
            PendingOrder.new("grid-alt", KIND_MARKET, OTHER, "BUY", {"level_index": 3})
        )
        self._cross_level(strategy, client)
        self.assertEqual(len(strategy._ledger.open_positions()), 1)

    def _open_position_above_target(self, strategy, client) -> dict:
        self._cross_level(strategy, client)
        (position,) = strategy._ledger.open_positions()
        client.price = position["target_sell_price"] * 1.001
        return position

    def test_unclear_sell_of_another_pair_does_not_block_the_sale(self):
        strategy, client = self._strategy()
        position = self._open_position_above_target(strategy, client)
        client.pending_orders.add(
            PendingOrder.new("grid-alt", KIND_MARKET, OTHER, "SELL", {"position_id": position["id"]})
        )
        strategy._process_sells(client.price)
        self.assertEqual(len(client.market_sell_calls), 1)

    def test_unclear_sell_of_the_same_pair_still_blocks_the_sale(self):
        strategy, client = self._strategy()
        position = self._open_position_above_target(strategy, client)
        client.pending_orders.add(
            PendingOrder.new("grid-offen", KIND_MARKET, CONFIGURED, "SELL", {"position_id": position["id"]})
        )
        with self.assertLogs("grid_bot", level="WARNING"):
            strategy._process_sells(client.price)
        self.assertEqual(client.market_sell_calls, [])

    def test_failed_sell_report_ignores_unclear_orders_of_another_pair(self):
        """
        Die Fehlschlag-Meldung sagt, ob der naechste Zyklus es erneut
        versucht. Ein Eintrag eines anderen Paars macht den Ausgang dieses
        Verkaufs nicht unklar.
        """
        strategy, client = self._strategy()
        position = self._open_position_above_target(strategy, client)
        client.pending_orders.add(
            PendingOrder.new("grid-alt", KIND_MARKET, OTHER, "SELL", {"position_id": position["id"]})
        )
        client.force_market_sell_failure = True
        with mock.patch("dca_bot.grid_strategy.send_notification"), \
                self.assertLogs("grid_bot", level="WARNING") as captured:
            # Der Verkaufsversuch selbst laeuft durch _process_sells; der
            # Eintrag des anderen Paars sperrt ihn nicht (siehe oben).
            strategy._process_sells(client.price)
        self.assertTrue(any("versucht es erneut" in line for line in captured.output), captured.output)

    def test_unclear_buy_of_the_same_pair_still_occupies_the_level(self):
        """Gegenprobe: dieselbe Lage mit passendem Symbol sperrt die Stufe wie bisher (K-B)."""
        strategy, client = self._strategy()
        client.pending_orders.add(
            PendingOrder.new("grid-offen", KIND_MARKET, CONFIGURED, "BUY", {"level_index": 3})
        )
        self._cross_level(strategy, client)
        self.assertEqual(strategy._ledger.open_positions(), [])


class TrendSymbolTestCase(_TmpDir):
    def _strategy(self, trading_enabled: bool = True):
        config = TrendConfig(
            api_key="test",
            api_secret="test",
            symbol=CONFIGURED,
            trading_enabled=trading_enabled,
            kill_switch_file=self._path("STOP_TREND_UNUSED"),
            state_file=self._path("trend_ledger.json"),
            stop_loss_state_file=self._path("trend_stop_loss.json"),
        )
        client = FakeTradingClient(trading_enabled, 50_000.0)
        strategy = TrendFollowingStrategy(config, client)
        strategy._seeded = True
        return strategy, client

    def test_real_entry_carries_the_configured_symbol(self):
        strategy, _ = self._strategy(trading_enabled=True)
        strategy._open_position(50_000.0)
        self.assertEqual(strategy._ledger.open_position()["symbol"], CONFIGURED)

    def test_dry_run_entry_carries_the_configured_symbol(self):
        strategy, _ = self._strategy(trading_enabled=False)
        strategy._open_position(50_000.0)
        self.assertEqual(strategy._ledger.open_position()["symbol"], CONFIGURED)

    def test_unclear_sell_of_another_pair_does_not_block_this_trade(self):
        strategy, client = self._strategy()
        strategy._open_position(50_000.0)
        trade = strategy._ledger.open_position()
        client.pending_orders.add(
            PendingOrder.new("trend-alt", KIND_MARKET, OTHER, "SELL", {"trade_id": trade["id"]})
        )
        self.assertEqual(strategy._pending_sells(trade), [])

    def test_unclear_sell_of_the_same_pair_still_blocks(self):
        strategy, client = self._strategy()
        strategy._open_position(50_000.0)
        trade = strategy._ledger.open_position()
        client.pending_orders.add(
            PendingOrder.new("trend-offen", KIND_MARKET, CONFIGURED, "SELL", {"trade_id": trade["id"]})
        )
        self.assertEqual(
            [p.client_order_id for p in strategy._pending_sells(trade)], ["trend-offen"]
        )

    def test_unclear_buy_of_another_pair_does_not_block_an_entry(self):
        """Die Einstiegssperre aus K-B filtert ebenfalls nach Symbol."""
        strategy, client = self._strategy()
        client.pending_orders.add(PendingOrder.new("trend-alt", KIND_MARKET, OTHER, "BUY", {}))
        with mock.patch("dca_bot.trend_strategy.decide_action", return_value="ENTER"):
            strategy.execute_once()
        self.assertIsNotNone(strategy._ledger.open_position())

    def test_unclear_buy_of_the_same_pair_still_blocks_an_entry(self):
        strategy, client = self._strategy()
        client.pending_orders.add(PendingOrder.new("trend-offen", KIND_MARKET, CONFIGURED, "BUY", {}))
        client.failing_lookups.add("trend-offen")
        with mock.patch("dca_bot.trend_strategy.decide_action", return_value="ENTER"), \
                mock.patch("dca_bot.pending_orders.send_notification"), \
                self.assertLogs("trend_bot", level="WARNING"):
            strategy.execute_once()
        self.assertIsNone(strategy._ledger.open_position())


class ReconciledEntrySymbolTestCase(ReconciliationTestBase):
    """Nachgetragene Kaeufe tragen das Symbol ihres Pending-Eintrags."""

    def test_reconciled_grid_buy_carries_the_pending_symbol(self):
        config = GridConfig(
            api_key="test", api_secret="test", symbol="BTCUSDT",
            lower_limit=70_000.0, upper_limit=90_000.0, grid_spacing_pct=1.5,
            amount_per_level=15.0, trading_enabled=True,
            kill_switch_file=str(self.tmp_path / "STOP_GRID_UNUSED"),
            state_file=str(self.tmp_path / "grid_positions.json"),
            stop_loss_state_file=str(self.tmp_path / "grid_stop_loss.json"),
            pending_orders_file=self.pending_file, bot_name="grid",
        )
        client = FakeReconcileClient(self.pending_file, "grid")
        strategy = GridTradingStrategy(config, client)
        self._add_pending(
            "grid-lost", context={"level_index": 3, "price": 74_000.0, "amount": 15.0},
            bot_name="grid",
        )
        client.lookups["grid-lost"] = ("found", filled_order(executed_qty=0.0002, cumulative_quote=14.8))

        with self.assertLogs("grid_bot", level="WARNING"):
            strategy.reconcile_pending_orders()

        (position,) = strategy._ledger.open_positions()
        self.assertEqual(position["symbol"], "BTCUSDT")

    def test_reconciled_trend_entry_carries_the_pending_symbol(self):
        config = TrendConfig(
            api_key="test", api_secret="test", symbol="BTCUSDT", trading_enabled=True,
            kill_switch_file=str(self.tmp_path / "STOP_TREND_UNUSED"),
            state_file=str(self.tmp_path / "trend_ledger.json"),
            stop_loss_state_file=str(self.tmp_path / "trend_stop_loss.json"),
            pending_orders_file=self.pending_file, bot_name="trend",
        )
        client = FakeReconcileClient(self.pending_file, "trend")
        strategy = TrendFollowingStrategy(config, client)
        self._add_pending(
            "trend-lost", context={"price": 50_000.0, "amount": 15.0}, bot_name="trend"
        )
        client.lookups["trend-lost"] = ("found", filled_order(executed_qty=0.0003, cumulative_quote=15.0))

        with self.assertLogs("trend_bot", level="WARNING"):
            strategy.reconcile_pending_orders()

        self.assertEqual(strategy._ledger.open_position()["symbol"], "BTCUSDT")


class AllocatorStateSymbolTestCase(_TmpDir):
    def _fetch(self, symbol, interval, start, end):
        out, day = [], date.fromisoformat(start)
        while day <= date.fromisoformat(end):
            stamp = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            out.append({"open_time": int(stamp.timestamp() * 1000), "close_price": 70_000.0,
                        "low_price": 0.0})
            day += timedelta(days=1)
        return out

    def test_state_file_names_its_pair(self):
        path = self.tmp / "allocator_state.json"
        allocator = Allocator(
            AllocatorConfig(api_key="k", api_secret="s", symbol=CONFIGURED, state_file=str(path))
        )
        with mock.patch.object(allocator_module, "fetch_historical_klines", self._fetch), \
                mock.patch.object(allocator_module, "send_notification", lambda m: None), \
                self.assertLogs("allocator", level="INFO"):
            allocator.execute_once()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["symbol"], CONFIGURED)


if __name__ == "__main__":
    unittest.main()

"""
Tests fuer die Startpruefung der Symbolbindung (28.09.2026), den Bericht
ohne Start (`python -m dca_bot.symbol_guard --report`), die Pruefung von
ALLOCATOR_SYMBOL gegen DCA_SYMBOL/TREND_SYMBOL (E4) und den Laufzeit-
Rueckfall bei einer Zuteilung fuer ein anderes Paar (E3).

Aufbau je Zustand: ein Fall mit fremdem Paar (Start verweigert), eine
Gegenprobe mit passendem Paar (Start laeuft). Ohne die Gegenprobe waere
"verweigert" auch gruen, wenn die Pruefung alles verweigerte.

Kein Netzwerk, keine Zugangsdaten, temporaere Dateien.

Ausfuehren mit:  python -m unittest tests.test_symbol_guard -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from dca_bot import main as dca_main
from dca_bot import main_allocator, main_grid, main_trend, symbol_guard
from dca_bot.allocator import Allocator
from dca_bot.allocator_config import AllocatorConfig, load_allocator_config
from dca_bot.allocator_signals import STALE_ALLOCATION_FALLBACK, read_allocation_fraction
from dca_bot.config import Config, load_config
from dca_bot.config_guard import ConfigError
from dca_bot.grid_config import GridConfig, load_grid_config
from dca_bot.grid_risk import GridPosition
from dca_bot.grid_strategy import GridTradingStrategy
from dca_bot.pending_orders import KIND_MARKET, PendingOrder, PendingOrderStore
from dca_bot.risk import TradeRecord
from dca_bot.strategy import DCAStrategy
from dca_bot.symbol_guard import SymbolMismatch
from dca_bot.trend_config import TrendConfig, load_trend_config
from dca_bot.trend_risk import TrendTrade
from dca_bot.trend_strategy import TrendFollowingStrategy

from tests.test_order_reconciliation import FakeReconcileClient
from tests.test_stage_c_safety import EnvTestCase

NEW = "BTCEUR"
OLD = "BTCUSDT"


def _fresh_allocator_state(symbol: str | None) -> dict:
    state = {
        "trend_fraction": 0.4,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "interval_minutes": 60,
    }
    if symbol is not None:
        state["symbol"] = symbol
    return state


class _BotFiles(unittest.TestCase):
    """Temporaere Zustandsdateien plus je eine Fabrik pro Bot."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        for target in ("dca_bot.strategy", "dca_bot.grid_strategy", "dca_bot.trend_strategy",
                       "dca_bot.allocator"):
            patcher = mock.patch(f"{target}.send_notification")
            setattr(self, "notify_" + target.split(".")[1], patcher.start())
            self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def p(self, name: str) -> str:
        return str(self.tmp / name)

    # -- Fabriken ----------------------------------------------------------

    def dca(self, symbol: str = NEW, allocator_file: str = ""):
        config = Config(
            api_key="t", api_secret="t", symbol=symbol, trading_enabled=True,
            kill_switch_file=self.p("STOP"), state_file=self.p("trade_ledger.json"),
            stop_loss_state_file=self.p("stop_loss_paused.json"),
            pending_orders_file=self.p("pending_dca.json"), bot_name="dca",
            allocator_state_file=allocator_file,
        )
        return DCAStrategy(config, FakeReconcileClient(config.pending_orders_file, "dca"))

    def grid(self, symbol: str = NEW):
        config = GridConfig(
            api_key="t", api_secret="t", symbol=symbol, lower_limit=70_000.0,
            upper_limit=90_000.0, grid_spacing_pct=1.5, amount_per_level=15.0,
            trading_enabled=True, kill_switch_file=self.p("STOP_GRID"),
            state_file=self.p("grid_positions.json"),
            stop_loss_state_file=self.p("grid_stop_loss_paused.json"),
            pending_orders_file=self.p("pending_grid.json"), bot_name="grid",
        )
        return GridTradingStrategy(config, FakeReconcileClient(config.pending_orders_file, "grid"))

    def trend(self, symbol: str = NEW, allocator_file: str = ""):
        config = TrendConfig(
            api_key="t", api_secret="t", symbol=symbol, trading_enabled=True,
            kill_switch_file=self.p("STOP_TREND"), state_file=self.p("trend_ledger.json"),
            stop_loss_state_file=self.p("trend_stop_loss_paused.json"),
            pending_orders_file=self.p("pending_trend.json"), bot_name="trend",
            allocator_state_file=allocator_file,
        )
        return TrendFollowingStrategy(config, FakeReconcileClient(config.pending_orders_file, "trend"))

    def allocator(self, symbol: str = NEW):
        return Allocator(AllocatorConfig(api_key="t", api_secret="t", symbol=symbol,
                                         state_file=self.p("allocator_state.json")))

    # -- Zustaende anlegen ------------------------------------------------

    def write_json(self, name: str, content) -> str:
        path = self.tmp / name
        path.write_text(json.dumps(content), encoding="utf-8")
        return str(path)

    def add_pending(self, file: str, bot: str, symbol: str) -> None:
        PendingOrderStore(self.p(file), bot).add(
            PendingOrder.new(f"{bot}-offen", KIND_MARKET, symbol, "BUY", {"level_index": 3})
        )

    def verify(self, bot, logger_name: str):
        """Fuehrt die Startpruefung aus; gibt die Log-Zeilen zurueck (oder wirft)."""
        with self.assertLogs(logger_name, level="INFO") as captured:
            bot.verify_symbol_binding()
        return captured.output

    def assertRefused(self, bot, logger_name: str, *fragments: str) -> SymbolMismatch:
        with self.assertRaises(SymbolMismatch) as ctx:
            with self.assertLogs(logger_name, level="INFO"):
                bot.verify_symbol_binding()
        for fragment in fragments:
            self.assertIn(fragment, str(ctx.exception))
        self.assertIn(symbol_guard.REPORT_COMMAND, str(ctx.exception))
        return ctx.exception


class DcaStartCheckTestCase(_BotFiles):
    def _buy(self, symbol: str) -> None:
        self.dca()._ledger.record(TradeRecord(
            timestamp=datetime.now(timezone.utc).isoformat(), symbol=symbol, quote_spent=15.0,
            quantity=0.0002, price=75_000.0, dry_run=False,
        ))

    def test_buys_of_another_pair_refuse_the_start(self):
        """
        Der DCA-Fall aus dem Audit: Kaeufe eines anderen Paars wurden still
        ignoriert (risk.py filtert nach Symbol). Jetzt faellt das auf.
        """
        self._buy(OLD)
        self.assertRefused(self.dca(NEW), "dca_bot", "DCA_SYMBOL=BTCEUR", "DCA-Ledger",
                           "1 Eintrag BTCUSDT", "trade_ledger.json")

    def test_buys_of_the_same_pair_start_normally(self):
        self._buy(NEW)
        self.verify(self.dca(NEW), "dca_bot")

    def test_a_mixed_ledger_refuses_the_start(self):
        """Entscheidung E5: ein gemischtes Ledger startet nicht - auch wenn ein Teil passt."""
        self._buy(NEW)
        self._buy(OLD)
        self.assertRefused(self.dca(NEW), "dca_bot", "1 Eintrag BTCEUR", "1 Eintrag BTCUSDT")

    def test_foreign_pending_entry_refuses_the_start(self):
        self.add_pending("pending_dca.json", "dca", OLD)
        self.assertRefused(self.dca(NEW), "dca_bot", "Pending-Datei", "--symbol")

    def test_foreign_latch_refuses_the_start(self):
        self.write_json("stop_loss_paused.json", {"symbol": OLD, "triggered_at": "x"})
        self.assertRefused(self.dca(NEW), "dca_bot", "Stop-Loss-Sperre", "reset_stop_loss")

    def test_foreign_allocator_state_refuses_the_start_with_opt_in(self):
        path = self.write_json("allocator_state.json", _fresh_allocator_state(OLD))
        self.assertRefused(self.dca(NEW, allocator_file=path), "dca_bot", "Allocator-Zustand",
                           "ALLOCATOR_SYMBOL")

    def test_allocator_state_is_ignored_without_opt_in(self):
        """Ohne Opt-in liest der DCA-Bot die Zuteilung nicht - dann ist sie auch kein Befund."""
        self.write_json("allocator_state.json", _fresh_allocator_state(OLD))
        self.verify(self.dca(NEW), "dca_bot")


class GridStartCheckTestCase(_BotFiles):
    def _position(self, symbol: str | None) -> None:
        position = GridPosition.new(level_index=3, buy_price=74_000.0, target_sell_price=75_110.0,
                                    quantity=0.0002, quote_spent=14.8, dry_run=False,
                                    symbol=symbol)
        self.grid()._ledger.record_buy(position)

    def test_positions_of_another_pair_refuse_the_start(self):
        self._position(OLD)
        self.assertRefused(self.grid(NEW), "grid_bot", "GRID_SYMBOL=BTCEUR", "Grid-Ledger")

    def test_legacy_positions_count_as_btcusdt(self):
        """
        Altbestand ohne Feld (die Homeserver-Ledger) gilt als BTCUSDT -
        stellt jemand GRID_SYMBOL um, ohne das Ledger zu archivieren,
        startet der Bot nicht.
        """
        self._position(None)
        self.assertRefused(self.grid(NEW), "grid_bot", "ohne Feld, gelten als BTCUSDT")

    def test_legacy_positions_start_normally_with_btcusdt(self):
        """Gegenprobe: derselbe Altbestand mit BTCUSDT - der laufende Betrieb der Server."""
        self._position(None)
        self.verify(self.grid(OLD), "grid_bot")

    def test_positions_of_the_same_pair_start_normally(self):
        self._position(NEW)
        self.verify(self.grid(NEW), "grid_bot")

    def test_foreign_pending_entry_refuses_the_start(self):
        self.add_pending("pending_grid.json", "grid", OLD)
        self.assertRefused(self.grid(NEW), "grid_bot", "Pending-Datei")

    def test_pending_entry_of_the_same_pair_starts_normally(self):
        self.add_pending("pending_grid.json", "grid", NEW)
        self.verify(self.grid(NEW), "grid_bot")

    def test_foreign_latch_refuses_the_start(self):
        self.write_json("grid_stop_loss_paused.json", {"symbol": OLD})
        self.assertRefused(self.grid(NEW), "grid_bot", "Stop-Loss-Sperre", "reset_grid_stop_loss")

    def test_latch_of_the_same_pair_starts_normally(self):
        self.write_json("grid_stop_loss_paused.json", {"symbol": NEW})
        self.verify(self.grid(NEW), "grid_bot")

    def test_unreadable_latch_only_warns_once(self):
        """
        Entscheidung E2: Die Sperrdatei wird bewusst nicht atomar
        geschrieben. Ein unlesbarer Inhalt ergibt eine Warnung (Log und
        einmal Telegram), keinen Abbruch - die Sperre blockiert weiter
        Kaeufe, das ist die harmlose Richtung.
        """
        (self.tmp / "grid_stop_loss_paused.json").write_text('{"symbol": "BTC', encoding="utf-8")
        lines = self.verify(self.grid(NEW), "grid_bot")
        self.assertTrue(
            any(line.startswith("WARNING") and "Sperre aktiv, Inhalt" in line for line in lines),
            lines,
        )
        self.assertEqual(self.notify_grid_strategy.call_count, 1)
        self.assertIn("[SYMBOL-WARNUNG]", self.notify_grid_strategy.call_args.args[0])

    def test_legacy_latch_without_field_counts_as_btcusdt(self):
        self.write_json("grid_stop_loss_paused.json", {"triggered_at": "x"})
        self.assertRefused(self.grid(NEW), "grid_bot", "Stop-Loss-Sperre")


class TrendStartCheckTestCase(_BotFiles):
    def _trade(self, symbol: str | None, dry_run: bool = False) -> None:
        self.trend()._ledger.record_entry(TrendTrade.new(
            entry_price=50_000.0, quantity=0.0003, quote_spent=15.0, dry_run=dry_run,
            symbol=symbol,
        ))

    def test_trade_of_another_pair_refuses_the_start(self):
        self._trade(OLD)
        self.assertRefused(self.trend(NEW), "trend_bot", "TREND_SYMBOL=BTCEUR", "Trend-Ledger")

    def test_the_open_dry_run_position_of_15_09_refuses_a_pair_switch(self):
        """
        Der konkrete Homeserver-Fall (6h): eine offene Dry-Run-Position ohne
        Feld. Mit BTCEUR wuerde sie sonst mit einem Scheinverlust (EUR-Kurs
        gegen USDT-Einstieg) simuliert geschlossen und die Sperre gesetzt.
        """
        self._trade(None, dry_run=True)
        self.assertRefused(self.trend(NEW), "trend_bot", "gelten als BTCUSDT")

    def test_trade_of_the_same_pair_starts_normally(self):
        self._trade(NEW)
        self.verify(self.trend(NEW), "trend_bot")

    def test_foreign_pending_entry_refuses_the_start(self):
        self.add_pending("pending_trend.json", "trend", OLD)
        self.assertRefused(self.trend(NEW), "trend_bot", "Pending-Datei")

    def test_foreign_latch_refuses_the_start(self):
        self.write_json("trend_stop_loss_paused.json", {"symbol": OLD})
        self.assertRefused(self.trend(NEW), "trend_bot", "reset_trend_stop_loss")

    def test_foreign_allocator_state_refuses_the_start_with_opt_in(self):
        path = self.write_json("allocator_state.json", _fresh_allocator_state(OLD))
        self.assertRefused(self.trend(NEW, allocator_file=path), "trend_bot", "Allocator-Zustand")

    def test_legacy_allocator_state_counts_as_btcusdt(self):
        path = self.write_json("allocator_state.json", _fresh_allocator_state(None))
        self.assertRefused(self.trend(NEW, allocator_file=path), "trend_bot", "(ohne Feld)")
        self.verify(self.trend(OLD, allocator_file=path), "trend_bot")

    def test_unreadable_allocator_state_only_warns(self):
        """Zur Laufzeit gilt dort ohnehin der Rueckfall auf 100 % DCA."""
        (self.tmp / "allocator_state.json").write_text("{kaputt", encoding="utf-8")
        self.verify(self.trend(NEW, allocator_file=self.p("allocator_state.json")), "trend_bot")
        self.assertEqual(self.notify_trend_strategy.call_count, 1)


class AllocatorStartCheckTestCase(_BotFiles):
    def test_own_state_of_another_pair_refuses_the_start(self):
        self.write_json("allocator_state.json", _fresh_allocator_state(OLD))
        self.assertRefused(self.allocator(NEW), "allocator", "ALLOCATOR_SYMBOL=BTCEUR",
                           "archivieren")

    def test_own_state_of_the_same_pair_starts_normally(self):
        self.write_json("allocator_state.json", _fresh_allocator_state(NEW))
        self.verify(self.allocator(NEW), "allocator")

    def test_legacy_state_starts_normally_with_btcusdt(self):
        """Der Homeserver-Zustand von heute: kein Feld, ALLOCATOR_SYMBOL nicht gesetzt."""
        self.write_json("allocator_state.json", _fresh_allocator_state(None))
        self.verify(self.allocator(OLD), "allocator")


# --- Einbau in die vier main() ----------------------------------------------


class _MainWiringMixin:
    """
    Die echte main() jedes Bots, ersetzt ist nur die Aussenwelt - gleiche
    Technik wie tests/test_heartbeat_status_file.py. Die Pruefung wirft;
    main() muss regulaer zurueckkehren (Exit-Code 0), ohne einen Zyklus,
    ohne Reconciliation, mit [SYMBOL-KONFLIKT] per Telegram.
    """

    module = None
    config_loader_name = ""
    strategy_class_name = ""
    logger_name = ""

    def make_config(self, tmp: Path):
        raise NotImplementedError

    def test_a_symbol_conflict_ends_main_regularly_before_anything_else(self):
        module = self.module
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            config = self.make_config(Path(tmp))
            strategy_cls = stack.enter_context(mock.patch.object(module, self.strategy_class_name))
            strategy = strategy_cls.return_value
            strategy.verify_symbol_binding.side_effect = SymbolMismatch(
                "Testbot", "X_SYMBOL", NEW, []
            )
            notify = stack.enter_context(mock.patch.object(module, "send_notification"))
            for name, kwargs in (
                (self.config_loader_name, {"return_value": config}),
                ("setup_logging", {}), ("ProcessLock", {}), ("init_notifier", {}),
                ("announce_trading_mode", {}), ("TradingClient", {}), ("KillSwitch", {}),
                ("Heartbeat", {}),
            ):
                stack.enter_context(mock.patch.object(module, name, **kwargs))
            reconcile = (
                stack.enter_context(mock.patch.object(module, "safe_startup_reconciliation"))
                if hasattr(module, "safe_startup_reconciliation") else None
            )
            stack.enter_context(self.assertLogs(self.logger_name, level="ERROR"))

            result = module.main()

        self.assertIsNone(result)
        strategy.verify_symbol_binding.assert_called_once()
        strategy.execute_once.assert_not_called()
        if reconcile is not None:
            reconcile.assert_not_called()
        self.assertTrue(any("[SYMBOL-KONFLIKT]" in c.args[0] for c in notify.call_args_list))


class DcaMainWiringTestCase(_MainWiringMixin, unittest.TestCase):
    module = dca_main
    config_loader_name = "load_config"
    strategy_class_name = "DCAStrategy"
    logger_name = "dca_bot"

    def make_config(self, tmp: Path) -> Config:
        return Config(api_key="t", api_secret="t", log_file=str(tmp / "dca.log"),
                      state_file=str(tmp / "l.json"), lock_file=str(tmp / "l.lock"))


class GridMainWiringTestCase(_MainWiringMixin, unittest.TestCase):
    module = main_grid
    config_loader_name = "load_grid_config"
    strategy_class_name = "GridTradingStrategy"
    logger_name = "grid_bot"

    def make_config(self, tmp: Path) -> GridConfig:
        return GridConfig(api_key="t", api_secret="t", log_file=str(tmp / "grid.log"),
                          state_file=str(tmp / "l.json"), lock_file=str(tmp / "l.lock"))


class TrendMainWiringTestCase(_MainWiringMixin, unittest.TestCase):
    module = main_trend
    config_loader_name = "load_trend_config"
    strategy_class_name = "TrendFollowingStrategy"
    logger_name = "trend_bot"

    def make_config(self, tmp: Path) -> TrendConfig:
        return TrendConfig(api_key="t", api_secret="t", log_file=str(tmp / "trend.log"),
                           state_file=str(tmp / "l.json"), lock_file=str(tmp / "l.lock"))


class AllocatorMainWiringTestCase(_MainWiringMixin, unittest.TestCase):
    module = main_allocator
    config_loader_name = "load_allocator_config"
    strategy_class_name = "Allocator"
    logger_name = "allocator"

    def make_config(self, tmp: Path) -> AllocatorConfig:
        return AllocatorConfig(api_key="t", api_secret="t", log_file=str(tmp / "a.log"),
                               state_file=str(tmp / "a.json"), lock_file=str(tmp / "a.lock"))


class StartOrderTestCase(unittest.TestCase):
    """
    Die Pruefung steht VOR der Reconciliation: die wuerde sonst Order-Fragen
    des alten Paars ins Ledger nachtragen. Gelesen wird der Quelltext von
    main(), gleiche Technik wie StartupWiringTestCase.
    """

    def test_the_check_runs_before_the_reconciliation(self):
        import inspect

        for module in (dca_main, main_grid, main_trend):
            with self.subTest(modul=module.__name__):
                source = inspect.getsource(module.main)
                self.assertLess(source.index("verify_state_readable"),
                                source.index("verify_symbol_binding"))
                self.assertLess(source.index("verify_symbol_binding"),
                                source.index("safe_startup_reconciliation("))

    def test_the_allocator_checks_before_its_loop(self):
        import inspect

        source = inspect.getsource(main_allocator.main)
        self.assertLess(source.index("verify_symbol_binding"), source.index("while True"))


# --- E4: ALLOCATOR_SYMBOL passt zu DCA_SYMBOL und TREND_SYMBOL -----------


class AllocatorSymbolConfigTestCase(EnvTestCase):
    def test_allocator_refuses_a_pair_that_dca_and_trend_do_not_trade(self):
        os.environ["ALLOCATOR_SYMBOL"] = NEW
        with self.assertRaises(ConfigError) as ctx:
            load_allocator_config()
        self.assertIn("DCA_SYMBOL=BTCUSDT", str(ctx.exception))
        self.assertIn("TREND_SYMBOL=BTCUSDT", str(ctx.exception))

    def test_allocator_loads_when_all_three_agree(self):
        for var in ("ALLOCATOR_SYMBOL", "DCA_SYMBOL", "TREND_SYMBOL"):
            os.environ[var] = NEW
        self.assertEqual(load_allocator_config().symbol, NEW)

    def test_allocator_checks_even_without_opt_in(self):
        """Der Allocator prueft immer gegen beide (E4) - auch ohne gesetztes Opt-in."""
        os.environ["ALLOCATOR_SYMBOL"] = NEW
        os.environ["DCA_SYMBOL"] = NEW
        with self.assertRaises(ConfigError):
            load_allocator_config()

    def test_dca_with_opt_in_refuses_a_different_allocator_pair(self):
        """Fehlt ALLOCATOR_SYMBOL, gilt der Default BTCUSDT - er muss beim Umstellen mit."""
        os.environ["DCA_SYMBOL"] = NEW
        os.environ["DCA_ALLOCATOR_STATE_FILE"] = "data/allocator_state.json"
        with self.assertRaises(ConfigError) as ctx:
            load_config()
        self.assertIn("ALLOCATOR_SYMBOL=BTCUSDT", str(ctx.exception))

    def test_dca_with_opt_in_loads_when_the_pairs_agree(self):
        os.environ["DCA_SYMBOL"] = NEW
        os.environ["ALLOCATOR_SYMBOL"] = NEW
        os.environ["DCA_ALLOCATOR_STATE_FILE"] = "data/allocator_state.json"
        self.assertEqual(load_config().symbol, NEW)

    def test_dca_without_opt_in_does_not_care_about_the_allocator(self):
        os.environ["DCA_SYMBOL"] = NEW
        self.assertEqual(load_config().symbol, NEW)

    def test_trend_with_opt_in_refuses_a_different_allocator_pair(self):
        os.environ["TREND_SYMBOL"] = NEW
        os.environ["TREND_ALLOCATOR_STATE_FILE"] = "data/allocator_state.json"
        with self.assertRaises(ConfigError):
            load_trend_config()

    def test_trend_without_opt_in_does_not_care_about_the_allocator(self):
        os.environ["TREND_SYMBOL"] = NEW
        self.assertEqual(load_trend_config().symbol, NEW)

    def test_grid_is_independent_of_the_allocator(self):
        os.environ["GRID_SYMBOL"] = NEW
        self.assertEqual(load_grid_config().symbol, NEW)


# --- E3: Laufzeit-Rueckfall --------------------------------------------------


class AllocationSymbolAtRuntimeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "allocator_state.json"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _read(self, state_symbol, expected):
        self.path.write_text(json.dumps(_fresh_allocator_state(state_symbol)), encoding="utf-8")
        return read_allocation_fraction(str(self.path), expected)

    def test_allocation_for_another_pair_falls_back_with_a_warning(self):
        with self.assertLogs("dca_bot", level="WARNING") as captured:
            self.assertEqual(self._read(OLD, NEW), STALE_ALLOCATION_FALLBACK)
        self.assertTrue(any("BTCUSDT" in line and "BTCEUR" in line for line in captured.output))

    def test_allocation_for_the_same_pair_is_used(self):
        self.assertAlmostEqual(self._read(NEW, NEW), 0.4)

    def test_legacy_state_counts_as_btcusdt(self):
        self.assertAlmostEqual(self._read(None, OLD), 0.4)
        with self.assertLogs("dca_bot", level="WARNING"):
            self.assertEqual(self._read(None, NEW), STALE_ALLOCATION_FALLBACK)

    def test_without_expected_symbol_nothing_changes(self):
        """Rueckwaertskompatibel: ein Aufruf ohne Symbol verhaelt sich wie bisher."""
        self.assertAlmostEqual(self._read(OLD, None), 0.4)

    def test_both_consumers_pass_their_symbol(self):
        """
        Die Verdrahtung: ein Trend-Bot auf BTCEUR mit einer BTCUSDT-Zuteilung
        steigt nicht ein (Rueckfall 0 % Trend), statt mit 40 % einzusteigen.
        """
        self.path.write_text(json.dumps(_fresh_allocator_state(OLD)), encoding="utf-8")
        from tests.test_trend_stop_loss import FakeTradingClient

        config = TrendConfig(
            api_key="t", api_secret="t", symbol=NEW, trading_enabled=True,
            kill_switch_file=str(self.path.parent / "STOP"),
            state_file=str(self.path.parent / "trend.json"),
            stop_loss_state_file=str(self.path.parent / "sl.json"),
            allocator_state_file=str(self.path),
        )
        client = FakeTradingClient(True, 50_000.0)
        strategy = TrendFollowingStrategy(config, client)
        with self.assertLogs("dca_bot", level="WARNING"), self.assertLogs("trend_bot", level="INFO"):
            strategy._open_position(50_000.0)
        self.assertEqual(client.market_buy_calls, [])

    def test_the_dca_consumer_passes_its_symbol(self):
        self.path.write_text(json.dumps(_fresh_allocator_state(OLD)), encoding="utf-8")
        tmp = self.path.parent
        config = Config(
            api_key="t", api_secret="t", symbol=NEW, trading_enabled=False, quote_amount=15.0,
            kill_switch_file=str(tmp / "STOP"), state_file=str(tmp / "dca.json"),
            stop_loss_state_file=str(tmp / "sl.json"), pending_orders_file=str(tmp / "p.json"),
            allocator_state_file=str(self.path),
        )
        from tests.test_dca_fee_adjustment import FakeDCAClient

        client = FakeDCAClient(trading_enabled=False, price=75_000.0)
        strategy = DCAStrategy(config, client)
        with self.assertLogs("dca_bot", level="WARNING") as captured, \
                mock.patch("dca_bot.strategy.send_notification"):
            strategy.execute_once()
        # Rueckfall 0.0 heisst 100 % DCA: voller Betrag statt 60 %.
        self.assertAlmostEqual(client.market_buy_calls[0][1], 15.0)
        self.assertTrue(any("gerechnet" in line for line in captured.output))


# --- Der Bericht ohne Start -------------------------------------------------


_MANAGED = ("DCA_", "GRID_", "TREND_", "ALLOCATOR_")


class ReportTestCase(unittest.TestCase):
    """
    `python -m dca_bot.symbol_guard --report`: dieselbe Pruefung wie beim
    Start, gegen die echten Dateien, nur lesend.
    """

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self._saved = dict(os.environ)
        for name in list(os.environ):
            if name.startswith(_MANAGED):
                del os.environ[name]
        d = self.tmp / "data"
        d.mkdir()
        self.files = {
            "DCA_BOT_STATE_FILE": d / "trade_ledger.json",
            "DCA_PENDING_ORDERS_FILE": d / "pending_orders_dca.json",
            "DCA_BOT_STOP_LOSS_STATE_FILE": d / "stop_loss_paused.json",
            "GRID_STATE_FILE": d / "grid_positions.json",
            # Liegt in einem Verzeichnis, das es nicht gibt - der Bericht
            # darf es nicht anlegen (PendingOrderStore wuerde das tun).
            "GRID_PENDING_ORDERS_FILE": self.tmp / "gibt-es-nicht" / "pending_orders_grid.json",
            "GRID_STOP_LOSS_STATE_FILE": d / "grid_stop_loss_paused.json",
            "TREND_STATE_FILE": d / "trend_ledger.json",
            "TREND_PENDING_ORDERS_FILE": d / "pending_orders_trend.json",
            "TREND_STOP_LOSS_STATE_FILE": d / "trend_stop_loss_paused.json",
            "ALLOCATOR_STATE_FILE": d / "allocator_state.json",
        }
        for var, path in self.files.items():
            os.environ[var] = str(path)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved)
        self._tmpdir.cleanup()

    def write(self, var: str, content) -> None:
        self.files[var].write_text(json.dumps(content), encoding="utf-8")

    def run_report(self) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = symbol_guard.main(["--report"])
        return code, out.getvalue()

    def _homeserver_like(self) -> None:
        """Ein Datenstand wie auf den Servern: Altbestand ohne Feld, BTCUSDT."""
        self.write("DCA_BOT_STATE_FILE", [{"symbol": OLD, "quantity": 0.1, "dry_run": False}])
        self.write("GRID_STATE_FILE", [{"id": "a", "status": "open", "dry_run": False}])
        self.write("TREND_STATE_FILE", [{"id": "t", "status": "open", "dry_run": True}])
        self.write("ALLOCATOR_STATE_FILE", _fresh_allocator_state(None))
        self.write("TREND_STOP_LOSS_STATE_FILE", {"symbol": OLD})

    def _snapshot(self) -> dict:
        return {
            str(p.relative_to(self.tmp)): (p.stat().st_mtime_ns, p.read_bytes())
            for p in sorted(self.tmp.rglob("*"))
            if p.is_file()
        } | {"dirs": tuple(sorted(str(p) for p in self.tmp.rglob("*") if p.is_dir()))}

    def test_the_report_writes_nothing(self):
        """
        Die zentrale Zusage: nur lesend. Zwei Ebenen: (1) jeder
        Schreibversuch wuerde scheitern (open im Schreibmodus, replace,
        mkdir, ...); (2) der Verzeichnisbaum ist hinterher byte- und
        zeitgenau derselbe, und das fehlende Verzeichnis gibt es weiterhin
        nicht.
        """
        self._homeserver_like()
        os.environ["GRID_SYMBOL"] = NEW  # auch ein Befund darf nichts schreiben
        (self.tmp / "data" / "grid_stop_loss_paused.json").write_text("{kaputt", encoding="utf-8")
        before = self._snapshot()

        real_open = io.open

        def read_only_open(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                raise AssertionError(f"Schreibzugriff im Bericht: {file} ({mode})")
            return real_open(file, mode, *args, **kwargs)

        def forbidden(*args, **kwargs):
            raise AssertionError(f"Schreibender Aufruf im Bericht: {args}")

        with mock.patch("builtins.open", read_only_open), mock.patch("io.open", read_only_open), \
                mock.patch("os.replace", forbidden), mock.patch("os.rename", forbidden), \
                mock.patch("os.mkdir", forbidden), mock.patch("os.makedirs", forbidden), \
                mock.patch("os.remove", forbidden), mock.patch("os.unlink", forbidden), \
                mock.patch("pathlib.Path.mkdir", forbidden), \
                mock.patch("pathlib.Path.write_text", forbidden), \
                mock.patch("pathlib.Path.write_bytes", forbidden), \
                mock.patch("pathlib.Path.touch", forbidden):
            code, out = self.run_report()

        self.assertEqual(self._snapshot(), before)
        self.assertFalse((self.tmp / "gibt-es-nicht").exists())
        self.assertEqual(code, 1)
        self.assertIn("Grid-Bot", out)

    def test_the_servers_data_as_of_today_would_start(self):
        """Der Stand der Server mit unveraenderter .env: jeder Bot wuerde starten."""
        self._homeserver_like()
        code, out = self.run_report()
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("-> Start: wuerde starten"), 4, out)
        self.assertIn("gelten als BTCUSDT", out)

    def test_a_pair_switch_on_old_data_is_reported_per_bot(self):
        """Dieselben Daten nach Umstellung aller vier *_SYMBOL: niemand wuerde starten."""
        self._homeserver_like()
        for var in ("DCA_SYMBOL", "GRID_SYMBOL", "TREND_SYMBOL", "ALLOCATOR_SYMBOL"):
            os.environ[var] = NEW
        code, out = self.run_report()
        self.assertEqual(code, 1)
        self.assertEqual(out.count("-> Start: wuerde NICHT starten"), 4, out)
        self.assertIn("FREMDES PAAR", out)
        self.assertIn("Loesung:", out)

    def test_an_allocator_pair_conflict_is_reported(self):
        os.environ["ALLOCATOR_SYMBOL"] = NEW
        code, out = self.run_report()
        self.assertEqual(code, 1)
        self.assertIn("ALLOCATOR_SYMBOL=BTCEUR passt nicht", out)

    def test_an_unreadable_latch_is_a_warning_in_the_report_too(self):
        (self.tmp / "data" / "grid_stop_loss_paused.json").write_text("{kaputt", encoding="utf-8")
        code, out = self.run_report()
        self.assertEqual(code, 0, out)
        self.assertIn("mit Warnung", out)

    def test_an_unreadable_ledger_is_reported_as_blocking(self):
        """So sieht es auch der Bot: LedgerUnreadable verhindert den Start."""
        (self.tmp / "data" / "grid_positions.json").write_text("[kaputt", encoding="utf-8")
        code, out = self.run_report()
        self.assertEqual(code, 1)
        self.assertIn("LedgerUnreadable", out)

    def test_the_report_and_the_start_check_agree(self):
        """
        Gleiche Dateien, gleiches Urteil: Was der Bericht fuer den Grid-Bot
        meldet, entscheidet auch der echte Start. Geprueft in beide
        Richtungen, damit die beiden Wege nicht auseinanderlaufen.
        """
        for grid_symbol, should_start in ((OLD, True), (NEW, False)):
            with self.subTest(GRID_SYMBOL=grid_symbol):
                self._homeserver_like()
                os.environ["GRID_SYMBOL"] = grid_symbol
                _, out = self.run_report()
                grid_block = out.split("Grid-Bot", 1)[1].split("Trend-Following-Bot", 1)[0]
                self.assertEqual("wuerde starten" in grid_block, should_start, grid_block)

                config = GridConfig(
                    api_key="t", api_secret="t", symbol=grid_symbol,
                    state_file=os.environ["GRID_STATE_FILE"],
                    stop_loss_state_file=os.environ["GRID_STOP_LOSS_STATE_FILE"],
                    pending_orders_file=str(self.tmp / "data" / "pending_grid_start.json"),
                    bot_name="grid",
                )
                bot = GridTradingStrategy(
                    config, FakeReconcileClient(config.pending_orders_file, "grid"))
                with mock.patch("dca_bot.grid_strategy.send_notification"), \
                        self.assertLogs("grid_bot", level="INFO"):
                    if should_start:
                        bot.verify_symbol_binding()
                    else:
                        with self.assertRaises(SymbolMismatch):
                            bot.verify_symbol_binding()


if __name__ == "__main__":
    unittest.main()

"""
Tests dafuer, dass der Heartbeat den Zeitpunkt des letzten ERFOLGREICHEN
Zyklus meldet - in allen vier Einstiegspunkten.

Hintergrund (Code-Ueberpruefung vom 25.09.2026, Prioritaet 2): Die vier
main*.py setzten `last_cycle_at` nach jedem Schleifendurchlauf auf
"jetzt", auch wenn `execute_once()` mit einer Exception abgebrochen war.
Damit lief der dokumentierte Zweck des Zeitstempels (heartbeat.py:
"Prozess laeuft" vs. "Prozess arbeitet") ins Leere - ein Bot, dessen
Zyklen alle scheitern, sah im Heartbeat aus wie ein gesunder.

Geprueft wird die echte `main()` jedes Bots, nicht eine nachgebaute
Schleife: Die Stelle existiert viermal fast identisch, und der
realistische Fehler ist, dass eine davon abweicht. Ersetzt sind nur die
Aussenwelt (Config, Client, Strategie, Lock, Schlaf) und die Uhr - Letztere,
damit zwei Zeitstempel sicher verschieden sind und "gleich" wirklich
"nicht neu gesetzt" bedeutet statt "in derselben Mikrosekunde".

Ausfuehren mit:  python -m unittest tests.test_heartbeat_last_cycle -v
"""

from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dca_bot import cycle_errors
from dca_bot import main as dca_main
from dca_bot import main_allocator, main_grid, main_trend
from dca_bot.allocator_config import AllocatorConfig
from dca_bot.config import Config
from dca_bot.grid_config import GridConfig
from dca_bot.trend_config import TrendConfig

# Marker in der Liste der Zyklus-Ergebnisse: dieser Zyklus scheitert.
FAIL = "fail"
OK = "ok"


class _FakeClock:
    """
    Ersatz fuer `datetime` im jeweiligen main-Modul. Jeder Aufruf von
    `now()` liefert einen spaeteren, eindeutig unterscheidbaren Zeitpunkt.
    """

    START = datetime(2026, 9, 25, 0, 30, tzinfo=timezone.utc)

    def __init__(self) -> None:
        self.calls = 0

    def now(self, tz=None) -> datetime:
        self.calls += 1
        return self.START + timedelta(minutes=5 * self.calls)


class _HeartbeatLastCycleMixin:
    """
    Gemeinsamer Ablauf fuer alle vier Bots. Die Unterklassen legen nur
    fest, welches Modul, welche Config und welche Strategie-Klasse gemeint
    sind. Bewusst ein Mixin ohne eigene TestCase-Basis: so laufen die
    Tests genau einmal pro Bot und nicht zusaetzlich fuer die Basisklasse.
    """

    module = None
    config_loader_name = ""
    strategy_class_name = ""
    logger_name = ""

    def make_config(self, tmp: Path):
        raise NotImplementedError

    def extra_patches(self) -> list:
        return []

    def run_cycles(self, outcomes: list[str]) -> list:
        """
        Laesst `main()` genau `len(outcomes)` Zyklen laufen und gibt die
        Argumente zurueck, mit denen `heartbeat.maybe_send()` nach jedem
        Zyklus aufgerufen wurde.
        """
        module = self.module
        side_effects = [
            RuntimeError("Read timed out (Testfall)") if o == FAIL else None
            for o in outcomes
        ]
        # Nach dem letzten Zyklus "Notaus waehrend der Wartezeit" -
        # das beendet die Schleife regulaer.
        sleeps = [False] * (len(outcomes) - 1) + [True]

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            config = self.make_config(Path(tmp))
            strategy_cls = stack.enter_context(
                mock.patch.object(module, self.strategy_class_name)
            )
            strategy_cls.return_value.execute_once.side_effect = side_effects
            heartbeat_cls = stack.enter_context(mock.patch.object(module, "Heartbeat"))

            for name, kwargs in (
                (self.config_loader_name, {"return_value": config}),
                ("setup_logging", {}),
                ("ProcessLock", {}),
                ("init_notifier", {}),
                ("announce_trading_mode", {}),
                ("TradingClient", {}),
                ("KillSwitch", {}),
                ("send_notification", {}),
                ("datetime", {"new": _FakeClock()}),
                ("_sleep_with_kill_switch_check", {"side_effect": sleeps}),
            ):
                stack.enter_context(mock.patch.object(module, name, **kwargs))
            if hasattr(module, "safe_startup_reconciliation"):
                stack.enter_context(mock.patch.object(module, "safe_startup_reconciliation"))
            # Grid und Allocator melden Zyklusfehler ueber cycle_errors.py.
            stack.enter_context(mock.patch.object(cycle_errors, "send_notification"))
            for patch in self.extra_patches():
                stack.enter_context(patch)

            # Faengt die Log-Ausgabe ab (inklusive der Tracebacks der
            # absichtlich gescheiterten Zyklen), statt die Testausgabe
            # damit zu fuellen.
            stack.enter_context(self.assertLogs(self.logger_name, level="INFO"))

            module.main()

        # Praemisse: es liefen wirklich alle Zyklen - sonst waere jede
        # Aussage unten auch bei einer abgebrochenen Schleife wahr.
        self.assertEqual(
            strategy_cls.return_value.execute_once.call_count, len(outcomes)
        )
        return [c.args[0] for c in heartbeat_cls.return_value.maybe_send.call_args_list]

    # -- die Tests ---------------------------------------------------------

    def test_failed_first_cycle_reports_no_successful_cycle(self):
        stamps = self.run_cycles([FAIL])
        self.assertEqual(stamps, [None])

    def test_failed_cycle_keeps_the_previous_timestamp(self):
        stamps = self.run_cycles([OK, FAIL, FAIL])
        self.assertIsNotNone(stamps[0])
        self.assertEqual(stamps[1], stamps[0], "Fehlzyklus darf den Zeitstempel nicht setzen")
        self.assertEqual(stamps[2], stamps[0], "auch der zweite Fehlzyklus nicht")

    def test_successful_cycle_after_failure_updates_the_timestamp(self):
        stamps = self.run_cycles([OK, FAIL, OK])
        self.assertEqual(stamps[1], stamps[0])
        self.assertGreater(stamps[2], stamps[1], "erfolgreicher Zyklus setzt neu")

    def test_every_successful_cycle_updates_the_timestamp(self):
        """
        Gegenprobe zu den Tests oben: ohne sie waere "Zeitstempel bleibt
        gleich" auch dann gruen, wenn die Uhr im Test gar nicht
        weiterliefe oder nie gelesen wuerde.
        """
        stamps = self.run_cycles([OK, OK])
        self.assertIsNotNone(stamps[0])
        self.assertGreater(stamps[1], stamps[0])


class DcaHeartbeatLastCycleTestCase(_HeartbeatLastCycleMixin, unittest.TestCase):
    module = dca_main
    config_loader_name = "load_config"
    strategy_class_name = "DCAStrategy"
    logger_name = "dca_bot"

    def make_config(self, tmp: Path) -> Config:
        return Config(
            api_key="test",
            api_secret="test",
            state_file=str(tmp / "trade_ledger.json"),
            stop_loss_state_file=str(tmp / "stop_loss_paused.json"),
            pending_orders_file=str(tmp / "pending_orders_dca.json"),
            lock_file=str(tmp / "dca_bot.lock"),
            heartbeat_status_file=str(tmp / "heartbeat_dca.json"),
            log_file=str(tmp / "dca_bot.log"),
        )

    def extra_patches(self) -> list:
        # Kein Warten vor dem ersten Zyklus (W2), und ein fester Tag,
        # damit keine Tageszusammenfassung dazwischenfunkt.
        return [
            mock.patch.object(dca_main, "_seconds_until_next_cycle", return_value=0),
            mock.patch.object(dca_main, "utc_today", return_value=date(2026, 9, 25)),
        ]


class GridHeartbeatLastCycleTestCase(_HeartbeatLastCycleMixin, unittest.TestCase):
    module = main_grid
    config_loader_name = "load_grid_config"
    strategy_class_name = "GridTradingStrategy"
    logger_name = "grid_bot"

    def make_config(self, tmp: Path) -> GridConfig:
        return GridConfig(
            api_key="test",
            api_secret="test",
            state_file=str(tmp / "grid_positions.json"),
            stop_loss_state_file=str(tmp / "grid_stop_loss_paused.json"),
            pending_orders_file=str(tmp / "pending_orders_grid.json"),
            lock_file=str(tmp / "grid_bot.lock"),
            heartbeat_status_file=str(tmp / "heartbeat_grid.json"),
            log_file=str(tmp / "grid_bot.log"),
        )


class TrendHeartbeatLastCycleTestCase(_HeartbeatLastCycleMixin, unittest.TestCase):
    module = main_trend
    config_loader_name = "load_trend_config"
    strategy_class_name = "TrendFollowingStrategy"
    logger_name = "trend_bot"

    def make_config(self, tmp: Path) -> TrendConfig:
        return TrendConfig(
            api_key="test",
            api_secret="test",
            state_file=str(tmp / "trend_ledger.json"),
            stop_loss_state_file=str(tmp / "trend_stop_loss_paused.json"),
            pending_orders_file=str(tmp / "pending_orders_trend.json"),
            lock_file=str(tmp / "trend_bot.lock"),
            heartbeat_status_file=str(tmp / "heartbeat_trend.json"),
            log_file=str(tmp / "trend_bot.log"),
        )


class AllocatorHeartbeatLastCycleTestCase(_HeartbeatLastCycleMixin, unittest.TestCase):
    module = main_allocator
    config_loader_name = "load_allocator_config"
    strategy_class_name = "Allocator"
    logger_name = "allocator"

    def make_config(self, tmp: Path) -> AllocatorConfig:
        return AllocatorConfig(
            api_key="test",
            api_secret="test",
            state_file=str(tmp / "allocator_state.json"),
            lock_file=str(tmp / "allocator.lock"),
            heartbeat_status_file=str(tmp / "heartbeat_allocator.json"),
            log_file=str(tmp / "allocator.log"),
        )


if __name__ == "__main__":
    unittest.main()

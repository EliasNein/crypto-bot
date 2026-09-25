"""
Tests fuer die Heartbeat-Statusdateien (dca_bot/heartbeat_status.py).

Jeder der vier Bots schreibt nach jedem Zyklus eine eigene kleine
JSON-Datei fuer die Dashboard-App: letzter erfolgreicher Zyklus, letzter
Versuch, Fehlschlaege in Folge. Geprueft wird dreierlei:

1. Der Writer selbst - Inhalt nach Erfolg und Fehlschlag, und dass ein
   Absturz mitten im Schreiben den vorherigen Stand unversehrt laesst.
2. Die echte `main()` aller vier Bots - wie in
   test_heartbeat_last_cycle.py sind nur Aussenwelt und Uhr ersetzt. Die
   Stelle existiert viermal fast identisch; der realistische Fehler ist,
   dass eine davon abweicht.
3. "Nur schreiben, nie lesen" - als Quelltext-Pruefung, weil sich das
   Fehlen eines Lesezugriffs nicht per Verhalten testen laesst.

Ausfuehren mit:  python -m unittest tests.test_heartbeat_status_file -v
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dca_bot import cycle_errors, heartbeat_status
from dca_bot import main as dca_main
from dca_bot import main_allocator, main_grid, main_trend
from dca_bot.allocator_config import AllocatorConfig
from dca_bot.config import Config
from dca_bot.grid_config import GridConfig
from dca_bot.heartbeat_status import HeartbeatStatusWriter
from dca_bot.risk import BotHalted
from dca_bot.trend_config import TrendConfig

DCA_BOT_DIR = Path(__file__).resolve().parent.parent / "dca_bot"

T0 = datetime(2026, 9, 25, 0, 30, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=5)
T2 = T0 + timedelta(minutes=10)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class _WriterTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "data" / "heartbeat_test.json"
        self.logger = logging.getLogger("test_heartbeat_status_file")
        self.logger.addHandler(logging.NullHandler())
        self.logger.propagate = False
        self.writer = HeartbeatStatusWriter(str(self.path), self.logger)


class WriterContentTestCase(_WriterTestBase):
    def test_success_writes_timestamp_and_zero_failures(self):
        self.writer.record_success(T0)
        self.assertEqual(
            _read(self.path),
            {
                "last_successful_cycle": T0.isoformat(),
                "last_cycle_attempt": T0.isoformat(),
                "consecutive_failures": 0,
            },
        )

    def test_failure_before_any_success_writes_null(self):
        self.writer.record_failure(T0, None)
        data = _read(self.path)
        self.assertIsNone(data["last_successful_cycle"])
        self.assertEqual(data["last_cycle_attempt"], T0.isoformat())
        self.assertEqual(data["consecutive_failures"], 1)

    def test_failure_updates_attempt_but_keeps_last_success(self):
        self.writer.record_success(T0)
        self.writer.record_failure(T1, T0)
        self.writer.record_failure(T2, T0)
        data = _read(self.path)
        self.assertEqual(data["last_successful_cycle"], T0.isoformat())
        self.assertEqual(data["last_cycle_attempt"], T2.isoformat())
        self.assertEqual(data["consecutive_failures"], 2)

    def test_success_resets_the_failure_counter(self):
        self.writer.record_failure(T0, None)
        self.writer.record_failure(T1, None)
        self.writer.record_success(T2)
        self.assertEqual(_read(self.path)["consecutive_failures"], 0)

    def test_timestamps_are_parseable_utc_iso(self):
        self.writer.record_success(T0)
        stamp = datetime.fromisoformat(_read(self.path)["last_successful_cycle"])
        self.assertEqual(stamp, T0)
        self.assertEqual(stamp.utcoffset(), timedelta(0))

    def test_writer_has_no_read_api(self):
        """Nur schreiben: oeffentlich gibt es genau die beiden record_*-Methoden."""
        public = {n for n in vars(HeartbeatStatusWriter) if not n.startswith("_")}
        self.assertEqual(public, {"record_success", "record_failure"})


class WriterAtomicityTestCase(_WriterTestBase):
    """
    Ein Absturz mitten im Schreiben darf nie einen halb geschriebenen
    Stand hinterlassen: Die Zieldatei behaelt den vorherigen Inhalt und
    bleibt gueltiges JSON. Simuliert an beiden Stellen, an denen es
    realistisch passiert - waehrend der Ausgabe und beim Umbenennen.
    """

    def setUp(self) -> None:
        super().setUp()
        self.writer.record_success(T0)
        self.before = self.path.read_text(encoding="utf-8")

    def assert_previous_state_intact(self) -> None:
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.before)
        self.assertEqual(_read(self.path)["last_successful_cycle"], T0.isoformat())

    def test_crash_during_json_output(self):
        def dump_half_then_crash(data, f, **kwargs):
            f.write('{"last_successful_cycle": "2026-')
            raise OSError("Absturz mitten in der Ausgabe (Testfall)")

        with mock.patch.object(heartbeat_status.json, "dump", side_effect=dump_half_then_crash):
            self.writer.record_failure(T1, T0)
        self.assert_previous_state_intact()

    def test_crash_during_replace(self):
        with mock.patch.object(
            heartbeat_status.os, "replace", side_effect=OSError("Absturz beim Umbenennen")
        ):
            self.writer.record_failure(T1, T0)
        self.assert_previous_state_intact()

    def test_next_write_after_a_crash_succeeds(self):
        with mock.patch.object(heartbeat_status.os, "replace", side_effect=OSError("x")):
            self.writer.record_failure(T1, T0)
        self.writer.record_failure(T2, T0)
        data = _read(self.path)
        self.assertEqual(data["last_cycle_attempt"], T2.isoformat())
        # Der Zaehler zaehlt Zyklen, nicht Schreibvorgaenge.
        self.assertEqual(data["consecutive_failures"], 2)


class WriterErrorHandlingTestCase(_WriterTestBase):
    """Ein Schreibfehler darf den Bot nie erreichen und das Log nicht fluten."""

    def test_write_error_is_not_raised(self):
        with mock.patch.object(heartbeat_status.os, "replace", side_effect=OSError("voll")):
            self.writer.record_success(T0)
            self.writer.record_failure(T1, T0)

    def test_write_error_is_logged_once_per_series(self):
        with mock.patch.object(self.logger, "warning") as warning:
            with mock.patch.object(heartbeat_status.os, "replace", side_effect=OSError("voll")):
                self.writer.record_failure(T0, None)
                self.writer.record_failure(T1, None)
                self.writer.record_failure(T2, None)
            self.assertEqual(warning.call_count, 1)

            # Nach einem gelungenen Write beginnt eine neue Serie.
            self.writer.record_success(T2)
            with mock.patch.object(heartbeat_status.os, "replace", side_effect=OSError("voll")):
                self.writer.record_failure(T2, T2)
            self.assertEqual(warning.call_count, 2)


# -- die echte main() aller vier Bots -------------------------------------

FAIL = "fail"
OK = "ok"
HALT = "halt"


class _FakeClock:
    """Ersatz fuer `datetime` im main-Modul: jeder now()-Aufruf ist spaeter."""

    def __init__(self) -> None:
        self.calls = 0

    def now(self, tz=None) -> datetime:
        self.calls += 1
        return T0 + timedelta(minutes=5 * self.calls)


class _MainStatusFileMixin:
    """
    Gemeinsamer Ablauf fuer alle vier Bots, gleiche Technik wie in
    test_heartbeat_last_cycle.py. Die Statusdatei wird nach jedem Zyklus
    gelesen - ueber `heartbeat.maybe_send()`, das die Schleife direkt nach
    dem Zyklus aufruft.
    """

    module = None
    config_loader_name = ""
    strategy_class_name = ""
    logger_name = ""

    def make_config(self, tmp: Path, status_file: Path):
        raise NotImplementedError

    def extra_patches(self) -> list:
        return []

    def run_cycles(self, outcomes: list[str], unwritable: bool = False):
        """
        Laesst `main()` die Zyklen laufen. Gibt zurueck: den Inhalt der
        Statusdatei nach jedem Zyklus (None, wenn es sie noch nicht gibt),
        die an `maybe_send()` uebergebenen Zeitstempel und ob die Datei
        am Ende existiert. `unwritable` macht das Elternverzeichnis der
        Statusdatei zu einer normalen Datei, sodass jeder Write scheitert.
        """
        module = self.module
        side_effects = []
        for o in outcomes:
            if o == FAIL:
                side_effects.append(RuntimeError("Read timed out (Testfall)"))
            elif o == HALT:
                side_effects.append(BotHalted("Notaus (Testfall)"))
            else:
                side_effects.append(None)
        sleeps = [False] * (len(outcomes) - 1) + [True]
        snapshots: list = []
        stamps: list = []

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            status_file = Path(tmp) / "hb.json"
            if unwritable:
                (Path(tmp) / "blocker").write_text("kein Verzeichnis", encoding="utf-8")
                status_file = Path(tmp) / "blocker" / "hb.json"
            config = self.make_config(Path(tmp), status_file)

            def snapshot(last_cycle_at):
                stamps.append(last_cycle_at)
                snapshots.append(_read(status_file) if status_file.is_file() else None)

            strategy_cls = stack.enter_context(
                mock.patch.object(module, self.strategy_class_name)
            )
            strategy_cls.return_value.execute_once.side_effect = side_effects
            heartbeat_cls = stack.enter_context(mock.patch.object(module, "Heartbeat"))
            heartbeat_cls.return_value.maybe_send.side_effect = snapshot

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
            stack.enter_context(mock.patch.object(cycle_errors, "send_notification"))
            for patch in self.extra_patches():
                stack.enter_context(patch)
            stack.enter_context(self.assertLogs(self.logger_name, level="INFO"))

            module.main()
            exists_at_end = status_file.is_file()

        self.assertEqual(
            strategy_cls.return_value.execute_once.call_count, len(outcomes)
        )
        return snapshots, stamps, exists_at_end

    # -- die Tests ---------------------------------------------------------

    def test_status_file_follows_every_cycle(self):
        snapshots, stamps, _ = self.run_cycles([FAIL, OK, FAIL, FAIL, OK])

        first, ok1, fail1, fail2, ok2 = snapshots
        self.assertIsNone(first["last_successful_cycle"])
        self.assertEqual(first["consecutive_failures"], 1)

        # Erfolg: derselbe Zeitstempel, den auch der Telegram-Heartbeat
        # bekommt - keine eigene Erfolgslogik.
        self.assertEqual(ok1["last_successful_cycle"], stamps[1].isoformat())
        self.assertEqual(ok1["last_cycle_attempt"], ok1["last_successful_cycle"])
        self.assertEqual(ok1["consecutive_failures"], 0)

        for failed, count in ((fail1, 1), (fail2, 2)):
            self.assertEqual(failed["last_successful_cycle"], ok1["last_successful_cycle"])
            self.assertEqual(failed["consecutive_failures"], count)

        self.assertEqual(ok2["last_successful_cycle"], stamps[4].isoformat())
        self.assertEqual(ok2["consecutive_failures"], 0)

        # last_cycle_attempt ist nach JEDEM Zyklus neu, auch nach Fehlschlaegen.
        attempts = [datetime.fromisoformat(s["last_cycle_attempt"]) for s in snapshots]
        self.assertEqual(attempts, sorted(set(attempts)))

    def test_nothing_is_written_on_kill_switch(self):
        snapshots, _, exists_at_end = self.run_cycles([HALT])
        self.assertEqual(snapshots, [])
        self.assertFalse(exists_at_end)

    def test_unwritable_status_file_does_not_disturb_the_loop(self):
        """
        Anforderung "keine Rueckwirkung": Laesst sich die Datei nicht
        schreiben (hier: das Elternverzeichnis ist eine Datei), laufen
        alle Zyklen weiter und der Telegram-Heartbeat bekommt dieselben
        Zeitstempel wie sonst.
        """
        snapshots, stamps, _ = self.run_cycles([FAIL, OK, FAIL], unwritable=True)
        self.assertEqual(snapshots, [None, None, None])
        self.assertIsNone(stamps[0])
        self.assertIsNotNone(stamps[1])
        self.assertEqual(stamps[2], stamps[1])


class DcaStatusFileTestCase(_MainStatusFileMixin, unittest.TestCase):
    module = dca_main
    config_loader_name = "load_config"
    strategy_class_name = "DCAStrategy"
    logger_name = "dca_bot"

    def make_config(self, tmp: Path, status_file: Path) -> Config:
        return Config(
            api_key="test",
            api_secret="test",
            state_file=str(tmp / "trade_ledger.json"),
            stop_loss_state_file=str(tmp / "stop_loss_paused.json"),
            pending_orders_file=str(tmp / "pending_orders_dca.json"),
            lock_file=str(tmp / "dca_bot.lock"),
            heartbeat_status_file=str(status_file),
            log_file=str(tmp / "dca_bot.log"),
        )

    def extra_patches(self) -> list:
        return [
            mock.patch.object(dca_main, "_seconds_until_next_cycle", return_value=0),
            mock.patch.object(dca_main, "utc_today", return_value=date(2026, 9, 25)),
        ]


class GridStatusFileTestCase(_MainStatusFileMixin, unittest.TestCase):
    module = main_grid
    config_loader_name = "load_grid_config"
    strategy_class_name = "GridTradingStrategy"
    logger_name = "grid_bot"

    def make_config(self, tmp: Path, status_file: Path) -> GridConfig:
        return GridConfig(
            api_key="test",
            api_secret="test",
            state_file=str(tmp / "grid_positions.json"),
            stop_loss_state_file=str(tmp / "grid_stop_loss_paused.json"),
            pending_orders_file=str(tmp / "pending_orders_grid.json"),
            lock_file=str(tmp / "grid_bot.lock"),
            heartbeat_status_file=str(status_file),
            log_file=str(tmp / "grid_bot.log"),
        )


class TrendStatusFileTestCase(_MainStatusFileMixin, unittest.TestCase):
    module = main_trend
    config_loader_name = "load_trend_config"
    strategy_class_name = "TrendFollowingStrategy"
    logger_name = "trend_bot"

    def make_config(self, tmp: Path, status_file: Path) -> TrendConfig:
        return TrendConfig(
            api_key="test",
            api_secret="test",
            state_file=str(tmp / "trend_ledger.json"),
            stop_loss_state_file=str(tmp / "trend_stop_loss_paused.json"),
            pending_orders_file=str(tmp / "pending_orders_trend.json"),
            lock_file=str(tmp / "trend_bot.lock"),
            heartbeat_status_file=str(status_file),
            log_file=str(tmp / "trend_bot.log"),
        )


class AllocatorStatusFileTestCase(_MainStatusFileMixin, unittest.TestCase):
    module = main_allocator
    config_loader_name = "load_allocator_config"
    strategy_class_name = "Allocator"
    logger_name = "allocator"

    def make_config(self, tmp: Path, status_file: Path) -> AllocatorConfig:
        return AllocatorConfig(
            api_key="test",
            api_secret="test",
            state_file=str(tmp / "allocator_state.json"),
            lock_file=str(tmp / "allocator.lock"),
            heartbeat_status_file=str(status_file),
            log_file=str(tmp / "allocator.log"),
        )


# -- "nur schreiben, nie lesen" -------------------------------------------


class WriteOnlyTestCase(unittest.TestCase):
    """
    Kein Bot darf eine Heartbeat-Statusdatei lesen - weder die eigene noch
    eine fremde. Verhaltenstests koennen ein Fehlen nicht zeigen, deshalb
    eine Quelltext-Pruefung ueber das ganze Paket.
    """

    CONFIG_MODULES = {"config.py", "grid_config.py", "trend_config.py", "allocator_config.py"}
    MAIN_MODULES = {"main.py", "main_grid.py", "main_trend.py", "main_allocator.py"}

    def sources(self) -> dict[str, str]:
        return {p.name: p.read_text(encoding="utf-8") for p in sorted(DCA_BOT_DIR.glob("*.py"))}

    def test_path_is_only_used_by_configs_and_the_writer_construction(self):
        for name, source in self.sources().items():
            uses = source.count("heartbeat_status_file")
            if name in self.CONFIG_MODULES:
                continue
            if name in self.MAIN_MODULES:
                self.assertEqual(uses, 1, name)
                self.assertIn(
                    "HeartbeatStatusWriter(config.heartbeat_status_file, logger)", source, name
                )
            else:
                self.assertEqual(uses, 0, name)

    def test_file_names_appear_only_in_the_configs(self):
        pattern = re.compile(r"heartbeat_(dca|grid|trend|allocator)\.json")
        for name, source in self.sources().items():
            if name in self.CONFIG_MODULES:
                continue
            self.assertIsNone(pattern.search(source), name)

    def test_each_bot_has_its_own_file_under_data(self):
        """Eine Datei pro Bot, keine gemeinsame (Lost-Update zwischen Prozessen)."""
        defaults = {
            cls.__name__: next(
                f.default for f in dataclasses.fields(cls) if f.name == "heartbeat_status_file"
            )
            for cls in (Config, GridConfig, TrendConfig, AllocatorConfig)
        }
        self.assertEqual(
            defaults,
            {
                "Config": "data/heartbeat_dca.json",
                "GridConfig": "data/heartbeat_grid.json",
                "TrendConfig": "data/heartbeat_trend.json",
                "AllocatorConfig": "data/heartbeat_allocator.json",
            },
        )

    def test_writer_module_contains_no_read_access(self):
        source = (DCA_BOT_DIR / "heartbeat_status.py").read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        for forbidden in ("json.load", "read_text", "read_bytes", '"r"', "'r'", ".read("):
            self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()

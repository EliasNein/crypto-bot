"""
Tests fuer das Mengenlimit der Zyklusfehler-Meldungen von Grid-Bot und
Allocator (Code-Ueberpruefung vom 25.09.2026, Prioritaet 3 - siehe
CycleErrorNotifier in cycle_errors.py).

Vorher ging jeder fehlgeschlagene Zyklus per Telegram raus, bei einer
laengeren Stoerung also zwoelf identische Meldungen pro Stunde (Grid)
bzw. eine pro Stunde (Allocator). Jetzt: die erste Meldung eines
Fehlertyps geht raus, weitere desselben Typs nur noch ins Log, bis ein
Zyklus wieder erfolgreich war.

Zwei Ebenen: `CycleErrorNotifier` direkt (die Regel), und die echte
`main()` von Grid-Bot und Allocator ueber mehrere Zyklen (die
Verdrahtung - dort muss zusaetzlich jeder Fehlschlag weiterhin im Log
stehen). Als Fehler dienen die Exception-Klassen, die bei der
naechtlichen Zwangstrennung tatsaechlich auftreten.

Ausfuehren mit:  python -m unittest tests.test_cycle_error_notification -v
"""

from __future__ import annotations

import logging
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ReadTimeout

from dca_bot import cycle_errors, main_allocator, main_grid
from dca_bot.allocator_config import AllocatorConfig
from dca_bot.cycle_errors import CycleErrorNotifier
from dca_bot.grid_config import GridConfig

OK = None


def _timeout() -> ReadTimeout:
    return ReadTimeout(
        "HTTPSConnectionPool(host='testnet.binance.vision', port=443): "
        "Read timed out. (read timeout=20)"
    )


def _connection_error() -> RequestsConnectionError:
    return RequestsConnectionError("Failed to resolve 'testnet.binance.vision'")


class CycleErrorNotifierTestCase(unittest.TestCase):
    """Die Regel selbst, unabhaengig davon, welcher Prozess sie nutzt."""

    TAG = "[TEST-FEHLER]"

    def setUp(self) -> None:
        self.logger = logging.getLogger("cycle_error_test")
        # Ohne Handler schriebe Pythons Notbehelf die Warnungen der Tests,
        # die das Log nicht selbst pruefen, auf die Konsole.
        null_handler = logging.NullHandler()
        self.logger.addHandler(null_handler)
        self.addCleanup(self.logger.removeHandler, null_handler)
        self.notifier = CycleErrorNotifier(self.logger, self.TAG, "Test-Zyklus")
        patcher = mock.patch.object(cycle_errors, "send_notification")
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)

    def _messages(self) -> list[str]:
        return [c.args[0] for c in self.notify.call_args_list]

    def test_first_failure_is_sent_via_telegram(self):
        self.notifier.report_failure(_timeout())

        messages = self._messages()
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].startswith(self.TAG), "Marker des Prozesses")
        self.assertIn("Test-Zyklus", messages[0])
        self.assertIn("Read timed out", messages[0], "Die Fehlerursache gehoert in die Meldung")
        self.assertIn("nur im Log", messages[0], "Die Meldung kuendigt die Sperre an")

    def test_repeated_failures_of_the_same_type_go_to_the_log_only(self):
        with self.assertLogs("cycle_error_test", level="WARNING") as captured:
            self.notifier.report_failure(_timeout())
            self.notifier.report_failure(_timeout())
            self.notifier.report_failure(_timeout())

        self.assertEqual(len(self._messages()), 1)
        suppressed = [line for line in captured.output if "Gleichartiger Fehler" in line]
        self.assertEqual(len(suppressed), 2, "Jeder unterdrueckte Fehlschlag steht im Log")
        self.assertIn(self.TAG, suppressed[-1])
        self.assertIn("3. Fehlzyklus in Folge", suppressed[-1])

    def test_success_in_between_rearms_the_notification(self):
        self.notifier.report_failure(_timeout())
        self.notifier.report_failure(_timeout())
        self.notifier.report_success()
        self.notifier.report_failure(_timeout())

        self.assertEqual(len(self._messages()), 2)

    def test_new_error_type_during_a_failure_series_is_sent(self):
        """
        "Pro Fehlertyp": wird aus dem Timeout mitten in der Serie ein
        Verbindungsfehler, ist das eine neue Information.
        """
        self.notifier.report_failure(_timeout())
        self.notifier.report_failure(_connection_error())
        self.notifier.report_failure(_timeout())
        self.notifier.report_failure(_connection_error())

        messages = self._messages()
        self.assertEqual(len(messages), 2)
        self.assertIn("ReadTimeout", messages[0])
        self.assertIn("ConnectionError", messages[1])

    def test_recovery_is_logged_with_the_number_of_failed_cycles(self):
        self.notifier.report_failure(_timeout())
        self.notifier.report_failure(_timeout())

        with self.assertLogs("cycle_error_test", level="INFO") as captured:
            self.notifier.report_success()

        self.assertTrue(
            any("wieder erfolgreich nach 2" in line for line in captured.output),
            captured.output,
        )

    def test_success_without_prior_failure_logs_nothing(self):
        """Der Normalfall (288 Grid-Zyklen am Tag) darf das Log nicht fuellen."""
        with self.assertNoLogs("cycle_error_test", level="INFO"):
            self.notifier.report_success()


class _MainCycleErrorNotificationMixin:
    """
    Die Verdrahtung in der echten main() eines Prozesses. Die
    Unterklassen legen nur Modul, Config, Strategie-Klasse, Logger und
    Telegram-Marker fest. Bewusst ein Mixin ohne eigene TestCase-Basis,
    damit die Tests genau einmal pro Prozess laufen.
    """

    module = None
    config_loader_name = ""
    strategy_class_name = ""
    logger_name = ""
    tag = ""
    cycle_log_text = ""

    def make_config(self, tmp: Path):
        raise NotImplementedError

    def _run_cycles(self, outcomes: list) -> tuple[list[str], list[str]]:
        """
        Laesst main() genau `len(outcomes)` Zyklen laufen. Jedes Element
        ist OK (None) oder die Exception, mit der der Zyklus scheitert.
        Gibt die Zyklusfehler-Meldungen per Telegram und die Log-Zeilen
        zurueck.
        """
        module = self.module
        sleeps = [False] * (len(outcomes) - 1) + [True]

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            config = self.make_config(Path(tmp))
            strategy_cls = stack.enter_context(
                mock.patch.object(module, self.strategy_class_name)
            )
            strategy_cls.return_value.execute_once.side_effect = outcomes
            notify = stack.enter_context(mock.patch.object(cycle_errors, "send_notification"))
            for name, kwargs in (
                (self.config_loader_name, {"return_value": config}),
                ("setup_logging", {}),
                ("ProcessLock", {}),
                ("init_notifier", {}),
                ("announce_trading_mode", {}),
                ("TradingClient", {}),
                ("KillSwitch", {}),
                ("Heartbeat", {}),
                ("send_notification", {}),
                ("_sleep_with_kill_switch_check", {"side_effect": sleeps}),
            ):
                stack.enter_context(mock.patch.object(module, name, **kwargs))
            if hasattr(module, "safe_startup_reconciliation"):
                stack.enter_context(mock.patch.object(module, "safe_startup_reconciliation"))
            captured = stack.enter_context(self.assertLogs(self.logger_name, level="INFO"))

            module.main()

        self.assertEqual(strategy_cls.return_value.execute_once.call_count, len(outcomes))
        messages = [c.args[0] for c in notify.call_args_list]
        for message in messages:
            self.assertTrue(message.startswith(self.tag), message)
        return messages, captured.output

    def _cycle_error_log_lines(self, log_lines: list[str]) -> list[str]:
        return [line for line in log_lines if self.cycle_log_text in line]

    def test_first_failed_cycle_sends_telegram(self):
        messages, log_lines = self._run_cycles([_timeout()])

        self.assertEqual(len(messages), 1)
        self.assertEqual(len(self._cycle_error_log_lines(log_lines)), 1)

    def test_following_failures_of_the_same_type_are_logged_only(self):
        messages, log_lines = self._run_cycles([_timeout(), _timeout(), _timeout()])

        self.assertEqual(len(messages), 1, "Telegram nur fuer den ersten Fehlzyklus")
        self.assertEqual(
            len(self._cycle_error_log_lines(log_lines)),
            3,
            "Jeder Fehlzyklus bleibt mit Traceback im Log",
        )

    def test_success_in_between_rearms_telegram(self):
        messages, _ = self._run_cycles([_timeout(), _timeout(), OK, _timeout()])

        self.assertEqual(len(messages), 2)

    def test_typical_night_sends_exactly_one_message(self):
        """
        Das konkrete Szenario: vorher und nachher laeuft alles, dazwischen
        ein einzelner Fehlzyklus - wie bei der naechtlichen Zwangstrennung.
        """
        messages, _ = self._run_cycles([OK, OK, _timeout(), OK, OK])

        self.assertEqual(len(messages), 1)


class GridMainCycleErrorNotificationTestCase(_MainCycleErrorNotificationMixin, unittest.TestCase):
    module = main_grid
    config_loader_name = "load_grid_config"
    strategy_class_name = "GridTradingStrategy"
    logger_name = "grid_bot"
    tag = "[GRID-FEHLER]"
    cycle_log_text = "Unerwarteter Fehler im Grid-Zyklus"

    def make_config(self, tmp: Path) -> GridConfig:
        return GridConfig(
            api_key="test",
            api_secret="test",
            state_file=str(tmp / "grid_positions.json"),
            stop_loss_state_file=str(tmp / "grid_stop_loss_paused.json"),
            pending_orders_file=str(tmp / "pending_orders_grid.json"),
            lock_file=str(tmp / "grid_bot.lock"),
            log_file=str(tmp / "grid_bot.log"),
        )


class AllocatorMainCycleErrorNotificationTestCase(
    _MainCycleErrorNotificationMixin, unittest.TestCase
):
    module = main_allocator
    config_loader_name = "load_allocator_config"
    strategy_class_name = "Allocator"
    logger_name = "allocator"
    tag = "[ALLOCATOR-FEHLER]"
    cycle_log_text = "Unerwarteter Fehler im Allocator-Zyklus"

    def make_config(self, tmp: Path) -> AllocatorConfig:
        return AllocatorConfig(
            api_key="test",
            api_secret="test",
            state_file=str(tmp / "allocator_state.json"),
            lock_file=str(tmp / "allocator.lock"),
            log_file=str(tmp / "allocator.log"),
        )


if __name__ == "__main__":
    unittest.main()

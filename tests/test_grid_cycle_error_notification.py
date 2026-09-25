"""
Tests fuer das Mengenlimit der `[GRID-FEHLER]`-Meldungen
(Code-Ueberpruefung vom 25.09.2026, Prioritaet 3 - siehe
CycleErrorNotifier in main_grid.py).

Vorher ging jeder fehlgeschlagene Grid-Zyklus per Telegram raus, bei
einer laengeren Stoerung also zwoelf identische Meldungen pro Stunde.
Jetzt: die erste Meldung eines Fehlertyps geht raus, weitere desselben
Typs nur noch ins Log, bis ein Zyklus wieder erfolgreich war.

Zwei Ebenen: `CycleErrorNotifier` direkt (die Regel), und die echte
`main_grid.main()` ueber mehrere Zyklen (die Verdrahtung - dort muss
zusaetzlich jeder Fehlschlag weiterhin im Log stehen). Als Fehler dienen
die Exception-Klassen, die bei der naechtlichen Zwangstrennung
tatsaechlich auftreten.

Ausfuehren mit:  python -m unittest tests.test_grid_cycle_error_notification -v
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

from dca_bot import main_grid
from dca_bot.grid_config import GridConfig
from dca_bot.main_grid import CycleErrorNotifier

OK = None


def _timeout() -> ReadTimeout:
    return ReadTimeout(
        "HTTPSConnectionPool(host='testnet.binance.vision', port=443): "
        "Read timed out. (read timeout=20)"
    )


def _connection_error() -> RequestsConnectionError:
    return RequestsConnectionError("Failed to resolve 'testnet.binance.vision'")


class CycleErrorNotifierTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("grid_bot")
        # Ohne Handler schriebe Pythons Notbehelf die Warnungen der Tests,
        # die das Log nicht selbst pruefen, auf die Konsole.
        null_handler = logging.NullHandler()
        self.logger.addHandler(null_handler)
        self.addCleanup(self.logger.removeHandler, null_handler)
        self.notifier = CycleErrorNotifier(self.logger)
        patcher = mock.patch.object(main_grid, "send_notification")
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)

    def _grid_error_messages(self) -> list[str]:
        return [
            c.args[0] for c in self.notify.call_args_list if "[GRID-FEHLER]" in c.args[0]
        ]

    def test_first_failure_is_sent_via_telegram(self):
        self.notifier.report_failure(_timeout())

        messages = self._grid_error_messages()
        self.assertEqual(len(messages), 1)
        self.assertIn("Read timed out", messages[0], "Die Fehlerursache gehoert in die Meldung")
        self.assertIn("nur im Log", messages[0], "Die Meldung kuendigt die Sperre an")

    def test_repeated_failures_of_the_same_type_go_to_the_log_only(self):
        with self.assertLogs("grid_bot", level="WARNING") as captured:
            self.notifier.report_failure(_timeout())
            self.notifier.report_failure(_timeout())
            self.notifier.report_failure(_timeout())

        self.assertEqual(len(self._grid_error_messages()), 1)
        suppressed = [line for line in captured.output if "Gleichartiger Fehler" in line]
        self.assertEqual(len(suppressed), 2, "Jeder unterdrueckte Fehlschlag steht im Log")
        self.assertIn("3. Fehlzyklus in Folge", suppressed[-1])

    def test_success_in_between_rearms_the_notification(self):
        self.notifier.report_failure(_timeout())
        self.notifier.report_failure(_timeout())
        self.notifier.report_success()
        self.notifier.report_failure(_timeout())

        self.assertEqual(len(self._grid_error_messages()), 2)

    def test_new_error_type_during_a_failure_series_is_sent(self):
        """
        "Pro Fehlertyp": wird aus dem Timeout mitten in der Serie ein
        Verbindungsfehler, ist das eine neue Information.
        """
        self.notifier.report_failure(_timeout())
        self.notifier.report_failure(_connection_error())
        self.notifier.report_failure(_timeout())
        self.notifier.report_failure(_connection_error())

        messages = self._grid_error_messages()
        self.assertEqual(len(messages), 2)
        self.assertIn("ReadTimeout", messages[0])
        self.assertIn("ConnectionError", messages[1])

    def test_recovery_is_logged_with_the_number_of_failed_cycles(self):
        self.notifier.report_failure(_timeout())
        self.notifier.report_failure(_timeout())

        with self.assertLogs("grid_bot", level="INFO") as captured:
            self.notifier.report_success()

        self.assertTrue(
            any("wieder erfolgreich nach 2" in line for line in captured.output),
            captured.output,
        )

    def test_success_without_prior_failure_logs_nothing(self):
        """Der Normalfall (288 Zyklen am Tag) darf das Log nicht fuellen."""
        with self.assertNoLogs("grid_bot", level="INFO"):
            self.notifier.report_success()


class GridMainCycleErrorNotificationTestCase(unittest.TestCase):
    """Die Verdrahtung in der echten main_grid.main()."""

    def _run_cycles(self, outcomes: list) -> tuple[list[str], list[str]]:
        """
        Laesst main() genau `len(outcomes)` Zyklen laufen. Jedes Element
        ist OK (None) oder die Exception, mit der der Zyklus scheitert.
        Gibt die [GRID-FEHLER]-Telegram-Meldungen und die Log-Zeilen zurueck.
        """
        sleeps = [False] * (len(outcomes) - 1) + [True]

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            tmp_path = Path(tmp)
            config = GridConfig(
                api_key="test",
                api_secret="test",
                state_file=str(tmp_path / "grid_positions.json"),
                stop_loss_state_file=str(tmp_path / "grid_stop_loss_paused.json"),
                pending_orders_file=str(tmp_path / "pending_orders_grid.json"),
                lock_file=str(tmp_path / "grid_bot.lock"),
                log_file=str(tmp_path / "grid_bot.log"),
            )
            strategy_cls = stack.enter_context(
                mock.patch.object(main_grid, "GridTradingStrategy")
            )
            strategy_cls.return_value.execute_once.side_effect = outcomes
            notify = stack.enter_context(mock.patch.object(main_grid, "send_notification"))
            for name, kwargs in (
                ("load_grid_config", {"return_value": config}),
                ("setup_logging", {}),
                ("ProcessLock", {}),
                ("init_notifier", {}),
                ("announce_trading_mode", {}),
                ("TradingClient", {}),
                ("KillSwitch", {}),
                ("Heartbeat", {}),
                ("safe_startup_reconciliation", {}),
                ("_sleep_with_kill_switch_check", {"side_effect": sleeps}),
            ):
                stack.enter_context(mock.patch.object(main_grid, name, **kwargs))
            captured = stack.enter_context(self.assertLogs("grid_bot", level="INFO"))

            main_grid.main()

        self.assertEqual(strategy_cls.return_value.execute_once.call_count, len(outcomes))
        messages = [
            c.args[0] for c in notify.call_args_list if "[GRID-FEHLER]" in c.args[0]
        ]
        return messages, captured.output

    @staticmethod
    def _cycle_error_log_lines(log_lines: list[str]) -> list[str]:
        return [line for line in log_lines if "Unerwarteter Fehler im Grid-Zyklus" in line]

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


if __name__ == "__main__":
    unittest.main()

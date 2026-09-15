"""
Tests für die Token-Hygiene der Telegram-Benachrichtigungen
(siehe dca_bot/notifier.py, Modul-Docstring).

Hintergrund: Der Telegram-Bot-Token ist Teil der Request-URL. Schlägt
ein Versand fehl, enthalten sowohl die `requests`-Exception-Message als
auch ein Traceback die vollständige URL - und damit den Token. Landet so
eine Zeile in `logs/*.log` und wird der Log später bei einem Meilenstein
ins (öffentliche) Repo archiviert (`!docs/**/*.log` in .gitignore), ist
der Token veröffentlicht. Diese Tests pinnen fest, dass aus dem Notifier
im Fehlerfall ausschließlich der Fehlertyp bzw. der HTTP-Statuscode ins
Log geht.

Kein echter Netzwerkzugriff: `requests.post` wird im Notifier-Modul
gepatcht, der Token ist ein offensichtlicher Fake-Wert.

Ausführen mit:  python -m unittest tests.test_notifier -v
"""

from __future__ import annotations

import logging
import unittest
from unittest import mock

import requests

from dca_bot import notifier
from dca_bot.config import Config

# Format wie ein echter Telegram-Token (Ziffernfolge, Doppelpunkt, Rest),
# aber offensichtlich erfunden.
FAKE_TOKEN = "123456789:AAFakeTokenForTestsOnly_DoNotUse_xyz"
FAKE_CHAT_ID = "987654321"
FAKE_URL = f"https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage"


class FakeResponse:
    """
    Minimale Nachbildung von requests.Response - bewusst kein Mock:
    ein Mock würde `raise_for_status()` stillschweigend als No-op
    akzeptieren, und genau dessen Rückkehr in den Code soll hier
    auffallen (die HTTPError-Message trägt die URL mit Token).
    """

    def __init__(self, status_code: int):
        self.status_code = status_code
        # Wie requests.Response.ok: False ab 400, nicht erst ab 500 und
        # nicht schon bei 3xx (Redirects folgt requests selbst).
        self.ok = status_code < 400
        self.text = '{"ok":false,"description":"Unauthorized"}'

    def raise_for_status(self) -> None:
        if not self.ok:
            # Exakt wie requests: die URL steht in der Message.
            raise requests.exceptions.HTTPError(
                f"{self.status_code} Client Error: Unauthorized for url: {FAKE_URL}"
            )


class NotifierTokenHygieneTestCase(unittest.TestCase):
    def setUp(self) -> None:
        notifier.init(
            Config(
                api_key="test",
                api_secret="test",
                telegram_bot_token=FAKE_TOKEN,
                telegram_chat_id=FAKE_CHAT_ID,
            )
        )

    def tearDown(self) -> None:
        # Modul-Zustand zurücksetzen, damit andere Tests nicht plötzlich
        # einen "konfigurierten" Notifier sehen.
        notifier.init(Config(api_key="test", api_secret="test"))

    def _assert_no_secret_leaked(self, captured_output: list[str]) -> None:
        """
        Gemeinsame Prüfung für jeden Fehlerpfad: weder Token noch
        vollständige Bot-URL dürfen irgendwo in den Log-Zeilen stehen.
        """
        joined = "\n".join(captured_output)
        self.assertNotIn(FAKE_TOKEN, joined, "Bot-Token steht im Log!")
        self.assertNotIn("api.telegram.org/bot", joined, "Bot-URL steht im Log!")
        # Auch Teil-Token (die Ziffern-ID vor dem Doppelpunkt) nicht.
        self.assertNotIn(FAKE_TOKEN.split(":")[0], joined, "Token-ID steht im Log!")

    def test_connection_error_logs_only_exception_type(self):
        """Netzwerkfehler: requests packt die URL in die Message."""
        exc = requests.exceptions.ConnectionError(
            f"HTTPSConnectionPool(host='api.telegram.org', port=443): Max "
            f"retries exceeded with url: /bot{FAKE_TOKEN}/sendMessage "
            f"(Caused by NewConnectionError(...))"
        )

        with mock.patch("dca_bot.notifier.requests.post", side_effect=exc):
            with self.assertLogs("dca_bot", level="ERROR") as captured:
                notifier.send_notification("[KAUF] Testnachricht")

        self._assert_no_secret_leaked(captured.output)
        self.assertIn("ConnectionError", "\n".join(captured.output))

    def test_http_error_status_logs_only_status_code(self):
        """HTTP-Fehler (z.B. 401 bei falschem Token) leakt nichts."""
        with mock.patch(
            "dca_bot.notifier.requests.post", return_value=FakeResponse(401)
        ):
            with self.assertLogs("dca_bot", level="ERROR") as captured:
                notifier.send_notification("[STOP-LOSS] Testnachricht")

        self._assert_no_secret_leaked(captured.output)
        self.assertIn("HTTP 401", "\n".join(captured.output))

    def test_unexpected_exception_type_also_sanitized(self):
        """
        Auch ein Fehler, der nicht von requests kommt (z.B. ein Bug im
        Aufruf selbst), darf nichts durchlassen - der except-Block fängt
        bewusst breit.
        """
        exc = ValueError(f"kaputter Aufruf gegen {FAKE_URL}")

        with mock.patch("dca_bot.notifier.requests.post", side_effect=exc):
            with self.assertLogs("dca_bot", level="ERROR") as captured:
                notifier.send_notification("[FEHLER] Testnachricht")

        self._assert_no_secret_leaked(captured.output)
        self.assertIn("ValueError", "\n".join(captured.output))

    def test_send_failure_never_raises(self):
        """
        Kernversprechen des Notifiers (siehe Docstring): ein
        fehlgeschlagener Versand darf einen Kaufzyklus nie abbrechen.
        """
        with mock.patch(
            "dca_bot.notifier.requests.post",
            side_effect=requests.exceptions.ReadTimeout("timeout"),
        ):
            with self.assertLogs("dca_bot", level="ERROR"):
                self.assertIsNone(notifier.send_notification("egal"))

        with mock.patch(
            "dca_bot.notifier.requests.post", return_value=FakeResponse(429)
        ):
            with self.assertLogs("dca_bot", level="ERROR"):
                self.assertIsNone(notifier.send_notification("egal"))

    def test_token_is_still_actually_used_in_request(self):
        """
        Gegenprobe zur Sanitisierung: der Token muss weiterhin in der
        echten Request-URL landen (sonst hätte man den Leak dadurch
        "behoben", dass der Versand gar nicht mehr funktioniert), und im
        Erfolgsfall darf trotzdem nichts geloggt werden.
        """
        with mock.patch(
            "dca_bot.notifier.requests.post", return_value=FakeResponse(200)
        ) as mock_post:
            with mock.patch.object(notifier.logger, "error") as mock_error:
                notifier.send_notification("[KAUF] Testnachricht")

        mock_error.assert_not_called()
        (called_url,), kwargs = mock_post.call_args
        self.assertEqual(called_url, FAKE_URL)
        self.assertEqual(kwargs["data"]["chat_id"], FAKE_CHAT_ID)
        self.assertEqual(kwargs["data"]["text"], "[KAUF] Testnachricht")

    def test_urllib3_debug_logging_cannot_leak_url(self):
        """
        urllib3 loggt die Request-Zeile (mit Token) auf DEBUG-Level.
        init() muss dieses Level anheben, damit ein späteres globales
        level=DEBUG den Token nicht wieder ins Log holt.
        """
        urllib3_logger = logging.getLogger("urllib3.connectionpool")
        original_level = urllib3_logger.level
        try:
            urllib3_logger.setLevel(logging.DEBUG)
            notifier.init(
                Config(
                    api_key="test",
                    api_secret="test",
                    telegram_bot_token=FAKE_TOKEN,
                    telegram_chat_id=FAKE_CHAT_ID,
                )
            )
            self.assertGreaterEqual(
                urllib3_logger.getEffectiveLevel(),
                logging.INFO,
                "urllib3 dürfte die Request-URL (mit Token) auf DEBUG loggen",
            )
        finally:
            urllib3_logger.setLevel(original_level)


if __name__ == "__main__":
    unittest.main()

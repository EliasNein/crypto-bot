"""
Tests für den Request-Timeout des Grid-Bots gegen die Binance-API.

Hintergrund: nächtliche Fehlalarme "HTTPSConnectionPool(host=
'testnet.binance.vision', ...): Read timed out" beim Grid-Bot, bei denen
das Testnet zwar noch antwortete, aber knapp langsamer als der
python-binance-Standard von 10 s (siehe trading-bot-projekt.md 6g). Der
Grid-Bot setzt deshalb 20 s, DCA, Trend und Allocator bleiben beim
Bibliotheks-Default.

Geprüft wird der Wert dort, wo er wirkt: am `requests`-Aufruf selbst.
Dafür läuft ein ECHTER `binance.client.Client` unter dem TradingClient,
nur `requests.Session.get` ist ersetzt - kein Netzwerkzugriff, aber auch
keine Annahme darüber, wie python-binance `requests_params` intern
verarbeitet. Ein Test, der nur prüft, dass `requests_params` übergeben
wurde, bliebe grün, falls ein Bibliotheks-Update den Parameter still
ignorierte.

Ausführen mit:  python -m unittest tests.test_request_timeout -v
"""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests
from binance.client import Client

from dca_bot import main as dca_main
from dca_bot import main_allocator, main_grid, main_trend
from dca_bot.binance_client import TradingClient
from dca_bot.config import Config
from dca_bot.grid_config import GridConfig


class _StopAfterClient(Exception):
    """Bricht main_grid.main() ab, sobald der Client angelegt werden soll."""


def _fake_response() -> mock.MagicMock:
    response = mock.MagicMock()
    response.status_code = 200
    # Eine Antwort für alle drei Endpunkte: ping ignoriert den Inhalt,
    # der Ticker liest "price", get_asset_balance liest "balances".
    response.json.return_value = {
        "price": "80000.00",
        "balances": [{"asset": "BTC", "free": "0.5", "locked": "0.0"}],
    }
    return response


class TradingClientRequestTimeoutTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config = Config(
            api_key="test",
            api_secret="test",
            pending_orders_file=str(Path(self._tmpdir.name) / "pending.json"),
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _timeouts_seen(self, **client_kwargs) -> list[tuple[str, object]]:
        """
        Baut einen TradingClient, setzt einen öffentlichen und einen
        signierten Request ab und liefert (URL, timeout) jedes
        `requests`-Aufrufs - inklusive des ping() aus dem Konstruktor.
        """
        seen: list[tuple[str, object]] = []

        def fake_get(session, url, **kwargs):
            seen.append((url, kwargs.get("timeout")))
            return _fake_response()

        with mock.patch.object(requests.Session, "get", autospec=True, side_effect=fake_get):
            client = TradingClient(self.config, **client_kwargs)
            client.get_current_price("BTCUSDT")
            client.get_asset_balance("BTC")
        return seen

    def test_grid_timeout_reaches_every_request(self):
        seen = self._timeouts_seen(request_timeout_seconds=20)

        urls = [url for url, _ in seen]
        # Prämisse: alle drei Wege sind tatsächlich gelaufen - sonst wäre
        # "jeder Request hat 20 s" auch bei einer leeren Liste wahr.
        self.assertTrue(any(url.endswith("/ping") for url in urls), urls)
        self.assertTrue(any("ticker/price" in url for url in urls), urls)
        self.assertTrue(any(url.endswith("/account") for url in urls), urls)

        for url, timeout in seen:
            with self.subTest(url=url):
                self.assertEqual(timeout, 20)

    def test_without_parameter_library_default_of_10_seconds_stays(self):
        """
        DCA, Trend und Allocator übergeben nichts - für sie muss alles
        beim Alten bleiben. Die 10 stehen hier bewusst als Zahl: sie sind
        die Prämisse der ganzen Änderung ("Standard-10-Sekunden").
        """
        self.assertEqual(Client.REQUEST_TIMEOUT, 10)

        seen = self._timeouts_seen()

        self.assertEqual(len(seen), 3, seen)
        for url, timeout in seen:
            with self.subTest(url=url):
                self.assertEqual(timeout, 10)


class GridEntryPointTimeoutTestCase(unittest.TestCase):
    """Die Verdrahtung: main_grid.main() legt den Client mit 20 s an."""

    def test_grid_main_instantiates_client_with_20_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = GridConfig(
                api_key="test",
                api_secret="test",
                state_file=str(Path(tmp) / "grid_positions.json"),
                stop_loss_state_file=str(Path(tmp) / "grid_stop_loss_paused.json"),
                pending_orders_file=str(Path(tmp) / "pending_orders_grid.json"),
                lock_file=str(Path(tmp) / "grid_bot.lock"),
                log_file=str(Path(tmp) / "grid_bot.log"),
            )
            with (
                mock.patch.object(main_grid, "load_grid_config", return_value=config),
                mock.patch.object(main_grid, "setup_logging"),
                mock.patch.object(main_grid, "ProcessLock"),
                mock.patch.object(
                    main_grid, "TradingClient", side_effect=_StopAfterClient
                ) as fake_client,
            ):
                with self.assertRaises(_StopAfterClient):
                    main_grid.main()

        fake_client.assert_called_once()
        _, kwargs = fake_client.call_args
        self.assertEqual(kwargs.get("request_timeout_seconds"), 20)
        self.assertEqual(main_grid.REQUEST_TIMEOUT_SECONDS, 20)

    def test_other_entry_points_keep_the_library_default(self):
        """
        Die Änderung ist bewusst auf den Grid-Bot beschränkt. Wird der
        Timeout später projektweit vereinheitlicht, ist dieser Test
        anzupassen - er soll dann auffallen, nicht still mitwandern.
        """
        for module in (dca_main, main_trend, main_allocator):
            with self.subTest(modul=module.__name__):
                self.assertNotIn("request_timeout_seconds", inspect.getsource(module.main))


if __name__ == "__main__":
    unittest.main()

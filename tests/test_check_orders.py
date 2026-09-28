"""
Tests fuer das Nachschlage-Werkzeug check_orders.py (Systemcheck vom
27.09.2026, W-E).

**Der Befund.** Die Eskalation bei einer Order mit unklarem Ausgang
(`[ORDER-UNKLAR]`) nennt eine clientOrderId, und die eine Frage danach
lautet: Gibt es diese Order bei Binance? Das alte Skript zeigte nur die
letzten 10 Orders des DCA-Symbols, ohne clientOrderId, und leitete Base-
und Quote-Asset per `symbol.replace("BTC", "")` ab.

**Wie getestet wird.** Unter dem ECHTEN TradingClient liegt ein
gefaelschter roher Binance-Client, derselbe Aufbau wie in
test_pending_orders.py. Gebaut wird der TradingClient mit derselben
Konfiguration, die das Skript benutzt (`_ReadOnlyClientConfig`), damit
auch die Nur-Lesend-Zusage am echten Objekt geprueft wird. Das Ergebnis
wird wie im Positions-Audit als Objekt geprueft (OrderLookup,
LocalBookkeeping), nicht aus gedrucktem Text zurueckgelesen - ausser dort,
wo die Ausgabe selbst die Aussage ist (keine Signatur im Text).

Kein Netzwerk, keine Zugangsdaten, temporaere Dateien.

Ausfuehren mit:  python -m unittest tests.test_check_orders -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from dca_bot import check_orders
from dca_bot.audit_positions import _ReadOnlyClientConfig
from dca_bot.binance_client import ORDER_DOES_NOT_EXIST_CODE, TradingClient
from dca_bot.check_orders import (
    EXIT_LOOKUP_FAILED,
    EXIT_OK,
    build_parser,
    check_local_bookkeeping,
    look_up,
    symbols_to_search,
    verdict,
)
from dca_bot.pending_orders import (
    LOOKUP_FAILED,
    LOOKUP_FOUND,
    LOOKUP_NOT_FOUND,
    PendingOrder,
    PendingOrderStore,
    lookup_command,
)

from tests.test_pending_orders import TradingClientTestBase, api_exception

GRID_ID = "grid-7f3a9c2e14b84d6fa0e51c83"
TREND_ID = "trend-0123456789abcdef01234567"
DCA_ID = "dca-aaaaaaaaaaaaaaaaaaaaaaaa"


class FakeRawClient:
    """
    Der rohe python-binance-Client unter dem TradingClient. `orders` bildet
    ab, was Binance kennt: {(symbol, clientOrderId): order}. Pro Symbol
    laesst sich ein Fehler fuer die Nachfrage einspielen.
    """

    def __init__(self) -> None:
        self.orders: dict[tuple[str, str], dict] = {}
        self.lookup_errors: dict[str, Exception] = {}
        self.get_order_calls: list[dict] = []
        self.balance_calls: list[str] = []
        self.all_orders_error: Exception | None = None
        self.recent: dict[str, list[dict]] = {}
        self.write_calls: list[str] = []

    def get_order(self, **params):
        self.get_order_calls.append(params)
        symbol = params["symbol"]
        if symbol in self.lookup_errors:
            raise self.lookup_errors[symbol]
        order = self.orders.get((symbol, params.get("origClientOrderId")))
        if order is None:
            raise api_exception(ORDER_DOES_NOT_EXIST_CODE, "Order does not exist.")
        return dict(order)

    def get_all_orders(self, **params):
        if self.all_orders_error is not None:
            raise self.all_orders_error
        return list(self.recent.get(params["symbol"], []))

    def get_symbol_info(self, symbol):
        base, quote = {"ETHBTC": ("ETH", "BTC")}.get(symbol, ("BTC", "USDT"))
        return {
            "baseAsset": base,
            "quoteAsset": quote,
            "quoteAssetPrecision": 8,
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "LOT_SIZE", "stepSize": "0.00001"},
                {"filterType": "NOTIONAL", "minNotional": "5.0"},
            ],
        }

    def get_symbol_ticker(self, symbol):
        return {"symbol": symbol, "price": "77000.00"}

    def get_asset_balance(self, asset):
        self.balance_calls.append(asset)
        return {"asset": asset, "free": "1.0", "locked": "0.0"}

    # Jede schreibende Methode wird mitgeschrieben - ein Aufruf waere der
    # Beweis, dass das Werkzeug doch Orders platzieren kann.
    def _write(self, name, **params):
        self.write_calls.append(name)
        raise AssertionError(f"schreibender Aufruf {name} im Nur-Lesend-Werkzeug")

    def order_market_buy(self, **params):
        return self._write("order_market_buy", **params)

    def order_market_sell(self, **params):
        return self._write("order_market_sell", **params)

    def create_order(self, **params):
        return self._write("create_order", **params)

    def cancel_order(self, **params):
        return self._write("cancel_order", **params)


def order(client_order_id, status="FILLED", executed="0.00019", order_id=4711, **extra):
    return {
        "orderId": order_id,
        "clientOrderId": client_order_id,
        "status": status,
        "side": "SELL",
        "type": "MARKET",
        "executedQty": executed,
        "origQty": "0.00019",
        "cummulativeQuoteQty": "14.63",
        "time": 1790000000000,
        **extra,
    }


class CheckOrdersTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        env = {
            "DCA_SYMBOL": "BTCUSDT",
            "GRID_SYMBOL": "ETHBTC",
            "TREND_SYMBOL": "BTCUSDT",
        }
        for bot, (pending_var, ledger_var) in {
            "dca": ("DCA_PENDING_ORDERS_FILE", "DCA_BOT_STATE_FILE"),
            "grid": ("GRID_PENDING_ORDERS_FILE", "GRID_STATE_FILE"),
            "trend": ("TREND_PENDING_ORDERS_FILE", "TREND_STATE_FILE"),
        }.items():
            env[pending_var] = str(self.dir / f"pending_{bot}.json")
            env[ledger_var] = str(self.dir / f"ledger_{bot}.json")
        self._env = mock.patch.dict(os.environ, env)
        self._env.start()

        with mock.patch("dca_bot.binance_client.Client"):
            self.client = TradingClient(
                _ReadOnlyClientConfig(api_key="k", api_secret="s", use_testnet=True)
            )
        self.raw = FakeRawClient()
        self.client._client = self.raw

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def write_ledger(self, bot: str, records: list[dict]) -> None:
        (self.dir / f"ledger_{bot}.json").write_text(json.dumps(records), encoding="utf-8")

    def add_pending(self, bot: str, client_order_id: str, symbol: str = "ETHBTC") -> None:
        store = PendingOrderStore(str(self.dir / f"pending_{bot}.json"), bot)
        store.add(
            PendingOrder(
                client_order_id=client_order_id,
                kind="market",
                symbol=symbol,
                side="SELL",
                created_at="2026-09-27T00:00:00+00:00",
                context={},
            )
        )

    def run_main(self, argv: list[str]) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch.object(
            check_orders, "_build_read_only_client", return_value=(self.client, None)
        ), contextlib.redirect_stdout(out):
            code = check_orders.main(argv)
        return code, out.getvalue()


class SymbolSelectionTestCase(CheckOrdersTestBase):
    """Binance braucht zum Nachschlagen das Symbol - woher es kommt."""

    def test_prefix_selects_the_bots_symbol(self):
        self.raw.orders[("ETHBTC", GRID_ID)] = order(GRID_ID)
        result = look_up(self.client, GRID_ID)

        self.assertEqual(result.bot, "grid")
        self.assertEqual(result.searched, ("ETHBTC",))
        self.assertEqual(result.lookup, LOOKUP_FOUND)
        self.assertEqual(
            self.raw.get_order_calls,
            [{"symbol": "ETHBTC", "origClientOrderId": GRID_ID}],
        )

    def test_unknown_prefix_searches_all_distinct_symbols(self):
        self.assertEqual(symbols_to_search("manuell-123", None), ["BTCUSDT", "ETHBTC"])

    def test_symbol_override_wins(self):
        self.assertEqual(symbols_to_search(GRID_ID, "SOLUSDT"), ["SOLUSDT"])

    def test_found_under_second_symbol(self):
        self.raw.orders[("ETHBTC", "manuell-1")] = order("manuell-1")
        result = look_up(self.client, "manuell-1")
        self.assertEqual(result.lookup, LOOKUP_FOUND)
        self.assertEqual(result.symbol, "ETHBTC")
        self.assertIsNone(result.bot)


class LookupOutcomeTestCase(CheckOrdersTestBase):
    """Dieselben drei Ausgaenge wie im Bot - nur -2013 heisst 'gibt es nicht'."""

    def test_not_found_without_a_known_symbol_is_no_statement(self):
        """
        Ersetzt den frueheren Test `test_not_found`, der "nie angenommen"
        auch ohne massgebliches Symbol festschrieb (Symbolbindung vom
        28.09.2026): Unter einem anderen Paar antwortet Binance ebenfalls
        mit -2013. Ohne --symbol und ohne Eintrag in der eigenen
        Buchhaltung sagt "nicht gefunden" deshalb nichts ueber die Order.
        """
        result = look_up(self.client, GRID_ID)
        self.assertEqual(result.lookup, LOOKUP_NOT_FOUND)
        self.assertEqual(result.searched, ("ETHBTC", "BTCUSDT"))
        text = verdict(result, None)
        self.assertNotIn("nie angenommen", text)
        self.assertIn("--symbol", text)

    def test_not_found_under_the_known_symbol_is_final(self):
        """Steht die Order in der Pending-Datei, ist deren Symbol massgeblich."""
        self.add_pending("grid", GRID_ID, symbol="ETHBTC")
        result = look_up(self.client, GRID_ID, None, check_orders.known_symbol("grid", GRID_ID))
        self.assertEqual(result.authoritative_symbol, "ETHBTC")
        self.assertIn("nie angenommen", verdict(result, None))
        self.assertIn("ETHBTC", verdict(result, None))

    def test_not_found_under_an_explicit_symbol_is_final(self):
        result = look_up(self.client, GRID_ID, "SOLUSDT")
        self.assertEqual(result.searched, ("SOLUSDT",))
        self.assertIn("nie angenommen", verdict(result, None))

    def test_failed_query_is_no_statement(self):
        self.raw.lookup_errors["ETHBTC"] = requests.exceptions.ConnectionError("weg")
        result = look_up(self.client, GRID_ID)
        self.assertEqual(result.lookup, LOOKUP_FAILED)
        self.assertIn("NICHTS", verdict(result, None))

    def test_one_failed_symbol_makes_not_found_impossible(self):
        """
        Unbekanntes Praefix: unter BTCUSDT 'nicht gefunden', unter ETHBTC
        gescheitert. Die Order kann genau unter ETHBTC liegen - das
        Ergebnis darf deshalb nicht 'nicht gefunden' sein.
        """
        self.raw.lookup_errors["ETHBTC"] = requests.exceptions.ReadTimeout("weg")
        self.assertEqual(look_up(self.client, "manuell-1").lookup, LOOKUP_FAILED)

    def test_counter_check_all_not_found(self):
        """Gegenprobe: ohne Fehler ergeben zwei Fehlanzeigen 'nicht gefunden'."""
        self.assertEqual(look_up(self.client, "manuell-1").lookup, LOOKUP_NOT_FOUND)

    def test_lifecycle_uses_the_bots_rule(self):
        """
        Die Einstufung kommt aus order_lifecycle_state(): EXPIRED mit
        ausgefuehrter Menge ist ausgefuehrt (nicht nur FILLED), ohne Menge
        ist es beendet ohne Wirkung, NEW ist aktiv.
        """
        for status, executed, expected in (
            ("EXPIRED", "0.00010", "Ausgeführt"),
            ("EXPIRED", "0", "kein Trade"),
            ("NEW", "0", "noch aktiv"),
        ):
            with self.subTest(status=status, executed=executed):
                self.raw.orders[("ETHBTC", GRID_ID)] = order(GRID_ID, status, executed)
                result = look_up(self.client, GRID_ID)
                local = check_local_bookkeeping("grid", GRID_ID, result.order)
                self.assertIn(expected, verdict(result, local))


class LocalBookkeepingTestCase(CheckOrdersTestBase):
    """Die eigentliche Antwort: ausgefuehrt - und auch verbucht?"""

    def _found(self, bot, client_order_id, symbol, **kwargs):
        self.raw.orders[(symbol, client_order_id)] = order(client_order_id, **kwargs)
        result = look_up(self.client, client_order_id)
        return result, check_local_bookkeeping(bot, client_order_id, result.order)

    def test_filled_pending_not_booked_is_left_to_the_bot(self):
        self.add_pending("grid", GRID_ID)
        result, local = self._found("grid", GRID_ID, "ETHBTC")

        self.assertTrue(local.in_pending)
        self.assertIsNone(local.ledger_field)
        self.assertIn("REKONZILIATION", verdict(result, local))

    def test_filled_and_booked_as_grid_sell(self):
        self.write_ledger("grid", [{"id": "p1", "sell_client_order_id": GRID_ID}])
        result, local = self._found("grid", GRID_ID, "ETHBTC")

        self.assertFalse(local.in_pending)
        self.assertEqual(local.ledger_field, "sell_client_order_id")
        self.assertIn("nichts zu tun", verdict(result, local))

    def test_filled_booked_and_still_pending(self):
        self.add_pending("grid", GRID_ID)
        self.write_ledger("grid", [{"id": "p1", "client_order_id": GRID_ID}])
        result, local = self._found("grid", GRID_ID, "ETHBTC")
        self.assertIn("räumt ihn auf", verdict(result, local))

    def test_filled_but_invisible_to_the_bot(self):
        """Weder Ledger noch Pending-Datei - der K2-Schaden."""
        self.write_ledger("grid", [{"id": "p1", "client_order_id": "grid-anders"}])
        result, local = self._found("grid", GRID_ID, "ETHBTC")
        self.assertIn("unsichtbar", verdict(result, local))

    def test_trend_exit_and_dca_buy_fields(self):
        self.write_ledger("trend", [{"id": "t1", "exit_client_order_id": TREND_ID}])
        self.write_ledger("dca", [{"client_order_id": DCA_ID}])
        _, trend_local = self._found("trend", TREND_ID, "BTCUSDT")
        _, dca_local = self._found("dca", DCA_ID, "BTCUSDT")
        self.assertEqual(trend_local.ledger_field, "exit_client_order_id")
        self.assertEqual(dca_local.ledger_field, "client_order_id")

    def test_trend_stop_order_matched_by_order_id(self):
        """Die Stop-Order steht im Trend-Ledger mit ihrer orderId."""
        self.write_ledger("trend", [{"id": "t1", "stop_loss_order_id": "9001"}])
        _, local = self._found("trend", TREND_ID, "BTCUSDT", order_id=9001, status="NEW", executed="0")
        self.assertEqual(local.ledger_field, "stop_loss_order_id")

    def test_unreadable_files_are_reported_not_guessed(self):
        (self.dir / "pending_grid.json").write_text("{kaputt", encoding="utf-8")
        (self.dir / "ledger_grid.json").write_text("[kaputt", encoding="utf-8")
        _, local = self._found("grid", GRID_ID, "ETHBTC")
        self.assertIsNone(local.in_pending)
        self.assertIn("nicht lesbar", local.ledger_error)


class MainTestCase(CheckOrdersTestBase):
    def test_lookup_exit_codes(self):
        self.raw.orders[("ETHBTC", GRID_ID)] = order(GRID_ID)
        code, out = self.run_main(["--client-order-id", GRID_ID])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("GEFUNDEN", out)

        self.raw.lookup_errors["ETHBTC"] = requests.exceptions.ConnectionError("weg")
        code, _ = self.run_main(["--client-order-id", GRID_ID])
        self.assertEqual(code, EXIT_LOOKUP_FAILED)

    def test_overview_shows_client_order_id_and_bot(self):
        self.raw.recent["ETHBTC"] = [order(GRID_ID)]
        self.raw.recent["BTCUSDT"] = [order(DCA_ID), order("web_manuell")]
        code, out = self.run_main([])

        self.assertEqual(code, EXIT_OK)
        self.assertIn(GRID_ID, out)
        # Die Bot-Spalte exakt pruefen - "grid" allein stuende schon in der
        # clientOrderId und waere deshalb immer enthalten.
        grid_line = next(line for line in out.splitlines() if GRID_ID in line)
        self.assertIn("| grid  |", grid_line)
        dca_line = next(line for line in out.splitlines() if DCA_ID in line)
        self.assertIn("| dca   |", dca_line)
        manual_line = next(line for line in out.splitlines() if "web_manuell" in line)
        self.assertIn("| -     |", manual_line)

    def test_assets_come_from_exchange_info_not_from_the_symbol_name(self):
        """
        `"ETHBTC".replace("BTC", "")` ergaebe "ETH" als Quote-Asset - falsch.
        Base und Quote kommen jetzt aus exchangeInfo.
        """
        self.run_main([])
        self.assertIn("ETH", self.raw.balance_calls)
        self.assertEqual(self.raw.balance_calls[:4], ["BTC", "USDT", "ETH", "BTC"])

    def test_no_request_url_or_signature_in_output(self):
        leak = requests.exceptions.ConnectionError(
            "https://testnet.binance.vision/api/v3/allOrders?symbol=BTCUSDT&signature=deadbeef"
        )
        self.raw.all_orders_error = leak
        self.raw.lookup_errors["ETHBTC"] = leak
        # Die Warnungen des Clients gehen ueber das Logging auf stderr -
        # auch dort darf die URL nicht landen.
        with self.assertLogs("dca_bot", level="WARNING") as logs:
            _, out1 = self.run_main([])
            _, out2 = self.run_main(["--client-order-id", GRID_ID])
        for out in (out1, out2, "\n".join(logs.output)):
            self.assertNotIn("signature", out)
            self.assertNotIn("deadbeef", out)
        self.assertTrue(any("ConnectionError" in line for line in logs.output))

    def test_tool_is_structurally_read_only(self):
        """
        Mit der Konfiguration des Werkzeugs kommt keine Order bei Binance
        an. Tatsaechlich scheitert der Aufruf schon eine Ebene VOR der
        Pending-Pruefung: `_ReadOnlyClientConfig` hat gar kein
        `trading_enabled`. Geprueft wird deshalb das Ergebnis (Ablehnung,
        kein roher Aufruf), nicht der Weg.
        """
        for call in (
            lambda: self.client.place_market_buy("BTCUSDT", 15.0),
            lambda: self.client.place_market_sell("BTCUSDT", 0.001),
        ):
            with self.assertRaises(Exception):
                call()
        self.assertEqual(self.raw.write_calls, [])

    def test_second_layer_rejects_without_pending_file(self):
        """
        Die zweite Ebene fuer sich: selbst mit `trading_enabled=True`
        lehnt der Client ohne Pending-Datei ab (ValueError), bevor etwas
        an Binance geht.
        """
        self.client._config = mock.Mock(
            trading_enabled=True, pending_orders_file="", bot_name="audit"
        )
        with mock.patch.object(
            self.client, "get_symbol_trading_rules",
            return_value=self.client.get_symbol_trading_rules("BTCUSDT"),
        ):
            with self.assertRaises(ValueError):
                self.client.place_market_sell("BTCUSDT", 0.001)
        self.assertEqual(self.raw.write_calls, [])


class PairSwitchTestCase(CheckOrdersTestBase):
    """
    check_orders ueber mehrere Paare (Symbolbindung vom 28.09.2026): Nach
    einem Paarwechsel liegen alte Orders unter dem alten Symbol. Gesucht
    wird zuerst unter dem Symbol aus der eigenen Buchhaltung, dann unter
    allen konfigurierten.
    """

    def setUp(self) -> None:
        super().setUp()
        os.environ["GRID_SYMBOL"] = "BTCEUR"

    def test_legacy_ledger_entry_points_to_the_old_pair(self):
        """
        Das Grid-Ledger fuehrt die Order als Altbestand ohne Feld - sie
        gilt als BTCUSDT und wird dort zuerst gesucht, obwohl GRID_SYMBOL
        inzwischen BTCEUR ist.
        """
        self.write_ledger("grid", [{"id": "p1", "client_order_id": GRID_ID}])
        self.raw.orders[("BTCUSDT", GRID_ID)] = order(GRID_ID)

        known = check_orders.known_symbol("grid", GRID_ID)
        result = look_up(self.client, GRID_ID, None, known)

        self.assertEqual(known, "BTCUSDT")
        self.assertEqual(result.lookup, LOOKUP_FOUND)
        self.assertEqual(result.symbol, "BTCUSDT")
        self.assertEqual(result.searched, ("BTCUSDT",))

    def test_without_bookkeeping_all_configured_pairs_are_searched(self):
        """Nichts in der eigenen Buchhaltung: erst das Paar des Bots, dann die uebrigen."""
        self.raw.orders[("BTCUSDT", GRID_ID)] = order(GRID_ID)
        result = look_up(self.client, GRID_ID)
        self.assertEqual(result.searched, ("BTCEUR", "BTCUSDT"))
        self.assertEqual(result.symbol, "BTCUSDT")

    def test_a_pair_that_is_nowhere_configured_is_not_claimed_as_never_accepted(self):
        """
        Die Order liegt unter einem Paar, das keine Konfiguration mehr
        nennt. "Nicht gefunden" darf dann nicht als "nie angenommen"
        erscheinen - genau die Falschaussage aus dem Audit.
        """
        self.raw.orders[("SOLUSDT", GRID_ID)] = order(GRID_ID)
        code, out = self.run_main(["--client-order-id", GRID_ID])
        self.assertEqual(code, EXIT_OK)
        self.assertNotIn("nie angenommen", out)
        self.assertIn("--symbol", out)

        code, out = self.run_main(["--client-order-id", GRID_ID, "--symbol", "SOLUSDT"])
        self.assertIn("GEFUNDEN unter SOLUSDT", out)

    def test_main_uses_the_pending_entry_symbol(self):
        self.add_pending("grid", GRID_ID, symbol="BTCUSDT")
        self.raw.orders[("BTCUSDT", GRID_ID)] = order(GRID_ID)
        code, out = self.run_main(["--client-order-id", GRID_ID])
        self.assertIn("GEFUNDEN unter BTCUSDT", out)
        self.assertEqual(self.raw.get_order_calls[0]["symbol"], "BTCUSDT")


class FakeExchangeLookupTestCase(unittest.TestCase):
    """
    Dasselbe gegen den symbolbewussten FakeExchange (tests/test_shared_account.py):
    Eine Order, die ueber BTCUSDT lief, ist unter BTCEUR unbekannt (-2013) -
    so wie bei Binance. Genau darauf beruht die Regel in verdict().
    """

    def test_an_order_is_only_known_under_its_own_pair(self):
        from tests.test_shared_account import FakeExchange

        exchange = FakeExchange(50_000.0)
        exchange.order_market_buy("BTCUSDT", 100.0, "grid-alt-paar")
        with mock.patch("dca_bot.binance_client.Client"):
            client = TradingClient(
                _ReadOnlyClientConfig(api_key="k", api_secret="s", use_testnet=True)
            )
        client._client = exchange

        with self.assertLogs("dca_bot", level="INFO"):
            self.assertEqual(
                client.get_order_by_client_id("BTCEUR", "grid-alt-paar")[0], LOOKUP_NOT_FOUND
            )
        with mock.patch.dict(os.environ, {"GRID_SYMBOL": "BTCEUR", "DCA_SYMBOL": "BTCEUR",
                                          "TREND_SYMBOL": "BTCEUR"}):
            result = look_up(client, "grid-alt-paar")
            self.assertEqual(result.lookup, LOOKUP_NOT_FOUND)
            self.assertNotIn("nie angenommen", verdict(result, None))
            found = look_up(client, "grid-alt-paar", "BTCUSDT")
        self.assertEqual(found.lookup, LOOKUP_FOUND)


class OrderUnclearHintTestCase(TradingClientTestBase):
    """Die [ORDER-UNKLAR]-Meldung nennt den fertigen Aufruf."""

    def test_command_parses_with_the_tools_own_parser(self):
        args = build_parser().parse_args(lookup_command(GRID_ID).split()[3:])
        self.assertEqual(args.client_order_id, GRID_ID)
        self.assertTrue(lookup_command(GRID_ID).startswith("python -m dca_bot.check_orders "))

    def test_order_unclear_message_contains_the_lookup_command(self):
        client, raw = self._make_client()
        raw.order_behaviour = requests.exceptions.ReadTimeout("weg")
        raw.status_behaviour = requests.exceptions.ReadTimeout("auch weg")

        with mock.patch("dca_bot.binance_client.send_notification") as notify:
            with self.assertLogs("dca_bot", level="ERROR") as captured:
                client.place_market_buy("BTCUSDT", 15.0)

        client_order_id = raw.placed_client_order_ids[0]
        self.assertIn(lookup_command(client_order_id), notify.call_args.args[0])
        self.assertTrue(
            any(lookup_command(client_order_id) in line for line in captured.output)
        )


if __name__ == "__main__":
    unittest.main()

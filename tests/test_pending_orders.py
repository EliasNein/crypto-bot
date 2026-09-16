"""
Tests fuer die idempotente Order-Platzierung (Sicherheitsreview-Punkt
K2), Teil 1: das Fundament in dca_bot/pending_orders.py.

Abgedeckt sind hier die drei Bausteine, die ohne Binance-Client
auskommen:

- `new_client_order_id()` - inklusive der Laengengrenze, an der eine
  naive Umsetzung ("trend-" + vollstaendiger uuid4-Hex = 38 Zeichen)
  live scheitern wuerde, auf dem Testnet aber je nach Stand nicht.
- `PendingOrderStore` - schreiben/lesen/entfernen, Verhalten bei
  fehlender oder beschaedigter Datei, atomares Schreiben.
- `classify_order_status()` / `resolve_pending_order()` - die Bewertung
  eines Order-Status, die zur Laufzeit UND beim Bot-Start dieselbe sein
  muss.

Die Netzwerkfehler-Szenarien des TradingClients stehen weiter unten in
dieser Datei; die Reconciliation der einzelnen Bots beim Start liegt in
tests/test_order_reconciliation.py.

Kein Netzwerk, keine Zugangsdaten, temporaere Dateien.

Ausfuehren mit:  python -m unittest tests.test_pending_orders -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests
from binance.exceptions import BinanceAPIException

from dca_bot.binance_client import ORDER_DOES_NOT_EXIST_CODE, TradingClient
from dca_bot.config import Config
from dca_bot.pending_orders import (
    KIND_MARKET,
    KIND_STOP_LOSS_LIMIT,
    LOOKUP_FAILED,
    LOOKUP_FOUND,
    LOOKUP_NOT_FOUND,
    MAX_CLIENT_ORDER_ID_LENGTH,
    ORDER_CONFIRMED,
    ORDER_UNCLEAR,
    ORDER_UNKNOWN,
    ORDER_WITHOUT_EFFECT,
    PendingOrder,
    PendingOrderStore,
    classify_order_status,
    new_client_order_id,
    resolve_pending_order,
)


class FakeLookupClient:
    """
    Minimaler Ersatz fuer den TradingClient: bietet nur
    get_order_by_client_id() an, das Einzige, was
    resolve_pending_order() braucht.
    """

    def __init__(self, result: tuple[str, dict | None]):
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def get_order_by_client_id(self, symbol: str, client_order_id: str):
        self.calls.append((symbol, client_order_id))
        return self.result


class ClientOrderIdTestCase(unittest.TestCase):
    def test_has_bot_prefix(self):
        self.assertTrue(new_client_order_id("grid").startswith("grid-"))

    def test_ids_are_unique(self):
        ids = {new_client_order_id("dca") for _ in range(500)}
        self.assertEqual(len(ids), 500)

    def test_stays_within_binance_length_limit(self):
        """
        Binance begrenzt newClientOrderId auf 36 Zeichen. "trend-" plus
        vollstaendiger uuid4-Hex waeren 38 - die Order wuerde live
        abgelehnt. Fuer alle real verwendeten Praefixe muss die ID
        deshalb sicher unter der Grenze bleiben.
        """
        for bot_name in ("dca", "grid", "trend"):
            with self.subTest(bot_name=bot_name):
                order_id = new_client_order_id(bot_name)
                self.assertLessEqual(len(order_id), MAX_CLIENT_ORDER_ID_LENGTH)

    def test_rejects_bot_name_that_would_produce_invalid_id(self):
        """
        Ein zu langer oder mit unerlaubten Zeichen versehener bot_name
        soll hier scheitern - nicht erst als abgelehnte Order bei der
        Boerse, wo bereits ein Kaufzyklus daran haengt.
        """
        with self.assertRaises(ValueError):
            new_client_order_id("x" * 40)
        with self.assertRaises(ValueError):
            new_client_order_id("bot mit leerzeichen")


class PendingOrderStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "nested" / "pending_orders_grid.json"
        self.store = PendingOrderStore(str(self.path), bot_name="grid")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_pending(self, client_order_id: str = "grid-abc") -> PendingOrder:
        return PendingOrder.new(
            client_order_id=client_order_id,
            kind=KIND_MARKET,
            symbol="BTCUSDT",
            side="BUY",
            context={"level_index": 3, "price": 77_000.0},
        )

    def test_missing_file_reads_as_empty(self):
        self.assertFalse(self.path.exists())
        self.assertEqual(self.store.all(), [])

    def test_add_and_read_back_roundtrip(self):
        self.store.add(self._make_pending())

        entries = self.store.all()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].client_order_id, "grid-abc")
        self.assertEqual(entries[0].kind, KIND_MARKET)
        self.assertEqual(entries[0].side, "BUY")
        # Der Kontext ist fuer den Store opak und muss unveraendert
        # zurueckkommen - die Strategie braucht ihn zum Nachtragen.
        self.assertEqual(entries[0].context, {"level_index": 3, "price": 77_000.0})

    def test_file_layout_has_version_and_bot(self):
        self.store.add(self._make_pending())

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["bot"], "grid")
        self.assertEqual(len(payload["orders"]), 1)

    def test_remove_deletes_only_the_matching_entry(self):
        self.store.add(self._make_pending("grid-one"))
        self.store.add(self._make_pending("grid-two"))

        self.store.remove("grid-one")

        remaining = [e.client_order_id for e in self.store.all()]
        self.assertEqual(remaining, ["grid-two"])

    def test_remove_of_unknown_id_is_a_no_op(self):
        self.store.add(self._make_pending("grid-one"))
        self.store.remove("grid-does-not-exist")
        self.assertEqual(len(self.store.all()), 1)

    def test_no_temp_file_is_left_behind(self):
        """
        Geschrieben wird ueber eine temporaere Datei plus os.replace -
        danach darf im data-Verzeichnis nichts uebrig bleiben, was ein
        Backup- oder Audit-Skript verwirren koennte.
        """
        self.store.add(self._make_pending())
        leftovers = [p.name for p in self.path.parent.iterdir() if p.suffix == ".tmp"]
        self.assertEqual(leftovers, [])

    def test_corrupt_file_is_treated_as_empty_with_warning(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{kein gueltiges json", encoding="utf-8")

        with self.assertLogs("dca_bot", level="WARNING") as captured:
            entries = self.store.all()

        self.assertEqual(entries, [])
        self.assertTrue(any("beschaedigt" in line for line in captured.output))

    def test_unexpected_format_is_treated_as_empty(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text('["eine nackte liste"]', encoding="utf-8")

        with self.assertLogs("dca_bot", level="WARNING"):
            self.assertEqual(self.store.all(), [])

    def test_foreign_bot_file_is_flagged_but_still_read(self):
        """
        Vertauschte Pfade in der .env duerfen nicht dazu fuehren, dass
        echte offene Order-Fragen stillschweigend ignoriert werden -
        also warnen, aber trotzdem liefern.
        """
        self.store.add(self._make_pending())
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["bot"] = "trend"
        self.path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertLogs("dca_bot", level="WARNING") as captured:
            entries = self.store.all()

        self.assertEqual(len(entries), 1)
        self.assertTrue(any("PENDING_ORDERS_FILE" in line for line in captured.output))

    def test_broken_single_entry_is_skipped(self):
        self.store.add(self._make_pending("grid-good"))
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["orders"].append({"kaputt": True})
        self.path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertLogs("dca_bot", level="WARNING"):
            entries = self.store.all()

        self.assertEqual([e.client_order_id for e in entries], ["grid-good"])


class ClassifyOrderStatusTestCase(unittest.TestCase):
    """
    Die Bewertungsregel selbst - rein, ohne Client. Sie ist der Kern von
    K2: davon haengt ab, ob ein Ledger-Eintrag nachgetragen, verworfen
    oder eskaliert wird.
    """

    def test_filled_market_order_is_confirmed(self):
        order = {"status": "FILLED", "executedQty": "0.0002"}
        self.assertEqual(classify_order_status(order, KIND_MARKET), ORDER_CONFIRMED)

    def test_expired_market_order_with_partial_fill_is_confirmed(self):
        """
        Abweichung von "nur FILLED zaehlt": eine Market-Order, die nicht
        vollstaendig gefuellt werden kann, endet bei Binance als EXPIRED
        mit einer echten Teilmenge. Die wurde real gekauft und gehoert
        ins Ledger - sie fuer immer als "unklar" zu fuehren, waere
        falsch.
        """
        order = {"status": "EXPIRED", "executedQty": "0.00005"}
        self.assertEqual(classify_order_status(order, KIND_MARKET), ORDER_CONFIRMED)

    def test_terminal_market_order_without_fill_has_no_effect(self):
        for status in ("CANCELED", "EXPIRED", "REJECTED", "EXPIRED_IN_MATCH"):
            with self.subTest(status=status):
                order = {"status": status, "executedQty": "0"}
                self.assertEqual(
                    classify_order_status(order, KIND_MARKET), ORDER_WITHOUT_EFFECT
                )

    def test_live_market_order_is_unclear(self):
        """
        Eine Market-Order, die laut Boerse noch NEW ist - unwahrschein-
        lich, aber moeglich. Hier wird bewusst nicht geraten.
        """
        for status in ("NEW", "PARTIALLY_FILLED"):
            with self.subTest(status=status):
                order = {"status": status, "executedQty": "0"}
                self.assertEqual(classify_order_status(order, KIND_MARKET), ORDER_UNCLEAR)

    def test_unreadable_executed_qty_does_not_raise(self):
        order = {"status": "FILLED", "executedQty": "keine zahl"}
        with self.assertLogs("dca_bot", level="WARNING"):
            self.assertEqual(
                classify_order_status(order, KIND_MARKET), ORDER_WITHOUT_EFFECT
            )

    # -- Stop-Loss-Orders folgen einer anderen Regel --

    def test_new_stop_order_is_confirmed(self):
        """
        Kern der Sonderbehandlung: eine frisch platzierte Stop-Order SOLL
        offen im Orderbuch liegen. "NEW" ist hier der Erfolgsfall, nicht
        ein unklarer Zwischenzustand.
        """
        order = {"status": "NEW", "executedQty": "0"}
        self.assertEqual(
            classify_order_status(order, KIND_STOP_LOSS_LIMIT), ORDER_CONFIRMED
        )

    def test_filled_stop_order_is_confirmed(self):
        """
        Auch eine bereits ausgeloeste Stop-Order existiert - sie gehoert
        ins Ledger zurueck, damit der bestehende Weg ueber
        reconcile_on_startup() den Exit erkennt.
        """
        order = {"status": "FILLED", "executedQty": "0.0002"}
        self.assertEqual(
            classify_order_status(order, KIND_STOP_LOSS_LIMIT), ORDER_CONFIRMED
        )

    def test_canceled_stop_order_has_no_effect(self):
        order = {"status": "CANCELED", "executedQty": "0"}
        self.assertEqual(
            classify_order_status(order, KIND_STOP_LOSS_LIMIT), ORDER_WITHOUT_EFFECT
        )

    def test_market_and_stop_orders_disagree_on_new(self):
        """
        Die beiden Regeln muessen sich bei "NEW" bewusst unterscheiden -
        diese Gegenprobe haelt fest, dass das kein Versehen ist.
        """
        order = {"status": "NEW", "executedQty": "0"}
        self.assertEqual(classify_order_status(order, KIND_MARKET), ORDER_UNCLEAR)
        self.assertEqual(
            classify_order_status(order, KIND_STOP_LOSS_LIMIT), ORDER_CONFIRMED
        )


class ResolvePendingOrderTestCase(unittest.TestCase):
    def _pending(self, kind: str = KIND_MARKET) -> PendingOrder:
        return PendingOrder.new(
            client_order_id="dca-abc", kind=kind, symbol="BTCUSDT", side="BUY"
        )

    def test_found_and_filled(self):
        client = FakeLookupClient((LOOKUP_FOUND, {"status": "FILLED", "executedQty": "1"}))
        state, order = resolve_pending_order(client, self._pending())
        self.assertEqual(state, ORDER_CONFIRMED)
        self.assertIsNotNone(order)
        self.assertEqual(client.calls, [("BTCUSDT", "dca-abc")])

    def test_not_found_means_never_accepted(self):
        client = FakeLookupClient((LOOKUP_NOT_FOUND, None))
        state, order = resolve_pending_order(client, self._pending())
        self.assertEqual(state, ORDER_UNKNOWN)
        self.assertIsNone(order)

    def test_failed_lookup_is_unclear(self):
        """
        Die Status-Abfrage selbst schlaegt fehl - daraus folgt NICHTS
        ueber die Order. Der Fall muss unklar bleiben, damit der
        Pending-Eintrag stehen bleibt und beim naechsten Start erneut
        geprueft wird.
        """
        client = FakeLookupClient((LOOKUP_FAILED, None))
        state, order = resolve_pending_order(client, self._pending())
        self.assertEqual(state, ORDER_UNCLEAR)
        self.assertIsNone(order)

    def test_kind_is_passed_through_to_the_classification(self):
        client = FakeLookupClient((LOOKUP_FOUND, {"status": "NEW", "executedQty": "0"}))

        market_state, _ = resolve_pending_order(client, self._pending(KIND_MARKET))
        stop_state, _ = resolve_pending_order(client, self._pending(KIND_STOP_LOSS_LIMIT))

        self.assertEqual(market_state, ORDER_UNCLEAR)
        self.assertEqual(stop_state, ORDER_CONFIRMED)


# ---------------------------------------------------------------------------
# Teil A: der TradingClient selbst - Netzwerkfehler bei der Order-Platzierung
# ---------------------------------------------------------------------------


def api_exception(code: int, message: str) -> BinanceAPIException:
    """Baut eine echte BinanceAPIException mit gesetztem `code`."""
    return BinanceAPIException(None, 400, json.dumps({"code": code, "msg": message}))


class FakeRawBinanceClient:
    """
    Steht an der Stelle des `binance.client.Client` INNERHALB des
    TradingClients - also eine Ebene tiefer als die Fake-Clients in den
    uebrigen Testdateien, die den TradingClient als Ganzes ersetzen.

    Nur so lassen sich die K2-Szenarien ueberhaupt pruefen: Der Fehler
    entsteht in genau der Zeile, in der python-binance seinen Request
    absetzt, und die Behandlung dieses Fehlers IST der Fix.
    """

    def __init__(self, price: float = 77_000.0):
        self.price = price
        self.placed_client_order_ids: list[str] = []
        self.get_order_calls: list[dict] = []
        self.my_trades_calls: list[dict] = []

        # Was die Order-Platzierung tun soll: "ok" oder eine
        # Exception-Instanz, die geworfen wird.
        self.order_behaviour: object = "ok"
        # Was get_order() tun soll: "found" | "not_found" | Exception.
        self.status_behaviour: object = "found"
        # Status, den get_order() im Fall "found" meldet.
        self.status_payload = {"status": "FILLED", "executedQty": "0.00019480"}
        self.my_trades_result: object = []

    # -- Order-Platzierung --

    def _record_and_maybe_fail(self, params: dict) -> None:
        self.placed_client_order_ids.append(params.get("newClientOrderId"))
        if isinstance(self.order_behaviour, Exception):
            raise self.order_behaviour

    def order_market_buy(self, **params):
        self._record_and_maybe_fail(params)
        executed_qty = params["quoteOrderQty"] / self.price
        return self._order_response(params, executed_qty, params["quoteOrderQty"])

    def order_market_sell(self, **params):
        self._record_and_maybe_fail(params)
        quantity = params["quantity"]
        return self._order_response(params, quantity, quantity * self.price)

    def create_order(self, **params):
        self._record_and_maybe_fail(params)
        return {
            "orderId": 4712,
            "clientOrderId": params.get("newClientOrderId"),
            "status": "NEW",
            "executedQty": "0",
            "cummulativeQuoteQty": "0",
        }

    def _order_response(self, params: dict, executed_qty: float, quote: float) -> dict:
        return {
            "orderId": 4711,
            "clientOrderId": params.get("newClientOrderId"),
            "status": "FILLED",
            "executedQty": executed_qty,
            "cummulativeQuoteQty": quote,
            "fills": [
                {
                    "price": self.price,
                    "qty": executed_qty,
                    "commission": 0.0,
                    "commissionAsset": "BTC",
                }
            ],
        }

    # -- Ground-Truth-Rueckfrage --

    def get_order(self, **params):
        self.get_order_calls.append(params)
        if isinstance(self.status_behaviour, Exception):
            raise self.status_behaviour
        if self.status_behaviour == "not_found":
            raise api_exception(ORDER_DOES_NOT_EXIST_CODE, "Order does not exist.")
        return {
            "orderId": 4711,
            "clientOrderId": params.get("origClientOrderId"),
            "cummulativeQuoteQty": "15.0",
            **self.status_payload,
        }

    def get_my_trades(self, **params):
        self.my_trades_calls.append(params)
        if isinstance(self.my_trades_result, Exception):
            raise self.my_trades_result
        return self.my_trades_result

    # -- Handelsregeln --

    def get_symbol_info(self, symbol):
        return {
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "quoteAssetPrecision": 8,
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "LOT_SIZE", "stepSize": "0.00001"},
                {"filterType": "NOTIONAL", "minNotional": "5.0"},
            ],
        }


class TradingClientTestBase(unittest.TestCase):
    """
    Baut einen ECHTEN TradingClient mit gefaelschtem rohen
    Binance-Client darunter. Der Konstruktor des echten
    `binance.client.Client` wird dabei weggepatcht - er wuerde die
    Boerse kontaktieren.
    """

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.pending_file = str(Path(self._tmpdir.name) / "pending_orders_dca.json")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_client(
        self, trading_enabled: bool = True, pending_file: str | None = None
    ) -> tuple[TradingClient, FakeRawBinanceClient]:
        config = Config(
            api_key="test",
            api_secret="test",
            trading_enabled=trading_enabled,
            bot_name="dca",
            pending_orders_file=(
                self.pending_file if pending_file is None else pending_file
            ),
        )
        with mock.patch("dca_bot.binance_client.Client"):
            client = TradingClient(config)
        raw = FakeRawBinanceClient()
        client._client = raw
        return client, raw

    def _pending_ids(self) -> list[str]:
        store = PendingOrderStore(self.pending_file, bot_name="dca")
        return [e.client_order_id for e in store.all()]


class TradingClientPendingOrderTestCase(TradingClientTestBase):
    """Die drei geforderten K2-Szenarien plus die Abgrenzungen."""

    # -- Normalbetrieb --

    def test_successful_order_sends_client_order_id_and_clears_pending(self):
        client, raw = self._make_client()

        order = client.place_market_buy("BTCUSDT", 15.0)

        self.assertIsNotNone(order)
        sent_id = raw.placed_client_order_ids[0]
        self.assertTrue(sent_id.startswith("dca-"), sent_id)
        self.assertEqual(self._pending_ids(), [], "Pending-Eintrag muss weg sein")

    def test_dry_run_writes_no_pending_entry(self):
        """
        Im Dry-Run existiert keine Order - also darf auch keine offene
        Order-Frage entstehen, die beim naechsten Start geprueft wird.
        """
        client, raw = self._make_client(trading_enabled=False)

        self.assertIsNone(client.place_market_buy("BTCUSDT", 15.0))
        self.assertEqual(raw.placed_client_order_ids, [])
        self.assertEqual(self._pending_ids(), [])

    def test_rejected_order_clears_pending_without_status_query(self):
        """
        Eine BinanceAPIException bedeutet: die Boerse HAT geantwortet und
        die Order abgelehnt. Das ist ein definitives Nein - es muss
        weder nachgefragt noch ein Eintrag aufgehoben werden.
        """
        client, raw = self._make_client()
        raw.order_behaviour = api_exception(-2010, "Account has insufficient balance.")

        with self.assertLogs("dca_bot", level="ERROR"):
            self.assertIsNone(client.place_market_buy("BTCUSDT", 15.0))

        self.assertEqual(raw.get_order_calls, [], "Keine Rueckfrage noetig")
        self.assertEqual(self._pending_ids(), [])

    def test_pending_entry_exists_while_the_request_is_in_flight(self):
        """
        Der eigentliche Kern des Fixes: der Eintrag muss BEREITS auf
        Platte liegen, waehrend der Request laeuft - nur so ueberlebt er
        einen Prozess-Kill mitten im Netzwerk-Call. Geprueft, indem der
        gefaelschte Client waehrend des Requests selbst nachsieht.
        """
        client, raw = self._make_client()
        seen_during_request: list[list[str]] = []

        original = raw.order_market_buy

        def spy(**params):
            seen_during_request.append(self._pending_ids())
            return original(**params)

        raw.order_market_buy = spy
        client.place_market_buy("BTCUSDT", 15.0, context={"quelle": "test"})

        self.assertEqual(len(seen_during_request[0]), 1)
        self.assertEqual(seen_during_request[0], raw.placed_client_order_ids)

    def test_context_is_persisted_with_the_pending_entry(self):
        """
        Der Kontext ist fuer den Client opak, muss aber unveraendert in
        der Datei landen - die Reconciliation braucht ihn spaeter zum
        Nachtragen.
        """
        client, raw = self._make_client()
        raw.order_behaviour = requests.exceptions.ReadTimeout("weg")
        raw.status_behaviour = requests.exceptions.ReadTimeout("auch weg")

        with mock.patch("dca_bot.binance_client.send_notification"):
            with self.assertLogs("dca_bot", level="ERROR"):
                client.place_market_buy(
                    "BTCUSDT", 15.0, context={"level_index": 3, "price": 77_000.0}
                )

        store = PendingOrderStore(self.pending_file, bot_name="dca")
        entry = store.all()[0]
        self.assertEqual(entry.context, {"level_index": 3, "price": 77_000.0})
        self.assertEqual(entry.side, "BUY")
        self.assertEqual(entry.kind, KIND_MARKET)

    # -- Szenario 1: Netzwerkfehler, Order laut Nachfrage ausgefuehrt --

    def test_network_error_but_order_was_filled_returns_real_order(self):
        """
        Das Kernszenario von K2: Die Order geht raus, Binance fuellt sie,
        die Antwort erreicht den Bot nicht. Vorher flog hier eine
        ungefangene Exception und der Trade blieb unverbucht - jetzt
        kommen die echten Order-Daten zurueck, als waere der Aufruf
        geglueckt, und die Strategie schreibt ihren Ledger-Eintrag ganz
        normal.
        """
        client, raw = self._make_client()
        raw.order_behaviour = requests.exceptions.ReadTimeout("Verbindung abgebrochen")

        with mock.patch("dca_bot.binance_client.send_notification") as notify:
            with self.assertLogs("dca_bot", level="WARNING") as captured:
                order = client.place_market_buy("BTCUSDT", 15.0)

        self.assertIsNotNone(order)
        self.assertEqual(order["status"], "FILLED")
        # Nachgefragt wurde ueber die selbstvergebene ID - eine orderId
        # hat der Bot in diesem Fall nie zu sehen bekommen.
        self.assertEqual(
            raw.get_order_calls[0]["origClientOrderId"], raw.placed_client_order_ids[0]
        )
        self.assertEqual(self._pending_ids(), [])
        notify.assert_not_called()
        self.assertTrue(
            any("trotz des Verbindungsfehlers" in line for line in captured.output)
        )

    def test_network_error_on_sell_is_resolved_the_same_way(self):
        """
        Gleiche Absicherung auf der Verkaufsseite: ein unverbuchter
        Verkauf wuerde die Position als weiter offen fuehren und im
        naechsten Zyklus ein ZWEITES Mal verkauft.
        """
        client, raw = self._make_client()
        raw.order_behaviour = requests.exceptions.ConnectionError("weg")
        raw.status_payload = {"status": "FILLED", "executedQty": "0.0002"}

        with mock.patch("dca_bot.binance_client.send_notification"):
            with self.assertLogs("dca_bot", level="WARNING"):
                order = client.place_market_sell("BTCUSDT", 0.0002)

        self.assertIsNotNone(order)
        self.assertEqual(self._pending_ids(), [])

    def test_network_error_on_stop_order_accepts_status_new(self):
        """
        Die Sonderregel fuer Stop-Orders im Zusammenspiel: nach einem
        Verbindungsfehler meldet die Boerse "NEW" - fuer eine Stop-Order
        ist das der Erfolgsfall, die Order liegt im Orderbuch. Sie muss
        zurueckgegeben werden, damit ihre ID im Ledger landet und nicht
        gleich eine zweite Order ueber dieselbe Menge entsteht.
        """
        client, raw = self._make_client()
        raw.order_behaviour = requests.exceptions.ConnectionError("weg")
        raw.status_payload = {"status": "NEW", "executedQty": "0"}

        with mock.patch("dca_bot.binance_client.send_notification") as notify:
            with self.assertLogs("dca_bot", level="WARNING"):
                order = client.place_stop_loss_limit_sell(
                    "BTCUSDT", 0.0002, 69_300.0, 68_953.5
                )

        self.assertIsNotNone(order)
        self.assertEqual(self._pending_ids(), [])
        notify.assert_not_called()

    # -- Szenario 2: Netzwerkfehler, Order nie angekommen --

    def test_network_error_and_order_unknown_is_treated_as_no_trade(self):
        """
        Binance kennt die clientOrderId nicht (-2013) - die Order wurde
        nie angenommen. Sauber als "kein Kauf" behandeln: None zurueck,
        kein Ledger-Eintrag, keine Eskalation, Pending-Eintrag weg.
        """
        client, raw = self._make_client()
        raw.order_behaviour = requests.exceptions.ConnectionError("weg")
        raw.status_behaviour = "not_found"

        with mock.patch("dca_bot.binance_client.send_notification") as notify:
            with self.assertLogs("dca_bot", level="WARNING") as captured:
                order = client.place_market_buy("BTCUSDT", 15.0)

        self.assertIsNone(order)
        self.assertEqual(self._pending_ids(), [])
        notify.assert_not_called()
        self.assertTrue(
            any("nicht wirksam erreicht" in line for line in captured.output)
        )

    # -- Szenario 3: Netzwerkfehler UND Status-Abfrage scheitert --

    def test_network_error_and_failed_status_query_escalates_and_keeps_entry(self):
        """
        Der unklare Zustand: weder die Order noch die Nachfrage kamen
        durch. Hier wird bewusst NICHT geraten - stattdessen ERROR-Log,
        Telegram, und die clientOrderId BLEIBT in der Pending-Datei
        stehen, damit der naechste Bot-Start erneut fragt.
        """
        client, raw = self._make_client()
        raw.order_behaviour = requests.exceptions.ReadTimeout("weg")
        raw.status_behaviour = requests.exceptions.ReadTimeout("auch weg")

        with mock.patch("dca_bot.binance_client.send_notification") as notify:
            with self.assertLogs("dca_bot", level="ERROR") as captured:
                order = client.place_market_buy("BTCUSDT", 15.0)

        self.assertIsNone(order)

        remaining = self._pending_ids()
        self.assertEqual(remaining, [raw.placed_client_order_ids[0]])

        self.assertTrue(
            any("UNKLARER ORDER-ZUSTAND" in line for line in captured.output)
        )
        notify.assert_called_once()
        self.assertIn("[ORDER-UNKLAR]", notify.call_args.args[0])
        self.assertIn(remaining[0], notify.call_args.args[0])

    def test_unrelated_api_error_during_status_query_is_not_treated_as_missing(self):
        """
        Abgrenzung zu Szenario 2: ein Rate-Limit-Fehler (-1003) ist KEINE
        Aussage darueber, ob die Order existiert. Er darf deshalb nicht
        als "nie passiert" durchgehen, sondern muss eskalieren.
        """
        client, raw = self._make_client()
        raw.order_behaviour = requests.exceptions.ConnectionError("weg")
        raw.status_behaviour = api_exception(-1003, "Too much request weight used.")

        with mock.patch("dca_bot.binance_client.send_notification") as notify:
            with self.assertLogs("dca_bot", level="ERROR"):
                self.assertIsNone(client.place_market_buy("BTCUSDT", 15.0))

        self.assertEqual(len(self._pending_ids()), 1)
        notify.assert_called_once()

    def test_live_status_after_network_error_stays_unclear(self):
        """
        Die Market-Order ist laut Boerse noch NEW - unwahrscheinlich,
        aber moeglich. Auch das wird nicht geraten.
        """
        client, raw = self._make_client()
        raw.order_behaviour = requests.exceptions.ReadTimeout("weg")
        raw.status_payload = {"status": "NEW", "executedQty": "0"}

        with mock.patch("dca_bot.binance_client.send_notification") as notify:
            with self.assertLogs("dca_bot", level="ERROR"):
                self.assertIsNone(client.place_market_buy("BTCUSDT", 15.0))

        self.assertEqual(len(self._pending_ids()), 1)
        notify.assert_called_once()

    def test_no_secret_bearing_exception_text_is_logged(self):
        """
        Token-Hygiene analog zu K5: requests-Fehlermeldungen tragen die
        vollstaendige Request-URL, bei einer signierten GET-Abfrage samt
        HMAC-Signatur als Query-Parameter. Geloggt wird deshalb nur der
        Exception-TYP.
        """
        client, raw = self._make_client()
        leaky = "https://testnet.binance.vision/api/v3/order?signature=GEHEIM123"
        raw.order_behaviour = requests.exceptions.ConnectionError(leaky)
        raw.status_behaviour = requests.exceptions.ConnectionError(leaky)

        with mock.patch("dca_bot.binance_client.send_notification"):
            with self.assertLogs("dca_bot", level="ERROR") as captured:
                client.place_market_buy("BTCUSDT", 15.0)

        joined = "\n".join(captured.output)
        self.assertNotIn("GEHEIM123", joined)
        self.assertIn("ConnectionError", joined)

    # -- Abgrenzung: Bot ohne Pending-Datei (Allocator) --

    def test_client_without_pending_file_refuses_to_place_orders(self):
        """
        Der Allocator setzt `pending_orders_file` bewusst auf "". Damit
        wird "der Allocator platziert nie Orders" von einer Zusage im
        Docstring zu einer Bedingung, die der Code erzwingt.
        """
        client, raw = self._make_client(pending_file="")

        with self.assertRaises(ValueError):
            client.place_market_buy("BTCUSDT", 15.0)
        self.assertEqual(raw.placed_client_order_ids, [])


class OrderFillsEnrichmentTestCase(TradingClientTestBase):
    """
    get_order_with_fills(): schliesst die Gebuehrenluecke des
    Reconciliation-Pfads - get_order()-Antworten enthalten keine Fills
    (siehe K3 in trading-bot-projekt.md).
    """

    def test_fills_are_loaded_from_my_trades(self):
        client, raw = self._make_client()
        raw.my_trades_result = [
            {
                "price": "77000.0",
                "qty": "0.0002",
                "commission": "0.0000002",
                "commissionAsset": "BTC",
            }
        ]

        with self.assertLogs("dca_bot", level="INFO"):
            enriched = client.get_order_with_fills(
                "BTCUSDT", {"orderId": 4711, "executedQty": "0.0002"}
            )

        self.assertEqual(len(enriched["fills"]), 1)
        self.assertEqual(enriched["fills"][0]["commissionAsset"], "BTC")
        self.assertEqual(raw.my_trades_calls[0]["orderId"], 4711)

    def test_existing_fills_are_not_overwritten(self):
        client, raw = self._make_client()
        order = {"orderId": 4711, "fills": [{"commission": "1", "commissionAsset": "BTC"}]}

        self.assertIs(client.get_order_with_fills("BTCUSDT", order), order)
        self.assertEqual(raw.my_trades_calls, [])

    def test_failed_my_trades_query_returns_order_unchanged_with_warning(self):
        """
        Lieber ein Ledger-Eintrag mit minimal zu hoher Menge als gar
        keiner - aber sichtbar, damit jemand nachrechnen kann.
        """
        client, raw = self._make_client()
        raw.my_trades_result = requests.exceptions.ReadTimeout("weg")
        order = {"orderId": 4711, "executedQty": "0.0002"}

        with self.assertLogs("dca_bot", level="WARNING") as captured:
            result = client.get_order_with_fills("BTCUSDT", order)

        self.assertNotIn("fills", result)
        self.assertTrue(any("myTrades" in line for line in captured.output))


if __name__ == "__main__":
    unittest.main()


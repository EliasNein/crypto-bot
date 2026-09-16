"""
Tests fuer Teil B des K2-Fixes: die Reconciliation beim Bot-Start.

Szenario aller Tests hier ist derselbe simulierte Vorfall - beim letzten
Lauf wurde eine Order abgeschickt, ihr Ergebnis kam aber nie im Ledger
an (Netzwerkfehler in unklarem Zustand oder Prozess-Kill zwischen Order
und Ledger-Eintrag). Zurueck bleibt ein Eintrag in der
Pending-Orders-Datei. Geprueft wird, was der jeweilige Bot beim naechsten
Start daraus macht:

- Order war erfolgreich  -> fehlender Ledger-Eintrag wird nachgetragen
- Order ist nie passiert -> Eintrag wird sauber verworfen
- Zustand weiter unklar  -> Eintrag bleibt stehen und eskaliert

Dazu die Eigenschaft, ohne die der Fix beim DCA-Bot mehr Schaden als
Nutzen braechte: das Nachtragen muss IDEMPOTENT sein (siehe
TradeRecord.client_order_id in risk.py).

Kein Netzwerk, keine Zugangsdaten, temporaere Dateien.

Ausfuehren mit:  python -m unittest tests.test_order_reconciliation -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dca_bot.config import Config
from dca_bot.grid_config import GridConfig
from dca_bot.grid_risk import GridPosition
from dca_bot.grid_strategy import GridTradingStrategy
from dca_bot.order_utils import SymbolTradingRules
from dca_bot.pending_orders import (
    KIND_MARKET,
    KIND_STOP_LOSS_LIMIT,
    LOOKUP_FAILED,
    LOOKUP_FOUND,
    LOOKUP_NOT_FOUND,
    PendingOrder,
    PendingOrderStore,
)
from dca_bot.strategy import DCAStrategy
from dca_bot.trend_config import TrendConfig
from dca_bot.trend_risk import TrendTrade
from dca_bot.trend_strategy import TrendFollowingStrategy

FAKE_TRADING_RULES = SymbolTradingRules(
    symbol="BTCUSDT",
    tick_size=0.01,
    step_size=0.00001,
    min_notional=5.0,
    base_asset="BTC",
    quote_asset="USDT",
    quote_precision=8,
)


class FakeReconcileClient:
    """
    Fake-TradingClient fuer die Startup-Reconciliation.

    Gegenueber den Fakes in den anderen Testdateien kommen die Teile
    dazu, die der K2-Fix braucht: eine echte PendingOrderStore-Instanz
    (temporaere Datei), die Ground-Truth-Rueckfrage
    `get_order_by_client_id()` und das Nachladen der Gebuehrendaten
    ueber `get_order_with_fills()`.
    """

    def __init__(self, pending_file: str, bot_name: str, price: float = 77_000.0):
        self.pending_orders = PendingOrderStore(pending_file, bot_name)
        self.price = price
        self.trading_enabled = True
        # clientOrderId -> (Lookup-Ergebnis, Order-Antwort)
        self.lookups: dict[str, tuple[str, dict | None]] = {}
        # orderId -> fills, die get_order_with_fills() nachlaedt
        self.fills_by_order_id: dict[object, list[dict]] = {}
        self.stop_order_calls: list[tuple] = []
        self.order_status: dict[str, dict] = {}
        self.order_status_calls: list[tuple] = []
        # Order-IDs, fuer die get_order_status() einen Fehlschlag
        # simuliert (der echte Client gibt dann None zurueck, siehe
        # binance_client.py). Bewusst getrennt von "ID nicht im dict":
        # so ist im Test sichtbar, dass es um eine GESCHEITERTE Abfrage
        # geht und nicht um eine unbekannte Order.
        self.failing_status_queries: set[str] = set()
        self.cancel_calls: list[tuple] = []
        self._next_order_id = 9000

    # -- Ground Truth --

    def get_order_by_client_id(self, symbol: str, client_order_id: str):
        return self.lookups.get(client_order_id, (LOOKUP_NOT_FOUND, None))

    def get_order_with_fills(self, symbol: str, order: dict) -> dict:
        if order.get("fills"):
            return order
        fills = self.fills_by_order_id.get(order.get("orderId"))
        if not fills:
            return order
        enriched = dict(order)
        enriched["fills"] = fills
        return enriched

    # -- Uebriger TradingClient --

    def get_current_price(self, symbol: str) -> float:
        return self.price

    def get_symbol_trading_rules(self, symbol: str):
        return FAKE_TRADING_RULES

    def place_stop_loss_limit_sell(
        self,
        symbol: str,
        quantity: float,
        stop_price: float,
        limit_price: float,
        context: dict | None = None,
    ) -> dict | None:
        self.stop_order_calls.append((symbol, quantity, stop_price, limit_price))
        if not self.trading_enabled:
            return None
        self._next_order_id += 1
        order_id = str(self._next_order_id)
        order = {"orderId": order_id, "status": "NEW", "executedQty": "0"}
        self.order_status[order_id] = order
        return order

    def get_order_status(self, symbol: str, order_id: str) -> dict | None:
        key = str(order_id)
        self.order_status_calls.append((symbol, key))
        if key in self.failing_status_queries:
            return None
        return self.order_status.get(key)

    def cancel_order(self, symbol: str, order_id: str) -> dict | None:
        self.cancel_calls.append((symbol, order_id))
        return None


def filled_order(
    order_id: object = 4711,
    executed_qty: float = 0.0002,
    cumulative_quote: float = 15.4,
) -> dict:
    """Eine per get_order() geholte, vollstaendig gefuellte Order."""
    return {
        "orderId": order_id,
        "status": "FILLED",
        "executedQty": str(executed_qty),
        "cummulativeQuoteQty": str(cumulative_quote),
    }


class ReconciliationTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)
        self.pending_file = str(self.tmp_path / "pending_orders.json")
        # Telegram-Versand pauschal stilllegen - in diesen Tests geht es
        # um den Ledger-Zustand; einzelne Tests patchen gezielt selbst.
        patcher = mock.patch("dca_bot.pending_orders.send_notification")
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _add_pending(
        self,
        client_order_id: str,
        side: str = "BUY",
        kind: str = KIND_MARKET,
        context: dict | None = None,
        bot_name: str = "bot",
    ) -> PendingOrder:
        store = PendingOrderStore(self.pending_file, bot_name)
        pending = PendingOrder.new(
            client_order_id=client_order_id,
            kind=kind,
            symbol="BTCUSDT",
            side=side,
            context=context or {},
        )
        store.add(pending)
        return pending

    def _remaining_pending(self, bot_name: str = "bot") -> list[str]:
        store = PendingOrderStore(self.pending_file, bot_name)
        return [e.client_order_id for e in store.all()]


class DCAReconciliationTestCase(ReconciliationTestBase):
    """
    Der DCA-Bot ist der interessanteste Fall: sein Ledger ist eine reine
    append-only Liste ohne Status, das Muster passt dort NICHT ohne
    Weiteres (siehe TradeRecord.client_order_id).
    """

    def _make_strategy(self, trading_enabled: bool = True):
        config = Config(
            api_key="test",
            api_secret="test",
            symbol="BTCUSDT",
            quote_amount=15.0,
            trading_enabled=trading_enabled,
            kill_switch_file=str(self.tmp_path / "STOP_UNUSED"),
            state_file=str(self.tmp_path / "trade_ledger.json"),
            stop_loss_state_file=str(self.tmp_path / "stop_loss_paused.json"),
            pending_orders_file=self.pending_file,
            bot_name="dca",
        )
        client = FakeReconcileClient(self.pending_file, "dca")
        return DCAStrategy(config, client), client

    def test_confirmed_order_is_written_to_the_ledger(self):
        """
        "War erfolgreich": Der Kauf lief beim letzten Lauf durch, sein
        Ergebnis kam nie an. Ohne diesen Nachtrag waeren Tageslimit und
        Stop-Loss-Kostenbasis dauerhaft zu niedrig.
        """
        strategy, client = self._make_strategy()
        self._add_pending("dca-lost", context={"price": 77_000.0, "amount": 15.0}, bot_name="dca")
        client.lookups["dca-lost"] = (LOOKUP_FOUND, filled_order())

        with self.assertLogs("dca_bot", level="WARNING"):
            strategy.reconcile_pending_orders()

        records = strategy._ledger._read()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["client_order_id"], "dca-lost")
        self.assertFalse(records[0]["dry_run"])
        self.assertAlmostEqual(records[0]["quote_spent"], 15.4)
        # Preis aus den echten Fuelldaten, nicht aus dem Kontext: der
        # damals gesehene Ticker-Preis waere nur eine Behauptung.
        self.assertAlmostEqual(records[0]["price"], 15.4 / 0.0002, places=4)
        self.assertEqual(self._remaining_pending("dca"), [])

    def test_unknown_order_is_discarded_without_ledger_entry(self):
        """"Ist nie passiert": sauber verwerfen, kein Eintrag, kein Fehler."""
        strategy, client = self._make_strategy()
        self._add_pending("dca-never", context={"price": 77_000.0}, bot_name="dca")
        client.lookups["dca-never"] = (LOOKUP_NOT_FOUND, None)

        with self.assertLogs("dca_bot", level="INFO") as captured:
            strategy.reconcile_pending_orders()

        self.assertEqual(strategy._ledger._read(), [])
        self.assertEqual(self._remaining_pending("dca"), [])
        self.assertTrue(
            any("nie wirksam erreicht" in line for line in captured.output)
        )
        self.notify.assert_not_called()

    def test_unclear_order_keeps_entry_and_escalates(self):
        """
        Weiterhin unklar: nicht raten. Der Eintrag bleibt stehen, damit
        der naechste Start erneut fragt - und es geht eine Meldung raus.
        """
        strategy, client = self._make_strategy()
        self._add_pending("dca-unclear", bot_name="dca")
        client.lookups["dca-unclear"] = (LOOKUP_FAILED, None)

        with self.assertLogs("dca_bot", level="ERROR"):
            strategy.reconcile_pending_orders()

        self.assertEqual(strategy._ledger._read(), [])
        self.assertEqual(self._remaining_pending("dca"), ["dca-unclear"])
        self.notify.assert_called_once()

    def test_reconciliation_is_idempotent(self):
        """
        Der Grund, warum TradeRecord ueberhaupt eine client_order_id
        bekommen hat: stirbt der Prozess zwischen Ledger-Eintrag und dem
        Entfernen des Pending-Eintrags, kommt derselbe Kauf beim
        naechsten Start erneut an. Im append-only Ledger wuerde er dann
        DOPPELT stehen - und Tageslimit sowie Stop-Loss-Kostenbasis
        verfaelschen.
        """
        strategy, client = self._make_strategy()
        self._add_pending("dca-twice", context={"price": 77_000.0}, bot_name="dca")
        client.lookups["dca-twice"] = (LOOKUP_FOUND, filled_order())

        with self.assertLogs("dca_bot", level="WARNING"):
            strategy.reconcile_pending_orders()

        # Simulierter Absturz genau nach dem Ledger-Eintrag: der
        # Pending-Eintrag ist wieder da, der Ledger-Eintrag auch.
        self._add_pending("dca-twice", context={"price": 77_000.0}, bot_name="dca")

        with self.assertLogs("dca_bot", level="INFO") as captured:
            strategy.reconcile_pending_orders()

        self.assertEqual(len(strategy._ledger._read()), 1, "Kein zweiter Eintrag")
        self.assertTrue(
            any("bereits im Ledger" in line for line in captured.output)
        )
        self.assertEqual(self._remaining_pending("dca"), [])

    def test_fee_is_deducted_via_my_trades(self):
        """
        get_order()-Antworten enthalten keine Fills. Ohne das Nachladen
        ueber myTrades kaeme die BRUTTO-Menge ins Ledger und wuerde den
        Portfoliowert ueberschaetzen - also zurueck in die K3-Falle,
        ausgerechnet auf dem neuen Pfad.
        """
        strategy, client = self._make_strategy()
        self._add_pending("dca-fee", context={"price": 77_000.0}, bot_name="dca")
        client.lookups["dca-fee"] = (LOOKUP_FOUND, filled_order())
        client.fills_by_order_id[4711] = [
            {
                "price": "77000.0",
                "qty": "0.0002",
                "commission": "0.0000002",
                "commissionAsset": "BTC",
            }
        ]

        with self.assertLogs("dca_bot", level="WARNING"):
            strategy.reconcile_pending_orders()

        quantity = strategy._ledger._read()[0]["quantity"]
        self.assertLess(quantity, 0.0002, "Gebuehr muss abgezogen sein")

    def test_nothing_happens_without_pending_entries(self):
        strategy, client = self._make_strategy()
        strategy.reconcile_pending_orders()
        self.assertEqual(strategy._ledger._read(), [])


class GridReconciliationTestCase(ReconciliationTestBase):
    def _make_strategy(self):
        config = GridConfig(
            api_key="test",
            api_secret="test",
            symbol="BTCUSDT",
            lower_limit=70_000.0,
            upper_limit=90_000.0,
            grid_spacing_pct=1.5,
            amount_per_level=15.0,
            trading_enabled=True,
            kill_switch_file=str(self.tmp_path / "STOP_GRID_UNUSED"),
            state_file=str(self.tmp_path / "grid_positions.json"),
            stop_loss_state_file=str(self.tmp_path / "grid_stop_loss.json"),
            pending_orders_file=self.pending_file,
            bot_name="grid",
        )
        client = FakeReconcileClient(self.pending_file, "grid")
        return GridTradingStrategy(config, client), client

    def test_confirmed_buy_reopens_the_level(self):
        """
        Ohne Nachtrag bliebe die Stufe "frei" und das naechste Crossing
        wuerde sie ein zweites Mal kaufen.
        """
        strategy, client = self._make_strategy()
        self._add_pending(
            "grid-lost",
            context={"level_index": 3, "price": 74_000.0, "amount": 15.0},
            bot_name="grid",
        )
        client.lookups["grid-lost"] = (
            LOOKUP_FOUND,
            filled_order(executed_qty=0.0002, cumulative_quote=14.8),
        )

        with self.assertLogs("grid_bot", level="WARNING"):
            strategy.reconcile_pending_orders()

        positions = strategy._ledger.open_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["level_index"], 3)
        self.assertEqual(positions[0]["client_order_id"], "grid-lost")
        self.assertFalse(positions[0]["dry_run"])
        # Verkaufsziel ist die naechsthoehere Grid-Stufe, exakt wie beim
        # regulaeren Kauf.
        self.assertAlmostEqual(
            positions[0]["target_sell_price"], strategy._levels[4], places=6
        )
        self.assertEqual(self._remaining_pending("grid"), [])

    def test_confirmed_sell_closes_the_position(self):
        """
        Ohne Nachtrag bliebe die Position offen, ihr Sell-Target waere
        weiterhin erreicht - und der naechste Zyklus wuerde eine Menge
        verkaufen, die es nicht mehr gibt.
        """
        strategy, client = self._make_strategy()
        position = GridPosition.new(
            level_index=3,
            buy_price=74_000.0,
            target_sell_price=75_110.0,
            quantity=0.0002,
            quote_spent=14.8,
            dry_run=False,
        )
        strategy._ledger.record_buy(position)

        self._add_pending(
            "grid-sell-lost",
            side="SELL",
            context={"position_id": position.id, "price": 75_110.0},
            bot_name="grid",
        )
        client.lookups["grid-sell-lost"] = (
            LOOKUP_FOUND,
            filled_order(executed_qty=0.0002, cumulative_quote=15.02),
        )

        with self.assertLogs("grid_bot", level="WARNING"):
            strategy.reconcile_pending_orders()

        self.assertEqual(strategy._ledger.open_positions(), [])
        closed = strategy._ledger.position_by_id(position.id)
        self.assertEqual(closed["status"], "closed")
        self.assertAlmostEqual(closed["realized_pnl"], 15.02 - 14.8, places=6)

    def test_already_closed_position_is_left_alone(self):
        """Idempotenz auf der Verkaufsseite."""
        strategy, client = self._make_strategy()
        position = GridPosition.new(
            level_index=3,
            buy_price=74_000.0,
            target_sell_price=75_110.0,
            quantity=0.0002,
            quote_spent=14.8,
            dry_run=False,
        )
        strategy._ledger.record_buy(position)
        strategy._ledger.record_sell(position.id, 75_110.0, "2026-09-16T10:00:00+00:00", 0.22)

        self._add_pending(
            "grid-sell-twice",
            side="SELL",
            context={"position_id": position.id},
            bot_name="grid",
        )
        client.lookups["grid-sell-twice"] = (LOOKUP_FOUND, filled_order())

        with self.assertLogs("grid_bot", level="INFO") as captured:
            strategy.reconcile_pending_orders()

        closed = strategy._ledger.position_by_id(position.id)
        self.assertAlmostEqual(closed["realized_pnl"], 0.22, places=6)
        self.assertTrue(
            any("bereits geschlossen" in line for line in captured.output)
        )

    def test_unknown_position_id_keeps_the_entry(self):
        """
        Der Verkauf hat real stattgefunden, laesst sich aber keiner
        Position zuordnen - dann lieber laut stehen lassen als raten.
        """
        strategy, client = self._make_strategy()
        self._add_pending(
            "grid-orphan",
            side="SELL",
            context={"position_id": "gibt-es-nicht"},
            bot_name="grid",
        )
        client.lookups["grid-orphan"] = (LOOKUP_FOUND, filled_order())

        with self.assertLogs("grid_bot", level="ERROR"):
            strategy.reconcile_pending_orders()

        self.assertEqual(self._remaining_pending("grid"), ["grid-orphan"])
        self.notify.assert_called_once()

    def test_vanished_grid_level_still_books_the_position(self):
        """
        Wurde die Grid-Konfiguration zwischen den Laeufen geaendert, kann
        die gespeicherte Stufe fehlen. Die Assets liegen trotzdem an der
        Boerse - sie nicht zu verbuchen waere die schlechteste Option.
        """
        strategy, client = self._make_strategy()
        self._add_pending(
            "grid-gone",
            context={"level_index": 999, "price": 74_000.0, "amount": 15.0},
            bot_name="grid",
        )
        client.lookups["grid-gone"] = (LOOKUP_FOUND, filled_order())

        with self.assertLogs("grid_bot", level="ERROR") as captured:
            strategy.reconcile_pending_orders()

        positions = strategy._ledger.open_positions()
        self.assertEqual(len(positions), 1)
        self.assertGreater(positions[0]["target_sell_price"], positions[0]["buy_price"])
        self.assertTrue(
            any("existiert im aktuellen Grid nicht mehr" in line for line in captured.output)
        )


class TrendReconciliationTestCase(ReconciliationTestBase):
    def _make_strategy(self, trading_enabled: bool = True):
        config = TrendConfig(
            api_key="test",
            api_secret="test",
            symbol="BTCUSDT",
            stop_loss_pct=10.0,
            stop_limit_offset_pct=0.5,
            trading_enabled=trading_enabled,
            kill_switch_file=str(self.tmp_path / "STOP_TREND_UNUSED"),
            state_file=str(self.tmp_path / "trend_ledger.json"),
            stop_loss_state_file=str(self.tmp_path / "trend_stop_loss.json"),
            pending_orders_file=self.pending_file,
            bot_name="trend",
        )
        client = FakeReconcileClient(self.pending_file, "trend")
        strategy = TrendFollowingStrategy(config, client)
        strategy._seeded = True
        return strategy, client

    def test_confirmed_entry_creates_position_and_gets_protected(self):
        """
        Die vollstaendige Kette und der gefaehrlichste Fall des ganzen
        Fixes: ein real gekaufter, aber unverbuchter Einstieg. Vorher
        waere daraus eine ungeschuetzte Position geworden, von der der
        Bot nichts weiss - und der naechste Zyklus haette bei weiter
        bestaetigtem Aufwaertstrend ERNEUT gekauft.

        reconcile_pending_orders() traegt den Einstieg nach,
        reconcile_on_startup() platziert direkt danach die fehlende
        exchange-seitige Stop-Loss-Order.
        """
        strategy, client = self._make_strategy()
        self._add_pending(
            "trend-lost", context={"price": 50_000.0, "amount": 15.0}, bot_name="trend"
        )
        client.lookups["trend-lost"] = (
            LOOKUP_FOUND,
            filled_order(executed_qty=0.0003, cumulative_quote=15.0),
        )

        with self.assertLogs("trend_bot", level="WARNING"):
            strategy.reconcile_pending_orders()

        open_trade = strategy._ledger.open_position()
        self.assertIsNotNone(open_trade)
        self.assertEqual(open_trade["client_order_id"], "trend-lost")
        self.assertIsNone(
            open_trade["stop_loss_order_id"], "Nach dem Nachtrag noch ungeschuetzt"
        )

        with self.assertLogs("trend_bot", level="INFO"):
            strategy.reconcile_on_startup()

        protected = strategy._ledger.open_position()
        self.assertIsNotNone(protected["stop_loss_order_id"])
        self.assertEqual(len(client.stop_order_calls), 1)
        # Schwelle wie beim regulaeren Entry: 10% unter Einstiegspreis.
        _, _, stop_price, _ = client.stop_order_calls[0]
        self.assertAlmostEqual(stop_price, protected["entry_price"] * 0.9, places=4)

    def test_second_open_position_is_refused_and_escalated(self):
        """
        Der Trend-Bot haelt bewusst nur eine Position. Einen zweiten
        offenen Eintrag anzulegen wuerde diese Invariante brechen - also
        nicht verbuchen, sondern stehen lassen und melden.
        """
        strategy, client = self._make_strategy()
        strategy._ledger.record_entry(
            TrendTrade.new(
                entry_price=50_000.0, quantity=0.0003, quote_spent=15.0, dry_run=False
            )
        )
        self._add_pending("trend-second", context={"price": 51_000.0}, bot_name="trend")
        client.lookups["trend-second"] = (LOOKUP_FOUND, filled_order())

        with self.assertLogs("trend_bot", level="ERROR"):
            strategy.reconcile_pending_orders()

        self.assertEqual(len(strategy._ledger._read()), 1)
        self.assertEqual(self._remaining_pending("trend"), ["trend-second"])
        self.notify.assert_called_once()

    def test_confirmed_stop_loss_exit_closes_trade_and_latches(self):
        strategy, client = self._make_strategy()
        trade = TrendTrade.new(
            entry_price=50_000.0, quantity=0.0003, quote_spent=15.0, dry_run=False
        )
        strategy._ledger.record_entry(trade)

        self._add_pending(
            "trend-exit",
            side="SELL",
            context={"trade_id": trade.id, "reason": "stop_loss", "price": 45_000.0},
            bot_name="trend",
        )
        client.lookups["trend-exit"] = (
            LOOKUP_FOUND,
            filled_order(executed_qty=0.0003, cumulative_quote=13.5),
        )

        with self.assertLogs("trend_bot", level="WARNING"):
            strategy.reconcile_pending_orders()

        closed = strategy._ledger.trade_by_id(trade.id)
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "stop_loss")
        self.assertAlmostEqual(closed["realized_pnl"], 13.5 - 15.0, places=6)
        # Der Latch gehoert zum Ausstieg: ohne ihn duerfte der Bot sofort
        # wieder einsteigen, obwohl der Stop-Loss real ausgeloest hat.
        self.assertTrue(strategy._stop_loss.is_paused())

    def test_confirmed_stop_order_is_reattached_to_the_trade(self):
        """
        Eine Stop-Order, die an der Boerse liegt, dem Ledger aber
        unbekannt ist. Ohne das Wiederanhaengen wuerde
        _ensure_stop_loss_protection() eine ZWEITE Order ueber dieselbe
        Menge platzieren.
        """
        strategy, client = self._make_strategy()
        trade = TrendTrade.new(
            entry_price=50_000.0, quantity=0.0003, quote_spent=15.0, dry_run=False
        )
        strategy._ledger.record_entry(trade)

        self._add_pending(
            "trend-stop-lost",
            side="SELL",
            kind=KIND_STOP_LOSS_LIMIT,
            context={"trade_id": trade.id, "limit_price": 44_775.0},
            bot_name="trend",
        )
        # Fuer eine Stop-Order ist "NEW" der Erfolgsfall.
        client.lookups["trend-stop-lost"] = (
            LOOKUP_FOUND,
            {"orderId": "8888", "status": "NEW", "executedQty": "0"},
        )

        with self.assertLogs("trend_bot", level="WARNING"):
            strategy.reconcile_pending_orders()

        updated = strategy._ledger.trade_by_id(trade.id)
        self.assertEqual(updated["stop_loss_order_id"], "8888")
        self.assertAlmostEqual(updated["stop_limit_price"], 44_775.0, places=4)
        self.assertEqual(self._remaining_pending("trend"), [])

    def _setup_duplicate_stop_order(self):
        """
        Gemeinsamer Aufbau fuer die Doppel-Stop-Order-Faelle: im Ledger
        liegt Order 1111, an der Boerse zusaetzlich 2222.
        """
        strategy, client = self._make_strategy()
        trade = TrendTrade.new(
            entry_price=50_000.0, quantity=0.0003, quote_spent=15.0, dry_run=False
        )
        strategy._ledger.record_entry(trade)
        strategy._ledger.set_stop_loss_order(trade.id, "1111", 44_775.0)

        self._add_pending(
            "trend-stop-dup",
            side="SELL",
            kind=KIND_STOP_LOSS_LIMIT,
            context={"trade_id": trade.id, "limit_price": 44_775.0},
            bot_name="trend",
        )
        client.lookups["trend-stop-dup"] = (
            LOOKUP_FOUND,
            {"orderId": "2222", "status": "NEW", "executedQty": "0"},
        )
        return strategy, client, trade

    def _run_duplicate_reconcile(self, strategy):
        """
        Fuehrt die Reconciliation aus und gibt (Telegram-Text,
        Log-Zeilen) zurueck. Die Meldung kommt aus der Strategie selbst,
        nicht aus dem gemeinsamen Reconciliation-Rahmen - also dort
        patchen.
        """
        with mock.patch("dca_bot.trend_strategy.send_notification") as notify:
            with self.assertLogs("trend_bot", level="ERROR") as captured:
                strategy.reconcile_pending_orders()
        notify.assert_called_once()
        return notify.call_args.args[0], captured.output

    def test_duplicate_stop_order_is_reported_but_never_cancelled(self):
        """
        Zwei Stop-Orders ueber dieselbe Menge, beide noch offen. Der Bot
        storniert hier bewusst NICHTS: das waere seine erste autonome,
        destruktive Aktion auf Basis eines abgeleiteten Zustands und
        widerspraeche dem sonst durchgehaltenen "im Zweifel nicht
        handeln". Stattdessen deutlich melden - inklusive des
        tatsaechlichen Status beider Orders, damit man vor der manuellen
        Pruefung nicht erst selbst nachsehen muss.
        """
        strategy, client, trade = self._setup_duplicate_stop_order()
        client.order_status["1111"] = {"status": "NEW"}
        client.order_status["2222"] = {"status": "NEW"}

        message, log_lines = self._run_duplicate_reconcile(strategy)

        # Beide Orders wurden tatsaechlich abgefragt.
        queried = [order_id for _, order_id in client.order_status_calls]
        self.assertIn("1111", queried)
        self.assertIn("2222", queried)

        self.assertIn("Doppelte Stop-Order erkannt", message)
        self.assertIn("Ledger-Order 1111: Status NEW", message)
        self.assertIn("Pending-Order 2222: Status NEW", message)
        self.assertIn("nichts automatisch storniert", message)
        self.assertTrue(
            any("Doppelte Stop-Order erkannt" in line for line in log_lines)
        )
        self.assertTrue(any("Status NEW" in line for line in log_lines))

        # Ledger bleibt unveraendert, nichts wurde storniert.
        updated = strategy._ledger.trade_by_id(trade.id)
        self.assertEqual(updated["stop_loss_order_id"], "1111")
        self.assertEqual(client.cancel_calls, [])
        # Der Fall ist damit geklaert - aber eben von Hand aufzuloesen.
        self.assertEqual(self._remaining_pending("trend"), [])

    def test_duplicate_stop_order_reports_differing_statuses(self):
        """
        Der haeufigere Fall in der Praxis: eine der beiden Orders ist
        laengst storniert. Dann ist gar nichts zu tun - und genau das
        muss aus der Meldung hervorgehen, ohne dass jemand erst bei
        Binance nachsieht.
        """
        strategy, client, _ = self._setup_duplicate_stop_order()
        client.order_status["1111"] = {"status": "CANCELED"}
        client.order_status["2222"] = {"status": "NEW"}

        message, _ = self._run_duplicate_reconcile(strategy)

        self.assertIn("Ledger-Order 1111: Status CANCELED", message)
        self.assertIn("Pending-Order 2222: Status NEW", message)
        self.assertEqual(client.cancel_calls, [])

    def test_duplicate_stop_order_marks_unreachable_status_explicitly(self):
        """
        Schlaegt eine der beiden Status-Abfragen fehl, wird das
        ausdruecklich als "nicht abrufbar" ausgewiesen - nicht geraten
        und nicht weggelassen. "Der Bot konnte es nicht klaeren" ist
        fuer die manuelle Pruefung eine andere Aussage als jeder echte
        Order-Status, und die zweite, erfolgreiche Abfrage muss trotzdem
        in der Meldung stehen.
        """
        strategy, client, _ = self._setup_duplicate_stop_order()
        client.failing_status_queries.add("1111")
        client.order_status["2222"] = {"status": "FILLED"}

        message, log_lines = self._run_duplicate_reconcile(strategy)

        self.assertIn("Ledger-Order 1111: Status nicht abrufbar", message)
        self.assertIn("Pending-Order 2222: Status FILLED", message)
        self.assertTrue(any("nicht abrufbar" in line for line in log_lines))
        self.assertEqual(client.cancel_calls, [])

    def test_orphaned_stop_order_of_closed_trade_is_only_reported(self):
        strategy, client = self._make_strategy()
        trade = TrendTrade.new(
            entry_price=50_000.0, quantity=0.0003, quote_spent=15.0, dry_run=False
        )
        strategy._ledger.record_entry(trade)
        strategy._ledger.record_exit(
            trade.id, 52_000.0, "2026-09-16T10:00:00+00:00", "signal", 0.6
        )

        self._add_pending(
            "trend-stop-orphan",
            side="SELL",
            kind=KIND_STOP_LOSS_LIMIT,
            context={"trade_id": trade.id},
            bot_name="trend",
        )
        client.lookups["trend-stop-orphan"] = (
            LOOKUP_FOUND,
            {"orderId": "3333", "status": "NEW", "executedQty": "0"},
        )

        with self.assertLogs("trend_bot", level="ERROR") as captured:
            strategy.reconcile_pending_orders()

        self.assertEqual(client.cancel_calls, [])
        self.assertTrue(any("VERWAISTE Order" in line for line in captured.output))
        # Geklaert ist der Fall trotzdem - der Eintrag darf weg.
        self.assertEqual(self._remaining_pending("trend"), [])


if __name__ == "__main__":
    unittest.main()

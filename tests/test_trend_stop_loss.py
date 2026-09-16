"""
Tests für den echten, exchange-seitigen Stop-Loss des Trend-Bots
(siehe README.md Abschnitt 9.5, trend_strategy.py).

Erster committeter Test im Projekt (siehe trading-bot-projekt.md,
Migrations-/Live-Vorbereitung): bewusste Abweichung vom bisherigen
"Ad-hoc-Skript, dann verwerfen"-Vorgehen der anderen Bots, weil dies der
erste Code ist, der eine echte Order platziert, die ohne weiteres
Bot-Zutun Geld bewegen kann (STOP_LOSS_LIMIT-Order an der Börse).

Nutzt einen Fake-TradingClient (kein echter Netzwerkzugriff, keine
Binance-Zugangsdaten nötig) statt Mocks auf Modulebene - TradingClient
wird in trend_strategy.py rein über Duck-Typing verwendet
(get_current_price/place_market_buy/place_market_sell/
place_stop_loss_limit_sell/cancel_order/get_order_status), ein
Fake-Objekt mit derselben Schnittstelle reicht deshalb aus.

Ausführen mit:  python -m unittest tests.test_trend_stop_loss -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dca_bot.order_utils import SymbolTradingRules
from dca_bot.pending_orders import (
    KIND_STOP_LOSS_LIMIT,
    ORDER_CONFIRMED,
    ORDER_LIFECYCLE_DEAD,
    ORDER_LIFECYCLE_FILLED,
    ORDER_LIFECYCLE_LIVE,
    ORDER_WITHOUT_EFFECT,
    classify_order_status,
    order_lifecycle_state,
)
from dca_bot.trend_config import TrendConfig
from dca_bot.trend_strategy import (
    UNCERTAIN_CYCLES_WARNING_THRESHOLD,
    UNPROTECTED_CYCLES_WARNING_THRESHOLD,
    TrendFollowingStrategy,
)


# Handelsregeln nahe an dem, was Binance fuer BTCUSDT meldet - damit die
# Tests dieselbe Quantisierung durchlaufen wie der Live-Betrieb.
FAKE_TRADING_RULES = SymbolTradingRules(
    symbol="BTCUSDT",
    tick_size=0.01,
    step_size=0.00001,
    min_notional=5.0,
    base_asset="BTC",
    quote_asset="USDT",
    quote_precision=8,
)


class FakeTradingClient:
    """
    Verhält sich bewusst wie der echte TradingClient (binance_client.py):
    im Dry-Run (trading_enabled=False) platzieren place_*-Methoden keine
    Order und geben None zurück, exakt wie beim echten Client. Das erlaubt
    es, dieselben Strategie-Codepfade zu testen, die auch live durchlaufen
    werden.
    """

    def __init__(self, trading_enabled: bool, price: float):
        self.trading_enabled = trading_enabled
        self.price = price
        self._next_order_id = 1000
        self.orders: dict[str, dict] = {}

        self.market_buy_calls: list[tuple] = []
        self.market_sell_calls: list[tuple] = []
        self.stop_order_calls: list[tuple] = []
        self.cancel_calls: list[tuple] = []
        self.order_status_calls: list[tuple] = []
        # Gemeinsames Call-Log über alle Methoden hinweg (in Aufrufreihenfolge),
        # um in Tests die relative Reihenfolge zwischen z.B. cancel_order und
        # place_market_sell zu prüfen - die einzelnen *_calls-Listen oben
        # erlauben das für sich allein nicht.
        self.call_log: list[str] = []
        # Testhilfe für die Race-Condition-Szenarien: erzwingt, dass
        # cancel_order() fehlschlägt (None zurückgibt), OHNE den
        # Order-Status zu verändern - simuliert einen echten transienten
        # Fehler (z.B. Netzwerk-Timeout), bei dem die Order in Wahrheit
        # weiterhin "NEW" ist (im Gegensatz zu einem Cancel-Fehlschlag,
        # weil die Order zwischenzeitlich bereits FILLED wurde - das wird
        # stattdessen über fill_order() VOR dem Cancel-Aufruf simuliert).
        self.force_transient_cancel_failure = False
        # Erzwingt, dass place_market_sell() None zurueckgibt, OBWOHL
        # trading_enabled=True ist - simuliert einen echten API-Fehler
        # beim Verkauf (der zweite, voellig andere Grund fuer None neben
        # dem Dry-Run; siehe K1 in TrendSellSafetyTestCase unten).
        self.force_market_sell_failure = False
        # Erzwingt, dass auch das Platzieren einer Stop-Loss-Order
        # fehlschlaegt - fuer den doppelt kritischen Fall "weder verkauft
        # noch abgesichert".
        self.force_stop_order_failure = False
        # Handelsgebuehr, die Binance beim KAUF vom erhaltenen Base-Asset
        # abzieht. Default 0.0 - exakt das Verhalten, das auf dem Testnet
        # beobachtet wurde (commission 0.00000000). Tests, die die
        # Gebuehrenkorrektur pruefen, setzen einen realistischen Wert
        # (0.001 = 0,1%, der Live-Standardsatz).
        self.commission_rate = 0.0
        # Gebuehren-Waehrung: normalerweise das Base-Asset (BTC), bei
        # aktivem BNB-Rabatt stattdessen "BNB" - dann darf die Menge NICHT
        # gekuerzt werden.
        self.commission_asset = "BTC"
        # Laesst get_symbol_trading_rules() scheitern, um zu pruefen, dass
        # das nicht stillschweigend ignoriert wird.
        self.force_trading_rules_failure = False
        self.trading_rules_calls = 0
        # Konsistenz-Check vor dem Verkauf (W11, siehe balance_guard.py).
        # Default bewusst reichlich: die bestehenden Testfaelle sollen
        # sich nicht darum kuemmern muessen, dass der Bot jetzt auch das
        # Guthaben prueft. Die W11-Tests setzen diese Werte gezielt.
        self.base_balance: tuple[float, float] | None = (1_000.0, 0.0)
        self.open_orders: list[dict] | None = []
        self.balance_calls = 0
        self.open_orders_calls = 0
        # Gebuehrendaten, die get_order_with_fills() zu einer per
        # get_order() geholten Order nachlaedt (K3-Restluecke im
        # Stop-Fill-Pfad). Leer = die myTrades-Abfrage liefert nichts,
        # die Order bleibt unveraendert.
        self.fills_by_order_id: dict[str, list[dict]] = {}
        self.order_with_fills_calls = 0
        # Seit dem K2-Fix reicht jede place_*-Methode einen `context` an
        # die Pending-Orders-Ablage durch (siehe binance_client.py) und
        # jede Order-Antwort traegt eine clientOrderId. Der Fake bildet
        # beides nach, damit die Tests denselben Codepfad durchlaufen wie
        # der Live-Betrieb.
        self.order_contexts: list[dict | None] = []
        self._next_client_order_id = 0

    def _new_order_id(self) -> str:
        self._next_order_id += 1
        return str(self._next_order_id)

    def _new_client_order_id(self) -> str:
        self._next_client_order_id += 1
        return f"trend-test-{self._next_client_order_id}"

    def get_current_price(self, symbol: str) -> float:
        return self.price

    def get_asset_balance(self, asset: str) -> tuple[float, float] | None:
        self.balance_calls += 1
        self.call_log.append("get_asset_balance")
        return self.base_balance

    def get_order_with_fills(self, symbol: str, order: dict) -> dict:
        """
        Wie TradingClient.get_order_with_fills: laedt die Gebuehrendaten
        einer per get_order() geholten Antwort nach.

        Dass diese Methode im Fake bis zum K3-Restluecken-Fix FEHLTE, ist
        selbst ein Befund - der Produktivpfad
        `_close_from_filled_stop_order` hat sie nie aufgerufen, obwohl die
        Projektdoku die Luecke als geschlossen auswies. Der Fake brauchte
        sie deshalb nicht.

        Verhaelt sich wie der echte Client: Sind bereits Fills vorhanden,
        bleibt die Antwort unveraendert; sind fuer die Order keine
        registriert (Testfall ohne Gebuehren), wird sie ebenfalls
        unveraendert zurueckgegeben - genau wie eine leere
        myTrades-Antwort.
        """
        self.order_with_fills_calls += 1
        self.call_log.append("get_order_with_fills")
        if order.get("fills"):
            return order
        fills = self.fills_by_order_id.get(str(order.get("orderId")))
        if not fills:
            return order
        enriched = dict(order)
        enriched["fills"] = fills
        return enriched

    def get_open_orders(self, symbol: str) -> list[dict] | None:
        self.open_orders_calls += 1
        return self.open_orders

    def get_symbol_trading_rules(self, symbol: str):
        self.trading_rules_calls += 1
        if self.force_trading_rules_failure:
            # Wie der echte Client: der Fehler wird weitergereicht, statt
            # auf stille Default-Werte auszuweichen.
            raise RuntimeError("exchangeInfo nicht erreichbar (Testfall)")
        return FAKE_TRADING_RULES

    def place_market_buy(
        self, symbol: str, quote_order_qty: float, context: dict | None = None
    ) -> dict | None:
        self.market_buy_calls.append((symbol, quote_order_qty))
        self.order_contexts.append(context)
        if not self.trading_enabled:
            return None
        executed_qty = quote_order_qty / self.price
        return {
            "clientOrderId": self._new_client_order_id(),
            "executedQty": executed_qty,
            "cummulativeQuoteQty": quote_order_qty,
            # Wie eine echte Binance-Antwort: die Gebuehr steht in den
            # Fills, nicht in einem Top-Level-Feld.
            "fills": [
                {
                    "price": self.price,
                    "qty": executed_qty,
                    "commission": executed_qty * self.commission_rate,
                    "commissionAsset": self.commission_asset,
                }
            ],
        }

    def place_market_sell(
        self, symbol: str, quantity: float, context: dict | None = None
    ) -> dict | None:
        self.market_sell_calls.append((symbol, quantity))
        self.order_contexts.append(context)
        self.call_log.append("place_market_sell")
        if not self.trading_enabled:
            return None
        if self.force_market_sell_failure:
            return None
        gross = quantity * self.price
        return {
            "clientOrderId": self._new_client_order_id(),
            "cummulativeQuoteQty": gross,
            # Beim Verkauf rechnet Binance die Gebuehr in der
            # Quote-Waehrung ab (USDT), nicht im Base-Asset.
            "fills": [
                {
                    "price": self.price,
                    "qty": quantity,
                    "commission": gross * self.commission_rate,
                    "commissionAsset": "USDT",
                }
            ],
        }

    def place_stop_loss_limit_sell(
        self,
        symbol: str,
        quantity: float,
        stop_price: float,
        limit_price: float,
        context: dict | None = None,
    ) -> dict | None:
        self.stop_order_calls.append((symbol, quantity, stop_price, limit_price))
        self.order_contexts.append(context)
        if not self.trading_enabled:
            return None
        if self.force_stop_order_failure:
            return None
        order_id = self._new_order_id()
        order = {
            "orderId": order_id,
            "clientOrderId": self._new_client_order_id(),
            "status": "NEW",
            "executedQty": "0",
            "cummulativeQuoteQty": "0",
        }
        self.orders[order_id] = order
        return order

    def cancel_order(self, symbol: str, order_id: str) -> dict | None:
        self.cancel_calls.append((symbol, order_id))
        self.call_log.append("cancel_order")
        if self.force_transient_cancel_failure:
            # Order bleibt unverändert (z.B. weiterhin "NEW") - simuliert
            # einen Fehlschlag, der NICHTS über den wahren Order-Status
            # aussagt (z.B. Netzwerk-Timeout beim Cancel-Request selbst).
            return None
        order = self.orders.get(order_id)
        if order is None or order["status"] != "NEW":
            # Wie der echte Client: harmloser Fehlschlag (z.B. schon
            # gefüllt), keine Exception.
            return None
        order["status"] = "CANCELED"
        return order

    def get_order_status(self, symbol: str, order_id: str) -> dict | None:
        self.order_status_calls.append((symbol, order_id))
        return self.orders.get(order_id)

    def fill_order(
        self,
        order_id: str,
        executed_qty: float,
        cumulative_quote: float,
        commission: float | None = None,
        commission_asset: str = "USDT",
    ) -> None:
        """
        Testhilfe: simuliert, dass die Börse die Order gefüllt hat.

        `commission` registriert zusätzlich Gebührendaten, die
        `get_order_with_fills()` nachliefert - so wie Binance sie über
        `myTrades` herausgibt. Ohne diesen Parameter bleibt es beim
        bisherigen Verhalten (keine Fills, kein Gebührenabzug), damit die
        vorhandenen Testfälle unverändert gelten.
        """
        order = self.orders[order_id]
        order["status"] = "FILLED"
        order["executedQty"] = executed_qty
        order["cummulativeQuoteQty"] = cumulative_quote
        if commission is not None:
            self.fills_by_order_id[str(order_id)] = [
                {
                    "price": cumulative_quote / executed_qty if executed_qty else 0.0,
                    "qty": executed_qty,
                    "commission": commission,
                    "commissionAsset": commission_asset,
                }
            ]

    def end_order_without_fill(self, order_id: str, status: str = "CANCELED") -> None:
        """
        Testhilfe fuer W7: die Order ist an der Boerse beendet, OHNE
        etwas bewegt zu haben - storniert, abgelaufen oder abgelehnt.
        Die Absicherung existiert damit nicht mehr, obwohl das Ledger
        weiterhin eine Order-ID fuehrt.
        """
        order = self.orders[order_id]
        order["status"] = status
        order["executedQty"] = "0"
        order["cummulativeQuoteQty"] = "0"

    def partially_fill_order(self, order_id: str, executed_qty: float) -> None:
        """
        Testhilfe fuer W8: die Order ist teilweise gefuellt und
        weiterhin offen.
        """
        order = self.orders[order_id]
        order["status"] = "PARTIALLY_FILLED"
        order["executedQty"] = executed_qty
        order["cummulativeQuoteQty"] = "0"


class TrendStrategyTestBase(unittest.TestCase):
    """
    Gemeinsame Testumgebung (temporaere Ledger-/State-Dateien, Config- und
    Strategie-Fabrik) fuer die Trend-Testfaelle. Enthaelt bewusst KEINE
    eigenen Testmethoden: erbte eine Testklasse direkt von einer anderen,
    wuerden deren Tests in beiden Klassen erneut ausgefuehrt.
    """

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmpdir.name)
        self.state_file = str(tmp_path / "trend_ledger.json")
        self.stop_loss_state_file = str(tmp_path / "trend_stop_loss_paused.json")
        self.kill_switch_file = str(tmp_path / "STOP_TREND_TEST_UNUSED")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_config(self, trading_enabled: bool, **overrides) -> TrendConfig:
        """
        `overrides` erlaubt einzelnen Testfaellen eine abweichende
        Konfiguration, ohne dass hier fuer jeden Bedarf ein eigener
        Parameter dazukommt - genutzt z.B. von
        tests/test_trend_decide_action.py, das kurze EMA-Perioden
        braucht, damit eine Preisreihe von Hand nachvollziehbar bleibt
        (mit den Live-Defaults 20/50 braeuchte es 50 Kurse Vorlauf, bevor
        ueberhaupt ein Signal moeglich waere).
        """
        params = dict(
            api_key="test",
            api_secret="test",
            symbol="BTCUSDT",
            stop_loss_pct=10.0,
            stop_limit_offset_pct=0.5,
            trading_enabled=trading_enabled,
            kill_switch_file=self.kill_switch_file,
            state_file=self.state_file,
            stop_loss_state_file=self.stop_loss_state_file,
        )
        params.update(overrides)
        return TrendConfig(**params)

    def _make_strategy(
        self, trading_enabled: bool, price: float, **overrides
    ) -> tuple[TrendFollowingStrategy, FakeTradingClient]:
        config = self._make_config(trading_enabled, **overrides)
        client = FakeTradingClient(trading_enabled, price)
        strategy = TrendFollowingStrategy(config, client)
        # Kein echter Netzwerkzugriff fuer die Historie. ACHTUNG: Damit
        # bleibt der Signalgenerator LEER - feed() liefert lauter None,
        # `confirmed_direction` ist nie gesetzt, und decide_action() gibt
        # in diesen Tests immer None zurueck. Genau das war der
        # W17-Befund; die Entscheidungslogik selbst wird deshalb in
        # tests/test_trend_decide_action.py mit echten Preisreihen
        # geprueft.
        strategy._seeded = True
        return strategy, client


class TrendStopLossTestCase(TrendStrategyTestBase):
    """Echter, exchange-seitiger Stop-Loss (siehe Modul-Docstring)."""

    # -- a) Entry setzt eine Stop-Loss-Order und speichert die Order-ID --

    def test_entry_places_stop_order_and_stores_id(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)

        strategy._open_position(50_000.0)

        self.assertEqual(len(client.stop_order_calls), 1)
        symbol, quantity, stop_price, limit_price = client.stop_order_calls[0]
        self.assertEqual(symbol, "BTCUSDT")
        # 10% Stop-Loss unter Entry, davon nochmal 0.5% Limit-Offset
        self.assertAlmostEqual(stop_price, 45_000.0, places=2)
        self.assertAlmostEqual(limit_price, 45_000.0 * (1 - 0.005), places=2)

        open_trade = strategy._ledger.open_position()
        self.assertIsNotNone(open_trade)
        self.assertEqual(open_trade["stop_loss_order_id"], "1001")

    def test_entry_in_dry_run_places_no_real_stop_order(self):
        strategy, client = self._make_strategy(trading_enabled=False, price=50_000.0)

        strategy._open_position(50_000.0)

        # Die Methode wird aufgerufen (damit sie loggen kann), liefert im
        # Dry-Run aber None zurück - exakt wie beim echten Client.
        self.assertEqual(len(client.stop_order_calls), 1)
        open_trade = strategy._ledger.open_position()
        self.assertIsNone(open_trade["stop_loss_order_id"])

    # -- b) Signal-Exit storniert die Stop-Order VOR dem Market-Sell --

    def test_signal_exit_cancels_stop_order_before_market_sell(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        order_id = open_trade["stop_loss_order_id"]
        self.assertEqual(client.orders[order_id]["status"], "NEW")

        strategy._close_position(open_trade, price=52_000.0, reason="signal")

        self.assertEqual(client.cancel_calls, [("BTCUSDT", order_id)])
        self.assertEqual(client.orders[order_id]["status"], "CANCELED")
        self.assertEqual(len(client.market_sell_calls), 1)
        # Reihenfolge: cancel_order muss VOR dem Market-Sell aufgerufen
        # worden sein (sonst bliebe eine verwaiste Order an der Börse).
        # Dazwischen liegt seit W11 die Deckungsprüfung - und die gehört
        # zwingend genau dorthin: Vor dem Stornieren bindet die eigene
        # Stop-Order die komplette Positionsmenge, das freie Guthaben
        # wäre also systematisch zu klein (siehe balance_guard.py).
        self.assertEqual(
            client.call_log,
            ["cancel_order", "get_asset_balance", "place_market_sell"],
        )
        closed_trade = strategy._ledger._read()[0]
        self.assertEqual(closed_trade["status"], "closed")
        self.assertEqual(closed_trade["exit_reason"], "signal")

    def test_internal_stop_loss_exit_also_cancels_stop_order_first(self):
        """
        Über die wörtliche Vorgabe hinaus (die das nur für den
        Signal-Exit verlangt hat): derselbe Cancel-vor-Verkauf-Ablauf
        gilt auch, wenn der interne is_stop_loss_hit()-Check auslöst,
        bevor die Exchange-Order gefüllt ist - sonst bliebe eine
        verwaiste Order an der Börse zurück, nachdem der Bot selbst per
        Market-Order verkauft hat.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        order_id = open_trade["stop_loss_order_id"]

        strategy._close_position(open_trade, price=44_000.0, reason="stop_loss")

        self.assertEqual(client.cancel_calls, [("BTCUSDT", order_id)])
        self.assertEqual(len(client.market_sell_calls), 1)

    # -- Race Condition: Order füllt sich ZWISCHEN Status-Check und Cancel --

    def test_close_position_when_cancel_fails_because_already_filled(self):
        """
        Race Condition aus der Aufgabenstellung: die Stop-Loss-Order war
        beim letzten Status-Check noch "NEW", füllt sich aber an der
        Börse, BEVOR der Cancel-Aufruf durchkommt - cancel_order()
        schlägt deshalb fehl, weil die Order nicht mehr existiert/aktiv
        ist. Der Bot darf jetzt NICHT nochmal verkaufen (die Position ist
        bereits weg), sondern muss die Position anhand der tatsächlichen
        Fülldaten der Stop-Order als per Stop-Loss geschlossen markieren -
        exakt wie im bestehenden "schon beim Status-Check FILLED"-Fall.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        order_id = open_trade["stop_loss_order_id"]

        quantity = 15.0 / 50_000.0
        fill_price = 44_900.0
        # Order füllt sich "im selben Moment", in dem der Bot versucht,
        # sie zu stornieren - cancel_order() (siehe FakeTradingClient)
        # schlägt dadurch automatisch fehl, weil der Status nicht mehr
        # "NEW" ist, exakt wie beim echten Binance-Client (Fehlercode
        # -2011 "Unknown order sent").
        client.fill_order(order_id, executed_qty=quantity, cumulative_quote=quantity * fill_price)

        # Ausgangs-Reason ist hier bewusst "signal" (Trend-Umkehr) - der
        # ausschlaggebende Fakt ist, dass die Order in Wahrheit per
        # Stop-Loss gefüllt wurde, nicht der ursprüngliche Exit-Grund.
        strategy._close_position(open_trade, price=52_000.0, reason="signal")

        self.assertEqual(client.cancel_calls, [("BTCUSDT", order_id)])
        self.assertEqual(client.market_sell_calls, [], "Kein zweiter Verkaufsversuch erlaubt")
        closed_trade = strategy._ledger._read()[0]
        self.assertEqual(closed_trade["status"], "closed")
        self.assertEqual(closed_trade["exit_reason"], "stop_loss")
        self.assertAlmostEqual(closed_trade["exit_price"], fill_price, places=2)

    def test_close_position_when_cancel_fails_transiently_stays_open(self):
        """
        Abgrenzung zum vorigen Test: ein ECHTER transienter Cancel-Fehler
        (z.B. Netzwerk-Timeout) sagt nichts darüber aus, ob die Order
        noch offen ist. Der Bot darf die Position dann weder fälschlich
        als geschlossen markieren NOCH selbst verkaufen (Risiko einer
        Doppel-Order, falls die Stop-Order in Wahrheit noch aktiv ist) -
        der Exit muss im nächsten Zyklus erneut versucht werden.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        order_id = open_trade["stop_loss_order_id"]

        client.force_transient_cancel_failure = True

        strategy._close_position(open_trade, price=52_000.0, reason="signal")

        self.assertEqual(client.cancel_calls, [("BTCUSDT", order_id)])
        # Ground Truth wurde nachgeprüft ...
        self.assertEqual(client.order_status_calls, [("BTCUSDT", order_id)])
        # ... zeigt aber weiterhin "NEW" -> weder verkaufen noch schließen.
        self.assertEqual(client.market_sell_calls, [])
        still_open = strategy._ledger.open_position()
        self.assertIsNotNone(still_open)
        self.assertEqual(still_open["id"], open_trade["id"])
        self.assertEqual(client.orders[order_id]["status"], "NEW")
        self.assertEqual(still_open["uncertain_cycles"], 1)

    def test_uncertain_streak_triggers_warning_after_threshold(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        client.force_transient_cancel_failure = True

        with mock.patch("dca_bot.trend_strategy.send_notification") as mock_notify:
            for _ in range(UNCERTAIN_CYCLES_WARNING_THRESHOLD - 1):
                open_trade = strategy._ledger.open_position()
                strategy._close_position(open_trade, price=52_000.0, reason="signal")
            mock_notify.assert_not_called()

            open_trade = strategy._ledger.open_position()
            strategy._close_position(open_trade, price=52_000.0, reason="signal")

        mock_notify.assert_called_once()
        (warning_text,), _ = mock_notify.call_args
        self.assertIn("[TREND-WARNUNG]", warning_text)
        self.assertIn(str(UNCERTAIN_CYCLES_WARNING_THRESHOLD), warning_text)

        open_trade = strategy._ledger.open_position()
        self.assertEqual(open_trade["uncertain_cycles"], UNCERTAIN_CYCLES_WARNING_THRESHOLD)

    def test_uncertain_counter_resets_after_successful_resolution(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)

        client.force_transient_cancel_failure = True
        for _ in range(UNCERTAIN_CYCLES_WARNING_THRESHOLD - 1):
            open_trade = strategy._ledger.open_position()
            strategy._close_position(open_trade, price=52_000.0, reason="signal")
        self.assertEqual(
            strategy._ledger.open_position()["uncertain_cycles"],
            UNCERTAIN_CYCLES_WARNING_THRESHOLD - 1,
        )

        # Der nächste Versuch klappt (z.B. Netzwerk wieder da) - Cancel
        # gelingt, normaler Verkauf, Zähler muss zurückgesetzt sein.
        client.force_transient_cancel_failure = False
        open_trade = strategy._ledger.open_position()
        strategy._close_position(open_trade, price=52_000.0, reason="signal")

        self.assertIsNone(strategy._ledger.open_position())
        self.assertEqual(len(client.market_sell_calls), 1)
        closed_trade = strategy._ledger._read()[0]
        self.assertEqual(closed_trade["uncertain_cycles"], 0)

    # -- c) Gefüllte Stop-Order wird im nächsten Zyklus korrekt als Exit erkannt --

    def test_execute_once_detects_filled_stop_order_before_internal_check(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        order_id = open_trade["stop_loss_order_id"]

        # Exchange hat die Stop-Order bereits gefüllt (z.B. zwischen zwei
        # Zyklen), realistisch nahe am Stop-Preis von 45.000 (10% unter
        # dem Entry @ 50.000). Preis für den nächsten Zyklus bewusst ÜBER
        # der internen Stop-Loss-Schwelle gewählt, damit is_stop_loss_hit()
        # NICHT selbst auslösen würde - der Fund muss also wirklich vom
        # Order-Status-Check kommen, nicht zufällig vom Preis.
        quantity = 15.0 / 50_000.0  # amount_per_trade (Default) / Entry-Preis
        fill_price = 44_850.0
        client.fill_order(
            order_id, executed_qty=quantity, cumulative_quote=quantity * fill_price
        )
        client.price = 49_000.0

        strategy.execute_once()

        # Kein eigener Verkaufsversuch, obwohl die Position noch als
        # "offen" im Ledger stand, bevor execute_once lief.
        self.assertEqual(client.market_sell_calls, [])
        closed_trade = strategy._ledger._read()[0]
        self.assertEqual(closed_trade["status"], "closed")
        self.assertEqual(closed_trade["exit_reason"], "stop_loss")
        self.assertAlmostEqual(closed_trade["exit_price"], fill_price, places=2)
        # Stop-Loss-Latch muss wie bei jedem Stop-Loss-Exit pausieren.
        self.assertTrue(strategy._stop_loss.is_paused())

    def test_stop_fill_analysis_logged_on_exchange_fill(self):
        """
        Dediziertes [STOP-FILL-ANALYSE]-Log für das echte Füllverhalten
        (Limit-Preis vs. tatsächlicher Füllpreis) - sammelt über die
        Paper-Trade-Phase automatisch Daten zur Offset-Zuverlässigkeit.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        order_id = open_trade["stop_loss_order_id"]
        limit_price = open_trade["stop_limit_price"]
        self.assertIsNotNone(limit_price)

        quantity = 15.0 / 50_000.0
        fill_price = limit_price + 12.34  # leicht ueber dem Limit-Preis gefuellt
        client.fill_order(order_id, executed_qty=quantity, cumulative_quote=quantity * fill_price)
        client.price = 49_000.0

        with self.assertLogs("trend_bot", level="INFO") as captured:
            strategy.execute_once()

        fill_analysis_lines = [line for line in captured.output if "[STOP-FILL-ANALYSE]" in line]
        self.assertEqual(len(fill_analysis_lines), 1)
        self.assertIn(f"Limit: {limit_price:.2f}", fill_analysis_lines[0])
        self.assertIn(f"gefüllt bei: {fill_price:.2f}", fill_analysis_lines[0])

    def test_latch_is_set_even_without_stop_limit_price(self):
        """
        Regressionstest zu W6: Der Stop-Loss-Latch darf nicht davon
        abhaengen, ob die [STOP-FILL-ANALYSE]-Zeile geschrieben werden
        kann.

        Vor dem Fix stand `self._stop_loss.pause(...)` am Ende von
        _log_stop_fill_analysis(), hinter dessen `return` fuer einen
        fehlenden stop_limit_price. Eine ueber einen Exchange-Fill
        geschlossene Position ohne hinterlegten Limitpreis bekam deshalb
        KEINEN Latch - der Bot haette im naechsten Zyklus sofort wieder
        einsteigen duerfen, also genau der Whipsaw, gegen den der Latch
        gebaut ist.

        Dieser Zustand entsteht real: die Stop-Order wurde erst spaeter
        nachgereicht (siehe _ensure_stop_loss_protection /
        _attach_reconciled_stop_order), oder der Ledger-Eintrag stammt
        aus der Zeit vor Einfuehrung des Feldes.

        Faellt gegen den alten Code um.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        order_id = open_trade["stop_loss_order_id"]

        # Limitpreis gezielt entfernen, Order-ID bleibt - genau die
        # Kombination, die vorher durchs Raster fiel.
        strategy._ledger.set_stop_loss_order(open_trade["id"], order_id, None)

        quantity = 15.0 / 50_000.0
        fill_price = 44_800.0
        client.fill_order(order_id, executed_qty=quantity, cumulative_quote=quantity * fill_price)
        client.price = 49_000.0

        with self.assertLogs("trend_bot", level="INFO") as captured:
            strategy.execute_once()

        closed_trade = strategy._ledger._read()[0]
        self.assertEqual(closed_trade["status"], "closed")
        self.assertEqual(closed_trade["exit_reason"], "stop_loss")
        self.assertTrue(
            strategy._stop_loss.is_paused(),
            "Stop-Loss-Latch muss auch ohne stop_limit_price gesetzt werden",
        )
        # Die Analyse-Zeile entfaellt mangels Vergleichswert - das ist
        # korrekt und darf folgenlos bleiben.
        self.assertEqual(
            [line for line in captured.output if "[STOP-FILL-ANALYSE]" in line], []
        )

    def test_execute_once_leaves_open_position_when_stop_order_still_new(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)

        # Preis bewusst über der Stop-Loss-Schwelle, kein Trigger erwartet.
        client.price = 51_000.0
        strategy.execute_once()

        open_trade = strategy._ledger.open_position()
        self.assertIsNotNone(open_trade)
        self.assertEqual(client.market_sell_calls, [])

    # -- d) Reconciliation beim Neustart erkennt eine während "Downtime" gefüllte Order --

    def test_reconcile_on_startup_detects_fill_during_downtime(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        order_id = open_trade["stop_loss_order_id"]

        # Downtime simulieren: Order wurde gefüllt, WÄHREND kein
        # execute_once()-Zyklus lief - erst beim (simulierten) Neustart
        # wird eine neue Strategie-Instanz auf demselben Ledger erzeugt.
        quantity = 15.0 / 50_000.0  # amount_per_trade (Default) / Entry-Preis
        fill_price = 44_700.0
        client.fill_order(
            order_id, executed_qty=quantity, cumulative_quote=quantity * fill_price
        )

        restarted_strategy = TrendFollowingStrategy(self._make_config(True), client)
        restarted_strategy._seeded = True
        restarted_strategy.reconcile_on_startup()

        self.assertIsNone(restarted_strategy._ledger.open_position())
        self.assertEqual(client.market_sell_calls, [])
        closed_trade = restarted_strategy._ledger._read()[0]
        self.assertEqual(closed_trade["status"], "closed")
        self.assertEqual(closed_trade["exit_reason"], "stop_loss")

    def test_reconcile_on_startup_leaves_open_position_when_not_filled(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)

        restarted_strategy = TrendFollowingStrategy(self._make_config(True), client)
        restarted_strategy._seeded = True
        restarted_strategy.reconcile_on_startup()

        self.assertIsNotNone(restarted_strategy._ledger.open_position())

    def test_reconcile_on_startup_does_nothing_without_open_position(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        # Keine offene Position vorhanden.
        strategy.reconcile_on_startup()
        self.assertEqual(client.order_status_calls, [])


class TrendSellSafetyTestCase(TrendStrategyTestBase):
    """
    Tests für die Verkaufs-Sicherheit des Trend-Bots
    (Sicherheitsreview-Punkte K1 und K4, siehe
    trend_strategy.py._close_position).

    Teilt sich die Testumgebung (TrendStrategyTestBase) mit den
    Stop-Loss-Tests oben - die Szenarien hier bauen auf exakt derselben
    Umgebung auf, nur mit anderem Fokus:

    - K1: place_market_sell() gibt None in ZWEI völlig verschiedenen
      Fällen zurück (Dry-Run UND echter API-Fehler). Vor dem Fix wurden
      beide gleich behandelt - der Bot erfand bei einem echten Fehler
      einen Erlös aus quantity*price und schloss die Position trotzdem.
    - K4: Eine im Dry-Run eröffnete Position (dry_run=true im Ledger)
      wäre nach einem Umschalten auf TREND_BOT_ENABLE_TRADING=true real
      verkauft worden - Assets, die nie gekauft wurden.

    Trend-spezifisch gegenüber Grid: _resolve_stop_order_before_close()
    storniert die exchange-seitige Stop-Order, BEVOR verkauft wird.
    Schlägt der Verkauf dann fehl, wäre die weiterhin offene Position
    schutzlos - es muss eine NEUE Stop-Order platziert werden.
    """

    def _open_dry_run_position_then_enable_trading(self, price: float = 50_000.0):
        """
        Stellt exakt den Zustand her, um den es in K4 geht: Position im
        Dry-Run eröffnet, danach auf echtes Trading umgeschaltet. Das
        Ledger bleibt dasselbe, nur Config und Client wechseln - wie beim
        echten Umschalten per .env plus Bot-Neustart.
        """
        dry_strategy, _ = self._make_strategy(trading_enabled=False, price=price)
        dry_strategy._open_position(price)

        live_client = FakeTradingClient(trading_enabled=True, price=price)
        live_strategy = TrendFollowingStrategy(self._make_config(True), live_client)
        live_strategy._seeded = True
        return live_strategy, live_client

    # -- K4: Dry-Run-Position wird NIE real verkauft --

    def test_dry_run_position_is_never_really_sold_when_trading_enabled(self):
        strategy, client = self._open_dry_run_position_then_enable_trading()
        open_trade = strategy._ledger.open_position()
        self.assertTrue(open_trade["dry_run"], "Vorbedingung: im Dry-Run eröffnet")

        with self.assertLogs("trend_bot", level="INFO") as captured:
            strategy._close_position(open_trade, price=52_000.0, reason="signal")

        self.assertEqual(client.market_sell_calls, [], "Keine echte Verkaufsorder erlaubt")
        self.assertEqual(client.cancel_calls, [], "Dry-Run-Position hat keine Stop-Order")

        marker_lines = [line for line in captured.output if "[DRY-RUN-POSITION]" in line]
        self.assertEqual(len(marker_lines), 1)
        self.assertIn("Verkauf bleibt simuliert", marker_lines[0])

        # Simuliert geschlossen - korrektes Verhalten, nur ohne echte Order.
        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "signal")
        self.assertIsNone(strategy._ledger.open_position())

    def test_dry_run_position_stop_loss_exit_still_latches(self):
        """
        Ein Stop-Loss-Exit einer Dry-Run-Position bleibt simuliert, muss
        aber weiterhin den Stop-Loss-Latch setzen - die Strategie hat den
        Ausstieg ja regulär entschieden.
        """
        strategy, client = self._open_dry_run_position_then_enable_trading()
        open_trade = strategy._ledger.open_position()

        strategy._close_position(open_trade, price=44_000.0, reason="stop_loss")

        self.assertEqual(client.market_sell_calls, [])
        self.assertTrue(strategy._stop_loss.is_paused())

    # -- K1: fehlgeschlagener echter Verkauf schließt die Position NICHT --

    def test_failed_real_sell_keeps_position_open_without_fake_pnl(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        client.force_market_sell_failure = True

        with mock.patch("dca_bot.trend_strategy.send_notification") as mock_notify:
            with self.assertLogs("trend_bot", level="INFO") as captured:
                strategy._close_position(open_trade, price=52_000.0, reason="signal")

        self.assertEqual(len(client.market_sell_calls), 1, "Der Verkauf wurde versucht")

        still_open = strategy._ledger.open_position()
        self.assertIsNotNone(still_open, "Position muss OFFEN bleiben")
        self.assertEqual(still_open["id"], open_trade["id"])
        self.assertIsNone(still_open["realized_pnl"])
        self.assertIsNone(still_open["exit_price"])
        self.assertIsNone(still_open["exit_time"])
        self.assertIsNone(still_open["exit_reason"])

        warnings = [line for line in captured.output if "[TREND-VERKAUF-FEHLGESCHLAGEN]" in line]
        self.assertTrue(warnings)
        self.assertIn("[TREND-VERKAUF-FEHLGESCHLAGEN]", mock_notify.call_args[0][0])

    def test_failed_real_sell_places_new_stop_loss_order(self):
        """
        Der Trend-spezifische Kern: _resolve_stop_order_before_close() hat
        die Stop-Order VOR dem fehlgeschlagenen Verkauf storniert, die
        weiterhin offene Position wäre danach ungeschützt. Es muss eine
        NEUE Stop-Order platziert und im Ledger hinterlegt werden.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        original_order_id = open_trade["stop_loss_order_id"]
        client.force_market_sell_failure = True

        strategy._close_position(open_trade, price=52_000.0, reason="signal")

        # Die ursprüngliche Order wurde storniert ...
        self.assertEqual(client.orders[original_order_id]["status"], "CANCELED")
        # ... und eine zweite Stop-Order platziert (die erste kam vom Entry).
        self.assertEqual(len(client.stop_order_calls), 2)
        self.assertEqual(len(client.market_sell_calls), 1)

        _, quantity, stop_price, limit_price = client.stop_order_calls[1]
        self.assertAlmostEqual(quantity, open_trade["quantity"], places=10)
        # Schwelle identisch zum Original: 10% unter dem Einstiegspreis.
        self.assertAlmostEqual(stop_price, 45_000.0, places=2)
        self.assertAlmostEqual(limit_price, 45_000.0 * (1 - 0.005), places=2)

        still_open = strategy._ledger.open_position()
        self.assertIsNotNone(still_open)
        self.assertNotEqual(still_open["stop_loss_order_id"], original_order_id)
        self.assertEqual(client.orders[still_open["stop_loss_order_id"]]["status"], "NEW")
        self.assertAlmostEqual(still_open["stop_limit_price"], limit_price, places=2)

    def test_failed_real_sell_and_failed_stop_order_warns_twice(self):
        """
        Doppelt kritisch: weder verkauft noch abgesichert. Muss deutlich
        eskaliert werden, und die längst stornierte Order-ID darf nicht
        als gültige Absicherung im Ledger stehen bleiben.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        client.force_market_sell_failure = True
        client.force_stop_order_failure = True

        with mock.patch("dca_bot.trend_strategy.send_notification") as mock_notify:
            with self.assertLogs("trend_bot", level="INFO") as captured:
                strategy._close_position(open_trade, price=52_000.0, reason="signal")

        error_lines = [line for line in captured.output if line.startswith("ERROR")]
        self.assertEqual(len(error_lines), 1, "Der doppelt kritische Zustand muss ERROR sein")
        self.assertIn("weder", error_lines[0])
        self.assertIn("noch exchange-seitig abgesichert", error_lines[0])

        # Bewusst EINE Telegram-Nachricht, die beide Fakten nennt, statt
        # zweier aufeinanderfolgender - der Empfaenger braucht den
        # Gesamtzustand, nicht zwei Teilmeldungen.
        self.assertEqual(mock_notify.call_count, 1)
        (text,), _ = mock_notify.call_args
        self.assertIn("[TREND-FEHLER]", text)
        self.assertIn("Verkauf", text)
        self.assertIn("Stop-Loss-Order", text)

        still_open = strategy._ledger.open_position()
        self.assertIsNotNone(still_open)
        self.assertIsNone(
            still_open["stop_loss_order_id"],
            "Die stornierte Order-ID darf nicht als Absicherung stehen bleiben",
        )
        self.assertIsNone(still_open["stop_limit_price"])

    def test_failed_real_sell_does_not_latch_stop_loss(self):
        """
        Kein Ausstieg = kein Stop-Loss-Latch. Sonst würde ein reiner
        API-Fehler dauerhaft neue Einstiege blockieren, obwohl die
        Position noch offen ist.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        client.force_market_sell_failure = True

        strategy._close_position(open_trade, price=44_000.0, reason="stop_loss")

        self.assertFalse(strategy._stop_loss.is_paused())
        self.assertIsNotNone(strategy._ledger.open_position())

    def test_failed_real_sell_is_retried_next_cycle(self):
        """Die offene Position wird im nächsten Zyklus erneut verkauft."""
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        client.force_market_sell_failure = True
        strategy._close_position(strategy._ledger.open_position(), 52_000.0, reason="signal")

        client.force_market_sell_failure = False
        strategy._close_position(strategy._ledger.open_position(), 52_000.0, reason="signal")

        self.assertIsNone(strategy._ledger.open_position())
        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        # Die beim ersten Fehlschlag neu platzierte Stop-Order wurde vor
        # dem zweiten Versuch ordentlich storniert.
        self.assertEqual(len(client.cancel_calls), 2)

    # -- Regression: erfolgreicher echter Verkauf unverändert --

    def test_successful_real_sell_still_closes_with_real_proceeds(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        self.assertFalse(open_trade["dry_run"], "Vorbedingung: echte Position")

        strategy._close_position(open_trade, price=52_000.0, reason="signal")

        self.assertEqual(len(client.market_sell_calls), 1)
        # Keine zusaetzliche Stop-Order - nur die vom Entry.
        self.assertEqual(len(client.stop_order_calls), 1)
        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "signal")
        # proceeds stammen aus cummulativeQuoteQty der echten Order - der
        # Fake-Client fuellt zu client.price, nicht zum an _close_position
        # uebergebenen Preis (wie an der Boerse: der Fuellpreis entsteht
        # beim Ausfuehren, nicht aus dem zuvor gelesenen Ticker).
        expected_pnl = open_trade["quantity"] * client.price - open_trade["quote_spent"]
        self.assertAlmostEqual(closed["realized_pnl"], expected_pnl, places=6)

    def test_missing_dry_run_field_blocks_any_sell_attempt(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        del open_trade["dry_run"]  # simuliert einen manuell editierten Ledger-Eintrag

        with self.assertLogs("trend_bot", level="INFO") as captured:
            strategy._close_position(open_trade, price=52_000.0, reason="signal")

        self.assertEqual(client.market_sell_calls, [])
        self.assertEqual(client.cancel_calls, [], "Auch die Stop-Order bleibt unangetastet")
        self.assertIsNotNone(strategy._ledger.open_position())
        self.assertTrue(
            any("[TREND-POSITION-UNKLAR]" in line for line in captured.output),
            "Der unklare Zustand muss sichtbar geloggt werden",
        )


class TrendStopLossProtectionTestCase(TrendStrategyTestBase):
    """
    Tests dafür, dass eine offene, echte Position nicht dauerhaft ohne
    exchange-seitige Stop-Loss-Order bleiben kann (siehe
    trend_strategy.py._ensure_stop_loss_protection).

    Zwei Wege führen in diesen Zustand, beide waren vorher Sackgassen:
    die Stop-Order konnte schon beim Entry nicht platziert werden, oder
    ein fehlgeschlagener Verkauf konnte seine stornierte Absicherung
    nicht ersetzen und der Exit-Grund entfiel danach (Trend dreht zurück
    auf "up"). In beiden Fällen hätte nie wieder etwas eine neue Order
    platziert - die Position wäre bei Bot-/Stromausfall ungeschützt
    gewesen, ohne dass es jemals eskaliert.
    """

    def _open_position_without_stop_order(self, price: float = 50_000.0):
        """
        Erzeugt genau den kritischen Zustand: echte Position (dry_run=False),
        aber ohne stop_loss_order_id, weil die Order beim Entry scheiterte.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=price)
        client.force_stop_order_failure = True
        strategy._open_position(price)

        open_trade = strategy._ledger.open_position()
        self.assertFalse(open_trade["dry_run"], "Vorbedingung: echte Position")
        self.assertIsNone(open_trade["stop_loss_order_id"], "Vorbedingung: ungeschützt")
        return strategy, client

    # -- Wiederherstellung im regulaeren Zyklus --

    def test_execute_once_places_missing_stop_order(self):
        strategy, client = self._open_position_without_stop_order()
        client.force_stop_order_failure = False
        # Preis deutlich ueber der Stop-Schwelle (45.000), damit kein
        # Exit ausgeloest wird - die Position soll den Zyklus ueberleben.
        client.price = 51_000.0

        with self.assertLogs("trend_bot", level="INFO") as captured:
            strategy.execute_once()

        # Zwei Versuche insgesamt: der gescheiterte beim Entry, der neue hier.
        self.assertEqual(len(client.stop_order_calls), 2)
        _, quantity, stop_price, limit_price = client.stop_order_calls[1]
        self.assertAlmostEqual(stop_price, 45_000.0, places=2)
        self.assertAlmostEqual(limit_price, 45_000.0 * (1 - 0.005), places=2)

        open_trade = strategy._ledger.open_position()
        self.assertIsNotNone(open_trade["stop_loss_order_id"])
        self.assertEqual(client.orders[open_trade["stop_loss_order_id"]]["status"], "NEW")
        self.assertAlmostEqual(open_trade["stop_limit_price"], limit_price, places=2)
        self.assertEqual(open_trade["unprotected_cycles"], 0)
        self.assertAlmostEqual(quantity, open_trade["quantity"], places=10)

        self.assertTrue(
            any("[TREND-ABSICHERUNG-WIEDERHERGESTELLT]" in line for line in captured.output)
        )

    def test_already_protected_position_gets_no_second_order(self):
        """Regression: eine abgesicherte Position wird nicht angefasst."""
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        client.price = 51_000.0

        strategy.execute_once()

        self.assertEqual(len(client.stop_order_calls), 1, "Nur die Order vom Entry")

    # -- Eskalation bei wiederholtem Fehlschlag --

    def test_repeated_failures_increment_counter_and_warn_at_threshold(self):
        strategy, client = self._open_position_without_stop_order()
        client.price = 51_000.0  # kein Exit, Position ueberlebt jeden Zyklus
        # force_stop_order_failure bleibt True: die Neuplatzierung scheitert weiter.

        with mock.patch("dca_bot.trend_strategy.send_notification") as mock_notify:
            for expected_count in range(1, UNPROTECTED_CYCLES_WARNING_THRESHOLD):
                strategy.execute_once()
                self.assertEqual(
                    strategy._ledger.open_position()["unprotected_cycles"], expected_count
                )
                mock_notify.assert_not_called()

            strategy.execute_once()

        self.assertEqual(
            strategy._ledger.open_position()["unprotected_cycles"],
            UNPROTECTED_CYCLES_WARNING_THRESHOLD,
        )
        mock_notify.assert_called_once()
        (text,), _ = mock_notify.call_args
        self.assertIn("[TREND-WARNUNG]", text)
        self.assertIn(str(UNPROTECTED_CYCLES_WARNING_THRESHOLD), text)
        self.assertIn("ohne exchange-seitige", text)

    def test_counter_resets_and_all_clear_after_successful_recovery(self):
        strategy, client = self._open_position_without_stop_order()
        client.price = 51_000.0

        with mock.patch("dca_bot.trend_strategy.send_notification") as mock_notify:
            for _ in range(UNPROTECTED_CYCLES_WARNING_THRESHOLD):
                strategy.execute_once()
            self.assertEqual(mock_notify.call_count, 1, "Warnung ist raus")

            # Ursache behoben (z.B. API wieder erreichbar).
            client.force_stop_order_failure = False
            strategy.execute_once()

        open_trade = strategy._ledger.open_position()
        self.assertIsNotNone(open_trade["stop_loss_order_id"])
        self.assertEqual(open_trade["unprotected_cycles"], 0)
        # Nach einer gesendeten Warnung gehoert die Entwarnung in denselben Kanal.
        self.assertEqual(mock_notify.call_count, 2)
        (text,), _ = mock_notify.call_args
        self.assertIn("[TREND-ABSICHERUNG-WIEDERHERGESTELLT]", text)

    def test_no_all_clear_notification_without_prior_warning(self):
        """
        Ein einzelner Fehlschlag, der sich sofort wieder einrenkt, ist
        kein Telegram-Ereignis - nur das Log haelt ihn fest.
        """
        strategy, client = self._open_position_without_stop_order()
        client.price = 51_000.0

        with mock.patch("dca_bot.trend_strategy.send_notification") as mock_notify:
            strategy.execute_once()          # 1 Fehlschlag, unter der Schwelle
            client.force_stop_order_failure = False
            strategy.execute_once()          # erholt sich

        self.assertIsNotNone(strategy._ledger.open_position()["stop_loss_order_id"])
        mock_notify.assert_not_called()

    # -- Der zweite Eintrittsweg: nach fehlgeschlagenem Verkauf dreht der Trend zurueck --

    def test_recovers_after_failed_sell_when_exit_reason_disappears(self):
        """
        Genau die gefundene Luecke: Verkauf UND Neuplatzierung scheitern,
        danach entfaellt der Exit-Grund (kein Stop-Loss-Treffer, kein
        Abwaertssignal). Vorher haette nie wieder etwas die Position
        abgesichert - jetzt repariert der naechste Zyklus das.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        client.force_market_sell_failure = True
        client.force_stop_order_failure = True

        strategy._close_position(open_trade, price=52_000.0, reason="signal")
        self.assertIsNone(
            strategy._ledger.open_position()["stop_loss_order_id"],
            "Vorbedingung: Position ist jetzt ungeschuetzt offen",
        )

        # Naechster Zyklus: kein Exit-Grund mehr, Ursache behoben.
        client.force_stop_order_failure = False
        client.price = 51_000.0
        strategy.execute_once()

        open_trade = strategy._ledger.open_position()
        self.assertIsNotNone(open_trade["stop_loss_order_id"])
        self.assertEqual(client.orders[open_trade["stop_loss_order_id"]]["status"], "NEW")
        self.assertEqual(open_trade["unprotected_cycles"], 0)

    # -- Wiederherstellung beim Neustart --

    def test_reconcile_on_startup_places_missing_stop_order(self):
        strategy, client = self._open_position_without_stop_order()
        client.force_stop_order_failure = False

        restarted = TrendFollowingStrategy(self._make_config(True), client)
        restarted._seeded = True
        with self.assertLogs("trend_bot", level="INFO") as captured:
            restarted.reconcile_on_startup()

        open_trade = restarted._ledger.open_position()
        self.assertIsNotNone(open_trade["stop_loss_order_id"])
        self.assertEqual(open_trade["unprotected_cycles"], 0)
        self.assertTrue(
            any(
                "[REKONZILIATION] [TREND-ABSICHERUNG-WIEDERHERGESTELLT]" in line
                for line in captured.output
            ),
            "Der Reconciliation-Pfad muss eigens markiert sein",
        )

    def test_reconcile_on_startup_counts_failure(self):
        strategy, client = self._open_position_without_stop_order()
        # force_stop_order_failure bleibt True

        restarted = TrendFollowingStrategy(self._make_config(True), client)
        restarted._seeded = True
        restarted.reconcile_on_startup()

        self.assertIsNone(restarted._ledger.open_position()["stop_loss_order_id"])
        self.assertEqual(restarted._ledger.open_position()["unprotected_cycles"], 1)

    # -- Abgrenzung: Dry-Run wird nicht angefasst --

    def test_dry_run_position_gets_no_stop_order(self):
        """
        Eine Dry-Run-Position existiert an der Boerse nicht - fuer sie darf
        auch keine echte Stop-Order platziert werden (gleiche Logik wie K4).
        """
        dry_strategy, _ = self._make_strategy(trading_enabled=False, price=50_000.0)
        dry_strategy._open_position(50_000.0)

        live_client = FakeTradingClient(trading_enabled=True, price=51_000.0)
        live_strategy = TrendFollowingStrategy(self._make_config(True), live_client)
        live_strategy._seeded = True

        live_strategy.execute_once()

        self.assertEqual(live_client.stop_order_calls, [], "Keine echte Order fuer Dry-Run")
        self.assertEqual(live_strategy._ledger.open_position()["unprotected_cycles"], 0)

    def test_dry_run_mode_places_no_stop_order(self):
        """Im Dry-Run-Modus wird ohnehin nie eine echte Order platziert."""
        strategy, client = self._open_position_without_stop_order()

        dry_client = FakeTradingClient(trading_enabled=False, price=51_000.0)
        dry_strategy = TrendFollowingStrategy(self._make_config(False), dry_client)
        dry_strategy._seeded = True

        dry_strategy.execute_once()

        self.assertEqual(dry_client.stop_order_calls, [])
        self.assertEqual(dry_strategy._ledger.open_position()["unprotected_cycles"], 0)


class TrendTradingRulesTestCase(TrendStrategyTestBase):
    """
    Tests für die Anbindung an die echten Handelsregeln und die
    Gebührenkorrektur (Sicherheitsreview-Punkt K3, siehe order_utils.py).

    Der eigentliche Live-Schaden bei diesem Bot: die beim Kauf gespeicherte
    Menge wird direkt für die exchange-seitige Stop-Loss-Order verwendet.
    Ist sie um die Gebühr zu hoch, lehnt die Börse die Order ab - und die
    Position steht ohne Absicherung da, genau das, was der Stop-Loss
    verhindern soll.
    """

    def test_buy_with_btc_commission_reduces_stored_quantity(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        client.commission_rate = 0.001  # 0,1%, Live-Standardsatz
        client.commission_asset = "BTC"

        strategy._open_position(50_000.0)

        open_trade = strategy._ledger.open_position()
        gross_quantity = 15.0 / 50_000.0  # 0.0003
        self.assertLess(
            open_trade["quantity"],
            gross_quantity,
            "Die gespeicherte Menge muss um die BTC-Gebühr gekürzt sein",
        )
        # 0.0003 - 0.0000003 = 0.0002997 -> auf stepSize 0.00001 abgerundet
        self.assertAlmostEqual(open_trade["quantity"], 0.00029, places=10)

    def test_stop_order_uses_fee_adjusted_quantity(self):
        """
        Der Kern von K3 für den Trend-Bot: die Stop-Loss-Order darf nur
        über die tatsächlich verfügbare Menge laufen.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        client.commission_rate = 0.001

        strategy._open_position(50_000.0)

        open_trade = strategy._ledger.open_position()
        _, stop_quantity, _, _ = client.stop_order_calls[0]
        self.assertAlmostEqual(stop_quantity, open_trade["quantity"], places=12)
        self.assertLess(stop_quantity, 15.0 / 50_000.0)

    def test_buy_with_bnb_commission_leaves_quantity_unchanged(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        client.commission_rate = 0.001
        client.commission_asset = "BNB"  # BNB-Rabatt aktiv

        strategy._open_position(50_000.0)

        self.assertAlmostEqual(
            strategy._ledger.open_position()["quantity"], 15.0 / 50_000.0, places=10
        )

    def test_sell_proceeds_are_net_of_quote_commission(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()

        client.commission_rate = 0.001  # gilt ab jetzt auch für den Verkauf
        strategy._close_position(open_trade, price=50_000.0, reason="signal")

        closed = strategy._ledger._read()[0]
        gross = open_trade["quantity"] * client.price
        expected_pnl = gross * (1 - 0.001) - open_trade["quote_spent"]
        self.assertAlmostEqual(closed["realized_pnl"], expected_pnl, places=8)
        self.assertLess(
            closed["realized_pnl"],
            gross - open_trade["quote_spent"],
            "Bruttoerlös wäre zu optimistisch",
        )

    def test_trading_rules_failure_is_not_silently_ignored(self):
        """
        Ohne tickSize/stepSize lässt sich keine Order sicher runden - der
        Fehler muss durchschlagen statt auf stille Defaults auszuweichen.
        Entscheidend: er passiert VOR jeder Order, es bleibt also nichts
        Halbfertiges zurück.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        client.force_trading_rules_failure = True

        with self.assertRaises(RuntimeError):
            strategy._open_position(50_000.0)

        self.assertEqual(client.market_buy_calls, [], "Keine Order ohne gültige Regeln")
        self.assertIsNone(strategy._ledger.open_position(), "Kein halber Ledger-Eintrag")

    def test_rules_are_fetched_before_the_buy_order(self):
        """
        Reihenfolge ist sicherheitsrelevant: würden die Regeln erst NACH
        dem Kauf gebraucht, könnte ein Fehler dort einen real ausgeführten
        Kauf unverbucht lassen.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)

        strategy._open_position(50_000.0)

        self.assertGreaterEqual(client.trading_rules_calls, 1)

    def test_dry_run_quantity_is_quantized_but_not_fee_adjusted(self):
        """
        Im Dry-Run gibt es keinen Fill und damit keine bekannte Gebühr -
        sie wird bewusst nicht geschätzt. Quantisiert wird trotzdem, damit
        simulierte und echte Werte vergleichbar bleiben.
        """
        strategy, client = self._make_strategy(trading_enabled=False, price=51_234.0)
        client.commission_rate = 0.001  # darf im Dry-Run keine Wirkung haben

        strategy._open_position(51_234.0)

        quantity = strategy._ledger.open_position()["quantity"]
        raw = 15.0 / 51_234.0
        self.assertLessEqual(quantity, raw)
        steps = quantity / FAKE_TRADING_RULES.step_size
        self.assertAlmostEqual(steps, round(steps), places=6)


class StopFillFeeCorrectionTestCase(TrendStrategyTestBase):
    """
    Die letzte offene Stelle der K3-Restluecke: der Ausstieg ueber eine
    bereits gefuellte, exchange-seitige Stop-Loss-Order.

    `_close_from_filled_stop_order()` buchte `cummulativeQuoteQty` direkt
    als Erloes - also BRUTTO. `get_order()`-Antworten enthalten keine
    `fills`, und die Methode hat `get_order_with_fills()` nie aufgerufen,
    obwohl das Werkzeug seit dem K2-Fix existiert und in fuenf
    Reconciliation-Pfaden genutzt wird. Die Projektdoku wies die Luecke
    trotzdem als geschlossen aus.

    Der Schaden ist klein (rund 0,1 % des Erloeses, zu optimistisch),
    landet aber im `realized_pnl` des Ledgers - also in genau der Zahl,
    an der die Strategie nach der Paper-Trade-Phase gemessen wird. Und
    betroffen ist ausgerechnet der Pfad, fuer den die boersenseitige
    Absicherung ueberhaupt gebaut wurde: Bot-Ausfall oder Kurssprung
    ueber Nacht.
    """

    ENTRY_PRICE = 50_000.0
    # amount_per_trade (Default 15.0) / Einstiegspreis
    QUANTITY = 15.0 / 50_000.0
    FILL_PRICE = 44_850.0

    def _open_and_fill_stop(self, commission: float | None):
        """Position eroeffnen und ihre Stop-Order an der Boerse fuellen."""
        strategy, client = self._make_strategy(
            trading_enabled=True, price=self.ENTRY_PRICE
        )
        strategy._open_position(self.ENTRY_PRICE)
        open_trade = strategy._ledger.open_position()
        order_id = open_trade["stop_loss_order_id"]

        gross = self.QUANTITY * self.FILL_PRICE
        client.fill_order(
            order_id,
            executed_qty=self.QUANTITY,
            cumulative_quote=gross,
            commission=commission,
        )
        # Preis bewusst UEBER der internen Stop-Schwelle: Der Ausstieg
        # muss nachweislich vom Order-Status kommen, nicht vom internen
        # Stop-Loss (gleiche Absicherung wie im bestehenden Fill-Test).
        client.price = 49_000.0
        return strategy, client, gross

    def test_quote_commission_is_deducted_from_the_booked_proceeds(self):
        """
        Negativkontrolle gegen den alten Stand: Ohne den Fix steht hier
        der Bruttoerloes im Ledger.
        """
        commission = 0.15  # in USDT abgerechnet, wie bei einem Spot-Verkauf
        strategy, client, gross = self._open_and_fill_stop(commission)

        strategy.execute_once()

        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        expected_pnl = (gross - commission) - closed["quote_spent"]
        self.assertAlmostEqual(closed["realized_pnl"], expected_pnl, places=10)
        # Und ausdruecklich NICHT der Bruttowert.
        self.assertNotAlmostEqual(
            closed["realized_pnl"], gross - closed["quote_spent"], places=10
        )

    def test_the_fee_data_is_actually_fetched(self):
        """
        Der Kern des Befundes war, dass dieser Pfad `get_order_with_fills`
        nie aufgerufen hat - das wird hier direkt festgehalten, nicht nur
        ueber das Ergebnis.
        """
        strategy, client, _ = self._open_and_fill_stop(commission=0.15)
        self.assertEqual(client.order_with_fills_calls, 0)

        strategy.execute_once()

        self.assertEqual(client.order_with_fills_calls, 1)

    def test_commission_in_another_asset_leaves_the_proceeds_gross(self):
        """
        Gegenprobe: Bei aktivem BNB-Rabatt wird die Gebuehr nicht in USDT
        abgerechnet und schmaelert den Erloes deshalb nicht - dieselbe
        Regel wie in net_proceeds().
        """
        strategy, client = self._make_strategy(
            trading_enabled=True, price=self.ENTRY_PRICE
        )
        strategy._open_position(self.ENTRY_PRICE)
        open_trade = strategy._ledger.open_position()
        gross = self.QUANTITY * self.FILL_PRICE
        client.fill_order(
            open_trade["stop_loss_order_id"],
            executed_qty=self.QUANTITY,
            cumulative_quote=gross,
            commission=0.002,
            commission_asset="BNB",
        )
        client.price = 49_000.0

        strategy.execute_once()

        closed = strategy._ledger._read()[0]
        self.assertAlmostEqual(
            closed["realized_pnl"], gross - closed["quote_spent"], places=10
        )

    def test_missing_fee_data_still_closes_the_position_gross(self):
        """
        Der Normalfall auf dem Testnet: myTrades liefert nichts (Gebuehr
        dort 0). Dann bleibt es beim Bruttowert - und die Position wird
        trotzdem sauber geschlossen.
        """
        strategy, client, gross = self._open_and_fill_stop(commission=None)

        strategy.execute_once()

        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertAlmostEqual(
            closed["realized_pnl"], gross - closed["quote_spent"], places=10
        )

    def test_failed_rules_lookup_does_not_block_the_ledger_correction(self):
        """
        Die wichtigste Zusicherung des Fixes: Er haengt jetzt zwei
        API-Aufrufe in einen Pfad, der zuvor nur `get_order_status()`
        brauchte. Scheitert einer davon, darf das die Korrektur NICHT
        verhindern - die Boerse hat bereits verkauft, und eine im Ledger
        faelschlich offene Position wuerde der naechste Zyklus erneut zu
        verkaufen versuchen.

        Ohne die Kapselung wuerde `execute_once()` hier mit einem
        RuntimeError abbrechen und die Position offen lassen.
        """
        strategy, client, gross = self._open_and_fill_stop(commission=0.15)
        client.force_trading_rules_failure = True

        strategy.execute_once()

        self.assertIsNone(strategy._ledger.open_position())
        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "stop_loss")
        # Degradiert auf brutto - das Verhalten vor dem Fix, aber ohne
        # dass etwas haengen bleibt.
        self.assertAlmostEqual(
            closed["realized_pnl"], gross - closed["quote_spent"], places=10
        )
        # Und der Stop-Loss-Latch wird trotzdem gesetzt (W6).
        self.assertTrue(strategy._stop_loss.is_paused())

    def test_startup_reconciliation_path_gets_the_same_correction(self):
        """
        `_close_from_filled_stop_order` hat zwei Aufrufer: den regulaeren
        Zyklus und den Abgleich beim Bot-Start. Beide muessen die
        Gebuehrenkorrektur bekommen - sonst haengt die Richtigkeit der
        PnL davon ab, ob der Bot zwischendurch neu gestartet wurde.
        """
        commission = 0.15
        strategy, client, gross = self._open_and_fill_stop(commission)

        strategy.reconcile_on_startup()

        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertAlmostEqual(
            closed["realized_pnl"],
            (gross - commission) - closed["quote_spent"],
            places=10,
        )


class DeadStopOrderTestCase(TrendStrategyTestBase):
    """
    Sicherheitsreview-Punkte W7 und W8: der Zyklus-Check der
    exchange-seitigen Stop-Loss-Order kannte vorher nur zwei der vier
    moeglichen Ausgaenge.

    W7 - eine Order, die an der Boerse beendet wurde, ohne etwas zu
    bewegen (storniert/abgelaufen/abgelehnt), blieb dem Ledger als
    gueltige Absicherung erhalten. `_ensure_stop_loss_protection()`
    steigt bei jeder vorhandenen stop_loss_order_id sofort aus - die
    Position waere damit dauerhaft ungeschuetzt geblieben, ohne dass es
    je eskaliert.

    W8 - `PARTIALLY_FILLED` fiel komplett durch: der Bot sah "nicht
    FILLED" und tat nichts, obwohl ein Teil der Position an der Boerse
    bereits verkauft war.

    Beide werden jetzt ueber dieselbe Funktion bewertet wie der
    Pending-Pfad (order_lifecycle_state in pending_orders.py).
    """

    def _open_protected_position(self, price: float = 50_000.0):
        strategy, client = self._make_strategy(trading_enabled=True, price=price)
        strategy._open_position(price)
        open_trade = strategy._ledger.open_position()
        self.assertIsNotNone(
            open_trade["stop_loss_order_id"], "Vorbedingung: abgesichert"
        )
        return strategy, client, open_trade["stop_loss_order_id"]

    # -- W7: tote Order --

    def test_dead_stop_order_is_replaced_in_the_same_cycle(self):
        """
        Kern von W7: storniert entdeckt -> Zuordnung geloest -> neue
        Order noch im selben Durchlauf. Faellt gegen den alten Code um
        (dort blieb die tote ID stehen und blockierte jeden Ersatz).
        """
        strategy, client, order_id = self._open_protected_position()
        client.end_order_without_fill(order_id)
        client.price = 51_000.0  # ueber der Stop-Schwelle, kein Exit-Grund

        with mock.patch("dca_bot.trend_strategy.send_notification") as notify:
            with self.assertLogs("trend_bot", level="WARNING"):
                strategy.execute_once()

        open_trade = strategy._ledger.open_position()
        self.assertIsNotNone(open_trade, "Position bleibt offen")
        self.assertIsNotNone(
            open_trade["stop_loss_order_id"], "Neue Absicherung muss stehen"
        )
        self.assertNotEqual(
            open_trade["stop_loss_order_id"], order_id, "Muss eine NEUE Order sein"
        )
        # Entry-Order + urspruengliche Stop-Order + Ersatz-Stop-Order.
        self.assertEqual(len(client.stop_order_calls), 2)

        messages = [call.args[0] for call in notify.call_args_list]
        self.assertTrue(
            any("ist beendet" in m for m in messages),
            f"Verschwundene Order muss gemeldet werden: {messages}",
        )

    def test_dead_stop_order_is_detected_for_all_terminal_states(self):
        for status in ("CANCELED", "EXPIRED", "REJECTED", "EXPIRED_IN_MATCH"):
            with self.subTest(status=status):
                # setUp() laeuft nur einmal pro Testmethode, die
                # Ledger-Datei ueberlebt also die Subtests. Ohne das
                # Zuruecksetzen wuerde open_position() ab der zweiten
                # Runde die Position der ERSTEN zurueckgeben.
                Path(self.state_file).unlink(missing_ok=True)
                strategy, client, order_id = self._open_protected_position()
                client.end_order_without_fill(order_id, status=status)
                client.price = 51_000.0

                with mock.patch("dca_bot.trend_strategy.send_notification"):
                    with self.assertLogs("trend_bot", level="WARNING"):
                        strategy.execute_once()

                open_trade = strategy._ledger.open_position()
                self.assertNotEqual(open_trade["stop_loss_order_id"], order_id)

    def test_dead_stop_order_is_replaced_on_startup_reconciliation(self):
        """
        Derselbe Weg beim Bot-Start: die Order wurde waehrend der
        Downtime storniert.
        """
        strategy, client, order_id = self._open_protected_position()
        client.end_order_without_fill(order_id)

        restarted = TrendFollowingStrategy(self._make_config(True), client)
        restarted._seeded = True

        with mock.patch("dca_bot.trend_strategy.send_notification"):
            with self.assertLogs("trend_bot", level="WARNING"):
                restarted.reconcile_on_startup()

        open_trade = restarted._ledger.open_position()
        self.assertIsNotNone(open_trade["stop_loss_order_id"])
        self.assertNotEqual(open_trade["stop_loss_order_id"], order_id)

    def test_dead_stop_order_does_not_close_the_position(self):
        """
        Abgrenzung zum FILLED-Pfad: storniert heisst NICHT verkauft. Die
        Position bleibt offen und es wird nichts als realisiert verbucht.
        """
        strategy, client, order_id = self._open_protected_position()
        client.end_order_without_fill(order_id)
        client.price = 51_000.0

        with mock.patch("dca_bot.trend_strategy.send_notification"):
            with self.assertLogs("trend_bot", level="WARNING"):
                strategy.execute_once()

        trade = strategy._ledger._read()[0]
        self.assertEqual(trade["status"], "open")
        self.assertIsNone(trade["realized_pnl"])
        self.assertFalse(strategy._stop_loss.is_paused())
        self.assertEqual(client.market_sell_calls, [])

    def test_unreadable_status_leaves_the_order_id_untouched(self):
        """
        Wichtige Gegenprobe: eine GESCHEITERTE Status-Abfrage ist keine
        Aussage ueber die Order. Die Zuordnung darf dabei nicht geloest
        werden - sonst wuerde ein Netzwerkhaenger eine zweite Stop-Order
        ueber dieselbe Menge ausloesen.
        """
        strategy, client, order_id = self._open_protected_position()
        client.orders.pop(order_id)  # get_order_status() liefert None
        client.price = 51_000.0

        strategy.execute_once()

        open_trade = strategy._ledger.open_position()
        self.assertEqual(open_trade["stop_loss_order_id"], order_id)
        self.assertEqual(len(client.stop_order_calls), 1, "Keine zweite Order")

    # -- W8: Teilfuellung --

    def test_partially_filled_stop_order_is_reported_but_not_acted_on(self):
        strategy, client, order_id = self._open_protected_position()
        open_trade = strategy._ledger.open_position()
        client.partially_fill_order(order_id, executed_qty=open_trade["quantity"] / 2)
        client.price = 51_000.0

        with mock.patch("dca_bot.trend_strategy.send_notification") as notify:
            with self.assertLogs("trend_bot", level="WARNING") as captured:
                strategy.execute_once()

        # Nichts angefasst: Order lebt noch und kann vollstaendig fuellen.
        trade = strategy._ledger._read()[0]
        self.assertEqual(trade["status"], "open")
        self.assertEqual(trade["stop_loss_order_id"], order_id)
        self.assertEqual(client.market_sell_calls, [])
        self.assertEqual(len(client.stop_order_calls), 1, "Keine zweite Order")

        self.assertTrue(any("TEILWEISE gefüllt" in line for line in captured.output))
        messages = [call.args[0] for call in notify.call_args_list]
        self.assertTrue(any("teilweise gefüllt" in m for m in messages))

    def test_untouched_open_stop_order_stays_silent(self):
        """
        Der Regelfall (NEW, nichts gefuellt) darf keine Warnung
        erzeugen - sonst waere die W8-Meldung wertlos.
        """
        strategy, client, order_id = self._open_protected_position()
        client.price = 51_000.0

        with mock.patch("dca_bot.trend_strategy.send_notification") as notify:
            strategy.execute_once()

        self.assertEqual(notify.call_args_list, [])
        open_trade = strategy._ledger.open_position()
        self.assertEqual(open_trade["stop_loss_order_id"], order_id)

    # -- Anti-Divergenz --

    def test_fill_check_and_pending_path_share_one_rule(self):
        """
        Der eigentliche Punkt hinter W7/W8: es darf nicht zwei
        Bewertungen desselben Order-Status geben.

        Geprueft wird deshalb nicht nur das Verhalten, sondern die
        Quelle: fuer jeden relevanten Status muss die Einstufung des
        Fill-Checks genau der von order_lifecycle_state() entsprechen -
        derselben Funktion, auf der classify_order_status() (Pending-Pfad)
        aufsetzt.
        """
        cases = {
            "FILLED": ORDER_LIFECYCLE_FILLED,
            "PARTIALLY_FILLED": ORDER_LIFECYCLE_LIVE,
            "NEW": ORDER_LIFECYCLE_LIVE,
            "CANCELED": ORDER_LIFECYCLE_DEAD,
            "EXPIRED": ORDER_LIFECYCLE_DEAD,
            "REJECTED": ORDER_LIFECYCLE_DEAD,
        }

        for status, expected_state in cases.items():
            with self.subTest(status=status):
                executed = "0.0001" if status in ("FILLED", "PARTIALLY_FILLED") else "0"
                order = {"status": status, "executedQty": executed}
                self.assertEqual(order_lifecycle_state(order), expected_state)

                # Die Pending-Seite leitet ihre Antwort aus demselben
                # Zustand ab - fuer eine Stop-Order gilt "lebt noch" dort
                # als bestaetigt, "beendet ohne Wirkung" als wirkungslos.
                expected_pending = {
                    ORDER_LIFECYCLE_FILLED: ORDER_CONFIRMED,
                    ORDER_LIFECYCLE_LIVE: ORDER_CONFIRMED,
                    ORDER_LIFECYCLE_DEAD: ORDER_WITHOUT_EFFECT,
                }[expected_state]
                self.assertEqual(
                    classify_order_status(order, KIND_STOP_LOSS_LIMIT), expected_pending
                )


if __name__ == "__main__":
    unittest.main()

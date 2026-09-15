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

from dca_bot.trend_config import TrendConfig
from dca_bot.trend_strategy import (
    UNCERTAIN_CYCLES_WARNING_THRESHOLD,
    UNPROTECTED_CYCLES_WARNING_THRESHOLD,
    TrendFollowingStrategy,
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

    def _new_order_id(self) -> str:
        self._next_order_id += 1
        return str(self._next_order_id)

    def get_current_price(self, symbol: str) -> float:
        return self.price

    def place_market_buy(self, symbol: str, quote_order_qty: float) -> dict | None:
        self.market_buy_calls.append((symbol, quote_order_qty))
        if not self.trading_enabled:
            return None
        return {
            "executedQty": quote_order_qty / self.price,
            "cummulativeQuoteQty": quote_order_qty,
        }

    def place_market_sell(self, symbol: str, quantity: float) -> dict | None:
        self.market_sell_calls.append((symbol, quantity))
        self.call_log.append("place_market_sell")
        if not self.trading_enabled:
            return None
        if self.force_market_sell_failure:
            return None
        return {"cummulativeQuoteQty": quantity * self.price}

    def place_stop_loss_limit_sell(
        self, symbol: str, quantity: float, stop_price: float, limit_price: float
    ) -> dict | None:
        self.stop_order_calls.append((symbol, quantity, stop_price, limit_price))
        if not self.trading_enabled:
            return None
        if self.force_stop_order_failure:
            return None
        order_id = self._new_order_id()
        order = {
            "orderId": order_id,
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

    def fill_order(self, order_id: str, executed_qty: float, cumulative_quote: float) -> None:
        """Testhilfe: simuliert, dass die Börse die Order gefüllt hat."""
        order = self.orders[order_id]
        order["status"] = "FILLED"
        order["executedQty"] = executed_qty
        order["cummulativeQuoteQty"] = cumulative_quote


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

    def _make_config(self, trading_enabled: bool) -> TrendConfig:
        return TrendConfig(
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

    def _make_strategy(
        self, trading_enabled: bool, price: float
    ) -> tuple[TrendFollowingStrategy, FakeTradingClient]:
        config = self._make_config(trading_enabled)
        client = FakeTradingClient(trading_enabled, price)
        strategy = TrendFollowingStrategy(config, client)
        strategy._seeded = True  # kein echter Netzwerkzugriff für die Historie
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
        self.assertEqual(client.call_log, ["cancel_order", "place_market_sell"])
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


if __name__ == "__main__":
    unittest.main()

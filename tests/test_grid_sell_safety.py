"""
Tests für die Verkaufs-Sicherheit des Grid-Bots (Sicherheitsreview-Punkte
K1 und K4, siehe grid_strategy.py._process_sells).

Zwei getrennte Fehlerbilder, die vor dem Fix beide in derselben
Code-Zeile zusammenfielen, weil place_market_sell() in ZWEI völlig
verschiedenen Fällen None zurückgibt:

- K1: Ein fehlgeschlagener ECHTER Verkauf (API-Fehler) wurde wie ein
  Dry-Run behandelt - der Bot erfand einen Erlös aus quantity*price und
  markierte die Position trotzdem als geschlossen. Die Assets lagen
  danach weiter an der Börse, der Ledger behauptete das Gegenteil.
- K4: Eine im Dry-Run "gekaufte" Position (dry_run=true im Ledger) wäre
  nach einem Umschalten auf GRID_BOT_ENABLE_TRADING=true real verkauft
  worden - Assets, die nie gekauft wurden.

Dateiname bewusst "sell_safety" statt "stop_loss": der Grid-Stop-Loss
ist der Trendbruch-KAUF-Blocker (siehe GridStopLoss in grid_risk.py),
ein völlig anderer Mechanismus als das hier Getestete.

Nutzt einen Fake-TradingClient (kein Netzwerkzugriff, keine
Binance-Zugangsdaten nötig) - grid_strategy.py verwendet den
TradingClient rein über Duck-Typing, ein Fake mit derselben
Schnittstelle reicht deshalb aus. Gleiches Vorgehen wie in
tests/test_trend_stop_loss.py; bewusst ein eigener, kleiner Fake statt
eines Imports von dort, da `tests/` kein Package ist.

Ausführen mit:  python -m unittest tests.test_grid_sell_safety -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dca_bot.grid_config import GridConfig
from dca_bot.grid_risk import GridPosition
from dca_bot.grid_signals import find_triggered_buy_levels
from dca_bot.order_utils import SymbolTradingRules, quantize_quantity
from dca_bot.grid_strategy import GridTradingStrategy


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


class FakeGridClient:
    """
    Verhält sich wie der echte TradingClient (binance_client.py): im
    Dry-Run (trading_enabled=False) gibt place_market_sell() None zurück,
    ohne eine Order zu platzieren. `force_market_sell_failure` simuliert
    zusätzlich den ANDEREN None-Fall - einen echten API-Fehler trotz
    aktiviertem Trading (genau die Zweideutigkeit, um die es in K1 geht).
    """

    def __init__(self, trading_enabled: bool, price: float):
        self.trading_enabled = trading_enabled
        self.price = price
        self.market_sell_calls: list[tuple] = []
        self.market_buy_calls: list[tuple] = []
        self.force_market_sell_failure = False
        # Siehe FakeTradingClient in tests/test_trend_stop_loss.py: Default
        # 0.0 entspricht dem beobachteten Testnet-Verhalten, Tests zur
        # Gebuehrenkorrektur setzen 0.001 (Live-Standardsatz).
        self.commission_rate = 0.0
        self.commission_asset = "BTC"
        # Erlaubt einem Test, die Boerse einen Betrag melden zu lassen,
        # der bewusst NICHT `quantity * price` entspricht - nur so ist
        # unterscheidbar, ob der Produktivcode den gemeldeten Wert
        # uebernimmt oder ihn zufaellig gleich ausrechnet.
        self.quote_qty_override: float | None = None
        # Preis, zu dem die Boerse eine Market-Order tatsaechlich fuellt.
        # None = zum Tickerpreis (`price`). Ein Test, der pruefen will,
        # ob der Produktivcode den echten Fuellpreis oder den vorher
        # abgefragten Ticker ins Ledger schreibt, setzt hier bewusst
        # einen ANDEREN Wert - sonst waeren beide nicht unterscheidbar.
        self.fill_price: float | None = None
        self.force_trading_rules_failure = False
        self.trading_rules_calls = 0
        # Seit dem K2-Fix reicht jede place_*-Methode einen `context` an
        # die Pending-Orders-Ablage durch (siehe binance_client.py) und
        # jede Order-Antwort traegt eine clientOrderId. Der Fake bildet
        # beides nach, damit die Tests denselben Codepfad durchlaufen wie
        # der Live-Betrieb.
        self.order_contexts: list[dict | None] = []
        self._next_client_order_id = 0
        # Konsistenz-Check vor dem Verkauf (W11, siehe balance_guard.py).
        # Default bewusst reichlich: die bestehenden Testfaelle sollen
        # sich nicht darum kuemmern muessen, dass der Bot jetzt auch das
        # Guthaben prueft. Die W11-Tests setzen diese Werte gezielt.
        self.base_balance: tuple[float, float] | None = (1_000.0, 0.0)
        self.open_orders: list[dict] | None = []
        self.balance_calls = 0
        self.open_orders_calls = 0

    def _new_client_order_id(self) -> str:
        self._next_client_order_id += 1
        return f"grid-test-{self._next_client_order_id}"

    def get_current_price(self, symbol: str) -> float:
        return self.price

    def get_asset_balance(self, asset: str) -> tuple[float, float] | None:
        self.balance_calls += 1
        return self.base_balance

    def get_open_orders(self, symbol: str) -> list[dict] | None:
        self.open_orders_calls += 1
        return self.open_orders

    def get_symbol_trading_rules(self, symbol: str):
        self.trading_rules_calls += 1
        if self.force_trading_rules_failure:
            raise RuntimeError("exchangeInfo nicht erreichbar (Testfall)")
        return FAKE_TRADING_RULES

    def place_market_buy(
        self, symbol: str, quote_order_qty: float, context: dict | None = None
    ) -> dict | None:
        self.market_buy_calls.append((symbol, quote_order_qty))
        self.order_contexts.append(context)
        if not self.trading_enabled:
            return None
        fill_price = self.price if self.fill_price is None else self.fill_price
        executed_qty = quote_order_qty / fill_price
        reported_quote_qty = (
            quote_order_qty if self.quote_qty_override is None else self.quote_qty_override
        )
        return {
            "clientOrderId": self._new_client_order_id(),
            "executedQty": executed_qty,
            "cummulativeQuoteQty": reported_quote_qty,
            "fills": [
                {
                    "price": fill_price,
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
        if not self.trading_enabled:
            return None
        if self.force_market_sell_failure:
            return None
        fill_price = self.price if self.fill_price is None else self.fill_price
        gross = quantity * fill_price
        # executedQty gehoert zu jeder echten Market-Order-Antwort - ohne
        # es liesse sich aus der Antwort kein Fuellpreis ableiten.
        return {
            "clientOrderId": self._new_client_order_id(),
            "executedQty": quantity,
            "cummulativeQuoteQty": gross,
            "fills": [
                {
                    "price": fill_price,
                    "qty": quantity,
                    "commission": gross * self.commission_rate,
                    "commissionAsset": "USDT",
                }
            ],
        }


class GridStrategyTestBase(unittest.TestCase):
    """
    Gemeinsame Testumgebung (temporaere Ledger-/State-Dateien, Config- und
    Strategie-Fabrik) fuer die Grid-Testfaelle. Enthaelt bewusst KEINE
    eigenen Testmethoden: erbte eine Testklasse direkt von einer anderen,
    wuerden deren Tests in beiden Klassen erneut ausgefuehrt.
    """

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmpdir.name)
        self.state_file = str(tmp_path / "grid_positions.json")
        self.stop_loss_state_file = str(tmp_path / "grid_stop_loss_paused.json")
        self.kill_switch_file = str(tmp_path / "STOP_GRID_TEST_UNUSED")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_config(self, trading_enabled: bool) -> GridConfig:
        return GridConfig(
            api_key="test",
            api_secret="test",
            symbol="BTCUSDT",
            lower_limit=70_000.0,
            upper_limit=90_000.0,
            grid_spacing_pct=1.5,
            amount_per_level=15.0,
            trading_enabled=trading_enabled,
            kill_switch_file=self.kill_switch_file,
            state_file=self.state_file,
            stop_loss_state_file=self.stop_loss_state_file,
        )

    def _make_strategy(
        self, trading_enabled: bool, price: float
    ) -> tuple[GridTradingStrategy, FakeGridClient]:
        config = self._make_config(trading_enabled)
        client = FakeGridClient(trading_enabled, price)
        return GridTradingStrategy(config, client), client

    def _add_open_position(
        self, strategy: GridTradingStrategy, dry_run: bool, target_sell_price: float = 78_000.0
    ) -> dict:
        """Legt eine offene Position direkt im Ledger an (unabhängig vom Kaufpfad)."""
        position = GridPosition.new(
            level_index=3,
            buy_price=77_000.0,
            target_sell_price=target_sell_price,
            quantity=0.0002,
            quote_spent=15.0,
            dry_run=dry_run,
        )
        strategy._ledger.record_buy(position)
        return strategy._ledger.open_positions()[0]


class GridSellSafetyTestCase(GridStrategyTestBase):
    """Verkaufs-Sicherheit: K1 und K4 (siehe Modul-Docstring)."""

    # -- K4: Dry-Run-Position wird NIE real verkauft --

    def test_dry_run_position_is_never_really_sold_when_trading_enabled(self):
        """
        Kern von K4: Position wurde im Dry-Run eröffnet, danach wurde
        GRID_BOT_ENABLE_TRADING auf true gestellt. Der Verkauf muss
        simuliert bleiben - place_market_sell() darf GAR NICHT aufgerufen
        werden, da es nur config.trading_enabled prüft und deshalb eine
        echte Order für nie gekaufte Assets platzieren würde.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        self._add_open_position(strategy, dry_run=True)

        with self.assertLogs("grid_bot", level="INFO") as captured:
            strategy._process_sells(79_000.0)

        self.assertEqual(client.market_sell_calls, [], "Keine echte Verkaufsorder erlaubt")

        marker_lines = [line for line in captured.output if "[DRY-RUN-POSITION]" in line]
        self.assertEqual(len(marker_lines), 1)
        self.assertIn("Verkauf bleibt simuliert", marker_lines[0])

        # Die Position wird trotzdem regulär (simuliert) geschlossen -
        # das ist korrektes Verhalten, nur eben ohne echte Order.
        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertIsNotNone(closed["realized_pnl"])
        self.assertEqual(strategy._ledger.open_positions(), [])

    # -- Spiegelbild zu K4: echte Position wird bei deaktiviertem Trading
    #    weder verkauft noch simuliert geschlossen --
    #
    # Bis zum 25.09.2026 stand hier ein Test, der genau das Gegenteil
    # festschrieb: echte Position + Dry-Run -> Position "closed", mit der
    # Begruendung "unkritisch, da keine Order platziert wird". Fuer die
    # Boerse stimmte das, fuers Ledger nicht: es behauptete einen Verkauf,
    # waehrend das BTC weiter an der Boerse lag (Schadensbild wie K1).

    def test_real_position_stays_open_when_trading_disabled(self):
        strategy, client = self._make_strategy(trading_enabled=False, price=79_000.0)
        record = self._add_open_position(strategy, dry_run=False)

        with mock.patch("dca_bot.grid_strategy.send_notification") as mock_notify:
            with self.assertLogs("grid_bot", level="INFO") as captured:
                strategy._process_sells(79_000.0)

        self.assertEqual(client.market_sell_calls, [], "Kein (simulierter) Verkaufsaufruf")
        still_open = strategy._ledger.open_positions()
        self.assertEqual(len(still_open), 1, "Position muss OFFEN bleiben")
        self.assertEqual(still_open[0]["id"], record["id"])
        # Kein erfundener Erlös, kein Verkaufspreis, kein Zeitpunkt.
        self.assertIsNone(still_open[0]["realized_pnl"])
        self.assertIsNone(still_open[0]["sell_price"])
        self.assertIsNone(still_open[0]["sold_at"])

        warnings = [line for line in captured.output if "[GRID-VERKAUF-GESPERRT]" in line]
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].startswith("WARNING"))

        mock_notify.assert_called_once()
        (text,), _ = mock_notify.call_args
        self.assertIn("[GRID-VERKAUF-GESPERRT]", text)
        self.assertIn("GRID_BOT_ENABLE_TRADING=true", text)

    def test_blocked_real_position_keeps_its_level_occupied(self):
        """
        Die eigentliche Folge des alten Verhaltens: die Stufe galt nach dem
        simulierten Schliessen als frei und wurde beim naechsten
        Durchqueren ein zweites Mal gekauft. Jetzt bleibt sie belegt.
        """
        strategy, client = self._make_strategy(trading_enabled=False, price=79_000.0)
        record = self._add_open_position(strategy, dry_run=False)

        with mock.patch("dca_bot.grid_strategy.send_notification"):
            strategy._process_sells(79_000.0)

            # Kurs faellt von oberhalb durch genau diese Stufe.
            level_price = strategy._levels[record["level_index"]]
            strategy._last_seen_price = level_price * 1.0001
            # Praemisse: ohne die offene Position wuerde genau diese Stufe
            # gekauft - sonst waere "kein Kauf" auch ohne Belegung wahr.
            self.assertEqual(
                find_triggered_buy_levels(
                    strategy._levels, strategy._last_seen_price, level_price, set()
                ),
                [record["level_index"]],
            )
            strategy._process_buys(level_price)

        self.assertEqual(client.market_buy_calls, [], "Stufe ist belegt - kein zweiter Kauf")
        self.assertEqual(len(strategy._ledger.open_positions()), 1)

    def test_blocked_real_position_is_logged_every_cycle_but_notified_once(self):
        strategy, client = self._make_strategy(trading_enabled=False, price=79_000.0)
        self._add_open_position(strategy, dry_run=False)

        with mock.patch("dca_bot.grid_strategy.send_notification") as mock_notify:
            with self.assertLogs("grid_bot", level="INFO") as captured:
                strategy._process_sells(79_000.0)
                strategy._process_sells(79_000.0)
                strategy._process_sells(79_000.0)

        self.assertEqual(
            len([line for line in captured.output if "[GRID-VERKAUF-GESPERRT]" in line]),
            3,
            "Jeder Zyklus wird geloggt",
        )
        self.assertEqual(mock_notify.call_count, 1, "Telegram nur einmal pro Prozesslauf")
        self.assertEqual(len(strategy._ledger.open_positions()), 1)

    def test_same_real_position_is_sold_once_trading_is_enabled(self):
        """
        Gegenprobe: dasselbe Ledger, derselbe Kurs, nur Trading an - dann
        wird regulaer verkauft. Belegt, dass es die neue Sperre ist, die
        oben den Verkauf verhindert, und nicht etwa ein verfehltes Ziel.
        """
        strategy, client = self._make_strategy(trading_enabled=False, price=79_000.0)
        self._add_open_position(strategy, dry_run=False)
        with mock.patch("dca_bot.grid_strategy.send_notification"):
            strategy._process_sells(79_000.0)
        self.assertEqual(len(strategy._ledger.open_positions()), 1, "Vorbedingung: gesperrt")

        live_client = FakeGridClient(trading_enabled=True, price=79_000.0)
        live_strategy = GridTradingStrategy(self._make_config(True), live_client)
        with mock.patch("dca_bot.grid_strategy.send_notification"):
            live_strategy._process_sells(79_000.0)

        self.assertEqual(len(live_client.market_sell_calls), 1)
        self.assertEqual(live_strategy._ledger.open_positions(), [])

    def test_dry_run_position_is_still_simulated_when_trading_disabled(self):
        """
        Abgrenzung: Die Sperre gilt nur fuer ECHTE Positionen. Eine
        Dry-Run-Position im Dry-Run-Modus wird weiterhin simuliert
        geschlossen - das ist der normale Paper-Trade-Betrieb.
        """
        strategy, client = self._make_strategy(trading_enabled=False, price=79_000.0)
        self._add_open_position(strategy, dry_run=True)

        with mock.patch("dca_bot.grid_strategy.send_notification"):
            strategy._process_sells(79_000.0)

        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertIsNotNone(closed["realized_pnl"])

    # -- K1: fehlgeschlagener echter Verkauf schließt die Position NICHT --

    def test_failed_real_sell_keeps_position_open(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        record = self._add_open_position(strategy, dry_run=False)
        client.force_market_sell_failure = True

        with mock.patch("dca_bot.grid_strategy.send_notification") as mock_notify:
            with self.assertLogs("grid_bot", level="INFO") as captured:
                strategy._process_sells(79_000.0)

        self.assertEqual(len(client.market_sell_calls), 1, "Der Verkauf wurde versucht")

        still_open = strategy._ledger.open_positions()
        self.assertEqual(len(still_open), 1, "Position muss OFFEN bleiben")
        self.assertEqual(still_open[0]["id"], record["id"])
        # Kein erfundener Erlös, kein Verkaufszeitpunkt.
        self.assertIsNone(still_open[0]["realized_pnl"])
        self.assertIsNone(still_open[0]["sell_price"])
        self.assertIsNone(still_open[0]["sold_at"])

        warnings = [line for line in captured.output if "[GRID-VERKAUF-FEHLGESCHLAGEN]" in line]
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].startswith("WARNING"))

        mock_notify.assert_called_once()
        (text,), _ = mock_notify.call_args
        self.assertIn("[GRID-VERKAUF-FEHLGESCHLAGEN]", text)

    def test_failed_real_sell_is_retried_next_cycle_without_notification_spam(self):
        """
        Die Position bleibt offen und ihr Sell-Target weiterhin erreicht,
        der nächste Zyklus versucht den Verkauf also automatisch erneut.
        Telegram darf dabei nur EINMAL pro Prozesslauf melden (sonst im
        5-Minuten-Takt), ins Log geht jeder Fehlschlag.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        self._add_open_position(strategy, dry_run=False)
        client.force_market_sell_failure = True

        with mock.patch("dca_bot.grid_strategy.send_notification") as mock_notify:
            with self.assertLogs("grid_bot", level="INFO") as captured:
                strategy._process_sells(79_000.0)
                strategy._process_sells(79_000.0)
                strategy._process_sells(79_000.0)

        self.assertEqual(len(client.market_sell_calls), 3, "Jeder Zyklus versucht es erneut")
        self.assertEqual(
            len([line for line in captured.output if "[GRID-VERKAUF-FEHLGESCHLAGEN]" in line]),
            3,
            "Jeder Fehlschlag wird geloggt",
        )
        self.assertEqual(mock_notify.call_count, 1, "Telegram nur einmal pro Prozesslauf")

        # Klappt der Verkauf später doch, wird regulär geschlossen.
        client.force_market_sell_failure = False
        strategy._process_sells(79_000.0)
        self.assertEqual(strategy._ledger.open_positions(), [])

    # -- Regression: erfolgreicher echter Verkauf funktioniert unverändert --

    def test_successful_real_sell_closes_position_with_real_proceeds(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        self._add_open_position(strategy, dry_run=False)

        with mock.patch("dca_bot.grid_strategy.send_notification") as mock_notify:
            strategy._process_sells(79_000.0)

        self.assertEqual(len(client.market_sell_calls), 1)
        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["sell_price"], 79_000.0)
        # proceeds stammen aus cummulativeQuoteQty der echten Order.
        self.assertAlmostEqual(closed["realized_pnl"], 0.0002 * 79_000.0 - 15.0, places=6)

        (text,), _ = mock_notify.call_args
        self.assertIn("[GRID-VERKAUF]", text)
        self.assertNotIn("DRY-RUN", text)

    def test_position_below_target_is_not_touched(self):
        """Regression: ohne erreichtes Sell-Target passiert weiterhin nichts."""
        strategy, client = self._make_strategy(trading_enabled=True, price=77_500.0)
        self._add_open_position(strategy, dry_run=False, target_sell_price=78_000.0)

        strategy._process_sells(77_500.0)

        self.assertEqual(client.market_sell_calls, [])
        self.assertEqual(len(strategy._ledger.open_positions()), 1)

    # -- Ledger-Eintrag ohne dry_run-Feld: nicht raten, nicht verkaufen --

    def test_missing_dry_run_field_blocks_any_sell_attempt(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        record = self._add_open_position(strategy, dry_run=False)

        # Feld nachträglich entfernen (nur so herstellbar - GridPosition
        # schreibt es immer).
        records = json.loads(Path(self.state_file).read_text(encoding="utf-8"))
        del records[0]["dry_run"]
        Path(self.state_file).write_text(json.dumps(records), encoding="utf-8")

        with self.assertLogs("grid_bot", level="INFO") as captured:
            strategy._process_sells(79_000.0)

        self.assertEqual(client.market_sell_calls, [], "Kein Verkaufsversuch bei unklarem Modus")
        still_open = strategy._ledger.open_positions()
        self.assertEqual(len(still_open), 1)
        self.assertEqual(still_open[0]["id"], record["id"])
        self.assertTrue(
            any("[GRID-POSITION-UNKLAR]" in line for line in captured.output),
            "Der unklare Zustand muss sichtbar geloggt werden",
        )


class GridTradingRulesTestCase(GridStrategyTestBase):
    """
    Tests für die Anbindung an die echten Handelsregeln und die
    Gebührenkorrektur beim Grid-Bot (Sicherheitsreview-Punkt K3, siehe
    order_utils.py).

    Teilt sich die Testumgebung (GridStrategyTestBase) mit den
    Verkaufs-Sicherheitstests oben. Anders als beim Trend-Bot gibt es hier
    keine Stop-Order, der Schaden zeigt sich also direkt beim Verkauf:
    eine um die Kaufgebühr zu hohe Menge lässt jeden Verkaufsversuch der
    Position scheitern.
    """

    def _buy_one_level(self, strategy, client, level_index: int = 3) -> tuple[dict, float]:
        """
        Löst über die Crossing-Erkennung genau EINEN echten Kauf aus.

        Der Preis wird bewusst aus dem Grid selbst abgeleitet statt frei
        gewählt: bei 1,5% Stufenabstand durchquert schon ein 5%-Rückgang
        mehrere Stufen auf einmal. `last_seen_price` liegt nur knapp über
        der Zielstufe, also innerhalb desselben Intervalls - damit
        triggert exakt diese eine Stufe.
        """
        level_price = strategy._levels[level_index]
        client.price = level_price
        strategy._last_seen_price = level_price * 1.0001
        strategy._process_buys(level_price)

        open_positions = strategy._ledger.open_positions()
        self.assertEqual(len(open_positions), 1, "Genau eine Position erwartet")
        return open_positions[0], level_price

    def test_buy_with_btc_commission_reduces_stored_quantity(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=77_000.0)
        client.commission_rate = 0.001
        client.commission_asset = "BTC"

        position, level_price = self._buy_one_level(strategy, client)

        gross_quantity = 15.0 / level_price
        self.assertLess(position["quantity"], gross_quantity)
        self.assertAlmostEqual(position["quantity"], gross_quantity * 0.999, delta=1e-5)

    def test_buy_with_bnb_commission_leaves_quantity_unchanged(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=77_000.0)
        client.commission_rate = 0.001
        client.commission_asset = "BNB"

        position, level_price = self._buy_one_level(strategy, client)

        expected = quantize_quantity(15.0 / level_price, FAKE_TRADING_RULES.step_size)
        self.assertAlmostEqual(position["quantity"], expected, places=10)

    def test_stored_quantity_is_a_valid_step_multiple(self):
        """Eine nicht durch stepSize teilbare Menge würde die Börse ablehnen."""
        strategy, client = self._make_strategy(trading_enabled=True, price=77_123.45)
        client.commission_rate = 0.001

        # Grid-Stufen sind geometrisch berechnet, also krumme Werte - eine
        # daraus abgeleitete Menge ist garantiert kein glattes Vielfaches.
        position, _ = self._buy_one_level(strategy, client, level_index=5)

        steps = position["quantity"] / FAKE_TRADING_RULES.step_size
        self.assertAlmostEqual(steps, round(steps), places=6)

    def test_sell_proceeds_are_net_of_quote_commission(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        client.commission_rate = 0.001
        self._add_open_position(strategy, dry_run=False)

        strategy._process_sells(79_000.0)

        closed = strategy._ledger._read()[0]
        gross = 0.0002 * 79_000.0
        expected_pnl = gross * (1 - 0.001) - 15.0
        self.assertAlmostEqual(closed["realized_pnl"], expected_pnl, places=8)

    def test_trading_rules_failure_blocks_buy_without_order(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=77_000.0)
        client.force_trading_rules_failure = True
        strategy._last_seen_price = 77_000.0 * 1.05

        with self.assertRaises(RuntimeError):
            strategy._process_buys(77_000.0)

        self.assertEqual(client.market_buy_calls, [], "Keine Order ohne gültige Regeln")
        self.assertEqual(strategy._ledger.open_positions(), [], "Kein halber Ledger-Eintrag")

    def test_trading_rules_failure_blocks_sell_without_order(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        self._add_open_position(strategy, dry_run=False)
        client.force_trading_rules_failure = True

        with self.assertRaises(RuntimeError):
            strategy._process_sells(79_000.0)

        self.assertEqual(client.market_sell_calls, [], "Keine Order ohne gültige Regeln")
        still_open = strategy._ledger.open_positions()
        self.assertEqual(len(still_open), 1, "Position bleibt unverändert offen")
        self.assertIsNone(still_open[0]["realized_pnl"])

    # -- Dry-Run: quote_spent muss der quantisierten Menge folgen --
    #
    # Gefunden am 22.09.2026 beim Auswerten der VPS-Live-Daten: die Menge
    # wurde seit dem K3-Fix quantisiert, der Betrag aber weiterhin als
    # konfigurierter Rohbetrag gebucht. Die weggerundete Teilmenge wurde
    # nie gekauft - sie stand trotzdem in der Kostenbasis.

    def test_dry_run_quote_spent_matches_quantized_quantity(self):
        """
        Der gebuchte Betrag ist der Wert der Menge, die die Position
        tatsaechlich haelt - nicht der konfigurierte Wunschbetrag.
        """
        strategy, client = self._make_strategy(trading_enabled=False, price=77_000.0)

        position, level_price = self._buy_one_level(strategy, client)

        self.assertTrue(position["dry_run"])
        self.assertAlmostEqual(
            position["quote_spent"], position["quantity"] * level_price, places=10
        )
        # Gegenprobe: Ohne sie waere dieser Test auch an einer Preislage
        # gruen, an der die Quantisierung gar nichts abschneidet - und
        # genau dort liegt der Fehler nicht. Bei stepSize 1e-5 und einem
        # 15-USDT-Auftrag ist eine Mengenstufe rund 0,80 USDT.
        self.assertLess(
            position["quote_spent"],
            15.0,
            "Quantisierung greift an dieser Preislage nicht - Test ohne Aussage",
        )

    def test_dry_run_round_trip_is_profitable_when_price_rises(self):
        """
        Das reproduzierte Live-Symptom: Kauf auf einer Stufe, Verkauf auf
        der naechsthoeheren - der Kurs ist gestiegen, die realisierte PnL
        muss positiv sein.

        Vor dem Fix war sie negativ, weil der Erloes der quantisierten
        Menge folgte (`quantity * price`), die Kostenbasis aber dem vollen
        konfigurierten Betrag. Die Differenz (~5 % des Auftrags) ist
        groesser als der Grid-Stufenabstand von 1,5 % und kippt damit das
        Vorzeichen.
        """
        strategy, client = self._make_strategy(trading_enabled=False, price=77_000.0)

        position, buy_price = self._buy_one_level(strategy, client, level_index=3)
        sell_price = position["target_sell_price"]
        self.assertGreater(sell_price, buy_price, "Testaufbau: Kurs muss steigen")

        client.price = sell_price
        strategy._process_sells(sell_price)

        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertGreater(
            closed["realized_pnl"],
            0.0,
            "Gestiegener Kurs muss eine positive realisierte PnL ergeben",
        )
        # Fuer eine simulierte Position gilt exakt quantity * (Verkauf -
        # Kauf): beide Seiten rechnen mit derselben Menge. Genau diese
        # Invariante war verletzt.
        self.assertAlmostEqual(
            closed["realized_pnl"],
            position["quantity"] * (sell_price - buy_price),
            places=10,
        )

    def test_real_buy_keeps_exchange_reported_quote_spent(self):
        """
        Regression fuer echte Orders: dort bleibt `cummulativeQuoteQty`
        die Quelle der Wahrheit und wird NICHT lokal nachgerechnet.

        Der gemeldete Betrag weicht hier bewusst von `quantity * price`
        ab - sonst waere nicht unterscheidbar, ob der Code den Wert der
        Boerse uebernimmt oder ihn zufaellig gleich ausrechnet.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=77_000.0)
        client.quote_qty_override = 14.97

        position, level_price = self._buy_one_level(strategy, client)

        self.assertFalse(position["dry_run"])
        self.assertAlmostEqual(position["quote_spent"], 14.97, places=10)
        self.assertNotAlmostEqual(
            position["quote_spent"],
            position["quantity"] * level_price,
            places=4,
            msg="Testaufbau: gemeldeter Betrag muss abweichen, sonst prueft der Test nichts",
        )

    # -- Preise im Ledger: tatsaechlicher Fuellpreis statt Ticker --
    #
    # Code-Ueberpruefung vom 25.09.2026, Prioritaet 4: buy_price/sell_price
    # echter Orders waren der VOR der Order abgefragte Tickerpreis. Die
    # PnL war nicht betroffen (sie rechnet mit quantity/quote_spent), die
    # angezeigten Preise in Dashboard und Steuer-Export aber schon. Der
    # Reconciliation-Pfad nahm schon immer den Fuellpreis. Der Fake fuellt
    # in diesen Tests bewusst zu einem ANDEREN Preis als dem Ticker - sonst
    # waere nicht unterscheidbar, welcher der beiden im Ledger landet.

    def test_real_buy_records_the_fill_price_not_the_ticker(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=77_000.0)
        level_price = strategy._levels[3]
        client.fill_price = level_price * 1.0015  # Slippage beim Kauf

        with mock.patch("dca_bot.grid_strategy.send_notification") as mock_notify:
            position, ticker_price = self._buy_one_level(strategy, client, level_index=3)

        self.assertNotAlmostEqual(
            client.fill_price, ticker_price, places=2,
            msg="Testaufbau: Fill und Ticker muessen sich unterscheiden",
        )
        self.assertAlmostEqual(position["buy_price"], client.fill_price, places=6)
        # Das Verkaufsziel haengt an der Grid-Stufe, nicht am Fill.
        self.assertAlmostEqual(position["target_sell_price"], strategy._levels[4], places=6)
        (text,), _ = mock_notify.call_args
        self.assertIn(f"@ {client.fill_price:.2f}", text)

    def test_real_sell_records_the_fill_price_not_the_ticker(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        self._add_open_position(strategy, dry_run=False)
        client.fill_price = 78_950.0  # Slippage beim Verkauf

        with mock.patch("dca_bot.grid_strategy.send_notification") as mock_notify:
            strategy._process_sells(79_000.0)

        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertAlmostEqual(closed["sell_price"], 78_950.0, places=6)
        # Die PnL folgt wie bisher dem gemeldeten Erloes - und der passt
        # jetzt auch zum gespeicherten Verkaufspreis.
        self.assertAlmostEqual(closed["realized_pnl"], 0.0002 * 78_950.0 - 15.0, places=8)
        (text,), _ = mock_notify.call_args
        self.assertIn("@ 78950.00 verkauft", text)

    def test_dry_run_keeps_the_observed_price(self):
        """
        Abgrenzung: Im Dry-Run gibt es keine Order-Antwort, der beobachtete
        Preis IST der simulierte Fill. Ein gesetzter Fuellpreis am Fake
        darf dort nichts aendern.
        """
        strategy, client = self._make_strategy(trading_enabled=False, price=77_000.0)
        client.fill_price = 12_345.0

        position, ticker_price = self._buy_one_level(strategy, client, level_index=3)
        self.assertEqual(position["buy_price"], ticker_price)

        sell_price = position["target_sell_price"]
        strategy._process_sells(sell_price)
        self.assertEqual(strategy._ledger._read()[0]["sell_price"], sell_price)

    def test_no_rules_lookup_when_nothing_to_sell(self):
        """
        Kein Verkaufsziel erreicht = kein Grund, die Regeln überhaupt zu
        holen. Sonst würde ein exchangeInfo-Ausfall den Zyklus abbrechen,
        obwohl gar nichts zu tun war.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=77_500.0)
        self._add_open_position(strategy, dry_run=False, target_sell_price=78_000.0)
        client.force_trading_rules_failure = True

        strategy._process_sells(77_500.0)  # darf NICHT werfen

        self.assertEqual(client.market_sell_calls, [])


if __name__ == "__main__":
    unittest.main()

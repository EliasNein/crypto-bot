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
        self.force_trading_rules_failure = False
        self.trading_rules_calls = 0

    def get_current_price(self, symbol: str) -> float:
        return self.price

    def get_symbol_trading_rules(self, symbol: str):
        self.trading_rules_calls += 1
        if self.force_trading_rules_failure:
            raise RuntimeError("exchangeInfo nicht erreichbar (Testfall)")
        return FAKE_TRADING_RULES

    def place_market_buy(self, symbol: str, quote_order_qty: float) -> dict | None:
        self.market_buy_calls.append((symbol, quote_order_qty))
        if not self.trading_enabled:
            return None
        executed_qty = quote_order_qty / self.price
        return {
            "executedQty": executed_qty,
            "cummulativeQuoteQty": quote_order_qty,
            "fills": [
                {
                    "price": self.price,
                    "qty": executed_qty,
                    "commission": executed_qty * self.commission_rate,
                    "commissionAsset": self.commission_asset,
                }
            ],
        }

    def place_market_sell(self, symbol: str, quantity: float) -> dict | None:
        self.market_sell_calls.append((symbol, quantity))
        if not self.trading_enabled:
            return None
        if self.force_market_sell_failure:
            return None
        gross = quantity * self.price
        return {
            "cummulativeQuoteQty": gross,
            "fills": [
                {
                    "price": self.price,
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

    def test_real_position_is_simulated_when_bot_runs_in_dry_run(self):
        """
        Umgekehrter Fall aus der Vorgabe: echte Position, aber der Bot
        läuft gerade im Dry-Run (z.B. Config zurückgestellt). Bleibt wie
        bisher simuliert - unkritisch, da keine Order platziert wird.
        """
        strategy, client = self._make_strategy(trading_enabled=False, price=79_000.0)
        self._add_open_position(strategy, dry_run=False)

        strategy._process_sells(79_000.0)

        # place_market_sell wird aufgerufen, gibt im Dry-Run-Modus aber
        # None zurück und loggt nur - exakt wie beim echten Client.
        self.assertEqual(len(client.market_sell_calls), 1)
        closed = strategy._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")

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

"""
Tests für die Gebührenkorrektur im DCA-Bot (Sicherheitsreview-Punkt K3).

Der DCA-Bot verkauft nie - die gespeicherte Menge ist hier trotzdem
sicherheitsrelevant: `PortfolioStopLoss` bewertet die Position mit
`quantity * current_price` (siehe risk.py). Eine um die Handelsgebühr zu
hohe Menge überschätzt den Portfoliowert und lässt den Stop-Loss dadurch
SPÄTER auslösen als konfiguriert.

Fake-Client wie in den anderen Testdateien (kein Netzwerk, keine
Zugangsdaten) - der TradingClient wird auch hier nur über Duck-Typing
verwendet.

Ausführen mit:  python -m unittest tests.test_dca_fee_adjustment -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dca_bot.config import Config
from dca_bot.order_utils import SymbolTradingRules
from dca_bot.strategy import DCAStrategy

FAKE_TRADING_RULES = SymbolTradingRules(
    symbol="BTCUSDT",
    tick_size=0.01,
    step_size=0.00001,
    min_notional=5.0,
    base_asset="BTC",
    quote_asset="USDT",
    quote_precision=8,
)


class FakeDCAClient:
    def __init__(self, trading_enabled: bool, price: float):
        self.trading_enabled = trading_enabled
        self.price = price
        self.commission_rate = 0.0
        self.commission_asset = "BTC"
        self.force_trading_rules_failure = False
        self.market_buy_calls: list[tuple] = []
        # Siehe FakeTradingClient in tests/test_trend_stop_loss.py: seit
        # dem K2-Fix reicht jede place_*-Methode einen `context` durch
        # und jede Order-Antwort traegt eine clientOrderId.
        self.order_contexts: list[dict | None] = []
        self._next_client_order_id = 0

    def get_current_price(self, symbol: str) -> float:
        return self.price

    def get_symbol_trading_rules(self, symbol: str):
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
        self._next_client_order_id += 1
        executed_qty = quote_order_qty / self.price
        return {
            "clientOrderId": f"dca-test-{self._next_client_order_id}",
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


class DCAFeeAdjustmentTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmpdir.name)
        self.state_file = str(tmp_path / "trade_ledger.json")
        self.stop_loss_state_file = str(tmp_path / "stop_loss_paused.json")
        self.kill_switch_file = str(tmp_path / "STOP_TEST_UNUSED")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_strategy(self, trading_enabled: bool, price: float):
        config = Config(
            api_key="test",
            api_secret="test",
            symbol="BTCUSDT",
            quote_amount=15.0,
            trading_enabled=trading_enabled,
            kill_switch_file=self.kill_switch_file,
            state_file=self.state_file,
            stop_loss_state_file=self.stop_loss_state_file,
        )
        client = FakeDCAClient(trading_enabled, price)
        return DCAStrategy(config, client), client

    def test_btc_commission_reduces_stored_quantity(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        client.commission_rate = 0.001
        client.commission_asset = "BTC"

        with mock.patch("dca_bot.strategy.send_notification"):
            strategy.execute_once()

        record = strategy._ledger._read()[0]
        gross = 15.0 / 50_000.0
        self.assertLess(record["quantity"], gross)
        self.assertAlmostEqual(record["quantity"], 0.00029, places=10)
        # Der gezahlte Betrag bleibt unveraendert - die Gebuehr wurde in
        # BTC abgezogen, nicht in USDT.
        self.assertAlmostEqual(record["quote_spent"], 15.0, places=8)

    def test_bnb_commission_leaves_quantity_unchanged(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        client.commission_rate = 0.001
        client.commission_asset = "BNB"

        with mock.patch("dca_bot.strategy.send_notification"):
            strategy.execute_once()

        self.assertAlmostEqual(strategy._ledger._read()[0]["quantity"], 0.0003, places=10)

    def test_stored_quantity_is_a_valid_step_multiple(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=51_234.56)
        client.commission_rate = 0.001

        with mock.patch("dca_bot.strategy.send_notification"):
            strategy.execute_once()

        quantity = strategy._ledger._read()[0]["quantity"]
        steps = quantity / FAKE_TRADING_RULES.step_size
        self.assertAlmostEqual(steps, round(steps), places=6)

    def test_trading_rules_failure_blocks_buy_without_ledger_entry(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        client.force_trading_rules_failure = True

        with mock.patch("dca_bot.strategy.send_notification"):
            with self.assertRaises(RuntimeError):
                strategy.execute_once()

        self.assertEqual(client.market_buy_calls, [], "Keine Order ohne gültige Regeln")
        self.assertEqual(strategy._ledger._read(), [], "Kein halber Ledger-Eintrag")

    def test_dry_run_quantity_is_quantized(self):
        strategy, client = self._make_strategy(trading_enabled=False, price=51_234.56)
        client.commission_rate = 0.001  # darf im Dry-Run keine Wirkung haben

        with mock.patch("dca_bot.strategy.send_notification"):
            strategy.execute_once()

        record = strategy._ledger._read()[0]
        self.assertTrue(record["dry_run"])
        steps = record["quantity"] / FAKE_TRADING_RULES.step_size
        self.assertAlmostEqual(steps, round(steps), places=6)
        self.assertLessEqual(record["quantity"], 15.0 / 51_234.56)


if __name__ == "__main__":
    unittest.main()

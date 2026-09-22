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
from datetime import datetime
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
        # Erlaubt einem Test, die Boerse einen Betrag melden zu lassen,
        # der bewusst NICHT `quantity * price` entspricht - nur so ist
        # unterscheidbar, ob der Produktivcode den gemeldeten Wert
        # uebernimmt oder ihn zufaellig gleich ausrechnet.
        self.quote_qty_override: float | None = None
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
        reported_quote_qty = (
            quote_order_qty if self.quote_qty_override is None else self.quote_qty_override
        )
        return {
            "clientOrderId": f"dca-test-{self._next_client_order_id}",
            "executedQty": executed_qty,
            "cummulativeQuoteQty": reported_quote_qty,
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

    # -- Dry-Run: quote_spent muss der quantisierten Menge folgen --
    #
    # Gefunden am 22.09.2026 an den VPS-Live-Daten des Grid-Bots; derselbe
    # Fehler stand seit dem K3-Fix in allen drei Strategien. Beim DCA-Bot
    # gibt es keine realisierte PnL (er verkauft nie) und der
    # Portfolio-Stop-Loss sieht Dry-Run-Kaeufe gar nicht - der falsche
    # Betrag landete hier stattdessen im Tageslimit.

    def test_dry_run_quote_spent_matches_quantized_quantity(self):
        strategy, client = self._make_strategy(trading_enabled=False, price=51_234.56)

        with mock.patch("dca_bot.strategy.send_notification"):
            strategy.execute_once()

        record = strategy._ledger._read()[0]
        self.assertTrue(record["dry_run"])
        self.assertAlmostEqual(
            record["quote_spent"], record["quantity"] * 51_234.56, places=10
        )
        # Gegenprobe: ohne sie waere der Test auch an einer Preislage
        # gruen, an der die Quantisierung nichts abschneidet.
        self.assertLess(
            record["quote_spent"],
            15.0,
            "Quantisierung greift an dieser Preislage nicht - Test ohne Aussage",
        )

    def test_dry_run_daily_spend_counts_the_corrected_amount(self):
        """
        Die Verdrahtung, nicht nur die Rechnung: `day_summary()` summiert
        ueber ALLE Kaeufe inklusive der simulierten (anders als
        `position()`, das Dry-Run-Kaeufe fuer den Portfolio-Stop-Loss
        herausfiltert). Der Betrag, der gegen das Tageslimit zaehlt, muss
        deshalb derselbe korrigierte sein - sonst bucht der Bot gegen
        seine Notbremse etwas, das er nie ausgegeben hat.
        """
        strategy, client = self._make_strategy(trading_enabled=False, price=51_234.56)

        with mock.patch("dca_bot.strategy.send_notification"):
            strategy.execute_once()

        record = strategy._ledger._read()[0]
        day = datetime.fromisoformat(record["timestamp"]).date()
        spent = strategy._ledger.spent_on_day("BTCUSDT", day)
        self.assertAlmostEqual(spent, record["quote_spent"], places=10)
        self.assertLess(spent, 15.0)

    def test_real_buy_keeps_exchange_reported_quote_spent(self):
        """
        Regression fuer echte Orders: dort bleibt `cummulativeQuoteQty`
        die Quelle der Wahrheit und wird NICHT lokal nachgerechnet.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        client.quote_qty_override = 14.97

        with mock.patch("dca_bot.strategy.send_notification"):
            strategy.execute_once()

        record = strategy._ledger._read()[0]
        self.assertFalse(record["dry_run"])
        self.assertAlmostEqual(record["quote_spent"], 14.97, places=10)
        self.assertNotAlmostEqual(
            record["quote_spent"],
            record["quantity"] * 50_000.0,
            places=4,
            msg="Testaufbau: gemeldeter Betrag muss abweichen, sonst prueft der Test nichts",
        )


if __name__ == "__main__":
    unittest.main()

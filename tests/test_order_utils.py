"""
Tests für die Order-Hilfslogik (dca_bot/order_utils.py):
Quantisierung auf die echten Binance-Handelsregeln und Bereinigung um die
tatsächlich abgezogenen Handelsgebühren.

Hintergrund (Sicherheitsreview-Punkt K3): Binance zieht die Gebühr bei
einem Spot-Kauf vom erhaltenen Base-Asset ab. `executedQty` ist der
Betrag VOR diesem Abzug - wer ihn als "verfügbare Menge" speichert,
versucht später mehr zu verkaufen, als er hat. Auf dem Testnet fiel das
nie auf (Gebühr dort 0), live beträfe es jeden Verkaufsversuch. Dazu
müssen Mengen und Preise auf gültige Vielfache von stepSize/tickSize
fallen, sonst lehnt die Börse die Order direkt ab.

Reine Funktionen, kein Client, kein Netzwerk.

Ausführen mit:  python -m unittest tests.test_order_utils -v
"""

from __future__ import annotations

import unittest

from dca_bot.order_utils import (
    SymbolTradingRules,
    net_executed_quantity,
    net_proceeds,
    quantize_price,
    quantize_quantity,
    sum_commission,
)

RULES = SymbolTradingRules(
    symbol="BTCUSDT",
    tick_size=0.01,
    step_size=0.00001,
    min_notional=5.0,
    base_asset="BTC",
    quote_asset="USDT",
    quote_precision=8,
)


class QuantizeQuantityTestCase(unittest.TestCase):
    def test_rounds_down_to_step_size(self):
        # 0.000123456 -> auf 0.00001er-Schritte abgerundet
        self.assertAlmostEqual(quantize_quantity(0.000123456, 0.00001), 0.00012, places=10)

    def test_never_rounds_up(self):
        """
        Kern der Regel: eine zu hohe Verkaufsmenge wird von der Börse
        abgelehnt, eine minimal zu niedrige ist nur unwesentlich
        suboptimal - der Fehlerfall ist asymmetrisch.
        """
        for raw in (0.000119999, 0.00019999, 0.0012999, 0.999999):
            with self.subTest(raw=raw):
                self.assertLessEqual(quantize_quantity(raw, 0.00001), raw)

    def test_exact_multiple_is_unchanged(self):
        """
        Off-by-one-Falle: mit float-Arithmetik ist 0.3 / 0.1 gleich
        2.9999999999999996, ein naives floor() würde daraus 0.2 machen.
        Eine Menge, die exakt auf der Schrittweite liegt, muss unverändert
        bleiben.
        """
        self.assertAlmostEqual(quantize_quantity(0.00001, 0.00001), 0.00001, places=12)
        self.assertAlmostEqual(quantize_quantity(0.3, 0.1), 0.3, places=12)
        self.assertAlmostEqual(quantize_quantity(0.0003, 0.00001), 0.0003, places=12)
        self.assertAlmostEqual(quantize_quantity(1.1, 0.1), 1.1, places=12)

    def test_below_step_size_becomes_zero(self):
        """Eine Menge unterhalb einer ganzen Stufe ist nicht handelbar."""
        self.assertEqual(quantize_quantity(0.000009, 0.00001), 0.0)

    def test_round_down_false_rounds_to_nearest(self):
        self.assertAlmostEqual(quantize_quantity(0.000119, 0.00001, round_down=False), 0.00012, places=10)

    def test_missing_rule_leaves_value_unchanged(self):
        self.assertEqual(quantize_quantity(0.123456789, 0.0), 0.123456789)

    def test_zero_and_negative_are_safe(self):
        self.assertEqual(quantize_quantity(0.0, 0.00001), 0.0)
        self.assertEqual(quantize_quantity(-1.0, 0.00001), 0.0)


class QuantizePriceTestCase(unittest.TestCase):
    def test_rounds_down_to_tick_size(self):
        self.assertAlmostEqual(quantize_price(45_123.4567, 0.01), 45_123.45, places=6)

    def test_exact_multiple_is_unchanged(self):
        self.assertAlmostEqual(quantize_price(45_000.0, 0.01), 45_000.0, places=6)
        self.assertAlmostEqual(quantize_price(44_775.0, 0.01), 44_775.0, places=6)

    def test_coarse_tick_size(self):
        """Nicht jedes Symbol hat 0.01 - z.B. tickSize 0.1 oder 1.0."""
        self.assertAlmostEqual(quantize_price(45_123.49, 0.1), 45_123.4, places=6)
        self.assertAlmostEqual(quantize_price(45_123.99, 1.0), 45_123.0, places=6)

    def test_missing_rule_leaves_value_unchanged(self):
        self.assertEqual(quantize_price(45_123.4567, 0.0), 45_123.4567)


class SumCommissionTestCase(unittest.TestCase):
    def test_sums_matching_asset_only(self):
        fills = [
            {"commission": "0.00000015", "commissionAsset": "BTC"},
            {"commission": "0.00000025", "commissionAsset": "BTC"},
            {"commission": "0.5", "commissionAsset": "BNB"},
        ]
        self.assertAlmostEqual(sum_commission(fills, "BTC"), 0.0000004, places=12)
        self.assertAlmostEqual(sum_commission(fills, "BNB"), 0.5, places=12)

    def test_malformed_input_never_raises(self):
        """
        Wird NACH einer bereits ausgeführten Order aufgerufen - eine
        Exception hier würde den Ledger-Eintrag für einen echten Trade
        verhindern. Das wäre schlimmer als eine unerkannte Gebühr.
        """
        for bad in (None, "nicht-liste", 42, [], [None], ["text"], [{"commission": "abc",
                                                                    "commissionAsset": "BTC"}]):
            with self.subTest(bad=bad):
                self.assertEqual(sum_commission(bad, "BTC"), 0.0)


class NetExecutedQuantityTestCase(unittest.TestCase):
    def test_base_asset_commission_reduces_quantity(self):
        """Der eigentliche K3-Fall: Gebühr in BTC kürzt die verfügbare Menge."""
        executed = 0.001
        commission = executed * 0.001  # 0,1% Standardsatz
        order = {
            "executedQty": str(executed),
            "cummulativeQuoteQty": "50.0",
            "fills": [{"commission": str(commission), "commissionAsset": "BTC"}],
        }

        result = net_executed_quantity(order, RULES, fallback=0.0)

        self.assertLess(result, executed, "Menge muss um die Gebühr sinken")
        # 0.001 - 0.000001 = 0.000999, exakt auf stepSize 0.00001 abgerundet
        self.assertAlmostEqual(result, 0.00099, places=10)

    def test_non_base_asset_commission_leaves_quantity_unchanged(self):
        """Bei BNB-Rabatt wird die erhaltene BTC-Menge nicht geschmälert."""
        order = {
            "executedQty": "0.001",
            "cummulativeQuoteQty": "50.0",
            "fills": [{"commission": "0.5", "commissionAsset": "BNB"}],
        }

        self.assertAlmostEqual(net_executed_quantity(order, RULES, fallback=0.0), 0.001, places=10)

    def test_missing_fills_falls_back_to_executed_qty(self):
        order = {"executedQty": "0.001", "cummulativeQuoteQty": "50.0"}
        self.assertAlmostEqual(net_executed_quantity(order, RULES, fallback=0.0), 0.001, places=10)

    def test_missing_executed_qty_uses_fallback(self):
        self.assertAlmostEqual(net_executed_quantity({}, RULES, fallback=0.0003), 0.0003, places=10)

    def test_result_is_always_a_valid_step_multiple(self):
        order = {
            "executedQty": "0.00123456789",
            "fills": [{"commission": "0.00000123", "commissionAsset": "BTC"}],
        }
        result = net_executed_quantity(order, RULES, fallback=0.0)
        steps = result / RULES.step_size
        self.assertAlmostEqual(steps, round(steps), places=6)

    def test_absurd_commission_does_not_produce_negative_quantity(self):
        order = {
            "executedQty": "0.001",
            "fills": [{"commission": "9.0", "commissionAsset": "BTC"}],
        }
        self.assertGreater(net_executed_quantity(order, RULES, fallback=0.0), 0.0)


class NetProceedsTestCase(unittest.TestCase):
    def test_quote_asset_commission_reduces_proceeds(self):
        """Spiegelbild: beim Verkauf rechnet Binance in USDT ab."""
        order = {
            "cummulativeQuoteQty": "50.0",
            "fills": [{"commission": "0.05", "commissionAsset": "USDT"}],
        }
        self.assertAlmostEqual(net_proceeds(order, RULES, fallback=0.0), 49.95, places=8)

    def test_base_asset_commission_does_not_touch_proceeds(self):
        order = {
            "cummulativeQuoteQty": "50.0",
            "fills": [{"commission": "0.000001", "commissionAsset": "BTC"}],
        }
        self.assertAlmostEqual(net_proceeds(order, RULES, fallback=0.0), 50.0, places=8)

    def test_response_without_fills_stays_gross(self):
        """
        get_order()-Antworten (z.B. bei einer bereits gefüllten
        Stop-Loss-Order) enthalten keine Fills - dort bleibt die Gebühr
        mangels Daten unberücksichtigt.
        """
        self.assertAlmostEqual(
            net_proceeds({"cummulativeQuoteQty": "50.0"}, RULES, fallback=0.0), 50.0, places=8
        )


if __name__ == "__main__":
    unittest.main()

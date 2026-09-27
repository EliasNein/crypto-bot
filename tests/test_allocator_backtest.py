"""
Tests fuer den Allocator-Backtest (Systemcheck vom 27.09.2026, W-G).

**Der Befund.** `run_allocated_backtest()` behauptete fuer die Trend-Seite
"exakt dieselbe Entscheidungslogik wie run_trend_backtest", uebergab aber
`stop_loss_paused=False` und setzte nach einem Stop-Loss keine Sperre. Die
kombinierten Zahlen in trading-bot-projekt.md 5a konnten damit
Wiedereinstiege enthalten, die der Live-Bot wegen seines Stop-Loss-Latches
nie gemacht haette - tatsaechlich einer, am 20.10.2023 (siehe 5a).

**Wie getestet wird.** Mit denselben synthetischen Preisreihen wie der
Auto-Reset-Test (tests/test_trend_auto_reset.py, kurze EMA-Perioden,
Gebuehr 0), damit jede Entscheidung von Hand nachvollziehbar bleibt. Der
Kern ist ein Konsistenztest: Blockiert die Zuteilung nie einen Einstieg
(sehr grosser Trend-Betrag), muss die Trend-Seite des Allocator-Backtests
dieselben Trades an denselben Tagen mit denselben Ausstiegsgruenden
liefern wie run_trend_backtest. Das prueft die Behauptung aus dem
Docstring direkt, statt nur den einen gefundenen Fall.

Vorher gab es fuer dieses Modul keinen einzigen Test.

Kein Netzwerk, keine Zugangsdaten.

Ausfuehren mit:  python -m unittest tests.test_allocator_backtest -v
"""

from __future__ import annotations

import contextlib
import io
import unittest
from unittest import mock

from dca_bot import allocator_backtest
from dca_bot.allocator_backtest import (
    isolated_dca_summary,
    isolated_trend_summary,
    run_allocated_backtest,
)
from dca_bot.backtest import run_dca_backtest
from dca_bot.trend_backtest import run_trend_backtest

from tests.test_trend_auto_reset import (
    CRASH,
    ENTRY_PRICE,
    FAST_PERIOD,
    FEE_PCT,
    MIN_GAP_PCT,
    RECOVERY,
    RISE,
    SIGNAL_REVERSAL,
    SLOW_PERIOD,
    START_DATE,
    STOP_LOSS_PCT,
    make_klines,
)

# So gross, dass die Zuteilung einen Einstieg nie am Mindestbetrag
# scheitern laesst - sobald sie ueberhaupt > 0 ist. Damit entscheidet auf
# der Trend-Seite allein die Trend-Logik, und der Vergleich mit
# run_trend_backtest wird exakt.
UNBLOCKED_TREND_AMOUNT = 1_000_000.0

# Nach einem Signal-Ausstieg bei 102.00 (SIGNAL_REVERSAL) ein neuer,
# bestaetigter Aufwaertstrend - der zweite Einstieg ist hier ERLAUBT, weil
# kein Stop-Loss vorlag.
SECOND_RISE = [104.0, 108.0, 113.0, 119.0, 126.0, 134.0]

SERIES = {
    "Stop-Loss, danach Erholung": RISE + CRASH + RECOVERY,
    "Signal-Ausstieg, danach neuer Anstieg": RISE + SIGNAL_REVERSAL + SECOND_RISE,
    "nur Anstieg (offen am Ende)": RISE,
}


def run_allocated(prices, trend_amount=UNBLOCKED_TREND_AMOUNT, stop_loss_pct=STOP_LOSS_PCT):
    return run_allocated_backtest(
        make_klines(prices),
        symbol="TESTUSDT",
        start_date=START_DATE,
        ema_fast_period=FAST_PERIOD,
        ema_slow_period=SLOW_PERIOD,
        zero_anchor_pct=0.0,
        full_anchor_pct=3.0,
        smoothing_period_days=3.0,
        dca_amount=15.0,
        trend_amount=trend_amount,
        trend_min_gap_pct=MIN_GAP_PCT,
        trend_stop_loss_pct=stop_loss_pct,
        fee_pct=FEE_PCT,
    )


def run_trend(prices, reset_cooldown_days=None):
    return run_trend_backtest(
        make_klines(prices),
        symbol="TESTUSDT",
        start_date=START_DATE,
        ema_fast_period=FAST_PERIOD,
        ema_slow_period=SLOW_PERIOD,
        min_gap_pct=MIN_GAP_PCT,
        amount_per_trade=15.0,
        stop_loss_pct=STOP_LOSS_PCT,
        fee_pct=FEE_PCT,
        reset_cooldown_days=reset_cooldown_days,
    )


def decisions(trade_log):
    return [(t["entry_date"], t["exit_date"], t["exit_reason"]) for t in trade_log]


class SeriesPremiseTestCase(unittest.TestCase):
    """Tun die Reihen, was die Tests unten von ihnen brauchen?"""

    def test_recovery_produces_a_new_entry_signal_after_the_stop_loss(self):
        """
        Ohne diese Praemisse waere "nach dem Stop-Loss kein zweiter
        Einstieg" auch dann gruen, wenn die Erholung gar kein
        Einstiegssignal erzeugt. run_trend_backtest mit simuliertem Reset
        nach einem Tag steigt in der Erholung erneut ein.
        """
        result = run_trend(RISE + CRASH + RECOVERY, reset_cooldown_days=1)
        self.assertEqual(result.trade_log[0]["exit_reason"], "stop_loss")
        self.assertIsNotNone(result.open_position_unrealized_pnl)

    def test_second_rise_produces_a_second_trade_after_a_signal_exit(self):
        result = run_trend(RISE + SIGNAL_REVERSAL + SECOND_RISE)
        self.assertEqual(result.trade_log[0]["exit_reason"], "signal")
        self.assertIsNotNone(result.open_position_unrealized_pnl)
        self.assertFalse(result.stop_loss_paused_at_end)

    def test_allocation_does_not_block_the_first_entry(self):
        """Mit dem grossen Betrag steigt die Trend-Seite am selben Tag ein."""
        result = run_allocated(RISE)
        self.assertIsNotNone(result.trend_open_unrealized_pnl)
        self.assertGreater(result.trend_total_invested, 0)


class StopLossLatchTestCase(unittest.TestCase):
    def test_no_reentry_after_stop_loss(self):
        """Der eigentliche W-G-Befund: vorher stieg die Trend-Seite hier wieder ein."""
        result = run_allocated(RISE + CRASH + RECOVERY)

        self.assertEqual([t["exit_reason"] for t in result.trade_log], ["stop_loss"])
        self.assertIsNone(result.trend_open_unrealized_pnl)
        self.assertTrue(result.trend_stop_loss_paused_at_end)

    def test_signal_exit_does_not_latch(self):
        """Die Sperre gilt nur nach einem Stop-Loss, nicht nach einem Signal-Ausstieg."""
        result = run_allocated(RISE + SIGNAL_REVERSAL + SECOND_RISE)

        self.assertEqual([t["exit_reason"] for t in result.trade_log], ["signal"])
        self.assertIsNotNone(result.trend_open_unrealized_pnl)
        self.assertFalse(result.trend_stop_loss_paused_at_end)

    def test_latch_holds_until_the_end_of_the_period(self):
        """
        Wie live bis zum manuellen Reset: auch eine laengere Erholung mit
        mehreren Aufwaertstagen fuehrt zu keinem Einstieg.
        """
        result = run_allocated(RISE + CRASH + RECOVERY + SECOND_RISE)
        self.assertEqual(len(result.trade_log), 1)
        self.assertIsNone(result.trend_open_unrealized_pnl)


class ConsistencyWithTrendBacktestTestCase(unittest.TestCase):
    """
    "Exakt dieselbe Entscheidungslogik wie run_trend_backtest" - hier als
    pruefbare Aussage: gleiche Trades, gleiche Tage, gleiche Gruende,
    gleicher Zustand am Ende.
    """

    def test_same_decisions_as_run_trend_backtest(self):
        for name, prices in SERIES.items():
            with self.subTest(series=name):
                allocated = run_allocated(prices)
                isolated = run_trend(prices)

                self.assertEqual(decisions(allocated.trade_log), decisions(isolated.trade_log))
                self.assertEqual(
                    allocated.trend_open_unrealized_pnl is not None,
                    isolated.open_position_unrealized_pnl is not None,
                )
                self.assertEqual(
                    allocated.trend_stop_loss_paused_at_end,
                    isolated.stop_loss_paused_at_end,
                )

    def test_entry_price_matches(self):
        """Einstieg am selben Kurs wie im Trend-Backtest (106.00)."""
        isolated = run_trend(RISE + CRASH)
        self.assertEqual(isolated.trade_log[0]["entry_price"], ENTRY_PRICE)
        allocated = run_allocated(RISE + CRASH)
        self.assertEqual(
            allocated.trade_log[0]["entry_date"], isolated.trade_log[0]["entry_date"]
        )


# --------------------------------------------------------------------------
# Vergleichszeilen des Reports (Berichtsfehler aus dem W-G-Nebenbefund)
# --------------------------------------------------------------------------

# Zwei per Signal abgeschlossene Trades, am Ende nichts offen - der Aufbau
# des 2023-Falls (dort zwei abgeschlossene Trades, 30,00 investiert).
TWO_CLOSED_TRADES = RISE + SIGNAL_REVERSAL + SECOND_RISE + [125.0, 116.0, 110.0, 105.0]
# Ein abgeschlossener Trade plus eine am Ende offene Position.
TRADE_THEN_OPEN = RISE + SIGNAL_REVERSAL + SECOND_RISE
# Nur eine offene Position, kein abgeschlossener Trade - der 2021-Fall.
ONLY_OPEN = RISE

TREND_AMOUNT = 15.0


class IsolatedTrendSummaryTestCase(unittest.TestCase):
    """
    Die Zeile "isoliert Trend" stellte `total_pnl_pct` aus run_trend_backtest
    neben den investierten Gesamtbetrag. Der Wert ist dort bewusst auf EINEN
    Trade-Betrag bezogen - bei mehreren Trades also zu gross, und eine am
    Ende offene Position fehlte ganz im PnL, zaehlte aber zum Einsatz.
    """

    def test_premise_two_closed_trades_reproduce_the_old_report_value(self):
        """
        Die Reihe hat genau zwei abgeschlossene Trades und nichts offen, und
        der bisher angezeigte Wert ist die Summe bezogen auf 15,00 - also
        genau der Fehler aus 2023 (dort +13,14 % statt +6,57 %).
        """
        result = run_trend(TWO_CLOSED_TRADES)
        self.assertEqual(len(result.trade_log), 2)
        self.assertIsNone(result.open_position_unrealized_pnl)
        self.assertAlmostEqual(
            result.total_pnl_pct, result.total_pnl / TREND_AMOUNT * 100
        )

    def test_two_closed_trades_are_related_to_the_total_invested(self):
        result = run_trend(TWO_CLOSED_TRADES)
        summary = isolated_trend_summary(result, TREND_AMOUNT)

        self.assertEqual(summary.invested, 30.0)
        self.assertAlmostEqual(summary.pnl, sum(t["pnl"] for t in result.trade_log))
        self.assertAlmostEqual(summary.return_pct, summary.pnl / 30.0 * 100)
        # Und das ist ein anderer Wert als der bisher angezeigte - halb so gross.
        self.assertAlmostEqual(summary.return_pct * 2, result.total_pnl_pct)

    def test_open_position_is_valued_at_period_end(self):
        for name, prices, entries in (
            ("Trade plus offene Position", TRADE_THEN_OPEN, 2),
            ("nur offene Position (2021-Fall)", ONLY_OPEN, 1),
        ):
            with self.subTest(series=name):
                result = run_trend(prices)
                # Praemisse: es gibt ein unrealisiertes Ergebnis, das fehlen koennte.
                self.assertIsNotNone(result.open_position_unrealized_pnl)
                self.assertNotAlmostEqual(result.open_position_unrealized_pnl, 0.0)

                summary = isolated_trend_summary(result, TREND_AMOUNT)
                expected_pnl = result.total_pnl + result.open_position_unrealized_pnl
                self.assertEqual(summary.invested, TREND_AMOUNT * entries)
                self.assertAlmostEqual(summary.pnl, expected_pnl)
                self.assertAlmostEqual(summary.return_pct, expected_pnl / summary.invested * 100)

    def test_no_trade_at_all(self):
        summary = isolated_trend_summary(run_trend([100.0] * 12), TREND_AMOUNT)
        self.assertEqual((summary.invested, summary.pnl, summary.return_pct), (0.0, 0.0, 0.0))


class IsolatedDcaSummaryTestCase(unittest.TestCase):
    def test_dca_is_valued_at_period_end(self):
        """
        DCA verkauft nie: PnL = Endwert - Einsatz, bezogen auf den Einsatz.
        Das war schon vorher richtig (dca_return_pct) - der Test haelt fest,
        dass die neue Zeile dieselbe Zahl liefert und jetzt auch den PnL.
        """
        result = run_dca_backtest(
            make_klines(RISE + CRASH), symbol="TESTUSDT", quote_amount=15.0, buy_every_n_candles=1
        )
        summary = isolated_dca_summary(result)
        self.assertEqual(summary.invested, result.total_invested)
        self.assertAlmostEqual(summary.pnl, result.dca_final_value - result.total_invested)
        self.assertAlmostEqual(summary.return_pct, result.dca_return_pct)


class ReportWiringTestCase(unittest.TestCase):
    """
    Der Fehler sass nicht in einer Rechenfunktion, sondern in main(), das
    den falschen Wert an print_report weitergab. Deshalb laeuft dieser Test
    durch die echte main(), nur die Kursdaten sind ersetzt.
    """

    def run_main(self, prices) -> str:
        argv = [
            "allocator_backtest", "--symbol", "TESTUSDT",
            "--start", START_DATE, "--end", "2024-12-31",
            "--ema-fast", str(FAST_PERIOD), "--ema-slow", str(SLOW_PERIOD),
            "--trend-min-gap-pct", str(MIN_GAP_PCT), "--trend-stop-loss-pct", str(STOP_LOSS_PCT),
            "--trend-amount", str(TREND_AMOUNT), "--fee-pct", str(FEE_PCT),
        ]
        out = io.StringIO()
        with mock.patch("sys.argv", argv), mock.patch.object(
            allocator_backtest, "fetch_historical_klines", return_value=make_klines(prices)
        ), contextlib.redirect_stdout(out):
            allocator_backtest.main()
        return out.getvalue()

    @staticmethod
    def line(output: str, marker: str) -> str:
        return next(line for line in output.splitlines() if marker in line)

    def test_trend_line_shows_total_based_pnl_and_percent(self):
        summary = isolated_trend_summary(run_trend(TWO_CLOSED_TRADES), TREND_AMOUNT)
        line = self.line(self.run_main(TWO_CLOSED_TRADES), "isoliert Trend")
        self.assertIn(
            f"investiert {summary.invested:,.2f}, PnL {summary.pnl:+,.2f} ({summary.return_pct:+.2f}%)",
            line,
        )

    def test_trend_line_includes_open_position(self):
        summary = isolated_trend_summary(run_trend(TRADE_THEN_OPEN), TREND_AMOUNT)
        line = self.line(self.run_main(TRADE_THEN_OPEN), "isoliert Trend")
        self.assertIn(f"PnL {summary.pnl:+,.2f} ({summary.return_pct:+.2f}%)", line)

    def test_dca_line_shows_pnl(self):
        output = self.run_main(TWO_CLOSED_TRADES)
        self.assertRegex(self.line(output, "isoliert DCA"), r"PnL [+-][\d,]+\.\d\d \([+-]\d+\.\d\d%\)")

    def test_valuation_rule_is_stated_in_the_report(self):
        self.assertIn("realisiert + unrealisiert", self.run_main(TWO_CLOSED_TRADES))


if __name__ == "__main__":
    unittest.main()

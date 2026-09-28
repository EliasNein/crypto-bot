"""
Backtests nach der Symbolbindung vom 28.09.2026:

- E6: Das Paar (und beim Grid-Backtest Spanne, Abstand und Betrag) kommt
  standardmaessig aus derselben Variablen wie beim Bot. Ohne gesetzte
  Variablen muessen die Backtests exakt mit den bisherigen Werten rechnen -
  sonst liessen sich die Zahlen in trading-bot-projekt.md (5a, 6) nicht
  mehr reproduzieren. Der Bericht nennt die verwendeten Werte und woher
  sie kommen.
- E7: Luecken in den Kerzen (BTCUSDC hat in den Tageskerzen eine vom
  30.09.2022 bis 11.03.2023) werden gewarnt, nie als Fehler behandelt -
  dieselbe Funktion versorgt auch den Live-Vorlauf von Trend-Bot und
  Allocator.
"""

from __future__ import annotations

import contextlib
import io
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from dca_bot import allocator_backtest, backtest, grid_backtest, trend_backtest

BOT_PREFIXES = ("DCA_", "GRID_", "TREND_", "ALLOCATOR_")
DAY_MS = 24 * 60 * 60 * 1000


class _Stop(Exception):
    """Bricht main() nach dem interessierenden Aufruf ab."""


def env_without_bot_variables(**values):
    env = {k: v for k, v in os.environ.items() if not k.startswith(BOT_PREFIXES)}
    env.update(values)
    return mock.patch.dict(os.environ, env, clear=True)


def run_main(module, argv, **env):
    """
    Startet module.main(argv) ohne echte .env (load_dotenv gepatcht) und
    ohne Netz: fetch_historical_klines liefert eine Kerze, die eigentliche
    Simulation wird abgefangen. Gibt (fetch-Mock, Simulations-Mock, Ausgabe)
    zurueck.
    """
    fetch = mock.Mock(return_value=[{"open_time": 0, "close_price": 80_000.0, "low_price": 79_000.0}])
    simulation = mock.Mock(side_effect=_Stop)
    run_name = {
        backtest: "run_dca_backtest",
        grid_backtest: "run_grid_backtest",
        trend_backtest: "run_trend_backtest",
        allocator_backtest: "run_allocated_backtest",
    }[module]
    out = io.StringIO()
    with env_without_bot_variables(**env), \
            mock.patch.object(backtest, "load_dotenv") as load_dotenv, \
            mock.patch.object(module, "fetch_historical_klines", fetch), \
            mock.patch.object(module, run_name, simulation), \
            contextlib.redirect_stdout(out):
        try:
            module.main(argv)
        except _Stop:
            pass
    load_dotenv.assert_called_once()
    return fetch, simulation, out.getvalue()


class DocumentedDefaultsTestCase(unittest.TestCase):
    """
    Ohne gesetzte Variablen und ohne Kommandozeilenwerte kommen bei der
    Simulation genau die Werte an, die bis zum 28.09.2026 fest im Code
    standen. Die Simulationsfunktionen selbst sind unveraendert - gleiche
    Eingaben, gleiche Zahlen wie in 5a und 6.
    """

    def test_dca_backtest(self):
        fetch, simulation, out = run_main(backtest, [])
        self.assertEqual(fetch.call_args.args[0], "BTCUSDT")
        self.assertEqual(simulation.call_args.kwargs["symbol"], "BTCUSDT")
        self.assertEqual(simulation.call_args.kwargs["quote_amount"], 15.0)
        self.assertIn("Symbol: BTCUSDT (Standard, DCA_SYMBOL nicht gesetzt)", out)

    def test_grid_backtest(self):
        fetch, simulation, out = run_main(grid_backtest, ["--no-scaled-analysis"])
        self.assertEqual(fetch.call_args.args[0], "BTCUSDT")
        kwargs = simulation.call_args.kwargs
        self.assertEqual(kwargs["symbol"], "BTCUSDT")
        self.assertEqual(kwargs["lower_limit"], 70000.0)
        self.assertEqual(kwargs["upper_limit"], 90000.0)
        self.assertEqual(kwargs["grid_spacing_pct"], 1.5)
        self.assertEqual(kwargs["amount_per_level"], 15.0)
        self.assertEqual(kwargs["stop_loss_pct"], 15.0)
        for line in (
            "Symbol: BTCUSDT (Standard, GRID_SYMBOL nicht gesetzt)",
            "Untere Grenze: 70000.0 (Standard, GRID_LOWER_LIMIT nicht gesetzt)",
            "Obere Grenze: 90000.0 (Standard, GRID_UPPER_LIMIT nicht gesetzt)",
            "Stufenabstand %: 1.5 (Standard, GRID_SPACING_PCT nicht gesetzt)",
            "Betrag je Stufe: 15.0 (Standard, GRID_AMOUNT_PER_LEVEL nicht gesetzt)",
        ):
            self.assertIn(line, out)

    def test_trend_backtest(self):
        fetch, simulation, out = run_main(trend_backtest, [])
        self.assertEqual(fetch.call_args.args[0], "BTCUSDT")
        self.assertEqual(simulation.call_args.kwargs["symbol"], "BTCUSDT")
        self.assertIn("Symbol: BTCUSDT (Standard, TREND_SYMBOL nicht gesetzt)", out)

    def test_allocator_backtest(self):
        fetch, simulation, out = run_main(allocator_backtest, [])
        self.assertEqual(fetch.call_args.args[0], "BTCUSDT")
        self.assertEqual(simulation.call_args.kwargs["symbol"], "BTCUSDT")
        self.assertIn("Symbol: BTCUSDT (Standard, ALLOCATOR_SYMBOL nicht gesetzt)", out)


class ConfiguredDefaultsTestCase(unittest.TestCase):
    """Gesetzte Variablen werden Standard; die Kommandozeile geht vor."""

    def test_each_backtest_takes_the_pair_of_its_bot(self):
        for module, var in (
            (backtest, "DCA_SYMBOL"),
            (grid_backtest, "GRID_SYMBOL"),
            (trend_backtest, "TREND_SYMBOL"),
            (allocator_backtest, "ALLOCATOR_SYMBOL"),
        ):
            with self.subTest(var=var):
                argv = ["--no-scaled-analysis"] if module is grid_backtest else []
                fetch, simulation, out = run_main(module, argv, **{var: "BTCEUR"})
                self.assertEqual(fetch.call_args.args[0], "BTCEUR")
                self.assertEqual(simulation.call_args.kwargs["symbol"], "BTCEUR")
                self.assertIn(f"Symbol: BTCEUR (aus {var})", out)

    def test_other_bots_variables_do_not_leak(self):
        """Der DCA-Backtest rechnet nicht mit dem Paar des Grid-Bots."""
        fetch, _, _ = run_main(backtest, [], GRID_SYMBOL="BTCEUR", TREND_SYMBOL="BTCEUR")
        self.assertEqual(fetch.call_args.args[0], "BTCUSDT")

    def test_grid_backtest_takes_range_spacing_and_amount(self):
        _, simulation, out = run_main(
            grid_backtest,
            ["--no-scaled-analysis"],
            GRID_SYMBOL="BTCEUR",
            GRID_LOWER_LIMIT="60000",
            GRID_UPPER_LIMIT="75000",
            GRID_SPACING_PCT="2.0",
            GRID_AMOUNT_PER_LEVEL="9",
        )
        kwargs = simulation.call_args.kwargs
        self.assertEqual(
            (kwargs["lower_limit"], kwargs["upper_limit"], kwargs["grid_spacing_pct"],
             kwargs["amount_per_level"]),
            (60000.0, 75000.0, 2.0, 9.0),
        )
        self.assertIn("Untere Grenze: 60000.0 (aus GRID_LOWER_LIMIT)", out)
        self.assertIn("Betrag je Stufe: 9.0 (aus GRID_AMOUNT_PER_LEVEL)", out)

    def test_command_line_wins(self):
        fetch, simulation, out = run_main(
            grid_backtest,
            ["--no-scaled-analysis", "--symbol", "BTCUSDC", "--lower-limit", "65000"],
            GRID_SYMBOL="BTCEUR",
            GRID_LOWER_LIMIT="60000",
        )
        self.assertEqual(fetch.call_args.args[0], "BTCUSDC")
        self.assertEqual(simulation.call_args.kwargs["lower_limit"], 65000.0)
        self.assertIn("Symbol: BTCUSDC (Kommandozeile)", out)
        self.assertIn("Untere Grenze: 65000.0 (Kommandozeile)", out)

    def test_blank_variable_counts_as_not_set(self):
        fetch, _, out = run_main(backtest, [], DCA_SYMBOL="  ")
        self.assertEqual(fetch.call_args.args[0], "BTCUSDT")
        self.assertIn("(Standard, DCA_SYMBOL nicht gesetzt)", out)

    def test_unusable_number_stops_with_a_clear_message(self):
        with self.assertRaises(SystemExit) as ctx:
            run_main(grid_backtest, [], GRID_LOWER_LIMIT="siebzigtausend")
        self.assertIn("GRID_LOWER_LIMIT", str(ctx.exception))


def _raw_candle(open_ms: int, close: float = 50_000.0) -> list:
    return [open_ms, "0", "0", f"{close * 0.99:.2f}", f"{close:.2f}", "0", open_ms + DAY_MS - 1]


def _utc_day_ms(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def fetch_with(candles: list[list], start: str, end: str, interval: str = "1d"):
    """
    fetch_historical_klines gegen eine feste Kerzenliste statt gegen Binance.
    Das Fensterende ist Mitternacht LOKALER Zeit - die Tests fragen deshalb
    bis einen Tag nach der letzten Kerze an.
    """
    def fake_get(url, params, timeout):
        rows = [c for c in candles if params["startTime"] <= c[0] <= params["endTime"]]
        return _Response(rows[: params["limit"]])

    with mock.patch.object(backtest.requests, "get", side_effect=fake_get):
        return backtest.fetch_historical_klines("BTCUSDC", interval, start, end)


def daily_candles(first: str, last: str, skip: tuple[str, str] | None = None) -> list[list]:
    day = datetime.strptime(first, "%Y-%m-%d")
    stop = datetime.strptime(last, "%Y-%m-%d")
    candles = []
    while day <= stop:
        text = day.strftime("%Y-%m-%d")
        if not (skip and skip[0] <= text <= skip[1]):
            candles.append(_raw_candle(_utc_day_ms(text)))
        day += timedelta(days=1)
    return candles


class CandleGapWarningTestCase(unittest.TestCase):
    def test_gap_like_btcusdc_is_warned_and_data_returned(self):
        candles = daily_candles("2022-09-01", "2023-03-31", skip=("2022-09-30", "2023-03-11"))
        with self.assertLogs("dca_bot.backtest", level="WARNING") as logs:
            klines = fetch_with(candles, "2022-09-01", "2023-04-01")
        self.assertEqual(len(klines), len(candles), "Warnen, nicht verwerfen")
        message = "\n".join(logs.output)
        self.assertIn("[KERZEN-LUECKE]", message)
        self.assertIn("BTCUSDC", message)
        self.assertIn("163 Kerzen fehlen", message)
        self.assertIn("2022-09-30 bis 2023-03-11", message)

    def test_complete_data_gives_no_warning(self):
        candles = daily_candles("2023-01-01", "2023-02-28")
        with self.assertNoLogs("dca_bot.backtest", level="WARNING"):
            klines = fetch_with(candles, "2023-01-01", "2023-03-01")
        self.assertEqual(len(klines), len(candles))

    def test_hourly_candles_use_the_hourly_step(self):
        start = _utc_day_ms("2023-01-02")
        candles = [_raw_candle(start + h * 3_600_000) for h in range(48) if h not in (10, 11, 12)]
        with self.assertLogs("dca_bot.backtest", level="WARNING") as logs:
            fetch_with(candles, "2023-01-01", "2023-01-04", interval="1h")
        self.assertIn("3 Kerzen fehlen", "\n".join(logs.output))

    def test_data_starting_later_than_requested_is_warned(self):
        """Paar erst spaeter gelistet (BTCEUR ab 03.01.2020): fehlender Anfang."""
        candles = daily_candles("2020-01-03", "2020-02-29")
        with self.assertLogs("dca_bot.backtest", level="WARNING") as logs:
            klines = fetch_with(candles, "2019-12-01", "2020-03-01")
        self.assertEqual(len(klines), len(candles))
        message = "\n".join(logs.output)
        self.assertIn("erst ab 2020-01-03", message)

    def test_a_failing_check_never_breaks_the_fetch(self):
        """Der Live-Vorlauf darf an der Warnung nie scheitern (E7)."""
        candles = daily_candles("2023-01-01", "2023-01-31")
        with mock.patch.object(backtest, "find_candle_gaps", side_effect=RuntimeError("kaputt")):
            klines = fetch_with(candles, "2023-01-01", "2023-02-01")
        self.assertEqual(len(klines), len(candles))

    def test_unknown_interval_is_not_checked(self):
        candles = daily_candles("2023-01-01", "2023-03-31", skip=("2023-02-01", "2023-02-10"))
        with self.assertNoLogs("dca_bot.backtest", level="WARNING"):
            fetch_with(candles, "2023-01-01", "2023-03-31", interval="1M")


if __name__ == "__main__":
    unittest.main()

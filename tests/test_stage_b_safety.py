"""
Tests fuer Stufe B der "wichtigen" Sicherheitsreview-Punkte:
Korrektheit und Verfuegbarkeit.

- W2  Sofortkauf bei jedem Prozessstart
- W3  Tageslimit-Fenster lokal statt UTC
- W5  Beschaedigtes Ledger setzt Limits still zurueck (plus atomare
      Schreibvorgaenge, ohne die der harte Abbruch ein
      Verfuegbarkeitsproblem waere)
- W10 Toter Allocator friert die Zuteilung ein
- W13 Kein Lebenszeichen
- W15 Grid prueft den Notaus nicht zwischen mehreren Kaeufen

W15 steht bewusst hier und nicht in test_grid_sell_safety.py: dort geht
es um die Verkaufsseite, hier um den Notaus waehrend eines
Mehrfach-Kaufdurchlaufs.

Kein Netzwerk, keine Zugangsdaten, temporaere Dateien.

Ausfuehren mit:  python -m unittest tests.test_stage_b_safety -v
"""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dca_bot.allocator_signals import (
    STALE_ALLOCATION_FALLBACK,
    read_allocation_fraction,
)
from dca_bot.grid_config import GridConfig
from dca_bot.grid_risk import GridLedger
from dca_bot.grid_strategy import GridTradingStrategy
from dca_bot.heartbeat import Heartbeat
from dca_bot.main import _seconds_until_next_cycle
from dca_bot.risk import (
    BotHalted,
    LedgerUnreadable,
    TradeLedger,
    TradeRecord,
    utc_today,
)
from dca_bot.trend_risk import TrendLedger

from tests.test_grid_sell_safety import FakeGridClient


class TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()


# ---------------------------------------------------------------------------
# W3: Tagesfenster in UTC
# ---------------------------------------------------------------------------


class UtcDayWindowTestCase(unittest.TestCase):
    def test_utc_today_matches_utc_not_local_time(self):
        self.assertEqual(utc_today(), datetime.now(timezone.utc).date())

    def test_daily_spend_window_uses_the_same_day_as_the_timestamps(self):
        """
        Kern von W3: die Ledger-Zeitstempel sind UTC. Wird das
        Tagesfenster aus der lokalen Serverzeit gebildet, zaehlt rund um
        den Zeitzonen-Versatz entweder zu viel oder zu wenig gegen das
        Limit.
        """
        with tempfile.TemporaryDirectory() as tmp:
            ledger = TradeLedger(str(Path(tmp) / "ledger.json"))
            now = datetime.now(timezone.utc)
            ledger.record(
                TradeRecord(
                    timestamp=now.isoformat(),
                    symbol="BTCUSDT",
                    quote_spent=15.0,
                    quantity=0.0002,
                    price=77_000.0,
                    dry_run=False,
                )
            )
            self.assertAlmostEqual(
                ledger.spent_on_day("BTCUSDT", utc_today()), 15.0, places=6
            )


# ---------------------------------------------------------------------------
# W5: beschaedigtes Ledger + atomare Writes
# ---------------------------------------------------------------------------


class LedgerIntegrityTestCase(TempDirTestCase):
    """
    Jeder der drei Ledger muss sich gleich verhalten - eine kaputte
    Datei darf nirgends als "leere Historie" durchgehen.
    """

    def _ledgers(self):
        return [
            ("TradeLedger", TradeLedger, "trade_ledger.json"),
            ("GridLedger", GridLedger, "grid_positions.json"),
            ("TrendLedger", TrendLedger, "trend_ledger.json"),
        ]

    def test_missing_file_is_a_fresh_start_not_an_error(self):
        """
        Die vom Nutzer ausdruecklich ausgenommene Grenze: ein frisches
        Deployment mit leerem data/-Ordner muss weiterhin starten.
        """
        for name, cls, filename in self._ledgers():
            with self.subTest(ledger=name):
                path = self.tmp_path / name / filename
                ledger = cls(str(path))
                # Konstruktor legt die Datei an; auch nach dem Loeschen
                # bleibt Lesen erlaubt.
                path.unlink()
                self.assertEqual(ledger._read(), [])

    def test_corrupt_file_raises_instead_of_resetting_silently(self):
        for name, cls, filename in self._ledgers():
            with self.subTest(ledger=name):
                path = self.tmp_path / name / filename
                ledger = cls(str(path))
                path.write_text("{das ist kein json", encoding="utf-8")

                with self.assertRaises(LedgerUnreadable):
                    ledger._read()

    def test_non_list_content_raises(self):
        for name, cls, filename in self._ledgers():
            with self.subTest(ledger=name):
                path = self.tmp_path / name / filename
                ledger = cls(str(path))
                path.write_text('{"kein": "array"}', encoding="utf-8")

                with self.assertRaises(LedgerUnreadable):
                    ledger._read()

    def test_verify_readable_surfaces_the_problem_at_startup(self):
        path = self.tmp_path / "trade_ledger.json"
        ledger = TradeLedger(str(path))
        path.write_text("kaputt", encoding="utf-8")

        with self.assertRaises(LedgerUnreadable):
            ledger.verify_readable()

    def test_daily_limit_does_not_silently_fall_back_to_zero(self):
        """
        Der eigentliche Schaden hinter W5: bei "leerer Historie" wirkt
        das Tageslimit, als waere heute noch nichts ausgegeben worden.
        """
        path = self.tmp_path / "trade_ledger.json"
        ledger = TradeLedger(str(path))
        ledger.record(
            TradeRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                symbol="BTCUSDT",
                quote_spent=45.0,
                quantity=0.0006,
                price=77_000.0,
                dry_run=False,
            )
        )
        path.write_text("kaputt", encoding="utf-8")

        with self.assertRaises(LedgerUnreadable):
            ledger.spent_on_day("BTCUSDT", utc_today())

    def test_writes_are_atomic(self):
        """
        Ohne atomare Writes waere der harte Abbruch oben ein
        Verfuegbarkeitsproblem: ein Absturz mitten im Schreiben (die
        komplette Liste wird bei JEDEM Eintrag neu geschrieben) wuerde
        den Bot dauerhaft stilllegen.
        """
        path = self.tmp_path / "trade_ledger.json"
        ledger = TradeLedger(str(path))
        ledger.record(
            TradeRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                symbol="BTCUSDT",
                quote_spent=15.0,
                quantity=0.0002,
                price=77_000.0,
                dry_run=False,
            )
        )

        leftovers = [p.name for p in path.parent.iterdir() if p.suffix == ".tmp"]
        self.assertEqual(leftovers, [], "Keine temporaere Datei darf zurueckbleiben")
        self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))), 1)


# ---------------------------------------------------------------------------
# W2: kein Sofortkauf nach Neustart
# ---------------------------------------------------------------------------


class StartupDueTimeTestCase(TempDirTestCase):
    INTERVAL = 24 * 3600

    def setUp(self) -> None:
        super().setUp()
        self.ledger = TradeLedger(str(self.tmp_path / "trade_ledger.json"))
        self.logger = logging.getLogger("dca_bot")

    def _record(self, age_hours: float, symbol: str = "BTCUSDT") -> None:
        stamp = datetime.now(timezone.utc) - timedelta(hours=age_hours)
        self.ledger.record(
            TradeRecord(
                timestamp=stamp.isoformat(),
                symbol=symbol,
                quote_spent=15.0,
                quantity=0.0002,
                price=77_000.0,
                dry_run=False,
            )
        )

    def test_empty_ledger_buys_immediately(self):
        """Allererster Start - unveraendertes Verhalten."""
        self.assertEqual(
            _seconds_until_next_cycle(self.ledger, "BTCUSDT", self.INTERVAL, self.logger),
            0,
        )

    def test_recent_trade_delays_the_first_cycle(self):
        """
        Kern von W2: Neustart kurz nach einem Kauf darf NICHT sofort
        wieder kaufen. Faellt gegen den alten Code um (dort gab es
        diese Pruefung gar nicht).
        """
        self._record(age_hours=2)

        wait = _seconds_until_next_cycle(
            self.ledger, "BTCUSDT", self.INTERVAL, self.logger
        )

        self.assertGreater(wait, 0)
        # ~22 Stunden Rest, grosszuegige Toleranz fuer die Laufzeit.
        self.assertAlmostEqual(wait, 22 * 3600, delta=60)

    def test_due_trade_runs_immediately(self):
        self._record(age_hours=30)
        self.assertEqual(
            _seconds_until_next_cycle(self.ledger, "BTCUSDT", self.INTERVAL, self.logger),
            0,
        )

    def test_exactly_at_the_interval_runs_immediately(self):
        self._record(age_hours=24.001)
        self.assertEqual(
            _seconds_until_next_cycle(self.ledger, "BTCUSDT", self.INTERVAL, self.logger),
            0,
        )

    def test_other_symbol_does_not_count(self):
        self._record(age_hours=1, symbol="ETHUSDT")
        self.assertEqual(
            _seconds_until_next_cycle(self.ledger, "BTCUSDT", self.INTERVAL, self.logger),
            0,
        )

    def test_dry_run_entries_count_as_a_cycle(self):
        """
        Die Frage ist "hat in diesem Intervall ein Zyklus
        stattgefunden", nicht "ist echtes Geld geflossen".
        """
        stamp = datetime.now(timezone.utc) - timedelta(hours=1)
        self.ledger.record(
            TradeRecord(
                timestamp=stamp.isoformat(),
                symbol="BTCUSDT",
                quote_spent=15.0,
                quantity=0.0002,
                price=77_000.0,
                dry_run=True,
            )
        )
        self.assertGreater(
            _seconds_until_next_cycle(self.ledger, "BTCUSDT", self.INTERVAL, self.logger),
            0,
        )

    def test_unreadable_timestamp_is_skipped_not_guessed(self):
        self._record(age_hours=1)
        records = json.loads(Path(self.ledger._path).read_text(encoding="utf-8"))
        records[0]["timestamp"] = "kein zeitstempel"
        Path(self.ledger._path).write_text(json.dumps(records), encoding="utf-8")

        with self.assertLogs("dca_bot", level="WARNING"):
            wait = _seconds_until_next_cycle(
                self.ledger, "BTCUSDT", self.INTERVAL, self.logger
            )

        # Im Zweifel "lange nicht gelaufen" - also das bisherige Verhalten.
        self.assertEqual(wait, 0)


# ---------------------------------------------------------------------------
# W10: veraltete Allocator-Zuteilung
# ---------------------------------------------------------------------------


class AllocationFreshnessTestCase(TempDirTestCase):
    def _write_state(self, **overrides) -> str:
        payload = {
            "trend_fraction": 1.0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "interval_minutes": 60,
        }
        payload.update(overrides)
        path = self.tmp_path / "allocator_state.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_fresh_allocation_is_used(self):
        self.assertEqual(read_allocation_fraction(self._write_state()), 1.0)

    def test_stale_allocation_falls_back_to_full_dca(self):
        """
        Kern von W10: stirbt der Allocator, bleibt die letzte Zahl fuer
        immer stehen. Bei eingefrorenen 100%% Trend haette der DCA-Bot
        dauerhaft gar nicht mehr gekauft - ein stiller Ausfall.
        """
        old = datetime.now(timezone.utc) - timedelta(hours=10)
        path = self._write_state(updated_at=old.isoformat())

        with self.assertLogs("dca_bot", level="WARNING") as captured:
            fraction = read_allocation_fraction(path)

        self.assertEqual(fraction, STALE_ALLOCATION_FALLBACK)
        self.assertEqual(fraction, 0.0)
        self.assertTrue(any("veraltet" in line or "alt" in line for line in captured.output))

    def test_threshold_follows_the_interval_from_the_file(self):
        """
        Die Schwelle kommt aus der Datei selbst (3x interval_minutes) -
        keine zweite Konfigurationsquelle, die auseinanderlaufen kann.
        """
        age = datetime.now(timezone.utc) - timedelta(minutes=100)

        # Bei 60-Minuten-Intervall (Grenze 180) noch frisch ...
        self.assertEqual(
            read_allocation_fraction(
                self._write_state(updated_at=age.isoformat(), interval_minutes=60)
            ),
            1.0,
        )
        # ... bei 5-Minuten-Intervall (Grenze 15) laengst veraltet.
        with self.assertLogs("dca_bot", level="WARNING"):
            self.assertEqual(
                read_allocation_fraction(
                    self._write_state(updated_at=age.isoformat(), interval_minutes=5)
                ),
                0.0,
            )

    def test_missing_updated_at_counts_as_stale(self):
        payload_path = self.tmp_path / "state.json"
        payload_path.write_text(json.dumps({"trend_fraction": 1.0}), encoding="utf-8")

        with self.assertLogs("dca_bot", level="WARNING"):
            self.assertEqual(read_allocation_fraction(str(payload_path)), 0.0)

    def test_unreadable_updated_at_counts_as_stale(self):
        path = self._write_state(updated_at="irgendwann")
        with self.assertLogs("dca_bot", level="WARNING"):
            self.assertEqual(read_allocation_fraction(path), 0.0)

    def test_missing_interval_uses_conservative_default(self):
        """State-Dateien aus der Zeit vor diesem Fix kennen das Feld nicht."""
        recent = datetime.now(timezone.utc) - timedelta(minutes=30)
        path = self.tmp_path / "state.json"
        path.write_text(
            json.dumps({"trend_fraction": 0.5, "updated_at": recent.isoformat()}),
            encoding="utf-8",
        )
        self.assertEqual(read_allocation_fraction(str(path)), 0.5)

    def test_disabled_and_missing_file_still_return_none(self):
        """
        Abgrenzung: "kein Allocator konfiguriert" bleibt None, nicht 0.0 -
        sonst wuerde der Trend-Bot faelschlich Einstiege ueberspringen.
        """
        self.assertIsNone(read_allocation_fraction(""))
        self.assertIsNone(read_allocation_fraction(str(self.tmp_path / "gibt-es-nicht.json")))


# ---------------------------------------------------------------------------
# W13: Heartbeat
# ---------------------------------------------------------------------------


class HeartbeatTestCase(unittest.TestCase):
    def test_no_heartbeat_immediately_after_start(self):
        """
        Bewusst: ein Bot in einer Neustartschleife wuerde sonst im
        Minutentakt "ich lebe" melden - genau dann, wenn er es nicht tut.
        """
        with mock.patch("dca_bot.heartbeat.send_notification") as notify:
            Heartbeat("DCA-Bot", 24.0).maybe_send(datetime.now(timezone.utc))
        notify.assert_not_called()

    def test_sends_after_the_interval_elapsed(self):
        heartbeat = Heartbeat("Grid-Bot", 24.0)
        heartbeat._last_sent = datetime.now(timezone.utc) - timedelta(hours=25)

        with mock.patch("dca_bot.heartbeat.send_notification") as notify:
            heartbeat.maybe_send(datetime.now(timezone.utc))

        notify.assert_called_once()
        message = notify.call_args.args[0]
        self.assertIn("[HEARTBEAT]", message)
        self.assertIn("Grid-Bot", message)
        self.assertIn("Version", message)
        self.assertIn("letzter erfolgreicher Zyklus", message)

    def test_sends_only_once_per_interval(self):
        """
        Der Grid-Bot ruft das alle 5 Minuten auf - daraus darf nicht
        alle 5 Minuten eine Nachricht werden.
        """
        heartbeat = Heartbeat("Grid-Bot", 24.0)
        heartbeat._last_sent = datetime.now(timezone.utc) - timedelta(hours=25)

        with mock.patch("dca_bot.heartbeat.send_notification") as notify:
            for _ in range(10):
                heartbeat.maybe_send(datetime.now(timezone.utc))

        self.assertEqual(notify.call_count, 1)

    def test_zero_interval_disables_it(self):
        heartbeat = Heartbeat("Trend-Following-Bot", 0.0)
        heartbeat._last_sent = datetime.now(timezone.utc) - timedelta(days=30)

        with mock.patch("dca_bot.heartbeat.send_notification") as notify:
            heartbeat.maybe_send(datetime.now(timezone.utc))

        notify.assert_not_called()

    def test_reports_when_no_cycle_completed_yet(self):
        heartbeat = Heartbeat("Kapital-Allocator", 24.0)
        heartbeat._last_sent = datetime.now(timezone.utc) - timedelta(hours=25)

        with mock.patch("dca_bot.heartbeat.send_notification") as notify:
            heartbeat.maybe_send(None)

        self.assertIn("noch kein erfolgreicher Zyklus", notify.call_args.args[0])

    def test_stale_cycle_timestamp_is_visible_in_the_message(self):
        """
        "Prozess laeuft" und "Prozess arbeitet" sind nicht dasselbe:
        haengt ein Bot in einem Timeout, bleibt der Zyklus-Zeitstempel
        stehen - und genau das soll in der Nachricht auffallen.
        """
        heartbeat = Heartbeat("Trend-Following-Bot", 24.0)
        heartbeat._last_sent = datetime.now(timezone.utc) - timedelta(hours=25)
        stuck_since = datetime(2026, 9, 10, 8, 5, tzinfo=timezone.utc)

        with mock.patch("dca_bot.heartbeat.send_notification") as notify:
            heartbeat.maybe_send(stuck_since)

        self.assertIn("2026-09-10 08:05 UTC", notify.call_args.args[0])


# ---------------------------------------------------------------------------
# W15: Notaus zwischen mehreren Grid-Kaeufen
# ---------------------------------------------------------------------------


class GridKillSwitchBetweenBuysTestCase(TempDirTestCase):
    def _make_strategy(self, price: float):
        self.kill_switch_file = self.tmp_path / "STOP_GRID"
        config = GridConfig(
            api_key="test",
            api_secret="test",
            symbol="BTCUSDT",
            lower_limit=70_000.0,
            upper_limit=90_000.0,
            grid_spacing_pct=1.5,
            amount_per_level=15.0,
            trading_enabled=True,
            kill_switch_file=str(self.kill_switch_file),
            state_file=str(self.tmp_path / "grid_positions.json"),
            stop_loss_state_file=str(self.tmp_path / "grid_stop_loss.json"),
            pending_orders_file=str(self.tmp_path / "pending.json"),
        )
        client = FakeGridClient(True, price)
        return GridTradingStrategy(config, client), client

    def test_kill_switch_stops_remaining_buys_of_the_same_cycle(self):
        """
        Kern von W15: faellt der Preis in einem Intervall durch mehrere
        Stufen (Crash), kauft die Schleife mehrere Positionen
        hintereinander - und genau dann zieht jemand den Notaus. Vorher
        liefen alle verbleibenden Kaeufe trotzdem durch, weil nur EINMAL
        vor der Schleife geprueft wurde.

        Faellt gegen den alten Code um.
        """
        strategy, client = self._make_strategy(price=88_000.0)
        # Referenzpreis oben setzen, dann tief fallen lassen: dadurch
        # werden mehrere Stufen auf einmal durchquert.
        strategy._last_seen_price = 88_000.0

        kill_file = self.kill_switch_file

        original_buy = client.place_market_buy

        def buy_then_trigger_kill_switch(*args, **kwargs):
            result = original_buy(*args, **kwargs)
            kill_file.write_text("", encoding="utf-8")  # Notaus nach dem 1. Kauf
            return result

        client.place_market_buy = buy_then_trigger_kill_switch

        with self.assertRaises(BotHalted):
            strategy._process_buys(71_000.0)

        # Genau EIN Kauf - der laufende wurde zu Ende gefuehrt und
        # verbucht, alle weiteren nicht mehr begonnen.
        self.assertEqual(len(client.market_buy_calls), 1)
        self.assertEqual(len(strategy._ledger.open_positions()), 1)

    def test_all_levels_are_bought_without_kill_switch(self):
        """Gegenprobe: ohne Notaus bleibt das Mehrfachkauf-Verhalten."""
        strategy, client = self._make_strategy(price=88_000.0)
        strategy._last_seen_price = 88_000.0

        strategy._process_buys(71_000.0)

        self.assertGreater(len(client.market_buy_calls), 1)
        self.assertEqual(
            len(strategy._ledger.open_positions()), len(client.market_buy_calls)
        )

    def test_nothing_is_left_unrecorded_when_halting(self):
        """
        Wichtig fuer die Sicherheit: die bereits getaetigten Kaeufe
        muessen im Ledger stehen, bevor BotHalted fliegt - sonst waere
        aus W15 ein K2-artiger unverbuchter Trade geworden.
        """
        strategy, client = self._make_strategy(price=88_000.0)
        strategy._last_seen_price = 88_000.0
        self.kill_switch_file.write_text("", encoding="utf-8")

        with self.assertRaises(BotHalted):
            strategy._process_buys(71_000.0)

        # Notaus griff schon vor dem ersten Kauf.
        self.assertEqual(client.market_buy_calls, [])
        self.assertEqual(strategy._ledger.open_positions(), [])


if __name__ == "__main__":
    unittest.main()

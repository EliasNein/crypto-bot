"""
Tests fuer Stufe C der "wichtigen" Sicherheitsreview-Punkte: die letzten
Code-Punkte vor dem Echtgeld-Schalter.

- W12 Kein Live-Schalter, kein Pflichtvariablen-Check
- W11 Geteiltes Konto/Symbol ohne Reservierung
- W9  Allocator-Reaktivitaet weicht vom Backtest ab

W16 (Kapitalbindung gegen den 150-EUR-Topf) und W14 (Grid ohne
boersenseitigen Stop-Loss) tauchen hier bewusst nicht auf: W16 war eine
Rechenaufgabe ohne Code-Aenderung, W14 ist als eigene
Architekturentscheidung zurueckgestellt (siehe trading-bot-projekt.md 6g).

Mehrere Tests sind ausdruecklich als Negativkontrolle gegen den ALTEN
Stand gebaut - sie fallen um, wenn man die jeweilige Aenderung
zurueckdreht:

- `parse_bool_strict` statt `... .lower() == "true"`: der Tippfehler-Test
  (USE_TESTNET=ture) wuerde sonst still "live" ergeben.
- Deckungspruefung vor dem Verkauf: ohne sie wuerde place_market_sell()
  aufgerufen.
- Feed-Takt des Allocators: ohne die Entkopplung ruecken EMAs und
  Glaettung bei jedem Zyklus vor statt einmal pro Tag.

Kein Netzwerk, keine Zugangsdaten, temporaere Dateien.

Ausfuehren mit:  python -m unittest tests.test_stage_c_safety -v
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dca_bot import allocator as allocator_module
from dca_bot.allocator import Allocator
from dca_bot.allocator_config import AllocatorConfig, load_allocator_config
from dca_bot.balance_guard import (
    SELL_INSUFFICIENT,
    SELL_OK,
    SELL_UNKNOWN,
    BalanceSnapshot,
    build_snapshot,
    check_sell_coverage,
    ledger_exceeds_account,
    split_locked_quantity,
)
from dca_bot.config import load_config
from dca_bot.config_guard import (
    USE_TESTNET_VAR,
    ConfigError,
    announce_trading_mode,
    env_float,
    env_int,
    env_text,
    load_use_testnet,
    parse_bool_strict,
)
from dca_bot.grid_config import load_grid_config
from dca_bot.trend_config import load_trend_config
from dca_bot.trend_signals import TrendSignalGenerator

from tests.test_grid_sell_safety import FAKE_TRADING_RULES, GridStrategyTestBase
from tests.test_trend_stop_loss import TrendStrategyTestBase


# Alle Variablen, die die vier load_*-Funktionen lesen. Jeder Test startet
# aus einer sauberen Umgebung, damit weder die .env des Entwicklungs-
# rechners noch ein vorheriger Test durchschlaegt.
_MANAGED_PREFIXES = ("DCA_", "GRID_", "TREND_", "ALLOCATOR_", "TELEGRAM_", "BINANCE_")
_MANAGED_NAMES = (USE_TESTNET_VAR, "HEARTBEAT_INTERVAL_HOURS")


class EnvTestCase(unittest.TestCase):
    """Basis mit kontrollierter, leerer Umgebung plus gueltigen Keys."""

    def setUp(self) -> None:
        self._saved = dict(os.environ)
        for name in list(os.environ):
            if name.startswith(_MANAGED_PREFIXES) or name in _MANAGED_NAMES:
                del os.environ[name]
        os.environ["BINANCE_API_KEY"] = "testkey1234567890"
        os.environ["BINANCE_API_SECRET"] = "testsecret1234567890"

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved)

    def go_live(self) -> None:
        """Schaltet auf Live und setzt alles, was dort Pflicht ist."""
        os.environ[USE_TESTNET_VAR] = "false"
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456:abcdef"
        os.environ["TELEGRAM_CHAT_ID"] = "4711"
        os.environ["DCA_QUOTE_AMOUNT"] = "15.0"
        os.environ["DCA_MAX_DAILY_SPEND"] = "50.0"
        os.environ["GRID_LOWER_LIMIT"] = "68000.0"
        os.environ["GRID_UPPER_LIMIT"] = "88000.0"
        os.environ["GRID_AMOUNT_PER_LEVEL"] = "8.82"
        os.environ["TREND_AMOUNT_PER_TRADE"] = "15.0"


# --------------------------------------------------------------------------
# W12 - Live-Schalter
# --------------------------------------------------------------------------


class StrictBoolTestCase(unittest.TestCase):
    """
    Negativkontrolle gegen den alten Stand: Vor W12 wurde ueberall
    `os.getenv(...).lower() == "true"` verwendet. Diese Schreibweise
    bildet JEDEN unbekannten Wert auf False ab - fuer USE_TESTNET
    bedeutet das "nicht Testnet", also live mit echtem Geld, und zwar
    ohne jede Fehlermeldung.
    """

    def test_accepts_true_and_false(self):
        self.assertIs(parse_bool_strict("X", "true"), True)
        self.assertIs(parse_bool_strict("X", "false"), False)

    def test_is_case_insensitive_and_trimmed(self):
        self.assertIs(parse_bool_strict("X", "  TRUE  "), True)
        self.assertIs(parse_bool_strict("X", "False"), False)

    def test_typo_raises_instead_of_silently_going_live(self):
        with self.assertRaises(ConfigError) as ctx:
            parse_bool_strict(USE_TESTNET_VAR, "ture")
        # Die Meldung muss den Variablennamen und den Wert nennen -
        # sonst sucht man ihn in gut zwei Dutzend Variablen.
        self.assertIn(USE_TESTNET_VAR, str(ctx.exception))
        self.assertIn("ture", str(ctx.exception))

    def test_numeric_and_other_truthy_spellings_are_refused(self):
        for value in ("1", "0", "yes", "ja", "on", "", "  "):
            with self.subTest(value=value):
                with self.assertRaises(ConfigError):
                    parse_bool_strict("X", value)


class UseTestnetSwitchTestCase(EnvTestCase):
    def test_default_is_testnet_for_all_four_bots(self):
        """
        Der Default muss Testnet sein: Auf beiden Servern steht
        USE_TESTNET heute nicht in der .env, und ein Update darf ihr
        Verhalten nicht veraendern.
        """
        self.assertTrue(load_use_testnet())
        self.assertTrue(load_config().use_testnet)
        self.assertTrue(load_grid_config().use_testnet)
        self.assertTrue(load_trend_config().use_testnet)
        self.assertTrue(load_allocator_config().use_testnet)

    def test_env_variable_flips_all_four_bots(self):
        self.go_live()
        self.assertFalse(load_config().use_testnet)
        self.assertFalse(load_grid_config().use_testnet)
        self.assertFalse(load_trend_config().use_testnet)
        self.assertFalse(load_allocator_config().use_testnet)

    def test_use_testnet_is_no_longer_hardcoded(self):
        """
        Der eigentliche W12-Befund: `use_testnet: bool = True` stand hart
        in allen vier Configs und wurde von keiner load_*-Funktion aus
        der Umgebung gelesen. "Live gehen" waere ein Code-Edit gewesen.
        """
        os.environ[USE_TESTNET_VAR] = "true"
        self.assertTrue(load_grid_config().use_testnet)
        os.environ[USE_TESTNET_VAR] = "false"
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456:abcdef"
        os.environ["TELEGRAM_CHAT_ID"] = "4711"
        os.environ["GRID_LOWER_LIMIT"] = "68000.0"
        os.environ["GRID_UPPER_LIMIT"] = "88000.0"
        os.environ["GRID_AMOUNT_PER_LEVEL"] = "8.82"
        self.assertFalse(load_grid_config().use_testnet)


class LiveModeAnnouncementTestCase(unittest.TestCase):
    """
    Die Sicherheitsschwelle selbst: Der Wechsel auf Live darf nicht
    stillschweigend passieren, sondern muss im Log UND per Telegram
    auftauchen.
    """

    def setUp(self) -> None:
        self.logger = logging.getLogger("stage_c_announce_test")
        self.logger.propagate = False
        self.logger.setLevel(logging.DEBUG)

    def _announce(self, **kwargs) -> tuple[list[logging.LogRecord], list[str]]:
        sent: list[str] = []
        with mock.patch("dca_bot.notifier.send_notification", sent.append):
            with self.assertLogs(self.logger, level=logging.DEBUG) as captured:
                announce_trading_mode(self.logger, "DCA-Bot", **kwargs)
        return captured.records, sent

    def test_testnet_stays_quiet_and_sends_nothing(self):
        """
        Der Normalfall darf nicht wie der Ausnahmefall aussehen - sonst
        gewoehnt man sich an den Alarm und uebersieht ihn, wenn er zaehlt.
        """
        records, sent = self._announce(
            use_testnet=True,
            trading_enabled=False,
            enable_var_name="DCA_BOT_ENABLE_TRADING",
        )
        self.assertEqual([r.levelno for r in records], [logging.INFO])
        self.assertIn("TESTNET", records[0].getMessage())
        self.assertEqual(sent, [])

    def test_live_with_trading_logs_critical_and_notifies(self):
        records, sent = self._announce(
            use_testnet=False,
            trading_enabled=True,
            enable_var_name="DCA_BOT_ENABLE_TRADING",
        )
        self.assertTrue(all(r.levelno == logging.CRITICAL for r in records))
        text = "\n".join(r.getMessage() for r in records)
        self.assertIn("ACHTUNG: LIVE-MODUS MIT ECHTEM GELD AKTIV", text)
        self.assertEqual(len(sent), 1)
        self.assertIn("LIVE-MODUS MIT ECHTEM GELD AKTIV", sent[0])

    def test_live_without_trading_is_its_own_case(self):
        """
        Live-Keys plus deaktiviertes Trading ist ein DRITTER Zustand, kein
        harmloser Dry-Run: die Kontodaten sind echt, und ein Umlegen
        EINER Variable genuegt fuer echtes Geld.
        """
        records, sent = self._announce(
            use_testnet=False,
            trading_enabled=False,
            enable_var_name="GRID_BOT_ENABLE_TRADING",
        )
        text = "\n".join(r.getMessage() for r in records)
        self.assertTrue(all(r.levelno == logging.WARNING for r in records))
        self.assertIn("LIVE-KONTO", text)
        self.assertNotIn("MIT ECHTEM GELD AKTIV", text)
        self.assertEqual(len(sent), 1)

    def test_allocator_case_mentions_that_it_places_no_orders(self):
        records, sent = self._announce(use_testnet=False, trading_enabled=None)
        text = "\n".join(r.getMessage() for r in records)
        self.assertIn("keine Orders", text)
        self.assertEqual(len(sent), 1)

    def test_banner_lines_are_hard_to_miss(self):
        """Der Block muss als Block erkennbar sein, nicht als eine Zeile."""
        records, _ = self._announce(
            use_testnet=False,
            trading_enabled=True,
            enable_var_name="DCA_BOT_ENABLE_TRADING",
        )
        self.assertGreater(len(records), 5)
        self.assertTrue(records[0].getMessage().startswith("!!!!"))
        self.assertTrue(records[-1].getMessage().startswith("!!!!"))


# --------------------------------------------------------------------------
# W12 - Pflichtvariablen-Check
# --------------------------------------------------------------------------


class MandatoryConfigTestCase(EnvTestCase):
    def test_missing_credentials_abort(self):
        del os.environ["BINANCE_API_KEY"]
        with self.assertRaises(ConfigError):
            load_config()

    def test_placeholder_credentials_abort(self):
        os.environ["BINANCE_API_KEY"] = "dein_testnet_key"
        with self.assertRaises(ConfigError):
            load_grid_config()

    def test_telegram_placeholder_from_env_example_is_refused(self):
        """
        Ein kopierter Platzhalter ist kein gesetzter Wert: er faellt sonst
        nie beim Start auf, sondern als stilles HTTP 401 bei JEDEM
        Versand - also genau dann, wenn die Nachricht gebraucht wird.
        """
        os.environ["TELEGRAM_BOT_TOKEN"] = "dein_telegram_bot_token"
        with self.assertRaises(ConfigError):
            load_trend_config()

    def test_empty_value_is_not_the_same_as_unset(self):
        """
        `GRID_SYMBOL=` in der .env ist eine Angabe, keine fehlende Zeile -
        der Default darf sie nicht stillschweigend ersetzen.
        """
        self.assertEqual(load_grid_config().symbol, "BTCUSDT")
        os.environ["GRID_SYMBOL"] = ""
        with self.assertRaises(ConfigError):
            load_grid_config()

    def test_zero_interval_is_refused_because_it_would_busy_loop(self):
        os.environ["GRID_INTERVAL_MINUTES"] = "0"
        with self.assertRaises(ConfigError):
            load_grid_config()

    def test_unparsable_number_names_the_variable(self):
        os.environ["GRID_AMOUNT_PER_LEVEL"] = "15,0"
        with self.assertRaises(ConfigError) as ctx:
            load_grid_config()
        self.assertIn("GRID_AMOUNT_PER_LEVEL", str(ctx.exception))

    def test_impossible_stop_loss_percentage_is_refused(self):
        """150% unter der Untergrenze waere eine negative Schwelle - der
        Stop-Loss waere still wirkungslos statt abgeschaltet."""
        os.environ["GRID_STOP_LOSS_PCT"] = "150"
        with self.assertRaises(ConfigError):
            load_grid_config()

    def test_zero_is_still_allowed_where_it_means_disabled(self):
        """
        Abgrenzung: Bei DCA und Grid heisst 0 dokumentiert "Stop-Loss
        aus". Das darf die neue Pruefung nicht kaputtmachen.
        """
        os.environ["DCA_BOT_STOP_LOSS_PCT"] = "0"
        os.environ["GRID_STOP_LOSS_PCT"] = "0"
        os.environ["HEARTBEAT_INTERVAL_HOURS"] = "0"
        self.assertEqual(load_config().stop_loss_pct, 0.0)
        self.assertEqual(load_grid_config().stop_loss_pct, 0.0)
        self.assertEqual(load_grid_config().heartbeat_interval_hours, 0.0)

    def test_zero_trend_stop_loss_is_refused_unlike_dca_and_grid(self):
        """
        Beim Trend-Bot ist 0 NICHT "aus", sondern fatal: is_stop_loss_hit()
        vergleicht dann gegen den Einstiegspreis selbst und schliesst die
        Position im ersten Zyklus ohne Kursgewinn wieder.
        """
        os.environ["TREND_STOP_LOSS_PCT"] = "0"
        with self.assertRaises(ConfigError):
            load_trend_config()

    def test_zero_stop_limit_offset_is_refused(self):
        os.environ["TREND_STOP_LIMIT_OFFSET_PCT"] = "0"
        with self.assertRaises(ConfigError):
            load_trend_config()

    def test_daily_limit_below_purchase_amount_is_refused(self):
        """Sonst blockiert das Tageslimit JEDEN Kauf und der Bot laeuft
        dauerhaft leer, ohne dass etwas darauf hinweist."""
        os.environ["DCA_QUOTE_AMOUNT"] = "30"
        os.environ["DCA_MAX_DAILY_SPEND"] = "20"
        with self.assertRaises(ConfigError):
            load_config()

    def test_empty_pending_orders_path_is_refused(self):
        """Ein leerer Pfad schaltet die K2-Absicherung ab - das fiel
        vorher erst bei der ersten Order auf."""
        os.environ["TREND_PENDING_ORDERS_FILE"] = ""
        with self.assertRaises(ConfigError):
            load_trend_config()

    def test_allocator_state_file_may_be_empty_because_that_means_off(self):
        """Gegenprobe: Wo leer eine gueltige Bedeutung hat, bleibt es
        erlaubt."""
        os.environ["DCA_ALLOCATOR_STATE_FILE"] = ""
        self.assertEqual(load_config().allocator_state_file, "")

    def test_broken_halt_variable_is_caught_at_startup(self):
        """
        KillSwitch liest zur Laufzeit bewusst tolerant weiter (eine
        Exception alle fuenf Sekunden waere schlimmer als das Problem).
        Der Start ist der einzige Moment, an dem ein Tippfehler dort
        gefahrlos auffallen kann - und `GRID_BOT_HALT=ture` bedeutet
        "kein Notaus", waehrend der Mensch vom Gegenteil ausgeht.
        """
        os.environ["GRID_BOT_HALT"] = "ture"
        with self.assertRaises(ConfigError):
            load_grid_config()

    def test_numeric_helpers_reject_nan_and_infinity(self):
        os.environ["X"] = "nan"
        with self.assertRaises(ConfigError):
            env_float("X", "1.0")
        os.environ["X"] = "inf"
        with self.assertRaises(ConfigError):
            env_float("X", "1.0")
        del os.environ["X"]

    def test_int_helper_refuses_a_decimal(self):
        os.environ["X"] = "5.5"
        with self.assertRaises(ConfigError):
            env_int("X", "5")
        del os.environ["X"]

    def test_text_helper_keeps_default_when_unset(self):
        self.assertEqual(env_text("DOES_NOT_EXIST_XYZ", "fallback"), "fallback")


class LiveModeRequirementsTestCase(EnvTestCase):
    def test_live_requires_telegram(self):
        """
        Ohne Kanal kommen im Echtgeld-Betrieb ausgerechnet
        [ORDER-UNKLAR], [STOP-LOSS] und [HEARTBEAT] nicht an.
        """
        os.environ[USE_TESTNET_VAR] = "false"
        with self.assertRaises(ConfigError) as ctx:
            load_config()
        self.assertIn("TELEGRAM", str(ctx.exception))

    def test_testnet_keeps_telegram_optional(self):
        """Abgrenzung: im Testnet bleibt Telegram wie bisher abschaltbar."""
        config = load_config()
        self.assertEqual(config.telegram_bot_token, "")

    def test_live_requires_explicit_position_sizes(self):
        """
        Die Defaults (15.00 pro Kauf, Grid 70k-90k) stammen aus der
        Testnet-Phase. Live bestimmen genau sie die Kapitalbindung, und
        ein vergessener Eintrag saehe im Log aus wie ein bewusst
        gewaehlter Wert (siehe W16).
        """
        os.environ[USE_TESTNET_VAR] = "false"
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456:abcdef"
        os.environ["TELEGRAM_CHAT_ID"] = "4711"
        with self.assertRaises(ConfigError) as ctx:
            load_grid_config()
        self.assertIn("GRID_", str(ctx.exception))

    def test_live_with_everything_set_loads(self):
        self.go_live()
        grid = load_grid_config()
        self.assertFalse(grid.use_testnet)
        self.assertEqual(grid.amount_per_level, 8.82)
        self.assertFalse(load_config().use_testnet)
        self.assertFalse(load_trend_config().use_testnet)

    def test_testnet_does_not_require_explicit_sizes(self):
        """Gegenprobe: im Testnet bleiben die Defaults zulaessig - sonst
        waere kein bestehendes Deployment mehr startfaehig."""
        self.assertEqual(load_grid_config().amount_per_level, 15.0)


# --------------------------------------------------------------------------
# W11 - geteiltes Konto
# --------------------------------------------------------------------------


def _sell_order(client_order_id: str, qty: float, executed: float = 0.0, status: str = "NEW"):
    return {
        "clientOrderId": client_order_id,
        "side": "SELL",
        "status": status,
        "origQty": str(qty),
        "executedQty": str(executed),
    }


class LockedQuantityAttributionTestCase(unittest.TestCase):
    """
    Die Zuordnung "welche gebundene Menge gehoert wem" ist ueberhaupt nur
    moeglich, weil der K2-Fix jeder Order ein Bot-Praefix in der
    clientOrderId gibt - hier wird vorhandene Infrastruktur genutzt statt
    neuer eingefuehrt.
    """

    def test_own_and_foreign_orders_are_separated_by_prefix(self):
        orders = [
            _sell_order("grid-aaa", 0.001),
            _sell_order("trend-bbb", 0.002),
            _sell_order("dca-ccc", 0.004),
        ]
        own, foreign = split_locked_quantity(orders, "grid")
        self.assertAlmostEqual(own, 0.001)
        self.assertAlmostEqual(foreign, 0.006)

    def test_partially_filled_order_only_binds_the_remainder(self):
        orders = [_sell_order("trend-bbb", 0.002, executed=0.0015, status="PARTIALLY_FILLED")]
        own, foreign = split_locked_quantity(orders, "grid")
        self.assertAlmostEqual(foreign, 0.0005)

    def test_buy_orders_do_not_bind_base_asset(self):
        """Eine offene Kauf-Order bindet USDT, nicht BTC."""
        orders = [{"clientOrderId": "trend-x", "side": "BUY", "status": "NEW",
                   "origQty": "0.01", "executedQty": "0"}]
        own, foreign = split_locked_quantity(orders, "grid")
        self.assertEqual((own, foreign), (0.0, 0.0))

    def test_terminal_orders_do_not_bind_anything(self):
        for status in ("FILLED", "CANCELED", "EXPIRED", "REJECTED"):
            with self.subTest(status=status):
                own, foreign = split_locked_quantity(
                    [_sell_order("grid-a", 0.01, status=status)], "grid"
                )
                self.assertEqual((own, foreign), (0.0, 0.0))

    def test_unknown_order_counts_as_foreign(self):
        """
        Die konservative Richtung: Eine Order ohne erkennbares Praefix
        (manueller Handel ueber die Boersen-Oberflaeche) als eigene zu
        zaehlen wuerde die Obergrenze kuenstlich erhoehen und damit eine
        echte Diskrepanz verdecken.
        """
        own, foreign = split_locked_quantity([_sell_order("", 0.01)], "grid")
        self.assertAlmostEqual(foreign, 0.01)
        self.assertEqual(own, 0.0)

    def test_failed_order_query_is_unknown_not_empty(self):
        self.assertIsNone(split_locked_quantity(None, "grid"))

    def test_snapshot_without_order_data_treats_all_locked_as_foreign(self):
        snapshot = build_snapshot((1.0, 0.5), None, "grid")
        self.assertEqual(snapshot.own_locked, 0.0)
        self.assertEqual(snapshot.foreign_locked, 0.5)

    def test_snapshot_is_none_when_balance_is_unavailable(self):
        self.assertIsNone(build_snapshot(None, [], "grid"))


class CoverageCheckTestCase(unittest.TestCase):
    STEP = FAKE_TRADING_RULES.step_size

    def test_enough_free_balance_passes(self):
        snapshot = BalanceSnapshot(free=1.0, locked=0.0, own_locked=0.0, foreign_locked=0.0)
        self.assertEqual(check_sell_coverage(snapshot, 0.5, self.STEP), SELL_OK)

    def test_insufficient_free_balance_is_detected(self):
        snapshot = BalanceSnapshot(free=0.1, locked=0.9, own_locked=0.0, foreign_locked=0.9)
        self.assertEqual(check_sell_coverage(snapshot, 0.5, self.STEP), SELL_INSUFFICIENT)

    def test_own_locked_quantity_does_not_count_as_available(self):
        """
        Eine Menge, die in einer eigenen offenen Order steckt, ist in
        diesem Moment nicht verkaeuflich - sie muesste erst storniert
        werden. Genau deshalb laeuft die Pruefung beim Trend-Bot NACH
        _resolve_stop_order_before_close().
        """
        snapshot = BalanceSnapshot(free=0.0, locked=1.0, own_locked=1.0, foreign_locked=0.0)
        self.assertEqual(check_sell_coverage(snapshot, 0.5, self.STEP), SELL_INSUFFICIENT)

    def test_unavailable_snapshot_is_unknown_not_insufficient(self):
        """
        Ein gescheiterter Abruf ist keine Aussage ueber das Konto. Ihn
        wie "zu wenig Guthaben" zu behandeln wuerde einen
        Stop-Loss-Ausstieg wegen eines Netzwerk-Haengers verhindern - die
        deutlich gefaehrlichere Richtung.
        """
        self.assertEqual(check_sell_coverage(None, 0.5, self.STEP), SELL_UNKNOWN)

    def test_rounding_remainder_does_not_block_a_sell(self):
        snapshot = BalanceSnapshot(
            free=0.5 - self.STEP / 2, locked=0.0, own_locked=0.0, foreign_locked=0.0
        )
        self.assertEqual(check_sell_coverage(snapshot, 0.5, self.STEP), SELL_OK)


class LedgerMismatchTestCase(unittest.TestCase):
    STEP = FAKE_TRADING_RULES.step_size

    def test_matching_ledger_raises_no_alarm(self):
        snapshot = BalanceSnapshot(free=1.0, locked=0.0, own_locked=0.0, foreign_locked=0.0)
        self.assertFalse(ledger_exceeds_account(snapshot, 1.0, self.STEP))

    def test_ledger_claiming_more_than_possible_is_detected(self):
        snapshot = BalanceSnapshot(free=0.2, locked=0.5, own_locked=0.0, foreign_locked=0.5)
        self.assertTrue(ledger_exceeds_account(snapshot, 1.0, self.STEP))

    def test_own_locked_quantity_still_counts_as_owned(self):
        """
        Fuer die Buchhaltungsfrage zaehlt eigenes gebundenes Guthaben sehr
        wohl mit - es ist nur gerade nicht verkaeuflich, aber es gehoert
        dem Bot. Sonst wuerde jede eigene Stop-Loss-Order einen
        Fehlalarm ausloesen.
        """
        snapshot = BalanceSnapshot(free=0.0, locked=1.0, own_locked=1.0, foreign_locked=0.0)
        self.assertFalse(ledger_exceeds_account(snapshot, 1.0, self.STEP))

    def test_fee_sized_difference_stays_within_tolerance(self):
        snapshot = BalanceSnapshot(
            free=1.0 - 0.0005, locked=0.0, own_locked=0.0, foreign_locked=0.0
        )
        self.assertFalse(ledger_exceeds_account(snapshot, 1.0, self.STEP))

    def test_no_alarm_without_data(self):
        self.assertFalse(ledger_exceeds_account(None, 1.0, self.STEP))


class GridBalanceGuardTestCase(GridStrategyTestBase):
    """Der Check im echten Grid-Verkaufspfad."""

    def _open_position(self, strategy, client, quantity=0.0002):
        from dca_bot.grid_risk import GridPosition

        strategy._ledger.record_buy(
            GridPosition.new(
                level_index=0,
                buy_price=70_000.0,
                target_sell_price=78_000.0,
                quantity=quantity,
                quote_spent=15.0,
                dry_run=False,
                client_order_id="grid-existing",
            )
        )

    def test_uncovered_sell_is_not_attempted(self):
        """
        Negativkontrolle: Ohne die Deckungspruefung wuerde hier
        place_market_sell() aufgerufen und die Boerse die Order mit
        "insufficient balance" ablehnen - ein Fehlschlag, der im Log wie
        ein Netzwerkproblem aussieht.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        self._open_position(strategy, client)
        # Das BTC liegt in einer Order des Trend-Bots.
        client.base_balance = (0.0, 0.0002)
        client.open_orders = [_sell_order("trend-other", 0.0002)]

        strategy._process_sells(79_000.0)

        self.assertEqual(client.market_sell_calls, [])
        self.assertEqual(len(strategy._ledger.open_positions()), 1)

    def test_covered_sell_still_goes_through(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        self._open_position(strategy, client)
        client.base_balance = (0.0002, 0.0)
        client.open_orders = []

        strategy._process_sells(79_000.0)

        self.assertEqual(len(client.market_sell_calls), 1)
        self.assertEqual(strategy._ledger.open_positions(), [])

    def test_balance_is_queried_once_per_cycle_not_per_position(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        for _ in range(3):
            self._open_position(strategy, client)
        client.base_balance = (1.0, 0.0)

        strategy._process_sells(79_000.0)

        self.assertEqual(len(client.market_sell_calls), 3)
        self.assertEqual(client.balance_calls, 1)

    def test_second_sell_in_the_same_cycle_accounts_for_the_first(self):
        """
        Der Snapshot stammt vom Zyklusanfang. Ohne Mitfuehren der bereits
        verkauften Menge haette die Pruefung dasselbe freie Guthaben fuer
        jeden Verkauf erneut fuer verfuegbar gehalten - und genau den Fall
        uebersehen, fuer den sie gebaut ist.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        self._open_position(strategy, client, quantity=0.0002)
        self._open_position(strategy, client, quantity=0.0002)
        # Reicht fuer genau einen der beiden Verkaeufe.
        client.base_balance = (0.00025, 0.0)

        strategy._process_sells(79_000.0)

        self.assertEqual(len(client.market_sell_calls), 1)
        self.assertEqual(len(strategy._ledger.open_positions()), 1)

    def test_unavailable_balance_does_not_block_the_sell(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        self._open_position(strategy, client)
        client.base_balance = None

        strategy._process_sells(79_000.0)

        self.assertEqual(len(client.market_sell_calls), 1)

    def test_dry_run_does_not_query_the_account_at_all(self):
        """Im Dry-Run existieren die Positionen an der Boerse nicht - ein
        Abgleich gegen echte Bestaende haette dort keine Bedeutung."""
        strategy, client = self._make_strategy(trading_enabled=False, price=79_000.0)
        self._open_position(strategy, client)

        strategy._process_sells(79_000.0)

        self.assertEqual(client.balance_calls, 0)
        self.assertEqual(client.open_orders_calls, 0)

    def test_ledger_mismatch_warns_but_lets_a_covered_sell_through(self):
        """
        Die weiche Pruefung blockiert bewusst nichts: ein gedeckter
        Verkauf reduziert Risiko und Kapitalbindung. Gleiche Abwaegung wie
        beim Trendbruch-Stop-Loss, der Verkaeufe ebenfalls durchlaesst.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        self._open_position(strategy, client, quantity=0.0002)
        # Ledger behauptet 0.0002, auf dem Konto ist weniger - aber die
        # zu verkaufende Menge selbst ist gedeckt.
        client.base_balance = (0.00005, 0.0)
        self._open_position(strategy, client, quantity=0.00002)
        client.base_balance = (0.00003, 0.0)

        sent: list[str] = []
        with mock.patch("dca_bot.grid_strategy.send_notification", sent.append):
            strategy._process_sells(79_000.0)

        self.assertTrue(any("BESTAND-DISKREPANZ" in m for m in sent))
        # Die kleine, gedeckte Position wurde trotzdem verkauft.
        self.assertEqual(len(client.market_sell_calls), 1)

    def test_mismatch_notification_is_sent_only_once_per_process(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=79_000.0)
        self._open_position(strategy, client, quantity=0.0002)
        client.base_balance = (0.00001, 0.0)

        sent: list[str] = []
        with mock.patch("dca_bot.grid_strategy.send_notification", sent.append):
            strategy._process_sells(79_000.0)
            strategy._process_sells(79_000.0)
            strategy._process_sells(79_000.0)

        self.assertEqual(sum("BESTAND-DISKREPANZ" in m for m in sent), 1)


class TrendBalanceGuardTestCase(TrendStrategyTestBase):
    """Der Check im Trend-Verkaufspfad - mit dem heiklen Detail."""

    def test_uncovered_sell_is_not_attempted(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        client.base_balance = (0.0, 0.0)
        client.open_orders = [_sell_order("grid-other", 1.0)]

        strategy._close_position(open_trade, price=52_000.0, reason="signal")

        self.assertEqual(client.market_sell_calls, [])
        self.assertIsNotNone(strategy._ledger.open_position())

    def test_aborted_sell_restores_the_exchange_stop_order(self):
        """
        Das eigentlich Heikle an dieser Stelle: Zum Zeitpunkt der
        Deckungspruefung ist die exchange-seitige Stop-Order bereits
        storniert (_resolve_stop_order_before_close lief davor). Ein
        einfaches `return` wuerde die weiterhin offene Position
        ungeschuetzt zuruecklassen - exakt der K1-Folgefund.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        first_stop_id = open_trade["stop_loss_order_id"]
        client.base_balance = (0.0, 0.0)

        strategy._close_position(open_trade, price=52_000.0, reason="stop_loss")

        still_open = strategy._ledger.open_position()
        self.assertIsNotNone(still_open)
        new_stop_id = still_open["stop_loss_order_id"]
        self.assertIsNotNone(new_stop_id)
        self.assertNotEqual(new_stop_id, first_stop_id)
        self.assertEqual(client.orders[new_stop_id]["status"], "NEW")

    def test_aborted_sell_does_not_latch_the_stop_loss(self):
        """Es hat kein Ausstieg stattgefunden - also auch kein Latch und
        kein erfundener Erloes."""
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        client.base_balance = (0.0, 0.0)

        strategy._close_position(open_trade, price=45_000.0, reason="stop_loss")

        self.assertFalse(strategy._stop_loss.is_paused())

    def test_balance_is_checked_after_cancelling_the_own_stop_order(self):
        """
        Reihenfolge-Test: Vor dem Stornieren bindet die eigene Stop-Order
        die komplette Positionsmenge. Liefe die Pruefung davor, waere das
        freie Guthaben systematisch zu klein und JEDER Ausstieg wuerde
        faelschlich als ungedeckt abgelehnt.
        """
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        client.call_log.clear()

        strategy._close_position(open_trade, price=52_000.0, reason="signal")

        self.assertLess(
            client.call_log.index("cancel_order"),
            client.call_log.index("get_asset_balance"),
        )
        self.assertLess(
            client.call_log.index("get_asset_balance"),
            client.call_log.index("place_market_sell"),
        )

    def test_unavailable_balance_does_not_block_a_stop_loss_exit(self):
        strategy, client = self._make_strategy(trading_enabled=True, price=50_000.0)
        strategy._open_position(50_000.0)
        open_trade = strategy._ledger.open_position()
        client.base_balance = None

        strategy._close_position(open_trade, price=45_000.0, reason="stop_loss")

        self.assertEqual(len(client.market_sell_calls), 1)
        self.assertIsNone(strategy._ledger.open_position())


# --------------------------------------------------------------------------
# W9 - Allocator-Feed-Takt
# --------------------------------------------------------------------------


class _FrozenDatetime(datetime):
    """Ersetzt datetime in allocator.py, damit "heute" steuerbar ist."""

    current = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):  # noqa: D102 - Signatur wie datetime.now
        return cls.current


class AllocatorFeedCadenceTestCase(unittest.TestCase):
    """
    Der Kern von W9: Der TrendSignalGenerator ist ereignisgesteuert - jeder
    feed() rueckt die EMAs um EINE Periode vor. Vor diesem Fix speiste der
    Allocator bei jedem 60-Minuten-Zyklus einen Spot-Ticker ein, also 24
    Werte pro Tag in eine auf 20/50 TAGE ausgelegte Berechnung. Das
    Ergebnis war faktisch eine EMA(20h)/EMA(50h) - ein anderer Indikator
    als der backgetestete.
    """

    FLAT_UNTIL = date(2026, 9, 15)

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self._tmpdir.name) / "allocator_state.json"
        self.config = AllocatorConfig(
            api_key="k",
            api_secret="s",
            smoothing_period=3,
            interval_minutes=60,
            state_file=str(self.state_path),
        )
        self.fetch_windows: list[tuple[str, str]] = []
        _FrozenDatetime.current = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _price(self, day: date) -> float:
        if day <= self.FLAT_UNTIL:
            return 70_000.0
        # Steiler Anstieg nach dem flachen Vorlauf, damit sich die
        # Zuteilung ueberhaupt bewegt.
        return 70_000.0 * (1.03 ** ((day - self.FLAT_UNTIL).days * 8))

    def _fetch(self, symbol, interval, start, end):
        self.fetch_windows.append((start, end))
        out, day = [], date.fromisoformat(start)
        last = date.fromisoformat(end)
        while day <= last:
            stamp = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            out.append(
                {
                    "open_time": int(stamp.timestamp() * 1000),
                    "close_price": self._price(day),
                    "low_price": 0.0,
                }
            )
            day += timedelta(days=1)
        return out

    def _run(self, when: datetime) -> dict:
        _FrozenDatetime.current = when
        with mock.patch.object(allocator_module, "fetch_historical_klines", self._fetch), \
             mock.patch.object(allocator_module, "datetime", _FrozenDatetime), \
             mock.patch.object(allocator_module, "send_notification", lambda m: None):
            self.allocator.execute_once()
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _make(self) -> None:
        with mock.patch.object(allocator_module, "datetime", _FrozenDatetime):
            self.allocator = Allocator(self.config)

    def test_allocation_does_not_move_between_two_cycles_of_the_same_day(self):
        """Negativkontrolle: Vor dem Fix bewegte sich hier jeder Zyklus."""
        self._make()
        first = self._run(datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc))
        for hour in (9, 10, 11, 12, 13):
            later = self._run(datetime(2026, 9, 16, hour, 0, tzinfo=timezone.utc))
            self.assertEqual(later["trend_fraction"], first["trend_fraction"])
            self.assertEqual(later["gap_pct"], first["gap_pct"])

    def test_timestamp_is_refreshed_even_without_a_new_day(self):
        """
        Der Zweck des 60-Minuten-Takts: Die Frische-Pruefung aus W10
        beantwortet "lebt der Allocator noch?" ausschliesslich ueber das
        Alter dieser Datei. Bliebe der Zeitstempel zwischen zwei Tagen
        stehen, saehe ein gesunder Allocator nach drei Stunden aus wie
        ein toter.
        """
        self._make()
        first = self._run(datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc))
        later = self._run(datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc))
        self.assertNotEqual(later["updated_at"], first["updated_at"])
        self.assertGreater(
            datetime.fromisoformat(later["updated_at"]),
            datetime.fromisoformat(first["updated_at"]),
        )

    def test_stale_threshold_stays_at_three_hours(self):
        """
        Die Alternative (ALLOCATOR_INTERVAL_MINUTES=1440) haette aus der
        W10-Schwelle ein Drei-Tage-Fenster gemacht, weil sie sich aus
        genau diesem Wert ableitet. Das hier haelt fest, dass der
        geschriebene Wert weiterhin der Zyklus-Takt ist.
        """
        self._make()
        state = self._run(datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(state["interval_minutes"], 60)

    def test_exactly_one_smoothing_step_per_completed_day(self):
        self._make()
        state = self._run(datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc))
        previous = state["trend_fraction"]

        for day in (17, 18, 19):
            state = self._run(datetime(2026, 9, day, 0, 30, tzinfo=timezone.utc))
            expected = previous + (state["raw_target_fraction"] - previous) * (
                2 / (self.config.smoothing_period + 1)
            )
            self.assertAlmostEqual(state["trend_fraction"], expected, places=12)
            previous = state["trend_fraction"]
            # Ein Zwischenzyklus am selben Tag darf nichts veraendern.
            same_day = self._run(datetime(2026, 9, day, 6, 0, tzinfo=timezone.utc))
            self.assertEqual(same_day["trend_fraction"], previous)

    def test_downtime_replays_each_missed_day_separately(self):
        """
        Eine EMA ueber n Tage ist etwas anderes als eine EMA ueber deren
        Mittelwert - und der Backtest kennt nur den tageweisen Verlauf.
        """
        self._make()
        self._run(datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc))
        after_gap = self._run(datetime(2026, 9, 21, 6, 0, tzinfo=timezone.utc))
        self.assertEqual(after_gap["last_fed_day"], "2026-09-20")

        # Gegenprobe: dieselben Tage einzeln durchlaufen ergibt denselben
        # Wert - der Nachholpfad ist kein Sonderweg.
        self.setUp()
        self._make()
        self._run(datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc))
        for day in (17, 18, 19, 20, 21):
            stepwise = self._run(datetime(2026, 9, day, 6, 0, tzinfo=timezone.utc))
        self.assertAlmostEqual(
            after_gap["trend_fraction"], stepwise["trend_fraction"], places=12
        )

    def test_no_kline_request_without_a_new_day(self):
        """Der 60-Minuten-Takt kostet keine API-Aufrufe - die Pruefung
        "gibt es einen neuen Tag?" ist ein reiner Datumsvergleich."""
        self._make()
        self._run(datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc))
        after_seed = len(self.fetch_windows)
        for hour in (9, 10, 11):
            self._run(datetime(2026, 9, 16, hour, 0, tzinfo=timezone.utc))
        self.assertEqual(len(self.fetch_windows), after_seed)

    def test_last_fed_day_is_written_for_traceability(self):
        """
        `updated_at` beantwortet seit der Entkopplung nicht mehr, bis zu
        welchem Tagesschlusskurs gerechnet wurde - deshalb steht das
        jetzt eigens in der Datei.
        """
        self._make()
        state = self._run(datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(state["last_fed_day"], "2026-09-15")

    def test_candle_day_reads_binance_millisecond_timestamps(self):
        stamp = int(datetime(2026, 9, 15, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(
            Allocator._candle_day({"open_time": stamp}), date(2026, 9, 15)
        )

    def test_unreadable_candle_timestamp_is_skipped_not_guessed(self):
        """Ein falsch datierter Feed wuerde die EMAs dauerhaft
        verschieben, und zwar unbemerkt."""
        self.assertIsNone(Allocator._candle_day({"open_time": "nicht-datum"}))
        self.assertIsNone(Allocator._candle_day({}))


class CurrentStateTestCase(unittest.TestCase):
    """
    `current_state()` ist die Voraussetzung dafuer, dass der Allocator in
    jedem Zyklus schreiben kann, ohne einen Kurs einzuspeisen.
    """

    def test_matches_the_last_feed_result(self):
        gen = TrendSignalGenerator(3, 5, 0.0)
        last = {}
        for price in (100, 101, 102, 103, 104, 105, 106):
            last = gen.feed(float(price))
        self.assertEqual(gen.current_state(), last)

    def test_repeated_calls_do_not_advance_the_emas(self):
        """Negativkontrolle gegen genau den W9-Fehler."""
        gen = TrendSignalGenerator(3, 5, 0.0)
        for price in (100, 101, 102, 103, 104, 105):
            gen.feed(float(price))
        first = gen.current_state()
        for _ in range(10):
            gen.current_state()
        self.assertEqual(gen.current_state(), first)

    def test_returns_empty_state_before_enough_history(self):
        gen = TrendSignalGenerator(3, 5, 0.0)
        gen.feed(100.0)
        state = gen.current_state()
        self.assertIsNone(state["ema_slow"])
        self.assertIsNone(state["gap_pct"])
        self.assertIsNone(state["confirmed_direction"])


if __name__ == "__main__":
    unittest.main()

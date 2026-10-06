"""
Tests fuer close_dry_run_trend.py - kontrolliertes Schliessen der
Dry-Run-Trend-Position im Ledger (07.10.2026).

Geprueft wird vor allem, was NICHT passieren darf: Schreiben im Bericht,
Schreiben bei jeder Weigerung, Anfassen einer echten Position, Setzen der
Stop-Loss-Sperre, Schreiben neben einem laufenden Bot. Jede Weigerung wird
ueber ihren Code (`[code]` in der Ausgabe) geprueft, damit eine Mutation
an genau dieser Pruefung den Test rot macht - auch wenn eine andere
Pruefung denselben Fall zufaellig mit abfaengt.

Ausfuehren mit:  python -m unittest tests.test_close_dry_run_trend -v
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dca_bot import close_dry_run_trend as tool
from dca_bot.process_lock import ProcessLock
from dca_bot.trend_config import TrendConfig
from dca_bot.trend_strategy import TrendFollowingStrategy

from tests.test_trend_stop_loss import FakeTradingClient

TRADE_ID = "c0e153c1-0000-4000-8000-000000000000"
ENTRY_PRICE = 76960.01
EXIT_PRICE = 86000.0

# Nachbildung der Homeserver-Position vom 15.09.2026: vor K2 (keine
# clientOrderId), vor K-B (kein exit_client_order_id), vor der
# Symbolbindung (kein symbol), vor K3 (Menge unquantisiert).
DRY_RUN_POSITION = {
    "id": TRADE_ID,
    "entry_price": ENTRY_PRICE,
    "entry_time": "2026-09-15T08:00:00+00:00",
    "quantity": 15.0 / ENTRY_PRICE,
    "quote_spent": 15.0,
    "dry_run": True,
    "client_order_id": None,
    "stop_loss_order_id": None,
    "stop_limit_price": None,
    "uncertain_cycles": 0,
    "unprotected_cycles": 0,
    "status": "open",
    "exit_price": None,
    "exit_time": None,
    "exit_reason": None,
    "realized_pnl": None,
}

REAL_CLOSED = {
    "id": "real-closed-1",
    "entry_price": 60000.0,
    "entry_time": "2026-09-01T08:00:00+00:00",
    "quantity": 0.00025,
    "quote_spent": 15.0,
    "dry_run": False,
    "client_order_id": "trend-buy-1",
    "stop_loss_order_id": None,
    "stop_limit_price": 53730.0,
    "status": "closed",
    "exit_price": 66000.0,
    "exit_time": "2026-09-05T08:00:00+00:00",
    "exit_reason": "signal",
    "realized_pnl": 1.5,
    "exit_client_order_id": "trend-sell-1",
}


class CloseToolTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.ledger = self.dir / "trend_ledger.json"
        self.pending = self.dir / "pending_orders_trend.json"
        self.latch = self.dir / "trend_stop_loss_paused.json"
        self.lock = self.dir / "trend_bot.lock"
        env = {
            "TREND_SYMBOL": "BTCUSDT",
            "TREND_STATE_FILE": str(self.ledger),
            "TREND_PENDING_ORDERS_FILE": str(self.pending),
            "TREND_STOP_LOSS_STATE_FILE": str(self.latch),
            "TREND_LOCK_FILE": str(self.lock),
            "TREND_ALLOCATOR_STATE_FILE": "",
            "ALLOCATOR_SYMBOL": "BTCUSDT",
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        dotenv = mock.patch("dca_bot.close_dry_run_trend.load_dotenv")
        dotenv.start()
        self.addCleanup(dotenv.stop)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_ledger(self, records: list[dict]) -> None:
        self.ledger.write_text(json.dumps(records, indent=2), encoding="utf-8")

    def read_ledger(self) -> list[dict]:
        return json.loads(self.ledger.read_text(encoding="utf-8"))

    def run_tool(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = tool.main(list(argv))
        return code, out.getvalue()

    def apply(self, trade_id: str = TRADE_ID, price: float = EXIT_PRICE) -> tuple[int, str]:
        return self.run_tool("--apply", "--trade-id", trade_id, "--exit-price", str(price))

    def snapshot(self) -> tuple[bytes, int, list[str]]:
        stat = self.ledger.stat()
        return self.ledger.read_bytes(), stat.st_mtime_ns, sorted(os.listdir(self.dir))


class NormalCaseTestCase(CloseToolTestBase):
    def test_apply_closes_the_dry_run_position(self):
        self.write_ledger([copy.deepcopy(DRY_RUN_POSITION)])
        original = self.ledger.read_bytes()

        code, out = self.apply()

        self.assertEqual(code, tool.EXIT_OK, out)
        [record] = self.read_ledger()
        self.assertEqual(record["status"], "closed")
        self.assertEqual(record["exit_reason"], "manual_close")
        self.assertEqual(record["exit_price"], EXIT_PRICE)
        self.assertIsNotNone(record["exit_time"])
        self.assertIsNone(record["exit_client_order_id"])
        self.assertAlmostEqual(
            record["realized_pnl"], DRY_RUN_POSITION["quantity"] * EXIT_PRICE - 15.0
        )
        # Alles andere unveraendert, dry_run bleibt true.
        for key, value in DRY_RUN_POSITION.items():
            if key not in ("status", "exit_price", "exit_time", "exit_reason", "realized_pnl"):
                self.assertEqual(record[key], value, key)

        backups = list(self.dir.glob("trend_ledger.json.pre-close-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertFalse((self.dir / "trend_ledger.json.tmp").exists())

    def test_other_records_stay_identical(self):
        self.write_ledger([copy.deepcopy(REAL_CLOSED), copy.deepcopy(DRY_RUN_POSITION)])

        code, out = self.apply()

        self.assertEqual(code, tool.EXIT_OK, out)
        real, closed = self.read_ledger()
        self.assertEqual(real, REAL_CLOSED)
        self.assertEqual(closed["exit_reason"], "manual_close")

    def test_stop_loss_latch_is_not_set(self):
        self.write_ledger([copy.deepcopy(DRY_RUN_POSITION)])

        code, out = self.apply()

        self.assertEqual(code, tool.EXIT_OK, out)
        self.assertFalse(self.latch.exists(), "Die Stop-Loss-Sperre darf nicht entstehen.")
        self.assertNotEqual(self.read_ledger()[0]["exit_reason"], "stop_loss")

    def test_second_apply_is_a_no_op(self):
        self.write_ledger([copy.deepcopy(DRY_RUN_POSITION)])
        self.assertEqual(self.apply()[0], tool.EXIT_OK)
        before = self.snapshot()

        code, out = self.apply()

        self.assertEqual(code, tool.EXIT_OK, out)
        self.assertIn("Bereits mit manual_close geschlossen", out)
        self.assertEqual(self.snapshot()[:2], before[:2])
        self.assertEqual(len(list(self.dir.glob("trend_ledger.json.pre-close-*"))), 1)


class VerificationTestCase(CloseToolTestBase):
    def test_unexpected_change_is_reported(self):
        # Simuliert einen Schreibweg, der mehr aendert als den einen Eintrag.
        self.write_ledger([copy.deepcopy(REAL_CLOSED), copy.deepcopy(DRY_RUN_POSITION)])
        original_record_exit = tool.TrendLedger.record_exit

        def record_exit_and_more(ledger, *args, **kwargs):
            original_record_exit(ledger, *args, **kwargs)
            records = json.loads(self.ledger.read_text(encoding="utf-8"))
            records[0]["realized_pnl"] = 999.0
            self.write_ledger(records)

        with mock.patch.object(tool.TrendLedger, "record_exit", record_exit_and_more):
            code, out = self.apply()

        self.assertEqual(code, tool.EXIT_VERIFY_FAILED, out)
        self.assertIn("real-closed-1", out)


class ReportTestCase(CloseToolTestBase):
    def test_report_writes_nothing(self):
        self.write_ledger([copy.deepcopy(DRY_RUN_POSITION)])
        before = self.snapshot()

        code, out = self.run_tool("--exit-price", str(EXIT_PRICE))

        self.assertEqual(code, tool.EXIT_OK, out)
        self.assertEqual(self.snapshot(), before)
        # Auch kein Lock: das schriebe die PID in die Lock-Datei.
        self.assertFalse(self.lock.exists())
        self.assertFalse(self.latch.exists())
        self.assertIn("simulierte realized_pnl", out)

    def test_report_with_trade_id_also_writes_nothing(self):
        self.write_ledger([copy.deepcopy(DRY_RUN_POSITION)])
        before = self.snapshot()

        code, out = self.run_tool("--trade-id", TRADE_ID, "--exit-price", str(EXIT_PRICE))

        self.assertEqual(code, tool.EXIT_OK, out)
        self.assertEqual(self.snapshot(), before)

    def test_report_shows_refusals_with_exit_code(self):
        record = copy.deepcopy(DRY_RUN_POSITION)
        record["dry_run"] = False
        self.write_ledger([record])

        code, out = self.run_tool()

        self.assertEqual(code, tool.EXIT_REFUSED)
        self.assertIn("[not_dry_run]", out)

    def test_big_price_deviation_only_warns(self):
        self.write_ledger([copy.deepcopy(DRY_RUN_POSITION)])

        code, out = self.run_tool("--exit-price", "8600")

        self.assertEqual(code, tool.EXIT_OK, out)
        self.assertIn("WARNUNG: Ausstiegspreis weicht", out)


class RefusalTestCase(CloseToolTestBase):
    """Jede Weigerung: richtiger Code, Exit-Code 1, nichts geschrieben."""

    def assert_refused(self, code_name: str, *, ledger_exists: bool = True,
                       trade_id: str = TRADE_ID, price: float = EXIT_PRICE) -> str:
        before = self.snapshot() if ledger_exists else None
        code, out = self.apply(trade_id, price)
        self.assertEqual(code, tool.EXIT_REFUSED, out)
        self.assertIn(f"[{code_name}]", out)
        if ledger_exists:
            self.assertEqual(self.snapshot()[:2], before[:2])
        self.assertEqual(list(self.dir.glob("*.pre-close-*")), [])
        self.assertFalse(self.latch.exists() and code_name != "latch_active")
        return out

    def position(self, **changes) -> dict:
        record = copy.deepcopy(DRY_RUN_POSITION)
        record.update(changes)
        return record

    def test_real_position_is_refused(self):
        self.write_ledger([self.position(dry_run=False)])
        self.assert_refused("not_dry_run")

    def test_missing_dry_run_flag_is_refused(self):
        record = self.position()
        del record["dry_run"]
        self.write_ledger([record])
        self.assert_refused("not_dry_run")

    def test_dry_run_flag_must_be_exactly_true(self):
        self.write_ledger([self.position(dry_run="true")])
        self.assert_refused("not_dry_run")

    def test_stop_loss_order_id_is_refused(self):
        self.write_ledger([self.position(stop_loss_order_id="12345")])
        self.assert_refused("exchange_link")

    def test_client_order_id_is_refused(self):
        self.write_ledger([self.position(client_order_id="trend-buy-9")])
        self.assert_refused("exchange_link")

    def test_exit_client_order_id_is_refused(self):
        self.write_ledger([self.position(exit_client_order_id="trend-sell-9")])
        self.assert_refused("exchange_link")

    def test_partial_fill_is_refused(self):
        self.write_ledger([self.position(partial_exit_qty=0.0001, partial_exit_order_ids=["77"])])
        self.assert_refused("exchange_link")

    def test_no_open_position_is_refused(self):
        self.write_ledger([copy.deepcopy(REAL_CLOSED)])
        self.assert_refused("open_count")

    def test_two_open_positions_are_refused(self):
        second = self.position(id="other-open")
        self.write_ledger([self.position(), second])
        self.assert_refused("open_count")

    def test_closed_with_other_reason_is_not_treated_as_done(self):
        self.write_ledger([self.position(status="closed", exit_reason="signal")])
        self.assert_refused("open_count")

    def test_wrong_trade_id_is_refused(self):
        self.write_ledger([self.position()])
        self.assert_refused("trade_id", trade_id="c0e153c1-falsch")

    def test_pending_entries_are_refused(self):
        self.write_ledger([self.position()])
        self.pending.write_text(json.dumps({
            "version": 1, "bot": "trend",
            "orders": [{"client_order_id": "trend-x", "symbol": "BTCUSDT", "side": "BUY"}],
        }), encoding="utf-8")
        self.assert_refused("pending_entries")

    def test_unreadable_pending_is_refused(self):
        self.write_ledger([self.position()])
        self.pending.write_text("{kaputt", encoding="utf-8")
        self.assert_refused("pending_unreadable")

    def test_empty_pending_file_is_fine(self):
        self.write_ledger([self.position()])
        self.pending.write_text(json.dumps({"version": 1, "bot": "trend", "orders": []}),
                                encoding="utf-8")
        code, out = self.apply()
        self.assertEqual(code, tool.EXIT_OK, out)

    def test_unreadable_ledger_is_refused(self):
        self.ledger.write_text("[{kaputt", encoding="utf-8")
        self.assert_refused("ledger_unreadable")

    def test_ledger_that_is_no_list_is_refused(self):
        self.ledger.write_text(json.dumps({"id": TRADE_ID}), encoding="utf-8")
        self.assert_refused("ledger_unreadable")

    def test_ledger_with_non_dict_entries_is_refused(self):
        # Ein Text-Eintrag ueberstuende die id/status-Pruefung ("id" in "id status")
        # - nur die Listenpruefung faengt ihn ab.
        self.ledger.write_text(json.dumps(["id status"]), encoding="utf-8")
        self.assert_refused("ledger_unreadable")

    def test_entry_without_id_is_refused(self):
        record = self.position()
        del record["id"]
        self.write_ledger([record])
        self.assert_refused("ledger_unreadable")

    def test_missing_ledger_is_refused_and_not_created(self):
        self.assert_refused("ledger_missing", ledger_exists=False)
        self.assertFalse(self.ledger.exists())

    def test_active_latch_is_refused(self):
        self.write_ledger([self.position()])
        self.latch.write_text(json.dumps({"symbol": "BTCUSDT"}), encoding="utf-8")
        self.assert_refused("latch_active")

    def test_foreign_symbol_in_ledger_is_refused(self):
        self.write_ledger([self.position(symbol="BTCEUR")])
        self.assert_refused("symbol")

    def test_ledger_of_other_pair_than_configured_is_refused(self):
        # Altbestand ohne Feld gilt als BTCUSDT - bei TREND_SYMBOL=BTCEUR passt das nicht.
        self.write_ledger([self.position()])
        with mock.patch.dict(os.environ, {"TREND_SYMBOL": "BTCEUR", "ALLOCATOR_SYMBOL": "BTCEUR"}):
            self.assert_refused("symbol")

    def test_unreadable_allocator_state_is_refused(self):
        self.write_ledger([self.position()])
        allocator = self.dir / "allocator_state.json"
        allocator.write_text("{kaputt", encoding="utf-8")
        with mock.patch.dict(os.environ, {"TREND_ALLOCATOR_STATE_FILE": str(allocator)}):
            self.assert_refused("symbol")

    def test_invalid_exit_price_is_refused(self):
        self.write_ledger([self.position()])
        before = self.snapshot()
        code, out = self.apply(price=0.0)
        self.assertEqual(code, tool.EXIT_REFUSED, out)
        self.assertEqual(self.snapshot()[:2], before[:2])

    def test_apply_without_trade_id_or_price_is_refused(self):
        self.write_ledger([self.position()])
        before = self.snapshot()
        for argv in (("--apply", "--exit-price", "86000"), ("--apply", "--trade-id", TRADE_ID)):
            code, out = self.run_tool(*argv)
            self.assertEqual(code, tool.EXIT_REFUSED, out)
        self.assertEqual(self.snapshot()[:2], before[:2])


class RealPositionNeverTouchedTestCase(CloseToolTestBase):
    """Eine echte Position - offen oder geschlossen - bleibt in jedem Fall unveraendert."""

    def test_real_open_position_with_stop_order_is_untouched(self):
        real_open = copy.deepcopy(REAL_CLOSED)
        real_open.update(id=TRADE_ID, status="open", exit_price=None, exit_time=None,
                         exit_reason=None, realized_pnl=None, exit_client_order_id=None,
                         stop_loss_order_id="555")
        self.write_ledger([real_open])
        before = self.ledger.read_bytes()

        for argv in ((), ("--apply", "--trade-id", TRADE_ID, "--exit-price", "86000")):
            code, out = self.run_tool(*argv)
            self.assertEqual(code, tool.EXIT_REFUSED, out)

        self.assertEqual(self.ledger.read_bytes(), before)

    def test_dry_run_flag_true_but_exchange_ids_still_refuses(self):
        # Widerspruechlicher Eintrag (manuell editiert?): dry_run true, aber
        # Verweise auf Boersen-Orders. Im Zweifel ist er echt.
        record = copy.deepcopy(DRY_RUN_POSITION)
        record.update(client_order_id="trend-buy-2", stop_loss_order_id="556")
        self.write_ledger([record])
        before = self.ledger.read_bytes()

        code, out = self.apply()

        self.assertEqual(code, tool.EXIT_REFUSED, out)
        self.assertEqual(self.ledger.read_bytes(), before)


class LockTestCase(CloseToolTestBase):
    def test_running_bot_aborts_apply(self):
        self.write_ledger([copy.deepcopy(DRY_RUN_POSITION)])
        before = self.snapshot()
        bot_lock = ProcessLock(str(self.lock), "trend")
        bot_lock.acquire()
        try:
            code, out = self.apply()
        finally:
            bot_lock.release()

        self.assertEqual(code, tool.EXIT_BOT_RUNNING, out)
        self.assertIn("ABGEBROCHEN", out)
        self.assertEqual(self.snapshot()[:2], before[:2])
        self.assertEqual(list(self.dir.glob("*.pre-close-*")), [])

    def test_lock_is_released_after_apply(self):
        self.write_ledger([copy.deepcopy(DRY_RUN_POSITION)])
        # Ausdruecklich pruefen, dass release() laeuft: Ein vergessenes
        # release() fiele sonst nicht auf, weil CPython das Datei-Handle beim
        # Aufraeumen ohnehin schliesst.
        with mock.patch.object(tool.ProcessLock, "release", autospec=True,
                               side_effect=ProcessLock.release) as release:
            self.assertEqual(self.apply()[0], tool.EXIT_OK)
        release.assert_called_once()
        # Der Bot muss danach starten koennen.
        lock = ProcessLock(str(self.lock), "trend")
        lock.acquire()
        lock.release()

    def test_lock_is_released_after_refusal(self):
        self.write_ledger([dict(DRY_RUN_POSITION, dry_run=False)])
        with mock.patch.object(tool.ProcessLock, "release", autospec=True,
                               side_effect=ProcessLock.release) as release:
            self.assertEqual(self.apply()[0], tool.EXIT_REFUSED)
        release.assert_called_once()


class EndToEndTestCase(CloseToolTestBase):
    """Der eigentliche Zweck: Nach dem Schliessen steigt der Bot bei "up" echt ein."""

    def make_strategy(self) -> tuple[TrendFollowingStrategy, FakeTradingClient]:
        config = TrendConfig(
            api_key="test",
            api_secret="test",
            symbol="BTCUSDT",
            stop_loss_pct=10.0,
            stop_limit_offset_pct=0.5,
            trading_enabled=True,
            kill_switch_file=str(self.dir / "STOP_TREND_TEST_UNUSED"),
            state_file=str(self.ledger),
            stop_loss_state_file=str(self.latch),
        )
        client = FakeTradingClient(True, EXIT_PRICE)
        strategy = TrendFollowingStrategy(config, client)
        strategy._seeded = True
        strategy._signal_gen.feed = lambda price: {"confirmed_direction": "up"}
        return strategy, client

    def test_bot_enters_after_close(self):
        self.write_ledger([copy.deepcopy(DRY_RUN_POSITION)])

        # Vorher: der Slot ist belegt, "up" fuehrt zu keinem Kauf.
        strategy, client = self.make_strategy()
        with mock.patch("dca_bot.trend_strategy.send_notification"):
            strategy.execute_once()
        self.assertEqual(client.market_buy_calls, [])

        self.assertEqual(self.apply()[0], tool.EXIT_OK)

        strategy, client = self.make_strategy()
        with mock.patch("dca_bot.trend_strategy.send_notification"):
            strategy.execute_once()

        self.assertEqual(len(client.market_buy_calls), 1)
        self.assertEqual(len(client.stop_order_calls), 1)
        records = self.read_ledger()
        self.assertEqual(len(records), 2)
        new = records[1]
        self.assertEqual(new["status"], "open")
        self.assertIs(new["dry_run"], False)
        self.assertEqual(new["symbol"], "BTCUSDT")
        self.assertIsNotNone(new["stop_loss_order_id"])


if __name__ == "__main__":
    unittest.main()

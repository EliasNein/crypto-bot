"""
Tests fuer remove_unfilled_grid_positions.py (16.10.2026).

Nachgebildet ist die Lage auf dem Homeserver am 16.10.2026: elf offene,
echte Eintraege ohne Bestand (Stufen 0-3 vom 09.10., 4-10 vom 11.10.2026,
mit den echten IDs aus dem Ledger) und aus derselben Minute am 09.10. die
sieben Kaeufe der Stufen 4-10 MIT Bestand, die laengst verkauft sind.

Geprueft wird vor allem, was NICHT passieren darf: eine Position mit
Bestand anfassen, im Bericht schreiben, bei einer Weigerung schreiben,
neben einem laufenden Bot schreiben. Jede Weigerung wird ueber ihren Code
geprueft (`[code]` in der Ausgabe bzw. am Kandidaten).

Ausfuehren mit:  python -m unittest tests.test_remove_unfilled_grid_positions -v
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

from dca_bot import remove_unfilled_grid_positions as tool
from dca_bot.grid_risk import GridLedger, GridPosition, is_unfilled_position
from dca_bot.process_lock import ProcessLock

# Stufe, bought_at, Ledger-id, client_order_id - Ausgabe (a) vom 16.10.2026.
PHANTOMS = (
    (0, "2026-10-09T05:17:31", "14f6af94-198f-47d0-91d0-33baf809d1d0", "grid-33b3641be36f4e139d6c5fd3"),
    (1, "2026-10-09T05:17:31", "54918462-99c6-46dc-a0c9-10478d687e32", "grid-21918cc10b2c4d7fa859380c"),
    (2, "2026-10-09T05:17:32", "c6564874-7359-4875-b4f2-8909599db89e", "grid-1be308d2e7d14b0791bd1445"),
    (3, "2026-10-09T05:17:33", "f29b06f6-e113-47c8-b03c-8f4a9b0aa756", "grid-4bdc0b39c3aa43088c0e82c2"),
    (4, "2026-10-11T16:01:35", "10418ef5-a18c-4241-adc5-8c9b8cdf3453", "grid-f0f245ee4ac64a08bf933fae"),
    (5, "2026-10-11T16:01:36", "19a4550e-ecc1-45fb-834a-dc7a4cce1787", "grid-752a27dc70224a708070cb37"),
    (6, "2026-10-11T16:01:37", "ed8c55fb-7c27-41f2-a7a8-1b7332014675", "grid-d6a7e35b0665427bbd118d85"),
    (7, "2026-10-11T16:01:38", "7aab14a6-6bf3-48e0-8eeb-34d729fdc684", "grid-5ac7a25d606446e4ba972cf8"),
    (8, "2026-10-11T16:01:39", "13f0fdee-b44c-4c7d-9f3b-17ec6d5ba9b3", "grid-3932c321ec4f4907b6229765"),
    (9, "2026-10-11T16:01:39", "1a5f6c8a-88ee-4466-87f3-dd46b4bd870e", "grid-c67242e66b0d440e8d20d89a"),
    (10, "2026-10-11T16:01:40", "c98bc132-506b-46db-a816-8d9b522a2019", "grid-1fe9e148bbb041e5b74fa824"),
)
PHANTOM_IDS = {p[2] for p in PHANTOMS}

# Ausgabe (b): die Kaeufe der Stufen 4-10 vom 09.10.2026 mit Bestand.
FILLED_0910 = (
    (4, "2026-10-09T05:17:43", 0.00013, 9.3780219),
    (5, "2026-10-09T05:17:44", 0.00014, 9.324),
    (6, "2026-10-09T05:17:55", 0.00011, 9.0690611),
    (7, "2026-10-09T05:17:55", 0.00011, 9.0690611),
    (8, "2026-10-09T05:17:56", 0.00011, 9.0690611),
    (9, "2026-10-09T05:17:56", 0.00011, 9.0690611),
    (10, "2026-10-09T05:17:57", 0.00011, 9.0690611),
)


def _record(level, bought_at, rid, coid, quantity, spent, status="open", **extra):
    record = {
        "id": rid,
        "level_index": level,
        "buy_price": 70192.26,
        "target_sell_price": 71245.14,
        "quantity": quantity,
        "quote_spent": spent,
        "bought_at": bought_at + "+00:00",
        "dry_run": False,
        "client_order_id": coid,
        "status": status,
        "sell_price": None,
        "sold_at": None,
        "realized_pnl": None,
        "sell_client_order_id": None,
        "symbol": "BTCUSDT",
    }
    record.update(extra)
    return record


def server_ledger(filled_status: str = "closed") -> list[dict]:
    records = []
    for i, (level, bought_at, quantity, spent) in enumerate(FILLED_0910):
        sold = {} if filled_status == "open" else {
            "sell_price": 83_000.0, "sold_at": "2026-10-09T06:00:00+00:00",
            "realized_pnl": 0.5, "sell_client_order_id": f"grid-sold-{i}"}
        records.append(_record(level, bought_at, f"filled-{i}", f"grid-filled-{i}",
                               quantity, spent, status=filled_status, **sold))
    for level, bought_at, rid, coid in PHANTOMS:
        records.append(_record(level, bought_at, rid, coid, 0.0, 0.0))
    # Weitere Eintraege, die nie angefasst werden duerfen:
    records.append(_record(12, "2026-10-12T08:00:00", "open-real", "grid-open-real", 0.0002, 15.0))
    records.append(_record(13, "2026-09-10T08:00:00", "dry-zero", None, 0.0, 0.0, dry_run=True))
    records.append(_record(14, "2026-10-01T08:00:00", "closed-zero", "grid-closed-zero", 0.0, 0.0,
                           status="closed"))
    return records


EXPIRED_ZERO = {"status": "EXPIRED", "executedQty": "0.00000000", "side": "BUY",
                "cummulativeQuoteQty": "0.00000000"}


class FakeClient:
    """Nur lesend: get_order_by_client_id() wie der echte TradingClient."""

    def __init__(self):
        self.results: dict[str, tuple[str, dict | None]] = {}
        self.calls: list[tuple[str, str]] = []

    def get_order_by_client_id(self, symbol, client_order_id):
        self.calls.append((symbol, client_order_id))
        return self.results.get(client_order_id, ("found", dict(EXPIRED_ZERO)))


class RemoveToolTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.ledger = self.dir / "grid_positions.json"
        self.pending = self.dir / "pending_orders_grid.json"
        self.lock = self.dir / "grid_bot.lock"
        env = {
            "GRID_SYMBOL": "BTCUSDT",
            "GRID_STATE_FILE": str(self.ledger),
            "GRID_PENDING_ORDERS_FILE": str(self.pending),
            "GRID_STOP_LOSS_STATE_FILE": str(self.dir / "grid_stop_loss_paused.json"),
            "GRID_LOCK_FILE": str(self.lock),
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        dotenv = mock.patch("dca_bot.remove_unfilled_grid_positions.load_dotenv")
        dotenv.start()
        self.addCleanup(dotenv.stop)
        self.client = FakeClient()
        self.write_ledger(server_ledger())

    def write_ledger(self, records) -> None:
        self.ledger.write_text(json.dumps(records, indent=2), encoding="utf-8")

    def read_ledger(self) -> list[dict]:
        return json.loads(self.ledger.read_text(encoding="utf-8"))

    def backups(self) -> list[Path]:
        return sorted(self.dir.glob("grid_positions.json.pre-remove-*"))

    def run_tool(self, *argv: str, client="default") -> tuple[int, str]:
        factory = (lambda: (self.client, None)) if client == "default" else client
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = tool.main(list(argv), client_factory=factory)
        return code, out.getvalue()

    def apply(self, expect: int = 11, **kwargs) -> tuple[int, str]:
        return self.run_tool("--apply", "--expect", str(expect), **kwargs)

    def assert_unchanged(self, before: list[dict]) -> None:
        self.assertEqual(self.read_ledger(), before, "Ledger darf sich nicht veraendern")
        self.assertEqual(self.backups(), [], "keine Sicherungskopie ohne Schreiben")


class FilterTestCase(RemoveToolTestBase):
    def test_filter_matches_exactly_the_eleven_from_the_server(self):
        a = tool.assess(tool.resolve_paths(), self.client)
        self.assertEqual(a.refusals, [])
        self.assertEqual({c.record["id"] for c in a.candidates}, PHANTOM_IDS)
        self.assertEqual(len(a.verified), 11)
        self.assertEqual(
            sorted(cid for _, cid in self.client.calls), sorted(p[3] for p in PHANTOMS),
            "nur die Kandidaten werden an der Boerse nachgeschlagen",
        )
        self.assertTrue(all(sym == "BTCUSDT" for sym, _ in self.client.calls))

    def test_the_seven_filled_entries_from_0910_are_never_candidates_even_if_open(self):
        self.write_ledger(server_ledger(filled_status="open"))
        a = tool.assess(tool.resolve_paths(), self.client)
        self.assertEqual({c.record["id"] for c in a.candidates}, PHANTOM_IDS)


class ReportTestCase(RemoveToolTestBase):
    def test_report_writes_nothing(self):
        before = self.read_ledger()
        code, out = self.run_tool()
        self.assertEqual(code, tool.EXIT_OK)
        self.assertIn("Kandidaten (offen, echt, Menge 0, Einsatz 0): 11", out)
        self.assertIn("--apply --expect 11", out)
        for _, _, rid, coid in PHANTOMS:
            self.assertIn(rid, out)
            self.assertIn(coid, out)
        self.assert_unchanged(before)
        self.assertFalse(self.lock.exists(), "Bericht holt kein Lock")

    def test_nothing_to_do(self):
        self.write_ledger([r for r in server_ledger() if r["id"] not in PHANTOM_IDS])
        code, out = self.run_tool()
        self.assertEqual(code, tool.EXIT_OK)
        self.assertIn("nichts zu tun", out)


class ApplyTestCase(RemoveToolTestBase):
    def test_apply_removes_exactly_the_eleven_and_nothing_else(self):
        before = self.read_ledger()
        code, out = self.apply()
        self.assertEqual(code, tool.EXIT_OK, out)
        self.assertIn("GESCHRIEBEN: 11", out)
        self.assertEqual(self.read_ledger(), [r for r in before if r["id"] not in PHANTOM_IDS])
        [backup] = self.backups()
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), before)

    def test_apply_needs_expect(self):
        before = self.read_ledger()
        for argv in (("--apply",), ("--apply", "--expect", "0")):
            with self.subTest(argv=argv):
                self.client.calls.clear()
                code, out = self.run_tool(*argv)
                self.assertEqual(code, tool.EXIT_REFUSED)
                self.assertIn("braucht --expect", out)
                self.assertEqual(self.client.calls, [], "Weigerung vor Lock und Boersenabfrage")
                self.assertFalse(self.lock.exists(), "kein Lock geholt")
                self.assert_unchanged(before)

    def test_expect_mismatch_refuses(self):
        before = self.read_ledger()
        for expect in (10, 12):
            with self.subTest(expect=expect):
                code, out = self.apply(expect)
                self.assertEqual(code, tool.EXIT_REFUSED)
                self.assertIn("[expect_mismatch]", out)
                self.assert_unchanged(before)

    def test_running_bot_aborts(self):
        before = self.read_ledger()
        lock = ProcessLock(str(self.lock), "grid")
        lock.acquire()
        try:
            code, out = self.apply()
        finally:
            lock.release()
        self.assertEqual(code, tool.EXIT_BOT_RUNNING)
        self.assertIn("ABGEBROCHEN", out)
        self.assert_unchanged(before)

    def test_verify_failure_is_reported(self):
        def broken(ledger_self, ids):
            records = ledger_self._read()
            records[0]["realized_pnl"] = 99.0  # fremder Eintrag veraendert
            ledger_self._write([r for r in records if r["id"] not in ids])
            return len(ids)

        with mock.patch("dca_bot.remove_unfilled_grid_positions.GridLedger.remove_unfilled_positions",
                        broken):
            code, out = self.apply()
        self.assertEqual(code, tool.EXIT_VERIFY_FAILED)
        self.assertIn("Kontrolle", out)
        self.assertEqual(len(self.backups()), 1)

    def test_apply_rechecks_under_the_lock(self):
        """Die Boerse wird unter dem Lock erneut gefragt - nicht dem Bericht vertraut."""
        self.client.results["grid-1fe9e148bbb041e5b74fa824"] = ("failed", None)
        before = self.read_ledger()
        code, out = self.apply(11)
        self.assertEqual(code, tool.EXIT_REFUSED)
        self.assert_unchanged(before)


class GlobalRefusalTestCase(RemoveToolTestBase):
    def assert_refused(self, code_name: str, client="default") -> None:
        before = self.read_ledger() if self.ledger.exists() else None
        for argv in ((), ("--apply", "--expect", "11")):
            with self.subTest(code=code_name, argv=argv):
                code, out = self.run_tool(*argv, client=client)
                self.assertEqual(code, tool.EXIT_REFUSED, out)
                self.assertIn(f"[{code_name}]", out)
                if before is not None:
                    self.assert_unchanged(before)

    def test_ledger_missing(self):
        self.ledger.unlink()
        self.assert_refused("ledger_missing")

    def test_ledger_unreadable(self):
        for content in ("{kaputt", json.dumps({"a": 1}), json.dumps([{"status": "open"}])):
            with self.subTest(content=content):
                self.ledger.write_text(content, encoding="utf-8")
                code, out = self.run_tool()
                self.assertEqual(code, tool.EXIT_REFUSED)
                self.assertIn("[ledger_unreadable]", out)

    def test_pending_entries(self):
        self.pending.write_text(json.dumps({"version": 1, "bot": "grid", "orders": [
            {"client_order_id": "grid-offen"}]}), encoding="utf-8")
        self.assert_refused("pending_entries")

    def test_pending_unreadable(self):
        self.pending.write_text("{kaputt", encoding="utf-8")
        self.assert_refused("pending_unreadable")

    def test_symbol_mismatch(self):
        with mock.patch.dict(os.environ, {"GRID_SYMBOL": "BTCEUR"}):
            self.assert_refused("symbol")

    def test_half_empty_entry(self):
        for change in ({"quantity": 0.0, "quote_spent": 9.32}, {"quantity": 0.00013, "quote_spent": 0.0}):
            with self.subTest(change=change):
                records = server_ledger()
                records[-3].update(change)  # "open-real"
                self.write_ledger(records)
                self.assert_refused("half_empty")

    def test_values_that_are_not_numbers(self):
        records = server_ledger()
        records[-3].update({"quantity": "0", "quote_spent": "0"})
        self.write_ledger(records)
        self.assert_refused("unusable")

    def test_no_client(self):
        self.assert_refused("no_client", client=lambda: (None, "keine Zugangsdaten"))


class PerEntryRefusalTestCase(RemoveToolTestBase):
    """Ein einzelner Kandidat wird verweigert und bleibt - die uebrigen nicht."""

    TARGET = PHANTOMS[10]

    def _check(self, code_name: str, *, result=None, change=None) -> None:
        records = server_ledger()
        if change:
            next(r for r in records if r["id"] == self.TARGET[2]).update(change)
        self.write_ledger(records)
        if result is not None:
            self.client.results[self.TARGET[3]] = result

        a = tool.assess(tool.resolve_paths(), self.client)
        [refused] = [c for c in a.candidates if not c.verified]
        self.assertEqual(refused.record["id"], self.TARGET[2])
        self.assertEqual(refused.refusal[0], code_name)

        before = self.read_ledger()
        code, out = self.apply(11)
        self.assertEqual(code, tool.EXIT_REFUSED, "11 erwartet, nur 10 belegt")
        self.assert_unchanged(before)

        code, out = self.apply(10)
        self.assertEqual(code, tool.EXIT_OK, out)
        remaining = {r["id"] for r in self.read_ledger()}
        self.assertIn(self.TARGET[2], remaining, "verweigerter Eintrag bleibt")
        self.assertEqual(remaining & PHANTOM_IDS, {self.TARGET[2]})
        self.assertIn("Verweigert und im Ledger geblieben: 1", out)

    def test_not_found(self):
        self._check("not_found", result=("not_found", None))

    def test_lookup_failed(self):
        self._check("lookup_failed", result=("failed", None))

    def test_still_live(self):
        self._check("live", result=("found", {"status": "NEW", "executedQty": "0", "side": "BUY"}))

    def test_executed_at_the_exchange(self):
        for status in ("EXPIRED", "FILLED"):
            with self.subTest(status=status):
                self.setUp()
                self._check("filled", result=("found", {"status": status, "executedQty": "0.00013",
                                                        "side": "BUY"}))

    def test_unreadable_status(self):
        self._check("unreadable", result=("found", {"status": "WEIRD", "executedQty": "0", "side": "BUY"}))

    def test_wrong_side(self):
        self._check("side", result=("found", {**EXPIRED_ZERO, "side": "SELL"}))

    def test_without_client_order_id(self):
        self._check("no_client_order_id", change={"client_order_id": None})

    def test_foreign_symbol(self):
        # Ein einzelner Eintrag mit fremdem Symbol: symbol_guard meldet dann
        # das Ledger als gemischt - das ist bereits eine Weigerung insgesamt.
        records = server_ledger()
        next(r for r in records if r["id"] == self.TARGET[2])["symbol"] = "BTCEUR"
        self.write_ledger(records)
        c = tool.Candidate(next(r for r in records if r["id"] == self.TARGET[2]))
        tool._pre_check(c, "BTCUSDT")
        self.assertEqual(c.refusal[0], "foreign_symbol")
        code, out = self.run_tool()
        self.assertEqual(code, tool.EXIT_REFUSED)
        self.assertIn("[symbol]", out)

    def test_sell_fields_set(self):
        self._check("sell_field", change={"sold_at": "2026-10-12T00:00:00+00:00"})

    def test_partial_or_dust_booked(self):
        for change in ({"partial_exit_qty": 0.0001}, {"dust_qty": 0.00001}):
            with self.subTest(change=change):
                self.setUp()
                self._check("partial", change=change)


class LedgerHelpersTestCase(unittest.TestCase):
    """Filter und Entfernen auf Ledger-Ebene (grid_risk) - die Grundlage des Werkzeugs."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    @staticmethod
    def _grid(quantity=0.0002, quote_spent=15.0, dry_run=False):
        return GridPosition.new(level_index=3, buy_price=75_000.0, target_sell_price=76_125.0,
                                quantity=quantity, quote_spent=quote_spent, dry_run=dry_run,
                                client_order_id="grid-a", symbol="BTCUSDT")

    def test_is_unfilled_position(self):
        base = {"status": "open", "dry_run": False, "quantity": 0.0, "quote_spent": 0.0}
        self.assertTrue(is_unfilled_position(base))
        for change in (
            {"status": "closed"}, {"dry_run": True}, {"dry_run": None},
            {"quantity": 0.00013}, {"quote_spent": 9.32}, {"quantity": "0"},
            {"quote_spent": "0"}, {"quantity": False}, {"quantity": None},
            {"quantity": -0.0001}, {"quote_spent": -1.0},
        ):
            with self.subTest(change=change):
                self.assertFalse(is_unfilled_position({**base, **change}))

    def test_remove_unfilled_positions_refuses_anything_else(self):
        ledger = GridLedger(str(self.dir / "g.json"))
        phantom = self._grid().__dict__ | {"id": "phantom", "quantity": 0.0, "quote_spent": 0.0}
        real = self._grid().__dict__ | {"id": "real"}
        closed = phantom | {"id": "closed", "status": "closed"}
        dry = phantom | {"id": "dry", "dry_run": True}
        ledger._write([phantom, real, closed, dry])
        before = ledger._read()
        for bad in ("real", "closed", "dry", "missing"):
            with self.subTest(id=bad):
                with self.assertRaises(ValueError):
                    ledger.remove_unfilled_positions({"phantom", bad})
                self.assertEqual(ledger._read(), before, "nichts entfernt")
        self.assertEqual(ledger.remove_unfilled_positions({"phantom"}), 1)
        self.assertEqual([r["id"] for r in ledger._read()], ["real", "closed", "dry"])


if __name__ == "__main__":
    unittest.main()

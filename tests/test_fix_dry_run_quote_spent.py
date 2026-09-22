"""
Tests für das einmalige Korrektur-Skript
`dca_bot/fix_dry_run_quote_spent.py` (Fund vom 22.09.2026, siehe
trading-bot-projekt.md Abschnitt 6g).

Warum ein reines Korrektur-Werkzeug Tests bekommt: Es schreibt Historie
um, die sich aus nichts anderem rekonstruieren lässt. Anders als beim
Live-Code fällt ein Fehler hier durch nichts auf - es gibt keinen
nächsten Zyklus, der ihn sichtbar machen würde. Dieselbe Begründung wie
bei den Tests für den Analyse-Modus des Trend-Backtests (6i).

Geprüft werden vor allem die drei Zusicherungen, an denen das Skript
gefährlich wäre, wenn sie nicht stimmen:

1. Echte Einträge (`dry_run: false`) werden NIE angefasst - dort ist
   `quote_spent` die Ground Truth der Börse. Mit Gegenprobe, dass ein
   Dry-Run-Eintrag direkt daneben sehr wohl korrigiert wird: sonst wäre
   "echte Einträge unverändert" auch grün, wenn das Skript gar nichts
   tut.
2. Ohne `--apply` wird nachweislich nichts geschrieben.
3. Idempotenz - ein zweiter Lauf ändert nichts mehr.

Ausführen mit:  python -m unittest tests.test_fix_dry_run_quote_spent -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dca_bot.fix_dry_run_quote_spent import (
    LedgerReport,
    correct_records,
    main,
    process_ledger,
)


def _grid_entry(
    entry_id: str,
    *,
    dry_run: bool | None = True,
    quantity: float = 0.00018,
    buy_price: float = 79_964.55,
    quote_spent: float = 15.0,
    sell_price: float | None = None,
    realized_pnl: float | None = None,
) -> dict:
    """
    Ein Grid-Ledger-Eintrag in der Form, die grid_risk.GridPosition
    schreibt. Die Defaults sind die Zahlen der real betroffenen
    VPS-Position 569fff51.
    """
    entry = {
        "id": entry_id,
        "level_index": 7,
        "buy_price": buy_price,
        "target_sell_price": buy_price * 1.015,
        "quantity": quantity,
        "quote_spent": quote_spent,
        "bought_at": "2026-09-19T08:00:00+00:00",
        "status": "closed" if sell_price is not None else "open",
        "sell_price": sell_price,
        "sold_at": "2026-09-21T11:00:00+00:00" if sell_price is not None else None,
        "realized_pnl": realized_pnl,
    }
    if dry_run is not None:
        entry["dry_run"] = dry_run
    return entry


def _correct_grid(records: list[dict]) -> LedgerReport:
    report = LedgerReport(name="grid", path=Path("unused"))
    correct_records(
        records,
        report,
        id_key="id",
        buy_price_key="buy_price",
        sell_price_key="sell_price",
    )
    return report


class CorrectRecordsTestCase(unittest.TestCase):
    """Die eigentliche Rechenregel, ohne Dateizugriff."""

    def test_closed_dry_run_position_gets_positive_pnl(self):
        """
        Der konkrete Beleg: 0.00018 BTC @ 79.964,55 waren nie 15,00 USDT
        wert, sondern 14,39. Mit dem Verkauf bei 81.333,33 ist das ein
        GEWINN - gebucht war ein Verlust von 0,36.
        """
        records = [
            _grid_entry(
                "569fff51", sell_price=81_333.33, realized_pnl=-0.36
            )
        ]

        report = _correct_grid(records)

        self.assertEqual(len(report.changes), 1)
        self.assertAlmostEqual(records[0]["quote_spent"], 0.00018 * 79_964.55, places=10)
        self.assertGreater(records[0]["realized_pnl"], 0.0)
        # Fuer eine simulierte Position gilt wieder exakt
        # quantity * (Verkauf - Kauf) - genau diese Invariante war verletzt.
        self.assertAlmostEqual(
            records[0]["realized_pnl"],
            0.00018 * (81_333.33 - 79_964.55),
            places=10,
        )
        self.assertTrue(report.changes[0].flips_sign)

    def test_open_dry_run_position_gets_quote_spent_only(self):
        """Eine offene Position hat keine realisierte PnL - und bekommt keine."""
        records = [_grid_entry("offen-01")]

        report = _correct_grid(records)

        self.assertEqual(len(report.changes), 1)
        self.assertAlmostEqual(records[0]["quote_spent"], 0.00018 * 79_964.55, places=10)
        self.assertIsNone(records[0]["realized_pnl"])
        self.assertIsNone(report.changes[0].new_realized_pnl)

    def test_real_entries_are_never_touched(self):
        """
        Die wichtigste Zusicherung: bei einer echten Order ist
        `quote_spent` der von der Börse gemeldete `cummulativeQuoteQty`.
        Ihn lokal nachzurechnen wäre genau der umgekehrte Fehler.

        Die Gegenprobe steht bewusst im selben Test: ohne sie wäre er
        auch grün, wenn das Skript überhaupt nichts korrigiert.
        """
        records = [
            _grid_entry("echt-01", dry_run=False, quote_spent=14.526203),
            _grid_entry("dry-01", dry_run=True, quote_spent=15.0),
        ]

        report = _correct_grid(records)

        self.assertAlmostEqual(records[0]["quote_spent"], 14.526203, places=10)
        self.assertEqual(report.real_entries_skipped, 1)
        # Gegenprobe: der Dry-Run-Eintrag daneben WURDE korrigiert.
        self.assertEqual([c.entry_id for c in report.changes], ["dry-01"])
        self.assertLess(records[1]["quote_spent"], 15.0)

    def test_entry_without_dry_run_flag_is_skipped_and_reported(self):
        """
        Fehlt das Feld, wird nicht geraten - dieselbe Regel wie
        [GRID-POSITION-UNKLAR] im Produktivcode. "Echt" anzunehmen hieße,
        einen Börsenwert zu überschreiben; "Dry-Run" anzunehmen hieße,
        eine echte Kostenbasis zu verfälschen.
        """
        records = [_grid_entry("ohne-flag", dry_run=None)]

        report = _correct_grid(records)

        self.assertEqual(report.changes, [])
        self.assertEqual(report.unknown_flag_skipped, ["ohne-flag"])
        self.assertEqual(records[0]["quote_spent"], 15.0)

    def test_pre_k3_entry_is_a_no_op(self):
        """
        Vor dem K3-Fix war die Menge unquantisiert (exakt amount/price) -
        die Rückrechnung trifft den Ausgangswert wieder. Genau deshalb
        braucht das Skript keinen Datumsfilter: alte Einträge fallen
        durch die Toleranz von selbst heraus.
        """
        buy_price = 77_612.18
        records = [
            _grid_entry("alt-01", quantity=15.0 / buy_price, buy_price=buy_price)
        ]

        report = _correct_grid(records)

        self.assertEqual(report.changes, [])
        self.assertEqual(records[0]["quote_spent"], 15.0)

    def test_second_run_changes_nothing(self):
        """Idempotenz - das Skript darf mehrfach laufen dürfen."""
        records = [
            _grid_entry("569fff51", sell_price=81_333.33, realized_pnl=-0.36)
        ]

        first = _correct_grid(records)
        after_first = json.dumps(records, sort_keys=True)
        second = _correct_grid(records)

        self.assertEqual(len(first.changes), 1)
        self.assertEqual(second.changes, [])
        self.assertEqual(json.dumps(records, sort_keys=True), after_first)

    def test_unusable_entry_is_skipped_not_guessed(self):
        """Fehlt die Menge, gibt es nichts nachzurechnen - melden, nicht raten."""
        records = [_grid_entry("kaputt-01")]
        records[0]["quantity"] = None

        report = _correct_grid(records)

        self.assertEqual(report.changes, [])
        self.assertEqual(report.unusable_entries, ["kaputt-01"])
        self.assertEqual(records[0]["quote_spent"], 15.0)

    def test_dca_entries_have_no_pnl_column(self):
        """
        Der DCA-Bot verkauft nie - `sell_price_key=None`. Auch wenn ein
        Eintrag zufällig ein `realized_pnl`-Feld trüge, darf dort nichts
        gerechnet werden.
        """
        records = [
            {
                "timestamp": "2026-09-19T08:00:00+00:00",
                "symbol": "BTCUSDT",
                "quote_spent": 15.0,
                "quantity": 0.00018,
                "price": 79_964.55,
                "dry_run": True,
            }
        ]
        report = LedgerReport(name="dca", path=Path("unused"))

        correct_records(
            records,
            report,
            id_key="timestamp",
            buy_price_key="price",
            sell_price_key=None,
        )

        self.assertEqual(len(report.changes), 1)
        self.assertAlmostEqual(records[0]["quote_spent"], 0.00018 * 79_964.55, places=10)
        self.assertNotIn("realized_pnl", records[0])


class LedgerFileTestCase(unittest.TestCase):
    """Die Datei-Ebene: Bericht vs. Schreiben, Kopie, fehlende Datei."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)
        self.grid_file = self.tmp_path / "grid_positions.json"
        self._write(
            [
                _grid_entry("569fff51", sell_price=81_333.33, realized_pnl=-0.36),
                _grid_entry("echt-01", dry_run=False, quote_spent=14.526203),
            ]
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write(self, records: list[dict]) -> None:
        with self.grid_file.open("w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2)

    def _read(self) -> list[dict]:
        with self.grid_file.open(encoding="utf-8") as fh:
            return json.load(fh)

    def _process(self, apply_changes: bool):
        return process_ledger(
            "grid",
            str(self.grid_file),
            id_key="id",
            buy_price_key="buy_price",
            sell_price_key="sell_price",
            lock_file=None,
            apply_changes=apply_changes,
        )

    def test_report_mode_writes_nothing(self):
        """
        Der Default ist Bericht. Geprüft wird der DATEIINHALT, nicht nur
        ein Flag im Report - sonst prüfte der Test seine eigene
        Buchhaltung statt der Wirkung.
        """
        before = self.grid_file.read_bytes()

        report = self._process(apply_changes=False)

        self.assertEqual(len(report.changes), 1)
        self.assertFalse(report.written)
        self.assertEqual(self.grid_file.read_bytes(), before)

    def test_apply_writes_and_keeps_a_backup(self):
        report = self._process(apply_changes=True)

        self.assertTrue(report.written)
        records = self._read()
        self.assertGreater(records[0]["realized_pnl"], 0.0)
        # Echter Eintrag unverändert.
        self.assertAlmostEqual(records[1]["quote_spent"], 14.526203, places=10)

        self.assertIsNotNone(report.backup_path)
        self.assertTrue(report.backup_path.exists())
        with report.backup_path.open(encoding="utf-8") as fh:
            backup = json.load(fh)
        self.assertEqual(backup[0]["quote_spent"], 15.0)
        self.assertAlmostEqual(backup[0]["realized_pnl"], -0.36, places=10)

    def test_apply_twice_is_idempotent(self):
        self._process(apply_changes=True)
        after_first = self._read()

        second = self._process(apply_changes=True)

        self.assertEqual(second.changes, [])
        self.assertFalse(second.written, "Ohne Abweichung darf nicht geschrieben werden")
        self.assertEqual(self._read(), after_first)

    def test_missing_file_is_not_an_error(self):
        """Eine fehlende Datei heißt "frisches Deployment", wie im Produktivcode."""
        report = process_ledger(
            "grid",
            str(self.tmp_path / "gibt-es-nicht.json"),
            id_key="id",
            buy_price_key="buy_price",
            sell_price_key="sell_price",
            lock_file=None,
            apply_changes=True,
        )

        self.assertFalse(report.exists)
        self.assertEqual(report.changes, [])


class CliTestCase(unittest.TestCase):
    """Die Verdrahtung der drei Ledger im Einstiegspunkt."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_all_three_ledgers_are_processed(self):
        """
        Drei beinahe identische Aufrufstellen, von denen später eine
        vergessen wird - derselbe Fehler, den der Verdrahtungstest der
        drei main*.py in test_startup_balance_check.py abdeckt.
        """
        grid = self.tmp_path / "grid.json"
        trend = self.tmp_path / "trend.json"
        dca = self.tmp_path / "dca.json"
        with grid.open("w", encoding="utf-8") as fh:
            json.dump([_grid_entry("g1")], fh)
        with trend.open("w", encoding="utf-8") as fh:
            json.dump(
                [
                    {
                        "id": "t1",
                        "entry_price": 79_964.55,
                        "entry_time": "2026-09-19T08:00:00+00:00",
                        "quantity": 0.00018,
                        "quote_spent": 15.0,
                        "dry_run": True,
                        "status": "closed",
                        "exit_price": 81_333.33,
                        "exit_time": "2026-09-21T11:00:00+00:00",
                        "exit_reason": "signal",
                        "realized_pnl": -0.36,
                    }
                ],
                fh,
            )
        with dca.open("w", encoding="utf-8") as fh:
            json.dump(
                [
                    {
                        "timestamp": "2026-09-19T08:00:00+00:00",
                        "symbol": "BTCUSDT",
                        "quote_spent": 15.0,
                        "quantity": 0.00018,
                        "price": 79_964.55,
                        "dry_run": True,
                    }
                ],
                fh,
            )

        exit_code = main(
            [
                "--grid-file", str(grid),
                "--trend-file", str(trend),
                "--dca-file", str(dca),
                "--no-lock",
                "--apply",
            ]
        )

        self.assertEqual(exit_code, 0)
        for path, key in ((grid, "quote_spent"), (trend, "quote_spent"), (dca, "quote_spent")):
            with path.open(encoding="utf-8") as fh:
                records = json.load(fh)
            self.assertAlmostEqual(
                records[0][key], 0.00018 * 79_964.55, places=10, msg=f"{path.name} nicht korrigiert"
            )
        # Der Trend-Ausstieg bekommt zusaetzlich seine PnL korrigiert.
        with trend.open(encoding="utf-8") as fh:
            self.assertGreater(json.load(fh)[0]["realized_pnl"], 0.0)

    def test_cli_default_is_report_only(self):
        grid = self.tmp_path / "grid.json"
        with grid.open("w", encoding="utf-8") as fh:
            json.dump([_grid_entry("g1")], fh)
        before = grid.read_bytes()

        exit_code = main(
            [
                "--grid-file", str(grid),
                "--trend-file", str(self.tmp_path / "keine.json"),
                "--dca-file", str(self.tmp_path / "keine.json"),
                "--no-lock",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(grid.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

"""
Tests fuer den bot-uebergreifenden Gesamtabgleich im Positions-Audit
(Stufe 2 der Verbesserungsvorschlaege, Punkt 3 in modifizierter Form -
Teil B) sowie fuer `split_locked_by_bot()` in balance_guard.py.

**Worum es geht.** Jeder Bot prueft nur, ob SEIN eigener Anspruch noch
gedeckt waere (W11, balance_guard.py) - eine bewusst konservative
Pruefung ohne Fehlalarme, die dafuer genau den Fall nicht sieht, in dem
erst die SUMME aller drei zu gross wird. Diese Frage kann kein Bot
stellen, ohne fremde Ledger zu lesen, und das bricht das Trennungsprinzip
des Projekts. Ein rein lesendes Werkzeug darf alles einsehen - deshalb
sitzt der Gesamtabgleich in audit_positions.py.

**Warum die Rechnung als reine Funktion getestet wird.** Das Skript gibt
sein Ergebnis auf stdout aus. Die Zahlen aus gedrucktem Text
zurueckzuparsen waere ein Test, der bei jeder Formatierungsaenderung
umfaellt und trotzdem nichts ueber die Richtigkeit sagt. `LedgerClaim`
und `compare_with_account()` liefern das Ergebnis deshalb als Objekt;
gedruckt wird es getrennt davon.

Kein Netzwerk, keine Zugangsdaten, temporaere Dateien.

Ausfuehren mit:  python -m unittest tests.test_audit_positions -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dca_bot.audit_positions import (
    BOT_NAMES,
    AccountComparison,
    LedgerClaim,
    _ReadOnlyClientConfig,
    _build_read_only_client,
    compare_with_account,
    dca_claim,
    grid_claim,
    trend_claim,
)
from dca_bot.balance_guard import FOREIGN_ORDERS, split_locked_by_bot

STEP_SIZE = 0.00001
# tolerance_for(0.5, 0.00001) = max(2 * 0.00001, 0.5 * 0.001) = 0.0005
TOTAL = 0.5
TOLERANCE = 0.0005


def sell_order(
    client_order_id: str,
    orig_qty: float,
    executed_qty: float = 0.0,
    status: str = "NEW",
    side: str = "SELL",
) -> dict:
    return {
        "clientOrderId": client_order_id,
        "side": side,
        "status": status,
        "origQty": orig_qty,
        "executedQty": executed_qty,
    }


class LedgerFileTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write(self, name: str, records) -> Path:
        path = self.tmp_path / name
        path.write_text(json.dumps(records), encoding="utf-8")
        return path

    def _dca_record(self, quantity: float, dry_run, symbol: str = "BTCUSDT") -> dict:
        record = {
            "timestamp": "2026-09-17T10:00:00+00:00",
            "symbol": symbol,
            "quote_spent": quantity * 50_000.0,
            "quantity": quantity,
            "price": 50_000.0,
        }
        if dry_run is not None:
            record["dry_run"] = dry_run
        return record

    def _position(self, quantity: float, dry_run, status: str = "open") -> dict:
        record = {"id": "x", "quantity": quantity, "status": status, "quote_spent": 15.0}
        if dry_run is not None:
            record["dry_run"] = dry_run
        return record


class DCAClaimTestCase(LedgerFileTestBase):
    """
    Der DCA-Bot verkauft nie - sein Ledger ist eine append-only-Liste
    ohne `status`. Die Summe aller echten Kaeufe IST der Bestand.
    """

    def test_real_buys_are_added_up(self):
        path = self._write(
            "dca.json",
            [self._dca_record(0.2, False), self._dca_record(0.3, False)],
        )
        claim = dca_claim(path, "BTCUSDT")
        self.assertAlmostEqual(claim.quantity, 0.5, places=9)
        self.assertEqual(claim.bot, "dca")

    def test_dry_run_buys_are_excluded_but_counted(self):
        path = self._write(
            "dca.json",
            [self._dca_record(0.2, False), self._dca_record(0.3, True)],
        )
        claim = dca_claim(path, "BTCUSDT")
        self.assertAlmostEqual(claim.quantity, 0.2, places=9)
        self.assertEqual(claim.dry_run_entries, 1)

    def test_entries_without_a_dry_run_field_are_excluded_but_counted(self):
        """
        Ein Eintrag ohne `dry_run` entsteht praktisch nur durch manuelles
        Editieren. Er wird NICHT mitgezaehlt (dieselbe konservative
        Richtung wie in den Bots), aber eigens ausgewiesen - sonst
        verschwaende er stillschweigend aus der Summe.
        """
        path = self._write(
            "dca.json",
            [self._dca_record(0.2, False), self._dca_record(0.3, None)],
        )
        claim = dca_claim(path, "BTCUSDT")
        self.assertAlmostEqual(claim.quantity, 0.2, places=9)
        self.assertEqual(claim.unknown_entries, 1)

    def test_other_symbols_are_filtered_out(self):
        """
        Anders als Grid und Trend tragen DCA-Eintraege ein Symbol. Ein
        Bestand in einem anderen Paar sagt ueber dieses Base-Asset nichts
        aus und darf die Summe nicht aufblaehen.
        """
        path = self._write(
            "dca.json",
            [
                self._dca_record(0.2, False),
                self._dca_record(9.0, False, symbol="ETHUSDT"),
            ],
        )
        claim = dca_claim(path, "BTCUSDT")
        self.assertAlmostEqual(claim.quantity, 0.2, places=9)

    def test_a_missing_file_is_reported_as_an_error_not_as_zero(self):
        """
        Wichtig fuer die Gesamtsumme: "Datei nicht da" ist etwas anderes
        als "nichts offen". Wuerde es als 0 durchgehen, sae he ein
        fehlendes Ledger wie ein gedeckter Zustand aus.
        """
        claim = dca_claim(self.tmp_path / "fehlt.json", "BTCUSDT")
        self.assertIsNotNone(claim.error)
        self.assertEqual(claim.quantity, 0.0)

    def test_a_broken_file_is_reported_as_an_error(self):
        path = self.tmp_path / "kaputt.json"
        path.write_text("{kein json", encoding="utf-8")
        claim = dca_claim(path, "BTCUSDT")
        self.assertIsNotNone(claim.error)


class GridAndTrendClaimTestCase(LedgerFileTestBase):
    """Grid und Trend fuehren `status` - nur offene Eintraege zaehlen."""

    def test_grid_adds_up_all_open_levels(self):
        path = self._write(
            "grid.json",
            [self._position(0.2, False), self._position(0.3, False)],
        )
        self.assertAlmostEqual(grid_claim(path, "BTCUSDT").quantity, 0.5, places=9)

    def test_grid_ignores_closed_positions(self):
        path = self._write(
            "grid.json",
            [self._position(0.2, False), self._position(0.3, False, status="closed")],
        )
        self.assertAlmostEqual(grid_claim(path, "BTCUSDT").quantity, 0.2, places=9)

    def test_grid_ignores_dry_run_positions(self):
        path = self._write(
            "grid.json",
            [self._position(0.2, False), self._position(0.3, True)],
        )
        claim = grid_claim(path, "BTCUSDT")
        self.assertAlmostEqual(claim.quantity, 0.2, places=9)
        self.assertEqual(claim.dry_run_entries, 1)

    def test_trend_reads_its_single_open_position(self):
        path = self._write(
            "trend.json",
            [self._position(0.3, False, status="closed"), self._position(0.2, False)],
        )
        claim = trend_claim(path, "BTCUSDT")
        self.assertAlmostEqual(claim.quantity, 0.2, places=9)
        self.assertEqual(claim.bot, "trend")

    def test_trend_with_no_open_position_claims_nothing(self):
        path = self._write("trend.json", [self._position(0.3, False, status="closed")])
        self.assertEqual(trend_claim(path, "BTCUSDT").quantity, 0.0)


class SplitLockedByBotTestCase(unittest.TestCase):
    """
    `split_locked_by_bot()`: die gebundene Menge nach Verursacher. Moeglich
    nur, weil seit dem K2-Fix jede Order dieses Projekts ein Bot-Praefix
    in ihrer clientOrderId traegt.
    """

    def test_orders_are_attributed_to_their_bot(self):
        result = split_locked_by_bot(
            [
                sell_order("grid-aaa", 0.2),
                sell_order("trend-bbb", 0.3),
                sell_order("dca-ccc", 0.1),
            ],
            BOT_NAMES,
        )
        self.assertAlmostEqual(result["grid"], 0.2, places=9)
        self.assertAlmostEqual(result["trend"], 0.3, places=9)
        self.assertAlmostEqual(result["dca"], 0.1, places=9)
        self.assertEqual(result[FOREIGN_ORDERS], 0.0)

    def test_orders_without_a_known_prefix_land_in_the_foreign_bucket(self):
        """
        Ein manueller Verkauf ueber die Boersen-Oberflaeche traegt eine
        von Binance vergebene ID. Er gehoert sichtbar ausgewiesen - im
        Zweifel fremd, dieselbe konservative Richtung wie in
        split_locked_quantity().
        """
        result = split_locked_by_bot(
            [sell_order("web_abcdef", 0.4), sell_order("grid-aaa", 0.1)], BOT_NAMES
        )
        self.assertAlmostEqual(result[FOREIGN_ORDERS], 0.4, places=9)
        self.assertAlmostEqual(result["grid"], 0.1, places=9)

    def test_buy_orders_do_not_bind_base_asset(self):
        """Eine offene KAUF-Order bindet Quote-Waehrung (USDT), nicht BTC."""
        result = split_locked_by_bot([sell_order("grid-aaa", 0.5, side="BUY")], BOT_NAMES)
        self.assertEqual(result["grid"], 0.0)

    def test_only_the_unfilled_remainder_counts(self):
        """
        Bei einer teilausgefuehrten Order ist nur der Rest noch gebunden -
        `origQty` waere zu viel.
        """
        result = split_locked_by_bot(
            [sell_order("grid-aaa", 0.5, executed_qty=0.2, status="PARTIALLY_FILLED")],
            BOT_NAMES,
        )
        self.assertAlmostEqual(result["grid"], 0.3, places=9)

    def test_finished_orders_bind_nothing(self):
        result = split_locked_by_bot(
            [sell_order("grid-aaa", 0.5, status="FILLED")], BOT_NAMES
        )
        self.assertEqual(result["grid"], 0.0)

    def test_unavailable_orders_yield_none_not_an_empty_split(self):
        """
        "Abfrage gescheitert" ist etwas anderes als "keine offenen
        Orders" - dieselbe Unterscheidung wie ueberall im Projekt.
        """
        self.assertIsNone(split_locked_by_bot(None, BOT_NAMES))

    def test_an_empty_order_list_yields_zeros(self):
        result = split_locked_by_bot([], BOT_NAMES)
        self.assertEqual(set(result), set(BOT_NAMES) | {FOREIGN_ORDERS})
        self.assertEqual(sum(result.values()), 0.0)


class CompareWithAccountTestCase(unittest.TestCase):
    """Der eigentliche Gesamtabgleich."""

    def _claims(self) -> list[LedgerClaim]:
        return [
            LedgerClaim(bot="dca", symbol="BTCUSDT", quantity=0.3),
            LedgerClaim(bot="grid", symbol="BTCUSDT", quantity=0.15),
            LedgerClaim(bot="trend", symbol="BTCUSDT", quantity=0.05),
        ]

    # Eigener Standardwert, damit ein ausdruecklich uebergebenes `None`
    # (= "offene Orders nicht abrufbar") den Helfer wirklich erreicht und
    # nicht von ihm zu einer leeren Liste gemacht wird - sonst entstuende
    # der zu pruefende Fall gar nicht.
    _UNSET = object()

    def _compare(self, free: float, locked: float = 0.0, open_orders=_UNSET):
        return compare_with_account(
            symbol="BTCUSDT",
            base_asset="BTC",
            claims=self._claims(),
            balance=(free, locked),
            open_orders=[] if open_orders is self._UNSET else open_orders,
            step_size=STEP_SIZE,
        )

    def test_the_claims_are_summed_across_all_three_bots(self):
        """
        Die Aussage, die kein einzelner Bot treffen kann: 0,3 + 0,15 +
        0,05 = 0,5 beansprucht, ueber Bot-Grenzen hinweg.
        """
        self.assertAlmostEqual(self._compare(1.0).total_claimed, TOTAL, places=9)

    def test_a_covered_account_is_no_finding(self):
        self.assertFalse(self._compare(1.0).discrepancy)

    def test_an_uncovered_account_is_a_finding(self):
        comparison = self._compare(0.1)
        self.assertTrue(comparison.discrepancy)
        self.assertAlmostEqual(comparison.difference, -0.4, places=9)

    def test_locked_quantity_counts_towards_coverage(self):
        """
        Eine Menge in einer offenen Verkaufs-Order EXISTIERT noch, sie ist
        nur gerade nicht verkaeuflich. Fuer die Frage "ist alles da?"
        zaehlt sie mit - anders als bei der Deckungspruefung eines
        einzelnen Verkaufs, die bewusst nur gegen `free` prueft.
        """
        self.assertFalse(self._compare(free=0.0, locked=TOTAL).discrepancy)

    def test_the_same_amount_missing_entirely_is_a_finding(self):
        """
        Gegenprobe: Ohne die gebundene Menge ist derselbe Anspruch
        ungedeckt. Der vorige Test haengt also wirklich an `locked`.
        """
        self.assertTrue(self._compare(free=0.0, locked=0.0).discrepancy)

    def test_no_finding_exactly_at_the_tolerance_boundary(self):
        self.assertFalse(self._compare(TOTAL - TOLERANCE).discrepancy)

    def test_a_finding_just_beyond_the_tolerance_boundary(self):
        """
        Gegenprobe zum vorigen Test - belegt, dass die Grenze dort liegt
        und die Toleranz nicht einfach alles schluckt.
        """
        self.assertTrue(self._compare(TOTAL - TOLERANCE - 0.0001).discrepancy)

    def test_a_surplus_on_the_account_is_not_a_finding(self):
        """
        Mehr auf dem Konto als beansprucht ist ausdruecklich kein
        Problem: manueller Bestand, eine Altlast, oder schlicht etwas,
        das keiner der drei Bots verwaltet.
        """
        comparison = self._compare(5.0)
        self.assertFalse(comparison.discrepancy)
        self.assertGreater(comparison.difference, 0)

    def test_the_locked_split_is_carried_into_the_result(self):
        comparison = self._compare(
            free=0.0, locked=0.5, open_orders=[sell_order("trend-aaa", 0.5)]
        )
        self.assertAlmostEqual(comparison.locked_by_bot["trend"], 0.5, places=9)

    def test_unavailable_orders_leave_the_split_unknown_without_breaking_the_verdict(self):
        """
        Die Zuordnung der gebundenen Menge ist eine Zugabe. Faellt sie
        aus, muss das Urteil ueber Deckung trotzdem zustande kommen - es
        braucht nur `free + locked`.
        """
        comparison = self._compare(free=0.0, locked=TOTAL, open_orders=None)
        self.assertIsNone(comparison.locked_by_bot)
        self.assertFalse(comparison.discrepancy)

    def test_a_ledger_that_could_not_be_read_does_not_silently_count_as_zero(self):
        """
        Ein unlesbares Ledger traegt 0 zur Summe bei - das ist
        unvermeidlich, es gibt ja keine Zahl. Entscheidend ist, dass der
        Fehler im Ergebnis sichtbar bleibt und in der Ausgabe landet,
        statt die Summe als vollstaendig erscheinen zu lassen.
        """
        comparison = compare_with_account(
            symbol="BTCUSDT",
            base_asset="BTC",
            claims=[
                LedgerClaim(bot="dca", symbol="BTCUSDT", quantity=0.2),
                LedgerClaim(bot="grid", symbol="BTCUSDT", error="Datei kaputt"),
            ],
            balance=(1.0, 0.0),
            open_orders=[],
            step_size=STEP_SIZE,
        )
        self.assertAlmostEqual(comparison.total_claimed, 0.2, places=9)
        self.assertTrue(any(c.error for c in comparison.claims))


class SymbolGroupingTestCase(unittest.TestCase):
    """
    Gruppierung nach Symbol. Im Normalfall handeln alle drei BTCUSDT und
    es gibt genau eine Gruppe - die Konfiguration erlaubt aber
    unterschiedliche Paare, und dann waere eine Gesamtsumme schlicht
    falsch (sie addierte Mengen verschiedener Assets).
    """

    def _group(self, claims: list[LedgerClaim]) -> dict[str, list[LedgerClaim]]:
        grouped: dict[str, list[LedgerClaim]] = {}
        for claim in claims:
            grouped.setdefault(claim.symbol, []).append(claim)
        return grouped

    def test_identical_symbols_form_a_single_group(self):
        grouped = self._group(
            [
                LedgerClaim(bot="dca", symbol="BTCUSDT", quantity=0.2),
                LedgerClaim(bot="grid", symbol="BTCUSDT", quantity=0.3),
                LedgerClaim(bot="trend", symbol="BTCUSDT", quantity=0.1),
            ]
        )
        self.assertEqual(list(grouped), ["BTCUSDT"])
        self.assertEqual(len(grouped["BTCUSDT"]), 3)

    def test_differing_symbols_are_kept_apart(self):
        grouped = self._group(
            [
                LedgerClaim(bot="dca", symbol="BTCUSDT", quantity=0.2),
                LedgerClaim(bot="grid", symbol="ETHUSDT", quantity=9.0),
            ]
        )
        self.assertEqual(sorted(grouped), ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(
            sum(c.quantity for c in grouped["BTCUSDT"]), 0.2
        )


class ReadOnlyClientTestCase(unittest.TestCase):
    """
    Der optionale Kontoabgleich - und die Zusage, dass dieses Skript
    niemals eine Order platzieren kann.
    """

    def test_missing_credentials_skip_the_check_instead_of_failing(self):
        """
        Die zentrale Zusage des Skripts: Ohne API-Keys laeuft der
        Ledger-Teil weiter, der Kontoabgleich entfaellt mit einem Grund.
        Ein Absturz waere hier das Schlechteste - das Werkzeug soll
        gerade dann helfen, wenn etwas nicht stimmt.
        """
        with mock.patch.dict(
            "os.environ", {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": ""}, clear=False
        ):
            client, reason = _build_read_only_client()

        self.assertIsNone(client)
        self.assertIn("BINANCE_API_KEY", reason)

    def test_valid_credentials_build_a_client(self):
        with mock.patch.dict(
            "os.environ",
            {"BINANCE_API_KEY": "echt", "BINANCE_API_SECRET": "auch-echt"},
            clear=False,
        ):
            with mock.patch("dca_bot.binance_client.TradingClient") as fake:
                client, reason = _build_read_only_client()

        self.assertIsNone(reason)
        self.assertIs(client, fake.return_value)

    def test_the_client_config_cannot_place_orders(self):
        """
        `pending_orders_file` ist leer - damit legt der TradingClient
        keinen Pending-Store an, und seine place_*-Methoden weisen jede
        Order aktiv zurueck (siehe binance_client.py). Die Nur-Lesend-
        Zusage haengt damit nicht an Disziplin, sondern ist strukturell
        abgesichert.
        """
        config = _ReadOnlyClientConfig(
            api_key="k", api_secret="s", use_testnet=True
        )
        self.assertEqual(config.pending_orders_file, "")
        self.assertEqual(config.bot_name, "audit")

    def test_the_audit_bot_name_is_not_one_of_the_real_bots(self):
        """
        Wichtig fuer split_locked_by_bot(): Traege das Audit denselben
        Namen wie ein Bot, koennte seine (nie existierende) Order dessen
        Menge verfaelschen. Es ist ausserdem kein Praefix, das je in
        einer clientOrderId auftaucht - das Skript platziert nichts.
        """
        self.assertNotIn(_ReadOnlyClientConfig.bot_name, BOT_NAMES)


if __name__ == "__main__":
    unittest.main()

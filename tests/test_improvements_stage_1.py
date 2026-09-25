"""
Tests fuer Stufe 1 der Verbesserungsvorschlaege aus Abschnitt 7 des
Sicherheitsreviews - die drei kleinen, vor dem Echtgeld-Schalter
faelligen Punkte.

Anders als die K/W-Punkte war nichts davon als sicherheitskritisch
eingestuft. Der Ist-Stand-Check am 17.09.2026 hat allerdings gezeigt,
dass zwei der drei inzwischen sehr wohl Gewicht haben:

- **Punkt 2 (atomare Zustandsschreibvorgaenge):** Die drei Ledger und der
  Pending-Store schreiben seit W5/K2 atomar, die Allocator-State-Datei
  nicht. Das war folgenlos, solange niemand sie las - mit der Aktivierung
  des Opt-ins (6h) lesen DCA und Trend sie jetzt vor JEDER neuen Order.
- **Punkt 10 (globales STOP_ALL):** Vorher brauchte es vier Dateien oder
  vier Variablen, um alle Bots anzuhalten.

Punkt 8 (Gebuehren im Stop-Fill-Pfad, die tatsaechlich nie geschlossene
K3-Restluecke) steht bewusst NICHT hier, sondern in
test_trend_stop_loss.py bei seinen Geschwistern - dort leben alle
Stop-Order-Tests und der passende Fake-Client.

Kein Netzwerk, keine Zugangsdaten, temporaere Dateien.

Ausfuehren mit:  python -m unittest tests.test_improvements_stage_1 -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dca_bot.allocator import Allocator
from dca_bot.allocator_config import AllocatorConfig
from dca_bot.allocator_signals import (
    STALE_ALLOCATION_FALLBACK,
    read_allocation_fraction,
)
from dca_bot.risk import GLOBAL_KILL_SWITCH_NAME, BotHalted, KillSwitch


class TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()


# ---------------------------------------------------------------------------
# Punkt 2: Allocator-State-Datei atomar schreiben
# ---------------------------------------------------------------------------


class AllocatorStateWriteTestCase(TempDirTestCase):
    def _make_allocator(self) -> Allocator:
        config = AllocatorConfig(
            api_key="test",
            api_secret="test",
            state_file=str(self.tmp_path / "allocator_state.json"),
        )
        return Allocator(config)

    def test_write_leaves_no_temporary_file_behind(self):
        allocator = self._make_allocator()
        allocator._write_state({"trend_fraction": 0.5})

        leftovers = [p.name for p in self.tmp_path.iterdir() if p.suffix == ".tmp"]
        self.assertEqual(leftovers, [], "Keine temporaere Datei darf zurueckbleiben")

    def test_written_file_is_complete_and_readable(self):
        allocator = self._make_allocator()
        payload = {"trend_fraction": 0.25, "gap_pct": 1.5, "interval_minutes": 60}
        allocator._write_state(payload)

        path = self.tmp_path / "allocator_state.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)

    def test_a_crash_while_writing_keeps_the_previous_version(self):
        """
        Der eigentliche Punkt des atomaren Musters, und seit dem
        Allocator-Opt-in (6h) mit echten Konsumenten: Bricht der Schreib-
        vorgang ab, muss die ALTE Fassung unversehrt stehen bleiben. Mit
        dem frueheren `open("w")` waere die Zieldatei zu diesem Zeitpunkt
        bereits gekuerzt gewesen - und DCA wie Trend haetten sie in
        diesem Zustand gelesen.
        """
        allocator = self._make_allocator()
        allocator._write_state({"trend_fraction": 0.25})
        path = self.tmp_path / "allocator_state.json"
        before = path.read_text(encoding="utf-8")

        with mock.patch(
            "dca_bot.allocator.json.dump", side_effect=OSError("Platte voll")
        ):
            with self.assertRaises(OSError):
                allocator._write_state({"trend_fraction": 0.9})

        self.assertEqual(path.read_text(encoding="utf-8"), before)
        self.assertEqual(json.loads(before)["trend_fraction"], 0.25)


# ---------------------------------------------------------------------------
# Punkt 2: konservativer Fallback bei unbrauchbarer Zuteilung
# ---------------------------------------------------------------------------


class AllocationFallbackTestCase(TempDirTestCase):
    """
    Die Unterscheidung, um die es geht:

    - `None` = "es gibt keinen Allocator" -> der lesende Bot nutzt den
      VOLLEN Betrag.
    - `0.0` = "die Datei ist da, aber unbrauchbar" -> 100% DCA, kein
      Trend-Einstieg.

    Vor dem 17.09.2026 ergaben beide Faelle `None`. Bei einer kaputten
    Datei hiess das: DCA kauft voll UND Trend steigt voll ein - zusammen
    mehr Kapital, als die Zuteilung je vorgesehen haette. Genau die
    Ueberallokation, gegen die der Allocator existiert, und genau die
    Richtung, die fuer den Veraltet-Fall unter W10 schon verworfen wurde.
    """

    def _write(self, content: str) -> str:
        path = self.tmp_path / "allocator_state.json"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def _fresh_payload(self, **overrides) -> dict:
        payload = {
            "trend_fraction": 0.75,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "interval_minutes": 60,
        }
        payload.update(overrides)
        return payload

    # -- Der Normalfall bleibt unveraendert --

    def test_valid_fresh_allocation_is_returned(self):
        path = self._write(json.dumps(self._fresh_payload()))
        self.assertAlmostEqual(read_allocation_fraction(path), 0.75)

    # -- "kein Allocator": weiterhin None --

    def test_disabled_feature_returns_none(self):
        self.assertIsNone(read_allocation_fraction(""))

    def test_missing_file_returns_none(self):
        """
        Die bewusste Abgrenzung: Eine fehlende Datei heisst "der
        Allocator hat noch nie geschrieben" - der regulaere Zustand bei
        einem frischen Deployment und in den Sekunden zwischen zwei
        Service-Starts. Bekaeme dieser Fall den Fallback, wuerde ein
        frisch aufgesetzter Bot mit gesetztem Opt-in, aber noch nicht
        gestartetem Allocator nie wieder Trend-Positionen eroeffnen.
        """
        self.assertIsNone(
            read_allocation_fraction(str(self.tmp_path / "gibt-es-nicht.json"))
        )

    # -- "unbrauchbar": konservativer Fallback --

    def test_corrupt_json_falls_back_conservatively(self):
        path = self._write('{"trend_fraction": 0.7')  # abgeschnitten
        self.assertEqual(read_allocation_fraction(path), STALE_ALLOCATION_FALLBACK)

    def test_missing_key_falls_back_conservatively(self):
        path = self._write(json.dumps({"gap_pct": 1.5}))
        self.assertEqual(read_allocation_fraction(path), STALE_ALLOCATION_FALLBACK)

    def test_unreadable_value_falls_back_conservatively(self):
        path = self._write(json.dumps(self._fresh_payload(trend_fraction="viel")))
        self.assertEqual(read_allocation_fraction(path), STALE_ALLOCATION_FALLBACK)

    def test_non_dict_content_falls_back_conservatively(self):
        path = self._write(json.dumps([1, 2, 3]))
        self.assertEqual(read_allocation_fraction(path), STALE_ALLOCATION_FALLBACK)

    def test_out_of_range_value_falls_back_conservatively(self):
        path = self._write(json.dumps(self._fresh_payload(trend_fraction=1.5)))
        self.assertEqual(read_allocation_fraction(path), STALE_ALLOCATION_FALLBACK)

    def test_unreadable_file_does_not_abort_the_cycle(self):
        """
        `OSError` war vorher gar nicht gefangen: Ein Rechteproblem an
        dieser Datei hat die Exception bis in `execute_once()`
        durchgereicht und damit den kompletten Kaufzyklus des lesenden
        Bots abgebrochen - wegen einer Datei, die nur die Ordergroesse
        skalieren soll.
        """
        path = self._write(json.dumps(self._fresh_payload()))
        with mock.patch("builtins.open", side_effect=PermissionError("kein Zugriff")):
            self.assertEqual(read_allocation_fraction(path), STALE_ALLOCATION_FALLBACK)

    def test_stale_allocation_still_falls_back(self):
        """Gegenprobe: Der W10-Pfad ist unveraendert."""
        old = datetime.now(timezone.utc) - timedelta(hours=10)
        path = self._write(json.dumps(self._fresh_payload(updated_at=old.isoformat())))
        self.assertEqual(read_allocation_fraction(path), STALE_ALLOCATION_FALLBACK)

    def test_fallback_means_full_dca_and_no_trend_entry(self):
        """
        Haelt fest, was der Fallback-Wert bedeutet - sonst waere `0.0`
        nur eine Zahl ohne Aussage. `1 - 0.0` ist der DCA-Anteil (voll),
        `0.0` der Trend-Anteil (kein Einstieg, weil das Ergebnis unter
        MIN_EFFECTIVE_QUOTE_AMOUNT faellt).
        """
        self.assertEqual(STALE_ALLOCATION_FALLBACK, 0.0)


# ---------------------------------------------------------------------------
# Punkt 10: globales STOP_ALL
# ---------------------------------------------------------------------------


class GlobalKillSwitchTestCase(TempDirTestCase):
    """
    Ein Schalter, der alle vier Bots gleichzeitig stoppt - zusaetzlich zu
    den botspezifischen, nicht an deren Stelle.
    """

    BOTS = (
        ("STOP", "DCA_BOT_HALT"),
        ("STOP_GRID", "GRID_BOT_HALT"),
        ("STOP_TREND", "TREND_BOT_HALT"),
        ("STOP_ALLOCATOR", "ALLOCATOR_HALT"),
    )

    def setUp(self) -> None:
        super().setUp()
        self.env_file = self.tmp_path / ".env"
        self.env_file.write_text("SONSTIGE_EINSTELLUNG=egal\n", encoding="utf-8")
        self.global_file = self.tmp_path / GLOBAL_KILL_SWITCH_NAME
        self._saved_env = dict(os.environ)
        for _, var in self.BOTS:
            os.environ.pop(var, None)
        os.environ.pop(GLOBAL_KILL_SWITCH_NAME, None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved_env)
        super().tearDown()

    def _switches(self) -> list[KillSwitch]:
        return [
            KillSwitch(
                str(self.tmp_path / stop_file),
                env_var_name=var,
                env_file=self.env_file,
                global_file=self.global_file,
            )
            for stop_file, var in self.BOTS
        ]

    def _write_env(self, content: str) -> None:
        self.env_file.write_text(content, encoding="utf-8")
        # Signatur sicher veraendern, siehe test_kill_switch.py
        stamp = self.env_file.stat().st_mtime + 10
        os.utime(self.env_file, (stamp, stamp))

    # -- Grundzustand --

    def test_nothing_is_set_by_default(self):
        for switch in self._switches():
            self.assertFalse(switch.is_set())

    # -- Weg 4: die globale Datei --

    def test_global_file_stops_all_four_bots(self):
        switches = self._switches()
        self.global_file.write_text("", encoding="utf-8")
        for switch in switches:
            self.assertTrue(switch.is_set())

    def test_global_file_works_on_switches_created_beforehand(self):
        """
        Wie bei der STOP-Datei: Der Schalter wird beim Start erzeugt und
        laeuft dann stundenlang. Die Datei muss waehrenddessen wirken,
        nicht erst beim naechsten Neustart.
        """
        switches = self._switches()
        for switch in switches:
            self.assertFalse(switch.is_set())
        self.global_file.write_text("", encoding="utf-8")
        for switch in switches:
            self.assertTrue(switch.is_set())

    # -- Weg 5: die globale Variable --

    def test_global_variable_in_process_environment_stops_all(self):
        os.environ[GLOBAL_KILL_SWITCH_NAME] = "true"
        for switch in self._switches():
            self.assertTrue(switch.is_set())

    def test_global_variable_in_the_env_file_stops_all(self):
        """
        Derselbe W1-Weg wie bei den botspezifischen Variablen: nachtraeglich
        in die `.env` geschrieben, ohne Neustart wirksam.
        """
        switches = self._switches()
        self._write_env(f"{GLOBAL_KILL_SWITCH_NAME}=true\n")
        for switch in switches:
            self.assertTrue(switch.is_set())

    def test_global_variable_is_case_insensitive_and_trimmed(self):
        os.environ[GLOBAL_KILL_SWITCH_NAME] = "  TRUE  "
        for switch in self._switches():
            self.assertTrue(switch.is_set())

    def test_global_variable_false_does_not_stop_anything(self):
        os.environ[GLOBAL_KILL_SWITCH_NAME] = "false"
        for switch in self._switches():
            self.assertFalse(switch.is_set())

    # -- Die botspezifischen Schalter bleiben unabhaengig --

    def test_a_single_bot_switch_does_not_stop_the_others(self):
        """
        Der globale Schalter ergaenzt, er ersetzt nicht: Einen einzelnen
        Bot anzuhalten muss weiterhin moeglich sein, ohne die anderen
        drei mitzunehmen.
        """
        switches = self._switches()
        (self.tmp_path / "STOP_GRID").write_text("", encoding="utf-8")

        self.assertFalse(switches[0].is_set())  # DCA
        self.assertTrue(switches[1].is_set())   # Grid
        self.assertFalse(switches[2].is_set())  # Trend
        self.assertFalse(switches[3].is_set())  # Allocator

    def test_global_false_does_not_override_a_bot_specific_stop(self):
        """
        Die ODER-Verknuepfung ist asymmetrisch (W1): Ausloesen leicht,
        Aufheben schwer. Ein `STOP_ALL=false` darf einen gesetzten
        botspezifischen Notaus nicht aufheben.
        """
        os.environ[GLOBAL_KILL_SWITCH_NAME] = "false"
        switches = self._switches()
        (self.tmp_path / "STOP").write_text("", encoding="utf-8")
        self.assertTrue(switches[0].is_set())

    # -- Diagnose: welche Quelle war es? --

    def test_the_reported_source_distinguishes_global_from_bot_specific(self):
        """
        Wenn alle vier Bots gleichzeitig stoppen, ist "warum?" die erste
        Frage - und "jemand hat STOP_ALL angelegt" ist eine andere
        Antwort als "dieser eine Bot hat seine eigene STOP-Datei".
        """
        switch = self._switches()[0]
        self.global_file.write_text("", encoding="utf-8")

        source = switch.triggered_by()
        self.assertIsNotNone(source)
        self.assertIn(GLOBAL_KILL_SWITCH_NAME, source)
        self.assertIn("alle vier", source)

        with self.assertRaises(BotHalted) as ctx:
            switch.check()
        self.assertIn(GLOBAL_KILL_SWITCH_NAME, str(ctx.exception))

    def test_bot_specific_source_is_named_as_such(self):
        switch = self._switches()[1]  # Grid
        (self.tmp_path / "STOP_GRID").write_text("", encoding="utf-8")

        source = switch.triggered_by()
        self.assertIn("STOP_GRID", source)
        self.assertNotIn(GLOBAL_KILL_SWITCH_NAME, source)

    def test_no_source_when_nothing_is_set(self):
        self.assertIsNone(self._switches()[0].triggered_by())

    def test_environment_variable_source_is_named(self):
        os.environ["DCA_BOT_HALT"] = "true"
        source = self._switches()[0].triggered_by()
        self.assertIn("DCA_BOT_HALT", source)


if __name__ == "__main__":
    unittest.main()

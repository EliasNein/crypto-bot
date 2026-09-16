"""
Tests fuer den Notaus (Sicherheitsreview-Punkt W1, siehe
dca_bot/risk.py, KillSwitch).

Der Befund: `KillSwitch.is_set()` las nur `os.getenv()`. Die
Prozess-Umgebung wird beim Start einmalig aus der `.env` befuellt -
`DCA_BOT_HALT=true` nachtraeglich in die Datei zu schreiben hatte
deshalb keinerlei Wirkung, bis der Bot neu startete. README und
`.env.example` beschrieben diesen Weg aber als gleichwertige
Alternative zur STOP-Datei. Ein Notaus, der nicht ausloest, ist die
schlechteste Sorte Sicherheitsmechanismus, weil man sich darauf
verlaesst.

Getestet werden alle drei Wege einzeln, ihre ODER-Verknuepfung und das
Verhalten bei fehlender/kaputter Datei.

Kein Netzwerk, keine Zugangsdaten, temporaere Dateien - die `.env` des
Projekts wird NICHT angefasst (jeder Test bekommt eine eigene).

Ausfuehren mit:  python -m unittest tests.test_kill_switch -v
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from dca_bot.risk import BotHalted, KillSwitch

ENV_VAR = "TEST_BOT_HALT"


class KillSwitchTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self._tmpdir.name)
        self.stop_file = tmp / "STOP_TEST"
        self.env_file = tmp / ".env"
        self.env_file.write_text("SONSTIGE_EINSTELLUNG=egal\n", encoding="utf-8")
        # Der globale Notaus zeigt im Betrieb fest auf
        # <Projektwurzel>/STOP_ALL. Hier wird er auf einen temporaeren
        # Pfad umgebogen, sonst faerbt eine echte, im Projekt angelegte
        # STOP_ALL-Datei diese gesamte Suite rot - und zwar mit einer
        # Meldung, die nicht verraet, warum.
        self.global_stop_file = tmp / "STOP_ALL"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_switch(self) -> KillSwitch:
        return KillSwitch(
            str(self.stop_file),
            env_var_name=ENV_VAR,
            env_file=self.env_file,
            global_file=self.global_stop_file,
        )

    def _write_env(self, content: str) -> None:
        """
        Schreibt die .env und stellt sicher, dass sich die Signatur
        (mtime+Groesse) aendert - auf schnellen Rechnern koennen zwei
        Schreibvorgaenge sonst in dieselbe Zeitaufloesung fallen.
        """
        self.env_file.write_text(content, encoding="utf-8")
        os.utime(self.env_file, (time.time() + 1, time.time() + 1))

    # -- Grundzustand --

    def test_not_set_by_default(self):
        self.assertFalse(self._make_switch().is_set())

    # -- Weg 1: Notaus-Datei --

    def test_stop_file_triggers(self):
        switch = self._make_switch()
        self.stop_file.write_text("", encoding="utf-8")
        self.assertTrue(switch.is_set())

    # -- Weg 2: Prozess-Umgebung --

    def test_process_environment_triggers(self):
        switch = self._make_switch()
        with mock.patch.dict(os.environ, {ENV_VAR: "true"}):
            self.assertTrue(switch.is_set())

    # -- Weg 3: die .env, live (W1) --

    def test_env_file_written_after_start_takes_effect(self):
        """
        Kern von W1: die Instanz existiert bereits, die Datei aendert
        sich danach. Faellt gegen den alten Code um.
        """
        switch = self._make_switch()
        self.assertFalse(switch.is_set())

        self._write_env(f"{ENV_VAR}=true\n")

        self.assertTrue(
            switch.is_set(),
            "Nachtraeglich gesetztes *_HALT muss ohne Neustart wirken",
        )

    def test_check_raises_after_env_file_change(self):
        switch = self._make_switch()
        switch.check()  # darf nicht werfen

        self._write_env(f"{ENV_VAR}=true\n")

        with self.assertRaises(BotHalted):
            switch.check()

    def test_cached_value_is_refreshed_when_file_changes_back(self):
        """
        Der mtime-Waechter darf nicht nur in eine Richtung greifen -
        sonst bliebe ein einmal gelesener Halt fuer immer stehen.
        """
        switch = self._make_switch()
        self._write_env(f"{ENV_VAR}=true\n")
        self.assertTrue(switch.is_set())

        self._write_env(f"{ENV_VAR}=false\n")
        self.assertFalse(switch.is_set())

    def test_only_the_own_variable_counts(self):
        """Der Grid-Notaus darf den DCA-Bot nicht stoppen."""
        switch = self._make_switch()
        self._write_env("EIN_ANDERER_BOT_HALT=true\n")
        self.assertFalse(switch.is_set())

    def test_value_is_case_insensitive_and_trimmed(self):
        switch = self._make_switch()
        self._write_env(f'{ENV_VAR}="  TRUE  "\n')
        self.assertTrue(switch.is_set())

    # -- Robustheit: dieser Weg darf nie selbst zur Fehlerquelle werden --

    def test_missing_env_file_is_harmless(self):
        switch = self._make_switch()
        self.env_file.unlink()
        self.assertFalse(switch.is_set())

    def test_missing_env_file_does_not_disable_the_other_paths(self):
        switch = self._make_switch()
        self.env_file.unlink()
        self.stop_file.write_text("", encoding="utf-8")
        self.assertTrue(switch.is_set())

    def test_unreadable_env_file_does_not_raise(self):
        switch = self._make_switch()
        self._write_env("das ist \x00 kein gueltiges env-format\n")
        # Egal wie dotenv das interpretiert - es darf nicht werfen.
        self.assertIsInstance(switch.is_set(), bool)

    # -- Die ODER-Verknuepfung ist bewusst asymmetrisch --

    def test_env_file_false_does_not_override_stop_file(self):
        """
        Ausloesen leicht, versehentliches Aufheben schwer: ein `false` in
        der .env darf eine vorhandene Notaus-Datei NICHT entkraeften.
        """
        switch = self._make_switch()
        self._write_env(f"{ENV_VAR}=false\n")
        self.stop_file.write_text("", encoding="utf-8")
        self.assertTrue(switch.is_set())

    def test_env_file_false_does_not_override_process_environment(self):
        switch = self._make_switch()
        self._write_env(f"{ENV_VAR}=false\n")
        with mock.patch.dict(os.environ, {ENV_VAR: "true"}):
            self.assertTrue(switch.is_set())

    # -- Keine Nebenwirkungen auf die Prozess-Umgebung --

    def test_process_environment_is_never_modified(self):
        """
        Bewusst dotenv_values() statt load_dotenv(override=True): der
        Notaus-Check darf keine anderen Einstellungen umbiegen, etwa ein
        in der systemd-Unit erzwungenes *_BOT_ENABLE_TRADING=false.
        """
        switch = self._make_switch()
        self._write_env(f"{ENV_VAR}=true\nBOT_ENABLE_TRADING_TESTWERT=aus_env_datei\n")

        switch.is_set()

        self.assertIsNone(os.environ.get("BOT_ENABLE_TRADING_TESTWERT"))
        self.assertIsNone(os.environ.get(ENV_VAR))


if __name__ == "__main__":
    unittest.main()

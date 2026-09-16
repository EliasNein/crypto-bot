"""
Tests fuer den Schutz gegen einen doppelten Bot-Start
(Sicherheitsreview-Punkt W4, siehe dca_bot/process_lock.py).

Laeuft derselbe Bot zweimal (z.B. manueller Aufruf neben dem laufenden
systemd-Service), lesen und schreiben beide dieselbe Ledger-Datei. Alle
drei Ledger arbeiten nach dem Muster "komplett lesen, Eintrag anhaengen,
komplett zurueckschreiben" - zwei Prozesse ueberschreiben sich dabei
gegenseitig Eintraege (Lost Update). Der sichtbare Schaden ist derselbe
wie bei K2: ein real ausgefuehrter Trade steht am Ende nicht im Ledger.

Die Tests laufen auf Linux (VPS/Homeserver) wie auf Windows
(Entwicklungsrechner) - das Modul waehlt intern fcntl bzw. msvcrt, die
Semantik ist dieselbe. Zwei ProcessLock-Instanzen im selben Prozess
oeffnen die Datei getrennt und konkurrieren deshalb echt miteinander.

Ausfuehren mit:  python -m unittest tests.test_process_lock -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from dca_bot.process_lock import BotAlreadyRunning, ProcessLock


class ProcessLockTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        # Bewusst in einem Unterverzeichnis, das noch nicht existiert -
        # im Livebetrieb liegt das Lockfile in data/, das beim ersten
        # Start eines frischen Deployments ebenfalls fehlen kann.
        self.lock_file = str(Path(self._tmpdir.name) / "data" / "dca_bot.lock")
        self._locks: list[ProcessLock] = []

    def tearDown(self) -> None:
        for lock in self._locks:
            lock.release()
        self._tmpdir.cleanup()

    def _make_lock(self, bot_name: str = "dca") -> ProcessLock:
        lock = ProcessLock(self.lock_file, bot_name)
        self._locks.append(lock)
        return lock

    def test_first_acquisition_succeeds(self):
        lock = self._make_lock()
        lock.acquire()
        self.assertTrue(Path(self.lock_file).exists())

    def test_second_acquisition_is_refused(self):
        """
        Der Kern von W4: der zweite Start kommt nicht durch - und zwar
        mit einer Exception, nicht mit einem Rueckgabewert, den ein
        Aufrufer uebersehen koennte.
        """
        self._make_lock().acquire()

        with self.assertRaises(BotAlreadyRunning) as ctx:
            self._make_lock().acquire()

        message = str(ctx.exception)
        self.assertIn("laeuft bereits", message)
        # Die Meldung muss den Weg zur Ursache zeigen, nicht nur "Fehler".
        self.assertIn("systemctl", message)
        self.assertIn(self.lock_file, message)

    def test_lock_is_reusable_after_release(self):
        """
        Wichtig fuer den Neustart nach einem Absturz: das Lock haengt am
        Dateideskriptor, nicht an der Existenz der Datei. Eine
        liegengebliebene .lock-Datei darf keinen Neustart blockieren -
        sonst bliebe der Bot nach einem `kill -9` dauerhaft unten.
        """
        first = self._make_lock()
        first.acquire()
        first.release()

        second = self._make_lock()
        second.acquire()  # darf nicht werfen
        self.assertTrue(Path(self.lock_file).exists())

    def test_stale_lock_file_does_not_block(self):
        """
        Gegenprobe zur PID-Datei-Loesung: eine vorhandene Datei mit einer
        fremden PID darf den Start nicht verhindern, solange sie niemand
        gesperrt haelt.
        """
        path = Path(self.lock_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("999999", encoding="utf-8")

        self._make_lock().acquire()  # darf nicht werfen

    def test_own_pid_is_written_for_diagnosis(self):
        """
        Die PID ist reine Diagnose (wer haelt das Lock gerade?), kein
        Sperrmechanismus - das macht das Lock selbst.

        Gelesen wird erst NACH dem Freigeben: unter Windows sperrt
        msvcrt.locking() den Bereich verbindlich, ein Lesen durch einen
        zweiten Dateizugriff scheitert dort mit PermissionError. Auf
        Linux (dem Zielsystem) ist flock advisory und das Lesen ginge
        auch waehrend des Locks - der spaetere Zeitpunkt funktioniert
        einfach auf beiden.
        """
        lock = self._make_lock()
        lock.acquire()
        lock.release()

        self.assertEqual(
            Path(self.lock_file).read_text(encoding="utf-8").strip(), str(os.getpid())
        )

    def test_different_bots_do_not_block_each_other(self):
        """
        Die vier Bots sollen weiterhin parallel laufen - jeder hat sein
        eigenes Lockfile, so wie er sein eigenes Ledger und seinen
        eigenen Notaus hat.
        """
        grid_lock_file = str(Path(self._tmpdir.name) / "data" / "grid_bot.lock")

        self._make_lock("dca").acquire()
        other = ProcessLock(grid_lock_file, "grid")
        self._locks.append(other)
        other.acquire()  # darf nicht werfen

    def test_release_without_acquire_is_harmless(self):
        self._make_lock().release()

    def test_double_release_is_harmless(self):
        lock = self._make_lock()
        lock.acquire()
        lock.release()
        lock.release()

    def test_context_manager_releases_on_exit(self):
        with ProcessLock(self.lock_file, "dca"):
            with self.assertRaises(BotAlreadyRunning):
                self._make_lock().acquire()

        # Nach dem Block ist das Lock wieder frei.
        self._make_lock().acquire()


if __name__ == "__main__":
    unittest.main()

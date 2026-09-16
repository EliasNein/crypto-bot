"""
Schutz gegen einen versehentlichen doppelten Bot-Start
(Sicherheitsreview-Punkt W4).

Problem: Startet jemand einen Bot manuell, waehrend derselbe Bot bereits
als systemd-Service laeuft, lesen und schreiben beide dieselbe
Ledger-Datei. Die Ledger arbeiten alle nach dem Muster "komplett lesen,
Eintrag anhaengen, komplett zurueckschreiben" (siehe risk.py,
grid_risk.py, trend_risk.py) - zwei Prozesse ueberschreiben sich dabei
gegenseitig Eintraege (Lost Update). Der Schaden ist derselbe wie bei
K2, nur aus einer anderen Richtung: ein real ausgefuehrter Trade steht
am Ende nicht im Ledger.

Betroffen sind alle vier Prozesse. Der Allocator platziert zwar nie
Orders, wuerde aber mit einem zweiten Exemplar seine State-Datei
ueberschreiben - dieselbe Fehlerklasse.

Bewusst ein Lock auf dem DATEIDESKRIPTOR, kein "Datei existiert
bereits"-Test:

- Das Betriebssystem gibt das Lock beim Prozessende automatisch frei,
  auch bei `kill -9` oder einem Stromausfall. Eine liegengebliebene
  .lock-Datei blockiert damit KEINEN Neustart - genau der Fehler, an dem
  naive PID-Datei-Loesungen scheitern und der bei einem Trading-Bot
  besonders teuer waere (der Bot bliebe nach einem Absturz dauerhaft
  unten, ohne dass jemand die Ursache sieht).
- Es gibt kein Zeitfenster zwischen Pruefen und Anlegen, in dem zwei
  gleichzeitig startende Prozesse beide durchkaemen.

Plattform: `fcntl.flock` auf Linux (VPS und Homeserver), `msvcrt.locking`
auf Windows (Entwicklungsrechner). Gleiche Semantik ueber dieselbe API -
ein reiner `import fcntl` wuerde jeden Testlauf auf dem Desktop-PC
zerlegen.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("dca_bot")

if os.name == "nt":  # pragma: no cover - plattformabhaengig
    import msvcrt

    def _try_lock(file_handle) -> None:
        file_handle.seek(0)
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(file_handle) -> None:
        file_handle.seek(0)
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)

else:  # pragma: no cover - plattformabhaengig
    import fcntl

    def _try_lock(file_handle) -> None:
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(file_handle) -> None:
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


class BotAlreadyRunning(Exception):
    """
    Ein anderer Prozess desselben Bots haelt bereits das Lock.

    Eigene Exception statt eines Rueckgabewerts, damit ein uebersehener
    Rueckgabewert nicht dazu fuehrt, dass der zweite Bot doch
    weiterlaeuft.
    """


class ProcessLock:
    """
    Exklusives Lock pro Bot, gehalten fuer die gesamte Prozesslaufzeit.

    Wird in den `main*.py` direkt nach dem Logging-Setup erworben - also
    bevor irgendein Zustand gelesen oder eine Verbindung aufgebaut wird.
    Freigegeben wird bewusst nicht explizit am Ende: das Betriebssystem
    erledigt das beim Prozessende zuverlaessiger, als es ein
    `finally`-Block koennte (der bei `kill -9` gar nicht mehr laeuft).
    `release()` existiert trotzdem - fuer Tests und fuer den Fall, dass
    ein Aufrufer das Lock bewusst frueher abgeben will.
    """

    def __init__(self, lock_file: str, bot_name: str):
        self._path = Path(lock_file)
        self._bot_name = bot_name
        self._handle = None

    @property
    def path(self) -> Path:
        return self._path

    def acquire(self) -> None:
        """
        Erwirbt das Lock oder wirft `BotAlreadyRunning`.

        In die Datei wird die eigene PID geschrieben - nicht als
        Sperrmechanismus (das macht das Lock selbst), sondern damit die
        Fehlermeldung des zweiten Starts sagen kann, WER gerade laeuft.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # "a+" statt "w": ein bereits laufender Prozess haelt das Lock
        # auf dieser Datei, ihr Inhalt darf beim Oeffnen nicht schon
        # weggeworfen werden - sonst wuerde der zweite Start die PID des
        # ersten loeschen, noch bevor er am Lock scheitert.
        handle = self._path.open("a+", encoding="utf-8")
        # PID VOR dem Lock-Versuch lesen: unter Windows sperrt
        # msvcrt.locking() den Bereich verbindlich, ein Lesen danach
        # scheitert. Auf Linux (VPS/Homeserver) ist flock rein
        # advisory, dort ginge beides - der frühere Zeitpunkt
        # funktioniert einfach auf beiden.
        other = self._read_pid(handle)
        try:
            _try_lock(handle)
        except OSError:
            handle.close()
            raise BotAlreadyRunning(
                f"Der {self._bot_name}-Bot laeuft bereits"
                f"{f' (PID {other})' if other else ''} und haelt "
                f"'{self._path}'. Ein zweiter Prozess wuerde denselben Zustand "
                "lesen und schreiben und sich mit dem ersten gegenseitig "
                "Eintraege ueberschreiben. Laeuft er als systemd-Service? "
                "Pruefen mit 'systemctl status <dienstname>' oder "
                "'ps aux | grep dca_bot'."
            ) from None

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle
        logger.info(
            "Prozess-Lock fuer den %s-Bot erworben (%s, PID %d).",
            self._bot_name,
            self._path,
            os.getpid(),
        )

    @staticmethod
    def _read_pid(handle) -> str | None:
        try:
            handle.seek(0)
            content = handle.read().strip()
        except OSError:
            return None
        return content or None

    def release(self) -> None:
        """Gibt das Lock frei. Mehrfaches Aufrufen ist unschaedlich."""
        if self._handle is None:
            return
        try:
            _unlock(self._handle)
        except OSError:
            # Beim Prozessende raeumt das Betriebssystem ohnehin auf -
            # ein Fehler hier darf einen sauberen Shutdown nicht stoeren.
            pass
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "ProcessLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

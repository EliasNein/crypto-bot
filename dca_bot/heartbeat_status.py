"""
Heartbeat-Status als kleine JSON-Datei fuer externe Betrachter.

Der Zeitpunkt des letzten erfolgreichen Zyklus lebt seit Prioritaet 2
der Code-Ueberpruefung (25.09.2026) korrekt als `last_cycle_at` in der
Schleife jedes Bots - aber nur im Prozessspeicher. Die separate
Dashboard-App (crypto-bot-app) liest ausschliesslich Dateien aus
`data/` und importiert keinen Bot-Code; damit sie den Status zeigen
kann, schreibt jeder Bot ihn zusaetzlich auf die Platte:

    {"last_successful_cycle": "<ISO-Zeitstempel oder null>",
     "last_cycle_attempt": "<ISO-Zeitstempel>",
     "consecutive_failures": <Zahl>}

Drei Regeln, alle bewusst:

- **Eine Datei pro Bot** (`data/heartbeat_<bot>.json`), keine
  gemeinsame. Vier unabhaengige Prozesse, die dieselbe Datei
  beschreiben, waeren ein Lost-Update-Risiko - dasselbe Prinzip wie
  "jeder Bot hat sein eigenes Ledger".
- **Nur schreiben, nie lesen.** Kein Bot liest seine eigene oder eine
  fremde Heartbeat-Datei; es gibt hier deshalb gar keine Lesefunktion.
  Die Dateien sind reine Ausgabe, jede Rueckkopplung in die Bot-Logik
  waere eine neue Kopplung zwischen Prozessen, die sonst getrennt sind.
  Folge: Die Werte gelten pro Prozesslauf. Nach einem Neustart beginnt
  alles wieder bei null/0, genau wie beim Telegram-Heartbeat.
- **Keine Rueckwirkung auf den Bot.** Ein Fehler beim Schreiben (volle
  Platte, fehlende Rechte) wird abgefangen und nur geloggt - einmal pro
  Fehlerserie, damit der Grid-Bot bei einem Plattenproblem nicht alle 5
  Minuten dieselbe Warnung schreibt. Handel, Notaus, Reconciliation und
  Telegram laufen davon unberuehrt weiter.

Was als Erfolg zaehlt, entscheidet dieses Modul nicht: Aufgerufen wird
es im selben `except`/`else` der Schleife, das auch `last_cycle_at`
setzt, und bekommt genau diesen Wert. Beim Notaus (`BotHalted`) wird
nichts geschrieben - das ist weder Erfolg noch Fehlschlag, sondern das
Ende des Prozesses.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path


def _iso(stamp: datetime | None) -> str | None:
    return stamp.isoformat() if stamp is not None else None


class HeartbeatStatusWriter:
    """
    Schreibt nach jedem Zyklus den Heartbeat-Status in `path`.

    Der Zaehler `consecutive_failures` lebt nur im Prozessspeicher (wie
    `_failed_cycles` in cycle_errors.py) und wird bei jedem Erfolg auf 0
    gesetzt.
    """

    def __init__(self, path: str, logger: logging.Logger):
        self._path = Path(path)
        self._logger = logger
        self._consecutive_failures = 0
        self._write_failing = False

    def record_success(self, last_successful_cycle: datetime) -> None:
        """Nach einem erfolgreichen Zyklus - Versuch und Erfolg fallen zusammen."""
        self._consecutive_failures = 0
        self._write(last_successful_cycle, last_successful_cycle)

    def record_failure(
        self, attempted_at: datetime, last_successful_cycle: datetime | None
    ) -> None:
        """
        Nach einem gescheiterten Zyklus. `last_successful_cycle` ist der
        unveraenderte Wert aus der Schleife (None, wenn es in diesem
        Prozesslauf noch keinen erfolgreichen Zyklus gab).
        """
        self._consecutive_failures += 1
        self._write(last_successful_cycle, attempted_at)

    def _write(
        self, last_successful_cycle: datetime | None, attempted_at: datetime
    ) -> None:
        data = {
            "last_successful_cycle": _iso(last_successful_cycle),
            "last_cycle_attempt": _iso(attempted_at),
            "consecutive_failures": self._consecutive_failures,
        }
        try:
            # ATOMAR wie die Ledger (W5): temporaere Datei, fsync,
            # os.replace. Ein Absturz mittendrin laesst die alte Datei
            # vollstaendig stehen - die Dashboard-App liest nie einen
            # halb geschriebenen Stand.
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_name(self._path.name + ".tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._path)
        except Exception as exc:
            # Bewusst breit: Diese Datei ist reine Ausgabe fuer externe
            # Betrachter, ein Fehler hier darf den Zyklus nie beeinflussen.
            if not self._write_failing:
                self._logger.warning(
                    "Heartbeat-Statusdatei %s konnte nicht geschrieben werden: %s "
                    "(weitere Fehlschlaege bis zum naechsten Erfolg nur still).",
                    self._path,
                    exc,
                )
            self._write_failing = True
        else:
            self._write_failing = False

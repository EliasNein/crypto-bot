"""
Mengenlimit fuer Telegram-Meldungen ueber fehlgeschlagene Zyklen.

Genutzt von den beiden Prozessen mit kurzem Takt: Grid-Bot (alle 5
Minuten) und Allocator (stuendlich). DCA und Trend laufen einmal am Tag,
dort ist jeder Fehlschlag ohnehin hoechstens eine Meldung pro Tag.

Hintergrund (Code-Ueberpruefung vom 25.09.2026, Prioritaet 3): Bis dahin
ging jeder fehlgeschlagene Zyklus per Telegram raus - bei einer
laengeren Stoerung (Internet weg, Testnet down) beim Grid-Bot also
zwoelf identische Meldungen pro Stunde, beim Allocator eine pro Stunde.
Konkreter Anlass ist die naechtliche Zwangstrennung des
Homeserver-Anschlusses (trading-bot-projekt.md 6g): heute eine Meldung
pro Nacht, bei einer echten Stoerung aber genau das Muster, das man
nicht will.

Die Klasse stand zuerst in main_grid.py und ist hierher umgezogen, als
der Allocator sie ebenfalls bekam: Dieselbe Regel zweimal zu
implementieren waere der als N3 kritisierte Weg (vgl.
safe_startup_reconciliation in pending_orders.py).
"""

from __future__ import annotations

import logging

from .notifier import send_notification


class CycleErrorNotifier:
    """
    Regel: Die erste Meldung eines Fehlertyps geht per Telegram raus,
    weitere desselben Typs nur noch ins Log - bis ein Zyklus wieder
    erfolgreich war, dann ist alles zurueckgesetzt. Gleiches Muster wie
    `_report_failed_sell` in grid_strategy.py ("einmal pro Lauf"), nur
    mit Reset bei Erfolg: ein Fehler, der naechste Nacht wiederkommt, ist
    ein neues Ereignis und soll wieder gemeldet werden.

    "Fehlertyp" ist die Exception-Klasse. Ein NEUER Typ mitten in einer
    Fehlerserie wird gemeldet - aus einem Timeout wird dann z.B. ein
    Verbindungsfehler, und das ist eine andere Information.

    Bewusst keine Entwarnung per Telegram nach der Erholung: ob ein Bot
    wieder arbeitet, zeigt der Heartbeat-Zeitstempel (letzter
    ERFOLGREICHER Zyklus, siehe heartbeat.py), und im Log steht die
    Erholung mit der Zahl der Fehlzyklen.

    Der Zustand lebt nur im Prozessspeicher, wie bei
    `_failed_sell_notified`.

    `tag` ist der Telegram-Marker des Prozesses ("[GRID-FEHLER]",
    "[ALLOCATOR-FEHLER]"), `cycle_label` steht im Meldungstext
    ("Grid-Zyklus", "Allocator-Zyklus").
    """

    def __init__(self, logger: logging.Logger, tag: str, cycle_label: str):
        self._logger = logger
        self._tag = tag
        self._cycle_label = cycle_label
        self._notified_types: set[type] = set()
        self._failed_cycles = 0

    def report_failure(self, exc: Exception) -> None:
        """Nach einem fehlgeschlagenen Zyklus aufrufen (das Log hat der
        Aufrufer bereits geschrieben, inklusive Traceback)."""
        self._failed_cycles += 1
        error_type = type(exc)
        if error_type in self._notified_types:
            self._logger.warning(
                "%s Gleichartiger Fehler (%s), %d. Fehlzyklus in Folge - "
                "bereits per Telegram gemeldet, bis zum naechsten "
                "erfolgreichen Zyklus nur im Log.",
                self._tag,
                error_type.__name__,
                self._failed_cycles,
            )
            return

        self._notified_types.add(error_type)
        send_notification(
            f"{self._tag} Unerwarteter Fehler im {self._cycle_label}: {exc} "
            f"(weitere {error_type.__name__}-Fehler bis zum naechsten "
            "erfolgreichen Zyklus nur im Log)"
        )

    def report_success(self) -> None:
        """Nach einem erfolgreichen Zyklus aufrufen: hebt die Sperre auf."""
        if self._failed_cycles:
            self._logger.info(
                "%s wieder erfolgreich nach %d Fehlzyklus/-zyklen in Folge - "
                "Zyklusfehler werden wieder per Telegram gemeldet.",
                self._cycle_label,
                self._failed_cycles,
            )
        self._notified_types.clear()
        self._failed_cycles = 0

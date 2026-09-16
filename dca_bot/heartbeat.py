"""
Lebenszeichen aller vier Bots (Sicherheitsreview-Punkt W13).

Problem: Ein abgestuerzter oder haengender Bot faellt bisher nur dadurch
auf, dass keine Nachrichten mehr kommen - und ausbleibende Nachrichten
uebersieht man leicht, gerade bei Bots, die von sich aus tagelang nichts
zu melden haben (der Trend-Bot handelt oft wochenlang nicht). Ein
stiller Grid-Bot kann bedeuten "keine Stufe durchquert" oder "seit
Dienstag tot", und von aussen sieht beides identisch aus.

Deshalb sendet jeder Bot einmal pro Intervall eine Nachricht, auch wenn
nichts passiert ist. Bewusst redundant zur DCA-Tageszusammenfassung
(die bleibt unveraendert): die ist DCA-spezifisch und haengt an einem
Kalendertagswechsel, das hier ist einheitlich fuer alle vier Prozesse
und unabhaengig von botspezifischen Ereignissen.

Bewusst KEIN Heartbeat beim Prozessstart: ein Bot in einer
Neustartschleife wuerde sonst im Minutentakt "ich lebe" melden - genau
dann, wenn er es nicht tut. Der erste Heartbeat kommt nach einem vollen
Intervall Laufzeit, und ein Ausbleiben ist damit ein echtes Signal.

Der Zustand liegt nur im Prozessspeicher (wie `last_summary_date` in
main.py): eine eigene Zustandsdatei waere mehr Mechanik, als ein
Lebenszeichen rechtfertigt.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .notifier import send_notification
from .version import get_code_version

logger = logging.getLogger("dca_bot")


class Heartbeat:
    """
    Sendet hoechstens alle `interval_hours` ein Lebenszeichen.

    `interval_hours <= 0` schaltet den Heartbeat ab.

    Die Code-Version wird EINMAL beim Erzeugen ermittelt, nicht pro
    Nachricht: `get_code_version()` startet einen git-Subprozess, und
    der Commit-Hash aendert sich waehrend eines Prozesslaufs ohnehin
    nicht.
    """

    def __init__(self, bot_name: str, interval_hours: float):
        self._bot_name = bot_name
        self._interval = timedelta(hours=interval_hours) if interval_hours > 0 else None
        self._version = get_code_version()
        # Auf "jetzt" initialisiert - siehe Modul-Docstring: kein
        # Heartbeat beim Start.
        self._last_sent = datetime.now(timezone.utc)

        if self._interval is None:
            logger.info("Heartbeat deaktiviert (Intervall <= 0).")
        else:
            logger.info(
                "Heartbeat aktiv: alle %.1f Stunden ein Lebenszeichen fuer %s.",
                interval_hours,
                bot_name,
            )

    def maybe_send(self, last_cycle_at: datetime | None = None) -> None:
        """
        Sendet ein Lebenszeichen, falls das Intervall abgelaufen ist.

        Wird nach jedem Zyklus aufgerufen; die Pruefung ist billig, das
        Senden passiert hoechstens einmal pro Intervall. Beim Grid-Bot
        (5-Minuten-Takt) bedeutet das eine Nachricht pro Tag, nicht eine
        alle fuenf Minuten.

        `last_cycle_at` ist der Zeitpunkt des letzten abgeschlossenen
        Zyklus. Er steht mit in der Nachricht, weil "Prozess laeuft" und
        "Prozess arbeitet" nicht dasselbe sind: haengt ein Bot in einem
        Netzwerk-Timeout fest, laeuft er zwar, aber der Zeitstempel
        bleibt stehen - und genau das faellt in der Nachricht auf.
        """
        if self._interval is None:
            return

        now = datetime.now(timezone.utc)
        if now - self._last_sent < self._interval:
            return
        self._last_sent = now

        if last_cycle_at is None:
            cycle_text = "noch kein abgeschlossener Zyklus"
        else:
            cycle_text = last_cycle_at.strftime("%Y-%m-%d %H:%M UTC")

        message = (
            f"[HEARTBEAT] {self._bot_name} laeuft, Version {self._version}, "
            f"letzter Zyklus {cycle_text}"
        )
        logger.info("%s", message)
        send_notification(message)

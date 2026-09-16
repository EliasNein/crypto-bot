"""
Gemeinsame Berechnungslogik für den Kapital-Allocator (stufenlose
Umschichtung zwischen DCA-Bot und Trend-Following-Bot je nach
Trendstärke).

WICHTIG: Dieses Modul wird sowohl vom Live-Allocator (allocator.py) als
auch vom Backtest (allocator_backtest.py) importiert - gleiches Prinzip
wie trend_signals.py für den Trend-Bot. Außerdem lesen strategy.py (DCA)
und trend_strategy.py (Trend) `read_allocation_fraction()` von hier, um
die vom Allocator geschriebene Zuteilung zu konsumieren, OHNE dass DCA
oder Trend irgendetwas über den Allocator selbst wissen müssen - ist die
State-Datei nicht gesetzt/vorhanden/lesbar, verhalten sie sich exakt wie
ohne Allocator (siehe Docstrings dort).

Alle Funktionen hier sind rein (keine Seiteneffekte, kein eigener
Zustand) bis auf `read_allocation_fraction()`, die lediglich liest.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("dca_bot")

# Wie viele Allocator-Zyklen eine Zuteilung alt sein darf, bevor sie als
# veraltet gilt (Sicherheitsreview-Punkt W10). Drei Zyklen lassen Raum
# fuer einen uebersprungenen Lauf oder eine kurze Stoerung, schlagen aber
# zuverlaessig an, wenn der Allocator-Prozess gestorben ist.
STALE_ALLOCATION_INTERVALS = 3

# Fallback, wenn die State-Datei ihr eigenes Intervall nicht mitschreibt
# (Dateien aus der Zeit vor diesem Fix). Entspricht dem Default von
# ALLOCATOR_INTERVAL_MINUTES (60) mal STALE_ALLOCATION_INTERVALS.
DEFAULT_STALE_AFTER_MINUTES = 180.0

# Zuteilung, auf die bei einer veralteten State-Datei zurueckgefallen
# wird: 0.0 Trend-Anteil, also 100% DCA. Bewusst NICHT None - None hiesse
# "kein Allocator", und der Trend-Bot wuerde dann seinen VOLLEN
# Einstiegsbetrag verwenden. 0.0 laesst den DCA-Bot regulaer kaufen und
# den Trend-Bot den Einstieg ueberspringen (unterhalb
# MIN_EFFECTIVE_QUOTE_AMOUNT) - die konservativere Richtung, wenn niemand
# mehr weiss, wie stark der Trend gerade ist.
STALE_ALLOCATION_FALLBACK = 0.0

# Unterhalb dieses Betrags (Quote-Währung) wird ein durch den Allocator
# herunterskalierter Kauf/Einstieg übersprungen statt eine wirtschaftlich
# bedeutungslose Mini-Order zu platzieren (Börsen haben ohnehin ein
# Mindest-Ordervolumen). Gemeinsam für DCA- und Trend-Seite, damit beide
# denselben Schwellenwert verwenden.
MIN_EFFECTIVE_QUOTE_AMOUNT = 5.0


def derive_trend_strength(state: dict) -> float:
    """
    Wandelt den Rückgabewert von TrendSignalGenerator.feed() in eine
    gerichtete Trendstärke für die Kapitalzuteilung um: nur eine
    bestätigte AUFWÄRTS-Richtung zählt. Der Trend-Bot ist long-only - bei
    Abwärtstrend oder keiner klaren Richtung würde er ohnehin nicht
    einsteigen, also bekommt er dann auch kein zusätzliches Kapital
    zugeteilt (Stärke 0, nicht negativ).
    """
    if state["confirmed_direction"] == "up" and state["gap_pct"] is not None:
        return state["gap_pct"]
    return 0.0


def compute_target_fraction(strength: float, zero_anchor_pct: float, full_anchor_pct: float) -> float:
    """
    Lineare Interpolation der Trend-Following-Kapitalzuteilung (0.0-1.0)
    zwischen den konfigurierbaren Ankerpunkten: bei `strength <=
    zero_anchor_pct` 0% Trend-Following-Anteil (100% DCA), bei `strength
    >= full_anchor_pct` 100% Trend-Following-Anteil (0% DCA). Werte
    außerhalb der Anker werden geklemmt (clamped), kein Extrapolieren.
    """
    if full_anchor_pct <= zero_anchor_pct:
        raise ValueError(
            "full_anchor_pct muss größer als zero_anchor_pct sein "
            f"(zero={zero_anchor_pct}, full={full_anchor_pct})."
        )
    if strength <= zero_anchor_pct:
        return 0.0
    if strength >= full_anchor_pct:
        return 1.0
    return (strength - zero_anchor_pct) / (full_anchor_pct - zero_anchor_pct)


def smooth_fraction(previous_smoothed: float | None, raw_target: float, period: float) -> float:
    """
    EMA-Glättung der Zuteilung selbst (gleiche Formel wie die Preis-EMAs
    in trend_signals.py, hier auf die Zuteilungs-Prozentzahl angewandt) -
    Schutz gegen Whipsaw bei einer stufenlosen Kurve, wo es (anders als
    bei diskreten Stufen) keinen festen Punkt zum "Bestätigen" gibt.

    `previous_smoothed=None` (erster Aufruf, kein Vorwert vorhanden)
    übernimmt den Rohwert direkt, statt künstlich bei 0 zu starten.
    """
    if previous_smoothed is None:
        return raw_target
    multiplier = 2 / (period + 1)
    return previous_smoothed + (raw_target - previous_smoothed) * multiplier


def read_allocation_fraction(path: str) -> float | None:
    """
    Liest die aktuelle geglättete Trend-Following-Zuteilung (0.0-1.0) aus
    der vom Allocator geschriebenen State-Datei.

    Zwei Ausgänge, und der Unterschied zwischen ihnen ist der Kern dieser
    Funktion:

    - **`None` = "es gibt keinen Allocator".** Nur bei leerem `path`
      (Feature nicht aktiviert) oder fehlender Datei (der Allocator hat
      noch nie geschrieben - der reguläre Zustand bei einem frischen
      Deployment und in den Sekunden zwischen zwei Service-Starts). Der
      aufrufende Bot verhält sich dann exakt wie ohne Allocator, nutzt
      also 100% seines konfigurierten Betrags.
    - **`STALE_ALLOCATION_FALLBACK` (0.0) = "die Datei ist da, aber
      unbrauchbar".** Veraltet (W10), unlesbar, kaputt, ohne
      `trend_fraction` oder mit einem Wert außerhalb 0-1.

    Dass der zweite Fall NICHT `None` ergibt, ist eine bewusste
    Entscheidung und war bis zum 17.09.2026 anders: `None` heißt für den
    Trend-Bot "voller Einstiegsbetrag" und für den DCA-Bot "voller
    Kaufbetrag" - zusammen also MEHR Kapital, als die Zuteilung je
    vorgesehen hätte. Das ist die Überallokation, gegen die der Allocator
    überhaupt existiert. Genau diese Abwägung war für den Veraltet-Fall
    schon getroffen (siehe STALE_ALLOCATION_FALLBACK und
    `_allocation_is_stale`); für die kaputte Datei war sie schlicht nie
    nachgezogen worden. `0.0` lässt den DCA-Bot regulär kaufen und den
    Trend-Einstieg entfallen - die konservative Richtung.

    Die Reihenfolge der `except`-Zweige ist wichtig: `FileNotFoundError`
    ist eine Unterklasse von `OSError`. Würde der generische Zweig zuerst
    greifen, bekäme "Datei existiert nicht" den Fallback statt `None` -
    und ein frisch aufgesetzter Bot mit gesetztem Opt-in, aber noch nicht
    gestartetem Allocator, würde nie wieder Trend-Positionen eröffnen.
    Dieselbe Falle wie bei W5.
    """
    if not path:
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        # Der Allocator hat noch nie geschrieben - kein Befund.
        return None
    except (json.JSONDecodeError, OSError) as exc:
        # OSError war vor dem 17.09.2026 gar nicht gefangen: Ein
        # Rechteproblem an dieser Datei (z.B. nach einem `chmod`) hat die
        # Exception bis in execute_once() durchgereicht und damit den
        # kompletten Kaufzyklus des lesenden Bots abgebrochen - wegen
        # einer Datei, die nur die Ordergröße skalieren soll.
        logger.warning(
            "Allocator-Zuteilung in '%s' ist nicht lesbar (%s) - es wird auf "
            "%.0f%% Trend / %.0f%% DCA zurückgefallen, statt den Allocator zu "
            "ignorieren (das hieße den vollen Betrag).",
            path,
            type(exc).__name__,
            STALE_ALLOCATION_FALLBACK * 100,
            (1 - STALE_ALLOCATION_FALLBACK) * 100,
        )
        return STALE_ALLOCATION_FALLBACK

    try:
        fraction = float(data["trend_fraction"])
    except (KeyError, ValueError, TypeError):
        logger.warning(
            "Allocator-Zuteilung in '%s' enthält kein brauchbares "
            "'trend_fraction' - es wird auf %.0f%% Trend / %.0f%% DCA "
            "zurückgefallen.",
            path,
            STALE_ALLOCATION_FALLBACK * 100,
            (1 - STALE_ALLOCATION_FALLBACK) * 100,
        )
        return STALE_ALLOCATION_FALLBACK

    if not (0.0 <= fraction <= 1.0):
        logger.warning(
            "Allocator-Zuteilung in '%s' liegt mit %.4f außerhalb von 0-1 - "
            "es wird auf %.0f%% Trend / %.0f%% DCA zurückgefallen.",
            path,
            fraction,
            STALE_ALLOCATION_FALLBACK * 100,
            (1 - STALE_ALLOCATION_FALLBACK) * 100,
        )
        return STALE_ALLOCATION_FALLBACK

    if _allocation_is_stale(data, path):
        return STALE_ALLOCATION_FALLBACK
    return fraction


def _allocation_is_stale(data: dict, path: str) -> bool:
    """
    Ob die zuletzt geschriebene Zuteilung zu alt ist, um ihr noch zu
    trauen (Sicherheitsreview-Punkt W10).

    Ohne diese Prüfung blieb der letzte berechnete Wert nach einem Tod
    des Allocator-Prozesses FÜR IMMER gültig, ohne dass DCA oder Trend
    etwas davon merkten: die State-Datei liegt weiterhin da und enthält
    eine plausible Zahl. Bei einer eingefrorenen Zuteilung von z.B. 100%
    Trend hätte der DCA-Bot dauerhaft gar nicht mehr gekauft - ein
    stiller Ausfall, der erst bei der nächsten Auswertung aufgefallen
    wäre.

    Die Schwelle kommt aus der Datei selbst: der Allocator schreibt sein
    `interval_minutes` mit, hier wird es mit
    STALE_ALLOCATION_INTERVALS multipliziert. Bewusst so, statt eine
    zweite Env-Variable auf Konsumentenseite einzuführen - zwei
    getrennte Werte für dasselbe Intervall würden früher oder später
    auseinanderlaufen, und der Fehler wäre still.

    Ein fehlendes oder unlesbares `updated_at` gilt als VERALTET, nicht
    als frisch: die Datei behauptet dann nichts über ihr Alter, und in
    dieser Lage ist die konservative Annahme die richtige.
    """
    raw_updated_at = data.get("updated_at")
    if raw_updated_at is None:
        logger.warning(
            "Allocator-Zuteilung in '%s' hat kein updated_at - sie wird als "
            "veraltet behandelt (Rückfall auf 100%% DCA). Läuft der "
            "Allocator-Prozess noch?",
            path,
        )
        return True

    try:
        updated_at = datetime.fromisoformat(str(raw_updated_at))
    except (TypeError, ValueError):
        logger.warning(
            "Allocator-Zuteilung in '%s' hat ein unlesbares updated_at (%r) - "
            "sie wird als veraltet behandelt (Rückfall auf 100%% DCA).",
            path,
            raw_updated_at,
        )
        return True

    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    try:
        interval_minutes = float(data["interval_minutes"])
        if interval_minutes <= 0:
            raise ValueError
        stale_after_minutes = interval_minutes * STALE_ALLOCATION_INTERVALS
    except (KeyError, TypeError, ValueError):
        # State-Dateien aus der Zeit vor diesem Fix kennen das Feld nicht.
        stale_after_minutes = DEFAULT_STALE_AFTER_MINUTES

    age_minutes = (datetime.now(timezone.utc) - updated_at).total_seconds() / 60
    if age_minutes <= stale_after_minutes:
        return False

    logger.warning(
        "Allocator-Zuteilung in '%s' ist %.0f Minuten alt (Grenze %.0f) - der "
        "Allocator-Prozess läuft vermutlich nicht mehr. Es wird auf 100%% DCA "
        "/ 0%% Trend zurückgefallen, statt einer eingefrorenen Zahl zu "
        "vertrauen.",
        path,
        age_minutes,
        stale_after_minutes,
    )
    return True

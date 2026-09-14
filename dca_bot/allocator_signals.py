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

    Gibt None zurück, wenn `path` leer ist (Feature nicht aktiviert),
    die Datei fehlt, kaputt ist oder einen ungültigen Wert enthält - der
    aufrufende Bot fällt dann auf sein Standardverhalten (100% des
    konfigurierten Betrags) zurück. So bleiben DCA/Trend voll
    funktionsfähig, auch wenn der Allocator nie läuft oder gerade down ist.
    """
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        fraction = float(data["trend_fraction"])
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None
    if not (0.0 <= fraction <= 1.0):
        return None
    return fraction

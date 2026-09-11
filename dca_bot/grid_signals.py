"""
Gemeinsame Signal-/Entscheidungslogik für die Spot-Grid-Trading-Strategie.

WICHTIG: Dieses Modul wird sowohl von der Live-Strategie (grid_strategy.py,
grid_risk.py) als auch vom Backtest (grid_backtest.py) importiert - exakt
das gleiche Muster wie trend_signals.py für den Trend-Following-Bot (siehe
dort für die ausführliche Begründung). Zwei getrennte Implementierungen
derselben Entscheidungslogik könnten unbemerkt auseinanderlaufen, und ein
Backtest-Ergebnis würde dann nichts mehr über das tatsächliche Live-
Verhalten aussagen.

Alle Funktionen hier sind rein (keine Seiteneffekte, kein eigener
Zustand) - Client-Aufrufe, Ledger-Persistenz und Telegram-Benachrichtigungen
bleiben bewusst in grid_strategy.py/grid_risk.py.
"""

from __future__ import annotations


def compute_grid_levels(lower_limit: float, upper_limit: float, spacing_pct: float) -> list[float]:
    """
    Berechnet die Grid-Preisstufen geometrisch (prozentualer statt fixer
    Abstand): level[i+1] = level[i] * (1 + spacing_pct / 100), aufsteigend
    von lower_limit bis upper_limit.
    """
    if lower_limit <= 0 or upper_limit <= lower_limit or spacing_pct <= 0:
        raise ValueError(
            "Ungültige Grid-Parameter: lower_limit muss > 0, upper_limit > "
            "lower_limit und spacing_pct > 0 sein."
        )

    levels = [lower_limit]
    while levels[-1] * (1 + spacing_pct / 100) <= upper_limit * 1.0001:
        levels.append(levels[-1] * (1 + spacing_pct / 100))

    if len(levels) < 2:
        raise ValueError(
            "Preisspanne zu eng für den gewählten Grid-Abstand - es muss "
            "mindestens eine Kaufstufe und eine Ziel-Verkaufsstufe geben."
        )
    return levels


def find_triggered_buy_levels(
    levels: list[float],
    last_seen_price: float | None,
    price: float,
    occupied_levels: set[int],
) -> list[int]:
    """
    Ermittelt, welche Grid-Stufen der Preis seit dem letzten Zyklus
    tatsächlich durchquert hat (Crossing-Erkennung) und noch nicht durch
    eine offene Position belegt sind.

    `last_seen_price=None` (Kaltstart) liefert immer eine leere Liste -
    sonst würde ein Neustart mitten im Grid sofort JEDE Stufe oberhalb des
    Startpreises gleichzeitig kaufen, nur weil sie zufällig über dem
    aktuellen Preis liegt, nicht weil der Preis tatsächlich gerade dort
    gefallen ist.

    Halb-offenes Intervall [price, last_seen_price): der alte Referenzpreis
    wurde im vorherigen Zyklus schon "gesehen" (oder war der Kaltstart-
    Referenzpunkt ohne Handel) und soll nicht erneut zählen; der neue,
    aktuelle Preis dagegen schon.
    """
    if last_seen_price is None or price > last_seen_price:
        return []

    triggered = []
    for level_index, level_price in enumerate(levels[:-1]):
        if level_price >= last_seen_price or level_price < price:
            continue
        if level_index in occupied_levels:
            continue
        triggered.append(level_index)
    return triggered


def is_sell_target_hit(price: float, target_sell_price: float) -> bool:
    """Ob der Preis das individuelle Verkaufs-Ziel einer offenen Position erreicht hat."""
    return price >= target_sell_price


def is_trend_break_stop_loss_hit(lower_limit: float, stop_loss_pct: float, price: float) -> bool:
    """
    Trendbruch-Stop-Loss-Schwelle: löst aus, wenn der Marktpreis deutlich
    unter die Grid-Untergrenze fällt.

        Schwelle = lower_limit * (1 - stop_loss_pct / 100)
        Auslösung, wenn: price < Schwelle
    """
    if stop_loss_pct <= 0:
        return False
    threshold = lower_limit * (1 - stop_loss_pct / 100)
    return price < threshold

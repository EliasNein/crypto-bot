"""
Gemeinsame Hilfslogik für Order-Mengen und -Preise: Quantisierung auf die
echten Binance-Handelsregeln und Bereinigung um die tatsächlich
abgezogenen Handelsgebühren.

WICHTIG: Dieses Modul wird von binance_client.py (vor jeder Order) UND
von allen drei Strategien (beim Auswerten einer ausgeführten Order)
importiert - gleiches Prinzip wie grid_signals.py/trend_signals.py: die
Regel steht an genau einer Stelle, statt in mehreren Modulen leicht
unterschiedlich nachgebaut zu werden.

Alle Funktionen hier sind rein (keine Seiteneffekte, kein eigener
Zustand, kein Netzwerkzugriff). Das Abrufen der echten Handelsregeln
selbst liegt bewusst in binance_client.py (dort lebt der API-Zugang und
der Cache), hier steht nur das Rechnen damit.

Hintergrund (Sicherheitsreview-Punkt K3):

- Binance zieht die Handelsgebühr bei einem Spot-KAUF standardmäßig vom
  erhaltenen Base-Asset ab (bei BTCUSDT also in BTC). `executedQty` ist
  der Betrag VOR diesem Abzug - wer ihn ungeprüft als "verfügbare Menge"
  ins Ledger schreibt, versucht später mehr zu verkaufen, als er hat.
  Auf dem Testnet fällt das nicht auf (Gebühr dort 0), live beträfe es
  jeden einzelnen Verkaufsversuch.
- Beim VERKAUF zieht Binance die Gebühr spiegelbildlich in der
  Quote-Währung ab: `cummulativeQuoteQty` ist der BRUTTO-Erlös, der
  realisierte Gewinn also ohne Korrektur zu optimistisch.
- Mengen und Preise müssen zusätzlich auf gültige Vielfache der
  `stepSize`/`tickSize` des jeweiligen Symbols fallen, sonst lehnt die
  Börse die Order direkt ab.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

logger = logging.getLogger("dca_bot")


@dataclass(frozen=True)
class SymbolTradingRules:
    """
    Die für uns relevanten Handelsregeln eines Symbols, wie Binance sie
    über exchangeInfo meldet (siehe
    binance_client.get_symbol_trading_rules, das sie abruft und cacht).

    `base_asset`/`quote_asset` kommen bewusst direkt aus der API-Antwort
    und werden NICHT aus dem Symbolnamen abgeleitet: "BTCUSDT" per
    String-Zerlegung in "BTC" + "USDT" zu zerteilen funktioniert nur
    zufällig und geht bei Symbolen wie "ETHBTC" oder mehrdeutigen
    Präfixen schief. Gebraucht wird das, um zu entscheiden, ob eine
    gemeldete Gebühr überhaupt die gehandelte Menge betrifft.
    """

    symbol: str
    tick_size: float      # PRICE_FILTER: gültige Preis-Schrittweite
    step_size: float      # LOT_SIZE: gültige Mengen-Schrittweite
    min_notional: float   # NOTIONAL/MIN_NOTIONAL: Mindest-Ordervolumen (0 = keine Regel)
    base_asset: str       # z.B. "BTC" bei BTCUSDT - hierin wird die Kaufgebühr abgezogen
    quote_asset: str      # z.B. "USDT" bei BTCUSDT - hierin wird die Verkaufsgebühr abgezogen
    quote_precision: int  # Nachkommastellen der Quote-Währung


def _to_decimal(value: float) -> Decimal:
    """
    Wandelt einen float verlustfrei in das um, was er DARSTELLEN SOLL -
    über den str()-Umweg, nicht über Decimal(float).

    Decimal(0.1) ist 0.1000000000000000055511151231257827..., der Umweg
    über str() ergibt exakt Decimal("0.1"). Ohne das würde die
    Quantisierung genau an den Werten scheitern, die eigentlich schon
    passen (siehe Kommentar in quantize_quantity).
    """
    return Decimal(str(value))


def quantize_quantity(quantity: float, step_size: float, round_down: bool = True) -> float:
    """
    Rundet eine Menge auf ein gültiges Vielfaches der `stepSize`.

    Für VERKAUFSMENGEN immer mit `round_down=True` (Default) aufrufen:
    eine zu hohe Menge wird von der Börse abgelehnt (bzw. verkauft im
    Zweifel mehr, als die Position hergibt), eine minimal zu niedrige ist
    nur unwesentlich suboptimal. Der Fehlerfall ist also asymmetrisch,
    und die sichere Richtung ist nach unten.

    Bewusst mit Decimal statt float gerechnet: `math.floor(0.3 / 0.1) * 0.1`
    ergibt 0.2, weil 0.3 / 0.1 in Fließkomma 2.9999999999999996 ist. Eine
    Menge, die exakt auf der Schrittweite liegt, würde dadurch um eine
    ganze Stufe nach unten "korrigiert" - genau der Off-by-one, den diese
    Funktion verhindern soll.

    `step_size <= 0` bedeutet "keine Regel bekannt" und lässt den Wert
    unverändert.
    """
    if step_size <= 0:
        return quantity
    if quantity <= 0:
        return 0.0

    steps = (_to_decimal(quantity) / _to_decimal(step_size)).to_integral_value(
        rounding=ROUND_DOWN if round_down else ROUND_HALF_UP
    )
    return float(steps * _to_decimal(step_size))


def quantize_price(price: float, tick_size: float, round_down: bool = True) -> float:
    """
    Rundet einen Preis auf ein gültiges Vielfaches der `tickSize`.

    Default ebenfalls abwärts - aus demselben Grund wie bei den Mengen
    (nie mehr Genauigkeit erfinden, als die Börse zulässt). Bei Preisen
    ist die Richtung praktisch nebensächlich, da die tickSize (z.B. 0,01)
    gegenüber dem Preisniveau verschwindend klein ist; für die
    Stop-Loss-Order bedeutet Abrunden einen minimal später auslösenden
    Stop und einen minimal leichter füllbaren Limit-Preis.

    `tick_size <= 0` bedeutet "keine Regel bekannt" und lässt den Wert
    unverändert.
    """
    if tick_size <= 0:
        return price
    if price <= 0:
        return 0.0

    ticks = (_to_decimal(price) / _to_decimal(tick_size)).to_integral_value(
        rounding=ROUND_DOWN if round_down else ROUND_HALF_UP
    )
    return float(ticks * _to_decimal(tick_size))


def sum_commission(fills: object, asset: str) -> float:
    """
    Summiert die in `asset` abgerechnete Gebühr über alle Fills einer
    Order.

    Bewusst vollständig defensiv: `fills` kann fehlen (z.B. bei
    get_order()-Antworten, die keine Fills enthalten), None sein, keine
    Liste sein, und einzelne Einträge können unerwartet aussehen. In all
    diesen Fällen wird 0.0 zurückgegeben statt eine Exception zu werfen -
    diese Funktion wird NACH einer bereits ausgeführten Order aufgerufen,
    und eine Exception an dieser Stelle würde den Ledger-Eintrag für einen
    real ausgeführten Trade verhindern. Ein nicht erkannter Gebührenanteil
    ist das deutlich kleinere Übel und wird geloggt.
    """
    if not isinstance(fills, list):
        return 0.0

    total = 0.0
    for fill in fills:
        if not isinstance(fill, dict):
            continue
        if fill.get("commissionAsset") != asset:
            # Gebühr in einer anderen Währung (z.B. BNB-Rabatt) - sie
            # schmälert die erhaltene Menge dieses Assets nicht.
            continue
        try:
            total += float(fill.get("commission", 0.0))
        except (TypeError, ValueError):
            logger.warning(
                "Unlesbarer commission-Wert in einem Fill (%r) - dieser "
                "Anteil bleibt in der Gebührenkorrektur unberücksichtigt.",
                fill.get("commission"),
            )
    return total


def net_executed_quantity(order: dict, rules: SymbolTradingRules, fallback: float) -> float:
    """
    Tatsächlich verfügbare Base-Asset-Menge aus einer ausgeführten
    KAUF-Order: `executedQty` abzüglich der in Base-Asset abgerechneten
    Gebühr, danach auf ein gültiges Vielfaches der stepSize abgerundet.

    Genau dieser Wert gehört ins Ledger - er ist die Menge, die später
    verkauft bzw. per Stop-Loss-Order abgesichert werden kann. `fallback`
    greift nur, wenn die Order kein `executedQty` mitliefert.
    """
    raw_quantity = _safe_float(order.get("executedQty"), fallback)
    commission = sum_commission(order.get("fills"), rules.base_asset)

    if commission <= 0:
        return quantize_quantity(raw_quantity, rules.step_size, round_down=True)

    net_quantity = raw_quantity - commission
    if net_quantity <= 0:
        # Kann realistisch nicht vorkommen (die Gebühr ist ein Bruchteil
        # der Menge) - wäre es doch so, ist die Annahme falsch und die
        # ungekürzte Menge die ehrlichere Angabe.
        logger.warning(
            "Gebühr (%.8f %s) >= ausgeführte Menge (%.8f) - Gebührenkorrektur "
            "wird übersprungen, bitte den Fill manuell prüfen.",
            commission,
            rules.base_asset,
            raw_quantity,
        )
        return quantize_quantity(raw_quantity, rules.step_size, round_down=True)

    quantized = quantize_quantity(net_quantity, rules.step_size, round_down=True)
    logger.info(
        "Gebührenkorrektur: ausgeführt %.8f %s, Gebühr %.8f %s -> verfügbare "
        "Menge %.8f (auf stepSize %.8f abgerundet).",
        raw_quantity,
        rules.base_asset,
        commission,
        rules.base_asset,
        quantized,
        rules.step_size,
    )
    return quantized


def net_proceeds(order: dict, rules: SymbolTradingRules, fallback: float) -> float:
    """
    Tatsächlich erhaltener Quote-Betrag aus einer ausgeführten
    VERKAUFS-Order: `cummulativeQuoteQty` abzüglich der in Quote-Währung
    abgerechneten Gebühr.

    Spiegelbild zu net_executed_quantity() - ohne diese Korrektur wäre
    der ins Ledger geschriebene realisierte Gewinn systematisch um die
    Verkaufsgebühr zu optimistisch.

    Hinweis: Antworten von get_order() (z.B. beim Erkennen einer bereits
    gefüllten Stop-Loss-Order) enthalten KEINE Fills - dort bleibt die
    Gebühr mangels Daten unberücksichtigt, siehe sum_commission().
    """
    gross = _safe_float(order.get("cummulativeQuoteQty"), fallback)
    commission = sum_commission(order.get("fills"), rules.quote_asset)
    if commission <= 0:
        return gross

    net = gross - commission
    if net <= 0:
        logger.warning(
            "Gebühr (%.8f %s) >= Bruttoerlös (%.8f) - Gebührenkorrektur wird "
            "übersprungen, bitte den Fill manuell prüfen.",
            commission,
            rules.quote_asset,
            gross,
        )
        return gross

    logger.info(
        "Gebührenkorrektur Verkauf: brutto %.2f %s, Gebühr %.8f %s -> netto %.2f.",
        gross,
        rules.quote_asset,
        commission,
        rules.quote_asset,
        net,
    )
    return net


def _safe_float(value: object, fallback: float) -> float:
    """Wie float(), fällt bei fehlendem/unlesbarem Wert auf `fallback` zurück."""
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning(
            "Unlesbarer Zahlenwert in der Order-Antwort (%r) - verwende "
            "Ersatzwert %.8f.",
            value,
            fallback,
        )
        return fallback

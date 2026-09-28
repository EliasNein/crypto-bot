"""
Symbolbindung der Zustandsdateien (28.09.2026).

**Das Problem.** Binance hat fuer Kunden im EWR alle USDT-Spot-Paare
entfernt; fuer echtes Geld wird BTCEUR gehandelt (Entscheidung vom
28.09.2026, trading-bot-projekt.md 6g/6h). Fuer einen frischen Start mit
leeren Ledgern reicht dafuer die Konfiguration. Gefaehrlich war der
Versehens-Fall "neues Symbol auf altem Ledger": Grid- und Trend-Ledger,
der Allocator-Zustand und die Stop-Loss-Sperren wussten nicht, zu welchem
Paar sie gehoeren, und ein Bot haette alte Positionen still als Positionen
des neuen Paars weitergefuehrt.

**Altbestand (Entscheidung E1 vom 28.09.2026, Option c).** Eintraege aus
der Zeit vor der Symbolbindung haben kein Feld `symbol`. Sie gelten als
`LEGACY_SYMBOL` = BTCUSDT. Das ist keine Annahme, sondern die
Projektgeschichte: Jedes Ledger, das es bis zu diesem Tag gibt - Desktop,
Laptop, VPS und Homeserver -, stammt aus BTCUSDT-Laeufen (siehe 6a-6h).
Bewusst NICHT gewaehlt:

- "Fehlendes Feld gilt als das konfigurierte Symbol": Stuende beim ersten
  Start schon das neue Paar in der .env, wuerde genau der Irrtum
  festgeschrieben, gegen den diese Pruefung gebaut ist.
- Ein Stempel-Skript als Voraussetzung: Der Deploy haette dann eine
  zwingende Reihenfolge bekommen, und ein Neustart vor dem Skript liesse
  die Bots still aus.

Alte Eintraege werden auch nicht nachtraeglich gestempelt - die Regel
gilt beim Lesen, die Dateien bleiben unveraendert.

Dieses Modul ist bewusst rein und ohne Projekt-Importe: Es wird von
allocator_signals.py (das DCA und Trend vor jeder Order lesen) ebenso
gebraucht wie vom Positions-Audit.
"""

from __future__ import annotations

from collections.abc import Mapping

# Das Paar, dem ein Eintrag ohne `symbol`-Feld zugerechnet wird - siehe
# Modul-Docstring. Nicht aendern: Die Konstante beschreibt Vergangenheit.
LEGACY_SYMBOL = "BTCUSDT"


def effective_symbol(entry: object) -> str:
    """
    Das Paar, zu dem ein Eintrag gehoert.

    - Feld fehlt oder ist `None` (Altbestand): `LEGACY_SYMBOL`.
    - Feld ist ein nicht-leerer Text: dieser Text.
    - Alles andere (leerer Text, Zahl, Liste - praktisch nur durch
      manuelles Editieren): eine Darstellung des Werts, die zu keinem
      konfigurierten Symbol passt. Ein kaputtes Feld wird also nicht als
      Altbestand durchgewunken, sondern faellt bei der Pruefung auf.
    """
    value = entry.get("symbol") if isinstance(entry, Mapping) else None
    if value is None:
        return LEGACY_SYMBOL
    if isinstance(value, str) and value.strip():
        return value.strip()
    return f"<unbrauchbar: {value!r}>"


def is_legacy(entry: object) -> bool:
    """Ob ein Eintrag aus der Zeit vor der Symbolbindung stammt (kein Feld)."""
    return not isinstance(entry, Mapping) or entry.get("symbol") is None

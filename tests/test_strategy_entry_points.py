"""
Nur die Einstiegspunkte duerfen die handelnden Strategien benutzen
(Systemcheck vom 27.09.2026, W-D).

**Der Befund.** `dca_bot/test_connection.py` rief `DCAStrategy.execute_once()`
direkt auf. Bei aktivem Trading war das ein ECHTER Kauf - ohne
Prozess-Lock (W4), ohne Live-Warnung (W12), ohne initialisierten Notifier
(ein [ORDER-UNKLAR] waere ins Leere gegangen) und ohne die W2-Wartezeit.
Der Name klang nach einem harmlosen Verbindungstest. Das Skript ist
geloescht, den Verbindungstest leistet `check_orders.py` ohne Argumente,
nur lesend.

**Was dieser Test festhaelt.** Alles, was ein `main*.py` rund um einen
Zyklus aufbaut, fehlt einem Hilfsskript, das die Strategie direkt
benutzt. Deshalb darf jedes der drei Strategie-Module nur von seinem
Einstiegspunkt importiert werden. Geprueft wird ueber den Syntaxbaum,
nicht per Textsuche: `allocator.py` und `grid_backtest.py` erwaehnen die
Strategien in Kommentaren, und das ist erlaubt.

Kein Netzwerk, keine Zugangsdaten.

Ausfuehren mit:  python -m unittest tests.test_strategy_entry_points -v
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "dca_bot"

# Strategie-Modul -> der einzige Einstiegspunkt, der es importieren darf.
ALLOWED_IMPORTERS = {
    "strategy": "main.py",
    "grid_strategy": "main_grid.py",
    "trend_strategy": "main_trend.py",
}


def imported_modules(path: Path) -> set[str]:
    """Die Modulnamen (ohne Paket-Praefix), die eine Datei importiert."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level >= 1 or module.startswith("dca_bot"):
                names.add(module.removeprefix("dca_bot").lstrip("."))
                # `from . import strategy`
                if not module or module == "dca_bot":
                    names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("dca_bot."):
                    names.add(alias.name.removeprefix("dca_bot."))
    return names


class StrategyEntryPointTestCase(unittest.TestCase):
    def test_premise_the_entry_points_are_detected(self):
        """
        Ohne diese Praemisse waere der Haupttest auch dann gruen, wenn
        `imported_modules` gar nichts erkennt.
        """
        for module, entry_point in ALLOWED_IMPORTERS.items():
            with self.subTest(module=module):
                self.assertIn(module, imported_modules(PACKAGE / entry_point))

    def test_only_the_entry_points_import_a_strategy(self):
        offenders = []
        for path in sorted(PACKAGE.glob("*.py")):
            imported = imported_modules(path)
            for module, entry_point in ALLOWED_IMPORTERS.items():
                if module in imported and path.name != entry_point:
                    offenders.append(f"{path.name} importiert {module}")
        self.assertEqual(offenders, [])

    def test_test_connection_is_gone(self):
        """Der Verbindungstest ist check_orders.py ohne Argumente (README 8.4)."""
        self.assertFalse((PACKAGE / "test_connection.py").exists())


if __name__ == "__main__":
    unittest.main()

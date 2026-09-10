"""
CLI-Befehl, um eine ausgelöste Grid-Trendbruch-Stop-Loss-Pause manuell
zurückzusetzen.

Setzt sich bewusst nicht von selbst zurück (siehe Begründung in
grid_risk.py) - dieser Befehl ist der vorgesehene Weg dafür, alternativ
genügt auch das manuelle Löschen der Status-Datei (`stop_loss_state_file`
in grid_config.py, Default `data/grid_stop_loss_paused.json`).

Ausführen mit:  python -m dca_bot.reset_grid_stop_loss
"""

from __future__ import annotations

import logging

from .grid_config import load_grid_config
from .grid_risk import GridStopLoss


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config = load_grid_config()
    stop_loss = GridStopLoss(config.lower_limit, config.stop_loss_pct, config.stop_loss_state_file)
    stop_loss.reset()


if __name__ == "__main__":
    main()

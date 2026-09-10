"""
CLI-Befehl, um eine ausgelöste Trend-Stop-Loss-Pause manuell zurückzusetzen.

Setzt sich bewusst nicht von selbst zurück (siehe Begründung in
trend_risk.py) - dieser Befehl ist der vorgesehene Weg dafür, alternativ
genügt auch das manuelle Löschen der Status-Datei (`stop_loss_state_file`
in trend_config.py, Default `data/trend_stop_loss_paused.json`).

Ausführen mit:  python -m dca_bot.reset_trend_stop_loss
"""

from __future__ import annotations

import logging

from .trend_config import load_trend_config
from .trend_risk import TrendStopLoss


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config = load_trend_config()
    stop_loss = TrendStopLoss(config.stop_loss_state_file)
    stop_loss.reset()


if __name__ == "__main__":
    main()

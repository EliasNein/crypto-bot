"""
CLI-Befehl, um eine ausgelöste Portfolio-Stop-Loss-Pause manuell
zurückzusetzen.

Der Stop-Loss setzt sich bewusst nicht von selbst zurück (siehe
Begründung in risk.py) - dieser Befehl ist der vorgesehene Weg dafür,
alternativ genügt auch das manuelle Löschen der Status-Datei
(`stop_loss_state_file` in config.py, Default `data/stop_loss_paused.json`).

Ausführen mit:  python -m dca_bot.reset_stop_loss
"""

from __future__ import annotations

import logging

from .config import load_config
from .risk import PortfolioStopLoss, TradeLedger


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config = load_config()
    ledger = TradeLedger(config.state_file)
    stop_loss = PortfolioStopLoss(ledger, config.stop_loss_pct, config.stop_loss_state_file)
    stop_loss.reset()


if __name__ == "__main__":
    main()

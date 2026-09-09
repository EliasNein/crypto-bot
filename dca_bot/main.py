"""
Einstiegspunkt des DCA-Bots.

Ausführen mit:  python -m dca_bot.main

Der Bot läuft in einer Endlosschleife und führt alle `interval_hours`
einen DCA-Kaufzyklus aus. Mit Strg+C sauber beendbar.
"""

from __future__ import annotations

import logging
import os
import time

from .binance_client import TradingClient
from .config import load_config
from .risk import BotHalted, KillSwitch
from .strategy import DCAStrategy

# Wie oft während der Wartezeit zwischen zwei Zyklen geprüft wird, ob der
# Notaus ausgelöst wurde - kurz genug, um "sofort" zu wirken, aber ohne
# spürbare CPU-Last.
KILL_SWITCH_POLL_SECONDS = 5


def setup_logging(log_file: str) -> None:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _sleep_with_kill_switch_check(total_seconds: int, kill_switch: KillSwitch) -> bool:
    """
    Schläft in kurzen Abschnitten statt am Stück, damit ein währenddessen
    ausgelöster Notaus nicht erst nach bis zu `interval_hours` bemerkt wird.

    Gibt True zurück, falls der Notaus während der Wartezeit ausgelöst wurde.
    """
    elapsed = 0
    while elapsed < total_seconds:
        if kill_switch.is_set():
            return True
        step = min(KILL_SWITCH_POLL_SECONDS, total_seconds - elapsed)
        time.sleep(step)
        elapsed += step
    return False


def main() -> None:
    config = load_config()
    setup_logging(config.log_file)
    logger = logging.getLogger("dca_bot")

    logger.info("=" * 60)
    logger.info("DCA-Bot startet")
    logger.info("Symbol: %s | Betrag pro Kauf: %.2f | Intervall: %.2fh",
                config.symbol, config.quote_amount, config.interval_hours)
    logger.info("Trading aktiv (kein Dry-Run): %s", config.trading_enabled)
    if not config.trading_enabled:
        logger.info(
            "Hinweis: DCA_BOT_ENABLE_TRADING=false -> es werden KEINE "
            "echten Orders platziert, nur simuliert und geloggt."
        )
    logger.info("=" * 60)

    client = TradingClient(config)
    strategy = DCAStrategy(config, client)
    kill_switch = KillSwitch(config.kill_switch_file)

    interval_seconds = config.interval_hours * 60 * 60

    try:
        while True:
            try:
                strategy.execute_once()
            except BotHalted as exc:
                logger.warning("Notaus ausgelöst: %s", exc)
                logger.info("Bot wird sauber gestoppt.")
                break
            except Exception:
                # Ein einzelner fehlgeschlagener Zyklus soll den Bot nicht
                # komplett beenden - loggen und beim nächsten Intervall
                # erneut versuchen.
                logger.exception("Unerwarteter Fehler im Kaufzyklus.")

            logger.info("Warte %.2f Stunden bis zum nächsten Zyklus ...",
                        config.interval_hours)
            if _sleep_with_kill_switch_check(interval_seconds, kill_switch):
                logger.warning("Notaus während Wartezeit ausgelöst - Bot wird gestoppt.")
                break
    except KeyboardInterrupt:
        logger.info("Bot wird durch Nutzer beendet (Strg+C).")


if __name__ == "__main__":
    main()

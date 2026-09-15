"""
Einstiegspunkt des Kapital-Allocators.

Ausführen mit:  python -m dca_bot.main_allocator

Komplett eigenständig von DCA (main.py), Grid (main_grid.py) und Trend
(main_trend.py): eigene Konfiguration, eigener Zustand, eigener Notaus,
eigenes Log. Platziert selbst nie Orders - berechnet nur die
Trend-Following-Kapitalzuteilung und schreibt sie in seine State-Datei
(siehe allocator.py). DCA/Trend nutzen diese Datei nur, wenn sie über
DCA_ALLOCATOR_STATE_FILE/TREND_ALLOCATOR_STATE_FILE explizit darauf
verweisen (Default: aus, siehe .env.example).
"""

from __future__ import annotations

import logging
import os
import time

from .allocator import Allocator
from .allocator_config import load_allocator_config
from .binance_client import TradingClient
from .notifier import init as init_notifier
from .notifier import send_notification
from .risk import BotHalted, KillSwitch
from .version import get_code_version

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
    """Schläft in kurzen Abschnitten statt am Stück, damit ein währenddessen
    ausgelöster Notaus nicht erst nach der vollen Intervalldauer bemerkt wird.
    Gibt True zurück, falls der Notaus während der Wartezeit ausgelöst wurde."""
    elapsed = 0
    while elapsed < total_seconds:
        if kill_switch.is_set():
            return True
        step = min(KILL_SWITCH_POLL_SECONDS, total_seconds - elapsed)
        time.sleep(step)
        elapsed += step
    return False


def main() -> None:
    config = load_allocator_config()
    setup_logging(config.log_file)
    logger = logging.getLogger("allocator")

    logger.info("=" * 60)
    logger.info("Kapital-Allocator startet")
    logger.info("Code-Version: %s", get_code_version())
    logger.info(
        "Symbol: %s | EMA %d/%d | Anker %.1f%%-%.1f%% | Glättung: %d Zyklen | "
        "Intervall: %dmin",
        config.symbol,
        config.ema_fast_period,
        config.ema_slow_period,
        config.zero_anchor_pct,
        config.full_anchor_pct,
        config.smoothing_period,
        config.interval_minutes,
    )
    logger.info("Hinweis: Der Allocator platziert selbst nie Orders - nur Berechnung + State-Datei.")
    logger.info("=" * 60)

    init_notifier(config)

    client = TradingClient(config)
    allocator = Allocator(config, client)
    kill_switch = KillSwitch(config.kill_switch_file, env_var_name="ALLOCATOR_HALT")

    interval_seconds = config.interval_minutes * 60

    try:
        while True:
            try:
                allocator.execute_once()
            except BotHalted as exc:
                logger.warning("Notaus ausgelöst: %s", exc)
                logger.info("Allocator wird sauber gestoppt.")
                send_notification(f"[ALLOCATOR-NOTAUS] Gestoppt: {exc}")
                break
            except Exception as exc:
                logger.exception("Unerwarteter Fehler im Allocator-Zyklus.")
                send_notification(f"[ALLOCATOR-FEHLER] Unerwarteter Fehler: {exc}")

            logger.info("Warte %d Minuten bis zur nächsten Berechnung ...", config.interval_minutes)
            if _sleep_with_kill_switch_check(interval_seconds, kill_switch):
                logger.warning("Notaus während Wartezeit ausgelöst - Allocator wird gestoppt.")
                send_notification("[ALLOCATOR-NOTAUS] Während Wartezeit gestoppt.")
                break
    except KeyboardInterrupt:
        logger.info("Allocator wird durch Nutzer beendet (Strg+C).")


if __name__ == "__main__":
    main()

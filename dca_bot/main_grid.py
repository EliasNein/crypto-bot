"""
Einstiegspunkt des Spot-Grid-Trading-Bots.

Ausführen mit:  python -m dca_bot.main_grid

Komplett eigenständig vom DCA-Bot (main.py): eigene Konfiguration, eigener
Zustand, eigener Notaus, eigenes Log. Kann parallel zum DCA-Bot auf
demselben Symbol laufen, ohne dass sich beide gegenseitig beeinflussen.
"""

from __future__ import annotations

import logging
import os
import time

from .binance_client import TradingClient
from .grid_config import load_grid_config
from .grid_strategy import GridTradingStrategy
from .notifier import init as init_notifier
from .notifier import send_notification
from .pending_orders import safe_startup_reconciliation
from .process_lock import BotAlreadyRunning, ProcessLock
from .risk import BotHalted, KillSwitch
from .version import get_code_version

# Wie oft während der Wartezeit zwischen zwei Zyklen geprüft wird, ob der
# Notaus ausgelöst wurde - kurz genug, um "sofort" zu wirken.
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
    config = load_grid_config()
    setup_logging(config.log_file)
    logger = logging.getLogger("grid_bot")

    logger.info("=" * 60)
    logger.info("Grid-Trading-Bot startet")
    logger.info("Code-Version: %s", get_code_version())
    logger.info(
        "Symbol: %s | Grid: %.2f - %.2f | Abstand: %.2f%% | Betrag/Stufe: %.2f | Intervall: %dmin",
        config.symbol,
        config.lower_limit,
        config.upper_limit,
        config.grid_spacing_pct,
        config.amount_per_level,
        config.interval_minutes,
    )
    logger.info("Trading aktiv (kein Dry-Run): %s", config.trading_enabled)
    if not config.trading_enabled:
        logger.info(
            "Hinweis: GRID_BOT_ENABLE_TRADING=false -> es werden KEINE "
            "echten Orders platziert, nur simuliert und geloggt."
        )
    logger.info("=" * 60)

    # Schutz gegen einen versehentlichen doppelten Bot-Start (siehe
    # process_lock.py): zwei Prozesse auf demselben Zustand wuerden sich
    # gegenseitig Eintraege ueberschreiben. Bewusst ganz am Anfang, noch
    # vor dem Lesen von Zustand oder dem Verbindungsaufbau.
    lock = ProcessLock(config.lock_file, "grid")
    try:
        lock.acquire()
    except BotAlreadyRunning as exc:
        logger.error("%s", exc)
        return

    init_notifier(config)

    client = TradingClient(config)
    strategy = GridTradingStrategy(config, client)
    kill_switch = KillSwitch(config.kill_switch_file, env_var_name="GRID_BOT_HALT")

    # Reconciliation VOR dem ersten Zyklus: eine beim letzten Lauf
    # ausgeführte, aber nicht mehr verbuchte Order würde sonst eine
    # Stufe fälschlich als frei (Kauf) oder eine verkaufte Position als
    # weiterhin offen (Verkauf) erscheinen lassen - beides führt im
    # ersten Zyklus zu einer doppelten Order. Siehe pending_orders.py
    # (Sicherheitsreview-Punkt K2).
    #
    # Gekapselt, damit ein Fehler hier den Bot-Start nicht verhindert
    # (W18) - der Aufruf liegt zwangsläufig außerhalb des try/except der
    # Hauptschleife.
    safe_startup_reconciliation(
        logger,
        "[GRID-FEHLER]",
        [("Reconciliation offener Order-Fragen", strategy.reconcile_pending_orders)],
    )

    interval_seconds = config.interval_minutes * 60

    try:
        while True:
            try:
                strategy.execute_once()
            except BotHalted as exc:
                logger.warning("Notaus ausgelöst: %s", exc)
                logger.info("Grid-Bot wird sauber gestoppt.")
                send_notification(f"[GRID-NOTAUS] Bot gestoppt: {exc}")
                break
            except Exception as exc:
                # Ein einzelner fehlgeschlagener Zyklus soll den Bot nicht
                # komplett beenden - loggen und beim nächsten Intervall
                # erneut versuchen.
                logger.exception("Unerwarteter Fehler im Grid-Zyklus.")
                send_notification(f"[GRID-FEHLER] Unerwarteter Fehler im Grid-Zyklus: {exc}")

            logger.info("Warte %d Minuten bis zum nächsten Zyklus ...", config.interval_minutes)
            if _sleep_with_kill_switch_check(interval_seconds, kill_switch):
                logger.warning("Notaus während Wartezeit ausgelöst - Grid-Bot wird gestoppt.")
                send_notification("[GRID-NOTAUS] Bot während Wartezeit gestoppt.")
                break
    except KeyboardInterrupt:
        logger.info("Grid-Bot wird durch Nutzer beendet (Strg+C).")


if __name__ == "__main__":
    main()

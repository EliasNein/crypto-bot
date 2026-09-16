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
from datetime import datetime, timezone

from .allocator import Allocator
from .allocator_config import load_allocator_config
from .config_guard import (
    ConfigError,
    announce_trading_mode,
    mode_label,
    report_config_error,
)
from .binance_client import TradingClient
from .heartbeat import Heartbeat
from .notifier import init as init_notifier
from .notifier import send_notification
from .process_lock import BotAlreadyRunning, ProcessLock
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
    # Siehe main.py: eine Fehlkonfiguration darf keine
    # systemd-Neustartschleife ausloesen (W12).
    try:
        config = load_allocator_config()
    except ConfigError as exc:
        report_config_error("Kapital-Allocator", exc)
        return

    setup_logging(config.log_file)
    logger = logging.getLogger("allocator")

    logger.info("=" * 60)
    logger.info("Kapital-Allocator startet")
    logger.info("Code-Version: %s", get_code_version())
    logger.info("Modus: %s", mode_label(config.use_testnet))
    logger.info(
        "Symbol: %s | EMA %d/%d | Anker %.1f%%-%.1f%% | Glättung: %d Tage | "
        "Zyklus: %dmin (Feed: 1 Tagesschlusskurs/Tag)",
        config.symbol,
        config.ema_fast_period,
        config.ema_slow_period,
        config.zero_anchor_pct,
        config.full_anchor_pct,
        config.smoothing_period,
        config.interval_minutes,
    )
    logger.info(
        "Hinweis: Der Allocator platziert selbst nie Orders - nur Berechnung "
        "+ State-Datei. Die EMAs werden mit genau einem Tagesschlusskurs pro "
        "Kalendertag gespeist (wie im Backtest); der Zyklus-Takt dient dem "
        "Neuveroeffentlichen und dem Notaus (W9)."
    )
    logger.info("=" * 60)

    # Schutz gegen einen versehentlichen doppelten Bot-Start (siehe
    # process_lock.py): zwei Prozesse auf demselben Zustand wuerden sich
    # gegenseitig Eintraege ueberschreiben. Bewusst ganz am Anfang, noch
    # vor dem Lesen von Zustand oder dem Verbindungsaufbau.
    lock = ProcessLock(config.lock_file, "allocator")
    try:
        lock.acquire()
    except BotAlreadyRunning as exc:
        logger.error("%s", exc)
        return

    init_notifier(config)

    # trading_enabled=None: der Allocator platziert nie Orders,
    # liest im Live-Modus aber echte Konto-/Kursdaten und steuert
    # die Ordergroesse von DCA und Trend (W12).
    announce_trading_mode(
        logger,
        "Kapital-Allocator",
        use_testnet=config.use_testnet,
        trading_enabled=None,
    )

    client = TradingClient(config)
    allocator = Allocator(config, client)
    kill_switch = KillSwitch(config.kill_switch_file, env_var_name="ALLOCATOR_HALT")

    heartbeat = Heartbeat("Kapital-Allocator", config.heartbeat_interval_hours)

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

            # Lebenszeichen (W13): laeuft nach jedem Zyklus, sendet aber
            # hoechstens einmal pro HEARTBEAT_INTERVAL_HOURS.
            last_cycle_at = datetime.now(timezone.utc)
            heartbeat.maybe_send(last_cycle_at)

            logger.info("Warte %d Minuten bis zur nächsten Berechnung ...", config.interval_minutes)
            if _sleep_with_kill_switch_check(interval_seconds, kill_switch):
                logger.warning("Notaus während Wartezeit ausgelöst - Allocator wird gestoppt.")
                send_notification("[ALLOCATOR-NOTAUS] Während Wartezeit gestoppt.")
                break
    except KeyboardInterrupt:
        logger.info("Allocator wird durch Nutzer beendet (Strg+C).")


if __name__ == "__main__":
    main()

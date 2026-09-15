"""
Einstiegspunkt des Trend-Following-Bots.

Ausführen mit:  python -m dca_bot.main_trend

Komplett eigenständig von DCA (main.py) und Grid (main_grid.py): eigene
Konfiguration, eigener Zustand, eigener Notaus, eigenes Log. Kann
parallel zu den anderen Bots auf demselben Symbol laufen, ohne dass sie
sich gegenseitig beeinflussen.
"""

from __future__ import annotations

import logging
import os
import time

from .binance_client import TradingClient
from .notifier import init as init_notifier
from .notifier import send_notification
from .risk import BotHalted, KillSwitch
from .trend_config import load_trend_config
from .trend_strategy import TrendFollowingStrategy
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
    config = load_trend_config()
    setup_logging(config.log_file)
    logger = logging.getLogger("trend_bot")

    logger.info("=" * 60)
    logger.info("Trend-Following-Bot startet")
    logger.info("Code-Version: %s", get_code_version())
    logger.info(
        "Symbol: %s | EMA %d/%d | Mindestabstand: %.2f%% | Betrag/Trade: %.2f | "
        "Stop-Loss: %.1f%% | Intervall: %dh",
        config.symbol,
        config.ema_fast_period,
        config.ema_slow_period,
        config.min_gap_pct,
        config.amount_per_trade,
        config.stop_loss_pct,
        config.interval_hours,
    )
    logger.info("Trading aktiv (kein Dry-Run): %s", config.trading_enabled)
    if not config.trading_enabled:
        logger.info(
            "Hinweis: TREND_BOT_ENABLE_TRADING=false -> es werden KEINE "
            "echten Orders platziert, nur simuliert und geloggt."
        )
    logger.info("=" * 60)

    init_notifier(config)

    client = TradingClient(config)
    strategy = TrendFollowingStrategy(config, client)
    kill_switch = KillSwitch(config.kill_switch_file, env_var_name="TREND_BOT_HALT")

    # Reconciliation VOR dem ersten Zyklus: gleicht eine im Ledger offene
    # Position gegen den tatsächlichen Stop-Loss-Order-Status bei Binance
    # ab, damit eine während der Downtime gefüllte Stop-Loss-Order sofort
    # erkannt wird statt erst im nächsten regulären Zyklus.
    strategy.reconcile_on_startup()

    interval_seconds = config.interval_hours * 60 * 60

    try:
        while True:
            try:
                strategy.execute_once()
            except BotHalted as exc:
                logger.warning("Notaus ausgelöst: %s", exc)
                logger.info("Trend-Bot wird sauber gestoppt.")
                send_notification(f"[TREND-NOTAUS] Bot gestoppt: {exc}")
                break
            except Exception as exc:
                # Ein einzelner fehlgeschlagener Zyklus soll den Bot nicht
                # komplett beenden - loggen und beim nächsten Intervall
                # erneut versuchen.
                logger.exception("Unerwarteter Fehler im Trend-Zyklus.")
                send_notification(f"[TREND-FEHLER] Unerwarteter Fehler im Trend-Zyklus: {exc}")

            logger.info("Warte %d Stunden bis zum nächsten Zyklus ...", config.interval_hours)
            if _sleep_with_kill_switch_check(interval_seconds, kill_switch):
                logger.warning("Notaus während Wartezeit ausgelöst - Trend-Bot wird gestoppt.")
                send_notification("[TREND-NOTAUS] Bot während Wartezeit gestoppt.")
                break
    except KeyboardInterrupt:
        logger.info("Trend-Bot wird durch Nutzer beendet (Strg+C).")


if __name__ == "__main__":
    main()

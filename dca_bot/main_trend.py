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
from datetime import datetime, timezone

from .binance_client import TradingClient
from .heartbeat import Heartbeat
from .notifier import init as init_notifier
from .notifier import send_notification
from .pending_orders import safe_startup_reconciliation
from .process_lock import BotAlreadyRunning, ProcessLock
from .risk import BotHalted, KillSwitch, LedgerUnreadable
from .config_guard import (
    ConfigError,
    announce_trading_mode,
    mode_label,
    report_config_error,
)
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
    # Siehe main.py: eine Fehlkonfiguration darf keine
    # systemd-Neustartschleife ausloesen (W12).
    try:
        config = load_trend_config()
    except ConfigError as exc:
        report_config_error("Trend-Following-Bot", exc)
        return

    setup_logging(config.log_file)
    logger = logging.getLogger("trend_bot")

    logger.info("=" * 60)
    logger.info("Trend-Following-Bot startet")
    logger.info("Code-Version: %s", get_code_version())
    logger.info("Modus: %s", mode_label(config.use_testnet))
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

    # Schutz gegen einen versehentlichen doppelten Bot-Start (siehe
    # process_lock.py): zwei Prozesse auf demselben Zustand wuerden sich
    # gegenseitig Eintraege ueberschreiben. Bewusst ganz am Anfang, noch
    # vor dem Lesen von Zustand oder dem Verbindungsaufbau.
    lock = ProcessLock(config.lock_file, "trend")
    try:
        lock.acquire()
    except BotAlreadyRunning as exc:
        logger.error("%s", exc)
        return

    init_notifier(config)

    # Live-Modus ausdruecklich laut melden, im Log UND per Telegram
    # (W12) - bewusst erst nach init_notifier().
    announce_trading_mode(
        logger,
        "Trend-Following-Bot",
        use_testnet=config.use_testnet,
        trading_enabled=config.trading_enabled,
        enable_var_name="TREND_BOT_ENABLE_TRADING",
    )

    client = TradingClient(config)
    strategy = TrendFollowingStrategy(config, client)
    kill_switch = KillSwitch(config.kill_switch_file, env_var_name="TREND_BOT_HALT")

    # Ledger-Integritaet VOR allem anderen (W5): eine vorhandene, aber
    # beschaedigte Ledger-Datei darf NICHT als leere Historie
    # durchgehen - Tageslimit und Stop-Loss-Basis fielen sonst
    # stillschweigend auf Null zurueck. Lieber gar nicht starten.
    try:
        strategy.verify_state_readable()
    except LedgerUnreadable as exc:
        logger.error("%s", exc)
        send_notification(
            f"[TREND-FEHLER] Bot startet NICHT: {exc} "
            "Bitte die Datei pruefen oder aus einem Backup wiederherstellen."
        )
        return

    # Zwei Reconciliation-Schritte, und die Reihenfolge ist bewusst so:
    #
    # 1. Offene Order-Fragen aus dem letzten Lauf auflösen (K2, siehe
    #    pending_orders.py). Ein hier nachgetragener Einstieg erzeugt
    #    eine offene Position OHNE exchange-seitige Stop-Loss-Order.
    # 2. Den bestehenden Abgleich der Stop-Loss-Order laufen lassen: er
    #    erkennt eine während der Downtime gefüllte Stop-Order UND
    #    platziert über _ensure_stop_loss_protection() die Absicherung,
    #    die der gerade nachgetragenen Position noch fehlt.
    #
    # Andersherum liefe Schritt 2 ins Leere - zu seinem Zeitpunkt gäbe
    # es die nachgetragene Position noch gar nicht.
    #
    # Beide Schritte einzeln gekapselt, damit ein Fehler den Bot-Start
    # nicht verhindert (W18) - und damit Schritt 2 auch dann läuft, wenn
    # Schritt 1 scheitert: er sichert eine bereits offene Position ab und
    # ist gerade dann wertvoll.
    safe_startup_reconciliation(
        logger,
        "[TREND-FEHLER]",
        [
            ("Reconciliation offener Order-Fragen", strategy.reconcile_pending_orders),
            ("Abgleich der Stop-Loss-Order", strategy.reconcile_on_startup),
        ],
    )

    heartbeat = Heartbeat("Trend-Following-Bot", config.heartbeat_interval_hours)

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

            # Lebenszeichen (W13): laeuft nach jedem Zyklus, sendet aber
            # hoechstens einmal pro HEARTBEAT_INTERVAL_HOURS.
            last_cycle_at = datetime.now(timezone.utc)
            heartbeat.maybe_send(last_cycle_at)

            logger.info("Warte %d Stunden bis zum nächsten Zyklus ...", config.interval_hours)
            if _sleep_with_kill_switch_check(interval_seconds, kill_switch):
                logger.warning("Notaus während Wartezeit ausgelöst - Trend-Bot wird gestoppt.")
                send_notification("[TREND-NOTAUS] Bot während Wartezeit gestoppt.")
                break
    except KeyboardInterrupt:
        logger.info("Trend-Bot wird durch Nutzer beendet (Strg+C).")


if __name__ == "__main__":
    main()

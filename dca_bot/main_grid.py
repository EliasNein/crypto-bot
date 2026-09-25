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
from datetime import datetime, timezone

from .binance_client import TradingClient
from .heartbeat import Heartbeat
from .heartbeat_status import HeartbeatStatusWriter
from .cycle_errors import CycleErrorNotifier
from .config_guard import (
    ConfigError,
    announce_trading_mode,
    mode_label,
    report_config_error,
)
from .grid_config import load_grid_config
from .grid_strategy import GridTradingStrategy
from .notifier import init as init_notifier
from .notifier import send_notification
from .pending_orders import safe_startup_reconciliation
from .process_lock import BotAlreadyRunning, ProcessLock
from .risk import BotHalted, KillSwitch, LedgerUnreadable
from .version import get_code_version

# Wie oft während der Wartezeit zwischen zwei Zyklen geprüft wird, ob der
# Notaus ausgelöst wurde - kurz genug, um "sofort" zu wirken.
KILL_SWITCH_POLL_SECONDS = 5

# Request-Timeout gegen die Binance-API in Sekunden, statt des
# python-binance-Standards von 10 s. Anlass waren nächtliche
# "HTTPSConnectionPool(host='testnet.binance.vision', ...): Read timed out"-
# Fehler auf dem Homeserver. Ursache ist nicht ein zu langsames Testnet,
# sondern die nächtliche Zwangstrennung des Heimanschlusses: Die Verbindung
# reißt ganz ab, der Request scheitert dann voraussichtlich auch nach 20 s.
# Der Wert schadet nicht und bleibt. Betroffen ist nur der Grid-Bot, weil
# er alle 5 Minuten abfragt statt einmal am Tag (siehe
# trading-bot-projekt.md 6g, Nachtrag 25.09.). Bewusst nur hier gesetzt -
# DCA, Trend und Allocator bleiben beim Bibliotheks-Default.
REQUEST_TIMEOUT_SECONDS = 20


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
        config = load_grid_config()
    except ConfigError as exc:
        report_config_error("Grid-Bot", exc)
        return

    setup_logging(config.log_file)
    logger = logging.getLogger("grid_bot")

    logger.info("=" * 60)
    logger.info("Grid-Trading-Bot startet")
    logger.info("Code-Version: %s", get_code_version())
    logger.info("Modus: %s", mode_label(config.use_testnet))
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

    # Live-Modus ausdruecklich laut melden, im Log UND per Telegram
    # (W12) - bewusst erst nach init_notifier().
    announce_trading_mode(
        logger,
        "Grid-Bot",
        use_testnet=config.use_testnet,
        trading_enabled=config.trading_enabled,
        enable_var_name="GRID_BOT_ENABLE_TRADING",
    )

    client = TradingClient(config, request_timeout_seconds=REQUEST_TIMEOUT_SECONDS)
    strategy = GridTradingStrategy(config, client)
    kill_switch = KillSwitch(config.kill_switch_file, env_var_name="GRID_BOT_HALT")

    # Ledger-Integritaet VOR allem anderen (W5): eine vorhandene, aber
    # beschaedigte Ledger-Datei darf NICHT als leere Historie
    # durchgehen - Tageslimit und Stop-Loss-Basis fielen sonst
    # stillschweigend auf Null zurueck. Lieber gar nicht starten.
    try:
        strategy.verify_state_readable()
    except LedgerUnreadable as exc:
        logger.error("%s", exc)
        send_notification(
            f"[GRID-FEHLER] Bot startet NICHT: {exc} "
            "Bitte die Datei pruefen oder aus einem Backup wiederherstellen."
        )
        return

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
    # Der Bestandsabgleich laeuft als LETZTER Startschritt, nach der
    # Reconciliation: die kann Kaeufe/Verkaeufe nachtragen, ein Abgleich
    # davor verglicher also gegen einen veralteten Ledger-Stand. Und er
    # liegt bewusst in dieser Liste statt in einem eigenen try/except -
    # so gilt der W18-Schutz auch fuer ihn (Stufe 2, Punkt 3, siehe
    # startup_checks.py).
    safe_startup_reconciliation(
        logger,
        "[GRID-FEHLER]",
        [
            ("Reconciliation offener Order-Fragen", strategy.reconcile_pending_orders),
            ("Bestandsabgleich gegen den Kontostand", strategy.check_balance_on_startup),
        ],
    )

    heartbeat = Heartbeat("Grid-Bot", config.heartbeat_interval_hours)
    # Nur nach einem ERFOLGREICHEN Zyklus gesetzt - siehe main.py.
    last_cycle_at: datetime | None = None
    # Derselbe Status zusaetzlich als Datei fuer die Dashboard-App -
    # nur geschrieben, von keinem Bot gelesen (siehe heartbeat_status.py).
    status_file = HeartbeatStatusWriter(config.heartbeat_status_file, logger)
    error_notifier = CycleErrorNotifier(logger, "[GRID-FEHLER]", "Grid-Zyklus")

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
                # erneut versuchen. Ins Log geht jeder Fehlschlag, per
                # Telegram nur der erste seiner Art (siehe
                # CycleErrorNotifier).
                logger.exception("Unerwarteter Fehler im Grid-Zyklus.")
                error_notifier.report_failure(exc)
                status_file.record_failure(datetime.now(timezone.utc), last_cycle_at)
            else:
                last_cycle_at = datetime.now(timezone.utc)
                error_notifier.report_success()
                status_file.record_success(last_cycle_at)

            # Lebenszeichen (W13): laeuft nach jedem Zyklus, sendet aber
            # hoechstens einmal pro HEARTBEAT_INTERVAL_HOURS.
            heartbeat.maybe_send(last_cycle_at)

            logger.info("Warte %d Minuten bis zum nächsten Zyklus ...", config.interval_minutes)
            if _sleep_with_kill_switch_check(interval_seconds, kill_switch):
                logger.warning("Notaus während Wartezeit ausgelöst - Grid-Bot wird gestoppt.")
                send_notification("[GRID-NOTAUS] Bot während Wartezeit gestoppt.")
                break
    except KeyboardInterrupt:
        logger.info("Grid-Bot wird durch Nutzer beendet (Strg+C).")


if __name__ == "__main__":
    main()

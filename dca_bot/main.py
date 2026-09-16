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
from datetime import date

from .binance_client import TradingClient
from .config import Config, load_config
from .notifier import init as init_notifier
from .notifier import send_notification
from .process_lock import BotAlreadyRunning, ProcessLock
from .risk import BotHalted, KillSwitch, PortfolioStopLoss, TradeLedger
from .strategy import DCAStrategy
from .version import get_code_version

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


def _send_daily_summary(
    config: Config, ledger: TradeLedger, stop_loss: PortfolioStopLoss, day: date
) -> None:
    """Sendet eine Zusammenfassung für einen abgeschlossenen Kalendertag."""
    count, total_spent = ledger.day_summary(config.symbol, day)
    stop_loss_status = (
        "PAUSIERT (manueller Reset nötig)" if stop_loss.is_paused() else "aktiv, kein Trigger"
    )
    send_notification(
        f"[TAGESZUSAMMENFASSUNG {day.isoformat()}] "
        f"Trades: {count} | Ausgaben: {total_spent:.2f} ({config.symbol}) | "
        f"Stop-Loss: {stop_loss_status}"
    )


def main() -> None:
    config = load_config()
    setup_logging(config.log_file)
    logger = logging.getLogger("dca_bot")

    logger.info("=" * 60)
    logger.info("DCA-Bot startet")
    logger.info("Code-Version: %s", get_code_version())
    logger.info("Symbol: %s | Betrag pro Kauf: %.2f | Intervall: %.2fh",
                config.symbol, config.quote_amount, config.interval_hours)
    logger.info("Trading aktiv (kein Dry-Run): %s", config.trading_enabled)
    if not config.trading_enabled:
        logger.info(
            "Hinweis: DCA_BOT_ENABLE_TRADING=false -> es werden KEINE "
            "echten Orders platziert, nur simuliert und geloggt."
        )
    logger.info("=" * 60)

    # Schutz gegen einen versehentlichen doppelten Bot-Start (siehe
    # process_lock.py): zwei Prozesse auf demselben Zustand wuerden sich
    # gegenseitig Eintraege ueberschreiben. Bewusst ganz am Anfang, noch
    # vor dem Lesen von Zustand oder dem Verbindungsaufbau.
    lock = ProcessLock(config.lock_file, "dca")
    try:
        lock.acquire()
    except BotAlreadyRunning as exc:
        logger.error("%s", exc)
        return

    init_notifier(config)

    client = TradingClient(config)
    strategy = DCAStrategy(config, client)
    kill_switch = KillSwitch(config.kill_switch_file)

    # Reconciliation VOR der ersten Kaufentscheidung: falls beim letzten
    # Lauf eine Order ausgeführt, aber nicht mehr verbucht wurde (siehe
    # pending_orders.py, Sicherheitsreview-Punkt K2), wird sie jetzt
    # nachgetragen. Sonst rechneten Tageslimit und Stop-Loss-Kostenbasis
    # in diesem Zyklus mit einer Position, die zu klein ist.
    strategy.reconcile_pending_orders()

    # Eigene, rein lesende Instanzen für die tägliche Zusammenfassung -
    # analog zu reset_stop_loss.py greifen sie auf dieselben Dateien zu wie
    # die Strategie, ohne dass main.py Zugriff auf deren interne Objekte
    # braucht.
    summary_ledger = TradeLedger(config.state_file)
    summary_stop_loss = PortfolioStopLoss(
        summary_ledger, config.stop_loss_pct, config.stop_loss_state_file
    )
    # Auf heute initialisiert, damit beim Start nicht sofort eine
    # (unvollständige) Zusammenfassung für den laufenden Tag rausgeht -
    # die erste Benachrichtigung kommt beim nächsten echten Tageswechsel.
    last_summary_date = date.today()

    interval_seconds = config.interval_hours * 60 * 60

    try:
        while True:
            try:
                strategy.execute_once()
            except BotHalted as exc:
                logger.warning("Notaus ausgelöst: %s", exc)
                logger.info("Bot wird sauber gestoppt.")
                send_notification(f"[NOTAUS] Bot gestoppt: {exc}")
                break
            except Exception as exc:
                # Ein einzelner fehlgeschlagener Zyklus soll den Bot nicht
                # komplett beenden - loggen und beim nächsten Intervall
                # erneut versuchen.
                logger.exception("Unerwarteter Fehler im Kaufzyklus.")
                send_notification(f"[FEHLER] Unerwarteter Fehler im Kaufzyklus: {exc}")

            today = date.today()
            if today != last_summary_date:
                _send_daily_summary(config, summary_ledger, summary_stop_loss, last_summary_date)
                last_summary_date = today

            logger.info("Warte %.2f Stunden bis zum nächsten Zyklus ...",
                        config.interval_hours)
            if _sleep_with_kill_switch_check(interval_seconds, kill_switch):
                logger.warning("Notaus während Wartezeit ausgelöst - Bot wird gestoppt.")
                send_notification("[NOTAUS] Bot während Wartezeit gestoppt.")
                break
    except KeyboardInterrupt:
        logger.info("Bot wird durch Nutzer beendet (Strg+C).")


if __name__ == "__main__":
    main()

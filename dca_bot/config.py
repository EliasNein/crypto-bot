"""
Zentrale Konfiguration für den DCA-Bot.

Alle Einstellungen werden hier gebündelt, damit main.py und strategy.py
nicht direkt mit Umgebungsvariablen hantieren müssen. Das erleichtert
später auch Unit-Tests (man kann eine Config einfach mocken).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Lädt Variablen aus einer .env-Datei im Projektverzeichnis, falls vorhanden.
load_dotenv()


@dataclass(frozen=True)
class Config:
    # --- Binance API ---
    api_key: str
    api_secret: str
    use_testnet: bool = True

    # --- DCA-Strategie ---
    symbol: str = "BTCUSDT"       # Handelspaar
    quote_amount: float = 15.0    # Betrag in Quote-Währung (z.B. USDT) pro Kauf
    interval_hours: int = 24      # Kaufintervall in Stunden

    # --- Sicherheit ---
    trading_enabled: bool = False  # Muss explizit auf True gesetzt werden
    max_daily_spend: float = 50.0  # Notbremse: max. Ausgaben pro Tag in Quote-Währung
    kill_switch_file: str = "STOP"  # Existiert diese Datei, stoppt der Bot sofort
    stop_loss_pct: float = 25.0    # Portfolio pausiert Käufe ab X% Verlust ggü. Einsatz (0 = aus)
    state_file: str = "data/trade_ledger.json"  # Persistente Trade-Historie
    stop_loss_state_file: str = "data/stop_loss_paused.json"  # Existiert diese Datei, bleibt der Stop-Loss pausiert

    # Kurzname dieses Bots. Dient als Präfix der selbstvergebenen
    # `newClientOrderId` jeder echten Order (siehe pending_orders.py) und
    # als Kennung in der Pending-Orders-Datei. Bewusst KEINE
    # Env-Variable: das ist eine Identität, keine Einstellung - ein
    # geänderter Name würde die Zuordnung zu bereits laufenden Orders
    # zerreißen.
    bot_name: str = "dca"
    # Orders, deren Ausgang noch offen ist (siehe pending_orders.py,
    # Sicherheitsreview-Punkt K2). Wird VOR jedem Order-Request
    # geschrieben und direkt nach dessen Klärung wieder geleert - im
    # Normalbetrieb also leer.
    pending_orders_file: str = "data/pending_orders_dca.json"
    # Lockfile gegen einen versehentlichen doppelten Bot-Start (z.B.
    # manueller Aufruf neben dem laufenden systemd-Service, siehe
    # process_lock.py). Zwei Prozesse auf demselben Ledger würden sich
    # gegenseitig Einträge überschreiben.
    lock_file: str = "data/dca_bot.lock"

    # --- Kapital-Allocator (optional, siehe allocator.py) ---
    # Leer = deaktiviert (Default): der Bot verhält sich dann exakt wie
    # ohne Allocator, unverändertes Standardverhalten. Nur wenn explizit
    # auf den gleichen Pfad wie ALLOCATOR_STATE_FILE gesetzt, skaliert der
    # Bot den Betrag NEUER Käufe anhand der dort geschriebenen Zuteilung.
    allocator_state_file: str = ""

    # --- Benachrichtigungen (optional) ---
    telegram_bot_token: str = ""  # Leer = Telegram-Benachrichtigungen deaktiviert
    telegram_chat_id: str = ""

    # Abstand zwischen zwei Lebenszeichen per Telegram in Stunden
    # (Sicherheitsreview-Punkt W13, siehe heartbeat.py). 0 = aus.
    # Bewusst EINE gemeinsame Variable fuer alle vier Bots, wie die
    # TELEGRAM_-Zugangsdaten auch - vier Praefix-Varianten waeren hier
    # nur Ballast.
    heartbeat_interval_hours: float = 24.0

    # --- Logging ---
    log_file: str = "logs/dca_bot.log"


def load_config() -> Config:
    """Liest alle Werte aus den Umgebungsvariablen und validiert sie."""
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    if not api_key or not api_secret or "dein_testnet" in api_key:
        raise ValueError(
            "BINANCE_API_KEY / BINANCE_API_SECRET sind nicht gesetzt. "
            "Kopiere .env.example zu .env und trage deine Testnet-Keys ein "
            "(https://testnet.binance.vision/)."
        )

    trading_enabled = os.getenv("DCA_BOT_ENABLE_TRADING", "false").lower() == "true"
    kill_switch_file = os.getenv("DCA_BOT_KILL_SWITCH_FILE", "STOP")
    stop_loss_pct = float(os.getenv("DCA_BOT_STOP_LOSS_PCT", "25.0"))
    state_file = os.getenv("DCA_BOT_STATE_FILE", "data/trade_ledger.json")
    stop_loss_state_file = os.getenv(
        "DCA_BOT_STOP_LOSS_STATE_FILE", "data/stop_loss_paused.json"
    )
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    return Config(
        api_key=api_key,
        api_secret=api_secret,
        trading_enabled=trading_enabled,
        kill_switch_file=kill_switch_file,
        stop_loss_pct=stop_loss_pct,
        state_file=state_file,
        stop_loss_state_file=stop_loss_state_file,
        pending_orders_file=os.getenv(
            "DCA_PENDING_ORDERS_FILE", "data/pending_orders_dca.json"
        ),
        lock_file=os.getenv("DCA_LOCK_FILE", "data/dca_bot.lock"),
        allocator_state_file=os.getenv("DCA_ALLOCATOR_STATE_FILE", ""),
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        heartbeat_interval_hours=float(os.getenv("HEARTBEAT_INTERVAL_HOURS", "24.0")),
    )

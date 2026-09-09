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

    # --- Benachrichtigungen (optional) ---
    telegram_bot_token: str = ""  # Leer = Telegram-Benachrichtigungen deaktiviert
    telegram_chat_id: str = ""

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
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
    )

"""
Konfiguration für den Spot-Grid-Trading-Bot.

Komplett eigenständig von config.py (DCA-Bot): eigene Env-Variablen mit
GRID_-Präfix, eigener Zustand, eigenes Tageslimit gibt es bewusst nicht
(siehe grid_strategy.py - die feste Anzahl Grid-Stufen × Betrag/Stufe
begrenzt die maximale Kapitalbindung bereits von selbst).

Nutzt dieselben Binance- und Telegram-Zugangsdaten wie der DCA-Bot
(gleiche Börse, gleicher Telegram-Chat) - das sind reine Zugangsdaten,
kein geteilter Bot-Zustand.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class GridConfig:
    # --- Binance API (gleiche Zugangsdaten wie der DCA-Bot) ---
    api_key: str
    api_secret: str
    use_testnet: bool = True

    # --- Grid-Strategie ---
    symbol: str = "BTCUSDT"
    lower_limit: float = 70000.0    # Untere Grid-Grenze in Quote-Währung
    upper_limit: float = 90000.0    # Obere Grid-Grenze in Quote-Währung
    grid_spacing_pct: float = 1.5   # Abstand zwischen den Grid-Stufen in %
    amount_per_level: float = 15.0  # Betrag pro Grid-Stufe in Quote-Währung
    interval_minutes: int = 5       # Wie oft der Preis geprüft wird

    # --- Sicherheit ---
    trading_enabled: bool = False       # Muss explizit auf True gesetzt werden
    kill_switch_file: str = "STOP_GRID"  # Eigene Notaus-Datei, unabhängig vom DCA-Bot
    stop_loss_pct: float = 15.0     # Trendbruch-Puffer unterhalb lower_limit in %
    state_file: str = "data/grid_positions.json"
    stop_loss_state_file: str = "data/grid_stop_loss_paused.json"

    # Siehe config.py (DCA) für die Begründung dieser drei Felder -
    # Präfix der selbstvergebenen Order-IDs, offene Order-Fragen (K2)
    # und Schutz gegen doppelten Bot-Start. Jeweils eigene Dateien,
    # komplett getrennt von DCA/Trend.
    bot_name: str = "grid"
    pending_orders_file: str = "data/pending_orders_grid.json"
    lock_file: str = "data/grid_bot.lock"

    # --- Benachrichtigungen (optional, gleiche Zugangsdaten wie der DCA-Bot) ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- Logging ---
    log_file: str = "logs/grid_bot.log"


def load_grid_config() -> GridConfig:
    """Liest alle Werte aus den Umgebungsvariablen und validiert sie."""
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    if not api_key or not api_secret or "dein_testnet" in api_key:
        raise ValueError(
            "BINANCE_API_KEY / BINANCE_API_SECRET sind nicht gesetzt. "
            "Kopiere .env.example zu .env und trage deine Testnet-Keys ein "
            "(https://testnet.binance.vision/)."
        )

    lower_limit = float(os.getenv("GRID_LOWER_LIMIT", "70000.0"))
    upper_limit = float(os.getenv("GRID_UPPER_LIMIT", "90000.0"))
    grid_spacing_pct = float(os.getenv("GRID_SPACING_PCT", "1.5"))

    if lower_limit <= 0 or upper_limit <= lower_limit or grid_spacing_pct <= 0:
        raise ValueError(
            "Ungültige Grid-Parameter: GRID_LOWER_LIMIT muss > 0, "
            "GRID_UPPER_LIMIT > GRID_LOWER_LIMIT und GRID_SPACING_PCT > 0 "
            f"sein (aktuell: lower={lower_limit}, upper={upper_limit}, "
            f"spacing={grid_spacing_pct})."
        )

    return GridConfig(
        api_key=api_key,
        api_secret=api_secret,
        symbol=os.getenv("GRID_SYMBOL", "BTCUSDT"),
        lower_limit=lower_limit,
        upper_limit=upper_limit,
        grid_spacing_pct=grid_spacing_pct,
        amount_per_level=float(os.getenv("GRID_AMOUNT_PER_LEVEL", "15.0")),
        interval_minutes=int(os.getenv("GRID_INTERVAL_MINUTES", "5")),
        trading_enabled=os.getenv("GRID_BOT_ENABLE_TRADING", "false").lower() == "true",
        kill_switch_file=os.getenv("GRID_KILL_SWITCH_FILE", "STOP_GRID"),
        stop_loss_pct=float(os.getenv("GRID_STOP_LOSS_PCT", "15.0")),
        state_file=os.getenv("GRID_STATE_FILE", "data/grid_positions.json"),
        stop_loss_state_file=os.getenv(
            "GRID_STOP_LOSS_STATE_FILE", "data/grid_stop_loss_paused.json"
        ),
        pending_orders_file=os.getenv(
            "GRID_PENDING_ORDERS_FILE", "data/pending_orders_grid.json"
        ),
        lock_file=os.getenv("GRID_LOCK_FILE", "data/grid_bot.lock"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
    )

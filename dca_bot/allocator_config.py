"""
Konfiguration für den Kapital-Allocator (stufenlose Umschichtung
zwischen DCA-Bot und Trend-Following-Bot je nach Trendstärke).

Komplett eigenständig von config.py (DCA) und trend_config.py (Trend) -
eigene Env-Variablen mit ALLOCATOR_-Präfix, eigener Zustand, eigener
Notaus. Nutzt dieselben Binance-/Telegram-Zugangsdaten wie die anderen
Bots. Der Allocator platziert selbst nie Orders (nur `get_current_price`
wird genutzt) - `trading_enabled` gibt es hier bewusst nicht, da er
nichts zum Deaktivieren hat.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AllocatorConfig:
    api_key: str
    api_secret: str
    use_testnet: bool = True

    symbol: str = "BTCUSDT"
    ema_fast_period: int = 20
    ema_slow_period: int = 50

    # Ankerpunkte der linearen Interpolation (siehe allocator_signals.py) -
    # bewusster Ausgangspunkt, kein empirisch hergeleiteter Optimalwert;
    # nach den Backtest-Ergebnissen ggf. anzupassen.
    zero_anchor_pct: float = 0.0    # EMA-Abstand, ab dem 0% Trend-Anteil gilt
    full_anchor_pct: float = 3.0    # EMA-Abstand, ab dem 100% Trend-Anteil gilt

    smoothing_period: int = 24      # EMA-Glättungsperiode in Allocator-Zyklen
    interval_minutes: int = 60      # Wie oft neu berechnet wird
    notify_threshold_pp: float = 15.0  # Telegram nur ab so vielen Prozentpunkten Verschiebung

    kill_switch_file: str = "STOP_ALLOCATOR"
    state_file: str = "data/allocator_state.json"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    log_file: str = "logs/allocator.log"


def load_allocator_config() -> AllocatorConfig:
    """Liest alle Werte aus den Umgebungsvariablen und validiert sie."""
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    if not api_key or not api_secret or "dein_testnet" in api_key:
        raise ValueError(
            "BINANCE_API_KEY / BINANCE_API_SECRET sind nicht gesetzt. "
            "Kopiere .env.example zu .env und trage deine Testnet-Keys ein "
            "(https://testnet.binance.vision/)."
        )

    ema_fast_period = int(os.getenv("ALLOCATOR_EMA_FAST_PERIOD", "20"))
    ema_slow_period = int(os.getenv("ALLOCATOR_EMA_SLOW_PERIOD", "50"))
    if ema_fast_period <= 0 or ema_slow_period <= ema_fast_period:
        raise ValueError(
            "Ungültige EMA-Perioden: ALLOCATOR_EMA_FAST_PERIOD muss > 0 und "
            "kleiner als ALLOCATOR_EMA_SLOW_PERIOD sein "
            f"(aktuell: fast={ema_fast_period}, slow={ema_slow_period})."
        )

    zero_anchor_pct = float(os.getenv("ALLOCATOR_ZERO_ANCHOR_PCT", "0.0"))
    full_anchor_pct = float(os.getenv("ALLOCATOR_FULL_ANCHOR_PCT", "3.0"))
    if full_anchor_pct <= zero_anchor_pct:
        raise ValueError(
            "ALLOCATOR_FULL_ANCHOR_PCT muss größer als ALLOCATOR_ZERO_ANCHOR_PCT "
            f"sein (aktuell: zero={zero_anchor_pct}, full={full_anchor_pct})."
        )

    return AllocatorConfig(
        api_key=api_key,
        api_secret=api_secret,
        symbol=os.getenv("ALLOCATOR_SYMBOL", "BTCUSDT"),
        ema_fast_period=ema_fast_period,
        ema_slow_period=ema_slow_period,
        zero_anchor_pct=zero_anchor_pct,
        full_anchor_pct=full_anchor_pct,
        smoothing_period=int(os.getenv("ALLOCATOR_SMOOTHING_PERIOD", "24")),
        interval_minutes=int(os.getenv("ALLOCATOR_INTERVAL_MINUTES", "60")),
        notify_threshold_pp=float(os.getenv("ALLOCATOR_NOTIFY_THRESHOLD_PP", "15.0")),
        kill_switch_file=os.getenv("ALLOCATOR_KILL_SWITCH_FILE", "STOP_ALLOCATOR"),
        state_file=os.getenv("ALLOCATOR_STATE_FILE", "data/allocator_state.json"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
    )

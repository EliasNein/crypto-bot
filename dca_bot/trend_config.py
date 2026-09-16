"""
Konfiguration für den Trend-Following-Bot (EMA-Crossover mit
Trendstärke-Filter auf Tageskerzen).

Komplett eigenständig von config.py (DCA) und grid_config.py (Grid) -
eigene Env-Variablen mit TREND_-Präfix, eigener Zustand. Nutzt dieselben
Binance-/Telegram-Zugangsdaten wie die anderen Bots.

Defaults entsprechen exakt den im Backtest getesteten Werten (siehe
trend_backtest.py) - bewusst nicht verändert, um die Backtest-Ergebnisse
nicht zu entwerten.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class TrendConfig:
    api_key: str
    api_secret: str
    use_testnet: bool = True

    symbol: str = "BTCUSDT"
    ema_fast_period: int = 20
    ema_slow_period: int = 50
    min_gap_pct: float = 1.0        # Trendstärke-Filter: Mindestabstand der EMAs in %
    amount_per_trade: float = 15.0  # Positionsgröße pro Trade in Quote-Währung
    interval_hours: int = 24        # Tageskerzen -> einmal täglich prüfen

    trading_enabled: bool = False        # Muss explizit auf True gesetzt werden
    kill_switch_file: str = "STOP_TREND"  # Eigene Notaus-Datei, unabhängig von DCA/Grid
    stop_loss_pct: float = 10.0     # Fixer Stop-Loss unterhalb des Einstiegspreises in %
    # Abstand zwischen Stop-Preis und Limit-Preis der echten, exchange-
    # seitigen Stop-Loss-Order in %: limit_price = stop_price * (1 -
    # stop_limit_offset_pct/100). Ohne diesen Puffer könnte die Order bei
    # einem schnellen Kurssturz durch den Limit-Preis "durchrutschen" und
    # ungefüllt im Orderbuch hängen bleiben.
    stop_limit_offset_pct: float = 0.5
    state_file: str = "data/trend_ledger.json"
    stop_loss_state_file: str = "data/trend_stop_loss_paused.json"

    # Siehe config.py (DCA) für die Begründung dieser drei Felder -
    # Präfix der selbstvergebenen Order-IDs, offene Order-Fragen (K2)
    # und Schutz gegen doppelten Bot-Start. Jeweils eigene Dateien,
    # komplett getrennt von DCA/Grid.
    bot_name: str = "trend"
    pending_orders_file: str = "data/pending_orders_trend.json"
    lock_file: str = "data/trend_bot.lock"

    # --- Kapital-Allocator (optional, siehe allocator.py) ---
    # Leer = deaktiviert (Default): der Bot verhält sich dann exakt wie
    # ohne Allocator, unverändertes Standardverhalten. Nur wenn explizit
    # auf den gleichen Pfad wie ALLOCATOR_STATE_FILE gesetzt, skaliert der
    # Bot den Betrag eines NEUEN Einstiegs anhand der dort geschriebenen
    # Zuteilung.
    allocator_state_file: str = ""

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Abstand zwischen zwei Lebenszeichen per Telegram in Stunden
    # (Sicherheitsreview-Punkt W13, siehe heartbeat.py). 0 = aus.
    # Bewusst EINE gemeinsame Variable fuer alle vier Bots, wie die
    # TELEGRAM_-Zugangsdaten auch - vier Praefix-Varianten waeren hier
    # nur Ballast.
    heartbeat_interval_hours: float = 24.0

    log_file: str = "logs/trend_bot.log"


def load_trend_config() -> TrendConfig:
    """Liest alle Werte aus den Umgebungsvariablen und validiert sie."""
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    if not api_key or not api_secret or "dein_testnet" in api_key:
        raise ValueError(
            "BINANCE_API_KEY / BINANCE_API_SECRET sind nicht gesetzt. "
            "Kopiere .env.example zu .env und trage deine Testnet-Keys ein "
            "(https://testnet.binance.vision/)."
        )

    ema_fast_period = int(os.getenv("TREND_EMA_FAST_PERIOD", "20"))
    ema_slow_period = int(os.getenv("TREND_EMA_SLOW_PERIOD", "50"))
    if ema_fast_period <= 0 or ema_slow_period <= ema_fast_period:
        raise ValueError(
            "Ungültige EMA-Perioden: TREND_EMA_FAST_PERIOD muss > 0 und "
            "kleiner als TREND_EMA_SLOW_PERIOD sein "
            f"(aktuell: fast={ema_fast_period}, slow={ema_slow_period})."
        )

    return TrendConfig(
        api_key=api_key,
        api_secret=api_secret,
        symbol=os.getenv("TREND_SYMBOL", "BTCUSDT"),
        ema_fast_period=ema_fast_period,
        ema_slow_period=ema_slow_period,
        min_gap_pct=float(os.getenv("TREND_MIN_GAP_PCT", "1.0")),
        amount_per_trade=float(os.getenv("TREND_AMOUNT_PER_TRADE", "15.0")),
        interval_hours=int(os.getenv("TREND_INTERVAL_HOURS", "24")),
        trading_enabled=os.getenv("TREND_BOT_ENABLE_TRADING", "false").lower() == "true",
        kill_switch_file=os.getenv("TREND_KILL_SWITCH_FILE", "STOP_TREND"),
        stop_loss_pct=float(os.getenv("TREND_STOP_LOSS_PCT", "10.0")),
        stop_limit_offset_pct=float(os.getenv("TREND_STOP_LIMIT_OFFSET_PCT", "0.5")),
        state_file=os.getenv("TREND_STATE_FILE", "data/trend_ledger.json"),
        stop_loss_state_file=os.getenv(
            "TREND_STOP_LOSS_STATE_FILE", "data/trend_stop_loss_paused.json"
        ),
        pending_orders_file=os.getenv(
            "TREND_PENDING_ORDERS_FILE", "data/pending_orders_trend.json"
        ),
        lock_file=os.getenv("TREND_LOCK_FILE", "data/trend_bot.lock"),
        allocator_state_file=os.getenv("TREND_ALLOCATOR_STATE_FILE", ""),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        heartbeat_interval_hours=float(os.getenv("HEARTBEAT_INTERVAL_HOURS", "24.0")),
    )

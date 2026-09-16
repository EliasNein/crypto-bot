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

from dataclasses import dataclass

from dotenv import load_dotenv

from .config_guard import (
    ConfigError,
    env_bool,
    env_float,
    env_int,
    env_text,
    load_api_credentials,
    load_telegram_credentials,
    load_use_testnet,
    require_explicit_in_live,
    validate_halt_variable,
)

load_dotenv()


@dataclass(frozen=True)
class TrendConfig:
    api_key: str
    api_secret: str
    # Siehe config.py (DCA): kommt seit dem W12-Fix aus `USE_TESTNET`.
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
    """
    Liest alle Werte aus den Umgebungsvariablen und validiert sie.
    Zur Pflichtprüfung insgesamt siehe config_guard.py (W12).
    """
    use_testnet = load_use_testnet()
    api_key, api_secret = load_api_credentials(use_testnet=use_testnet)
    telegram_bot_token, telegram_chat_id = load_telegram_credentials(
        use_testnet=use_testnet
    )
    validate_halt_variable("TREND_BOT_HALT")

    require_explicit_in_live(
        "TREND_AMOUNT_PER_TRADE",
        use_testnet=use_testnet,
        hint="Das ist die Positionsgröße jedes Einstiegs.",
    )

    ema_fast_period = env_int("TREND_EMA_FAST_PERIOD", "20", gt=0)
    ema_slow_period = env_int("TREND_EMA_SLOW_PERIOD", "50", gt=0)
    if ema_slow_period <= ema_fast_period:
        raise ConfigError(
            "Ungültige EMA-Perioden: TREND_EMA_FAST_PERIOD muss kleiner als "
            "TREND_EMA_SLOW_PERIOD sein "
            f"(aktuell: fast={ema_fast_period}, slow={ema_slow_period})."
        )

    return TrendConfig(
        api_key=api_key,
        api_secret=api_secret,
        use_testnet=use_testnet,
        symbol=env_text("TREND_SYMBOL", "BTCUSDT", hint="Zum Beispiel BTCUSDT."),
        ema_fast_period=ema_fast_period,
        ema_slow_period=ema_slow_period,
        # 0 ist zulässig und heißt "kein Trendstärke-Filter" - dann zählt
        # jeder rohe EMA-Crossover als bestätigt (siehe
        # TrendSignalGenerator.feed).
        min_gap_pct=env_float("TREND_MIN_GAP_PCT", "1.0", ge=0, lt=100),
        amount_per_trade=env_float("TREND_AMOUNT_PER_TRADE", "15.0", gt=0),
        interval_hours=env_int("TREND_INTERVAL_HOURS", "24", gt=0),
        trading_enabled=env_bool("TREND_BOT_ENABLE_TRADING", "false"),
        kill_switch_file=env_text("TREND_KILL_SWITCH_FILE", "STOP_TREND"),
        # Anders als bei DCA und Grid ist 0 hier NICHT "aus", sondern
        # fatal: is_stop_loss_hit() vergleicht dann gegen den
        # Einstiegspreis selbst und löst beim ersten Zyklus aus, in dem
        # der Preis nicht gestiegen ist. Der Bot würde also jede Position
        # sofort wieder schließen und den Stop-Loss-Latch setzen.
        stop_loss_pct=env_float("TREND_STOP_LOSS_PCT", "10.0", gt=0, lt=100),
        # 0 hieße kein Puffer zwischen Stop- und Limit-Preis - genau der
        # Durchrutsch-Fall, gegen den dieser Wert existiert (siehe 6f).
        stop_limit_offset_pct=env_float(
            "TREND_STOP_LIMIT_OFFSET_PCT", "0.5", gt=0, lt=100
        ),
        state_file=env_text("TREND_STATE_FILE", "data/trend_ledger.json"),
        stop_loss_state_file=env_text(
            "TREND_STOP_LOSS_STATE_FILE", "data/trend_stop_loss_paused.json"
        ),
        pending_orders_file=env_text(
            "TREND_PENDING_ORDERS_FILE", "data/pending_orders_trend.json"
        ),
        lock_file=env_text("TREND_LOCK_FILE", "data/trend_bot.lock"),
        # Leer ist hier die gültige Bedeutung "Allocator-Anbindung aus".
        allocator_state_file=env_text(
            "TREND_ALLOCATOR_STATE_FILE", "", required=False
        ),
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        heartbeat_interval_hours=env_float("HEARTBEAT_INTERVAL_HOURS", "24.0", ge=0),
    )

"""
Konfiguration für den Kapital-Allocator (stufenlose Umschichtung
zwischen DCA-Bot und Trend-Following-Bot je nach Trendstärke).

Komplett eigenständig von config.py (DCA) und trend_config.py (Trend) -
eigene Env-Variablen mit ALLOCATOR_-Präfix, eigener Zustand, eigener
Notaus. Nutzt dieselben Binance-/Telegram-Zugangsdaten wie die anderen
Bots. Der Allocator platziert selbst nie Orders - `trading_enabled` gibt
es hier bewusst nicht, da er nichts zum Deaktivieren hat. Seit dem
W9-Fix bezieht er seine Kursdaten ausserdem ausschliesslich aus
oeffentlichen Tageskerzen (`fetch_historical_klines`, dieselbe Quelle
wie der Backtest) statt aus einem Spot-Ticker ueber den
authentifizierten Client.
"""

from __future__ import annotations

from dataclasses import dataclass

from dotenv import load_dotenv

from .config_guard import (
    GLOBAL_KILL_SWITCH_NAME,
    ConfigError,
    env_float,
    env_int,
    env_text,
    load_api_credentials,
    load_telegram_credentials,
    load_use_testnet,
    validate_halt_variable,
)

load_dotenv()


@dataclass(frozen=True)
class AllocatorConfig:
    api_key: str
    api_secret: str
    # Siehe config.py (DCA): kommt seit dem W12-Fix aus `USE_TESTNET`.
    # Gilt auch hier, obwohl der Allocator nie handelt - er liest Kurs-
    # und Kontodaten und muss dafür dieselbe Umgebung verwenden wie die
    # Bots, deren Ordergröße er steuert.
    use_testnet: bool = True

    symbol: str = "BTCUSDT"
    ema_fast_period: int = 20
    ema_slow_period: int = 50

    # Ankerpunkte der linearen Interpolation (siehe allocator_signals.py) -
    # bewusster Ausgangspunkt, kein empirisch hergeleiteter Optimalwert;
    # nach den Backtest-Ergebnissen ggf. anzupassen.
    zero_anchor_pct: float = 0.0    # EMA-Abstand, ab dem 0% Trend-Anteil gilt
    full_anchor_pct: float = 3.0    # EMA-Abstand, ab dem 100% Trend-Anteil gilt

    # EMA-Glättung der Zuteilung, in TAGEN. Seit dem W9-Fix rückt sie
    # genau einmal pro eingespeistem Tagesschlusskurs vor, nicht mehr
    # einmal pro Zyklus (siehe allocator.py) - damit ist der Wert
    # direkt mit `--smoothing-period-days` aus allocator_backtest.py
    # vergleichbar, dessen Default 3.0 ist. Vorher bedeuteten 24
    # Zyklen à 60 Minuten rund einen Tag, also deutlich schneller als
    # im Backtest.
    smoothing_period: int = 3
    # Wie oft der Prozess aufwacht: Zustand neu veröffentlichen,
    # Notaus prüfen, und einen etwaigen neuen Tag einspeisen. NICHT
    # der Takt der EMA-Berechnung - siehe smoothing_period oben.
    interval_minutes: int = 60
    notify_threshold_pp: float = 15.0  # Telegram nur ab so vielen Prozentpunkten Verschiebung

    kill_switch_file: str = "STOP_ALLOCATOR"
    state_file: str = "data/allocator_state.json"

    bot_name: str = "allocator"
    # Bewusst LEER: der Allocator platziert nie Orders, es kann also auch
    # nie eine offene Order-Frage geben (siehe pending_orders.py). Das
    # Feld existiert trotzdem, und die place_*-Methoden in
    # binance_client.py weisen einen leeren Wert aktiv zurück - damit
    # wird "der Allocator handelt nicht" von einer Absichtserklärung im
    # Docstring zu einer Bedingung, die der Code erzwingt.
    pending_orders_file: str = ""
    # Lockfile wie bei den drei Trading-Bots: zwei Allocator-Prozesse
    # würden sich dieselbe State-Datei überschreiben (Lost Update) -
    # dieselbe Fehlerklasse wie ein doppelt gestarteter Bot auf einem
    # Ledger, auch wenn hier keine Order daran hängt.
    lock_file: str = "data/allocator.lock"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Abstand zwischen zwei Lebenszeichen per Telegram in Stunden
    # (Sicherheitsreview-Punkt W13, siehe heartbeat.py). 0 = aus.
    # Bewusst EINE gemeinsame Variable fuer alle vier Bots, wie die
    # TELEGRAM_-Zugangsdaten auch - vier Praefix-Varianten waeren hier
    # nur Ballast.
    heartbeat_interval_hours: float = 24.0

    log_file: str = "logs/allocator.log"


def load_allocator_config() -> AllocatorConfig:
    """
    Liest alle Werte aus den Umgebungsvariablen und validiert sie.
    Zur Pflichtprüfung insgesamt siehe config_guard.py (W12).

    `require_explicit_in_live` gibt es hier bewusst nicht: der Allocator
    platziert nie Orders und hat deshalb keinen Wert, der eine
    Positionsgröße bestimmt.
    """
    use_testnet = load_use_testnet()
    api_key, api_secret = load_api_credentials(use_testnet=use_testnet)
    telegram_bot_token, telegram_chat_id = load_telegram_credentials(
        use_testnet=use_testnet
    )
    validate_halt_variable("ALLOCATOR_HALT")
    # Der globale Notaus gilt fuer alle vier Bots - ein Tippfehler
    # dort haette also vierfache Wirkung (bzw. vierfache Nicht-Wirkung).
    validate_halt_variable(GLOBAL_KILL_SWITCH_NAME)

    ema_fast_period = env_int("ALLOCATOR_EMA_FAST_PERIOD", "20", gt=0)
    ema_slow_period = env_int("ALLOCATOR_EMA_SLOW_PERIOD", "50", gt=0)
    if ema_slow_period <= ema_fast_period:
        raise ConfigError(
            "Ungültige EMA-Perioden: ALLOCATOR_EMA_FAST_PERIOD muss kleiner "
            "als ALLOCATOR_EMA_SLOW_PERIOD sein "
            f"(aktuell: fast={ema_fast_period}, slow={ema_slow_period})."
        )

    zero_anchor_pct = env_float("ALLOCATOR_ZERO_ANCHOR_PCT", "0.0", ge=0, lt=100)
    full_anchor_pct = env_float("ALLOCATOR_FULL_ANCHOR_PCT", "3.0", gt=0, lt=100)
    if full_anchor_pct <= zero_anchor_pct:
        raise ConfigError(
            "ALLOCATOR_FULL_ANCHOR_PCT muss größer als ALLOCATOR_ZERO_ANCHOR_PCT "
            f"sein (aktuell: zero={zero_anchor_pct}, full={full_anchor_pct})."
        )

    return AllocatorConfig(
        api_key=api_key,
        api_secret=api_secret,
        use_testnet=use_testnet,
        symbol=env_text("ALLOCATOR_SYMBOL", "BTCUSDT", hint="Zum Beispiel BTCUSDT."),
        ema_fast_period=ema_fast_period,
        ema_slow_period=ema_slow_period,
        zero_anchor_pct=zero_anchor_pct,
        full_anchor_pct=full_anchor_pct,
        # In TAGEN, siehe Dataclass oben (W9). 0 wäre kein "keine
        # Glättung", sondern ein Multiplikator von 2/(0+1) = 2 in
        # smooth_fraction() - die Glättung würde über das Ziel
        # hinausschießen statt zu dämpfen.
        smoothing_period=env_int("ALLOCATOR_SMOOTHING_PERIOD", "3", gt=0),
        # 0 wäre ein Busy-Loop (siehe GRID_INTERVAL_MINUTES).
        interval_minutes=env_int("ALLOCATOR_INTERVAL_MINUTES", "60", gt=0),
        # 0 ist zulässig und heißt "bei jeder Änderung benachrichtigen".
        notify_threshold_pp=env_float(
            "ALLOCATOR_NOTIFY_THRESHOLD_PP", "15.0", ge=0, le=100
        ),
        kill_switch_file=env_text("ALLOCATOR_KILL_SWITCH_FILE", "STOP_ALLOCATOR"),
        state_file=env_text("ALLOCATOR_STATE_FILE", "data/allocator_state.json"),
        lock_file=env_text("ALLOCATOR_LOCK_FILE", "data/allocator.lock"),
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        heartbeat_interval_hours=env_float("HEARTBEAT_INTERVAL_HOURS", "24.0", ge=0),
    )

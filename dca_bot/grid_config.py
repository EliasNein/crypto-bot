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
class GridConfig:
    # --- Binance API (gleiche Zugangsdaten wie der DCA-Bot) ---
    api_key: str
    api_secret: str
    # Siehe config.py (DCA): kommt seit dem W12-Fix aus `USE_TESTNET`.
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

    # Abstand zwischen zwei Lebenszeichen per Telegram in Stunden
    # (Sicherheitsreview-Punkt W13, siehe heartbeat.py). 0 = aus.
    # Bewusst EINE gemeinsame Variable fuer alle vier Bots, wie die
    # TELEGRAM_-Zugangsdaten auch - vier Praefix-Varianten waeren hier
    # nur Ballast.
    heartbeat_interval_hours: float = 24.0

    # --- Logging ---
    log_file: str = "logs/grid_bot.log"


def load_grid_config() -> GridConfig:
    """
    Liest alle Werte aus den Umgebungsvariablen und validiert sie.

    Zur Pflichtprüfung insgesamt siehe config_guard.py (W12). Für den
    Grid-Bot ist die Größenprüfung besonders wichtig: Er hat bewusst KEIN
    Tageslimit (siehe Modul-Docstring oben), die maximale Kapitalbindung
    ergibt sich allein aus Stufenzahl x `amount_per_level`. Damit sind
    `GRID_LOWER_LIMIT`, `GRID_UPPER_LIMIT`, `GRID_SPACING_PCT` und
    `GRID_AMOUNT_PER_LEVEL` die einzige Obergrenze, die es gibt - im
    Live-Modus müssen sie deshalb ausdrücklich in der `.env` stehen und
    dürfen nicht auf Testnet-Defaults zurückfallen (siehe W16).
    """
    use_testnet = load_use_testnet()
    api_key, api_secret = load_api_credentials(use_testnet=use_testnet)
    telegram_bot_token, telegram_chat_id = load_telegram_credentials(
        use_testnet=use_testnet
    )
    validate_halt_variable("GRID_BOT_HALT")

    for name, hint in (
        ("GRID_LOWER_LIMIT", "Untere Grid-Grenze."),
        ("GRID_UPPER_LIMIT", "Obere Grid-Grenze."),
        ("GRID_AMOUNT_PER_LEVEL", "Betrag pro Stufe."),
    ):
        require_explicit_in_live(
            name,
            use_testnet=use_testnet,
            hint=f"{hint} Spanne, Abstand und Betrag/Stufe bestimmen "
            "zusammen die maximale Kapitalbindung - beim Grid-Bot die "
            "einzige Obergrenze, ein Tageslimit gibt es hier nicht.",
        )

    lower_limit = env_float("GRID_LOWER_LIMIT", "70000.0", gt=0)
    upper_limit = env_float("GRID_UPPER_LIMIT", "90000.0", gt=0)
    grid_spacing_pct = env_float("GRID_SPACING_PCT", "1.5", gt=0, lt=100)

    if upper_limit <= lower_limit:
        raise ConfigError(
            "Ungültige Grid-Parameter: GRID_UPPER_LIMIT muss größer als "
            f"GRID_LOWER_LIMIT sein (aktuell: lower={lower_limit}, "
            f"upper={upper_limit})."
        )

    return GridConfig(
        api_key=api_key,
        api_secret=api_secret,
        use_testnet=use_testnet,
        symbol=env_text("GRID_SYMBOL", "BTCUSDT", hint="Zum Beispiel BTCUSDT."),
        lower_limit=lower_limit,
        upper_limit=upper_limit,
        grid_spacing_pct=grid_spacing_pct,
        amount_per_level=env_float("GRID_AMOUNT_PER_LEVEL", "15.0", gt=0),
        # 0 wäre ein Busy-Loop: `time.sleep(0)` in main_grid.py, und der
        # Bot würde die Preis-API im Takt der Schleife befragen.
        interval_minutes=env_int("GRID_INTERVAL_MINUTES", "5", gt=0),
        trading_enabled=env_bool("GRID_BOT_ENABLE_TRADING", "false"),
        kill_switch_file=env_text("GRID_KILL_SWITCH_FILE", "STOP_GRID"),
        # 0 schaltet den Trendbruch-Stop-Loss ab (siehe
        # is_trend_break_stop_loss_hit), deshalb ge=0. Über 100 ergäbe
        # eine negative Schwelle, die nie erreicht werden kann - der
        # Stop-Loss wäre dann still wirkungslos statt abgeschaltet.
        stop_loss_pct=env_float("GRID_STOP_LOSS_PCT", "15.0", ge=0, lt=100),
        state_file=env_text("GRID_STATE_FILE", "data/grid_positions.json"),
        stop_loss_state_file=env_text(
            "GRID_STOP_LOSS_STATE_FILE", "data/grid_stop_loss_paused.json"
        ),
        pending_orders_file=env_text(
            "GRID_PENDING_ORDERS_FILE", "data/pending_orders_grid.json"
        ),
        lock_file=env_text("GRID_LOCK_FILE", "data/grid_bot.lock"),
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        heartbeat_interval_hours=env_float("HEARTBEAT_INTERVAL_HOURS", "24.0", ge=0),
    )

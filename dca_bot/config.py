"""
Zentrale Konfiguration für den DCA-Bot.

Alle Einstellungen werden hier gebündelt, damit main.py und strategy.py
nicht direkt mit Umgebungsvariablen hantieren müssen. Das erleichtert
später auch Unit-Tests (man kann eine Config einfach mocken).
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

# Lädt Variablen aus einer .env-Datei im Projektverzeichnis, falls vorhanden.
load_dotenv()


@dataclass(frozen=True)
class Config:
    # --- Binance API ---
    api_key: str
    api_secret: str
    # Testnet oder echtes Konto. Der Default bleibt `True`, aber der Wert
    # kommt seit dem W12-Fix aus `USE_TESTNET` und nicht mehr aus einem
    # hart codierten Literal - "live gehen" ist damit ein
    # Konfigurationsschritt, kein Code-Edit. Siehe config_guard.py.
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
    """
    Liest alle Werte aus den Umgebungsvariablen und validiert sie.

    Seit dem W12-Fix laufen alle Zugriffe über die Helfer in
    config_guard.py: sie unterscheiden "nicht gesetzt" (Default gilt) von
    "auf leer gesetzt" (Fehler), prüfen Wertebereiche und nennen in jeder
    Meldung die betroffene Variable. Vorher scheiterte z.B. ein
    Tippfehler in einer Zahl mit "could not convert string to float:
    'abc'" - ohne zu sagen, welche der gut zwei Dutzend Variablen gemeint
    war.

    Symbol, Kaufbetrag, Intervall und Tageslimit sind dabei neu aus der
    `.env` lesbar (`DCA_SYMBOL`, `DCA_QUOTE_AMOUNT`, `DCA_INTERVAL_HOURS`,
    `DCA_MAX_DAILY_SPEND`). Sie standen als einzige der vier Bots
    ausschließlich als Code-Default hier - genau der Zustand, den W12
    beanstandet. Die Defaults sind unverändert, ein bestehendes
    Deployment verhält sich also exakt wie vorher.
    """
    use_testnet = load_use_testnet()
    api_key, api_secret = load_api_credentials(use_testnet=use_testnet)
    telegram_bot_token, telegram_chat_id = load_telegram_credentials(
        use_testnet=use_testnet
    )

    # Der Notaus wird zur Laufzeit bewusst tolerant gelesen (siehe
    # KillSwitch) - ein Tippfehler dort bedeutet aber "kein Notaus", und
    # der Start ist der einzige Moment, das gefahrlos zu bemerken.
    validate_halt_variable("DCA_BOT_HALT")

    # Positionsgröße und Tageslimit müssen im Live-Modus ausdrücklich
    # dastehen: die Defaults stammen aus der Testnet-Phase.
    require_explicit_in_live(
        "DCA_QUOTE_AMOUNT",
        use_testnet=use_testnet,
        hint="Das ist der Betrag, der bei jedem Kauf tatsächlich ausgegeben wird.",
    )
    require_explicit_in_live(
        "DCA_MAX_DAILY_SPEND",
        use_testnet=use_testnet,
        hint="Das ist die Notbremse gegen unbegrenzte Käufe bei einem Bug.",
    )

    quote_amount = env_float("DCA_QUOTE_AMOUNT", "15.0", gt=0)
    max_daily_spend = env_float("DCA_MAX_DAILY_SPEND", "50.0", gt=0)
    if max_daily_spend < quote_amount:
        raise ConfigError(
            f"DCA_MAX_DAILY_SPEND ({max_daily_spend}) ist kleiner als "
            f"DCA_QUOTE_AMOUNT ({quote_amount}) - damit würde das Tageslimit "
            "JEDEN Kauf blockieren und der Bot liefe dauerhaft leer."
        )

    return Config(
        api_key=api_key,
        api_secret=api_secret,
        use_testnet=use_testnet,
        symbol=env_text(
            "DCA_SYMBOL", "BTCUSDT", hint="Zum Beispiel BTCUSDT."
        ),
        quote_amount=quote_amount,
        interval_hours=env_int("DCA_INTERVAL_HOURS", "24", gt=0),
        trading_enabled=env_bool("DCA_BOT_ENABLE_TRADING", "false"),
        max_daily_spend=max_daily_spend,
        kill_switch_file=env_text("DCA_BOT_KILL_SWITCH_FILE", "STOP"),
        # 0 schaltet den Portfolio-Stop-Loss ab (dokumentiertes
        # Verhalten, siehe PortfolioStopLoss) - deshalb ge=0 und nicht
        # gt=0. Über 100 wäre dagegen sinnlos: mehr als den gesamten
        # Einsatz kann man nicht verlieren.
        stop_loss_pct=env_float("DCA_BOT_STOP_LOSS_PCT", "25.0", ge=0, le=100),
        state_file=env_text("DCA_BOT_STATE_FILE", "data/trade_ledger.json"),
        stop_loss_state_file=env_text(
            "DCA_BOT_STOP_LOSS_STATE_FILE", "data/stop_loss_paused.json"
        ),
        # Ein leerer Pfad würde die K2-Absicherung abschalten - das fiele
        # sonst erst bei der ersten Order auf (siehe _place_order).
        pending_orders_file=env_text(
            "DCA_PENDING_ORDERS_FILE", "data/pending_orders_dca.json"
        ),
        lock_file=env_text("DCA_LOCK_FILE", "data/dca_bot.lock"),
        # Leer ist hier die gültige Bedeutung "Allocator-Anbindung aus".
        allocator_state_file=env_text(
            "DCA_ALLOCATOR_STATE_FILE", "", required=False
        ),
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        # 0 schaltet den Heartbeat ab (siehe heartbeat.py).
        heartbeat_interval_hours=env_float("HEARTBEAT_INTERVAL_HOURS", "24.0", ge=0),
    )

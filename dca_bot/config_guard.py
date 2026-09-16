"""
Gemeinsame Konfigurationspruefung und Live-Modus-Schalter fuer alle vier
Bots (Sicherheitsreview-Punkt W12).

Zwei Probleme werden hier geloest:

1. **Es gab keinen Live-Schalter.** `use_testnet: bool = True` stand hart
   in allen vier Config-Dataclasses, und keine der vier `load_*`-
   Funktionen las dafuer eine Umgebungsvariable. "Live gehen" waere damit
   ein Code-Edit gewesen statt eines Konfigurationsschritts - und ein
   Code-Edit hinterlaesst keine Spur in der `.env`, laesst sich nicht per
   Deployment zurueckdrehen und wird beim naechsten `git pull` still
   ueberschrieben. Jetzt entscheidet `USE_TESTNET` (Default `true`), und
   der Wechsel auf `false` ist ausdruecklich KEIN stiller Vorgang (siehe
   `announce_trading_mode`).

2. **Fehlkonfiguration lief mit Defaults weiter.** Geprueft wurden bisher
   nur API-Key/Secret und ein paar strategiespezifische Plausibilitaeten.
   Ein leeres `GRID_SYMBOL=`, ein `GRID_INTERVAL_MINUTES=0` (ein
   Busy-Loop, der die API im Takt der Schleife befragt) oder ein
   Tippfehler in einer Zahl fielen entweder gar nicht auf oder erst zur
   Laufzeit - im schlechtesten Fall mit einer Meldung wie "could not
   convert string to float: 'abc'", die nicht einmal sagt, WELCHE
   Variable gemeint ist.

Warum das hier gebuendelt steht statt viermal kopiert: Die vier
Config-Module sind bewusst voneinander unabhaengig (eigenes Praefix,
eigene Dataclass, eigener Zustand) - das bleibt so, jede `load_*`-
Funktion behaelt ihre eigene Liste an Pruefungen. Der MECHANISMUS
dahinter ist aber sicherheitsrelevanter Code, und den vierfach zu
kopieren ist genau das Muster, das der Review als N3 kritisiert hat.
Gleiche Begruendung wie bei `safe_startup_reconciliation()` in
pending_orders.py.
"""

from __future__ import annotations

import logging
import math
import os
import sys

# Name der einen Variable, die ueber Testnet und Echtgeld entscheidet.
# Bewusst OHNE Bot-Praefix: alle vier Prozesse handeln zwangslaeufig auf
# derselben Boerse - vier getrennte Schalter koennten auseinanderlaufen,
# und ein halb-live laufendes System waere schlimmer als beides ganz.
USE_TESTNET_VAR = "USE_TESTNET"

# Werte, die als Platzhalter aus `.env.example` erkannt werden. Ein
# kopierter Platzhalter ist kein "gesetzter Wert": ein
# TELEGRAM_BOT_TOKEN=dein_telegram_bot_token laeuft nicht auf einen
# Fehler beim Start, sondern auf ein stilles HTTP 401 bei JEDEM Versand -
# also genau dann, wenn die Nachricht gebraucht wird.
_PLACEHOLDER_PREFIXES = ("dein_", "deine_", "your_")
_PLACEHOLDER_SUBSTRINGS = ("dein_testnet",)

_BANNER_WIDTH = 66


class ConfigError(ValueError):
    """
    Eine Konfiguration, mit der dieser Bot nicht starten darf.

    Erbt bewusst von `ValueError`: die vier `load_*`-Funktionen warfen
    bisher `ValueError`, und alles, was darauf faengt, soll unveraendert
    weiterfunktionieren. Der eigene Typ erlaubt den `main*.py` trotzdem,
    eine Konfigurationsmeldung von einem beliebigen anderen Fehler zu
    unterscheiden - siehe `report_config_error`.
    """


# --- Wahrheitswerte --------------------------------------------------------


def parse_bool_strict(name: str, raw: object) -> bool:
    """
    Liest einen Wahrheitswert und akzeptiert AUSSCHLIESSLICH "true" oder
    "false" (getrimmt, Gross-/Kleinschreibung egal).

    Die uebliche Kurzform `os.getenv(name, "false").lower() == "true"` ist
    hier nicht gut genug, und zwar wegen der Fehlerrichtung: Sie bildet
    jeden Tippfehler auf `False` ab. Fuer `USE_TESTNET` hiesse das
    `USE_TESTNET=ture` -> nicht Testnet -> **live mit echtem Geld**, und
    zwar ohne dass irgendwo ein Fehler auftaucht. Genau die Variable, bei
    der ein stiller Fehlgriff am teuersten ist, haette damit die
    schlechteste Fehlerbehandlung.

    Deshalb: unbekannter Wert -> Abbruch, nicht raten.
    """
    value = str(raw).strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise ConfigError(
        f"{name}={str(raw).strip()!r} ist kein gueltiger Wahrheitswert. "
        "Erlaubt sind ausschliesslich 'true' oder 'false'. Ein Tippfehler "
        "wird hier bewusst NICHT stillschweigend als 'false' gelesen - bei "
        f"{USE_TESTNET_VAR} waere das der Unterschied zwischen Testnet und "
        "echtem Geld."
    )


def env_bool(name: str, default: str) -> bool:
    """Wie `parse_bool_strict`, liest den Wert selbst aus der Umgebung."""
    raw = os.getenv(name)
    return parse_bool_strict(name, default if raw is None else raw)


def load_use_testnet() -> bool:
    """
    Der Live-Schalter des Projekts. Default `true` - wer nichts
    konfiguriert, landet auf dem Testnet.

    Bewusst ein Default und keine Pflichtangabe: beide Server haben die
    Variable heute nicht in ihrer `.env`, und ein Update darf ihr
    Verhalten nicht veraendern. Der gefaehrliche Zustand ist "live, ohne
    es zu wissen", nicht "Testnet, ohne es hingeschrieben zu haben".
    """
    return env_bool(USE_TESTNET_VAR, "true")


def validate_halt_variable(name: str) -> None:
    """
    Prueft beim START, dass eine gesetzte Notaus-Variable (z.B.
    `GRID_BOT_HALT`) einen verstehbaren Wert hat.

    `KillSwitch.is_set()` liest sie zur Laufzeit bewusst weiterhin
    tolerant (`... == "true"`), und das bleibt auch so: Ein Notaus-Check,
    der bei einem Tippfehler eine Exception wirft, wuerde den Bot alle
    fuenf Sekunden sprengen statt ihn zu schuetzen.

    Nur ist die Fehlerrichtung dort die unangenehme - `GRID_BOT_HALT=ture`
    heisst "kein Notaus", waehrend der Mensch, der es getippt hat, vom
    Gegenteil ausgeht. Der Start ist der einzige Moment, in dem sich das
    gefahrlos bemerken laesst, und genau da passiert es jetzt.
    """
    raw = os.getenv(name)
    if raw is None:
        return
    parse_bool_strict(name, raw)


# --- Zahlen und Text -------------------------------------------------------


def _bounds_text(gt, ge, lt, le) -> str:
    parts = []
    if gt is not None:
        parts.append(f"groesser als {gt}")
    if ge is not None:
        parts.append(f"mindestens {ge}")
    if lt is not None:
        parts.append(f"kleiner als {lt}")
    if le is not None:
        parts.append(f"hoechstens {le}")
    return " und ".join(parts)


def _check_bounds(name: str, value: float, gt, ge, lt, le) -> None:
    if (
        (gt is not None and not value > gt)
        or (ge is not None and not value >= ge)
        or (lt is not None and not value < lt)
        or (le is not None and not value <= le)
    ):
        raise ConfigError(
            f"{name}={value} liegt ausserhalb des gueltigen Bereichs - der "
            f"Wert muss {_bounds_text(gt, ge, lt, le)} sein."
        )


def _raw_value(name: str, default: str) -> str:
    """
    Der Rohwert einer Variable.

    Unterscheidet bewusst zwischen "nicht gesetzt" (dann gilt der
    dokumentierte Default) und "auf leer gesetzt". `GRID_SYMBOL=` in der
    `.env` ist kein fehlender Eintrag, sondern eine Angabe - eine leere,
    und die soll auffallen statt durch den Default ersetzt zu werden.
    """
    raw = os.getenv(name)
    return default if raw is None else raw


def env_float(name: str, default: str, *, gt=None, ge=None, lt=None, le=None) -> float:
    """Kommazahl aus der Umgebung, mit Bereichspruefung und klarer Meldung."""
    text = _raw_value(name, default).strip()
    if not text:
        raise ConfigError(
            f"{name} ist auf einen leeren Wert gesetzt. Entweder eine Zahl "
            "eintragen oder die Zeile ganz entfernen, damit der Default gilt."
        )
    try:
        value = float(text)
    except ValueError:
        raise ConfigError(
            f"{name}={text!r} ist keine Zahl. Erwartet wird ein Wert wie "
            "'15.0' (Dezimalpunkt, kein Komma, keine Einheit)."
        ) from None
    if math.isnan(value) or math.isinf(value):
        raise ConfigError(f"{name}={text!r} ist keine endliche Zahl.")
    _check_bounds(name, value, gt, ge, lt, le)
    return value


def env_int(name: str, default: str, *, gt=None, ge=None, lt=None, le=None) -> int:
    """Ganzzahl aus der Umgebung, mit Bereichspruefung und klarer Meldung."""
    text = _raw_value(name, default).strip()
    if not text:
        raise ConfigError(
            f"{name} ist auf einen leeren Wert gesetzt. Entweder eine ganze "
            "Zahl eintragen oder die Zeile ganz entfernen, damit der Default "
            "gilt."
        )
    try:
        value = int(text)
    except ValueError:
        raise ConfigError(
            f"{name}={text!r} ist keine ganze Zahl. Erwartet wird ein Wert "
            "wie '60' (keine Nachkommastellen, keine Einheit)."
        ) from None
    _check_bounds(name, value, gt, ge, lt, le)
    return value


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered.startswith(_PLACEHOLDER_PREFIXES):
        return True
    return any(marker in lowered for marker in _PLACEHOLDER_SUBSTRINGS)


def env_text(name: str, default: str, *, required: bool = True, hint: str = "") -> str:
    """
    Textwert aus der Umgebung.

    `required=True` lehnt einen leeren Wert ab; `required=False` ist fuer
    Einstellungen gedacht, bei denen leer eine gueltige Bedeutung hat
    (z.B. `DCA_ALLOCATOR_STATE_FILE` = Allocator-Anbindung aus).
    Platzhalter aus `.env.example` gelten in beiden Faellen als nicht
    gesetzt.
    """
    value = _raw_value(name, default).strip()
    if not value:
        if required:
            raise ConfigError(f"{name} ist nicht gesetzt oder leer. {hint}".strip())
        return ""
    if _looks_like_placeholder(value):
        raise ConfigError(
            f"{name}={value!r} ist noch der Platzhalter aus .env.example. "
            "Entweder einen echten Wert eintragen oder die Zeile leeren, "
            "falls die Funktion nicht genutzt werden soll. Ein Platzhalter "
            "wuerde sonst erst zur Laufzeit auffallen - und zwar als "
            "stiller Fehlschlag."
        )
    return value


# --- Zugangsdaten ----------------------------------------------------------


def load_api_credentials(*, use_testnet: bool) -> tuple[str, str]:
    """
    Binance-Zugangsdaten. Ersetzt den bisher viermal kopierten Block.

    Der Hinweistext haengt am Modus: Im Testnet ist der richtige Weg
    testnet.binance.vision, im Live-Modus waeren genau das die falschen
    Keys - und ein Testnet-Key gegen die echte Boerse scheitert mit einem
    Authentifizierungsfehler, der nicht verraet, woran es lag.
    """
    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()

    if not api_key or not api_secret:
        where = (
            "Testnet-Keys bekommst du unter https://testnet.binance.vision/"
            if use_testnet
            else f"Achtung: {USE_TESTNET_VAR}=false - hier werden die Keys "
            "des ECHTEN Binance-Kontos gebraucht, nicht die des Testnets."
        )
        raise ConfigError(
            "BINANCE_API_KEY / BINANCE_API_SECRET sind nicht gesetzt. "
            f"Kopiere .env.example zu .env und trage deine Keys ein. {where}"
        )

    if _looks_like_placeholder(api_key) or _looks_like_placeholder(api_secret):
        raise ConfigError(
            "BINANCE_API_KEY / BINANCE_API_SECRET enthalten noch einen "
            "Platzhalter aus .env.example statt echter Zugangsdaten."
        )

    return api_key, api_secret


def load_telegram_credentials(*, use_testnet: bool) -> tuple[str, str]:
    """
    Telegram-Zugangsdaten - optional im Testnet, **Pflicht im Live-Modus**.

    Im Testnet bleibt Telegram wie bisher abschaltbar (leer lassen). Im
    Live-Modus nicht: Ohne Kanal kommen ausgerechnet die Meldungen nicht
    an, die dort zaehlen - `[ORDER-UNKLAR]` (es ist offen, ob eine Order
    an der Boerse existiert), `[STOP-LOSS]`, `[REKONZILIATION]` und der
    `[HEARTBEAT]`, an dessen Ausbleiben ein toter Bot ueberhaupt erst
    auffaellt. Ein Live-Bot, den man nur bemerkt, wenn man von sich aus
    ins Log schaut, ist kein ueberwachter Live-Bot.
    """
    token = env_text("TELEGRAM_BOT_TOKEN", "", required=False)
    chat_id = env_text("TELEGRAM_CHAT_ID", "", required=False)

    if not use_testnet and not (token and chat_id):
        raise ConfigError(
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID muessen im Live-Modus "
            f"({USE_TESTNET_VAR}=false) gesetzt sein. Ohne sie gaebe es "
            "keinen Zustellweg fuer [ORDER-UNKLAR], [STOP-LOSS] und "
            "[HEARTBEAT] - im Echtgeld-Betrieb genau die Meldungen, die "
            "nicht verloren gehen duerfen. Im Testnet bleibt Telegram "
            "weiterhin optional."
        )

    return token, chat_id


def require_explicit_in_live(name: str, *, use_testnet: bool, hint: str) -> None:
    """
    Verlangt, dass eine Variable im Live-Modus AUSDRUECKLICH in der
    Umgebung steht, statt auf ihren Default zurueckzufallen.

    Gedacht fuer die Werte, die die Positionsgroesse bestimmen. Die
    Defaults im Code (15.00 pro Kauf, Grid-Spanne 70k-90k) stammen aus
    der Testnet-Phase, wo eine falsche Groesse folgenlos ist. Live sind
    genau sie die Stellschraube fuer die tatsaechliche Kapitalbindung -
    und ein vergessener Eintrag saehe im Log exakt aus wie ein bewusst
    gewaehlter Wert (siehe W16: Stufenzahl x Betrag/Stufe ist beim
    Grid-Bot die EINZIGE Obergrenze, ein Tageslimit gibt es dort nicht).
    """
    if use_testnet:
        return
    if os.getenv(name) is None:
        raise ConfigError(
            f"{name} muss im Live-Modus ({USE_TESTNET_VAR}=false) "
            "ausdruecklich in der .env stehen - der Default aus dem Code "
            f"gilt hier nicht. {hint}"
        )


# --- Live-Modus sichtbar machen -------------------------------------------


def _banner(lines: list[str]) -> list[str]:
    edge = "!" * _BANNER_WIDTH
    inner = _BANNER_WIDTH - 10
    return [edge] + ["!!!  " + line.ljust(inner) + "  !!!" for line in lines] + [edge]


def mode_label(use_testnet: bool) -> str:
    """Kurzform fuer das Start-Banner der vier `main*.py`."""
    return "TESTNET (kein echtes Geld)" if use_testnet else "LIVE (ECHTES GELD)"


def announce_trading_mode(
    bot_logger: logging.Logger,
    bot_label: str,
    *,
    use_testnet: bool,
    trading_enabled: bool | None,
    enable_var_name: str | None = None,
) -> None:
    """
    Macht den Betriebsmodus unuebersehbar - der eigentliche Zweck des
    W12-Fixes.

    Ein Live-Schalter, der sich still umlegen laesst, verlagert das
    Risiko nur: vorher war "live" ein unsichtbarer Code-Edit, danach
    waere es ein unsichtbarer `.env`-Eintrag. Deshalb ist die Umschaltung
    hier ausdruecklich laut - im Log UND per Telegram, beim Start jedes
    einzelnen Prozesses.

    Drei Faelle, bewusst unterschieden:

    - Testnet: eine ruhige INFO-Zeile. Der Normalfall darf nicht so
      aussehen wie der Ausnahmefall, sonst gewoehnt man sich an den Alarm.
    - Live + Trading aktiv: der volle Block auf CRITICAL. Hier bewegt
      sich echtes Geld.
    - Live + Trading deaktiviert: ebenfalls ein Block, aber mit eigenem
      Text. Das ist ein DRITTER Zustand, kein harmloser Dry-Run: es sind
      die Keys des echten Kontos, jeder Lesezugriff geht auf echte
      Bestaende, und ein spaeteres Umlegen von `*_BOT_ENABLE_TRADING`
      genuegt dann fuer echte Orders.
    """
    # Import bewusst erst hier: notifier.py importiert config.py, und
    # config.py importiert dieses Modul - ein Import auf Modulebene waere
    # ein Zirkelbezug. Zum Aufrufzeitpunkt ist alles laengst geladen.
    from .notifier import send_notification

    if use_testnet:
        bot_logger.info(
            "Modus: TESTNET - Orders gehen ans Binance-Testnet, es wird zu "
            "keinem Zeitpunkt echtes Geld bewegt (%s=true).",
            USE_TESTNET_VAR,
        )
        return

    if trading_enabled is None:
        # Der Allocator platziert nie Orders (siehe allocator_config.py).
        lines = [
            "ACHTUNG: LIVE-MODUS - ECHTES BINANCE-KONTO",
            "",
            f"{USE_TESTNET_VAR}=false - dieser Prozess liest Kurs- und",
            "Kontodaten vom ECHTEN Konto, nicht vom Testnet.",
            "Er platziert selbst keine Orders, seine Zuteilung",
            "steuert aber die Ordergroesse von DCA und Trend.",
        ]
        level = logging.WARNING
        telegram = (
            f"[LIVE-MODUS] {bot_label}: {USE_TESTNET_VAR}=false - echtes "
            "Binance-Konto. Der Allocator platziert selbst keine Orders, "
            "steuert aber die Ordergroesse von DCA und Trend."
        )
    elif trading_enabled:
        lines = [
            "ACHTUNG: LIVE-MODUS MIT ECHTEM GELD AKTIV",
            "",
            f"{USE_TESTNET_VAR}=false - Orders gehen an die ECHTE",
            "Binance-Boerse, NICHT ans Testnet.",
            f"{enable_var_name}=true - dieser Bot platziert",
            "echte Orders und bewegt damit echtes Geld.",
            "",
            "Wenn das nicht beabsichtigt ist: Prozess sofort",
            "stoppen (Notaus-Datei anlegen oder systemctl stop).",
        ]
        level = logging.CRITICAL
        telegram = (
            "[LIVE-MODUS] ACHTUNG: LIVE-MODUS MIT ECHTEM GELD AKTIV - "
            f"{bot_label} startet mit {USE_TESTNET_VAR}=false und "
            f"{enable_var_name}=true. Orders gehen an die echte Binance-"
            "Boerse. Falls nicht beabsichtigt: sofort stoppen."
        )
    else:
        lines = [
            "ACHTUNG: LIVE-KONTO, Trading aktuell deaktiviert",
            "",
            f"{USE_TESTNET_VAR}=false - die Zugangsdaten gehoeren",
            "zum ECHTEN Binance-Konto, nicht zum Testnet.",
            f"{enable_var_name}=false - es werden noch keine",
            "Orders platziert, aber alle Kontodaten sind echt.",
            "",
            f"Ein Umlegen von {enable_var_name}",
            "genuegt jetzt, damit echtes Geld bewegt wird.",
        ]
        level = logging.WARNING
        telegram = (
            f"[LIVE-MODUS] {bot_label}: {USE_TESTNET_VAR}=false (echtes "
            f"Konto), {enable_var_name}=false - noch keine echten Orders. "
            "Ein Umlegen dieser einen Variable genuegt fuer Echtgeld-Handel."
        )

    for line in _banner(lines):
        bot_logger.log(level, "%s", line)
    send_notification(telegram)


def report_config_error(bot_label: str, error: Exception) -> None:
    """
    Meldet eine Fehlkonfiguration, bevor ueberhaupt ein Logger existiert.

    `load_*()` laeuft als Allererstes in `main()` - noch vor
    `setup_logging()`, das seinen Pfad ja aus der Config bezieht. Eine
    durchgereichte Exception ergaebe deshalb einen nackten Traceback und
    Exit-Code 1, und `Restart=on-failure` in der systemd-Unit macht
    daraus eine Neustartschleife, die nie zum Erfolg fuehren kann (die
    Konfiguration aendert sich von allein nicht). Dieselbe Fehlerklasse
    wie W18, nur eine Stufe frueher.

    Deshalb: klare Meldung auf stderr (landet im journal), Telegram
    soweit moeglich, und der Aufrufer kehrt danach regulaer zurueck -
    Exit-Code 0, also keine Schleife. Gleiches Muster wie die bestehende
    Behandlung von `BotAlreadyRunning` in den `main*.py`.
    """
    print(
        f"\n{bot_label} startet NICHT - Fehler in der Konfiguration:\n\n"
        f"  {error}\n\n"
        "Bitte die .env pruefen und den Prozess danach neu starten.\n",
        file=sys.stderr,
    )

    # Best effort: der Notifier ist noch nicht initialisiert, die
    # Zugangsdaten stehen aber bereits in der Umgebung. Schlaegt das fehl,
    # bleibt es bei der stderr-Meldung - eine Fehlermeldung ueber eine
    # Fehlermeldung hilft niemandem.
    try:
        from . import notifier

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id or _looks_like_placeholder(token):
            return
        notifier._bot_token = token
        notifier._chat_id = chat_id
        notifier.send_notification(
            f"[KONFIGURATIONSFEHLER] {bot_label} startet NICHT: {error}"
        )
    except Exception:
        return

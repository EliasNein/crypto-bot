"""
Telegram-Benachrichtigungen für den DCA-Bot.

Bewusst nur eine öffentliche Funktion (send_notification) mit einer
einzigen Aufgabe: Benachrichtigungen sind ein Nice-to-have, kein
Sicherheitsmechanismus. Ein Netzwerkfehler, ein ungültiger Token oder
ein down-Telegram dürfen den Bot niemals stoppen oder einen Kaufzyklus
abbrechen - deshalb wird jeder Fehler nur geloggt statt weitergeworfen,
und ohne konfigurierte Zugangsdaten tut die Funktion einfach nichts.

`init()` muss einmal beim Bot-Start aufgerufen werden (siehe main.py),
damit `send_notification(message)` ohne Config-Parameter auskommt.

WICHTIG - Token-Hygiene beim Logging: Der Bot-Token ist Teil der
Request-URL (so funktioniert die Telegram-Bot-API). Deshalb darf aus
diesem Modul NIEMALS eine Exception-Message, ein Traceback oder die URL
selbst in eine Log-Zeile gelangen: `requests`-Fehler tragen die
vollständige URL in ihrer Message ("Max retries exceeded with url:
/bot<TOKEN>/sendMessage", "401 Client Error ... for url: https://
api.telegram.org/bot<TOKEN>/sendMessage"), und `logger.exception()`
würde genau das in `logs/*.log` schreiben. Log-Dateien werden in diesem
Projekt bei Meilensteinen ins (öffentliche) Repo archiviert (siehe
`!docs/**/*.log` in .gitignore) - ein solcher Log-Eintrag veröffentlicht
den Token. Es wird daher ausschließlich der Exception-TYP bzw. der
HTTP-Statuscode geloggt, beides ohne Geheimnis. Siehe tests/test_notifier.py.
"""

from __future__ import annotations

import logging

import requests

from .config import Config

logger = logging.getLogger("dca_bot")

_TELEGRAM_API_TIMEOUT_SECONDS = 10

_bot_token: str | None = None
_chat_id: str | None = None


def _silence_urllib3_request_logging() -> None:
    """
    Verhindert, dass die HTTP-Bibliothek die Request-Zeile (und damit den
    Token in der URL) selbst ins Log schreibt: urllib3 loggt auf
    DEBUG-Level Zeilen der Form
    `https://api.telegram.org:443 "POST /bot<TOKEN>/sendMessage HTTP/1.1"`.
    Aktuell laufen alle Bots auf INFO, das greift also nicht - aber ein
    späteres `level=logging.DEBUG` in einem setup_logging() würde den
    Token wieder ins Log holen, ohne dass es jemandem auffällt. Das Level
    wird nur angehoben, nie gesenkt.
    """
    urllib3_logger = logging.getLogger("urllib3.connectionpool")
    if urllib3_logger.getEffectiveLevel() < logging.INFO:
        urllib3_logger.setLevel(logging.INFO)


def init(config: Config) -> None:
    """Einmalig beim Start aufrufen, um die Telegram-Zugangsdaten zu setzen."""
    global _bot_token, _chat_id
    _bot_token = config.telegram_bot_token or None
    _chat_id = config.telegram_chat_id or None
    _silence_urllib3_request_logging()
    if _bot_token and _chat_id:
        logger.info("Telegram-Benachrichtigungen aktiv.")
    else:
        logger.info(
            "Telegram-Benachrichtigungen deaktiviert "
            "(TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID nicht gesetzt)."
        )


def send_notification(message: str) -> None:
    """
    Sendet `message` per Telegram Bot API an den konfigurierten Chat.

    Tut nichts, wenn Telegram nicht konfiguriert ist (init() wurde nicht
    aufgerufen oder Token/Chat-ID fehlen). Wirft niemals eine Exception -
    jeder Fehler (Netzwerk, ungültiger Token, Telegram down) wird nur
    geloggt und danach ignoriert. Geloggt wird dabei bewusst nur der
    Fehlertyp bzw. der HTTP-Statuscode, nie die Exception-Message oder
    ein Traceback - siehe Modul-Docstring (Token steckt in der URL).
    """
    if not _bot_token or not _chat_id:
        return

    url = f"https://api.telegram.org/bot{_bot_token}/sendMessage"
    try:
        response = requests.post(
            url,
            data={"chat_id": _chat_id, "text": message},
            timeout=_TELEGRAM_API_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        # NUR type(exc).__name__ - weder str(exc) noch logger.exception():
        # beide enthalten die URL samt Token (siehe Modul-Docstring).
        # Der Typ allein ("ConnectionError", "ReadTimeout", "SSLError")
        # reicht für die Fehlersuche im Log völlig aus.
        logger.error("Telegram-Versand fehlgeschlagen: %s", type(exc).__name__)
        return

    if not response.ok:
        # Bewusst kein response.raise_for_status(): dessen HTTPError-
        # Message enthält die vollständige URL mit Token. Der Statuscode
        # allein ist für die Fehlersuche sogar aussagekräftiger
        # (401 = Token ungültig, 403 = Chat nicht gestartet/blockiert,
        # 429 = Rate Limit) und enthält kein Geheimnis.
        logger.error(
            "Telegram-Versand fehlgeschlagen: HTTP %s", response.status_code
        )

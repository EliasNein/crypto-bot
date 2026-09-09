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
"""

from __future__ import annotations

import logging

import requests

from .config import Config

logger = logging.getLogger("dca_bot")

_TELEGRAM_API_TIMEOUT_SECONDS = 10

_bot_token: str | None = None
_chat_id: str | None = None


def init(config: Config) -> None:
    """Einmalig beim Start aufrufen, um die Telegram-Zugangsdaten zu setzen."""
    global _bot_token, _chat_id
    _bot_token = config.telegram_bot_token or None
    _chat_id = config.telegram_chat_id or None
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
    geloggt und danach ignoriert.
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
        response.raise_for_status()
    except Exception:
        logger.exception("Telegram-Benachrichtigung fehlgeschlagen, wird ignoriert.")

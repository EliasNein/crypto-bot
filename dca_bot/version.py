"""
Ermittelt die laufende Code-Version (Git-Commit-Hash) für das Start-Banner
der vier Einstiegspunkte.

Hintergrund: Die Bots laufen als systemd-Services auf VPS und Homeserver
(siehe trading-bot-projekt.md 6b/6e), teils über Wochen. Steht in jedem
Log-Start der Commit-Hash, lässt sich ein beobachtetes Verhalten später
eindeutig einem Codestand zuordnen - ohne das muss man aus Zeitstempeln
und Deploy-Erinnerungen raten, welche Fassung gerade lief.

Bewusst rein informativ: schlägt die Ermittlung aus irgendeinem Grund
fehl (kein Git installiert, kein Repository, Timeout, unerwarteter
Fehler), wird "unbekannt" zurückgegeben. Der Bot-Start darf daran unter
keinen Umständen scheitern - ein fehlender Versionshinweis ist folgenlos,
ein nicht startender Trading-Bot nicht.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

UNKNOWN_VERSION = "unbekannt"

# Projektwurzel (ein Verzeichnis über diesem Modul) statt des aktuellen
# Arbeitsverzeichnisses: der Aufruf soll auch dann das richtige Repository
# treffen, wenn der Prozess von woanders gestartet wurde.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_GIT_TIMEOUT_SECONDS = 5


def get_code_version() -> str:
    """
    Kurzer Git-Commit-Hash des laufenden Codestands, oder "unbekannt".

    Wirft niemals - siehe Modul-Docstring.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception:
        # Bewusst breit gefangen: FileNotFoundError (kein Git installiert),
        # TimeoutExpired, PermissionError und alles Weitere sind hier
        # gleichwertig unwichtig. Diese Funktion liefert eine reine
        # Log-Zeile - keine denkbare Ausnahme rechtfertigt es, deswegen
        # den Start eines Trading-Bots zu verhindern.
        return UNKNOWN_VERSION

    if result.returncode != 0:
        # Kein Repository, oder Git verweigert den Zugriff (z.B.
        # "dubious ownership" bei fremdem Besitzer des Verzeichnisses).
        return UNKNOWN_VERSION

    return result.stdout.strip() or UNKNOWN_VERSION

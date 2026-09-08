"""
Risikomanagement für den DCA-Bot: Notaus-Schalter, persistente
Trade-Historie und Portfolio-Stop-Loss-Prüfung.

Bewusst als eigenes Modul getrennt von strategy.py, damit die
DCA-Kauflogik selbst einfach bleibt und die Sicherheitsmechanismen an
einer Stelle nachvollziehbar sind.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger("dca_bot")


class BotHalted(Exception):
    """Wird ausgelöst, wenn der Notaus-Mechanismus ausgelöst wurde."""


class KillSwitch:
    """
    Notaus: Der Bot stoppt sofort - auch mitten in einem laufenden
    Kaufzyklus -, sobald entweder eine bestimmte Datei existiert oder die
    Umgebungsvariable DCA_BOT_HALT auf "true" gesetzt ist.

    Zwei Wege bewusst: Die Datei lässt sich auch von außen (Skript,
    Cronjob, manuell) anlegen, ohne den laufenden Prozess oder dessen
    Umgebung anzufassen; die Env-Variable ist praktisch, wenn man den Bot
    direkt im gleichen Terminal steuert.
    """

    def __init__(self, file_path: str):
        self._file_path = Path(file_path)

    def is_set(self) -> bool:
        if self._file_path.exists():
            return True
        return os.getenv("DCA_BOT_HALT", "false").lower() == "true"

    def check(self) -> None:
        """Wirft BotHalted, falls der Notaus aktiv ist."""
        if self.is_set():
            raise BotHalted(
                f"Notaus ausgelöst (Datei '{self._file_path}' vorhanden "
                "oder DCA_BOT_HALT=true gesetzt)."
            )


@dataclass
class TradeRecord:
    timestamp: str  # ISO-8601, UTC
    symbol: str
    quote_spent: float
    quantity: float
    price: float
    dry_run: bool


class TradeLedger:
    """
    Persistiert jeden Kaufversuch (auch Dry-Run) in einer JSON-Datei, damit
    Tageslimit und Stop-Loss-Berechnung einen Bot-Neustart überleben statt
    nur im Prozessspeicher zu existieren.

    Bewusst simpel gehalten (eine JSON-Liste, komplett neu geschrieben pro
    Eintrag) statt einer echten Datenbank - für das erwartete Volumen
    (wenige Käufe pro Tag) ausreichend und ohne zusätzliche Abhängigkeit.
    """

    def __init__(self, state_file: str):
        self._path = Path(state_file)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write([])

    def _read(self) -> list[dict]:
        try:
            with self._path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logger.warning(
                "Trade-Ledger '%s' fehlt oder ist beschädigt - starte mit "
                "leerer Historie.",
                self._path,
            )
            return []

    def _write(self, records: list[dict]) -> None:
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

    def record(self, trade: TradeRecord) -> None:
        records = self._read()
        records.append(asdict(trade))
        self._write(records)

    def spent_on_day(self, symbol: str, day: date) -> float:
        """Summe aller (auch simulierten) Käufe eines Symbols an einem Tag."""
        return sum(
            r["quote_spent"]
            for r in self._read()
            if r["symbol"] == symbol
            and datetime.fromisoformat(r["timestamp"]).date() == day
        )

    def position(self, symbol: str) -> tuple[float, float]:
        """
        Gesamteinsatz und Gesamtmenge aus echten (nicht simulierten) Käufen
        eines Symbols - Basis für die Stop-Loss-Berechnung. Dry-Run-Käufe
        erzeugen keine reale Position und fließen bewusst nicht ein.
        """
        total_spent = 0.0
        total_qty = 0.0
        for r in self._read():
            if r["symbol"] != symbol or r["dry_run"]:
                continue
            total_spent += r["quote_spent"]
            total_qty += r["quantity"]
        return total_spent, total_qty


class PortfolioStopLoss:
    """
    Prüft, ob der aktuelle Wert der bisher gekauften Position mehr als
    `stop_loss_pct` Prozent unter der Summe der Einkaufspreise liegt.

    Löst bewusst KEINEN Verkauf aus - nur eine deutliche Log-Warnung und
    ein Pausieren weiterer Käufe. Ob/wie automatisch verkauft wird, ist
    eine separate, spätere Entscheidung.

    Wichtiger Default: Einmal ausgelöst, bleibt die Pause bestehen, bis sie
    manuell zurückgesetzt wird (siehe `reset()` / `reset_stop_loss.py`) -
    sie hebt sich NICHT von selbst auf, nur weil der Preis sich wieder
    über die Schwelle erholt. Grund: Ein automatischer Reset würde bei
    volatilen Seitwärts-/Erholungsphasen ("Whipsaw") dazu führen, dass der
    Bot immer wieder knapp über der Schwelle neu einsteigt, kurz bevor der
    Kurs erneut fällt ("dead cat bounce") - und damit über viele kleine
    Wiedereinstiege genau den Verlust vergrößert, vor dem der Stop-Loss
    eigentlich schützen soll. Der erzwungene manuelle Reset stellt sicher,
    dass jemand die Lage bewusst bewertet, bevor der Bot wieder aktiv wird.
    Ein optionaler automatischer Reset (mit Erholungs-Schwelle + Cooldown)
    ist eine mögliche spätere Erweiterung, siehe trading-bot-projekt.md.
    """

    def __init__(self, ledger: TradeLedger, stop_loss_pct: float, state_file: str):
        self._ledger = ledger
        self._stop_loss_pct = stop_loss_pct
        self._path = Path(state_file)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def is_paused(self) -> bool:
        """Ob der Stop-Loss aktuell ausgelöst ist und auf Reset wartet."""
        return self._path.exists()

    def reset(self) -> None:
        """
        Hebt eine ausgelöste Pause manuell auf. Analog zum Notaus-Mechanismus
        genügt auch das Löschen der Status-Datei von Hand.
        """
        if self._path.exists():
            self._path.unlink()
            logger.info(
                "Portfolio-Stop-Loss-Pause manuell zurückgesetzt (%s entfernt).",
                self._path,
            )
        else:
            logger.info("Portfolio-Stop-Loss war nicht pausiert, nichts zu tun.")

    def _pause(self, symbol: str, total_spent: float, current_value: float, loss_pct: float) -> None:
        payload = {
            "symbol": symbol,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "total_spent": total_spent,
            "value_at_trigger": current_value,
            "loss_pct_at_trigger": loss_pct,
        }
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def is_triggered(self, symbol: str, current_price: float) -> bool:
        if self.is_paused():
            logger.warning(
                "Portfolio-Stop-Loss weiterhin pausiert (letzter Trigger in "
                "%s) - Kauf für %s wird übersprungen, bis manuell "
                "zurückgesetzt (siehe reset_stop_loss.py).",
                self._path,
                symbol,
            )
            return True

        if self._stop_loss_pct <= 0:
            return False

        total_spent, total_qty = self._ledger.position(symbol)
        if total_qty <= 0 or total_spent <= 0:
            return False

        current_value = total_qty * current_price
        loss_pct = (1 - current_value / total_spent) * 100

        if loss_pct >= self._stop_loss_pct:
            logger.warning(
                "PORTFOLIO-STOP-LOSS ausgelöst für %s: eingesetzt %.2f, "
                "aktueller Wert %.2f (%.1f%% Verlust, Limit %.1f%%). "
                "Bot pausiert weitere Käufe, bis manuell zurückgesetzt - "
                "es wird NICHT automatisch verkauft.",
                symbol,
                total_spent,
                current_value,
                loss_pct,
                self._stop_loss_pct,
            )
            self._pause(symbol, total_spent, current_value, loss_pct)
            return True
        return False

"""
Zustand für den Trend-Following-Bot: Trade-Ledger (eine Position
gleichzeitig) und Stop-Loss-Latch.

Komplett eigenständig von risk.py (DCA) und grid_risk.py (Grid) - eigene
Zustandsdateien, eigenes Datenmodell. KillSwitch/BotHalted werden aus
risk.py wiederverwendet (generisch, kein DCA-spezifischer Zustand) -
main_trend.py/trend_strategy.py erzeugen jeweils eine eigene
KillSwitch-Instanz mit eigenem Dateipfad/Env-Var-Namen.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .notifier import send_notification

logger = logging.getLogger("trend_bot")


@dataclass
class TrendTrade:
    id: str
    entry_price: float
    entry_time: str  # ISO-8601, UTC
    quantity: float
    quote_spent: float
    dry_run: bool
    # ID der echten, exchange-seitigen STOP_LOSS_LIMIT-Order (siehe
    # binance_client.place_stop_loss_limit_sell) - None im Dry-Run (dort
    # wird nie eine echte Order platziert, siehe trend_strategy.py).
    stop_loss_order_id: str | None = None
    # Limit-Preis der Stop-Loss-Order zum Zeitpunkt der Platzierung (siehe
    # trend_strategy.py._open_position) - None im Dry-Run. Wird beim
    # Exit über eine gefüllte Stop-Order für die Fill-Analyse (siehe
    # [STOP-FILL-ANALYSE] in _close_from_filled_stop_order) gebraucht,
    # um den tatsächlichen Füllpreis mit dem erwarteten Limit-Preis zu
    # vergleichen - separat von entry_price/stop_loss_pct gespeichert,
    # damit eine spätere Config-Änderung (TREND_STOP_LIMIT_OFFSET_PCT)
    # bereits offene Positionen nicht rückwirkend verfälscht.
    stop_limit_price: float | None = None
    # Zählt aufeinanderfolgende Zyklen, in denen der Status der
    # Stop-Loss-Order nach einem fehlgeschlagenen Cancel-Versuch unklar
    # blieb (siehe trend_strategy.py, _resolve_stop_order_before_close) -
    # ab einer konfigurierten Schwelle löst das eine explizite Warnung
    # aus. Wird bei jedem eindeutigen Ergebnis (sicher verkaufbar oder
    # bereits geschlossen) wieder auf 0 zurückgesetzt.
    uncertain_cycles: int = 0
    # Zaehlt aufeinanderfolgende Zyklen, in denen diese offene Position
    # KEINE exchange-seitige Stop-Loss-Order hatte und auch keine neue
    # platziert werden konnte (siehe trend_strategy.py,
    # _ensure_stop_loss_protection) - ab einer Schwelle loest das eine
    # explizite Warnung aus. Ohne diesen Zaehler koennte eine Position
    # unbegrenzt lange ungeschuetzt bleiben, ohne dass es jemals
    # eskaliert. Wird bei erfolgreicher Absicherung auf 0 zurueckgesetzt.
    unprotected_cycles: int = 0
    status: str = "open"  # "open" | "closed"
    exit_price: float | None = None
    exit_time: str | None = None
    exit_reason: str | None = None  # "signal" | "stop_loss"
    realized_pnl: float | None = None

    @staticmethod
    def new(entry_price: float, quantity: float, quote_spent: float, dry_run: bool) -> "TrendTrade":
        return TrendTrade(
            id=str(uuid.uuid4()),
            entry_price=entry_price,
            entry_time=datetime.now(timezone.utc).isoformat(),
            quantity=quantity,
            quote_spent=quote_spent,
            dry_run=dry_run,
        )


class TrendLedger:
    """
    Persistiert Trades (höchstens eine offene Position gleichzeitig, plus
    geschlossene Historie) in einer JSON-Datei - anders als Grid gibt es
    hier nur einen "Slot", da die Strategie long-only ist und immer nur
    einer Richtung folgt statt mehrerer paralleler Positionen.
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
                "Trend-Ledger '%s' fehlt oder ist beschädigt - starte mit leerer Historie.",
                self._path,
            )
            return []

    def _write(self, records: list[dict]) -> None:
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

    def open_position(self) -> dict | None:
        for r in self._read():
            if r["status"] == "open":
                return r
        return None

    def record_entry(self, trade: TrendTrade) -> None:
        records = self._read()
        records.append(asdict(trade))
        self._write(records)

    def set_uncertain_cycles(self, trade_id: str, count: int) -> None:
        """
        Persistiert den uncertain_cycles-Zähler einer offenen Position
        (siehe TrendTrade) - eigene Methode statt record_exit/record_entry
        mitzunutzen, da hier weder ein neuer Trade noch ein Exit
        entsteht, nur ein Zwischenstand für die Warnschwelle.
        """
        records = self._read()
        for r in records:
            if r["id"] == trade_id:
                r["uncertain_cycles"] = count
                break
        self._write(records)

    def set_unprotected_cycles(self, trade_id: str, count: int) -> None:
        """
        Persistiert den unprotected_cycles-Zähler einer offenen Position
        (siehe TrendTrade) - eigene Methode aus demselben Grund wie
        set_uncertain_cycles: hier entsteht weder ein neuer Trade noch
        ein Exit, nur ein Zwischenstand für die Warnschwelle.
        """
        records = self._read()
        for r in records:
            if r["id"] == trade_id:
                r["unprotected_cycles"] = count
                break
        self._write(records)

    def set_stop_loss_order(
        self, trade_id: str, order_id: str | None, limit_price: float | None
    ) -> None:
        """
        Aktualisiert die einer offenen Position zugeordnete, exchange-
        seitige Stop-Loss-Order. Gebraucht, wenn die ursprüngliche Order
        bereits storniert wurde, der anschließende Verkauf aber
        fehlschlug und die weiterhin offene Position durch eine NEUE
        Stop-Order wieder abgesichert werden musste (siehe
        trend_strategy.py, _handle_failed_real_sell).

        `order_id=None`/`limit_price=None` löscht die Zuordnung - damit im
        Ledger keine längst stornierte Order-ID stehen bleibt, falls auch
        die Neuplatzierung fehlschlägt.

        Eigene Methode statt record_entry/record_exit mitzunutzen, aus
        demselben Grund wie bei set_uncertain_cycles: hier entsteht weder
        ein neuer Trade noch ein Exit.
        """
        records = self._read()
        for r in records:
            if r["id"] == trade_id:
                r["stop_loss_order_id"] = order_id
                r["stop_limit_price"] = limit_price
                break
        self._write(records)

    def record_exit(
        self, trade_id: str, exit_price: float, exit_time: str, exit_reason: str, realized_pnl: float
    ) -> None:
        records = self._read()
        for r in records:
            if r["id"] == trade_id:
                r["status"] = "closed"
                r["exit_price"] = exit_price
                r["exit_time"] = exit_time
                r["exit_reason"] = exit_reason
                r["realized_pnl"] = realized_pnl
                break
        self._write(records)


class TrendStopLoss:
    """
    Latched Pause nach einem Stop-Loss-Exit (nicht Signal-Umkehr) - analog
    zu PortfolioStopLoss (DCA) / GridStopLoss (Grid): kein automatischer
    Reset, wenn sich der Kurs erholt. Blockiert nur neue Einstiege; die
    ausgelöste Position wurde zum Auslösezeitpunkt bereits regulär
    geschlossen (siehe trend_strategy.py).

    Gleiche Begründung wie bei den anderen beiden Stop-Loss-Varianten: ein
    automatischer Reset würde bei einer kurzen Erholung ("Whipsaw") zu
    einem erneuten verfrühten Einstieg führen, kurz bevor der Trend
    tatsächlich weiter fällt. Der erzwungene manuelle Reset stellt sicher,
    dass jemand die Lage bewusst bewertet, bevor der Bot wieder eine neue
    Position eingeht. Der Backtest (trend_backtest.py) zeigt aber auch
    deutlich den Preis dafür: ohne periodischen manuellen Reset verpasst
    die Strategie ggf. einen Großteil einer nachfolgenden Erholung.
    """

    def __init__(self, state_file: str):
        self._path = Path(state_file)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def is_paused(self) -> bool:
        return self._path.exists()

    def reset(self) -> None:
        """
        Hebt eine ausgelöste Pause manuell auf. Analog zu den anderen
        Bots genügt auch das Löschen der Status-Datei von Hand.
        """
        if self._path.exists():
            self._path.unlink()
            logger.info("Trend-Stop-Loss-Pause manuell zurückgesetzt (%s entfernt).", self._path)
        else:
            logger.info("Trend-Stop-Loss war nicht pausiert, nichts zu tun.")

    def pause(self, symbol: str, entry_price: float, exit_price: float, loss_pct: float) -> None:
        payload = {
            "symbol": symbol,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "loss_pct": loss_pct,
        }
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        logger.warning(
            "TREND-STOP-LOSS ausgelöst für %s: Einstieg %.2f, Ausstieg %.2f "
            "(%.1f%% Verlust). Neue Einstiege pausiert, bis manuell zurückgesetzt.",
            symbol,
            entry_price,
            exit_price,
            loss_pct,
        )
        send_notification(
            f"[TREND-STOP-LOSS] {symbol}: Einstieg {entry_price:.2f} -> Ausstieg "
            f"{exit_price:.2f} ({loss_pct:.1f}% Verlust). Neue Einstiege pausiert "
            "bis manueller Reset (python -m dca_bot.reset_trend_stop_loss)."
        )

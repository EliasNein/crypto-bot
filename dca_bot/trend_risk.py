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
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .risk import LedgerUnreadable
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
    # Selbstvergebene `newClientOrderId` der EINSTIEGS-Order (siehe
    # pending_orders.py) - None im Dry-Run und bei Trades aus der Zeit
    # vor dem K2-Fix. Erlaubt beim Nachtragen aus der
    # Pending-Orders-Datei die Frage "kenne ich diese Order schon?";
    # die lokale `id` oben taugt dafür nicht, die hat die Börse nie
    # gesehen. Bewusst nur für den Einstieg: Exit-Order und
    # Stop-Loss-Order hängen über die Trade-ID am selben Eintrag und
    # sind über `status` bzw. `stop_loss_order_id` schon eindeutig.
    client_order_id: str | None = None
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
    def new(
        entry_price: float,
        quantity: float,
        quote_spent: float,
        dry_run: bool,
        client_order_id: str | None = None,
    ) -> "TrendTrade":
        return TrendTrade(
            id=str(uuid.uuid4()),
            entry_price=entry_price,
            entry_time=datetime.now(timezone.utc).isoformat(),
            quantity=quantity,
            quote_spent=quote_spent,
            dry_run=dry_run,
            client_order_id=client_order_id,
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
        """
        Liest das Ledger.

        Eine FEHLENDE Datei ist der regulaere Fall "frisches Deployment,
        allererster Start" und ergibt eine leere Historie - sonst liesse
        sich kein Bot mehr mit leerem data/-Ordner in Betrieb nehmen
        (genau so aufgesetzt beim Homeserver-Deployment).

        Eine VORHANDENE, aber kaputte Datei ist etwas voellig anderes und
        wirft seit dem W5-Fix `LedgerUnreadable`: sie als leere Historie
        zu lesen wuerde Tageslimit und Stop-Loss-Kostenbasis
        stillschweigend auf Null setzen, und der Bot kaufte weiter,
        obwohl faktisch Kapital gebunden ist. Siehe LedgerUnreadable in
        risk.py.

        Reihenfolge der except-Zweige ist wichtig: FileNotFoundError ist
        eine Unterklasse von OSError - wuerde der generische Zweig zuerst
        greifen, schluckte er genau den Fall, der erlaubt bleiben soll.
        """
        if not self._path.exists():
            logger.info(
                "%s '%s' existiert nicht - frischer Start mit leerer Historie.",
                "Trend-Ledger",
                self._path,
            )
            return []

        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            # Zwischen exists() und open() verschwunden - ein Rennen, kein
            # Datenverlust-Signal.
            return []
        except json.JSONDecodeError as exc:
            logger.error(
                "%s '%s' ist beschaedigt und kann NICHT als leere Historie "
                "behandelt werden: Tageslimit und Stop-Loss-Basis wuerden "
                "stillschweigend auf Null zurueckfallen. Bitte die Datei "
                "pruefen/wiederherstellen (%s).",
                "Trend-Ledger",
                self._path,
                exc,
            )
            raise LedgerUnreadable(
                f"{"Trend-Ledger"} '{self._path}' enthaelt kein gueltiges JSON: {exc}"
            ) from exc
        except OSError as exc:
            logger.error(
                "%s '%s' ist vorhanden, aber nicht lesbar (%s) - es wird "
                "bewusst NICHT mit leerer Historie weitergemacht.",
                "Trend-Ledger",
                self._path,
                exc,
            )
            raise LedgerUnreadable(
                f"{"Trend-Ledger"} '{self._path}' ist nicht lesbar: {exc}"
            ) from exc

        if not isinstance(data, list):
            logger.error(
                "%s '%s' hat ein unerwartetes Format (%s statt Liste) - "
                "bewusst kein Weitermachen mit leerer Historie.",
                "Trend-Ledger",
                self._path,
                type(data).__name__,
            )
            raise LedgerUnreadable(
                f"{"Trend-Ledger"} '{self._path}' enthaelt keine JSON-Liste."
            )
        return data

    def verify_readable(self) -> None:
        """
        Liest das Ledger einmal, um Beschaedigungen sofort beim Bot-Start
        aufzudecken statt erst im ersten Zyklus (siehe die main*.py).
        Wirft `LedgerUnreadable`.
        """
        self._read()

    def _write(self, records: list[dict]) -> None:
        """
        Schreibt das Ledger ATOMAR: temporäre Datei, fsync, os.replace.

        Vorher wurde die Zieldatei direkt geöffnet (`open("w")`), also
        zuerst gekürzt und dann neu befüllt - ein Absturz oder
        Stromausfall dazwischen hinterließ eine halb geschriebene,
        unparsbare Datei. Das ist kein theoretischer Fall: bei jedem
        Eintrag wird die komplette Liste neu geschrieben.

        Seit dem W5-Fix führt genau so eine kaputte Datei zum harten
        Abbruch (siehe LedgerUnreadable) - deshalb gehört diese
        Absicherung zwingend dazu. Was nach einem Absturz übrig bleibt,
        ist jetzt entweder die vollständige alte oder die vollständige
        neue Fassung, nie etwas dazwischen. Gleiches Muster wie in
        pending_orders.PendingOrderStore.
        """
        tmp_path = self._path.with_name(self._path.name + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self._path)

    def open_position(self) -> dict | None:
        for r in self._read():
            if r["status"] == "open":
                return r
        return None

    def trade_by_id(self, trade_id: str) -> dict | None:
        """Ein Trade (offen oder geschlossen) über seine lokale ID."""
        for r in self._read():
            if r["id"] == trade_id:
                return r
        return None

    def has_client_order_id(self, client_order_id: str) -> bool:
        """
        Ob zu dieser Börsen-Einstiegs-Order bereits ein Trade existiert -
        Basis der Idempotenz beim Nachtragen aus der Pending-Orders-Datei
        (siehe TrendTrade.client_order_id).
        """
        return any(r.get("client_order_id") == client_order_id for r in self._read())

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
        # Bewusst KEIN atomares Schreiben (anders als die Ledger, siehe
        # dort): Fuer diesen Latch zaehlt allein, DASS die Datei
        # existiert - `is_paused()` prueft nur `self._path.exists()`.
        # Der Inhalt ist rein informativ fuer die spaetere Auswertung.
        # Eine halb geschriebene Datei haelt die Pause damit genauso
        # zuverlaessig wie eine vollstaendige. Hier steht also keine
        # vergessene Stelle, sondern eine Abwaegung (Stufe 1 der
        # Verbesserungsvorschlaege, Punkt 2).
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

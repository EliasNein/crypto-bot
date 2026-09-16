"""
Zustand und Risikomanagement für den Grid-Trading-Bot: Positions-Ledger
und Trendbruch-Stop-Loss.

Komplett eigenständig von risk.py (DCA-Bot) - eigene Zustandsdateien,
eigenes Datenmodell. Notaus (KillSwitch) und die BotHalted-Exception
werden aus risk.py wiederverwendet, da sie generisch (nur ein Dateipfad
+ Env-Var-Name) und ohne DCA-spezifischen Zustand sind - siehe main_grid.py
und grid_strategy.py, die jeweils eine eigene KillSwitch-Instanz mit
eigenem Dateipfad/Env-Var-Namen erzeugen.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .grid_signals import is_trend_break_stop_loss_hit
from .risk import LedgerUnreadable
from .notifier import send_notification

logger = logging.getLogger("grid_bot")


@dataclass
class GridPosition:
    id: str
    level_index: int          # welche Grid-Stufe wurde gekauft
    buy_price: float
    target_sell_price: float  # Preis der nächsthöheren Grid-Stufe
    quantity: float
    quote_spent: float
    bought_at: str             # ISO-8601, UTC
    dry_run: bool
    # Selbstvergebene `newClientOrderId` der Kauf-Order (siehe
    # pending_orders.py) - None im Dry-Run und bei Positionen aus der
    # Zeit vor dem K2-Fix. Erlaubt beim Nachtragen aus der
    # Pending-Orders-Datei die Frage "kenne ich diese Order schon?";
    # die lokale `id` oben taugt dafür nicht, die hat die Börse nie
    # gesehen.
    client_order_id: str | None = None
    status: str = "open"       # "open" | "closed"
    sell_price: float | None = None
    sold_at: str | None = None
    realized_pnl: float | None = None

    @staticmethod
    def new(
        level_index: int,
        buy_price: float,
        target_sell_price: float,
        quantity: float,
        quote_spent: float,
        dry_run: bool,
        client_order_id: str | None = None,
    ) -> "GridPosition":
        return GridPosition(
            id=str(uuid.uuid4()),
            level_index=level_index,
            buy_price=buy_price,
            target_sell_price=target_sell_price,
            quantity=quantity,
            quote_spent=quote_spent,
            bought_at=datetime.now(timezone.utc).isoformat(),
            dry_run=dry_run,
            client_order_id=client_order_id,
        )


class GridLedger:
    """
    Persistiert jede Grid-Position (offen und geschlossen) in einer
    JSON-Datei - anders als das DCA-Ledger (das nur akkumulierte Käufe
    kennt) muss hier jede Position individuell nachverfolgbar sein: eine
    offene Position gehört zu genau einer Kaufstufe und wird beim Verkauf
    als "closed" markiert, nicht gelöscht (bleibt als Historie erhalten).
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
                "Grid-Ledger",
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
                "Grid-Ledger",
                self._path,
                exc,
            )
            raise LedgerUnreadable(
                f"{"Grid-Ledger"} '{self._path}' enthaelt kein gueltiges JSON: {exc}"
            ) from exc
        except OSError as exc:
            logger.error(
                "%s '%s' ist vorhanden, aber nicht lesbar (%s) - es wird "
                "bewusst NICHT mit leerer Historie weitergemacht.",
                "Grid-Ledger",
                self._path,
                exc,
            )
            raise LedgerUnreadable(
                f"{"Grid-Ledger"} '{self._path}' ist nicht lesbar: {exc}"
            ) from exc

        if not isinstance(data, list):
            logger.error(
                "%s '%s' hat ein unerwartetes Format (%s statt Liste) - "
                "bewusst kein Weitermachen mit leerer Historie.",
                "Grid-Ledger",
                self._path,
                type(data).__name__,
            )
            raise LedgerUnreadable(
                f"{"Grid-Ledger"} '{self._path}' enthaelt keine JSON-Liste."
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

    def open_positions(self) -> list[dict]:
        return [r for r in self._read() if r["status"] == "open"]

    def open_position_for_level(self, level_index: int) -> dict | None:
        for r in self._read():
            if r["level_index"] == level_index and r["status"] == "open":
                return r
        return None

    def position_by_id(self, position_id: str) -> dict | None:
        """Eine Position (offen oder geschlossen) über ihre lokale ID."""
        for r in self._read():
            if r["id"] == position_id:
                return r
        return None

    def has_client_order_id(self, client_order_id: str) -> bool:
        """
        Ob zu dieser Börsen-Kauf-Order bereits eine Position existiert -
        Basis der Idempotenz beim Nachtragen aus der Pending-Orders-Datei
        (siehe GridPosition.client_order_id).
        """
        return any(r.get("client_order_id") == client_order_id for r in self._read())

    def record_buy(self, position: GridPosition) -> None:
        records = self._read()
        records.append(asdict(position))
        self._write(records)

    def record_sell(
        self, position_id: str, sell_price: float, sold_at: str, realized_pnl: float
    ) -> None:
        records = self._read()
        for r in records:
            if r["id"] == position_id:
                r["status"] = "closed"
                r["sell_price"] = sell_price
                r["sold_at"] = sold_at
                r["realized_pnl"] = realized_pnl
                break
        self._write(records)


class GridStopLoss:
    """
    Trendbruch-Stop-Loss: Löst aus, wenn der Marktpreis deutlich unter die
    Grid-Untergrenze fällt - unabhängig davon, ob/wie viele Positionen
    gerade offen sind. Anders als der DCA-Stop-Loss (der auf Kostenbasis
    der eigenen Käufe prüft) geht es hier rein um den Marktpreis relativ
    zur konfigurierten Grid-Untergrenze:

        Schwelle = lower_limit * (1 - stop_loss_pct / 100)
        Auslösung, wenn: aktueller_preis < Schwelle

    Blockiert nur neue Käufe. Bereits offene Positionen können weiterhin
    normal verkauft werden, wenn ihr Sell-Target erreicht wird (siehe
    grid_strategy.py) - eine bewusste Entscheidung, weil Verkäufe Risiko
    und Kapitalbindung reduzieren statt sie zu erhöhen.

    Wie bei PortfolioStopLoss (siehe risk.py) latched: Einmal ausgelöst,
    bleibt die Pause bestehen, bis sie manuell zurückgesetzt wird (siehe
    reset_grid_stop_loss.py) - kein automatischer Reset, wenn der Preis
    sich wieder erholt. Gleicher Grund wie dort: ein automatischer Reset
    würde bei volatilen Erholungsphasen ("Whipsaw") zu wiederholtem
    Neu-Einstieg kurz vor erneutem Fall führen. Der erzwungene manuelle
    Reset stellt sicher, dass jemand die Lage bewusst bewertet, bevor der
    Bot wieder neue Positionen eingeht.
    """

    def __init__(self, lower_limit: float, stop_loss_pct: float, state_file: str):
        self._lower_limit = lower_limit
        self._stop_loss_pct = stop_loss_pct
        self._path = Path(state_file)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def is_paused(self) -> bool:
        """Ob der Trendbruch-Stop-Loss aktuell ausgelöst ist und auf Reset wartet."""
        return self._path.exists()

    def reset(self) -> None:
        """
        Hebt eine ausgelöste Pause manuell auf. Analog zum Notaus-Mechanismus
        genügt auch das Löschen der Status-Datei von Hand.
        """
        if self._path.exists():
            self._path.unlink()
            logger.info(
                "Grid-Trendbruch-Stop-Loss-Pause manuell zurückgesetzt (%s entfernt).",
                self._path,
            )
        else:
            logger.info("Grid-Stop-Loss war nicht pausiert, nichts zu tun.")

    def _pause(self, symbol: str, current_price: float, threshold: float) -> None:
        payload = {
            "symbol": symbol,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "lower_limit": self._lower_limit,
            "threshold": threshold,
            "price_at_trigger": current_price,
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

    def is_triggered(self, symbol: str, current_price: float) -> bool:
        if self.is_paused():
            logger.warning(
                "Grid-Trendbruch-Stop-Loss weiterhin pausiert (letzter "
                "Trigger in %s) - neue Käufe für %s werden übersprungen, "
                "bis manuell zurückgesetzt (siehe reset_grid_stop_loss.py).",
                self._path,
                symbol,
            )
            return True

        if not is_trend_break_stop_loss_hit(self._lower_limit, self._stop_loss_pct, current_price):
            return False

        threshold = self._lower_limit * (1 - self._stop_loss_pct / 100)
        logger.warning(
            "GRID-TRENDBRUCH-STOP-LOSS ausgelöst für %s: Preis %.2f "
            "unter Schwelle %.2f (Grid-Untergrenze %.2f, Puffer %.1f%%). "
            "Neue Käufe pausiert, bis manuell zurückgesetzt - offene "
            "Positionen werden weiterhin normal verkauft.",
            symbol,
            current_price,
            threshold,
            self._lower_limit,
            self._stop_loss_pct,
        )
        self._pause(symbol, current_price, threshold)
        send_notification(
            f"[GRID-STOP-LOSS] {symbol}: Preis {current_price:.2f} unter "
            f"Trendbruch-Schwelle {threshold:.2f} (Grid-Untergrenze "
            f"{self._lower_limit:.2f}, Puffer {self._stop_loss_pct:.1f}%). "
            "Neue Käufe pausiert bis manueller Reset "
            "(python -m dca_bot.reset_grid_stop_loss)."
        )
        return True

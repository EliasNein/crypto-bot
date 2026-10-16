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
from .risk import LedgerUnreadable, require_plausible_entry
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
    # Selbstvergebene `newClientOrderId` der VERKAUFS-Order (Systemcheck vom
    # 27.09.2026, K-B). Macht das Nachtragen eines Verkaufs idempotent und
    # unterscheidbar: Ist die Position schon geschlossen, zeigt der
    # Vergleich mit dieser ID, ob die Order aus der Pending-Datei DIESER
    # Verkauf war (nichts zu tun) oder ein ZWEITER (Doppelverkauf). Ohne
    # sie waren beide Faelle gleich - und ein Doppelverkauf ging als
    # "bereits verbucht" durch. None im Dry-Run und bei Altbestand.
    sell_client_order_id: str | None = None
    # Das Handelspaar dieser Position (Symbolbindung vom 28.09.2026). Bis
    # dahin trug kein Grid-Eintrag ein Symbol - das Paar war eine
    # Eigenschaft der Konfiguration, und ein Bot mit geaendertem
    # GRID_SYMBOL haette alte Positionen still als Positionen des neuen
    # Paars weitergefuehrt: Verkaufsziel in USDT gegen einen EUR-Kurs,
    # Verkauf gegen EUR, PnL aus EUR-Erloes minus USDT-Einsatz. Fehlt das
    # Feld (Altbestand), gilt symbol_guard.LEGACY_SYMBOL.
    symbol: str | None = None
    # Staub beim Kauf (16.10.2026, T2): Hat die Boerse eine Kauf-Order nur
    # teilweise ausgefuehrt und liegt die gekaufte Menge unter dem
    # Mindestvolumen, laesst sie sich nie wieder verkaufen. Die Position
    # wird dann sofort geschlossen - `close_reason` "dust", `dust_qty` die
    # Menge, die als Staub auf dem Konto bleibt, `realized_pnl` =
    # -quote_spent (vorsichtig bewertet wie K-A beim Trend-Bot: der Staub
    # hat einen Restwert unter dem Mindestvolumen). Im Normalfall 0.0 bzw.
    # None. Teilverkaeufe nutzen diese Felder erst ab Runde 2.
    dust_qty: float = 0.0
    close_reason: str | None = None

    @staticmethod
    def new(
        level_index: int,
        buy_price: float,
        target_sell_price: float,
        quantity: float,
        quote_spent: float,
        dry_run: bool,
        client_order_id: str | None = None,
        symbol: str | None = None,
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
            symbol=symbol,
        )


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_unfilled_position(record: dict) -> bool:
    """
    Offene, echte Position ohne Bestand: Menge UND Einsatz sind als Zahl
    genau 0 (16.10.2026). Text wie "0" oder ein bool zaehlt bewusst nicht -
    so ein Eintrag ist ein anderer Fehler und wird nicht angefasst.
    """
    quantity = record.get("quantity")
    quote_spent = record.get("quote_spent")
    return (
        record.get("status") == "open"
        and record.get("dry_run") is False
        and _is_number(quantity)
        and quantity == 0
        and _is_number(quote_spent)
        and quote_spent == 0
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

    def records(self) -> list[dict]:
        """Alle Eintraege, offen und geschlossen (fuer die Symbolpruefung beim Start)."""
        return self._read()

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
        # Nur der NEUE Eintrag wird geprueft (A3, 16.10.2026) - die alten
        # Eintraege ohne Bestand duerfen das Schreiben nicht blockieren,
        # sonst stuende der Bot bis zur Bereinigung still.
        require_plausible_entry(
            "Grid-Ledger", position.dry_run, position.quantity, position.quote_spent,
            position.client_order_id,
        )
        records = self._read()
        records.append(asdict(position))
        self._write(records)

    def remove_unfilled_positions(self, position_ids: set[str]) -> int:
        """
        Entfernt Eintraege OHNE Bestand - und nur solche (Werkzeug
        remove_unfilled_grid_positions.py, 16.10.2026).

        Ohne Bestand heisst: offen, echt (`dry_run` False), Menge und
        Einsatz genau 0 - eine Kauf-Order, die die Boerse ohne Ausfuehrung
        beendet hat und die vor dem Fix A1 trotzdem verbucht wurde. Zeigt
        eine der IDs auf etwas anderes oder auf gar nichts, wird NICHTS
        geschrieben: Diese Methode ist die letzte Sperre davor, eine
        Position mit Bestand aus dem Ledger zu loeschen.

        Atomar ueber denselben _write() wie jeder andere Schreibvorgang.
        Gibt die Zahl der entfernten Eintraege zurueck.
        """
        records = self._read()
        by_id = {r.get("id"): r for r in records}
        for position_id in position_ids:
            record = by_id.get(position_id)
            if record is None or not is_unfilled_position(record):
                raise ValueError(
                    f"Eintrag {position_id!r} ist keine offene, echte Position "
                    "ohne Bestand - es wird nichts entfernt."
                )
        kept = [r for r in records if r.get("id") not in position_ids]
        self._write(kept)
        return len(records) - len(kept)

    def record_sell(
        self,
        position_id: str,
        sell_price: float,
        sold_at: str,
        realized_pnl: float,
        sell_client_order_id: str | None = None,
    ) -> None:
        records = self._read()
        for r in records:
            if r["id"] == position_id:
                r["status"] = "closed"
                r["sell_price"] = sell_price
                r["sold_at"] = sold_at
                r["realized_pnl"] = realized_pnl
                r["sell_client_order_id"] = sell_client_order_id
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

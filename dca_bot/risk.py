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

from dotenv import dotenv_values

from .config_guard import GLOBAL_KILL_SWITCH_NAME
from .notifier import send_notification

logger = logging.getLogger("dca_bot")

# Projektwurzel (ein Verzeichnis über diesem Modul) - Fundort der `.env`
# für die Notaus-Prüfung, siehe KillSwitch. Gleiche Herleitung wie in
# version.py: der Pfad soll auch stimmen, wenn der Prozess von woanders
# gestartet wurde.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class BotHalted(Exception):
    """Wird ausgelöst, wenn der Notaus-Mechanismus ausgelöst wurde."""


class LedgerUnreadable(Exception):
    """
    Eine vorhandene Ledger-Datei ist unlesbar oder beschädigt
    (Sicherheitsreview-Punkt W5).

    Bewusst eine Exception statt "leere Historie": Tageslimit und
    Stop-Loss-Kostenbasis werden bei jedem Zyklus neu aus dem Ledger
    berechnet. Eine kaputte Datei stillschweigend als "noch nichts
    gekauft" zu lesen, setzt beide auf Null zurück - der Bot würde
    munter weiterkaufen, obwohl faktisch längst Kapital gebunden ist,
    und die einzige Spur wäre eine Warnzeile im Log. Ein Bot, der nicht
    startet, ist deutlich besser als einer, der mit falschen Limits
    weiterläuft.

    Gilt ausdrücklich NUR für vorhandene Dateien mit kaputtem Inhalt.
    Eine fehlende Datei ist der reguläre Fall "frisches Deployment,
    allererster Start" (siehe TradeLedger._read) und bleibt unverändert
    erlaubt - sonst ließe sich kein Bot mehr mit leerem data/-Ordner in
    Betrieb nehmen.

    Wird hier neben BotHalted definiert, weil beide dieselbe Rolle
    haben: ein generischer, botübergreifender Grund, sicher anzuhalten.
    Grid- und Trend-Ledger verwenden sie mit (wie schon KillSwitch).
    """


def utc_today() -> date:
    """
    Heutiges Datum in UTC.

    Ersetzt `date.today()` (Sicherheitsreview-Punkt W3): die
    Ledger-Zeitstempel werden in UTC geschrieben und beim Auswerten mit
    `datetime.fromisoformat(...).date()` wieder als UTC-Datum gelesen.
    Wurde das Tagesfenster dagegen mit der LOKALEN Serverzeit bestimmt,
    verschob sich die Tageslimit-Grenze je nach Zeitzone um Stunden
    gegenüber der tatsächlichen Kalendertag-Grenze der Daten - mit dem
    Ergebnis, dass rund um den Zeitzonen-Versatz entweder zu viel oder
    zu wenig auf das Limit angerechnet wurde.
    """
    return datetime.now(timezone.utc).date()


class KillSwitch:
    """
    Notaus: Der Bot stoppt sofort - auch mitten in einem laufenden
    Kaufzyklus -, sobald einer von fünf Wegen ausgelöst wird.

    Botspezifisch (stoppt nur diesen einen Bot):

    1. Die Notaus-Datei existiert (z.B. `STOP`).
    2. Die Umgebungsvariable des Prozesses (z.B. `DCA_BOT_HALT`) steht
       auf "true" - gesetzt beim Start, etwa über die systemd-Unit.
    3. Die aktuelle `.env` im Projektverzeichnis setzt sie auf "true".

    Global (stoppt ALLE vier Bots gleichzeitig):

    4. Die Datei `STOP_ALL` liegt im Projektverzeichnis.
    5. `STOP_ALL=true` steht in der Prozessumgebung oder in der
       aktuellen `.env`.

    Die Wege 4 und 5 sind Stufe 1 der Verbesserungsvorschläge (Punkt 10).
    Vorher brauchte es vier Dateien oder vier Variablen, um alles
    anzuhalten - und im Ernstfall ist "habe ich wirklich alle vier
    erwischt?" genau die Frage, die man sich nicht stellen will. Sie
    ersetzen die botspezifischen Schalter NICHT: Einen einzelnen Bot
    anzuhalten muss weiterhin möglich sein, ohne die anderen drei
    mitzunehmen.

    Weg 3 war der Sicherheitsreview-Punkt W1: `os.getenv()` liest die
    Umgebung, die beim Prozessstart einmalig aus der `.env` befüllt
    wurde. `DCA_BOT_HALT=true` nachträglich in die Datei zu schreiben
    hatte deshalb KEINE Wirkung, bis der Bot neu startete - während
    README und `.env.example` es als gleichwertige Alternative zur
    STOP-Datei beschrieben. Ein Notaus, der nicht auslöst, ist die
    schlechteste Sorte Sicherheitsmechanismus: man verlässt sich darauf.

    Alle Wege sind mit ODER verknüpft, und das ist bewusst
    asymmetrisch: Auslösen soll leicht sein, versehentliches Aufheben
    schwer. Zum Wiederanlaufen müssen alle Quellen sauber sein - beim
    Neustart liest `load_dotenv()` die Datei ohnehin frisch ein.

    Gelesen wird mit `dotenv_values()`, NICHT mit
    `load_dotenv(override=True)`: Letzteres würde `os.environ`
    überschreiben und damit auch Werte, die die systemd-Unit bewusst
    gesetzt hat (z.B. ein dort erzwungenes `*_BOT_ENABLE_TRADING=false`).
    Ein Notaus-Check darf keine anderen Einstellungen umbiegen.
    """

    def __init__(
        self,
        file_path: str,
        env_var_name: str = "DCA_BOT_HALT",
        env_file: str | Path | None = None,
        global_file: str | Path | None = None,
    ):
        self._file_path = Path(file_path)
        self._env_var_name = env_var_name
        # `global_file` existiert ausschliesslich fuer Tests - im Betrieb
        # ist der Pfad bewusst fest (siehe GLOBAL_KILL_SWITCH_NAME).
        self._global_file = (
            Path(global_file) if global_file else _PROJECT_ROOT / GLOBAL_KILL_SWITCH_NAME
        )
        # Projektwurzel wie in version.py, damit der Pfad auch stimmt,
        # wenn der Prozess von woanders gestartet wurde.
        self._env_file = Path(env_file) if env_file else _PROJECT_ROOT / ".env"
        # mtime+Größe der zuletzt geparsten Fassung. Neu geparst wird nur
        # bei Änderung: der Check läuft im Notaus-Polling alle paar
        # Sekunden, ein `os.stat` kostet dabei rund 15 µs gegenüber
        # ~570 µs für einen Vollparse der .env. Selbst der Vollparse wäre
        # bei 5 Sekunden Takt vernachlässigbar (~0,01 % eines Kerns) -
        # der Wächter ist billige Absicherung dagegen, dass jemand das
        # Polling-Intervall später deutlich verkürzt.
        self._env_file_signature: tuple[int, int] | None = None
        self._env_file_values: dict[str, str | None] = {}

    def _env_file_halts(self, var_name: str) -> bool:
        """
        Ob die aktuelle `.env` die genannte Notaus-Variable setzt -
        aufgerufen für die botspezifische Variable UND für `STOP_ALL`.

        Eine fehlende, unlesbare oder kaputte Datei bedeutet "kein
        Notaus" - dieser Weg darf nie selbst zur Fehlerquelle werden.
        Die anderen Wege bleiben davon unberührt.
        """
        try:
            stat = self._env_file.stat()
        except OSError:
            return False

        signature = (stat.st_mtime_ns, stat.st_size)
        if signature != self._env_file_signature:
            try:
                self._env_file_values = dict(dotenv_values(self._env_file))
            except Exception:
                logger.warning(
                    "Notaus-Prüfung: '%s' konnte nicht gelesen werden - der "
                    "Datei-Weg des Notaus (%s / %s) entfällt in diesem "
                    "Durchlauf. Notaus-Dateien und Prozess-Umgebung wirken "
                    "weiterhin.",
                    self._env_file,
                    self._env_var_name,
                    GLOBAL_KILL_SWITCH_NAME,
                )
                self._env_file_values = {}
            self._env_file_signature = signature

        raw = self._env_file_values.get(var_name)
        return str(raw or "").strip().lower() == "true"

    def _halt_variable_set(self, var_name: str) -> bool:
        """
        Prozessumgebung ODER aktuelle `.env` - siehe W1.

        Der `.strip()` auf dem Umgebungswert kam beim STOP_ALL-Fix dazu:
        Der `.env`-Weg hat den Wert schon immer getrimmt (siehe
        `_env_file_halts`), der Prozess-Weg nicht. Ein `DCA_BOT_HALT=" true "`
        in einer systemd-Unit hiess damit still "kein Notaus" - dieselbe
        unangenehme Fehlerrichtung wie bei einem Tippfehler, nur durch
        ein Leerzeichen ausgeloest. Jetzt verhalten sich beide Wege gleich.
        """
        if os.getenv(var_name, "false").strip().lower() == "true":
            return True
        return self._env_file_halts(var_name)

    def triggered_by(self) -> str | None:
        """
        Welche Quelle den Notaus auslöst, oder None.

        Die Quelle zu benennen ist seit dem globalen `STOP_ALL` kein
        Luxus mehr: Wenn alle vier Bots gleichzeitig stoppen, ist "warum
        eigentlich?" die erste Frage - und die Antwort "jemand hat
        STOP_ALL angelegt" ist eine andere als "dieser eine Bot hat
        seine eigene STOP-Datei".

        Die Reihenfolge der Prüfungen ist reine Diagnose-Ergonomie: Die
        beiden Datei-Wege stehen vorn, weil sie der übliche manuelle
        Eingriff sind.
        """
        if self._file_path.exists():
            return f"Notaus-Datei '{self._file_path}'"
        if self._global_file.exists():
            return (
                f"globale Notaus-Datei '{self._global_file}' "
                "(stoppt alle vier Bots)"
            )
        if self._halt_variable_set(self._env_var_name):
            return f"{self._env_var_name}=true"
        if self._halt_variable_set(GLOBAL_KILL_SWITCH_NAME):
            return f"{GLOBAL_KILL_SWITCH_NAME}=true (stoppt alle vier Bots)"
        return None

    def is_set(self) -> bool:
        return self.triggered_by() is not None

    def check(self) -> None:
        """Wirft BotHalted, falls der Notaus aktiv ist."""
        source = self.triggered_by()
        if source is not None:
            raise BotHalted(f"Notaus ausgelöst durch {source}.")


@dataclass
class TradeRecord:
    timestamp: str  # ISO-8601, UTC
    symbol: str
    quote_spent: float
    quantity: float
    price: float
    dry_run: bool
    # Die von uns selbst vergebene `newClientOrderId` der zugehörigen
    # Börsen-Order (siehe pending_orders.py) - None im Dry-Run und bei
    # allen Einträgen aus der Zeit vor dem K2-Fix.
    #
    # Dieses Feld ist hier der IDEMPOTENZSCHLÜSSEL, und das ist der
    # Grund, warum es überhaupt existiert: Grid und Trend führen pro
    # Trade eine eigene `id` plus ein `status`-Feld, ein doppeltes
    # Nachtragen fällt dort von selbst auf ("ist schon geschlossen").
    # Das DCA-Ledger ist dagegen eine reine append-only Liste ohne
    # Status - stürzt der Bot zwischen Ledger-Eintrag und dem Entfernen
    # des Pending-Eintrags ab, würde die Reconciliation beim nächsten
    # Start denselben Kauf ein zweites Mal anhängen und damit Tageslimit
    # und Stop-Loss-Kostenbasis verfälschen. Genau der Schaden, den K2
    # verhindern soll, nur mit umgekehrtem Vorzeichen. Über dieses Feld
    # lässt sich "kenne ich schon" beantworten, ohne das append-only-
    # Modell aufzugeben.
    client_order_id: str | None = None


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
                "Trade-Ledger",
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
                "Trade-Ledger",
                self._path,
                exc,
            )
            raise LedgerUnreadable(
                f"{"Trade-Ledger"} '{self._path}' enthaelt kein gueltiges JSON: {exc}"
            ) from exc
        except OSError as exc:
            logger.error(
                "%s '%s' ist vorhanden, aber nicht lesbar (%s) - es wird "
                "bewusst NICHT mit leerer Historie weitergemacht.",
                "Trade-Ledger",
                self._path,
                exc,
            )
            raise LedgerUnreadable(
                f"{"Trade-Ledger"} '{self._path}' ist nicht lesbar: {exc}"
            ) from exc

        if not isinstance(data, list):
            logger.error(
                "%s '%s' hat ein unerwartetes Format (%s statt Liste) - "
                "bewusst kein Weitermachen mit leerer Historie.",
                "Trade-Ledger",
                self._path,
                type(data).__name__,
            )
            raise LedgerUnreadable(
                f"{"Trade-Ledger"} '{self._path}' enthaelt keine JSON-Liste."
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

    def record(self, trade: TradeRecord) -> None:
        records = self._read()
        records.append(asdict(trade))
        self._write(records)

    def last_trade_time(self, symbol: str) -> datetime | None:
        """
        Zeitpunkt des letzten protokollierten Kaufzyklus dieses Symbols,
        oder None bei leerer Historie.

        Basis für die Fälligkeitsprüfung beim Bot-Start
        (Sicherheitsreview-Punkt W2, siehe main.py): ohne sie löste JEDER
        Prozessstart sofort einen Kauf aus, weil `execute_once()` vor dem
        ersten `sleep` läuft. Ein Neustart alle paar Minuten - geplant
        oder durch eine Restart-Schleife - erzeugte damit so viele Käufe,
        wie das Tageslimit gerade noch durchließ.

        Gezählt werden bewusst AUCH Dry-Run-Einträge: die Frage ist "hat
        in diesem Intervall bereits ein Zyklus stattgefunden", nicht "ist
        echtes Geld geflossen". Unlesbare Zeitstempel werden
        übersprungen statt geraten - im Zweifel wirkt der Bot dann
        "länger nicht gelaufen" und startet sofort, also das bisherige
        Verhalten.
        """
        newest: datetime | None = None
        for record in self._read():
            if record.get("symbol") != symbol:
                continue
            raw = record.get("timestamp")
            try:
                stamp = datetime.fromisoformat(str(raw))
            except (TypeError, ValueError):
                logger.warning(
                    "Unlesbarer Zeitstempel im Trade-Ledger (%r) - Eintrag "
                    "bleibt bei der Fälligkeitsprüfung unberücksichtigt.",
                    raw,
                )
                continue
            if stamp.tzinfo is None:
                # Alle Einträge werden mit Zeitzone geschrieben; ein
                # nackter Zeitstempel kann nur von Hand entstanden sein.
                # Als UTC zu lesen passt zum Rest des Projekts.
                stamp = stamp.replace(tzinfo=timezone.utc)
            if newest is None or stamp > newest:
                newest = stamp
        return newest

    def has_client_order_id(self, client_order_id: str) -> bool:
        """
        Ob zu dieser Börsen-Order bereits ein Eintrag existiert.

        Basis der Idempotenz beim Nachtragen aus der Pending-Orders-Datei
        (siehe TradeRecord.client_order_id und
        strategy.py.reconcile_pending_orders). Alte Einträge ohne das
        Feld liefern None und können deshalb nie versehentlich matchen.
        """
        return any(r.get("client_order_id") == client_order_id for r in self._read())

    def spent_on_day(self, symbol: str, day: date) -> float:
        """Summe aller (auch simulierten) Käufe eines Symbols an einem Tag."""
        _, total_spent = self.day_summary(symbol, day)
        return total_spent

    def day_summary(self, symbol: str, day: date) -> tuple[int, float]:
        """Anzahl und Gesamtausgaben aller (auch simulierten) Käufe eines
        Symbols an einem Tag - Basis für die tägliche Zusammenfassung."""
        matching = [
            r
            for r in self._read()
            if r["symbol"] == symbol
            and datetime.fromisoformat(r["timestamp"]).date() == day
        ]
        return len(matching), sum(r["quote_spent"] for r in matching)

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
            send_notification(
                f"[STOP-LOSS] {symbol}: {loss_pct:.1f}% Verlust (Limit "
                f"{self._stop_loss_pct:.1f}%). Käufe pausiert bis manueller "
                "Reset (python -m dca_bot.reset_stop_loss)."
            )
            return True
        return False

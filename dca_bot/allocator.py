"""
Kapital-Allocator: stufenlose Umschichtung zwischen DCA-Bot und
Trend-Following-Bot je nach aktueller Trendstärke (EMA-Abstand).

Nutzt dieselbe Trendstärke-Berechnung (TrendSignalGenerator aus
trend_signals.py) wie der Trend-Bot und dessen Backtest - keine
Doppelimplementierung. Läuft als vierter, komplett eigenständiger
Prozess: eigener Zustand (`data/allocator_state.json`), eigener Notaus
(`STOP_ALLOCATOR`/`ALLOCATOR_HALT`), eigenes Log. Platziert selbst NIE
Orders - er berechnet nur eine Zahl (den Trend-Following-Anteil
zwischen 0.0 und 1.0) und schreibt sie in seine State-Datei.

DCA-Bot (strategy.py) und Trend-Bot (trend_strategy.py) wissen nichts
von diesem Modul - sie lesen optional (nur wenn explizit über
DCA_ALLOCATOR_STATE_FILE/TREND_ALLOCATOR_STATE_FILE konfiguriert) die
geschriebene Zuteilung via allocator_signals.read_allocation_fraction()
und skalieren damit nur den Betrag einer NEUEN Order - beide bleiben
technisch komplett eigenständig (eigenes Ledger, Notaus, Stop-Loss) und
funktionieren unverändert, falls dieser Prozess nie läuft.

WICHTIG - zwei Takte, bewusst entkoppelt (Sicherheitsreview-Punkt W9):

- Der **Zyklus-Takt** (`ALLOCATOR_INTERVAL_MINUTES`, Default 60 min)
  bestimmt, wie oft dieser Prozess aufwacht, die State-Datei mit
  frischem `updated_at` zurückschreibt und den Notaus prüft.
- Der **Feed-Takt** ist davon unabhängig und beträgt genau EINEN
  Tagesschlusskurs pro Kalendertag (UTC) - exakt wie im Backtest.

Der Grund: `TrendSignalGenerator` ist ereignisgesteuert, nicht
zeitgesteuert. Jeder `feed()` rückt die EMAs um eine Periode vor. Vor
diesem Fix speiste der Allocator bei jedem 60-Minuten-Zyklus einen
aktuellen Spot-Ticker ein, also 24 Werte pro Tag in eine auf 20/50
TAGE ausgelegte Berechnung. Das Ergebnis war faktisch eine
EMA(20h)/EMA(50h) - ein anderer Indikator als der backgetestete, nicht
bloß eine empfindlichere Variante desselben. Erschwerend kam hinzu, dass
`_seed_with_history()` echte Tageskerzen einspeist: nach jedem Neustart
war die EMA rund 50 Zyklen lang ein Mischwesen aus beiden Skalen.

Warum nicht einfach `ALLOCATOR_INTERVAL_MINUTES=1440`: Die
Frische-Prüfung aus W10 leitet ihre Schwelle aus genau diesem Wert ab
(3 × Intervall, siehe allocator_signals._allocation_is_stale). Ein
Tages-Intervall hätte aus "toter Allocator fällt nach 3 Stunden auf" ein
Drei-Tage-Fenster gemacht - ein gerade erst gebauter
Sicherheitsmechanismus wäre für eine Genauigkeitsfrage verwässert
worden. Die Entkopplung liefert beides: Backtest-treue EMAs UND eine
stündlich nachweisbar lebende State-Datei.

Folge für `ALLOCATOR_SMOOTHING_PERIOD`: Die Glättung rückt ebenfalls nur
beim Feed vor, ihre Einheit ist damit **Tage** und direkt vergleichbar
mit `--smoothing-period-days` im Backtest (Default dort 3.0). Der
Default hier ist entsprechend von 24 auf 3 gewechselt - vorher waren 24
Zyklen à 60 Minuten rund ein Tag, also ebenfalls deutlich schneller als
im Backtest.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .allocator_config import AllocatorConfig
from .allocator_signals import compute_target_fraction, derive_trend_strength, smooth_fraction
from .backtest import fetch_historical_klines
from .binance_client import TradingClient
from .notifier import send_notification
from .risk import KillSwitch
from .trend_signals import TrendSignalGenerator

logger = logging.getLogger("allocator")


class Allocator:
    def __init__(self, config: AllocatorConfig, client: TradingClient | None = None):
        """
        `client` wird seit dem W9-Fix nicht mehr gebraucht und deshalb
        auch nicht mehr gespeichert: Die Trendstärke kommt jetzt
        ausschließlich aus öffentlichen Tageskerzen
        (`fetch_historical_klines`, dieselbe Quelle wie der Backtest)
        statt aus einem Spot-Ticker über den authentifizierten Client.

        Der Parameter bleibt trotzdem erhalten - main_allocator.py legt
        weiterhin einen `TradingClient` an, und das ist auch sinnvoll: er
        bringt einen Zugangsdaten-Fehler beim Start ans Licht statt
        irgendwann später. Ihn hier stillschweigend als ungenutztes Feld
        mitzuführen wäre dagegen nur Ballast, den ein späterer Leser für
        einen Rest halten müsste.
        """
        self._config = config
        self._kill_switch = KillSwitch(config.kill_switch_file, env_var_name="ALLOCATOR_HALT")
        # min_gap_pct=0.0 bewusst: die Bestätigungslogik in trend_signals.py
        # ist für binäre Ein-/Ausstiegsentscheidungen gedacht (siehe dort);
        # der Allocator braucht stattdessen den rohen, kontinuierlichen
        # EMA-Abstand für seine eigene lineare Interpolation.
        self._signal_gen = TrendSignalGenerator(config.ema_fast_period, config.ema_slow_period, 0.0)
        self._seeded = False
        # Letzter Kalendertag (UTC), dessen Schlusskurs bereits in die
        # EMAs eingeflossen ist. Trennt den Feed-Takt vom Zyklus-Takt
        # (W9, siehe Modul-Docstring). Bewusst nur im Prozessspeicher:
        # nach einem Neustart wird ohnehin komplett neu aus echten
        # Tageskerzen geseedet, ein persistierter Wert hätte nichts zu
        # sagen, was die Historie nicht besser beantwortet.
        self._last_fed_day: date | None = None
        self._state_path = Path(config.state_file)
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

    def _seed_with_history(self) -> None:
        """Wie TrendFollowingStrategy._seed_with_history() - lädt echte
        historische Tageskerzen, damit die EMAs nicht bei Null anfangen."""
        end_dt = datetime.now(timezone.utc).date() - timedelta(days=1)
        start_dt = end_dt - timedelta(days=self._config.ema_slow_period + 30)
        klines = fetch_historical_klines(
            self._config.symbol, "1d", start_dt.isoformat(), end_dt.isoformat()
        )
        for candle in klines:
            self._signal_gen.feed(candle["close_price"])
        logger.info(
            "Historie geladen: %d Tageskerzen bis %s (EMA-Vorlauf).",
            len(klines),
            end_dt.isoformat(),
        )
        self._seeded = True

        # Den Startpunkt des Feed-Takts aus der TATSÄCHLICH letzten
        # erhaltenen Kerze ableiten, nicht aus `end_dt`. Die Fenstergrenzen
        # in fetch_historical_klines() entstehen über
        # `datetime.strptime(...).timestamp()`, also in lokaler Zeit - ob
        # die Kerze von gestern noch enthalten ist, hängt damit an der
        # Zeitzone des Servers. Würde hier `end_dt` behauptet, obwohl die
        # letzte Kerze von vorgestern stammt, fiele genau ein Tag
        # dauerhaft aus der Berechnung, ohne dass es auffiele.
        last_day = self._candle_day(klines[-1]) if klines else None
        self._last_fed_day = last_day or end_dt
        if last_day is not None and last_day != end_dt:
            logger.info(
                "Letzte erhaltene Tageskerze ist vom %s (erwartet war %s) - "
                "der Feed setzt dort auf.",
                last_day.isoformat(),
                end_dt.isoformat(),
            )

    def _fetch_daily_closes(self, first_day: date, last_day: date) -> list[tuple[date, float]]:
        """
        Holt die Tagesschlusskurse für [first_day, last_day] - dieselbe
        Quelle wie Seeding und Backtest (`fetch_historical_klines`), damit
        live und simuliert nachweislich dieselben Zahlen sehen.

        Das angefragte Fenster ist bewusst auf beiden Seiten um einen Tag
        weiter als das gebrauchte: Die Grenzen in
        `fetch_historical_klines` werden in LOKALER Zeit gebildet, ein
        exakt passend angefragtes Fenster könnte den Randtag je nach
        Zeitzone verlieren. Gefiltert wird danach über den echten
        Kerzen-Zeitstempel, ein zu weites Fenster ist also folgenlos.

        Gibt `(Datum, Schlusskurs)`-Paare zurück, damit der Aufrufer
        `_last_fed_day` auf den zuletzt tatsächlich verarbeiteten Tag
        setzen kann statt auf den erhofften.
        """
        klines = fetch_historical_klines(
            self._config.symbol,
            "1d",
            (first_day - timedelta(days=1)).isoformat(),
            (last_day + timedelta(days=1)).isoformat(),
        )
        result: list[tuple[date, float]] = []
        for candle in klines:
            day = self._candle_day(candle)
            if day is None or day < first_day or day > last_day:
                continue
            result.append((day, float(candle["close_price"])))
        result.sort()
        return result

    @staticmethod
    def _candle_day(candle: dict) -> date | None:
        """
        Kalendertag (UTC) einer Kerze.

        `fetch_historical_klines` liefert `open_time` als
        Millisekunden-Zeitstempel durch, so wie Binance ihn schickt (bei
        einer Tageskerze ist das 00:00 UTC des jeweiligen Tages).
        `datetime`/`date` werden zusätzlich akzeptiert, damit Tests und
        mögliche andere Aufrufwege nicht umgerechnet werden müssen.

        Eine Kerze mit unlesbarem Zeitstempel wird übersprungen statt
        geraten: ein falsch datierter Feed würde die EMAs dauerhaft
        verschieben, und zwar unbemerkt.
        """
        raw = candle.get("open_time")
        if isinstance(raw, bool):
            raw = None
        if isinstance(raw, datetime):
            return raw.astimezone(timezone.utc).date() if raw.tzinfo else raw.date()
        if isinstance(raw, date):
            return raw
        if isinstance(raw, (int, float)):
            try:
                return datetime.fromtimestamp(raw / 1000, tz=timezone.utc).date()
            except (OverflowError, OSError, ValueError):
                pass
        else:
            try:
                return datetime.fromisoformat(str(raw)).date()
            except (TypeError, ValueError):
                pass
        logger.warning(
            "Kerze mit unlesbarem Zeitstempel (%r) wird übersprungen - sie "
            "fließt nicht in die Trendstärke ein.",
            raw,
        )
        return None

    def _feed_completed_days(self) -> list[float]:
        """
        Speist alle seit dem letzten Feed abgeschlossenen Kalendertage
        (UTC) in die EMAs ein - der Kern des W9-Fixes.

        Gibt die Ziel-Zuteilung JE eingespeistem Tag zurück (leer, wenn
        es nichts Neues gab). Dass der Rohwert hier pro Tag entsteht und
        nicht einmal am Ende, ist der entscheidende Punkt: Nach einer
        Downtime von n Tagen glättet der Aufrufer sonst n-mal gegen ein
        einziges Ziel - nämlich das des LETZTEN Tages - statt dem
        tatsächlichen Verlauf zu folgen. Das Ergebnis wäre ein anderes
        als beim tageweisen Durchlaufen derselben Tage, und damit wieder
        eine Abweichung vom Backtest, die genau dann zuschlägt, wenn der
        Prozess eine Weile weg war.

        Eine leere Liste ist der Normalfall: Bei 60-Minuten-Zyklen sind
        das 23 von 24 Durchläufen pro Tag, in denen es schlicht nichts
        Neues zu verarbeiten gibt - die Zuteilung bleibt dann unverändert
        und wird nur mit frischem Zeitstempel neu geschrieben.
        """
        if self._last_fed_day is None:
            return []

        # Der heutige Tag läuft noch - sein Schlusskurs steht erst morgen
        # fest. Gespeist wird bis einschliesslich gestern, exakt wie beim
        # Seeding und im Backtest.
        last_complete_day = datetime.now(timezone.utc).date() - timedelta(days=1)
        first_missing_day = self._last_fed_day + timedelta(days=1)
        if first_missing_day > last_complete_day:
            return []

        missing = (last_complete_day - first_missing_day).days + 1
        logger.info(
            "%d abgeschlossene(r) Tag(e) seit dem letzten Feed (%s) - "
            "Tagesschlusskurse werden nachgeholt.",
            missing,
            self._last_fed_day.isoformat(),
        )

        daily_targets: list[float] = []
        for day, close_price in self._fetch_daily_closes(
            first_missing_day, last_complete_day
        ):
            state = self._signal_gen.feed(close_price)
            self._last_fed_day = day
            daily_targets.append(
                compute_target_fraction(
                    derive_trend_strength(state),
                    self._config.zero_anchor_pct,
                    self._config.full_anchor_pct,
                )
            )
            logger.info(
                "Tagesschlusskurs %s für %s eingespeist: %.2f",
                day.isoformat(),
                self._config.symbol,
                close_price,
            )

        if len(daily_targets) < missing:
            # Binance liefert die Kerze eines gerade erst abgeschlossenen
            # Tages mitunter mit ein paar Minuten Verzoegerung. Kein
            # Fehler - der naechste Zyklus holt den Rest.
            logger.info(
                "%d von %d erwarteten Tageskerzen erhalten - der Rest wird "
                "im nächsten Zyklus nachgeholt.",
                len(daily_targets),
                missing,
            )
        return daily_targets

    def _load_state(self) -> dict:
        if not self._state_path.exists():
            return {}
        try:
            with self._state_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning(
                "Allocator-State-Datei '%s' beschädigt - starte mit leerem Zustand.",
                self._state_path,
            )
            return {}

    def _write_state(self, data: dict) -> None:
        """
        Schreibt die Zuteilung ATOMAR: temporäre Datei, fsync,
        os.replace - dasselbe Muster wie die drei Ledger (W5) und der
        Pending-Store (K2).

        Bis zum 17.09.2026 lief das hier über ein einfaches `open("w")`,
        also kürzen und neu befüllen. Solange DCA und Trend das Opt-in
        nicht gesetzt hatten, war das folgenlos: Die Datei hatte keine
        Konsumenten außer dem Allocator selbst. Mit der Aktivierung des
        Opt-ins (siehe 6h) lesen beide Bots sie vor JEDER neuen Order -
        eine halb geschriebene Datei landet damit unmittelbar in einer
        Kaufentscheidung.

        Und die Fehlerrichtung wäre die falsche gewesen: Eine kaputte
        Datei ließ `read_allocation_fraction()` `None` zurückgeben, was
        bei beiden Bots "kein Allocator" und damit den VOLLEN Betrag
        bedeutet - DCA kauft voll, Trend steigt voll ein, zusammen also
        mehr Kapital als die Zuteilung je vorgesehen hätte. Genau die
        Überallokation, gegen die der Allocator gebaut ist. Die
        Gegenmaßnahme dort steht in allocator_signals.py; hier wird die
        Ursache beseitigt.
        """
        tmp_path = self._state_path.with_name(self._state_path.name + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self._state_path)

    def execute_once(self) -> None:
        """
        Führt genau einen Allocator-Zyklus aus.

        Zwei verschiedene Dinge passieren hier, je nachdem ob seit dem
        letzten Zyklus ein Kalendertag abgeschlossen wurde (W9, siehe
        Modul-Docstring):

        - **Mit neuem Tag:** dessen Schlusskurs fließt in die EMAs, die
          Zuteilung wird neu berechnet und geglättet, und bei einer
          signifikanten Verschiebung geht eine Benachrichtigung raus.
        - **Ohne neuen Tag** (der Normalfall, 23 von 24 Zyklen): die
          Zuteilung bleibt unverändert und wird nur mit frischem
          `updated_at` zurückgeschrieben. Genau das ist der Zweck des
          60-Minuten-Takts - er ist das Lebenszeichen, an dem die
          Frische-Prüfung der Konsumenten hängt (W10). Ohne ihn müsste
          deren Schwelle auf Tage hochgesetzt werden, und ein toter
          Allocator fiele entsprechend später auf.
        """
        self._kill_switch.check()

        if not self._seeded:
            self._seed_with_history()

        daily_targets = self._feed_completed_days()
        fed_days = len(daily_targets)
        previous = self._load_state()

        # Rein aus dem bereits vorhandenen EMA-Stand abgeleitet, ohne
        # neuen Kurs und ohne API-Aufruf - deshalb in JEDEM Zyklus, auch
        # ohne neuen Tag. So stehen gap_pct und Richtung in der
        # State-Datei immer passend zu den tagesbasierten EMAs, statt bis
        # zum nächsten Tageswechsel einen Wert aus einem früheren
        # Prozesslauf zu konservieren.
        state = self._signal_gen.current_state()
        strength = derive_trend_strength(state)
        raw_target = compute_target_fraction(
            strength, self._config.zero_anchor_pct, self._config.full_anchor_pct
        )

        previous_smoothed = previous.get("trend_fraction")
        # Die Glättung rückt genau einmal pro eingespeistem Tag vor -
        # NICHT einmal pro Zyklus. Damit ist `smoothing_period` in TAGEN
        # zu lesen und direkt mit `--smoothing-period-days` aus
        # allocator_backtest.py vergleichbar. Zwei Folgen davon sind
        # Absicht: Ein Zyklus ohne neuen Tag lässt die Zuteilung exakt
        # unverändert (auch direkt nach einem Neustart - ein Neustart
        # darf die geglättete Reihe nicht verschieben), und nach einer
        # Downtime werden die versäumten Tage einzeln nachgeholt, jeder
        # gegen SEIN eigenes Tagesziel. Das Ergebnis ist damit dasselbe,
        # als wäre der Prozess durchgelaufen - es gibt eigens einen Test
        # dafür, der beide Wege gegeneinander stellt.
        smoothed = previous_smoothed
        for daily_target in daily_targets:
            smoothed = smooth_fraction(
                smoothed, daily_target, self._config.smoothing_period
            )
        if smoothed is None:
            # Allererster Lauf überhaupt: kein Vorwert vorhanden, also
            # den Rohwert als Ausgangspunkt nehmen statt künstlich bei 0
            # zu starten (gleiche Regel wie in smooth_fraction).
            smoothed = raw_target

        is_first_run = "last_notified_fraction" not in previous
        last_notified = previous.get("last_notified_fraction", smoothed)
        moved_pp = abs(smoothed - last_notified) * 100

        if is_first_run:
            # Erster Lauf: Baseline setzen, aber nicht als "Verschiebung"
            # benachrichtigen - es gibt noch keinen Vorwert zum Vergleichen.
            last_notified = smoothed
        elif moved_pp >= self._config.notify_threshold_pp:
            send_notification(
                f"[ALLOCATION-UPDATE] Trend-Following-Anteil: {smoothed * 100:.1f}% "
                f"(DCA: {(1 - smoothed) * 100:.1f}%) - Trendstärke {strength:.2f}% "
                f"(Verschiebung seit letzter Meldung: {moved_pp:+.1f} Prozentpunkte)."
            )
            last_notified = smoothed

        self._write_state(
            {
                "trend_fraction": smoothed,
                "raw_target_fraction": raw_target,
                "last_notified_fraction": last_notified,
                "gap_pct": state["gap_pct"],
                "direction": state["confirmed_direction"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
                # Macht die Datei selbstbeschreibend: die Konsumenten
                # (DCA/Trend) leiten daraus ab, ab wann eine Zuteilung
                # als veraltet gilt, statt dieselbe Zahl ein zweites Mal
                # in ihrer eigenen Konfiguration zu führen (W10, siehe
                # allocator_signals._allocation_is_stale).
                "interval_minutes": self._config.interval_minutes,
                # Rein informativ, aber beim Nachvollziehen im Nachhinein
                # der entscheidende Wert: Bis zu welchem Tagesschlusskurs
                # ist diese Zuteilung gerechnet? `updated_at` beantwortet
                # das seit der Entkopplung von Feed- und Zyklus-Takt
                # nicht mehr (W9).
                "last_fed_day": (
                    self._last_fed_day.isoformat() if self._last_fed_day else None
                ),
            }
        )

        if fed_days:
            logger.info(
                "Trendstärke: %.2f%% (Richtung: %s) -> Ziel-Trend-Anteil %.1f%%, "
                "geglättet %.1f%% (DCA-Anteil %.1f%%), Stand %s",
                strength,
                state["confirmed_direction"],
                raw_target * 100,
                smoothed * 100,
                (1 - smoothed) * 100,
                self._last_fed_day.isoformat() if self._last_fed_day else "?",
            )
        else:
            # Der Normalfall: 23 von 24 Zyklen pro Tag. Hier passiert
            # bewusst nichts außer dem frischen Zeitstempel - genau das
            # ist der Zweck des Zyklus-Takts. Die Frische-Prüfung in
            # allocator_signals._allocation_is_stale() beantwortet die
            # Frage "lebt der Allocator noch?" ausschließlich über das
            # Alter dieser Datei; bliebe der Zeitstempel zwischen zwei
            # Tagen stehen, sähe ein gesunder Allocator nach drei Stunden
            # aus wie ein toter, und DCA/Trend fielen grundlos auf 100%
            # DCA zurück.
            logger.info(
                "Kein neuer abgeschlossener Tag seit %s - Zuteilung unverändert "
                "(Trend-Anteil %.1f%%, Trendstärke %.2f%%), Zeitstempel "
                "aktualisiert.",
                self._last_fed_day.isoformat() if self._last_fed_day else "?",
                smoothed * 100,
                strength,
            )

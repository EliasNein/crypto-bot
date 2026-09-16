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
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
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
    def __init__(self, config: AllocatorConfig, client: TradingClient):
        self._config = config
        self._client = client
        self._kill_switch = KillSwitch(config.kill_switch_file, env_var_name="ALLOCATOR_HALT")
        # min_gap_pct=0.0 bewusst: die Bestätigungslogik in trend_signals.py
        # ist für binäre Ein-/Ausstiegsentscheidungen gedacht (siehe dort);
        # der Allocator braucht stattdessen den rohen, kontinuierlichen
        # EMA-Abstand für seine eigene lineare Interpolation.
        self._signal_gen = TrendSignalGenerator(config.ema_fast_period, config.ema_slow_period, 0.0)
        self._seeded = False
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
        with self._state_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def execute_once(self) -> None:
        """Führt genau eine Allocator-Berechnung aus: Preis holen, EMA-
        Abstand aktualisieren, Zuteilung berechnen/glätten, State schreiben,
        bei signifikanter Verschiebung benachrichtigen."""
        self._kill_switch.check()

        if not self._seeded:
            self._seed_with_history()

        price = self._client.get_current_price(self._config.symbol)
        logger.info(
            "Aktueller Preis für %s: %.2f (Näherung für Tagesschlusskurs)",
            self._config.symbol,
            price,
        )

        state = self._signal_gen.feed(price)
        strength = derive_trend_strength(state)
        raw_target = compute_target_fraction(
            strength, self._config.zero_anchor_pct, self._config.full_anchor_pct
        )

        previous = self._load_state()
        previous_smoothed = previous.get("trend_fraction")
        smoothed = smooth_fraction(previous_smoothed, raw_target, self._config.smoothing_period)

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
            }
        )

        logger.info(
            "Trendstärke: %.2f%% (Richtung: %s) -> Ziel-Trend-Anteil %.1f%%, geglättet %.1f%% "
            "(DCA-Anteil %.1f%%)",
            strength,
            state["confirmed_direction"],
            raw_target * 100,
            smoothed * 100,
            (1 - smoothed) * 100,
        )

"""
Gemeinsame Signal-Logik für die Trend-Following-Strategie (EMA-Crossover
mit Trendstärke-Bestätigung).

WICHTIG: Dieses Modul wird sowohl vom Backtest (trend_backtest.py) als
auch von der Live-Strategie (trend_strategy.py) importiert. Zwei getrennte
Implementierungen derselben Entscheidungslogik wären ein klassisches
Risiko: Sie könnten unbemerkt auseinanderlaufen, und ein Backtest-Ergebnis
würde dann nichts mehr über das tatsächliche Live-Verhalten aussagen.
Jede Änderung an der Signal-Logik hier wirkt sich also automatisch auf
beide aus.

Trendstärke-Filter (statt ADX bewusst als einfacher, robust zu
verifizierender EMA-Abstand umgesetzt - siehe trading-bot-projekt.md):
Ein Crossover allein reicht nicht - der Abstand zwischen den beiden EMAs
muss auf mindestens `min_gap_pct` anwachsen, BEVOR das Signal als
bestätigt gilt. Direkt am Crossover-Tag ist der Abstand naturgemäß nahe
null; die Bestätigung filtert genau die Whipsaws heraus, bei denen der
Preis kurz danach wieder zurückkreuzt, ohne dass sich ein echter Trend
etabliert.
"""

from __future__ import annotations


def compute_ema(values: list[float], period: int) -> list[float | None]:
    """
    Exponentieller gleitender Durchschnitt, Standard-Glättungsfaktor
    2/(period+1), mit einfachem Durchschnitt (SMA) der ersten `period`
    Werte als Startpunkt. Gibt None für Indizes zurück, an denen noch
    nicht genug Historie vorliegt.
    """
    if period <= 0:
        raise ValueError("EMA-Periode muss > 0 sein.")

    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result

    sma = sum(values[:period]) / period
    result[period - 1] = sma

    multiplier = 2 / (period + 1)
    ema = sma
    for i in range(period, len(values)):
        ema = (values[i] - ema) * multiplier + ema
        result[i] = ema

    return result


class TrendSignalGenerator:
    """
    Zustandsbehaftete EMA-Crossover-Erkennung mit Trendstärke-Bestätigung.

    Verarbeitet Schlusskurse nacheinander über feed() - identisch nutzbar
    im Backtest (Schleife über historische Kerzen) und live (ein Aufruf
    pro neuer Tageskerze). Kennt selbst KEINE Positionen; gibt nur
    zurück, welcher Trend gerade bestätigt ist ("up"/"down"/None). Die
    Positions-Entscheidung (ein-/aussteigen) trifft die aufrufende Seite
    über decide_action(), siehe unten.
    """

    def __init__(self, fast_period: int, slow_period: int, min_gap_pct: float):
        if fast_period <= 0 or slow_period <= fast_period:
            raise ValueError(
                "fast_period muss > 0 und kleiner als slow_period sein "
                f"(fast={fast_period}, slow={slow_period})."
            )
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._min_gap_pct = min_gap_pct
        self._fast_multiplier = 2 / (fast_period + 1)
        self._slow_multiplier = 2 / (slow_period + 1)
        self._seed_prices: list[float] = []
        self._ema_fast: float | None = None
        self._ema_slow: float | None = None
        self._pending_direction: str | None = None

    def feed(self, close_price: float) -> dict:
        """
        Nimmt einen neuen Schlusskurs entgegen, aktualisiert beide EMAs
        und gibt den aktuellen Stand zurück:
        {"ema_fast": float|None, "ema_slow": float|None,
         "gap_pct": float|None, "confirmed_direction": "up"|"down"|None}
        None-Werte, solange nicht genug Historie für beide EMAs vorliegt.
        """
        if self._ema_slow is None:
            self._seed_prices.append(close_price)
            if len(self._seed_prices) < self._slow_period:
                return {
                    "ema_fast": None,
                    "ema_slow": None,
                    "gap_pct": None,
                    "confirmed_direction": None,
                }
            # Genug Historie: beide EMAs mit dem SMA der letzten `period`
            # Preise seeden (Standard-Vorgehen für EMA-Initialisierung).
            self._ema_fast = sum(self._seed_prices[-self._fast_period:]) / self._fast_period
            self._ema_slow = sum(self._seed_prices[-self._slow_period:]) / self._slow_period
            self._seed_prices = []
        else:
            self._ema_fast = (close_price - self._ema_fast) * self._fast_multiplier + self._ema_fast
            self._ema_slow = (close_price - self._ema_slow) * self._slow_multiplier + self._ema_slow

        if self._ema_fast > self._ema_slow:
            raw_direction = "up"
        elif self._ema_fast < self._ema_slow:
            raw_direction = "down"
        else:
            raw_direction = None

        if raw_direction != self._pending_direction:
            # Neuer roher Crossover (oder erster überhaupt) - die
            # Bestätigungs-"Uhr" für die alte Richtung verfällt, für die
            # neue beginnt sie gerade erst.
            self._pending_direction = raw_direction

        return self.current_state()

    def current_state(self) -> dict:
        """
        Der aktuelle Stand OHNE neuen Kurs - gleiche Struktur wie der
        Rückgabewert von feed().

        Gebraucht vom Kapital-Allocator (allocator.py, W9): Seit der
        Entkopplung von Feed- und Zyklus-Takt speist er die EMAs nur
        einmal pro abgeschlossenem Kalendertag, muss die aktuelle
        Trendstärke aber in JEDEM Zyklus in seine State-Datei schreiben.
        Ohne diese Methode bliebe nur, dafür einen Kurs einzuspeisen -
        also genau der Fehler, den W9 behebt.

        feed() endet bewusst mit einem Aufruf hierher, statt dieselbe
        Ableitung ein zweites Mal zu enthalten: zwei Formeln für
        denselben Sachverhalt sind die Art Divergenz, die später niemand
        mehr bemerkt (siehe W8 und order_lifecycle_state()).
        """
        if self._ema_fast is None or self._ema_slow is None:
            return {
                "ema_fast": None,
                "ema_slow": None,
                "gap_pct": None,
                "confirmed_direction": None,
            }

        gap_pct = abs(self._ema_fast - self._ema_slow) / self._ema_slow * 100

        confirmed_direction = None
        if self._pending_direction is not None and gap_pct >= self._min_gap_pct:
            confirmed_direction = self._pending_direction

        return {
            "ema_fast": self._ema_fast,
            "ema_slow": self._ema_slow,
            "gap_pct": gap_pct,
            "confirmed_direction": confirmed_direction,
        }


def decide_action(
    confirmed_direction: str | None, has_open_position: bool, stop_loss_paused: bool
) -> str | None:
    """
    Reine Entscheidungsfunktion ohne eigenen Zustand oder Seiteneffekte -
    definiert an EINER Stelle, wann ein-/ausgestiegen wird. Gibt
    "ENTER", "EXIT_SIGNAL" oder None zurück.

    Stop-Loss-Exits werden bewusst NICHT hier entschieden, weil dafür der
    aktuelle Preis gegen den individuellen Einstiegspreis der offenen
    Position geprüft werden muss - das übernimmt die aufrufende Seite
    direkt mit is_stop_loss_hit() (siehe unten), üblicherweise VOR dieser
    Funktion aufgerufen, mit Priorität bei Gleichzeitigkeit.
    """
    if has_open_position:
        if confirmed_direction == "down":
            return "EXIT_SIGNAL"
        return None

    if stop_loss_paused:
        return None
    if confirmed_direction == "up":
        return "ENTER"
    return None


def is_stop_loss_hit(entry_price: float, current_price: float, stop_loss_pct: float) -> bool:
    """Fixer Stop-Loss unterhalb des Einstiegspreises einer offenen Position."""
    return current_price <= entry_price * (1 - stop_loss_pct / 100)

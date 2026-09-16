"""
Tests fuer den Entscheidungspfad des Trend-Following-Bots
(Sicherheitsreview-Punkt W17).

Der Befund hatte zwei Haelften, und beide werden hier abgedeckt:

1. **`decide_action()` wurde nie mit einem echten Signal aufgerufen.**
   Kein Test fuetterte den `TrendSignalGenerator` mit einer zeitlich
   fortschreitenden Preisreihe. Was geprueft wurde, waren die Folgen
   einer Entscheidung (`_open_position`, `_close_position`), aufgerufen
   von Hand - nicht die Entscheidung selbst.
2. **`execute_once()` lief nie ueber ein echtes Signal.** Die
   Testbasis in test_trend_stop_loss.py setzt `strategy._seeded = True`,
   um den Netzwerkzugriff auf die Historie zu vermeiden. Nebenwirkung:
   Der Signalgenerator bleibt LEER, `feed()` liefert lauter `None`, und
   `confirmed_direction` ist in allen dortigen Tests `None` - womit
   `decide_action()` ausnahmslos `None` zurueckgibt. Der Pfad Signal ->
   Entscheidung -> Ein-/Ausstieg in `execute_once()` war damit
   vollstaendig ungetestet.

Die Preisreihen hier sind synthetisch, aber sie durchlaufen dieselbe
Mechanik wie echte Kurse: Seeding-Phase, EMA-Fortschreibung, Crossover,
Trendstaerke-Filter. Sie sind bewusst kurz und mit kurzen EMA-Perioden
(3/5 statt der Live-Defaults 20/50) gehalten, damit jeder einzelne
Schritt von Hand nachvollziehbar bleibt - die getestete LOGIK ist
identisch, nur der Vorlauf ist kuerzer.

Kein Netzwerk, keine Zugangsdaten, temporaere Dateien.

Ausfuehren mit:  python -m unittest tests.test_trend_decide_action -v
"""

from __future__ import annotations

import unittest

from dca_bot.trend_signals import TrendSignalGenerator, decide_action

from tests.test_trend_stop_loss import TrendStrategyTestBase


# `decide_action()` gibt fuer "nichts tun" `None` zurueck, keinen String
# "HOLD" - es gibt im Code keine solche Konstante. Der Name hier macht
# die Tests lesbar, ohne etwas zu behaupten, das es nicht gibt: verglichen
# wird gegen den tatsaechlichen Rueckgabewert.
HOLD = None

ENTER = "ENTER"
EXIT_SIGNAL = "EXIT_SIGNAL"

# Parameter aller Preisreihen unten. Kurz genug, um die Reihen von Hand
# nachzurechnen; die Schwelle entspricht dem Live-Default von
# TREND_MIN_GAP_PCT (1,0 %).
FAST_PERIOD = 3
SLOW_PERIOD = 5
MIN_GAP_PCT = 1.0


# --- Preisreihen ----------------------------------------------------------
#
# Alle Reihen beginnen mit SLOW_PERIOD Kursen Vorlauf - so lange gibt es
# per Konstruktion noch keine EMAs und damit auch kein Signal (siehe
# TrendSignalGenerator.feed).

# Stetiger Anstieg. Der EMA-Abstand waechst ueber die Schwelle und bleibt
# darueber: ab dem 6. Kurs ist "up" bestaetigt.
RISING = [100.0, 101.0, 102.0, 103.0, 104.0, 106.0, 109.0, 113.0, 118.0]

# Spiegelbild: stetiger Rueckgang, ab dem 5. Kurs ist "down" bestaetigt.
FALLING = [100.0, 99.0, 98.0, 97.0, 96.0, 94.0, 91.0, 87.0, 82.0]

# Vollkommen flach: EMAs fallen zusammen, der Abstand ist exakt 0 und es
# gibt nicht einmal eine ROHE Richtung.
FLAT = [100.0] * 9

# Seitwaerts mit kleinen Zacken: rohe Richtung wechselt, der Abstand
# bleibt aber weit unter der Schwelle.
CHOPPY = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0]

# Sauberer Aufwaertstrend, der die Schwelle knapp NICHT erreicht - der
# Trendstaerke-Filter ist hier der einzige Grund, warum nichts passiert.
WEAK_RISING = [100.0, 100.2, 100.4, 100.6, 100.8, 101.0, 101.2, 101.4]

# Whipsaw: ein echter Crossover (rohe Richtung springt von "down" auf
# "up") samt Rueckkehr, ohne dass der Abstand je die Schwelle erreicht.
WHIPSAW = [100.0, 99.0, 98.0, 97.5, 97.0, 98.5, 99.5, 99.0, 97.8, 96.8]

# Vollstaendiger Zyklus fuer den End-to-End-Test: erst bestaetigt
# aufwaerts (Einstieg), dann Umkehr bis zu bestaetigt abwaerts (Ausstieg
# per Signal). Der tiefste Kurs nach dem Einstieg liegt bewusst deutlich
# ueber der internen Stop-Loss-Schwelle, damit der Ausstieg nachweislich
# vom SIGNAL kommt und nicht vom Stop-Loss.
FULL_CYCLE = [
    100.0, 101.0, 102.0, 103.0, 104.0,   # Vorlauf, noch kein Signal
    106.0, 109.0, 113.0, 118.0, 119.0,   # bestaetigt "up" ab 106.0
    117.0, 113.0, 110.0, 108.0, 107.0,   # Umkehr, bestaetigt "down" bei 107.0
]

# Derselbe Aufwaertstrend, aber statt der langsamen Umkehr ein Absturz in
# EINEM Schritt. Das erzeugt den Fall, auf den es fuer die
# Reihenfolge-Pruefung in execute_once() ankommt: Im selben Zyklus ist
# gleichzeitig der interne Stop-Loss ausgeloest (90.0 liegt unter der
# 10%-Schwelle von 95.40 zum Einstieg bei 106.0) UND ein Abwaertstrend
# bestaetigt. Bei einer langsameren Umkehr waere das nicht zu haben - dort
# feuert der Signal-Exit schon einen Zyklus frueher, noch oberhalb der
# Stop-Schwelle, und die beiden Bedingungen treffen nie zusammen.
CRASH = FULL_CYCLE[:10] + [90.0]

# Erholung nach dem Absturz: bestaetigt wieder "up" beim Kurs 112.0.
RECOVERY = [92.0, 97.0, 104.0, 112.0, 120.0]


def feed_series(prices, min_gap_pct: float = MIN_GAP_PCT) -> list[dict]:
    """Fuettert eine Preisreihe und gibt den Zustand nach jedem Kurs zurueck."""
    generator = TrendSignalGenerator(FAST_PERIOD, SLOW_PERIOD, min_gap_pct)
    return [generator.feed(price) for price in prices]


def raw_direction(state: dict) -> str | None:
    """
    Die ROHE Richtung (welche EMA liegt oben), unabhaengig vom
    Trendstaerke-Filter.

    Wird gebraucht, um die Praemisse eines Tests zu belegen statt sie
    anzunehmen: Beim Whipsaw-Fall ist der springende Punkt, dass ein
    Crossover TATSAECHLICH stattgefunden hat und trotzdem kein Signal
    entstand. Ohne diese Unterscheidung koennte dieselbe Zusicherung auch
    von einer Reihe erfuellt werden, in der die EMAs sich nie kreuzen -
    der Test wuerde dann gruen sein, ohne den gemeinten Fall zu pruefen.
    """
    fast, slow = state["ema_fast"], state["ema_slow"]
    if fast is None or slow is None or fast == slow:
        return None
    return "up" if fast > slow else "down"


class SignalSeriesTestCase(unittest.TestCase):
    """
    Die Preisreihen selbst: Tun sie, was ihr Name behauptet?

    Bewusst vor den decide_action-Tests: Diese pruefen "Signal X fuehrt zu
    Entscheidung Y". Waere Signal X in Wahrheit gar nicht entstanden,
    waeren sie trotzdem gruen - und wuerden nichts belegen.
    """

    def test_no_signal_during_the_seeding_phase(self):
        states = feed_series(RISING)
        for index, state in enumerate(states[: SLOW_PERIOD - 1]):
            with self.subTest(kurs=index + 1):
                self.assertIsNone(state["ema_slow"])
                self.assertIsNone(state["gap_pct"])
                self.assertIsNone(state["confirmed_direction"])

    def test_rising_series_confirms_up(self):
        states = feed_series(RISING)
        self.assertEqual(states[-1]["confirmed_direction"], "up")
        self.assertGreaterEqual(states[-1]["gap_pct"], MIN_GAP_PCT)

    def test_falling_series_confirms_down(self):
        states = feed_series(FALLING)
        self.assertEqual(states[-1]["confirmed_direction"], "down")
        self.assertGreaterEqual(states[-1]["gap_pct"], MIN_GAP_PCT)

    def test_flat_series_has_no_direction_at_all(self):
        states = feed_series(FLAT)
        for state in states[SLOW_PERIOD - 1 :]:
            self.assertEqual(state["gap_pct"], 0.0)
            self.assertIsNone(raw_direction(state))
            self.assertIsNone(state["confirmed_direction"])

    def test_weak_rising_series_has_a_direction_but_stays_below_threshold(self):
        """
        Die Praemisse des Trendstaerke-Tests: Die rohe Richtung IST "up",
        nur der Abstand reicht nicht. Sonst pruefte der Test weiter unten
        nur, dass eine richtungslose Reihe kein Signal erzeugt - eine
        deutlich schwaechere Aussage.
        """
        states = feed_series(WEAK_RISING)
        tail = states[SLOW_PERIOD - 1 :]
        self.assertTrue(all(raw_direction(s) == "up" for s in tail))
        self.assertTrue(all(s["gap_pct"] < MIN_GAP_PCT for s in tail))
        self.assertTrue(all(s["confirmed_direction"] is None for s in tail))

    def test_crash_series_confirms_down_in_the_very_same_cycle(self):
        """
        Praemisse der Reihenfolge-Pruefung weiter unten: Beim Absturz auf
        90.0 ist im SELBEN Zyklus ein Abwaertstrend bestaetigt und die
        interne Stop-Loss-Schwelle unterschritten. Ohne diesen Nachweis
        wuerde dort nur geprueft, dass ein Stop-Loss-Exit stattfindet -
        nicht, dass er sich gegen ein gleichzeitiges Signal durchsetzt.
        """
        from dca_bot.trend_signals import is_stop_loss_hit

        final = feed_series(CRASH)[-1]
        self.assertEqual(final["confirmed_direction"], "down")
        self.assertTrue(is_stop_loss_hit(106.0, CRASH[-1], 10.0))

    def test_recovery_series_confirms_up_again(self):
        """Praemisse der Latch-Tests: Ohne Sperre waere hier ein neuer
        Einstieg faellig."""
        generator = TrendSignalGenerator(FAST_PERIOD, SLOW_PERIOD, MIN_GAP_PCT)
        states = [generator.feed(price) for price in CRASH + RECOVERY]
        self.assertEqual(states[-1]["confirmed_direction"], "up")

    def test_whipsaw_series_really_contains_a_crossover(self):
        """
        Der Whipsaw-Fall steht und faellt mit dieser Praemisse: Die rohe
        Richtung muss von "down" auf "up" springen UND zurueck, waehrend
        der Abstand nie die Schwelle erreicht.
        """
        states = feed_series(WHIPSAW)
        directions = [raw_direction(s) for s in states[SLOW_PERIOD - 1 :]]
        self.assertIn("down", directions)
        self.assertIn("up", directions)
        self.assertEqual(directions[0], "down")
        self.assertEqual(directions[-1], "down")
        self.assertLess(max(s["gap_pct"] for s in states[SLOW_PERIOD - 1 :]), MIN_GAP_PCT)


class DecideActionFromRealSignalsTestCase(unittest.TestCase):
    """
    Der eigentliche W17-Kern: decide_action() an Signalen, die aus einer
    echten Preisreihe entstanden sind - nicht an von Hand gesetzten
    Richtungs-Strings.
    """

    def _final_direction(self, prices) -> str | None:
        return feed_series(prices)[-1]["confirmed_direction"]

    # -- Bestaetigter Aufwaertstrend --

    def test_confirmed_uptrend_without_position_enters(self):
        direction = self._final_direction(RISING)
        self.assertEqual(
            decide_action(direction, has_open_position=False, stop_loss_paused=False),
            ENTER,
        )

    def test_confirmed_uptrend_with_open_position_holds(self):
        """Kein Doppel-Einstieg: der Bot haelt genau eine Position."""
        direction = self._final_direction(RISING)
        self.assertEqual(
            decide_action(direction, has_open_position=True, stop_loss_paused=False),
            HOLD,
        )

    def test_uptrend_does_not_enter_while_the_stop_loss_is_latched(self):
        """
        Der Latch aus 6f: Nach einem Stop-Loss-Exit bleibt der Einstieg
        gesperrt, bis jemand ihn von Hand zuruecksetzt - auch wenn der
        Trend weiterhin bestaetigt aufwaerts zeigt. Genau der Whipsaw,
        gegen den der Latch gebaut ist.
        """
        direction = self._final_direction(RISING)
        self.assertEqual(
            decide_action(direction, has_open_position=False, stop_loss_paused=True),
            HOLD,
        )

    # -- Bestaetigte Signal-Umkehr --

    def test_confirmed_downtrend_with_open_position_exits(self):
        direction = self._final_direction(FALLING)
        self.assertEqual(
            decide_action(direction, has_open_position=True, stop_loss_paused=False),
            EXIT_SIGNAL,
        )

    def test_confirmed_downtrend_without_position_holds(self):
        """
        Long-only: Ein Abwaertstrend ohne offene Position ist kein
        Einstiegssignal. Der Bot geht nie short - so dokumentiert im
        Docstring von trend_strategy.py, hier auch geprueft.
        """
        direction = self._final_direction(FALLING)
        self.assertEqual(
            decide_action(direction, has_open_position=False, stop_loss_paused=False),
            HOLD,
        )

    def test_downtrend_exit_is_not_blocked_by_a_latched_stop_loss(self):
        """
        Die Sperre gilt nur fuer EINSTIEGE. Eine offene Position muss auch
        bei gesetztem Latch noch per Signal geschlossen werden koennen -
        andernfalls haenge sie fest, obwohl der Trend gedreht hat.
        """
        direction = self._final_direction(FALLING)
        self.assertEqual(
            decide_action(direction, has_open_position=True, stop_loss_paused=True),
            EXIT_SIGNAL,
        )

    # -- Unterhalb der Trendstaerke-Schwelle --

    def test_weak_uptrend_holds_in_both_positions(self):
        """
        Der Trendstaerke-Filter ist hier der einzige Unterschied zu
        RISING: gleiche Richtung, nur zu schwach. Ohne ihn waere das ein
        Einstieg.
        """
        direction = self._final_direction(WEAK_RISING)
        self.assertIsNone(direction)
        self.assertEqual(
            decide_action(direction, has_open_position=False, stop_loss_paused=False),
            HOLD,
        )
        self.assertEqual(
            decide_action(direction, has_open_position=True, stop_loss_paused=False),
            HOLD,
        )

    def test_same_series_would_enter_with_a_lower_threshold(self):
        """
        Gegenprobe zum vorigen Test: Dieselbe Preisreihe fuehrt zu einem
        Einstieg, sobald die Schwelle unter den tatsaechlichen Abstand
        faellt. Das belegt, dass oben WIRKLICH der Filter gegriffen hat
        und nicht etwa die Reihe gar keine Richtung hatte.
        """
        states = feed_series(WEAK_RISING, min_gap_pct=0.1)
        self.assertEqual(states[-1]["confirmed_direction"], "up")
        self.assertEqual(
            decide_action(
                states[-1]["confirmed_direction"],
                has_open_position=False,
                stop_loss_paused=False,
            ),
            ENTER,
        )

    def test_choppy_sideways_market_never_acts(self):
        for index, state in enumerate(feed_series(CHOPPY)):
            with self.subTest(kurs=index + 1):
                for has_position in (False, True):
                    self.assertEqual(
                        decide_action(
                            state["confirmed_direction"],
                            has_open_position=has_position,
                            stop_loss_paused=False,
                        ),
                        HOLD,
                    )

    def test_flat_market_never_acts(self):
        for index, state in enumerate(feed_series(FLAT)):
            with self.subTest(kurs=index + 1):
                self.assertEqual(
                    decide_action(
                        state["confirmed_direction"],
                        has_open_position=False,
                        stop_loss_paused=False,
                    ),
                    HOLD,
                )

    # -- Whipsaw --

    def test_whipsaw_crossover_triggers_no_signal_at_any_point(self):
        """
        Der Fall, fuer den der Trendstaerke-Filter ueberhaupt existiert:
        Die EMAs kreuzen sich tatsaechlich (belegt in
        SignalSeriesTestCase), aber der Abstand erreicht die Schwelle nie.
        Ueber die GESAMTE Reihe darf keine einzige Entscheidung fallen -
        nicht nur am Ende, denn ein einzelner Fehleinstieg irgendwo in der
        Mitte waere genauso teuer.
        """
        for index, state in enumerate(feed_series(WHIPSAW)):
            with self.subTest(kurs=index + 1):
                for has_position in (False, True):
                    self.assertEqual(
                        decide_action(
                            state["confirmed_direction"],
                            has_open_position=has_position,
                            stop_loss_paused=False,
                        ),
                        HOLD,
                    )

    # -- Der Uebergang selbst --

    def test_full_cycle_produces_exactly_one_enter_and_one_exit(self):
        """
        Ueber den kompletten Verlauf auf und ab: genau ein Einstiegs- und
        genau ein Ausstiegssignal, in dieser Reihenfolge. Geprueft wird
        dabei mit mitgefuehrter Position - also so, wie der Bot die
        Funktion tatsaechlich aufruft, statt jeden Kurs isoliert zu
        betrachten.
        """
        has_position = False
        actions: list[tuple[int, str]] = []
        for index, state in enumerate(feed_series(FULL_CYCLE), start=1):
            action = decide_action(
                state["confirmed_direction"],
                has_open_position=has_position,
                stop_loss_paused=False,
            )
            if action == ENTER:
                has_position = True
                actions.append((index, ENTER))
            elif action == EXIT_SIGNAL:
                has_position = False
                actions.append((index, EXIT_SIGNAL))

        self.assertEqual([a for _, a in actions], [ENTER, EXIT_SIGNAL])
        enter_at, exit_at = actions[0][0], actions[1][0]
        self.assertLess(enter_at, exit_at)
        # Der Einstieg faellt beim ersten Kurs, an dem die Schwelle
        # ueberschritten wird - nicht schon beim rohen Crossover davor.
        self.assertEqual(FULL_CYCLE[enter_at - 1], 106.0)
        self.assertEqual(FULL_CYCLE[exit_at - 1], 107.0)


class ExecuteOnceWithRealSignalsTestCase(TrendStrategyTestBase):
    """
    Die zweite Haelfte des W17-Befundes: `execute_once()` selbst, getrieben
    von einer echten Preisreihe statt von direkten Methodenaufrufen.

    Anders als in test_trend_stop_loss.py wird der Signalgenerator hier
    nicht umgangen - er fuellt sich aus denselben Kursen, die der Bot pro
    Zyklus abfragt. Damit laeuft der komplette Pfad Preis -> feed() ->
    decide_action() -> _open_position()/_close_position() genau so, wie
    er live laeuft.
    """

    def _run_series(self, prices, **overrides):
        """
        Laesst den Bot die Preisreihe Zyklus fuer Zyklus durchlaufen -
        ein `execute_once()` pro Kurs, genau wie im Betrieb ein Aufruf
        pro Tageskerze.
        """
        params = dict(
            ema_fast_period=FAST_PERIOD,
            ema_slow_period=SLOW_PERIOD,
            min_gap_pct=MIN_GAP_PCT,
        )
        params.update(overrides)
        strategy, client = self._make_strategy(
            trading_enabled=True, price=prices[0], **params
        )
        for price in prices:
            client.price = price
            strategy.execute_once()
        return strategy, client

    def test_execute_once_enters_and_exits_on_real_signals(self):
        strategy, client = self._run_series(FULL_CYCLE)

        # Genau ein Einstieg und ein Ausstieg, beide ueber echte Orders.
        self.assertEqual(len(client.market_buy_calls), 1)
        self.assertEqual(len(client.market_sell_calls), 1)
        self.assertIsNone(strategy._ledger.open_position())

        trades = strategy._ledger._read()
        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade["status"], "closed")
        # Der Ausstieg kam vom SIGNAL, nicht vom Stop-Loss - der tiefste
        # Kurs nach dem Einstieg liegt weit ueber der 10%-Schwelle.
        self.assertEqual(trade["exit_reason"], "signal")
        self.assertEqual(trade["entry_price"], 106.0)
        self.assertEqual(trade["exit_price"], 107.0)
        # Ein Signal-Exit setzt den Stop-Loss-Latch NICHT.
        self.assertFalse(strategy._stop_loss.is_paused())

    def test_execute_once_does_not_enter_twice_while_a_position_is_open(self):
        """
        Zwischen Einstieg (Kurs 106) und Umkehr liegen vier weitere
        Zyklen mit bestaetigtem Aufwaertstrend. Keiner davon darf eine
        zweite Position eroeffnen.

        Geprueft wird hier die STRUKTUR von execute_once(), nicht die
        Regel in decide_action(): Bei offener Position wertet
        execute_once() nur `action == "EXIT_SIGNAL"` aus und ruft
        `_open_position()` in diesem Zweig gar nicht erst auf. Die Regel
        "up + offene Position -> nichts tun" in decide_action() ist
        also eine zweite, unabhaengige Sicherung derselben Aussage - sie
        hat ihren eigenen Test weiter oben
        (test_confirmed_uptrend_with_open_position_holds). Beide Ebenen
        einzeln zu pruefen ist Absicht: faellt eine weg, faellt es auf.
        """
        _, client = self._run_series(FULL_CYCLE)
        self.assertEqual(len(client.market_buy_calls), 1)

    def test_execute_once_stays_idle_through_a_whipsaw(self):
        """
        Derselbe Weg, aber mit der Whipsaw-Reihe: kein Einstieg, kein
        Verkauf, kein Ledger-Eintrag - ueber alle Zyklen hinweg.
        """
        strategy, client = self._run_series(WHIPSAW)

        self.assertEqual(client.market_buy_calls, [])
        self.assertEqual(client.market_sell_calls, [])
        self.assertEqual(strategy._ledger._read(), [])
        self.assertIsNone(strategy._ledger.open_position())

    def test_execute_once_stays_idle_below_the_strength_threshold(self):
        strategy, client = self._run_series(WEAK_RISING)
        self.assertEqual(client.market_buy_calls, [])
        self.assertEqual(strategy._ledger._read(), [])

    def test_execute_once_enters_on_the_same_series_with_a_lower_threshold(self):
        """
        Gegenprobe zum vorigen Test, diesmal durch execute_once():
        Dieselbe Reihe fuehrt zu einem echten Kauf, sobald die Schwelle
        unter dem tatsaechlichen EMA-Abstand liegt. Ohne diesen Test
        koennte der vorige auch gruen sein, wenn execute_once() aus einem
        ganz anderen Grund nichts tut.
        """
        _, client = self._run_series(WEAK_RISING, min_gap_pct=0.1)
        self.assertEqual(len(client.market_buy_calls), 1)

    def test_execute_once_never_shorts_a_falling_market(self):
        """Long-only, jetzt auch auf dem echten Pfad: eine von Anfang an
        fallende Reihe loest keinerlei Order aus."""
        strategy, client = self._run_series(FALLING)

        self.assertEqual(client.market_buy_calls, [])
        self.assertEqual(client.market_sell_calls, [])
        self.assertEqual(strategy._ledger._read(), [])

    def test_internal_stop_loss_wins_over_a_simultaneous_exit_signal(self):
        """
        Reihenfolge in execute_once(): Der interne Stop-Loss wird VOR
        decide_action() geprueft. Faellt der Kurs unter die Stop-Schwelle,
        waehrend gleichzeitig ein bestaetigter Abwaertstrend vorliegt,
        muss der Ausstieg als `stop_loss` verbucht werden und den Latch
        setzen - sonst duerfte der Bot im naechsten bestaetigten
        Aufwaertstrend sofort wieder einsteigen.
        """
        strategy, client = self._run_series(CRASH)

        trades = strategy._ledger._read()
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["status"], "closed")
        self.assertEqual(trades[0]["exit_reason"], "stop_loss")
        self.assertTrue(strategy._stop_loss.is_paused())

    def test_latched_stop_loss_blocks_a_later_entry_signal(self):
        """
        Fortsetzung des vorigen Falls ueber execute_once(): Nach dem
        Stop-Loss-Exit folgt eine erneute, bestaetigte Aufwaertsbewegung.
        Solange der Latch steht, darf daraus kein neuer Einstieg werden.

        Das prueft eine Stelle, die decide_action() allein nicht zeigt:
        `execute_once()` uebergibt dort hart `stop_loss_paused=False` und
        behandelt die Pause stattdessen mit einem eigenen frueheren
        Return. Waere dieser Return nicht da, faende der Test einen
        zweiten Kauf.
        """
        strategy, client = self._run_series(CRASH + RECOVERY)

        self.assertTrue(strategy._stop_loss.is_paused())
        self.assertEqual(len(client.market_buy_calls), 1)
        self.assertEqual(len(strategy._ledger._read()), 1)

    def test_entry_is_possible_again_after_resetting_the_latch(self):
        """
        Gegenprobe: Der Latch ist die Ursache, nicht etwa ein erschoepfter
        Signalgenerator. Nach einem manuellen Reset (wie ihn
        reset_trend_stop_loss.py ausloest) fuehrt dieselbe Erholung zu
        einem neuen Einstieg.
        """
        strategy, client = self._run_series(CRASH)
        self.assertTrue(strategy._stop_loss.is_paused())
        strategy._stop_loss.reset()

        for price in RECOVERY:
            client.price = price
            strategy.execute_once()

        self.assertEqual(len(client.market_buy_calls), 2)
        self.assertIsNotNone(strategy._ledger.open_position())


if __name__ == "__main__":
    unittest.main()

"""
Direkte Tests der Zuteilungs-Mathematik des Kapital-Allocators
(`derive_trend_strength`, `compute_target_fraction`, `smooth_fraction` in
`dca_bot/allocator_signals.py`) - Stufe 2 der Verbesserungsvorschlaege,
Anhang zur Grid-Haelfte von Punkt 12.

**Der Befund ist derselbe wie beim Grid:** Diese drei Funktionen hatten
keinen direkten Test. Sie liefen nur indirekt ueber den Allocator-Backtest
und den Live-Prozess mit. `read_allocation_fraction()` - die vierte
Funktion des Moduls - ist dagegen seit Stufe 1 in
tests/test_improvements_stage_1.py abgedeckt und steht bewusst nicht hier
noch einmal: Sie liest eine Datei und ist damit etwas anderes als die
reine Rechnung.

**Warum das zaehlt, obwohl der Allocator nie Orders platziert:** Seit dem
Opt-in vom 16.09. (6h) skalieren DCA und Trend den Betrag JEDER neuen
Order mit dem Ergebnis dieser Kette. Ein Fehler hier aendert keine
Entscheidung, aber jede Positionsgroesse - und zwar still, weil das
Ergebnis eine plausible Zahl zwischen 0 und 1 bleibt.

Wie in tests/test_trend_decide_action.py und tests/test_grid_signals.py
gilt: Wo ein Test die Form "Situation X ergibt Y" hat, belegt ein eigener
Test, dass Situation X wirklich vorlag. Beim Abwaertstrend ist das der
springende Punkt - die dortige Preisreihe hat einen EMA-Abstand von ueber
3 %, der ohne die Richtungspruefung auf volle 100 % Trend-Anteil
abgebildet wuerde.

Kein Netzwerk, keine Zugangsdaten, keine Dateien.

Ausfuehren mit:  python -m unittest tests.test_allocator_signals -v
"""

from __future__ import annotations

import unittest

from dca_bot.allocator_signals import (
    compute_target_fraction,
    derive_trend_strength,
    smooth_fraction,
)
from dca_bot.trend_signals import TrendSignalGenerator


# Live-Defaults aus .env.example (ALLOCATOR_ZERO_ANCHOR_PCT /
# ALLOCATOR_FULL_ANCHOR_PCT): unter 0 % EMA-Abstand kein Trend-Anteil, ab
# 3 % voller Trend-Anteil. Laut 5a ein bewusster Ausgangspunkt, kein
# empirisch hergeleiteter Optimalwert.
ZERO_ANCHOR = 0.0
FULL_ANCHOR = 3.0

# Glaettungsperiode in TAGEN (ALLOCATOR_SMOOTHING_PERIOD, Default 3) -
# ergibt den EMA-Multiplikator 2/(3+1) = 0,5.
SMOOTHING_PERIOD = 3.0
SMOOTHING_MULTIPLIER = 0.5

# EMA-Perioden wie in test_trend_decide_action.py: kurz genug zum
# Nachrechnen, identische Logik. Der Allocator fuettert den Generator
# bewusst mit min_gap_pct=0 - er braucht den rohen, kontinuierlichen
# EMA-Abstand, nicht die Bestaetigungslogik fuer binaere Entscheidungen
# (siehe allocator.py und trading-bot-projekt.md 7.4).
FAST_PERIOD = 3
SLOW_PERIOD = 5
ALLOCATOR_MIN_GAP_PCT = 0.0

RISING = [100.0, 101.0, 102.0, 103.0, 104.0, 106.0, 109.0, 113.0, 118.0]
FALLING = [100.0, 99.0, 98.0, 97.0, 96.0, 94.0, 91.0, 87.0, 82.0]
FLAT = [100.0] * 9


def final_state(prices: list[float]) -> dict:
    """Zustand des Signalgenerators nach der kompletten Preisreihe."""
    generator = TrendSignalGenerator(FAST_PERIOD, SLOW_PERIOD, ALLOCATOR_MIN_GAP_PCT)
    state = {}
    for price in prices:
        state = generator.feed(price)
    return state


class DeriveTrendStrengthTestCase(unittest.TestCase):
    """
    `derive_trend_strength`: aus dem Signalzustand wird eine GERICHTETE
    Staerke. Nur eine bestaetigte Aufwaertsrichtung zaehlt - der Trend-Bot
    ist long-only, bei Abwaertstrend bekaeme er ohnehin kein Kapital.
    """

    def test_confirmed_uptrend_yields_the_raw_gap(self):
        state = final_state(RISING)
        self.assertEqual(state["confirmed_direction"], "up")
        self.assertAlmostEqual(derive_trend_strength(state), state["gap_pct"], places=9)

    def test_the_rising_series_really_confirms_up_with_a_usable_gap(self):
        """
        Praemisse: Die Reihe erzeugt tatsaechlich eine bestaetigte
        Aufwaertsrichtung, und der Abstand liegt ZWISCHEN den Ankern -
        nicht geklemmt. Damit durchlaeuft der Test weiter unten wirklich
        die Interpolation und nicht nur den Klemmzweig.
        """
        state = final_state(RISING)
        self.assertEqual(state["confirmed_direction"], "up")
        self.assertAlmostEqual(state["gap_pct"], 2.4527, places=3)
        self.assertGreater(state["gap_pct"], ZERO_ANCHOR)
        self.assertLess(state["gap_pct"], FULL_ANCHOR)

    def test_confirmed_downtrend_yields_zero_strength(self):
        """
        Long-only, auf der Kapitalseite: Ein Abwaertstrend ist keine
        negative Zuteilung, sondern gar keine.
        """
        state = final_state(FALLING)
        self.assertEqual(state["confirmed_direction"], "down")
        self.assertEqual(derive_trend_strength(state), 0.0)

    def test_the_falling_series_has_a_gap_that_would_otherwise_mean_full_allocation(self):
        """
        Die wichtigste Praemisse dieser Datei. Die fallende Reihe hat
        einen EMA-Abstand von ueber 3 % - also OBERHALB des
        Voll-Ankers. Wuerde `derive_trend_strength` die Richtung
        ignorieren und den rohen Abstand durchreichen, bekaeme der
        Trend-Bot ausgerechnet im Abwaertstrend 100 % des Kapitals.

        Ohne diesen Nachweis waere "Abwaertstrend ergibt 0" auch an einer
        Reihe gruen, deren Abstand ohnehin bei null lag - der Test wuerde
        dann nichts ueber die Richtungspruefung aussagen.
        """
        state = final_state(FALLING)
        self.assertGreater(state["gap_pct"], FULL_ANCHOR)
        self.assertEqual(
            compute_target_fraction(state["gap_pct"], ZERO_ANCHOR, FULL_ANCHOR), 1.0
        )
        # Und mit der Richtungspruefung wird daraus das Gegenteil:
        self.assertEqual(
            compute_target_fraction(
                derive_trend_strength(state), ZERO_ANCHOR, FULL_ANCHOR
            ),
            0.0,
        )

    def test_no_confirmed_direction_yields_zero_strength(self):
        state = final_state(FLAT)
        self.assertIsNone(state["confirmed_direction"])
        self.assertEqual(derive_trend_strength(state), 0.0)

    def test_missing_gap_yields_zero_even_when_the_direction_says_up(self):
        """
        Waehrend der Seeding-Phase gibt es noch keinen Abstand. Ein
        `gap_pct` von `None` darf nicht durchgereicht werden - die
        Multiplikation damit waere ein TypeError mitten im Kaufzyklus des
        lesenden Bots.
        """
        self.assertEqual(
            derive_trend_strength({"confirmed_direction": "up", "gap_pct": None}), 0.0
        )

    def test_a_fresh_generator_yields_zero_strength(self):
        """Derselbe Fall aus dem echten Generator statt aus einem Dict."""
        generator = TrendSignalGenerator(FAST_PERIOD, SLOW_PERIOD, ALLOCATOR_MIN_GAP_PCT)
        self.assertEqual(derive_trend_strength(generator.current_state()), 0.0)


class ComputeTargetFractionTestCase(unittest.TestCase):
    """
    `compute_target_fraction`: lineare Interpolation zwischen den Ankern,
    an beiden Enden geklemmt.
    """

    def _fraction(self, strength: float) -> float:
        return compute_target_fraction(strength, ZERO_ANCHOR, FULL_ANCHOR)

    # -- Interpolation --

    def test_midpoint_between_the_anchors_is_half(self):
        self.assertAlmostEqual(self._fraction(1.5), 0.5, places=9)

    def test_a_quarter_of_the_way_is_a_quarter(self):
        self.assertAlmostEqual(self._fraction(0.75), 0.25, places=9)

    def test_three_quarters_of_the_way_is_three_quarters(self):
        self.assertAlmostEqual(self._fraction(2.25), 0.75, places=9)

    def test_interpolation_is_linear_across_the_whole_span(self):
        """
        Gleiche Staerke-Schritte ergeben gleiche Zuteilungs-Schritte -
        das ist die Aussage "linear" und nicht nur "irgendwo dazwischen".
        """
        steps = [self._fraction(s) for s in (0.5, 1.0, 1.5, 2.0, 2.5)]
        deltas = [b - a for a, b in zip(steps, steps[1:])]
        for delta in deltas:
            self.assertAlmostEqual(delta, deltas[0], places=9)

    def test_interpolation_works_with_a_non_zero_lower_anchor(self):
        """
        Die Anker sind konfigurierbar. Mit `zero=1.0, full=3.0` liegt die
        Mitte bei 2,0 - der Nullpunkt verschiebt sich mit, statt weiter
        bei 0 zu kleben.
        """
        self.assertAlmostEqual(compute_target_fraction(2.0, 1.0, 3.0), 0.5, places=9)
        self.assertEqual(compute_target_fraction(1.0, 1.0, 3.0), 0.0)
        self.assertEqual(compute_target_fraction(0.5, 1.0, 3.0), 0.0)

    # -- Anker und Klemmung --

    def test_exactly_on_the_zero_anchor_is_zero(self):
        self.assertEqual(self._fraction(ZERO_ANCHOR), 0.0)

    def test_exactly_on_the_full_anchor_is_one(self):
        self.assertEqual(self._fraction(FULL_ANCHOR), 1.0)

    def test_strength_above_the_full_anchor_is_clamped_to_one(self):
        self.assertEqual(self._fraction(10.0), 1.0)

    def test_strength_below_the_zero_anchor_is_clamped_to_zero(self):
        self.assertEqual(self._fraction(-1.0), 0.0)

    def test_without_clamping_those_values_would_leave_the_valid_range(self):
        """
        Praemisse der beiden Klemm-Tests: Die reine Formel ergaebe dort
        3,33 bzw. -0,33. Beides waere kein gueltiger Anteil - und
        `read_allocation_fraction()` wuerde eine solche Zahl auf der
        Leseseite als kaputt werten und konservativ auf 0 zurueckfallen
        (siehe Stufe 1). Geklemmt wird also hier, nicht erst dort.
        """
        span = FULL_ANCHOR - ZERO_ANCHOR
        self.assertGreater((10.0 - ZERO_ANCHOR) / span, 1.0)
        self.assertLess((-1.0 - ZERO_ANCHOR) / span, 0.0)

    def test_the_first_live_measurement_maps_to_full_trend_allocation(self):
        """
        Der erste real gemessene Wert des Live-Dry-Runs vom 15.09.2026
        (6e): Trendstaerke 5,25 % bei Richtung "up" ergab
        `trend_fraction: 1.0` in data/allocator_state.json. Hier
        nachgerechnet, damit die Doku-Aussage an einem Test haengt und
        nicht nur an einem Logauszug.
        """
        self.assertEqual(self._fraction(5.25), 1.0)

    def test_the_result_stays_within_zero_and_one_for_any_strength(self):
        """
        Die Eigenschaft, auf die sich beide Konsumenten verlassen: Der
        Rueckgabewert ist immer ein gueltiger Anteil. DCA rechnet
        `betrag * (1 - f)`, Trend `betrag * f` - ein Wert ausserhalb 0-1
        ergaebe dort einen negativen oder ueberhoehten Betrag.
        """
        for strength in (-100.0, -1.0, 0.0, 0.001, 1.5, 2.999, 3.0, 3.001, 100.0):
            with self.subTest(staerke=strength):
                self.assertGreaterEqual(self._fraction(strength), 0.0)
                self.assertLessEqual(self._fraction(strength), 1.0)

    # -- Ungueltige Anker --

    def test_full_anchor_not_above_zero_anchor_is_rejected(self):
        """
        Waeren die Anker gleich, waere die Interpolation eine Division
        durch null; waeren sie vertauscht, liefe die Zuteilung
        rueckwaerts (mehr Trendstaerke -> weniger Trend-Anteil). Beides
        faengt `config_guard.py` beim Start ab, aber die Funktion bleibt
        selbst auf der sicheren Seite.
        """
        for zero, full in ((3.0, 3.0), (3.0, 1.0)):
            with self.subTest(zero=zero, full=full):
                with self.assertRaises(ValueError):
                    compute_target_fraction(2.0, zero, full)


class SmoothFractionTestCase(unittest.TestCase):
    """
    `smooth_fraction`: EMA-Glaettung der Zuteilung selbst - der
    Whipsaw-Schutz. Bei einer stufenlosen Kurve gibt es (anders als bei
    diskreten Signalen) keinen festen Punkt zum "Bestaetigen".
    """

    def test_the_first_call_adopts_the_raw_value(self):
        """
        Ohne Vorwert wird der Rohwert uebernommen, statt kuenstlich bei 0
        zu starten. Sonst braeuchte ein frisch gestarteter Allocator
        mehrere Tage, bis seine Zuteilung ueberhaupt aussagekraeftig
        waere - und DCA/Trend wuerden solange mit einer erfundenen Zahl
        rechnen.
        """
        self.assertEqual(smooth_fraction(None, 0.8, SMOOTHING_PERIOD), 0.8)

    def test_the_multiplier_matches_the_documented_ema_formula(self):
        """
        Praemisse der folgenden Faelle: Es ist wirklich `2/(period+1)`,
        dieselbe Formel wie die Preis-EMAs in trend_signals.py. Bei
        Periode 3 also exakt 0,5.
        """
        self.assertEqual(2 / (SMOOTHING_PERIOD + 1), SMOOTHING_MULTIPLIER)
        self.assertEqual(smooth_fraction(0.0, 1.0, SMOOTHING_PERIOD), SMOOTHING_MULTIPLIER)

    def test_a_jump_to_full_allocation_is_damped(self):
        """
        Der Kern des Whipsaw-Schutzes: Springt das Rohziel von 0 auf 1,
        steigt die geglaettete Zuteilung nur auf 0,5. Ein einzelner Tag
        mit starkem Trend schichtet also nicht sofort das ganze Kapital um.
        """
        self.assertEqual(smooth_fraction(0.0, 1.0, SMOOTHING_PERIOD), 0.5)

    def test_without_smoothing_the_same_jump_would_be_immediate(self):
        """Gegenprobe: Der Rohwert selbst ist 1,0 - die Daempfung oben
        kommt von der Glaettung und nicht vom Eingangswert."""
        self.assertEqual(compute_target_fraction(FULL_ANCHOR, ZERO_ANCHOR, FULL_ANCHOR), 1.0)

    def test_repeated_days_converge_towards_the_raw_target(self):
        """
        Haelt der Trend an, naehert sich die Zuteilung dem Rohziel -
        schrittweise, mit exakt halbierter Restdistanz pro Tag.
        """
        expected = [0.5, 0.75, 0.875, 0.9375, 0.96875]
        smoothed = 0.0
        for day, want in enumerate(expected, start=1):
            smoothed = smooth_fraction(smoothed, 1.0, SMOOTHING_PERIOD)
            with self.subTest(tag=day):
                self.assertAlmostEqual(smoothed, want, places=9)

    def test_it_approaches_but_never_quite_reaches_the_target(self):
        """
        Eigenschaft eines EMA: asymptotisch. Auch nach vielen Tagen
        bleibt ein Rest - relevant, weil "Zuteilung erreicht nie exakt
        1,0" sonst wie ein Fehler aussieht.
        """
        smoothed = 0.0
        for _ in range(50):
            smoothed = smooth_fraction(smoothed, 1.0, SMOOTHING_PERIOD)
        self.assertLess(smoothed, 1.0)
        self.assertGreater(smoothed, 0.999)

    def test_it_damps_downwards_symmetrically(self):
        """
        Die Glaettung wirkt in beide Richtungen gleich stark - ein
        abflauender Trend zieht das Kapital ebenso schrittweise zurueck,
        wie er es geholt hat.
        """
        self.assertEqual(smooth_fraction(1.0, 0.0, SMOOTHING_PERIOD), 0.5)

    def test_an_unchanged_target_leaves_the_value_alone(self):
        self.assertEqual(smooth_fraction(0.42, 0.42, SMOOTHING_PERIOD), 0.42)

    def test_a_longer_period_damps_more_strongly(self):
        """
        `ALLOCATOR_SMOOTHING_PERIOD` ist der Regler fuer die Traegheit.
        Dass eine groessere Periode langsamer reagiert, ist die ganze
        Bedeutung dieser Einstellung.
        """
        steps = [smooth_fraction(0.0, 1.0, period) for period in (1.0, 3.0, 9.0, 29.0)]
        self.assertEqual(steps, sorted(steps, reverse=True))
        self.assertAlmostEqual(steps[2], 0.2, places=9)

    def test_smoothing_keeps_the_value_within_zero_and_one(self):
        """
        Wie bei compute_target_fraction: Das Ergebnis muss ein gueltiger
        Anteil bleiben, sonst schreibt der Allocator eine Zahl in die
        State-Datei, die die Leseseite als kaputt verwirft.
        """
        smoothed = 0.0
        for raw in (1.0, 0.0, 1.0, 0.3, 0.9, 0.0):
            smoothed = smooth_fraction(smoothed, raw, SMOOTHING_PERIOD)
            with self.subTest(rohziel=raw):
                self.assertGreaterEqual(smoothed, 0.0)
                self.assertLessEqual(smoothed, 1.0)


class AllocationChainTestCase(unittest.TestCase):
    """
    Die drei Funktionen in der Reihenfolge, in der `allocator.execute_once()`
    sie aufruft: Signalzustand -> Staerke -> Rohziel -> Glaettung.

    Gleiche Ueberlegung wie die `execute_once()`-Klasse in
    test_trend_decide_action.py: Jede Funktion einzeln zu pruefen zeigt
    nicht, ob sie richtig zusammengesteckt sind.
    """

    def _chain(self, prices: list[float], previous_smoothed: float | None) -> float:
        state = final_state(prices)
        strength = derive_trend_strength(state)
        raw_target = compute_target_fraction(strength, ZERO_ANCHOR, FULL_ANCHOR)
        return smooth_fraction(previous_smoothed, raw_target, SMOOTHING_PERIOD)

    def test_an_uptrend_allocates_most_capital_to_the_trend_bot(self):
        """
        Der Abstand von 2,45 % liegt zwischen den Ankern und ergibt ein
        Rohziel von rund 0,82. Beim allerersten Lauf (kein Vorwert) wird
        es unveraendert uebernommen.
        """
        self.assertAlmostEqual(self._chain(RISING, None), 0.8176, places=3)

    def test_a_downtrend_allocates_nothing_to_the_trend_bot(self):
        """
        Trotz eines EMA-Abstands von ueber 3 % - die Richtung entscheidet.
        Beim ersten Lauf also 0,0: voller DCA-Betrag, kein Trend-Einstieg.
        """
        self.assertEqual(self._chain(FALLING, None), 0.0)

    def test_a_flat_market_allocates_nothing_to_the_trend_bot(self):
        self.assertEqual(self._chain(FLAT, None), 0.0)

    def test_an_existing_allocation_is_only_moved_halfway_per_day(self):
        """
        Mit Vorwert greift die Glaettung: Stand die Zuteilung gestern bei
        0,0 und das Rohziel liegt heute bei 0,82, geht sie nur auf rund
        0,41. Das ist der Unterschied zwischen "der Allocator schichtet
        um" und "der Allocator springt".
        """
        self.assertAlmostEqual(self._chain(RISING, 0.0), 0.8176 / 2, places=3)

    def test_a_trend_reversal_pulls_capital_back_gradually(self):
        """
        Der Fall, fuer den die Glaettung gebaut ist: Gestern voll im
        Trend, heute dreht der Markt. Die Zuteilung faellt auf die
        Haelfte statt sofort auf null - und ein einzelner Ausreisser-Tag
        wuerde sie beim naechsten Feed wieder anheben.
        """
        self.assertEqual(self._chain(FALLING, 1.0), 0.5)

    def test_the_dca_share_is_the_complement_of_the_trend_share(self):
        """
        So lesen die beiden Konsumenten das Ergebnis (siehe strategy.py
        und trend_strategy.py): Trend nimmt `f`, DCA nimmt `1 - f`.
        Zusammen also nie mehr als der volle Betrag - genau die
        Ueberallokation, gegen die der Allocator existiert.
        """
        trend_share = self._chain(RISING, None)
        dca_share = 1 - trend_share
        self.assertAlmostEqual(trend_share + dca_share, 1.0, places=9)
        self.assertGreater(trend_share, dca_share)


if __name__ == "__main__":
    unittest.main()

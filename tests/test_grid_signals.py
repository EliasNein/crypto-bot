"""
Direkte Tests der vier Entscheidungsfunktionen des Grid-Bots
(`dca_bot/grid_signals.py`) - Stufe 2 der Verbesserungsvorschlaege,
Grid-Haelfte von Punkt 12.

**Der Befund.** `compute_grid_levels`, `find_triggered_buy_levels`,
`is_sell_target_hit` und `is_trend_break_stop_loss_hit` hatten bis hierher
keinen einzigen direkten Test. Sie liefen ausschliesslich indirekt ueber
die Strategie-Tests mit - also immer nur an der einen Preislage, die der
jeweilige Testfall zufaellig brauchte, nie an einer absichtlich
konstruierten Kursreihe. Das ist dieselbe Lage, die W17 beim Trend-Bot
behoben hat (siehe tests/test_trend_decide_action.py, an dem sich diese
Datei in Stil und Aufbau orientiert).

**Warum ausgerechnet hier.** Genau in diesen Funktionen sassen die beiden
Designfehler, die vor Fertigstellung des Grid-Bots gefunden wurden (siehe
trading-bot-projekt.md Abschnitt 6):

1. **Kaltstart-Bug** - ein naiver Vergleich "Stufe liegt ueber dem
   aktuellen Preis" haette bei einem Start mitten im Grid sofort jede
   Stufe oberhalb gleichzeitig gekauft, nur weil sie dort liegt, nicht
   weil der Preis tatsaechlich gerade durch sie gefallen ist. Behoben
   durch die Crossing-Erkennung gegen den zuletzt beobachteten Preis.
2. **Intervallgrenzen-Fehler** - die Referenzstufe wurde doppelt
   gezaehlt. Behoben durch das halb-offene Intervall [price,
   last_seen_price).

Beide sind hier mit ihrer jeweiligen Gegenprobe abgedeckt: Ein Test der
Form "Situation X ergibt Ergebnis Y" ist auch dann gruen, wenn Situation X
in Wahrheit gar nicht vorlag - er prueft dann nichts. Deshalb belegt jeder
der beiden Faelle zusaetzlich, dass die konstruierte Preislage die
gemeinte Situation wirklich erzeugt.

Die Grid-Parameter sind bewusst klein und rund (100-120 bei 2 % Abstand,
10 Stufen), damit jede Stufe von Hand nachrechenbar bleibt - dieselbe
Ueberlegung wie die kurzen EMA-Perioden in test_trend_decide_action.py.
Die getestete LOGIK ist identisch zur Live-Konfiguration, nur die Zahlen
sind handhabbar.

Kein Netzwerk, keine Zugangsdaten, keine Dateien.

Ausfuehren mit:  python -m unittest tests.test_grid_signals -v
"""

from __future__ import annotations

import unittest

from dca_bot.grid_signals import (
    compute_grid_levels,
    find_triggered_buy_levels,
    is_sell_target_hit,
    is_trend_break_stop_loss_hit,
)


# --- Das Test-Grid ---------------------------------------------------------
#
# 100.00 bis 120.00 bei 2 % Abstand ergibt 10 Stufen:
#
#   0: 100.000000   5: 110.408080
#   1: 102.000000   6: 112.616242
#   2: 104.040000   7: 114.868567
#   3: 106.120800   8: 117.165938
#   4: 108.243216   9: 119.509257   <- reine Verkaufsstufe, nie Kaufstufe
#
# Kaufstufen sind also 0-8, die oberste Stufe 9 ist nur Verkaufsziel.
# Genau diese Asymmetrie ist die Grundlage der W16-Rechnung
# (max. Kapitalbindung = (Stufen - 1) x Betrag pro Stufe).

LOWER_LIMIT = 100.0
UPPER_LIMIT = 120.0
SPACING_PCT = 2.0

LEVELS = compute_grid_levels(LOWER_LIMIT, UPPER_LIMIT, SPACING_PCT)

# Index der obersten Stufe bzw. der obersten KAUFstufe.
TOP_LEVEL = len(LEVELS) - 1
TOP_BUY_LEVEL = TOP_LEVEL - 1


def naive_triggered_levels(levels: list[float], price: float) -> list[int]:
    """
    Der historische Kaltstart-Bug, nachgebaut: "kaufe jede Kaufstufe, die
    ueber dem aktuellen Preis liegt" - ohne jeden Bezug darauf, ob der
    Preis dort tatsaechlich gerade durchgefallen ist.

    Wird nicht getestet, sondern als MASSSTAB gebraucht: Er macht
    sichtbar, wie viele Stufen ein Kaltstart mitten im Grid frueher auf
    einen Schlag gekauft haette. Ohne diese Zahl waere die Zusicherung
    "der Kaltstart loest nichts aus" nicht von "an dieser Stelle gab es
    ohnehin nichts zu kaufen" zu unterscheiden.
    """
    return [i for i, level_price in enumerate(levels[:-1]) if level_price >= price]


class ComputeGridLevelsTestCase(unittest.TestCase):
    """`compute_grid_levels`: die geometrische Berechnung selbst."""

    def test_first_level_is_exactly_the_lower_limit(self):
        self.assertEqual(LEVELS[0], LOWER_LIMIT)

    def test_levels_are_geometric_not_linear(self):
        """
        Jede Stufe ist das `1 + spacing/100`-fache ihrer Vorgaengerin -
        NICHT ein fester Betrag darueber. Der Unterschied ist bei dieser
        Spanne deutlich sichtbar: geometrisch waechst der absolute
        Abstand von 2,00 (100 -> 102) auf 2,34 (117,17 -> 119,51).
        """
        factor = 1 + SPACING_PCT / 100
        for index in range(1, len(LEVELS)):
            with self.subTest(stufe=index):
                self.assertAlmostEqual(LEVELS[index], LEVELS[index - 1] * factor, places=9)

        # Gegenprobe zur Praemisse: Waere die Progression linear, waeren
        # alle absoluten Abstaende gleich. Sie sind es nachweislich nicht.
        first_gap = LEVELS[1] - LEVELS[0]
        last_gap = LEVELS[-1] - LEVELS[-2]
        self.assertGreater(last_gap, first_gap * 1.1)

    def test_level_count_matches_the_configured_range(self):
        self.assertEqual(len(LEVELS), 10)

    def test_levels_ascend_and_stay_within_the_configured_range(self):
        self.assertEqual(LEVELS, sorted(LEVELS))
        self.assertGreaterEqual(LEVELS[0], LOWER_LIMIT)
        self.assertLessEqual(LEVELS[-1], UPPER_LIMIT)

    def test_the_next_level_above_the_top_would_exceed_the_upper_limit(self):
        """
        Die Obergrenze ist wirklich ausgereizt: Eine weitere Stufe laege
        ueber `upper_limit`. Ohne diesen Test waere auch ein Grid gruen,
        das viel zu frueh aufhoert.
        """
        self.assertGreater(LEVELS[-1] * (1 + SPACING_PCT / 100), UPPER_LIMIT)

    def test_a_level_marginally_above_the_upper_limit_is_still_included(self):
        """
        Die Toleranz von 0,01 % in der Schleifenbedingung
        (`upper_limit * 1.0001`) ist beobachtbar und bewusst: Eine Stufe,
        die nur knapp ueber der Obergrenze liegt, faellt nicht durch
        Gleitkomma-Rundung weg.

        Hier liegt 102,00 ueber der Obergrenze 101,99 (um 0,0098 %) und
        wird trotzdem mitgenommen. Relevant, weil die Stufenzahl direkt
        in die maximale Kapitalbindung eingeht (W16).
        """
        levels = compute_grid_levels(100.0, 101.99, 2.0)
        self.assertEqual(levels, [100.0, 102.0])
        self.assertGreater(levels[-1], 101.99)

    # -- Ungueltige Parameter --

    def test_non_positive_lower_limit_is_rejected(self):
        for lower in (0.0, -1.0):
            with self.subTest(lower_limit=lower):
                with self.assertRaises(ValueError):
                    compute_grid_levels(lower, 120.0, 2.0)

    def test_upper_limit_not_above_lower_limit_is_rejected(self):
        for upper in (100.0, 90.0):
            with self.subTest(upper_limit=upper):
                with self.assertRaises(ValueError):
                    compute_grid_levels(100.0, upper, 2.0)

    def test_non_positive_spacing_is_rejected(self):
        """
        Ein Abstand von 0 waere eine Endlosschleife (die Stufe bliebe
        immer dieselbe), ein negativer eine absteigende Reihe.
        """
        for spacing in (0.0, -1.0):
            with self.subTest(spacing_pct=spacing):
                with self.assertRaises(ValueError):
                    compute_grid_levels(100.0, 120.0, spacing)

    def test_range_too_narrow_for_even_one_buy_level_is_rejected(self):
        """
        Bei 100-101 und 2 % Abstand passt keine zweite Stufe mehr hinein.
        Ein Grid aus einer einzigen Stufe haette keine Kaufstufe (die
        oberste ist reine Verkaufsstufe) und damit gar keine Funktion -
        deshalb ein Abbruch statt eines still funktionslosen Bots.
        """
        with self.assertRaises(ValueError):
            compute_grid_levels(100.0, 101.0, 2.0)


class FindTriggeredBuyLevelsTestCase(unittest.TestCase):
    """
    `find_triggered_buy_levels`: die Crossing-Erkennung - die Funktion, in
    der beide historischen Bugs sassen.
    """

    # -- Kaltstart (historischer Bug 1) --

    def test_a_cold_start_in_the_middle_of_the_grid_buys_nothing(self):
        """
        Der Kern des Kaltstart-Bugs: Der Bot startet neu, waehrend der
        Preis mitten im Grid steht. `last_seen_price` ist dann `None`, und
        es darf KEINE einzige Stufe ausgeloest werden - der Preis ist
        nirgends durchgefallen, er stand beim ersten Blick einfach dort.
        """
        self.assertEqual(find_triggered_buy_levels(LEVELS, None, 106.0, set()), [])

    def test_the_cold_start_situation_really_contains_levels_to_buy(self):
        """
        Die Praemisse des vorigen Tests, und der wichtigste Test dieser
        Datei: Bei einem Preis von 106,00 liegen SECHS Kaufstufen
        oberhalb - genau die, die der naive Vergleich auf einen Schlag
        gekauft haette.

        Ohne diesen Nachweis waere "der Kaltstart loest nichts aus" auch
        an einer Preislage gruen, an der ohnehin nichts zu kaufen gewesen
        waere. Der Test wuerde dann nichts belegen.
        """
        would_have_bought = naive_triggered_levels(LEVELS, 106.0)
        self.assertEqual(would_have_bought, [3, 4, 5, 6, 7, 8])
        self.assertEqual(len(would_have_bought), 6)

    def test_the_same_price_level_does_trigger_once_a_reference_price_exists(self):
        """
        Gegenprobe zum Kaltstart: DIESELBE Preislage (106,00), aber der
        Preis ist nachweislich von 119,00 dorthin gefallen. Jetzt loesen
        genau die sechs Stufen aus, die der Kaltstart oben verweigert hat.

        Damit steht fest, dass die leere Liste oben vom Kaltstart-Fall
        kommt und nicht davon, dass an dieser Stelle nichts zu kaufen war.
        Gleiches Muster wie die Schwellen-Gegenprobe bei W17.
        """
        triggered = find_triggered_buy_levels(LEVELS, 119.0, 106.0, set())
        self.assertEqual(triggered, [3, 4, 5, 6, 7, 8])
        self.assertEqual(triggered, naive_triggered_levels(LEVELS, 106.0))

    # -- Normaler Verlauf --

    def test_a_single_crossed_level_triggers_exactly_that_level(self):
        """Der Alltagsfall: Der Preis faellt um eine Stufe."""
        self.assertEqual(find_triggered_buy_levels(LEVELS, 111.0, 110.0, set()), [5])

    def test_a_rising_price_triggers_nothing(self):
        """
        Grid kauft beim FALLEN. Ein steigender Preis loest nie einen Kauf
        aus - er loest Verkaeufe aus, und die entscheidet
        `is_sell_target_hit` (siehe unten).
        """
        self.assertEqual(find_triggered_buy_levels(LEVELS, 104.0, 119.0, set()), [])

    def test_an_unchanged_price_triggers_nothing(self):
        """
        Der haeufigste Zyklus ueberhaupt: Der Preis hat sich seit dem
        letzten Blick nicht bewegt. Das halb-offene Intervall
        [price, last_seen_price) ist dann leer.
        """
        self.assertEqual(find_triggered_buy_levels(LEVELS, 110.0, 110.0, set()), [])

    # -- Crash: mehrere Stufen in einem Intervall --

    def test_a_crash_through_several_levels_buys_all_of_them(self):
        """
        Faellt der Preis in EINEM Intervall durch mehrere Stufen, werden
        alle tatsaechlich durchquerten gekauft - nicht nur die unterste.
        Der Live-Bot prueft alle fuenf Minuten, ein schneller Abverkauf
        ueberspringt in dieser Zeit ohne Weiteres mehrere Stufen.

        Das ist auch der Fall, fuer den der Notaus zwischen den einzelnen
        Kaeufen geprueft wird (W15, siehe grid_strategy._process_buys).
        """
        triggered = find_triggered_buy_levels(LEVELS, 119.0, 104.0, set())
        self.assertEqual(triggered, [2, 3, 4, 5, 6, 7, 8])

    def test_the_crash_interval_really_spans_several_levels(self):
        """
        Praemisse des vorigen Tests: Zwischen 104,00 und 119,00 liegen
        tatsaechlich sieben Kaufstufen. Sonst pruefte er nur, dass eine
        Handvoll Stufen zurueckkommt, ohne dass die Reihe je ein
        Crash-Szenario gewesen waere.
        """
        levels_in_span = [p for p in LEVELS[:-1] if 104.0 <= p < 119.0]
        self.assertEqual(len(levels_in_span), 7)

    def test_triggered_levels_come_back_in_ascending_order(self):
        """
        Die Reihenfolge ist nicht kosmetisch: `_process_buys` kauft in
        genau dieser Reihenfolge und prueft zwischen den Kaeufen den
        Notaus (W15). Bricht der Zyklus mittendrin ab, sind damit die
        untersten - also die guenstigsten - Stufen gekauft.
        """
        triggered = find_triggered_buy_levels(LEVELS, 119.0, 104.0, set())
        self.assertEqual(triggered, sorted(triggered))

    # -- Intervallgrenze (historischer Bug 2) --

    def test_the_reference_level_is_not_counted_twice(self):
        """
        Der Kern des Intervallgrenzen-Fehlers: Steht der Referenzpreis
        EXAKT auf einer Stufe, wurde diese Stufe frueher erneut gekauft -
        obwohl sie im vorherigen Zyklus bereits "gesehen" wurde.

        `last_seen_price` wird hier direkt aus `LEVELS[5]` entnommen und
        nicht als Literal geschrieben: Nur so gilt die Gleichheit bei
        Gleitkommazahlen per Konstruktion, statt von der Schreibweise
        einer gerundeten Zahl abzuhaengen.

        Der Fall zeigt beide Enden des halb-offenen Intervalls auf einmal:
        Stufe 5 (der alte Referenzpunkt) faellt heraus, Stufe 3 (der neue,
        aktuelle Preis) zaehlt mit.
        """
        triggered = find_triggered_buy_levels(LEVELS, LEVELS[5], LEVELS[3], set())
        self.assertEqual(triggered, [3, 4])
        self.assertNotIn(5, triggered)
        self.assertIn(3, triggered)

    def test_a_reference_price_a_hair_above_the_level_does_include_it(self):
        """
        Gegenprobe zur Intervallgrenze: Liegt der Referenzpreis nur
        minimal UEBER Stufe 5, gehoert sie sehr wohl ins Intervall und
        wird gekauft.

        Damit ist belegt, dass ihr Fehlen im vorigen Test von der
        Grenzregel kommt (`level_price >= last_seen_price` wird
        uebersprungen) und nicht davon, dass sie ohnehin ausserhalb der
        Spanne laege.
        """
        triggered = find_triggered_buy_levels(LEVELS, LEVELS[5] * 1.0000001, LEVELS[3], set())
        self.assertEqual(triggered, [3, 4, 5])

    def test_the_current_price_exactly_on_a_level_includes_that_level(self):
        """
        Das andere Ende derselben Regel, eigens geprueft: Der AKTUELLE
        Preis auf einer Stufe zaehlt mit (`level_price < price` wird
        uebersprungen, nicht `<=`). Der Preis ist ja gerade dort
        angekommen - das ist genau der Moment, in dem gekauft werden soll.
        """
        triggered = find_triggered_buy_levels(LEVELS, 111.0, LEVELS[4], set())
        self.assertIn(4, triggered)

    # -- Oberste Stufe ist keine Kaufstufe --

    def test_the_top_level_is_never_a_buy_level(self):
        """
        Die oberste Stufe ist reines Verkaufsziel. Geprueft wird das
        ueber das beobachtbare Verhalten und nicht durch Nachlesen von
        `levels[:-1]`: Selbst ein Durchlauf, der das gesamte Grid von
        oberhalb der obersten Stufe bis unter die unterste durchquert,
        gibt sie nicht zurueck.

        Diese eine Stufe Unterschied ist die Grundlage der W16-Rechnung:
        max. Kapitalbindung = (Anzahl Stufen - 1) x Betrag pro Stufe.
        """
        triggered = find_triggered_buy_levels(LEVELS, 125.0, 99.0, set())
        self.assertEqual(triggered, list(range(TOP_LEVEL)))
        self.assertNotIn(TOP_LEVEL, triggered)
        self.assertEqual(max(triggered), TOP_BUY_LEVEL)

    def test_a_full_sweep_yields_exactly_one_less_than_the_level_count(self):
        """Dieselbe Aussage als Zahl - so steht sie auch im Start-Log."""
        triggered = find_triggered_buy_levels(LEVELS, 125.0, 99.0, set())
        self.assertEqual(len(triggered), len(LEVELS) - 1)

    # -- Belegte Stufen --

    def test_occupied_levels_are_skipped(self):
        """
        Pro Stufe hoechstens eine offene Position. Eine Stufe, die bereits
        eine offene Position haelt, wird nicht erneut gekauft - sonst
        wuerde dieselbe Stufe bei jedem Hin und Her Kapital binden.
        """
        triggered = find_triggered_buy_levels(LEVELS, 119.0, 104.0, {3, 5})
        self.assertEqual(triggered, [2, 4, 6, 7, 8])

    def test_the_skipped_levels_would_otherwise_have_triggered(self):
        """
        Praemisse: Ohne die Belegung waeren Stufe 3 und 5 sehr wohl
        dabei. Sonst pruefte der vorige Test nur, dass zwei Stufen fehlen,
        die vielleicht ohnehin ausserhalb des Intervalls lagen.
        """
        without_occupancy = find_triggered_buy_levels(LEVELS, 119.0, 104.0, set())
        self.assertIn(3, without_occupancy)
        self.assertIn(5, without_occupancy)

    def test_a_fully_occupied_grid_triggers_nothing(self):
        """
        Die Obergrenze der Kapitalbindung, von der anderen Seite: Sind
        alle Kaufstufen belegt, kauft auch ein Durchlauf durch das ganze
        Grid nichts mehr dazu. Genau deshalb braucht der Grid-Bot kein
        Tageslimit (siehe grid_config.py).
        """
        all_buy_levels = set(range(len(LEVELS) - 1))
        self.assertEqual(
            find_triggered_buy_levels(LEVELS, 125.0, 99.0, all_buy_levels), []
        )


class IsSellTargetHitTestCase(unittest.TestCase):
    """`is_sell_target_hit`: das individuelle Verkaufsziel einer Position."""

    def test_price_above_the_target_hits(self):
        self.assertTrue(is_sell_target_hit(110.0, 108.243216))

    def test_price_below_the_target_does_not_hit(self):
        self.assertFalse(is_sell_target_hit(107.0, 108.243216))

    def test_price_exactly_on_the_target_hits(self):
        """
        Grenzfall: `>=`, nicht `>`. Der Zielpreis wird direkt aus
        `LEVELS[4]` genommen statt als gerundetes Literal geschrieben -
        so ist es wirklich der Wert, den der Bot als `target_sell_price`
        in die Position schreibt, und die Gleichheit haengt nicht an der
        Schreibweise.
        """
        target = LEVELS[4]
        self.assertTrue(is_sell_target_hit(target, target))

    def test_a_hair_below_the_target_does_not_hit(self):
        """
        Gegenprobe zum Grenzfall: Knapp darunter loest nicht aus. Ohne
        diesen Test waere auch ein `>=`, das faelschlich immer True
        liefert, gruen.
        """
        target = LEVELS[4]
        self.assertFalse(is_sell_target_hit(target * 0.9999999, target))

    def test_the_target_is_the_next_level_up_from_the_buy_level(self):
        """
        Praemisse der Faelle oben: So bildet der Bot das Ziel (siehe
        `_process_buys`, `target_sell_price=self._levels[level_index + 1]`).
        Der Gewinn einer Position ist damit per Konstruktion genau ein
        Stufenabstand - vor Gebuehren.
        """
        buy_level = 3
        target = LEVELS[buy_level + 1]
        self.assertAlmostEqual(target / LEVELS[buy_level], 1 + SPACING_PCT / 100, places=9)
        self.assertFalse(is_sell_target_hit(LEVELS[buy_level], target))
        self.assertTrue(is_sell_target_hit(target, target))


class IsTrendBreakStopLossHitTestCase(unittest.TestCase):
    """
    `is_trend_break_stop_loss_hit`: der Trendbruch-Stop-Loss relativ zur
    Grid-Untergrenze.

    Anders als der DCA-Stop-Loss (Kostenbasis der eigenen Kaeufe) haengt
    er ausschliesslich am Marktpreis gegenueber `lower_limit` - wie viele
    Positionen offen sind, spielt keine Rolle.
    """

    STOP_LOSS_PCT = 15.0
    # 100.0 * (1 - 15/100)
    THRESHOLD = 85.0

    def test_the_threshold_matches_the_documented_formula(self):
        """
        Praemisse aller folgenden Faelle: Die Schwelle ist wirklich
        `lower_limit * (1 - pct/100)`, nicht etwa ein Abschlag auf den
        aktuellen Preis. Das ist der Unterschied zwischen "der Markt ist
        unter das Grid gefallen" und "der Markt ist gerade gefallen".
        """
        self.assertEqual(LOWER_LIMIT * (1 - self.STOP_LOSS_PCT / 100), self.THRESHOLD)

    def test_price_clearly_below_the_threshold_triggers(self):
        self.assertTrue(
            is_trend_break_stop_loss_hit(LOWER_LIMIT, self.STOP_LOSS_PCT, 80.0)
        )

    def test_price_above_the_threshold_does_not_trigger(self):
        self.assertFalse(
            is_trend_break_stop_loss_hit(LOWER_LIMIT, self.STOP_LOSS_PCT, 90.0)
        )

    def test_price_below_the_lower_limit_but_above_the_threshold_does_not_trigger(self):
        """
        Der eigentlich interessante Bereich: Der Preis hat das Grid nach
        unten verlassen (95 < 100), aber der Puffer von 15 % ist noch
        nicht aufgebraucht. Das ist normaler Grid-Betrieb, kein
        Trendbruch - alle Kaufstufen sind dann belegt, und der Bot wartet
        auf die Erholung.
        """
        self.assertLess(95.0, LOWER_LIMIT)
        self.assertFalse(
            is_trend_break_stop_loss_hit(LOWER_LIMIT, self.STOP_LOSS_PCT, 95.0)
        )

    def test_price_exactly_on_the_threshold_does_not_trigger(self):
        """Grenzfall: `price < threshold`, nicht `<=`."""
        self.assertFalse(
            is_trend_break_stop_loss_hit(LOWER_LIMIT, self.STOP_LOSS_PCT, self.THRESHOLD)
        )

    def test_a_hair_below_the_threshold_triggers(self):
        """
        Gegenprobe zum Grenzfall - belegt, dass die Schwelle genau dort
        liegt und der vorige Test nicht aus einem anderen Grund gruen ist.
        """
        self.assertTrue(
            is_trend_break_stop_loss_hit(
                LOWER_LIMIT, self.STOP_LOSS_PCT, self.THRESHOLD * 0.9999999
            )
        )

    def test_zero_percent_disables_the_stop_loss(self):
        """
        `GRID_STOP_LOSS_PCT=0` ist ausdruecklich erlaubt und heisst
        "Stop-Loss aus" (siehe config_guard.py). Ohne die Sonderbehandlung
        laege die Schwelle bei `lower_limit * 1.0` - der Stop-Loss wuerde
        dann bei jedem Preis unterhalb der Grid-Untergrenze ausloesen,
        also im Normalbetrieb.
        """
        self.assertFalse(is_trend_break_stop_loss_hit(LOWER_LIMIT, 0.0, 1.0))

    def test_the_zero_case_would_otherwise_trigger_at_the_lower_limit(self):
        """
        Praemisse des vorigen Tests: Ohne die `pct <= 0`-Abkuerzung waere
        die Schwelle gleich der Untergrenze, und ein Preis knapp darunter
        haette ausgeloest. Genau davor schuetzt die Sonderbehandlung.
        """
        threshold_without_guard = LOWER_LIMIT * (1 - 0.0 / 100)
        self.assertEqual(threshold_without_guard, LOWER_LIMIT)
        self.assertLess(99.0, threshold_without_guard)

    def test_a_negative_percentage_also_disables_it(self):
        """
        Ein negativer Wert ergaebe eine Schwelle OBERHALB der
        Untergrenze - der Stop-Loss loeste dann mitten im normalen
        Grid-Betrieb aus. `config_guard.py` faengt das beim Start ab;
        hier bleibt die Funktion selbst auf der sicheren Seite.
        """
        self.assertFalse(is_trend_break_stop_loss_hit(LOWER_LIMIT, -15.0, 99.0))


if __name__ == "__main__":
    unittest.main()

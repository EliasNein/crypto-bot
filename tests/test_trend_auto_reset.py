"""
Tests fuer den ANALYSE-Modus "automatischer Stop-Loss-Reset"
(`--analyze-auto-reset` in dca_bot/trend_backtest.py) - Punkt 16 der
Verbesserungsvorschlaege aus Review-Abschnitt 7.

**Was hier NICHT passiert:** Der Live-Bot bekommt keinen automatischen
Reset. `TrendStopLoss` (trend_risk.py) bleibt unveraendert, der Latch
haelt weiterhin bis zum manuellen `python -m dca_bot.reset_trend_stop_loss`.
Getestet wird ausschliesslich der Backtest-Mechanismus, mit dem die Frage
"was haette ein Auto-Reset gebracht" beantwortet wurde.

**Warum ein Analyse-Modus ueberhaupt Tests bekommt.** Auf dieser Rechnung
soll eine Strategie-Entscheidung beruhen, und sie ist die einzige
Grundlage dafuer - anders als beim Live-Code faellt ein Fehler hier durch
nichts anderes auf. Dieselbe Ueberlegung wie bei Punkt 12: Die beiden
Designfehler des Grid-Bots sassen in genau solchen kleinen,
unscheinbaren Entscheidungsfunktionen.

Drei Aussagen sind die eigentliche Substanz:

1. **Die UND-Verknuepfung ist wirklich ein UND.** Zu einem ODER
   verrutscht waere es eine stille, im Ergebnis aber gravierende
   Aenderung - ein reines "Preis hat sich erholt" greift auch beim
   Ein-Tages-Sprung direkt nach dem Exit, also genau beim
   Dead-Cat-Bounce. Jede Bedingung wird deshalb einzeln als ALLEIN
   nicht ausreichend geprueft.
2. **Der Anker ist der Ausstiegskurs, nicht die rechnerische
   Stop-Schwelle.** Beide fallen oft zusammen; wo sie es nicht tun,
   entscheidet die Wahl ueber das Ergebnis.
3. **Die Einordnung eines Wiedereinstiegs als "falsch" haengt am
   Ausstiegsgrund, nicht am Vorzeichen der PnL.** Dazu gibt es die
   Gegenprobe mit einem Wiedereinstieg, der Verlust macht und trotzdem
   nicht als falsch zaehlt.

Preisreihen wie in tests/test_trend_decide_action.py: synthetisch, kurze
EMA-Perioden (3/5), von Hand nachrechenbar, identische Logik zum
Live-Betrieb.

Kein Netzwerk, keine Zugangsdaten, keine Dateien.

Ausfuehren mit:  python -m unittest tests.test_trend_auto_reset -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from dca_bot.trend_backtest import (
    AutoResetParams,
    _auto_reset_is_due,
    run_trend_backtest,
)
from dca_bot.trend_signals import TrendSignalGenerator


FAST_PERIOD = 3
SLOW_PERIOD = 5
MIN_GAP_PCT = 1.0
STOP_LOSS_PCT = 10.0
AMOUNT_PER_TRADE = 15.0

# Gebuehren bewusst auf 0: Sie sind in run_trend_backtest laengst
# abgedeckt und wuerden hier nur jede Zahl unrund machen, ohne an der
# getesteten Entscheidung etwas zu aendern.
FEE_PCT = 0.0

_BASE_DATE = datetime(2024, 1, 1)
START_DATE = _BASE_DATE.strftime("%Y-%m-%d")


# --- Preisreihen ----------------------------------------------------------
#
# Bausteine, aus denen die Faelle zusammengesetzt werden. Getrennt
# gehalten, damit in jedem Test sichtbar bleibt, welche Phase er braucht.

# Vorlauf plus bestaetigter Aufwaertstrend: Einstieg bei 106.00 (ab dort
# liegt der EMA-Abstand ueber MIN_GAP_PCT).
RISE = [100.0, 101.0, 102.0, 103.0, 104.0, 106.0, 109.0, 113.0, 118.0]
ENTRY_PRICE = 106.0

# Absturz unter die Stop-Schwelle (106.00 * 0.9 = 95.40). Der tatsaechliche
# Ausstieg liegt mit 90.00 DARUNTER - genau diese Luecke macht Test 2
# oben ueberhaupt erst pruefbar.
CRASH = [90.0]
STOP_EXIT_PRICE = 90.0
THEORETICAL_STOP_PRICE = ENTRY_PRICE * (1 - STOP_LOSS_PCT / 100)  # 95.40

# Erholung bis zu einem erneut bestaetigten Aufwaertstrend: Wiedereinstieg
# bei 112.00.
RECOVERY = [92.0, 97.0, 104.0, 112.0, 120.0]
REENTRY_PRICE = 112.0

# Nach dem Wiedereinstieg faellt der Kurs unter dessen Stop-Schwelle
# (112.00 * 0.9 = 100.80) - der Wiedereinstieg endet selbst im Stop-Loss.
SECOND_CRASH = [95.0]

# Nach dem Wiedereinstieg dreht der Trend bestaetigt nach unten, OHNE die
# Stop-Schwelle zu reissen: Ausstieg per Signal-Umkehr bei 102.00, also
# oberhalb von 100.80 - und mit Verlust gegenueber dem Einstieg zu 112.00.
SIGNAL_REVERSAL = [118.0, 110.0, 105.0, 102.0]
SIGNAL_EXIT_PRICE = 102.0

# Parameter, die in den Ablauf-Tests bewusst NICHT die bindende Bedingung
# sind - dort geht es um die Einordnung des Wiedereinstiegs, nicht um die
# Schwellen selbst (die haben ihre eigenen Tests weiter oben).
PERMISSIVE = AutoResetParams(recovery_threshold_pct=2.0, cooldown_days=3)


def make_klines(prices: list[float]) -> list[dict]:
    """
    Baut Tageskerzen im Format von `fetch_historical_klines` (backtest.py):
    ein Kalendertag je Preis, `open_time` als Millisekunden-Zeitstempel.

    `low_price` wird mitgeschrieben, obwohl run_trend_backtest es nicht
    liest - der echte Loader liefert es (es gehoert zur
    Stop-Limit-Analyse), und eine Kerze ohne dieses Feld waere eine
    stillschweigende Abweichung vom Produktivformat.
    """
    return [
        {
            "open_time": int((_BASE_DATE + timedelta(days=index)).timestamp() * 1000),
            "close_price": price,
            "low_price": price,
        }
        for index, price in enumerate(prices)
    ]


def run(prices: list[float], auto_reset: AutoResetParams | None = None):
    """Ein Backtest-Lauf mit den Testparametern - sonst unveraendert."""
    return run_trend_backtest(
        make_klines(prices),
        symbol="TESTUSDT",
        start_date=START_DATE,
        ema_fast_period=FAST_PERIOD,
        ema_slow_period=SLOW_PERIOD,
        min_gap_pct=MIN_GAP_PCT,
        amount_per_trade=AMOUNT_PER_TRADE,
        stop_loss_pct=STOP_LOSS_PCT,
        fee_pct=FEE_PCT,
        auto_reset=auto_reset,
    )


class PriceSeriesPremiseTestCase(unittest.TestCase):
    """
    Tun die Preisreihen, was ihr Name behauptet?

    Bewusst vor allen anderen Tests, aus demselben Grund wie in
    tests/test_trend_decide_action.py: Ein Test der Form "nach einem
    Stop-Loss passiert X" ist auch dann gruen, wenn es gar keinen
    Stop-Loss gab - er prueft dann nichts.
    """

    def test_rise_and_crash_produce_exactly_one_stop_loss_exit(self):
        result = run(RISE + CRASH)

        self.assertEqual(len(result.trade_log), 1)
        trade = result.trade_log[0]
        self.assertEqual(trade["exit_reason"], "stop_loss")
        self.assertEqual(trade["entry_price"], ENTRY_PRICE)
        self.assertEqual(trade["exit_price"], STOP_EXIT_PRICE)
        self.assertTrue(result.stop_loss_paused_at_end)

    def test_actual_exit_price_lies_below_the_theoretical_stop_threshold(self):
        """
        Praemisse des Anker-Tests: Ausstiegskurs (90.00) und rechnerische
        Schwelle (95.40) fallen hier NICHT zusammen. Waeren sie gleich,
        koennte kein Test unterscheiden, welcher von beiden als Anker
        dient.
        """
        self.assertLess(STOP_EXIT_PRICE, THEORETICAL_STOP_PRICE)

    def test_recovery_series_confirms_an_uptrend_again(self):
        """
        Praemisse aller Wiedereinstiegs-Tests: Ohne Latch waere hier ein
        neuer Einstieg faellig. Geprueft am Signalgenerator selbst - der
        Latch der Backtest-Schleife wuerde die Aussage sonst verdecken.
        """
        generator = TrendSignalGenerator(FAST_PERIOD, SLOW_PERIOD, MIN_GAP_PCT)
        states = [generator.feed(price) for price in RISE + CRASH + RECOVERY]
        self.assertEqual(states[-1]["confirmed_direction"], "up")

    def test_signal_reversal_series_exits_above_its_own_stop_threshold(self):
        """
        Praemisse des "richtiger Wiedereinstieg"-Tests: Der Ausstieg muss
        per SIGNAL erfolgen, nicht per Stop-Loss. Dafuer muss der
        Ausstiegskurs oberhalb der Stop-Schwelle des Wiedereinstiegs
        liegen - sonst haette die Stop-Loss-Pruefung Vorrang und der Test
        pruefte das Gegenteil dessen, was sein Name sagt.
        """
        reentry_stop_threshold = REENTRY_PRICE * (1 - STOP_LOSS_PCT / 100)
        self.assertGreater(SIGNAL_EXIT_PRICE, reentry_stop_threshold)
        # ... und er macht trotzdem Verlust - das ist der Punkt des Tests.
        self.assertLess(SIGNAL_EXIT_PRICE, REENTRY_PRICE)


class AutoResetConditionTestCase(unittest.TestCase):
    """
    `_auto_reset_is_due()` direkt - die UND-Verknuepfung ist die
    eigentliche Aussage des Experiments (siehe AutoResetParams).
    """

    # Die Zahlen sind bewusst so gewaehlt, dass `anchor * (1 + pct/100)`
    # in Fliesskomma EXAKT aufgeht: 25/100 = 0,25 und damit 1,25 sind
    # binaer exakt darstellbar, 100,00 * 1,25 ergibt glatt 125,00. Mit
    # den naheliegenderen 10 % waere es das nicht - 100,00 * 1,1 ergibt
    # 110.00000000000001, und ein Kurs von exakt 110,00 laege
    # rechnerisch DARUNTER. Der Vergleich in `_auto_reset_is_due` ist
    # eine gewoehnliche Fliesskomma-Rechnung, genau wie
    # `is_stop_loss_hit` und `is_trend_break_stop_loss_hit` im
    # Live-Code; fuer die Analyse ist ein Bruchteil eines Cents
    # bedeutungslos. Nur laesst sich "die Schwelle zaehlt inklusive"
    # eben nur an einem Zahlenpaar pruefen, das die Frage ueberhaupt
    # stellt - sonst prueft der Test ein Artefakt der Darstellung statt
    # des Vergleichsoperators.
    PARAMS = AutoResetParams(recovery_threshold_pct=25.0, cooldown_days=5)
    ANCHOR = 100.0
    RECOVERED = 125.0      # genau auf der Erholungsschwelle
    NOT_RECOVERED = 120.0  # erholt, aber nicht genug

    def test_both_conditions_met_releases_the_latch(self):
        self.assertTrue(
            _auto_reset_is_due(self.PARAMS, 5, self.ANCHOR, self.RECOVERED)
        )

    def test_cooldown_alone_is_not_enough(self):
        """Lange genug her, aber der Kurs hat sich nicht erholt."""
        self.assertFalse(
            _auto_reset_is_due(self.PARAMS, 99, self.ANCHOR, self.NOT_RECOVERED)
        )

    def test_recovery_alone_is_not_enough(self):
        """
        Erholt, aber noch im Cooldown - genau der Dead-Cat-Bounce, gegen
        den der Cooldown existiert.
        """
        self.assertFalse(
            _auto_reset_is_due(self.PARAMS, 1, self.ANCHOR, self.RECOVERED)
        )

    def test_neither_condition_met(self):
        self.assertFalse(
            _auto_reset_is_due(self.PARAMS, 1, self.ANCHOR, self.NOT_RECOVERED)
        )

    def test_an_or_instead_of_an_and_would_change_both_single_cases(self):
        """
        Die Gegenprobe, die die beiden Tests darueber erst scharf macht:
        Bei einer ODER-Verknuepfung waeren GENAU diese beiden Eingaben
        True. Dass sie False sind, ist also eine Aussage ueber die
        Verknuepfung - nicht darueber, dass die Eingaben ohnehin
        unzureichend waren.
        """
        cooldown_only = (99, self.ANCHOR, self.NOT_RECOVERED)
        recovery_only = (1, self.ANCHOR, self.RECOVERED)

        for days, anchor, price in (cooldown_only, recovery_only):
            with self.subTest(tage=days, preis=price):
                cooldown_ok = days >= self.PARAMS.cooldown_days
                recovery_ok = price >= anchor * (
                    1 + self.PARAMS.recovery_threshold_pct / 100
                )
                # Genau eine der beiden Bedingungen trifft zu ...
                self.assertNotEqual(cooldown_ok, recovery_ok)
                # ... ein ODER waere hier True, das UND ist es nicht.
                self.assertTrue(cooldown_ok or recovery_ok)
                self.assertFalse(_auto_reset_is_due(self.PARAMS, days, anchor, price))

    def test_both_thresholds_are_inclusive(self):
        """
        Exakt auf der Schwelle zaehlt - bei beiden Bedingungen. Ein
        `>` statt `>=` waere ein Off-by-one, der nur an genau diesem
        Punkt sichtbar wird.
        """
        self.assertTrue(
            _auto_reset_is_due(self.PARAMS, 5, self.ANCHOR, self.RECOVERED)
        )
        self.assertFalse(
            _auto_reset_is_due(self.PARAMS, 4, self.ANCHOR, self.RECOVERED)
        )

    def test_missing_anchor_never_releases(self):
        """
        Ohne Ausloesepreis gibt es keine Erholungsschwelle - dann wird
        bewusst nicht aufgehoben, statt die Bedingung als erfuellt
        durchgehen zu lassen.
        """
        self.assertFalse(_auto_reset_is_due(self.PARAMS, 99, None, 1_000_000.0))
        self.assertFalse(_auto_reset_is_due(self.PARAMS, 99, 0.0, 1_000_000.0))

    def test_anchor_is_the_exit_price_not_the_theoretical_stop_threshold(self):
        """
        Die zweite Kernaussage (siehe Modul-Docstring): Anker ist der
        Kurs, zu dem tatsaechlich ausgestiegen wurde.

        Hier auseinandergehalten am echten Zahlenpaar der Preisreihen
        oben: Einstieg 106.00, rechnerische Schwelle 95.40, tatsaechlicher
        Ausstieg 90.00. Ein Kurs von 100.00 liegt ueber der 10%-Erholung
        gegenueber 90.00 (= 99.00), aber unter der gegenueber 95.40
        (= 104.94). Genau dieser Kurs unterscheidet die beiden Varianten.
        """
        params = AutoResetParams(recovery_threshold_pct=10.0, cooldown_days=3)
        price_between = 100.0

        self.assertTrue(
            _auto_reset_is_due(params, 3, STOP_EXIT_PRICE, price_between)
        )
        # Gegenprobe: mit der rechnerischen Schwelle als Anker waere
        # derselbe Kurs zu wenig.
        self.assertFalse(
            _auto_reset_is_due(params, 3, THEORETICAL_STOP_PRICE, price_between)
        )

    def test_the_backtest_loop_really_passes_the_exit_price_as_anchor(self):
        """
        Derselbe Punkt, aber eine Ebene hoeher - und das ist hier kein
        Doppel, sondern die eigentliche Absicherung: Der Test darueber
        prueft die FUNKTION, dieser die VERDRAHTUNG. Reicht die
        Backtest-Schleife den falschen Wert als Anker herein, rechnet die
        Funktion weiterhin korrekt, nur eben mit der falschen Zahl - und
        der Test darueber bliebe gruen. Genau diese Luecke ist in Stufe 2
        der Verbesserungsvorschlaege schon einmal aufgetreten (siehe die
        Notiz zur zuerst falschen Wirksamkeitsmessung in
        trading-bot-projekt.md 6i).

        Unterschieden wird ueber eine Erholungsschwelle von 30 %, die
        genau zwischen den beiden Kandidaten liegt:
          - Anker Ausstiegskurs 90,00  -> Schwelle 117,00, die Reihe
            erreicht 120,00 -> Reset faellt, Wiedereinstieg.
          - Anker Stop-Schwelle 95,40  -> Schwelle 124,02, unerreichbar
            -> kein Reset, kein Wiedereinstieg.
        """
        result = run(
            RISE + CRASH + RECOVERY,
            auto_reset=AutoResetParams(recovery_threshold_pct=30.0, cooldown_days=3),
        )

        self.assertEqual(result.auto_reset_stats.num_auto_resets, 1)
        self.assertEqual(result.auto_reset_stats.num_reentries, 1)

        # Die Praemisse dazu, damit der Test nicht aus einem anderen
        # Grund gruen ist: Mit der rechnerischen Schwelle als Anker laege
        # der hoechste Kurs der Reihe unter der 30%-Marke.
        highest_price = max(RISE + CRASH + RECOVERY)
        self.assertGreaterEqual(highest_price, STOP_EXIT_PRICE * 1.30)
        self.assertLess(highest_price, THEORETICAL_STOP_PRICE * 1.30)


class AutoResetIsOptOnlyTestCase(unittest.TestCase):
    """
    Der Modus darf ausserhalb seiner selbst nichts veraendern - sonst
    waere der Referenzwert "ohne Auto-Reset" keiner mehr.
    """

    def test_without_auto_reset_the_latch_holds_until_the_end(self):
        """Negativkontrolle: unveraendertes Live-Verhalten."""
        result = run(RISE + CRASH + RECOVERY)

        self.assertIsNone(result.auto_reset_stats)
        self.assertTrue(result.stop_loss_paused_at_end)
        self.assertEqual(len(result.trade_log), 1)
        self.assertIsNone(result.open_position_unrealized_pnl)

    def test_with_auto_reset_the_very_same_series_re_enters(self):
        """
        Gegenprobe dazu: Dass oben nichts passiert, liegt am Latch - nicht
        daran, dass die Reihe kein Signal mehr hergeben wuerde.
        """
        result = run(RISE + CRASH + RECOVERY, auto_reset=PERMISSIVE)

        self.assertEqual(result.auto_reset_stats.num_auto_resets, 1)
        self.assertEqual(result.auto_reset_stats.num_reentries, 1)
        self.assertFalse(result.stop_loss_paused_at_end)
        self.assertIsNotNone(result.open_position_unrealized_pnl)

    def test_combining_both_reset_modes_is_rejected(self):
        """
        Zwei konkurrierende Regeln fuer denselben Latch - das Ergebnis
        waere keiner von beiden zuzuordnen (siehe run_trend_backtest).
        """
        with self.assertRaises(ValueError) as ctx:
            run_trend_backtest(
                make_klines(RISE + CRASH + RECOVERY),
                symbol="TESTUSDT",
                start_date=START_DATE,
                ema_fast_period=FAST_PERIOD,
                ema_slow_period=SLOW_PERIOD,
                min_gap_pct=MIN_GAP_PCT,
                amount_per_trade=AMOUNT_PER_TRADE,
                stop_loss_pct=STOP_LOSS_PCT,
                fee_pct=FEE_PCT,
                reset_cooldown_days=14,
                auto_reset=PERMISSIVE,
            )
        self.assertIn("schließen sich aus", str(ctx.exception))

    def test_the_older_periodic_reset_mode_still_works_unchanged(self):
        """
        Der bestehende `reset_cooldown_days`-Pfad ist die Grundlage der
        bereits dokumentierten Zahl in trading-bot-projekt.md Abschnitt 6.
        Er darf durch den neuen Modus nicht beruehrt worden sein.
        """
        result = run_trend_backtest(
            make_klines(RISE + CRASH + RECOVERY),
            symbol="TESTUSDT",
            start_date=START_DATE,
            ema_fast_period=FAST_PERIOD,
            ema_slow_period=SLOW_PERIOD,
            min_gap_pct=MIN_GAP_PCT,
            amount_per_trade=AMOUNT_PER_TRADE,
            stop_loss_pct=STOP_LOSS_PCT,
            fee_pct=FEE_PCT,
            reset_cooldown_days=3,
        )

        self.assertIsNone(result.auto_reset_stats)
        self.assertFalse(result.stop_loss_paused_at_end)
        # Der rein zeitliche Reset laesst denselben Wiedereinstieg zu.
        self.assertIsNotNone(result.open_position_unrealized_pnl)


class ReentryClassificationTestCase(unittest.TestCase):
    """
    Die dritte Kernaussage: Wann gilt ein Wiedereinstieg als "falsch"?

    Definition (siehe AutoResetStats): wenn er selbst wieder im Stop-Loss
    endet. Nicht: wenn er Verlust macht.
    """

    def test_first_trade_is_never_counted_as_a_reentry(self):
        """
        Der Einstieg VOR dem ersten Stop-Loss haette auch ohne Auto-Reset
        stattgefunden - er darf dem Mechanismus nicht zugerechnet werden.
        """
        result = run(RISE + CRASH, auto_reset=PERMISSIVE)

        self.assertEqual(len(result.trade_log), 1)
        self.assertFalse(result.trade_log[0]["is_reentry"])
        self.assertEqual(result.auto_reset_stats.num_reentries, 0)

    def test_reentry_that_is_stopped_out_again_counts_as_wrong(self):
        """Der Whipsaw-Fall, um den es bei der Latch-Frage geht."""
        result = run(RISE + CRASH + RECOVERY + SECOND_CRASH, auto_reset=PERMISSIVE)
        stats = result.auto_reset_stats

        self.assertEqual(stats.num_reentries, 1)
        self.assertEqual(stats.num_reentries_stopped_out, 1)
        self.assertEqual(stats.num_reentries_exited_by_signal, 0)
        self.assertEqual(stats.num_reentries_still_open, 0)

        reentry = result.trade_log[1]
        self.assertTrue(reentry["is_reentry"])
        self.assertEqual(reentry["exit_reason"], "stop_loss")
        self.assertEqual(reentry["entry_price"], REENTRY_PRICE)

    def test_reentry_exited_by_signal_is_not_wrong_even_at_a_loss(self):
        """
        Die Gegenprobe, auf die es ankommt: Dieser Wiedereinstieg macht
        VERLUST (112.00 -> 102.00) und zaehlt trotzdem nicht als falsch.
        Er ist per Signal-Umkehr geschlossen worden, hat sich also als
        Entscheidung bewaehrt - der Bot ist nicht in einen weiterlaufenden
        Abwaertstrend hineingelaufen, sondern regulaer wieder ausgestiegen.

        Waere "falsch" ueber das Vorzeichen der PnL definiert, faellt
        genau dieser Test um.
        """
        result = run(RISE + CRASH + RECOVERY + SIGNAL_REVERSAL, auto_reset=PERMISSIVE)
        stats = result.auto_reset_stats

        reentry = result.trade_log[1]
        self.assertTrue(reentry["is_reentry"])
        self.assertEqual(reentry["exit_reason"], "signal")
        self.assertLess(reentry["pnl"], 0)  # Verlust ...

        self.assertEqual(stats.num_reentries, 1)
        self.assertEqual(stats.num_reentries_stopped_out, 0)  # ... aber nicht falsch
        self.assertEqual(stats.num_reentries_exited_by_signal, 1)

    def test_reentry_still_open_at_the_end_is_counted_separately(self):
        """
        Ein Wiedereinstieg ohne Ausgang wird weder als falsch noch als
        bestaetigt gezaehlt - die Daten geben dazu nichts her.
        """
        result = run(RISE + CRASH + RECOVERY, auto_reset=PERMISSIVE)
        stats = result.auto_reset_stats

        self.assertEqual(stats.num_reentries, 1)
        self.assertEqual(stats.num_reentries_still_open, 1)
        self.assertEqual(stats.num_reentries_stopped_out, 0)
        self.assertEqual(stats.num_reentries_exited_by_signal, 0)

    def test_the_three_outcome_counters_always_add_up(self):
        """
        Jeder Wiedereinstieg hat genau einen der drei Ausgaenge. Geht die
        Summe nicht auf, faellt ein Fall unter den Tisch - und die Spalte
        "davon falsch" waere gegen eine falsche Grundgesamtheit gerechnet.
        """
        cases = {
            "offen am Ende": RISE + CRASH + RECOVERY,
            "erneuter Stop-Loss": RISE + CRASH + RECOVERY + SECOND_CRASH,
            "Signal-Umkehr": RISE + CRASH + RECOVERY + SIGNAL_REVERSAL,
        }
        for name, prices in cases.items():
            with self.subTest(fall=name):
                stats = run(prices, auto_reset=PERMISSIVE).auto_reset_stats
                self.assertEqual(
                    stats.num_reentries,
                    stats.num_reentries_stopped_out
                    + stats.num_reentries_exited_by_signal
                    + stats.num_reentries_still_open,
                )


class AutoResetBlockingTestCase(unittest.TestCase):
    """
    Beide Bedingungen noch einmal im vollstaendigen Ablauf statt nur an
    der reinen Funktion - eine richtig verdrahtete Bedingung ist etwas
    anderes als eine richtig gerechnete.
    """

    def test_cooldown_that_outlasts_the_period_prevents_every_reentry(self):
        result = run(
            RISE + CRASH + RECOVERY,
            auto_reset=AutoResetParams(recovery_threshold_pct=2.0, cooldown_days=99),
        )

        self.assertEqual(result.auto_reset_stats.num_auto_resets, 0)
        self.assertEqual(result.auto_reset_stats.num_reentries, 0)
        self.assertTrue(result.stop_loss_paused_at_end)

    def test_recovery_threshold_that_is_never_reached_prevents_every_reentry(self):
        result = run(
            RISE + CRASH + RECOVERY,
            auto_reset=AutoResetParams(recovery_threshold_pct=60.0, cooldown_days=3),
        )

        self.assertEqual(result.auto_reset_stats.num_auto_resets, 0)
        self.assertEqual(result.auto_reset_stats.num_reentries, 0)
        self.assertTrue(result.stop_loss_paused_at_end)

    def test_both_blocking_runs_match_the_reference_exactly(self):
        """
        Wird der Latch nie aufgehoben, muss das Ergebnis Zeichen fuer
        Zeichen dem Lauf ohne Auto-Reset entsprechen. Sonst haette der
        Analyse-Modus einen Nebeneffekt - und die Spalte "ohne
        Auto-Reset" waere kein Referenzwert mehr.
        """
        reference = run(RISE + CRASH + RECOVERY)
        for params in (
            AutoResetParams(recovery_threshold_pct=2.0, cooldown_days=99),
            AutoResetParams(recovery_threshold_pct=60.0, cooldown_days=3),
        ):
            with self.subTest(params=params):
                blocked = run(RISE + CRASH + RECOVERY, auto_reset=params)
                self.assertEqual(blocked.total_pnl, reference.total_pnl)
                self.assertEqual(blocked.num_trades, reference.num_trades)
                self.assertEqual(
                    blocked.open_position_unrealized_pnl,
                    reference.open_position_unrealized_pnl,
                )
                self.assertEqual(
                    blocked.stop_loss_paused_at_end, reference.stop_loss_paused_at_end
                )


if __name__ == "__main__":
    unittest.main()

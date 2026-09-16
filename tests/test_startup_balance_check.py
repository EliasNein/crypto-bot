"""
Tests fuer den Konsistenz-Check beim Bot-Start (Stufe 2 der
Verbesserungsvorschlaege, Punkt 3 in modifizierter Form - Teil A).

Geprueft wird `dca_bot/startup_checks.py` samt den drei
`check_balance_on_startup()`-Methoden, die ihn fuettern - fuer alle drei
Bots in einer Datei, weil es genau derselbe Mechanismus mit drei
unterschiedlich aufgebauten Ledgern ist (gleiches Vorgehen wie
tests/test_order_reconciliation.py, das den Startpfad ebenfalls fuer alle
drei buendelt).

**Was hier NICHT noch einmal geprueft wird:** die Bewertungslogik selbst
(`ledger_exceeds_account`, `build_snapshot`, `split_locked_quantity`,
`tolerance_for`). Die steht seit W11 in tests/test_stage_c_safety.py.
Hier geht es um die Frage davor und danach: Bekommt sie beim Start
ueberhaupt die richtigen Zahlen, und was passiert mit dem Ergebnis?

Drei Eigenschaften sind dabei die eigentliche Aussage:

1. **Der Check blockiert nie.** Er meldet laut und kehrt zurueck - ein
   Bot, der wegen eines Buchhaltungsverdachts nicht startet, kann auch
   keine offenen Positionen mehr absichern oder schliessen.
2. **Ohne echte Menge kostet er nichts.** Kein einziger API-Aufruf, wenn
   das Ledger keine echten offenen Mengen fuehrt - belegt ueber die
   Aufrufzaehler des Fakes, nicht behauptet.
3. **Die eigene Stop-Loss-Order des Trend-Bots loest keinen Fehlalarm
   aus.** Sie bindet die komplette Positionsmenge; nur weil sie das
   `trend-`Praefix traegt, zaehlt sie in `own_locked`. Dazu gibt es die
   Gegenprobe mit einer fremden Order.

Kein Netzwerk, keine Zugangsdaten, temporaere Dateien.

Ausfuehren mit:  python -m unittest tests.test_startup_balance_check -v
"""

from __future__ import annotations

import inspect
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from dca_bot.config import Config
from dca_bot.grid_config import GridConfig
from dca_bot.grid_risk import GridPosition
from dca_bot.grid_strategy import GridTradingStrategy
from dca_bot.order_utils import SymbolTradingRules
from dca_bot.risk import TradeLedger, TradeRecord
from dca_bot.strategy import DCAStrategy
from dca_bot.trend_config import TrendConfig
from dca_bot.trend_risk import TrendTrade
from dca_bot.trend_strategy import TrendFollowingStrategy


FAKE_TRADING_RULES = SymbolTradingRules(
    symbol="BTCUSDT",
    tick_size=0.01,
    step_size=0.00001,
    min_notional=5.0,
    base_asset="BTC",
    quote_asset="USDT",
    quote_precision=8,
)

# Testmenge und die daraus folgende Toleranz der weichen Pruefung:
#   tolerance_for(0.5, 0.00001) = max(2 * 0.00001, 0.5 * 0.001) = 0.0005
# Eine Diskrepanz wird also gemeldet, sobald
#   own_upper_bound + 0.0005 < 0.5, also own_upper_bound < 0.4995.
LEDGER_QUANTITY = 0.5
TOLERANCE = 0.0005
COVERED_BALANCE = 1.0      # deutlich mehr als das Ledger beansprucht
UNCOVERED_BALANCE = 0.1    # deutlich weniger


class FakeAccountClient:
    """
    Minimal-Fake fuer genau die drei Methoden, die der Start-Check
    benutzt. Bewusst EIN Fake fuer alle drei Bots: Der gepruefte Pfad ist
    derselbe, nur die Ledger davor unterscheiden sich - ein je Bot
    eigener Fake wuerde hier nur dreimal dasselbe behaupten.

    Die Zaehler sind Teil der Aussage: Ohne echte offene Menge darf keine
    dieser Methoden ueberhaupt aufgerufen werden.
    """

    def __init__(
        self,
        free: float = COVERED_BALANCE,
        locked: float = 0.0,
        open_orders: list[dict] | None = None,
    ):
        self.base_balance: tuple[float, float] | None = (free, locked)
        self.open_orders: list[dict] | None = open_orders if open_orders is not None else []
        self.rules_calls = 0
        self.balance_calls = 0
        self.open_orders_calls = 0
        self.force_trading_rules_failure = False

    def get_symbol_trading_rules(self, symbol: str) -> SymbolTradingRules:
        self.rules_calls += 1
        if self.force_trading_rules_failure:
            raise RuntimeError("exchangeInfo nicht erreichbar (Testfall)")
        return FAKE_TRADING_RULES

    def get_asset_balance(self, asset: str) -> tuple[float, float] | None:
        self.balance_calls += 1
        return self.base_balance

    def get_open_orders(self, symbol: str) -> list[dict] | None:
        self.open_orders_calls += 1
        return self.open_orders

    @property
    def api_calls(self) -> int:
        return self.rules_calls + self.balance_calls + self.open_orders_calls


def sell_order(client_order_id: str, quantity: float, status: str = "NEW") -> dict:
    """Eine offene Verkaufs-Order, wie `get_open_orders()` sie liefert."""
    return {
        "clientOrderId": client_order_id,
        "side": "SELL",
        "status": status,
        "origQty": quantity,
        "executedQty": 0.0,
    }


class StartupCheckTestBase(unittest.TestCase):
    """
    Gemeinsame Umgebung: temporaere Zustandsdateien plus je eine Fabrik
    pro Bot. Enthaelt bewusst KEINE eigenen Testmethoden - erbte eine
    Testklasse direkt von einer anderen, liefen deren Tests doppelt
    (gleiche Ueberlegung wie GridStrategyTestBase).
    """

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)
        # Telegram darf in keinem dieser Tests tatsaechlich feuern.
        for module in ("dca_bot.startup_checks",):
            patcher = mock.patch(f"{module}.send_notification")
            self.notify = patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _path(self, name: str) -> str:
        return str(self.tmp_path / name)

    # -- DCA --

    def _dca(self, client: FakeAccountClient, trading_enabled: bool = True):
        config = Config(
            api_key="test",
            api_secret="test",
            symbol="BTCUSDT",
            trading_enabled=trading_enabled,
            kill_switch_file=self._path("STOP_UNUSED"),
            state_file=self._path("trade_ledger.json"),
            stop_loss_state_file=self._path("stop_loss_paused.json"),
        )
        return DCAStrategy(config, client)

    def _add_dca_buy(self, strategy, quantity: float, dry_run: bool, symbol: str = "BTCUSDT"):
        strategy._ledger.record(
            TradeRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                symbol=symbol,
                quote_spent=quantity * 50_000.0,
                quantity=quantity,
                price=50_000.0,
                dry_run=dry_run,
            )
        )

    # -- Grid --

    def _grid(self, client: FakeAccountClient, trading_enabled: bool = True):
        config = GridConfig(
            api_key="test",
            api_secret="test",
            symbol="BTCUSDT",
            lower_limit=70_000.0,
            upper_limit=90_000.0,
            grid_spacing_pct=1.5,
            amount_per_level=15.0,
            trading_enabled=trading_enabled,
            kill_switch_file=self._path("STOP_GRID_UNUSED"),
            state_file=self._path("grid_positions.json"),
            stop_loss_state_file=self._path("grid_stop_loss_paused.json"),
        )
        return GridTradingStrategy(config, client)

    def _add_grid_position(self, strategy, quantity: float, dry_run: bool, level_index: int = 3):
        strategy._ledger.record_buy(
            GridPosition.new(
                level_index=level_index,
                buy_price=77_000.0,
                target_sell_price=78_000.0,
                quantity=quantity,
                quote_spent=15.0,
                dry_run=dry_run,
            )
        )

    # -- Trend --

    def _trend(self, client: FakeAccountClient, trading_enabled: bool = True):
        config = TrendConfig(
            api_key="test",
            api_secret="test",
            symbol="BTCUSDT",
            trading_enabled=trading_enabled,
            kill_switch_file=self._path("STOP_TREND_UNUSED"),
            state_file=self._path("trend_ledger.json"),
            stop_loss_state_file=self._path("trend_stop_loss_paused.json"),
        )
        return TrendFollowingStrategy(config, client)

    def _add_trend_position(self, strategy, quantity: float, dry_run: bool):
        strategy._ledger.record_entry(
            TrendTrade.new(
                entry_price=50_000.0,
                quantity=quantity,
                quote_spent=quantity * 50_000.0,
                dry_run=dry_run,
            )
        )

    # -- Hilfen --

    def _run(self, strategy, logger_name: str) -> list[str]:
        """Fuehrt den Check aus und gibt die Logzeilen zurueck."""
        with self.assertLogs(logger_name, level="INFO") as captured:
            strategy.check_balance_on_startup()
        return captured.output

    def assertReportedDiscrepancy(self, lines: list[str], marker: str) -> None:
        hits = [line for line in lines if marker in line]
        self.assertEqual(len(hits), 1, f"Genau eine {marker}-Zeile erwartet: {lines}")
        self.assertTrue(self.notify.called, "Eine Diskrepanz muss auch per Telegram gehen")

    def assertNoDiscrepancy(self, lines: list[str]) -> None:
        self.assertEqual(
            [line for line in lines if "DISKREPANZ" in line], [], f"Kein Befund erwartet: {lines}"
        )
        self.assertFalse(self.notify.called, "Ohne Befund darf keine Telegram-Nachricht gehen")


class DCAStartupCheckTestCase(StartupCheckTestBase):
    """
    Der DCA-Bot - der eigentliche Neuzugang. Er verkauft nie und hatte
    deshalb bis hierher ueberhaupt keinen Moment, in dem seine
    Buchhaltung je gegen die Realitaet gehalten wurde.
    """

    def test_a_covered_ledger_reports_nothing(self):
        client = FakeAccountClient(free=COVERED_BALANCE)
        strategy = self._dca(client)
        self._add_dca_buy(strategy, LEDGER_QUANTITY, dry_run=False)

        self.assertNoDiscrepancy(self._run(strategy, "dca_bot"))

    def test_an_uncovered_ledger_warns_loudly(self):
        client = FakeAccountClient(free=UNCOVERED_BALANCE)
        strategy = self._dca(client)
        self._add_dca_buy(strategy, LEDGER_QUANTITY, dry_run=False)

        lines = self._run(strategy, "dca_bot")
        self.assertReportedDiscrepancy(lines, "[BESTAND-DISKREPANZ]")

    def test_the_warning_never_blocks_the_start(self):
        """
        Die zentrale Zusicherung: laut, aber nicht blockierend. Der Check
        wirft nicht und gibt normal zurueck - der Bot startet weiter.
        """
        client = FakeAccountClient(free=UNCOVERED_BALANCE)
        strategy = self._dca(client)
        self._add_dca_buy(strategy, LEDGER_QUANTITY, dry_run=False)

        # assertLogs auch hier, obwohl die Zeilen nicht geprueft werden:
        # sonst landet die ERROR-Zeile im Testprotokoll und sieht dort wie
        # ein Fehlschlag aus.
        with self.assertLogs("dca_bot", level="INFO"):
            self.assertIsNone(strategy.check_balance_on_startup())

    def test_several_buys_are_added_up(self):
        """
        Das DCA-Ledger ist append-only ohne Status: Der Bot verkauft nie,
        also ist die Summe ALLER echten Kaeufe der aktuelle Bestand.
        Drei Kaeufe zu 0,2 ergeben 0,6 - mehr als die 0,5 auf dem Konto.
        """
        client = FakeAccountClient(free=LEDGER_QUANTITY)
        strategy = self._dca(client)
        for _ in range(3):
            self._add_dca_buy(strategy, 0.2, dry_run=False)

        self.assertReportedDiscrepancy(
            self._run(strategy, "dca_bot"), "[BESTAND-DISKREPANZ]"
        )

    def test_a_single_one_of_those_buys_would_be_covered(self):
        """
        Praemisse des vorigen Tests: Ein einzelner Kauf ueber 0,2 waere
        von den 0,5 auf dem Konto gedeckt. Der Befund kommt also von der
        Summenbildung und nicht davon, dass der Kontostand ohnehin zu
        niedrig war.
        """
        client = FakeAccountClient(free=LEDGER_QUANTITY)
        strategy = self._dca(client)
        self._add_dca_buy(strategy, 0.2, dry_run=False)

        self.assertNoDiscrepancy(self._run(strategy, "dca_bot"))

    def test_dry_run_buys_do_not_count(self):
        """
        Simulierte Kaeufe existieren an der Boerse nicht und begruenden
        keinen Anspruch auf echtes Guthaben (K4). `TradeLedger.position()`
        filtert sie bereits - hier ist belegt, dass der Check diesen Weg
        wirklich nimmt.
        """
        client = FakeAccountClient(free=UNCOVERED_BALANCE)
        strategy = self._dca(client)
        self._add_dca_buy(strategy, LEDGER_QUANTITY, dry_run=True)

        self.assertNoDiscrepancy(self._run(strategy, "dca_bot"))
        self.assertEqual(client.api_calls, 0, "Ohne echte Menge kein API-Aufruf")

    def test_buys_of_another_symbol_do_not_count(self):
        """
        `position()` filtert nach Symbol. Ein Bestand in einem anderen
        Paar hat mit dem Base-Asset dieses Symbols nichts zu tun.
        """
        client = FakeAccountClient(free=UNCOVERED_BALANCE)
        strategy = self._dca(client)
        self._add_dca_buy(strategy, LEDGER_QUANTITY, dry_run=False, symbol="ETHUSDT")

        self.assertNoDiscrepancy(self._run(strategy, "dca_bot"))

    def test_an_empty_ledger_costs_no_api_call(self):
        client = FakeAccountClient()
        strategy = self._dca(client)

        self.assertNoDiscrepancy(self._run(strategy, "dca_bot"))
        self.assertEqual(client.api_calls, 0)

    def test_the_check_runs_even_in_dry_run_mode_when_real_holdings_exist(self):
        """
        Der bewusste Unterschied zum Verkaufspfad: Dort schaltet der
        Dry-Run die Pruefung ab, weil ein simulierter Verkauf gar keine
        Order platziert. Hier ist das Gate die MENGE. Ein auf Dry-Run
        zurueckgestellter Bot mit echtem Altbestand ist gerade der
        interessante Fall - die Assets liegen weiterhin an der Boerse.
        """
        client = FakeAccountClient(free=UNCOVERED_BALANCE)
        strategy = self._dca(client, trading_enabled=False)
        self._add_dca_buy(strategy, LEDGER_QUANTITY, dry_run=False)

        self.assertReportedDiscrepancy(
            self._run(strategy, "dca_bot"), "[BESTAND-DISKREPANZ]"
        )


class GridStartupCheckTestCase(StartupCheckTestBase):
    """
    Der Grid-Bot. Ergaenzt `_warn_on_ledger_mismatch()`, das nur in einem
    Zyklus laeuft, in dem ueberhaupt ein Verkaufsziel erreicht ist.
    """

    def test_a_covered_ledger_reports_nothing(self):
        client = FakeAccountClient(free=COVERED_BALANCE)
        strategy = self._grid(client)
        self._add_grid_position(strategy, LEDGER_QUANTITY, dry_run=False)

        self.assertNoDiscrepancy(self._run(strategy, "grid_bot"))

    def test_an_uncovered_ledger_warns_loudly(self):
        client = FakeAccountClient(free=UNCOVERED_BALANCE)
        strategy = self._grid(client)
        self._add_grid_position(strategy, LEDGER_QUANTITY, dry_run=False)

        self.assertReportedDiscrepancy(
            self._run(strategy, "grid_bot"), "[GRID-BESTAND-DISKREPANZ]"
        )

    def test_all_open_levels_are_added_up(self):
        """
        Der Grid-Bot haelt viele Positionen gleichzeitig - genau das ist
        seine Kapitalbindung (W16). Fuenf Stufen zu 0,2 ergeben 1,0, mehr
        als die 0,5 auf dem Konto.
        """
        client = FakeAccountClient(free=LEDGER_QUANTITY)
        strategy = self._grid(client)
        for level in range(5):
            self._add_grid_position(strategy, 0.2, dry_run=False, level_index=level)

        self.assertReportedDiscrepancy(
            self._run(strategy, "grid_bot"), "[GRID-BESTAND-DISKREPANZ]"
        )

    def test_closed_positions_do_not_count(self):
        """
        Eine verkaufte Position bleibt als Historie im Ledger stehen
        (`status: closed`), beansprucht aber kein Guthaben mehr.
        """
        client = FakeAccountClient(free=UNCOVERED_BALANCE)
        strategy = self._grid(client)
        self._add_grid_position(strategy, LEDGER_QUANTITY, dry_run=False)
        position = strategy._ledger.open_positions()[0]
        strategy._ledger.record_sell(
            position["id"], 78_000.0, datetime.now(timezone.utc).isoformat(), 1.0
        )

        self.assertNoDiscrepancy(self._run(strategy, "grid_bot"))
        self.assertEqual(client.api_calls, 0)

    def test_dry_run_positions_do_not_count(self):
        client = FakeAccountClient(free=UNCOVERED_BALANCE)
        strategy = self._grid(client)
        self._add_grid_position(strategy, LEDGER_QUANTITY, dry_run=True)

        self.assertNoDiscrepancy(self._run(strategy, "grid_bot"))
        self.assertEqual(client.api_calls, 0)

    def test_a_position_without_a_dry_run_field_counts_as_simulated(self):
        """
        Ein Eintrag ohne `dry_run` kann praktisch nur durch manuelles
        Editieren entstehen. Er wird ueber den Default `True` als
        simuliert behandelt - die konservative Richtung, weil er die
        eigene Anspruchsmenge sonst kuenstlich erhoehen und damit einen
        Fehlalarm erzeugen wuerde. Dieselbe Regel wie im Verkaufspfad.
        """
        client = FakeAccountClient(free=UNCOVERED_BALANCE)
        strategy = self._grid(client)
        self._add_grid_position(strategy, LEDGER_QUANTITY, dry_run=False)
        records = strategy._ledger._read()
        del records[0]["dry_run"]
        strategy._ledger._write(records)

        self.assertNoDiscrepancy(self._run(strategy, "grid_bot"))


class TrendStartupCheckTestCase(StartupCheckTestBase):
    """
    Der Trend-Bot. Hier ist die geschlossene Luecke am groessten: Der
    Verkaufspfad laeuft nur bei einem echten Exit, und zwischen zwei
    Signalen koennen Monate liegen.
    """

    def test_a_covered_position_reports_nothing(self):
        client = FakeAccountClient(free=COVERED_BALANCE)
        strategy = self._trend(client)
        self._add_trend_position(strategy, LEDGER_QUANTITY, dry_run=False)

        self.assertNoDiscrepancy(self._run(strategy, "trend_bot"))

    def test_an_uncovered_position_warns_loudly(self):
        client = FakeAccountClient(free=UNCOVERED_BALANCE)
        strategy = self._trend(client)
        self._add_trend_position(strategy, LEDGER_QUANTITY, dry_run=False)

        self.assertReportedDiscrepancy(
            self._run(strategy, "trend_bot"), "[TREND-BESTAND-DISKREPANZ]"
        )

    def test_the_own_stop_loss_order_does_not_trigger_a_false_alarm(self):
        """
        Der wichtigste Fall dieser Klasse. Eine offene Trend-Position hat
        im Normalbetrieb eine exchange-seitige Stop-Loss-Order, die die
        KOMPLETTE Menge bindet - das freie Guthaben ist dann 0.

        Kein Fehlalarm entsteht nur deshalb, weil die Order seit dem
        K2-Fix das `trend-`Praefix traegt und damit in `own_locked`
        zaehlt: `own_upper_bound` ist `free + own_locked`.
        """
        client = FakeAccountClient(
            free=0.0,
            locked=LEDGER_QUANTITY,
            open_orders=[sell_order("trend-abc123", LEDGER_QUANTITY)],
        )
        strategy = self._trend(client)
        self._add_trend_position(strategy, LEDGER_QUANTITY, dry_run=False)

        self.assertNoDiscrepancy(self._run(strategy, "trend_bot"))

    def test_the_same_order_without_the_bot_prefix_does_trigger_the_alarm(self):
        """
        Gegenprobe: DIESELBE Lage, nur traegt die bindende Order kein
        Bot-Praefix (manueller Verkauf ueber die Boersen-Oberflaeche).
        Dann gilt sie als fremd, `own_upper_bound` faellt auf 0 - und die
        Diskrepanz ist eindeutig.

        Damit ist belegt, dass der vorige Test wirklich an der
        Praefix-Zuordnung haengt und nicht daran, dass `locked` pauschal
        mitgezaehlt wuerde.
        """
        client = FakeAccountClient(
            free=0.0,
            locked=LEDGER_QUANTITY,
            open_orders=[sell_order("manual-xyz", LEDGER_QUANTITY)],
        )
        strategy = self._trend(client)
        self._add_trend_position(strategy, LEDGER_QUANTITY, dry_run=False)

        self.assertReportedDiscrepancy(
            self._run(strategy, "trend_bot"), "[TREND-BESTAND-DISKREPANZ]"
        )

    def test_no_open_position_costs_no_api_call(self):
        client = FakeAccountClient()
        strategy = self._trend(client)

        self.assertNoDiscrepancy(self._run(strategy, "trend_bot"))
        self.assertEqual(client.api_calls, 0)

    def test_a_dry_run_position_does_not_count(self):
        client = FakeAccountClient(free=UNCOVERED_BALANCE)
        strategy = self._trend(client)
        self._add_trend_position(strategy, LEDGER_QUANTITY, dry_run=True)

        self.assertNoDiscrepancy(self._run(strategy, "trend_bot"))
        self.assertEqual(client.api_calls, 0)


class SharedBehaviourTestCase(StartupCheckTestBase):
    """
    Eigenschaften, die fuer alle drei gleich sind - am DCA-Bot
    stellvertretend geprueft, weil der Pfad danach identisch ist.
    """

    def _strategy_with_holdings(self, client: FakeAccountClient):
        strategy = self._dca(client)
        self._add_dca_buy(strategy, LEDGER_QUANTITY, dry_run=False)
        return strategy

    def test_an_unavailable_balance_is_not_a_finding(self):
        """
        Ein Netzwerkfehler ist keine Aussage ueber das Konto. Gleiche
        Haltung wie in `get_asset_balance()` und im Verkaufspfad - eine
        Warnung hier waere ein Fehlalarm bei jedem kurzen Aussetzer.
        """
        client = FakeAccountClient()
        client.base_balance = None
        strategy = self._strategy_with_holdings(client)

        lines = self._run(strategy, "dca_bot")
        self.assertNoDiscrepancy(lines)
        self.assertTrue(any("nicht abrufbar" in line for line in lines))

    def test_unavailable_open_orders_still_allow_the_check(self):
        """
        Sind nur die offenen Orders unbekannt, wird trotzdem geprueft -
        die gebundene Menge gilt dann vollstaendig als fremd (die
        konservative Richtung, siehe build_snapshot). Bei gedecktem
        freiem Guthaben bleibt das folgenlos.
        """
        client = FakeAccountClient(free=COVERED_BALANCE)
        client.open_orders = None
        strategy = self._strategy_with_holdings(client)

        self.assertNoDiscrepancy(self._run(strategy, "dca_bot"))
        self.assertEqual(client.balance_calls, 1)

    def test_a_failing_rules_lookup_propagates_to_the_startup_wrapper(self):
        """
        `get_symbol_trading_rules()` reicht einen Fehlschlag bewusst
        weiter (siehe binance_client.py) - der Check faengt ihn NICHT ab.

        Das ist Absicht: Der Aufruf liegt in der
        `safe_startup_reconciliation()`-Liste, die jeden Schritt einzeln
        kapselt, loggt und per Telegram meldet (W18). Ihn hier still zu
        schlucken wuerde diese Meldung verhindern. Dass der Wrapper das
        tatsaechlich auffaengt, ist in tests/test_stage_b_safety.py
        geprueft; hier ist nur belegt, dass der Fehler ihn erreicht.
        """
        client = FakeAccountClient()
        client.force_trading_rules_failure = True
        strategy = self._strategy_with_holdings(client)

        with self.assertRaises(RuntimeError):
            strategy.check_balance_on_startup()

    def test_the_tolerance_boundary_is_where_it_is_documented(self):
        """
        Die weiche Pruefung hat eine Toleranz von 0,1 % der eigenen Menge
        (bzw. zwei stepSize-Schritte, je nachdem was groesser ist) - hier
        also 0,0005 auf 0,5. Knapp darueber schweigt sie, knapp darunter
        meldet sie. Ohne dieses Paar waere nicht belegt, dass die Grenze
        ueberhaupt dort liegt.
        """
        just_covered = FakeAccountClient(free=LEDGER_QUANTITY - TOLERANCE)
        self.assertNoDiscrepancy(
            self._run(self._strategy_with_holdings(just_covered), "dca_bot")
        )

        self.notify.reset_mock()
        just_short = FakeAccountClient(free=LEDGER_QUANTITY - TOLERANCE - 0.0001)
        self.assertReportedDiscrepancy(
            self._run(self._strategy_with_holdings(just_short), "dca_bot"),
            "[BESTAND-DISKREPANZ]",
        )

    def test_a_covered_ledger_is_logged_as_checked(self):
        """
        Auch der unauffaellige Fall hinterlaesst eine Zeile. Sonst waere
        im Log nicht zu unterscheiden, ob der Abgleich in Ordnung war
        oder gar nicht gelaufen ist - und genau das will man nach einem
        Deployment sehen koennen.
        """
        client = FakeAccountClient(free=COVERED_BALANCE)
        lines = self._run(self._strategy_with_holdings(client), "dca_bot")
        self.assertTrue(any("in Ordnung" in line for line in lines))


class StartupWiringTestCase(unittest.TestCase):
    """
    Dass der Check in allen drei Einstiegspunkten tatsaechlich
    aufgerufen wird.

    **Was dieser Test leistet und was nicht:** Er liest den Quelltext der
    jeweiligen `main()`-Funktion, statt sie auszufuehren - ein echter
    Lauf braeuchte Konfiguration, Lockfile, Logging-Setup und einen
    Binance-Client. Er belegt damit nicht, dass der Aufruf zur Laufzeit
    ankommt, wohl aber den Fehler, der hier realistisch ist: drei
    beinahe identische Aufrufstellen, von denen bei einer spaeteren
    Aenderung eine vergessen wird. Die bestehenden Startpfad-Tests
    (test_order_reconciliation.py) pruefen die Verdrahtung gar nicht -
    das hier ist also mehr, nicht weniger.
    """

    def _main_source(self, module_name: str) -> str:
        import importlib

        module = importlib.import_module(module_name)
        return inspect.getsource(module.main)

    def test_all_three_entry_points_call_the_startup_check(self):
        for module_name in ("dca_bot.main", "dca_bot.main_grid", "dca_bot.main_trend"):
            with self.subTest(modul=module_name):
                source = self._main_source(module_name)
                self.assertIn("check_balance_on_startup", source)
                self.assertIn("Bestandsabgleich gegen den Kontostand", source)

    def test_the_check_is_wrapped_by_the_startup_guard(self):
        """
        Der Aufruf muss INNERHALB von `safe_startup_reconciliation()`
        stehen (W18). Stuende er daneben, wuerde ein Fehlschlag den
        Prozess beenden - und `Restart=on-failure` machte daraus eine
        Neustartschleife.
        """
        for module_name in ("dca_bot.main", "dca_bot.main_grid", "dca_bot.main_trend"):
            with self.subTest(modul=module_name):
                source = self._main_source(module_name)
                guard_at = source.index("safe_startup_reconciliation")
                check_at = source.index("check_balance_on_startup")
                self.assertLess(guard_at, check_at)

    def test_the_check_runs_after_the_reconciliation_steps(self):
        """
        Die Reihenfolge ist inhaltlich wichtig: Die Reconciliation kann
        Ledger-Eintraege nachtragen (K2), beim Trend-Bot stellt der
        zweite Schritt ausserdem die Stop-Loss-Order wieder her, die die
        Positionsmenge bindet. Ein Abgleich davor verglicher gegen einen
        anderen Stand.
        """
        for module_name, earlier in (
            ("dca_bot.main", "reconcile_pending_orders"),
            ("dca_bot.main_grid", "reconcile_pending_orders"),
            ("dca_bot.main_trend", "reconcile_on_startup"),
        ):
            with self.subTest(modul=module_name):
                source = self._main_source(module_name)
                self.assertLess(
                    source.index(earlier), source.index("check_balance_on_startup")
                )


if __name__ == "__main__":
    unittest.main()

"""
Tests gegen das GETEILTE Konto - Systemcheck vom 27.09.2026, Befunde
K-A, K-B, W-A und W-B (siehe trading-bot-projekt.md 6g).

**Warum eine eigene Testumgebung.** Die Fakes der uebrigen Testdateien
ersetzen den `TradingClient` als Ganzes und starten mit 1.000 BTC freiem
Guthaben. Damit ist genau die Fehlerklasse unsichtbar, um die es hier
geht: DCA, Grid und Trend teilen sich EIN Binance-Konto, und das freie
BTC des DCA-Bots deckt jeden Ueberverkauf von Grid oder Trend still ab.
Die Deckungspruefung (balance_guard.check_sell_coverage) vergleicht nur
gegen `free` - wem das freie BTC gehoert, kann sie nicht wissen.

Hier laeuft deshalb die komplette Kette: echte Strategie -> echter
`TradingClient` (inklusive K2-Logik) -> `FakeExchange`. Ersetzt ist nur
der ROHE python-binance-Client, und der verhaelt sich so, wie Binance
es dokumentiert:

- EIN Konto mit `free`/`locked` je Asset, gemeinsam fuer alle Bots.
- Deckung wird durchgesetzt: ein Verkauf ueber `free` hinaus wird mit
  -2010 abgelehnt, eine Stop-Order bindet ihre Menge.
- Auch eine PARTIALLY_FILLED-Order laesst sich stornieren; die Antwort
  traegt `executedQty` und `cummulativeQuoteQty`.
- Mindestvolumen (`NOTIONAL`) gilt auch fuer Market-Verkaeufe.
- Fehler lassen sich einspielen: "Order ausgefuehrt, Antwort verloren"
  und "Rueckfrage schlaegt fehl" - das Muster der naechtlichen
  Zwangstrennung.

**Die Invariante, die diese Klasse von Bug faengt** (`assert_ownership`).
Jeder Fill gehoert ueber das Praefix seiner clientOrderId eindeutig zu
einem Bot. Daraus folgt fuer jeden Bot, unabhaengig davon, ueber welchen
Codepfad etwas schiefgeht:

1. Er hat netto nie mehr verkauft, als er gekauft hat.
2. Er bindet in offenen Orders nie mehr, als er netto besitzt.
3. Was er laut Boerse besitzt, steht in seinem Ledger - bis auf Orders,
   deren Ausgang er selbst als offen fuehrt (Pending-Datei) und
   ausgewiesenen Staub.

Ausfuehren mit:  python -m unittest tests.test_shared_account -v
"""

from __future__ import annotations

import json
import logging
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests
from binance.exceptions import BinanceAPIException

from dca_bot.binance_client import TradingClient
from dca_bot.config import Config
from dca_bot.grid_config import GridConfig
from dca_bot.grid_strategy import GridTradingStrategy
from dca_bot.order_utils import quantize_quantity
from dca_bot.pending_orders import PendingOrderStore
from dca_bot.strategy import DCAStrategy
from dca_bot.trend_config import TrendConfig
from dca_bot.trend_strategy import TrendFollowingStrategy

SYMBOL = "BTCUSDT"
STEP_SIZE = 0.00001
TICK_SIZE = 0.01
MIN_NOTIONAL = 5.0
TOLERANCE = 1e-9

# Module, deren `send_notification` eingesammelt wird - so lassen sich
# Telegram-Meldungen pruefen, ohne dass etwas verschickt wird.
_NOTIFYING_MODULES = (
    "binance_client",
    "pending_orders",
    "strategy",
    "grid_strategy",
    "trend_strategy",
    "risk",
    "grid_risk",
    "trend_risk",
    "startup_checks",
)


def _api_error(code: int, msg: str, status: int = 400) -> BinanceAPIException:
    return BinanceAPIException(None, status, json.dumps({"code": code, "msg": msg}))


def bot_of(client_order_id: str) -> str:
    return str(client_order_id).split("-", 1)[0]


# ---------------------------------------------------------------------------
# Die Boerse
# ---------------------------------------------------------------------------


class FakeExchange:
    """
    Steht an der Stelle von `binance.client.Client` - fuer JEDEN Bot
    dieselbe Instanz, also ein einziges Konto.

    Mengen werden intern mit derselben Decimal-Quantisierung gerundet wie
    im Produktivcode (order_utils.quantize_quantity), damit Gleichheiten
    nicht an Fliesskomma-Rauschen scheitern.
    """

    def __init__(self, price: float, usdt: float = 100_000.0):
        self.price = price
        self.free = {"BTC": 0.0, "USDT": usdt}
        self.locked = {"BTC": 0.0, "USDT": 0.0}
        self.fee_rate = 0.0
        self.orders: dict[int, dict] = {}
        self.by_client_id: dict[str, int] = {}
        # Jede Ausfuehrung, in Reihenfolge: Grundlage der Invariante.
        self.fills: list[dict] = []
        self._faults: dict[str, list[str]] = {}
        self.lookup_down = False
        self._next_order_id = 1000

    # -- Fehler einspielen ----------------------------------------------------

    def inject(self, method: str, *modes: str) -> None:
        """
        Modi fuer die naechsten Aufrufe von `method`:

        - "lost": die Boerse fuehrt aus, die Antwort erreicht den Bot nie
          (ReadTimeout NACH der Ausfuehrung).
        - "dropped": der Request erreicht die Boerse nie (ReadTimeout
          VOR der Ausfuehrung).
        """
        self._faults.setdefault(method, []).extend(modes)

    def _fault(self, method: str) -> str | None:
        queue = self._faults.get(method)
        return queue.pop(0) if queue else None

    # -- interne Buchhaltung -------------------------------------------------

    @staticmethod
    def _q(value: float) -> float:
        return quantize_quantity(value, STEP_SIZE, round_down=True)

    def _new_order(self, client_order_id: str, side: str, order_type: str, orig_qty: float,
                   **extra) -> dict:
        self._next_order_id += 1
        order = {
            "symbol": SYMBOL,
            "orderId": self._next_order_id,
            "clientOrderId": client_order_id,
            "side": side,
            "type": order_type,
            "status": "NEW",
            "origQty": orig_qty,
            "executedQty": 0.0,
            "cummulativeQuoteQty": 0.0,
            **extra,
        }
        self.orders[order["orderId"]] = order
        self.by_client_id[client_order_id] = order["orderId"]
        return order

    def _execute(self, order: dict, qty: float, price: float) -> dict:
        """Fuehrt `qty` einer Order aus und bucht das Konto."""
        quote = qty * price
        if order["side"] == "BUY":
            commission = self._q(qty * self.fee_rate) if self.fee_rate else 0.0
            self.free["USDT"] -= quote
            self.free["BTC"] += qty - commission
            commission_asset = "BTC"
        else:
            commission = quote * self.fee_rate
            self.free["USDT"] += quote - commission
            commission_asset = "USDT"
        order["executedQty"] = self._q(float(order["executedQty"]) + qty)
        order["cummulativeQuoteQty"] = float(order["cummulativeQuoteQty"]) + quote
        fill = {
            "orderId": order["orderId"],
            "clientOrderId": order["clientOrderId"],
            "side": order["side"],
            "qty": qty,
            "price": price,
            "quote": quote,
            "commission": commission,
            "commissionAsset": commission_asset,
        }
        self.fills.append(fill)
        return fill

    @staticmethod
    def _public(order: dict, with_fills: list[dict] | None = None) -> dict:
        """Antwort wie von Binance: Zahlen als Strings, Fills nur bei Placement."""
        response = {
            key: (f"{value:.8f}" if isinstance(value, float) else value)
            for key, value in order.items()
        }
        if with_fills is not None:
            response["fills"] = [
                {
                    "price": f"{f['price']:.2f}",
                    "qty": f"{f['qty']:.8f}",
                    "commission": f"{f['commission']:.8f}",
                    "commissionAsset": f["commissionAsset"],
                }
                for f in with_fills
            ]
        return response

    def _place(self, method: str, action):
        mode = self._fault(method)
        if mode == "dropped":
            raise requests.exceptions.ReadTimeout("Read timed out. (Testfall: nie angekommen)")
        response = action()
        if mode == "lost":
            raise requests.exceptions.ReadTimeout("Read timed out. (Testfall: Antwort verloren)")
        return response

    # -- python-binance-Schnittstelle ------------------------------------------

    def get_symbol_info(self, symbol):
        return {
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "quoteAssetPrecision": 8,
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": str(TICK_SIZE)},
                {"filterType": "LOT_SIZE", "stepSize": f"{STEP_SIZE:.8f}"},
                {"filterType": "NOTIONAL", "minNotional": str(MIN_NOTIONAL)},
            ],
        }

    def get_symbol_ticker(self, symbol):
        return {"symbol": symbol, "price": f"{self.price:.2f}"}

    def get_asset_balance(self, asset):
        return {
            "asset": asset,
            "free": f"{self.free[asset]:.8f}",
            "locked": f"{self.locked[asset]:.8f}",
        }

    def get_open_orders(self, symbol):
        return [
            self._public(o)
            for o in self.orders.values()
            if o["status"] in ("NEW", "PARTIALLY_FILLED")
        ]

    def get_order(self, symbol, orderId=None, origClientOrderId=None):
        if self.lookup_down:
            raise requests.exceptions.ConnectionError("Verbindung weg (Testfall)")
        if origClientOrderId is not None:
            order_id = self.by_client_id.get(origClientOrderId)
        else:
            order_id = int(orderId)
        order = self.orders.get(order_id)
        if order is None:
            raise _api_error(-2013, "Order does not exist.")
        return self._public(order)

    def get_my_trades(self, symbol, orderId):
        return [
            {
                "price": f"{f['price']:.2f}",
                "qty": f"{f['qty']:.8f}",
                "commission": f"{f['commission']:.8f}",
                "commissionAsset": f["commissionAsset"],
            }
            for f in self.fills
            if f["orderId"] == int(orderId)
        ]

    def order_market_buy(self, symbol, quoteOrderQty, newClientOrderId):
        def action():
            quote = float(quoteOrderQty)
            if quote > self.free["USDT"] + TOLERANCE:
                raise _api_error(-2010, "Account has insufficient balance.")
            qty = self._q(quote / self.price)
            if qty * self.price < MIN_NOTIONAL:
                raise _api_error(-1013, "Filter failure: NOTIONAL")
            order = self._new_order(newClientOrderId, "BUY", "MARKET", qty)
            fill = self._execute(order, qty, self.price)
            order["status"] = "FILLED"
            return self._public(order, [fill])

        return self._place("order_market_buy", action)

    def order_market_sell(self, symbol, quantity, newClientOrderId):
        def action():
            qty = self._q(float(quantity))
            if qty * self.price < MIN_NOTIONAL:
                raise _api_error(-1013, "Filter failure: NOTIONAL")
            if qty > self.free["BTC"] + TOLERANCE:
                raise _api_error(-2010, "Account has insufficient balance.")
            self.free["BTC"] -= qty
            order = self._new_order(newClientOrderId, "SELL", "MARKET", qty)
            fill = self._execute(order, qty, self.price)
            order["status"] = "FILLED"
            return self._public(order, [fill])

        return self._place("order_market_sell", action)

    def create_order(self, symbol, side, type, timeInForce, quantity, stopPrice, price,
                     newClientOrderId):
        def action():
            qty = self._q(float(quantity))
            if qty > self.free["BTC"] + TOLERANCE:
                raise _api_error(-2010, "Account has insufficient balance.")
            self.free["BTC"] -= qty
            self.locked["BTC"] += qty
            order = self._new_order(
                newClientOrderId, "SELL", "STOP_LOSS_LIMIT", qty,
                stopPrice=float(stopPrice), price=float(price),
            )
            return self._public(order)

        return self._place("create_order", action)

    def cancel_order(self, symbol, orderId):
        order = self.orders.get(int(orderId))
        # Wie Binance: auch eine teilgefuellte Order ist stornierbar.
        if order is None or order["status"] not in ("NEW", "PARTIALLY_FILLED"):
            raise _api_error(-2011, "Unknown order sent.")
        self._release(order)
        order["status"] = "CANCELED"
        return self._public(order)

    # -- Steuerung durch den Test ----------------------------------------------

    def _remaining(self, order: dict) -> float:
        return self._q(float(order["origQty"]) - float(order["executedQty"]))

    def _release(self, order: dict) -> None:
        remaining = self._remaining(order)
        self.locked["BTC"] -= remaining
        self.free["BTC"] += remaining

    def fill_stop(self, order_id, qty: float, price: float | None = None) -> None:
        """Die Stop-Order hat ausgeloest und fuellt `qty` zum Limit-Preis."""
        order = self.orders[int(order_id)]
        qty = self._q(qty)
        assert qty <= self._remaining(order) + TOLERANCE, "Testaufbau: mehr als offen"
        self.locked["BTC"] -= qty
        self._execute(order, qty, order["price"] if price is None else price)
        order["status"] = "FILLED" if self._remaining(order) <= TOLERANCE else "PARTIALLY_FILLED"

    def expire(self, order_id, status: str = "EXPIRED") -> None:
        """Die Order endet an der Boerse (z.B. manuell storniert) - Rest frei."""
        order = self.orders[int(order_id)]
        self._release(order)
        order["status"] = status

    def move_price(self, price: float, rng: random.Random) -> None:
        """
        Neuer Kurs. Ausgeloeste Stop-Orders fuellen zufaellig gar nicht,
        teilweise oder ganz - genau die Lage, fuer die der Stop-Limit-Offset
        kalibriert wird.
        """
        self.price = price
        for order in list(self.orders.values()):
            if order["type"] != "STOP_LOSS_LIMIT" or order["status"] not in ("NEW", "PARTIALLY_FILLED"):
                continue
            if price > order["stopPrice"]:
                continue
            fraction = rng.choice((0.0, 0.3, 0.5, 1.0))
            qty = self._q(self._remaining(order) * fraction)
            if qty > 0:
                self.fill_stop(order["orderId"], qty)

    # -- Auswertung -----------------------------------------------------------

    def fills_of(self, bot: str, side: str | None = None) -> list[dict]:
        return [
            f for f in self.fills
            if bot_of(f["clientOrderId"]) == bot and (side is None or f["side"] == side)
        ]

    def net_base(self, bot: str) -> float:
        """Was dieser Bot laut Boerse netto an BTC besitzt."""
        total = 0.0
        for f in self.fills_of(bot):
            if f["side"] == "BUY":
                base_fee = f["commission"] if f["commissionAsset"] == "BTC" else 0.0
                total += f["qty"] - base_fee
            else:
                total -= f["qty"]
        return total

    def locked_by(self, bot: str) -> float:
        return sum(
            self._remaining(o)
            for o in self.orders.values()
            if o["side"] == "SELL"
            and o["status"] in ("NEW", "PARTIALLY_FILLED")
            and bot_of(o["clientOrderId"]) == bot
        )


# ---------------------------------------------------------------------------
# Die Testumgebung: mehrere Bots auf einem Konto
# ---------------------------------------------------------------------------


class SharedAccountTestBase(unittest.TestCase):
    PRICE = 50_000.0

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp = Path(self._tmpdir.name)
        self.exchange = FakeExchange(self.PRICE)

        # Log-Ausgabe schlucken (Warnungen sind in diesen Szenarien der
        # Normalfall), ohne assertLogs in einzelnen Tests zu stoeren.
        for name in ("dca_bot", "grid_bot", "trend_bot"):
            handler = logging.NullHandler()
            logging.getLogger(name).addHandler(handler)
            self.addCleanup(logging.getLogger(name).removeHandler, handler)

        self.messages: list[str] = []
        for module in _NOTIFYING_MODULES:
            patcher = mock.patch(
                f"dca_bot.{module}.send_notification", self.messages.append, create=True
            )
            patcher.start()
            self.addCleanup(patcher.stop)

        # Die kurze Nachfrage-Wartezeit des Trend-Bots nach einem unklaren
        # Verkauf (60 s) darf die Tests nicht ausbremsen.
        patcher = mock.patch("dca_bot.trend_strategy._sleep", lambda s: None, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.bots: dict[str, object] = {}

    # -- Bots ------------------------------------------------------------------

    def _client(self, config) -> TradingClient:
        with mock.patch("dca_bot.binance_client.Client"):
            client = TradingClient(config)
        client._client = self.exchange
        return client

    def _path(self, name: str) -> str:
        return str(self.tmp / name)

    def dca_config(self, quote_amount: float = 500.0) -> Config:
        return Config(
            api_key="k", api_secret="s", symbol=SYMBOL,
            quote_amount=quote_amount, max_daily_spend=1_000_000.0,
            trading_enabled=True, stop_loss_pct=0.0,
            kill_switch_file=self._path("STOP_DCA"),
            state_file=self._path("trade_ledger.json"),
            stop_loss_state_file=self._path("dca_stop_loss.json"),
            pending_orders_file=self._path("pending_orders_dca.json"),
            bot_name="dca",
        )

    def grid_config(self) -> GridConfig:
        return GridConfig(
            api_key="k", api_secret="s", symbol=SYMBOL,
            lower_limit=70_000.0, upper_limit=90_000.0, grid_spacing_pct=1.5,
            amount_per_level=15.0, trading_enabled=True, stop_loss_pct=15.0,
            kill_switch_file=self._path("STOP_GRID"),
            state_file=self._path("grid_positions.json"),
            stop_loss_state_file=self._path("grid_stop_loss.json"),
            pending_orders_file=self._path("pending_orders_grid.json"),
            bot_name="grid",
        )

    def trend_config(self, **overrides) -> TrendConfig:
        params = dict(
            api_key="k", api_secret="s", symbol=SYMBOL,
            amount_per_trade=15.0, stop_loss_pct=10.0, stop_limit_offset_pct=0.5,
            trading_enabled=True,
            kill_switch_file=self._path("STOP_TREND"),
            state_file=self._path("trend_ledger.json"),
            stop_loss_state_file=self._path("trend_stop_loss.json"),
            pending_orders_file=self._path("pending_orders_trend.json"),
            bot_name="trend",
        )
        params.update(overrides)
        return TrendConfig(**params)

    def start_dca(self, **kwargs) -> DCAStrategy:
        bot = DCAStrategy(self.dca_config(**kwargs), self._client(self.dca_config(**kwargs)))
        self.bots["dca"] = bot
        return bot

    def start_grid(self) -> GridTradingStrategy:
        bot = GridTradingStrategy(self.grid_config(), self._client(self.grid_config()))
        self.bots["grid"] = bot
        return bot

    def start_trend(self, seeded: bool = True, **overrides) -> TrendFollowingStrategy:
        config = self.trend_config(**overrides)
        bot = TrendFollowingStrategy(config, self._client(config))
        # Ohne Netzwerk: kein Seeding der EMAs. Die Szenarien hier
        # steuern Ein- und Ausstiege direkt bzw. ueber den Stop-Loss.
        bot._seeded = seeded
        self.bots["trend"] = bot
        return bot

    def seed_dca_holdings(self) -> DCAStrategy:
        """
        Der Bestand, der jeden Ueberverkauf still abdeckt: der DCA-Bot
        kauft einmal fuer 500 USDT (0,01 BTC bei 50.000) - ueber die Boerse,
        damit der Bestand ihm per clientOrderId zugeordnet ist.
        """
        dca = self.start_dca()
        dca.execute_once()
        self.assertAlmostEqual(self.exchange.net_base("dca"), 0.01, places=9)
        return dca

    # -- Ledger-Sicht der Bots --------------------------------------------------

    def ledger_open_quantity(self, bot_name: str) -> float:
        bot = self.bots[bot_name]
        if bot_name == "dca":
            return bot._ledger.position(SYMBOL)[1]
        if bot_name == "grid":
            return sum(
                float(r["quantity"])
                for r in bot._ledger.open_positions()
                if r.get("dry_run") is False
            )
        total = 0.0
        for trade in bot._ledger._read():
            if trade.get("dry_run") is not False:
                continue
            # Ausgewiesener Staub gehoert dem Bot weiterhin (K-A).
            total += float(trade.get("dust_qty") or 0.0)
            if trade["status"] == "open":
                total += float(trade["quantity"]) - float(trade.get("partial_exit_qty") or 0.0)
        return total

    def known_unbooked(self, bot_name: str) -> float:
        """
        Fills zu Orders, deren Ausgang der Bot selbst noch als offen fuehrt
        (Pending-Datei). Die darf das Ledger noch nicht enthalten - das ist
        kein Fehler, sondern genau der Zustand, den die Datei festhaelt.
        """
        config = self.bots[bot_name]._config
        pending_ids = {
            p.client_order_id
            for p in PendingOrderStore(config.pending_orders_file, config.bot_name).all()
        }
        total = 0.0
        for f in self.exchange.fills_of(bot_name):
            if f["clientOrderId"] in pending_ids:
                total += f["qty"] if f["side"] == "BUY" else -f["qty"]
        return total

    def assert_ownership(self) -> None:
        """Die Invariante aus dem Modul-Docstring, fuer jeden laufenden Bot."""
        for name in self.bots:
            net = self.exchange.net_base(name)
            self.assertGreaterEqual(
                net, -TOLERANCE,
                f"[Regel 1] {name} hat netto {-net:.8f} BTC mehr verkauft als "
                "gekauft - das kam aus dem Bestand eines anderen Bots",
            )
            locked = self.exchange.locked_by(name)
            self.assertLessEqual(
                locked, max(net, 0.0) + TOLERANCE,
                f"[Regel 2] {name} bindet {locked:.8f} BTC in offenen Orders, "
                f"besitzt aber nur {net:.8f}",
            )
            self.assertAlmostEqual(
                net - self.known_unbooked(name),
                self.ledger_open_quantity(name),
                places=8,
                msg=f"[Regel 3] {name}: Boersenbestand und Ledger laufen auseinander",
            )


# ---------------------------------------------------------------------------
# K-A: Trend-Ausstieg bei teilgefuellter Stop-Order
# ---------------------------------------------------------------------------


class TrendPartialStopFillTestCase(SharedAccountTestBase):
    def _open_trend(self) -> tuple[TrendFollowingStrategy, dict]:
        trend = self.start_trend()
        trend._open_position(self.PRICE)
        trade = trend._ledger.open_position()
        self.assertAlmostEqual(trade["quantity"], 0.0003, places=9)
        self.assertIsNotNone(trade["stop_loss_order_id"])
        return trend, trade

    def test_exit_with_partially_filled_stop_sells_only_the_remainder(self):
        """
        Reproduktion 1 aus dem Systemcheck: Die Stop-Order hat die Haelfte
        verkauft, danach loest der interne Stop-Loss aus. Verkauft werden
        darf nur noch der Rest - und der Erloes der Teilfuellung gehoert
        ins Ledger.
        """
        self.seed_dca_holdings()
        trend, trade = self._open_trend()
        stop_id = trade["stop_loss_order_id"]
        limit = trade["stop_limit_price"]
        self.exchange.fill_stop(stop_id, 0.00015)
        self.exchange.price = 44_000.0

        trend.execute_once()

        self.assert_ownership()
        sells = self.exchange.fills_of("trend", "SELL")
        self.assertAlmostEqual(sum(f["qty"] for f in sells), 0.0003, places=9)
        closed = trend._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "stop_loss")
        self.assertTrue(trend._stop_loss.is_paused())
        expected_proceeds = 0.00015 * limit + 0.00015 * 44_000.0
        self.assertAlmostEqual(
            closed["realized_pnl"], expected_proceeds - closed["quote_spent"], places=6
        )

    def test_stop_order_that_ended_partially_filled_during_downtime_is_completed(self):
        """
        Der verwandte Fall ueber den Startpfad: Die Stop-Order hat teilweise
        gefuellt und ist danach beendet worden (hier: abgelaufen). Bisher
        wurde die GANZE Position mit dem Teilerloes geschlossen - der Rest
        lag danach ohne Ledger auf dem Konto.
        """
        self.seed_dca_holdings()
        trend, trade = self._open_trend()
        stop_id = trade["stop_loss_order_id"]
        self.exchange.fill_stop(stop_id, 0.00015)
        self.exchange.expire(stop_id)
        self.exchange.price = 46_000.0  # ueber der internen Stop-Schwelle

        restarted = self.start_trend()
        restarted.reconcile_on_startup()

        self.assert_ownership()
        closed = restarted._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "stop_loss")
        self.assertAlmostEqual(
            sum(f["qty"] for f in self.exchange.fills_of("trend", "SELL")), 0.0003, places=9
        )

    def test_remainder_below_min_notional_is_closed_and_reported_as_dust(self):
        """
        Bleibt nach der Teilfuellung weniger als das Mindestvolumen, lehnt
        Binance jeden Verkauf ab. Die Position wird dann geschlossen, der
        Rest als Staub ausgewiesen und gemeldet - nicht jeden Zyklus erneut
        erfolglos verkauft, und schon gar nicht aus fremdem Bestand.
        """
        self.seed_dca_holdings()
        trend, trade = self._open_trend()
        self.exchange.fill_stop(trade["stop_loss_order_id"], 0.00025)
        self.exchange.price = 44_000.0  # Rest 0,00005 x 44.000 = 2,20 < 5,00

        trend.execute_once()

        self.assert_ownership()
        closed = trend._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertAlmostEqual(closed["dust_qty"], 0.00005, places=9)
        self.assertTrue(any("Staub" in m for m in self.messages), self.messages)


# ---------------------------------------------------------------------------
# K-B: kein zweiter Verkauf, solange der erste ungeklaert ist
# ---------------------------------------------------------------------------


class UnclearSellTestCase(SharedAccountTestBase):
    def _grid_with_open_position(self) -> tuple[GridTradingStrategy, dict]:
        grid = self.start_grid()
        level_price = grid._levels[3]
        # Der Ticker liefert zwei Nachkommastellen - der Kurs muss also
        # sichtbar UNTER der (krummen) Stufe liegen, damit sie durchquert ist.
        self.exchange.price = round(level_price - 1.0, 2)
        grid._last_seen_price = level_price + 1.0
        grid.execute_once()
        positions = grid._ledger.open_positions()
        self.assertEqual(len(positions), 1, "Testaufbau: genau ein Grid-Kauf")
        return grid, positions[0]

    def test_grid_does_not_sell_again_while_the_first_sell_is_unclear(self):
        """
        Reproduktion 2: Der Verkauf geht durch, die Antwort geht verloren,
        die Rueckfrage scheitert (Zwangstrennung). Bisher verkaufte der
        naechste Zyklus mit neuer clientOrderId erneut - aus dem Bestand
        des DCA-Bots.
        """
        self.seed_dca_holdings()
        grid, position = self._grid_with_open_position()
        self.exchange.price = position["target_sell_price"] * 1.0001
        self.exchange.inject("order_market_sell", "lost")
        self.exchange.lookup_down = True

        grid.execute_once()  # Verkauf ausgefuehrt, Ausgang unklar
        grid.execute_once()  # Leitung weiter weg
        self.assert_ownership()

        self.exchange.lookup_down = False
        grid.execute_once()  # Rueckfrage klappt

        sells = self.exchange.fills_of("grid", "SELL")
        self.assertEqual(len(sells), 1, "Genau EIN Verkauf fuer EINE Position")
        closed = grid._ledger.position_by_id(position["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["sell_client_order_id"], sells[0]["clientOrderId"])
        self.assertEqual(grid._client.pending_orders.all(), [])
        self.assert_ownership()

    def test_trend_places_no_stop_order_from_foreign_holdings_after_unclear_sell(self):
        """
        Trend-Seite von K-B: Nach dem unklaren Verkauf platzierte
        `_handle_failed_real_sell` sofort eine neue Stop-Order ueber die
        volle Menge - gedeckt vom DCA-Bestand - und der naechste Zyklus
        verkaufte ein zweites Mal.
        """
        self.seed_dca_holdings()
        trend = self.start_trend()
        trend._open_position(self.PRICE)
        self.exchange.price = 44_000.0  # interner Stop-Loss faellig
        self.exchange.inject("order_market_sell", "lost")
        self.exchange.lookup_down = True

        trend.execute_once()
        self.assert_ownership()

        self.exchange.lookup_down = False
        trend.execute_once()

        self.assert_ownership()
        self.assertEqual(len(self.exchange.fills_of("trend", "SELL")), 1)
        closed = trend._ledger._read()[0]
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["exit_reason"], "stop_loss")
        self.assertTrue(trend._stop_loss.is_paused())
        self.assertEqual(trend._client.pending_orders.all(), [])

    def _place_foreign_sell_directly(self, client_order_id: str, qty: float) -> None:
        """Ein Verkauf, der real an der Boerse lief (Ausgang war verloren)."""
        self.exchange.order_market_sell(SYMBOL, qty, client_order_id)

    def test_grid_reconciliation_reports_a_double_sale_instead_of_swallowing_it(self):
        """
        Zweite Sicherung dahinter: Ist die Position schon geschlossen, aber
        mit einer ANDEREN Verkaufs-Order als der aus der Pending-Datei, liefen
        zwei Verkaeufe. Bisher hielt die Reconciliation das fuer "schon
        verbucht" und verwarf den Eintrag ohne Meldung.
        """
        self.seed_dca_holdings()
        grid, position = self._grid_with_open_position()
        records = grid._ledger._read()
        records[0].update(status="closed", sell_price=80_000.0, realized_pnl=0.1,
                          sold_at="2026-09-27T00:00:00+00:00",
                          sell_client_order_id="grid-erster-verkauf")
        grid._ledger._write(records)
        store = grid._client.pending_orders
        from dca_bot.pending_orders import KIND_MARKET, PendingOrder
        store.add(PendingOrder.new("grid-zweiter-verkauf", KIND_MARKET, SYMBOL, "SELL",
                                   {"position_id": position["id"], "price": 80_000.0}))
        self._place_foreign_sell_directly("grid-zweiter-verkauf", position["quantity"])

        grid.reconcile_pending_orders()

        self.assertTrue(any("[GRID-DOPPELVERKAUF]" in m for m in self.messages), self.messages)
        self.assertEqual(
            [p.client_order_id for p in store.all()], ["grid-zweiter-verkauf"],
            "Der Eintrag bleibt bis zur manuellen Klaerung stehen",
        )

    def test_trend_reconciliation_reports_a_double_sale_instead_of_swallowing_it(self):
        self.seed_dca_holdings()
        trend = self.start_trend()
        trend._open_position(self.PRICE)
        trade = trend._ledger.open_position()
        trend._client.cancel_order(SYMBOL, trade["stop_loss_order_id"])
        trend._ledger.record_exit(trade["id"], 51_000.0, "2026-09-27T00:00:00+00:00",
                                  "signal", 0.3)
        records = trend._ledger._read()
        records[0]["exit_client_order_id"] = "trend-erster-verkauf"
        trend._ledger._write(records)
        store = trend._client.pending_orders
        from dca_bot.pending_orders import KIND_MARKET, PendingOrder
        store.add(PendingOrder.new("trend-zweiter-verkauf", KIND_MARKET, SYMBOL, "SELL",
                                   {"trade_id": trade["id"], "reason": "signal"}))
        self._place_foreign_sell_directly("trend-zweiter-verkauf", trade["quantity"])

        trend.reconcile_pending_orders()

        self.assertTrue(any("[TREND-DOPPELVERKAUF]" in m for m in self.messages), self.messages)
        self.assertEqual([p.client_order_id for p in store.all()], ["trend-zweiter-verkauf"])

    def test_grid_does_not_buy_a_level_again_while_its_buy_is_unclear(self):
        """
        Gegenstueck auf der Kaufseite: Der Kauf geht durch, die Antwort geht
        verloren, die Rueckfrage scheitert. Durchquert der Kurs dieselbe
        Stufe erneut, bevor der Kauf geklaert ist, darf sie nicht ein zweites
        Mal gekauft werden - sie gilt ueber den Pending-Eintrag als belegt.
        """
        grid = self.start_grid()
        level_price = grid._levels[3]
        self.exchange.inject("order_market_buy", "lost")
        self.exchange.lookup_down = True
        self.exchange.price = round(level_price - 1.0, 2)
        grid._last_seen_price = level_price + 1.0
        grid.execute_once()  # Kauf ausgefuehrt, Ausgang unklar

        self.exchange.price = round(level_price + 1.0, 2)
        grid.execute_once()  # Kurs wieder ueber der Stufe
        self.exchange.price = round(level_price - 1.0, 2)
        grid.execute_once()  # ... und erneut durchquert

        self.assertEqual(len(self.exchange.fills_of("grid", "BUY")), 1)
        self.assert_ownership()

        self.exchange.lookup_down = False
        grid.execute_once()  # Rueckfrage klappt, Kauf wird nachgetragen

        self.assertEqual(len(grid._ledger.open_positions()), 1)
        self.assertEqual(grid._client.pending_orders.all(), [])
        self.assert_ownership()


# ---------------------------------------------------------------------------
# W-A und W-B
# ---------------------------------------------------------------------------


class LedgerWindowTestCase(SharedAccountTestBase):
    def test_buy_whose_ledger_entry_failed_is_booked_in_the_next_cycle(self):
        """
        Reproduktion 3 (W-A): Die Order ist ausgefuehrt, das Schreiben ins
        Ledger scheitert. Bisher war der Pending-Eintrag zu diesem Zeitpunkt
        schon weg - der Kauf blieb fuer immer unverbucht.
        """
        dca = self.start_dca()
        with mock.patch.object(dca._ledger, "record", side_effect=OSError("No space left")):
            with self.assertRaises(OSError):
                dca.execute_once()
        self.assert_ownership()  # der Kauf steht als offen in der Pending-Datei

        dca.execute_once()  # naechster Zyklus

        self.assertEqual(len(self.exchange.fills_of("dca", "BUY")), 2)
        self.assertEqual(len(dca._ledger._read()), 2)
        self.assert_ownership()

    def test_trend_places_no_second_stop_order_after_an_unclear_one(self):
        """
        Reproduktion 4 (W-B): Die Stop-Order liegt an der Boerse, ihre
        Antwort ging verloren. Bisher platzierte der naechste Zyklus eine
        zweite - gebunden aus dem Bestand des DCA-Bots.
        """
        self.seed_dca_holdings()
        trend = self.start_trend()
        self.exchange.inject("create_order", "lost")
        self.exchange.lookup_down = True
        trend._open_position(self.PRICE)
        self.exchange.lookup_down = False
        self.exchange.price = 51_000.0

        trend.execute_once()

        self.assert_ownership()
        stops = [o for o in self.exchange.orders.values() if o["type"] == "STOP_LOSS_LIMIT"]
        self.assertEqual(len(stops), 1)
        self.assertEqual(
            str(trend._ledger.open_position()["stop_loss_order_id"]), str(stops[0]["orderId"])
        )

    def test_grid_sell_booked_but_not_confirmed_is_cleaned_up_quietly(self):
        """
        W-A auf der Verkaufsseite: Der Verkauf steht im Ledger, der Prozess
        stirbt vor `confirm_booked()`. Die naechste Reconciliation findet den
        Eintrag und muss ueber die gespeicherte Verkaufs-ID erkennen, dass
        genau dieser Verkauf schon verbucht ist - ohne sie saehe er wie ein
        zweiter Verkauf aus und wuerde als Doppelverkauf gemeldet.
        """
        self.seed_dca_holdings()
        grid = self.start_grid()
        level_price = grid._levels[3]
        self.exchange.price = round(level_price - 1.0, 2)
        grid._last_seen_price = level_price + 1.0
        grid.execute_once()
        (position,) = grid._ledger.open_positions()
        self.exchange.price = position["target_sell_price"] * 1.0001

        with mock.patch.object(grid._client, "confirm_booked"):
            grid.execute_once()  # verkauft und verbucht, Eintrag bleibt
        self.assertEqual(len(grid._client.pending_orders.all()), 1)

        grid.execute_once()

        self.assertFalse(any("DOPPELVERKAUF" in m for m in self.messages), self.messages)
        self.assertEqual(grid._client.pending_orders.all(), [])
        self.assertEqual(len(self.exchange.fills_of("grid", "SELL")), 1)
        self.assert_ownership()

    def test_trend_exit_booked_but_not_confirmed_is_cleaned_up_quietly(self):
        """Dasselbe fuer den Trend-Ausstieg (exit_client_order_id)."""
        self.seed_dca_holdings()
        trend = self.start_trend()
        trend._open_position(self.PRICE)
        self.exchange.price = 44_000.0  # interner Stop-Loss faellig

        with mock.patch.object(trend._client, "confirm_booked"):
            trend.execute_once()  # verkauft und verbucht, Eintrag bleibt
        self.assertEqual(len(trend._client.pending_orders.entries_for(side="SELL")), 1)

        trend.execute_once()

        self.assertFalse(any("DOPPELVERKAUF" in m for m in self.messages), self.messages)
        self.assertEqual(trend._client.pending_orders.entries_for(side="SELL"), [])
        self.assertEqual(len(self.exchange.fills_of("trend", "SELL")), 1)
        self.assert_ownership()


# ---------------------------------------------------------------------------
# Zufallsgesteuerter Dauerlauf
# ---------------------------------------------------------------------------


class SharedAccountSoakTestCase(SharedAccountTestBase):
    """
    DCA, Grid und Trend auf einem Konto, mehrere hundert Zyklen mit
    zufaelligen Kursen, Teilfuellungen, Neustarts und eingespielten
    Netzwerkfehlern. Die Invariante wird nach JEDEM Schritt geprueft.
    Ein Verstoss nennt Seed und Schritt - damit ist er reproduzierbar.
    """

    SEEDS = range(8)
    STEPS = 200
    PRICE = 80_000.0

    def _history(self, symbol, interval, start, end):
        return [{"close_price": 80_000.0 + 50.0 * i, "open_time": 0, "low_price": 0.0}
                for i in range(10)]

    def _run_seed(self, seed: int) -> None:
        rng = random.Random(seed)
        self.exchange = FakeExchange(self.PRICE)
        self.bots = {}
        for name in ("pending_orders_dca.json", "pending_orders_grid.json",
                     "pending_orders_trend.json", "trade_ledger.json", "grid_positions.json",
                     "trend_ledger.json", "grid_stop_loss.json", "trend_stop_loss.json"):
            (self.tmp / name).unlink(missing_ok=True)

        dca = self.start_dca(quote_amount=200.0)
        dca.execute_once()
        grid = self.start_grid()
        trend = self.start_trend(seeded=False, ema_fast_period=3, ema_slow_period=5)

        price = self.PRICE
        for step in range(self.STEPS):
            price = min(max(price * (1 + rng.gauss(0, 0.02)), 55_000.0), 95_000.0)
            self.exchange.move_price(round(price, 2), rng)
            self.exchange.lookup_down = rng.random() < 0.25
            for method in ("order_market_buy", "order_market_sell", "create_order"):
                roll = rng.random()
                if roll < 0.08:
                    self.exchange.inject(method, "lost")
                elif roll < 0.12:
                    self.exchange.inject(method, "dropped")

            if rng.random() < 0.05:
                grid = self.start_grid()
                grid.reconcile_pending_orders()
            if rng.random() < 0.05:
                trend = self.start_trend(seeded=False, ema_fast_period=3, ema_slow_period=5)
                trend.reconcile_pending_orders()
                trend.reconcile_on_startup()
            # Fallengelassene Stop-Loss-Sperren wieder aufheben, damit der
            # Trend-Bot ueber den ganzen Lauf handelt.
            if rng.random() < 0.1:
                trend._stop_loss.reset()

            bots = [grid, trend] + ([dca] if step % 10 == 0 else [])
            for bot in bots:
                try:
                    bot.execute_once()
                except Exception:  # wie die Hauptschleife: Zyklus faellt aus
                    pass

            try:
                self.assert_ownership()
            except AssertionError as exc:
                raise AssertionError(f"Seed {seed}, Schritt {step}: {exc}") from None

    def test_invariant_holds_under_random_faults(self):
        # Ledger und Pending-Dateien schreiben per fsync - fuer die
        # Absturzsicherheit, nicht fuer die Logik. Auf Windows kostete das
        # hier allein rund zehn Sekunden; die Dateien selbst bleiben echt.
        with mock.patch("dca_bot.trend_strategy.fetch_historical_klines", self._history), \
                mock.patch("os.fsync"):
            for seed in self.SEEDS:
                self._run_seed(seed)


if __name__ == "__main__":
    unittest.main()

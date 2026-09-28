"""
Der Rueckweg: Kann der alte Code die Dateien lesen, die der neue schreibt?

**Warum das ein eigener Test ist.** Die Symbolbindung vom 28.09.2026
schreibt ein zusaetzliches Feld `symbol` in Grid- und Trend-Ledger und in
den Allocator-Zustand. Geht nach dem Deploy etwas schief, ist der einzige
Rueckweg `git checkout` auf den vorherigen Stand - und der muss dann mit
genau diesen Dateien weiterlaufen. Ein Rueckweg, der erst im Ernstfall
ausprobiert wird, ist keiner.

**Wie geprueft wird.**

1. Der AKTUELLE Code erzeugt in einem temporaeren Verzeichnis einen
   vollstaendigen Satz Zustandsdateien: DCA-, Grid- und Trend-Ledger (mit
   offenen und geschlossenen Eintraegen, Trend mit Stop-Order), den
   Allocator-Zustand aus einem echten Allocator-Zyklus, alle drei
   Stop-Loss-Sperren und eine Pending-Datei. Ein Praemissen-Test belegt,
   dass das neue Feld wirklich drinsteht.
2. Der ALTE Stand wird per `git archive` aus dem Repository geholt (nur
   `dca_bot/`, nichts im Arbeitsverzeichnis wird angefasst) und in einem
   eigenen Python-Prozess gegen diese Dateien ausgefuehrt - nicht nur
   Lesen, sondern die Pfade, die ein Bot nach einem Rueckschritt
   tatsaechlich nimmt: Grid verkauft eine offene Position, Trend gleicht
   die Stop-Order ab und steigt per Stop-Loss aus, DCA kauft (Dry-Run),
   der Allocator rechnet weiter, die Sperren werden erkannt und
   aufgehoben, Positions-Audit, Korrektur-Skript (Bericht) und
   check_orders-Abgleich laufen. Dabei muss das unbekannte Feld die
   Schreibvorgaenge des alten Codes ueberleben.

Geprueft werden zwei Staende: 10ce096 laeuft am 28.09.2026 auf beiden
Servern, 46ca7a7 ist der Stand direkt vor dieser Runde. Fehlt einer davon
(flacher Klon, kein git), wird der Test mit Begruendung uebersprungen -
er ist dann ausdruecklich NICHT gelaufen.

Ausfuehren mit:  python -m unittest tests.test_rollback_compat -v
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dca_bot import allocator as allocator_module
from dca_bot.allocator import Allocator
from dca_bot.allocator_config import AllocatorConfig
from dca_bot.grid_risk import GridLedger, GridPosition, GridStopLoss
from dca_bot.pending_orders import KIND_MARKET, PendingOrder, PendingOrderStore
from dca_bot.risk import PortfolioStopLoss, TradeLedger, TradeRecord
from dca_bot.trend_risk import TrendLedger, TrendStopLoss, TrendTrade

REPO = Path(__file__).resolve().parent.parent

OLD_STATES = (
    ("10ce096", "laeuft am 28.09.2026 auf VPS und Homeserver"),
    ("46ca7a7", "Stand direkt vor der Symbolbindung"),
)


def _flat_klines(symbol, interval, start, end):
    out, day = [], date.fromisoformat(start)
    while day <= date.fromisoformat(end):
        stamp = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        out.append({"open_time": int(stamp.timestamp() * 1000), "close_price": 70_000.0,
                    "low_price": 0.0})
        day += timedelta(days=1)
    return out


def write_new_format_files(data: Path) -> dict[str, str]:
    """Ein vollstaendiger Satz Zustandsdateien, geschrieben vom AKTUELLEN Code."""
    data.mkdir(parents=True, exist_ok=True)
    paths = {name: str(data / file) for name, file in (
        ("dca", "trade_ledger.json"), ("grid", "grid_positions.json"),
        ("trend", "trend_ledger.json"), ("alloc", "allocator_state.json"),
        ("dca_sl", "stop_loss_paused.json"), ("grid_sl", "grid_stop_loss_paused.json"),
        ("trend_sl", "trend_stop_loss_paused.json"), ("pending", "pending_orders_grid.json"),
    )}
    paths["tmp"] = str(data)
    paths["stop"] = str(data / "STOP_UNUSED")

    dca = TradeLedger(paths["dca"])
    dca.record(TradeRecord(
        timestamp=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        symbol="BTCUSDT", quote_spent=15.0, quantity=0.0002, price=75_000.0,
        dry_run=False, client_order_id="dca-x",
    ))

    grid = GridLedger(paths["grid"])
    grid.record_buy(GridPosition.new(
        level_index=3, buy_price=74_000.0, target_sell_price=75_110.0, quantity=0.0002,
        quote_spent=14.8, dry_run=False, client_order_id="grid-open", symbol="BTCUSDT",
    ))
    closed = GridPosition.new(
        level_index=5, buy_price=76_000.0, target_sell_price=77_140.0, quantity=0.0002,
        quote_spent=15.2, dry_run=False, client_order_id="grid-closed", symbol="BTCUSDT",
    )
    grid.record_buy(closed)
    grid.record_sell(closed.id, 77_140.0, datetime.now(timezone.utc).isoformat(), 0.2, "grid-sold")

    trend = TrendLedger(paths["trend"])
    old_trade = TrendTrade.new(entry_price=48_000.0, quantity=0.0003, quote_spent=14.4,
                               dry_run=False, client_order_id="trend-old", symbol="BTCUSDT")
    trend.record_entry(old_trade)
    trend.record_exit(old_trade.id, 49_000.0, datetime.now(timezone.utc).isoformat(),
                      "signal", 0.3, "trend-old-exit")
    open_trade = TrendTrade.new(entry_price=50_000.0, quantity=0.0003, quote_spent=15.0,
                                dry_run=False, client_order_id="trend-open", symbol="BTCUSDT")
    trend.record_entry(open_trade)
    trend.set_stop_loss_order(open_trade.id, "9001", 44_775.0)

    with mock.patch.object(allocator_module, "fetch_historical_klines", _flat_klines), \
            mock.patch.object(allocator_module, "send_notification", lambda m: None), \
            mock.patch("dca_bot.trend_risk.send_notification"), \
            mock.patch("dca_bot.trend_risk.logger"), mock.patch("dca_bot.risk.logger"), \
            mock.patch("dca_bot.grid_risk.logger"):
        Allocator(AllocatorConfig(api_key="k", api_secret="s", state_file=paths["alloc"])).execute_once()
        PortfolioStopLoss(dca, 25.0, paths["dca_sl"])._pause("BTCUSDT", 15.0, 10.0, 33.3)
        GridStopLoss(70_000.0, 15.0, paths["grid_sl"])._pause("BTCUSDT", 50_000.0, 59_500.0)
        TrendStopLoss(paths["trend_sl"]).pause("BTCUSDT", 50_000.0, 44_000.0, 12.0)

    PendingOrderStore(paths["pending"], "grid").add(
        PendingOrder.new("grid-pend", KIND_MARKET, "BTCUSDT", "BUY", {"level_index": 7})
    )
    return paths


# Laeuft im ALTEN Code, in einem eigenen Prozess. Jede Pruefung ist ein
# assert mit Klartext; am Ende steht "ALLES OK".
OLD_CODE_SCRIPT = r'''
import contextlib, io, json, logging, os, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

P = json.loads(sys.argv[1])
logging.disable(logging.CRITICAL)

from dca_bot.order_utils import SymbolTradingRules
from dca_bot.pending_orders import PendingOrderStore

RULES = SymbolTradingRules(symbol="BTCUSDT", tick_size=0.01, step_size=0.00001,
                           min_notional=5.0, base_asset="BTC", quote_asset="USDT",
                           quote_precision=8)


class Fake:
    def __init__(self, pending_file, bot, price):
        self.pending_orders = PendingOrderStore(pending_file, bot)
        self.price, self.n, self.sells, self.cancels = price, 0, [], []
    def get_current_price(self, s): return self.price
    def get_symbol_trading_rules(self, s): return RULES
    def get_asset_balance(self, a): return (1000.0, 0.0)
    def get_open_orders(self, s): return []
    def get_order_by_client_id(self, s, c): return ("not_found", None)
    def get_order_with_fills(self, s, o): return o
    def get_order_status(self, s, oid):
        return {"orderId": oid, "status": "NEW", "executedQty": "0", "cummulativeQuoteQty": "0"}
    def cancel_order(self, s, oid):
        self.cancels.append(str(oid))
        return {"orderId": oid, "status": "CANCELED", "executedQty": "0", "cummulativeQuoteQty": "0"}
    def place_market_buy(self, s, amount, context=None): return None
    def place_market_sell(self, s, qty, context=None):
        self.sells.append(qty)
        self.n += 1
        return {"clientOrderId": f"alt-{self.n}", "executedQty": str(qty),
                "cummulativeQuoteQty": str(qty * self.price), "fills": []}
    def place_stop_loss_limit_sell(self, *a, **k): return None
    def confirm_booked(self, cid):
        if cid: self.pending_orders.remove(cid)


def flat(symbol, interval, start, end):
    out, day = [], date.fromisoformat(start)
    while day <= date.fromisoformat(end):
        stamp = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        out.append({"open_time": int(stamp.timestamp() * 1000), "close_price": 70000.0, "low_price": 0.0})
        day += timedelta(days=1)
    return out


quiet = contextlib.redirect_stdout(io.StringIO())

# --- nur lesen ---------------------------------------------------------------
from dca_bot.risk import TradeLedger, PortfolioStopLoss
from dca_bot.grid_risk import GridLedger, GridStopLoss
from dca_bot.trend_risk import TrendLedger, TrendStopLoss
from dca_bot.allocator_signals import read_allocation_fraction
from dca_bot import audit_positions as ap
from dca_bot import fix_dry_run_quote_spent as fx

dca = TradeLedger(P["dca"])
assert dca.position("BTCUSDT")[1] > 0, "DCA-Bestand nicht gelesen"
assert dca.has_client_order_id("dca-x"), "DCA clientOrderId nicht gefunden"
assert dca.last_trade_time("BTCUSDT") is not None, "DCA last_trade_time"

grid = GridLedger(P["grid"])
opens = grid.open_positions()
assert len(opens) == 1 and opens[0]["symbol"] == "BTCUSDT", "Grid offene Position"
assert grid.open_position_for_level(3) is not None, "Grid Stufe 3"
assert grid.has_client_order_id("grid-closed"), "Grid clientOrderId"

trend = TrendLedger(P["trend"])
open_trade = trend.open_position()
assert open_trade is not None and open_trade["stop_loss_order_id"] == "9001", "Trend offene Position"

state = json.load(open(P["alloc"], encoding="utf-8"))
assert state["symbol"] == "BTCUSDT", "Praemisse: Allocator-Zustand traegt das neue Feld"
assert read_allocation_fraction(P["alloc"]) == state["trend_fraction"], "Allocator-Zuteilung"

assert PortfolioStopLoss(dca, 25.0, P["dca_sl"]).is_paused(), "DCA-Sperre"
assert GridStopLoss(70000.0, 15.0, P["grid_sl"]).is_paused(), "Grid-Sperre"
assert TrendStopLoss(P["trend_sl"]).is_paused(), "Trend-Sperre"

assert [p.client_order_id for p in PendingOrderStore(P["pending"], "grid").all()] == ["grid-pend"]

with quiet:
    ap.audit_dca(Path(P["dca"]), "BTCUSDT")
    ap.audit_grid(Path(P["grid"]))
    ap.audit_trend(Path(P["trend"]))
    rc = fx.main(["--dca-file", P["dca"], "--grid-file", P["grid"],
                  "--trend-file", P["trend"], "--no-lock"])
assert rc == 0, "Korrektur-Skript (Bericht)"
assert ap.grid_claim(Path(P["grid"]), "BTCUSDT").error is None
assert abs(ap.trend_claim(Path(P["trend"]), "BTCUSDT").quantity - 0.0003) < 1e-12

os.environ["GRID_STATE_FILE"] = P["grid"]
os.environ["GRID_PENDING_ORDERS_FILE"] = P["pending"]
from dca_bot import check_orders as co
# Den Buchhaltungsabgleich gibt es erst seit W-E (194dfc7) - 10ce096 ist aelter.
if hasattr(co, "check_local_bookkeeping"):
    assert co.check_local_bookkeeping("grid", "grid-open", None).ledger_field == "client_order_id"

# --- weiterarbeiten wie ein zurueckgedrehter Bot ------------------------------
from dca_bot.grid_config import GridConfig
from dca_bot.grid_strategy import GridTradingStrategy
cfg = GridConfig(api_key="k", api_secret="s", symbol="BTCUSDT", lower_limit=70000.0,
                 upper_limit=90000.0, grid_spacing_pct=1.5, amount_per_level=15.0,
                 trading_enabled=True, kill_switch_file=P["stop"], state_file=P["grid"],
                 stop_loss_state_file=P["tmp"] + "/grid_sl_neu.json",
                 pending_orders_file=P["tmp"] + "/p_grid.json", bot_name="grid")
client = Fake(cfg.pending_orders_file, "grid", 76000.0)
GridTradingStrategy(cfg, client).execute_once()
assert client.sells, "Grid hat die offene Position nicht verkauft"
sold = GridLedger(P["grid"]).position_by_id(opens[0]["id"])
assert sold["status"] == "closed", "Grid-Position nicht geschlossen"
assert sold["symbol"] == "BTCUSDT", "Feld symbol hat den Schreibvorgang des alten Codes nicht ueberlebt"

from dca_bot.trend_config import TrendConfig
from dca_bot.trend_strategy import TrendFollowingStrategy
cfg = TrendConfig(api_key="k", api_secret="s", symbol="BTCUSDT", trading_enabled=True,
                  kill_switch_file=P["stop"], state_file=P["trend"],
                  stop_loss_state_file=P["tmp"] + "/trend_sl_neu.json",
                  pending_orders_file=P["tmp"] + "/p_trend.json", bot_name="trend")
client = Fake(cfg.pending_orders_file, "trend", 51000.0)
strategy = TrendFollowingStrategy(cfg, client)
strategy._seeded = True
strategy.reconcile_on_startup()
client.price = 44000.0
strategy.execute_once()
exited = TrendLedger(P["trend"]).trade_by_id(open_trade["id"])
assert exited["status"] == "closed" and exited["exit_reason"] == "stop_loss", "Trend-Ausstieg"
assert client.cancels == ["9001"], "Trend hat die Stop-Order nicht storniert"
assert exited["symbol"] == "BTCUSDT", "Trend: Feld symbol verloren"

from dca_bot.config import Config
from dca_bot.strategy import DCAStrategy
cfg = Config(api_key="k", api_secret="s", symbol="BTCUSDT", trading_enabled=False,
             kill_switch_file=P["stop"], state_file=P["dca"],
             stop_loss_state_file=P["tmp"] + "/dca_sl_neu.json",
             pending_orders_file=P["tmp"] + "/p_dca.json", bot_name="dca")
DCAStrategy(cfg, Fake(cfg.pending_orders_file, "dca", 75000.0)).execute_once()
assert len(TradeLedger(P["dca"])._read()) == 2, "DCA-Kauf (Dry-Run) nicht angehaengt"

from dca_bot import allocator as am
from dca_bot.allocator_config import AllocatorConfig
with mock.patch.object(am, "fetch_historical_klines", flat):
    am.Allocator(AllocatorConfig(api_key="k", api_secret="s", state_file=P["alloc"])).execute_once()
assert "trend_fraction" in json.load(open(P["alloc"], encoding="utf-8")), "Allocator-Zyklus"

for latch in (PortfolioStopLoss(dca, 25.0, P["dca_sl"]), GridStopLoss(70000.0, 15.0, P["grid_sl"]),
              TrendStopLoss(P["trend_sl"])):
    latch.reset()
    assert not latch.is_paused(), "Sperre liess sich nicht aufheben"

print("ALLES OK")
'''


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True)


def extract_old_code(commit: str, target: Path) -> None:
    """Holt `dca_bot/` eines Commits per git archive - ohne das Arbeitsverzeichnis anzufassen."""
    archive = _git("archive", "--format=zip", commit, "dca_bot")
    if archive.returncode != 0:
        raise RuntimeError(archive.stderr.decode(errors="replace"))
    with zipfile.ZipFile(io.BytesIO(archive.stdout)) as zf:
        zf.extractall(target)


def old_code_available(commit: str) -> str | None:
    """None, wenn der Stand verfuegbar ist - sonst der Grund, warum nicht."""
    if shutil.which("git") is None:
        return "git ist nicht installiert"
    if _git("cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
        return f"Commit {commit} ist in diesem Klon nicht vorhanden"
    return None


def run_old_code(commit: str, paths: dict[str, str], workdir: Path) -> subprocess.CompletedProcess:
    extract_old_code(commit, workdir)
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith(("DCA_", "GRID_", "TREND_", "ALLOCATOR_", "TELEGRAM_", "BINANCE_"))
        and k not in ("STOP_ALL", "USE_TESTNET")
    }
    env["PYTHONPATH"] = str(workdir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", "-c", OLD_CODE_SCRIPT, json.dumps(paths)],
        cwd=workdir, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120,
    )


class NewFilesPremiseTestCase(unittest.TestCase):
    """Praemisse: Die Dateien, die der alte Code lesen soll, tragen das neue Feld wirklich."""

    def test_new_files_carry_the_symbol_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_new_format_files(Path(tmp) / "data")
            grid = json.loads(Path(paths["grid"]).read_text(encoding="utf-8"))
            trend = json.loads(Path(paths["trend"]).read_text(encoding="utf-8"))
            alloc = json.loads(Path(paths["alloc"]).read_text(encoding="utf-8"))
            self.assertTrue(all(r["symbol"] == "BTCUSDT" for r in grid))
            self.assertTrue(all(r["symbol"] == "BTCUSDT" for r in trend))
            self.assertEqual(alloc["symbol"], "BTCUSDT")
            for latch in ("dca_sl", "grid_sl", "trend_sl"):
                self.assertEqual(
                    json.loads(Path(paths[latch]).read_text(encoding="utf-8"))["symbol"], "BTCUSDT"
                )


class RollbackCompatibilityTestCase(unittest.TestCase):
    def test_old_code_reads_and_continues_on_new_files(self):
        for commit, meaning in OLD_STATES:
            with self.subTest(stand=commit, bedeutung=meaning):
                reason = old_code_available(commit)
                if reason is not None:
                    self.skipTest(f"Rueckweg gegen {commit} NICHT geprueft: {reason}")
                with tempfile.TemporaryDirectory() as tmp:
                    paths = write_new_format_files(Path(tmp) / "data")
                    result = run_old_code(commit, paths, Path(tmp) / "alt")
                self.assertEqual(
                    result.returncode, 0,
                    f"Alter Stand {commit} scheitert an den neuen Dateien:\n"
                    f"{result.stdout}\n{result.stderr[-3000:]}",
                )
                self.assertIn("ALLES OK", result.stdout)


if __name__ == "__main__":
    unittest.main()

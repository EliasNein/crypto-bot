"""
Orders bei Binance nachschlagen - nur lesend, für alle drei Bots.

Zwei Aufrufe:

    python -m dca_bot.check_orders
        Die letzten Orders aller Symbole von DCA, Grid und Trend, jeweils
        mit clientOrderId und dem Bot, der sie platziert hat, dazu Kurs und
        Guthaben von Base- und Quote-Asset. Zugleich der Verbindungstest:
        ersetzt das frühere test_connection.py, das bei aktivem Trading
        einen echten DCA-Kauf auslöste (Systemcheck vom 27.09.2026, W-D).

    python -m dca_bot.check_orders --client-order-id grid-7f3a9c2e14b84d6fa0e51c83
        Die eine Frage nach einem [ORDER-UNKLAR]: Gibt es diese Order bei
        Binance, und was ist aus ihr geworden? Dazu der Abgleich mit der
        eigenen Buchhaltung: Steht die ID noch in der Pending-Datei des
        Bots, steht sie im Ledger?

Bis zum 27.09.2026 (Systemcheck, W-E) zeigte dieses Skript nur die
letzten 10 Orders des DCA-Symbols, ohne clientOrderId - also genau ohne
das Merkmal, nach dem man bei einem [ORDER-UNKLAR] sucht - und leitete
Base- und Quote-Asset per String-Ersetzung aus "BTC" ab.

**Nur lesend, strukturell abgesichert.** Der Client kommt aus
audit_positions._build_read_only_client(): ohne Pending-Orders-Datei, und
die place_*-Methoden des TradingClient weisen genau diesen Zustand aktiv
zurück. Die Zusage hängt damit nicht an Disziplin, sondern am Aufbau -
dieselbe Konstruktion wie beim Positions-Audit, bewusst wiederverwendet
statt ein zweites Mal gebaut.

**Dieselben Regeln wie der Bot.** Nachgeschlagen wird über
get_order_by_client_id(), bewertet über order_lifecycle_state() - also mit
denselben drei Ausgängen (gefunden / Binance kennt sie nicht / Abfrage
gescheitert) und derselben Einstufung, nach der der Bot selbst
entscheidet. Ein Werkzeug, das zu einer Order etwas anderes sagt als der
Bot, der sie gemeldet hat, wäre bei der Klärung schlimmer als keins.

Das Ergebnis entsteht als Objekt (OrderLookup, LocalBookkeeping) und wird
getrennt davon gedruckt - aus demselben Grund wie im Positions-Audit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .audit_positions import BOT_NAMES, _build_read_only_client
from .pending_orders import (
    LOOKUP_FAILED,
    LOOKUP_FOUND,
    LOOKUP_NOT_FOUND,
    ORDER_LIFECYCLE_DEAD,
    ORDER_LIFECYCLE_FILLED,
    ORDER_LIFECYCLE_LIVE,
    UNKNOWN_FINAL_AFTER_SECONDS,
    PendingOrderStore,
    bot_for_client_order_id,
    order_lifecycle_state,
)


@dataclass(frozen=True)
class BotFiles:
    """Wo ein Bot sein Symbol, seine Pending-Datei und sein Ledger hat -
    dieselben Variablen und Defaults wie in den drei Configs."""

    symbol_var: str
    pending_var: str
    pending_default: str
    ledger_var: str
    ledger_default: str

    def symbol(self) -> str:
        return os.getenv(self.symbol_var, "BTCUSDT").strip() or "BTCUSDT"

    def pending_file(self) -> Path:
        return Path(os.getenv(self.pending_var, self.pending_default))

    def ledger_file(self) -> Path:
        return Path(os.getenv(self.ledger_var, self.ledger_default))


BOT_FILES = {
    "dca": BotFiles(
        "DCA_SYMBOL",
        "DCA_PENDING_ORDERS_FILE",
        "data/pending_orders_dca.json",
        "DCA_BOT_STATE_FILE",
        "data/trade_ledger.json",
    ),
    "grid": BotFiles(
        "GRID_SYMBOL",
        "GRID_PENDING_ORDERS_FILE",
        "data/pending_orders_grid.json",
        "GRID_STATE_FILE",
        "data/grid_positions.json",
    ),
    "trend": BotFiles(
        "TREND_SYMBOL",
        "TREND_PENDING_ORDERS_FILE",
        "data/pending_orders_trend.json",
        "TREND_STATE_FILE",
        "data/trend_ledger.json",
    ),
}

# Felder, unter denen die drei Ledger eine clientOrderId ablegen: Kauf
# (alle drei), Verkauf (Grid), Ausstieg (Trend).
LEDGER_CLIENT_ID_FIELDS = ("client_order_id", "sell_client_order_id", "exit_client_order_id")
# Die Stop-Loss-Order des Trend-Bots steht im Ledger mit ihrer orderId,
# nicht mit der clientOrderId.
LEDGER_ORDER_ID_FIELDS = ("stop_loss_order_id",)

EXIT_OK = 0
EXIT_NO_CLIENT = 1
EXIT_LOOKUP_FAILED = 2


def all_symbols() -> list[str]:
    """Die Symbole der drei Bots, ohne Dopplungen, in Bot-Reihenfolge."""
    symbols: list[str] = []
    for name in BOT_NAMES:
        symbol = BOT_FILES[name].symbol()
        if symbol not in symbols:
            symbols.append(symbol)
    return symbols


def symbols_to_search(client_order_id: str, symbol_override: str | None) -> list[str]:
    """
    Unter welchen Symbolen gesucht wird. Binance braucht zum Nachschlagen
    immer das Symbol, die clientOrderId allein reicht nicht.

    Vorrang hat `--symbol`. Sonst verrät das Präfix den Bot und damit sein
    Symbol. Passt kein Präfix, wird unter allen drei Symbolen gesucht.
    """
    if symbol_override:
        return [symbol_override]
    bot = bot_for_client_order_id(client_order_id, BOT_NAMES)
    if bot is not None:
        return [BOT_FILES[bot].symbol()]
    return all_symbols()


@dataclass(frozen=True)
class OrderLookup:
    client_order_id: str
    bot: str | None
    symbol: str | None  # das Symbol, unter dem sie gefunden wurde
    searched: tuple[str, ...]
    lookup: str  # LOOKUP_FOUND / LOOKUP_NOT_FOUND / LOOKUP_FAILED
    order: dict | None

    @property
    def lifecycle(self) -> str | None:
        return order_lifecycle_state(self.order) if self.lookup == LOOKUP_FOUND else None


def look_up(client, client_order_id: str, symbol_override: str | None = None) -> OrderLookup:
    """
    Schlägt eine clientOrderId unter allen in Frage kommenden Symbolen
    nach.

    Über mehrere Symbole gilt: ein Treffer entscheidet. "Nicht gefunden"
    darf dagegen nur gemeldet werden, wenn JEDE Abfrage "nicht gefunden"
    ergab - ist eine davon gescheitert, kann die Order genau dort liegen,
    und das Ergebnis ist LOOKUP_FAILED. Dieselbe Regel wie im Bot: nur
    -2013 heißt "gibt es nicht".
    """
    bot = bot_for_client_order_id(client_order_id, BOT_NAMES)
    searched = symbols_to_search(client_order_id, symbol_override)
    any_failed = False
    for symbol in searched:
        result, order = client.get_order_by_client_id(symbol, client_order_id)
        if result == LOOKUP_FOUND:
            return OrderLookup(client_order_id, bot, symbol, tuple(searched), LOOKUP_FOUND, order)
        if result != LOOKUP_NOT_FOUND:
            any_failed = True
    return OrderLookup(
        client_order_id,
        bot,
        None,
        tuple(searched),
        LOOKUP_FAILED if any_failed else LOOKUP_NOT_FOUND,
        None,
    )


@dataclass(frozen=True)
class LocalBookkeeping:
    """Was die eigenen Dateien des Bots zu dieser Order sagen."""

    pending_file: Path
    in_pending: bool | None  # None = Datei nicht lesbar
    ledger_file: Path
    ledger_field: str | None  # in welchem Feld die ID steht, None = nicht verbucht
    ledger_error: str | None


def check_local_bookkeeping(bot: str, client_order_id: str, order: dict | None) -> LocalBookkeeping:
    files = BOT_FILES[bot]
    pending_path = files.pending_file()
    in_pending = _in_pending_file(pending_path, bot, client_order_id)

    ledger_path = files.ledger_file()
    order_id = str(order.get("orderId")) if isinstance(order, dict) and order.get("orderId") is not None else None
    field, error = _find_in_ledger(ledger_path, client_order_id, order_id)
    return LocalBookkeeping(pending_path, in_pending, ledger_path, field, error)


def _in_pending_file(path: Path, bot: str, client_order_id: str) -> bool | None:
    if not path.exists():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("orders"), list):
        return None
    # Über den PendingOrderStore, damit dieselbe Lesart gilt wie im Bot.
    store = PendingOrderStore(str(path), bot)
    return any(entry.client_order_id == client_order_id for entry in store.all())


def _find_in_ledger(path: Path, client_order_id: str, order_id: str | None) -> tuple[str | None, str | None]:
    if not path.exists():
        return None, None
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"Ledger nicht lesbar ({type(exc).__name__})"
    if not isinstance(records, list):
        return None, "Ledger hat ein unerwartetes Format (erwartet: JSON-Liste)"
    for record in records:
        if not isinstance(record, dict):
            continue
        for field in LEDGER_CLIENT_ID_FIELDS:
            if record.get(field) == client_order_id:
                return field, None
        if order_id is not None:
            for field in LEDGER_ORDER_ID_FIELDS:
                if record.get(field) is not None and str(record.get(field)) == order_id:
                    return field, None
    return None, None


def verdict(lookup: OrderLookup, local: LocalBookkeeping | None) -> str:
    """Die Einordnung in einem Satz - was daraus für den Menschen folgt."""
    if lookup.lookup == LOOKUP_FAILED:
        return (
            "Die Abfrage ist gescheitert - daraus folgt NICHTS über die Order. "
            "Später erneut versuchen."
        )
    if lookup.lookup == LOOKUP_NOT_FOUND:
        return (
            "Binance kennt diese clientOrderId nicht (-2013): die Order wurde "
            "nie angenommen. Bis etwa "
            f"{int(UNKNOWN_FINAL_AFTER_SECONDS)} s nach dem Absenden kann sie "
            "noch auftauchen - danach ist die Antwort endgültig."
        )

    state = lookup.lifecycle
    if state == ORDER_LIFECYCLE_LIVE:
        return "Die Order ist noch aktiv (liegt im Orderbuch oder wird noch ausgeführt)."
    if state == ORDER_LIFECYCLE_DEAD:
        return "Die Order ist beendet, ohne etwas bewegt zu haben - kein Trade."
    if state != ORDER_LIFECYCLE_FILLED:
        return "Der Status der Order ist nicht bewertbar - bitte bei Binance direkt prüfen."

    if local is None:
        return "Die Order wurde ausgeführt. Sie gehört zu keinem der drei Bots."
    if local.ledger_field is not None:
        if local.in_pending:
            return (
                "Ausgeführt und im Ledger verbucht. Der Pending-Eintrag steht "
                "noch; der nächste Zyklus räumt ihn auf."
            )
        return "Ausgeführt und im Ledger verbucht - nichts zu tun."
    if local.in_pending:
        return (
            "Ausgeführt, noch NICHT im Ledger. Der Pending-Eintrag steht noch, "
            "der Bot trägt die Order im nächsten Zyklus nach ([REKONZILIATION]). "
            "Nicht von Hand ins Ledger schreiben."
        )
    return (
        "Ausgeführt, aber weder im Ledger noch in der Pending-Datei - diese "
        "Order ist für den Bot unsichtbar. Manuell klären, BEVOR der Bot "
        "weiter handelt (Positions-Audit: python -m dca_bot.audit_positions)."
    )


# --- Ausgabe ---------------------------------------------------------------


def _format_time(ms) -> str:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    except (TypeError, ValueError, OSError):
        return "?"


def print_lookup(lookup: OrderLookup, local: LocalBookkeeping | None) -> None:
    print(f"clientOrderId: {lookup.client_order_id}")
    print(f"Bot:           {lookup.bot or 'keiner der drei (unbekanntes Präfix)'}")
    print(f"Gesucht unter: {', '.join(lookup.searched)}")
    print()

    if lookup.lookup == LOOKUP_FOUND:
        order = lookup.order or {}
        print(f"Binance: GEFUNDEN unter {lookup.symbol}")
        print(f"  orderId:        {order.get('orderId', '?')}")
        print(f"  Status:         {order.get('status', '?')}")
        print(f"  Seite / Typ:    {order.get('side', '?')} / {order.get('type', '?')}")
        print(f"  Menge:          {order.get('executedQty', '?')} ausgeführt von {order.get('origQty', '?')}")
        print(f"  Betrag:         {order.get('cummulativeQuoteQty', '?')}")
        if order.get("stopPrice") not in (None, "", "0", "0.00000000"):
            print(f"  Stop / Limit:   {order.get('stopPrice')} / {order.get('price', '?')}")
        print(f"  Zeit:           {_format_time(order.get('time'))}")
    elif lookup.lookup == LOOKUP_NOT_FOUND:
        print("Binance: NICHT GEFUNDEN (-2013)")
    else:
        print("Binance: ABFRAGE GESCHEITERT")

    if local is not None:
        print()
        pending = {True: "steht noch drin", False: "nicht (mehr) drin", None: "nicht lesbar"}[local.in_pending]
        print(f"Pending-Datei ({local.pending_file}): {pending}")
        if local.ledger_error:
            ledger = local.ledger_error
        elif local.ledger_field:
            ledger = f"verbucht (Feld {local.ledger_field})"
        else:
            ledger = "nicht verbucht"
        print(f"Ledger ({local.ledger_file}): {ledger}")

    print()
    print(f"Einordnung: {verdict(lookup, local)}")


def print_recent_orders(client, limit: int) -> None:
    """Die Übersicht ohne Argumente - zugleich der Verbindungstest."""
    for symbol in all_symbols():
        print()
        print("=" * 78)
        print(f"{symbol}")
        print("=" * 78)

        try:
            rules = client.get_symbol_trading_rules(symbol)
        except Exception as exc:
            # Nur der Typ: bei einem requests-Fehler stünde in str(exc) die
            # signierte Request-URL.
            print(f"Handelsregeln nicht abrufbar ({type(exc).__name__}) - Symbol übersprungen.")
            continue

        try:
            print(f"Kurs: {client.get_current_price(symbol):.2f} {rules.quote_asset}")
        except Exception as exc:
            print(f"Kurs nicht abrufbar ({type(exc).__name__}).")

        for asset in (rules.base_asset, rules.quote_asset):
            balance = client.get_asset_balance(asset)
            if balance is None:
                print(f"Guthaben {asset}: nicht abrufbar")
            else:
                print(f"Guthaben {asset}: frei {balance[0]:.8f}, gebunden {balance[1]:.8f}")

        orders = client.get_recent_orders(symbol, limit)
        print()
        if orders is None:
            print("Letzte Orders nicht abrufbar.")
            continue
        if not orders:
            print("Keine Orders für dieses Symbol.")
            continue
        print(f"Letzte {len(orders)} Orders (älteste zuerst):")
        for order in orders:
            client_order_id = str(order.get("clientOrderId", "") or "")
            bot = bot_for_client_order_id(client_order_id, BOT_NAMES) or "-"
            print(
                f"  {_format_time(order.get('time'))} | {bot:<5} | {client_order_id:<36} | "
                f"{order.get('side', '?'):<4} {order.get('type', '?'):<16} | "
                f"{order.get('status', '?'):<16} | ausgeführt {order.get('executedQty', '?')} | "
                f"Betrag {order.get('cummulativeQuoteQty', '?')}"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Orders bei Binance nachschlagen, nur lesend. Ohne Argumente: "
            "letzte Orders aller drei Bots mit clientOrderId, Kurs und "
            "Guthaben. Mit --client-order-id: gezielte Suche nach einer "
            "Order, z.B. nach einer [ORDER-UNKLAR]-Meldung."
        )
    )
    parser.add_argument(
        "--client-order-id",
        help="Die clientOrderId aus der Meldung, z.B. grid-7f3a9c2e14b84d6fa0e51c83",
    )
    parser.add_argument(
        "--symbol",
        help="Symbol erzwingen, statt es aus dem Präfix der clientOrderId abzuleiten.",
    )
    parser.add_argument(
        "--limit", type=int, default=10, help="Anzahl Orders pro Symbol in der Übersicht (Default 10)."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    client, reason = _build_read_only_client()
    if client is None:
        print(f"Kein Zugriff auf Binance: {reason}")
        return EXIT_NO_CLIENT

    print("Orders nachschlagen (nur lesend, es wird nichts verändert)")

    if not args.client_order_id:
        print_recent_orders(client, args.limit)
        return EXIT_OK

    client_order_id = args.client_order_id.strip()
    lookup = look_up(client, client_order_id, args.symbol)
    local = (
        check_local_bookkeeping(lookup.bot, client_order_id, lookup.order)
        if lookup.bot is not None
        else None
    )
    print()
    print_lookup(lookup, local)
    return EXIT_LOOKUP_FAILED if lookup.lookup == LOOKUP_FAILED else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

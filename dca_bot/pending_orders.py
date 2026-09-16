"""
Idempotente Order-Platzierung: selbstvergebene Order-IDs, eine kleine
"Pending-Orders"-Datei pro Bot und die Ground-Truth-Rueckfrage bei der
Boerse.

Hintergrund (Sicherheitsreview-Punkt K2): Eine Order konnte an der
Boerse ausgefuehrt werden, ohne je im Ledger zu landen. Zwei Wege
fuehrten dorthin:

1. `python-binance` setzt seine Requests ueber `requests` ab. Ein
   Timeout oder Verbindungsabbruch kommt deshalb als
   `requests.exceptions.RequestException` durch, eine kaputte Antwort
   als `BinanceRequestException` - keine davon wurde in den
   `place_*`-Methoden gefangen. Die Order ging raus, Binance nahm sie an
   und fuellte sie, die Antwort erreichte den Bot nicht: ungefangene
   Exception, `execute_once()` bricht ab, kein Ledger-Eintrag.
2. Dasselbe Loch entsteht ganz ohne Netzwerkfehler durch einen
   Prozess-Kill zwischen Order-Platzierung und Ledger-Schreibvorgang.
   Das Fenster ist real mehrere Sekunden gross - beim Trend-Bot liegt
   dazwischen ein kompletter zweiter API-Call (die Stop-Loss-Order) plus
   Telegram-Sendeversuche.

Die Gegenmassnahme besteht aus drei Teilen, von denen dieses Modul die
ersten beiden beisteuert:

- **Selbstvergebene Order-ID:** Jede echte Order bekommt vorab eine
  eindeutige `newClientOrderId` (siehe `new_client_order_id`). Damit ist
  eine Order, die die Boerse gesehen haben *koennte*, nachtraeglich
  adressierbar - ohne sie muesste man raten oder ueber Zeitstempel
  suchen.
- **Pending-Datei:** Die ID wird zusammen mit minimalem Kontext
  geschrieben, BEVOR der Netzwerk-Call abgesetzt wird (siehe
  `PendingOrderStore`). Das ueberlebt auch einen Kill mitten im Request.
- **Ground Truth statt Vermutung:** `resolve_pending_order()` fragt die
  Boerse, was mit einer solchen ID tatsaechlich passiert ist. Dieselbe
  Funktion wird zur Laufzeit (binance_client.py, direkt nach dem
  Netzwerkfehler) UND beim naechsten Bot-Start (Reconciliation in den
  Strategien) verwendet - gleiches Prinzip wie bei grid_signals.py /
  trend_signals.py / order_utils.py: die Regel steht an genau einer
  Stelle, statt in mehreren Modulen leicht unterschiedlich nachgebaut zu
  werden.

Was dieses Modul bewusst NICHT tut: Ledger schreiben. Was ein
bestaetigter Fill bedeutet, weiss nur die jeweilige Strategie (DCA kennt
nur eine append-only Liste, Grid kennt Stufen, Trend kennt genau einen
Slot plus Stop-Order). Hier steht nur, WAS an der Boerse passiert ist -
nicht, was daraus im Ledger folgt.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .notifier import send_notification

logger = logging.getLogger("dca_bot")


# --- Order-Arten -----------------------------------------------------------

# Market-Order (Kauf oder Verkauf): "hat gewirkt" heisst hier, dass
# tatsaechlich eine Menge ausgefuehrt wurde.
KIND_MARKET = "market"

# Exchange-seitige STOP_LOSS_LIMIT-Order (siehe
# binance_client.place_stop_loss_limit_sell): "hat gewirkt" heisst hier
# etwas voellig anderes - naemlich, dass die Order im Orderbuch LIEGT.
# Eine frisch platzierte Stop-Order ist "NEW", und das ist der
# Erfolgsfall, nicht ein unklarer Zwischenzustand.
KIND_STOP_LOSS_LIMIT = "stop_loss_limit"


# --- Ergebnis der Ground-Truth-Rueckfrage ----------------------------------

# Die Order ist an der Boerse real angekommen und hat dort Wirkung:
# bei einer Market-Order wurde eine Menge ausgefuehrt, bei einer
# Stop-Order liegt sie im Orderbuch (oder hat bereits ausgeloest).
# Der Aufrufer darf sie behandeln, als waere der urspruengliche Call
# erfolgreich gewesen.
ORDER_CONFIRMED = "confirmed"

# Die Order existierte an der Boerse, hat aber nichts bewegt (terminaler
# Status ohne ausgefuehrte Menge, z.B. REJECTED/EXPIRED mit 0). Sicher
# als "kein Kauf/Verkauf stattgefunden" zu werten.
ORDER_WITHOUT_EFFECT = "without_effect"

# Binance kennt diese clientOrderId nicht (Fehlercode -2013) - die Order
# wurde nie angenommen. Ebenfalls sicher als "nie passiert" zu werten.
ORDER_UNKNOWN = "unknown"

# Unklarer Zustand: die Order ist noch live (NEW/PARTIALLY_FILLED, bei
# einer Market-Order unwahrscheinlich aber moeglich), oder die
# Status-Abfrage selbst ist fehlgeschlagen. Hier wird bewusst NICHT
# geraten - der Eintrag bleibt in der Pending-Datei stehen und wird beim
# naechsten Bot-Start erneut geprueft.
ORDER_UNCLEAR = "unclear"


# Ergebnis der reinen Nachschlage-Operation (siehe
# binance_client.get_order_by_client_id) - bewusst getrennt von der
# Bewertung oben: "gefunden" sagt noch nichts darueber aus, ob die Order
# gewirkt hat.
LOOKUP_FOUND = "found"
LOOKUP_NOT_FOUND = "not_found"
LOOKUP_FAILED = "failed"


# Statuswerte, nach denen sich an einer Order nichts mehr aendert.
# "EXPIRED_IN_MATCH" ist ein neuerer Binance-Status (Order wurde beim
# Matching verworfen, z.B. wegen Self-Trade-Prevention) - mit
# aufgefuehrt, damit er nicht faelschlich als "noch live" gilt.
TERMINAL_STATUSES = frozenset(
    {"FILLED", "CANCELED", "EXPIRED", "REJECTED", "EXPIRED_IN_MATCH"}
)

# Statuswerte, bei denen die Order an der Boerse noch aktiv ist.
LIVE_STATUSES = frozenset({"NEW", "PARTIALLY_FILLED", "PENDING_NEW", "PENDING_CANCEL"})


# Binance begrenzt newClientOrderId auf 36 Zeichen und einen festen
# Zeichenvorrat. Beides wird hier selbst geprueft, statt die Order von
# der Boerse ablehnen zu lassen: "trend-" + uuid4().hex waeren 38
# Zeichen - das faellt je nach Testnet-Stand erst im Echtgeld-Betrieb
# auf, und dann an der denkbar schlechtesten Stelle.
MAX_CLIENT_ORDER_ID_LENGTH = 36
_CLIENT_ORDER_ID_PATTERN = re.compile(r"^[\.A-Z\:/a-z0-9_-]{1,36}$")

# 24 Hex-Zeichen = 96 Bit Zufall. Reicht fuer praktische
# Kollisionsfreiheit um Groessenordnungen und laesst genug Platz fuer das
# laengste Bot-Praefix ("trend-" -> 30 Zeichen).
_UUID_HEX_CHARS = 24

PENDING_FILE_VERSION = 1


def new_client_order_id(bot_name: str) -> str:
    """
    Erzeugt eine eindeutige `newClientOrderId` mit Bot-Praefix, z.B.
    "grid-7f3a9c2e14b84d6fa0e51c83".

    Das Praefix ist reine Lesbarkeit im Nachhinein (in der Binance-
    Order-Historie ist auf einen Blick sichtbar, welcher Bot die Order
    ausgeloest hat) - die Eindeutigkeit kommt allein aus dem UUID-Anteil.
    """
    candidate = f"{bot_name}-{uuid.uuid4().hex[:_UUID_HEX_CHARS]}"
    if not _CLIENT_ORDER_ID_PATTERN.match(candidate):
        raise ValueError(
            f"Ungueltige clientOrderId '{candidate}' (aus bot_name '{bot_name}'): "
            "Binance erlaubt maximal 36 Zeichen aus [A-Za-z0-9.:/_-]."
        )
    return candidate


@dataclass
class PendingOrder:
    """
    Eine Order, die abgeschickt wurde (oder abgeschickt werden sollte),
    deren Ausgang aber noch nicht im Ledger verbucht ist.

    `context` ist bewusst ein offenes Dict und fuer binance_client.py
    vollstaendig OPAK: die Strategie uebergibt beim Platzieren, was sie
    spaeter zum Nachtragen braucht (Grid z.B. die Stufe, Trend die
    Trade-ID und den Ausstiegsgrund), und liest es beim Reconcile
    unveraendert zurueck. So bleibt "vor dem Netzwerk-Call schreiben"
    dort, wo der Netzwerk-Call stattfindet, und das bot-spezifische
    Wissen dort, wo es hingehoert.
    """

    client_order_id: str
    kind: str        # KIND_MARKET | KIND_STOP_LOSS_LIMIT
    symbol: str
    side: str        # "BUY" | "SELL"
    created_at: str  # ISO-8601, UTC
    context: dict = field(default_factory=dict)

    @staticmethod
    def new(
        client_order_id: str, kind: str, symbol: str, side: str, context: dict | None = None
    ) -> "PendingOrder":
        return PendingOrder(
            client_order_id=client_order_id,
            kind=kind,
            symbol=symbol,
            side=side,
            created_at=datetime.now(timezone.utc).isoformat(),
            context=dict(context or {}),
        )


class PendingOrderStore:
    """
    Kleine, separate JSON-Datei pro Bot (z.B.
    `data/pending_orders_grid.json`) mit allen Orders, deren Ausgang noch
    offen ist.

    Bewusst NICHT im jeweiligen Ledger untergebracht: Ein Pending-Eintrag
    ist kein Trade, sondern die Aussage "hier koennte ein Trade
    existieren". Ihn ins Ledger zu schreiben hiesse, Tageslimit,
    Stop-Loss-Kostenbasis und Positionslisten mit etwas zu fuettern, das
    es vielleicht gar nicht gibt.

    Im Normalbetrieb ist die Liste leer - ein Eintrag lebt typischerweise
    Millisekunden (schreiben, Order platzieren, entfernen). Bleibt einer
    stehen, ist das genau das Signal, auf das die Reconciliation beim
    naechsten Start wartet.

    Geschrieben wird atomar (temporaere Datei + `os.replace`): ein Kill
    mitten im Schreibvorgang darf keine halb geschriebene Datei
    hinterlassen, sonst ersetzt dieser Fix K2 nur durch ein neues
    Datenverlust-Loch.
    """

    def __init__(self, state_file: str, bot_name: str):
        self._path = Path(state_file)
        self._bot_name = bot_name
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def _read_payload(self) -> dict:
        if not self._path.exists():
            return {"version": PENDING_FILE_VERSION, "bot": self._bot_name, "orders": []}
        try:
            with self._path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Gleiche Haltung wie in den Ledgern: lieber mit leerem Stand
            # weiterlaufen als den Bot am Start scheitern lassen. Der
            # Unterschied wird hier aber als WARNUNG geloggt, weil eine
            # unlesbare Pending-Datei bedeuten kann, dass eine offene
            # Order-Frage verloren gegangen ist.
            logger.warning(
                "Pending-Orders-Datei '%s' fehlt oder ist beschaedigt - es kann "
                "keine offene Order-Frage aus einem frueheren Lauf geprueft "
                "werden. Bitte die letzten Orders bei Binance manuell "
                "gegenpruefen (python -m dca_bot.check_orders).",
                self._path,
            )
            return {"version": PENDING_FILE_VERSION, "bot": self._bot_name, "orders": []}

        if not isinstance(payload, dict) or not isinstance(payload.get("orders"), list):
            logger.warning(
                "Pending-Orders-Datei '%s' hat ein unerwartetes Format - wird "
                "wie eine leere Datei behandelt.",
                self._path,
            )
            return {"version": PENDING_FILE_VERSION, "bot": self._bot_name, "orders": []}

        stored_bot = payload.get("bot")
        if stored_bot and stored_bot != self._bot_name:
            # Praktisch nur durch vertauschte Pfade in der .env moeglich.
            # Nicht abbrechen (die Eintraege sind trotzdem echte offene
            # Fragen), aber sichtbar machen.
            logger.warning(
                "Pending-Orders-Datei '%s' wurde von Bot '%s' geschrieben, "
                "gelesen wird sie gerade von '%s' - stimmen die "
                "*_PENDING_ORDERS_FILE-Pfade in der .env?",
                self._path,
                stored_bot,
                self._bot_name,
            )
        return payload

    def _write_payload(self, orders: list[dict]) -> None:
        payload = {
            "version": PENDING_FILE_VERSION,
            "bot": self._bot_name,
            "orders": orders,
        }
        tmp_path = self._path.with_name(self._path.name + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self._path)

    def add(self, pending: PendingOrder) -> None:
        """
        Haelt eine Order fest, BEVOR sie abgeschickt wird.

        Der `fsync` in `_write_payload` ist hier der eigentliche Punkt:
        ohne ihn koennte der Eintrag noch im Page-Cache stehen, waehrend
        die Order bereits bei Binance liegt - bei einem Stromausfall
        genau der Zustand, den diese Datei verhindern soll.
        """
        payload = self._read_payload()
        orders = payload["orders"]
        orders.append(asdict(pending))
        self._write_payload(orders)

    def remove(self, client_order_id: str) -> None:
        """
        Entfernt einen Eintrag, nachdem sein Ausgang geklaert ist - egal
        mit welchem Ergebnis. Ein geklaerter Fall ist kein offener mehr,
        auch wenn die Order nie zustande kam.
        """
        payload = self._read_payload()
        remaining = [
            o for o in payload["orders"] if o.get("client_order_id") != client_order_id
        ]
        if len(remaining) == len(payload["orders"]):
            return
        self._write_payload(remaining)

    def all(self) -> list[PendingOrder]:
        """Alle offenen Eintraege, aelteste zuerst (Einfuegereihenfolge)."""
        result: list[PendingOrder] = []
        for raw in self._read_payload()["orders"]:
            if not isinstance(raw, dict) or not raw.get("client_order_id"):
                logger.warning(
                    "Unbrauchbarer Eintrag in '%s' wird uebersprungen: %r",
                    self._path,
                    raw,
                )
                continue
            context = raw.get("context")
            result.append(
                PendingOrder(
                    client_order_id=str(raw["client_order_id"]),
                    kind=str(raw.get("kind", KIND_MARKET)),
                    symbol=str(raw.get("symbol", "")),
                    side=str(raw.get("side", "")),
                    created_at=str(raw.get("created_at", "")),
                    context=context if isinstance(context, dict) else {},
                )
            )
        return result


def _executed_quantity(order: dict) -> float:
    """`executedQty` als float, 0.0 bei fehlendem/unlesbarem Wert."""
    try:
        return float(order.get("executedQty", 0.0) or 0.0)
    except (TypeError, ValueError):
        logger.warning(
            "Unlesbares executedQty in der Order-Antwort (%r) - fuer die "
            "Bewertung wird 0 angenommen.",
            order.get("executedQty"),
        )
        return 0.0


def classify_order_status(order: dict, kind: str) -> str:
    """
    Bewertet eine per `get_order()` geholte Order-Antwort.

    Reine Funktion (kein Netzwerk, kein Zustand) - der eigentliche Abruf
    liegt in binance_client.py, hier steht nur die Regel.

    Fuer eine MARKET-Order:
    - terminaler Status und `executedQty > 0` -> ORDER_CONFIRMED. Bewusst
      nicht nur `FILLED`: eine Market-Order, die nicht vollstaendig
      gefuellt werden kann, endet bei Binance als `EXPIRED` mit einer
      echten Teilmenge. Auf `FILLED` zu bestehen hiesse, diesen Fall fuer
      immer als "unklar" zu fuehren, obwohl die Information eindeutig
      vorliegt.
    - terminaler Status ohne ausgefuehrte Menge -> ORDER_WITHOUT_EFFECT.
    - alles andere (noch live) -> ORDER_UNCLEAR.

    Fuer eine STOP_LOSS_LIMIT-Order gilt eine ANDERE Regel: dort ist
    "NEW" der Erfolgsfall. Eine frisch platzierte Stop-Order soll offen
    im Orderbuch liegen und erst spaeter ausloesen - sie als "unklar" zu
    behandeln, nur weil sie nicht gefuellt ist, waere genau falsch
    herum. Entscheidend ist hier allein, ob die Order an der Boerse
    EXISTIERT; ob sie schon ausgeloest hat, klaert danach der bestehende
    Weg ueber `_check_exchange_stop_loss_fill` /
    `reconcile_on_startup()` im Trend-Bot.
    """
    status = str(order.get("status", "")).upper()
    executed_qty = _executed_quantity(order)

    if kind == KIND_STOP_LOSS_LIMIT:
        if status in LIVE_STATUSES or status == "FILLED" or executed_qty > 0:
            return ORDER_CONFIRMED
        if status in TERMINAL_STATUSES:
            # Storniert/abgelaufen ohne Wirkung: es liegt keine
            # Absicherung an der Boerse, und es wurde auch nichts
            # verkauft.
            return ORDER_WITHOUT_EFFECT
        return ORDER_UNCLEAR

    if status in TERMINAL_STATUSES:
        return ORDER_CONFIRMED if executed_qty > 0 else ORDER_WITHOUT_EFFECT
    return ORDER_UNCLEAR


def resolve_pending_order(client, pending: PendingOrder) -> tuple[str, dict | None]:
    """
    Fragt die Boerse, was mit `pending` tatsaechlich passiert ist, und
    gibt (Bewertung, Order-Antwort) zurueck.

    `client` ist ein TradingClient (bzw. im Test ein Fake mit derselben
    Schnittstelle) und muss `get_order_by_client_id()` anbieten.

    Diese Funktion ist die gemeinsame Grundlage von Teil A (zur Laufzeit,
    unmittelbar nach einem Netzwerkfehler in binance_client.py) und Teil
    B (beim Bot-Start, in den Strategien). Beide muessen zwingend
    dieselbe Bewertung vornehmen - saehe der Startup-Check einen Zustand
    anders als der Laufzeit-Check, haette man zwei Wahrheiten ueber
    denselben Trade.

    Wichtig: NUR der Binance-Fehlercode -2013 ("Order does not exist")
    gilt als "nie angenommen". Jeder andere Fehler (Rate-Limit,
    Timestamp-Drift, 5xx, Netzwerk) ist KEINE Aussage ueber die Order und
    fuehrt zu ORDER_UNCLEAR - siehe get_order_by_client_id(). Eine
    pauschale "Exception = nie passiert"-Regel waere exakt der Fehler,
    den K2 behebt, nur eine Ebene hoeher.
    """
    lookup_state, order = client.get_order_by_client_id(
        pending.symbol, pending.client_order_id
    )

    if lookup_state == LOOKUP_NOT_FOUND:
        return ORDER_UNKNOWN, None
    if lookup_state == LOOKUP_FAILED or order is None:
        return ORDER_UNCLEAR, None
    return classify_order_status(order, pending.kind), order


# Log-Marker fuer alles, was beim Bot-Start nachgetragen oder verworfen
# wird - bewusst derselbe Marker wie beim bereits bestehenden
# Stop-Order-Abgleich des Trend-Bots (trend_strategy.reconcile_on_startup),
# damit `grep REKONZILIATION logs/*.log` alle Korrekturen zeigt.
RECONCILIATION_PREFIX = "[REKONZILIATION] "


def reconcile_pending_orders(client, store, bot_logger, apply_confirmed) -> None:
    """
    Teil B des K2-Fixes: arbeitet beim Bot-Start alle offenen
    Order-Fragen aus einem frueheren Lauf ab.

    Der gemeinsame Rahmen steht hier, weil er fuer alle drei Bots
    identisch ist: nachfragen, bewerten, Eintrag aufraeumen oder
    eskalieren. Was ein bestaetigter Fill im jeweiligen Ledger bedeutet,
    weiss nur die Strategie - das uebernimmt `apply_confirmed(pending,
    order)`.

    `apply_confirmed` MUSS idempotent sein: derselbe Eintrag kann
    mehrfach ankommen, wenn der Bot zwischen dem Ledger-Schreibvorgang
    und dem Entfernen des Pending-Eintrags erneut stirbt. Die Strategien
    loesen das ueber die gespeicherte clientOrderId (siehe
    has_client_order_id() in den drei Ledgern).

    Wirft `apply_confirmed` eine Exception, bleibt der Pending-Eintrag
    bewusst STEHEN: ein nicht nachgetragener Trade ist genau der
    Zustand, den diese Datei festhalten soll - er darf nicht dadurch
    verloren gehen, dass das Nachtragen selbst gescheitert ist.
    """
    entries = store.all()
    if not entries:
        return

    bot_logger.warning(
        "%s%d offene Order-Frage(n) aus einem frueheren Lauf gefunden (%s) - "
        "sie werden jetzt gegen den tatsaechlichen Status bei Binance "
        "geprueft, bevor der erste regulaere Zyklus laeuft.",
        RECONCILIATION_PREFIX,
        len(entries),
        store.path,
    )

    for pending in entries:
        state, order = resolve_pending_order(client, pending)

        if state == ORDER_CONFIRMED and order is not None:
            try:
                apply_confirmed(pending, order)
            except Exception:
                bot_logger.exception(
                    "%sNachtragen der Order %s ist fehlgeschlagen - der "
                    "Eintrag bleibt in '%s' stehen und wird beim naechsten "
                    "Start erneut versucht.",
                    RECONCILIATION_PREFIX,
                    pending.client_order_id,
                    store.path,
                )
                send_notification(
                    f"[REKONZILIATION] {pending.symbol}: Order "
                    f"{pending.client_order_id} existiert an der Boerse, "
                    "konnte aber nicht ins Ledger nachgetragen werden. Siehe "
                    "Bot-Log, manuelle Pruefung noetig."
                )
                continue
            store.remove(pending.client_order_id)
            continue

        if state in (ORDER_UNKNOWN, ORDER_WITHOUT_EFFECT):
            bot_logger.info(
                "%sOrder %s (%s %s) hat die Boerse nie wirksam erreicht (%s) - "
                "kein Ledger-Eintrag noetig, Eintrag verworfen.",
                RECONCILIATION_PREFIX,
                pending.client_order_id,
                pending.side,
                pending.symbol,
                state,
            )
            store.remove(pending.client_order_id)
            continue

        bot_logger.error(
            "%sOrder %s (%s %s) ist weiterhin in unklarem Zustand - die "
            "Boerse gibt keine eindeutige Auskunft. Der Eintrag bleibt in "
            "'%s' stehen und wird beim naechsten Start erneut geprueft. "
            "Bitte manuell nachsehen (python -m dca_bot.check_orders).",
            RECONCILIATION_PREFIX,
            pending.client_order_id,
            pending.side,
            pending.symbol,
            store.path,
        )
        send_notification(
            f"[REKONZILIATION] {pending.symbol}: Order "
            f"{pending.client_order_id} ({pending.side}) weiterhin in "
            "unklarem Zustand. Bitte manuell bei Binance nachsehen."
        )

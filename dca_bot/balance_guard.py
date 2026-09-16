"""
Konsistenz-Check vor jedem Verkauf (Sicherheitsreview-Punkt W11).

Das Problem: DCA, Grid und Trend teilen sich EIN Binance-Konto und
handeln dasselbe Symbol (BTCUSDT), aber jeder fuehrt sein eigenes Ledger.
Die Zuordnung "dieses BTC gehoert dem Grid-Bot" existiert ausschliesslich
buchhalterisch - die Boerse kennt nur einen einzigen Bestand. Bisher hat
kein Bot vor einem Verkauf geprueft, ob seine Buchhaltung ueberhaupt zur
Realitaet passt. Ein Bot konnte damit Mengen verkaufen wollen, die es
nicht (mehr) gibt oder die faktisch einem anderen Bot gehoeren.

Zwei Pruefungen, bewusst mit UNTERSCHIEDLICHER Konsequenz:

**1. Deckungspruefung (hart).** Reicht das freie Guthaben fuer genau
diesen Verkauf? Wenn nicht, wuerde die Boerse die Order ohnehin ablehnen.
Statt sie abzuschicken und den Fehlschlag als generischen "echter Verkauf
fehlgeschlagen"-Fall zu behandeln (der genauso gut ein Netzwerkproblem
sein koennte), wird hier gar nicht erst verkauft - mit einer Meldung, die
die wahrscheinliche Ursache benennt.

**2. Buchhaltungspruefung (weich).** Deckt das Konto ueberhaupt die
Summe dessen ab, was im eigenen Ledger als offen steht? Wenn nicht, ist
etwas grundsaetzlich schief - aber der EINZELNE, gedeckte Verkauf laeuft
trotzdem. Gleiche Haltung wie beim Grid-Trendbruch-Stop-Loss (siehe
GridStopLoss): Ein Verkauf reduziert Risiko und Kapitalbindung, ihn zu
blockieren wuerde Assets stranden lassen, waehrend das eigentliche
Problem ungeloest bliebe. Gemeldet wird trotzdem laut.

**Warum die weiche Pruefung konservativ konstruiert ist:** Das freie
Guthaben enthaelt auch fremdes, nicht gebundenes BTC - `free +
eigene_gebundene_Menge` ist also eine OBERGRENZE dessen, was dem
pruefenden Bot gehoeren koennte. Liegt schon diese Obergrenze unter
seinem eigenen Anspruch, ist die Diskrepanz eindeutig. Das ergibt eine
Pruefung ohne Fehlalarme, die dafuer nicht jeden Fall erkennt - die
ehrliche Grenze dessen, was ein einzelner Bot feststellen kann, ohne die
strikte Trennung der Ledger aufzugeben (fremde Ledger zu lesen waere die
einzige Alternative und widerspricht dem Grundprinzip des Projekts).
Laufen alle drei Bots mit dieser Pruefung, meldet derjenige, der zuerst
zu kurz kommt.

Die Zuordnung "welche gebundene Menge gehoert wem" ist ueberhaupt nur
moeglich, weil der K2-Fix jeder Order eine selbstvergebene
`clientOrderId` mit Bot-Praefix gibt (siehe
pending_orders.new_client_order_id) - hier wird vorhandene Infrastruktur
genutzt statt neuer eingefuehrt.

Alle Funktionen hier sind rein (kein Netzwerk, kein Zustand) - gleiches
Muster wie order_utils.py und die drei `*_signals.py`. Die eigentlichen
Abrufe liegen in binance_client.py (`get_asset_balance`,
`get_open_orders`).
"""

from __future__ import annotations

from dataclasses import dataclass

# Statuswerte, bei denen eine Order noch im Orderbuch liegt und damit
# Menge bindet. Bewusst eine eigene, engere Liste als LIVE_STATUSES in
# pending_orders.py: dort geht es um "kann sich noch aendern", hier um
# "bindet gerade Guthaben". PENDING_CANCEL gehoert in beide - die Order
# ist bis zur Bestaetigung der Stornierung weiterhin aktiv.
_BINDING_STATUSES = frozenset({"NEW", "PARTIALLY_FILLED", "PENDING_NEW", "PENDING_CANCEL"})

# Relativer Toleranzanteil der Buchhaltungspruefung. 0,1 % liegt in der
# Groessenordnung einer einzelnen Handelsgebuehr - damit loest ein
# einzelner nicht verbuchter Gebuehrenrest keinen Fehlalarm aus. Die
# absolute Untergrenze (zwei stepSize-Schritte) faengt reine
# Rundungsreste bei sehr kleinen Bestaenden ab.
_RELATIVE_TOLERANCE = 0.001
_STEP_TOLERANCE_FACTOR = 2


# Ergebnis der Deckungspruefung.
SELL_OK = "ok"
SELL_INSUFFICIENT = "insufficient"
# Guthaben oder offene Orders konnten nicht abgefragt werden. Bewusst ein
# eigener Wert und NICHT mit SELL_INSUFFICIENT zusammengelegt: "ich
# konnte es nicht klaeren" ist keine Aussage ueber das Konto, und ein
# Netzwerkfehler darf keinen Stop-Loss-Ausstieg verhindern.
SELL_UNKNOWN = "unknown"


@dataclass(frozen=True)
class BalanceSnapshot:
    """
    Der Kontostand des Base-Assets aus Sicht EINES Bots, zu einem
    Zeitpunkt.

    `own_locked`/`foreign_locked` teilen `locked` danach auf, welcher Bot
    die bindende Order platziert hat (ueber das clientOrderId-Praefix).
    Summieren sie sich nicht zu `locked`, liegt der Rest in Orders, die
    dieses Projekt nie platziert hat (manueller Handel ueber die
    Boersen-Oberflaeche) - das ist gewollt sichtbar und faellt unter
    `foreign_locked`.
    """

    free: float
    locked: float
    own_locked: float
    foreign_locked: float

    @property
    def own_upper_bound(self) -> float:
        """
        Obergrenze dessen, was diesem Bot gehoeren KOENNTE: freies
        Guthaben plus die von ihm selbst gebundene Menge.

        Bewusst eine Obergrenze und keine exakte Zahl - siehe
        Modul-Docstring. `free` enthaelt auch fremdes Guthaben, die
        Pruefung schlaegt deshalb nur an, wenn die Diskrepanz eindeutig
        ist.
        """
        return self.free + self.own_locked


def _order_binds_base_asset(order: dict) -> bool:
    """
    Ob eine offene Order Base-Asset bindet.

    Nur VERKAUFS-Orders tun das (eine offene Kauf-Order bindet
    Quote-Waehrung, also USDT). Der Status muss ausserdem einer sein, bei
    dem die Order tatsaechlich noch im Orderbuch liegt.
    """
    if str(order.get("side", "")).strip().upper() != "SELL":
        return False
    return str(order.get("status", "")).strip().upper() in _BINDING_STATUSES


def _remaining_quantity(order: dict) -> float:
    """
    Noch offene Menge einer Order: `origQty` minus bereits ausgefuehrter
    Teil. Nur dieser Rest ist weiterhin gebunden - bei einer
    teilausgefuehrten Order waere `origQty` zu viel.
    """
    try:
        orig = float(order.get("origQty", 0.0) or 0.0)
        executed = float(order.get("executedQty", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(orig - executed, 0.0)


def split_locked_quantity(
    open_orders: list[dict] | None, bot_name: str
) -> tuple[float, float] | None:
    """
    Teilt die in offenen Verkaufs-Orders gebundene Base-Asset-Menge in
    `(eigene, fremde)` auf - anhand des clientOrderId-Praefixes aus K2.

    `None` bei `open_orders=None` (Abfrage gescheitert): dann ist die
    Aufteilung schlicht unbekannt, und der Aufrufer faellt auf die
    Pruefung ohne Order-Zuordnung zurueck.

    Eine Order ohne verwertbare `clientOrderId` gilt als FREMD. Das ist
    die konservative Richtung: sie als eigene zu zaehlen wuerde die
    Obergrenze `own_upper_bound` kuenstlich erhoehen und damit eine echte
    Diskrepanz verdecken - also genau das, was diese Pruefung finden soll.
    """
    if open_orders is None:
        return None

    prefix = f"{bot_name}-"
    own = 0.0
    foreign = 0.0
    for order in open_orders:
        if not _order_binds_base_asset(order):
            continue
        quantity = _remaining_quantity(order)
        if quantity <= 0:
            continue
        client_order_id = str(order.get("clientOrderId", "") or "")
        if client_order_id.startswith(prefix):
            own += quantity
        else:
            foreign += quantity
    return own, foreign


def build_snapshot(
    balance: tuple[float, float] | None,
    open_orders: list[dict] | None,
    bot_name: str,
) -> BalanceSnapshot | None:
    """
    Baut den Snapshot aus den beiden Abrufen in binance_client.py.

    `None`, wenn das Guthaben selbst nicht abrufbar war - ohne das gibt
    es nichts zu vergleichen. Sind nur die offenen Orders unbekannt, wird
    trotzdem ein Snapshot gebaut: die Deckungspruefung braucht nur `free`
    und bleibt damit wirksam. Die gebundene Menge gilt dann vollstaendig
    als fremd, wieder die konservative Richtung (siehe
    split_locked_quantity).
    """
    if balance is None:
        return None

    free, locked = balance
    split = split_locked_quantity(open_orders, bot_name)
    if split is None:
        own_locked, foreign_locked = 0.0, locked
    else:
        own_locked, foreign_locked = split

    return BalanceSnapshot(
        free=free,
        locked=locked,
        own_locked=own_locked,
        foreign_locked=foreign_locked,
    )


def tolerance_for(own_ledger_quantity: float, step_size: float) -> float:
    """
    Toleranz der Buchhaltungspruefung - siehe die Konstanten oben.

    Zwei Anteile, weil zwei verschiedene Abweichungen abzufangen sind:
    ein relativer fuer nicht verbuchte Gebuehrenreste (skaliert mit dem
    Bestand) und ein absoluter fuer Rundung auf die stepSize (skaliert
    nicht).
    """
    return max(
        _STEP_TOLERANCE_FACTOR * max(step_size, 0.0),
        own_ledger_quantity * _RELATIVE_TOLERANCE,
    )


def check_sell_coverage(
    snapshot: BalanceSnapshot | None, sell_quantity: float, step_size: float
) -> str:
    """
    Deckungspruefung (hart): Reicht das FREIE Guthaben fuer genau diesen
    Verkauf?

    Bewusst nur gegen `free` und nicht gegen `own_upper_bound`: Eine
    Menge, die in einer eigenen offenen Order steckt, ist in diesem
    Moment nicht verkaeuflich - sie muesste erst storniert werden. Genau
    das tut der Trend-Bot vor einem Exit (`_resolve_stop_order_before_close`),
    weshalb die Pruefung dort NACH dem Stornieren laufen muss.

    Die Toleranz nach unten ist hier Absicht: eine um Bruchteile einer
    stepSize zu grosse Verkaufsmenge wuerde von der Boerse abgelehnt,
    obwohl faktisch alles da ist. `place_market_sell` rundet ohnehin auf
    die stepSize ab.
    """
    if snapshot is None:
        return SELL_UNKNOWN
    if sell_quantity <= 0:
        return SELL_OK
    if snapshot.free + max(step_size, 0.0) >= sell_quantity:
        return SELL_OK
    return SELL_INSUFFICIENT


def ledger_exceeds_account(
    snapshot: BalanceSnapshot | None, own_ledger_quantity: float, step_size: float
) -> bool:
    """
    Buchhaltungspruefung (weich): Behauptet das eigene Ledger mehr, als
    auf dem Konto ueberhaupt fuer diesen Bot da sein KANN?

    `True` nur bei einer eindeutigen Diskrepanz - siehe
    `own_upper_bound` und Modul-Docstring. Ein nicht abrufbarer Snapshot
    ergibt `False`: keine Daten sind kein Befund.
    """
    if snapshot is None or own_ledger_quantity <= 0:
        return False
    return snapshot.own_upper_bound + tolerance_for(own_ledger_quantity, step_size) < own_ledger_quantity


def describe(snapshot: BalanceSnapshot, own_ledger_quantity: float) -> str:
    """Einzeiler fuer Log und Telegram - ueberall gleich formuliert."""
    return (
        f"Ledger offen: {own_ledger_quantity:.8f} | frei: {snapshot.free:.8f} | "
        f"gebunden gesamt: {snapshot.locked:.8f} (davon eigene Orders: "
        f"{snapshot.own_locked:.8f}, fremde: {snapshot.foreign_locked:.8f})"
    )

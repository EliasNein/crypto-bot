"""
Dünner Wrapper um die python-binance-Bibliothek.

Kapselt den Verbindungsaufbau zum Testnet und die eigentliche Order-Platzierung,
damit strategy.py sich nicht um API-Details kümmern muss und wir die
Trading-Logik einfacher testen/mocken können.
"""

from __future__ import annotations

import logging

import requests
from binance.client import Client
from binance.exceptions import (
    BinanceAPIException,
    BinanceOrderException,
    BinanceRequestException,
)

from .config import Config
from .notifier import send_notification
from .order_utils import SymbolTradingRules, quantize_price, quantize_quantity
from .pending_orders import (
    KIND_MARKET,
    KIND_STOP_LOSS_LIMIT,
    LOOKUP_FAILED,
    LOOKUP_FOUND,
    LOOKUP_NOT_FOUND,
    ORDER_CONFIRMED,
    ORDER_UNKNOWN,
    ORDER_WITHOUT_EFFECT,
    PendingOrder,
    PendingOrderStore,
    new_client_order_id,
    resolve_pending_order,
)

logger = logging.getLogger("dca_bot")

# Binance-Fehlercode fuer "Order does not exist". Der EINZIGE Code, aus
# dem geschlossen werden darf, dass eine Order nie angenommen wurde -
# jeder andere Fehler (Rate-Limit, Timestamp-Drift, 5xx) sagt nichts
# ueber die Order aus, siehe get_order_by_client_id().
ORDER_DOES_NOT_EXIST_CODE = -2013

# Fehler, die bedeuten "wir wissen nicht, ob die Order angekommen ist":
# python-binance setzt seine Requests ueber `requests` ab, ein Timeout
# oder Verbindungsabbruch kommt also als requests.exceptions.*, eine
# unlesbare Antwort als BinanceRequestException. Keine davon wurde vor
# dem K2-Fix gefangen - die Exception flog durch bis in die
# execute_once()-Schleife, und ein real ausgefuehrter Trade blieb
# unverbucht.
INCONCLUSIVE_REQUEST_ERRORS = (BinanceRequestException, requests.exceptions.RequestException)


def _parse_trading_rules(symbol: str, info: dict) -> SymbolTradingRules:
    """
    Zieht die relevanten Filter aus einer exchangeInfo-Antwort.

    Das Mindestvolumen heisst je nach API-Stand "NOTIONAL" (aktuell) oder
    "MIN_NOTIONAL" (aelter, u.a. auf manchen Testnet-Staenden) - beide
    werden akzeptiert, sonst wuerde die Pruefung je nach Umgebung
    stillschweigend ausfallen.

    Fehlen PRICE_FILTER oder LOT_SIZE, wird bewusst eine Exception
    geworfen statt mit 0 weiterzumachen: ohne diese beiden laesst sich
    keine Order sicher runden.
    """
    filters = {
        f.get("filterType"): f for f in info.get("filters", []) if isinstance(f, dict)
    }

    price_filter = filters.get("PRICE_FILTER")
    lot_size = filters.get("LOT_SIZE")
    if price_filter is None or lot_size is None:
        raise ValueError(
            f"exchangeInfo fuer '{symbol}' enthaelt kein PRICE_FILTER/LOT_SIZE - "
            "ohne tickSize und stepSize kann keine Order sicher gerundet werden."
        )

    notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}
    min_notional = float(notional.get("minNotional", 0.0))
    if min_notional <= 0:
        logger.info(
            "Kein Mindestvolumen-Filter fuer %s gemeldet - die entsprechende "
            "Pruefung vor einem Kauf entfaellt damit.",
            symbol,
        )

    return SymbolTradingRules(
        symbol=symbol,
        tick_size=float(price_filter["tickSize"]),
        step_size=float(lot_size["stepSize"]),
        min_notional=min_notional,
        base_asset=info["baseAsset"],
        quote_asset=info["quoteAsset"],
        quote_precision=int(info.get("quoteAssetPrecision", info.get("quotePrecision", 8))),
    )


class TradingClient:
    def __init__(self, config: Config, request_timeout_seconds: float | None = None):
        """
        `request_timeout_seconds` ersetzt den Standard-Timeout von
        python-binance (`Client.REQUEST_TIMEOUT`, 10 s) fuer JEDEN Request
        dieses Clients - inklusive des `ping()`, den der Konstruktor von
        `Client` selbst absetzt. `None` laesst den Bibliotheks-Default
        unveraendert; das ist der Fall fuer DCA, Trend und Allocator.
        Gesetzt wird der Wert bisher nur vom Grid-Bot (siehe main_grid.py).
        """
        self._config = config
        self._client = Client(
            config.api_key,
            config.api_secret,
            testnet=config.use_testnet,
            requests_params=(
                {"timeout": request_timeout_seconds}
                if request_timeout_seconds is not None
                else None
            ),
        )
        # Handelsregeln je Symbol (exchangeInfo), einmalig beim ersten
        # Bedarf geholt und danach fuer die Lebensdauer dieses Clients
        # behalten - siehe get_symbol_trading_rules(). Bewusst pro
        # Instanz statt modulglobal: jeder Bot-Prozess erzeugt genau
        # einen TradingClient, "pro Instanz" ist hier also faktisch "pro
        # Prozess", aber ohne globalen Zustand, der zwischen Tests
        # durchschlagen wuerde.
        self._trading_rules: dict[str, SymbolTradingRules] = {}
        # Offene Order-Fragen dieses Bots (siehe pending_orders.py,
        # Sicherheitsreview-Punkt K2). Der Allocator setzt
        # `pending_orders_file` bewusst auf "" - er platziert nie Orders,
        # und die place_*-Methoden weisen diesen Zustand aktiv zurueck,
        # statt still ohne Absicherung zu handeln.
        pending_file = getattr(config, "pending_orders_file", "")
        self._pending_store: PendingOrderStore | None = (
            PendingOrderStore(pending_file, getattr(config, "bot_name", "bot"))
            if pending_file
            else None
        )
        logger.info(
            "Binance-Client initialisiert (testnet=%s, Request-Timeout %s s)",
            config.use_testnet,
            request_timeout_seconds
            if request_timeout_seconds is not None
            else f"{Client.REQUEST_TIMEOUT} (Standard)",
        )

    @property
    def pending_orders(self) -> PendingOrderStore:
        """
        Die Pending-Orders-Ablage dieses Bots (siehe pending_orders.py).

        Wird von der Reconciliation beim Bot-Start gebraucht (Teil B des
        K2-Fixes, siehe die reconcile_pending_orders()-Methoden in den
        Strategien). Ein Zugriff auf einem Client ohne konfigurierte
        Datei ist ein Programmierfehler, kein Laufzeitzustand - deshalb
        eine Exception statt eines stillen Ersatzobjekts.
        """
        if self._pending_store is None:
            raise ValueError(
                "Fuer diesen Bot ist keine Pending-Orders-Datei konfiguriert "
                "(pending_orders_file ist leer) - er ist nicht zum Platzieren "
                "von Orders vorgesehen."
            )
        return self._pending_store

    def get_symbol_trading_rules(self, symbol: str) -> SymbolTradingRules:
        """
        Liefert die echten Handelsregeln des Symbols (tickSize, stepSize,
        Mindestvolumen, Base-/Quote-Asset) aus exchangeInfo.

        Wird beim ersten Aufruf pro Symbol einmal von der Boerse geholt
        und danach aus dem Instanz-Cache bedient - NICHT bei jedem
        Zyklus neu, das waere ein unnoetiger API-Aufruf alle paar
        Minuten fuer Werte, die sich praktisch nie aendern.

        Bewusst KEIN TTL/Refresh: Binance aendert diese Filter aeusserst
        selten, die Bots werden regelmaessig neu gestartet, und eine
        veraltete stepSize wuerde sich als abgelehnte Order zeigen - die
        in beiden Bots inzwischen sauber eskaliert, statt still zu
        scheitern.

        Schlaegt der Abruf fehl (Netzwerk, API-Fehler, unbekanntes
        Symbol), wird der Fehler bewusst WEITERGEREICHT statt auf
        Default-Werte auszuweichen: ohne diese Werte laesst sich eine
        Order nicht sicher quantisieren, und eine stillschweigend
        falsch gerundete Menge ist schlimmer als ein abgebrochener
        Zyklus. Die Aufrufer holen die Regeln deshalb, BEVOR sie eine
        Order platzieren - ein Fehlschlag bricht dann folgenlos ab,
        statt eine bereits ausgefuehrte Order unverbucht zu lassen.
        """
        cached = self._trading_rules.get(symbol)
        if cached is not None:
            return cached

        try:
            info = self._client.get_symbol_info(symbol)
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.error(
                "Handelsregeln (exchangeInfo) fuer %s konnten nicht abgerufen "
                "werden: %s - es wird KEINE Order platziert, da Menge/Preis "
                "ohne diese Werte nicht sicher gerundet werden koennen.",
                symbol,
                exc,
            )
            raise
        except INCONCLUSIVE_REQUEST_ERRORS as exc:
            # Netzwerkfehler wird genauso weitergereicht - die Regeln
            # werden bewusst VOR der ersten Order geholt, ein Fehlschlag
            # bricht den Zyklus also folgenlos ab (keine Order existiert).
            logger.error(
                "Handelsregeln (exchangeInfo) fuer %s konnten wegen eines "
                "Verbindungsfehlers nicht abgerufen werden (%s) - es wird "
                "KEINE Order platziert.",
                symbol,
                type(exc).__name__,
            )
            raise

        if not info:
            raise ValueError(
                f"Binance liefert keine Handelsregeln fuer das Symbol '{symbol}' - "
                "ist es richtig geschrieben und auf dieser Umgebung handelbar?"
            )

        rules = _parse_trading_rules(symbol, info)
        self._trading_rules[symbol] = rules
        logger.info(
            "Handelsregeln fuer %s geladen: tickSize %s, stepSize %s, "
            "Mindestvolumen %s %s (Base: %s).",
            symbol,
            rules.tick_size,
            rules.step_size,
            rules.min_notional,
            rules.quote_asset,
            rules.base_asset,
        )
        return rules

    def get_current_price(self, symbol: str) -> float:
        """Aktuellen Preis für ein Symbol abfragen (z.B. BTCUSDT)."""
        ticker = self._client.get_symbol_ticker(symbol=symbol)
        return float(ticker["price"])

    def get_quote_balance(self, quote_asset: str) -> float:
        """Verfügbares Guthaben der Quote-Währung (z.B. USDT) abfragen."""
        balance = self._client.get_asset_balance(asset=quote_asset)
        return float(balance["free"]) if balance else 0.0

    def get_asset_balance(self, asset: str) -> tuple[float, float] | None:
        """
        Freies und gebundenes Guthaben eines Assets als `(free, locked)` -
        Grundlage des Konsistenz-Checks vor jedem Verkauf
        (Sicherheitsreview-Punkt W11, siehe balance_guard.py).

        `locked` ist die Menge, die aktuell in offenen Orders steckt -
        für den Vergleich wichtig, weil sie zwar existiert, aber nicht
        verkäuflich ist.

        Gibt `None` zurück (statt 0.0 oder einer Exception), wenn die
        Abfrage scheitert, und das ist eine bewusste Unterscheidung: `0.0`
        hieße "kein Guthaben da" und würde jeden Verkauf blockieren,
        `None` heißt "ich konnte es nicht klären". Nur der erste Fall ist
        eine Aussage über das Konto. Gleiche Haltung wie bei
        `LOOKUP_FAILED` in get_order_by_client_id(): ein gescheiterter
        Abruf ist kein Befund.
        """
        try:
            balance = self._client.get_asset_balance(asset=asset)
        except (
            BinanceAPIException,
            BinanceOrderException,
            *INCONCLUSIVE_REQUEST_ERRORS,
        ) as exc:
            logger.warning(
                "Guthaben für %s konnte nicht abgefragt werden (%s) - der "
                "Konsistenz-Check vor dem Verkauf entfällt in diesem Zyklus.",
                asset,
                type(exc).__name__,
            )
            return None

        if not balance:
            # Binance meldet ein nie gehaltenes Asset gar nicht. Das ist
            # eine echte Aussage ("nichts davon da"), kein Fehlschlag.
            return 0.0, 0.0

        try:
            return float(balance.get("free", 0.0)), float(balance.get("locked", 0.0))
        except (TypeError, ValueError):
            logger.warning(
                "Guthaben-Antwort für %s ist unlesbar (%r) - der "
                "Konsistenz-Check vor dem Verkauf entfällt in diesem Zyklus.",
                asset,
                balance,
            )
            return None

    def get_open_orders(self, symbol: str) -> list[dict] | None:
        """
        Alle aktuell offenen Orders eines Symbols - für die Frage, welche
        gebundene Menge zu WELCHEM Bot gehört (W11).

        Möglich ist diese Zuordnung nur wegen des K2-Fixes: jede Order
        dieses Projekts trägt eine selbstvergebene `clientOrderId` mit
        Bot-Präfix (`grid-…`, `trend-…`, `dca-…`, siehe
        pending_orders.new_client_order_id). Damit lässt sich ohne
        Zugriff auf fremde Ledger unterscheiden, ob eine offene
        Verkaufs-Order die eigene ist - und damit, ob das dort gebundene
        Base-Asset überhaupt für einen eigenen Verkauf zur Verfügung
        stünde.

        Gibt wie get_asset_balance() `None` zurück, wenn die Abfrage
        scheitert: eine leere Liste hieße "keine offenen Orders", und das
        ist etwas anderes als "unbekannt".
        """
        try:
            orders = self._client.get_open_orders(symbol=symbol)
        except (
            BinanceAPIException,
            BinanceOrderException,
            *INCONCLUSIVE_REQUEST_ERRORS,
        ) as exc:
            logger.warning(
                "Offene Orders für %s konnten nicht abgefragt werden (%s) - "
                "die Zuordnung gebundener Mengen zu den einzelnen Bots "
                "entfällt in diesem Zyklus.",
                symbol,
                type(exc).__name__,
            )
            return None

        if not isinstance(orders, list):
            return None
        return [o for o in orders if isinstance(o, dict)]

    def get_order_by_client_id(
        self, symbol: str, client_order_id: str
    ) -> tuple[str, dict | None]:
        """
        Fragt eine Order über die von uns selbst vergebene
        `newClientOrderId` ab - der Ground-Truth-Check des K2-Fixes.

        Gibt ein Tupel (Nachschlage-Ergebnis, Order-Antwort) zurück:

        - LOOKUP_FOUND: Binance kennt die Order, `order` enthält ihren
          Status. Was daraus folgt, entscheidet
          `pending_orders.classify_order_status()`.
        - LOOKUP_NOT_FOUND: Binance kennt diese clientOrderId NICHT
          (Fehlercode -2013) - die Order wurde nie angenommen.
        - LOOKUP_FAILED: Die Abfrage selbst ist gescheitert. Das ist
          KEINE Aussage über die Order.

        Die Unterscheidung zwischen den letzten beiden ist der Kern
        dieser Methode: NUR -2013 bedeutet "nie passiert". Jeden anderen
        Fehler (Rate-Limit, Timestamp-Drift, 5xx, Netzwerk) als "nie
        passiert" zu verbuchen wäre exakt der Fehler, den K2 behebt -
        nur eine Ebene höher und mit demselben Ergebnis: ein real
        ausgeführter Trade ohne Ledger-Eintrag.
        """
        try:
            order = self._client.get_order(
                symbol=symbol, origClientOrderId=client_order_id
            )
        except BinanceAPIException as exc:
            if getattr(exc, "code", None) == ORDER_DOES_NOT_EXIST_CODE:
                logger.info(
                    "Binance kennt die clientOrderId %s nicht (Code %s) - die "
                    "Order wurde nie angenommen.",
                    client_order_id,
                    ORDER_DOES_NOT_EXIST_CODE,
                )
                return LOOKUP_NOT_FOUND, None
            logger.error(
                "Status-Abfrage für clientOrderId %s fehlgeschlagen (Code %s): "
                "%s - daraus folgt NICHTS über die Order.",
                client_order_id,
                getattr(exc, "code", "?"),
                exc,
            )
            return LOOKUP_FAILED, None
        except (BinanceOrderException, *INCONCLUSIVE_REQUEST_ERRORS) as exc:
            # Nur der Exception-TYP, nicht str(exc): bei einem
            # requests-Fehler steht die vollständige Request-URL in der
            # Message, und bei einer signierten GET-Abfrage hängt die
            # HMAC-Signatur als Query-Parameter daran. Sie ist zwar kein
            # wiederverwendbares Geheimnis (einmalig, an Timestamp
            # gebunden, das Secret lässt sich daraus nicht herleiten) -
            # aber Logs dieses Projekts werden bei Meilensteinen ins
            # öffentliche Repo archiviert, und der Typ allein reicht für
            # die Fehlersuche völlig aus. Gleiche Haltung wie in
            # notifier.py (Sicherheitsreview-Punkt K5).
            logger.error(
                "Status-Abfrage für clientOrderId %s fehlgeschlagen (%s) - "
                "daraus folgt NICHTS über die Order.",
                client_order_id,
                type(exc).__name__,
            )
            return LOOKUP_FAILED, None

        return LOOKUP_FOUND, order

    def get_order_with_fills(self, symbol: str, order: dict) -> dict:
        """
        Ergänzt eine per `get_order()` geholte Order-Antwort um ihre
        einzelnen Teilausführungen (`fills`), damit die bestehende
        Gebührenkorrektur aus order_utils.py unverändert darauf läuft.

        Hintergrund: `get_order()`-Antworten enthalten KEINE Fills - das
        ist die in trading-bot-projekt.md (K3) als "bewusst offen"
        notierte Restlücke. Für den Reconciliation-Pfad wiegt sie
        schwerer als für den ursprünglichen Fall: ein nachgetragener KAUF
        käme sonst mit der Brutto-Menge ins Ledger, und über genau diese
        Menge liefen später Stop-Loss-Order und Verkauf - also zurück in
        die K3-Falle ("verkaufe mehr, als da ist").

        `myTrades` liefert die fehlenden `commission`/`commissionAsset`
        pro Teilausführung. Scheitert die Abfrage, wird die Order
        unverändert zurückgegeben: ein Ledger-Eintrag mit minimal zu
        hoher Menge ist deutlich besser als gar kein Ledger-Eintrag -
        und die Warnung macht sichtbar, dass hier nachgerechnet gehört.
        """
        if order.get("fills"):
            return order

        order_id = order.get("orderId")
        if order_id is None:
            return order

        try:
            # `orderId` steht nicht im python-binance-Docstring, wird aber
            # als **params durchgereicht und vom Endpoint unterstützt.
            trades = self._client.get_my_trades(symbol=symbol, orderId=order_id)
        except (
            BinanceAPIException,
            BinanceOrderException,
            *INCONCLUSIVE_REQUEST_ERRORS,
        ) as exc:
            logger.warning(
                "Teilausführungen (myTrades) zu Order %s konnten nicht geholt "
                "werden (%s) - der Ledger-Eintrag entsteht ohne "
                "Gebührenkorrektur und ist damit um die Handelsgebühr zu "
                "günstig/zu hoch. Bitte bei Gelegenheit gegenprüfen.",
                order_id,
                type(exc).__name__,
            )
            return order

        if not isinstance(trades, list) or not trades:
            return order

        enriched = dict(order)
        enriched["fills"] = [t for t in trades if isinstance(t, dict)]
        logger.info(
            "Gebührendaten zu Order %s über myTrades nachgeladen (%d "
            "Teilausführung(en)).",
            order_id,
            len(enriched["fills"]),
        )
        return enriched

    def _place_order(
        self,
        *,
        kind: str,
        symbol: str,
        side: str,
        label: str,
        context: dict | None,
        request,
    ) -> dict | None:
        """
        Gemeinsamer Ablauf aller drei `place_*`-Methoden (K2).

        `request` ist eine Funktion, die die selbstvergebene
        clientOrderId entgegennimmt und den eigentlichen API-Aufruf
        macht. Die Reihenfolge ist der ganze Punkt:

        1. clientOrderId erzeugen und MIT Kontext in die
           Pending-Orders-Datei schreiben - VOR dem Netzwerk-Call. Nur so
           überlebt die Information einen Prozess-Kill mitten im Request.
        2. Order abschicken.
        3. Ausgang klären und den Pending-Eintrag wieder entfernen.

        Die drei Fehlerklassen werden dabei streng getrennt:

        - BinanceAPIException/BinanceOrderException: Binance HAT
          geantwortet und die Order abgelehnt. Definitives Nein, der
          Pending-Eintrag kann weg.
        - Netzwerk-/Verbindungsfehler: keine Antwort, keine Aussage -
          es wird nachgefragt (siehe _resolve_after_network_error).
        - Alles andere fliegt weiter: ein Programmierfehler soll nicht
          als "Order fehlgeschlagen" getarnt werden.
        """
        if self._pending_store is None:
            raise ValueError(
                f"{label} kann nicht platziert werden: für diesen Bot ist keine "
                "Pending-Orders-Datei konfiguriert (pending_orders_file ist "
                "leer). Ohne sie gäbe es keine Absicherung gegen eine "
                "ausgeführte, aber unverbuchte Order."
            )

        client_order_id = new_client_order_id(self._config.bot_name)
        pending = PendingOrder.new(
            client_order_id=client_order_id,
            kind=kind,
            symbol=symbol,
            side=side,
            context=context,
        )
        self._pending_store.add(pending)

        try:
            order = request(client_order_id)
        except (BinanceAPIException, BinanceOrderException) as exc:
            self._pending_store.remove(client_order_id)
            logger.error("Fehler beim Platzieren der %s: %s", label, exc)
            return None
        except INCONCLUSIVE_REQUEST_ERRORS as exc:
            return self._resolve_after_network_error(pending, label, exc)

        self._pending_store.remove(client_order_id)
        logger.info("%s erfolgreich platziert: %s", label, order)
        return order

    def _resolve_after_network_error(
        self, pending: PendingOrder, label: str, exc: Exception
    ) -> dict | None:
        """
        Klärt nach einem Netzwerkfehler, ob die Order die Börse doch
        erreicht hat - der Kern des K2-Fixes.

        Vor diesem Fix gab es diesen Pfad gar nicht: die Exception flog
        bis in die execute_once()-Schleife, wurde dort als "unerwarteter
        Fehler im Zyklus" geloggt, und eine real gefüllte Order blieb
        für immer unverbucht. Einfach `None` zurückzugeben wäre aber
        genauso falsch - das sähe für die Strategie aus wie ein sauberer
        "kein Handelsbedarf"-Fall.

        Drei Ausgänge:

        - Order ist angekommen und hat gewirkt -> die echten Order-Daten
          zurückgeben, als wäre der ursprüngliche Call erfolgreich
          gewesen. Die Strategie schreibt daraufhin ganz normal einen
          korrekten Ledger-Eintrag, ohne von dem Zwischenfall zu wissen.
        - Order nie angenommen oder ohne Wirkung -> `None` wie bisher,
          der Pending-Eintrag kann weg.
        - Unklar -> NICHT raten. Deutliche Fehlermeldung samt
          clientOrderId, Telegram, und der Pending-Eintrag BLEIBT
          stehen, damit die Reconciliation beim nächsten Bot-Start
          erneut fragt.
        """
        # Nur der Exception-TYP (siehe Begründung in
        # get_order_by_client_id): requests-Fehlermeldungen tragen die
        # vollständige Request-URL.
        logger.error(
            "Verbindungsfehler beim Platzieren der %s für %s (%s) - die Order "
            "kann die Börse trotzdem erreicht haben. Frage den tatsächlichen "
            "Status zur clientOrderId %s ab.",
            label,
            pending.symbol,
            type(exc).__name__,
            pending.client_order_id,
        )

        state, order = resolve_pending_order(self, pending)

        if state == ORDER_CONFIRMED and order is not None:
            self._pending_store.remove(pending.client_order_id)
            logger.warning(
                "%s %s (clientOrderId %s) ist trotz des Verbindungsfehlers an "
                "der Börse angekommen - sie wird jetzt regulär verbucht, als "
                "wäre der ursprüngliche Aufruf erfolgreich gewesen.",
                label,
                pending.symbol,
                pending.client_order_id,
            )
            return order

        if state in (ORDER_UNKNOWN, ORDER_WITHOUT_EFFECT):
            self._pending_store.remove(pending.client_order_id)
            logger.warning(
                "%s für %s (clientOrderId %s) hat die Börse nicht wirksam "
                "erreicht (%s) - es hat nachweislich kein Trade stattgefunden.",
                label,
                pending.symbol,
                pending.client_order_id,
                state,
            )
            return None

        # ORDER_UNCLEAR - der einzige Fall, in dem der Eintrag bleibt.
        logger.error(
            "UNKLARER ORDER-ZUSTAND: %s für %s konnte nach einem "
            "Verbindungsfehler nicht geklärt werden. Die clientOrderId %s "
            "steht in '%s' und wird beim nächsten Bot-Start erneut geprüft. "
            "Bis dahin ist offen, ob diese Order an der Börse existiert - "
            "bitte manuell nachsehen (python -m dca_bot.check_orders).",
            label,
            pending.symbol,
            pending.client_order_id,
            self._pending_store.path,
        )
        send_notification(
            f"[ORDER-UNKLAR] {pending.symbol}: {label} in unklarem Zustand "
            f"(clientOrderId {pending.client_order_id}). Es ist offen, ob die "
            "Order an der Börse existiert. Sie steht in der "
            "pending-orders-Datei und wird beim nächsten Bot-Start erneut "
            "geprüft - bitte trotzdem manuell nachsehen."
        )
        return None

    def place_market_buy(
        self, symbol: str, quote_order_qty: float, context: dict | None = None
    ) -> dict | None:
        """
        Platziert einen Market-Buy über einen festen Quote-Betrag
        (z.B. "kaufe für 15 USDT Bitcoin", unabhängig vom aktuellen Preis).

        Gibt None zurück, wenn Trading deaktiviert ist (Sicherheits-Schalter)
        oder ein Fehler auftritt - der Bot soll nie wegen eines API-Fehlers
        abstürzen, sondern sauber loggen und weiterlaufen/abbrechen können.

        Anders als bei den Verkaufs-Methoden greifen hier NICHT stepSize
        oder tickSize: der Betrag ist in der Quote-Waehrung angegeben
        (quoteOrderQty), nicht als Base-Asset-Menge. Was hier zaehlt, ist
        die Praezision der Quote-Waehrung und das Mindestvolumen - Letzteres
        wird bewusst selbst geprueft (mit klarer Meldung), statt die Order
        von der Boerse ablehnen zu lassen. Die Pruefung laeuft absichtlich
        VOR dem Dry-Run-Zweig, damit ein zu klein konfigurierter Betrag
        schon in der Paper-Trade-Phase auffaellt und nicht erst beim
        Live-Gang.

        `context` wird von der aufrufenden Strategie mitgegeben und
        unveraendert in die Pending-Orders-Datei geschrieben (siehe
        _place_order und pending_orders.py) - er enthaelt, was die
        Strategie braucht, um den Kauf spaeter nachzutragen, falls die
        Antwort der Boerse nie ankommt. Fuer diese Methode ist er opak.
        """
        rules = self.get_symbol_trading_rules(symbol)
        quote_order_qty = quantize_quantity(
            quote_order_qty, 10 ** -rules.quote_precision, round_down=True
        )

        if rules.min_notional > 0 and quote_order_qty < rules.min_notional:
            logger.error(
                "Kaufbetrag %.8f %s liegt unter dem Mindestvolumen der Boerse "
                "(%.8f %s) fuer %s - es wird keine Order platziert.",
                quote_order_qty,
                rules.quote_asset,
                rules.min_notional,
                rules.quote_asset,
                symbol,
            )
            return None

        if not self._config.trading_enabled:
            logger.info(
                "[DRY-RUN] Würde Market-Buy platzieren: %s für %.2f Quote-Einheiten",
                symbol,
                quote_order_qty,
            )
            return None

        return self._place_order(
            kind=KIND_MARKET,
            symbol=symbol,
            side="BUY",
            label="Order",
            context=context,
            request=lambda client_order_id: self._client.order_market_buy(
                symbol=symbol,
                quoteOrderQty=quote_order_qty,
                newClientOrderId=client_order_id,
            ),
        )

    def place_market_sell(
        self, symbol: str, quantity: float, context: dict | None = None
    ) -> dict | None:
        """
        Platziert einen Market-Sell über eine exakte Menge des Base-Assets
        (z.B. "verkaufe 0.0002 BTC") - z.B. zum Schließen einer einzelnen
        Grid-Position. Gleiche Sicherheits-/Fehlerlogik wie place_market_buy:
        Dry-Run-Schalter und niemals ein Absturz wegen eines API-Fehlers.

        Die Menge wird vorher auf ein gueltiges Vielfaches der stepSize
        ABGERUNDET (nie auf) - eine zu hohe Menge wuerde die Boerse
        ablehnen bzw. mehr verkaufen, als die Position hergibt.

        Zu `context` siehe place_market_buy: die Strategie legt dort ab,
        welche Position dieser Verkauf schliesst, damit ein verlorener
        Antwortweg spaeter aufloesbar bleibt.
        """
        rules = self.get_symbol_trading_rules(symbol)
        quantity = quantize_quantity(quantity, rules.step_size, round_down=True)
        if quantity <= 0:
            logger.error(
                "Verkaufsmenge fuer %s ist nach dem Abrunden auf die stepSize "
                "(%.8f) 0 - es wird keine Order platziert.",
                symbol,
                rules.step_size,
            )
            return None

        if not self._config.trading_enabled:
            logger.info(
                "[DRY-RUN] Würde Market-Sell platzieren: %s, Menge %.8f",
                symbol,
                quantity,
            )
            return None

        return self._place_order(
            kind=KIND_MARKET,
            symbol=symbol,
            side="SELL",
            label="Sell-Order",
            context=context,
            request=lambda client_order_id: self._client.order_market_sell(
                symbol=symbol,
                quantity=quantity,
                newClientOrderId=client_order_id,
            ),
        )

    def place_stop_loss_limit_sell(
        self,
        symbol: str,
        quantity: float,
        stop_price: float,
        limit_price: float,
        context: dict | None = None,
    ) -> dict | None:
        """
        Platziert eine echte, exchange-seitige STOP_LOSS_LIMIT-Sell-Order:
        löst aus, sobald der Marktpreis `stop_price` erreicht, wird dann
        als Limit-Order zu `limit_price` (leicht unter `stop_price`, siehe
        TREND_STOP_LIMIT_OFFSET_PCT) ins Orderbuch gelegt. Anders als der
        software-interne Stop-Loss (der nur wirkt, solange der Bot-Prozess
        läuft) übernimmt die Börse selbst die Überwachung - schützt eine
        offene Position auch bei Bot-/Internet-/Stromausfall.

        Gleiche Sicherheits-/Fehlerlogik wie die übrigen place_*-Methoden:
        Dry-Run-Schalter und niemals ein Absturz wegen eines API-Fehlers.

        Auch diese Order läuft über die Pending-Orders-Absicherung (K2),
        obwohl sie selbst kein Geld bewegt: geht ihre Antwort verloren,
        liegt eine Stop-Order an der Börse, von der das Ledger nichts
        weiß - und `_ensure_stop_loss_protection()` würde im nächsten
        Zyklus eine ZWEITE Order über dieselbe Menge platzieren.
        """
        # Menge und beide Preise werden gegen die echten Handelsregeln des
        # Symbols quantisiert (PRICE_FILTER.tickSize bzw. LOT_SIZE.stepSize,
        # siehe get_symbol_trading_rules) - das ersetzt die frueher hier
        # stehende feste Rundung auf 2 Nachkommastellen, die je nach Symbol
        # zu "Filter failure: PRICE_FILTER" fuehren konnte.
        rules = self.get_symbol_trading_rules(symbol)
        quantity = quantize_quantity(quantity, rules.step_size, round_down=True)
        stop_price = quantize_price(stop_price, rules.tick_size)
        limit_price = quantize_price(limit_price, rules.tick_size)

        if quantity <= 0:
            logger.error(
                "Menge fuer die Stop-Loss-Order (%s) ist nach dem Abrunden auf "
                "die stepSize (%.8f) 0 - es wird keine Order platziert.",
                symbol,
                rules.step_size,
            )
            return None

        if not self._config.trading_enabled:
            logger.info(
                "[DRY-RUN] Würde Stop-Loss-Order platzieren: %s, Menge %.8f, "
                "Stop %.2f, Limit %.2f",
                symbol,
                quantity,
                stop_price,
                limit_price,
            )
            return None

        return self._place_order(
            kind=KIND_STOP_LOSS_LIMIT,
            symbol=symbol,
            side="SELL",
            label="Stop-Loss-Order",
            context=context,
            request=lambda client_order_id: self._client.create_order(
                symbol=symbol,
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_STOP_LOSS_LIMIT,
                timeInForce=Client.TIME_IN_FORCE_GTC,
                quantity=quantity,
                stopPrice=stop_price,
                price=limit_price,
                newClientOrderId=client_order_id,
            ),
        )

    def cancel_order(self, symbol: str, order_id: str) -> dict | None:
        """
        Storniert eine offene Order (z.B. eine Stop-Loss-Order vor einem
        Signal-basierten Exit). Ein Fehlschlag - z.B. weil die Order
        zwischenzeitlich bereits gefüllt oder storniert wurde (Binance
        liefert dafür typischerweise Fehlercode -2011 "Unknown order
        sent"), aber auch ein echter transienter Fehler - wird hier
        bewusst NICHT unterschieden (jeder Fehler wird einheitlich als
        Warnung geloggt, nicht als Fehler, und gibt None zurück). Der
        Grund: der numerische Fehlercode allein ist keine zuverlässige
        Grundlage für eine Sell/Nicht-Sell-Entscheidung (z.B. ob die
        Position bereits verkauft ist) - das übernimmt die aufrufende
        Seite (trend_strategy.py, _resolve_stop_order_before_close)
        robuster per erneuter get_order_status()-Abfrage der tatsächlichen
        Order-Ground-Truth statt Code-Interpretation hier. Der Code wird
        hier nur mitgeloggt, für die Fehlersuche im Log.
        """
        try:
            result = self._client.cancel_order(symbol=symbol, orderId=order_id)
            logger.info("Order %s storniert: %s", order_id, result)
            return result
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.warning(
                "Stornieren der Order %s fehlgeschlagen (Code %s, evtl. "
                "bereits gefüllt/storniert, evtl. transient): %s",
                order_id,
                getattr(exc, "code", "?"),
                exc,
            )
            return None
        except INCONCLUSIVE_REQUEST_ERRORS as exc:
            # Vor dem K2-Fix flog ein Verbindungsfehler hier bis in die
            # Zyklus-Schleife und beendete den Zyklus hart. Damit wurde
            # die sorgfältig gebaute "uncertain"-Behandlung in
            # trend_strategy._resolve_stop_order_before_close() gar nicht
            # erst erreicht. Jetzt wird daraus ein regulärer Fehlschlag,
            # den die aufrufende Seite per Status-Nachfrage auflöst.
            logger.warning(
                "Stornieren der Order %s wegen eines Verbindungsfehlers "
                "fehlgeschlagen (%s) - der tatsächliche Status wird von der "
                "aufrufenden Seite nachgeprüft.",
                order_id,
                type(exc).__name__,
            )
            return None

    def get_order_status(self, symbol: str, order_id: str) -> dict | None:
        """
        Fragt den aktuellen Status einer Order ab (z.B. um zu prüfen, ob
        eine Stop-Loss-Order zwischenzeitlich - auch während einer
        Bot-Downtime - gefüllt wurde). Gibt None zurück statt einer
        Exception, falls die Abfrage fehlschlägt.
        """
        try:
            return self._client.get_order(symbol=symbol, orderId=order_id)
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.error("Fehler beim Abfragen des Order-Status für %s: %s", order_id, exc)
            return None
        except INCONCLUSIVE_REQUEST_ERRORS as exc:
            # Siehe cancel_order: ein Verbindungsfehler darf hier nicht
            # den Zyklus sprengen, sondern muss als "Status unbekannt"
            # ankommen - genau der Fall, für den die aufrufende Seite
            # den uncertain_cycles-Zähler hat.
            logger.error(
                "Order-Status für %s konnte wegen eines Verbindungsfehlers "
                "nicht abgefragt werden (%s) - Status bleibt unbekannt.",
                order_id,
                type(exc).__name__,
            )
            return None

"""
Dünner Wrapper um die python-binance-Bibliothek.

Kapselt den Verbindungsaufbau zum Testnet und die eigentliche Order-Platzierung,
damit strategy.py sich nicht um API-Details kümmern muss und wir die
Trading-Logik einfacher testen/mocken können.
"""

from __future__ import annotations

import logging

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

from .config import Config
from .order_utils import SymbolTradingRules, quantize_price, quantize_quantity

logger = logging.getLogger("dca_bot")


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
    def __init__(self, config: Config):
        self._config = config
        self._client = Client(
            config.api_key,
            config.api_secret,
            testnet=config.use_testnet,
        )
        # Handelsregeln je Symbol (exchangeInfo), einmalig beim ersten
        # Bedarf geholt und danach fuer die Lebensdauer dieses Clients
        # behalten - siehe get_symbol_trading_rules(). Bewusst pro
        # Instanz statt modulglobal: jeder Bot-Prozess erzeugt genau
        # einen TradingClient, "pro Instanz" ist hier also faktisch "pro
        # Prozess", aber ohne globalen Zustand, der zwischen Tests
        # durchschlagen wuerde.
        self._trading_rules: dict[str, SymbolTradingRules] = {}
        logger.info(
            "Binance-Client initialisiert (testnet=%s)", config.use_testnet
        )

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

    def place_market_buy(self, symbol: str, quote_order_qty: float) -> dict | None:
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

        try:
            order = self._client.order_market_buy(
                symbol=symbol,
                quoteOrderQty=quote_order_qty,
            )
            logger.info("Order erfolgreich platziert: %s", order)
            return order
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.error("Fehler beim Platzieren der Order: %s", exc)
            return None

    def place_market_sell(self, symbol: str, quantity: float) -> dict | None:
        """
        Platziert einen Market-Sell über eine exakte Menge des Base-Assets
        (z.B. "verkaufe 0.0002 BTC") - z.B. zum Schließen einer einzelnen
        Grid-Position. Gleiche Sicherheits-/Fehlerlogik wie place_market_buy:
        Dry-Run-Schalter und niemals ein Absturz wegen eines API-Fehlers.

        Die Menge wird vorher auf ein gueltiges Vielfaches der stepSize
        ABGERUNDET (nie auf) - eine zu hohe Menge wuerde die Boerse
        ablehnen bzw. mehr verkaufen, als die Position hergibt.
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

        try:
            order = self._client.order_market_sell(
                symbol=symbol,
                quantity=quantity,
            )
            logger.info("Sell-Order erfolgreich platziert: %s", order)
            return order
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.error("Fehler beim Platzieren der Sell-Order: %s", exc)
            return None

    def place_stop_loss_limit_sell(
        self, symbol: str, quantity: float, stop_price: float, limit_price: float
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

        try:
            order = self._client.create_order(
                symbol=symbol,
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_STOP_LOSS_LIMIT,
                timeInForce=Client.TIME_IN_FORCE_GTC,
                quantity=quantity,
                stopPrice=stop_price,
                price=limit_price,
            )
            logger.info("Stop-Loss-Order erfolgreich platziert: %s", order)
            return order
        except (BinanceAPIException, BinanceOrderException) as exc:
            logger.error("Fehler beim Platzieren der Stop-Loss-Order: %s", exc)
            return None

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

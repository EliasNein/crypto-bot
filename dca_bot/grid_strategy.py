"""
Spot-Grid-Trading-Strategie.

Kauft, wenn der Preis auf eine Grid-Stufe fällt, und verkauft genau diese
Position wieder, wenn der Preis auf die nächsthöhere Stufe steigt. Kein
Hebel, kein Liquidationsrisiko (Spot only). Siehe trading-bot-projekt.md
Abschnitt 5 für die Recherche dazu: Erwartungswert vor Gebühren ist
akademisch mathematisch null - der Sinn dieser Strategie liegt in der
einfachen, latenzunkritischen Umsetzung, nicht in überlegener Rendite.
Haupt-Risiko ist ein Trendbruch (siehe GridStopLoss in grid_risk.py).

Komplett eigenständig von strategy.py (DCA-Bot) - kein geteilter Zustand.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .binance_client import TradingClient
from .grid_config import GridConfig
from .grid_risk import GridLedger, GridPosition, GridStopLoss
from .grid_signals import compute_grid_levels, find_triggered_buy_levels, is_sell_target_hit
from .notifier import send_notification
from .order_utils import net_executed_quantity, net_proceeds, quantize_quantity
from .risk import KillSwitch

logger = logging.getLogger("grid_bot")


class GridTradingStrategy:
    def __init__(self, config: GridConfig, client: TradingClient):
        self._config = config
        self._client = client
        self._ledger = GridLedger(config.state_file)
        self._kill_switch = KillSwitch(config.kill_switch_file, env_var_name="GRID_BOT_HALT")
        self._stop_loss = GridStopLoss(
            config.lower_limit, config.stop_loss_pct, config.stop_loss_state_file
        )
        self._levels = compute_grid_levels(
            config.lower_limit, config.upper_limit, config.grid_spacing_pct
        )
        # Referenzpreis für die Crossing-Erkennung beim Kauf (siehe
        # _process_buys) - bewusst nur im Prozessspeicher: nach einem
        # Neustart wird im ersten Zyklus nur neu referenziert statt
        # rückwirkend zu handeln, das ist sicher und einfach zu erklären.
        self._last_seen_price: float | None = None
        # IDs von Positionen, fuer die ein fehlgeschlagener ECHTER Verkauf
        # bereits per Telegram gemeldet wurde (siehe _report_failed_sell) -
        # bewusst nur im Prozessspeicher, wie _last_seen_price.
        self._failed_sell_notified: set[str] = set()
        logger.info(
            "Grid initialisiert: %d Stufen von %.2f bis %.2f (Abstand %.2f%%, "
            "max. Kapitalbindung ca. %.2f)",
            len(self._levels),
            self._levels[0],
            self._levels[-1],
            config.grid_spacing_pct,
            (len(self._levels) - 1) * config.amount_per_level,
        )

    def _process_sells(self, price: float) -> None:
        """
        Verkauft jede offene Position, deren individuelles Sell-Target
        erreicht ist - unabhängig vom Trendbruch-Stop-Loss.

        Ob dabei tatsächlich eine echte Order platziert wird, hängt NICHT
        nur am aktuellen Trading-Modus, sondern zusätzlich am `dry_run`-Flag
        der jeweiligen Position im Ledger (siehe README.md Abschnitt 8.4):
        eine im Dry-Run "gekaufte" Position existiert an der Börse gar
        nicht und darf deshalb auch nach einem Umschalten auf echtes
        Trading niemals real verkauft werden.
        """
        open_positions = self._ledger.open_positions()
        if not any(
            is_sell_target_hit(price, r["target_sell_price"]) for r in open_positions
        ):
            return

        # Handelsregeln bewusst VOR dem ersten Verkaufsversuch holen
        # (danach aus dem Cache): schlägt der Abruf fehl, bricht der
        # Zyklus ab, ohne dass eine Order existiert. Nach einem
        # ausgeführten Verkauf hier eine Exception zu riskieren, würde die
        # Position unverkauft im Ledger stehen lassen, obwohl sie weg ist.
        rules = self._client.get_symbol_trading_rules(self._config.symbol)

        for record in open_positions:
            if not is_sell_target_hit(price, record["target_sell_price"]):
                continue

            position_dry_run = record.get("dry_run")
            if position_dry_run is None:
                # Ledger-Eintrag ohne dry_run-Feld (praktisch nur durch
                # manuelles Editieren möglich - GridPosition schreibt es
                # immer). Hier wird bewusst NICHT geraten: "echt"
                # anzunehmen hieße, nie gekaufte Assets verkaufen zu
                # wollen; "Dry-Run" anzunehmen hieße, eine echte Position
                # mit erfundenem Erlös als geschlossen zu buchen, während
                # die Assets an der Börse liegen bleiben. Beides ist
                # schlechter als abzuwarten.
                logger.warning(
                    "[GRID-POSITION-UNKLAR] Position %s (Stufe %s) hat kein "
                    "dry_run-Feld im Ledger - Verkaufsziel erreicht, aber "
                    "kein Verkaufsversuch. Position bleibt offen, bitte "
                    "manuell prüfen (python -m dca_bot.audit_positions).",
                    record["id"],
                    record.get("level_index", "?"),
                )
                continue

            if position_dry_run and self._config.trading_enabled:
                # place_market_sell() prüft nur config.trading_enabled, NICHT
                # das Positions-Flag - ein Aufruf wäre hier also eine echte
                # Order für eine nie gekaufte Position. Deshalb gar nicht
                # erst aufrufen, sondern direkt simulieren.
                logger.warning(
                    "[DRY-RUN-POSITION] Position %s (Stufe %d) wurde im "
                    "Dry-Run eröffnet, Verkauf bleibt simuliert, unabhängig "
                    "vom aktuellen Trading-Modus.",
                    record["id"],
                    record["level_index"],
                )
                order = None
            else:
                order = self._client.place_market_sell(self._config.symbol, record["quantity"])
                if order is None and self._config.trading_enabled:
                    # Echter Verkaufsversuch bei der Börse fehlgeschlagen -
                    # anders als im Dry-Run (wo None der Normalfall ist).
                    # Kein erfundener Erlös, kein record_sell(): die
                    # Position bleibt OFFEN und wird im nächsten Zyklus
                    # erneut versucht (das Sell-Target ist ja weiterhin
                    # erreicht).
                    self._report_failed_sell(record, price)
                    continue

            if order is not None:
                # Netto, also abzüglich der in USDT abgerechneten
                # Verkaufsgebühr - cummulativeQuoteQty ist der Bruttoerlös.
                proceeds = net_proceeds(order, rules, fallback=record["quantity"] * price)
            else:
                proceeds = record["quantity"] * price
            realized_pnl = proceeds - record["quote_spent"]

            sold_at = datetime.now(timezone.utc).isoformat()
            self._ledger.record_sell(record["id"], price, sold_at, realized_pnl)
            self._failed_sell_notified.discard(record["id"])

            logger.info(
                "Grid-Verkauf: Stufe %d, Kauf @ %.2f -> Verkauf @ %.2f, realisiert %.2f",
                record["level_index"],
                record["buy_price"],
                price,
                realized_pnl,
            )
            tag = "[GRID-VERKAUF]" if order is not None else "[GRID-VERKAUF DRY-RUN]"
            send_notification(
                f"{tag} Stufe {record['level_index']}: {record['quantity']:.8f} "
                f"{self._config.symbol} @ {price:.2f} verkauft "
                f"(Kauf @ {record['buy_price']:.2f}), realisiert: {realized_pnl:+.2f}"
            )

    def _report_failed_sell(self, record: dict, price: float) -> None:
        """
        Meldet einen fehlgeschlagenen ECHTEN Verkauf (siehe _process_sells).

        Anders als beim Trend-Bot muss hier keine Absicherung
        wiederhergestellt werden: der Grid-Bot platziert nie eine
        exchange-seitige Stop-Order und storniert vor einem Verkauf
        entsprechend auch keine. Die Position ist nach dem Fehlschlag also
        exakt so abgesichert wie eine Sekunde davor und wird im nächsten
        Zyklus (alle GRID_INTERVAL_MINUTES) automatisch erneut zum Verkauf
        angeboten, da ihr Sell-Target weiterhin erreicht ist.

        Die Telegram-Meldung geht bewusst nur EINMAL pro Prozesslauf und
        Position raus: bei einer dauerhaften Ursache (z.B. zu wenig
        Guthaben) würde der 5-Minuten-Zyklus sonst im Minutentakt
        benachrichtigen. Ins Log geht dagegen jeder einzelne Fehlschlag.
        Der Zustand lebt nur im Prozessspeicher (wie _last_seen_price) -
        nach einem Neustart wird einmalig erneut gemeldet.
        """
        logger.warning(
            "[GRID-VERKAUF-FEHLGESCHLAGEN] Echter Verkauf für Stufe %d "
            "fehlgeschlagen (Position %s, Preis ~%.2f) - Position bleibt "
            "OFFEN im Ledger, kein Erlös verbucht. Der nächste Zyklus "
            "versucht es erneut.",
            record["level_index"],
            record["id"],
            price,
        )

        if record["id"] in self._failed_sell_notified:
            return
        self._failed_sell_notified.add(record["id"])
        send_notification(
            f"[GRID-VERKAUF-FEHLGESCHLAGEN] Stufe {record['level_index']}: "
            f"echter Verkauf @ {price:.2f} fehlgeschlagen. Position bleibt "
            "offen, kein Erlös verbucht - siehe Bot-Log."
        )

    def _process_buys(self, price: float) -> None:
        """
        Kauft an jeder Grid-Stufe, die der Preis seit dem letzten Zyklus
        tatsächlich durchquert hat (nicht: irgendeine Stufe irgendwo
        unterhalb des aktuellen Preises - siehe Crossing-Erkennung unten).
        """
        occupied_levels = {
            r["level_index"] for r in self._ledger.open_positions()
        }
        triggered_levels = find_triggered_buy_levels(
            self._levels, self._last_seen_price, price, occupied_levels
        )
        if not triggered_levels:
            return

        # Siehe _process_sells: Regeln vor der ersten Order holen, damit
        # ein Fehlschlag folgenlos abbricht statt einen bereits
        # ausgeführten Kauf unverbucht zu lassen.
        rules = self._client.get_symbol_trading_rules(self._config.symbol)

        for level_index in triggered_levels:
            order = self._client.place_market_buy(self._config.symbol, self._config.amount_per_level)

            if order is None and self._config.trading_enabled:
                # Echter Kaufversuch bei der Börse fehlgeschlagen - analog
                # zum DCA-Bot keine Ledger-Eintragung, kein simulierter Erfolg.
                logger.error(
                    "Echter Grid-Kauf fehlgeschlagen für Stufe %d (Preis ~%.2f).",
                    level_index,
                    price,
                )
                send_notification(
                    f"[GRID-FEHLER] Echter Kauf fehlgeschlagen für Stufe "
                    f"{level_index} (Preis ~{price:.2f}). Siehe Bot-Log."
                )
                continue

            if order is not None:
                # Menge abzüglich der in BTC abgezogenen Kaufgebühr - genau
                # diese Menge steht später für den Verkauf zur Verfügung.
                quantity = net_executed_quantity(
                    order, rules, fallback=self._config.amount_per_level / price
                )
                quote_spent = float(order.get("cummulativeQuoteQty", self._config.amount_per_level))
            else:
                # Dry-Run: keine echte Gebühr bekannt, deshalb keine
                # geschätzte abgezogen - die Menge wird aber quantisiert,
                # damit simulierte und echte Werte vergleichbar bleiben.
                quantity = quantize_quantity(
                    self._config.amount_per_level / price, rules.step_size
                )
                quote_spent = self._config.amount_per_level

            position = GridPosition.new(
                level_index=level_index,
                buy_price=price,
                target_sell_price=self._levels[level_index + 1],
                quantity=quantity,
                quote_spent=quote_spent,
                dry_run=not self._config.trading_enabled,
            )
            self._ledger.record_buy(position)

            logger.info(
                "Grid-Kauf: Stufe %d @ %.2f (Ziel-Verkauf @ %.2f)",
                level_index,
                price,
                position.target_sell_price,
            )
            tag = "[GRID-KAUF]" if order is not None else "[GRID-KAUF DRY-RUN]"
            send_notification(
                f"{tag} Stufe {level_index}: {quantity:.8f} {self._config.symbol} "
                f"@ {price:.2f} (Ziel-Verkauf @ {position.target_sell_price:.2f})"
            )

    def execute_once(self) -> None:
        """Führt genau einen Grid-Zyklus aus: Preis holen, Verkäufe prüfen,
        Trendbruch-Stop-Loss prüfen, ggf. Käufe prüfen."""
        self._kill_switch.check()

        price = self._client.get_current_price(self._config.symbol)
        logger.info("Aktueller Preis für %s: %.2f", self._config.symbol, price)

        # Stop-Loss-Status wird zuerst ermittelt, aber Verkäufe laufen davon
        # unabhängig weiter (siehe GridStopLoss-Docstring in grid_risk.py) -
        # sie reduzieren Risiko/Kapitalbindung statt sie zu erhöhen.
        stop_loss_active = self._stop_loss.is_triggered(self._config.symbol, price)

        self._process_sells(price)

        if not stop_loss_active:
            # Erneute Prüfung unmittelbar vor neuen Käufen, damit ein
            # Notaus, der während Preisabfrage/Verkäufen ausgelöst wurde,
            # sie noch verhindert statt erst im nächsten Zyklus zu greifen.
            self._kill_switch.check()
            self._process_buys(price)

        # Referenzpreis immer aktualisieren (auch bei aktivem Stop-Loss),
        # damit die Crossing-Erkennung beim nächsten Kauf-Check den
        # tatsächlich zuletzt beobachteten Preis verwendet.
        self._last_seen_price = price

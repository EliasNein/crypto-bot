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

from . import symbol_guard
from .balance_guard import (
    SELL_INSUFFICIENT,
    BalanceSnapshot,
    build_snapshot,
    check_sell_coverage,
    describe,
    ledger_exceeds_account,
)
from .binance_client import TradingClient
from .grid_config import GridConfig
from .grid_risk import GridLedger, GridPosition, GridStopLoss
from .grid_signals import compute_grid_levels, find_triggered_buy_levels, is_sell_target_hit
from .notifier import send_notification
from .order_utils import (
    average_fill_price,
    is_dust,
    net_executed_quantity,
    net_proceeds,
    open_quantity,
    quantize_quantity,
    received_base_quantity,
    sold_fully,
)
from .pending_orders import (
    RECONCILIATION_PREFIX,
    ManualReviewRequired,
    PendingOrder,
    executed_quantity,
    is_partial_fill,
    reconcile_pending_orders,
)
from .risk import KillSwitch
from .startup_checks import report_ledger_vs_account

logger = logging.getLogger("grid_bot")

# close_reason einer Position, deren Kauf nur teilweise und unter dem
# Mindestvolumen ausgefuehrt wurde (T2, 16.10.2026, siehe GridPosition).
CLOSE_REASON_DUST = "dust"
# close_reason einer Position, deren Rest nach einem Teilverkauf unter dem
# Mindestvolumen liegt (Runde 2, 19.10.2026, Entscheidung D3).
CLOSE_REASON_DUST_AFTER_SELL = "dust_after_sell"

# Ergebnisse von _book_sell (Runde 2, 19.10.2026).
SELL_CLOSED = "closed"
SELL_PARTIAL = "partial"
SELL_DUST = "dust_after_sell"


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
        # IDs echter Positionen, deren Verkauf wegen deaktiviertem Trading
        # bereits per Telegram gemeldet wurde (siehe
        # _report_sell_blocked_by_dry_run) - gleiche Kurzlebigkeit.
        self._dry_run_block_notified: set[str] = set()
        # Ob die Buchhaltungs-Diskrepanz (W11, siehe balance_guard.py)
        # in diesem Prozesslauf bereits per Telegram gemeldet wurde. Der
        # Grid-Bot prueft alle GRID_INTERVAL_MINUTES - bei einer
        # dauerhaften Ursache waere das sonst eine Nachricht im
        # Minutentakt. Ins Log geht sie weiterhin bei jedem Zyklus.
        # Gleiche Ueberlegung und gleiche Kurzlebigkeit wie
        # _failed_sell_notified.
        self._balance_mismatch_notified = False
        # clientOrderIds, zu denen die laufende Reconciliation bereits per
        # Telegram eskaliert hat - bei 5-Minuten-Takt sonst eine Meldung
        # pro Zyklus (siehe reconcile_pending_orders).
        self._pending_escalated: set[str] = set()
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
        der jeweiligen Position im Ledger (siehe trading-bot-projekt.md 7.2):
        eine im Dry-Run "gekaufte" Position existiert an der Börse gar
        nicht und darf deshalb auch nach einem Umschalten auf echtes
        Trading niemals real verkauft werden. Umgekehrt wird eine ECHTE
        Position bei deaktiviertem Trading weder verkauft noch
        simuliert geschlossen - sie bleibt offen und wird gemeldet
        (siehe _report_sell_blocked_by_dry_run).
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

        # Konsistenz-Check vor dem Verkauf (W11, siehe balance_guard.py).
        # Einmal pro Zyklus abgefragt, nicht pro Position: die Schleife
        # unten kann mehrere Positionen schliessen, und zwei API-Aufrufe
        # pro Position waeren unnoetige Last fuer eine Zahl, die sich
        # zwischen zwei Verkaeufen nur um genau die bekannte, selbst
        # verkaufte Menge aendert - die wird darum unten mitgefuehrt.
        snapshot = self._account_snapshot(rules)
        self._warn_on_ledger_mismatch(snapshot, open_positions, rules)
        sold_this_cycle = 0.0

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

            if not position_dry_run and not self._config.trading_enabled:
                # Spiegelbild zu K4 direkt darunter: eine ECHTE Position,
                # waehrend der Bot im Dry-Run laeuft. place_market_sell()
                # wuerde hier nur simulieren und None liefern - bis zu
                # diesem Fix wurde daraufhin ein Erloes aus
                # quantity * price erfunden und die Position geschlossen,
                # obwohl das BTC weiter an der Boerse liegt. Die Stufe galt
                # danach als frei und wurde erneut gekauft, und der
                # Bestandsabgleich sah nichts (er meldet nur ein Ledger,
                # das MEHR beansprucht, als da ist). Deshalb: gar nicht erst
                # aufrufen, Position offen lassen, deutlich melden.
                self._report_sell_blocked_by_dry_run(record, price)
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
                # Sperre (Systemcheck vom 27.09.2026, K-B): Steht fuer diese
                # Position noch ein Verkauf mit ungeklaertem Ausgang in der
                # Pending-Datei, wird NICHT erneut verkauft. Bis dahin
                # verkaufte der naechste Zyklus mit neuer clientOrderId ein
                # zweites Mal - war der erste Verkauf durchgegangen, kam die
                # Menge aus dem Bestand eines anderen Bots, und die
                # Deckungspruefung unten konnte das nicht erkennen (sie
                # sieht nur `free`, nicht, wem es gehoert). Die
                # Reconciliation zu Beginn jedes Zyklus klaert den Eintrag,
                # sobald Binance wieder antwortet.
                if self._sell_is_pending(record):
                    continue

                # Rest eines Teilverkaufs unter dem Mindestvolumen (Runde 2):
                # jeder Verkaufsversuch kaeme als Ablehnung zurueck. Normal
                # schliesst _book_sell ihn sofort - hier landet er nur, wenn
                # der Prozess zwischen Teilbuchung und Abschluss gestorben ist.
                if self._close_rest_if_dust(record, price, rules):
                    continue

                # Deckungsprüfung unmittelbar vor der Order (W11): reicht
                # das freie Guthaben für genau diesen Verkauf? Wenn nicht,
                # würde die Börse ablehnen - und der Fehlschlag sähe im
                # Log aus wie ein Netzwerkproblem, obwohl die Ursache
                # feststeht. Lieber gar nicht erst verkaufen und das
                # deutlich sagen.
                if not self._sell_is_covered(record, snapshot, sold_this_cycle, rules):
                    continue

                # `context` landet VOR dem Netzwerk-Call in der
                # Pending-Orders-Datei (siehe
                # binance_client._place_order): geht die Antwort
                # verloren, weiß die Reconciliation beim nächsten Start,
                # WELCHE Position dieser Verkauf geschlossen hat. Ohne
                # das bliebe die Position offen und der nächste Zyklus
                # würde ein zweites Mal verkaufen.
                #
                # Verkauft wird die OFFENE Menge (Runde 2): nach einem
                # Teilverkauf ist ein Teil von `quantity` schon weg, und auf
                # dem geteilten Konto deckte das freie BTC eines anderen Bots
                # den Fehlbetrag still ab.
                order = self._client.place_market_sell(
                    self._config.symbol,
                    open_quantity(record),
                    context={"position_id": record["id"], "price": price},
                )
                if order is None and self._config.trading_enabled:
                    # Echter Verkaufsversuch bei der Börse fehlgeschlagen -
                    # anders als im Dry-Run (wo None der Normalfall ist).
                    # Kein erfundener Erlös, kein record_sell(): die
                    # Position bleibt OFFEN und wird im nächsten Zyklus
                    # erneut versucht (das Sell-Target ist ja weiterhin
                    # erreicht) - aber nur nach einer eindeutigen
                    # Ablehnung. War der Ausgang unklar, steht der
                    # Pending-Eintrag noch, und _sell_is_pending() sperrt
                    # den nächsten Versuch, bis er geklärt ist (K-B).
                    self._report_failed_sell(record, price)
                    continue

                # Der Verkauf ist durch - diese Menge steht dem nächsten
                # Durchlauf dieser Schleife nicht mehr zur Verfügung. Seit
                # Runde 2 die AUSGEFUEHRTE Menge, nicht die bestellte: nach
                # einem Teilverkauf liegt der Rest noch auf dem Konto.
                sold_this_cycle += (
                    executed_quantity(order) if order is not None else open_quantity(record)
                )

            if order is not None:
                outcome, sell_price, realized_pnl, sold_qty = self._book_sell(
                    record, order, rules, price
                )
                # Erst mit dem Verkauf im Ledger ist die Order-Frage erledigt
                # (W-A) - auch bei einem Teilverkauf: der ist verbucht, der
                # Rest wird mit einer NEUEN Order verkauft.
                self._client.confirm_booked(order.get("clientOrderId"))
                if outcome != SELL_CLOSED:
                    continue
                logger.info(
                    "Grid-Verkauf: Stufe %d, Kauf @ %.2f -> Verkauf @ %.2f, realisiert %.2f",
                    record["level_index"],
                    record["buy_price"],
                    sell_price,
                    realized_pnl,
                )
                send_notification(
                    f"[GRID-VERKAUF] Stufe {record['level_index']}: {sold_qty:.8f} "
                    f"{self._config.symbol} @ {sell_price:.2f} verkauft "
                    f"(Kauf @ {record['buy_price']:.2f}), realisiert: {realized_pnl:+.2f}"
                )
                continue

            # Dry-Run-Position: simulierter Verkauf zum beobachteten Preis.
            # Eine Dry-Run-Position hat nie einen Teilverkauf (kein Fill).
            sell_price = price
            proceeds = record["quantity"] * price
            realized_pnl = proceeds - record["quote_spent"]
            self._ledger.record_sell(
                record["id"], sell_price, datetime.now(timezone.utc).isoformat(), realized_pnl, None
            )
            self._failed_sell_notified.discard(record["id"])

            logger.info(
                "Grid-Verkauf: Stufe %d, Kauf @ %.2f -> Verkauf @ %.2f, realisiert %.2f",
                record["level_index"],
                record["buy_price"],
                sell_price,
                realized_pnl,
            )
            send_notification(
                f"[GRID-VERKAUF DRY-RUN] Stufe {record['level_index']}: {record['quantity']:.8f} "
                f"{self._config.symbol} @ {sell_price:.2f} verkauft "
                f"(Kauf @ {record['buy_price']:.2f}), realisiert: {realized_pnl:+.2f}"
            )

    def _book_sell(
        self,
        record: dict,
        order: dict,
        rules,
        price: float,
        client_order_id: str | None = None,
        prefix: str = "",
    ) -> tuple[str, float, float, float]:
        """
        Verbucht einen ausgefuehrten Market-Verkauf nach seiner AUSGEFUEHRTEN
        Menge (Runde 2, 19.10.2026) - gemeinsam fuer den direkten Pfad und die
        Reconciliation. Bis dahin wurde jeder Verkauf ueber die volle Menge
        als geschlossen gebucht, eine Teilfuellung meldete nur
        [GRID-TEILFUELLUNG-UNGEBUCHT].

        Drei Zweige, entschieden ueber die Menge (order_utils.sold_fully):

        - Vollstaendig (Rest < stepSize): Position geschlossen. sell_price ist
          der mengengewichtete Bruttodurchschnitt aller Teile, realized_pnl
          die Summe der Netto-Erloese minus quote_spent.
        - Teilweise: record_partial_exit (idempotent ueber die orderId), die
          Position bleibt mit dem Rest offen und belegt ihre Stufe; der
          naechste Zyklus verkauft den Rest, solange das Ziel erreicht ist.
        - Teilweise, Rest unter dem Mindestvolumen zum Fuellpreis: sofort
          geschlossen, Rest als dust_qty, close_reason "dust_after_sell".

        Rueckgabe (Ergebnis, sell_price, realized_pnl, verkaufte Menge); die
        drei letzten Werte sind nur bei SELL_CLOSED aussagekraeftig. Gemeldet
        werden hier nur Teilverkauf und Staub - den Abschluss melden die
        Aufrufer mit ihrem eigenen Text.

        `executedQty` kommt aus der Order-Antwort, nicht aus `fills` - wie in
        allen anderen Pfaden (average_fill_price, net_executed_quantity);
        `fills` liefern nur die Gebuehr.
        """
        client_order_id = client_order_id or order.get("clientOrderId")
        executed = executed_quantity(order)
        if executed <= 0:
            # Nach A1 (16.10.2026) nicht erreichbar: eine Order ohne
            # Ausfuehrung kommt als None zurueck bzw. wird verworfen.
            raise ValueError(
                f"Verkauf {client_order_id} ohne ausgefuehrte Menge - nichts gebucht."
            )
        open_qty = open_quantity(record)
        # Tatsaechlicher Fuellpreis statt des vorher abgefragten Tickers -
        # siehe die Begruendung im Kaufpfad (_process_buys).
        fill_price = average_fill_price(order, fallback=price)
        gross = fill_price * executed
        # Netto, also abzueglich der in der Quote-Waehrung abgerechneten
        # Verkaufsgebuehr - cummulativeQuoteQty ist der Bruttoerloes.
        proceeds = net_proceeds(order, rules, fallback=gross)

        if sold_fully(open_qty, executed, rules):
            partial_qty = float(record.get("partial_exit_qty") or 0.0)
            sold_qty = partial_qty + executed
            sell_price = (float(record.get("partial_exit_quote") or 0.0) + gross) / sold_qty
            total_proceeds = proceeds + float(record.get("partial_exit_proceeds") or 0.0)
            realized_pnl = total_proceeds - record["quote_spent"]
            self._ledger.record_sell(
                record["id"],
                sell_price,
                datetime.now(timezone.utc).isoformat(),
                realized_pnl,
                client_order_id,
            )
            self._failed_sell_notified.discard(record["id"])
            return SELL_CLOSED, sell_price, realized_pnl, sold_qty

        order_id = order.get("orderId")
        if order_id is None:
            raise ValueError(
                f"Teilverkauf {client_order_id} ohne orderId - ohne sie liesse er "
                "sich nicht idempotent verbuchen, nichts gebucht."
            )
        booked = self._ledger.record_partial_exit(
            record["id"], str(order_id), executed, gross, proceeds
        )
        refreshed = self._ledger.position_by_id(record["id"]) or record
        if booked:
            self._report_partial_sell(refreshed, order, executed, fill_price, prefix)
        if self._close_rest_if_dust(refreshed, fill_price, rules, client_order_id, prefix):
            return SELL_DUST, 0.0, 0.0, 0.0
        return SELL_PARTIAL, 0.0, 0.0, 0.0

    def _report_partial_sell(
        self, record: dict, order: dict, executed: float, fill_price: float, prefix: str
    ) -> None:
        rest = open_quantity(record)
        logger.warning(
            "%s[GRID-TEILVERKAUF] Stufe %s: Verkauf %s nur teilweise ausgefuehrt "
            "(Boerse meldet %s, %.8f %s @ %.2f). Verbucht, die Position bleibt mit "
            "%.8f offen und wird verkauft, solange das Ziel erreicht ist.",
            prefix,
            record.get("level_index", "?"),
            order.get("clientOrderId"),
            order.get("status"),
            executed,
            self._config.symbol,
            fill_price,
            rest,
        )
        send_notification(
            f"{prefix}[GRID-TEILVERKAUF] Stufe {record.get('level_index', '?')}: nur "
            f"{executed:.8f} {self._config.symbol} @ {fill_price:.2f} verkauft (Boerse "
            f"meldet {order.get('status')}). Verbucht - der Rest ({rest:.8f}) bleibt "
            "offen und wird verkauft, solange das Ziel erreicht ist."
        )

    def _close_rest_if_dust(
        self,
        record: dict,
        price: float,
        rules,
        client_order_id: str | None = None,
        prefix: str = "",
    ) -> bool:
        """
        Schliesst eine teilverkaufte Position, deren Rest sich nicht mehr
        verkaufen laesst (Runde 2, Muster wie _close_with_dust beim Trend-Bot
        aus K-A). Ohne das kaeme jeder Verkaufsversuch am Ziel als Ablehnung
        zurueck, Zyklus fuer Zyklus, und die Stufe bliebe belegt.

        Der Rest bleibt als Staub auf dem Konto (`dust_qty`), `close_reason`
        "dust_after_sell", sell_price der Durchschnitt der Teile,
        realized_pnl = Erloes der Teile - quote_spent (vorsichtig bewertet:
        der Staub hat einen Restwert unter dem Mindestvolumen). Keine Sperre.

        True, wenn geschlossen wurde. Ohne verbuchten Teilverkauf nie.
        """
        partial_qty = float(record.get("partial_exit_qty") or 0.0)
        if partial_qty <= 0:
            return False
        rest = open_quantity(record)
        if not is_dust(rest, price, rules):
            return False
        sell_price = float(record.get("partial_exit_quote") or 0.0) / partial_qty
        realized_pnl = float(record.get("partial_exit_proceeds") or 0.0) - record["quote_spent"]
        self._ledger.record_sell(
            record["id"],
            sell_price,
            datetime.now(timezone.utc).isoformat(),
            realized_pnl,
            client_order_id,
            dust_qty=rest,
            close_reason=CLOSE_REASON_DUST_AFTER_SELL,
        )
        self._failed_sell_notified.discard(record["id"])
        logger.warning(
            "%s[GRID-STAUB] Stufe %s: nach dem Teilverkauf bleiben %.8f %s (~%.2f %s), "
            "unter dem Mindestvolumen und damit nicht verkaufbar. Position geschlossen "
            "(dust_after_sell), der Rest bleibt als Staub auf dem Konto. Realisiert "
            "%.2f %s, Stufe ist frei.",
            prefix,
            record.get("level_index", "?"),
            rest,
            rules.base_asset,
            rest * price,
            rules.quote_asset,
            realized_pnl,
            rules.quote_asset,
        )
        send_notification(
            f"{prefix}[GRID-STAUB] Stufe {record.get('level_index', '?')}: nach dem "
            f"Teilverkauf ({partial_qty:.8f} {self._config.symbol} @ {sell_price:.2f}) "
            f"bleiben {rest:.8f} {rules.base_asset} (~{rest * price:.2f} "
            f"{rules.quote_asset}) unter dem Mindestvolumen als Staub auf dem Konto. "
            f"Position geschlossen, realisiert: {realized_pnl:+.2f}. Stufe ist frei."
        )
        return True

    def _sell_is_pending(self, record: dict) -> bool:
        """
        Ob fuer diese Position noch ein Verkauf mit ungeklaertem Ausgang in
        der Pending-Datei steht (K-B, siehe _process_sells). Nur ins Log -
        die Telegram-Meldung dazu kam bereits als [ORDER-UNKLAR] bzw. ueber
        die Reconciliation.
        """
        pending = self._client.pending_orders.entries_for(
            side="SELL", symbol=self._config.symbol, position_id=record["id"]
        )
        if not pending:
            return False
        logger.warning(
            "[GRID-VERKAUF-UNGEKLAERT] Stufe %s: fuer Position %s ist der "
            "Verkauf %s noch ungeklaert - es wird NICHT erneut verkauft, bis "
            "Binance den Ausgang bestaetigt (Reconciliation zu Beginn jedes "
            "Zyklus).",
            record.get("level_index", "?"),
            record["id"],
            ", ".join(p.client_order_id for p in pending),
        )
        return True

    def _account_snapshot(self, rules) -> BalanceSnapshot | None:
        """
        Kontostand des Base-Assets samt Zuordnung der gebundenen Mengen
        (W11, siehe balance_guard.py).

        Nur im echten Trading-Modus: im Dry-Run existieren die Positionen
        an der Börse gar nicht, ein Abgleich gegen echte Bestände hätte
        dort keine Bedeutung - und würde bei jedem Zyklus zwei
        API-Aufrufe für nichts kosten.

        `None` heißt "nicht abrufbar" und schaltet beide Prüfungen für
        diesen Zyklus ab. Das ist Absicht: ein gescheiterter Abruf ist
        keine Aussage über das Konto, und ein Verkauf, der wegen eines
        Netzwerk-Hängers unterbleibt, wäre die gefährlichere Richtung.
        """
        if not self._config.trading_enabled:
            return None
        return build_snapshot(
            self._client.get_asset_balance(rules.base_asset),
            self._client.get_open_orders(self._config.symbol),
            self._config.bot_name,
        )

    def _warn_on_ledger_mismatch(
        self, snapshot: BalanceSnapshot | None, open_positions: list[dict], rules
    ) -> None:
        """
        Buchhaltungsprüfung (weich, W11): Deckt das Konto überhaupt ab,
        was das eigene Ledger als offen führt?

        Blockiert bewusst NICHTS - siehe Modul-Docstring von
        balance_guard.py: ein gedeckter Einzelverkauf reduziert Risiko
        und Kapitalbindung, ihn zu verhindern würde das eigentliche
        Problem nicht lösen, sondern nur Assets stranden lassen. Gleiche
        Abwägung wie beim Trendbruch-Stop-Loss, der Verkäufe ebenfalls
        durchlässt.

        Dry-Run-Positionen zählen nicht mit: sie existieren an der Börse
        nicht und dürfen deshalb auch keinen Anspruch auf echtes
        Guthaben begründen (K4).
        """
        if snapshot is None:
            return

        # Offene Menge, also nach Teilverkaeufen (Runde 2) - sonst meldete
        # jede teilverkaufte Position eine Diskrepanz, die es nicht gibt.
        own_quantity = sum(
            open_quantity(r)
            for r in open_positions
            if not r.get("dry_run", True)
        )
        if not ledger_exceeds_account(snapshot, own_quantity, rules.step_size):
            self._balance_mismatch_notified = False
            return

        logger.error(
            "[GRID-BESTAND-DISKREPANZ] Das Grid-Ledger führt mehr %s als "
            "auf dem Konto für diesen Bot vorhanden sein kann. %s. Da sich "
            "DCA, Grid und Trend ein Konto teilen, kann das bedeuten, dass "
            "ein anderer Bot oder ein manueller Trade Bestand verkauft hat, "
            "der hier noch als offen geführt wird. Gedeckte Verkäufe laufen "
            "weiter, bitte mit 'python -m dca_bot.audit_positions' prüfen.",
            rules.base_asset,
            describe(snapshot, own_quantity),
        )

        if self._balance_mismatch_notified:
            return
        self._balance_mismatch_notified = True
        send_notification(
            f"[GRID-BESTAND-DISKREPANZ] Das Grid-Ledger führt mehr "
            f"{rules.base_asset}, als für diesen Bot auf dem Konto sein "
            f"kann. {describe(snapshot, own_quantity)}. Geteiltes Konto - "
            "bitte Positionen prüfen (python -m dca_bot.audit_positions)."
        )

    def _sell_is_covered(
        self,
        record: dict,
        snapshot: BalanceSnapshot | None,
        sold_this_cycle: float,
        rules,
    ) -> bool:
        """
        Deckungsprüfung (hart, W11) für genau diese eine Position.

        `sold_this_cycle` zieht ab, was in diesem Durchlauf bereits
        verkauft wurde: Der Snapshot stammt vom Anfang des Zyklus, und
        durchquert der Preis mehrere Stufen nach oben, schließt diese
        Schleife mehrere Positionen nacheinander. Ohne diese Korrektur
        hielte die Prüfung dasselbe freie Guthaben für jeden Verkauf
        erneut verfügbar - und übersähe genau den Fall, für den sie
        gebaut ist.
        """
        if snapshot is None:
            return True

        # Genau die Menge, die gleich verkauft wird (Runde 2: die offene).
        quantity = open_quantity(record)
        remaining = BalanceSnapshot(
            free=snapshot.free - sold_this_cycle,
            locked=snapshot.locked,
            own_locked=snapshot.own_locked,
            foreign_locked=snapshot.foreign_locked,
        )
        if check_sell_coverage(remaining, quantity, rules.step_size) != SELL_INSUFFICIENT:
            return True

        logger.error(
            "[GRID-VERKAUF-UNGEDECKT] Stufe %s: Verkauf über %.8f %s wird "
            "NICHT versucht - frei verfügbar sind nur %.8f. %.8f stecken in "
            "offenen Orders (davon %.8f aus anderen Bots bzw. manuellem "
            "Handel). Die Börse würde die Order ablehnen; die Position "
            "bleibt offen und wird im nächsten Zyklus erneut geprüft.",
            record.get("level_index", "?"),
            quantity,
            rules.base_asset,
            remaining.free,
            snapshot.locked,
            snapshot.foreign_locked,
        )
        if record["id"] not in self._failed_sell_notified:
            self._failed_sell_notified.add(record["id"])
            send_notification(
                f"[GRID-VERKAUF-UNGEDECKT] Stufe {record.get('level_index', '?')}: "
                f"Verkauf über {quantity:.8f} {rules.base_asset} nicht gedeckt "
                f"(frei: {remaining.free:.8f}, in fremden Orders gebunden: "
                f"{snapshot.foreign_locked:.8f}). Position bleibt offen - "
                "geteiltes Konto, bitte prüfen."
            )
        return False

    def _report_sell_blocked_by_dry_run(self, record: dict, price: float) -> None:
        """
        Meldet, dass eine ECHTE Position ihr Verkaufsziel erreicht hat,
        aber nicht verkauft werden kann, weil GRID_BOT_ENABLE_TRADING=false
        ist (siehe _process_sells).

        Die Position bleibt offen und damit auch ihre Stufe belegt - das
        BTC liegt ja weiterhin an der Boerse. Sobald Trading wieder an
        ist, verkauft der naechste Zyklus regulaer, solange das Ziel dann
        noch erreicht ist.

        Telegram einmal pro Prozesslauf und Position, ins Log jeder Zyklus
        - gleiches Muster wie _report_failed_sell, aber mit eigener Menge:
        teilten sich beide eine, wuerde eine fruehere Sperr-Meldung nach
        dem Wiedereinschalten eine echte Fehlschlag-Meldung derselben
        Position verschlucken. (Praktisch setzt ein Neustart beides
        zurueck, da trading_enabled nur beim Start gelesen wird - die
        Trennung haengt aber nicht an diesem Detail.)
        """
        logger.warning(
            "[GRID-VERKAUF-GESPERRT] Stufe %s: echte Position %s hat ihr "
            "Verkaufsziel erreicht (Preis ~%.2f), aber GRID_BOT_ENABLE_TRADING "
            "ist false - es wird NICHT verkauft und nichts gebucht. Position "
            "bleibt offen, die Assets liegen weiter an der Boerse. Zum "
            "Verkaufen Trading wieder aktivieren.",
            record.get("level_index", "?"),
            record["id"],
            price,
        )

        if record["id"] in self._dry_run_block_notified:
            return
        self._dry_run_block_notified.add(record["id"])
        send_notification(
            f"[GRID-VERKAUF-GESPERRT] Stufe {record.get('level_index', '?')}: "
            f"echte Position ({open_quantity(record):.8f} {self._config.symbol}) "
            f"hat ihr Verkaufsziel @ {price:.2f} erreicht, Trading ist aber "
            "deaktiviert. Kein Verkauf, Position bleibt offen - zum Verkaufen "
            "GRID_BOT_ENABLE_TRADING=true setzen."
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

        Seit dem Systemcheck vom 27.09.2026 (K-B) unterscheidet der Text,
        ob der nächste Zyklus es wirklich erneut versucht: nach einer
        eindeutigen Ablehnung ja, bei unklarem Ausgang (Pending-Eintrag
        steht noch) erst, wenn die Reconciliation ihn geklärt hat.
        """
        unclear = bool(
            self._client.pending_orders.entries_for(
                side="SELL", symbol=self._config.symbol, position_id=record["id"]
            )
        )
        follow_up = (
            "Ausgang UNKLAR - kein neuer Versuch, bis Binance ihn bestätigt."
            if unclear
            else "Der nächste Zyklus versucht es erneut."
        )
        logger.warning(
            "[GRID-VERKAUF-FEHLGESCHLAGEN] Echter Verkauf für Stufe %d "
            "fehlgeschlagen (Position %s, Preis ~%.2f) - Position bleibt "
            "OFFEN im Ledger, kein Erlös verbucht. %s",
            record["level_index"],
            record["id"],
            price,
            follow_up,
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
        # Eine Stufe mit einem Kauf, dessen Ausgang noch ungeklaert ist, gilt
        # ebenfalls als belegt (Systemcheck vom 27.09.2026, Gegenstueck zu
        # K-B): war der Kauf durchgegangen, wuerde ein erneutes Durchqueren
        # sonst ein zweites Mal kaufen. Die Reconciliation traegt ihn nach
        # oder verwirft den Eintrag - danach ist die Stufe wieder regulaer.
        for pending in self._client.pending_orders.entries_for(
            side="BUY", symbol=self._config.symbol
        ):
            level = pending.context.get("level_index")
            if isinstance(level, int):
                occupied_levels.add(level)
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
            # Notaus vor JEDEM einzelnen Kauf, nicht nur einmal vor der
            # Schleife (Sicherheitsreview-Punkt W15). Genau hier zählt es:
            # Wenn der Preis in einem Intervall durch mehrere Stufen
            # gefallen ist (Crash-Szenario), kauft diese Schleife mehrere
            # Positionen hintereinander - und das ist der Moment, in dem
            # jemand den Notaus zieht. Ohne die Prüfung liefen alle
            # verbleibenden Käufe trotzdem durch.
            #
            # BotHalted fliegt bis main_grid.py und stoppt den Bot sauber;
            # die in diesem Durchlauf bereits getätigten Käufe stehen zu
            # diesem Zeitpunkt schon im Ledger, es bleibt nichts
            # unverbucht.
            self._kill_switch.check()

            order = self._client.place_market_buy(
                self._config.symbol,
                self._config.amount_per_level,
                context={
                    "level_index": level_index,
                    "price": price,
                    "amount": self._config.amount_per_level,
                },
            )

            if order is None and self._config.trading_enabled:
                # Echter Kauf nicht zustande gekommen - analog zum DCA-Bot
                # keine Ledger-Eintragung, kein simulierter Erfolg. Seit A1
                # (16.10.2026) landet hier auch eine Order, die die Boerse
                # ohne Ausfuehrung beendet hat (EXPIRED mit 0) oder deren
                # Ende unklar ist - der Grund steht in der Meldung des
                # Clients direkt davor. Die Stufe bleibt frei (bzw. bei
                # unklarem Ausgang ueber den Pending-Eintrag belegt).
                logger.error(
                    "Echter Grid-Kauf für Stufe %d (Preis ~%.2f) nicht verbucht: "
                    "abgelehnt, ohne Ausfuehrung beendet oder Ausgang unklar "
                    "(siehe Meldung davor).",
                    level_index,
                    price,
                )
                send_notification(
                    f"[GRID-FEHLER] Echter Kauf für Stufe {level_index} "
                    f"(Preis ~{price:.2f}) nicht verbucht - von der Börse "
                    "abgelehnt, ohne Ausführung beendet oder Ausgang unklar. "
                    "Nichts gebucht, siehe Bot-Log."
                )
                continue

            if order is not None:
                # Tatsaechlicher Fuellpreis aus der Order-Antwort
                # (cummulativeQuoteQty / executedQty), nicht der vor der
                # Order abgefragte Ticker - gleiche Quelle wie im
                # Reconciliation-Pfad (_record_reconciled_buy). Bis zum
                # 25.09.2026 stand hier der Ticker; die PnL war davon nicht
                # betroffen (sie rechnet mit quantity/quote_spent), aber
                # der angezeigte Kaufpreis in Dashboard und Steuer-Export
                # wich vom echten Fill ab. Das Verkaufsziel bleibt die
                # naechsthoehere Grid-Stufe, es haengt nicht am Fill.
                buy_price = average_fill_price(order, fallback=price)
                # Menge abzüglich der in BTC abgezogenen Kaufgebühr - genau
                # diese Menge steht später für den Verkauf zur Verfügung.
                quantity = net_executed_quantity(
                    order, rules, fallback=self._config.amount_per_level / price
                )
                quote_spent = float(order.get("cummulativeQuoteQty", self._config.amount_per_level))
            else:
                # Dry-Run: der beobachtete Preis IST der simulierte Fill.
                buy_price = price
                # Dry-Run: keine echte Gebühr bekannt, deshalb keine
                # geschätzte abgezogen - die Menge wird aber quantisiert,
                # damit simulierte und echte Werte vergleichbar bleiben.
                quantity = quantize_quantity(
                    self._config.amount_per_level / price, rules.step_size
                )
                # Und genau deshalb muss auch der Betrag aus der
                # quantisierten Menge kommen: die weggerundete Teilmenge
                # wurde nie gekauft. Ein echter Fill liefert oben
                # cummulativeQuoteQty, also den tatsaechlich belasteten
                # Betrag - `quantity * price` ist dessen Entsprechung im
                # Dry-Run. Mit dem konfigurierten Rohbetrag staende eine
                # zu hohe Kostenbasis im Ledger, und jede realisierte PnL
                # dieser Position waere um die Differenz zu negativ: bei
                # 15 USDT und stepSize 1e-5 ist eine Mengenstufe rund
                # 0,80 USDT, also ~5 % des Auftrags und damit mehr als
                # der Grid-Stufenabstand selbst.
                quote_spent = quantity * price

            position = GridPosition.new(
                level_index=level_index,
                buy_price=buy_price,
                target_sell_price=self._levels[level_index + 1],
                quantity=quantity,
                quote_spent=quote_spent,
                dry_run=not self._config.trading_enabled,
                client_order_id=order.get("clientOrderId") if order else None,
                symbol=self._config.symbol,
            )
            partial = is_partial_fill(order)
            dust = partial and is_dust(quantity, buy_price, rules)
            if dust:
                self._close_as_dust(position, order, rules)
            self._ledger.record_buy(position)
            # Erst mit dem Kauf im Ledger ist die Order-Frage erledigt (W-A).
            self._client.confirm_booked(position.client_order_id)

            if dust:
                self._report_dust(position, order, "")
                continue

            logger.info(
                "Grid-Kauf: Stufe %d @ %.2f (Ziel-Verkauf @ %.2f)%s",
                level_index,
                buy_price,
                position.target_sell_price,
                self._partial_note(order, quote_spent) if partial else "",
            )
            tag = "[GRID-KAUF]" if order is not None else "[GRID-KAUF DRY-RUN]"
            send_notification(
                f"{tag} Stufe {level_index}: {quantity:.8f} {self._config.symbol} "
                f"@ {buy_price:.2f} (Ziel-Verkauf @ {position.target_sell_price:.2f})"
                + (self._partial_note(order, quote_spent) if partial else "")
            )

    def _partial_note(self, order: dict, quote_spent: float) -> str:
        """Zusatz fuer Log/Telegram bei einem nur teilweise ausgefuehrten Kauf (T2)."""
        return (
            f" - Teilfüllung: Börse meldet {order.get('status')}, ausgeführt "
            f"{quote_spent:.2f} von {self._config.amount_per_level:.2f}"
        )

    def _close_as_dust(self, position: GridPosition, order: dict, rules) -> None:
        """
        Schliesst eine Position, deren Kauf nur teilweise ausgefuehrt wurde
        und deren Menge unter dem Mindestvolumen liegt (T2, 16.10.2026,
        Muster wie _close_with_dust beim Trend-Bot aus K-A).

        Ohne das stuende sie offen im Ledger, ihre Stufe waere belegt, und
        jeder Verkaufsversuch am Ziel kaeme als Ablehnung zurueck - Zyklus
        fuer Zyklus. Der Staub bleibt auf dem Konto. Bewertet wird
        vorsichtig: realized_pnl = -quote_spent, obwohl der Staub einen
        Restwert unter dem Mindestvolumen hat. Keine Sperre.

        `quantity` ist die tatsaechlich erhaltene Menge OHNE Rundung auf die
        stepSize - gerundet koennte sie 0 sein, und das wuerde der
        Ledger-Schutz A3 zu Recht ablehnen, obwohl Geld geflossen ist.
        """
        received = received_base_quantity(order, rules)
        position.quantity = received
        position.dust_qty = received
        position.status = "closed"
        position.sold_at = position.bought_at
        position.realized_pnl = -position.quote_spent
        position.close_reason = CLOSE_REASON_DUST

    def _report_dust(self, position: GridPosition, order: dict, prefix: str) -> None:
        logger.warning(
            "%s[GRID-STAUB] Stufe %d: Kauf nur teilweise ausgefuehrt (Boerse meldet "
            "%s, %.8f %s fuer %.2f) - die Menge liegt unter dem Mindestvolumen und "
            "laesst sich nicht verkaufen. Position sofort geschlossen, Menge bleibt "
            "als Staub auf dem Konto, als Verlust von %.2f gebucht. Stufe ist frei.",
            prefix,
            position.level_index,
            order.get("status"),
            position.dust_qty,
            self._config.symbol,
            position.quote_spent,
            position.quote_spent,
        )
        send_notification(
            f"{prefix}[GRID-STAUB] Stufe {position.level_index}: Kauf nur teilweise "
            f"ausgeführt ({position.dust_qty:.8f} {self._config.symbol} für "
            f"{position.quote_spent:.2f}), unter dem Mindestvolumen - bleibt als "
            f"Staub auf dem Konto, als Verlust von {position.quote_spent:.2f} gebucht. "
            "Stufe ist wieder frei."
        )

    def verify_state_readable(self) -> None:
        """
        Prueft beim Bot-Start, ob das Ledger lesbar ist
        (Sicherheitsreview-Punkt W5). Wirft `LedgerUnreadable`.

        Bewusst ein eigener Schritt und NICHT in
        safe_startup_reconciliation() gekapselt: deren Zweck ist "der
        Start darf nicht scheitern", und genau das waere hier falsch
        herum. Ein beschaedigtes Ledger MUSS den Start verhindern.
        """
        self._ledger.verify_readable()

    def verify_symbol_binding(self) -> None:
        """
        Prueft beim Bot-Start, ob Ledger, Pending-Datei und Stop-Loss-Sperre
        zu GRID_SYMBOL gehoeren (Symbolbindung vom 28.09.2026, siehe
        symbol_guard.py). Wirft `SymbolMismatch`.

        Ohne diese Pruefung haette ein Grid-Bot mit geaendertem GRID_SYMBOL
        alte Positionen still als Positionen des neuen Paars weitergefuehrt:
        Verkaufsziele in USDT gegen einen EUR-Kurs, Verkauf gegen EUR,
        realisierte PnL aus EUR-Erloes minus USDT-Einsatz, und die alten
        Stufen-Indizes belegten Stufen des neuen Grids.
        """
        symbol_guard.enforce(
            symbol_guard.bot_findings(
                symbol_var="GRID_SYMBOL",
                expected=self._config.symbol,
                ledger_label="Grid-Ledger",
                ledger_path=self._config.state_file,
                ledger_records=self._ledger.records(),
                pending_store=self._client.pending_orders,
                latch_path=self._config.stop_loss_state_file,
                latch_reset="python -m dca_bot.reset_grid_stop_loss",
            ),
            bot_label="Grid-Bot",
            symbol_var="GRID_SYMBOL",
            expected=self._config.symbol,
            logger=logger,
            notify=send_notification,
        )

    def check_balance_on_startup(self) -> None:
        """
        Gleicht beim Bot-Start alle offenen Positionen gegen den
        tatsächlichen Kontostand ab (Stufe 2, Punkt 3 - siehe
        startup_checks.py). Laut, aber nicht blockierend.

        Ergänzt die bestehende Prüfung in `_warn_on_ledger_mismatch()`,
        ersetzt sie nicht: Die läuft nur in einem Zyklus, in dem
        überhaupt ein Verkaufsziel erreicht ist. Steht der Preis
        wochenlang unterhalb aller Ziele - also genau dann, wenn viele
        Stufen belegt sind und am meisten Kapital gebunden ist -, wird
        dort gar nichts geprüft.

        Dieselbe Mengenberechnung wie dort: Dry-Run-Positionen zählen
        nicht mit, sie existieren an der Börse nicht und begründen
        keinen Anspruch auf echtes Guthaben (K4). Ein Eintrag ohne
        `dry_run`-Feld gilt über den Default `True` als simuliert - die
        konservative Richtung, weil er die eigene Anspruchsmenge nicht
        künstlich erhöht.
        """
        quantity = sum(
            open_quantity(r)
            for r in self._ledger.open_positions()
            if not r.get("dry_run", True)
        )
        report_ledger_vs_account(
            client=self._client,
            logger=logger,
            symbol=self._config.symbol,
            bot_name=self._config.bot_name,
            own_open_quantity=quantity,
            notify_tag="[GRID-BESTAND-DISKREPANZ]",
            ledger_label="Das Grid-Ledger",
        )

    def reconcile_pending_orders(self) -> None:
        """
        Trägt beim Bot-Start Käufe/Verkäufe nach, deren Ausgang beim
        letzten Lauf offen geblieben ist (Sicherheitsreview-Punkt K2,
        Teil B - siehe pending_orders.py und main_grid.py).

        Für den Grid-Bot sind beide Richtungen kritisch:
        - Ein unverbuchter KAUF lässt die Stufe "frei" aussehen, und das
          nächste Crossing kauft sie ein zweites Mal.
        - Ein unverbuchter VERKAUF lässt die Position offen stehen, ihr
          Sell-Target ist weiterhin erreicht, und der nächste Zyklus
          verkauft eine Menge, die es nicht mehr gibt.
        """
        reconcile_pending_orders(
            client=self._client,
            store=self._client.pending_orders,
            bot_logger=logger,
            apply_confirmed=self._apply_reconciled_order,
        )

    def _reconcile_pending_at_runtime(self) -> None:
        """
        Dieselbe Reconciliation zu Beginn JEDES Zyklus (Systemcheck vom
        27.09.2026, K-B/W-A). Ein Verkauf mit unklarem Ausgang wird damit
        geklaert, sobald Binance wieder antwortet - und nicht erst beim
        naechsten Neustart, waehrend der Bot dieselbe Position in der
        Zwischenzeit womoeglich ein zweites Mal verkauft.
        """
        reconcile_pending_orders(
            client=self._client,
            store=self._client.pending_orders,
            bot_logger=logger,
            apply_confirmed=self._apply_reconciled_order,
            escalated=self._pending_escalated,
        )

    def _apply_reconciled_order(self, pending: PendingOrder, order: dict) -> None:
        if pending.side == "BUY":
            self._record_reconciled_buy(pending, order)
        elif pending.side == "SELL":
            self._record_reconciled_sell(pending, order)
        else:
            raise ValueError(
                f"Unerwartete Order-Seite '{pending.side}' in der "
                "Pending-Orders-Datei des Grid-Bots."
            )

    def _target_sell_price_for(self, level_index: int, buy_price: float) -> float:
        """
        Verkaufsziel einer nachgetragenen Position.

        Normalfall ist die nächsthöhere Grid-Stufe, exakt wie beim
        regulären Kauf. Wurde die Grid-Konfiguration zwischen den beiden
        Läufen geändert, kann die gespeicherte Stufe aber gar nicht mehr
        existieren. Die Position dann NICHT zu verbuchen wäre die
        schlechteste Option (die Assets liegen real an der Börse) -
        stattdessen wird das Ziel aus dem Kaufpreis und dem aktuellen
        Stufenabstand abgeleitet und der Sonderfall deutlich geloggt.
        """
        if 0 <= level_index < len(self._levels) - 1:
            return self._levels[level_index + 1]

        fallback = buy_price * (1 + self._config.grid_spacing_pct / 100)
        logger.error(
            "%sStufe %s existiert im aktuellen Grid nicht mehr (%d Stufen) - "
            "die nachgetragene Position bekommt ein aus dem Kaufpreis "
            "abgeleitetes Verkaufsziel von %.2f. Bitte prüfen, ob die "
            "Grid-Konfiguration seit dem letzten Lauf geändert wurde.",
            RECONCILIATION_PREFIX,
            level_index,
            len(self._levels),
            fallback,
        )
        return fallback

    def _record_reconciled_buy(self, pending: PendingOrder, order: dict) -> None:
        if self._ledger.has_client_order_id(pending.client_order_id):
            logger.info(
                "%sKauf zu Order %s ist bereits im Ledger - nichts nachzutragen.",
                RECONCILIATION_PREFIX,
                pending.client_order_id,
            )
            return

        symbol = pending.symbol or self._config.symbol
        level_index = int(pending.context.get("level_index", -1))
        amount = float(pending.context.get("amount", self._config.amount_per_level))

        rules = self._client.get_symbol_trading_rules(symbol)
        order = self._client.get_order_with_fills(symbol, order)

        buy_price = average_fill_price(
            order, fallback=float(pending.context.get("price", 0.0)) or 0.0
        )
        if buy_price <= 0:
            raise ValueError(
                f"Kein brauchbarer Kaufpreis für Order {pending.client_order_id} "
                "ermittelbar - die Position bekäme ein unsinniges Verkaufsziel."
            )

        existing = self._ledger.open_position_for_level(level_index)
        if existing is not None:
            # Verletzt "höchstens eine offene Position pro Stufe". Die
            # Assets existieren trotzdem - sie zu verschweigen wäre
            # schlimmer als zwei Einträge auf einer Stufe (beide werden
            # bei erreichtem Ziel verkauft, die Stufe gilt bis dahin als
            # belegt).
            logger.error(
                "%sStufe %d hat bereits eine offene Position (%s) - die "
                "nachgetragene Position kommt zusätzlich ins Ledger, damit "
                "die real gekauften Assets nicht verschwinden. Bitte prüfen.",
                RECONCILIATION_PREFIX,
                level_index,
                existing["id"],
            )

        quantity = net_executed_quantity(order, rules, fallback=amount / buy_price)
        quote_spent = float(order.get("cummulativeQuoteQty", amount))

        position = GridPosition.new(
            level_index=level_index,
            buy_price=buy_price,
            target_sell_price=self._target_sell_price_for(level_index, buy_price),
            quantity=quantity,
            quote_spent=quote_spent,
            dry_run=False,
            client_order_id=pending.client_order_id,
            symbol=symbol,
        )
        # Dieselbe Staub-Regel wie im direkten Pfad (T2, 16.10.2026).
        if is_partial_fill(order) and is_dust(quantity, buy_price, rules):
            self._close_as_dust(position, order, rules)
            self._ledger.record_buy(position)
            self._report_dust(position, order, RECONCILIATION_PREFIX)
            return
        self._ledger.record_buy(position)

        logger.warning(
            "%sGrid-Kauf nachgetragen: Stufe %d @ %.2f (Menge %.8f, "
            "Ziel-Verkauf @ %.2f, Order %s).",
            RECONCILIATION_PREFIX,
            level_index,
            buy_price,
            quantity,
            position.target_sell_price,
            pending.client_order_id,
        )
        send_notification(
            f"[REKONZILIATION] Nachgetragener Grid-Kauf: Stufe {level_index}, "
            f"{quantity:.8f} {symbol} @ {buy_price:.2f} "
            f"(Ziel-Verkauf @ {position.target_sell_price:.2f}). Die Order lief "
            "beim letzten Bot-Lauf durch, ihr Ergebnis kam aber nicht mehr an."
        )

    def _record_reconciled_sell(self, pending: PendingOrder, order: dict) -> None:
        position_id = pending.context.get("position_id")
        record = self._ledger.position_by_id(position_id) if position_id else None

        if record is None:
            raise ValueError(
                f"Verkaufs-Order {pending.client_order_id} verweist auf die "
                f"unbekannte Position '{position_id}' - der Verkauf hat real "
                "stattgefunden, lässt sich aber keiner Position zuordnen."
            )

        symbol = pending.symbol or self._config.symbol

        # Schon als Teilverkauf verbucht (Runde 2)? Dann ist nichts
        # nachzutragen - auch wenn die Position inzwischen mit einer ANDEREN
        # Order geschlossen wurde. Ohne diese Pruefung zuerst hielte der
        # Zweig darunter genau das fuer einen Doppelverkauf. Gleiche Lage
        # nach einem Neustart zwischen record_partial_exit() und
        # confirm_booked(): Der Teil steht schon im Ledger, der
        # Pending-Eintrag aber auch noch.
        order_id = order.get("orderId")
        booked_ids = {str(i) for i in (record.get("partial_exit_order_ids") or [])}
        if order_id is not None and str(order_id) in booked_ids:
            logger.info(
                "%sTeilverkauf zu Order %s ist bei Position %s bereits verbucht - "
                "nichts nachzutragen.",
                RECONCILIATION_PREFIX,
                pending.client_order_id,
                position_id,
            )
            if record["status"] == "open":
                # Starb der Prozess, bevor ein Staub-Rest geschlossen war,
                # holt das der Abschluss jetzt nach - sonst bliebe die Stufe
                # belegt, bis das Ziel wieder erreicht ist.
                rules = self._client.get_symbol_trading_rules(symbol)
                self._close_rest_if_dust(
                    record,
                    average_fill_price(order, fallback=float(pending.context.get("price", 0.0)) or 0.0),
                    rules,
                    pending.client_order_id,
                    RECONCILIATION_PREFIX,
                )
            return

        if record["status"] != "open":
            if record.get("sell_client_order_id") == pending.client_order_id:
                # Genau der Fall, für den die Idempotenz da ist: der
                # Verkauf wurde schon verbucht, nur das Aufräumen des
                # Pending-Eintrags kam nicht mehr dazu.
                logger.info(
                    "%sPosition %s ist bereits geschlossen (mit Order %s) - "
                    "nichts nachzutragen.",
                    RECONCILIATION_PREFIX,
                    position_id,
                    pending.client_order_id,
                )
                return
            # Die Position ist mit einer ANDEREN Order geschlossen worden -
            # diese hier lief also zusätzlich: ein Doppelverkauf aus dem
            # Bestand eines anderen Bots (Systemcheck vom 27.09.2026, K-B).
            # Bis dahin ging genau dieser Fall als "schon verbucht" durch.
            # Nicht raten, sondern stehen lassen und melden.
            raise ManualReviewRequired(
                f"[GRID-DOPPELVERKAUF] {self._config.symbol}: Position "
                f"{position_id} (Stufe {record.get('level_index', '?')}) ist "
                f"bereits mit Order {record.get('sell_client_order_id') or 'unbekannt'} "
                f"geschlossen, Order {pending.client_order_id} hat an der Boerse "
                f"ZUSAETZLICH {order.get('executedQty', '?')} verkauft "
                f"(Erloes {order.get('cummulativeQuoteQty', '?')}). Das stammt "
                "aus dem Bestand eines anderen Bots - bitte manuell klaeren "
                "(python -m dca_bot.audit_positions)."
            )

        rules = self._client.get_symbol_trading_rules(symbol)
        order = self._client.get_order_with_fills(symbol, order)

        # Dieselben Regeln wie im direkten Pfad (Runde 2): gebucht wird nach
        # der ausgefuehrten Menge - vollstaendig, teilweise oder mit Staub.
        outcome, sell_price, realized_pnl, _ = self._book_sell(
            record,
            order,
            rules,
            float(pending.context.get("price", 0.0)) or 0.0,
            client_order_id=pending.client_order_id,
            prefix=RECONCILIATION_PREFIX,
        )
        if outcome != SELL_CLOSED:
            return

        logger.warning(
            "%sGrid-Verkauf nachgetragen: Stufe %s, Kauf @ %.2f -> Verkauf "
            "@ %.2f, realisiert %.2f (Order %s).",
            RECONCILIATION_PREFIX,
            record.get("level_index", "?"),
            record["buy_price"],
            sell_price,
            realized_pnl,
            pending.client_order_id,
        )
        send_notification(
            f"[REKONZILIATION] Nachgetragener Grid-Verkauf: Stufe "
            f"{record.get('level_index', '?')} @ {sell_price:.2f} "
            f"(Kauf @ {record['buy_price']:.2f}), realisiert: {realized_pnl:+.2f}. "
            "Die Order lief beim letzten Bot-Lauf durch, ihr Ergebnis kam aber "
            "nicht mehr an."
        )

    def execute_once(self) -> None:
        """Führt genau einen Grid-Zyklus aus: Preis holen, Verkäufe prüfen,
        Trendbruch-Stop-Loss prüfen, ggf. Käufe prüfen."""
        self._kill_switch.check()
        self._reconcile_pending_at_runtime()

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

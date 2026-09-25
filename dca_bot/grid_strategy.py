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
    net_executed_quantity,
    net_proceeds,
    quantize_quantity,
)
from .pending_orders import (
    RECONCILIATION_PREFIX,
    PendingOrder,
    reconcile_pending_orders,
)
from .risk import KillSwitch
from .startup_checks import report_ledger_vs_account

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
                order = self._client.place_market_sell(
                    self._config.symbol,
                    record["quantity"],
                    context={"position_id": record["id"], "price": price},
                )
                if order is None and self._config.trading_enabled:
                    # Echter Verkaufsversuch bei der Börse fehlgeschlagen -
                    # anders als im Dry-Run (wo None der Normalfall ist).
                    # Kein erfundener Erlös, kein record_sell(): die
                    # Position bleibt OFFEN und wird im nächsten Zyklus
                    # erneut versucht (das Sell-Target ist ja weiterhin
                    # erreicht).
                    self._report_failed_sell(record, price)
                    continue

                # Der Verkauf ist durch - diese Menge steht dem nächsten
                # Durchlauf dieser Schleife nicht mehr zur Verfügung.
                sold_this_cycle += float(record["quantity"])

            if order is not None:
                # Tatsaechlicher Fuellpreis statt des vorher abgefragten
                # Tickers - siehe die Begruendung im Kaufpfad
                # (_process_buys) und _record_reconciled_sell, das es schon
                # immer so macht.
                sell_price = average_fill_price(order, fallback=price)
                # Netto, also abzüglich der in USDT abgerechneten
                # Verkaufsgebühr - cummulativeQuoteQty ist der Bruttoerlös.
                proceeds = net_proceeds(order, rules, fallback=record["quantity"] * price)
            else:
                sell_price = price
                proceeds = record["quantity"] * price
            realized_pnl = proceeds - record["quote_spent"]

            sold_at = datetime.now(timezone.utc).isoformat()
            self._ledger.record_sell(record["id"], sell_price, sold_at, realized_pnl)
            self._failed_sell_notified.discard(record["id"])

            logger.info(
                "Grid-Verkauf: Stufe %d, Kauf @ %.2f -> Verkauf @ %.2f, realisiert %.2f",
                record["level_index"],
                record["buy_price"],
                sell_price,
                realized_pnl,
            )
            tag = "[GRID-VERKAUF]" if order is not None else "[GRID-VERKAUF DRY-RUN]"
            send_notification(
                f"{tag} Stufe {record['level_index']}: {record['quantity']:.8f} "
                f"{self._config.symbol} @ {sell_price:.2f} verkauft "
                f"(Kauf @ {record['buy_price']:.2f}), realisiert: {realized_pnl:+.2f}"
            )

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

        own_quantity = sum(
            float(r.get("quantity", 0.0))
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

        quantity = float(record["quantity"])
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
            f"echte Position ({record['quantity']:.8f} {self._config.symbol}) "
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
            )
            self._ledger.record_buy(position)

            logger.info(
                "Grid-Kauf: Stufe %d @ %.2f (Ziel-Verkauf @ %.2f)",
                level_index,
                buy_price,
                position.target_sell_price,
            )
            tag = "[GRID-KAUF]" if order is not None else "[GRID-KAUF DRY-RUN]"
            send_notification(
                f"{tag} Stufe {level_index}: {quantity:.8f} {self._config.symbol} "
                f"@ {buy_price:.2f} (Ziel-Verkauf @ {position.target_sell_price:.2f})"
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
            float(r.get("quantity", 0.0))
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
        )
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

        if record["status"] != "open":
            # Genau der Fall, für den die Idempotenz da ist: der Verkauf
            # wurde schon verbucht, nur das Aufräumen des Pending-
            # Eintrags kam nicht mehr dazu.
            logger.info(
                "%sPosition %s ist bereits geschlossen - Verkauf zu Order %s "
                "war schon verbucht.",
                RECONCILIATION_PREFIX,
                position_id,
                pending.client_order_id,
            )
            return

        symbol = pending.symbol or self._config.symbol
        rules = self._client.get_symbol_trading_rules(symbol)
        order = self._client.get_order_with_fills(symbol, order)

        sell_price = average_fill_price(
            order, fallback=float(pending.context.get("price", 0.0)) or 0.0
        )
        proceeds = net_proceeds(order, rules, fallback=record["quantity"] * sell_price)
        realized_pnl = proceeds - record["quote_spent"]

        self._ledger.record_sell(
            record["id"],
            sell_price,
            datetime.now(timezone.utc).isoformat(),
            realized_pnl,
        )
        self._failed_sell_notified.discard(record["id"])

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

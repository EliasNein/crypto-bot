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
from .notifier import send_notification
from .risk import KillSwitch

logger = logging.getLogger("grid_bot")


def compute_grid_levels(lower_limit: float, upper_limit: float, spacing_pct: float) -> list[float]:
    """
    Berechnet die Grid-Preisstufen geometrisch (prozentualer statt fixer
    Abstand): level[i+1] = level[i] * (1 + spacing_pct / 100), aufsteigend
    von lower_limit bis upper_limit.
    """
    if lower_limit <= 0 or upper_limit <= lower_limit or spacing_pct <= 0:
        raise ValueError(
            "Ungültige Grid-Parameter: lower_limit muss > 0, upper_limit > "
            "lower_limit und spacing_pct > 0 sein."
        )

    levels = [lower_limit]
    while levels[-1] * (1 + spacing_pct / 100) <= upper_limit * 1.0001:
        levels.append(levels[-1] * (1 + spacing_pct / 100))

    if len(levels) < 2:
        raise ValueError(
            "Preisspanne zu eng für den gewählten Grid-Abstand - es muss "
            "mindestens eine Kaufstufe und eine Ziel-Verkaufsstufe geben."
        )
    return levels


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
        """Verkauft jede offene Position, deren individuelles Sell-Target
        erreicht ist - unabhängig vom Trendbruch-Stop-Loss."""
        for record in self._ledger.open_positions():
            if price < record["target_sell_price"]:
                continue

            order = self._client.place_market_sell(self._config.symbol, record["quantity"])
            if order is not None:
                proceeds = float(order.get("cummulativeQuoteQty", record["quantity"] * price))
            else:
                proceeds = record["quantity"] * price
            realized_pnl = proceeds - record["quote_spent"]

            sold_at = datetime.now(timezone.utc).isoformat()
            self._ledger.record_sell(record["id"], price, sold_at, realized_pnl)

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

    def _process_buys(self, price: float) -> None:
        """
        Kauft an jeder Grid-Stufe, die der Preis seit dem letzten Zyklus
        tatsächlich durchquert hat (nicht: irgendeine Stufe irgendwo
        unterhalb des aktuellen Preises - siehe Crossing-Erkennung unten).
        """
        if self._last_seen_price is None:
            # Erster Zyklus: nur Referenzpreis setzen, noch nicht handeln.
            # Sonst würde ein Kaltstart mitten im Grid sofort JEDE Stufe
            # oberhalb des Startpreises gleichzeitig kaufen, nur weil sie
            # zufällig über dem aktuellen Preis liegt - nicht weil der
            # Preis tatsächlich gerade dort gefallen ist.
            return

        if price > self._last_seen_price:
            return  # Preis ist gestiegen/gleich geblieben, kein Fall durch eine Stufe

        for level_index, level_price in enumerate(self._levels[:-1]):
            # Halb-offenes Intervall [price, last_seen_price): der alte
            # Referenzpreis wurde im vorherigen Zyklus schon "gesehen"
            # (oder war der Kaltstart-Referenzpunkt ohne Handel) und soll
            # nicht erneut zählen; der neue, aktuelle Preis dagegen schon.
            if level_price >= self._last_seen_price or level_price < price:
                continue
            if self._ledger.open_position_for_level(level_index) is not None:
                continue

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
                quantity = float(order.get("executedQty", self._config.amount_per_level / price))
                quote_spent = float(order.get("cummulativeQuoteQty", self._config.amount_per_level))
            else:
                quantity = self._config.amount_per_level / price
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

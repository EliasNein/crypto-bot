"""
Backtesting für die DCA-Strategie.

Lädt echte historische Tageskurse von Binance (öffentliche API, kein
API-Key nötig - historische Daten sind auf dem Testnet nicht in
ausreichender Tiefe verfügbar, deshalb hier bewusst die Mainnet-
Marktdaten, es wird dabei nichts gehandelt, nur gelesen).

Simuliert dann: "Was wäre passiert, wenn der Bot in diesem Zeitraum
mit diesen Einstellungen gelaufen wäre?" und vergleicht das Ergebnis
mit einer Lump-Sum-Investition (alles am ersten Tag investiert).

Ausführen mit:  python -m dca_bot.backtest
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime

import requests

BINANCE_PUBLIC_API = "https://api.binance.com/api/v3/klines"


@dataclass
class BacktestResult:
    symbol: str
    start_date: str
    end_date: str
    num_buys: int
    total_invested: float
    total_units_bought: float
    final_price: float
    dca_final_value: float
    dca_return_pct: float
    lump_sum_final_value: float
    lump_sum_return_pct: float
    trade_log: list[tuple[str, float, float]] = field(default_factory=list)


def fetch_historical_klines(
    symbol: str, interval: str, start_date: str, end_date: str
) -> list[dict]:
    """
    Lädt historische Kerzen (Klines) von der öffentlichen Binance-API.

    interval: z.B. "1d" für Tageskerzen (passend zu unserem Standard-
    DCA-Intervall von 24h).
    """
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
    end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

    all_klines: list[dict] = []
    current_start = start_ts

    while current_start < end_ts:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": current_start,
            "endTime": end_ts,
            "limit": 1000,
        }
        response = requests.get(BINANCE_PUBLIC_API, params=params, timeout=10)
        response.raise_for_status()
        batch = response.json()

        if not batch:
            break

        for candle in batch:
            all_klines.append(
                {
                    "open_time": candle[0],
                    "close_price": float(candle[4]),
                    # Zusätzlich zum Schlusskurs: Low der Kerze - additiv,
                    # bestehende Konsumenten (DCA/Grid/Trend/Allocator)
                    # nutzen weiterhin nur close_price. Wird aktuell nur
                    # von trend_backtest.py (Stop-Limit-Zuverlässigkeits-
                    # Analyse, Low-basierter Fill-Proxy) genutzt.
                    "low_price": float(candle[3]),
                }
            )

        # Nächste Anfrage direkt nach der letzten geladenen Kerze starten,
        # um alle Daten im Zeitraum zu bekommen (API liefert max. 1000 pro Call).
        current_start = batch[-1][0] + 1

        if len(batch) < 1000:
            break

    return all_klines


def run_dca_backtest(
    klines: list[dict],
    symbol: str,
    quote_amount: float,
    buy_every_n_candles: int,
) -> BacktestResult:
    """
    Simuliert einen DCA-Kauf alle `buy_every_n_candles` Kerzen
    (bei Tageskerzen und buy_every_n_candles=1 => täglicher Kauf).
    """
    if not klines:
        raise ValueError("Keine Kursdaten zum Backtesten vorhanden.")

    total_invested = 0.0
    total_units = 0.0
    trade_log: list[tuple[str, float, float]] = []

    for i, candle in enumerate(klines):
        if i % buy_every_n_candles != 0:
            continue
        price = candle["close_price"]
        units_bought = quote_amount / price
        total_units += units_bought
        total_invested += quote_amount

        date_str = datetime.fromtimestamp(candle["open_time"] / 1000).strftime(
            "%Y-%m-%d"
        )
        trade_log.append((date_str, price, units_bought))

    final_price = klines[-1]["close_price"]
    dca_final_value = total_units * final_price
    dca_return_pct = (
        (dca_final_value - total_invested) / total_invested * 100
        if total_invested > 0
        else 0.0
    )

    # Vergleich: alles am ersten Tag investiert (Lump Sum)
    first_price = klines[0]["close_price"]
    lump_sum_units = total_invested / first_price
    lump_sum_final_value = lump_sum_units * final_price
    lump_sum_return_pct = (
        (lump_sum_final_value - total_invested) / total_invested * 100
        if total_invested > 0
        else 0.0
    )

    start_date = datetime.fromtimestamp(klines[0]["open_time"] / 1000).strftime(
        "%Y-%m-%d"
    )
    end_date = datetime.fromtimestamp(klines[-1]["open_time"] / 1000).strftime(
        "%Y-%m-%d"
    )

    return BacktestResult(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        num_buys=len(trade_log),
        total_invested=total_invested,
        total_units_bought=total_units,
        final_price=final_price,
        dca_final_value=dca_final_value,
        dca_return_pct=dca_return_pct,
        lump_sum_final_value=lump_sum_final_value,
        lump_sum_return_pct=lump_sum_return_pct,
        trade_log=trade_log,
    )


def print_report(result: BacktestResult) -> None:
    print(f"\n{'=' * 60}")
    print(f"DCA-Backtest: {result.symbol}")
    print(f"Zeitraum: {result.start_date} bis {result.end_date}")
    print(f"{'=' * 60}")
    print(f"Anzahl Käufe:              {result.num_buys}")
    print(f"Investierter Gesamtbetrag: {result.total_invested:,.2f}")
    print(f"Gekaufte Einheiten:        {result.total_units_bought:.6f}")
    print(f"Preis am Ende:             {result.final_price:,.2f}")
    print(f"{'-' * 60}")
    print(f"DCA-Strategie:")
    print(f"  Endwert:                 {result.dca_final_value:,.2f}")
    print(f"  Rendite:                 {result.dca_return_pct:+.2f} %")
    print(f"{'-' * 60}")
    print(f"Vergleich - Lump Sum (alles am ersten Tag investiert):")
    print(f"  Endwert:                 {result.lump_sum_final_value:,.2f}")
    print(f"  Rendite:                 {result.lump_sum_return_pct:+.2f} %")
    print(f"{'=' * 60}")

    diff = result.dca_return_pct - result.lump_sum_return_pct
    if diff > 0:
        print(f"-> DCA schlug Lump-Sum in diesem Zeitraum um {diff:.2f} Prozentpunkte.")
    else:
        print(
            f"-> Lump-Sum schlug DCA in diesem Zeitraum um {abs(diff):.2f} Prozentpunkte."
        )
    print(
        "Hinweis: Das ist nur EIN historischer Zeitraum. Wechsle Start-/End-Datum,\n"
        "um zu sehen, wie stark das Ergebnis je nach Marktphase schwankt -\n"
        "genau das ist der Kern der DCA-vs-Lump-Sum-Debatte aus unserer Recherche."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="DCA-Strategie-Backtest")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--start", default="2023-01-01", help="Format: YYYY-MM-DD")
    parser.add_argument("--end", default="2024-01-01", help="Format: YYYY-MM-DD")
    parser.add_argument(
        "--amount", type=float, default=15.0, help="Betrag pro Kauf (Quote-Währung)"
    )
    parser.add_argument(
        "--every-n-days",
        type=int,
        default=1,
        help="Kaufintervall in Tagen (1 = täglich)",
    )
    args = parser.parse_args()

    print(f"Lade historische Daten für {args.symbol} ({args.start} bis {args.end}) ...")
    klines = fetch_historical_klines(args.symbol, "1d", args.start, args.end)
    print(f"{len(klines)} Tageskerzen geladen.")

    result = run_dca_backtest(
        klines,
        symbol=args.symbol,
        quote_amount=args.amount,
        buy_every_n_candles=args.every_n_days,
    )
    print_report(result)


if __name__ == "__main__":
    main()

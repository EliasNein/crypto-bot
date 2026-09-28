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

Das Paar kommt standardmäßig aus DCA_SYMBOL (Umgebung oder .env), sonst
BTCUSDT - siehe apply_env_defaults(). Der Bericht nennt die verwendeten
Werte und ihre Herkunft.
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

BINANCE_PUBLIC_API = "https://api.binance.com/api/v3/klines"

logger = logging.getLogger(__name__)

# Symbolbindung vom 28.09.2026 (E6): Die Backtests rechnen standardmäßig
# mit dem Paar (und beim Grid mit Spanne, Abstand und Betrag), das der
# jeweilige Bot laut Umgebung/.env handelt. Ist nichts gesetzt, bleiben
# es die Werte, die bis dahin fest im Code standen - mit ihnen sind die
# Zahlen in trading-bot-projekt.md (5a, 6) gerechnet. Bewusst NICHT
# config_guard.DEFAULT_SYMBOL: ändert sich dessen Wert, dürfen die
# dokumentierten Zahlen nicht still mitwandern.
DOCUMENTED_SYMBOL = "BTCUSDT"


@dataclass(frozen=True)
class EnvDefault:
    """Ein Kommandozeilenwert, dessen Standard aus einer Bot-Variablen kommt."""

    attr: str  # Name im argparse-Namespace (Standard dort: None)
    env_var: str
    fallback: str | float
    label: str


def load_backtest_environment() -> None:
    """
    Liest die .env wie die Bots (bereits gesetzte Variablen gehen vor).
    Gebraucht werden daraus nur die Symbol- und Grid-Variablen; API-
    Schlüssel braucht kein Backtest, er fragt nur öffentliche Kerzen ab.
    """
    load_dotenv()


def apply_env_defaults(args, defaults: list[EnvDefault], env=None) -> list[str]:
    """
    Füllt die auf der Kommandozeile nicht angegebenen Werte: aus der
    Variablen des Bots, sonst aus dem dokumentierten Standard. Vorrang:
    Kommandozeile, Variable, Standard. Eine leere Variable gilt als nicht
    gesetzt (wie bei den Bots). Gibt die Berichtszeilen zurück - welcher
    Wert verwendet wurde und woher er kommt.
    """
    env = os.environ if env is None else env
    lines = []
    for default in defaults:
        value = getattr(args, default.attr)
        if value is not None:
            source = "Kommandozeile"
        else:
            raw = (env.get(default.env_var) or "").strip()
            cast = type(default.fallback)
            if raw:
                try:
                    value = cast(raw)
                except ValueError:
                    raise SystemExit(
                        f"{default.env_var}={raw!r} ist für den Backtest nicht "
                        f"verwendbar (erwartet: Zahl). Variable korrigieren oder "
                        f"den Wert auf der Kommandozeile angeben."
                    ) from None
                source = f"aus {default.env_var}"
            else:
                value = default.fallback
                source = f"Standard, {default.env_var} nicht gesetzt"
            setattr(args, default.attr, value)
        lines.append(f"  {default.label}: {value} ({source})")
    return lines


def print_used_settings(lines: list[str]) -> None:
    print("Verwendete Werte:")
    for line in lines:
        print(line)


_INTERVAL_UNIT_MS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}


def interval_ms(interval: str) -> int | None:
    """Länge einer Kerze in ms ("1d" -> 86.400.000); None bei unbekanntem Format (z.B. "1M")."""
    unit = _INTERVAL_UNIT_MS.get(interval[-1:]) if interval[-1:] != "M" else None
    if unit is None or not interval[:-1].isdigit():
        return None
    return int(interval[:-1]) * unit


def _utc_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def find_candle_gaps(open_times: list[int], step_ms: int) -> list[tuple[int, int, int]]:
    """
    Lücken zwischen aufeinanderfolgenden Kerzen: je Lücke (erste fehlende
    open_time, letzte fehlende open_time, Anzahl fehlender Kerzen).
    """
    gaps = []
    for previous, current in zip(open_times, open_times[1:]):
        missing = (current - previous) // step_ms - 1
        if missing > 0:
            gaps.append((previous + step_ms, current - step_ms, missing))
    return gaps


def warn_about_candle_gaps(
    symbol: str, interval: str, start_ts: int, klines: list[dict]
) -> None:
    """
    Warnt, wenn Kerzen fehlen (Symbolbindung vom 28.09.2026, E7) - etwa
    bei BTCUSDC, dessen Tageskerzen vom 30.09.2022 bis 11.03.2023 fehlen,
    oder wenn ein Paar erst nach dem angefragten Beginn gelistet wurde
    (BTCEUR ab 03.01.2020). Ein Backtest über eine Lücke hinweg rechnet
    stillschweigend, als hätte es den Zeitraum nicht gegeben.

    Nur eine Warnung, nie ein Fehler: Dieselbe Funktion versorgt den
    Live-Vorlauf von Trend-Bot und Allocator, und der darf daran nie
    scheitern. Deshalb fängt der Aufrufer auch jeden Fehler dieser Prüfung.
    """
    step = interval_ms(interval)
    if step is None or not klines:
        return
    open_times = [candle["open_time"] for candle in klines]
    if open_times[0] - start_ts > step:
        logger.warning(
            "[KERZEN-LUECKE] %s %s: Daten erst ab %s (angefragt ab %s) - das "
            "Paar ist vermutlich erst später gelistet. Der Zeitraum davor fehlt "
            "in der Rechnung.",
            symbol,
            interval,
            _utc_day(open_times[0]),
            _utc_day(start_ts),
        )
    gaps = find_candle_gaps(open_times, step)
    if gaps:
        first, last, missing = max(gaps, key=lambda gap: gap[2])
        logger.warning(
            "[KERZEN-LUECKE] %s %s: %d Kerzen fehlen in %d Lücke(n), die größte "
            "mit %d Kerzen von %s bis %s. Ergebnisse über diesen Zeitraum sind "
            "nicht belastbar - die Rechnung überspringt ihn stillschweigend.",
            symbol,
            interval,
            sum(gap[2] for gap in gaps),
            len(gaps),
            missing,
            _utc_day(first),
            _utc_day(last),
        )


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

    try:
        warn_about_candle_gaps(symbol, interval, start_ts, all_klines)
    except Exception:  # noqa: BLE001 - die Warnung darf nie den Abruf kippen (E7)
        logger.debug("Lückenprüfung übersprungen", exc_info=True)
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


ENV_DEFAULTS = [EnvDefault("symbol", "DCA_SYMBOL", DOCUMENTED_SYMBOL, "Symbol")]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="DCA-Strategie-Backtest")
    parser.add_argument(
        "--symbol", default=None, help=f"Standard: DCA_SYMBOL, sonst {DOCUMENTED_SYMBOL}"
    )
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
    args = parser.parse_args(argv)
    load_backtest_environment()
    print_used_settings(apply_env_defaults(args, ENV_DEFAULTS))

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

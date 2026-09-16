"""
Konsistenz-Check beim Bot-Start (Stufe 2 der Verbesserungsvorschlaege,
Punkt 3 in modifizierter Form - Teil A).

**Was vorher fehlte.** Der `balance_guard` (W11) lief ausschliesslich VOR
EINEM VERKAUF. Das hatte zwei Luecken:

1. **Der DCA-Bot war gar nicht angeschlossen.** Er verkauft nie, hatte
   also nie einen Verkaufspfad - und damit ueberhaupt keinen Moment, in
   dem seine Buchhaltung je gegen die Realitaet geprueft wurde. Sein
   Ledger ist aber die Kostenbasis des Portfolio-Stop-Loss: Steht dort
   mehr, als tatsaechlich da ist, bewertet `PortfolioStopLoss` die
   Position mit einer zu grossen Menge und loest zu spaet aus.
2. **Grid und Trend prueften nur im Verkaufsmoment.** Zwischen zwei
   Verkaeufen koennen Wochen liegen - beim Trend-Bot auch Monate, wenn
   kein Signal kommt. Eine Diskrepanz, die waehrend einer Downtime
   entstanden ist (manueller Trade ueber die Boersen-Oberflaeche, ein
   anderer Bot, ein von Hand editiertes Ledger), blieb bis dahin
   unsichtbar.

Der Start ist der natuerliche zweite Zeitpunkt: Er liegt nach jeder
Downtime, nach jedem Deployment und nach jeder manuellen Aenderung an
den Ledger-Dateien - also genau nach den Ereignissen, die eine
Diskrepanz ueberhaupt erzeugen.

**Laut, aber nicht blockierend.** Genau wie die weiche Pruefung im
Verkaufspfad (siehe `ledger_exceeds_account` in balance_guard.py):
gemeldet wird deutlich, gestoppt wird nichts. Ein Bot, der wegen eines
Buchhaltungsverdachts gar nicht erst startet, loest das Problem nicht -
er nimmt nur zusaetzlich die Faehigkeit weg, offene Positionen
abzusichern und zu schliessen. Dieselbe Abwaegung wie beim
Grid-Trendbruch-Stop-Loss, der Verkaeufe ebenfalls durchlaesst.

**Warum hier und nicht in balance_guard.py:** Das Modul sagt in seinem
Docstring ausdruecklich zu, rein zu sein - keine Netzwerkaufrufe, kein
Zustand, gleiches Muster wie order_utils.py und die drei `*_signals.py`.
Die Client-Aufrufe gehoeren deshalb hierher. `balance_guard.py` liefert
weiterhin die reine Bewertung, dieses Modul beschafft ihr die Daten.

**Der Aufruf liegt in der bestehenden `safe_startup_reconciliation()`-
Liste** der drei `main*.py`, und zwar als LETZTER Schritt. Zwei Gruende:
Die Reconciliation davor kann Ledger-Eintraege nachtragen (K2) - ein
Abgleich davor verglicher gegen einen veralteten Stand. Und der
W18-Schutz gilt damit automatisch: `get_symbol_trading_rules()` reicht
einen Fehlschlag bewusst weiter, und ausserhalb der Hauptschleife wuerde
das sonst eine systemd-Neustartschleife ausloesen.
"""

from __future__ import annotations

import logging

from .balance_guard import build_snapshot, describe, ledger_exceeds_account
from .notifier import send_notification


def report_ledger_vs_account(
    *,
    client,
    logger: logging.Logger,
    symbol: str,
    bot_name: str,
    own_open_quantity: float,
    notify_tag: str,
    ledger_label: str,
) -> bool:
    """
    Vergleicht beim Start, was das eigene Ledger als offen fuehrt, mit
    dem, was auf dem geteilten Konto fuer diesen Bot ueberhaupt da sein
    KANN. Gibt zurueck, ob eine Diskrepanz gemeldet wurde.

    `own_open_quantity` ist die Menge des Base-Assets aus ECHTEN (nicht
    simulierten) Positionen - jeder Bot bestimmt sie aus seinem eigenen
    Ledger, weil die drei Ledger unterschiedlich aufgebaut sind.

    **Das Gate ist die Menge, nicht `trading_enabled`** - und das ist der
    eine Punkt, an dem dieser Check bewusst vom Verkaufspfad abweicht.
    Dort wird im Dry-Run abgeschaltet, weil ein simulierter Verkauf gar
    keine Order platziert; die Pruefung haette schlicht keinen
    Gegenstand. Hier ist die Frage eine andere: "Gibt es ueberhaupt etwas
    zu pruefen?" Und die haengt an echten Positionen, nicht am aktuellen
    Schalterstand. Ein auf Dry-Run zurueckgestellter Bot mit echtem
    Altbestand ist gerade der interessante Fall - da hat jemand den
    Schalter umgelegt, und die Assets liegen weiterhin an der Boerse. Ist
    die Menge dagegen 0 (Dry-Run-Bot mit frischem Ledger, der Normalfall
    im Testbetrieb), passiert gar nichts und es wird kein einziger
    API-Aufruf verbraucht.

    Ein nicht abrufbares Guthaben ergibt KEINEN Befund: Ein
    Netzwerkfehler ist keine Aussage ueber das Konto. Gleiche Haltung wie
    in `get_asset_balance()` und im Verkaufspfad.
    """
    if own_open_quantity <= 0:
        logger.info(
            "Bestandsabgleich beim Start: %s fuehrt keine echten offenen "
            "Mengen - nichts zu pruefen.",
            ledger_label,
        )
        return False

    # Darf werfen: safe_startup_reconciliation() faengt es ab (W18).
    # Absichtlich nicht hier abgefangen - ein stiller Fehlschlag waere
    # schlechter als eine Zeile im Log plus Telegram.
    rules = client.get_symbol_trading_rules(symbol)

    snapshot = build_snapshot(
        client.get_asset_balance(rules.base_asset),
        client.get_open_orders(symbol),
        bot_name,
    )
    if snapshot is None:
        logger.warning(
            "Bestandsabgleich beim Start: Guthaben fuer %s nicht abrufbar - "
            "der Abgleich entfaellt. Das ist keine Aussage ueber das Konto, "
            "der naechste Verkauf prueft ohnehin erneut.",
            rules.base_asset,
        )
        return False

    if not ledger_exceeds_account(snapshot, own_open_quantity, rules.step_size):
        logger.info(
            "Bestandsabgleich beim Start in Ordnung: %s. (%s)",
            ledger_label,
            describe(snapshot, own_open_quantity),
        )
        return False

    logger.error(
        "%s %s fuehrt beim Start mehr %s als auf dem Konto fuer diesen Bot "
        "vorhanden sein kann. %s. Da sich DCA, Grid und Trend ein Konto "
        "teilen, kann das bedeuten, dass ein anderer Bot oder ein manueller "
        "Trade Bestand verkauft hat, der hier noch als offen gefuehrt wird. "
        "Der Bot laeuft trotzdem weiter - bitte mit "
        "'python -m dca_bot.audit_positions' pruefen.",
        notify_tag,
        ledger_label,
        rules.base_asset,
        describe(snapshot, own_open_quantity),
    )
    send_notification(
        f"{notify_tag} Beim Start: {ledger_label} fuehrt mehr "
        f"{rules.base_asset}, als fuer diesen Bot auf dem Konto sein kann. "
        f"{describe(snapshot, own_open_quantity)}. Geteiltes Konto - der Bot "
        "laeuft weiter, bitte Positionen pruefen "
        "(python -m dca_bot.audit_positions)."
    )
    return True

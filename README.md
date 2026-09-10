# Trading-Bots (Binance Testnet)

Zwei komplett eigenständige Bots im selben Projekt, beide gegen die
**Binance Testnet API** – es wird zu keinem Zeitpunkt echtes Geld bewegt,
solange du keine echten API-Keys einträgst:

- **DCA-Bot** (`dca_bot/main.py`): kauft in festen Intervallen einen festen
  Betrag eines Assets (Dollar-Cost-Averaging).
- **Grid-Trading-Bot** (`dca_bot/main_grid.py`, siehe Abschnitt 9): kauft an
  festen Preisstufen innerhalb einer Preisspanne und verkauft jede Position
  einzeln wieder, wenn der Preis eine Stufe höher steigt.

Beide teilen sich nur die Binance-/Telegram-Zugangsdaten in der `.env` -
Zustand (Trade-Historie, Notaus, Stop-Loss) ist für jeden Bot komplett
getrennt, sie können unabhängig voneinander (auch gleichzeitig) laufen.

## 1. Voraussetzungen

- Python 3.10+
- Ein kostenloser Testnet-Account: https://testnet.binance.vision/
  (Login mit GitHub-Account, danach "Generate HMAC_SHA256 Key" für API Key + Secret)

## 2. Installation

```bash
cd trading-bot
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Konfiguration

```bash
cp .env.example .env
```

Dann `.env` öffnen und deine Testnet-Keys eintragen:

```
BINANCE_API_KEY=dein_echter_testnet_key
BINANCE_API_SECRET=dein_echtes_testnet_secret
DCA_BOT_ENABLE_TRADING=false

# Risikomanagement (optional, Defaults siehe dca_bot/config.py)
DCA_BOT_KILL_SWITCH_FILE=STOP          # Existiert diese Datei -> Bot stoppt sofort
DCA_BOT_HALT=false                     # Alternative zur Datei: auf "true" setzen zum Stoppen
DCA_BOT_STOP_LOSS_PCT=25.0             # Käufe pausieren ab X% Verlust ggü. Einsatz (0 = aus)
DCA_BOT_STATE_FILE=data/trade_ledger.json

# Telegram-Benachrichtigungen (optional, leer lassen zum Deaktivieren)
TELEGRAM_BOT_TOKEN=dein_telegram_bot_token
TELEGRAM_CHAT_ID=deine_telegram_chat_id
```

**Wichtig:** `DCA_BOT_ENABLE_TRADING` bleibt zunächst auf `false`. In diesem Modus
simuliert der Bot jeden Kauf nur und loggt ihn ("[DRY-RUN]"), platziert aber keine
echte Order. Erst wenn du das Verhalten im Log geprüft hast, auf `true` stellen,
um echte Testnet-Orders (mit Test-Guthaben, kein echtes Geld) zu platzieren.

Weitere Einstellungen (Symbol, Betrag, Intervall, Tageslimit) befinden sich aktuell
als Defaults in `dca_bot/config.py` – für den nächsten Schritt können wir diese
auch über Umgebungsvariablen konfigurierbar machen.

## 4. Starten

```bash
python -m dca_bot.main
```

Logs erscheinen sowohl in der Konsole als auch in `logs/dca_bot.log`.
Beenden mit `Strg+C`.

## 5. Projektstruktur

```
trading-bot/
├── dca_bot/
│   ├── config.py         # Zentrale Konfiguration DCA-Bot (liest .env)
│   ├── binance_client.py # Wrapper um die Binance-API (Testnet, Buy+Sell)
│   ├── strategy.py       # DCA-Logik inkl. Tageslimit als Notbremse
│   ├── risk.py           # Notaus, Trade-Ledger, Portfolio-Stop-Loss (DCA)
│   ├── notifier.py       # Telegram-Benachrichtigungen (optional, geteilt)
│   ├── main.py           # Einstiegspunkt DCA-Bot
│   ├── grid_config.py    # Zentrale Konfiguration Grid-Bot (liest .env)
│   ├── grid_risk.py      # Positions-Ledger, Trendbruch-Stop-Loss (Grid)
│   ├── grid_strategy.py  # Grid-Kauf-/Verkaufslogik
│   ├── main_grid.py      # Einstiegspunkt Grid-Bot
│   ├── reset_stop_loss.py       # CLI: DCA-Stop-Loss-Pause zurücksetzen
│   └── reset_grid_stop_loss.py  # CLI: Grid-Stop-Loss-Pause zurücksetzen
├── requirements.txt
├── .env.example
└── README.md
```

## 6. Eingebaute Sicherheitsmechanismen (schon jetzt)

- **Dry-Run per Default**: keine echten Orders ohne explizites Opt-in.
- **Tageslimit** (`max_daily_spend` in `config.py`): verhindert, dass bei einem
  Bug (z.B. Endlosschleife) unbegrenzt viele Käufe ausgelöst werden. Wird aus
  der persistenten Trade-Historie (`data/trade_ledger.json`) berechnet, gilt
  also auch nach einem Neustart des Bots weiter.
- **Notaus**: Läuft die Datei `STOP` (Pfad über `DCA_BOT_KILL_SWITCH_FILE`
  konfigurierbar) im Projektverzeichnis, oder ist `DCA_BOT_HALT=true`
  gesetzt, stoppt der Bot sofort und sauber – auch mitten in einem laufenden
  Kaufzyklus, nicht erst beim nächsten Intervall.
- **Portfolio-Stop-Loss** (`DCA_BOT_STOP_LOSS_PCT`, Default 25%): Fällt der
  aktuelle Wert der bisher gekauften Position mehr als X% unter die Summe
  der Einkaufspreise, pausiert der Bot weitere Käufe und loggt das deutlich.
  Es wird **nicht automatisch verkauft** – das ist bewusst eine separate,
  spätere Entscheidung. Die Pause hebt sich auch **nicht von selbst** auf,
  wenn sich der Kurs wieder erholt (Whipsaw-Risiko, siehe Kommentar in
  `dca_bot/risk.py`) – manueller Reset nötig, entweder mit
  `python -m dca_bot.reset_stop_loss` oder durch Löschen der Datei unter
  `DCA_BOT_STOP_LOSS_STATE_FILE` (Default `data/stop_loss_paused.json`).
- **Fehlerbehandlung pro Zyklus**: Ein einzelner Fehler (z.B. API-Timeout)
  beendet nicht den ganzen Bot, sondern wird geloggt; der nächste Zyklus läuft normal weiter.

## 7. Telegram-Benachrichtigungen (optional)

Der Bot kann optional Ereignisse per Telegram-Nachricht melden. Ist nichts
konfiguriert, bleibt Telegram komplett deaktiviert (Default) - der Bot läuft
identisch weiter, es wird nur nichts verschickt.

### 7.1 Einrichtung

1. **Bot erstellen:** Mit [@BotFather](https://t.me/BotFather) in Telegram
   chatten, `/newbot` senden und den Anweisungen folgen (Name + Username
   vergeben). Am Ende bekommst du einen **Bot-Token** (Format
   `123456789:AAxx...`) - das ist `TELEGRAM_BOT_TOKEN`.
2. **Chat mit deinem Bot starten:** Deinen neuen Bot in Telegram suchen und
   ihm eine beliebige erste Nachricht schicken (z.B. "Hallo") - ohne diesen
   Schritt darf der Bot dir laut Telegram-API nicht schreiben.
3. **Chat-ID herausfinden**, eine der folgenden Optionen:
   - Kurz [@userinfobot](https://t.me/userinfobot) anschreiben, er zeigt
     deine eigene Chat-ID an, oder
   - `https://api.telegram.org/bot<TOKEN>/getUpdates` im Browser aufrufen
     (nachdem du deinem Bot wie in Schritt 2 geschrieben hast) und im JSON
     nach `"chat":{"id": ...}` suchen.
4. Beide Werte in `.env` eintragen:
   ```
   TELEGRAM_BOT_TOKEN=123456789:AAxx...
   TELEGRAM_CHAT_ID=987654321
   ```
5. Neu starten - im Log erscheint dann `Telegram-Benachrichtigungen aktiv.`

### 7.2 Welche Ereignisse gemeldet werden

- **Käufe**: jeder ausgeführte Kaufzyklus - `[KAUF]` bei einer echten Order,
  `[DRY-RUN]` bei einem simulierten Kauf, `[FEHLER]` wenn eine echte Order
  bei der Börse fehlschlägt.
- **Stop-Loss**: `[STOP-LOSS]`, wenn der Portfolio-Stop-Loss auslöst (siehe
  Abschnitt 6) - nur einmal beim Auslösen, keine Wiederholung, solange er
  pausiert bleibt.
- **Notaus**: `[NOTAUS]`, sobald der Notaus-Mechanismus greift.
- **Fehler**: `[FEHLER]` bei unerwarteten Fehlern im Kaufzyklus (z.B.
  API-Timeout), zusätzlich zum Log-Eintrag.
- **Tageszusammenfassung**: `[TAGESZUSAMMENFASSUNG]` einmal pro
  abgeschlossenem Kalendertag mit Trade-Anzahl, Ausgaben und
  Stop-Loss-Status.

Ein Telegram-Ausfall, ein falscher Token oder ein Netzwerkfehler lässt den
Bot niemals abstürzen oder einen Kaufzyklus abbrechen - jeder Fehler beim
Senden wird nur geloggt (siehe `dca_bot/notifier.py`).

## 9. Spot-Grid-Trading-Bot (zweiter, eigenständiger Bot)

Kauft an festen Preisstufen ("Grid-Stufen") innerhalb einer konfigurierten
Preisspanne und verkauft jede einzelne Position wieder, sobald der Preis auf
die nächsthöhere Stufe steigt - Spot only, kein Hebel, kein
Liquidationsrisiko. Siehe `trading-bot-projekt.md` Abschnitt 5 für die
Recherche dazu: der Erwartungswert ist vor Gebühren akademisch mathematisch
null, der Sinn dieser Strategie liegt in der einfachen, latenzunkritischen
Umsetzung, nicht in überlegener Rendite. Haupt-Risiko ist ein Trendbruch.

### 9.1 Konfiguration

Zusätzlich zu den Binance-/Telegram-Zugangsdaten oben (werden mitgenutzt):

```
GRID_SYMBOL=BTCUSDT
GRID_LOWER_LIMIT=70000.0      # Untere Grid-Grenze - AN AKTUELLEN MARKT ANPASSEN!
GRID_UPPER_LIMIT=90000.0      # Obere Grid-Grenze - AN AKTUELLEN MARKT ANPASSEN!
GRID_SPACING_PCT=1.5          # Abstand zwischen den Stufen in %
GRID_AMOUNT_PER_LEVEL=15.0    # Betrag pro Stufe in Quote-Währung
GRID_INTERVAL_MINUTES=5       # Wie oft der Preis geprüft wird
GRID_BOT_ENABLE_TRADING=false
GRID_KILL_SWITCH_FILE=STOP_GRID
GRID_BOT_HALT=false
GRID_STOP_LOSS_PCT=15.0
GRID_STATE_FILE=data/grid_positions.json
GRID_STOP_LOSS_STATE_FILE=data/grid_stop_loss_paused.json
```

**Wichtig:** `GRID_LOWER_LIMIT`/`GRID_UPPER_LIMIT` sind Platzhalter-Defaults -
unbedingt vor dem Start an den aktuellen Marktpreis anpassen, sonst kauft
(im Dry-Run: simuliert) der Bot ggf. weit weg vom echten Kurs.

### 9.2 Starten

```bash
python -m dca_bot.main_grid
```

Läuft komplett unabhängig vom DCA-Bot (auch parallel), eigenes Log unter
`logs/grid_bot.log`.

### 9.3 Kernlogik

- Die Grid-Stufen werden geometrisch berechnet (`level[i+1] = level[i] * (1 +
  GRID_SPACING_PCT/100)`), nicht linear.
- Pro Stufe kann höchstens eine Position gleichzeitig offen sein. Jede
  Position merkt sich ihre Kaufstufe und ihr individuelles Verkaufsziel (die
  nächsthöhere Stufe) - Verkäufe sind dadurch immer eindeutig einer
  bestimmten Kaufstufe zugeordnet, nie "irgendeine" Position.
- Käufe werden über eine Crossing-Erkennung ausgelöst (Vergleich mit dem
  zuletzt beobachteten Preis), nicht durch einen einfachen Vergleich mit dem
  aktuellen Preis - sonst würde ein Kaltstart mitten im Grid sofort jede
  Stufe oberhalb des Startpreises gleichzeitig kaufen. Fällt der Preis in
  einem Intervall durch mehrere Stufen auf einmal (z.B. bei einem Crash),
  werden alle tatsächlich durchquerten Stufen gekauft.
- Maximale Kapitalbindung ist durch das Design von selbst begrenzt: Anzahl
  Grid-Stufen × `GRID_AMOUNT_PER_LEVEL` - kein zusätzliches Tageslimit nötig.

### 9.4 Sicherheitsmechanismen (eigenständig vom DCA-Bot)

- **Dry-Run per Default**, analog zum DCA-Bot.
- **Notaus**: eigene Datei (`GRID_KILL_SWITCH_FILE`, Default `STOP_GRID`)
  und eigene Env-Variable (`GRID_BOT_HALT`) - unabhängig vom DCA-Notaus.
- **Trendbruch-Stop-Loss** (`GRID_STOP_LOSS_PCT`, Default 15%): Fällt der
  Marktpreis mehr als X% unter `GRID_LOWER_LIMIT`, pausiert der Bot neue
  Käufe. Bereits offene Positionen werden weiterhin normal verkauft, wenn
  ihr Ziel erreicht wird (Verkäufe reduzieren Risiko, statt es zu erhöhen).
  Latched wie der DCA-Stop-Loss: kein automatischer Reset, manuell mit
  `python -m dca_bot.reset_grid_stop_loss` oder durch Löschen der Datei
  unter `GRID_STOP_LOSS_STATE_FILE`.
- **Telegram-Benachrichtigungen** (falls konfiguriert, siehe Abschnitt 7):
  `[GRID-KAUF]`/`[GRID-KAUF DRY-RUN]`, `[GRID-VERKAUF]` (mit realisiertem
  Gewinn/Verlust dieser Position), `[GRID-STOP-LOSS]`, `[GRID-NOTAUS]`,
  `[GRID-FEHLER]`.

## 10. Nächste Ausbaustufen (siehe trading-bot-projekt.md)

- [ ] Konfiguration vollständig über `.env` statt Code-Defaults
- [x] Persistente Speicherung der Trade-Historie (`data/trade_ledger.json`)
- [ ] Backtesting-Skript für die DCA-Logik auf historischen Daten
- [x] Grid-Trading-Strategie als zweiter, eigenständiger Bot (siehe Abschnitt 9)

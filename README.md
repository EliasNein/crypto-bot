# DCA-Bot (Binance Testnet)

Erster Baustein des Trading-Bot-Projekts: ein einfacher Dollar-Cost-Averaging-Bot,
der in festen Intervallen einen festen Betrag eines Assets kauft. Läuft ausschließlich
gegen die **Binance Testnet API** – es wird zu keinem Zeitpunkt echtes Geld bewegt,
solange du keine echten API-Keys einträgst.

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
│   ├── config.py         # Zentrale Konfiguration (liest .env)
│   ├── binance_client.py # Wrapper um die Binance-API (Testnet)
│   ├── strategy.py       # DCA-Logik inkl. Tageslimit als Notbremse
│   ├── risk.py           # Notaus, Trade-Ledger, Portfolio-Stop-Loss
│   ├── notifier.py       # Telegram-Benachrichtigungen (optional)
│   └── main.py           # Einstiegspunkt / Ausführungsschleife
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

Wenn `TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID` gesetzt sind, schickt der Bot
Nachrichten für:

- jeden ausgeführten Kaufzyklus (`[KAUF]` für echte Orders, `[DRY-RUN]` für
  simulierte, `[FEHLER]` wenn eine echte Order bei der Börse fehlschlägt),
- ein Auslösen des Portfolio-Stop-Loss (`[STOP-LOSS]`),
- ein Auslösen des Notaus (`[NOTAUS]`),
- unerwartete Fehler im Kaufzyklus (`[FEHLER]`),
- eine Tageszusammenfassung (`[TAGESZUSAMMENFASSUNG]`) einmal pro
  abgeschlossenem Kalendertag mit Trade-Anzahl, Ausgaben und Stop-Loss-Status.

Sind beide Variablen leer, bleibt Telegram komplett deaktiviert - das ist der
Default. Ein Telegram-Ausfall oder ein falscher Token lässt den Bot niemals
abstürzen, es wird nur geloggt (siehe `dca_bot/notifier.py`).

Bot-Token bekommst du von [@BotFather](https://t.me/BotFather), deine Chat-ID
z.B. über [@userinfobot](https://t.me/userinfobot) oder indem du deinem Bot
eine Nachricht schickst und dann `https://api.telegram.org/bot<TOKEN>/getUpdates`
im Browser aufrufst.

## 8. Nächste Ausbaustufen (siehe trading-bot-projekt.md)

- [ ] Konfiguration vollständig über `.env` statt Code-Defaults
- [x] Persistente Speicherung der Trade-Historie (`data/trade_ledger.json`)
- [ ] Backtesting-Skript für die DCA-Logik auf historischen Daten
- [ ] Danach: Grid-Trading- bzw. Mean-Reversion-Strategie als zweiter Baustein

# Trading-Bots (Binance Testnet)

Drei komplett eigenständige Trading-Bots plus ein steuernder Zusatzprozess
im selben Projekt, alle gegen die **Binance Testnet API** – es wird zu
keinem Zeitpunkt echtes Geld bewegt, solange du keine echten API-Keys
einträgst:

- **DCA-Bot** (`dca_bot/main.py`): kauft in festen Intervallen einen festen
  Betrag eines Assets (Dollar-Cost-Averaging).
- **Grid-Trading-Bot** (`dca_bot/main_grid.py`, siehe Abschnitt 3.1): kauft an
  festen Preisstufen innerhalb einer Preisspanne und verkauft jede Position
  einzeln wieder, wenn der Preis eine Stufe höher steigt.
- **Trend-Following-Bot** (`dca_bot/main_trend.py`, siehe Abschnitt 3.2):
  EMA-Crossover mit Trendstärke-Filter auf Tageskerzen, long-only, mit
  festem Stop-Loss pro Trade. Vor dem ersten Dry-Run per Backtest über
  mehrere historische Marktphasen validiert (siehe `trend_backtest.py`).
- **Kapital-Allocator** (`dca_bot/main_allocator.py`, siehe Abschnitt 3.3):
  kein eigener Trading-Bot, sondern ein steuernder Zusatzprozess, der
  Kapital stufenlos zwischen DCA- und Trend-Following-Bot umschichtet, je
  nach aktueller Trendstärke. Platziert selbst nie Orders, wirkt sich auf
  DCA/Trend nur nach explizitem Opt-in aus.

Alle vier teilen sich nur die Binance-/Telegram-Zugangsdaten in der `.env` -
Zustand (Trade-Historie, Notaus, Stop-Loss) ist für jeden Bot komplett
getrennt, sie können unabhängig voneinander (auch gleichzeitig) laufen.

## Dashboard-App

Ein separates, read-only Web-Dashboard zur Anzeige der Bot-Stats (aktuelle
Positionen, Gesamtgewinn/-verlust, Trade-Export für die Steuererklärung)
liegt in einem eigenen Repository:
[crypto-bot-app](https://github.com/EliasNein/crypto-bot-app).

Komplett unabhängig von diesem Projekt - liest nur die Ledger-Dateien, hat
keinen Zugriff auf API-Keys oder Trading-Funktionen.

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
USE_TESTNET=true                       # false = ECHTE Börse, echtes Geld
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

Symbol, Betrag, Intervall und Tageslimit des DCA-Bots sind seit dem
W12-Fix ebenfalls über die `.env` einstellbar (`DCA_SYMBOL`,
`DCA_QUOTE_AMOUNT`, `DCA_INTERVAL_HOURS`, `DCA_MAX_DAILY_SPEND`) – sie
standen als einzige der vier Bots vorher nur als Default im Code. Die
Defaults sind unverändert.

**`USE_TESTNET` ist der Live-Schalter des Projekts** (Default `true`).
Auf `false` gesetzt, handeln alle vier Prozesse gegen die echte Börse mit
echtem Geld – das meldet jeder von ihnen beim Start unübersehbar im Log
und per Telegram, eine stille Umschaltung gibt es nicht. Im Live-Modus
werden ausserdem Telegram-Zugangsdaten und alle Positionsgrössen zur
Pflichtangabe (siehe Abschnitt 6), und die Testwerte aus `.env.example`
werden abgelehnt. Ein Testwert, der nach der Kalibrierung bewusst gelten
soll, wird mit Name und Wert bestätigt, z.B.
`LIVE_CONFIRMED_VALUES=TREND_STOP_LIMIT_OFFSET_PCT=0.5`. Nicht vergessen: Testnet-Keys
funktionieren an der echten Börse nicht, `BINANCE_API_KEY`/`SECRET`
müssen mitgewechselt werden.

### 3.1 Grid-Bot

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

### 3.2 Trend-Following-Bot

Zusätzlich zu den Binance-/Telegram-Zugangsdaten oben (werden mitgenutzt).
Defaults entsprechen exakt den im Backtest getesteten Werten:

```
TREND_SYMBOL=BTCUSDT
TREND_EMA_FAST_PERIOD=20      # Schneller EMA in Tagen
TREND_EMA_SLOW_PERIOD=50      # Langsamer EMA in Tagen
TREND_MIN_GAP_PCT=1.0         # Trendstärke-Filter: Mindestabstand der EMAs in %
TREND_AMOUNT_PER_TRADE=15.0   # Positionsgröße pro Trade in Quote-Währung
TREND_INTERVAL_HOURS=24       # Tageskerzen -> einmal täglich prüfen
TREND_BOT_ENABLE_TRADING=false
TREND_KILL_SWITCH_FILE=STOP_TREND
TREND_STOP_LOSS_PCT=10.0      # Fixer Stop-Loss unterhalb des Einstiegspreises
TREND_STOP_LIMIT_OFFSET_PCT=0.5  # Abstand Stop-/Limit-Preis der echten Exchange-Stop-Order (siehe trading-bot-projekt.md 7.3)
```

### 3.3 Kapital-Allocator

Zusätzlich zu den Binance-/Telegram-Zugangsdaten oben (werden mitgenutzt):

```
ALLOCATOR_SYMBOL=BTCUSDT
ALLOCATOR_EMA_FAST_PERIOD=20
ALLOCATOR_EMA_SLOW_PERIOD=50
ALLOCATOR_ZERO_ANCHOR_PCT=0.0     # EMA-Abstand, ab dem 0% Trend-Anteil gilt
ALLOCATOR_FULL_ANCHOR_PCT=3.0     # EMA-Abstand, ab dem 100% Trend-Anteil gilt
ALLOCATOR_SMOOTHING_PERIOD=3      # EMA-Glättung der Zuteilung, in TAGEN
ALLOCATOR_INTERVAL_MINUTES=60     # Wie oft der Prozess aufwacht (nicht: EMA-Takt)
ALLOCATOR_NOTIFY_THRESHOLD_PP=15.0
ALLOCATOR_KILL_SWITCH_FILE=STOP_ALLOCATOR
ALLOCATOR_HALT=false
ALLOCATOR_STATE_FILE=data/allocator_state.json
```

Die Ankerpunkte (0%/3%) sind ein bewusster Ausgangspunkt, kein empirisch
hergeleiteter Optimalwert - siehe Backtest-Ergebnisse zur Einordnung.

**Wirkung auf DCA/Trend nur nach explizitem Opt-in:** Standardmäßig
kennen weder der DCA-Bot noch der Trend-Bot den Allocator. Erst wenn du
in der `.env` zusätzlich `DCA_ALLOCATOR_STATE_FILE` bzw.
`TREND_ALLOCATOR_STATE_FILE` auf denselben Pfad wie `ALLOCATOR_STATE_FILE`
setzt, skaliert der jeweilige Bot den Betrag einer NEUEN Order mit der
aktuellen Zuteilung. Offene Positionen bleiben davon immer unberührt.

## 4. Starten

Jeder Baustein ist ein eigener Prozess und läuft komplett unabhängig von
den anderen (auch parallel):

| Baustein | Start | Log |
|---|---|---|
| DCA-Bot | `python -m dca_bot.main` | `logs/dca_bot.log` |
| Grid-Bot | `python -m dca_bot.main_grid` | `logs/grid_bot.log` |
| Trend-Following-Bot | `python -m dca_bot.main_trend` | `logs/trend_bot.log` |
| Kapital-Allocator | `python -m dca_bot.main_allocator` | `logs/allocator.log` |

Logs erscheinen sowohl in der Konsole als auch in der jeweiligen Datei.
Beenden mit `Strg+C`. Trend-Bot und Allocator laden beim Start
automatisch echte historische Tageskerzen (öffentliche Binance-API),
damit die EMAs nicht bei Null anfangen müssen.

## 5. Projektstruktur

```
trading-bot/
├── dca_bot/
│   ├── config.py         # Zentrale Konfiguration DCA-Bot (liest .env)
│   ├── config_guard.py   # Live-Schalter + Pflichtvariablen-Check (geteilt)
│   ├── balance_guard.py  # Konsistenz-Check vor jedem Verkauf (geteilt)
│   ├── startup_checks.py # Konsistenz-Check beim Bot-Start (geteilt)
│   ├── binance_client.py # Wrapper um die Binance-API (Testnet, Buy+Sell, Handelsregeln)
│   ├── order_utils.py    # Quantisierung auf tickSize/stepSize + Gebührenkorrektur (geteilt)
│   ├── pending_orders.py # Idempotente Order-Platzierung + Ground-Truth-Abgleich (geteilt)
│   ├── process_lock.py   # Schutz gegen doppelten Bot-Start (geteilt)
│   ├── heartbeat.py      # Tägliches Lebenszeichen aller vier Bots (geteilt)
│   ├── heartbeat_status.py # Heartbeat-Status als Datei für die Dashboard-App (geteilt)
│   ├── cycle_errors.py   # Mengenlimit für Zyklusfehler-Meldungen (Grid + Allocator)
│   ├── strategy.py       # DCA-Logik inkl. Tageslimit als Notbremse
│   ├── risk.py           # Notaus, Trade-Ledger, Portfolio-Stop-Loss (DCA)
│   ├── notifier.py       # Telegram-Benachrichtigungen (optional, geteilt)
│   ├── main.py           # Einstiegspunkt DCA-Bot
│   ├── grid_config.py    # Zentrale Konfiguration Grid-Bot (liest .env)
│   ├── grid_signals.py   # Crossing-/Sell-/Stop-Loss-Logik (Backtest UND Live)
│   ├── grid_risk.py      # Positions-Ledger, Trendbruch-Stop-Loss (Grid)
│   ├── grid_strategy.py  # Grid-Kauf-/Verkaufslogik
│   ├── grid_backtest.py  # Backtest über historische Marktphasen
│   ├── main_grid.py      # Einstiegspunkt Grid-Bot
│   ├── trend_config.py   # Zentrale Konfiguration Trend-Bot (liest .env)
│   ├── trend_signals.py  # EMA-Crossover + Trendstärke-Filter (Backtest UND Live)
│   ├── trend_risk.py     # Trade-Ledger, Stop-Loss-Latch (Trend)
│   ├── trend_strategy.py # Trend-Following-Ein-/Ausstiegslogik
│   ├── trend_backtest.py # Backtest über historische Marktphasen
│   ├── main_trend.py     # Einstiegspunkt Trend-Bot
│   ├── allocator_config.py  # Zentrale Konfiguration Allocator (liest .env)
│   ├── allocator_signals.py # Zuteilungs-/Glättungslogik + State-Reader (Backtest UND Live)
│   ├── allocator.py         # Allocator-Kernlogik (Berechnung + State-Datei)
│   ├── allocator_backtest.py # Backtest: kombiniert vs. isoliert DCA/Trend
│   ├── main_allocator.py    # Einstiegspunkt Allocator
│   ├── audit_positions.py         # CLI: Bestand aller drei Bots + Kontoabgleich (nur lesend)
│   ├── check_orders.py            # CLI: Orders nachschlagen, z.B. nach [ORDER-UNKLAR] (nur lesend)
│   ├── reset_stop_loss.py         # CLI: DCA-Stop-Loss-Pause zurücksetzen
│   ├── reset_grid_stop_loss.py    # CLI: Grid-Stop-Loss-Pause zurücksetzen
│   ├── reset_trend_stop_loss.py   # CLI: Trend-Stop-Loss-Pause zurücksetzen
│   └── fix_dry_run_quote_spent.py # CLI: einmalige Korrektur verfälschter Dry-Run-Beträge
├── requirements.txt
├── .env.example
└── README.md
```

## 6. Sicherheitsmechanismen auf einen Blick

Kurzfassung. Die vollständige Beschreibung jedes Mechanismus samt
Begründung steht in `trading-bot-projekt.md` Abschnitt 7 (7.1 für alle
Bots, 7.2 Grid, 7.3 Trend, 7.4 Allocator).

### Im Notfall

```bash
touch STOP_ALL     # stoppt DCA, Grid, Trend und Allocator
```

**Ein Notaus beendet die Prozesse.** Sie enden regulär (Exit-Code 0),
und `Restart=on-failure` startet nur nach einem Fehler neu. Die Datei
wieder zu entfernen, startet also **nichts**. Wiederanlaufen geht in zwei
Schritten, in dieser Reihenfolge:

```bash
rm STOP_ALL
sudo systemctl start dca-bot grid-bot trend-bot allocator
systemctl status dca-bot grid-bot trend-bot allocator   # Kontrolle
```

Wird ein Service gestartet, solange die Notaus-Quelle noch da ist,
beendet er sich nach den Startprüfungen sofort wieder. Bis zum Start
läuft kein Zyklus und kommt kein Heartbeat. Offene Grid-Positionen haben
in dieser Zeit keine Absicherung (der Grid-Bot hat keine Stop-Order an
der Börse), eine Trend-Position nur ihre Stop-Order an der Börse.

- Einzelnen Bot stoppen: Notaus-Datei anlegen (Defaults `STOP`,
  `STOP_GRID`, `STOP_TREND`, `STOP_ALLOCATOR`) oder `*_HALT=true` bzw.
  `STOP_ALL=true` setzen - auch nachträglich in der `.env`, ohne
  Neustart. Wiederanlaufen genauso: erst alle Quellen bereinigen (Datei
  entfernen, Variable auf `false` oder Zeile löschen), dann den Service
  starten, z.B. `rm STOP_GRID && sudo systemctl start grid-bot`.
- Stop-Loss-Sperren heben sich nie von selbst auf, Reset nur manuell:
  `python -m dca_bot.reset_stop_loss`, `python -m
  dca_bot.reset_grid_stop_loss`, `python -m dca_bot.reset_trend_stop_loss`.
- Bestand prüfen, bevor ein Bot wieder freigeschaltet oder
  `*_BOT_ENABLE_TRADING` umgestellt wird: `python -m
  dca_bot.audit_positions` (siehe Abschnitt 8.1).

### Alle Bots (Details: 7.1)

- **Dry-Run per Default:** keine echten Orders ohne explizites Opt-in
  (`*_BOT_ENABLE_TRADING=true`).
- **Live-Schalter `USE_TESTNET`:** nur `true`/`false` erlaubt, ein
  Tippfehler bricht ab. Im Live-Modus unübersehbare Warnung in Log und
  Telegram; Telegram-Zugangsdaten und alle Positionsgrößen werden
  Pflichtangaben, und die Testwerte aus `.env.example` werden abgelehnt,
  sofern sie nicht über `LIVE_CONFIRMED_VALUES` bestätigt sind.
- **Pflichtvariablen-Check beim Start:** leere, unsinnige oder aus
  `.env.example` kopierte Werte stoppen den Start mit klarer Meldung -
  ohne systemd-Neustartschleife.
- **Notaus:** botspezifisch oder global (`STOP_ALL`), wirkt sofort, auch
  mitten im Zyklus; beim Grid-Bot vor jedem einzelnen Kauf.
- **Stop-Loss mit manuellem Reset:** DCA pausiert Käufe ab
  `DCA_BOT_STOP_LOSS_PCT` Verlust (verkauft nicht), Grid pausiert Käufe
  beim Trendbruch unter die Grid-Untergrenze, Trend schließt die Position
  und pausiert neue Einstiege.
- **Tageslimit (DCA):** aus dem persistenten Ledger berechnet, gilt auch
  nach einem Neustart; Tagesfenster in UTC.
- **Keine Order ohne Ledger-Eintrag:** jede Order steht vor dem
  Netzwerk-Call in einer Pending-Datei. Nach einem Verbindungsfehler oder
  einer Antwort mit unbekanntem Ausgang (HTTP 5xx, −1006/−1007) fragt der
  Bot bei Binance nach, statt zu raten; der nächste Zyklus trägt Fehlendes
  als `[REKONZILIATION]` nach. Lässt sich der Ausgang nicht klären, meldet
  er `[ORDER-UNKLAR]` mit der clientOrderId. Nachschlagen, ob es die
  Order gibt und ob sie verbucht ist (Abschnitt 8.4):
  `python -m dca_bot.check_orders --client-order-id grid-7f3a9c2e14b84d6fa0e51c83`
- **Kein zweiter Verkauf bei unklarem Ausgang:** solange ein Verkauf oder
  eine Stop-Order ungeklärt ist, verkauft der Bot dieselbe Position nicht
  erneut - auf dem geteilten Konto ginge das aus fremdem Bestand durch.
- **Beschädigtes Ledger:** der Bot startet nicht, statt still mit leerer
  Historie weiterzulaufen. Alle Ledger werden atomar geschrieben.
- **Kein Sofortkauf bei jedem Neustart (DCA)** und **kein doppelter
  Bot-Start** (Prozess-Lock).
- **Konsistenz-Check gegen den Kontostand:** vor jedem echten Verkauf
  (ungedeckt → kein Verkauf) und bei jedem Start; eine Diskrepanz im
  Ledger wird laut gemeldet, blockiert aber nichts.
- **Echte Handelsregeln, Gebühren, Füllpreise:** Mengen und Preise auf
  `stepSize`/`tickSize` quantisiert, Gebühren abgezogen, im Ledger steht
  der tatsächliche Füllpreis.
- **Fehler pro Zyklus** beenden den Bot nicht. **Heartbeat** einmal pro
  Tag mit dem Zeitpunkt des letzten erfolgreichen Zyklus.

### Grid-Bot (Details: 7.2)

- Dry-Run-Positionen werden nie echt verkauft; echte Positionen werden
  bei deaktiviertem Trading nie simuliert geschlossen
  (`[GRID-VERKAUF-GESPERRT]`).
- Ein fehlgeschlagener echter Verkauf lässt die Position offen, der
  nächste Zyklus versucht es erneut - bei unklarem Ausgang erst, wenn er
  geklärt ist.
- Maximale Kapitalbindung = Anzahl Kaufstufen × `GRID_AMOUNT_PER_LEVEL`
  (kein Tageslimit).
- `[GRID-FEHLER]` pro Fehlertyp nur einmal per Telegram, bis ein Zyklus
  wieder erfolgreich war.

### Trend-Following-Bot (Details: 7.3)

- Echte `STOP_LOSS_LIMIT`-Order an der Börse, schützt die Position auch
  bei Bot-, Internet- oder Stromausfall; Schwelle aus dem Füllpreis des
  Einstiegs.
- Die Absicherung heilt sich selbst: fehlt die Stop-Order oder ist sie
  verschwunden, platziert der Bot Ersatz; unklare Zustände werden gezählt
  und ab 3 Zyklen gemeldet.
- Dry-Run-Positionen werden nie echt verkauft; bei deaktiviertem Trading
  wird eine echte Position nicht angefasst, ihre Stop-Order bleibt
  bestehen (`[TREND-AUSSTIEG-GESPERRT]`).
- Ein fehlgeschlagener echter Verkauf lässt die Position offen und
  platziert sofort eine neue Stop-Order; bei unklarem Ausgang fragt der
  Bot bis zu 60 s nach und platziert sie nur, wenn der Verkauf
  nachweislich nicht stattfand.
- Hat die Stop-Order teilweise verkauft, wird das verbucht und nur der
  Rest verkauft.

### Kapital-Allocator (Details: 7.4)

- Platziert selbst nie Orders (vom Code erzwungen).
- Ist die Zuteilung veraltet oder unbrauchbar, fallen DCA und Trend auf
  100 % DCA / 0 % Trend zurück.
- `[ALLOCATOR-FEHLER]` pro Fehlertyp nur einmal per Telegram, bis ein
  Zyklus wieder erfolgreich war.

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

### 7.3 Meldungen von Grid, Trend und Allocator

- **Grid-Bot:** `[GRID-KAUF]`/`[GRID-KAUF DRY-RUN]`, `[GRID-VERKAUF]` (mit
  realisiertem Gewinn/Verlust dieser Position),
  `[GRID-VERKAUF-FEHLGESCHLAGEN]`, `[GRID-VERKAUF-GESPERRT]`,
  `[GRID-STOP-LOSS]`, `[GRID-NOTAUS]`, `[GRID-FEHLER]`,
  `[GRID-DOPPELVERKAUF]`.
- **Trend-Following-Bot:** `[TREND-EINSTIEG]`/`[TREND-EINSTIEG DRY-RUN]`,
  `[TREND-AUSSTIEG]` (mit realisiertem Gewinn/Verlust und
  Ausstiegsgrund), `[TREND-VERKAUF-FEHLGESCHLAGEN]`,
  `[TREND-AUSSTIEG-GESPERRT]`, `[TREND-STOP-LOSS]`, `[TREND-WARNUNG]`,
  `[TREND-ABSICHERUNG-WIEDERHERGESTELLT]`, `[TREND-NOTAUS]`,
  `[TREND-FEHLER]`, `[TREND-TEILFUELLUNG]`, `[TREND-DOPPELVERKAUF]`.
- **Kapital-Allocator:** `[ALLOCATION-UPDATE]` (bei signifikanter
  Verschiebung), `[ALLOCATOR-NOTAUS]`, `[ALLOCATOR-FEHLER]`.
- **Alle vier:** `[HEARTBEAT]` (Lebenszeichen, siehe Abschnitt 6).
  Botübergreifend außerdem `[ORDER-UNKLAR]` (nachschlagen: Abschnitt
  8.4), `[REKONZILIATION]` und die `[…BESTAND-DISKREPANZ]`-Meldungen.

`[GRID-FEHLER]` und `[ALLOCATOR-FEHLER]` kommen pro Fehlertyp nur einmal,
bis ein Zyklus wieder erfolgreich war - weitere gleichartige Fehlschläge
stehen nur im Log.

## 8. Werkzeuge

### 8.1 Positions-Audit (offene Positionen prüfen)

```bash
python -m dca_bot.audit_positions
```

Listet den Bestand von **DCA-, Grid- und Trend-Bot** auf, jeweils mit
seinem **Dry-Run-Status**. Rein informativ: das Skript liest nur, ändert
nichts an den Ledger-Dateien und platziert keine Orders.

Sind Binance-Zugangsdaten vorhanden, hängt das Skript einen
bot-übergreifenden Abgleich gegen den tatsächlichen Kontostand an
(`--offline` schaltet ihn ab). Details und Einordnung:
`trading-bot-projekt.md` Abschnitt 7.5.

### 8.2 Backtests

```bash
python -m dca_bot.backtest             # DCA
python -m dca_bot.grid_backtest        # Grid
python -m dca_bot.trend_backtest       # Trend-Following
python -m dca_bot.allocator_backtest   # Allocator: kombiniert vs. isoliert
```

Ergebnisse und ihre Einordnung stehen in `trading-bot-projekt-archiv.md`
(Abschnitte 5a, 6, 6f und 6i), der Caveat zur Grid-Preisspanne in
`trading-bot-projekt.md` 7.2.

### 8.3 Einmalige Datenkorrektur (Dry-Run-Beträge)

```bash
python -m dca_bot.fix_dry_run_quote_spent            # nur Bericht
python -m dca_bot.fix_dry_run_quote_spent --apply    # schreibt
```

Einmaliges Korrektur-Werkzeug zum Fund vom 22.09.2026: rechnet
`quote_spent` und `realized_pnl` betroffener Dry-Run-Einträge neu.
**Ohne `--apply` wird nichts geschrieben**, nur berichtet. Hintergrund
und Eigenschaften: `trading-bot-projekt-archiv.md` Abschnitt 6g
(„Folgefund aus K3“).

### 8.4 Orders nachschlagen (z.B. nach `[ORDER-UNKLAR]`)

```bash
python -m dca_bot.check_orders --client-order-id grid-7f3a9c2e14b84d6fa0e51c83
python -m dca_bot.check_orders             # Übersicht aller drei Bots
```

Mit `--client-order-id` beantwortet das Skript die Frage hinter einer
`[ORDER-UNKLAR]`-Meldung (die Meldung nennt den fertigen Aufruf): Gibt
es diese Order bei Binance, und was ist aus ihr geworden? Das Symbol
folgt aus dem Präfix (`dca-`, `grid-`, `trend-`), `--symbol` überschreibt
es. Dazu prüft es die eigene Buchhaltung des Bots: Steht die ID noch in
seiner Pending-Datei, steht sie im Ledger? Die letzte Zeile ordnet das
ein, z.B. „Ausgeführt, noch NICHT im Ledger – der Bot trägt die Order im
nächsten Zyklus nach“. Eine gescheiterte Abfrage ist keine Aussage über
die Order (Exit-Code 2).

Ohne Argumente zeigt es je Symbol der drei Bots Kurs, Guthaben und die
letzten Orders (`--limit`, Default 10) mit clientOrderId und Bot. Das ist
zugleich der **Verbindungstest**: Kommen Kurs und Guthaben an,
funktionieren Verbindung und API-Keys. (Das frühere
`python -m dca_bot.test_connection` ist entfernt, es löste bei aktivem
Trading einen echten DCA-Kauf aus.) Das Skript liest nur: Es nutzt denselben Client wie das Positions-Audit
(8.1), der strukturell keine Orders platzieren kann.

## 9. Tests

```bash
python -m unittest discover -s tests -t .
```

Alle Tests laufen ohne Netzwerkzugriff und ohne Binance-Zugangsdaten
(Fake-Clients mit derselben Schnittstelle wie `binance_client.py`,
temporäre Ledger-Dateien). Abgedeckt sind die sicherheitskritischen
Pfade: Token-Hygiene der Telegram-Benachrichtigungen, der echte
exchange-seitige Stop-Loss inkl. Race Conditions, sowie die
Verkaufs-Sicherheit von Grid und Trend (Dry-Run-Positionen, fehl-
geschlagene echte Verkäufe), sowie die Anbindung an die echten
Handelsregeln inklusive Gebührenkorrektur.

| Testdatei | Thema |
|---|---|
| `test_notifier` | Token-Hygiene der Telegram-Meldungen (K5) |
| `test_order_utils`, `test_dca_fee_adjustment` | Handelsregeln, Quantisierung, Gebühren (K3) |
| `test_grid_sell_safety` | Verkaufssicherheit, Handelsregeln und Füllpreise des Grid-Bots |
| `test_trend_stop_loss` | Stop-Loss an der Börse, Verkaufssicherheit und Füllpreise des Trend-Bots |
| `test_pending_orders`, `test_order_reconciliation` | Keine Order ohne Ledger-Eintrag, Nachtragen beim Start (K2) |
| `test_process_lock`, `test_kill_switch` | Doppelter Bot-Start, Notaus-Wege |
| `test_stage_b_safety`, `test_stage_c_safety` | Review-Punkte Stufe B und C (u.a. UTC-Fenster, Ledger-Integrität, Live-Schalter, Kontostand-Check) |
| `test_trend_decide_action`, `test_grid_signals`, `test_allocator_signals` | Entscheidungslogik von Trend, Grid und Allocator |
| `test_improvements_stage_1` | Allocator-State-Datei, globaler Notaus `STOP_ALL` |
| `test_startup_balance_check`, `test_audit_positions` | Konsistenz-Check beim Start, Positions-Audit |
| `test_trend_auto_reset` | Analyse-Modus `--analyze-auto-reset` des Trend-Backtests |
| `test_fix_dry_run_quote_spent` | Einmalige Datenkorrektur der Dry-Run-Beträge |
| `test_request_timeout` | Request-Timeout des Grid-Bots |
| `test_heartbeat_last_cycle`, `test_cycle_error_notification` | Heartbeat-Zeitstempel, Mengenlimit für Zyklusfehler |
| `test_shared_account` | Alle Bots auf einem geteilten Konto: Teilfüllung, unklare Verkäufe, Dauerlauf mit Eigentums-Invariante |
| `test_check_orders` | Orders nachschlagen (nur lesend), Abgleich mit Pending-Datei und Ledger |
| `test_strategy_entry_points` | Nur die Einstiegspunkte benutzen die handelnden Strategien |
| `test_allocator_backtest` | Allocator-Backtest: Stop-Loss-Sperre und Konsistenz mit dem Trend-Backtest |

Was die einzelnen Tests prüfen und wie ihre Wirksamkeit gemessen wurde,
steht bei den jeweiligen Fixes in `trading-bot-projekt-archiv.md` (6f, 6g,
6i), für neuere im „Log ab 29.09.2026“ in `trading-bot-projekt.md`,
ergänzend dort 7.6.

## 10. Weiterführende Doku

Das Projektdokument besteht seit dem 29.09.2026 aus zwei Dateien.

`trading-bot-projekt.md`, der aktuelle Stand:

- **Aktueller Stand und offene Punkte:** Betrieb, Deploy-Stand, Termine,
  Vorbedingungen für echtes Kapital, zurückgestellte Punkte
- **Log ab 29.09.2026:** das laufende Fortschritts-Log
- **Abschnitt 7:** Technische Referenz - alle Sicherheitsmechanismen und
  die Kernlogik der vier Bausteine im Detail

`trading-bot-projekt-archiv.md`, Planung, Recherche und das Log bis
28.09.2026, unverändert verschoben:

- **Abschnitt 5 / 5a:** Recherche zu den Strategien, Backtest des Allocators
- **Abschnitt 6:** Fortschritts-Log inkl. Backtest-Ergebnisse von DCA, Grid und Trend
- **Abschnitte 6f-6i:** Stop-Loss an der Börse, Sicherheitsreview mit allen
  Fixes (K1-K5, W1-W18), Verbesserungsvorschläge, Systemcheck vom
  27.09.2026 und Symbolbindung

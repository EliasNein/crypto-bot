# Trading-Bots (Binance Testnet)

Drei komplett eigenständige Trading-Bots plus ein steuernder Zusatzprozess
im selben Projekt, alle gegen die **Binance Testnet API** – es wird zu
keinem Zeitpunkt echtes Geld bewegt, solange du keine echten API-Keys
einträgst:

- **DCA-Bot** (`dca_bot/main.py`): kauft in festen Intervallen einen festen
  Betrag eines Assets (Dollar-Cost-Averaging).
- **Grid-Trading-Bot** (`dca_bot/main_grid.py`, siehe Abschnitt 8): kauft an
  festen Preisstufen innerhalb einer Preisspanne und verkauft jede Position
  einzeln wieder, wenn der Preis eine Stufe höher steigt.
- **Trend-Following-Bot** (`dca_bot/main_trend.py`, siehe Abschnitt 9):
  EMA-Crossover mit Trendstärke-Filter auf Tageskerzen, long-only, mit
  festem Stop-Loss pro Trade. Vor dem ersten Dry-Run per Backtest über
  mehrere historische Marktphasen validiert (siehe `trend_backtest.py`).
- **Kapital-Allocator** (`dca_bot/main_allocator.py`, siehe Abschnitt 10):
  kein eigener Trading-Bot, sondern ein steuernder Zusatzprozess, der
  Kapital stufenlos zwischen DCA- und Trend-Following-Bot umschichtet, je
  nach aktueller Trendstärke. Platziert selbst nie Orders, wirkt sich auf
  DCA/Trend nur nach explizitem Opt-in aus.

Alle vier teilen sich nur die Binance-/Telegram-Zugangsdaten in der `.env` -
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
│   ├── reset_stop_loss.py         # CLI: DCA-Stop-Loss-Pause zurücksetzen
│   ├── reset_grid_stop_loss.py    # CLI: Grid-Stop-Loss-Pause zurücksetzen
│   └── reset_trend_stop_loss.py   # CLI: Trend-Stop-Loss-Pause zurücksetzen
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

## 8. Spot-Grid-Trading-Bot (zweiter, eigenständiger Bot)

Kauft an festen Preisstufen ("Grid-Stufen") innerhalb einer konfigurierten
Preisspanne und verkauft jede einzelne Position wieder, sobald der Preis auf
die nächsthöhere Stufe steigt - Spot only, kein Hebel, kein
Liquidationsrisiko. Siehe `trading-bot-projekt.md` Abschnitt 5 für die
Recherche dazu: der Erwartungswert ist vor Gebühren akademisch mathematisch
null, der Sinn dieser Strategie liegt in der einfachen, latenzunkritischen
Umsetzung, nicht in überlegener Rendite. Haupt-Risiko ist ein Trendbruch.

**Backtest verfügbar** (`python -m dca_bot.grid_backtest`, Code in
`grid_backtest.py`) - siehe Abschnitt 8.5 und `trading-bot-projekt.md` für
die Ergebnisse und einen wichtigen Caveat zur Preisspanne.

### 8.1 Konfiguration

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

### 8.2 Starten

```bash
python -m dca_bot.main_grid
```

Läuft komplett unabhängig vom DCA-Bot (auch parallel), eigenes Log unter
`logs/grid_bot.log`.

### 8.3 Kernlogik

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
- **Dieselbe Entscheidungslogik** (`compute_grid_levels`,
  `find_triggered_buy_levels`, `is_sell_target_hit`,
  `is_trend_break_stop_loss_hit` aus `grid_signals.py`) wird von Backtest
  UND Live-Strategie importiert - keine doppelte Implementierung, die
  unbemerkt auseinanderlaufen könnte (gleiches Prinzip wie beim
  Trend-Bot, siehe Abschnitt 9.3).

### 8.4 Sicherheitsmechanismen (eigenständig vom DCA-Bot)

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

### 8.5 Backtest

```bash
python -m dca_bot.grid_backtest
```

Läuft über dieselben drei Referenz-Zeiträume wie der Trend-Backtest (2022
Bärenmarkt, 2023 Erholung, 2021 Seitwärts/Konsolidierung), auf
Stundenkerzen (Kompromiss - der Live-Bot prüft alle paar Minuten, aber
Tageskerzen würden die meisten Grid-Durchquerungen unsichtbar machen).

**Wichtiger Unterschied zu DCA/Trend:** `GRID_LOWER_LIMIT`/`GRID_UPPER_LIMIT`
sind kein skaleninvarianter Wert, sondern ein absoluter Preisbereich,
gekoppelt an das heutige Kursniveau. Gegen die historischen Testzeiträume
(BTC damals deutlich niedriger) getestet, läge die unveränderte Live-Spanne
sofort außerhalb des Kurses -> 0 Trades, sofortiger Trendbruch-Stop-Loss.
Der Backtest zeigt deshalb standardmäßig zwei Ergebnisse pro Zeitraum: das
literale (mit den unveränderten Live-Werten) und einen klar als "ANALYSE,
NICHT Live-Verhalten" gekennzeichneten zweiten Lauf, bei dem die Spanne
symmetrisch um den tatsächlichen Startpreis der jeweiligen Periode skaliert
wird (gleiches Breiten-Verhältnis/Abstand wie live). Siehe
`trading-bot-projekt.md` für die vollständigen Ergebnisse.

## 9. Trend-Following-Bot (dritter, eigenständiger Bot)

EMA-Crossover-Strategie auf Tageskerzen mit Trendstärke-Filter, long-only
(Spot, kein Shorting). Siehe `trading-bot-projekt.md` Abschnitt 5 für die
Recherche: Trend-Following ist die akademisch am besten belegte
Alpha-Strategie (Liu & Tsyvinski, Gbadebo), Hauptrisiken sind Overfitting
und Momentum-Crashes.

**Vor dem ersten Dry-Run wurde die Strategie per Backtest über drei
historische Marktphasen validiert** (`python -m dca_bot.trend_backtest`,
Code in `trend_backtest.py`) - siehe trading-bot-projekt.md für die
Ergebnisse und deren ehrliche Einordnung (schützt im Bärenmarkt, verpasst
ohne periodischen manuellen Stop-Loss-Reset einen Teil der Rendite im
Bullenmarkt).

### 9.1 Konfiguration

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
TREND_STOP_LIMIT_OFFSET_PCT=0.5  # Abstand Stop-/Limit-Preis der echten Exchange-Stop-Order (siehe 9.5)
```

### 9.2 Starten

```bash
python -m dca_bot.main_trend
```

Läuft komplett unabhängig von DCA- und Grid-Bot (auch parallel), eigenes
Log unter `logs/trend_bot.log`. Lädt beim Start automatisch echte
historische Tageskerzen (öffentliche Binance-API), damit die EMAs nicht
bei Null anfangen müssen.

### 9.3 Kernlogik

- **Signal**: Ein EMA-Crossover allein reicht nicht - der Abstand zwischen
  schnellem und langsamem EMA muss auf mindestens `TREND_MIN_GAP_PCT`
  anwachsen, bevor das Signal als bestätigt gilt (Bestätigungslogik statt
  ADX - einfacher und robuster zu verifizieren, siehe `trend_signals.py`).
  Das filtert Whipsaws heraus, bei denen der Preis kurz nach dem Crossover
  wieder zurückkreuzt.
- **Ein-/Ausstieg**: Long bei bestätigtem Aufwärtssignal; Ausstieg bei
  bestätigter Signal-Umkehr ODER Erreichen des Stop-Loss, je nachdem was
  zuerst eintritt (Stop-Loss hat Priorität bei Gleichzeitigkeit). Kein
  Shorting - bei bestätigtem Abwärtssignal ohne offene Position passiert
  nichts.
- **Dieselbe Entscheidungslogik** (`TrendSignalGenerator`, `decide_action`,
  `is_stop_loss_hit` aus `trend_signals.py`) wird von Backtest UND
  Live-Strategie importiert - keine doppelte Implementierung, die
  unbemerkt auseinanderlaufen könnte.

### 9.4 Sicherheitsmechanismen (eigenständig von DCA/Grid)

- **Dry-Run per Default**, analog zu DCA/Grid.
- **Notaus**: eigene Datei (`TREND_KILL_SWITCH_FILE`, Default `STOP_TREND`)
  und eigene Env-Variable (`TREND_BOT_HALT`) - unabhängig von DCA/Grid.
- **Fixer Stop-Loss pro Trade** (`TREND_STOP_LOSS_PCT`, Default 10%
  unterhalb des Einstiegspreises): schließt die Position und pausiert
  danach neue Einstiege. Latched wie bei DCA/Grid: kein automatischer
  Reset, manuell mit `python -m dca_bot.reset_trend_stop_loss` oder durch
  Löschen der Datei unter `TREND_STOP_LOSS_STATE_FILE`. Der Backtest zeigt
  deutlich den Preis dafür - ohne periodischen manuellen Reset verpasst
  die Strategie ggf. einen Großteil einer nachfolgenden Erholung.
- **Telegram-Benachrichtigungen** (falls konfiguriert, siehe Abschnitt 7):
  `[TREND-EINSTIEG]`/`[TREND-EINSTIEG DRY-RUN]`, `[TREND-AUSSTIEG]` (mit
  realisiertem Gewinn/Verlust und Ausstiegsgrund), `[TREND-STOP-LOSS]`,
  `[TREND-NOTAUS]`, `[TREND-FEHLER]`.

### 9.5 Echter, exchange-seitiger Stop-Loss

Zusätzlich zum software-internen Stop-Loss (siehe 9.4) platziert der Bot
bei jedem Entry eine echte `STOP_LOSS_LIMIT`-Sell-Order direkt an der
Börse (`place_stop_loss_limit_sell` in `binance_client.py`). Der Grund:
der software-interne Stop-Loss wirkt nur, solange der Bot-Prozess läuft
- fällt der Bot aus (Absturz, Internet-/Stromausfall), bleibt eine offene
Position ohne diesen Mechanismus komplett ungeschützt, egal wie weit der
Kurs fällt. Die exchange-seitige Order übernimmt die Überwachung an der
Börse selbst und wirkt unabhängig vom Bot-Prozess.

- **Stop-/Limit-Preis:** `stop_price = entry_price * (1 -
  TREND_STOP_LOSS_PCT/100)` (identisch zur Schwelle des internen
  Stop-Loss), `limit_price = stop_price * (1 -
  TREND_STOP_LIMIT_OFFSET_PCT/100)` (Default 0,5%) - der Abstand
  verhindert, dass die Order bei einem schnellen Kurssturz ungefüllt im
  Orderbuch hängen bleibt.
- **Exit-Reihenfolge bei Signal-Umkehr oder internem Stop-Loss-Trigger:**
  der Bot storniert IMMER zuerst die noch offene Stop-Loss-Order, bevor
  er selbst per Market-Order verkauft - sonst bliebe eine verwaiste
  Sell-Order an der Börse zurück. Ein Stornierungsfehler (z.B. Order war
  zwischenzeitlich bereits gefüllt) wird nur geloggt, nicht als Fehler
  behandelt.
- **Erkennung einer bereits gefüllten Stop-Order:** vor jeder normalen
  Zyklus-Entscheidung fragt der Bot den Order-Status der hinterlegten
  Stop-Loss-Order ab. Ist sie bereits `FILLED` (die Börse hat also schon
  verkauft, z.B. während einer Downtime), markiert der Bot die Position
  im Ledger anhand der tatsächlichen Order-Fülldaten als geschlossen,
  OHNE selbst nochmal zu verkaufen.
- **Reconciliation beim Bot-Start:** bevor der erste reguläre Zyklus
  läuft, gleicht der Bot eine im Ledger offene Position gegen den
  tatsächlichen Order-Status bei Binance ab und korrigiert den Ledger
  sofort, falls die Stop-Order während der Downtime gefüllt wurde -
  klar geloggt als `[REKONZILIATION]`.
- **Race Condition zwischen Status-Check und Stornierung:** füllt sich
  die Stop-Order genau zwischen der letzten Status-Abfrage und dem
  Cancel-Aufruf, schlägt das Stornieren fehl. Der Bot verlässt sich dann
  NICHT auf den Cancel-Fehlercode, sondern fragt den Order-Status erneut
  ab: ist sie tatsächlich `FILLED`, wird die Position anhand der echten
  Fülldaten geschlossen (kein zweiter Verkaufsversuch); bleibt der
  Status trotz Cancel-Fehlschlag unklar (z.B. echter Netzwerkfehler),
  verkauft der Bot in diesem Zyklus bewusst NICHT (Risiko einer
  Doppel-Order) und markiert die Position auch nicht als geschlossen -
  ein Zähler (`uncertain_cycles`) löst ab 3 aufeinanderfolgenden unklaren
  Zyklen eine `[TREND-WARNUNG]`-Telegram-Meldung aus (manuelle Prüfung
  empfohlen).
- **Fill-Analyse-Logging:** bei jedem Exit über eine gefüllte
  Exchange-Stop-Order loggt der Bot eine eigene, leicht auffindbare
  Zeile `[STOP-FILL-ANALYSE] Limit: X, gefüllt bei: Y, Differenz: Z%` -
  sammelt über die Paper-Trade-Phase automatisch reale Daten zur
  Zuverlässigkeit von `TREND_STOP_LIMIT_OFFSET_PCT`, ohne dass das
  manuell nachgehalten werden muss (siehe Einschränkung unten).
- **Dry-Run** (`TREND_BOT_ENABLE_TRADING=false`): es wird KEINE echte
  Stop-Order platziert, nur geloggt ("[DRY-RUN] Würde
  Stop-Loss-Order platzieren..."). Die Position bleibt dann wie bisher
  ausschließlich software-intern überwacht - gleiches Sicherheitsprinzip
  wie bei der Entry-Order (kein Trading ohne Opt-in).
- **Bekannte Einschränkung (TODO vor Echtgeld):** Stop-/Limit-Preis
  werden aktuell nur auf 2 Nachkommastellen gerundet, nicht gegen die
  echte `PRICE_FILTER`-Tick-Size des Symbols validiert (siehe TODO-
  Kommentar in `binance_client.py`) - vor dem Live-Start durch eine
  echte `exchangeInfo`-Abfrage ersetzen.
- **Bekannte Einschränkung: `TREND_STOP_LIMIT_OFFSET_PCT`-Default (0,5%)
  basiert auf einer zu kleinen historischen Stichprobe** (Backtest-
  Analyse über die drei Referenz-Zeiträume ergab nur 2 simulierte
  Stop-Loss-Exits insgesamt, siehe trading-bot-projekt.md) - wird
  während der monatelangen Paper-Trade-Phase anhand echter Fill-Daten
  (siehe Fill-Analyse-Logging oben) überprüft, bevor der Wert für den
  Live-Gang final bestätigt wird.

## 10. Kapital-Allocator (vierter, übergeordneter Baustein)

Stufenlose Umschichtung von Kapital zwischen DCA-Bot und Trend-Following-Bot
je nach aktueller Trendstärke (EMA-Abstand) - **kein** eigenständiger
Trading-Bot, sondern ein steuernder Zusatzprozess. Grid-Bot bleibt davon
unberührt (hat bereits einen eigenen Trendbruch-Stop-Loss, siehe Abschnitt
8.4). Der Allocator platziert selbst **nie** Orders - er berechnet nur eine
Zahl (den Trend-Following-Anteil zwischen 0% und 100%) und schreibt sie in
seine State-Datei.

**Backtest verfügbar** (`python -m dca_bot.allocator_backtest`, Code in
`allocator_backtest.py`) - vergleicht die kombinierte Performance mit
isoliertem DCA und isoliertem Trend über dieselben drei Marktphasen wie
die anderen Backtests, inklusive investiertem Betrag und absolutem PnL
(nicht nur Prozent) - die Kapitalbasis ist zwischen den drei Varianten
NICHT gleich groß (siehe Modul-Docstring/Report-Hinweis in
`allocator_backtest.py`), ein reiner Prozentvergleich wäre irreführend.
Siehe `trading-bot-projekt.md` für die vollständigen Ergebnisse.

### 10.1 Konfiguration

Zusätzlich zu den Binance-/Telegram-Zugangsdaten oben (werden mitgenutzt):

```
ALLOCATOR_SYMBOL=BTCUSDT
ALLOCATOR_EMA_FAST_PERIOD=20
ALLOCATOR_EMA_SLOW_PERIOD=50
ALLOCATOR_ZERO_ANCHOR_PCT=0.0     # EMA-Abstand, ab dem 0% Trend-Anteil gilt
ALLOCATOR_FULL_ANCHOR_PCT=3.0     # EMA-Abstand, ab dem 100% Trend-Anteil gilt
ALLOCATOR_SMOOTHING_PERIOD=24     # EMA-Glättung der Zuteilung, in Allocator-Zyklen
ALLOCATOR_INTERVAL_MINUTES=60     # Wie oft neu berechnet wird
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

### 10.2 Starten

```bash
python -m dca_bot.main_allocator
```

Läuft komplett unabhängig von DCA/Grid/Trend (auch parallel), eigenes Log
unter `logs/allocator.log`. Lädt beim Start automatisch echte historische
Tageskerzen, damit die EMAs nicht bei Null anfangen müssen (wie der
Trend-Bot).

### 10.3 Kernlogik

- **Trendstärke**: wiederverwendet `TrendSignalGenerator` aus
  `trend_signals.py` (mit `min_gap_pct=0`, da die dortige
  Bestätigungslogik für binäre Ein-/Ausstiegsentscheidungen gedacht ist -
  der Allocator braucht den rohen, kontinuierlichen EMA-Abstand). Nur eine
  bestätigte AUFWÄRTS-Richtung zählt als Stärke - der Trend-Bot ist
  long-only, bei Abwärtstrend bekäme er ohnehin kein Kapital zugeteilt.
- **Lineare Interpolation** zwischen `ALLOCATOR_ZERO_ANCHOR_PCT` und
  `ALLOCATOR_FULL_ANCHOR_PCT`, außerhalb der Anker geklemmt (kein
  Extrapolieren).
- **Whipsaw-Schutz durch EMA-Glättung der Zuteilung selbst** (gleiche
  Formel wie die Preis-EMAs in `trend_signals.py`, hier auf die
  Zuteilungs-Prozentzahl angewandt) - da es bei einer stufenlosen Kurve
  keine feste Stufe zum "Bestätigen" gibt wie bei diskreten Signalen.
- **Additive, standardmäßig deaktivierte Integration**: DCA/Trend lesen
  die Zuteilung nur bei explizitem Opt-in (siehe 10.1) unmittelbar vor
  einer NEUEN Order; unterhalb von 5 USDT wird die Order übersprungen
  statt einer wirtschaftlich bedeutungslosen Mini-Order.
- **Telegram-Benachrichtigung** (falls konfiguriert) nur bei einer
  Verschiebung um mindestens `ALLOCATOR_NOTIFY_THRESHOLD_PP`
  Prozentpunkte seit der letzten Meldung - verhindert Spam bei kleinen,
  stufenlosen Schwankungen.

### 10.4 Sicherheitsmechanismen (eigenständig von DCA/Grid/Trend)

- **Notaus**: eigene Datei (`ALLOCATOR_KILL_SWITCH_FILE`, Default
  `STOP_ALLOCATOR`) und eigene Env-Variable (`ALLOCATOR_HALT`) -
  unabhängig von DCA/Grid/Trend. Der Allocator platziert ohnehin nie
  Orders, der Notaus stoppt hier nur die Berechnung/State-Aktualisierung.
- **Telegram-Benachrichtigungen**: `[ALLOCATION-UPDATE]` (bei
  signifikanter Verschiebung), `[ALLOCATOR-NOTAUS]`, `[ALLOCATOR-FEHLER]`.

## 11. Nächste Ausbaustufen (siehe trading-bot-projekt.md)

- [ ] Konfiguration vollständig über `.env` statt Code-Defaults
- [x] Persistente Speicherung der Trade-Historie (`data/trade_ledger.json`)
- [ ] Backtesting-Skript für die DCA-Logik auf historischen Daten
- [x] Grid-Trading-Strategie als zweiter, eigenständiger Bot (siehe Abschnitt 8), inkl. Backtesting-Skript (siehe Abschnitt 8.5)
- [x] Trend-Following-Strategie (EMA-Crossover) als dritter, eigenständiger Bot, inkl. Backtest vor dem ersten Dry-Run (siehe Abschnitt 9)
- [x] Kapital-Allocator als vierter, übergeordneter Baustein (siehe Abschnitt 10), inkl. Backtest vor dem ersten Dry-Run - Live-Dry-Run noch offen

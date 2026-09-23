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
Pflichtangabe (siehe Abschnitt 6). Nicht vergessen: Testnet-Keys
funktionieren an der echten Börse nicht, `BINANCE_API_KEY`/`SECRET`
müssen mitgewechselt werden.

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
│   ├── config_guard.py   # Live-Schalter + Pflichtvariablen-Check (geteilt)
│   ├── balance_guard.py  # Konsistenz-Check vor jedem Verkauf (geteilt)
│   ├── startup_checks.py # Konsistenz-Check beim Bot-Start (geteilt)
│   ├── binance_client.py # Wrapper um die Binance-API (Testnet, Buy+Sell, Handelsregeln)
│   ├── order_utils.py    # Quantisierung auf tickSize/stepSize + Gebührenkorrektur (geteilt)
│   ├── pending_orders.py # Idempotente Order-Platzierung + Ground-Truth-Abgleich (geteilt)
│   ├── process_lock.py   # Schutz gegen doppelten Bot-Start (geteilt)
│   ├── heartbeat.py      # Tägliches Lebenszeichen aller vier Bots (geteilt)
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
│   ├── reset_stop_loss.py         # CLI: DCA-Stop-Loss-Pause zurücksetzen
│   ├── reset_grid_stop_loss.py    # CLI: Grid-Stop-Loss-Pause zurücksetzen
│   ├── reset_trend_stop_loss.py   # CLI: Trend-Stop-Loss-Pause zurücksetzen
│   └── fix_dry_run_quote_spent.py # CLI: einmalige Korrektur verfälschter Dry-Run-Beträge
├── requirements.txt
├── .env.example
└── README.md
```

## 6. Eingebaute Sicherheitsmechanismen (schon jetzt)

- **Dry-Run per Default**: keine echten Orders ohne explizites Opt-in.
- **Tageslimit** (`max_daily_spend` in `config.py`): verhindert, dass bei einem
  Bug (z.B. Endlosschleife) unbegrenzt viele Käufe ausgelöst werden. Wird aus
  der persistenten Trade-Historie (`data/trade_ledger.json`) berechnet, gilt
  also auch nach einem Neustart des Bots weiter. Das Tagesfenster läuft
  durchgängig in **UTC**, passend zu den Zeitstempeln im Ledger – mit
  lokaler Serverzeit verschob sich die Grenze je nach Zeitzone um
  Stunden gegenüber den Daten. Die Tageszusammenfassung folgt derselben
  Grenze (UTC-Mitternacht).
- **Notaus**: Läuft die Datei `STOP` (Pfad über `DCA_BOT_KILL_SWITCH_FILE`
  konfigurierbar) im Projektverzeichnis, oder ist `DCA_BOT_HALT=true`
  gesetzt, stoppt der Bot sofort und sauber – auch mitten in einem laufenden
  Kaufzyklus, nicht erst beim nächsten Intervall. Geprüft werden drei
  Quellen: die Notaus-Datei, die Prozess-Umgebung (z.B. aus der
  systemd-Unit) und die **aktuelle** `.env`. Letzteres wird bei jeder
  Prüfung neu gelesen – `DCA_BOT_HALT=true` nachträglich in die `.env`
  zu schreiben wirkt deshalb sofort, ohne Neustart, genau wie das
  Anlegen der STOP-Datei. Die drei Wege sind mit ODER verknüpft, bewusst
  asymmetrisch: auslösen soll leicht sein, versehentliches Aufheben
  schwer – zum Wiederanlaufen müssen alle drei Quellen sauber sein.
  Beim Grid-Bot wird der Notaus zusätzlich **zwischen jedem einzelnen
  Kauf** eines Zyklus geprüft, nicht nur einmal davor: durchquert der
  Preis in einem Intervall mehrere Stufen, kauft die Schleife mehrere
  Positionen hintereinander – und genau dann zieht jemand den Notaus.
- **Globaler Notaus `STOP_ALL`**: Eine Datei `STOP_ALL` im
  Projektverzeichnis **oder** `STOP_ALL=true` (Prozessumgebung oder
  `.env`) stoppt **alle vier Bots gleichzeitig** – zusätzlich zu deren
  eigenen Schaltern, nicht an deren Stelle. Einen einzelnen Bot
  anzuhalten bleibt also weiterhin möglich.

  ```bash
  touch STOP_ALL     # stoppt DCA, Grid, Trend und Allocator
  rm STOP_ALL        # gibt alle wieder frei
  ```

  Vorher brauchte es vier Dateien oder vier Variablen – und im Ernstfall
  ist „habe ich wirklich alle vier erwischt?" genau die Frage, die man
  sich nicht stellen will. Der Dateiname ist deshalb bewusst **nicht**
  konfigurierbar (anders als die botspezifischen
  `*_KILL_SWITCH_FILE`): Ein globaler Notausschalter, dessen Pfad man
  erst nachschlagen muss, verfehlt seinen Zweck. Die ausgelöste Meldung
  benennt außerdem, **welche** Quelle gegriffen hat – bei vier
  gleichzeitig stoppenden Bots ist das die erste Frage.
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
- **Keine Order ohne Ledger-Eintrag** (`dca_bot/pending_orders.py`): Jede
  echte Order bekommt vorab eine selbstvergebene `newClientOrderId`, die
  **vor** dem Netzwerk-Call in eine kleine, separate Datei
  (`data/pending_orders_<bot>.json`) geschrieben wird. Bricht die
  Verbindung danach ab (`requests`-Timeout, `BinanceRequestException`),
  gibt der Bot **nicht** einfach "kein Trade" zurück, sondern fragt die
  Börse per `get_order()` nach dieser ID, was tatsächlich passiert ist:
  ausgeführt → die echten Order-Daten werden zurückgegeben und regulär
  verbucht; nie angenommen (Fehlercode −2013) → sauber als "kein Trade"
  gewertet; unklar → **nicht geraten**, sondern `ERROR` + Telegram, und
  der Eintrag bleibt für den nächsten Start stehen. Beim Bot-Start
  arbeitet jeder Bot verbliebene Einträge ab und trägt fehlende
  Ledger-Einträge als `[REKONZILIATION]` nach. Das schließt auch das
  Fenster, das ohne jeden Netzwerkfehler durch einen Prozess-Kill
  zwischen Order und Ledger-Eintrag entstand.
- **Beschädigtes Ledger stoppt den Bot, statt still zurückzusetzen**:
  Tageslimit und Stop-Loss-Kostenbasis werden bei jedem Zyklus aus der
  Ledger-Datei berechnet. Eine vorhandene, aber unparsbare Datei als
  "leere Historie" zu lesen würde beide auf Null setzen - der Bot
  kaufte weiter, obwohl faktisch Kapital gebunden ist. Deshalb: klarer
  `ERROR` + Telegram, und der Bot **startet nicht** (bzw. der laufende
  Zyklus bricht ab). Eine **fehlende** Datei bleibt ausdrücklich der
  normale Fall "frisches Deployment, allererster Start". Damit das
  keinen Verfügbarkeitsverlust bedeutet, werden alle drei Ledger jetzt
  **atomar** geschrieben (temporäre Datei + `os.replace`) - ein Absturz
  mitten im Schreiben kann keine halbe Datei mehr hinterlassen.
- **Kein Sofortkauf bei jedem Neustart** (DCA): Beim Start prüft der Bot
  aus dem Ledger, wie lange der letzte Zyklus her ist, und wartet bis
  zum nächsten fälligen Zeitpunkt. Vorher löste **jeder** Prozessstart
  sofort einen echten Kauf aus - in einer Neustartschleife so viele, wie
  das Tageslimit gerade noch durchließ. Bei leerem Ledger (allererster
  Start) wird wie bisher sofort gekauft.
- **Lebenszeichen** (`dca_bot/heartbeat.py`, `HEARTBEAT_INTERVAL_HOURS`,
  Default 24 h): Jeder der vier Bots meldet sich einmal pro Intervall per
  Telegram (`[HEARTBEAT] <Bot> läuft, Version <hash>, letzter Zyklus
  <Zeitpunkt>`), auch wenn nichts passiert ist. Ohne das fällt ein
  abgestürzter Bot nur durch *ausbleibende* Nachrichten auf - und ein
  stiller Grid-Bot kann "keine Stufe durchquert" oder "seit Dienstag tot"
  bedeuten. Der mitgesendete Zyklus-Zeitstempel unterscheidet zusätzlich
  "Prozess läuft" von "Prozess arbeitet". Bewusst **kein** Heartbeat beim
  Start: ein Bot in einer Neustartschleife würde sonst im Minutentakt
  "ich lebe" melden.
- **Kein doppelter Bot-Start** (`dca_bot/process_lock.py`): Jeder der vier
  Prozesse hält beim Start ein exklusives Lock auf einer eigenen
  `.lock`-Datei (`fcntl`/`msvcrt`). Ein zweiter Start desselben Bots
  (z.B. manueller Aufruf neben dem laufenden systemd-Service) wird mit
  klarer Meldung abgelehnt, statt dass beide dasselbe Ledger lesen und
  schreiben und sich gegenseitig Einträge überschreiben. Bewusst ein
  Lock auf dem Dateideskriptor und keine PID-Datei: das Betriebssystem
  gibt es auch bei `kill -9` frei, eine liegengebliebene `.lock`-Datei
  blockiert also keinen Neustart.
- **Live-Schalter mit Sicherheitsschwelle** (`USE_TESTNET`, Default
  `true`): Ob die Bots gegen das Testnet oder die echte Börse handeln,
  ist eine Einstellung in der `.env` und kein Code-Edit mehr. Nur die
  Werte `true`/`false` sind erlaubt - ein Tippfehler bricht ab, statt
  stillschweigend auf `false` (also **live**) zu fallen. Bei `false` gibt
  jeder der vier Prozesse beim Start einen unübersehbaren Block ins Log
  (`ACHTUNG: LIVE-MODUS MIT ECHTEM GELD AKTIV`) **und** eine
  Telegram-Nachricht aus. Unterschieden werden dabei drei Zustände:
  Testnet (eine ruhige Zeile), Live mit aktivem Trading (`CRITICAL`), und
  Live mit deaktiviertem Trading - Letzteres ist ausdrücklich ein eigener
  Fall und kein harmloser Dry-Run, denn die Kontodaten sind echt und ein
  Umlegen einer einzigen Variable genügt dann für echtes Geld.
- **Pflichtvariablen-Check beim Start** (`dca_bot/config_guard.py`):
  Jeder Wert wird beim Laden geprüft, statt mit einem Default
  weiterzulaufen oder erst im Betrieb aufzufallen. Abgedeckt sind unter
  anderem leere Angaben (`GRID_SYMBOL=` ist eine Angabe, keine fehlende
  Zeile - der Default ersetzt sie nicht), Intervalle von 0 (ein
  Busy-Loop gegen die API), unsinnige Prozentwerte (ein
  `GRID_STOP_LOSS_PCT=150` ergäbe eine negative Schwelle und damit einen
  still wirkungslosen Stop-Loss), nicht lesbare Zahlen (die Meldung nennt
  jetzt die betroffene Variable), aus `.env.example` kopierte Platzhalter
  und ein leerer Pending-Orders-Pfad, der die K2-Absicherung abschalten
  würde. Wo `0` eine dokumentierte Bedeutung hat (Stop-Loss aus bei
  DCA/Grid, Heartbeat aus), bleibt es ausdrücklich erlaubt - beim
  Trend-Bot dagegen nicht, dort schlösse ein Stop-Loss von 0 % jede
  Position sofort wieder. Auch die `*_HALT`-Variablen werden beim Start
  geprüft: zur Laufzeit liest der Notaus sie bewusst weiter tolerant
  (eine Exception alle fünf Sekunden wäre schlimmer als das Problem),
  aber `GRID_BOT_HALT=ture` bedeutet dort "kein Notaus" - und der Start
  ist der einzige Moment, das gefahrlos zu bemerken.
- **Im Live-Modus zusätzlich Pflicht**: Telegram-Zugangsdaten (ohne
  Kanal kämen ausgerechnet `[ORDER-UNKLAR]`, `[STOP-LOSS]` und
  `[HEARTBEAT]` nirgends an) sowie alle Werte, die die Positionsgröße
  bestimmen - `DCA_QUOTE_AMOUNT`, `DCA_MAX_DAILY_SPEND`,
  `GRID_LOWER_LIMIT`, `GRID_UPPER_LIMIT`, `GRID_AMOUNT_PER_LEVEL`,
  `TREND_AMOUNT_PER_TRADE`. Sie müssen ausdrücklich in der `.env` stehen
  und dürfen nicht auf die Testnet-Defaults zurückfallen: Live sind genau
  sie die Stellschraube für die tatsächliche Kapitalbindung, und ein
  vergessener Eintrag sähe im Log aus wie ein bewusst gewählter Wert.
- **Fehlkonfiguration löst keine Neustartschleife aus**: Die Prüfung
  läuft zwangsläufig vor dem Logging-Setup. Statt eines nackten
  Tracebacks mit Exit-Code 1 (den `Restart=on-failure` endlos
  wiederholen würde, ohne je erfolgreich zu sein) gibt es eine klare
  Meldung auf stderr, nach Möglichkeit eine Telegram-Nachricht, und ein
  sauberes Ende. Gleiches Muster wie bei einem bereits laufenden Bot.
- **Konsistenz-Check vor jedem Verkauf** (`dca_bot/balance_guard.py`):
  DCA, Grid und Trend teilen sich ein Konto und handeln dasselbe Symbol,
  aber jeder führt sein eigenes Ledger - die Zuordnung "dieses BTC gehört
  dem Grid-Bot" existiert nur buchhalterisch. Vor jedem echten Verkauf
  wird deshalb gegen den tatsächlichen Kontostand geprüft, und zwar
  zweistufig: Reicht das **freie** Guthaben für genau diesen Verkauf
  nicht, wird gar nicht erst verkauft (die Börse würde ablehnen, und der
  Fehlschlag sähe im Log aus wie ein Netzwerkproblem). Deckt das Konto
  darüber hinaus nicht ab, was das eigene Ledger insgesamt als offen
  führt, gibt es eine deutliche Warnung samt Telegram - der einzelne,
  gedeckte Verkauf läuft aber **trotzdem**: Er reduziert Risiko und
  Kapitalbindung, ihn zu blockieren würde nur Assets stranden lassen
  (dieselbe Abwägung wie beim Grid-Stop-Loss, der Verkäufe ebenfalls
  durchlässt). Welche gebundene Menge zu welchem Bot gehört, lässt sich
  dabei ohne Zugriff auf fremde Ledger beantworten - jede Order trägt
  seit dem K2-Fix ein Bot-Präfix in ihrer `clientOrderId`. Die Prüfung
  ist bewusst so gebaut, dass sie keine Fehlalarme erzeugen kann und
  dafür nicht jeden Fall erkennt. Ein **nicht abrufbares** Guthaben lässt
  den Verkauf zu: ein Netzwerkfehler ist keine Aussage über das Konto,
  und einen Stop-Loss-Ausstieg deswegen zu verweigern wäre die
  gefährlichere Richtung.
- **Konsistenz-Check auch beim Bot-Start** (`dca_bot/startup_checks.py`):
  Derselbe Abgleich läuft zusätzlich einmal bei jedem Start - und zwar
  in **allen drei** Bots, also auch im DCA-Bot. Zwei Lücken schließt
  das. Erstens: Der DCA-Bot verkauft nie, hatte also gar keinen
  Verkaufspfad und damit überhaupt keinen Moment, in dem seine
  Buchhaltung je gegen die Realität gehalten wurde - obwohl sein Ledger
  die Kostenbasis des Portfolio-Stop-Loss ist und eine zu große Menge
  den Portfoliowert überschätzt, der Stop-Loss also zu spät auslöst.
  Zweitens: Bei Grid und Trend lief die Prüfung nur im Verkaufsmoment,
  und zwischen zwei Verkäufen können Wochen liegen, beim Trend-Bot auch
  Monate. Der Start ist der natürliche zweite Zeitpunkt - er liegt nach
  jeder Downtime, jedem Deployment und jeder manuellen Änderung an den
  Ledger-Dateien, also nach genau den Ereignissen, die eine Diskrepanz
  überhaupt erzeugen. Gemeldet wird wie im Verkaufspfad **laut, aber
  nicht blockierend** (`[BESTAND-DISKREPANZ]`,
  `[GRID-BESTAND-DISKREPANZ]`, `[TREND-BESTAND-DISKREPANZ]`): Ein Bot,
  der wegen eines Buchhaltungsverdachts gar nicht erst startet, löst
  nichts - er nimmt nur zusätzlich die Fähigkeit weg, offene Positionen
  abzusichern und zu schließen. Das Gate ist dabei bewusst die **Menge**
  und nicht `*_BOT_ENABLE_TRADING`: Führt das Ledger keine echten
  offenen Mengen, passiert gar nichts und es wird kein einziger
  API-Aufruf verbraucht; führt es welche, wird geprüft - auch im
  Dry-Run, denn ein zurückgestellter Bot mit echtem Altbestand ist
  gerade der interessante Fall. Der Aufruf hängt in derselben
  gekapselten Startsequenz wie die Reconciliation, ein Fehlschlag kann
  den Start also nicht verhindern.

- **Echte Handelsregeln statt Annahmen** (`dca_bot/order_utils.py`,
  `binance_client.get_symbol_trading_rules`): Vor jeder Order werden Menge
  und Preise gegen die tatsächlichen Filter des Symbols quantisiert
  (`LOT_SIZE`/`stepSize`, `PRICE_FILTER`/`tickSize`), und der Kaufbetrag
  gegen das Mindestvolumen (`NOTIONAL`/`minNotional`) geprüft. Die Regeln
  werden einmalig pro Bot-Prozess von der Börse geholt und danach
  gecacht - nicht bei jedem Zyklus neu. Schlägt der Abruf fehl, wird der
  Fehler **weitergereicht** statt auf Default-Werte auszuweichen: eine
  still falsch gerundete Order wäre schlimmer als ein abgebrochener
  Zyklus. Alle Bots holen die Regeln deshalb, **bevor** sie eine Order
  platzieren - ein Fehlschlag bricht dann folgenlos ab, statt eine
  bereits ausgeführte Order unverbucht zu lassen.
- **Gebührenbereinigte Mengen**: Binance zieht die Handelsgebühr bei
  einem Spot-Kauf vom erhaltenen Base-Asset ab (bei BTCUSDT also in BTC).
  `executedQty` ist der Betrag **vor** diesem Abzug - ins Ledger kommt
  deshalb die tatsächlich verfügbare Menge (`executedQty` minus der in
  BTC abgerechneten Gebühr aus `fills[]`, abgerundet auf die `stepSize`).
  Ohne das würde jeder spätere Verkauf und jede Stop-Loss-Order über eine
  Menge laufen, die gar nicht mehr da ist. Spiegelbildlich wird beim
  Verkauf die in USDT abgerechnete Gebühr vom Erlös abgezogen, damit der
  realisierte Gewinn nicht systematisch zu optimistisch ist. Im Dry-Run
  gibt es keinen Fill und damit keine bekannte Gebühr - sie wird bewusst
  **nicht** geschätzt, die Menge aber trotzdem quantisiert, damit
  simulierte und echte Werte vergleichbar bleiben.

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
- **Dry-Run-Positionen werden nie real verkauft:** Vor jedem Verkauf
  prüft der Bot das `dry_run`-Flag der jeweiligen Position im Ledger,
  nicht nur den aktuellen Trading-Modus. Eine im Dry-Run "gekaufte"
  Position existiert an der Börse gar nicht - sie bleibt deshalb auch
  nach einem Umschalten auf `GRID_BOT_ENABLE_TRADING=true` simuliert und
  wird dabei explizit als `[DRY-RUN-POSITION]` geloggt. Ohne diese
  Prüfung würde der Bot versuchen, nie gekaufte Assets zu verkaufen.
- **Fehlgeschlagener echter Verkauf schließt die Position nicht:**
  `place_market_sell()` gibt in zwei völlig verschiedenen Fällen `None`
  zurück - im Dry-Run UND bei einem echten API-Fehler. Beide werden
  unterschieden: bei einem echten Fehler wird **kein** Erlös aus
  `quantity * price` erfunden, die Position bleibt **offen** im Ledger
  (`[GRID-VERKAUF-FEHLGESCHLAGEN]` im Log und per Telegram) und der
  nächste Zyklus versucht den Verkauf automatisch erneut, da ihr
  Sell-Target weiterhin erreicht ist. Anders als beim Trend-Bot muss
  dabei keine Absicherung wiederhergestellt werden - der Grid-Bot
  platziert nie eine exchange-seitige Stop-Order und storniert vor einem
  Verkauf entsprechend auch keine. Die Telegram-Meldung kommt pro
  Position nur einmal je Prozesslauf (sonst im 5-Minuten-Takt), ins Log
  geht jeder Fehlschlag.
- **Telegram-Benachrichtigungen** (falls konfiguriert, siehe Abschnitt 7):
  `[GRID-KAUF]`/`[GRID-KAUF DRY-RUN]`, `[GRID-VERKAUF]` (mit realisiertem
  Gewinn/Verlust dieser Position), `[GRID-VERKAUF-FEHLGESCHLAGEN]`,
  `[GRID-STOP-LOSS]`, `[GRID-NOTAUS]`, `[GRID-FEHLER]`.

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
  Ein **automatischer** Reset (Erholungsschwelle + Cooldown) wurde am
  17.09.2026 als reines Backtest-Experiment durchgespielt
  (`python -m dca_bot.trend_backtest --analyze-auto-reset`, Ergebnisse in
  trading-bot-projekt.md 6i) und bewusst **nicht** umgesetzt: Über alle
  drei Referenz-Zeiträume und 27 Parameter-Kombinationen gab es genau
  ein auswertbares Ereignis, und aus n=1 lässt sich keine Parameterwahl
  für eine Sicherheitssperre ableiten. Entschieden wird das mit echten
  Daten aus der Paper-Trade-Phase - gleiches Vorgehen wie beim
  `TREND_STOP_LIMIT_OFFSET_PCT` (siehe Abschnitt 9.5).
- **Telegram-Benachrichtigungen** (falls konfiguriert, siehe Abschnitt 7):
  `[TREND-EINSTIEG]`/`[TREND-EINSTIEG DRY-RUN]`, `[TREND-AUSSTIEG]` (mit
  realisiertem Gewinn/Verlust und Ausstiegsgrund),
  `[TREND-VERKAUF-FEHLGESCHLAGEN]`, `[TREND-STOP-LOSS]`,
  `[TREND-WARNUNG]`, `[TREND-ABSICHERUNG-WIEDERHERGESTELLT]`,
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
  OHNE selbst nochmal zu verkaufen. Der Stop-Loss-Latch wird dabei im
  Exit-Pfad selbst gesetzt und hängt **nicht** daran, ob die
  `[STOP-FILL-ANALYSE]`-Zeile geschrieben werden kann – sonst bliebe ein
  Exit ohne hinterlegten Limitpreis ohne Sperre, und der Bot dürfte
  sofort wieder einsteigen.
- **Verschwundene Stop-Order wird erkannt und ersetzt:** ist die Order
  laut Börse beendet, ohne verkauft zu haben (`CANCELED`/`EXPIRED`/
  `REJECTED` ohne ausgeführte Menge – z.B. manuell storniert), schützt
  sie nichts mehr. Der Bot löst die Zuordnung im Ledger und platziert
  noch im selben Durchlauf Ersatz. Ohne das hätte die tote Order-ID
  `_ensure_stop_loss_protection()` dauerhaft blockiert, das bei jeder
  vorhandenen ID sofort aussteigt – die Position wäre unbegrenzt ohne
  Absicherung geblieben. Eine **fehlgeschlagene** Status-Abfrage gilt
  ausdrücklich nicht als „Order weg": sie sagt nichts über die Order,
  und ein Netzwerkhänger würde sonst eine zweite Order über dieselbe
  Menge auslösen.
- **Teilweise gefüllte Stop-Order** (`PARTIALLY_FILLED`): wird gemeldet
  (Log + Telegram), aber bewusst **nicht** korrigiert – die Order lebt
  noch und kann vollständig füllen, jede jetzt notierte Teilmenge wäre
  im nächsten Moment falsch. Sobald sie einen Endzustand erreicht,
  greift der reguläre Pfad mit den echten Fülldaten. Bei 24-Stunden-Takt
  ist das höchstens eine Erinnerung pro Tag.
- **Eine einzige Regel für Order-Status:** die Bewertung, ob eine Order
  gefüllt, noch aktiv, beendet oder unlesbar ist, steht genau einmal im
  Projekt (`order_lifecycle_state()` in `pending_orders.py`) und wird
  sowohl vom Zyklus-Check als auch vom Pending-Orders-Pfad (Abschnitt 6)
  verwendet. Vorher hatten beide eigene, leicht unterschiedliche
  Regeln.
- **Reconciliation beim Bot-Start:** bevor der erste reguläre Zyklus
  läuft, gleicht der Bot eine im Ledger offene Position gegen den
  tatsächlichen Order-Status bei Binance ab und korrigiert den Ledger
  sofort, falls die Stop-Order während der Downtime gefüllt wurde -
  klar geloggt als `[REKONZILIATION]`. Davor läuft seit dem K2-Fix
  `reconcile_pending_orders()` (siehe Abschnitt 6), und diese
  Reihenfolge ist bewusst so: ein dort nachgetragener Einstieg erzeugt
  eine offene Position **ohne** Stop-Loss-Order, die dieser Schritt
  unmittelbar danach über `_ensure_stop_loss_protection()` absichert.
  Umgekehrt liefe er ins Leere - die Position gäbe es zu seinem
  Zeitpunkt noch gar nicht.
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
- **Dry-Run-Positionen werden nie real verkauft:** Vor jedem Verkauf
  prüft der Bot das `dry_run`-Flag des Ledger-Eintrags, nicht nur den
  aktuellen Trading-Modus. Eine im Dry-Run "gekaufte" Position existiert
  an der Börse gar nicht - sie bleibt deshalb auch nach einem Umschalten
  auf `TREND_BOT_ENABLE_TRADING=true` simuliert und wird dabei explizit
  als `[DRY-RUN-POSITION]` geloggt.
- **Fehlgeschlagener echter Verkauf schließt die Position nicht:**
  `place_market_sell()` gibt in zwei völlig verschiedenen Fällen `None`
  zurück - im Dry-Run UND bei einem echten API-Fehler. Beide werden
  unterschieden: bei einem echten Fehler wird **kein** Erlös aus
  `quantity * price` erfunden, die Position bleibt **offen** im Ledger
  und es wird **kein** Stop-Loss-Latch gesetzt (es hat ja kein Ausstieg
  stattgefunden). Geloggt als `[TREND-VERKAUF-FEHLGESCHLAGEN]`, zusätzlich
  per Telegram. Da die exchange-seitige Stop-Order zu diesem Zeitpunkt
  bereits storniert ist (siehe Exit-Reihenfolge oben), wäre die weiterhin
  offene Position sonst ungeschützt - der Bot platziert deshalb sofort
  eine **neue** Stop-Loss-Order mit derselben Schwelle
  (`entry_price * (1 - TREND_STOP_LOSS_PCT/100)`) und hinterlegt sie im
  Ledger. Schlägt auch das fehl, wird der doppelt kritische Zustand
  (weder verkauft noch exchange-seitig abgesichert) als `ERROR` geloggt
  und per Telegram gemeldet; die stornierte Order-ID wird aus dem Ledger
  entfernt, statt eine tote Order als Absicherung auszuweisen.
- **Selbstheilende Absicherung:** In jedem Zyklus, in dem eine offene,
  echte Position NICHT geschlossen wird, sowie beim Reconciliation-Schritt
  am Bot-Start prüft der Bot, ob überhaupt eine Stop-Loss-Order hinterlegt
  ist - und platziert sonst eine neue (Schwelle wie beim Entry aus
  `entry_price`). Das schließt beide Wege, auf denen eine Position sonst
  dauerhaft ungeschützt bleiben konnte: die Stop-Order scheiterte schon
  beim Entry, oder ein fehlgeschlagener Verkauf konnte seine zuvor
  stornierte Absicherung nicht ersetzen und der Exit-Grund entfiel danach
  wieder (Trend dreht zurück auf "up") - in beiden Fällen hätte vorher nie
  wieder etwas eine Order platziert. Erfolg wird als
  `[TREND-ABSICHERUNG-WIEDERHERGESTELLT]` geloggt; scheitert es weiter,
  zählt `unprotected_cycles` hoch und löst ab 3 aufeinanderfolgenden
  Zyklen eine `[TREND-WARNUNG]` per Telegram aus (gleiches Muster wie
  `uncertain_cycles`), mit Entwarnung, sobald die Absicherung wieder
  steht. Bewusst erst NACH den Exit-Entscheidungen des Zyklus: wird die
  Position ohnehin gerade geschlossen, wäre eine neue Order sofort wieder
  zu stornieren, und bei ausgelöstem Stop-Loss läge der Preis bereits
  unter der Stop-Schwelle (die Börse würde die Order zurückweisen).
- **Dry-Run** (`TREND_BOT_ENABLE_TRADING=false`): es wird KEINE echte
  Stop-Order platziert, nur geloggt ("[DRY-RUN] Würde
  Stop-Loss-Order platzieren..."). Die Position bleibt dann wie bisher
  ausschließlich software-intern überwacht - gleiches Sicherheitsprinzip
  wie bei der Entry-Order (kein Trading ohne Opt-in).
- **Erledigt (war: TODO vor Echtgeld):** Stop-/Limit-Preis wurden früher
  nur auf 2 Nachkommastellen gerundet, nicht gegen die echte
  `PRICE_FILTER`-Tick-Size des Symbols validiert. Seit dem K3-Fix werden
  beide Preise und die Menge gegen die tatsächlichen `exchangeInfo`-Filter
  quantisiert (siehe Abschnitt 6) - die Menge zusätzlich um die beim Kauf
  abgezogene Handelsgebühr bereinigt, sonst würde die Stop-Order über eine
  nicht mehr vorhandene Menge laufen und von der Börse abgelehnt.
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
- **Zwei Takte, bewusst entkoppelt** (Sicherheitsreview-Punkt W9): Die
  EMAs werden mit **genau einem Tagesschlusskurs pro Kalendertag**
  gefüttert - identisch zum Backtest. `ALLOCATOR_INTERVAL_MINUTES`
  bestimmt dagegen nur, wie oft der Prozess aufwacht, den Zustand mit
  frischem Zeitstempel neu veröffentlicht und den Notaus prüft.
  Hintergrund: `TrendSignalGenerator` ist ereignisgesteuert, jeder
  `feed()` rückt die EMAs um **eine Periode** vor. Vorher speiste jeder
  60-Minuten-Zyklus einen Spot-Ticker ein, also 24 Werte pro Tag in eine
  auf 20/50 **Tage** ausgelegte Berechnung - das Ergebnis war faktisch
  eine EMA(20h)/EMA(50h), ein anderer Indikator als der backgetestete.
  Der stündliche Takt bleibt trotzdem: Er ist das Lebenszeichen, an dem
  die Frische-Prüfung unten hängt. Ein Tages-Intervall hätte deren
  Schwelle von drei Stunden auf drei Tage gedehnt.
- **Glättung in Tagen**: `ALLOCATOR_SMOOTHING_PERIOD` rückt entsprechend
  nur beim Tages-Feed vor und ist damit direkt mit
  `--smoothing-period-days` im Backtest vergleichbar (dort Default 3.0).
  Nach einer Downtime werden versäumte Tage einzeln nachgeholt, jeder
  gegen sein eigenes Tagesziel - das Ergebnis ist dasselbe, als wäre der
  Prozess durchgelaufen.
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
- **Frische-Prüfung der Zuteilung**: Stirbt der Allocator-Prozess, bliebe
  der zuletzt berechnete Wert sonst für immer gültig – bei eingefrorenen
  100% Trend hätte der DCA-Bot dauerhaft gar nicht mehr gekauft, ohne
  dass irgendetwas darauf hinweist. Ist `updated_at` älter als das
  Dreifache des Allocator-Intervalls, fallen DCA/Trend auf **100% DCA /
  0% Trend** zurück (die konservativere Richtung) und loggen eine
  Warnung. Die Schwelle kommt aus der State-Datei selbst: der Allocator
  schreibt sein `interval_minutes` mit, statt dieselbe Zahl ein zweites
  Mal auf Konsumentenseite zu konfigurieren.
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

## 11. Positions-Audit (offene Positionen prüfen)

```bash
python -m dca_bot.audit_positions
```

Listet den Bestand von **DCA-, Grid- und Trend-Bot** auf, jeweils mit
seinem **Dry-Run-Status**. Rein informativ: das Skript liest nur, ändert
nichts an den Ledger-Dateien und platziert keine Orders.

Gedacht als Überblick, bevor ein pausierter Bot wieder freigeschaltet
oder `*_BOT_ENABLE_TRADING` umgestellt wird - dann ist auf einen Blick
sichtbar, welche offenen Positionen an der Börse tatsächlich existieren
(`ECHT`) und welche nur simuliert wurden (`DRY-RUN`, werden nie real
verkauft, siehe Abschnitt 8.4/9.5). Der DCA-Abschnitt zeigt zusätzlich
Menge, Einsatz und durchschnittlichen Einstandspreis - der Bot verkauft
nie, seine Summe aller echten Käufe *ist* sein Bestand.

Pfade kommen aus `DCA_BOT_STATE_FILE`/`GRID_STATE_FILE`/
`TREND_STATE_FILE` bzw. den üblichen Defaults, alternativ über
`--dca-file` / `--grid-file` / `--trend-file`.

**Invarianten-Check auf geschlossene Grid-Positionen:** Zusätzlich meldet
der Grid-Abschnitt jede **geschlossene Dry-Run-Position mit negativer
`realized_pnl`**. Das sollte strukturell gar nicht vorkommen können: Der
Grid-Bot verkauft nur bei erreichtem Sell-Target, und das ist die
nächsthöhere Grid-Stufe, liegt also über dem Kaufpreis - und im Dry-Run
gibt es keine Gebühr, die etwas abziehen könnte. Ein Minus ist dort
deshalb kein schlechter Trade, sondern ein Datenfehler; es war genau das
Symptom, an dem der Folgefund aus K3 aufgefallen ist (siehe
`trading-bot-projekt.md` Abschnitt 6g und 11.2 unten). Rein informativ
wie der Rest des Skripts: es wird gemeldet, nicht korrigiert. Echte
Positionen bleiben bewusst draußen - dort zieht die Verkaufsgebühr vom
Erlös ab, ein knapp erreichtes Ziel darf legitim im Minus enden. Beim
Trend-Bot existiert die Invariante ohnehin nicht (ein Stop-Loss-Exit
macht per Definition Verlust).

### 11.1 Bot-übergreifender Kontoabgleich

Sind Binance-Zugangsdaten vorhanden, hängt das Skript einen zweiten
Teil an: Es fragt den **tatsächlichen** Kontostand und die offenen
Orders ab und stellt ihnen die **Summe** dessen gegenüber, was alle drei
Ledger als offen führen.

```
Bot          laut Ledger offen  Hinweis
------------------------------------------------------------------
dca                 0.00780000
grid                0.00116000  2 Dry-Run (zählt nicht)
trend               0.00019505
------------------------------------------------------------------
SUMME               0.00915505
```

Das ist bewusst **kein** Feature eines Bots, sondern nur dieses
Werkzeugs. Jeder Bot führt sein eigenes Ledger und darf kein fremdes
lesen - diese Trennung ist ein Grundprinzip des Projekts. Damit kann
aber auch keiner die entscheidende Frage beantworten: Passt die Summe
aller drei überhaupt auf das eine geteilte Konto? Der `balance_guard`
prüft in jedem Bot nur, ob dessen *eigener* Anspruch für sich genommen
noch gedeckt wäre - eine Prüfung ohne Fehlalarme, die dafür genau den
Fall nicht sieht, in dem erst die Summe zu groß wird. Ein rein lesendes
Werkzeug darf alles einsehen und ist deshalb der richtige Ort dafür.

Weitere Eigenschaften:

- **Ohne API-Keys wird nur dieser zweite Teil übersprungen**, mit einer
  Meldung, was fehlt - der Ledger-Teil läuft weiter. Die bisherige
  Zusage "braucht keine API-Keys" gilt also unverändert. Mit `--offline`
  lässt sich der Abgleich auch bei vorhandenen Keys abschalten.
- **Der Client kann strukturell keine Orders platzieren:** Er wird ohne
  Pending-Orders-Datei gebaut, und die `place_*`-Methoden weisen genau
  diesen Zustand aktiv zurück (siehe `binance_client.py`). Die
  Nur-Lesend-Zusage hängt damit nicht an Disziplin beim Programmieren.
- **Verglichen wird gegen `frei + gebunden`**, nicht nur gegen das freie
  Guthaben: Eine Menge in einer offenen Verkaufs-Order existiert noch,
  sie ist nur gerade nicht verkäuflich. Die gebundene Menge wird
  zusätzlich nach Verursacher aufgeschlüsselt (über das
  clientOrderId-Präfix aus dem K2-Fix), inklusive eines eigenen Eintrags
  für fremde bzw. manuell über die Börsen-Oberfläche platzierte Orders.
- **Gruppiert nach Symbol**, falls die drei Bots unterschiedliche Paare
  handeln - eine Gesamtsumme über verschiedene Assets wäre sinnlos. Im
  Normalfall (alle drei BTCUSDT) ist das genau eine Gruppe.
- **Ein Überschuss ist kein Befund.** Hält das Konto mehr, als die
  Ledger beanspruchen, kann das manueller Bestand oder eine Altlast
  sein. Nur die andere Richtung wird als Problem gemeldet - und dann mit
  dem ausdrücklichen Hinweis, die Ledger-Dateien **nicht** blind
  anzupassen, bevor geklärt ist, welche Seite recht hat.
- Die Toleranz stammt aus demselben `balance_guard`, nach dem auch die
  Bots entscheiden - zwei getrennte Toleranzen für dieselbe Frage wären
  der sichere Weg zu einem Audit, das einem Bot widerspricht.

### 11.2 Einmalige Datenkorrektur (Dry-Run-Beträge)

```bash
python -m dca_bot.fix_dry_run_quote_spent            # nur Bericht
python -m dca_bot.fix_dry_run_quote_spent --apply    # schreibt
```

Einmaliges Korrektur-Werkzeug zum Fund vom 22.09.2026 (siehe
`trading-bot-projekt.md` Abschnitt 6g): Seit dem K3-Fix quantisierten
alle drei Bots im Dry-Run die Kaufmenge, buchten als `quote_spent` aber
weiter den konfigurierten Rohbetrag – die weggerundete Teilmenge wurde
nie gekauft, stand aber in der Kostenbasis. Die realisierte PnL
geschlossener Dry-Run-Positionen wurde dadurch systematisch zu negativ
und konnte trotz gestiegenem Kurs im Minus landen.

Das Skript rechnet `quote_spent` und `realized_pnl` betroffener Einträge
aus der tatsächlich gehaltenen Menge neu. **Ohne `--apply` wird nichts
geschrieben**, nur berichtet. Einträge mit `dry_run: false` bleiben
unangetastet – dort ist `quote_spent` der von der Börse gemeldete
`cummulativeQuoteQty` und damit die Quelle der Wahrheit; fehlt das
`dry_run`-Feld, wird ebenfalls nicht geraten, sondern gemeldet. Der Lauf
ist idempotent (Einträge von vor dem K3-Fix sind ein No-op), legt vor dem
Schreiben eine zeitgestempelte Kopie an und holt dabei dasselbe Lock wie
der jeweilige Bot – er läuft also nicht neben einem laufenden Bot, dessen
nächster Zyklus die Korrektur sonst überschriebe.

## 12. Tests

```bash
python -m unittest tests.test_notifier tests.test_order_utils     tests.test_dca_fee_adjustment tests.test_trend_stop_loss     tests.test_grid_sell_safety tests.test_pending_orders     tests.test_order_reconciliation tests.test_process_lock     tests.test_kill_switch tests.test_stage_b_safety     tests.test_stage_c_safety tests.test_trend_decide_action     tests.test_improvements_stage_1 tests.test_grid_signals     tests.test_allocator_signals tests.test_startup_balance_check     tests.test_audit_positions tests.test_trend_auto_reset \
    tests.test_fix_dry_run_quote_spent -v
```

Alle Tests laufen ohne Netzwerkzugriff und ohne Binance-Zugangsdaten
(Fake-Clients mit derselben Schnittstelle wie `binance_client.py`,
temporäre Ledger-Dateien). Abgedeckt sind die sicherheitskritischen
Pfade: Token-Hygiene der Telegram-Benachrichtigungen, der echte
exchange-seitige Stop-Loss inkl. Race Conditions, sowie die
Verkaufs-Sicherheit von Grid und Trend (Dry-Run-Positionen, fehl-
geschlagene echte Verkäufe), sowie die Anbindung an die echten
Handelsregeln inklusive Gebührenkorrektur.

Dazu die idempotente Order-Platzierung (siehe Abschnitt 6):
`test_pending_orders.py` prüft den Ground-Truth-Abgleich und die drei
Netzwerkfehler-Szenarien direkt am `TradingClient` (mit einem gefälschten
**rohen** Binance-Client darunter - der Fehler entsteht genau in der
Zeile, in der `python-binance` seinen Request absetzt),
`test_order_reconciliation.py` das Nachtragen beim Bot-Start für alle
drei Bots inklusive Idempotenz, und `test_process_lock.py` den Schutz
gegen einen doppelten Bot-Start. `test_kill_switch.py` deckt alle drei
Notaus-Wege ab, insbesondere das Wirken einer nachträglich geänderten
`.env` ohne Neustart. `test_stage_b_safety.py` bündelt die
Korrektheits- und Verfügbarkeitspunkte: UTC-Tagesfenster,
Ledger-Integrität inkl. atomarer Writes, Fälligkeitsprüfung beim Start,
Frische der Allocator-Zuteilung, Heartbeat und der Notaus zwischen
mehreren Grid-Käufen. `test_stage_c_safety.py` deckt die letzten
Code-Punkte vor dem Echtgeld-Schalter ab: den Live-Schalter samt
striktem Wahrheitswert-Parsing und der lauten Start-Warnung, den
Pflichtvariablen-Check, den Konsistenz-Check vor jedem Verkauf auf dem
geteilten Konto, und den entkoppelten Feed-Takt des Allocators. Mehrere
davon sind ausdrücklich Negativkontrollen: Dreht man die jeweilige
Änderung zurück, fallen sie um.

`test_trend_decide_action.py` schließt die letzte Lücke der
Testabdeckung: die Entscheidungslogik des Trend-Bots
(`decide_action()` in `trend_signals.py`). Alle übrigen Trend-Tests
setzen `strategy._seeded = True`, um den Netzwerkzugriff auf die
Historie zu vermeiden – damit bleibt der Signalgenerator leer,
`confirmed_direction` ist dort immer `None`, und die Entscheidung wurde
nie mit einem echten Signal getroffen (nachgemessen: 24 Aufrufe in der
übrigen Suite, davon 0 mit bestätigter Richtung). Diese Datei füttert
den Generator stattdessen mit synthetischen, aber vollständig
durchlaufenen Preisreihen – Aufwärts- und Abwärtstrend, Seitwärtsmarkt,
ein Trend knapp unter der Trendstärke-Schwelle und ein echter Whipsaw
(die EMAs kreuzen sich tatsächlich, ohne dass die Schwelle erreicht
wird). Jede Reihe hat zusätzlich einen eigenen Test, der belegt, dass
sie das Signal erzeugt, das ihr Name behauptet: Ein Test, dessen
Prämisse nicht stimmt, wäre grün, ohne etwas zu prüfen. Der Pfad Signal
→ Entscheidung → Ein-/Ausstieg läuft dabei auch einmal komplett durch
`execute_once()`, nicht nur durch direkte Methodenaufrufe.

`test_improvements_stage_1.py` deckt die erste Stufe der
Verbesserungsvorschläge ab: das atomare Schreiben der
Allocator-State-Datei, den konservativen Rückfall bei einer
unbrauchbaren Zuteilung (und die bewusste Abgrenzung zur *fehlenden*
Datei, die weiterhin „kein Allocator" bedeutet), sowie den globalen
Notaus `STOP_ALL` über alle vier Bots. Die Gebührenkorrektur im
Stop-Fill-Pfad steht in `test_trend_stop_loss.py` bei ihren
Geschwistern. Auch hier sind alle drei Bereiche gegen den
zurückgedrehten Stand gemessen.

`test_grid_signals.py` und `test_allocator_signals.py` schließen die
zweite Lücke derselben Art wie W17 beim Trend-Bot: Die vier
Entscheidungsfunktionen des Grid-Bots (`compute_grid_levels`,
`find_triggered_buy_levels`, `is_sell_target_hit`,
`is_trend_break_stop_loss_hit`) und die Zuteilungs-Mathematik des
Allocators hatten keinen einzigen direkten Test - sie liefen nur
indirekt über Strategie- und Backtest-Läufe mit, also immer nur an der
Preislage, die ein anderer Testfall zufällig brauchte. Ausgerechnet
dort saßen die beiden Designfehler, die vor Fertigstellung des
Grid-Bots gefunden wurden (Kaltstart, Intervallgrenze). Beide sind
jetzt mit einer **Gegenprobe** abgedeckt, nicht nur mit einer
Zusicherung: Zum Kaltstart-Fall gehört der Nachweis, dass an derselben
Preislage sechs Kaufstufen zu holen *wären* und mit gesetztem
Referenzpreis auch geholt werden - sonst wäre „der Kaltstart löst
nichts aus" auch dort grün, wo ohnehin nichts zu kaufen war. Zur
Intervallgrenze gehört spiegelbildlich, dass ein minimal höherer
Referenzpreis die Stufe sehr wohl einschließt. Bei den
Allocator-Funktionen trägt die fallende Preisreihe einen EMA-Abstand
von über 3 %, der ohne die Richtungsprüfung auf volle 100 %
Trend-Anteil abgebildet würde - erst das macht „Abwärtstrend ergibt
0 %" zu einer Aussage über die Logik statt über eine flache Reihe.

`test_startup_balance_check.py` und `test_audit_positions.py` decken die
zweite Stufe der Verbesserungsvorschläge ab: den Konsistenz-Check beim
Bot-Start für alle drei Bots (inklusive des Nachweises, dass ohne echte
offene Menge kein einziger API-Aufruf entsteht, und dass die eigene
Stop-Loss-Order des Trend-Bots keinen Fehlalarm auslöst - mit
Gegenprobe über dieselbe Order ohne Bot-Präfix), sowie den
bot-übergreifenden Kontoabgleich im Positions-Audit. Die Verdrahtung in
allen drei `main*.py` hat einen eigenen Test; er liest den Quelltext
der jeweiligen `main()`, statt sie auszuführen, und belegt damit genau
den Fehler, der hier realistisch ist - drei beinahe identische
Aufrufstellen, von denen später eine vergessen wird.

`test_trend_auto_reset.py` deckt den Analyse-Modus
`--analyze-auto-reset` des Trend-Backtests ab (siehe Abschnitt 9.4 und
trading-bot-projekt.md 6i). Dass ein reiner Analyse-Modus Tests bekommt,
hat denselben Grund wie bei den Entscheidungsfunktionen von Grid und
Allocator: Auf dieser Rechnung soll eine Strategie-Entscheidung beruhen,
und sie ist die einzige Grundlage dafür - anders als beim Live-Code
fällt ein Fehler hier durch nichts anderes auf. Geprüft werden vor allem
drei Aussagen: dass die UND-Verknüpfung von Erholungsschwelle und
Cooldown wirklich ein UND ist (jede Bedingung allein reicht
nachweislich nicht - zu einem ODER verrutscht wäre es eine stille, im
Ergebnis aber gravierende Änderung), dass der Anker der Erholung der
tatsächliche Ausstiegskurs ist und nicht die rechnerische Stop-Schwelle
(mit einem eigenen Test für die *Verdrahtung*, nicht nur für die
Rechnung), und dass ein Wiedereinstieg über seinen Ausstiegsgrund als
"falsch" gilt und nicht über das Vorzeichen seiner PnL - dazu die
Gegenprobe mit einem Wiedereinstieg, der Verlust macht und trotzdem
nicht als falsch zählt.

## 13. Nächste Ausbaustufen (siehe trading-bot-projekt.md)

- [ ] Konfiguration vollständig über `.env` statt Code-Defaults
- [x] Persistente Speicherung der Trade-Historie (`data/trade_ledger.json`)
- [ ] Backtesting-Skript für die DCA-Logik auf historischen Daten
- [x] Grid-Trading-Strategie als zweiter, eigenständiger Bot (siehe Abschnitt 8), inkl. Backtesting-Skript (siehe Abschnitt 8.5)
- [x] Trend-Following-Strategie (EMA-Crossover) als dritter, eigenständiger Bot, inkl. Backtest vor dem ersten Dry-Run (siehe Abschnitt 9)
- [x] Kapital-Allocator als vierter, übergeordneter Baustein (siehe Abschnitt 10), inkl. Backtest vor dem ersten Dry-Run - Live-Dry-Run noch offen

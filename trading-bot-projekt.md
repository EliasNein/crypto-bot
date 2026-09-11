# Trading-Bot-Projekt: Planung & Recherche

**Stand:** September 2026
**Status:** Planungsphase – Entwicklung startet auf Demo-/Testnet-Konto, kein Live-Geld bisher.

---

## 1. Projektziel

Ein vollautomatisierter Trading-Bot, der Trades eigenständig abschließt. Entwicklung erfolgt schrittweise, zuerst vollständig auf einem Demo-/Testnet-Konto, bevor überhaupt reales Kapital eingesetzt wird.

**Wichtige Rahmenbedingungen:**
- Kein Erfolgs- oder Renditeversprechen – auch ein technisch einwandfreier Bot kann Geld verlieren.
- Rechtlich (Deutschland): automatisiertes Trading mit eigenem Kapital ist unproblematisch, Gewinne sind steuerpflichtig (Abgeltungssteuer). Sobald fremdes Geld verwaltet oder der Bot Dritten angeboten wird, greift das KWG und es braucht eine BaFin-Erlaubnis. Für dieses Projekt (eigener Bot, eigenes Konto) nicht relevant.

---

## 2. Rahmen-Entscheidungen (bisher)

| Punkt | Entscheidung |
|---|---|
| Asset-Klasse | Krypto (Empfehlung, aus Recherche zu Erfolgsaussichten je Asset-Klasse) |
| Programmiererfahrung | Grundkenntnisse vorhanden → Python |
| Broker/Exchange | Binance Testnet (empfohlen: kostenlos, gute API, 24/7-Markt, viele Trainingsdaten) |
| Alternative Asset-Klasse | Aktien über Alpaca (kostenloses Paper-Trading, sehr einsteigerfreundliche API) – falls Krypto sich doch nicht als richtig erweist |

---

## 3. Projekt-Roadmap (8 Phasen)

1. **Strategie & Ziele definieren** – Art der Strategie, Zeithorizont, realistisches Renditeziel, maximal akzeptabler Drawdown festlegen.
2. **Tech-Stack & Broker/Exchange wählen** – Python, Binance Testnet, Bibliotheken wie pandas, backtrader/vectorbt oder Freqtrade.
3. **Daten-Pipeline aufbauen** – historische Kursdaten + Live-Datenanbindung, saubere und konsistente Datenbasis.
4. **Strategie implementieren & Backtesting** – Overfitting vermeiden, Out-of-Sample-Tests einplanen.
5. **Risikomanagement einbauen** – feste Positionsgrößen, Stop-Loss-Logik, Tagesverlustlimit, Notaus-Schalter.
6. **Paper Trading auf dem Demokonto** – mehrere Wochen/Monate Live-Test ohne echtes Geld (Slippage, Latenz, Marktlücken).
7. **Monitoring & Logging** – jeder Trade protokolliert, Dashboard/Benachrichtigungen (z.B. Telegram).
8. **Vorsichtiger Live-Start** – erst nach erfolgreicher Paper-Trading-Phase, nur mit kleinem, verschmerzbarem Betrag, schrittweise skalieren.

---

## 4. Recherche-Ergebnis 1: Welche Asset-Klasse ist für Bots am erfolgreichsten?

*(Erste, oberflächliche Websuche – siehe Einschränkung unten)*

- **Es gibt keinen eindeutigen Sieger** unter den Anlageklassen – Erfolg hängt von Strategie-zu-Markt-Struktur-Fit ab.
- **Krypto:** am zugänglichsten für Retail-Bots (24/7-Handel, fragmentierte Liquidität über viele Exchanges → begünstigt Arbitrage & Momentum). Akademisch belegte, dauerhaft ausnutzbare Ineffizienz bei Binance-Triangular-Arbitrage: ca. 14,4 Basispunkte besserer Wechselkurs, ca. 2,71 % aller Binance-Trades betroffen. Grid-Bots funktionieren am besten in Seitwärtsmärkten (BTC/ETH), realistisch ca. 0,5–3 % Rendite/Monat in Ranging-Phasen.
- **Forex:** lange Historie im Algo-Handel, stark institutionalisiert, MetaTrader-5-Expert-Advisors (MQL5) als Quasi-Standard – nicht Python-basiert.
- **Aktien:** ca. 80 % des US-Aktienhandelsvolumens (2018) bereits algorithmisch, aber überwiegend institutionelles High-Frequency-Trading – als Privatperson kaum konkurrenzfähig auf Geschwindigkeit.
- **Wichtige Einschränkung:** Gewinnrate ist nicht gleich Profitabilität – ein Beispiel-Bot hatte nur 37 % Trefferquote, war aber trotzdem profitabel wegen eines Gewinn-Verlust-Verhältnisses von 2,5:1.

**Fazit:** Krypto als pragmatischster technischer Einstieg (einfacher API-Zugang, kostenlose Testnets, kein Handelsschluss).

---

## 5. Recherche-Ergebnis 2: Vertiefte, quellenkritische Untersuchung zu Krypto-Bot-Strategien

*(Advanced-Research-Auftrag – akademisch fundierte Quellen priorisiert, Marketing-Blogs explizit gekennzeichnet)*

### Kernaussage
Für einen Python-Einsteiger, der zuerst auf Testnet entwickelt, sind **DCA** und **Grid-Trading** die realistischsten Startstrategien – nicht wegen höchster Rendite, sondern wegen einfacher, latenzunkritischer technischer Umsetzung. **Trend-Following/Momentum** ist die am besten akademisch belegte Alpha-Strategie und sinnvoller nächster Schritt. **Arbitrage, Market Making und Scalping sind für Einsteiger ungeeignet** (Latenz- und Kapitalanforderungen, Konkurrenz durch professionelle HFT-Firmen).

### Strategie-Übersicht

| Strategie | Beste Marktbedingung | Akademische Evidenz (Kurzfassung) | Einstiegshürde | Haupt-Risiko |
|---|---|---|---|---|
| **Grid Trading** | Volatile Seitwärtsmärkte | Erwartungswert mathematisch **null** vor Gebühren (Chen/Chen/Jang, arXiv 2506.11921); dynamische Variante (DGT) erzielte 60–70 % IRR im Backtest 2021–2024, aber stark bullenmarkt-getrieben | Niedrig | Trendbruch |
| **DCA** | Fallende/volatile Märkte | Vanguard-Studie: Lump-Sum schlägt 12M-DCA in ~67–68 % der Fälle; DCA im Vorteil in 20–70 %-BTC-Drawdown-Zone | Sehr niedrig | Kein Schutz vor Mehrjahres-Bärenmärkten |
| **Mean Reversion** | Range-/Seitwärtsmärkte | BTC neigt am lokalen Minimum zu Mean Reversion, am Maximum zu Trend (Vojtko/Padyšák); Pairs-Trading ~3 %/Monat | Mittel | Trendbruch ("fallendes Messer") |
| **Momentum/Trend-Following** | Anhaltende Trends | Stärkste Evidenz der Gruppe: Liu & Tsyvinski (NBER); Time-Series-Momentum 31,96 % p.a. im Vergleich (Gbadebo 2026) | Mittel | Overfitting, Momentum-Crashes |
| **Arbitrage** | Preisineffizienzen zwischen Börsen | Makarov & Schoar (Journal of Financial Economics 2020): große dokumentierte Spreads, aber Netto-Profite nach Kosten oft vernachlässigbar; Ausführung in ≤146 ms nötig | Sehr hoch (Latenz-Infrastruktur) | Kapazitätsbegrenzt, ausgereizt |
| **Market Making** | Mean-reverting Umgebungen | Falces Marin et al. (PLOS ONE): Sharpe 0,624 (Gen-AS-Modell) | Hoch | Inventory-Risiko, Gebührenabhängigkeit |
| **Scalping/HFT** | Hohe Liquidität | Kearns et al.: Breakeven-Win-Rate ~55 % bei 0,1 % Kosten | Sehr hoch | Gebühren fressen Profit |
| **KI/ML-Ansätze** | Variabel | Gort et al.: überangepasste Modelle performen schlechter als weniger überangepasste | Sehr hoch | Overfitting (dominant) |

### Empfohlener Umsetzungsfahrplan

**Stufe 1 (Wochen 1–4) – Fundament auf Testnet:**
Start mit **DCA-Bot** auf Binance-Testnet. Tools: `python-binance` oder **Freqtrade** (Open Source, Python, eingebauter Dry-Run/Paper-Trading-Modus, Backtesting). Ziel: API-Anbindung, Order-Platzierung, Logging, Fehlerbehandlung sauber beherrschen.

**Stufe 2 (Wochen 5–10) – Erste echte Strategie mit Backtesting:**
**Spot-Grid-Bot** (kein Hebel, kein Liquidationsrisiko) und/oder einfache **Mean-Reversion**-Strategie (Bollinger/RSI). Rigoroses Backtesting vor Paper-Trading. Stop-Loss unterhalb der Grid-Untergrenze essenziell.

**Stufe 3 (ab Woche 10) – Alpha-Strategie:**
**Time-Series-Momentum/Trend-Following** (EMA-Crossover, Volatilitäts-Normalisierung). Walk-Forward-Validierung, Out-of-Sample-Test zwingend gegen Overfitting.

### Benchmarks vor jedem Realgeld-Einsatz
1. Mindestens 200 Paper-Trades, Ergebnisse innerhalb ±15 % des Backtests.
2. Stop-Loss serverseitig auf der Börse, nicht nur im Code.
3. Realistische Gebühren und Slippage im Backtest berücksichtigt.
4. Positive risikoadjustierte Kennzahl (Sharpe > 1 als Zielmarke).

### Was zu vermeiden ist
Arbitrage, Market Making, Scalping als **erste** Strategien – zu kapital-/latenzintensiv für Einsteiger. ML/RL-Ansätze erst nach sauberer Validierungspipeline.

### Wichtige Caveats
- Backtest ≠ Live-Performance (Overfitting, Survivorship Bias, optimistische Gebühren-Annahmen möglich).
- Quellenqualität variiert stark: Akademische Quellen (NBER, Journal of Financial Economics, SSRN, peer-reviewed) sind belastbar; viele Anbieter-Blogs enthalten unbelegte/erfundene Zahlen (z.B. "99%+ Trefferquote", "6.712% Rendite") – diese wurden bewusst nicht übernommen.
- Krypto-spezifische Risiken (Börsen-Insolvenz, Hacks, Marktmanipulation) bestehen unabhängig von der gewählten Strategie.

**Vollständiger Recherche-Bericht mit allen Quellenangaben und Zitaten:** siehe separates Artefakt "Krypto-Trading-Bot-Strategien: Quellenkritischer Vergleich" aus dem Chat.

---

## 6. Nächste Schritte (offen)

- [ ] Konkrete Erst-Strategie final festlegen (Empfehlung: DCA als Startpunkt)
- [ ] Binance-Testnet-Account einrichten
- [ ] Projektgrundgerüst aufsetzen (Python, ggf. Freqtrade)
- [ ] Erste einfache Strategie + Backtesting-Skript implementieren
- [x] Risikomanagement-Logik definieren (Positionsgrößen, Stop-Loss, Tagesverlustlimit) – Notaus, persistentes Tageslimit und Portfolio-Stop-Loss in `dca_bot/risk.py` umgesetzt
- [ ] Optionaler automatischer Reset des Portfolio-Stop-Loss (Erholungs-Schwelle + Cooldown-Zeit, z.B. "erst wieder aktiv, wenn Kurs X% über Trigger-Niveau UND mindestens Y Stunden seit Trigger vergangen"): bewusst noch **nicht** implementiert. Aktueller Default ist ein reiner manueller Reset (siehe `dca_bot/reset_stop_loss.py`), um Whipsaw-Effekte (wiederholtes Neu-Einsteigen bei kurzen Erholungen knapp über der Schwelle, gefolgt von erneutem Fall) zu vermeiden. Falls das zu unpraktisch wird, könnte diese Erweiterung optional (per Config-Flag) nachgerüstet werden.
- [x] Monitoring & Benachrichtigungen (Telegram) – `dca_bot/notifier.py` sendet optional (nur wenn `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` gesetzt sind) bei jedem Kaufzyklus, Stop-Loss-Trigger, Notaus, unerwarteten Fehlern und einmal täglich als Zusammenfassung; Fehler beim Senden legen den Bot nie lahm (siehe README Abschnitt 7). Fertig gebaut und am 10.09.2026 auf dem Desktop-PC verifiziert (Dry-Run-Livetest mit echten Telegram-Nachrichten für Kauf, Stop-Loss und Notaus, jeweils per isoliertem Fake-Client-Test bestätigt). Dabei eine echte Prüfreihenfolge-Lücke in `strategy.py` gefunden und behoben: Der Stop-Loss wurde vor dem Fix erst NACH dem Tageslimit-Check geprüft, wodurch er an Tagen mit bereits ausgeschöpftem Tageslimit gar nicht mehr ausgewertet wurde (kein zusätzliches Geld-Risiko, da ohnehin nicht gekauft worden wäre, aber verzögerte/ausbleibende Stop-Loss-Benachrichtigung). Jetzt wird der Stop-Loss vor dem Tageslimit geprüft und greift unabhängig davon in jedem Zyklus.
- [ ] **Übertragung auf den Laptop zurückgestellt:** Die Telegram-Integration inkl. Bugfix liegt aktuell nur auf dem Desktop-PC (committet, noch nicht gepusht/übertragen). Auf dem Laptop läuft seit dem 09./10.09.2026 ein mehrtägiger 24h-Intervall-Test; um den nicht zu unterbrechen, wird die Telegram-Integration erst nach dessen Abschluss (Samstag, 12.09.2026, 18:10 Uhr) auf den Laptop übertragen.
- [x] **DCA-Bot 3-Tage-Stabilitätstest auf dem Laptop abgeschlossen** – Zeitraum 09.09.2026 17:57 Uhr bis 11.09.2026 16:54 Uhr, Laufzeit 1 Tag 22h58min von geplanten 3 Tagen (vorzeitig per Notaus beendet, nicht durch einen Fehler). Echtes Trading auf dem Testnet (`DCA_BOT_ENABLE_TRADING=true`), 24h-Intervall: 2 erfolgreiche Käufe (09.09. @ 78.620,79, 10.09. @ 77.209,97, je 15 USDT), keine einzige Fehler-/Exception-Zeile im gesamten Log, sauberer Notaus-Stopp ohne Datenverlust. Vollständiges Log dauerhaft archiviert unter `docs/test-reports/2026-09-09_dca-3tage-stabilitaetstest.log` (nicht in `logs/`, da dieser Ordner per `.gitignore` ausgeschlossen ist und durch künftige Bot-Läufe überschrieben würde; `.gitignore` um eine gezielte Ausnahme `!docs/**/*.log` ergänzt, damit archivierte Logs trotz der globalen `*.log`-Regel eingecheckt werden können).
- [x] **Zweite, eigenständige Strategie: Spot-Grid-Trading-Bot** (Stufe 2 aus dem Umsetzungsfahrplan in Abschnitt 5) – `dca_bot/main_grid.py`, `grid_config.py`, `grid_risk.py`, `grid_strategy.py`, `reset_grid_stop_loss.py`. Komplett eigenständig vom DCA-Bot: eigenes Trade-Ledger (`data/grid_positions.json`), eigener Notaus (`STOP_GRID`/`GRID_BOT_HALT`), eigener Trendbruch-Stop-Loss (latched, manueller Reset – gleiche Whipsaw-Begründung wie beim DCA-Stop-Loss), eigene Telegram-Nachrichten (`[GRID-KAUF]`, `[GRID-VERKAUF]` inkl. realisiertem PnL, `[GRID-STOP-LOSS]`, `[GRID-NOTAUS]`). Positions-Zuordnung: jede Kaufposition speichert ihre eigene Grid-Stufe und ihr individuelles Verkaufsziel (nächsthöhere Stufe) – Verkäufe sind dadurch immer eindeutig einer Kaufstufe zugeordnet. Beim Implementieren zwei echte Designfehler im ersten Entwurf gefunden und vor Fertigstellung behoben (durch selbst geschriebene Tests aufgedeckt, nicht durch Review): (1) ein naiver "aktueller Preis vs. Stufe"-Vergleich hätte bei einem Kaltstart mitten im Grid sofort alle Stufen oberhalb des Startpreises gleichzeitig gekauft statt nur die tatsächlich durchquerten – behoben durch Crossing-Erkennung gegen den zuletzt beobachteten Preis; (2) an der Intervallgrenze wurde die alte Referenzstufe fälschlich doppelt gezählt – durch ein halb-offenes Intervall behoben. Nebenbei zwei kleine, rein additive Änderungen an gemeinsam genutzten Dateien: `KillSwitch` in `risk.py` akzeptiert jetzt einen konfigurierbaren Env-Var-Namen (Default weiterhin `DCA_BOT_HALT`, damit `GRID_BOT_HALT` nicht versehentlich auch den DCA-Bot stoppt), und `binance_client.py` hat jetzt zusätzlich `place_market_sell()`. DCA-Bot-Regressionstest nach beiden Änderungen bestanden. Grid-Dry-Run am 10.09.2026 auf dem Desktop gestartet (zunächst reguläre Preisspanne 68k–88k, dann für einen schnelleren Beobachtungstest temporär auf eine enge ±0,5%-Spanne mit 0,1%-Abstand verengt) – noch keine reale Kursbewegung groß genug für einen ersten Kauf/Verkauf beobachtet, Log-Watcher läuft im Hintergrund weiter.
  - **Backtesting-Skript nachgerüstet** (`dca_bot/grid_backtest.py`, 12.09.2026) – bis dahin fehlte das im Gegensatz zu DCA/Trend. Um Backtest-Live-Abweichungen zu vermeiden (gleiches Prinzip wie bei `trend_signals.py`), wurde die bis dahin inline in `grid_strategy.py`/`grid_risk.py` verstreute Entscheidungslogik zuerst in ein neues, zustandsloses Modul `grid_signals.py` extrahiert (`compute_grid_levels`, `find_triggered_buy_levels`, `is_sell_target_hit`, `is_trend_break_stop_loss_hit`) – Live-Code und Backtest rufen jetzt exakt dieselben Funktionen auf, keine Doppelimplementierung. Kerzenauflösung bewusst 1h statt 1d, da der Live-Bot alle 5 Minuten prüft und Tageskerzen die meisten Grid-Durchquerungen unsichtbar gemacht hätten.
  - **Skalen-Mismatch entdeckt und transparent gemacht** (vor Abschluss dem Nutzer gemeldet, nicht stillschweigend übernommen): Anders als bei DCA/Trend sind die Grid-Parameter `GRID_LOWER_LIMIT`/`GRID_UPPER_LIMIT` kein skaleninvarianter Wert, sondern ein absoluter USD-Preisbereich, der an das heutige (2026er) BTC-Kursniveau gekoppelt ist. Gegen die drei Standard-Testzeiträume (2021–2023, BTC damals deutlich niedriger) getestet, hätte die unveränderte Live-Spanne (70.000–90.000) in JEDEM Zeitraum sofort außerhalb gelegen → 0 Trades, sofortiger Trendbruch-Stop-Loss. Das literale Ergebnis wird trotzdem angezeigt (reales, meldenswertes Faktum: die heutige Config hätte damals nie gegriffen), zusätzlich läuft standardmäßig ein klar als "ANALYSE, NICHT Live-Verhalten" gekennzeichneter zweiter Modus, der die Spanne symmetrisch um den tatsächlichen Startpreis der jeweiligen Periode skaliert (gleiches Breiten-Verhältnis/Abstand wie live) – analog zum Aufsetzen des echten Live-Grids "symmetrisch um den aktuellen Preis".
  - **Backtest-Ergebnisse** (Live-Defaults: 70.000–90.000, Abstand 1,5%, 15 USDT/Stufe, Stop-Loss-Puffer 15%, Gebühr 0,1%/Seite) – literal: in allen drei Zeiträumen 0 Trades, sofortiger Trendbruch-Stop-Loss (Spanne lag historisch nie im Kurs). ANALYSE-Modus (Spanne auf Periodenstart skaliert): 2022 Bärenmarkt 25 Trades, +8,90 realisiert, aber 1 am Ende offene Position mit −9,69 unrealisiert und Stop-Loss ausgelöst (Trendbruch-Risiko bestätigt trotz Schutzmechanismus); 2023 Erholung nur 5 Trades, +1,61 realisiert, keine offene Position (wenig Gelegenheit für Käufe im Aufwärtstrend); 2021 Seitwärts/Konsolidierung 109 Trades, +47,22 realisiert, keine offene Position am Ende – das beste Ergebnis der drei, deckt sich mit der Recherche (Chen/Chen/Jang: Grid funktioniert am besten in Seitwärtsmärkten, Erwartungswert vor Gebühren mathematisch null).
- [x] **Dritte, eigenständige Strategie: Trend-Following-Bot** (Stufe 3 aus dem Umsetzungsfahrplan in Abschnitt 5 – "Alpha-Strategie") – `dca_bot/main_trend.py`, `trend_config.py`, `trend_signals.py`, `trend_risk.py`, `trend_strategy.py`, `trend_backtest.py`, `reset_trend_stop_loss.py`. EMA-Crossover (Default 20/50 Tage) auf Tageskerzen, long-only, mit Trendstärke-Filter (Mindestabstand der EMAs, Default 1,0% – bewusst statt ADX gewählt: einfacher und robuster korrekt zu implementieren, siehe Modul-Docstring in `trend_signals.py`) und fixem Stop-Loss pro Trade (Default 10%, latched wie bei DCA/Grid). Backtest UND Live-Strategie nutzen exakt dieselbe Entscheidungslogik (`trend_signals.py`), um zu verhindern, dass beide unbemerkt auseinanderlaufen.
  - **Backtest vor dem ersten Dry-Run** (wie gefordert) über drei historische Marktphasen: 2022 Bärenmarkt (−15,75% Strategie vs. −65,20% Buy&Hold – deutlich weniger Verlust), 2023 Erholung (+13,14% realisiert vs. +153,60% Buy&Hold – erhebliche Unterperformance), 2021 Seitwärts Jun–Sep (0 geschlossene Trades, aber 1 am Periodenende noch offene Position, unrealisiert +1,77 – ursprünglich fälschlich als "0 Aktivität" berichtet, siehe Bugfix unten). Parameter waren vor dem ersten Lauf fixiert (Literatur-Standardwerte, nicht gegen diese Zeiträume optimiert) und wurden nicht nachjustiert – Overfitting-Vorsicht gemäß Gort et al.
  - **Zusatz-Analyse** (nur zur Einordnung, NICHT das Live-Verhalten): ein simulierter periodischer manueller Stop-Loss-Reset (`--simulate-reset-after-days`) zeigt, dass der fehlende Reset einen erheblichen Teil der 2023-Unterperformance erklärt (mit 14-Tage-Reset: ~+55% statt ~+13% ggü. Positionsgröße, durch einen zusätzlichen Wiedereinstieg am 19.10.2023). Im Bärenmarkt 2022 ändert der Reset dagegen nichts – kein neues Fehlsignal, da der Trend durchgehend negativ blieb.
  - **Beim Backtesting selbst ein Report-Bug gefunden und behoben** (kein Fehler in der Handelslogik): Eine am Ende eines Testzeitraums noch offene Position wurde nicht in `Anzahl Trades`/`Gesamt-PnL` gezählt, wodurch aktive Perioden fälschlich wie "keine Aktivität" wirkten (siehe 2021-Seitwärts-Ergebnis oben) und die Reset-Analyse zunächst wirkungslos erschien. Jetzt wird eine am Ende offene Position separat und unrealisiert ausgewiesen.
  - Live-Strategie mit Fake-Client-Tests verifiziert: Einstieg bei bestätigtem Signal, kein Doppel-Einstieg, Ausstieg per Signal-Umkehr (separat getestet, ohne Stop-Loss-Interferenz), Stop-Loss-Exit mit Latch und Blockade neuer Einstiege bis manueller Reset, Notaus-Isolation (`TREND_BOT_HALT` betrifft nicht DCA/Grid).
  - Kurzer technischer Dry-Run-Check am 10.09.2026 auf dem Desktop erfolgreich: Start fehlerfrei, historische Tageskerzen korrekt geladen, EMA-Berechnung unabhängig gegengeprüft (EMA-20/EMA-50-Abstand 6,66 %, Richtung "up" bestätigt – deckungsgleich mit der Bot-Entscheidung), ein Dry-Run-Einstieg ausgelöst (kein echter Trade), sauber über den Notaus gestoppt. Kein tagelanger Dauerlauf gestartet, da ein echtes Signal auf Tageskerzen ohnehin mehrere Tage dauert.

## 6a. Plan für Samstag (nach Abschluss des Laptop-DCA-Tests, 12.09.2026, 18:10 Uhr)

Reihenfolge wichtig: Schritt 2 (Datei-Transfer) muss vor Schritt 3
(Grid-Bot starten) passieren, sonst startet der Grid-Bot fälschlich mit
leerem Zustand statt die bestehenden Positionen fortzusetzen. Schritte 1
und 4 sind davon unabhängig und können in beliebiger Reihenfolge erfolgen.

1. **DCA-Bot mit Telegram-Integration auf dem Laptop neu starten.**
   Sicherstellen, dass alle Commits vom Desktop nach GitHub gepusht
   wurden, dann auf dem Laptop `git pull` (bringt Telegram-Integration +
   den Stop-Loss/Tageslimit-Prüfreihenfolge-Fix). In der Laptop-`.env`
   `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` ergänzen (Teil von `.gitignore`,
   kommt nicht automatisch mit). Prüfen, dass `interval_hours` in
   `config.py` auf dem regulären Wert (24) steht, nicht mehr auf einem
   Test-Intervall. Starten mit `python -m dca_bot.main`.

2. **Zustand vom Desktop auf den Laptop übertragen – manuell, NICHT über
   Git.** Der Ordner `data/` steht in `.gitignore` und wird nicht
   synchronisiert. Insbesondere `data/grid_positions.json` (6 offene
   Grid-Positionen vom 10.09.2026, siehe oben) muss manuell kopiert
   werden (z.B. USB-Stick oder Cloud-Speicher) – sonst startet der
   Grid-Bot auf dem Laptop mit leerem Ledger statt die bestehenden
   Positionen weiterzuverfolgen. Optional auch `data/trend_ledger.json`
   (1 offene Dry-Run-Position aus dem Technik-Check vom 10.09.2026)
   mitübertragen, falls dort Kontinuität gewünscht ist – nicht zwingend,
   da es nur ein Testartefakt ohne echten Trade war.

3. **Grid-Bot auf dem Laptop fortsetzen.** Nach dem Datei-Transfer aus
   Schritt 2: `GRID_LOWER_LIMIT`/`GRID_UPPER_LIMIT`/`GRID_SPACING_PCT`/
   `GRID_INTERVAL_MINUTES` in der Laptop-`.env` auf die eigentlichen
   Ziel-Werte setzen (68000.0 / 88000.0 / 1.5 / 5) – **nicht** die auf dem
   Desktop nur für den kurzen Beobachtungstest verwendete enge Spanne
   (±0,5 %, 0,1 % Abstand, 2-Minuten-Intervall) übernehmen. Starten mit
   `python -m dca_bot.main_grid` – die 6 übertragenen offenen Positionen
   werden automatisch aus dem Ledger erkannt und weiterverfolgt.

4. **Trend-Following-Bot auf dem Laptop starten.** Mit den Backtest-
   Defaults (20/50 EMA, 1,0 % Filter, 10 % Stop-Loss), unverändert.
   Starten mit `python -m dca_bot.main_trend` – lädt die EMA-Historie
   beim Start automatisch aus echten historischen Kursdaten neu, dafür
   ist kein manueller Datei-Transfer nötig.

---

*Diese Datei dient als lebendes Projektdokument und sollte bei neuen Entscheidungen und Recherche-Ergebnissen aktualisiert werden.*

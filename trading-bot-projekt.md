# Trading-Bot-Projekt: Planung & Recherche

**Stand:** 25. September 2026
**Status:** Testnet-Betrieb, kein Live-Geld. Der Sicherheitsreview (K1–K5, W1–W18, Infrastruktur) ist seit dem 16.09. abgeschlossen. Der Homeserver läuft faktisch seit dem 16.09.2026 als vollständiges System, mit allen vier Bausteinen und aktivem Allocator-Opt-in für DCA und Trend. Der aktuelle Trading-Status dort wurde am 25.09.2026 verifiziert (siehe 6h). Der formale Cutover (VPS-Abschaltung, finaler Snapshot) bleibt für den 05.10.2026 geplant. Bis zum Vertragsende am 12.10. läuft der VPS isoliert weiter, ohne Allocator. Die Testphase ist auf ca. 2–3 Monate verlängert, also bis etwa Mitte November bis Mitte Dezember 2026. Seit dem Review sind mehrere Fund-und-Fix-Serien abgeschlossen: die Verbesserungsvorschläge (6i, 17.09.), die Dry-Run-Beträge (22.09.) und die Code-Überprüfung vom 25.09. (6g). Die technische Referenz zum aktuellen Stand steht in Abschnitt 7.

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

## 5a. Kapital-Allocator zwischen DCA und Trend-Following — BACKTEST ABGESCHLOSSEN

**Problem:** DCA ist für Seitwärts-/lineare Marktphasen gedacht und performt nachweislich schlecht bei starken, anhaltenden Trends.

**Umgesetzt (14.09.2026):** Stufenloser Kapital-Umschalter (Allocator) zwischen DCA-Bot und Trend-Following-Bot – `dca_bot/allocator_config.py`, `allocator_signals.py`, `allocator.py`, `main_allocator.py`, `allocator_backtest.py`. Grid-Bot bleibt bewusst unberührt (hat bereits einen eigenen Trendbruch-Stop-Loss). Läuft als vierter, komplett eigenständiger Prozess (eigener Zustand `data/allocator_state.json`, eigener Notaus `STOP_ALLOCATOR`/`ALLOCATOR_HALT`) und platziert selbst nie Orders.

**Architektur:**
- **Trendstärke-Berechnung:** wiederverwendet `TrendSignalGenerator` aus `trend_signals.py` (mit `min_gap_pct=0`, da die dortige Bestätigungslogik für binäre Ein-/Ausstiegsentscheidungen gedacht ist, der Allocator aber den rohen, kontinuierlichen EMA-Abstand braucht). Nur eine bestätigte AUFWÄRTS-Richtung zählt als Stärke – Trend-Bot ist long-only, bei Abwärtstrend bekäme er ohnehin kein Kapital zugeteilt.
- **Lineare Interpolation** zwischen konfigurierbaren Ankerpunkten (Default: 0% EMA-Abstand → 0% Trend-Anteil, 3% → 100% Trend-Anteil) – bewusster Ausgangspunkt, kein empirisch hergeleiteter Optimalwert.
- **Whipsaw-Schutz durch EMA-Glättung der Zuteilung selbst** (gleiche Formel wie die Preis-EMAs in `trend_signals.py`, nur auf die Zuteilungs-Prozentzahl angewandt) – nur ein persistierter Wert nötig statt eines Verlaufsfensters.
- **Additive, standardmäßig deaktivierte Integration:** DCA und Trend bekommen je eine neue, leere Default-Config-Option. Nur wenn explizit gesetzt, skalieren sie den Betrag einer NEUEN Order; ist die Option nicht gesetzt, verhalten sich beide exakt wie zuvor. Offene Positionen bleiben in jedem Fall unangetastet. Unterhalb von 5 USDT wird ein Kauf/Einstieg übersprungen statt einer wirtschaftlich bedeutungslosen Mini-Order. Per Fake-Client-Tests verifiziert.

**Backtest-Ergebnisse** (dieselben drei Zeiträume wie DCA/Trend, mit investiertem Betrag, absolutem PnL und Rendite%):

| Zeitraum | Kombiniert: investiert / PnL / % | Isoliert DCA: investiert / PnL / % | Isoliert Trend: investiert / PnL / % | Buy & Hold |
|---|---|---|---|---|
| 2022 Bärenmarkt | 5.199,13 / −1.667,56 / −32,07 % | 5.460,00 / −1.821,46 / −33,36 % | 15,00 / −2,36 / −15,75 % | −65,20 % |
| 2023 Erholung | 2.136,57 / +1.370,90 / +64,16 % | 5.460,00 / **+2.844,11** / +52,09 % | 30,00 / +3,94 / +13,14 % | +153,60 % |
| 2021 Seitwärts | 1.062,69 / **+242,89** / +22,86 % | 1.830,00 / +198,74 / +10,86 % | 15,00 / +0,00 / +0,00 % | +19,43 % |

**Wichtige Korrektur nach expliziter Nachfrage vor dem Commit** (berechtigter Einwand: ist die Kapitalbasis beim Prozentvergleich überhaupt gleich groß?) – Antwort: **nein**. Kombiniert investiert deutlich weniger Gesamtkapital als Isoliert DCA (z.B. 2023: nur 39%): DCA wird täglich um den aktuellen Trend-Anteil reduziert, das freiwerdende Kapital fließt aber nicht automatisch zum Trend-Bot (der nur an eigenen, seltenen Einstiegstagen investiert) – exakt wie im Live-Design (additive, unabhängige Skalierung, kein gemeinsamer Kapitaltopf). Die Prozentwerte sind eine Rendite-pro-eingesetztem-Euro-Kennzahl je Strategie, **kein** Vergleich bei identischem Gesamtbudget.

Bei absolutem Gewinn zeigt sich dadurch ein gemischtes Bild: In 2021 und 2022 übertrifft Kombiniert Isoliert DCA trotz geringerem Kapitaleinsatz auch absolut. In 2023 erzielt Isoliert DCA trotz niedrigerer Prozentrendite den deutlich höheren absoluten Gewinn, weil dort mehr als doppelt so viel Kapital eingesetzt wird.

**Separat gegengeprüfter, weiterhin gültiger Befund:** Die DCA-Seite *innerhalb* der Kombination erzielt eine bessere Rendite pro eingesetztem Euro als isoliertes, uniformes DCA (2023: 64,55% statt 52,09%) – an Tagen mit hoher Trendstärke wird weniger DCA-Kapital eingesetzt, was den durchschnittlichen Einstandspreis des verbleibenden DCA-Kapitals verbessert.

**Geplanter Vergleichstest:** Sobald live getestet, zusätzlich auf dem Homeserver parallel zum isolierten Drei-Bot-System auf dem VPS laufen lassen (separater, neuer Testnet-Account nötig, damit keine gemeinsame Kontostand-Verfälschung entsteht).

**Modellwahl:** Sonnet 5 (high effort) für die Umsetzung. Opus 5 gezielt für den finalen Sicherheitsreview vor Echtgeld reserviert (siehe 6d).

**Status:** Backtest abgeschlossen und verifiziert. *(Aktualisiert 16.09.2026: Der frühere Satz „Noch kein Live-Dry-Run gestartet – offen für eine spätere Session" ist überholt. Der Dry-Run läuft seit dem 15.09. auf dem Homeserver, siehe „Allocator-Live-Dry-Run gestartet" in 6e; seit dem 16.09. ist dort zusätzlich das Opt-in für DCA und Trend aktiv, das vollständige Vier-Bausteine-System läuft also live im Testnet — siehe 6h.)*

## 5b. Geplantes Live-Kapital

**Grundsatzentscheidung (15.09.2026):** Gesamtbetrag **300€**, Architektur für den Live-Betrieb: **Allocator-Struktur** – DCA und Trend-Following bilden einen gemeinsamen, vom Allocator dynamisch verwalteten Kapitaltopf; Grid-Bot bleibt als eigenständiger, fester Topf davon getrennt (unverändert zur bisherigen Architektur, siehe 5a/10). Aufteilung zwischen den beiden Töpfen: **150€ Grid-Topf / 150€ Allocator-Topf (DCA+Trend gemeinsam)**.

**Bewusst noch offen:** Die konkreten `*_AMOUNT_PER_LEVEL`/`*_AMOUNT_PER_TRADE`-Werte sowie bei Grid die Preisspanne/`GRID_SPACING_PCT` werden NICHT jetzt schon festgelegt – hängen vom aktuellen BTC-Kurs zum Zeitpunkt des Live-Starts sowie von den Erkenntnissen aus dem noch bevorstehenden monatelangen Paper-Trade-Test (mit aktiviertem Allocator-Opt-in, geplant nach Abschluss der übrigen Live-Gang-Vorbereitungen aus 6d) ab. Positionsgrößen-Kalibrierung ist als eigener Schritt kurz vor dem tatsächlichen Live-Start eingeplant, nicht heute schon mit möglicherweise überholten Platzhalter-Werten.

*(Aktualisiert 17.09.2026: Für den **Grid-Bot** trifft dieser Satz nicht mehr zu — `GRID_AMOUNT_PER_LEVEL` ist auf dem Homeserver auf 9,38 € gesetzt, siehe „W16 umgesetzt" in 6g. Das ist ausdrücklich keine Kurs-Kalibrierung, sondern das Einhalten der 150-€-Obergrenze aus diesem Abschnitt, die ohnehin feststand: Der Grid-Bot hat bewusst kein Tageslimit, Stufenzahl × Betrag ist dort die einzige Bremse, und sie lag mit 240 € um 60 % daneben. Preisspanne und `GRID_SPACING_PCT` bleiben unverändert offen — sie hängen am Kursniveau und verschieben, anders als der Betrag, auch das Strategieprofil. Für `DCA_QUOTE_AMOUNT` und `TREND_AMOUNT_PER_TRADE` gilt der Satz vollständig weiter.)*

---

## 6. Nächste Schritte / Fortschritts-Log

- [x] Erst-Strategie festgelegt: DCA als Startpunkt
- [x] Binance-Testnet-Account eingerichtet
- [x] Projektgrundgerüst aufgesetzt (Python, `dca_bot`-Package)
- [x] DCA-Strategie + Backtesting-Skript implementiert (`backtest.py`), verifiziert an 2022 (Bärenmarkt) vs. 2023 (Bullenmarkt)
- [x] Risikomanagement-Logik (`dca_bot/risk.py`): Notaus (`KillSwitch`), persistentes Tageslimit (`TradeLedger`), Portfolio-Stop-Loss (latched, manueller Reset). Whipsaw-Vermeidung bewusster Grund für fehlenden Automatik-Reset (dokumentiert im Code).
- [ ] Optionaler automatischer Stop-Loss-Reset (Erholungs-Schwelle + Cooldown) – bewusst nicht implementiert, siehe Begründung oben. Könnte bei Bedarf als Config-Flag nachgerüstet werden.
- [x] **Monitoring & Benachrichtigungen (Telegram)** – `dca_bot/notifier.py`, sendet optional (nur wenn Token/Chat-ID gesetzt) bei Kaufzyklus, Stop-Loss, Notaus, Fehlern, tägliche Zusammenfassung. Fehler beim Senden legen den Bot nie lahm. Verifiziert am 10.09.2026 auf dem Desktop-PC (Dry-Run-Livetest, alle vier Nachrichtentypen bestätigt). Dabei echte Prüfreihenfolge-Lücke in `strategy.py` gefunden und behoben: Stop-Loss wurde vor dem Fix erst NACH dem Tageslimit-Check geprüft, wodurch er an Tagen mit ausgeschöpftem Tageslimit übersprungen wurde. Jetzt Preisabfrage/Stop-Loss-Check vor dem Tageslimit-Check.
- [x] **DCA-Bot 3-Tage-Stabilitätstest auf dem Laptop** – Zeitraum 09.09.2026 17:57 bis 11.09.2026 16:54 Uhr, Laufzeit 1 Tag 22h58min von geplanten 3 Tagen (vorzeitig per Notaus beendet, nicht durch Fehler). Echtes Trading (`DCA_BOT_ENABLE_TRADING=true`), 24h-Intervall: 2 erfolgreiche Käufe (09.09. @ 78.620,79, 10.09. @ 77.209,97, je 15 USDT), keine einzige Fehler-Zeile im gesamten Log. Vollständiges Log archiviert unter `docs/test-reports/2026-09-09_dca-3tage-stabilitaetstest.log` (`.gitignore` um `!docs/**/*.log` ergänzt).
- [x] **Zweite Strategie: Spot-Grid-Trading-Bot** – `dca_bot/main_grid.py`, `grid_config.py`, `grid_risk.py`, `grid_strategy.py`, `grid_signals.py`, `reset_grid_stop_loss.py`. Komplett eigenständig: eigenes Ledger (`data/grid_positions.json`), eigener Notaus (`GRID_BOT_HALT`), eigener Trendbruch-Stop-Loss (latched), eigene Telegram-Nachrichten. Positions-Zuordnung: jede Kaufposition kennt ihre Grid-Stufe und ihr individuelles Verkaufsziel.
  - Zwei echte Designfehler vor Fertigstellung selbst gefunden und behoben: (1) Kaltstart-Bug (naiver Preis-vs-Stufe-Vergleich hätte bei Start mitten im Grid alle Stufen oberhalb gleichzeitig gekauft) – behoben durch Crossing-Erkennung gegen zuletzt beobachteten Preis. (2) Intervallgrenzen-Fehler (Referenzstufe doppelt gezählt) – behoben durch halb-offenes Intervall.
  - Additive Änderungen an Shared-Code: `KillSwitch` akzeptiert konfigurierbaren Env-Var-Namen; `binance_client.py` erhielt `place_market_sell()`. DCA-Regressionstest danach bestanden.
  - **Backtesting nachgerüstet** (`grid_backtest.py`, 12.09.2026): Logik zuerst in zustandsloses `grid_signals.py` extrahiert (keine Doppelimplementierung, analog zu `trend_signals.py`). 1h-Kerzen (nicht Tageskerzen, da Live-Bot alle 5 Minuten prüft).
  - **Skalen-Mismatch entdeckt und transparent gemacht:** Grid-Preisspanne ist absoluter USD-Wert, an heutiges Kursniveau gekoppelt (anders als DCA/Trend, die skaleninvariant sind). Gegen 2021–2023-Daten getestet, hätte die Live-Spanne (70k–90k) 0 Trades ergeben. Literales Ergebnis UND ein zusätzlicher, klar gekennzeichneter Analyse-Modus (Spanne auf Periodenstart skaliert) werden beide gezeigt.
  - **Backtest-Ergebnisse** (Live-Defaults, Analyse-Modus): 2022 Bärenmarkt 25 Trades, +8,90 realisiert, aber 1 offene Position −9,69 unrealisiert bei ausgelöstem Stop-Loss; 2023 Erholung nur 5 Trades, +1,61; 2021 Seitwärts 109 Trades, +47,22 realisiert, glatt geschlossen – bestätigt Recherche (Grid funktioniert am besten in Seitwärtsmärkten).
  - Grid-Dry-Run-Test auf dem Desktop (10.09.2026): 6 echte Kaufpositionen aus tatsächlicher Marktbewegung entstanden (Crossing-Erkennung bei mehreren gleichzeitig durchquerten Stufen live bestätigt), noch kein Verkauf beobachtet, bevor auf den VPS umgezogen wurde.
- [x] **Dritte Strategie: Trend-Following-Bot** – `dca_bot/main_trend.py`, `trend_config.py`, `trend_signals.py`, `trend_risk.py`, `trend_strategy.py`, `trend_backtest.py`, `reset_trend_stop_loss.py`. EMA-Crossover (20/50 Tage), long-only, Trendstärke-Filter (Mindestabstand 1,0%, bewusst statt ADX – einfacher korrekt zu implementieren). Backtest und Live-Strategie nutzen exakt dieselbe Logik (`trend_signals.py`).
  - **Backtest-Ergebnisse:** 2022 Bärenmarkt −15,75% Strategie vs. −65,20% Buy&Hold (deutlich weniger Verlust); 2023 Erholung +13,14% vs. +153,60% Buy&Hold (erhebliche Unterperformance); 2021 Seitwärts 0 geschlossene Trades, 1 offene Position +1,77 unrealisiert am Ende.
  - **Zusatz-Analyse** (simulierter periodischer Reset): erklärt einen erheblichen Teil der 2023-Unterperformance (mit 14-Tage-Reset: ~+55% statt ~+13%, durch zusätzlichen Wiedereinstieg). Im Bärenmarkt 2022 ändert Reset nichts (kein neues Fehlsignal).
  - Beim Backtesting ein Report-Bug gefunden und behoben: eine am Ende offene Position wurde nicht in Anzahl Trades/PnL gezählt (wirkte fälschlich wie "keine Aktivität"). Jetzt separat als unrealisiert ausgewiesen.
  - Fake-Client-Tests: Einstieg bei bestätigtem Signal, kein Doppel-Einstieg, Ausstieg per Signal-Umkehr (separat getestet), Stop-Loss-Exit mit Latch, Notaus-Isolation bestätigt.
  - Technischer Dry-Run-Check (10.09.2026): EMA-Berechnung unabhängig gegengeprüft (6,66% Abstand, Richtung "up"), ein Dry-Run-Einstieg ausgelöst, sauber gestoppt.

---

## 6a. Übertragung auf den Laptop (12.09.2026) — ABGESCHLOSSEN

Nach Abschluss des Laptop-DCA-Tests: DCA-Bot mit Telegram-Integration neu gestartet, `data/`-Ordner (6 offene Grid-Positionen, 1 Trend-Testposition) manuell vom Desktop übertragen (nicht über Git, da `data/` in `.gitignore`), Grid- und Trend-Bot auf dem Laptop mit den korrekten Ziel-Werten gestartet (nicht die engen Test-Werte vom Desktop-Beobachtungstest).

## 6b. Umzug auf einen gemieteten VPS (13.09.2026) — ABGESCHLOSSEN

**Grund:** Laptop/PC können nicht wochenlang durchlaufen (Stromverbrauch, Praktikabilität). Für einen geplanten ca. einmonatigen Beobachtungszeitraum aller drei Strategien wurde ein Cloud-VPS gemietet.

**Anbieter:** Contabo Cloud VPS 4 (4 vCPU, 8 GB RAM, 100 GB SSD), Ubuntu 24.04, 1 Monat Laufzeit für 6,55€. Bestellt 12.09.2026, **Kündigung bereits zum 12.10.2026 gesetzt** (verhindert automatische Vertragsverlängerung; Server läuft bis dahin regulär weiter). Projektpfad `/root/crypto-bot`. *(Aktualisiert 25.09.2026: Hier stand bis dahin die öffentliche IP-Adresse des VPS im Klartext. Sie ist entfernt, weil das Repository öffentlich ist und die Adresse für dieses Dokument nicht gebraucht wird. In der Git-Historie bleibt sie erhalten; mit dem Vertragsende am 12.10. ist sie ohnehin gegenstandslos.)*

**Wichtiger Reminder:** Vor dem 12.10. müssen Logs und `data/`-Ordner final gesichert werden (siehe 6c), sonst gehen die Testergebnisse beim Vertragsende verloren.

**Absicherung:** SSH-Key-Login eingerichtet (Ed25519), Passwort-Authentifizierung deaktiviert (`PasswordAuthentication no` in `sshd_config`). *(Korrektur 16.09.2026: Für den VPS traf das faktisch NICHT zu — `sshd_config.d/50-cloud-init.conf` setzte `PasswordAuthentication yes` und wurde alphabetisch vor der Haupteinstellung wirksam. Die Lücke bestand vom 13.09. bis zum 16.09. und ist erst beim SSH-Check behoben worden, siehe „Infrastruktur-Härtung auf beiden Servern" in 6g. Bemerkenswert: Derselbe Cloud-Init-Fallstrick steht seit dem 15.09. in 6e — dort beim Homeserver-Setup bemerkt, aber nie rückwirkend auf den VPS angewendet.)* Zusätzlich ein separater, passphrasefreier Deploy-Key für Claude-Code-Automatisierung angelegt (getrennt vom Haupt-SSH-Key, der weiterhin für GitHub etc. mit Passphrase geschützt bleibt).

**Deployment:** Projekt von GitHub geklont (öffentliches Repo `EliasNein/crypto-bot`), `.env` und `data/`-Ordner manuell übertragen (`scp`, da beide über `.gitignore` ausgeschlossen sind). Alle drei Bots laufen als **systemd-Services** (`dca-bot`, `grid-bot`, `trend-bot`):
- Automatischer Start bei Server-Neustart (`enabled`)
- Automatischer Neustart bei Absturz (`Restart=on-failure`)
- Laufen unabhängig von aktiver SSH-Sitzung
- Nutzen die Projekt-`.venv`
- Notaus-Mechanismus (STOP-Dateien) und `systemctl stop` funktionieren nachweislich unabhängig voneinander (verifiziert durch Code-/Systemd-Semantik-Analyse statt riskantem Live-Test: `BotHalted` führt zu regulärem `break` und Exit-Code 0, `Restart=on-failure` reagiert nur auf Fehler-Exits; `systemctl stop` unterdrückt `Restart=` grundsätzlich bei administrativ angefordertem Stopp)

**Live-Konfiguration beim Start:**
- DCA-Bot: `DCA_BOT_ENABLE_TRADING=true` (echte Testnet-Orders, wie beim vorherigen erfolgreichen Laptop-Test) – erster echter Kauf sofort erfolgreich (15 USDT @ 76.952,01)
- Grid-Bot: Dry-Run, korrekte Ziel-Spanne (68.000–87.585, 18 Stufen)
- Trend-Bot: Dry-Run, Historie geladen

Eine Telegram-Nachricht scheiterte initial an einem transienten Verbindungsfehler – vom Notifier wie vorgesehen abgefangen (kein Crash), bestätigt die robuste Fehlerbehandlung.

## 6c. Plan für die kommenden Wochen (Testmonat auf dem VPS)

- Kein Dauerbeobachten nötig – gelegentliche Check-ins (SSH `journalctl -u <service> -f`, oder Telegram) reichen.
- **Zu erwartende Meilensteine, bevor der Test als "ausreichend" gilt:**
  - DCA: mehrere weitere Zyklen ohne Fehler (Basis: schon 2 Tage sauber auf dem Laptop verifiziert)
  - Grid: mindestens ein kompletter Kauf-Verkauf-Zyklus einer Position (bisher nur Käufe live beobachtet)
  - Trend-Following: mindestens ein echtes, bestätigtes Signal (kann laut Tageskerzen-Logik mehrere Tage dauern)
- **Snapshot-Strategie statt Live-Sync:** Keine automatische Synchronisierung einrichten. Stattdessen alle paar Tage bzw. an Meilensteinen `scp`-Snapshots von Logs und `data/`-Ordner auf den PC ziehen, zusätzlich zwingend **vor dem 12.10.** ein finaler Snapshot.
- **Vor dem 12.10. zu entscheiden:** Server verlängern (neue Bestellung) oder Umzug auf den Homeserver abschließen (siehe 6d).

## 6d. Plan für den Live-Gang nach dem Testmonat

Nutzer plant: nach Abschluss des VPS-Testmonats Umzug auf den eigenen Homeserver (TrueNAS, bereits eine Ubuntu-Server-VM für Cloudflare-Webseiten aktiv) für den Live-Betrieb mit echtem Kapital (100–300€, siehe 5b).

**Empfehlung: separate, eigene VM auf dem TrueNAS-Server** für die Bots (nicht die bestehende Webseiten-VM mitnutzen), um Isolation zu wahren – konsistent mit dem Trennungsprinzip zwischen den Bot-Strategien selbst. Einrichtung technisch nahezu identisch zum VPS-Setup (Ubuntu, Python, Git-Clone, systemd-Services), aber ohne laufende Kosten.

**Vor dem eigentlichen Live-Gang mit echtem Geld noch zu klären/umzusetzen:**
1. **Sicherheitsreview (Code + Infrastruktur) mit Claude Opus 5** – bewusst zurückgestellt bis kurz vor Live-Gang, jetzt zeitlich relevant *(Aktualisiert 25.09.2026: **erledigt.** Der Review fand am 15.09. statt, alle Punkte sind seit dem 16.09. abgearbeitet, siehe „Sicherheitsreview vollständig abgearbeitet“ in 6g. Unabhängig davon bleibt ein **abschließender** Review kurz vor dem tatsächlichen Live-Gang vorgesehen, siehe 6h.)*
2. **Echter, exchange-seitiger Stop-Loss** – im Code umgesetzt (siehe 6f), noch nicht deployed/live getestet *(Aktualisiert 25.09.2026: **deployed**, siehe „Was das für den Live-Gang heißt“ in 6g. Noch offen ist der Teil „live getestet“: Ein tatsächlich an der Börse gefüllter Stop-Loss ist bisher nicht dokumentiert, und genau diese Fälle braucht die Kalibrierung von `TREND_STOP_LIMIT_OFFSET_PCT`, siehe 6f und 6h.)*
3. Entscheidung zur Kapitalverteilung auf die Strategien (nach Auswertung der Testmonat-Ergebnisse, inkl. Allocator-System) *(Aktualisiert 25.09.2026: **teilweise entschieden, im Kern offen.** Festgelegt sind der Gesamtbetrag von 300 € und die Aufteilung 150 € Grid / 150 € Allocator-Topf (5b), beim Grid-Bot außerdem der Betrag pro Stufe (9,38 €, „W16 umgesetzt“ in 6g). Offen sind `DCA_QUOTE_AMOUNT`, `TREND_AMOUNT_PER_TRADE` sowie Preisspanne und Stufenabstand des Grids. Sie werden nach der Auswertung der auf 2–3 Monate verlängerten Testphase festgelegt, siehe 5b und 6h.)*
4. Home-Netzwerk-Absicherung prüfen (Router-Firewall, ggf. VPN-Zugriff statt offener Ports) *(Aktualisiert 25.09.2026: **erledigt.** Am 15.09. wurden die FritzBox-Portfreigaben geprüft, es gibt keine, siehe „Woche 1 abgeschlossen“ in 6e. Am 16.09. kam `ufw` auf dem Homeserver dazu, nur Port 22 aus dem lokalen Subnetz, siehe „Infrastruktur-Härtung auf beiden Servern“ in 6g.)*
5. Allocator-System (siehe 5a) fertig getestet und verifiziert – Backtest abgeschlossen, Live-Dry-Run steht noch aus, falls bis dahin nicht nachgeholt *(Aktualisiert 25.09.2026: Der Live-Dry-Run **läuft seit dem 15.09.** auf dem Homeserver (6e), seit dem 16.09. mit aktivem Opt-in für DCA und Trend (6h). „Fertig getestet und verifiziert“ ist damit Teil der laufenden Testphase und noch nicht abgeschlossen.)*

*(Aktualisiert 25.09.2026: Von dieser Liste sind die Punkte 1 und 4 erledigt. Offen sind Punkt 3 sowie die Teile von 2 und 5, die an Daten aus der laufenden Testphase hängen. Welche Vorbedingungen vor echtem Geld gelten, steht zusammengefasst in 6h, „Die Vorbedingungen für echtes Kapital ändern sich nicht“.)*

## 6e. Migrations-Timeline VPS → Homeserver (erstellt 14.09.2026)

**Ausgangslage:** VPS-Kündigung ist bereits zum 12.10.2026 gesetzt (hartes, unveränderliches Datum) – Migration wird deshalb vor dem Allocator-Live-Dry-Run priorisiert, da letzterer zeitlich flexibel ist und jederzeit in den nächsten Wochen starten kann.

**Grundsatzentscheidungen (14.09.2026):**
- **Keine Datenzusammenführung:** VPS- und Homeserver-Datensätze (Trade-Historie, Logs) bleiben dauerhaft getrennte Testreihen, kein Merge – sauberer Vergleich, konsistent mit dem Prinzip aus 5a (separate Accounts, damit sich Kontostände nicht gegenseitig verfälschen).
- **Allocator-Live-Dry-Run läuft auf dem Homeserver** (nicht auf dem VPS, wie ursprünglich am 14.09. geplant - am 15.09. bewusst geändert, da der Homeserver ohnehin der zukünftige dauerhafte Standort wird und eine spätere Migration des Allocators vom VPS erspart bleibt), zunächst weiterhin additiv/deaktiviert für DCA/Trend (kein `DCA_ALLOCATOR_STATE_FILE`/`TREND_ALLOCATOR_STATE_FILE` gesetzt), erst nur Berechnung/State-Datei live beobachten.

**Zeitplan:**

| Zeitraum | VPS | Homeserver |
|---|---|---|
| 14.–20.09. | DCA/Grid/Trend laufen weiter; Allocator-Dry-Run kann jederzeit dazugeschaltet werden | Neue, isolierte Ubuntu-Server-VM auf TrueNAS aufsetzen (getrennt von der bestehenden Cloudflare-Webseiten-VM); SSH-Key-Login, Passwort-Auth deaktivieren; Python/Git-Clone/venv/Requirements (1:1 wie VPS-Deployment); neuer, separater Testnet-API-Key; `data/`-Ordner bewusst NICHT vom VPS übernehmen (Parallelvergleich soll bei Null starten) |
| 21.–27.09. | wie oben, Snapshot-Rhythmus (siehe 6c) beibehalten | DCA/Grid/Trend als systemd-Services starten, eigener unabhängiger Datensatz; guter Zeitpunkt für Home-Netzwerk-Absicherung (Router-Firewall, VPN statt offener Ports – vorgezogen aus Punkt 4 der Live-Gang-Liste in 6d) |
| 28.09.–04.10. | Beobachtung, laufende Snapshots | Beobachtung, Vergleich VPS- vs. Homeserver-Verhalten (Meilensteine aus 6c gelten für beide) |
| 05.–11.10. | **Finaler Snapshot** (Logs + `data/` aller Bots, inkl. Allocator-Daten falls gestartet); Integritätsprüfung; sauberer Shutdown der Services per `systemctl stop` | wird primärer Standort (weicher Cutover-Zieltag: 05.10.) |
| 12.10. | Vertragsende (bereits gekündigt) | — |

**Puffer:** Ziel-Cutover 05.10., also ca. eine Woche Puffer vor dem harten 12.10.-Stichtag für unerwartete Probleme.

### Woche 1 abgeschlossen (15.09.2026)

Homeserver-VM aufgesetzt und alle drei Bots laufen sauber – Parallelbetrieb zum VPS kann ab jetzt starten.

- **VM:** `crypto_bot_vm` auf TrueNAS SCALE (2 vCPU, 4 GiB RAM, 30 GiB Disk, Ubuntu Server 26.04.1 LTS), eigene isolierte VM getrennt von der bestehenden Cloudflare-Webseiten-VM, statische IP `192.168.178.37` (per FritzBox-Reservierung), Hostname `trading-bot-server`, Linux-Benutzer `elias`
- **SSH:** dedizierter, passphrasegeschützter Ed25519-Key (`crypto_bot_vm`, separat vom Haupt-/Webserver-Key), `PasswordAuthentication no` gesetzt (Achtung: musste zusätzlich in `/etc/ssh/sshd_config.d/50-cloud-init.conf` deaktiviert werden, nicht nur in der Haupt-`sshd_config` – sonst überschreibt Cloud-Init die Einstellung)
- **Software:** Python 3, Git, venv, Projekt von `EliasNein/crypto-bot` geklont, Dependencies installiert
- **API-Key:** neuer, separater Binance-Testnet-Key (bewusst nicht der VPS-Key, für sauberen Parallelvergleich ohne Kontostand-Vermischung, siehe Grundsatzentscheidung oben)
- **Telegram:** bewusst derselbe Bot-Token/Chat-ID wie beim VPS wiederverwendet (reiner Benachrichtigungskanal, keine sicherheitsrelevante Trennung nötig, anders als bei den API-Keys)
- **systemd-Services:** `dca-bot`, `grid-bot`, `trend-bot` angelegt, aktiviert (`enable`) und gestartet – alle drei laufen fehlerfrei im Dry-Run (`*_BOT_ENABLE_TRADING=false`), verifiziert per `journalctl`: DCA-Kauf simuliert, Grid mit 17 Stufen initialisiert, Trend-Historie geladen
- **Netzwerk-Absicherung:** FritzBox-Portfreigaben geprüft – keine Einträge vorhanden, kein VPN nötig (nur lokaler Zugriff gewünscht), Isolation nach außen bereits gegeben

*(Korrektur 25.09.2026: Der Dry-Run-Zustand aus dem Punkt „systemd-Services“ hielt bei DCA und Grid nicht lange. Laut Ledger gab es auf dem Homeserver schon am selben Tag echte Trades, DCA um 12:53:03 UTC und Grid um 13:38:07 UTC. Beide wurden also noch am 15.09. auf `*_BOT_ENABLE_TRADING=true` umgestellt, dokumentiert war das nicht. Der Trend-Bot lief zu dieser Zeit noch im Dry-Run. Details siehe „Umstellung auf echte Orders auf dem Homeserver“ in 6h.)*

### Allocator-Live-Dry-Run gestartet (15.09.2026)

Kapital-Allocator läuft jetzt live auf der Homeserver-VM als vierter, komplett isolierter systemd-Service (`allocator.service`, gleiches Muster wie die drei Bot-Services).

- **Konfiguration:** Alle `ALLOCATOR_*`-Variablen aus `.env.example` übernommen (Default-Werte, keine Anpassung nötig). `DCA_ALLOCATOR_STATE_FILE`/`TREND_ALLOCATOR_STATE_FILE` bestätigt auskommentiert (inaktiv) - kein Opt-in, DCA und Trend bekommen vom Allocator nichts mit, laufen unverändert weiter.
- **Verifiziert per Log und State-Datei:** Historie geladen (81 Tageskerzen), Trendstärke-Berechnung läuft fehlerfrei im 60-Minuten-Zyklus. Erster Messwert: Trendstärke 5,25 % (Richtung "up", über dem `ALLOCATOR_FULL_ANCHOR_PCT`-Anker von 3,0 %) → berechneter Trend-Anteil 100 %, DCA-Anteil 0 % (`data/allocator_state.json` bestätigt: `trend_fraction: 1.0`, `gap_pct: 5.25`). Rein beobachtend, keine Wirkung auf DCA/Trend, da Opt-in weiterhin deaktiviert.
- **Läuft ausschließlich auf dem Homeserver**, nicht auf dem VPS (siehe korrigierte Grundsatzentscheidung oben).

## 6f. Trend-Bot: Echter, exchange-seitiger Stop-Loss (15.09.2026)

Umgesetzt (nur lokaler Code, noch nicht deployed/committet zum Zeitpunkt dieses Eintrags): der Trend-Bot platziert jetzt bei jedem Entry zusätzlich zur software-internen Überwachung eine echte `STOP_LOSS_LIMIT`-Order direkt an der Börse (`binance_client.place_stop_loss_limit_sell`), siehe README.md Abschnitt 9.5 für die vollständige Dokumentation *(seit 25.09.2026: Abschnitt 7.3 dieses Dokuments)*. Schützt eine offene Position auch bei Ausfall des Bot-Prozesses (Strom-/Internetausfall zuhause) – der bisherige software-interne Stop-Loss wirkt nur, solange der Prozess läuft.

**Race Condition selbst gefunden und behoben** (vor dem Commit, auf gezielte Nachfrage geprüft): zwischen dem letzten Order-Status-Check und dem Stornieren der Stop-Order (vor einem Signal-Exit oder internen Stop-Loss-Exit) kann sich die Order an der Börse tatsächlich füllen. Der Bot verlässt sich dafür nicht auf den Binance-Fehlercode, sondern fragt bei einem fehlgeschlagenen Cancel den Order-Status erneut ab (Ground Truth statt Code-Interpretation) – ist sie `FILLED`, wird die Position korrekt geschlossen statt ein zweites Mal verkauft zu werden; bleibt der Status unklar (echter transienter Fehler), verkauft der Bot bewusst nicht und markiert auch nichts als geschlossen (Zähler `uncertain_cycles`, ab 3 Zyklen in Folge Telegram-Warnung).

**Fill-Analyse-Logging:** jeder Exit über eine gefüllte Exchange-Stop-Order loggt eine eigene `[STOP-FILL-ANALYSE]`-Zeile (Limit-Preis, tatsächlicher Füllpreis, Differenz in %) – sammelt automatisch reale Daten über die Paper-Trade-Phase, ohne manuelles Nachhalten.

**Backtest-Erweiterung** (`trend_backtest.py --analyze-stop-limit-reliability`): Näherung basierend auf Tageskerzen-Low (kein Orderbuch/Intraday-Daten verfügbar), geprüft für Offsets 0,5/1,0/2,0 %. Ergebnis über die drei Referenz-Zeiträume: nur **2 simulierte Stop-Loss-Exits insgesamt** (2022: 1, 2023: 1, 2021: 0), bei beiden wäre die Order laut Näherung am selben Tag gefüllt worden, für alle drei Offsets – 0 ungefüllte Fälle, 0,00 Zusatzverlust.

**Wichtige Einordnung, bewusst nicht als Bestätigung überinterpretiert:** die Stichprobe (n=2) ist zu klein, um daraus verlässlich abzuleiten, dass 0,5 % Offset ausreicht. `TREND_STOP_LIMIT_OFFSET_PCT` bleibt vorerst beim Default **0,5 %** – **wird während der monatelangen Paper-Trade-Phase anhand realer Fill-Daten (siehe Fill-Analyse-Logging oben) überprüft, bevor der Wert für den Live-Gang final bestätigt wird.**

**Tests:** `tests/test_trend_stop_loss.py`, erster committeter Test im Projekt (bewusste Abweichung vom bisherigen Ad-hoc-Skript-Muster, siehe Docstring dort – erster Code, der eine echte Order platzieren kann, die ohne Bot-Zutun Geld bewegt).

## 6g. Sicherheitsreview-Fixes (ab 15.09.2026)

Laufendes Log der Behebung der im Sicherheitsreview (Claude Opus 5, 15.09.2026) gefundenen Punkte. Vollständiger Befund als Referenz: siehe Review-Ausgabe im Chat-Verlauf.

### K5: Telegram-Bot-Token-Leak behoben (15.09.2026)

Drei Leak-Pfade in notifier.py gefunden und behoben: `logger.exception()` mit vollständigem Traceback, `raise_for_status()`-Fehlermeldung mit eingebetteter URL, sowie latentes urllib3-DEBUG-Logging. Alle drei geschlossen, 6 neue Tests inkl. Negativ-Kontrolle gegen den alten Code (3 von 6 Tests fallen gegen den alten Code korrekt um). Geprüft: Git-Historie und bisher committete Logs enthalten keinen geleakten Token. Homeserver-Logs geprüft (`grep "api.telegram.org" logs/*.log`): 2 Treffer, beide mit dem alten `.env.example`-Platzhaltertext aus der Zeit vor dem Eintragen des echten Tokens, kein echter Leak. **VPS-Prüfung nachgeholt und abgeschlossen (16.09.2026):** `grep -c "api.telegram.org" logs/*.log` auf dem VPS ergab **0 Treffer** in allen drei Log-Dateien (`dca_bot.log`, `grid_bot.log`, `trend_bot.log`) – auch der in 6b dokumentierte reale Telegram-Sendefehler hat also keinen Token hinterlassen. Kein Leak, keine Maßnahme nötig. Der Suchbegriff ist bewusst der API-Host: jede der drei früheren Leak-Varianten hätte die vollständige URL samt Token ins Log geschrieben und damit zwingend `api.telegram.org` enthalten. Aussagekraft bezieht sich auf den Inhalt dieser drei Dateien zum Prüfzeitpunkt. **Damit ist K5 vollständig abgeschlossen.**

### K1 + K4: Verkaufsseite von Grid und Trend abgesichert (16.09.2026)

Gemeinsam behoben, da beide denselben Ursprung haben: `place_market_sell()` gibt in ZWEI völlig verschiedenen Fällen `None` zurück - im Dry-Run **und** bei einem echten API-Fehler. Auf der Kaufseite wurde das immer schon unterschieden (`strategy.py`, `grid_strategy.py`, `trend_strategy.py`), auf der Verkaufsseite in beiden Bots nicht.

- **K1 (fehlgeschlagener echter Verkauf wurde als Erfolg verbucht):** Der Code rechnete bei `None` einen fiktiven Erlös aus `quantity * price` aus und markierte die Position trotzdem als geschlossen - die Assets lagen danach weiter an der Börse, das Ledger behauptete das Gegenteil. Jetzt: kein erfundener Erlös, Position bleibt **offen**, klare `[GRID-VERKAUF-FEHLGESCHLAGEN]`- bzw. `[TREND-VERKAUF-FEHLGESCHLAGEN]`-Warnung plus Telegram, automatischer erneuter Versuch im nächsten Zyklus.
- **K4 (Dry-Run-Positionen wären beim Umschalten auf Live real verkauft worden):** Keine der beiden Verkaufsfunktionen prüfte das `dry_run`-Flag des Ledger-Eintrags. Jetzt wird es vor jedem Verkauf geprüft; für eine Dry-Run-Position wird `place_market_sell()` **gar nicht erst aufgerufen** (die Methode prüft nur `config.trading_enabled`, ein Aufruf wäre also eine echte Order für nie gekaufte Assets). Der Verkauf bleibt simuliert und wird explizit als `[DRY-RUN-POSITION]` geloggt - sichtbar bewusst simuliert, statt zufällig funktionierend.

**Trend-spezifische Zusatzarbeit:** `_resolve_stop_order_before_close()` storniert die exchange-seitige Stop-Order, BEVOR verkauft wird. Schlug der Verkauf danach fehl, wäre die weiterhin offene Position komplett ungeschützt gewesen. Der Bot platziert deshalb sofort eine **neue** Stop-Loss-Order mit derselben Schwelle und hinterlegt sie im Ledger (neue Methode `TrendLedger.set_stop_loss_order`). Scheitert auch das, wird der doppelt kritische Zustand als `ERROR` + Telegram gemeldet und die stornierte Order-ID aus dem Ledger entfernt, statt eine tote Order als Absicherung auszuweisen.

**Warum es bei Grid diese Zusatzarbeit nicht braucht** (explizit geprüft, nicht übersehen): Der Grid-Bot platziert nie eine exchange-seitige Stop-Order und storniert vor einem Verkauf entsprechend auch keine. Eine Grid-Position ist nach einem fehlgeschlagenen Verkauf exakt so abgesichert wie eine Sekunde davor - es wurde nichts abgebaut. Der 5-Minuten-Zyklus wiederholt den Verkauf von selbst. Eine Stop-Order-Mechanik für Grid nachzurüsten wäre eine eigene Architekturentscheidung (18 parallele Orders, Kapitalbindung, Reconciliation für n Positionen) und bewusst nicht Teil dieses Fixes.

**Über die Vorgabe hinaus ergänzt:** Fehlt einem Ledger-Eintrag das `dry_run`-Feld komplett (praktisch nur durch manuelles Editieren möglich), wird der Modus **nicht geraten** - beide Bots verweigern dann jeden Verkaufsversuch und loggen `[GRID-POSITION-UNKLAR]`/`[TREND-POSITION-UNKLAR]`. Auf "echt" zu raten hieße, nie gekaufte Assets verkaufen zu wollen; auf "Dry-Run" zu raten hieße, eine echte Position mit erfundenem Erlös zu schließen. Außerdem meldet Grid einen dauerhaft fehlschlagenden Verkauf pro Position nur einmal je Prozesslauf per Telegram (sonst im 5-Minuten-Takt) - ins Log geht weiterhin jeder Fehlschlag.

**Auflösung des konkreten Homeserver-Zustands:** Die dort offenen Positionen (6 Grid, 1 Trend) sind laut Ledger **alle** `dry_run: true`. Nach dem Fix kann für sie kein Codepfad mehr eine echte Verkaufsorder auslösen, unabhängig von `*_BOT_ENABLE_TRADING` - ein Bereinigen der Ledger-Dateien ist deshalb nicht nötig, das Wiederfreischalten per Notaus-Entfernung ist ungefährlich. Neu dafür: `python -m dca_bot.audit_positions` listet alle offenen Positionen beider Bots mit Dry-Run-Status auf, rein lesend, ohne API-Keys (siehe README Abschnitt 11; seit 25.09.2026 README 8.1 und Abschnitt 7.5 dieses Dokuments). Gegen die echten Ledger-Dateien verifiziert.

*(Korrektur 25.09.2026: Die Zahlen „6 Grid, 1 Trend“ beziehen sich nicht auf den Homeserver, sondern auf den **VPS**. Dorthin ging der Bestand aus der Übertragung vom Desktop über den Laptop (6a, 6b). Der Homeserver ist laut 6e mit leerem `data/`-Ordner gestartet, und die Prüfung seiner Ledger am 25.09.2026 ergab zu keinem geprüften Zeitpunkt Dry-Run-Grid-Positionen: Das Grid-Ledger dort ist durchgehend echt. Eine Dry-Run-Trend-Position gab es allerdings auch auf dem Homeserver, eröffnet am 15.09.2026 um 12:19:01 UTC. Die Aussage über die Wirkung des Fixes gilt für die VPS-Positionen unverändert. Details siehe „Umstellung auf echte Orders auf dem Homeserver“ in 6h.)*

**Tests:** 16 neue Tests - `tests/test_grid_sell_safety.py` (7, eigener Fake-Client; Dateiname bewusst nicht `test_grid_stop_loss.py`, da der Grid-Stop-Loss der Trendbruch-KAUF-Blocker und ein völlig anderer Mechanismus ist) und eine neue Klasse `TrendSellSafetyTestCase` in `tests/test_trend_stop_loss.py` (9, inkl. Neuplatzierung der Stop-Order nach fehlgeschlagenem Verkauf und dem doppelten Fehlerfall). Die geteilte Testumgebung wurde dafür in eine Basisklasse ohne eigene Testmethoden extrahiert. Gesamtstand: 36 Tests, alle grün.

### Folgefund aus K1: Position konnte dauerhaft ohne Börsen-Absicherung bleiben (16.09.2026)

Auf Nachfrage nach dem K1/K4-Commit geprüft und bestätigt: es gab einen Zustand, aus dem der Trend-Bot allein nicht mehr herausfand, ohne dass es jemals eskalierte.

**Der Befund:** Eine offene, echte Position hat nur dann eine exchange-seitige Stop-Loss-Order, wenn deren Platzierung beim Entry geklappt hat. Schlug sie fehl, gab es **keinen** Codepfad, der das je nachgeholt hätte – `_open_position()` platziert nur beim Einstieg, `_handle_failed_real_sell()` (neu aus K1) nur aus einem Exit-Versuch heraus. Ein erneuter Exit-Versuch passiert aber nur, solange `is_stop_loss_hit()` oder ein bestätigtes Abwärtssignal gilt. Dreht `confirmed_direction` zurück auf "up", entfällt der Exit-Grund – die Position lief dann unbegrenzt weiter, nur noch software-intern abgesichert (also nur, solange der Prozess läuft), ohne Schutz bei Bot-/Strom-/Internetausfall. Nach der einmaligen Fehlermeldung kam nichts mehr: kein Zähler, keine Wiederholungswarnung.

Zwei Wege führten hinein: (a) die Stop-Order scheiterte schon beim Entry – diese Lücke bestand seit 6f, also unabhängig von K1; (b) nach einem fehlgeschlagenen Verkauf scheiterte auch die sofortige Neuplatzierung – dieser Weg kam mit K1 dazu.

**Umgesetzt:** Neue Methode `_ensure_stop_loss_protection()` in `trend_strategy.py`, aufgerufen in jedem Zyklus, in dem die Position **nicht** geschlossen wird, sowie im Reconciliation-Schritt beim Bot-Start. Fehlt die `stop_loss_order_id` einer offenen, echten Position, wird eine neue Order mit derselben Schwelle (`entry_price`) platziert und im Ledger hinterlegt (`[TREND-ABSICHERUNG-WIEDERHERGESTELLT]`). Scheitert das, zählt das neue Ledger-Feld `unprotected_cycles` hoch; ab `UNPROTECTED_CYCLES_WARNING_THRESHOLD` (3, wie bei `uncertain_cycles`) gibt es eine `[TREND-WARNUNG]` per Telegram, dazu eine Entwarnung, sobald die Absicherung wieder steht (nur, wenn zuvor gewarnt wurde – ein einzelner Fehlschlag, der sich sofort einrenkt, bleibt reine Log-Sache).

**Bewusst erst NACH den Exit-Entscheidungen des Zyklus** statt am Zyklusanfang: wird die Position ohnehin gerade geschlossen, wäre die neue Order sofort wieder zu stornieren – und bei ausgelöstem Stop-Loss läge der Preis bereits unter der Stop-Schwelle, die Börse würde eine solche Order mit "would immediately trigger" zurückweisen und den Zähler fälschlich hochlaufen lassen. Im relevanten Fall (Position überlebt den Zyklus) ist das Ergebnis identisch.

**Nebeneffekt, der einen alten Kommentar einlöst:** Die Warnung in `_open_position()` versprach bisher "bis zum nächsten erfolgreichen Versuch" – einen solchen Versuch gab es im Code nirgends, der Text beschrieb nie implementiertes Verhalten. Mit diesem Fix stimmt er zum ersten Mal; Kommentar und Log-Zeile entsprechend präzisiert.

**Tests:** 10 neue in der Klasse `TrendStopLossProtectionTestCase` (`tests/test_trend_stop_loss.py`) – Wiederherstellung im Zyklus und beim Neustart, Zähler-Eskalation genau ab der Schwelle, Reset plus Entwarnung nach erfolgreicher Reparatur, der konkrete Weg über einen fehlgeschlagenen Verkauf mit anschließend entfallenem Exit-Grund, sowie die Abgrenzungen (bereits abgesicherte Position wird nicht angefasst, Dry-Run-Position und Dry-Run-Modus bekommen nie eine echte Order). Gesamtstand: 46 Tests, alle grün. `audit_positions.py` weist `unprotected_cycles` jetzt mit aus.

### K3: Gebühren und echte Handelsregeln (16.09.2026)

Zwei zusammenhängende Befunde, die beide erst im Echtgeld-Betrieb zugeschlagen hätten – auf dem Testnet waren sie unsichtbar, weil `commission` dort bei allen bisherigen Fills `0.00000000` war.

**Gebühr wurde nicht abgezogen:** Binance zieht die Handelsgebühr bei einem Spot-Kauf vom erhaltenen Base-Asset ab (bei BTCUSDT in BTC), sichtbar in `fills[].commission`/`commissionAsset`. Gespeichert wurde bisher `executedQty`, also der Betrag VOR diesem Abzug. Diese zu hohe Menge ging anschließend in die exchange-seitige Stop-Loss-Order **und** in jeden Market-Sell beim Exit – live mit ca. 0,1% Gebühr hätte das **jeden einzelnen Verkaufsversuch** betroffen, und beim Trend-Bot zusätzlich dazu geführt, dass die Stop-Order gar nicht erst zustande kommt (die Position wäre ungeschützt geblieben, siehe den Folgefund oben).

**Keine Anbindung an die echten Handelsregeln:** `tickSize`/`stepSize`/`minNotional` wurden nirgends abgefragt; der bekannte TODO in `binance_client.py` deckte nur den Preis der Stop-Order ab (feste Rundung auf 2 Nachkommastellen). Eine nicht durch `stepSize` teilbare Menge lehnt die Börse direkt ab.

**Umgesetzt:**
- Neues Modul `dca_bot/order_utils.py` (rein, ohne Seiteneffekte, wie `*_signals.py`): `quantize_price`, `quantize_quantity` (Verkaufsmengen **immer** abrunden – eine zu hohe Menge wird abgelehnt, eine minimal zu niedrige ist nur unwesentlich suboptimal), `sum_commission`, `net_executed_quantity`, `net_proceeds`. Gerechnet wird mit `Decimal`, nicht mit float: `math.floor(0.3 / 0.1)` ergibt 2 statt 3, eine exakt auf der Schrittweite liegende Menge wäre also um eine ganze Stufe nach unten „korrigiert" worden.
- `binance_client.get_symbol_trading_rules()` holt die Filter einmalig pro Symbol aus `exchangeInfo` und cacht sie **pro Client-Instanz** (jeder Bot-Prozess erzeugt genau einen Client – faktisch „pro Prozess", aber ohne globalen Zustand, der zwischen Tests durchschlägt). Kein TTL: Binance ändert diese Filter praktisch nie, die Bots werden regelmäßig neu gestartet, und eine veraltete `stepSize` würde sich als abgelehnte Order zeigen, die seit den vorherigen Fixes sauber eskaliert. Schlägt der Abruf fehl, wird der Fehler **weitergereicht** statt auf Defaults auszuweichen.
- Alle drei `place_*`-Methoden quantisieren vor dem Request. Bei `place_market_buy` greifen bewusst **nicht** `stepSize`/`tickSize` – der Betrag ist in der Quote-Währung angegeben (`quoteOrderQty`), dort zählen Quote-Präzision und Mindestvolumen. Letzteres wird selbst geprüft (klare Meldung) statt die Order von der Börse ablehnen zu lassen, und zwar **vor** dem Dry-Run-Zweig, damit ein zu klein konfigurierter Betrag schon in der Paper-Trade-Phase auffällt.
- Gebührenkorrektur in allen drei Strategien. **DCA wurde mitgenommen**, obwohl er nie verkauft: `PortfolioStopLoss` bewertet die Position mit `quantity * current_price` – eine zu hohe Menge überschätzt den Portfoliowert und löst den Stop-Loss später aus als konfiguriert.
- **Verkaufsseite gleich mit:** die beim Verkauf in USDT abgerechnete Gebühr wird vom Erlös abgezogen (`cummulativeQuoteQty` ist brutto). Ohne das wäre nach diesem Fix die Kaufseite gebührengenau und die Verkaufsseite nicht – genau die Inkonsistenz, die später Zeit kostet.

**Reihenfolge als eigener Sicherheitspunkt:** Die Handelsregeln werden in allen Strategien **vor** der ersten Order geholt. Würde eine Exception erst nach einem erfolgreich ausgeführten Kauf auftreten, bliebe ein real bewegter Trade unverbucht – das wäre schlimmer als K3 selbst. Die Gebühren-Auswertung danach parst `fills` vollständig defensiv und wirft nie.

**Dry-Run:** Mengen werden quantisiert (damit Paper-Trade-Zahlen wie Live-Zahlen aussehen), eine Gebühr aber bewusst **nicht** simuliert – es gibt keinen Fill, ein geschätzter Satz wäre erfundene Zahl.

> **Korrektur 22.09.2026: Dieser Absatz beschrieb die Änderung als vollständig, die sie nicht war.** Quantisiert wurde nur die *Menge*; der zugehörige `quote_spent` blieb in allen drei Strategien der konfigurierte Rohbetrag. Damit hielt jede simulierte Position weniger, als ihre eigene Kostenbasis behauptete. Gefunden am 22.09. an den VPS-Live-Daten, behoben am selben Tag – siehe „Folgefund aus K3" direkt unten.

**Bekannte Restlücke, bewusst offen:** Antworten von `get_order()` (also der Pfad „exchange-seitige Stop-Order war bereits gefüllt") enthalten keine `fills` – dort bleibt die Verkaufsgebühr mangels Daten unberücksichtigt, der PnL dieses einen Exit-Pfads ist also weiterhin um ca. 0,1% zu optimistisch. Sauber lösbar nur über eine zusätzliche `myTrades`-Abfrage.

**Tests:** 36 neue. `tests/test_order_utils.py` (22, reine Funktionen inkl. der Decimal-Off-by-one-Falle und des „Menge exakt gleich stepSize"-Falls), `tests/test_dca_fee_adjustment.py` (5), plus `TrendTradingRulesTestCase` (7) und `GridTradingRulesTestCase` (7). Beide Fake-Clients liefern jetzt realistische `fills` mit `commission`/`commissionAsset` und implementieren `get_symbol_trading_rules` – der Gebührensatz bleibt per Default 0.0, weil das exakt dem beobachteten Testnet-Verhalten entspricht; die neuen Tests setzen 0,1%. Gesamtstand: 87 Tests, alle grün.

### Folgefund aus K3: `quote_spent` im Dry-Run-Kaufpfad (22.09.2026)

Beim Auswerten der laufenden VPS-Live-Daten aufgefallen: mehrere geschlossene Grid-Positionen mit **negativer** `realized_pnl`, obwohl der Kurs zwischen Kauf und Verkauf gestiegen war. Kein Rundungsrest, sondern ein Vorzeichenfehler.

**Der Befund.** Der K3-Fix baute in alle drei Strategien denselben Dry-Run-Zweig ein – und in alle drei denselben Fehler:

```python
quantity    = quantize_quantity(amount / price, step)   # abgerundet
quote_spent = amount                                    # NICHT abgerundet
```

Die weggerundete Teilmenge wurde nie gekauft, stand aber trotzdem in der Kostenbasis. Die Verkaufsseite rechnet im Dry-Run korrekt mit `quantity * price` – daraus entsteht die Asymmetrie: Der Erlös folgt der quantisierten Menge, die Kosten folgen dem Wunschbetrag.

**Warum das keine Nachkommastelle ist.** Bei `stepSize` 1e-5 und einem 15-USDT-Auftrag ist *eine* Mengenstufe bei BTC ≈ 80.000 rund 0,80 USDT, also bis zu ~5 % des Auftrags – mehr als der Grid-Stufenabstand von 1,5 %, den die Strategie überhaupt verdienen soll. Deshalb kippt das Vorzeichen, statt das Ergebnis nur zu verschieben.

Der konkrete Beleg (Position `569fff51`):

| | |
|---|---|
| `buy_price` / `quantity` / `quote_spent` | 79.964,55 / 0,00018 / 15,00 |
| tatsächlicher Wert der Menge beim Kauf | **14,39** |
| Fehler in der Kostenbasis | +0,61 (4,04 %) |
| gebuchte `realized_pnl` | −0,36 |
| korrekt | **+0,25** |

**Alle drei Bots waren betroffen**, mit unterschiedlichem Schadensbild:

| Bot | Stelle | Wirkung |
|---|---|---|
| Grid | `grid_strategy._process_buys()` | `realized_pnl` jeder geschlossenen Dry-Run-Position zu negativ |
| Trend | `trend_strategy._open_position()` | dasselbe; wiegt schwerer, weil es wenige große Trades sind – und mit aktivem Allocator-Opt-in ist `amount` kleiner, dieselbe Mengenstufe macht relativ also **mehr** aus |
| DCA | `strategy.execute_once()` | kein `realized_pnl` (verkauft nie), und der Portfolio-Stop-Loss sieht Dry-Run-Käufe gar nicht (`TradeLedger.position()` filtert sie). Aber `day_summary()` summiert über **alle** Käufe: der Bot buchte gegen sein Tageslimit einen Betrag, den er nie ausgegeben hat, und meldete ihn so auch in der Tageszusammenfassung |

**Der Homeserver ist nicht betroffen, und das ist keine Glückssache.** Dort laufen echte Orders (`dry_run: false`). Ein Market-Buy geht über `quoteOrderQty` – Binance gibt den vollen Betrag aus und meldet mit `cummulativeQuoteQty` den tatsächlich belasteten. Menge und Betrag stammen damit aus derselben Quelle und passen per Konstruktion zueinander; es gibt lokal nichts nachzurechnen. Nur der Dry-Run-Pfad muss den Betrag selbst herleiten – und tat es nicht. Genau daran war der Fehler auch zu erkennen: Auf dem Homeserver sind die Werte krumm (14,526203 / 8,9345333), auf dem VPS glatt 15,00. **Ein glatter `quote_spent` neben einer quantisierten Menge ist selbst schon das Symptom.**

**Ebenfalls geprüft und nicht betroffen:** die Reconciliation-Pfade aller drei Bots (schreiben immer `dry_run=False` und lesen `cummulativeQuoteQty`), `_close_from_filled_stop_order()` (kann eine Dry-Run-Position nicht erreichen – dort existiert keine Stop-Order) und **alle Backtests**: die quantisieren gar nicht, dort ist `quantity = amount/price` und `quote_spent = amount` in sich konsistent. Die in 5a/6i dokumentierten Backtest-Zahlen sind von diesem Fund also unberührt.

**Umgesetzt:** In allen drei Dry-Run-Zweigen kommt `quote_spent` jetzt aus der quantisierten Menge (`quantity * price`) – die Entsprechung dessen, was ein echter Fill als `cummulativeQuoteQty` liefert. Bewusst ohne zusätzliche Rundung auf die Quote-Präzision: Nur so gilt für simulierte Trades wieder exakt `realized_pnl = quantity * (Verkauf − Kauf)`, eine Invariante, die man nachrechnen kann und die genau die verletzte Aussage ist. Die K3-Entscheidung, im Dry-Run **keine** Gebühr zu schätzen, bleibt unangetastet.

**Bestehende Daten korrigiert** über ein einmaliges, versioniertes Skript `dca_bot/fix_dry_run_quote_spent.py` (im Repo statt als Wegwerf-Einzeiler, damit der Eingriff reproduzierbar und im Git-Log auffindbar ist). Es rechnet für Einträge mit `dry_run: true` den Betrag aus `quantity × Kaufpreis` und die PnL aus `quantity × Verkaufspreis − quote_spent` neu. Eigenschaften, die dabei zählten:

- **Bericht ist der Default**, geschrieben wird nur mit `--apply` – gleiche Haltung wie `audit_positions.py`.
- **`dry_run` wird nie geraten.** `false` bleibt unangetastet (dort ist `quote_spent` die Ground Truth der Börse; es zu überschreiben wäre genau der umgekehrte Fehler), ein fehlendes Feld ebenfalls, mit lauter Meldung – dieselbe Regel wie `[GRID-POSITION-UNKLAR]`.
- **Idempotent per Konstruktion:** geschrieben wird nur oberhalb einer Toleranz. Für Einträge von **vor** dem K3-Fix ist die Neuberechnung ein No-op (die Menge war dort unquantisiert, die Rückrechnung trifft den Ausgangswert). Es braucht deshalb weder Datumsfilter noch „schon korrigiert"-Markierung. An den lokalen Ledgern vom 10.09. verifiziert: 0 Änderungen.
- **Läuft nicht neben einem laufenden Bot** – vor dem Schreiben wird dasselbe Lock geholt, das der Bot hält. Sonst überschriebe dessen nächster Zyklus die Korrektur mit seinem eigenen Stand.
- **Zeitgestempelte Kopie vor dem Schreiben.** Das weicht bewusst von der Entscheidung in 6i ab, auf `.bak`-Kopien zu verzichten – die galt dem *laufenden* Schreibpfad, der durch atomare Writes, VM-Snapshots und Git abgedeckt ist. Hier schreibt ein einmaliges Skript Historie um, die sich aus nichts anderem rekonstruieren lässt. Unterschiedliche Lage, unterschiedliche Antwort.

**Ergebnis des Laufs.** Auf dem VPS **8 korrigierte Einträge im Grid-Ledger, davon 4 mit Vorzeichenwechsel**. Die realisierte PnL der sieben geschlossenen Positionen zusammengenommen: **−0,42 → +2,98 USDT**, also eine Verschiebung um +3,40. Der achte Eintrag ist eine noch offene Position – dort gibt es nur `quote_spent` zu korrigieren, eine realisierte PnL existiert noch nicht. Auf dem **Homeserver 0 Änderungen**, wie vorhergesagt.

Zwei Dinge sind daran bemerkenswert. Erstens: Das Vorzeichen kippte bei **mehr als der Hälfte** der geschlossenen Positionen – der Fehler war also nicht der Ausreißer, als den die eine dokumentierte Beispielposition ihn aussehen lässt, sondern der Regelfall bei dieser Auftragsgröße. Zweitens war das Gesamtergebnis vor der Korrektur **negativ**, nach der Korrektur positiv. Eine Auswertung der Paper-Trade-Phase hätte damit nicht nur ungenaue Zahlen geliefert, sondern das falsche Vorzeichen für die Frage „verdient die Grid-Strategie im Testbetrieb überhaupt etwas?" – und genau das ist die Frage, wegen der der Testbetrieb läuft.

Die 0 Änderungen auf dem Homeserver sind dabei ausdrücklich **gemessen und nicht angenommen**: Die Begründung oben (echte Orders bekommen Menge und Betrag aus derselben Quelle) ist ein strukturelles Argument, und ein strukturelles Argument ist eine Vorhersage. Der Lauf hat sie geprüft. Das ist derselbe Grund, aus dem der Lauf auch gegen die lokalen Ledger vom 10.09. lief (ebenfalls 0 Änderungen, siehe Idempotenz oben).

Die zeitgestempelte `.pre-fix`-Kopie bleibt bis zur Auswertung der Paper-Trade-Phase liegen. Sie wegzuräumen kostet nichts und bringt nichts – solange die Zahlen noch ausgewertet werden, ist der Stand davor der einzige Beleg dafür, was korrigiert wurde.

**Beobachtung zur Allocator-Wirkung, als Hinweis für die spätere Auswertung.** Beim Durchsehen derselben Daten fiel etwas auf, das kein Fehler ist, die Auswertung aber verzerren würde, wenn man es nicht weiß: Auf dem Homeserver gibt es **Tage ganz ohne DCA-Kauf**, und zwar genau an Tagen mit hoher Trendstärke. Der Mechanismus ist dokumentiert und gewollt – bei aktivem Opt-in skaliert der DCA-Bot seinen Betrag mit `1 − trend_fraction`, und unterhalb von `MIN_EFFECTIVE_QUOTE_AMOUNT` (5,00) wird der Kauf übersprungen statt als wirtschaftlich bedeutungslose Mini-Order platziert (siehe 5a und die entsprechende `[INFO]`-Zeile in `strategy.py`). Bei `DCA_QUOTE_AMOUNT=15,00` greift das ab einem Trend-Anteil von rund 67 %.

Das ist die **Live-Entsprechung des Backtest-Befunds aus 5a**: Die Kombination bindet deutlich weniger Gesamtkapital als isoliertes DCA (2023 nur 39 %), weil das dem DCA entzogene Kapital nicht automatisch zum Trend-Bot fließt – der investiert nur an seinen eigenen, seltenen Einstiegstagen. Im Backtest war das eine Kennzahl in einer Tabelle, live ist es ein ausbleibender Kauf.

Für die Auswertung der Paper-Trade-Phase heißt das zweierlei:

- **Die Anzahl der Trades ist zwischen VPS und Homeserver nicht vergleichbar.** Auf dem VPS läuft der Allocator bewusst nicht (siehe 6e), dort kauft der DCA-Bot jeden Tag. Weniger Käufe auf dem Homeserver sind das erwartete Verhalten und kein Hinweis auf eine Störung – eine Erwartung, die man vor dem Vergleich festhalten sollte und nicht danach.
- **Verglichen werden muss die Rendite pro eingesetztem Euro, nicht der absolute Gewinn.** Das ist exakt die Korrektur, die in 5a schon einmal nötig war, nachdem die erste Fassung der Backtest-Tabelle Prozentwerte bei ungleicher Kapitalbasis nebeneinandergestellt hatte. Derselbe Fehler steht bei der Live-Auswertung ein zweites Mal bereit, nur mit echten Zahlen statt simulierten.

**Was der Fund über die Testabdeckung sagt.** Grid und Trend hatten je einen Test, dass die Dry-Run-Menge quantisiert wird – aber keiner prüfte den Betrag dazu. Die Zusicherung war einseitig, und die fehlende Hälfte *war* der Bug. Dass die 523 bestehenden Tests nach dem Fix unverändert grün blieben, ist der Beleg dafür. Dieselbe Fehlerklasse wie bei den Funden in 6i, nur eine Ebene tiefer: nicht ein Test, dessen Prämisse nicht stimmt, sondern ein Test, der nur die Hälfte seiner Aussage prüft.

**Tests:** 24 neue – 3 in `test_grid_sell_safety.py`, 4 in `test_trend_stop_loss.py`, 3 in `test_dca_fee_adjustment.py`, 14 in der neuen `tests/test_fix_dry_run_quote_spent.py`. Jeder der drei Bots bekommt dieselben drei Aussagen: Betrag folgt der Menge (**mit Gegenprobe**, dass die Quantisierung an der gewählten Preislage überhaupt greift – sonst wäre der Test auch dort grün, wo es nichts abzuschneiden gibt), Rundlauf bei gestiegenem Kurs ergibt positive PnL (das reproduzierte Live-Symptom), und eine Regression für echte Orders, bei der die Börse bewusst einen von `quantity * price` **abweichenden** Betrag meldet – sonst wäre nicht unterscheidbar, ob der Code den gemeldeten Wert übernimmt oder ihn zufällig gleich ausrechnet. Gesamtstand: **547 Tests, alle grün.**

**Wirksamkeit gemessen, in beide Richtungen.** Kontrolllauf ohne Mutation: 0 Fehlschläge. Dry-Run-Zweig auf den Rohbetrag zurückgedreht → Grid 2, Trend 3, DCA 2 Fehlschläge. Gegenrichtung (Echt-Order-Pfad rechnet lokal nach, statt `cummulativeQuoteQty` zu übernehmen) → Grid 1, Trend 1, DCA 2. Beim Korrektur-Skript werden 6 von 7 Mutationen gefangen (Echt-Einträge ungeschützt → 1, fehlendes `dry_run` wird geraten → 1, Bericht schreibt trotzdem → 2, keine Sicherungskopie → 1, PnL gegen die alte Kostenbasis → 5, Toleranz aufgehoben → 3).

Die siebte Mutation (der DCA-Aufruf bekommt ein Verkaufspreis-Feld gesetzt) meldet 0 Fehlschläge – und das ist diesmal **weder** ein mehrdeutiges Suchmuster noch eine Testlücke, die beiden Ursachen aus 6i. `TradeRecord` hat schlicht kein `sell_price`-Feld (nachgeprüft, nicht angenommen), die Bedingung für den PnL-Zweig kann dort also nie wahr werden; die Mutation ist ohne beobachtbare Wirkung. Festgehalten statt weggelassen, weil „0 Fehlschläge" im Projekt bisher zweimal ein echtes Problem angezeigt hat – die Unterscheidung ist nur etwas wert, wenn auch der harmlose Fall benannt wird.

**Zwei Nebenbeobachtungen aus der Messung:** Erstens traf die Gegenmutation im DCA-Bot zunächst die falsche Stelle – `quote_spent = float(order.get("cummulativeQuoteQty", amount))` steht in `strategy.py` **zweimal** (Reconcile-Pfad und Kaufpfad), und die Ersetzung erwischte die erste. Exakt dieselbe Falle wie bei `split_locked_by_bot` in 6i, Stufe 2. Zweitens meldeten drei Tests nach dem Zurücksetzen einer Mutation weiterhin Fehlschläge: Mutation und Restore lagen in derselben Sekunde, und Python prüft die Gültigkeit seines Bytecode-Caches sekundengenau über `mtime` – die Messung lief gegen ein `.pyc` der mutierten Fassung. Die Messreihe wurde deshalb mit `-B` wiederholt. Beide Male war das Warnsignal dasselbe wie in 6i: ein Messergebnis, das zum offensichtlich einschlägigen Test nicht passt.

**Nachgerüstet (23.09.2026): Invarianten-Check im Positions-Audit.** `audit_positions.py` meldet jetzt jede geschlossene Dry-Run-Grid-Position mit negativer `realized_pnl`. Rein informativ wie der Rest des Skripts – keine Korrektur, nur Sichtbarkeit; das Korrektur-Werkzeug bleibt `fix_dry_run_quote_spent.py`.

Der Punkt ist nicht, dieselben Daten ein zweites Mal zu prüfen, sondern **das Symptom zu benennen, an dem der Fund überhaupt aufgefallen ist**. Bemerkt wurde er beim manuellen Durchsehen der Live-Daten – also dadurch, dass jemand hingesehen und die Zahl als widersprüchlich erkannt hat. Der Check macht aus dieser Beobachtung eine Zusicherung, die auch ohne aufmerksames Hinsehen anschlägt: Ein Verkauf findet nur bei erreichtem Sell-Target statt, das ist die nächsthöhere Grid-Stufe und liegt über dem Kaufpreis, und im Dry-Run gibt es keine Gebühr, die etwas abziehen könnte. `realized_pnl = quantity * (Verkauf − Kauf)` kann dort nicht negativ werden – das ist genau die Invariante, die der Fix wiederhergestellt hat.

Bewusst **nur Dry-Run und nur Grid**: Bei einer echten Position zieht die Verkaufsgebühr vom Erlös ab, ein knapp erreichtes Ziel darf legitim im Minus enden; beim Trend-Bot ist ein Verlust der Normalfall eines Stop-Loss-Exits, dort existiert die Invariante gar nicht. Einträge ohne `dry_run`-Feld bleiben wie überall sonst draußen, statt geraten zu werden. Ein Check, der auch dort meldet, wo das Minus richtig ist, wäre nach dem dritten Fehlalarm keiner mehr.

**Tests:** 10 neue in `tests/test_audit_positions.py`, Gesamtstand **557, alle grün**. Die Gegenproben tragen hier den Inhalt, denn ein Check, der meldet, wäre auch grün, wenn er *alles* meldete: dieselbe Position mit korrigierter PnL (+0,25) ist kein Befund, eine echte Position mit demselben Minus ebenso wenig, und eine offene Position hat noch gar keine PnL. Wirksamkeit gemessen, Kontrolllauf 0 Fehlschläge; alle 6 Mutationen gefangen (Dry-Run-Gate entfernt → 2, `>= 0` zu `> 0` → 1, geschlossene → alle Einträge → 1, geschlossene → offene → 4, Abbruch nach dem ersten Treffer → 1, Verkaufspreis nicht in den Befund übernommen → 1).

### K2: Order ohne Ledger-Eintrag (16.09.2026)

Der komplexeste der fünf kritischen Punkte und zugleich der einzige, bei dem ein real ausgeführter Trade dauerhaft unsichtbar bleiben konnte — ohne dass irgendetwas im Log darauf hingewiesen hätte, dass Zahlen fehlen.

**Der Befund, zweiteilig:** `binance_client.py` fing in allen `place_*`-Methoden nur `BinanceAPIException` und `BinanceOrderException`. `python-binance` setzt seine Requests aber über `requests` ab: ein Timeout oder Verbindungsabbruch kommt als `requests.exceptions.ReadTimeout`/`ConnectionError` durch, eine kaputte Antwort als `BinanceRequestException` — keine davon wurde gefangen. Die Order geht raus, Binance nimmt sie an und füllt sie, die Antwort erreicht den Bot nicht → ungefangene Exception → `execute_once()` bricht ab → kein Ledger-Eintrag, obwohl eine echte, gefüllte Order an der Börse existiert. Dasselbe Loch entsteht **ohne jeden Netzwerkfehler** durch einen Prozess-Kill zwischen Order-Platzierung und Ledger-Schreibvorgang; beim Trend-Bot lagen dazwischen ein kompletter zweiter API-Call (die Stop-Loss-Order) plus Telegram-Sendeversuche, also mehrere Sekunden.

Auswirkung pro Bot: DCA — gekaufte Menge fehlt, Tageslimit und Stop-Loss-Kostenbasis bleiben dauerhaft zu niedrig. Grid — die Stufe bleibt "frei" und wird beim nächsten Crossing nochmal gekauft. Trend — der gravierendste Fall: Position existiert an der Börse, im Ledger nicht, **keine** Stop-Loss-Order gesetzt (der Code dafür lief nach der Order-Bestätigung), und der nächste Zyklus sieht "keine offene Position" und kauft bei weiter bestätigtem Aufwärtstrend erneut.

**Umgesetzt, Teil A — idempotente Platzierung mit Ground-Truth-Verifikation:** Neues Modul `dca_bot/pending_orders.py`. Jede echte Order bekommt vorab eine selbstvergebene `newClientOrderId` (`<bot>-<uuid>`), die zusammen mit minimalem Kontext **vor** dem Netzwerk-Call atomar (`tmp` + `os.replace` + `fsync`) in `data/pending_orders_<bot>.json` geschrieben wird — das überlebt auch einen Kill mitten im Request. Die `except`-Blöcke fangen jetzt zusätzlich `requests.exceptions.RequestException` und `BinanceRequestException`; bei einem Treffer wird nicht einfach `None` zurückgegeben (das sähe für die Strategie aus wie ein sauberer "kein Handelsbedarf"-Fall), sondern per `get_order(origClientOrderId=…)` nachgefragt. Vier Ausgänge: ausgeführt → echte Order-Daten zurück, als wäre der Call geglückt (die Strategie verbucht ganz normal); nie angenommen oder ohne Wirkung → `None` wie bisher; unklar → `ERROR` + Telegram mit der clientOrderId, und der Pending-Eintrag **bleibt** stehen. Die zusätzlichen `except`-Zweige kamen auch in `cancel_order()`, `get_order_status()` und `get_symbol_trading_rules()` — bei den ersten beiden flog ein Verbindungsfehler vorher bis in die Zyklus-Schleife und umging damit die sorgfältig gebaute `uncertain_cycles`-Behandlung aus 6f.

**Teil B — Reconciliation beim Start:** Neue Methode `reconcile_pending_orders()` auf allen drei Strategien (Muster wie das bestehende `reconcile_on_startup()`), aufgerufen vor der Hauptschleife. Pro Eintrag derselbe Ground-Truth-Check, dann nachtragen (`[REKONZILIATION]` in Log und Telegram), verwerfen oder weiter eskalieren. **In `main_trend.py` bewusst VOR `reconcile_on_startup()`:** ein nachgetragener Einstieg erzeugt eine offene Position ohne Stop-Loss-Order, und der bestehende Schritt sichert sie unmittelbar danach über `_ensure_stop_loss_protection()` ab — der gefährlichste Fall des ganzen Fixes landet damit auf bereits vorhandener, getesteter Mechanik statt auf neuem Code.

**Sechs bewusste Abweichungen von der ursprünglichen Vorgabe** (vor der Umsetzung vorgelegt und freigegeben):
1. `newClientOrderId` ist bei Binance auf **36 Zeichen** begrenzt — `"trend-" + uuid4().hex` wären 38. Der UUID-Anteil wird deshalb auf 24 Hex-Zeichen gekürzt (96 Bit). Das wäre sonst je nach Testnet-Stand erst im Echtgeld-Betrieb aufgefallen.
2. "Nicht gefunden" gilt **nur** bei Fehlercode −2013. Jeder andere API-Fehler (Rate-Limit, Timestamp-Drift, 5xx) ist keine Aussage über die Order → unklar. Eine pauschale "Exception = nie passiert"-Regel wäre genau der K2-Fehler, eine Ebene höher.
3. Für eine `STOP_LOSS_LIMIT`-Order ist **`NEW` der Erfolgsfall**, nicht "unklar" — sie soll offen im Orderbuch liegen. Die Vorgabe "gefunden, aber nicht FILLED → unklar" gilt nur für Market-Orders; daher das `kind`-Feld im Pending-Eintrag.
4. Market-Order: `terminaler Status + executedQty > 0` statt strikt `FILLED`. Eine nicht voll füllbare Market-Order endet bei Binance als `EXPIRED` mit echter Teilmenge — auf `FILLED` zu bestehen hieße, diesen Fall für immer als "unklar" zu führen.
5. **Gebühren im Reconcile-Pfad:** `get_order()`-Antworten enthalten keine `fills`. Ein nachgetragener Kauf käme sonst mit der Brutto-Menge ins Ledger und liefe damit zurück in die K3-Falle ("verkaufe mehr, als da ist"). Neue Methode `get_order_with_fills()` lädt die Gebührendaten über `myTrades` nach, sodass `net_executed_quantity()`/`net_proceeds()` unverändert greifen — schließt zugleich die in K3 als "bewusst offen" notierte Restlücke für diesen Pfad. Scheitert die Abfrage: Brutto mit deutlicher Warnung, ein Eintrag mit minimal zu hoher Menge ist besser als gar keiner.
6. Lockfile portabel (`fcntl` **und** `msvcrt`) statt nur `fcntl` — ein reiner `import fcntl` hätte jeden Testlauf auf dem Windows-Entwicklungsrechner zerlegt.

**Der DCA-Sonderfall (explizit vorab geprüft):** Das Muster passt dort **nicht** 1:1. Grid und Trend führen pro Trade eine `id` plus `status`, ein doppelter Nachtrag fällt dort von selbst auf. `TradeLedger` ist eine reine append-only Liste ohne Status — stirbt der Prozess zwischen Ledger-Eintrag und dem Entfernen des Pending-Eintrags, würde derselbe Kauf beim nächsten Start ein **zweites Mal** angehängt und Tageslimit sowie Stop-Loss-Kostenbasis verfälschen; also derselbe Schaden wie K2, nur mit umgekehrtem Vorzeichen. Gelöst über ein neues Feld `client_order_id` als reinen Idempotenzschlüssel (`has_client_order_id()`), ohne das append-only-Modell aufzugeben. Dasselbe Feld kam zu `GridPosition` und `TrendTrade` — deren lokale `id` taugt zur Korrelation nicht, die hat die Börse nie gesehen. Alle drei Felder haben `None` als Default, bestehende Ledger-Dateien bleiben unverändert lesbar.

**Nebenbefund, mitbehoben:** In `trend_strategy._open_position()` stand `record_entry()` ganz am Ende — nach der Stop-Loss-Order und den Telegram-Aufrufen. Genau dieses Fenster machte den Trend-Bot zum schlimmsten K2-Fall. Der Ledger-Eintrag entsteht jetzt **unmittelbar** nach dem bestätigten Kauf, die Stop-Order wird nachträglich per `set_stop_loss_order()` am bestehenden Eintrag hinterlegt.

**Bewusst NICHT automatisch storniert (auf ausdrückliche Entscheidung):** Findet der Reconcile eine Stop-Order an der Börse, während im Ledger bereits eine *andere* Order-ID steht, existieren zwei Stop-Orders über dieselbe Menge. Der Bot meldet das laut (Log + Telegram) und lässt beide stehen. Begründung: das wäre seine erste autonome, destruktive Aktion auf Basis eines abgeleiteten, nicht vollständig kartierten Zustands — und widerspräche dem sonst durchgehaltenen Prinzip "im Zweifel nicht handeln" (vgl. Cancel-Pfad/`uncertain`-Zustand aus 6f). Ein Mensch sieht sich das einmal an.

**Die Meldung dazu wurde anschließend angereichert** (ohne die Entscheidung oben anzutasten): Vor dem Versand fragt der Bot per `get_order_status()` den tatsächlichen Börsen-Status **beider** Orders ab und baut ihn in Log-Zeile und Telegram-Nachricht ein (`Ledger-Order <id>: Status NEW. Pending-Order <id>: Status CANCELED.`). Der praktische Nutzen: oft ist eine der beiden längst `CANCELED` oder `FILLED` und es ist gar nichts zu tun — das steht jetzt direkt in der Nachricht, statt dass man nach jeder Meldung erst manuell bei Binance nachsehen muss. Schlägt eine der beiden Abfragen fehl, wird das ausdrücklich als `Status nicht abrufbar` ausgewiesen statt geraten oder weggelassen — "der Bot konnte es nicht klären" ist für die manuelle Prüfung eine andere Aussage als jeder echte Order-Status. `cancel_order()` wird weiterhin nicht aufgerufen: reine Informationsanreicherung, keine Verhaltensänderung.

**W4 gleich mit erledigt (Lockfile gegen doppelten Bot-Start):** Neues Modul `dca_bot/process_lock.py`, eingebunden in alle **vier** Einstiegspunkte — der Allocator platziert zwar nie Orders, zwei Exemplare würden aber dieselbe State-Datei überschreiben, also dieselbe Fehlerklasse. Bewusst ein Lock auf dem Dateideskriptor statt einer PID-Datei: das OS gibt es auch bei `kill -9` frei, eine liegengebliebene `.lock`-Datei blockiert damit keinen Neustart — der Fehler, an dem naive Lösungen scheitern und der bei einem Trading-Bot besonders teuer wäre.

**Erzwungene Invariante nebenbei:** `AllocatorConfig.pending_orders_file` ist bewusst leer, und die `place_*`-Methoden weisen einen leeren Wert aktiv zurück. Damit ist "der Allocator platziert nie Orders" keine Zusage im Docstring mehr, sondern eine Bedingung, die der Code erzwingt.

**Tests:** 72 neue. `tests/test_pending_orders.py` (44 — Store, ID-Längengrenze, die Bewertungsregel inkl. der bewussten Market-vs-Stop-Abweichung bei `NEW`, und die drei geforderten Netzwerkfehler-Szenarien gegen einen echten `TradingClient` mit gefälschtem **rohen** Binance-Client darunter, plus eine Gegenprobe zur Token-Hygiene: die Request-URL samt HMAC-Signatur darf nicht ins Log, gleiche Haltung wie K5), `tests/test_order_reconciliation.py` (19 — Nachtragen/Verwerfen/Eskalieren je Bot, Idempotenz beim DCA, die vollständige Trend-Kette bis zur nachgeholten Stop-Order, und drei Kombinationen für die Doppel-Stop-Order-Meldung inkl. der Gegenprobe, dass nichts storniert wird) und `tests/test_process_lock.py` (9). Gesamtstand: **159 Tests, alle grün.**

**Ehrliche Einordnung der Verifikation:** Auf dem Testnet ist dieser Pfad kaum zu provozieren — Verbindungsabbrüche gegen `testnet.binance.vision` sind selten, und ein Prozess-Kill im richtigen Millisekundenfenster noch seltener. Die Wirksamkeit belegen hier die Tests, nicht der Livebetrieb. Im Normalbetrieb ist von dem Mechanismus nichts zu sehen: die Pending-Datei ist leer, ein Eintrag lebt Millisekunden. Die Stelle, an der sich etwas zeigen würde, ist `grep REKONZILIATION logs/*.log`.

### Sicherheitsreview abgeschlossen: K1–K5 vollständig behoben (16.09.2026)

Mit dem K2-Fix sind **alle fünf kritischen Punkte** aus dem Sicherheitsreview (Claude Opus 5, 15.09.2026) behoben:

| Punkt | Inhalt | Behoben |
|---|---|---|
| **K1** | Fehlgeschlagener echter Verkauf wurde als Erfolg verbucht (Grid + Trend) | 16.09.2026 |
| **K2** | Order konnte ausgeführt werden, ohne je im Ledger zu landen | 16.09.2026 |
| **K3** | Handelsgebühren und echte Handelsregeln (tickSize/stepSize/minNotional) | 16.09.2026 |
| **K4** | Dry-Run-Positionen wären beim Umschalten auf Live real verkauft worden | 16.09.2026 |
| **K5** | Telegram-Bot-Token-Leak in Logs | 15.09.2026 (VPS-Prüfung 16.09.) |

Dazu zwei Funde, die aus der Bearbeitung selbst entstanden und mit erledigt wurden: der **K1-Folgefund** (Position konnte dauerhaft ohne Börsen-Absicherung bleiben) und **W4** (kein Schutz gegen doppelten Bot-Start).

**Die K3-Restlücke ist damit ebenfalls geschlossen.** Sie war beim K3-Fix bewusst offen gelassen worden: `get_order()`-Antworten enthalten keine `fills`, weshalb im Exit-Pfad "exchange-seitige Stop-Order war bereits gefüllt" die Verkaufsgebühr mangels Daten unberücksichtigt blieb (PnL dieses einen Pfads ca. 0,1% zu optimistisch); die Notiz dort lautete "sauber lösbar nur über eine zusätzliche `myTrades`-Abfrage". Genau diese Abfrage wurde für den K2-Reconcile-Pfad gebraucht und als `get_order_with_fills()` gebaut — dort zwingend, weil ein nachgetragener Kauf sonst mit der Brutto-Menge ins Ledger käme und damit in dieselbe K3-Falle zurückliefe.

> **Korrektur 17.09.2026: Der Absatz oben stimmte nicht.** Das Werkzeug `get_order_with_fills()` wurde gebaut und in den fünf Reconciliation-Pfaden genutzt — aber an `_close_from_filled_stop_order()`, also genau den Pfad, um den es in der Restlücke ging, nie angeschlossen. Er buchte weiterhin `cummulativeQuoteQty` brutto. Die Restlücke bestand damit vom 16.09. bis zum 17.09. unverändert fort, während dieser Absatz sie als geschlossen auswies. Aufgefallen beim Ist-Stand-Check der Verbesserungsvorschläge aus Review-Abschnitt 7 (Punkt 8), behoben am 17.09. — siehe „Verbesserungsvorschläge, Stufe 1" in 6i.
>
> Das ist eine andere Fehlerklasse als die beiden Doku-Karteileichen desselben Tages (6b, 5a): Dort war ein Text veraltet, hier stand im Dokument eine **Zusicherung über das laufende System, die nie zutraf**. Festgehalten statt stillschweigend überschrieben, weil genau diese Sorte Aussage später als Beleg herangezogen wird.

**Was das für den Live-Gang heißt:** Punkt 1 der Liste aus 6d (Sicherheitsreview mit Opus 5) ist abgeschlossen, Punkt 2 (exchange-seitiger Stop-Loss) ist umgesetzt und deployed. Offen bleiben die nicht-code-seitigen Punkte: Kapitalverteilung nach Auswertung des Testmonats (3), Home-Netzwerk-Absicherung (4, laut 6e bereits geprüft — keine Portfreigaben vorhanden) sowie der weiterlaufende Allocator-Live-Dry-Run (5). Der Code selbst gilt damit als review-seitig freigegeben; die verbleibende Absicherung ist die monatelange Paper-Trade-Phase, u.a. zur Kalibrierung von `TREND_STOP_LIMIT_OFFSET_PCT` (siehe 6f).

### Wichtige Punkte, Stufe A: W18, W7, W6, W8, W1 (16.09.2026)

Nach Abschluss von K1–K5 wurde zuerst ein Ist-Stand-Check über alle 18 „wichtigen" Punkte des Reviews gemacht, statt sie der Reihe nach abzuarbeiten. Ergebnis: **W4 war durch den K2-Fix bereits erledigt** (Lockfile), **W7, W8 und W18 nur teilweise**, die übrigen 14 unverändert offen. Daraus entstand eine nach Sicherheitsrelevanz sortierte Liste; Stufe A umfasst die fünf Punkte, bei denen ein dokumentierter Sicherheitsmechanismus nicht hält, was er verspricht. Vier davon (W18/W7/W6/W8) liegen im selben Bereich — der Fill-Erkennung der exchange-seitigen Stop-Order — und wurden deshalb als ein Arbeitspaket umgesetzt.

**W18 — Reconciliation außerhalb von `try/except` (selbst eingeschleppt):** Der Check brachte einen Punkt ans Licht, der durch den K2-Fix **schlimmer** geworden war. `reconcile_on_startup()` lag schon vorher ungeschützt vor der Hauptschleife; mit K2 kam `reconcile_pending_orders()` dazu — ungeschützt, und jetzt in allen **drei** Bots statt nur einem. Eine Exception dort beendet den Prozess, `Restart=on-failure` startet neu, das Ganze wiederholt sich; beim DCA-Bot löst zusätzlich jeder Start sofort einen Kauf aus (W2). Neuer Helfer `safe_startup_reconciliation()` in `pending_orders.py`, der jeden Schritt **einzeln** kapselt: scheitert beim Trend-Bot Schritt 1, läuft Schritt 2 trotzdem — er sichert eine bereits offene Position ab und ist gerade dann wertvoll. Bewusst ein gemeinsamer Helfer statt dreier identischer Blöcke: die vorhandene Duplikation von `_sleep_with_kill_switch_check()` in den `main*.py` ist selbst ein Review-Kritikpunkt (N3) und kein Vorbild für neuen sicherheitsrelevanten Code; als Funktion ist das Ganze außerdem direkt testbar.

**W6 — Stop-Loss-Latch hing an einem Logging-Detail:** `self._stop_loss.pause(...)` stand am Ende von `_log_stop_fill_analysis()` — hinter dessen `return` für einen fehlenden `stop_limit_price`. Eine über einen Exchange-Fill geschlossene Position ohne hinterlegten Limitpreis bekam deshalb **keinen** Latch, obwohl es ein regulärer Stop-Loss-Exit war: der Bot hätte im nächsten Zyklus sofort wieder einsteigen dürfen, also genau der Whipsaw, gegen den der Latch gebaut ist. Der Zustand ist real erreichbar (Stop-Order erst nachträglich platziert, oder Ledger-Eintrag aus der Zeit vor Einführung des Feldes). Der Latch sitzt jetzt im Exit-Pfad selbst, direkt hinter `record_exit()`; die Logging-Funktion tut nur noch das, was ihr Name sagt.

**W7 — verschwundene Stop-Order wurde nie erkannt:** `_check_exchange_stop_loss_fill()` prüfte nur `status == "FILLED"`. Eine Order, die an der Börse beendet wurde, ohne etwas zu bewegen (`CANCELED`/`EXPIRED`/`REJECTED`), blieb dem Ledger als gültige Absicherung erhalten — und `_ensure_stop_loss_protection()` steigt bei **jeder** vorhandenen `stop_loss_order_id` sofort aus. Die Position wäre dauerhaft ungeschützt geblieben, ohne dass es je eskaliert: derselbe Endzustand wie beim K1-Folgefund, nur über einen anderen Weg hinein. Jetzt wird die Zuordnung gelöst (Log + Telegram) und noch im selben Durchlauf Ersatz platziert. Eine **fehlgeschlagene** Status-Abfrage gilt ausdrücklich nicht als „Order weg" — sonst würde ein Netzwerkhänger eine zweite Order über dieselbe Menge auslösen.

**W8 — `PARTIALLY_FILLED` und eine Regel-Divergenz:** Der Fill-Check kannte nur „FILLED oder nicht" und hatte damit eine eigene, vom K2-Pfad abweichende Regel für denselben Sachverhalt. Behoben wurde nicht nur der Symptomfall, sondern die Divergenz: neue Funktion `order_lifecycle_state()` in `pending_orders.py` ist die **einzige** Stelle im Projekt, an der ein Binance-Order-Status ausgewertet wird (`filled` / `live` / `dead` / `unreadable`). `classify_order_status()` (Pending-Pfad) wurde zur reinen Übersetzung darüber, der Fill-Check nutzt sie direkt. Der einzige Unterschied zwischen beiden — für eine Stop-Order ist „lebt noch" ein Erfolg, für eine Market-Order ein unklarer Zustand — steht jetzt an genau einer Stelle. Eine teilgefüllte Stop-Order wird gemeldet, aber bewusst **nicht** korrigiert: die Order kann noch vollständig füllen, jede notierte Teilmenge wäre im nächsten Moment falsch.

**W1 — `*_HALT` wirkte erst nach Neustart:** `KillSwitch.is_set()` las `os.getenv()`, also die beim Prozessstart einmalig aus der `.env` befüllte Umgebung. `DCA_BOT_HALT=true` nachträglich in die Datei zu schreiben hatte keinerlei Wirkung — während README und `.env.example` es als gleichwertige Alternative zur STOP-Datei beschrieben. Ein Notaus, der nicht auslöst, ist die schlechteste Sorte Sicherheitsmechanismus, weil man sich darauf verlässt. Jetzt werden drei Quellen ODER-verknüpft geprüft: Notaus-Datei, Prozess-Umgebung und die **aktuelle** `.env`. Die Verknüpfung ist bewusst asymmetrisch — auslösen leicht, versehentliches Aufheben schwer.

Gelesen wird mit `dotenv_values()`, **nicht** `load_dotenv(override=True)`: Letzteres würde `os.environ` überschreiben und damit auch Werte, die die systemd-Unit gesetzt hat (z.B. ein dort erzwungenes `*_BOT_ENABLE_TRADING=false`). Ein Notaus-Check darf keine anderen Einstellungen umbiegen. Davor ein mtime+Größe-Wächter; **gemessen statt angenommen**: ein Vollparse der `.env` (1476 Bytes) kostet ~570 µs, ein `os.stat` ~15 µs. Selbst ohne Wächter wären das bei 5-Sekunden-Takt ~0,01 % eines Kerns — er ist billige Absicherung dagegen, dass jemand das Polling-Intervall später verkürzt.

**Tests:** 28 neue, davon vier mit expliziter Negativ-Kontrolle gegen den alten Code (W6: 1 Test fällt um; W7/W8: 5 Testmethoden; W1: 4 von 14). Neue Datei `tests/test_kill_switch.py` (14), neue Klasse `DeadStopOrderTestCase` in `tests/test_trend_stop_loss.py` (8, inklusive eines **Anti-Divergenz-Tests**, der nicht nur Verhalten prüft, sondern dass Fill-Check und Pending-Pfad derselben Quelle folgen), `SafeStartupReconciliationTestCase` (5) und der W6-Regressionstest. Gesamtstand: **187 Tests, alle grün.**

**Damit bleiben 13 der 18 W-Punkte offen** (W2, W3, W5, W9–W17) plus die Infrastruktur-Punkte, die nur per SSH auf VPS und Homeserver prüfbar sind — im Repo liegen keine `.service`-Dateien. Zwei davon hängen am harten VPS-Vertragsende **12.10.2026**: finaler `data/`-Snapshot und Entfernen des Deploy-Keys.

### Wichtige Punkte, Stufe B: W2, W3, W5, W10, W13, W15 (16.09.2026)

Korrektheit und Verfügbarkeit — sechs Punkte, die keinen dokumentierten Sicherheitsmechanismus aushebeln (das war Stufe A), aber jeweils zu falschen Zahlen oder zu unbemerkten Ausfällen führen.

**W5 — beschädigtes Ledger setzte Limits still zurück, und zwar in zwei Hälften.** `_read()` fing `JSONDecodeError` und lieferte eine leere Liste: Tageslimit und Stop-Loss-Kostenbasis fielen damit unbemerkt auf Null, der Bot kaufte weiter, obwohl faktisch Kapital gebunden war. Jetzt wirft eine vorhandene, aber unparsbare Datei `LedgerUnreadable`, und der Bot startet nicht (neue Methode `verify_state_readable()`, aufgerufen in allen drei `main*.py` **vor** der Hauptschleife und bewusst NICHT in `safe_startup_reconciliation()` gekapselt — deren Zweck ist „Start nicht verhindern", genau das wäre hier falsch herum).

Die zweite Hälfte war Voraussetzung für die erste: `_write()` war **nicht atomar** (`open("w")` kürzt und schreibt neu, und zwar die komplette Liste bei jedem Eintrag). Korruption fatal zu machen, ohne sie unwahrscheinlicher zu machen, wäre unterm Strich ein Verfügbarkeitsverlust gewesen — heute übersteht ein Crash-beim-Schreiben den Neustart mit falschen Zahlen, künftig hätte er den Bot stillgelegt. Alle drei Ledger schreiben jetzt atomar (`tmp` + `fsync` + `os.replace`), wie `PendingOrderStore` seit K2.

**Abgrenzung auf ausdrückliche Korrektur:** Eine **fehlende** Datei bleibt der reguläre Fall „frisches Deployment, allererster Start" und ergibt weiterhin eine leere Historie. Mein erster Entwurf hätte auch sie zum harten Abbruch gemacht — das hätte jedes Neuaufsetzen mit leerem `data/`-Ordner blockiert, also genau das Vorgehen vom Homeserver-Setup am 15.09. Der W5-Befund betraf ausschließlich kaputten Inhalt. Implementierungsdetail dazu: `FileNotFoundError` ist eine Unterklasse von `OSError`, die `except`-Reihenfolge muss „fehlt" vor „nicht lesbar" behandeln.

**W2 — jeder Prozessstart kaufte sofort.** `execute_once()` lief vor dem ersten `sleep`. Ein Neustart alle paar Minuten — geplant oder durch eine Restart-Schleife (siehe W18 in Stufe A, das genau so eine Schleife erzeugen konnte) — löste so viele echte Käufe aus, wie das Tageslimit gerade noch durchließ. Jetzt ermittelt `_seconds_until_next_cycle()` aus dem Ledger, wann der letzte Zyklus war, und wartet bis zur Fälligkeit (notaus-unterbrechbar). Leeres Ledger und abgelaufenes Intervall verhalten sich unverändert. Gezählt werden auch Dry-Run-Einträge: die Frage ist „hat ein Zyklus stattgefunden", nicht „ist Geld geflossen". Ein durch Stop-Loss oder Tageslimit übersprungener Zyklus schreibt keinen Eintrag — der nächste Start rechnet dann korrekt „lange her" und läuft sofort.

**W3 — Tagesfenster lokal statt UTC.** `date.today()` (lokale Serverzeit) gegen UTC-Zeitstempel im Ledger: je nach Zeitzone verschob sich die Tageslimit-Grenze um Stunden gegenüber den Daten. Neue Funktion `utc_today()` in `risk.py`, verwendet in Tageslimit und Tageszusammenfassung. Sichtbare Nebenwirkung: die Zusammenfassung wechselt auf UTC-Mitternacht — auf beiden Servern (Ubuntu, UTC) ändert das faktisch nichts, auf dem Windows-Desktop verschiebt es sich um 1–2 Stunden.

**W10 — toter Allocator fror die Zuteilung ein.** `read_allocation_fraction()` las `trend_fraction` und ignorierte das mitgeschriebene `updated_at` komplett. Stirbt der Allocator, bleibt der letzte Wert für immer gültig; bei eingefrorenen 100 % Trend hätte der DCA-Bot dauerhaft gar nicht mehr gekauft, ohne dass irgendetwas darauf hinweist. Jetzt Frische-Prüfung mit Rückfall auf **0.0** (100 % DCA, 0 % Trend). Bewusst `0.0` und nicht `None`: `None` heißt „kein Allocator", und der Trend-Bot würde dann seinen **vollen** Einstiegsbetrag verwenden — `0.0` lässt DCA regulär kaufen und den Trend-Einstieg entfallen, also die konservativere Richtung.

Die Schwelle (3 × Intervall) kommt aus der State-Datei selbst: der Allocator schreibt sein `interval_minutes` mit. Bewusst so, statt eine zweite Env-Variable auf Konsumentenseite — zwei getrennte Werte für dasselbe Intervall würden auseinanderlaufen, und der Fehler wäre still. Fehlendes oder unlesbares `updated_at` gilt als veraltet, nicht als frisch.

**W13 — kein Lebenszeichen.** Ein abgestürzter Bot fiel nur durch *ausbleibende* Nachrichten auf, und ein stiller Grid-Bot kann „keine Stufe durchquert" oder „seit Dienstag tot" bedeuten — von außen identisch. Neues Modul `heartbeat.py`, eingebunden in alle **vier** `main*.py`: `[HEARTBEAT] <Bot> laeuft, Version <hash>, letzter Zyklus <Zeitpunkt>`, per Default alle 24 h (`HEARTBEAT_INTERVAL_HOURS`, gemeinsame Variable wie die `TELEGRAM_*`-Zugangsdaten, 0 = aus). Der mitgesendete Zyklus-Zeitstempel unterscheidet „Prozess läuft" von „Prozess arbeitet": hängt ein Bot in einem Timeout, bleibt der Zeitstempel stehen. Bewusst **kein** Heartbeat beim Start — ein Bot in einer Neustartschleife würde sonst im Minutentakt „ich lebe" melden, also genau dann, wenn er es nicht tut. Die DCA-Tageszusammenfassung bleibt unverändert daneben bestehen.

**W15 — Grid prüfte den Notaus nicht zwischen mehreren Käufen.** `_process_buys()` prüfte einmal vor der Schleife. Durchquert der Preis in einem Intervall mehrere Stufen (Crash-Szenario), kauft die Schleife mehrere Positionen hintereinander — und genau dann zieht jemand den Notaus; die verbleibenden Käufe liefen trotzdem durch. Jetzt Prüfung zu Beginn jeder Iteration. Die bereits getätigten Käufe stehen zu diesem Zeitpunkt im Ledger, es bleibt nichts unverbucht (eigener Test dafür, damit aus W15 nicht ein K2-artiger unverbuchter Trade wird).

**Tests:** 31 neue in `tests/test_stage_b_safety.py`, mit Negativkontrollen gegen den alten Code für alle vier nicht-trivialen Bereiche (W2, W5, W10, W15 — 13 Fehlschläge gegen den zurückgedrehten Stand). Gesamtstand: **218 Tests, alle grün.**

**Damit bleiben 7 der 18 W-Punkte offen:** W9, W11, W12, W14, W16 (Stufe C, vor dem Echtgeld-Schalter) und W17 (Stufe D) — plus die Infrastruktur-Punkte, die nur per SSH auf VPS und Homeserver prüfbar sind.

### Wichtige Punkte, Stufe C: W12, W11, W9 (16.09.2026)

Die letzten Code-Punkte vor dem Echtgeld-Schalter. W14 und W16 gehören ebenfalls zu Stufe C, waren aber keine Code-Aufgaben — siehe die beiden eigenen Abschnitte unten.

**W12 — „live gehen" war ein Code-Edit, kein Konfigurationsschritt.** `use_testnet: bool = True` stand hart in allen vier Config-Dataclasses, und keine der vier `load_*`-Funktionen las dafür eine Umgebungsvariable. Umschalten hätte geheißen: vier Dateien editieren — ohne Spur in der `.env`, ohne Möglichkeit, es über das Deployment zurückzudrehen, und beim nächsten `git pull` still überschrieben. Jetzt entscheidet **eine** Variable `USE_TESTNET` (Default `true`, bewusst ohne Bot-Präfix: alle vier handeln zwangsläufig auf derselben Börse, und ein halb-live laufendes System wäre schlimmer als beides ganz).

Das Wahrheitswert-Parsing ist für diese eine Variable **streng**, und das ist der eigentliche Punkt: Die übliche Kurzform `os.getenv(...).lower() == "true"` bildet jeden Tippfehler auf `False` ab — `USE_TESTNET=ture` hätte also „nicht Testnet" bedeutet, also live mit echtem Geld, ohne jede Fehlermeldung. Ausgerechnet die Variable mit den teuersten Folgen hätte die schlechteste Fehlerbehandlung gehabt.

Die Sicherheitsschwelle: Bei `false` gibt jeder der vier Prozesse beim Start einen mehrzeiligen Block auf `CRITICAL` aus (`ACHTUNG: LIVE-MODUS MIT ECHTEM GELD AKTIV`) **und** eine Telegram-Nachricht. Bewusst erst nach `init_notifier()` — vorher gäbe es keinen Kanal, und gerade diese Meldung soll nicht nur im Log stehen. Drei Zustände werden unterschieden, nicht zwei: Testnet (eine ruhige INFO-Zeile — der Normalfall darf nicht wie der Ausnahmefall aussehen, sonst gewöhnt man sich an den Alarm), Live mit aktivem Trading, und **Live mit deaktiviertem Trading**. Letzteres ist ausdrücklich ein eigener Fall und kein harmloser Dry-Run: Es sind die Keys des echten Kontos, jeder Lesezugriff geht auf echte Bestände, und ein Umlegen einer einzigen weiteren Variable genügt dann für echte Orders.

**W12, zweiter Teil — Pflichtvariablen-Check.** Geprüft wurden bisher nur API-Key/Secret und ein paar strategiespezifische Plausibilitäten. Neu in `config_guard.py`, von allen vier `load_*` genutzt: leere Angaben (`GRID_SYMBOL=` ist eine Angabe, keine fehlende Zeile — der Default darf sie nicht ersetzen), Intervalle von 0 (ein `time.sleep(0)`-Busy-Loop, der die API im Takt der Schleife befragt), unsinnige Prozentwerte (`GRID_STOP_LOSS_PCT=150` ergäbe eine negative Schwelle — der Stop-Loss wäre still wirkungslos statt abgeschaltet), nicht lesbare Zahlen (die Meldung nennt jetzt die Variable statt nur „could not convert string to float"), aus `.env.example` kopierte Platzhalter (ein `TELEGRAM_BOT_TOKEN=dein_telegram_bot_token` fiel vorher nie beim Start auf, sondern als stilles HTTP 401 bei jedem Versand) und ein leerer Pending-Orders-Pfad, der die K2-Absicherung abschalten würde.

Wichtig war dabei die **Abgrenzung**, wo `0` eine dokumentierte Bedeutung hat: Bei DCA und Grid heißt es „Stop-Loss aus", beim Heartbeat „kein Lebenszeichen" — das bleibt erlaubt. Beim Trend-Bot dagegen ist `TREND_STOP_LOSS_PCT=0` nicht „aus", sondern fatal: `is_stop_loss_hit()` vergleicht dann gegen den Einstiegspreis selbst und schließt jede Position im ersten Zyklus ohne Kursgewinn wieder, inklusive Latch. Drei Bots, dieselbe Zahl, drei verschiedene Bedeutungen — genau deshalb behält jede `load_*`-Funktion ihre eigene Liste, während nur der Mechanismus geteilt wird (gleiche Begründung wie bei `safe_startup_reconciliation()` unter W18: sicherheitsrelevanten Code viermal zu kopieren ist der als N3 kritisierte Weg).

Ebenfalls neu geprüft werden die `*_HALT`-Variablen — allerdings **nur beim Start**. `KillSwitch.is_set()` liest sie zur Laufzeit bewusst weiterhin tolerant: Ein Notaus-Check, der bei einem Tippfehler eine Exception wirft, würde den Bot alle fünf Sekunden sprengen statt ihn zu schützen. Nur ist die Fehlerrichtung dort die unangenehme — `GRID_BOT_HALT=ture` heißt „kein Notaus", während der Mensch, der es getippt hat, vom Gegenteil ausgeht. Der Start ist der einzige Moment, in dem sich das gefahrlos bemerken lässt.

Im **Live-Modus** kommen zwei Pflichten dazu. Erstens Telegram: Ohne Kanal kämen ausgerechnet `[ORDER-UNKLAR]`, `[STOP-LOSS]` und `[HEARTBEAT]` nirgends an — ein Live-Bot, den man nur bemerkt, wenn man von sich aus ins Log schaut, ist kein überwachter Live-Bot. Zweitens müssen alle Werte, die die Positionsgröße bestimmen, ausdrücklich in der `.env` stehen (`DCA_QUOTE_AMOUNT`, `DCA_MAX_DAILY_SPEND`, `GRID_LOWER_LIMIT`, `GRID_UPPER_LIMIT`, `GRID_AMOUNT_PER_LEVEL`, `TREND_AMOUNT_PER_TRADE`) statt auf die Testnet-Defaults zurückzufallen. Die stammen aus einer Phase, in der eine falsche Größe folgenlos war; live sind sie die Stellschraube für die tatsächliche Kapitalbindung, und ein vergessener Eintrag sähe im Log aus wie ein bewusst gewählter Wert — siehe W16, wo genau diese Werte das Thema sind.

Beiläufig geschlossen: Symbol, Betrag, Intervall und Tageslimit des DCA-Bots sind jetzt über die `.env` einstellbar. Er war als einziger der vier ohne diese Möglichkeit — `DCA_SYMBOL` gab es schlicht nicht, das Symbol war ein Code-Default. Die Werte selbst sind unverändert.

**Abbruchverhalten, eine Stufe vor W18.** `load_*()` läuft zwangsläufig vor `setup_logging()`, das seinen Pfad ja aus der Config bezieht. Eine durchgereichte Exception ergäbe einen nackten Traceback und Exit-Code 1 — und `Restart=on-failure` macht daraus eine Neustartschleife, die **nie** zum Erfolg führen kann, weil sich die Konfiguration von allein nicht ändert. Deshalb: klare Meldung auf stderr (landet im journal), Telegram soweit möglich (die Zugangsdaten stehen bereits in der Umgebung, auch wenn der Notifier noch nicht initialisiert ist), und ein regulärer Rücksprung mit Exit-Code 0. Gleiches Muster wie die bestehende Behandlung von `BotAlreadyRunning`.

**W11 — geteiltes Konto ohne Reservierung.** DCA, Grid und Trend teilen sich ein Binance-Konto und handeln dasselbe Symbol, aber jeder führt sein eigenes Ledger: Die Zuordnung „dieses BTC gehört dem Grid-Bot" existiert ausschließlich buchhalterisch, die Börse kennt nur einen Bestand. Vor jedem echten Verkauf wird jetzt gegen den tatsächlichen Kontostand geprüft (`balance_guard.py`, plus zwei neue Lesemethoden in `binance_client.py`).

Zwei Prüfungen mit **bewusst unterschiedlicher Konsequenz**. Die Deckungsprüfung ist hart: Reicht das freie Guthaben für genau diesen Verkauf nicht, wird gar nicht erst verkauft. Die Börse würde ohnehin ablehnen — nur sähe dieser Fehlschlag im Log aus wie ein Netzwerkproblem, obwohl die Ursache feststeht. Die Buchhaltungsprüfung ist weich: Deckt das Konto nicht ab, was das eigene Ledger insgesamt als offen führt, gibt es `ERROR` plus Telegram, aber der einzelne gedeckte Verkauf läuft **trotzdem**. Gleiche Abwägung wie beim Grid-Trendbruch-Stop-Loss, der Verkäufe ebenfalls durchlässt: Ein Verkauf reduziert Risiko und Kapitalbindung, ihn zu blockieren würde das eigentliche Problem nicht lösen, sondern nur Assets stranden lassen.

Die Zuordnung „welche gebundene Menge gehört wem" ist überhaupt nur beantwortbar, weil der **K2-Fix** jeder Order eine selbstvergebene `clientOrderId` mit Bot-Präfix gibt — vorhandene Infrastruktur, keine neue. Eine Order ohne erkennbares Präfix (manueller Handel über die Börsen-Oberfläche) zählt als fremd; das ist die konservative Richtung, sie als eigene zu zählen würde eine echte Diskrepanz verdecken.

Die weiche Prüfung ist bewusst so konstruiert, dass sie **keine Fehlalarme erzeugen kann und dafür nicht jeden Fall erkennt**: Das freie Guthaben enthält auch fremdes, ungebundenes BTC, `free + eigene_gebundene_Menge` ist also eine Obergrenze dessen, was dem prüfenden Bot gehören könnte. Liegt schon diese Obergrenze unter seinem Anspruch, ist die Diskrepanz eindeutig. Das ist die ehrliche Grenze dessen, was ein einzelner Bot feststellen kann, ohne die strikte Trennung der Ledger aufzugeben — fremde Ledger zu lesen wäre die einzige Alternative und widerspricht dem Grundprinzip des Projekts. Laufen alle drei Bots mit der Prüfung, meldet derjenige, der zuerst zu kurz kommt.

Zwei Einbau-Details, die den Unterschied machen. Beim Grid-Bot wird das Guthaben **einmal pro Zyklus** abgefragt, und bereits in diesem Durchlauf verkaufte Mengen werden mitgeführt — sonst hielte die Prüfung dasselbe freie Guthaben für jeden der mehreren Verkäufe erneut für verfügbar und übersähe genau den Fall, für den sie gebaut ist. Beim Trend-Bot läuft sie **nach** `_resolve_stop_order_before_close()`: Bis dahin bindet die eigene Stop-Loss-Order die komplette Positionsmenge, das freie Guthaben wäre systematisch zu klein und jeder Ausstieg fälschlich „ungedeckt". Und weil die Stop-Order zu diesem Zeitpunkt bereits storniert ist, darf der Abbruch kein einfaches `return` sein — er läuft über `_handle_failed_real_sell()`, das die Absicherung neu platziert. Ein `return` hätte die weiterhin offene Position ungeschützt zurückgelassen: exakt der K1-Folgefund, nur über einen neuen Weg hinein.

Ein **nicht abrufbares** Guthaben lässt den Verkauf durch. Ein gescheiterter Abruf ist keine Aussage über das Konto, und einen Stop-Loss-Ausstieg wegen eines Netzwerk-Hängers zu verweigern wäre die deutlich gefährlichere Richtung — dieselbe Haltung wie bei `LOOKUP_FAILED` unter K2.

**W9 — Allocator-Reaktivität, und warum weder (a) noch (b) die Antwort war.** Der Befund war größer als „reaktiver": `TrendSignalGenerator` ist **ereignisgesteuert**, jeder `feed()` rückt die EMAs um eine Periode vor. Der Allocator speiste bei jedem 60-Minuten-Zyklus einen Spot-Ticker ein, also 24 Werte pro Tag in eine auf 20/50 **Tage** ausgelegte Berechnung. Live lief damit faktisch eine EMA(20h)/EMA(50h) — ein *anderer Indikator* als der backgetestete, nicht dieselbe Kurve mit anderer Empfindlichkeit. Dazu zwei Punkte, die im Review-Text nicht standen: `_seed_with_history()` füttert echte Tageskerzen, die EMA war nach jedem Neustart also rund 50 Zyklen lang ein Mischwesen aus beiden Skalen; und `ALLOCATOR_SMOOTHING_PERIOD=24` zählt *Feeds*, entsprach live also rund einem Tag gegenüber `--smoothing-period-days=3.0` im Backtest.

Die naheliegende Lösung (a), `ALLOCATOR_INTERVAL_MINUTES=1440`, hätte zwei Nebenwirkungen gehabt. Erstens leitet die **W10-Frischeprüfung** ihre Schwelle aus genau diesem Wert ab (3 × Intervall, aus der State-Datei selbst) — aus „toter Allocator fällt nach 3 Stunden auf" wäre ein Drei-Tage-Fenster geworden. Ein gerade erst gebauter Sicherheitsmechanismus wäre für eine Genauigkeitsfrage verwässert worden. Zweitens hätte `SMOOTHING_PERIOD=24` dann 24 *Tage* bedeutet, also deutlich träger als der Backtest; (a) war also keine Ein-Zeilen-Änderung, sondern zwei gekoppelte Werte. Lösung (b), es nur zu dokumentieren, hätte die eine Ausnahme dort festgeschrieben, wo das zentrale Projektprinzip („Backtest und Live teilen dieselbe Logik", vgl. `grid_signals.py`/`trend_signals.py`/`order_utils.py`) am meisten zählt — und die Zahlen aus 5a gälten für das Live-System weiterhin nicht.

Umgesetzt wurde stattdessen die **Entkopplung von Feed-Takt und Zyklus-Takt**. Die EMAs bekommen genau einen Tagesschlusskurs pro Kalendertag (UTC), aus derselben Quelle wie Seeding und Backtest (`fetch_historical_klines`) — nicht mehr aus einem Spot-Ticker. `ALLOCATOR_INTERVAL_MINUTES` bleibt bei 60 und bestimmt nur noch, wie oft der Prozess aufwacht, den Zustand mit frischem `updated_at` neu veröffentlicht und den Notaus prüft. Damit stimmen Feed-Kadenz, Eingangsdaten und Glättungsschritte mit dem Backtest überein, **und** die stündliche Frischeprüfung bleibt scharf. Nebeneffekt: Der Hinweis „Näherung für Tagesschlusskurs" im Log entfällt, weil es jetzt der echte Schlusskurs ist; und der Allocator braucht pro Tag einen Klines-Abruf statt pro Stunde einen Ticker-Abruf, also *weniger* API-Last.

`ALLOCATOR_SMOOTHING_PERIOD` ist damit in **Tagen** zu lesen und direkt mit `--smoothing-period-days` vergleichbar — Default entsprechend von 24 auf **3** gewechselt. Neu ist `current_state()` in `trend_signals.py` (der aktuelle Stand ohne neuen Kurs): Ohne sie bliebe nur, für jedes Schreiben einen Kurs einzuspeisen — also genau der Fehler, den W9 behebt. `feed()` endet jetzt mit einem Aufruf dorthin, statt dieselbe Ableitung ein zweites Mal zu enthalten.

**Ein Fehler, den erst der Test zutage gefördert hat:** Der erste Entwurf des Nachhol-Pfads (nach einer Downtime) speiste die versäumten Tage einzeln ein, glättete dann aber n-mal gegen **ein** Ziel — das des letzten Tages. Der Backtest berechnet das Ziel pro Tag. Ein Test, der beide Wege gegeneinanderstellt (fünf Tage am Stück nachholen vs. fünf Tage einzeln durchlaufen), fiel mit 0,969 gegen 0,953 um. Behoben: `_feed_completed_days()` liefert jetzt die Ziel-Zuteilung *je* eingespeistem Tag, der Aufrufer glättet gegen jede einzeln. Genau die Art Abweichung, die sonst nur nach einer Downtime zuschlägt und im Betrieb nie auffällt.

Der **Trend-Bot ist von W9 nicht betroffen**: Sein Zyklus ist bereits 24 h, er feedet also schon einmal pro Tag. Er nutzt nur den Spot-Ticker statt des echten Schlusskurses, was sein Docstring als bewusste Näherung ausweist.

**Einmaliger Übergang beim Deployment:** Die bestehende `allocator_state.json` auf dem Homeserver enthält einen unter dem Stunden-Regime geglätteten Wert. Er wird nicht verworfen (eine geglättete Reihe soll übertragen werden), konvergiert aber über die nächsten Tage mit der neuen Periode. `gap_pct`, `direction` und `raw_target_fraction` sind ab dem ersten Zyklus korrekt skaliert. Da der Opt-in bei DCA/Trend weiterhin deaktiviert ist, hat das ohnehin keine Wirkung auf Orders.

**Tests:** 77 neue in `tests/test_stage_c_safety.py`. Negativkontrollen gegen den zurückgedrehten Stand für alle drei Bereiche, gemessen statt behauptet: striktes Bool-Parsing (alle 4 Testmethoden fallen um), Deckungsprüfung vor dem Verkauf (6 von 13), Feed-Takt des Allocators (3 von 9), `current_state()` (2 von 3). Gesamtstand: **295 Tests, alle grün.**

**Damit sind alle 18 W-Punkte abgearbeitet** — 15 behoben (W1–W8, W10–W13, W15, W18), W14 bewusst zurückgestellt (eigener Abschnitt unten), W16 als Rechenaufgabe beantwortet (eigener Abschnitt unten), W17 bleibt als Stufe D offen. Dazu weiterhin die Infrastruktur-Punkte, die nur per SSH auf VPS und Homeserver prüfbar sind, sowie die zwei Punkte am harten VPS-Vertragsende 12.10.2026 (finaler `data/`-Snapshot, Entfernen des Deploy-Keys).

### Wichtige Punkte, Stufe D: W17 (16.09.2026)

Der letzte offene W-Punkt: die Testabdeckung des `decide_action`-Entscheidungspfads. Reine Testarbeit, keine Änderung an der Produktivlogik — bis auf zwei optionale Parameter in der Test-Basis (`_make_config`/`_make_strategy` nehmen jetzt `**overrides`), damit ein Testfall kurze EMA-Perioden setzen kann.

**Der Befund, nachgemessen statt behauptet.** Vor dieser Runde wurde `decide_action()` in der gesamten Suite **24-mal** aufgerufen — und zwar ausnahmslos mit `confirmed_direction=None`. Kein einziger Aufruf mit „up" oder „down". Die Ursache steht in der Test-Basis von `test_trend_stop_loss.py`: Sie setzt `strategy._seeded = True`, um den Netzwerkzugriff auf die historischen Tageskerzen zu vermeiden. Nebenwirkung: Der `TrendSignalGenerator` bleibt vollständig leer, `feed()` liefert lauter `None`, und damit gibt `decide_action()` per Konstruktion immer `None` zurück. Getestet wurden die *Folgen* einer Entscheidung (`_open_position`, `_close_position` — beide direkt aufgerufen), nie die Entscheidung selbst. Die Zeile ist jetzt mit einem entsprechenden Warnhinweis versehen, damit der nächste Leser nicht in dieselbe Annahme läuft.

**Neue Datei `tests/test_trend_decide_action.py`** (29 Tests), mit synthetischen Preisreihen, die dieselbe Mechanik vollständig durchlaufen: Seeding-Phase, EMA-Fortschreibung, Crossover, Trendstärke-Filter. Bewusst kurze EMA-Perioden (3/5 statt 20/50) — die getestete Logik ist identisch, nur der Vorlauf ist kurz genug, um jeden Schritt von Hand nachzurechnen.

Abgedeckt sind die sechs geforderten Fälle plus vier, die sich beim Bauen als lohnend herausstellten:

| Situation | Erwartung |
|---|---|
| Bestätigt aufwärts, keine Position | `ENTER` |
| Bestätigt aufwärts, Position offen | nichts tun (kein Doppel-Einstieg) |
| Bestätigt abwärts, Position offen | `EXIT_SIGNAL` |
| Bestätigt abwärts, keine Position | nichts tun (long-only, kein Shorting) |
| Abstand unter der Schwelle | nichts tun, in beiden Positionslagen |
| Whipsaw (Crossover ohne Bestätigung) | über die **gesamte** Reihe kein Signal |
| Aufwärts, aber Stop-Loss-Latch gesetzt | nichts tun |
| Abwärts, Position offen, Latch gesetzt | `EXIT_SIGNAL` (die Sperre gilt nur für Einstiege) |
| Vollständiger Zyklus auf/ab | genau ein `ENTER`, genau ein `EXIT_SIGNAL`, in dieser Reihenfolge |
| Seitwärts (flach und gezackt) | nichts tun |

**Jede Preisreihe hat ihren eigenen Prämissen-Test.** Das war die wichtigste Design-Entscheidung an dieser Datei: Ein Test der Form „Signal X führt zu Entscheidung Y" ist auch dann grün, wenn Signal X in Wahrheit nie entstanden ist — und prüft dann nichts. Beim Whipsaw-Fall zählt genau das: Belegt wird, dass die rohen EMAs sich **tatsächlich** kreuzen (Richtung springt von „down" auf „up" und zurück), während der Abstand nie die Schwelle erreicht. Ohne diesen Nachweis würde dieselbe Zusicherung auch von einer Reihe erfüllt, in der sich gar nichts kreuzt. Dasselbe Muster beim Trendstärke-Filter: Die schwache Aufwärtsreihe hat nachweislich die Richtung „up", nur zu wenig Abstand — und eine Gegenprobe zeigt, dass **dieselbe** Reihe mit niedrigerer Schwelle zu einem Einstieg führt. Damit steht fest, dass der Filter gegriffen hat und nicht etwa die Reihe richtungslos war.

**Zweite Hälfte des Befundes: `execute_once()` selbst.** Eine eigene Testklasse lässt den Bot die Reihen Zyklus für Zyklus durchlaufen — ein `execute_once()` pro Kurs, genau wie im Betrieb ein Aufruf pro Tageskerze — ohne den Signalgenerator zu umgehen. Der komplette Pfad Preis → `feed()` → `decide_action()` → `_open_position()`/`_close_position()` läuft damit so, wie er live läuft. Der Vollzyklus führt zu genau einem echten Kauf bei 106,00 und einem echten Verkauf bei 107,00 mit `exit_reason="signal"`; Whipsaw und schwacher Trend erzeugen über alle Zyklen hinweg keine einzige Order.

Dazu drei Fälle, die nur auf diesem Weg prüfbar sind:

- **Interner Stop-Loss schlägt gleichzeitiges Signal.** `execute_once()` prüft `is_stop_loss_hit()` vor `decide_action()`. Damit das überhaupt testbar ist, braucht es einen Kurs, bei dem im **selben** Zyklus beide Bedingungen zutreffen — bei einer langsamen Umkehr feuert der Signal-Exit schon einen Zyklus früher, noch oberhalb der Stop-Schwelle. Gelöst über einen Absturz in einem Schritt (119 → 90 bei Einstieg 106, Schwelle 95,40); dass dort wirklich beides gleichzeitig gilt, ist eigens belegt. Ergebnis: `exit_reason="stop_loss"` und gesetzter Latch.
- **Der Latch sperrt einen späteren Einstieg.** Nach dem Stop-Loss-Exit folgt eine erneute, bestätigte Aufwärtsbewegung — ohne Sperre gäbe es einen zweiten Kauf.
- **Gegenprobe dazu:** Nach einem manuellen Reset führt dieselbe Erholung sehr wohl zu einem neuen Einstieg. Damit ist der Latch als Ursache belegt und nicht etwa ein erschöpfter Signalgenerator.

**Mutationsprobe statt Behauptung.** Ob die Tests etwas prüfen, wurde gemessen: Fünf Mutationen, jede bricht genau eine Regel. Kontrolllauf ohne Mutation: 0 Fehlschläge. Long-only aufgehoben → 3 Testmethoden fallen um; Doppel-Einstieg erlaubt → 2; Signal-Exit entfernt → 4; Stop-Loss-Latch in `decide_action` ignoriert → 1; Trendstärke-Filter deaktiviert → 8.

Der erste Anlauf dieser Messung war selbst fehlerhaft und meldete für jede Mutation dieselben ~46 Treffer, darunter Tests für flache und gezackte Seitwärtsmärkte, die von keiner der Mutationen betroffen sein können. Ursache: Die Mutanten-Signaturen verwendeten andere Parameternamen, die Tests rufen aber mit Schlüsselwörtern auf — es waren durchweg `TypeError` statt echter Fehlschläge. Eine Gleichverteilung über offensichtlich unbeteiligte Tests ist das Warnsignal, an dem so etwas auffällt.

**Ein Nebenbefund aus der korrigierten Messung:** Zwei Regeln in `decide_action()` sind gegenüber `execute_once()` redundant. Die Regel „aufwärts + offene Position → nichts tun" wird dort nie gebraucht, weil `execute_once()` im Zweig mit offener Position ohnehin nur auf `EXIT_SIGNAL` reagiert und `_open_position()` gar nicht erst aufruft. Und die Stop-Loss-Sperre in `decide_action()` läuft leer, weil `execute_once()` `stop_loss_paused=False` hart übergibt und die Pause stattdessen mit einem eigenen, früheren `return` behandelt (nachgewiesen: entfernt man diesen Return, fällt der entsprechende Test um). Beides ist kein Fehler, sondern doppelte Absicherung — festgehalten wird es, weil beide Ebenen jetzt getrennt geprüft werden und deshalb auffällt, wenn eine davon wegfällt.

**Tests:** 29 neue in `tests/test_trend_decide_action.py`. Gesamtstand: **324 Tests, alle grün.**

**Damit sind alle 18 W-Punkte abgeschlossen** — 16 behoben (W1–W13, W15, W17, W18), W14 bewusst zurückgestellt, W16 als Rechenaufgabe beantwortet. Offen bleiben nur noch die Infrastruktur-Punkte, die per SSH auf VPS und Homeserver zu prüfen sind, sowie die beiden Punkte am harten VPS-Vertragsende 12.10.2026 (finaler `data/`-Snapshot, Entfernen des Deploy-Keys).

### W16: Grid-Kapitalbindung gegen den 150-€-Topf gerechnet (16.09.2026)

Keine Code-Änderung und keine Änderung an den Werten — laut 5b ist die Positionsgrößen-Kalibrierung eine bewusste, spätere Entscheidung. Hier steht nur die Rechnung, damit sie vorliegt.

*(Aktualisiert 17.09.2026: Der erste Satz gilt für den Homeserver nicht mehr — die erste Stellschraube aus der Tabelle unten ist dort inzwischen angewendet, siehe „W16 umgesetzt" direkt im Anschluss. Die Rechnung selbst bleibt unverändert stehen, sie ist die Grundlage der Änderung.)*

Die Formel steckt bereits im Code (`grid_strategy.py`, Log-Zeile beim Start): `(Anzahl Stufen − 1) × GRID_AMOUNT_PER_LEVEL`. Die oberste Stufe ist reine Verkaufsstufe, `find_triggered_buy_levels()` iteriert über `levels[:-1]` — es gibt immer eine Kaufstufe weniger als Stufen.

| | Spanne | Abstand | Stufen | Kaufstufen | Betrag/Stufe | Max. Kapitalbindung |
|---|---|---|---|---|---|---|
| **VPS** | 68.000 – 87.585 | 1,5 % | 18 | 17 | 15,00 | **255,00 €** |
| **Homeserver** | 70.000 – 88.829 | 1,5 % | 17 | 16 | 15,00 | **240,00 €** |
| Grid-Topf laut 5b | | | | | | 150,00 € |

**Ergebnis: Die aktuelle Konfiguration passt nicht zum geplanten Topf.** Der VPS liegt 70 % darüber, der Homeserver 60 %.

Datenherkunft, damit klar ist was gemessen und was abgeleitet ist: Die VPS-Zeile ist direkt belegt — dieselbe Konfiguration lief am 10.09. lokal, und `logs/grid_bot.log` enthält wörtlich `Grid initialisiert: 18 Stufen von 68000.00 bis 87585.38 (Abstand 1.50%, max. Kapitalbindung ca. 255.00)`. Die Homeserver-Zeile war zum Zeitpunkt dieser Rechnung **abgeleitet**: 6e protokolliert nur „Grid mit 17 Stufen initialisiert", und 17 Stufen ergeben sich exakt aus den `.env.example`-Werten (70.000–90.000 @ 1,5 %) — plausibel, weil der Homeserver frisch aus dem Repo aufgesetzt wurde. Gegenzuprüfen mit `grep -E 'GRID_(LOWER|UPPER|SPACING|AMOUNT)' .env` bzw. `grep "Grid initialisiert" logs/grid_bot.log`.

*(Aktualisiert 17.09.2026: Die Homeserver-Zeile ist **inzwischen direkt belegt**, der Vorbehalt „abgeleitet" ist damit erledigt. Der Neustart nach der Betragsänderung (siehe „W16 umgesetzt" unten) hat wörtlich geloggt: `Grid initialisiert: 17 Stufen von 70000.00 bis 88828.99 (Abstand 1.50%, max. Kapitalbindung ca. 150.08)`. Bestätigt sind damit die Struktur — 17 Stufen, also 16 Kaufstufen — und die Spanne, deren Obergrenze mit 88.828,99 genau dort liegt, wo die Tabelle sie ausweist. Die 240,00 € der Tabelle waren der Stand mit 15,00 € pro Stufe und sind seit der Änderung historisch; die Rechnung als solche stimmt, nur der Faktor ist ein anderer. Dass die Prüfung überhaupt nötig war, ist der Punkt: Die 9,38 € stehen auf genau dieser Stufenzahl — wären es 18 Stufen gewesen, läge die Bindung bei 17 × 9,38 = 159,46 € und der Topf wäre weiterhin überschritten.)*

Drei Punkte, die an dieser Rechnung wichtig sind:

1. **Die Zahl ist exakt, nicht geschätzt.** `amount_per_level` ist ein *Quote*-Betrag (`quoteOrderQty`), die Bindung ist 17 × 15 USDT unabhängig vom BTC-Kurs.
2. **255 € sind real erreichbar.** Alle Kaufstufen sind gleichzeitig belegt, sobald der Kurs die Spanne einmal von oben nach unten durchläuft, ohne zwischendurch eine volle Stufe zurückzusteigen — ein gewöhnlicher Abverkauf. Der Trendbruch-Stop-Loss deckelt das **nicht**: Er greift erst bei 68.000 × 0,85 = 57.800, und dort sind längst alle Stufen gekauft; er blockiert dann nur noch Käufe, die es gar nicht mehr gibt.
3. **Es gibt keine zweite Bremse.** Der Grid-Bot hat bewusst kein Tageslimit (`grid_config.py` begründet das genau damit: die Stufenzahl sei die Grenze). Stufen × Betrag ist also die einzige Obergrenze — und muss deshalb stimmen. Genau deshalb verlangt der W12-Check diese Werte im Live-Modus als ausdrückliche Angabe.

Stellschrauben, falls 150 € der Zielwert bleibt:

| Stellschraube | VPS (17 Kaufstufen) | Homeserver (16) | Anmerkung |
|---|---|---|---|
| Betrag/Stufe senken | **8,82 €** | **9,38 €** | sicher über dem Binance-Mindestvolumen (`NOTIONAL`, bei BTCUSDT typ. 5 USDT); `place_market_buy()` prüft das selbst |
| Spanne verengen | auf 10 Kaufstufen @ 15 € | | z.B. 68.000–78.900 @ 1,5 % |
| Abstand vergrößern | auf ~2,6 % bei gleicher Spanne | | weniger, dafür größere Trades |

Nur die erste Zeile skaliert ausschließlich die Größe und lässt das Verhalten sonst unverändert. Bei den anderen beiden verschiebt sich, wo und wie oft der Bot überhaupt handelt — die Backtest-Ergebnisse aus Abschnitt 6 („2021 Seitwärts: 109 Trades") gälten dann nicht mehr unverändert.

### W16 umgesetzt (17.09.2026)

Auf dem Homeserver wurde die saubere Stellschraube aus der W16-Rechnung angewendet: `GRID_AMOUNT_PER_LEVEL` von 15,00 € auf **9,38 €** gesenkt (150 € / 16 Kaufstufen). Maximale Kapitalbindung jetzt ca. **150,08 €** statt zuvor 240 € — passt zum 150-€-Grid-Topf aus 5b. Anzahl Stufen und Spanne unverändert, damit bleiben die Backtest-Ergebnisse aus Abschnitt 6 weiterhin gültig (nur die Größe skaliert, nicht das Strategieprofil).

Bewusst nur auf dem Homeserver, nicht auf dem VPS (der zum 12.10. ohnehin abgeschaltet wird). Bereits offene Grid-Positionen behalten ihren ursprünglichen Einsatz (15,00 €), nur neue Käufe nutzen den reduzierten Betrag.

Kein Code-Change, reine `.env`-Anpassung plus Neustart des Grid-Bots.

### W14 — Grid ohne börsenseitigen Stop-Loss: bewusst zurückgestellt (16.09.2026)

**Bewusst KEINE Code-Änderung in dieser Runde.** W14 ist eine eigene Architekturentscheidung, kein Nebenbei-Fix, und wird deshalb hier explizit als zurückgestellt festgehalten statt stillschweigend offen zu bleiben.

**Der Befund:** Der Grid-Bot platziert nie eine exchange-seitige Absicherung. Sein Trendbruch-Stop-Loss (`GridStopLoss` in `grid_risk.py`) ist rein software-intern und tut außerdem etwas anderes, als der Name vermuten lässt: er **blockiert nur neue Käufe** und verkauft offene Positionen ausdrücklich nicht (bewusst so, siehe Docstring dort — Verkäufe reduzieren Risiko, das Blockieren neuer Käufe ebenfalls). Fällt der Prozess aus (Strom, Internet, Absturz), während der Kurs unter die Grid-Untergrenze bricht, liegen bis zu 17 offene Positionen (siehe W16) völlig ungeschützt an der Börse. Der Trend-Bot hat für genau dieses Szenario seit 6f eine echte `STOP_LOSS_LIMIT`-Order; der Grid-Bot hat nichts Vergleichbares.

**Warum das kein kleiner Nachtrag ist:**

- **n parallele Stop-Orders statt einer.** Der Trend-Bot verwaltet genau *einen* Positions-Slot — `_ensure_stop_loss_protection()`, `_check_exchange_stop_loss_fill()`, `_forget_dead_stop_order()` und `_warn_on_partially_filled_stop_order()` sind alle auf diese Annahme gebaut. Für das Grid müsste dieselbe Mechanik pro offener Position laufen, inklusive Zuordnung Order↔Position im Ledger.
- **Kapitalbindung durch die Absicherung selbst.** Eine offene Verkaufs-Order bindet ihre Menge an der Börse (`locked`). Die abgesicherten Positionen wären damit nicht mehr frei verkäuflich: Der reguläre Grid-Verkauf beim Erreichen des Sell-Targets müsste die zugehörige Stop-Order erst stornieren. Das vervielfacht genau die Race Condition, die beim Trend-Bot für einen einzelnen Fall schon aufwendig war (`_resolve_stop_order_before_close`, `uncertain_cycles`, Ground-Truth-Nachfrage statt Fehlercode-Interpretation, siehe 6f).
- **Reconciliation für n Positionen.** Der Startup-Abgleich müsste für jede offene Position prüfen: Stop-Order noch da, gefüllt, tot, teilgefüllt? Der Trend-Bot löst das heute für einen Slot und braucht dafür bereits fünf Methoden und 8 Tests (`DeadStopOrderTestCase`).
- **Konzeptioneller Bruch.** Ein Grid-Trendbruch-Stop ist inhaltlich etwas anderes als ein Positions-Stop: die Schwelle hängt an der *Grid-Untergrenze*, nicht am individuellen Einstiegspreis. Sinnvoller wäre vermutlich **eine** Stop-Order über die Gesamtmenge aller offenen Positionen an der Trendbruch-Schwelle — dann muss aber bei **jedem** Kauf und **jedem** Verkauf die Menge dieser einen Order angepasst (also storniert und neu platziert) werden, und genau dieses Fenster ist wieder ein eigenes Konsistenzproblem der K2-Klasse. Welche der beiden Varianten richtig ist, ist eine Designfrage mit eigenem Backtest-/Testbedarf, keine Implementierungsdetailfrage.

**Was heute stattdessen wirkt** (bewusst als Zwischenstand benannt, nicht als Ersatz): der Trendbruch-Stop-Loss blockt neue Käufe, solange der Prozess läuft; die maximale Kapitalbindung ist durch Stufenzahl × Betrag/Stufe von vornherein begrenzt und damit der Schaden nach oben gedeckelt (siehe W16); Notaus und Heartbeat (W13) machen einen toten Bot innerhalb von 24 h sichtbar.

**Wieder aufzugreifen** als eigener Arbeitsschritt mit eigenem Design, eigenen Tests und einer bewussten Entscheidung zwischen „eine Sammel-Stop-Order" und „n Einzel-Stop-Orders" — nicht als Teil dieser Review-Fix-Runde.

### Sicherheitsreview vollständig abgearbeitet (16.09.2026)

Mit W17 sind **alle 18 „wichtigen" Punkte** aus dem Sicherheitsreview (Claude Opus 5, 15.09.2026) abgearbeitet — 16 behoben, einer bewusst zurückgestellt, einer als Rechenaufgabe beantwortet. Zusammen mit den fünf kritischen Punkten K1–K5 (abgeschlossen am 16.09., siehe oben) ist der Review damit vollständig aufgearbeitet.

| Punkt | Inhalt | Ergebnis |
|---|---|---|
| **W1** | `*_HALT` wirkte erst nach einem Neustart | behoben (Stufe A) |
| **W2** | Jeder Prozessstart löste sofort einen Kauf aus | behoben (Stufe B) |
| **W3** | Tageslimit-Fenster in lokaler Zeit statt UTC | behoben (Stufe B) |
| **W4** | Kein Schutz gegen doppelten Bot-Start | behoben (Lockfile, Nebenprodukt des K2-Fixes) |
| **W5** | Beschädigtes Ledger setzte Limits still zurück | behoben (Stufe B) |
| **W6** | Stop-Loss-Latch hing an einem Logging-Detail | behoben (Stufe A) |
| **W7** | Verschwundene Stop-Order wurde nie erkannt | behoben (Stufe A) |
| **W8** | `PARTIALLY_FILLED` und eine Regel-Divergenz | behoben (Stufe A) |
| **W9** | Allocator-Reaktivität wich vom Backtest ab | behoben (Stufe C) |
| **W10** | Toter Allocator fror die Zuteilung ein | behoben (Stufe B) |
| **W11** | Geteiltes Konto/Symbol ohne Reservierung | behoben (Stufe C) |
| **W12** | Kein Live-Schalter, kein Pflichtvariablen-Check | behoben (Stufe C) |
| **W13** | Kein Lebenszeichen der Bots | behoben (Stufe B) |
| **W14** | Grid ohne börsenseitigen Stop-Loss | **bewusst zurückgestellt** (eigene Architekturentscheidung) |
| **W15** | Grid prüfte den Notaus nicht zwischen mehreren Käufen | behoben (Stufe B) |
| **W16** | Grid-Kapitalbindung gegen den 150-€-Topf | **als Rechnung beantwortet** (keine Wertänderung — bewusste spätere Entscheidung laut 5b) |
| **W17** | Testabdeckung des `decide_action`-Entscheidungspfads | behoben (Stufe D) |
| **W18** | Reconciliation außerhalb von `try/except` | behoben (Stufe A) |

**Testabdeckung über die vier Stufen:** 187 → 218 → 295 → **324 Tests**, alle grün. Kein Testlauf braucht Netzwerkzugriff oder Zugangsdaten.

**Durchgehaltenes Prinzip:** Für jeden nicht-trivialen Fix wurde die Wirksamkeit der Tests **gemessen** statt behauptet — durch Zurückdrehen der jeweiligen Änderung (Stufen A–C) bzw. durch Mutation der geprüften Regel (Stufe D). Ein Test, der auch gegen den alten Stand grün ist, prüft nichts. In Stufe D war die erste Messung selbst fehlerhaft und musste korrigiert werden, bevor sie etwas aussagte; das ist im dortigen Abschnitt festgehalten, weil die Fehlerart (gleichmäßige Treffer über offensichtlich unbeteiligte Tests) das verlässlichste Warnsignal dafür ist.

**Was der Review NICHT ersetzt.** Zwei Dinge bleiben ausdrücklich offen und sind keine Code-Aufgaben:

1. **Die zwei Termine am harten VPS-Vertragsende 12.10.2026**: finaler `data/`-Snapshot (sonst gehen die Testergebnisse verloren) und Entfernen des Claude-Code-Deploy-Keys.
2. **Die Paper-Trade-Phase selbst.** Der Code gilt als review-seitig freigegeben, aber ein freigegebener Code ist keine validierte Strategie. Offen bleiben insbesondere die Kalibrierung von `TREND_STOP_LIMIT_OFFSET_PCT` anhand realer Fill-Daten (siehe 6f, bisherige Stichprobe n=2) und die Positionsgrößen-Festlegung inklusive des in W16 gerechneten Grid-Topfs.

**Für den Echtgeld-Schalter heißt das:** Die technischen Voraussetzungen stehen — `USE_TESTNET=false` ist ein Konfigurationsschritt mit lauter Warnung, Pflichtprüfung und erzwungenen expliziten Positionsgrößen (W12). Die verbleibende Absicherung ist nicht mehr der Code, sondern die Beobachtungszeit.

### Infrastruktur-Härtung auf beiden Servern (16.09.2026)

Direkt per SSH durchgeführt, kein Code-Change im Repo.

**SSH/Netzwerk:**
- Homeserver: `PermitRootLogin no`, `AllowUsers elias` ergänzt (waren zuvor nicht explizit gesetzt). `ufw` aktiviert, nur Port 22 aus dem lokalen Subnetz (192.168.178.0/24) erlaubt.
- VPS: **Echte Sicherheitslücke gefunden** - `sshd_config.d/50-cloud-init.conf` setzte `PasswordAuthentication yes`, wurde alphabetisch VOR der korrigierenden `60-cloudimg-settings.conf` (mit `no`) eingelesen und damit wirksam, obwohl die Projektdoku (6b) "Passwort-Authentifizierung deaktiviert" behauptete. Per `sshd -T` verifiziert, mit neuer `00-hardening.conf` behoben (`PasswordAuthentication no`, `PermitRootLogin prohibit-password`). `ufw` aktiviert (Port 22 von überall, da kein festes Zugriffsnetz).
- Beide: `.env`-Berechtigungen von `644`/`664` auf `600` korrigiert (waren zuvor world-readable bzw. group-writable).

**systemd-Härtung (alle Bot-Services):**
- `WorkingDirectory`, `After=network-online.target`+`Wants=network-online.target`, `StartLimitIntervalSec=600`/`StartLimitBurst=5`, `RestartSec=30`.
- Härtungsdirektiven: `NoNewPrivileges=yes`, `PrivateTmp=yes`, `ProtectSystem=strict` mit `ReadWritePaths` auf `data/`+`logs/`, `CapabilityBoundingSet=` (leer).
- Homeserver: Services laufen als dedizierter Nutzer `elias` (bereits vorher so, `User=elias` in allen vier inkl. Allocator).
- VPS: bewusste Entscheidung, Services weiterhin als `root` laufen zu lassen (kein dedizierter Nutzer angelegt) - Begründung: VPS wird zum 12.10. abgeschaltet, Aufwand für Nutzer-Migration (Verzeichnis verschieben, Berechtigungen, SSH-Keys) steht nicht im Verhältnis zur verbleibenden Laufzeit. Härtungsdirektiven wirken trotzdem, auch ohne dedizierten Nutzer.
- `OnFailure=notify-failure@%n.service` auf allen Services ergänzt: neues Skript `/usr/local/bin/notify-service-failure.sh` + Template-Unit `notify-failure@.service` senden eine Telegram-Nachricht, falls ein Service die Neustart-Grenze erreicht und komplett aufgibt (Fall, in dem der Bot selbst keine Telegram-Nachricht mehr senden könnte). Auf beiden Servern getestet und funktionsfähig.

**Log-Rotation:**
- `logrotate`-Konfiguration (`/etc/logrotate.d/crypto-bot`) auf beiden Servern: wöchentlich, 8 Wochen Aufbewahrung, `copytruncate` (nötig, da die Bots ihre Log-Dateien durchgehend offen halten).

**Backup/Snapshot:**
- Homeserver: TrueNAS Periodic Snapshot Task für `volume1/VM/crypto_bot_vm-ipgehi` eingerichtet - täglich um Mitternacht, 4 Wochen Aufbewahrung. Erster manueller Snapshot bereits erstellt.
- VPS: kein laufendes Snapshot-Äquivalent eingerichtet (Contabo-VPS), stattdessen der bereits geplante finale `data/`-Snapshot vor dem 12.10. (siehe 6c/6e).

Damit sind alle Infrastruktur-Punkte aus dem Sicherheitsreview abgeschlossen. Offen bleiben nur die zwei terminlich an den 12.10. gebundenen Punkte: finaler VPS-Snapshot und Entfernen des Deploy-Keys beim Decommissioning.

### Grid-Bot: Request-Timeout 10 → 20 Sekunden (25.09.2026)

**Beobachtung.** Nachts kamen vereinzelt `[GRID-FEHLER]`-Meldungen der Form `HTTPSConnectionPool(host='testnet.binance.vision', port=443): Read timed out. (read timeout=10)`. Das Testnet antwortete in diesen Fällen durchaus, nur knapp langsamer als das Zeitfenster, das python-binance standardmäßig lässt (`Client.REQUEST_TIMEOUT` = 10 s). Der Bot selbst hat richtig reagiert: Zyklus abgebrochen, geloggt, gemeldet, nächster Zyklus lief normal. Es waren also Fehlalarme und kein Fehlverhalten.

**Nur der Grid-Bot war betroffen, und das liegt an der Abfragehäufigkeit, nicht am Code.** Alle vier Prozesse nutzen denselben `TradingClient` und damit denselben Timeout. Der Grid-Bot fragt aber alle 5 Minuten ab, also 288-mal am Tag; DCA und Trend fragen einmal am Tag ab. Eine nächtliche Verlangsamung von ein paar Minuten trifft deshalb fast zwangsläufig einen Grid-Zyklus und nur mit geringer Wahrscheinlichkeit einen DCA- oder Trend-Zyklus. Erwischt sie einen davon, wären sie genauso betroffen.

**Keine offizielle Testnet-Wartungszeit gefunden.** Für `testnet.binance.vision` ist kein festes, wiederkehrendes Wartungsfenster dokumentiert. Wartungen und Daten-Resets werden nur im Einzelfall angekündigt, auf der Testnet-Startseite und im Testnet-CHANGELOG des Repos `binance/binance-spot-api-docs`. Die nächtlichen Timeouts lassen sich damit keiner planmäßigen Wartung zuordnen. Sie werden als gelegentliche Verlangsamung des Testnets behandelt, nicht als Termin, um den herum man planen könnte.

**Umgesetzt.** `TradingClient` nimmt einen optionalen Parameter `request_timeout_seconds` an und reicht ihn als `requests_params={"timeout": …}` an python-binance weiter. Ohne den Parameter bleibt alles wie bisher, und das ist der Fall für DCA, Trend und Allocator. Gesetzt wird er nur in `main_grid.py` (`REQUEST_TIMEOUT_SECONDS = 20`). Kein Retry und keine sonstige Logik, nur der eine Wert. Die Start-Logzeile nennt den Timeout jetzt mit (`Binance-Client initialisiert (testnet=True, Request-Timeout 20 s)`), damit sich auf dem Server per `journalctl` prüfen lässt, dass der neue Stand läuft.

Drei Eigenschaften, die man kennen sollte:

- Der Wert gilt für **jeden** Request dieses Clients, auch für den `ping()`, den der Konstruktor von python-binance selbst absetzt, sowie für Order- und Status-Abfragen.
- Eine einzelne Zahl setzt bei `requests` **Verbindungs- und Lese-Timeout gemeinsam** auf 20 s.
- Ein Zyklus kann im ungünstigsten Fall entsprechend länger hängen. Bei 5-Minuten-Takt ist das unkritisch. Der Notaus wird unverändert vor dem Zyklus, vor jedem Kauf und im Wartetakt geprüft.

Nebeneffekt in die richtige Richtung: Bei Order-Requests führt ein Timeout über den K2-Pfad zu einer Ground-Truth-Nachfrage und im ungünstigsten Fall zu `[ORDER-UNKLAR]`. Weniger Timeouts heißt dort weniger ungeklärte Orders.

**Bewusst nur beim Grid-Bot.** Projektweit zu vereinheitlichen wäre ebenso vertretbar gewesen (DCA und Trend hängen am selben Wert). Es fehlte aber der Anlass: Dort gab es keine Fehlalarme, und ein ausgefallener Zyklus kostet bei DCA/Trend höchstens eine Verschiebung um einen Tag. Ein Test hält die Beschränkung fest, damit eine spätere Vereinheitlichung bewusst geschieht und nicht nebenbei.

**Tests:** 4 neue in `tests/test_request_timeout.py`, Gesamtstand **561, alle grün**. Geprüft wird der Wert dort, wo er wirkt: Unter dem `TradingClient` läuft ein **echter** `binance.client.Client`, ersetzt ist nur `requests.Session.get`. Ping, ein öffentlicher und ein signierter Request tragen nachweislich `timeout=20`. Ohne den Parameter tragen alle drei `timeout=10`, und diese Zahl steht bewusst als Literal im Test, weil sie die Prämisse der Änderung ist. Ein Test, der nur prüft, ob `requests_params` übergeben wurde, bliebe grün, falls ein python-binance-Update den Parameter still ignoriert. Dazu kommen die Verdrahtung (`main_grid.main()` legt den Client tatsächlich mit 20 an) und die Abgrenzung (DCA, Trend und Allocator übergeben nichts). Wirksamkeit gemessen, Kontrolllauf 0 Fehlschläge, alle 4 Mutationen gefangen: `requests_params` nie gesetzt → 1 Testmethode (3 Subtests), Default ebenfalls 20 → 1 (3 Subtests), `main_grid` übergibt nichts → 1, Wert 10 statt 20 → 1.

> **Nachtrag 25.09.2026: Auswertung der Fehlerzeitpunkte.** Die Fehlerzeitpunkte wurden im Nachhinein ausgewertet. Sie präzisieren zwei Aussagen oben; die ursprünglichen Absätze bleiben stehen.
>
> **Befund:**
> - **6 von 7 Vorfällen** liegen im engen Fenster **00:34–00:40 UTC** (02:34–02:40 Uhr deutscher Sommerzeit), verteilt über 6 verschiedene Tage. Ein Ausreißer liegt bei 09:13 UTC.
> - Die erste Vermutung waren lokale Timer auf dem Homeserver (`logrotate`, `dpkg-db-backup`). Sie ist **geprüft und widerlegt**: Diese laufen um 00:00–00:07 UTC, also 30–40 Minuten vor dem Fenster.
> - **Der VPS zeigt im selben Zeitraum keinen einzigen Read-Timeout.** Das Phänomen betrifft nur den Homeserver.
>
> **Präzisierung von „Nur der Grid-Bot war betroffen, und das liegt an der Abfragehäufigkeit“:** Die Abfragehäufigkeit erklärt, warum es auf dem Homeserver den Grid-Bot trifft und nicht DCA oder Trend. Sie erklärt aber **nicht**, warum der VPS verschont bleibt: Dessen Grid-Bot fragt ebenfalls alle 5 Minuten ab, und zwar denselben öffentlichen Ticker-Endpunkt. In einem 6-Minuten-Fenster liegt bei 5-Minuten-Takt zwangsläufig mindestens eine Abfrage.
>
> **Präzisierung von „keine offizielle Wartungszeit, gelegentliche Verlangsamung“:** Eine zufällige Verlangsamung ist es nicht. Ein Fenster, das an sechs Tagen auf wenige Minuten genau wiederkehrt, ist ein regelmäßiger Vorgang. Er liegt allerdings nicht beim Testnet, sondern am Internetanschluss des Homeservers (siehe Ursache unten).
>
> **Ursache geklärt: nächtliche Zwangstrennung des Internetanschlusses.** Das Ereignisprotokoll der FritzBox zeigt jede Nacht eine vom Router ausgelöste Trennung („Die Internetverbindung wird kurz unterbrochen, um der Zwangstrennung durch den Anbieter zuvorzukommen“). Der Anschluss ist 1&1 über DTAG-Infrastruktur mit DS-Lite (LineID `1UND1.DEU.DTAG`). Die Zeitpunkte der letzten sechs Nächte in Ortszeit (MESZ):
>
> | 20.09. | 21.09. | 22.09. | 23.09. | 24.09. | 25.09. |
> |---|---|---|---|---|---|
> | 02:41:08 | 02:39:53 | 02:38:51 | 02:37:47 | 02:36:41 | 02:35:27 |
>
> In UTC ist das 00:35–00:41, also dasselbe Fenster wie die Fehlerzeitpunkte (00:34–00:40 UTC, bis auf etwa eine Minute deckungsgleich). Die Trennung wandert um gut eine Minute pro Tag nach vorn. Das ist typisch dafür, dass der Router sich kurz vor Ablauf der 24 Stunden seit der letzten Einwahl neu verbindet. Bei jeder Trennung wechseln die IPv4-Anbindung (DS-Lite/AFTR) und das IPv6-Präfix vollständig, die Verbindung ist für mehrere Sekunden komplett weg.
>
> Damit ist auch der VPS-Befund erklärt: Der VPS hat keinen Heimanschluss mit Zwangstrennung dazwischen. Die Hypothese eines Wartungsvorgangs bei `testnet.binance.vision` ist damit **hinfällig**, die Frage nicht mehr offen. Der Ausreißer um 09:13 UTC passt nicht in dieses Muster. Er bleibt ein Einzelfall ohne zugeordnete Ursache.
>
> **Was das für den 20-Sekunden-Timeout heißt:** Die Annahme hinter der Änderung („das Testnet antwortet, nur knapp zu langsam“, siehe „Beobachtung“ oben) trifft nicht zu. Die Verbindung ist in diesen Momenten vollständig weg. Für den typischen Ablauf hilft ein längerer Timeout **voraussichtlich gar nicht**, nicht nur teilweise. Im Einzelnen:
>
> - **Die Verbindung ist dauerhaft tot.** Eine Anfrage, deren TCP-Verbindung noch über die alte Adresse lief, bekommt nach dem Adresswechsel nie wieder eine Antwort. Das gilt auch für eine Verbindung, die python-binance über seine `requests`-Session wiederverwendet. Sie endet deshalb in jedem Fall als `Read timed out`, nur eben nach 20 statt nach 10 Sekunden.
> - **Warum die Meldung trotzdem „Read timed out“ heißt, obwohl die Leitung nicht langsam, sondern weg ist:** Die Verbindung selbst stand ja, gewartet wird auf eine Antwort, die nicht mehr kommen kann.
>
> Helfen würde ein längerer Timeout nur in dem schmalen Fall, dass eine Anfrage genau in den wenigen Sekunden der Unterbrechung auf eine noch intakte Verbindung trifft. Die Erhöhung schadet trotzdem nicht und bleibt bestehen.
>
> Entscheidend ist ohnehin der bestehende Zyklus-Mechanismus: Ein fehlgeschlagener Zyklus wird geloggt und gemeldet, der nächste läuft normal. Laut Logs der letzten Tage gab es keinen Fall, in dem zwei aufeinanderfolgende Zyklen fehlschlugen. Ein Codeänderungsbedarf besteht deshalb nicht.
>
> Nachprüfbar bleibt die Einordnung nach dem Deployment: Treffer für `grep "read timeout=20" logs/grid_bot.log` im Fenster der Zwangstrennung bestätigen, dass der längere Timeout diesen Fall nicht abfängt.

### Echte Position bei deaktiviertem Trading: das Spiegelbild zu K4 (25.09.2026)

Gefunden bei der Überprüfung des Grid-Codes im Zuge der Timeout-Änderung. K4 hatte den einen Fall abgesichert: Eine **Dry-Run-Position** wird nach dem Umschalten auf Live nie echt verkauft. Den umgekehrten Fall, eine **echte Position** bei `*_BOT_ENABLE_TRADING=false`, hatte niemand betrachtet. Beim Grid-Bot war er sogar per Test festgeschrieben, mit der Begründung „unkritisch, da keine Order platziert wird“. Für die Börse stimmte das, für das Ledger nicht.

**Grid.** `place_market_sell()` gibt im Dry-Run `None` zurück. Die K1-Prüfung (`order is None and trading_enabled`) greift dort nicht, der Code rechnete also einen Erlös aus `quantity * price` aus und schloss die Position. Danach lag das BTC weiter an der Börse, während das Ledger „verkauft“ behauptete. Die Stufe galt als frei und wurde beim nächsten Durchqueren erneut gekauft. Der Bestandsabgleich sah nichts, denn er meldet nur ein Ledger, das **mehr** beansprucht, als da ist, nicht eines, das weniger beansprucht. Und die erfundene `realized_pnl` stand in einem Eintrag mit `dry_run: false`, also genau in den Daten, die Dashboard-App und Steuer-Export als echten Verkauf lesen.

**Trend, schwerer.** Dieselbe Logik in `_close_position()`, aber vorher lief `_resolve_stop_order_before_close()`, und `cancel_order()` prüfte `trading_enabled` nicht. Ein fälliger Ausstieg im Dry-Run stornierte deshalb die **echte** Stop-Order an der Börse und buchte die Position anschließend als geschlossen. Ergebnis: echtes BTC, weder im Ledger noch durch eine Stop-Order abgesichert.

**Realistischer Auslöser:** Auf dem Homeserver liegen echte Positionen. Wer dort zum Pausieren `*_BOT_ENABLE_TRADING=false` setzt, statt den Notaus zu nutzen, löst genau das aus.

**Umgesetzt:**

- **Grid** (`_process_sells`): Neuer Zweig direkt nach der Prüfung auf ein fehlendes `dry_run`-Feld. Eine echte Position bei deaktiviertem Trading wird weder verkauft noch gebucht, `place_market_sell()` wird gar nicht aufgerufen. Die Position bleibt offen, ihre Stufe belegt. Meldung `[GRID-VERKAUF-GESPERRT]`: ins Log in jedem Zyklus, per Telegram einmal pro Position und Prozesslauf. Dafür gibt es eine eigene Menge statt `_failed_sell_notified`, weil eine frühere Sperr-Meldung sonst später eine echte Fehlschlag-Meldung derselben Position verschlucken würde.
- **Trend** (`_close_position`): Derselbe Zweig, aber **vor** dem Regel-Abruf und vor `_resolve_stop_order_before_close()`. Also kein Stornieren, kein Verkauf, kein `record_exit` und kein Stop-Loss-Latch, weil kein Ausstieg stattgefunden hat (gleiche Logik wie bei K1). Die Stop-Order an der Börse bleibt liegen und schützt die Position weiter. Meldung `[TREND-AUSSTIEG-GESPERRT]` bei jedem Versuch, beim 24-Stunden-Takt also höchstens einmal am Tag. Die Meldung sagt, ob eine Stop-Order besteht.
- **Zweite Sicherung in `binance_client.cancel_order()`:** Bei deaktiviertem Trading wirft die Methode eine Exception, bevor irgendetwas an Binance geht. Das trifft keinen legitimen Fall, denn Stop-Orders haben nur echte Positionen, und die fasst die Strategie im Dry-Run jetzt nicht mehr an. Die Sicherung ist für einen künftigen Aufrufer da, der die Prüfung vergisst. `None` wäre die falsche Antwort gewesen: Die aufrufende Seite liest das als fehlgeschlagene Stornierung und fiele in den `uncertain`-Pfad. Die Exception bricht den Zyklus dagegen laut mit `[TREND-FEHLER]` ab, bevor etwas storniert oder gebucht ist.

**Mitbehoben: `_ensure_stop_loss_protection()` im Dry-Run.** Die Methode stieg bei `not trading_enabled` sofort aus. Verschwand die Stop-Order einer echten Position, während der Bot auf Dry-Run stand, wurde das weder gezählt noch gemeldet, und die Telegram-Meldung zur verschwundenen Order behauptete sogar „Der Bot platziert automatisch Ersatz“. Jetzt:

- Für eine echte Position ohne `stop_loss_order_id` zählt `unprotected_cycles` auch im Dry-Run hoch. Ab derselben Schwelle wie sonst (3 Zyklen) kommt `[TREND-WARNUNG]`, mit dem Grund „Trading ist deaktiviert“. Es wird nur nichts platziert.
- Die Schwelle bleibt bewusst bei 3: Der realistischste Weg in diesen Zustand, eine verschwundene Stop-Order, meldet sich in `_forget_dead_stop_order()` ohnehin sofort. Deren Text sagt im Dry-Run jetzt, dass **kein** Ersatz möglich ist, solange Trading aus ist.
- Der gesperrte Ausstieg ruft die Methode ebenfalls auf, denn auch dort überlebt die Position den Zyklus. Der Grund, warum sie sonst erst nach den Ausstiegs-Entscheidungen läuft (eine neue Order unter der Stop-Schwelle würde abgelehnt), gilt hier nicht: im Dry-Run wird nichts platziert.
- Zählung und Meldung stehen jetzt in einer gemeinsamen Methode `_count_unprotected_cycle()` mit dem Grund als Parameter. Beide Ursachen („Neuplatzierung gescheitert“ und „Trading aus“) teilen damit Zähler, Schwelle und die bestehende Entwarnung. Wird Trading später eingeschaltet, platziert der erste Zyklus die Order, setzt den Zähler zurück und entwarnt.
- **Fehlendes `dry_run`-Feld:** Die Methode prüfte `open_trade.get("dry_run")`, ein fehlendes Feld galt also als „echt“. Mit Trading an hätte eine Position unbekannter Art damit eine echte Stop-Order bekommen, gegen die „nicht raten“-Regel des übrigen Projekts. Jetzt kommt `[TREND-POSITION-UNKLAR]`, ohne Platzieren und ohne Zählen, wie im Ausstiegspfad.

**Tests:** 17 neue. Einer davon ersetzt einen bestehenden Test, und ein weiterer bestehender Test ist angepasst – beide hatten das alte Verhalten festgeschrieben. Gesamtstand **577 (561 − 1 + 17), alle grün**.

- **Ersetzt bzw. angepasst:** Der Grid-Test „echte Position im Dry-Run wird geschlossen“ ist durch sein Gegenteil ersetzt. Beim Trend-Test „Dry-Run-Modus platziert keine Stop-Order“ bleibt die Prüfung „keine Order“, der Zähler ist jetzt 1 statt 0.
- **Grid:**
  - Position bleibt offen, `realized_pnl`, `sell_price` und `sold_at` bleiben `None`.
  - Die Stufe bleibt belegt und wird nicht erneut gekauft. Die Prämisse ist eigens belegt: ohne die Position würde genau diese Stufe gekauft.
  - Log in jedem Zyklus, Telegram einmal.
  - Gegenprobe: dasselbe Ledger mit Trading an wird regulär verkauft.
  - Abgrenzung: eine Dry-Run-Position wird weiterhin simuliert geschlossen.
- **Trend:**
  - Signal-Ausstieg und interner Stop-Loss über `execute_once()` lassen Position und Stop-Order unberührt (`cancel_calls == []`, Order weiter `NEW`, kein Latch).
  - Gegenprobe mit Trading an: stornieren und verkaufen wie bisher.
  - Zusatzpunkt: Zähler 1/2/3 mit Telegram genau beim dritten Zyklus; der gesperrte Ausstieg zählt mit; verschwundene Order im Dry-Run mit korrigiertem Text; Entwarnung nach dem Einschalten; Dry-Run-Position zählt nicht; fehlendes `dry_run`-Feld bekommt keine Order.
- **Client:** zwei Tests am echten `TradingClient` für die zweite Sicherung, dazu die Gegenprobe mit Trading an.
- **Fake-Client:** `FakeTradingClient.cancel_order` bildet die neue Sicherung nach, wie der Fake auch sonst den echten Client nachbildet.

**Wirksamkeit gemessen,** Kontrolllauf 0 Fehlschläge, alle 10 Mutationen gefangen:

| Mutation | Ergebnis |
|---|---|
| Grid-Sperre entfernt | 4 Tests schlagen fehl |
| Grid-Telegram ohne Mengenlimit | 1 |
| Trend-Sperre entfernt | 2 Tests brechen mit Fehler ab |
| Trend-Sperre erst nach dem Stornieren | 2 Tests brechen mit Fehler ab |
| Sicherung in `cancel_order` entfernt | 1 |
| Dry-Run steigt in `_ensure_stop_loss_protection` wieder still aus | 5 |
| Dry-Run versucht zu platzieren | 4 |
| gesperrter Ausstieg zählt nicht | 1 |
| alter Ersatz-Text im Dry-Run | 1 |
| fehlendes `dry_run` gilt wieder als echt | 1 |

Die beiden Trend-Sperren-Mutationen erscheinen als Fehlerabbruch statt als Fehlschlag, weil dann die zweite Sicherung im Fake-Client auslöst. Auch das ist eine Messung: Beide Ebenen greifen unabhängig voneinander.

### Restpunkte der Code-Überprüfung vom 25.09.2026

Die Punkte, die nach Priorität 1 („Echte Position bei deaktiviertem Trading“, direkt oben) offen waren. Jeder wurde einzeln vorgelegt und freigegeben.

#### Priorität 2: Heartbeat meldet nur noch erfolgreiche Zyklen (25.09.2026)

**Befund.** Alle vier `main*.py` setzten `last_cycle_at` nach jedem Schleifendurchlauf auf „jetzt“, auch wenn `execute_once()` mit einer Exception abgebrochen war. Der Zeitstempel ist laut `heartbeat.py` genau dafür da, „Prozess läuft“ von „Prozess arbeitet“ zu unterscheiden. Ein Bot, dessen Zyklen alle scheitern, sah im Heartbeat trotzdem aus wie ein gesunder. Nebenbei stand die Variable innerhalb der Schleife, ein Zeitpunkt aus früheren Zyklen wurde also nie behalten.

**Umgesetzt.** `last_cycle_at` beginnt vor der Schleife mit `None` und wird nur im `else`-Zweig des `try` gesetzt, also nur nach einem Zyklus ohne Exception. `None` heißt „in diesem Prozesslauf noch kein erfolgreicher Zyklus“. Ein Zyklus, der bewusst nichts tut (DCA mit ausgelöstem Stop-Loss oder erreichtem Tageslimit, Grid ohne durchquerte Stufe), zählt als erfolgreich: Der Bot hat gearbeitet und entschieden. Der Notaus-Pfad (`BotHalted`) beendet die Schleife wie bisher, ohne Heartbeat.

Die Nachricht sagt jetzt, was sie weiß: `letzter erfolgreicher Zyklus <Zeitpunkt>` statt `letzter Zyklus`, und `noch kein erfolgreicher Zyklus` statt `noch kein abgeschlossener Zyklus`. Ein Fehlzyklus ist durchaus „abgeschlossen“, der alte Text hätte nach dem Fix also missverständlich gewirkt.

**Einordnung zur nächtlichen Zwangstrennung.** Der Fix macht den Zeitstempel korrekt. Für den einzelnen nächtlichen Fehlzyklus des Grid-Bots ist die sichtbare Wirkung aber klein: Der Heartbeat geht nur einmal pro 24 Stunden raus, nach dem ersten Zyklus, in dem das Intervall abgelaufen ist. Nur wenn das ausgerechnet der gescheiterte Zyklus ist, zeigt die Nachricht jetzt den Zyklus fünf Minuten davor statt „jetzt“. Seinen eigentlichen Wert hat der Fix bei einer **länger** anhaltenden Störung: Scheitert jeder Zyklus über Stunden, steht in der nächsten Heartbeat-Nachricht ein entsprechend alter Zeitpunkt statt eines frischen.

**Tests:** 16 neue in `tests/test_heartbeat_last_cycle.py`, zwei bestehende in `test_stage_b_safety.py` auf den neuen Nachrichtentext angepasst. Gesamtstand **593, alle grün**. Geprüft wird die echte `main()` jedes der vier Bots über mehrere Zyklen, ersetzt sind nur Außenwelt und Uhr. Die Stelle existiert viermal fast identisch, und der realistische Fehler ist, dass eine davon abweicht. Je Bot vier Aussagen: erster Zyklus scheitert → `None`; Erfolg, dann zwei Fehlschläge → Zeitstempel bleibt stehen; Erfolg, Fehlschlag, Erfolg → der zweite Erfolg setzt neu; und als Gegenprobe zwei Erfolge → zwei verschiedene Zeitstempel. Ohne diese Gegenprobe wäre „bleibt stehen“ auch grün, wenn die Test-Uhr gar nicht weiterliefe. Die Uhr ist dafür ersetzt, damit „gleich“ wirklich „nicht neu gesetzt“ bedeutet und nicht „in derselben Mikrosekunde“.

**Wirksamkeit gemessen.** Kontrolllauf 0 Fehlschläge. Das alte Verhalten (Zeitstempel unbedingt vor `maybe_send`) je Einstiegspunkt einzeln wiederhergestellt: DCA, Grid, Trend und Allocator jeweils 3 Fehlschläge. Das sind genau die drei Tests mit Fehlzyklus; die Gegenprobe bleibt erwartungsgemäß grün.

#### Priorität 3: Mengenlimit für `[GRID-FEHLER]` (25.09.2026)

**Befund.** `main_grid.py` schickte bei jedem fehlgeschlagenen Zyklus `[GRID-FEHLER]` per Telegram. Durch die nächtliche Zwangstrennung ist der praktische Schaden heute klar umrissen: eine Meldung pro Nacht. Bei einer tatsächlich längeren Störung (Internet weg, Testnet down) wären es aber zwölf identische Meldungen pro Stunde gewesen.

**Umgesetzt.** Neue kleine Klasse `CycleErrorNotifier` in `main_grid.py`, nach dem Muster von `_report_failed_sell` („einmal pro Lauf“), nur mit Reset bei Erfolg:

- Die erste Meldung eines Fehlertyps geht per Telegram raus. Sie kündigt dabei an, dass weitere gleichartige Fehler bis zum nächsten erfolgreichen Zyklus nur im Log landen.
- Weitere Fehlschläge desselben Typs landen nur im Log, mit der Zahl der Fehlzyklen in Folge. Der vollständige Traceback jedes Fehlschlags steht dort unverändert.
- Nach einem erfolgreichen Zyklus ist alles zurückgesetzt, und die Erholung wird mit der Zahl der Fehlzyklen geloggt. Der nächste Fehler, etwa in der folgenden Nacht, wird also wieder gemeldet.
- **„Fehlertyp“ ist die Exception-Klasse.** Wird aus dem Timeout mitten in einer Störung ein Verbindungsfehler (`ReadTimeout` → `ConnectionError`), ist das eine neue Information und geht raus. In einer schlechten Nacht können es damit zwei Meldungen statt einer sein.

Bewusst nur beim Grid-Bot: DCA und Trend laufen einmal am Tag, dort ist jeder Fehlschlag ohnehin höchstens eine Meldung pro Tag. Der Allocator (stündlich) hätte bei einer längeren Störung dasselbe Muster mit einer Meldung pro Stunde; er war nicht Teil des Befunds und ist nicht angefasst. Eine Entwarnung per Telegram nach der Erholung gibt es ebenfalls bewusst nicht, weil sie nicht gefordert war. Ob die Störung vorbei ist, zeigen das Log und seit Priorität 2 auch der Heartbeat-Zeitstempel.

**Tests:** 10 neue in `tests/test_grid_cycle_error_notification.py`, Gesamtstand **603, alle grün**. Sechs prüfen die Regel direkt an `CycleErrorNotifier` (erste Meldung, Unterdrückung samt Log-Zeile, Reset nach Erfolg, neuer Typ mitten in der Serie, Erholungs-Log, kein Log im Normalfall). Vier laufen durch die echte `main_grid.main()`, darunter das konkrete Nachtszenario (Erfolg, Erfolg, ein Timeout, Erfolg, Erfolg → genau eine Meldung) und der Nachweis, dass jeder Fehlzyklus weiterhin mit Traceback im Log steht. Als Fehler dienen die `requests`-Exceptions, die bei der Zwangstrennung tatsächlich auftreten.

**Wirksamkeit gemessen.** Kontrolllauf 0 Fehlschläge, alle 6 Mutationen gefangen:

| Mutation | Ergebnis |
|---|---|
| altes Verhalten, jeder Fehlzyklus per Telegram | 2 |
| kein Reset bei Erfolg | 2 |
| Sperre für alle Typen statt pro Typ | 1 |
| `main()` ruft `report_success()` nicht auf | 1 |
| unterdrückter Fehler wird nicht geloggt | 1 |
| erster Fehler wird nicht gemeldet | 8 |

**Nachtrag (25.09.2026): auch beim Allocator.** Nach Vorlage ausdrücklich erweitert. Der Allocator war nicht Teil des Befunds, hat aber strukturell dasselbe Problem: stündlicher Takt, dieselbe mögliche nächtliche Störung, bei einer längeren Störung also eine `[ALLOCATOR-FEHLER]`-Meldung pro Stunde. Der Satz oben, der Allocator sei „nicht angefasst“, ist damit überholt.

Dafür ist `CycleErrorNotifier` aus `main_grid.py` in ein eigenes Modul `dca_bot/cycle_errors.py` umgezogen. Telegram-Marker und Zyklusname sind jetzt Parameter, die Regel ist unverändert. Dieselbe Logik zweimal zu implementieren wäre der als N3 kritisierte Weg. Die Allocator-Meldung heißt jetzt `[ALLOCATOR-FEHLER] Unerwarteter Fehler im Allocator-Zyklus: …` statt `[ALLOCATOR-FEHLER] Unerwarteter Fehler: …`, mit demselben Hinweis auf die Sperre wie beim Grid-Bot. Beim Verzicht auf eine Entwarnung per Telegram bleibt es für beide Prozesse, auch das nach Rückfrage bestätigt.

Die Testdatei heißt entsprechend `tests/test_cycle_error_notification.py`. Die Unit-Tests prüfen die gemeinsame Klasse, die vier `main()`-Tests laufen über eine gemeinsame Basis einmal für den Grid-Bot und einmal für den Allocator. Dazu kommt eine Prüfung, dass jede Meldung den richtigen Marker trägt. Gesamtstand **607, alle grün**. Wirksamkeit erneut gemessen, Kontrolllauf 0 Fehlschläge, alle 9 Mutationen gefangen: je Prozess das alte Verhalten (4) und ein fehlender `report_success()`-Aufruf (1); Allocator mit dem Grid-Marker (4); an der Klasse kein Reset (3), Sperre für alle Typen (1), Unterdrückung ohne Log (1), erster Fehler nicht gemeldet (12).

#### Priorität 4: Füllpreis statt Tickerpreis im Grid-Ledger (25.09.2026)

**Befund.** Bei echten Grid-Orders standen als `buy_price` und `sell_price` die Tickerpreise, die der Bot *vor* der Order abgefragt hatte, nicht der tatsächliche Füllpreis. Der Reconciliation-Pfad (`_record_reconciled_buy`/`_record_reconciled_sell`) nahm dagegen schon immer den echten Füllpreis über `average_fill_price()`. Die PnL war nicht betroffen, sie rechnet mit `quantity`, `quote_spent` und dem gemeldeten Erlös. Die angezeigten Preise waren aber ungenau, und genau die lesen Dashboard-App und Steuer-Export.

**Umgesetzt.** Im direkten Kauf- und Verkaufspfad von `grid_strategy.py` kommt der Preis einer echten Order jetzt aus der Order-Antwort (`average_fill_price(order, fallback=price)`, also `cummulativeQuoteQty / executedQty`). Das ist dieselbe Funktion wie im Reconciliation-Pfad, beide Wege schreiben also denselben Preis. Log-Zeile und Telegram-Meldung nennen ebenfalls den Füllpreis, damit Nachricht und Ledger übereinstimmen. Zwei Abgrenzungen:

- **Das Verkaufsziel hängt weiter an der Grid-Stufe** (`levels[i+1]`), nicht am Füllpreis. Das ist das Grid-Design: Jede Position gehört zu einer Stufe und wird auf der nächsten verkauft.
- **Im Dry-Run bleibt der beobachtete Preis.** Dort gibt es keine Order-Antwort, der Tickerpreis *ist* der simulierte Fill.

Der Ticker bleibt als Fallback, falls einer Antwort `executedQty` oder `cummulativeQuoteQty` fehlt. Für eine echte Market-Order-Antwort kommt das bei Binance nicht vor.

Bereits geschriebene Ledger-Einträge bleiben unverändert. Eine rückwirkende Korrektur ginge nur über die Order-Historie bei Binance (`myTrades` je `clientOrderId`). **Entscheidung: nicht jetzt.** Es ist eine reine Anzeigeungenauigkeit, kein PnL-Fehler. **Vorgemerkt für den Zeitpunkt, an dem der Steuer-Export tatsächlich ansteht**, nicht vorher. Einträge ohne `clientOrderId` (vor dem K2-Fix) wären dabei gesondert zu betrachten.

**Tests:** 3 neue in `tests/test_grid_sell_safety.py`, Gesamtstand **610, alle grün**. Der Fake-Client füllt dafür bewusst zu einem anderen Preis als dem Ticker (neues Feld `fill_price`), sonst wäre nicht unterscheidbar, welcher der beiden im Ledger landet. Seine Verkaufsantwort enthält außerdem jetzt `executedQty`, wie jede echte Market-Order-Antwort. Ohne das Feld ließe sich aus ihr kein Füllpreis ableiten. Geprüft werden: echter Kauf → `buy_price` = Fill, Verkaufsziel weiter die Grid-Stufe, Meldung mit Fill; echter Verkauf → `sell_price` = Fill und PnL passend zum gemeldeten Erlös; Dry-Run → beobachteter Preis, auch wenn am Fake ein anderer Fill gesetzt ist.

**Wirksamkeit gemessen.** Kontrolllauf 0 Fehlschläge, alle 6 Mutationen gefangen (je 1 Fehlschlag): Ticker statt Fill beim Kauf, Ticker statt Fill beim Verkauf, `record_sell` bekommt den Ticker, Kaufmeldung nennt den Ticker, Verkaufsmeldung nennt den Ticker, Verkaufsziel aus dem Fill statt aus der Grid-Stufe abgeleitet.

#### Priorität 5: Füllpreis als `entry_price` beim Trend-Bot (25.09.2026)

**Befund.** Beim Einlesen vor Priorität 2 gefunden und auf Entscheidung zu einem eigenen Punkt gemacht. `trend_strategy._open_position()` speicherte als `entry_price` den Tickerpreis *vor* der Order. Anders als beim Grid-Bot ist das keine reine Anzeigefrage: Aus `entry_price` entsteht die Stop-Loss-Schwelle. Sie gilt für die Order an der Börse, für den internen Check `is_stop_loss_hit()` und für jede später neu platzierte Absicherung (`_handle_failed_real_sell`, `_ensure_stop_loss_protection`). Die Schwelle lag damit um die Slippage des Kaufs daneben. Der Reconciliation-Einstieg (`_record_reconciled_entry`) nahm schon immer den Füllpreis.

**Umgesetzt.** Für eine echte Order kommt `entry_price` aus der Order-Antwort (`average_fill_price(order, fallback=price)`), und die Schwelle der Stop-Order wird aus diesem Wert berechnet. Alle späteren Stellen lesen `entry_price` aus dem Ledger und rechnen damit automatisch auf derselben Basis. Im Dry-Run bleibt der beobachtete Preis, weil es dort keine Order-Antwort gibt.

**Über die wörtliche Vorgabe hinaus, bewusst mit dabei: der Ausstieg.** Priorität 4 umfasste Kauf *und* Verkauf. Beim Trend-Bot hatte `_close_position()` denselben Fehler, `exit_price` war der Ticker, während `_record_reconciled_exit` den Füllpreis nimmt. Jetzt ist auch `exit_price` der Füllpreis. Er landet zusätzlich in der Latch-Datei des Stop-Loss (`exit_price`, `loss_pct`), dem vorgesehenen Anker eines späteren automatischen Resets (siehe Punkt 16 in 6i). Der Ausstieg über eine gefüllte Stop-Order (`_close_from_filled_stop_order`) nahm den Füllpreis schon vorher.

**Tests:** 6 neue in der Klasse `TrendFillPriceTestCase` (`tests/test_trend_stop_loss.py`), Gesamtstand **616, alle grün**. Der Fake-Client hat wie beim Grid-Bot ein Feld `fill_price` bekommen, und seine Verkaufsantwort enthält jetzt `executedQty`. Alle bestehenden Trend-Tests blieben unverändert grün. Geprüft werden:

- `entry_price` im Ledger und die Einstiegsmeldung sind der Füllpreis.
- Stop- und Limit-Preis der Order an der Börse sind aus dem Füllpreis berechnet. Die Prämisse, dass die tickerbasierte Schwelle eine andere Zahl wäre, ist eigens belegt.
- **Die Folge im laufenden Betrieb, über `execute_once()`:** Kauf mit Ticker 50.000 und Fill 50.100, danach fällt der Kurs auf 45.050. Das liegt unter der Fill-Schwelle (45.090), aber über der Ticker-Schwelle (45.000). Der interne Stop-Loss löst genau deshalb aus. Dass er es mit dem Ticker als Basis *nicht* täte, ist eigens belegt.
- `exit_price` und Ausstiegsmeldung sind der Füllpreis des Verkaufs.
- Die Latch-Datei speichert den Füllpreis und den daraus berechneten Verlust.
- Dry-Run: beobachteter Preis und tickerbasierte Schwelle, auch wenn am Fake ein anderer Fill gesetzt ist.

**Wirksamkeit gemessen.** Kontrolllauf 0 Fehlschläge, alle 7 Mutationen gefangen: Ticker statt Fill beim Einstieg (4), Stop-Schwelle aus dem Ticker (1), Ledger bekommt den Ticker (3), Einstiegsmeldung mit dem Ticker (1), Ticker statt Fill beim Ausstieg (2), `record_exit` bekommt den Ticker (1), Latch bekommt den Ticker (1).

Bei der Messung trat die aus 6i bekannte Falle zum dritten Mal auf: Zwei Suchmuster standen je **zweimal** in `trend_strategy.py`. Die `TrendTrade.new(entry_price=…)`-Zeile gibt es auch im Reconciliation-Einstieg, den `pause(…, exit_price, …)`-Aufruf auch im Ausstieg über die gefüllte Stop-Order. Diesmal hat das Messskript vor jeder Mutation geprüft, dass der Anker genau einmal vorkommt, und die beiden übersprungen, statt die falsche Stelle zu verändern. Mit eindeutigen Ankern werden beide gefangen.

#### Priorität 6: Füllpreis im DCA-Ledger (25.09.2026)

**Befund.** Bei der Vorlage von Priorität 4 gefunden und auf Entscheidung als eigener Punkt nach Priorität 5 umgesetzt. Die Begründung ist dieselbe wie bei Priorität 1: Wären Grid und Trend korrigiert, DCA aber nicht, stünde genau die Inkonsistenz im Code, um die es geht. `strategy.execute_once()` schrieb bei echten Käufen den Tickerpreis vor der Order in `TradeRecord.price`. Im Bot liest niemand diesen Wert, Portfolio-Stop-Loss, Tageslimit und Positions-Audit rechnen mit `quantity` und `quote_spent`. Dashboard und Steuer-Export zeigen ihn aber an. Der Reconciliation-Pfad (`_record_reconciled_buy`) nahm schon immer den Füllpreis.

**Umgesetzt.** Für eine echte Order kommt der Preis aus der Order-Antwort (`average_fill_price(order, fallback=price)`), ebenso in Log-Zeile und `[KAUF]`-Meldung. Der Tickerpreis bleibt dort, wo er richtig ist: beim Stop-Loss-Check vor dem Kauf, der den aktuellen Marktwert braucht und für den es noch keinen Fill gibt. Im Dry-Run bleibt der beobachtete Preis.

Damit schreiben alle drei handelnden Bots bei echten Orders denselben Preis wie ihr jeweiliger Reconciliation-Pfad. Die README fasst das in Abschnitt 6 botübergreifend zusammen (ausführlich seit 25.09.2026 in Abschnitt 7.1 dieses Dokuments). Für bereits geschriebene Einträge gilt die Entscheidung aus Priorität 4: keine rückwirkende Korrektur jetzt, vorgemerkt für den Steuer-Export.

**Tests:** 3 neue in `tests/test_dca_fee_adjustment.py`, Gesamtstand **619, alle grün**. Der DCA-Fake-Client hat dasselbe Feld `fill_price` bekommen wie die Fakes von Grid und Trend. Geprüft werden: echter Kauf → `price` und `[KAUF]`-Meldung sind der Füllpreis; der gespeicherte Preis passt zu Betrag und Menge derselben Order-Antwort; Dry-Run → beobachteter Preis, auch wenn am Fake ein anderer Fill gesetzt ist.

**Wirksamkeit gemessen.** Kontrolllauf 0 Fehlschläge, alle 4 Mutationen gefangen: Ticker statt Fill (2), Ledger bekommt den Ticker (2), `[KAUF]`-Meldung nennt den Ticker (1), Dry-Run mit erfundenem Fill (1). `price=price` steht in `strategy.py` zweimal (Reconciliation und Kaufpfad), dieselbe Stelle, an der schon in 6g eine Gegenmutation die falsche Zeile traf. Das Messskript hat die Eindeutigkeit diesmal vor jeder Mutation geprüft.

#### Punkt A: Gescheiterter Grid-Kauf wird nicht wiederholt, bewusst so belassen (25.09.2026)

**Frage aus der Code-Überprüfung.** An einer durchquerten Stufe wird ein gescheiterter Kauf nicht wiederholt, weil `_last_seen_price` weiterläuft und die Stufe damit als erledigt gilt. Ein fehlgeschlagener Verkauf bleibt dagegen offen und wird im nächsten Zyklus erneut versucht. Ist das Absicht oder eine Inkonsistenz, und wie sieht das mit der nächtlichen Zwangstrennung aus?

**Befund, am Code nachvollzogen und mit dem Fake-Client nachgestellt.** „Gescheitert“ heißt zweierlei:

- **Der ganze Zyklus bricht ab** (Ticker, Regelabruf, …): `_last_seen_price` wird erst am Ende von `execute_once()` gesetzt und bleibt deshalb stehen. Die Durchquerung geht nicht verloren, der nächste erfolgreiche Zyklus kauft die Stufe.
- **Nur die Kauf-Order scheitert** (`place_market_buy()` liefert `None`): `_last_seen_price` rückt vor, und die Stufe wird erst beim nächsten Durchqueren wieder gekauft.

**Die Zwangstrennung trifft praktisch nur den ersten Fall.** Jeder Zyklus beginnt mit der Ticker-Abfrage, und die scheitert zuerst, wenn die Leitung weg ist. In den zweiten Fall käme man nur, wenn die Trennung genau zwischen Ticker-Antwort und Order beginnt, also in einem Fenster von Millisekunden. Selbst dann ist der Ausgang meist „unklar“, und dort wäre eine Wiederholung gerade falsch: Die erste Order kann durchgegangen sein, eine Wiederholung würde dieselbe Stufe doppelt kaufen. Realistische Auslöser für den zweiten Fall sind fehlendes Guthaben auf dem geteilten Konto, Rate-Limit, Mindestvolumen oder ein Serverfehler bei Binance.

**Entscheidung: so belassen, kein Code-Änderungsbedarf.** Die Asymmetrie zum Verkauf ist ein etabliertes Projektprinzip und kein Zufall. Ein wiederholter Verkauf senkt das Risiko, und Ledger-Position plus Guthabenprüfung (W11) schützen vor einem Doppelverkauf. Ein wiederholter Kauf erhöht das Risiko, und einen unverbuchten ersten Kauf erkennt nichts. Mit derselben Begründung lässt der Trendbruch-Stop-Loss Verkäufe durch und sperrt Käufe. Ein entgangener Trade ist ein vertretbarer Preis dafür, einen möglichen Doppelkauf bei unklarem Order-Ausgang zu vermeiden.

Die verworfene Alternative wäre eine Wiederholung wie beim Verkauf gewesen. Sicher wäre sie nur mit einer Unterscheidung „eindeutig abgelehnt“ gegen „Ausgang unklar“, und die liefert `place_market_buy()` heute nicht, weil alle drei Fälle `None` ergeben. Dafür hätte die Client-Schnittstelle für alle drei Bots umgebaut werden müssen, dazu kämen Wiederholungszustand, Obergrenzen und ein Mengenlimit für Meldungen. Bei dauerhaft fehlendem Guthaben entstünde alle 5 Minuten eine abgelehnte Order.

#### Punkt B: −2013 nach einem Timeout, Pending-Eintrag bleibt stehen (25.09.2026)

**Frage aus der Code-Überprüfung.** Nach einem Verbindungsfehler fragt `_resolve_after_network_error()` sofort bei Binance nach. Antwortet Binance mit −2013 („Order existiert nicht“), wurde der Pending-Eintrag gelöscht. Ist die Order in diesem Moment noch in Bearbeitung und wird danach ausgeführt, fehlt sie für immer im Ledger, also der K2-Schaden.

**Was schon abgedeckt war.** Eine *gescheiterte* Nachfrage galt nie als „existiert nicht“: Das Ergebnis ist `LOOKUP_FAILED`, damit „unklar“, der Eintrag bleibt und es kommt `[ORDER-UNKLAR]`. Offen war nur die *erfolgreiche* Antwort −2013 zu einem Zeitpunkt, an dem die Order noch unterwegs ist. Die Zwangstrennung löst diesen Fall nicht aus. Entweder scheitert die Nachfrage, oder die Order hat Binance nie erreicht, und dann ist −2013 richtig. Übrig bleibt eine Verzögerung im Binance-Backend. Dass es die gibt, bestätigt die Binance-Dokumentation (siehe Nebenbefund unten): Die API wartet bis zu 10 Sekunden auf die Matching Engine und meldet danach „execution status unknown“.

**Umgesetzt: B1.** In `_resolve_after_network_error()` sind `ORDER_UNKNOWN` (−2013) und `ORDER_WITHOUT_EFFECT` (Order existiert, ist ohne ausgeführte Menge beendet) jetzt getrennt. Nur der zweite Fall ist eine endgültige Antwort und löscht den Eintrag wie bisher. Bei −2013 bekommt die Strategie weiterhin `None` und bucht nichts, der Pending-Eintrag **bleibt aber stehen**. Die Reconciliation beim nächsten Start fragt erneut: Ist die Order weiterhin unbekannt, wird der Eintrag verworfen; ist sie doch ausgeführt, wird sie nachgetragen. Aus „für immer verloren“ wird damit „verzögert bis zum nächsten Start“. Bei den bisher üblichen regelmäßigen Deploys ist der nicht fern. Es gibt keine Telegram-Meldung, weil −2013 im Normalfall eine Order ist, die Binance nie erreicht hat, und keine Aufforderung zum Eingreifen. Ins Log geht eine Warnung mit dem Hinweis auf die Prüfung beim nächsten Start.

**Bewusst nicht umgesetzt: B2**, also nach einer Wartezeit ein zweites Mal nachfragen. Das brächte zusätzliche Komplexität in die Hauptschleife für einen Fall, der ohnehin selten ist, und B1 hat das Risiko bereits von „verloren“ auf „verzögert“ reduziert.

**Tests:** 3 neue in `tests/test_pending_orders.py`, ein bestehender umgestellt, Gesamtstand **622, alle grün**. Der umgestellte Test (`…_order_unknown_is_no_trade_but_entry_stays`) hatte das Löschen bei −2013 festgeschrieben, wie der Grid-Test in Priorität 1. Neu sind die Gegenprobe (eine ohne Wirkung beendete Order löscht den Eintrag weiterhin, sonst wäre „Eintrag bleibt“ auch grün, wenn nie mehr gelöscht würde) und zwei Tests, die zwei Schritte durchspielen: zur Laufzeit −2013, danach die Reconciliation beim nächsten Start. Ist die Order inzwischen gefüllt, wird sie mit der echten Order-Antwort zum Nachtragen weitergereicht. Ist sie weiter unbekannt, wird der Eintrag verworfen, die Pending-Datei wächst also nicht dauerhaft.

**Wirksamkeit gemessen.** Kontrolllauf 0 Fehlschläge, alle 4 Mutationen gefangen: altes Verhalten, bei dem −2013 den Eintrag löscht (3); Order ohne Wirkung löscht nicht mehr (1); −2013 meldet per Telegram (1); Start-Reconciliation verwirft −2013 nicht mehr (2).

#### Nebenbefund zu Punkt B: 5xx, −1006 und −1007 gelten nicht mehr als „abgelehnt“ (25.09.2026)

**Befund.** `_place_order()` wertet jede `BinanceAPIException` als „Binance hat geantwortet und die Order abgelehnt“ und löscht den Pending-Eintrag, ohne nachzufragen. python-binance (installiert: 1.0.19) wirft diese Exception aber für **jeden** HTTP-Status außerhalb 2xx (`_handle_response`, nachgelesen), also auch für Serverfehler.

**Gegen die aktuelle Binance-Dokumentation geprüft**, nicht aus dem Gedächtnis. Quelle ist das offizielle Repository `binance/binance-spot-api-docs`, Stand letzter Commit 18.09.2026, im Rohtext gelesen am 25.09.2026:

- `rest-api.md`, Abschnitt „HTTP Return Codes“: *„HTTP `5XX` return codes are used for internal errors; the issue is on Binance's side. It is important to **NOT** treat this as a failure operation; the execution status is **UNKNOWN** and could have been a success.“*
- `errors.md`: *„-1006 UNEXPECTED_RESP – An unexpected response was received from the message bus. Execution status unknown.“* und *„-1007 TIMEOUT – Timeout waiting for response from backend server. Send status unknown; execution status unknown.“*
- `rest-api.md`, „General API Information“: *„APIs have a timeout of 10 seconds when processing a request. If a response from the Matching Engine takes longer than this, the API responds with […] (-1007 TIMEOUT). This does not always mean that the request failed in the Matching Engine. If the status of the request has not appeared in User Data Stream, please perform an API query for its status.“*
- Zum Einordnen von Punkt B: `recvWindow` ist ohne Angabe 5000 ms und wird laut „Timing security“ zweimal geprüft, beim Eingang und noch einmal unmittelbar vor der Weitergabe an die Matching Engine. Die Datenquelle von „Query order“ (`GET /api/v3/order`) ist „Memory => Database“.

Die Aussage ist damit bestätigt. Bei 5xx, −1006 und −1007 hat eine Order möglicherweise gewirkt, der Code löschte aber den Eintrag und meldete der Strategie „kein Trade“. Ist die Order doch ausgeführt, fehlt sie im Ledger, also derselbe Schaden wie in K2 über einen anderen Fehlerweg. Der Plan wurde nach der Verifikation vorgelegt und freigegeben.

**Umgesetzt.** Neue Funktion `_execution_status_unknown()` in `binance_client.py`. Sie gibt `True` zurück bei HTTP-Status ≥ 500 **oder** Code −1006/−1007 (Konstante `EXECUTION_STATUS_UNKNOWN_CODES`, mit Verweis auf die Doku-Stelle). Der Code wird unabhängig vom HTTP-Status geprüft, weil die Doku für −1006/−1007 keinen Status nennt. Eine 5xx-Antwort ohne lesbaren Fehlertext (etwa eine HTML-Fehlerseite) hat bei python-binance `code == 0` und wird über den Status erkannt. `_place_order()` schickt diese Fälle in denselben Weg wie einen Verbindungsfehler: Rückfrage bei Binance, dann nachbuchen, verwerfen oder als unklar melden. Das ist bestehender, getesteter Code. Alle anderen API-Fehler bleiben eine endgültige Ablehnung, laut Doku heißt 4xx „the issue is on the sender's side“, etwa −2010 (Guthaben), −1013 (Filter) oder 429/−1003 (Rate-Limit).

Die Log-Texte in `_resolve_after_network_error()` sprechen jetzt von „Verbindungs- oder Serverfehler“ und nennen bei API-Fehlern HTTP-Status und Code (`_describe_inconclusive_error()`). Weiterhin nie `str(exc)`, weil bei `requests`-Fehlern darin die URL samt Signatur steht. Ein Kommentar aus B1 war dabei veraltet („ORDER_UNCLEAR – der einzige Fall, in dem der Eintrag bleibt“) und ist korrigiert: Seit B1 bleibt er auch bei `ORDER_UNKNOWN`.

**Zusammenspiel mit B1.** Nach −1007 kann die Matching Engine noch arbeiten, eine sofortige Rückfrage liefert dann eher −2013 als nach einem reinen Verbindungsabbruch. Genau dafür lässt B1 den Eintrag bis zum nächsten Start stehen. Das ist auch der Pfad, auf dem B2 (zweite Rückfrage nach einer Wartezeit) am meisten brächte. B2 wurde in Kenntnis dessen erneut zurückgestellt: B1 und dieser Fix zusammen machen aus „verloren“ bereits „verzögert bis zum nächsten Start“.

Nicht angefasst ist `cancel_order()`: Dort gilt ein fehlgeschlagener Aufruf ohnehin nicht als Wahrheit, der Trend-Bot fragt danach den tatsächlichen Order-Status ab (`_resolve_stop_order_before_close`).

**Tests:** 8 neue in der Klasse `ServerErrorWithUnknownOutcomeTestCase` (`tests/test_pending_orders.py`), eine bestehende Log-Zusicherung auf den neuen Wortlaut angepasst. Gesamtstand **630, alle grün**. Geprüft am echten `TradingClient` mit gefälschtem Binance-Client darunter:

- HTTP 503 bei gefüllter Order → Order wird zurückgegeben und verbucht, das Log nennt „HTTP 503“.
- HTTP 500 ohne lesbaren Fehlertext (`code == 0`) → wird über den Status erkannt.
- −1007 bei HTTP 408 → wird über den Code erkannt. Der Status liegt bewusst unter 500, damit der Test nicht über die 5xx-Regel grün wird.
- −1006 → wird über den Code erkannt.
- −1007 mit anschließender Antwort −2013 → `None`, der Eintrag bleibt für den nächsten Start (B1).
- Serverfehler und gescheiterte Rückfrage → `[ORDER-UNKLAR]`, der Eintrag bleibt.
- Gegenprobe: 429/−1003 bleibt eine endgültige Ablehnung ohne Rückfrage (die bestehende Gegenprobe für −2010 läuft unverändert). Ohne sie wäre „es wird nachgefragt“ auch grün, wenn *jede* API-Exception nachfragen würde.
- Eine Tabelle über die Einstufung selbst: acht Fälle einschließlich eines Verbindungsfehlers, der den anderen Weg nimmt.

**Wirksamkeit gemessen.** Kontrolllauf 0 Fehlschläge, alle 7 Mutationen gefangen: altes Verhalten, bei dem jede API-Exception eine Ablehnung ist (6); 5xx-Regel entfernt (5); Grenze `>= 500` zu `> 500` (2); −1006 fehlt (2); −1007 fehlt (3); jede API-Exception gilt als unbekannt (5); Log ohne HTTP-Status und Code (1).

## 6h. Allocator-Opt-in aktiviert - vollständiges System live (16.09.2026)

Nach Abschluss des kompletten Sicherheitsreviews (K1-K5, alle 18 W-Punkte, Infrastruktur-Härtung) wurde das Allocator-Opt-in für DCA und Trend auf dem Homeserver aktiviert (DCA_ALLOCATOR_STATE_FILE, TREND_ALLOCATOR_STATE_FILE gesetzt). Damit läuft erstmals das vollständige, integrierte Vier-Bausteine-System im Testnet-Live-Betrieb: DCA und Trend lesen jetzt die Allocator-Zuteilung vor jeder neuen Order, statt unabhängig voneinander zu handeln.

Bewusst nur auf dem Homeserver, nicht auf dem VPS (dort bleibt der Allocator inaktiv, siehe Grundsatzentscheidung in 6e). Beide Bots starten fehlerfrei mit aktiviertem Opt-in, keine Fehler beim Lesen der Allocator-State-Datei.

Damit beginnt jetzt faktisch die geplante, mindestens einmonatige Live-Testphase des vollständigen Systems vor dem Echtgeld-Einstieg (siehe 5b, 6c).

### Testphase auf dem Homeserver verlängert auf ca. 2–3 Monate (25.09.2026)

Die oben geplante, mindestens einmonatige Testphase wird auf **ca. 2–3 Monate** verlängert. Gerechnet ab dem Start des vollständigen Systems am 16.09.2026 endet sie damit etwa zwischen Mitte November und Mitte Dezember 2026.

**Grund: zwei offene Fragen brauchen echte Stop-Loss-Ereignisse, keinen zusätzlichen Code.**

- **Kalibrierung von `TREND_STOP_LIMIT_OFFSET_PCT`** (siehe 6f): Der Default von 0,5 % stützt sich bisher auf **n = 2** Stop-Loss-Exits. Die stammen aus dem Backtest (Tageskerzen-Näherung), nicht aus realen Fills. Die realen Daten liefert erst der Testbetrieb über die `[STOP-FILL-ANALYSE]`-Zeilen, und jede davon setzt einen tatsächlich ausgelösten Trend-Stop-Loss voraus.
- **Automatischer Stop-Loss-Reset** (Punkt 16, siehe 6i): Er ist bewusst zurückgestellt, weil es über alle Backtest-Zeiträume genau **n = 1** auswertbares Ereignis gab.

Beide Ereignisarten sind selten, beim Trend-Bot mit Tageskerzen liegen Wochen dazwischen. Mehr Laufzeit ist der einzige Weg zu einer belastbaren Datenbasis.

**Betrifft ausschließlich den Homeserver.** Dort läuft das System bereits vollständig live im Testnet: `DCA_BOT_ENABLE_TRADING`, `GRID_BOT_ENABLE_TRADING` und `TREND_BOT_ENABLE_TRADING` stehen alle auf `true`, verifiziert am 25.09.2026. Es ist also keine Umstellung nötig, nur Zeit.

**Der VPS bleibt unverändert** beim feststehenden Enddatum **12.10.2026** (Vertragskündigung, siehe 6b/6e). Dort gibt es keine Verlängerung und keine Umstellung der VPS-Bots auf Live. Die Punkte zum Vertragsende (finaler `data/`-Snapshot, Entfernen des Deploy-Keys) gelten weiter wie geplant.

**Die Vorbedingungen für echtes Kapital ändern sich nicht.** Der Einsatz von echtem Geld bleibt an die bereits dokumentierten Voraussetzungen geknüpft:

- finale Positionsgrößen-Kalibrierung (siehe 5b),
- eine ausreichende Datenbasis für den Stop-Limit-Offset (siehe 6f),
- ein abschließender Sicherheitsreview mit Claude Opus 5 kurz vor dem tatsächlichen Live-Gang (siehe 6d).

Die längere Laufzeit im Testnet ist ausdrücklich dafür da, diese Vorbedingungen mit besserer Datenbasis zu erfüllen, nicht um sie zu umgehen oder abzukürzen.

### Umstellung auf echte Orders auf dem Homeserver: aus den Ledgern rekonstruiert (25.09.2026)

Wann `*_BOT_ENABLE_TRADING` auf dem Homeserver auf `true` gestellt wurde, stand nirgends. Laut 6e („Woche 1 abgeschlossen“) liefen am 15.09. alle drei Bots im Dry-Run, am 25.09. ist `true` für alle drei verifiziert (siehe oben). Die Ledger grenzen den Zeitpunkt je Bot ein. Ausgewertet wurde mit `python -m dca_bot.audit_positions` am 25.09.2026:

- **DCA:** Echte Käufe am 15.09.2026 um 12:53:03 UTC und am 16.09.2026 um 08:34:37 UTC, dazu zwei simulierte Käufe. Deren Zeitstempel wurden nicht ausgewertet; vermutlich stammen sie aus der Dry-Run-Phase laut 6e. Umgestellt wurde damit **spätestens am 15.09.2026 um 12:53 UTC**.
- **Grid:** 10 Einträge, davon 3 offen, alle echt (`dry_run: false`). Am 22.09. waren es 7 Einträge, ebenfalls ohne Dry-Run. Im Grid-Ledger gibt es keinen Dry-Run-Eintrag; bereits der erste Trade am 15.09.2026, 13:38:07 UTC (Stufe 6), war echt. Eine mögliche kurze Dry-Run-Phase davor ohne Trade (laut 6e) hinterlässt im Ledger keine Spur. Umgestellt wurde damit **spätestens am 15.09.2026 um 13:38 UTC**.
- **Trend:** Die einzige offene Position ist vom 15.09.2026, 12:19:01 UTC, und ist Dry-Run. `TREND_BOT_ENABLE_TRADING` war zu diesem Zeitpunkt also `false`. Die Umstellung erfolgte **zwischen dem 15.09. und dem 25.09.2026** (Bestätigung `TREND_BOT_ENABLE_TRADING=true`). Der exakte Zeitpunkt ist aus dem Ledger nicht rekonstruierbar, weil seither noch kein realer Trade stattgefunden hat.

Für die Auswertung der Testphase heißt das: In den Homeserver-Ledgern von DCA und Trend stehen Dry-Run- und echte Einträge nebeneinander, die Auswertung muss nach `dry_run` trennen. Das Grid-Ledger ist durchgehend echt.

### ⚠ Trend-Bot: Die Kalibrierungsdaten fließen noch nicht (25.09.2026)

**Die Kalibrierung von `TREND_STOP_LIMIT_OFFSET_PCT` ist der Hauptgrund für die Verlängerung der Testphase (siehe oben). Beim Trend-Bot kann sie erst beginnen, wenn zwei Dinge nacheinander passiert sind:**

1. Die offene **Dry-Run-Position vom 15.09.2026** (12:19:01 UTC, siehe Rekonstruktion oben) wird simuliert geschlossen, per Signal-Umkehr oder über den internen Stop-Loss.
2. Danach findet ein **neuer, echter Einstieg** mit echter Stop-Loss-Order an der Börse statt.

**Bis dahin trägt der Trend-Bot nichts zur Kalibrierungsdatenbasis bei.** Der Grund liegt im Design, ein Fehler ist es nicht: Der Trend-Bot hält genau eine Position, die Dry-Run-Position belegt diesen Platz. Eine Dry-Run-Position hat nie eine Stop-Order an der Börse und bleibt auch nach dem Umschalten auf `TREND_BOT_ENABLE_TRADING=true` simuliert (K4). Sie liefert also keine `[STOP-FILL-ANALYSE]`-Zeile.

**Der VPS hilft dabei nicht.** Laut diesem Dokument läuft sein Trend-Bot seit Beginn im Dry-Run (6b), und eine Umstellung der VPS-Bots auf echte Orders ist ausdrücklich nicht vorgesehen (siehe oben). Nicht auf dem Server selbst geprüft, sondern aus der Dokumentation abgeleitet. Mit dem Vertragsende am 12.10. entfällt er ohnehin. **Derzeit fließen damit von keinem Server Kalibrierungsdaten.**

Zwei Einzelheiten dazu, beide im Code nachgeprüft (`trend_strategy.py`):

- **Schließt sich die Dry-Run-Position über den internen Stop-Loss, wird der Stop-Loss-Latch gesetzt**, auch für eine Dry-Run-Position. Danach blockiert der Bot jeden neuen Einstieg, bis manuell zurückgesetzt wird (`python -m dca_bot.reset_trend_stop_loss`). Nur bei einem Ausstieg per Signal-Umkehr ist der Weg zum neuen Einstieg ohne Eingriff frei.
- **Auch ein echter Trade liefert nur unter einer Bedingung eine `[STOP-FILL-ANALYSE]`-Zeile**: wenn die Stop-Order an der Börse gefüllt wird. Ein Ausstieg per Signal-Umkehr oder über den internen Stop-Loss (der Bot storniert dann die Order und verkauft selbst) trägt nichts zur Kalibrierung bei.

**Bewusste Entscheidung: kein Eingriff.** Die Position wird weder per Notaus angehalten noch manuell geschlossen. Das wäre ein unnötiges Risiko für einen reinen Zeitgewinn, und die Position schließt sich ohnehin von selbst, sobald ein Signal kommt. Die Testphase ist damit faktisch erst ab dem ersten echten Trend-Einstieg auf die Kalibrierungsfrage ausgerichtet. Das ist bei der Bewertung, ob 2–3 Monate reichen, zu berücksichtigen.

## 6i. Verbesserungsvorschläge aus Review-Abschnitt 7 (17.09.2026)

Der Sicherheitsreview enthielt neben den K- und W-Punkten eine dritte, kürzere Liste: 17 Qualitäts- und Komfortvorschläge, von denen keiner als sicherheitskritisch eingestuft war. Am 17.09. wurde dafür ein Ist-Stand-Check gemacht.

**Ergebnis des Checks:** 8 waren als Nebeneffekt der K/W-Fixes bereits vollständig erledigt (exchangeInfo-Quantisierung → K3, idempotente Orderplatzierung → K2, Lockfile → W4, Heartbeat → W13, Balance-Check vor dem Verkauf → W11, Allocator-Kadenz → W9, DCA-Konfiguration nach `.env` → W12, Log-Rotation und Snapshots → Infrastruktur-Härtung in 6g). 4 waren teilweise erledigt, 5 offen — davon zwei bewusst (W14-artige Architekturentscheidung bzw. als Overkill eingestuft).

Drei Funde aus dem Check waren gewichtiger, als die Liste sie eingestuft hatte:

1. **Die Allocator-State-Datei wurde nicht atomar geschrieben.** Bis zum Opt-in vom 16.09. (siehe 6h) folgenlos, weil sie außer dem Allocator selbst niemand las. Seitdem lesen DCA und Trend sie vor *jeder* neuen Order.
2. **Die K3-Restlücke war entgegen der Dokumentation nie geschlossen** — siehe die Korrektur-Notiz in 6g.
3. **Die Entscheidungsfunktionen von Grid und Allocator haben keinen einzigen direkten Test.** Genau dort saßen die beiden Designfehler, die vor Fertigstellung des Grid-Bots gefunden wurden (Kaltstart, Intervallgrenze, siehe Abschnitt 6) — also nicht „könnte theoretisch mal ein Problem werden".

### Stufe 1 umgesetzt: Punkte 8, 2 und 10 (17.09.2026)

Die drei kleinen, vor dem Echtgeld-Schalter fälligen Punkte.

**Punkt 8 — Gebührenkorrektur im Stop-Fill-Pfad (die eigentliche K3-Restlücke).** `_close_from_filled_stop_order()` buchte `cummulativeQuoteQty` direkt als Erlös, also brutto. `get_order_with_fills()` existierte seit dem K2-Fix und wurde in fünf Reconciliation-Pfaden genutzt — an diesen einen Pfad war es nie angeschlossen worden. Der Fehler ist klein (rund 0,1 % des Erlöses, zu optimistisch), landet aber im `realized_pnl` des Ledgers, also in genau der Zahl, an der die Strategie nach der Paper-Trade-Phase gemessen wird. Und betroffen ist ausgerechnet der Pfad, für den die börsenseitige Absicherung überhaupt gebaut wurde: Bot-Ausfall oder Kurssprung über Nacht.

Beide Aufrufstellen (regulärer Zyklus und Startup-Abgleich) bekommen die Korrektur, es gibt für jede einen eigenen Test — sonst hinge die Richtigkeit der PnL daran, ob der Bot zwischendurch neu gestartet wurde.

**Bewusste Konstruktion:** Der Fix hängt zwei API-Aufrufe in einen Pfad, der zuvor nur `get_order_status()` brauchte. Beide sind gekapselt und fallen bei einem Fehlschlag auf den Bruttoerlös zurück — also exakt das Verhalten vor dem Fix. Der Grund: Diese Methode trägt einen Verkauf nach, den die Börse **bereits ausgeführt hat**. Bräche sie an einer fehlgeschlagenen Gebührenabfrage ab, stünde die Position weiterhin als „offen" im Ledger, obwohl die Assets weg sind — und der nächste Zyklus würde sie erneut zu verkaufen versuchen. Ein um die Gebühr zu optimistischer Eintrag ist dagegen folgenlos. Damit kann der Fix nur verbessern, nie verschlechtern; es gibt einen eigenen Test dafür.

**Punkt 2 — Atomares Schreiben der Allocator-State-Datei.** Umgestellt auf dasselbe `tmp` + `fsync` + `os.replace`-Muster wie die drei Ledger (W5) und der Pending-Store (K2).

Dazu der eigentlich wichtigere Teil: **`read_allocation_fraction()` unterscheidet jetzt zwei Fälle**, die vorher beide `None` ergaben.

| Lage | vorher | jetzt |
|---|---|---|
| Feature nicht aktiviert, Datei fehlt | `None` → voller Betrag | unverändert `None` |
| kaputtes JSON, fehlendes `trend_fraction`, unlesbarer Wert, Wert außerhalb 0–1 | `None` → voller Betrag | `0.0` → 100 % DCA, kein Trend-Einstieg |
| `PermissionError`/`OSError` | **gar nicht gefangen** → Abbruch des Kaufzyklus | `0.0` |
| veraltet (W10) | `0.0` | unverändert `0.0` |

`None` heißt für beide Konsumenten „kein Allocator" und damit **voller Betrag** — DCA kauft voll *und* Trend steigt voll ein, zusammen also mehr Kapital, als die Zuteilung je vorgesehen hätte. Das ist genau die Überallokation, gegen die der Allocator existiert. Für den *veralteten* Fall war diese Abwägung unter W10 längst getroffen; für die *kaputte* Datei war sie nie nachgezogen worden.

Dass `FileNotFoundError` weiterhin `None` ergibt, ist die bewusste Grenze: Eine fehlende Datei heißt „der Allocator hat noch nie geschrieben" — der reguläre Zustand bei einem frischen Deployment und in den Sekunden zwischen zwei Service-Starts. Bekäme dieser Fall den Fallback, würde ein neu aufgesetzter Bot mit gesetztem Opt-in, aber noch nicht gestartetem Allocator nie wieder Trend-Positionen eröffnen. Die Reihenfolge der `except`-Zweige ist deshalb kritisch (`FileNotFoundError` ist eine Unterklasse von `OSError`) — dieselbe Falle wie bei W5.

Die **drei Stop-Loss-Latch-Dateien** schreiben bewusst weiterhin einfach: Für sie zählt allein, *dass* die Datei existiert (`is_paused()` prüft nur `exists()`), der Inhalt ist rein informativ. Eine halb geschriebene Datei hält die Pause genauso zuverlässig. Das steht jetzt als Kommentar an allen drei Stellen, damit es nicht wie eine vergessene Ecke aussieht.

**Punkt 10 — Globaler Notaus `STOP_ALL`.** Eine Datei `STOP_ALL` im Projektverzeichnis oder `STOP_ALL=true` (Prozessumgebung oder aktuelle `.env`) stoppt alle vier Bots gleichzeitig. Dieselbe ODER-Verknüpfung und dieselbe Asymmetrie wie bei W1: auslösen leicht, versehentlich aufheben schwer. Die botspezifischen Schalter bleiben unberührt — einen einzelnen Bot anzuhalten muss weiterhin möglich sein.

Der Pfad ist **bewusst nicht konfigurierbar**, anders als die `*_KILL_SWITCH_FILE`: Ein globaler Notausschalter, dessen Namen man erst in der `.env` nachschlagen muss, verfehlt seinen Zweck. Aufgelöst wird er gegen die Projektwurzel, nicht gegen das Arbeitsverzeichnis. `STOP_ALL` wird außerdem beim Start validiert wie die vier `*_HALT`-Variablen — ein `STOP_ALL=ture` hätte sonst vierfache Nicht-Wirkung.

Neu ist dabei `KillSwitch.triggered_by()`: Die `BotHalted`-Meldung benennt jetzt, **welche** Quelle ausgelöst hat. Wenn vier Bots gleichzeitig stoppen, ist „warum eigentlich?" die erste Frage, und „jemand hat STOP_ALL angelegt" ist eine andere Antwort als „dieser eine Bot hat seine eigene STOP-Datei".

**Ein Nebenfund beim Testen:** Der `.env`-Weg des Notaus hat den Wert schon immer getrimmt, der Prozessumgebungs-Weg nicht. Ein `DCA_BOT_HALT=" true "` in einer systemd-Unit hieß damit still „kein Notaus" — dieselbe unangenehme Fehlerrichtung wie ein Tippfehler, nur durch ein Leerzeichen ausgelöst. Beide Wege verhalten sich jetzt gleich.

**Tests:** 33 neue (6 in `tests/test_trend_stop_loss.py` für Punkt 8, 27 in der neuen `tests/test_improvements_stage_1.py` für die Punkte 2 und 10). Wirksamkeit wieder gemessen statt behauptet, Kontrolllauf ohne Änderung bei 0 Fehlschlägen: nicht-atomares Schreiben → 1 Test fällt um, alter `None`-Fallback → 6, fehlender globaler Notaus → 6, fehlende Gebührenkorrektur → 2. Gesamtstand: **357 Tests, alle grün.**

Beiläufig: `FakeTradingClient` in `test_trend_stop_loss.py` hatte gar kein `get_order_with_fills` — der Fake brauchte die Methode nie, weil der Produktivpfad sie nie aufrief. Das ist Befund 2 von der anderen Seite gesehen.

### Stufe 2 umgesetzt: Punkte 12 (Grid-Hälfte) und 3 (17.09.2026)

Die beiden Punkte, die vor dem Echtgeld-Schalter noch fällig waren.

#### Punkt 12, Grid-Hälfte — direkte Tests für die Entscheidungsfunktionen

Reine Testarbeit, keine Zeile Produktivlogik geändert. Der Befund war derselbe wie bei W17, nur an anderer Stelle: `compute_grid_levels`, `find_triggered_buy_levels`, `is_sell_target_hit` und `is_trend_break_stop_loss_hit` hatten **keinen einzigen direkten Test**. Sie liefen ausschließlich indirekt über die Strategie-Tests mit — also immer nur an der einen Preislage, die der jeweilige Testfall zufällig brauchte, nie an einer absichtlich konstruierten Kursreihe. Dasselbe für die Zuteilungs-Mathematik des Allocators (`derive_trend_strength`, `compute_target_fraction`, `smooth_fraction`).

Das Gewicht kommt daher, wo diese Funktionen stehen: **Genau dort saßen die beiden Designfehler**, die vor Fertigstellung des Grid-Bots gefunden wurden (Kaltstart-Bug, Intervallgrenzen-Fehler, siehe Abschnitt 6). Und beim Allocator skalieren DCA und Trend seit dem Opt-in vom 16.09. den Betrag *jeder* neuen Order mit dem Ergebnis der Kette — ein Fehler dort ändert keine Entscheidung, aber jede Positionsgröße, und zwar still, weil das Ergebnis eine plausible Zahl zwischen 0 und 1 bleibt.

**Zwei neue Dateien statt einer gemischten:** `tests/test_grid_signals.py` (41 Tests) und `tests/test_allocator_signals.py` (36). Sie prüfen Module, keinen Change-Set — die Projektkonvention dafür ist Thema-pro-Datei. `test_improvements_stage_1.py` heißt nur deshalb nach einer Stufe, weil es bot-übergreifende Änderungen bündelt.

Das Test-Grid ist bewusst klein und rund (100–120 bei 2 % Abstand, 10 Stufen, davon 9 Kaufstufen) — jede Stufe von Hand nachrechenbar, identische Logik wie live. Gleiche Überlegung wie die kurzen EMA-Perioden bei W17.

**Die Gegenproben sind der eigentliche Inhalt.** Ein Test der Form „Situation X ergibt Y" ist auch dann grün, wenn Situation X nie vorlag:

| Fall | Zusicherung | Gegenprobe, die sie erst scharf macht |
|---|---|---|
| Kaltstart | `last_seen_price=None` löst nichts aus | Bei Preis 106,00 liegen **sechs** Kaufstufen oberhalb, die der naive Vergleich gekauft hätte — und mit gesetztem Referenzpreis (119,00) werden exakt diese sechs auch geholt |
| Intervallgrenze | Referenzstufe exakt auf `last_seen_price` zählt nicht erneut | Ein um 1e-7 höherer Referenzpreis schließt dieselbe Stufe sehr wohl ein |
| Oberste Stufe | ist nie Kaufstufe | Über das beobachtbare Verhalten geprüft (Durchlauf durch das ganze Grid), nicht durch Nachlesen von `levels[:-1]` |
| Allocator, Abwärtstrend | ergibt 0 % Trend-Anteil | Dieselbe Reihe hat einen EMA-Abstand von 3,07 %, der **ohne** die Richtungsprüfung auf volle 100 % abgebildet würde |

Der `last_seen_price` der Grenzfall-Tests wird direkt aus `LEVELS[5]` entnommen statt als Literal geschrieben — nur so gilt die Gleitkomma-Gleichheit per Konstruktion und nicht von der Schreibweise einer gerundeten Zahl abhängig.

Mit aufgenommen: der erste real gemessene Live-Wert vom 15.09. (Trendstärke 5,25 % → `trend_fraction: 1.0`, siehe 6e) ist jetzt nachgerechnet, die Doku-Aussage hängt also an einem Test statt nur an einem Logauszug.

#### Punkt 3 — Konsistenz-Check beim Start + bot-übergreifender Abgleich

**Teil A: `balance_guard` beim Start, auch im DCA-Bot.** Neues Modul `dca_bot/startup_checks.py` mit einer Funktion, die alle drei nutzen; je eine kurze `check_balance_on_startup()`-Methode pro Strategie bestimmt die eigene Menge (die Ledger sind unterschiedlich aufgebaut). `balance_guard.py` bleibt dabei rein wie zugesagt — es liefert weiterhin nur die Bewertung, das neue Modul beschafft ihr die Daten.

Zwei Lücken schließt das. Der **DCA-Bot** verkauft nie, hatte also gar keinen Verkaufspfad und damit überhaupt keinen Moment, in dem seine Buchhaltung je gegen die Realität gehalten wurde — er band `balance_guard` als einziger überhaupt nicht ein. Nötig ist es trotzdem: Sein Ledger ist die Kostenbasis des Portfolio-Stop-Loss, und der bewertet mit `quantity * current_price`; eine zu große Menge überschätzt den Portfoliowert und lässt den Stop-Loss zu spät auslösen. Bei **Grid und Trend** lief die Prüfung nur im Verkaufsmoment, und zwischen zwei Verkäufen können Wochen liegen, beim Trend-Bot (Tageskerzen, EMA 20/50) auch Monate.

Der Aufruf hängt in der **bestehenden** `safe_startup_reconciliation()`-Liste, als letzter Schritt. Zwei Gründe: Die Reconciliation davor kann Ledger-Einträge nachtragen (K2), beim Trend-Bot stellt der zweite Schritt außerdem die Stop-Loss-Order wieder her — und genau die bindet die komplette Positionsmenge. Ein Abgleich davor verglicher gegen einen anderen Stand. Und der W18-Schutz gilt damit automatisch, ohne neuen `try/except`.

**Eine bewusste Abweichung vom Verkaufspfad:** Das Gate ist die **Menge**, nicht `trading_enabled`. Dort schaltet der Dry-Run ab, weil ein simulierter Verkauf gar keine Order platziert — die Prüfung hätte keinen Gegenstand. Hier ist die Frage „gibt es überhaupt etwas zu prüfen?", und die hängt an echten Positionen, nicht am Schalterstand. Ein auf Dry-Run zurückgestellter Bot mit echtem Altbestand ist gerade der interessante Fall. Ist die Menge 0 (Dry-Run mit frischem Ledger, der Normalfall im Testbetrieb), entsteht kein einziger API-Aufruf.

Kein Fehlalarm bei offener Trend-Position, und das ist nicht selbstverständlich: Deren exchange-seitige Stop-Loss-Order bindet die komplette Menge, das freie Guthaben wäre also 0. Sie trägt aber seit K2 das `trend-`Präfix und zählt damit in `own_locked` — genau dafür ist `own_upper_bound = free + own_locked` so gebaut. Beide Richtungen sind getestet, die Gegenprobe läuft über dieselbe Order ohne Präfix.

**Teil B: `audit_positions.py` erweitert.** Das Skript liest jetzt zusätzlich das DCA-Ledger (eigener Abschnitt mit Menge, Einsatz und Ø-Einstandspreis) und hängt — falls API-Keys vorhanden sind — einen bot-übergreifenden Kontoabgleich an: tatsächlicher Bestand und offene Orders gegen die Summe dessen, was alle drei Ledger als offen führen.

Warum das hierher und in keinen Bot gehört, ist das eigentliche Argument: Jeder Bot prüft nur, ob **sein** Anspruch für sich genommen noch gedeckt wäre — eine Prüfung ohne Fehlalarme, die dafür genau den Fall nicht sieht, in dem erst die Summe zu groß wird. Diese Frage zu stellen hieße für einen Bot, fremde Ledger zu lesen, und das bricht das Trennungsprinzip. Ein rein lesendes Werkzeug darf alles einsehen.

Details, die dabei zählten:

- **Ohne API-Keys wird nur der Abgleich übersprungen**, mit Begründung; der Ledger-Teil läuft weiter. Die Zusage „braucht keine API-Keys" gilt unverändert. `--offline` schaltet ihn auch bei vorhandenen Keys ab.
- **Der Client kann strukturell keine Orders platzieren:** gebaut ohne Pending-Orders-Datei, und die `place_*`-Methoden weisen genau diesen Zustand aktiv zurück. Die Nur-Lesend-Zusage hängt nicht an Disziplin.
- **Gruppiert nach Symbol.** Handeln die drei Bots unterschiedliche Paare, wäre eine Gesamtsumme schlicht falsch — sie addierte Mengen verschiedener Assets. Grid- und Trend-Ledger tragen selbst kein Symbol-Feld; es kommt aus der Konfiguration.
- **Verglichen wird gegen `frei + gebunden`**, nicht nur gegen `free`: Eine Menge in einer offenen Verkaufs-Order existiert noch, sie ist nur nicht verkäuflich. Anders als bei der Deckungsprüfung eines einzelnen Verkaufs, die bewusst nur `free` betrachtet.
- **Ein Überschuss ist kein Befund** (manueller Bestand, Altlast). Nur die andere Richtung wird gemeldet — mit dem ausdrücklichen Hinweis, die Ledger **nicht** blind anzupassen, bevor geklärt ist, welche Seite recht hat.
- Die neue `split_locked_by_bot()` steht in `balance_guard.py`, nicht im Skript: Die Regel, welche Order überhaupt Base-Asset bindet, darf es nur einmal geben — sonst zeigt das Audit früher oder später andere Zahlen als der Bot, der sich gerade beschwert. Die vorhandene `split_locked_quantity()` bleibt unangetastet (additiv oder gar nicht, so kurz vor dem Echtgeld-Schalter).

#### Tests und Wirksamkeit

141 neue Tests (41 + 36 + 29 + 35), Gesamtstand **498, alle grün**. Wirksamkeit wieder gemessen statt behauptet, Kontrolllauf je ohne Mutation bei 0 Fehlschlägen. Alle 39 Mutationen über die vier Bereiche werden gefangen; die markantesten: Kaltstart-Guard entfernt → 1, Intervall oben geschlossen → 1, `levels[:-1]` → `levels` → 3, Klemmung der Zuteilung entfernt → je 5, Richtungsprüfung des Allocators aufgehoben → 4, Mengen-Gate des Start-Checks entfernt → 6, Start-Check blockiert statt weiterzulaufen → 9, Verdrahtung im DCA-Einstiegspunkt entfernt → 3, Vergleich nur gegen `free` → 2, Überschuss gilt als Befund → 3.

**Die Messung war dabei zuerst selbst falsch — schon wieder an derselben Stelle wie bei W17.** Eine Mutation (`split_locked_by_bot` nimmt `origQty` statt der Restmenge) meldete 0 Fehlschläge, obwohl es einen passenden Test gibt. Ursache: Das Suchmuster `quantity = _remaining_quantity(order)` steht **zweimal** in `balance_guard.py` — einmal in der alten `split_locked_quantity()` und einmal in der neuen Funktion. Die Ersetzung traf die erste, also die falsche, und die wird in `test_stage_c_safety.py` geprüft, nicht in der gemessenen Datei. Der Anker läuft jetzt bis `for name in bot_names:`, was es nur in der neuen Funktion gibt. Das Warnsignal war dasselbe wie damals: ein Ergebnis, das zu einem vorhandenen, offensichtlich einschlägigen Test nicht passt.

### Punkt 16 als Backtest-Experiment durchgespielt — Ergebnis: vorerst NICHT umsetzen (17.09.2026)

Punkt 16 (automatischer Stop-Loss-Reset) war als größter Hebel der Liste eingestuft und für die laufende Paper-Trade-Phase vorgemerkt — „als Backtest-Experiment mit Erholungsschwelle und Cooldown als Parametern" (siehe unten). Genau das ist jetzt gemacht. **Ergebnis: keine Änderung am Produktivsystem.** Der Latch in `TrendStopLoss` (`trend_risk.py`) bleibt ohne Auto-Reset, DCA und Grid ebenso.

**Was gebaut wurde.** Ein neuer Analyse-Modus `--analyze-auto-reset` in `trend_backtest.py`, rein additiv und ohne eine Zeile Produktivlogik — dasselbe Muster wie `--analyze-stop-limit-reliability` aus K3. Der bestehende `--simulate-reset-after-days`-Pfad bleibt unangetastet: Er ist die Grundlage der bereits in Abschnitt 6 dokumentierten Zahl, und die muss reproduzierbar bleiben. Beide Modi gleichzeitig zu setzen wird aktiv abgewiesen (zwei konkurrierende Regeln für denselben Latch; das Ergebnis wäre keiner von beiden zuzuordnen).

Der simulierte Mechanismus hebt den Latch auf, sobald **beide** Bedingungen erfüllt sind (UND, nicht ODER):

- **Erholungsschwelle:** Preis ≥ Auslösepreis des Stop-Loss × (1 + X %)
- **Cooldown:** mindestens Y Tage seit dem Stop-Loss-Exit

Die UND-Verknüpfung ist der eigentliche Gegenstand. Jede Bedingung für sich hat eine offensichtliche Lücke: Eine reine Erholungsschwelle greift auch beim Ein-Tages-Sprung direkt nach dem Exit (Dead-Cat-Bounce), ein reiner Cooldown ist wieder die Zeitregel von `--simulate-reset-after-days`, nur anders benannt. Anker der Schwelle ist der **tatsächliche Ausstiegskurs**, nicht die rechnerische Schwelle `entry_price × (1 − stop_loss_pct/100)` — beide fallen oft, aber nicht immer zusammen, und `TrendStopLoss.pause()` schreibt den Ausstiegskurs ohnehin schon als `exit_price` in die Latch-Datei. Eine spätere Live-Umsetzung bräuchte also keinen neuen Zustand.

**Definition „falscher Wiedereinstieg":** ein Wiedereinstieg, der selbst wieder im Stop-Loss endet, statt per Signal-Umkehr geschlossen zu werden. Bewusst **nicht** „macht Verlust". Ein per Signal geschlossener Wiedereinstieg hat sich als Entscheidung bewährt, auch wenn er im Minus endete — die Frage des Latches ist nicht „hat sich der Trade gelohnt", sondern „ist der Bot in einen noch laufenden Abwärtstrend hineingelaufen". Am Periodenende offene Wiedereinstiege werden eigens ausgewiesen: Sie haben keinen Ausgang, und sie als „nicht falsch" zu zählen wäre eine Aussage, die die Daten nicht hergeben.

**Ergebnis der Grid-Suche** (3 Schwellen × 3 Cooldowns × 3 Zeiträume, Live-Defaults: EMA 20/50, Mindestabstand 1,0 %, Stop-Loss 10 %, 15,00 pro Trade, 0,1 % Gebühr je Seite). Rendite = realisiert **plus** unrealisiert:

| Zeitraum | Erholung % | Cooldown | Resets | Rendite mit Auto-Reset | Rendite ohne (Referenz) | Zusätzl. Wiedereinstiege | davon falsch |
|---|---|---|---|---|---|---|---|
| 2022 Bärenmarkt | 2 | 3 / 7 / 14 | 1 | −15,75 % | −15,75 % | 0 | 0 |
| 2022 Bärenmarkt | 5 | 3 / 7 / 14 | 0 | −15,75 % | −15,75 % | 0 | 0 |
| 2022 Bärenmarkt | 10 | 3 / 7 / 14 | 0 | −15,75 % | −15,75 % | 0 | 0 |
| 2023 Erholung | 2 / 5 / 10 | 3 / 7 / 14 | 1 | **+55,03 %** | +13,14 % | 1 | 0 (1 offen) |
| 2021 Seitwärts | 2 / 5 / 10 | 3 / 7 / 14 | 0 | +11,83 % | +11,83 % | 0 | 0 |

*(Zusammengefasste Schreibweise: Innerhalb einer Zeile sind alle aufgeführten Kombinationen zahlengleich. Vollständige 27-Zeilen-Ausgabe über `python -m dca_bot.trend_backtest --analyze-auto-reset`.)*

**Die Rendite-Spalte enthält bewusst auch den unrealisierten Anteil**, und das ist hier nicht kosmetisch: Der gesamte 2023-Effekt steckt in einer am Periodenende noch **offenen** Position (+13,14 % realisiert / +41,89 % unrealisiert). Eine Tabelle nach der Konvention von `print_report` — nur realisierte PnL — hätte für alle 27 Kombinationen exakt den Referenzwert gezeigt und den Effekt vollständig verborgen. Das war der erste Entwurf der Ausgabe und ist genau deshalb jetzt ausdrücklich dokumentiert. Nebenbei eine saubere Gegenprobe: +55,03 % reproduziert die in Abschnitt 6 dokumentierten ~55 % exakt — der echte Mechanismus kommt auf dasselbe Ergebnis wie die grobe 14-Tage-Simulation.

**Drei Befunde:**

1. **Es gibt genau EIN auswertbares Ereignis über alle drei Zeiträume.** 2021: Der Stop-Loss löst nie aus, der Auto-Reset hat keinen Gegenstand. 2022: Er löst einmal aus (Exit 11.04. @ 39.530,45), der Latch fällt bei 2 % — der Kurs erholte sich um zwischen 2 % und 5 % über den Ausstieg, mehr nie —, aber danach kommt kein bestätigtes Aufwärtssignal mehr, also 0 Wiedereinstiege. Das bestätigt die Aussage aus Abschnitt 6 („im Bärenmarkt ändert Reset nichts") und zeigt jetzt auch den Grund: nicht weil der Latch hielt, sondern weil kein Signal kam. 2023: 1 Stop-Loss, 1 Wiedereinstieg.

2. **In 2023 waren die Parameter nie die bindende Bedingung — deshalb sind alle neun Zellen identisch.** Stop-Loss-Exit am 17.08.2023 @ 26.623,41. Die Schwellen werden sehr unterschiedlich erreicht: 2 % am 29.08. (+12 Tage), 5 % am 01.10. (+45), 10 % am 20.10. (+64). Das bestätigte Aufwärtssignal kommt am **20.10.2023**, also am selben Tag wie die strengste Schwelle. Engpass war durchgängig das EMA-Signal, nie der Latch — die Grid-Suche kann zwischen den Parametern folglich gar nicht unterscheiden. Eine erweiterte Suche (Schwellen bis 25 %, Cooldowns bis 90 Tage) zeigt, dass der Effekt trotzdem nicht auf Messers Schneide steht: Der Wiedereinstieg bleibt bestehen, die Rendite sinkt graduell +55 % → +40 % → +24 %, **nie unter die Referenz von +13,14 %**.

3. **Die Whipsaw-Sorge ist weder bestätigt noch widerlegt.** 0 falsche Wiedereinstiege in allen 27 Kombinationen — bei genau **einem** Wiedereinstieg insgesamt. Das ist keine Entlastung des Latches, das ist Stichprobengröße 1. Exakt dieselbe Kategorie wie der `TREND_STOP_LIMIT_OFFSET_PCT`-Fund (2 simulierte Stop-Loss-Exits, siehe 6f): eine Frage, die der Backtest mangels Ereignissen nicht beantworten kann. Der eine Wiedereinstieg ist zudem am Periodenende offen, seine +41,89 % hängen also am gewählten Enddatum.

**Entscheidung: vorerst nicht umsetzen, n = 1 ist nicht ausreichend.** Der Mechanismus sieht in dem einen Fall, in dem er überhaupt wirken konnte, nützlich und harmlos aus — aber aus einem einzigen Ereignis eine Parameterwahl abzuleiten wäre Overfitting mit maximaler Stichprobenarmut, und zwar an einer Sicherheitssperre. Die Entscheidung fällt mit echten Daten aus der laufenden Paper-Trade-Phase, gleiches Vorgehen und gleiche Begründung wie beim Stop-Limit-Offset. Bis dahin gilt unverändert: Nach einem Trend-Stop-Loss setzt ein Mensch zurück (`python -m dca_bot.reset_trend_stop_loss`), und genau das ist der Punkt des Latches.

**Tests:** 25 neue in `tests/test_trend_auto_reset.py`, Gesamtstand **523, alle grün**. Wirksamkeit wieder gemessen: Kontrolllauf 0 Fehlschläge, alle 8 Mutationen gefangen (UND→ODER → 10, Schwelle `>=`→`>` → 2, Cooldown-Off-by-one → 1, falscher Anker → 1, „falsch" per PnL statt Ausstiegsgrund → 1, Wiedereinstiegs-Markierung → 5, offener Wiedereinstieg → 2, fehlender Modus-Ausschluss → 1).

**Und wieder dieselbe Falle wie in Stufe 2 und bei W17:** Die Anker-Mutation meldete zunächst 0 Fehlschläge. Ursache diesmal nicht ein mehrdeutiges Suchmuster, sondern eine echte Testlücke — der vorhandene Test prüfte `_auto_reset_is_due()` selbst, also die *Rechnung*, nicht die *Verdrahtung* in der Backtest-Schleife. Reicht diese den falschen Wert als Anker herein, rechnet die Funktion weiterhin korrekt, nur mit der falschen Zahl. Dafür gibt es jetzt einen eigenen Test über eine 30-%-Schwelle, die genau zwischen den beiden Kandidaten liegt (Ausstiegskurs 90,00 → 117,00 erreichbar; rechnerische Schwelle 95,40 → 124,02 unerreichbar). Das Warnsignal war zum dritten Mal dasselbe: ein Messergebnis, das zu einem offensichtlich einschlägigen Test nicht passt.

Ein kleiner Nebenbefund noch: `100.0 * 1.1` ergibt in Fließkomma `110.00000000000001`, eine Erholungsschwelle bei krummen Prozentwerten ist also nicht exakt erreichbar. Die Vergleichsform ist projektkonform (`is_stop_loss_hit` und `is_trend_break_stop_loss_hit` rechnen genauso, Decimal ist in `order_utils.py` den Ordermengen vorbehalten, wo die Börse ablehnt), für eine Analyse ist der Bruchteil eines Cents bedeutungslos. Die Testkonstanten sind deshalb binär exakt gewählt (25 % statt 10 %), damit „die Schwelle zählt inklusive" den Vergleichsoperator prüft und nicht ein Darstellungsartefakt.

### Offen aus der Liste

**Stufe 3 (später oder bewusst nicht):** Punkt 16 (automatischer Stop-Loss-Reset) ist **durchgespielt und bewusst zurückgestellt** — siehe den Abschnitt direkt darüber. Die frühere Einschätzung „größter Hebel der Liste (~40 Prozentpunkte in 2023)" bleibt der Größenordnung nach richtig, ruht aber auf einem einzigen Ereignis; das war vor dem Experiment nicht sichtbar. Punkt 13 (gemeinsame Bot-Runtime) ist reiner Wartbarkeitsgewinn und fasst alle vier Einstiegspunkte gleichzeitig an — nach dem Cutover am 05.10., nicht davor. Punkt 15 (SQLite) ist bei aktuell 1–6 Ledger-Einträgen und ein paar Trades pro Tag Jahre entfernt. Punkt 17 (Dashboard) bleibt für 300 € Kapital Overkill. `.bak`-Kopien aus Punkt 2 entfallen: atomare Writes plus tägliche VM-Snapshots plus Git decken das ab.

*(Aktualisiert 17.09.2026: Punkt 17 ist umgesetzt — allerdings anders, als die Liste ihn gemeint hat, und deshalb bleibt die Einschätzung „Overkill" oben stehen statt gestrichen zu werden. Gemeint war ein Dashboard **in diesem** Repository, mit dem Aufwand und der Angriffsfläche der Bots selbst. Gebaut wurde stattdessen eine separate, rein lesende App in einem eigenen Repository ([crypto-bot-app](https://github.com/EliasNein/crypto-bot-app)): Sie liest nur die Ledger-Dateien und hat keinen Zugriff auf API-Keys oder Trading-Funktionen. Damit berührt sie das Trennungsprinzip nicht — dieselbe Überlegung wie bei `audit_positions.py`, das als rein lesendes Werkzeug ebenfalls mehr sehen darf als jeder einzelne Bot, ohne dass ihm jemand Handelsfähigkeit zugestehen müsste. In der README steht der Verweis darauf gleich zu Beginn.)*

---

## 7. Technische Referenz (aus der README hierher verschoben, 25.09.2026)

Dieser Abschnitt beschreibt den **aktuellen Stand** der Bots und ihrer
Sicherheitsmechanismen - anders als das chronologische Log in Abschnitt 6.
Bis zum 25.09.2026 stand er in der README, die dadurch auf über 1.200
Zeilen angewachsen war. Die README ist seitdem die schlanke Einstiegs- und
Setup-Dokumentation mit einer Kurzübersicht der Sicherheitsmechanismen;
die ausführlichen Texte stehen hier. Sie sind **wörtlich übernommen** -
angepasst wurden nur Verweise auf Abschnittsnummern, die sich durch den
Umzug geändert haben. Konfiguration, Start und Werkzeuge: README.

### 7.1 Botübergreifende Sicherheitsmechanismen

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
  Börse per `get_order()` nach dieser ID, was tatsächlich passiert ist.
  Dasselbe gilt für eine Antwort von Binance, deren Ausgang laut
  Binance-Doku unbekannt ist (HTTP 5xx, Fehlercodes −1006/−1007) - sie
  ist keine Ablehnung, auch wenn python-binance sie als
  `BinanceAPIException` meldet:
  ausgeführt → die echten Order-Daten werden zurückgegeben und regulär
  verbucht; nie angenommen (Fehlercode −2013) → für diesen Zyklus als
  "kein Trade" gewertet, der Eintrag bleibt aber bis zum nächsten Start
  stehen (die Nachfrage kommt unmittelbar nach dem Timeout, eine noch
  laufende Order würde erst danach sichtbar); unklar → **nicht
  geraten**, sondern `ERROR` + Telegram, und
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
  Telegram (`[HEARTBEAT] <Bot> läuft, Version <hash>, letzter
  erfolgreicher Zyklus <Zeitpunkt>`), auch wenn nichts passiert ist. Ohne
  das fällt ein abgestürzter Bot nur durch *ausbleibende* Nachrichten auf
  - und ein stiller Grid-Bot kann "keine Stufe durchquert" oder "seit
  Dienstag tot" bedeuten. Der mitgesendete Zyklus-Zeitstempel
  unterscheidet zusätzlich "Prozess läuft" von "Prozess arbeitet": er
  wird nur nach einem **erfolgreichen** Zyklus gesetzt, ein Zyklus, der
  mit einem Fehler abbricht, lässt ihn stehen (seit 25.09.2026, vorher
  galt jeder Durchlauf). Bewusst **kein** Heartbeat beim
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
- **Füllpreis statt Tickerpreis** (DCA, Grid, Trend, seit 25.09.2026):
  Der Preis, den ein Bot zu einer echten Order ins Ledger schreibt, ist
  der tatsächliche Durchschnitts-Füllpreis aus der Order-Antwort
  (`cummulativeQuoteQty / executedQty`), nicht der kurz vorher
  abgefragte Ticker. Das ist dieselbe Quelle, die die Reconciliation
  immer schon verwendet hat. Beim Trend-Bot hängt daran die
  Stop-Loss-Schwelle (siehe 7.3), bei DCA und Grid die Anzeige in
  Dashboard und Steuer-Export. Im Dry-Run ist der beobachtete Preis der
  simulierte Fill. Vorher geschriebene Einträge sind unverändert.

### 7.2 Grid-Bot

Kauft an festen Preisstufen ("Grid-Stufen") innerhalb einer konfigurierten
Preisspanne und verkauft jede einzelne Position wieder, sobald der Preis auf
die nächsthöhere Stufe steigt - Spot only, kein Hebel, kein
Liquidationsrisiko. Siehe Abschnitt 5 für die
Recherche dazu: der Erwartungswert ist vor Gebühren akademisch mathematisch
null, der Sinn dieser Strategie liegt in der einfachen, latenzunkritischen
Umsetzung, nicht in überlegener Rendite. Haupt-Risiko ist ein Trendbruch.

**Backtest verfügbar** (`python -m dca_bot.grid_backtest`, Code in
`grid_backtest.py`) - siehe „Backtest“ unten und Abschnitt 6 für
die Ergebnisse und einen wichtigen Caveat zur Preisspanne.

#### Kernlogik

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
- Kauf- und Verkaufspreis einer echten Position im Ledger sind der
  tatsächliche Füllpreis aus der Order-Antwort (`cummulativeQuoteQty /
  executedQty`), nicht der kurz vorher abgefragte Ticker - dieselbe
  Quelle wie beim Nachtragen über die Reconciliation. Im Dry-Run ist
  der beobachtete Preis der simulierte Fill. Das Verkaufsziel bleibt
  unabhängig davon die nächsthöhere Grid-Stufe.
- Maximale Kapitalbindung ist durch das Design von selbst begrenzt: Anzahl
  Grid-Stufen × `GRID_AMOUNT_PER_LEVEL` - kein zusätzliches Tageslimit nötig.
- **Dieselbe Entscheidungslogik** (`compute_grid_levels`,
  `find_triggered_buy_levels`, `is_sell_target_hit`,
  `is_trend_break_stop_loss_hit` aus `grid_signals.py`) wird von Backtest
  UND Live-Strategie importiert - keine doppelte Implementierung, die
  unbemerkt auseinanderlaufen könnte (gleiches Prinzip wie beim
  Trend-Bot, siehe 7.3).

#### Sicherheitsmechanismen (eigenständig vom DCA-Bot)

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
- **Echte Positionen werden im Dry-Run nie simuliert geschlossen:** Das
  Spiegelbild dazu. Läuft der Bot mit `GRID_BOT_ENABLE_TRADING=false`,
  während im Ledger echte Positionen (`dry_run: false`) offen sind, wird
  eine solche Position bei erreichtem Ziel weder verkauft noch als
  verkauft gebucht. Sie bleibt offen, ihre Stufe bleibt belegt, und der
  Bot meldet `[GRID-VERKAUF-GESPERRT]` (Telegram einmal pro Position und
  Prozesslauf). Bis zum 25.09.2026 wurde hier ein Erlös aus
  `quantity * price` erfunden und die Position geschlossen, obwohl das
  BTC weiter an der Börse lag.
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
- **Telegram-Benachrichtigungen** (falls konfiguriert, siehe README Abschnitt 7):
  `[GRID-KAUF]`/`[GRID-KAUF DRY-RUN]`, `[GRID-VERKAUF]` (mit realisiertem
  Gewinn/Verlust dieser Position), `[GRID-VERKAUF-FEHLGESCHLAGEN]`,
  `[GRID-VERKAUF-GESPERRT]`,
  `[GRID-STOP-LOSS]`, `[GRID-NOTAUS]`, `[GRID-FEHLER]`.
- **Mengenlimit für Zyklusfehler:** Ein fehlgeschlagener Zyklus meldet
  `[GRID-FEHLER]` per Telegram nur beim ersten Auftreten seines
  Fehlertyps (Exception-Klasse). Weitere gleichartige Fehlschläge gehen
  nur noch ins Log, bis ein Zyklus wieder erfolgreich war - dann ist die
  Sperre aufgehoben. Ein neuer Fehlertyp mitten in einer Störung wird
  sofort gemeldet. Vorher kamen bei einer längeren Störung zwölf
  identische Meldungen pro Stunde.

#### Backtest

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
Abschnitt 6 für die vollständigen Ergebnisse.

### 7.3 Trend-Following-Bot

EMA-Crossover-Strategie auf Tageskerzen mit Trendstärke-Filter, long-only
(Spot, kein Shorting). Siehe Abschnitt 5 für die
Recherche: Trend-Following ist die akademisch am besten belegte
Alpha-Strategie (Liu & Tsyvinski, Gbadebo), Hauptrisiken sind Overfitting
und Momentum-Crashes.

**Vor dem ersten Dry-Run wurde die Strategie per Backtest über drei
historische Marktphasen validiert** (`python -m dca_bot.trend_backtest`,
Code in `trend_backtest.py`) - siehe Abschnitt 6 für die
Ergebnisse und deren ehrliche Einordnung (schützt im Bärenmarkt, verpasst
ohne periodischen manuellen Stop-Loss-Reset einen Teil der Rendite im
Bullenmarkt).

#### Kernlogik

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

#### Sicherheitsmechanismen (eigenständig von DCA/Grid)

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
  Abschnitt 6i) und bewusst **nicht** umgesetzt: Über alle
  drei Referenz-Zeiträume und 27 Parameter-Kombinationen gab es genau
  ein auswertbares Ereignis, und aus n=1 lässt sich keine Parameterwahl
  für eine Sicherheitssperre ableiten. Entschieden wird das mit echten
  Daten aus der Paper-Trade-Phase - gleiches Vorgehen wie beim
  `TREND_STOP_LIMIT_OFFSET_PCT` (siehe „Echter, exchange-seitiger Stop-Loss“ unten).
- **Telegram-Benachrichtigungen** (falls konfiguriert, siehe README Abschnitt 7):
  `[TREND-EINSTIEG]`/`[TREND-EINSTIEG DRY-RUN]`, `[TREND-AUSSTIEG]` (mit
  realisiertem Gewinn/Verlust und Ausstiegsgrund),
  `[TREND-VERKAUF-FEHLGESCHLAGEN]`, `[TREND-AUSSTIEG-GESPERRT]`, `[TREND-STOP-LOSS]`,
  `[TREND-WARNUNG]`, `[TREND-ABSICHERUNG-WIEDERHERGESTELLT]`,
  `[TREND-NOTAUS]`, `[TREND-FEHLER]`.

#### Echter, exchange-seitiger Stop-Loss

Zusätzlich zum software-internen Stop-Loss (siehe oben) platziert der Bot
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
  Orderbuch hängen bleibt. `entry_price` ist bei einer echten Order der
  tatsächliche Füllpreis des Kaufs (`cummulativeQuoteQty /
  executedQty`), nicht der kurz vorher abgefragte Ticker - dieselbe
  Basis gilt damit für die Order an der Börse, den internen Stop-Loss
  und jede spätere Ersatz-Order. Ebenso ist der gespeicherte
  Ausstiegspreis der Füllpreis des Verkaufs.
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
  sowohl vom Zyklus-Check als auch vom Pending-Orders-Pfad (7.1)
  verwendet. Vorher hatten beide eigene, leicht unterschiedliche
  Regeln.
- **Reconciliation beim Bot-Start:** bevor der erste reguläre Zyklus
  läuft, gleicht der Bot eine im Ledger offene Position gegen den
  tatsächlichen Order-Status bei Binance ab und korrigiert den Ledger
  sofort, falls die Stop-Order während der Downtime gefüllt wurde -
  klar geloggt als `[REKONZILIATION]`. Davor läuft seit dem K2-Fix
  `reconcile_pending_orders()` (siehe 7.1), und diese
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
- **Echte Positionen werden im Dry-Run nicht angefasst:** Das
  Spiegelbild dazu. Läuft der Bot mit `TREND_BOT_ENABLE_TRADING=false`,
  während eine echte Position offen ist, führt er einen fälligen
  Ausstieg (Signal oder interner Stop-Loss) nicht aus. Er storniert
  keine Stop-Order, verkauft nicht, bucht nichts und setzt keinen Latch.
  Die Position bleibt offen, die Stop-Order an der Börse schützt sie
  weiter, und der Bot meldet `[TREND-AUSSTIEG-GESPERRT]`. Bis zum
  25.09.2026 stornierte er in diesem Fall die echte Stop-Order und
  schloss die Position mit erfundenem Erlös. Zusätzlich wirft
  `cancel_order()` im `TradingClient` bei deaktiviertem Trading eine
  Exception, statt zu stornieren – eine zweite Sicherung, falls ein
  künftiger Aufrufer die Prüfung vergisst.
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
  **Bei deaktiviertem Trading** wird für eine echte Position keine Order
  platziert, der fehlende Schutz aber trotzdem gezählt und ab 3 Zyklen
  gemeldet. Die Meldung zu einer verschwundenen Stop-Order sagt dann
  ausdrücklich, dass kein Ersatz möglich ist. Eine Position ohne
  `dry_run`-Feld bekommt keine Order, sondern `[TREND-POSITION-UNKLAR]`.
- **Dry-Run** (`TREND_BOT_ENABLE_TRADING=false`): es wird KEINE echte
  Stop-Order platziert, nur geloggt ("[DRY-RUN] Würde
  Stop-Loss-Order platzieren..."). Die Position bleibt dann wie bisher
  ausschließlich software-intern überwacht - gleiches Sicherheitsprinzip
  wie bei der Entry-Order (kein Trading ohne Opt-in).
- **Erledigt (war: TODO vor Echtgeld):** Stop-/Limit-Preis wurden früher
  nur auf 2 Nachkommastellen gerundet, nicht gegen die echte
  `PRICE_FILTER`-Tick-Size des Symbols validiert. Seit dem K3-Fix werden
  beide Preise und die Menge gegen die tatsächlichen `exchangeInfo`-Filter
  quantisiert (siehe 7.1) - die Menge zusätzlich um die beim Kauf
  abgezogene Handelsgebühr bereinigt, sonst würde die Stop-Order über eine
  nicht mehr vorhandene Menge laufen und von der Börse abgelehnt.
- **Bekannte Einschränkung: `TREND_STOP_LIMIT_OFFSET_PCT`-Default (0,5%)
  basiert auf einer zu kleinen historischen Stichprobe** (Backtest-
  Analyse über die drei Referenz-Zeiträume ergab nur 2 simulierte
  Stop-Loss-Exits insgesamt, siehe 6f) - wird
  während der monatelangen Paper-Trade-Phase anhand echter Fill-Daten
  (siehe Fill-Analyse-Logging oben) überprüft, bevor der Wert für den
  Live-Gang final bestätigt wird.

### 7.4 Kapital-Allocator

Stufenlose Umschichtung von Kapital zwischen DCA-Bot und Trend-Following-Bot
je nach aktueller Trendstärke (EMA-Abstand) - **kein** eigenständiger
Trading-Bot, sondern ein steuernder Zusatzprozess. Grid-Bot bleibt davon
unberührt (hat bereits einen eigenen Trendbruch-Stop-Loss, siehe
7.2). Der Allocator platziert selbst **nie** Orders - er berechnet nur eine
Zahl (den Trend-Following-Anteil zwischen 0% und 100%) und schreibt sie in
seine State-Datei.

Konfiguration und Start: README Abschnitte 3.3 und 4.

#### Kernlogik

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
  die Zuteilung nur bei explizitem Opt-in (siehe README 3.3) unmittelbar vor
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

#### Sicherheitsmechanismen (eigenständig von DCA/Grid/Trend)

- **Notaus**: eigene Datei (`ALLOCATOR_KILL_SWITCH_FILE`, Default
  `STOP_ALLOCATOR`) und eigene Env-Variable (`ALLOCATOR_HALT`) -
  unabhängig von DCA/Grid/Trend. Der Allocator platziert ohnehin nie
  Orders, der Notaus stoppt hier nur die Berechnung/State-Aktualisierung.
- **Telegram-Benachrichtigungen**: `[ALLOCATION-UPDATE]` (bei
  signifikanter Verschiebung), `[ALLOCATOR-NOTAUS]`, `[ALLOCATOR-FEHLER]`.
  Für `[ALLOCATOR-FEHLER]` gilt dasselbe Mengenlimit wie beim Grid-Bot
  (siehe 7.2): pro Fehlertyp eine Meldung, bis ein Zyklus wieder
  erfolgreich war.

### 7.5 Positions-Audit

Aufruf: `python -m dca_bot.audit_positions` (siehe README Abschnitt 8.1).

Gedacht als Überblick, bevor ein pausierter Bot wieder freigeschaltet
oder `*_BOT_ENABLE_TRADING` umgestellt wird - dann ist auf einen Blick
sichtbar, welche offenen Positionen an der Börse tatsächlich existieren
(`ECHT`) und welche nur simuliert wurden (`DRY-RUN`, werden nie real
verkauft, siehe 7.2/7.3). Der DCA-Abschnitt zeigt zusätzlich
Menge, Einsatz und durchschnittlichen Einstandspreis - der Bot verkauft
nie, seine Summe aller echten Käufe *ist* sein Bestand.

Pfade kommen aus `DCA_BOT_STATE_FILE`/`GRID_STATE_FILE`/
`TREND_STATE_FILE` bzw. den üblichen Defaults, alternativ über
`--dca-file` / `--grid-file` / `--trend-file`.

#### Bot-übergreifender Kontoabgleich

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

### 7.6 Tests

Was die einzelnen Testdateien prüfen, steht bei den jeweiligen Fixes in
6f, 6g und 6i. Hier steht nur, was dort fehlt:

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

---

*Diese Datei dient als lebendes Projektdokument und sollte bei neuen Entscheidungen und Recherche-Ergebnissen aktualisiert werden. Stand 13.09.2026: zusammengeführt aus zwei parallel gepflegten Versionen (Chat-Artefakt + lokale Claude-Code-Fortschreibung).*

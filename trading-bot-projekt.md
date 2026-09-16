# Trading-Bot-Projekt: Planung & Recherche

**Stand:** 14. September 2026
**Status:** Testnet-Betrieb – drei Strategien laufen parallel auf einem gemieteten VPS, vierter Baustein (Allocator) backgetestet, Live-Test steht noch aus. Kein Live-Geld bisher.

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

**Anbieter:** Contabo Cloud VPS 4 (4 vCPU, 8 GB RAM, 100 GB SSD), Ubuntu 24.04, 1 Monat Laufzeit für 6,55€. Bestellt 12.09.2026, **Kündigung bereits zum 12.10.2026 gesetzt** (verhindert automatische Vertragsverlängerung; Server läuft bis dahin regulär weiter). Server-IP: 161.97.113.170, Projektpfad `/root/crypto-bot`.

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
1. **Sicherheitsreview (Code + Infrastruktur) mit Claude Opus 5** – bewusst zurückgestellt bis kurz vor Live-Gang, jetzt zeitlich relevant
2. **Echter, exchange-seitiger Stop-Loss** – im Code umgesetzt (siehe 6f), noch nicht deployed/live getestet
3. Entscheidung zur Kapitalverteilung auf die Strategien (nach Auswertung der Testmonat-Ergebnisse, inkl. Allocator-System)
4. Home-Netzwerk-Absicherung prüfen (Router-Firewall, ggf. VPN-Zugriff statt offener Ports)
5. Allocator-System (siehe 5a) fertig getestet und verifiziert – Backtest abgeschlossen, Live-Dry-Run steht noch aus, falls bis dahin nicht nachgeholt

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

### Allocator-Live-Dry-Run gestartet (15.09.2026)

Kapital-Allocator läuft jetzt live auf der Homeserver-VM als vierter, komplett isolierter systemd-Service (`allocator.service`, gleiches Muster wie die drei Bot-Services).

- **Konfiguration:** Alle `ALLOCATOR_*`-Variablen aus `.env.example` übernommen (Default-Werte, keine Anpassung nötig). `DCA_ALLOCATOR_STATE_FILE`/`TREND_ALLOCATOR_STATE_FILE` bestätigt auskommentiert (inaktiv) - kein Opt-in, DCA und Trend bekommen vom Allocator nichts mit, laufen unverändert weiter.
- **Verifiziert per Log und State-Datei:** Historie geladen (81 Tageskerzen), Trendstärke-Berechnung läuft fehlerfrei im 60-Minuten-Zyklus. Erster Messwert: Trendstärke 5,25 % (Richtung "up", über dem `ALLOCATOR_FULL_ANCHOR_PCT`-Anker von 3,0 %) → berechneter Trend-Anteil 100 %, DCA-Anteil 0 % (`data/allocator_state.json` bestätigt: `trend_fraction: 1.0`, `gap_pct: 5.25`). Rein beobachtend, keine Wirkung auf DCA/Trend, da Opt-in weiterhin deaktiviert.
- **Läuft ausschließlich auf dem Homeserver**, nicht auf dem VPS (siehe korrigierte Grundsatzentscheidung oben).

## 6f. Trend-Bot: Echter, exchange-seitiger Stop-Loss (15.09.2026)

Umgesetzt (nur lokaler Code, noch nicht deployed/committet zum Zeitpunkt dieses Eintrags): der Trend-Bot platziert jetzt bei jedem Entry zusätzlich zur software-internen Überwachung eine echte `STOP_LOSS_LIMIT`-Order direkt an der Börse (`binance_client.place_stop_loss_limit_sell`), siehe README.md Abschnitt 9.5 für die vollständige Dokumentation. Schützt eine offene Position auch bei Ausfall des Bot-Prozesses (Strom-/Internetausfall zuhause) – der bisherige software-interne Stop-Loss wirkt nur, solange der Prozess läuft.

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

**Auflösung des konkreten Homeserver-Zustands:** Die dort offenen Positionen (6 Grid, 1 Trend) sind laut Ledger **alle** `dry_run: true`. Nach dem Fix kann für sie kein Codepfad mehr eine echte Verkaufsorder auslösen, unabhängig von `*_BOT_ENABLE_TRADING` - ein Bereinigen der Ledger-Dateien ist deshalb nicht nötig, das Wiederfreischalten per Notaus-Entfernung ist ungefährlich. Neu dafür: `python -m dca_bot.audit_positions` listet alle offenen Positionen beider Bots mit Dry-Run-Status auf, rein lesend, ohne API-Keys (siehe README Abschnitt 11). Gegen die echten Ledger-Dateien verifiziert.

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

**Bekannte Restlücke, bewusst offen:** Antworten von `get_order()` (also der Pfad „exchange-seitige Stop-Order war bereits gefüllt") enthalten keine `fills` – dort bleibt die Verkaufsgebühr mangels Daten unberücksichtigt, der PnL dieses einen Exit-Pfads ist also weiterhin um ca. 0,1% zu optimistisch. Sauber lösbar nur über eine zusätzliche `myTrades`-Abfrage.

**Tests:** 36 neue. `tests/test_order_utils.py` (22, reine Funktionen inkl. der Decimal-Off-by-one-Falle und des „Menge exakt gleich stepSize"-Falls), `tests/test_dca_fee_adjustment.py` (5), plus `TrendTradingRulesTestCase` (7) und `GridTradingRulesTestCase` (7). Beide Fake-Clients liefern jetzt realistische `fills` mit `commission`/`commissionAsset` und implementieren `get_symbol_trading_rules` – der Gebührensatz bleibt per Default 0.0, weil das exakt dem beobachteten Testnet-Verhalten entspricht; die neuen Tests setzen 0,1%. Gesamtstand: 87 Tests, alle grün.

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

Die Formel steckt bereits im Code (`grid_strategy.py`, Log-Zeile beim Start): `(Anzahl Stufen − 1) × GRID_AMOUNT_PER_LEVEL`. Die oberste Stufe ist reine Verkaufsstufe, `find_triggered_buy_levels()` iteriert über `levels[:-1]` — es gibt immer eine Kaufstufe weniger als Stufen.

| | Spanne | Abstand | Stufen | Kaufstufen | Betrag/Stufe | Max. Kapitalbindung |
|---|---|---|---|---|---|---|
| **VPS** | 68.000 – 87.585 | 1,5 % | 18 | 17 | 15,00 | **255,00 €** |
| **Homeserver** | 70.000 – 88.829 | 1,5 % | 17 | 16 | 15,00 | **240,00 €** |
| Grid-Topf laut 5b | | | | | | 150,00 € |

**Ergebnis: Die aktuelle Konfiguration passt nicht zum geplanten Topf.** Der VPS liegt 70 % darüber, der Homeserver 60 %.

Datenherkunft, damit klar ist was gemessen und was abgeleitet ist: Die VPS-Zeile ist direkt belegt — dieselbe Konfiguration lief am 10.09. lokal, und `logs/grid_bot.log` enthält wörtlich `Grid initialisiert: 18 Stufen von 68000.00 bis 87585.38 (Abstand 1.50%, max. Kapitalbindung ca. 255.00)`. Die Homeserver-Zeile ist **abgeleitet**: 6e protokolliert nur „Grid mit 17 Stufen initialisiert", und 17 Stufen ergeben sich exakt aus den `.env.example`-Werten (70.000–90.000 @ 1,5 %) — plausibel, weil der Homeserver frisch aus dem Repo aufgesetzt wurde. Gegenzuprüfen mit `grep -E 'GRID_(LOWER|UPPER|SPACING|AMOUNT)' .env` bzw. `grep "Grid initialisiert" logs/grid_bot.log`.

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

## 6h. Allocator-Opt-in aktiviert - vollständiges System live (16.09.2026)

Nach Abschluss des kompletten Sicherheitsreviews (K1-K5, alle 18 W-Punkte, Infrastruktur-Härtung) wurde das Allocator-Opt-in für DCA und Trend auf dem Homeserver aktiviert (DCA_ALLOCATOR_STATE_FILE, TREND_ALLOCATOR_STATE_FILE gesetzt). Damit läuft erstmals das vollständige, integrierte Vier-Bausteine-System im Testnet-Live-Betrieb: DCA und Trend lesen jetzt die Allocator-Zuteilung vor jeder neuen Order, statt unabhängig voneinander zu handeln.

Bewusst nur auf dem Homeserver, nicht auf dem VPS (dort bleibt der Allocator inaktiv, siehe Grundsatzentscheidung in 6e). Beide Bots starten fehlerfrei mit aktiviertem Opt-in, keine Fehler beim Lesen der Allocator-State-Datei.

Damit beginnt jetzt faktisch die geplante, mindestens einmonatige Live-Testphase des vollständigen Systems vor dem Echtgeld-Einstieg (siehe 5b, 6c).

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

### Offen aus der Liste

**Stufe 2 (vor dem Echtgeld-Schalter, je etwa ein Tag):** Punkt 12 in seiner Grid-Hälfte — direkte Tests für `grid_signals.py` mit echten Kursreihen, analog zu `test_trend_decide_action.py`; begründet durch die beiden historischen Bugs genau dort. Und Punkt 3 in modifizierter Form: der vorhandene `balance_guard` zusätzlich **beim Start** und **auch im DCA-Bot** (der verkauft nie und prüft seinen Bestand deshalb heute überhaupt nicht gegen die Realität). Der bot-übergreifende Gesamtabgleich gehört dagegen nicht in einen Bot, sondern als Erweiterung in `audit_positions.py` — sonst müsste ein Bot fremde Ledger lesen, und das bricht das Trennungsprinzip.

**Stufe 3 (später oder bewusst nicht):** Punkt 16 (automatischer Stop-Loss-Reset) ist der größte Hebel der Liste (~40 Prozentpunkte in 2023 laut eigener Zusatzanalyse), aber eine **Strategie**-Frage: Eine Änderung entwertet die Backtest-Basis, solange sie nicht neu backgetestet ist. Richtiger Zeitpunkt ist die laufende Paper-Trade-Phase, als Backtest-Experiment mit Erholungsschwelle und Cooldown als Parametern. Punkt 13 (gemeinsame Bot-Runtime) ist reiner Wartbarkeitsgewinn und fasst alle vier Einstiegspunkte gleichzeitig an — nach dem Cutover am 05.10., nicht davor. Punkt 15 (SQLite) ist bei aktuell 1–6 Ledger-Einträgen und ein paar Trades pro Tag Jahre entfernt. Punkt 17 (Dashboard) bleibt für 300 € Kapital Overkill. `.bak`-Kopien aus Punkt 2 entfallen: atomare Writes plus tägliche VM-Snapshots plus Git decken das ab.

---

*Diese Datei dient als lebendes Projektdokument und sollte bei neuen Entscheidungen und Recherche-Ergebnissen aktualisiert werden. Stand 13.09.2026: zusammengeführt aus zwei parallel gepflegten Versionen (Chat-Artefakt + lokale Claude-Code-Fortschreibung).*

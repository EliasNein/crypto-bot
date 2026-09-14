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

**Status:** Backtest abgeschlossen und verifiziert. Noch kein Live-Dry-Run gestartet (wie gefordert erst nach dem Backtest) – offen für eine spätere Session.

## 5b. Geplantes Live-Kapital

Nutzer plant beim eventuellen Live-Start mit 100–300€ Echtkapital zu starten (genaue Aufteilung zwischen DCA/Grid/Trend-Following bzw. dem Allocator-System noch offen). Relevant erst nach Abschluss der Testnet-Phase – bei Verteilung auf mehrere Bots ergeben sich entsprechend kleine Positionsgrößen pro Trade, das sollte vor dem Live-Gang nochmal bewusst durchgerechnet werden.

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

**Absicherung:** SSH-Key-Login eingerichtet (Ed25519), Passwort-Authentifizierung deaktiviert (`PasswordAuthentication no` in `sshd_config`). Zusätzlich ein separater, passphrasefreier Deploy-Key für Claude-Code-Automatisierung angelegt (getrennt vom Haupt-SSH-Key, der weiterhin für GitHub etc. mit Passphrase geschützt bleibt).

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
2. **Echter, exchange-seitiger Stop-Loss** statt nur software-interner Überwachung – aktueller Stop-Loss wirkt nur, solange der Bot-Prozess läuft; bei einem Ausfall (Stromausfall/Internetausfall zuhause) wäre eine offene Position sonst ungeschützt
3. Entscheidung zur Kapitalverteilung auf die Strategien (nach Auswertung der Testmonat-Ergebnisse, inkl. Allocator-System)
4. Home-Netzwerk-Absicherung prüfen (Router-Firewall, ggf. VPN-Zugriff statt offener Ports)
5. Allocator-System (siehe 5a) fertig getestet und verifiziert – Backtest abgeschlossen, Live-Dry-Run steht noch aus, falls bis dahin nicht nachgeholt

---

*Diese Datei dient als lebendes Projektdokument und sollte bei neuen Entscheidungen und Recherche-Ergebnissen aktualisiert werden. Stand 13.09.2026: zusammengeführt aus zwei parallel gepflegten Versionen (Chat-Artefakt + lokale Claude-Code-Fortschreibung).*

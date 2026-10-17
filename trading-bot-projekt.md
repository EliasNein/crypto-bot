# Trading-Bot-Projekt: Planung, Fortschritts-Log und technische Referenz

**Stand:** 17. Oktober 2026
**Status:** Testnet-Betrieb, kein Live-Geld. Der Sicherheitsreview (K1–K5, W1–W18, Infrastruktur) ist seit dem 16.09. abgeschlossen. Der Homeserver läuft faktisch seit dem 16.09.2026 als vollständiges System, mit allen vier Bausteinen und aktivem Allocator-Opt-in für DCA und Trend. Der aktuelle Trading-Status dort wurde am 25.09.2026 verifiziert (siehe 6h). Der VPS ist seit dem 07.10.2026 abgeschlossen (Dienste gestoppt, Zugang entfernt, Vertrag gekündigt zum 12.10.), die VPS-Daten werden nicht ausgewertet, und der formale Cutover am 05.10. mit Snapshot-Schritt entfällt (siehe Log 07.10.2026). Die Testphase ist auf ca. 2–3 Monate verlängert, also bis etwa Mitte November bis Mitte Dezember 2026. Seit dem Review sind mehrere Fund-und-Fix-Serien abgeschlossen: die Verbesserungsvorschläge (6i, 17.09.), die Dry-Run-Beträge (22.09.), die Code-Überprüfung vom 25.09. und der Systemcheck vom 27.09. mit K-A/K-B und W-A bis W-G (alle 6g). Am 16.10. kam ein Fund aus dem Betrieb dazu: Market-Orders, die die Börse ohne Ausführung beendet hatte, standen als Positionen mit Menge 0 im Grid-Ledger (Fix Runde 1, siehe Log 16.10.2026). Am 17.10. ist die Dry-Run-Trend-Position vom 15.09. geschlossen worden, seitdem läuft die erste echte Trend-Position mit Stop-Order an der Börse (siehe Log 17.10.2026). Die technische Referenz zum aktuellen Stand steht in Abschnitt 7.

---

*Ältere, abgeschlossene Historie (Abschnitte 1–6i: Recherche, Planung und das chronologische Log bis 28.09.2026) steht unverändert in `trading-bot-projekt-archiv.md` und muss nur bei Bedarf gelesen werden, etwa bei einer Rückfrage zur ursprünglichen Strategiewahl. Verweise wie „siehe 6g“ in Code und Doku meinen die Abschnitte dort. Was davon heute noch offen ist, fasst der Abschnitt „Aktueller Stand und offene Punkte“ zusammen.*

---

## Aktueller Stand und offene Punkte

*Stand 17.10.2026 für Deploy-Stand, Vorbedingungen, Auswertung der Testphase und die Zwangstrennung (Betrieb), 07.10.2026 für VPS und Termine, übrige Angaben Stand 29.09.2026. Dieser Abschnitt beschreibt wie Abschnitt 7 den aktuellen Stand und wird direkt korrigiert. Die Herleitung steht jeweils im Archiv (`trading-bot-projekt-archiv.md`), Abschnittsnummern und Überschriften sind dort unverändert.*

### Betrieb

- **Homeserver** (vollständiges System seit 16.09.2026): alle vier Bots als systemd-Services im Testnet. DCA, Grid und Trend handeln mit echten Testnet-Orders (`*_BOT_ENABLE_TRADING=true`, verifiziert 25.09.), das Allocator-Opt-in für DCA und Trend ist aktiv. `GRID_AMOUNT_PER_LEVEL` = 9,38, maximale Kapitalbindung ca. 150,08. Details: Archiv 6e, 6h, 6g „W16 umgesetzt“.
- **VPS:** abgeschlossen seit 07.10.2026. Die drei Bot-Dienste (dca-bot, grid-bot, trend-bot) sind gestoppt und deaktiviert, `.env` und Archivdatei auf dem VPS sind gelöscht, der Claude-Code-Deploy-Schlüssel (claude-code-vps-deploy) ist aus `authorized_keys` entfernt, der VPS-Eintrag aus `known_hosts` auf dem lokalen Rechner ebenfalls. Es gibt keine Auswertung der VPS-Daten und keinen behaltenen Snapshot. Details: Log 07.10.2026.
- **Paar:** im Testnet BTCUSDT, alle „€“-Beträge sind dort USDT. Für echtes Geld wird BTCEUR verwendet (Entscheidung 28.09.2026). Details: Archiv 5b (Vermerk 28.09.), 6g „Symbolbindung“.
- **Zwangstrennung:** gemessen an den Logzeilen „Unerwarteter Fehler im Grid-Zyklus“ (UTC): 26.09. 00:38, 30.09. 00:33, 02.10. 00:31, 03.10. 00:31, 04.10. 00:29, 05.10. 00:27:02, 07.10. 00:26:52, 08.10. 00:24:25, 09.10. 00:21:52, 10.10. 00:22:50, 12.10. 00:19:06, 13.10. 00:20:09, 14.10. 00:16:22, 15.10. 00:18:10, 16.10. 00:14:31, 17.10. 00:13:36. Ab dem 05.10. ist es jeweils die erste solche Zeile der Nacht, bis zum 16.10. von Elias am 16.10.2026 abgefragt. Der Wert vom 17.10. stammt aus dem Nachtcheck vom 17.10.2026 (einzige solche Zeile der Nacht, erste Nacht unter `76f261b`). Am 06.10. und 11.10. gab es keine solche Zeile (Grund nicht geprüft). Gemessene Drift rund 1,1 Minuten pro Tag nach vorne (00:27 am 05.10. auf 00:14 am 16.10.). Die Zeile zeigt den ersten betroffenen Zyklus, die Trennung selbst begann bis zu fünf Minuten früher. Pro Nacht steht nur eine Zeile, die Trennung dauert daher vermutlich unter etwa fünf Minuten (Schluss aus der Zahl der Zeilen, nicht gemessen). Sperrfenster für Eingriffe am Server: einheitlich 23:50 bis 00:30 UTC. Begründung: Die Fehlerzeile erreicht bei 1,1 Minuten Drift pro Tag 00:05 UTC etwa am 25.10., der Beginn der Trennung (bis zu fünf Minuten früher) bereits um den 20.10. Das Fenster deckt die Zeile bis etwa Anfang November. Das ist eine Fortschreibung des gemessenen Drifts, keine Messung. Neu messen bis spätestens 25.10.2026 (Befehl: `journalctl -u grid-bot --since <Datum> | grep 'Unerwarteter Fehler im Grid-Zyklus'`) und das Fenster danach nach der echten Lage setzen.

### Deploy-Stand

- Deployed: `76f261b` auf Homeserver am 16.10.2026. Grid-Bot um 14:32 UTC, DCA, Trend und Allocator um 14:40 UTC neu gestartet, alle vier mit „Code-Version: 76f261b“, Symbolprüfungen „passt“, Bestandsabgleich in Ordnung. Gegenüber dem vorherigen Stand `980f3c3` (deployt 29.09.2026, mit W-C bis W-G samt Nachtrag und der Symbolbindung) laufen dort jetzt zusätzlich das Werkzeug `close_dry_run_trend` (am 17.10.2026 angewendet) und der Fix vom 16.10.2026 zu Market-Orders ohne Ausführung samt Werkzeug `remove_unfilled_grid_positions` (am 16.10.2026 angewendet). Ablauf und Ergebnis: Log 16.10.2026, „Bereinigung und Deploy“, Rückweg auf `980f3c3` dort unter „Rückweg“. Auf master seitdem nur Doku. Bei jedem Deploy nach dem Pull und vor dem Neustart: `python -m dca_bot.symbol_guard --report`.
- Deploys werden ab jetzt **hier** vermerkt, als `Deployed: <hash> auf Homeserver am <Datum>`. Das ersetzt den Vermerk vom 29.09.2026 in Archiv 6g. Details zum Rückweg auf den alten Code: Archiv 6g „Symbolbindung“.

### Termine

- **12.10.2026, Vertragsende VPS** (Contabo Cloud VPS 4 (2026), gekündigt zum 12.10.2026, laut Kundenbereich bis dahin abgerechnet, keine Zusatzposten): kein Handlungsbedarf mehr.
- **Testphase** auf dem Homeserver bis etwa Mitte November bis Mitte Dezember 2026. Details: Archiv 6h.

### Vorbedingungen für echtes Kapital (300 €: 150 € Grid, 150 € Allocator-Topf)

1. **Positionsgrößen:** offen sind `DCA_QUOTE_AMOUNT`, `TREND_AMOUNT_PER_TRADE`, Grid-Spanne und `GRID_SPACING_PCT`. Beim Paarwechsel sind alle Beträge und die Spanne neu in Euro festzulegen. Details: Archiv 5b, 6d Punkt 3.
2. **Datenbasis für `TREND_STOP_LIMIT_OFFSET_PCT`**, bisher n = 2 simulierte Exits. **Status: Trend-Prozedur am 17.10.2026 durchgeführt, echter Einstieg mit Stop-Order, noch keine Fill-Daten.** Die Dry-Run-Position vom 15.09. ist mit `python -m dca_bot.close_dry_run_trend` als `manual_close` geschlossen, ohne Sperre. Seitdem läuft die erste echte Trend-Position (`bd1c3457-…`, Einstieg 81.726,36, Menge 0.00018 BTC) mit Stop-Order an der Börse (orderId 3807835, Stop 73.553,72, Limit 73.185,95, Status `NEW`). Kalibrierungsdaten entstehen erst, wenn diese Stop-Order an der Börse gefüllt wird (Zeile `[STOP-FILL-ANALYSE]`). Schließt die Position über den Stop-Loss, sperrt der Latch neue Einstiege bis zum manuellen Reset (`python -m dca_bot.reset_trend_stop_loss`). Details: Archiv 6f, 6h „Trend-Bot: Die Kalibrierungsdaten fließen noch nicht“, Log 17.10.2026.
   Trend-Prozedur (Ablauf: Log 07.10.2026 mit Nachtrag vom 16.10.2026): durchgeführt am 17.10.2026, Ergebnis im Log 17.10.2026. Als Datenbasis für den Offset taugt das Testnet aber kaum: Laut Auswertung der öffentlichen Kerzen zeigt es an etwa 4 % der Stunden ein Tief mehr als 10 % unter dem Mainnet. Eine echte Stop-Order wird dort vermutlich von einem Ausreißer ausgelöst, nicht vom Markt. Löst ein Ausreißer die Stop-Order aus, ist das ein Technik-Test der Kette (Stop-Fill, Verbuchung, Sperre, manueller Reset), kein Kalibrierungswert. Gefüllte Stop-Orders im Testnet belegen die Technik, nicht den Offset.
3. **Abschließender Sicherheitsreview** kurz vor dem Live-Gang. Details: Archiv 6d, 6h.
4. **Paarwechsel auf BTCEUR**, noch nicht geplant: alle vier `*_SYMBOL`, Grid-Spanne und Beträge in Euro, frische Ledger oder bewusst weitergeführter Altbestand. Offen sind außerdem die Dashboard-App und der Pilot. Nicht verifiziert ist, ob Binance bei einer Abfrage unter dem falschen Symbol mit −2013 antwortet, das lässt sich erst im Pilot prüfen. Details: Archiv 6g „Symbolbindung“, 6h.
5. **„Gebühren mit BNB bezahlen“ ausgeschaltet.** Details: Archiv 6h.
6. **Unterkonten pro Bot:** vor dem Live-Gang bewusst entscheiden, keine harte Vorbedingung. Fällt die Entscheidung dafür, braucht es Code (eigene Schlüssel je Bot, Audit über mehrere Konten) vor dem Live-Gang. Details: Archiv 6h (Ergänzung 29.09.), 6g „Systemcheck vom 27.09.2026“.
7. **Kaufpfad prüft den Ausführungsstatus:** Die Antwort jeder Market-Order wird vor dem Buchen gegen Status und `executedQty` bewertet, dazu lehnen die Ledger echte Einträge ohne Menge oder Einsatz ab (A1/A3, seit 16.10.2026 auf dem Homeserver deployt). Offen: Erfüllt erst, wenn auf dem Server belegt ist, dass eine Order ohne Ausführung im Journal als `[ORDER-OHNE-AUSFUEHRUNG]` erscheint und nicht als Kauf. Der Nachweis im Echtbetrieb entsteht, sobald das Testnet wieder eine Market-Order ohne Ausführung liefert. Beim Trend-Einstieg vom 17.10.2026 hat der Kaufpfad den Status `FILLED` korrekt bewertet, ein Fall ohne Ausführung ist weiter nicht aufgetreten. Details: Log 16.10.2026, Log 17.10.2026.
8. **Teilfüllung beim Verkauf wird korrekt gebucht (Runde 2):** Bis dahin bucht der Bot einen nur teilweise ausgeführten Market-Verkauf über die volle Menge und meldet ihn nur laut (`[GRID-TEILFUELLUNG-UNGEBUCHT]`/`[TREND-TEILFUELLUNG-UNGEBUCHT]`). Details: Log 16.10.2026.

### Bewusst zurückgestellt oder vorgemerkt

- **W14, Grid ohne börsenseitigen Stop-Loss:** eine eigene Architekturentscheidung zwischen einer Sammel-Stop-Order und n Einzel-Stop-Orders. Bis dahin sperrt der Trendbruch-Stop nur Käufe, und die Kapitalbindung ist durch Stufen × Betrag gedeckelt. Details: Archiv 6g „W14“.
- **Automatischer Stop-Loss-Reset (Punkt 16):** im Backtest durchgespielt, n = 1. Entschieden wird mit echten Daten, bis dahin wird manuell zurückgesetzt. Details: Archiv 6i „Punkt 16 als Backtest-Experiment“.
- **Punkt 13 (gemeinsame Bot-Runtime) und F2 (Notaus pausiert statt zu beenden):** zurückgestellt, kein fester Zeitpunkt (der ursprüngliche Cutover am 05.10. entfällt). Voraussetzung: keine offenen Deploys und eine ruhige Woche, weil beide Punkte alle vier Einstiegspunkte anfassen. Details: Archiv 6i „Offen aus der Liste“, 6g „W-F“.
- **DCA-Portfolio-Stop-Loss in den Backtests:** wird nicht abgebildet, die DCA-Zahlen in 5a und 6 überschätzen deshalb den Kapitaleinsatz im Bärenmarkt. Details: Archiv 6g „W-G“.
- **Archivierung der Ledger-Dateien:** kein akuter Bedarf, nur zusammen mit der Dashboard-App. Details: Archiv 6g „Vorgemerkt: langfristiges Datenwachstum“.
- **Füllpreis alter Ledger-Einträge rückwirkend korrigieren:** vorgemerkt für den Steuer-Export. Einträge von vor K2 haben keine `clientOrderId`. Details: Archiv 6g „Priorität 4“.
- **Punkt 15 (SQLite):** bei der heutigen Datenmenge noch Jahre entfernt. Details: Archiv 6i.
- **Idee (Elias, 16.10.2026): Kapitalbudget als fester Anteil am Kontowert, getestet im Testnet.** Ausdrücklich eine Testphase im Binance-Testnet mit Testguthaben, kein echtes Geld (Quote-Währung dort USDT). Den Bots wird nicht mehr ein fester Betrag pro Order zugewiesen, sondern ein fester Anteil des Kontowerts (Beispiel von Elias: 30 %, bei 10.000 wären das 3.000, bei 11.000 entsprechend 3.300). Wächst das Konto durch monatliche Einzahlungen, wächst das Budget der Bots mit. Getestet werden soll das rund ein halbes Jahr mit simulierten monatlichen Aufstockungen um 1.000. Das wäre ein neues Feature (heute sind die Beträge feste Werte in der `.env`), kein bloßes Anheben von Einstellungen. Status: nur festgehalten, nicht entschieden, nicht geplant, kein Auftrag. Offen:
  - Was als Kontowert zählt, ist offen: Am 16.10.2026 lagen laut `check_orders` 9.999,10 USDT und 1,00011 BTC auf dem Testnet-Konto (rund 92.000 USDT insgesamt, das BTC gehört den Bots nicht).
  - Im Testnet gibt es keine Einzahlungen, die Aufstockung müsste simuliert werden.
  - Vorher offen ist Runde 2 (Teilfüllung beim Verkauf buchen, Vorbedingung 8). Die Trend-Prozedur ist am 17.10.2026 durchgeführt.
  - Die Erträge aus dem Testnet bleiben wegen der Ticker-Ausreißer ohne Aussage, es ginge um die Mechanik.

### Für die Auswertung der Testphase

- In den Homeserver-Ledgern von DCA und Trend stehen Dry-Run- und echte Einträge nebeneinander, die Auswertung muss nach `dry_run` trennen. Das Grid-Ledger ist durchgehend echt. Details: Archiv 6h „Umstellung auf echte Orders“.
- Die Trend-Dry-Run-Position vom 15.09. ist seit dem 17.10.2026 als `manual_close` geschlossen. Ihre simulierte `realized_pnl` (+0,93062751) zählt nirgends als Ergebnis. Die Trend-Karte der Dashboard-App zählt den Eintrag als geschlossenen Trade, nicht als Ergebnis (Analyse vom 07.10.2026). Details: Log 07.10.2026, Log 17.10.2026.
- Einen Vergleich VPS gegen Homeserver gibt es nicht: Die VPS-Daten werden nicht ausgewertet (Entscheidung 07.10.2026, Gründe im Log). Details: Archiv 6g „Beobachtung zur Allocator-Wirkung“, 5a.
- Die Dry-Run-Werte des VPS-Grid sind am 22.09. korrigiert. Die `.pre-fix`-Kopie wird nicht mehr gebraucht, weil die VPS-Daten nicht ausgewertet werden. Details: Archiv 6g „Folgefund aus K3“.
- Staub (`dust_qty`) rechnet das Positions-Audit keinem Bot zu, er erscheint als Überschuss. Das gilt für den Trend-Bot seit K-A und für Staub beim Kauf (Grid und Trend) seit dem 16.10.2026. Details: Archiv 6g „Systemcheck vom 27.09.2026“, Log 16.10.2026.
- **Einträge ohne Bestand im Grid-Ledger:** elf offene Positionen mit Menge 0 (Stufen 0 bis 3 seit 09.10., 4 bis 10 seit 11.10.2026) belegten bis zur Bereinigung am 16.10.2026 ihre Stufen. Der Grid-Bot kaufte dort nicht, das Grid-Ergebnis vom 09.10. bis 16.10. ist dadurch zusätzlich verzerrt. Die Kopie `grid_positions.json.pre-remove-20261016T143039Z` auf dem Server enthält sie noch. Ein vor der Bereinigung erstellter CSV-Export führt sie als BUY-Zeilen mit Menge 0 und sollte neu erzeugt werden. Details: Log 16.10.2026.
- **Ticker-Ausreißer im Testnet:** Testnet-Gewinne sind dadurch verzerrt und taugen nicht für Renditeschätzungen. Als Ursache wird ein dünnes Orderbuch vermutet, das ist nicht gemessen. Beispiel 02.10.2026: Vom realisierten Grid-Ergebnis von 8,65 USDT (Auswertung vom 06.10.) entfallen 6,31 USDT auf diesen einen Tag, davon 6,15 USDT auf sechs Stufen (8 bis 13). Sie wurden am 02.10. zwischen 13:30:13 und 13:30:16 UTC zu 77.809 bis 79.480 USDT gekauft und zwischen 13:35:17 und 13:35:30 UTC zu 86.928 bis 86.962 USDT verkauft, je Stufe 0,82 bis 1,09 USDT, normale Zyklen bringen 0,14 bis 0,21 USDT. Die Mainnet-Stundenkerze von 13:00 UTC hatte ihr Tief bei 86.465,72, die Testnet-Kerze bei 75.745,57, das Mainnet-Tagestief lag bei 83.888 (Stundenkerzen, 18:00 UTC). Alle sechs Kaufpreise liegen unter dem Mainnet-Tagestief. Die Prüfung aller Grid-Trades gegen die Mainnet-Stundenkerzen ist am 16.10.2026 gemacht (Elias, Kaufpreis mehr als 3 % unter dem Tief der Kaufstunde, nur verkaufte echte Positionen, ca. 41 Tage): Vom realisierten Grid-Ergebnis von **16,82 USDT** stammen **13,93 USDT** aus drei Ausreißer-Ereignissen (02.10. 13:30 UTC, Stufen 8 bis 13, 6,15; 09.10. 05:17 UTC, Stufen 4 und 5, 3,56; 09.10. 07:03 UTC, Stufen 7 bis 10, 4,23; die gerundeten Ereignissummen ergeben 13,94, die exakte Summe ist 13,93), rund 2,9 USDT aus normalem Betrieb (Näherung: 16,82 minus 13,93). Zum Vergleich der Stand vom 06.10.: 6,15 von 8,65 USDT. Details: Log 16.10.2026. Aussagen über die Strategie stützen sich auf die Backtests (Mainnet-Kerzen), das Testnet belegt vor allem die Technik. Vom selben Ticker hängen auch die echte Trend-Position vom 17.10.2026 (Stop-Order 3807835) und die Stop-Offset-Kalibrierung ab: Ein Ausreißer könnte dort Einstiege oder Stop-Loss-Auslösungen erzeugen, die es auf dem echten Markt nicht gäbe. Details: Log 06.10.2026.

### Nicht im Repository

- Der Recherche-Bericht zu Abschnitt 5 und die Review-Ausgabe vom 15.09. gibt es nur im claude.ai-Chat. Falls exportierbar, gehören sie nach `docs/research/` bzw. `docs/reviews/`, die Review-Ausgabe vorher auf IP-Adressen und Pfade prüfen. Details: Archiv 5, 6g (Einleitung).

---

## Log ab 29.09.2026

Chronologisches Log seit der Aufteilung des Dokuments, Fortsetzung von Abschnitt 6 im Archiv. Einträge bleiben stehen, spätere Erkenntnisse werden als datierte Vermerke ergänzt. Ältere Einträge wandern später gesammelt ins Archiv.

### Projektdokument aufgeteilt (29.09.2026)

`trading-bot-projekt.md` war auf über 2.500 Zeilen (350 KB) gewachsen und wurde in vielen Sitzungen komplett mitgelesen, obwohl der Großteil abgeschlossen ist. Die Abschnitte 1–6i stehen jetzt unverändert in `trading-bot-projekt-archiv.md`. Hier bleiben der Kopfbereich, der neue Abschnitt „Aktueller Stand und offene Punkte“, dieses Log und Abschnitt 7. Nichts ist gelöscht oder umformuliert. Ein Prüfskript hat nach dem Verschieben festgestellt, dass der Archivteil byte-gleich mit den Originalzeilen ist und dass jede Originalzeile in genau einer der beiden Dateien steht. Geändert wurden nur die Zeile „Stand:“, der Einleitungsabsatz von Abschnitt 7 und die Fußzeile.

Bewusst **nicht** angepasst sind die Verweise in Code-Kommentaren und Tests („siehe trading-bot-projekt.md 6g“ u.ä.). Die Abschnitte haben im Archiv dieselben Nummern, und der Verweis-Absatz oben führt dorthin. Angepasst sind die README (Abschnitte 8.2, 8.3, 9 und 10) und `CLAUDE.md`.

### Grid-Ergebnis vom 02.10.2026 ist ein Testnet-Artefakt (06.10.2026)

Bei der Auswertung der Homeserver-Daten am 06.10.2026 lag das realisierte Grid-Ergebnis bei 8,65 USDT, davon 6,31 USDT allein am 02.10.2026. Die Ursache ist ein Testnet-Artefakt: Der Bot hat korrekt zu den Preisen gekauft und verkauft, die der Testnet-Ticker gemeldet hat, auf dem echten Markt hätte es diese Preise nicht gegeben.

**Belege:**

- Am 02.10. wurden um 13:30:13 bis 13:30:16 UTC sechs Grid-Stufen (8 bis 13) zu Kaufpreisen von 77.809 bis 79.480 USDT gekauft. Um 13:35:17 bis 13:35:30 UTC wurden alle sechs zu 86.928 bis 86.962 verkauft, zusammen +6,15 USDT. Auf Stufe 8 bis 13 entfallen jeweils 0,82 bis 1,09 USDT, normale Zyklen bringen 0,14 bis 0,21 USDT.
- Die öffentlichen Stundenkerzen (BTCUSDT, 1h) zeigen für den 02.10. folgende Tiefs, Testnet gegen Mainnet: 05:00 UTC 66.745,57 gegen 85.893,27; 13:00 UTC 75.745,57 gegen 86.465,72; 15:00 UTC 75.000,00 gegen 85.162,90. In allen übrigen Stunden liegen beide Quellen nahe beieinander. Das Mainnet-Tagestief lag bei 83.888 (Stundenkerzen, 18:00 UTC), alle sechs Kaufpreise liegen darunter.
- Das Testnet-Tief von 75.745 in der Stunde 13:00 passt zu den Käufen um 13:30.

**Grenzen der Aussage:**

- Die Stunden 05:00 und 15:00 hatten ebenfalls Testnet-Ausreißer. Ob der Bot in diesen Stunden etwas gekauft hat, wurde nicht geprüft.
- Ein dünnes Orderbuch ist als Ursache für die Abweichung der Testnet- von den Mainnet-Kerzen nur vermutet, nicht gemessen.
- Der Rest von etwa 2,5 USDT aus normalem Betrieb ist eine Näherung (8,65 minus 6,15) und nicht einzeln belegt. Ob dieser Rest frei von Ausreißern ist, wurde nicht geprüft.

**Folgerung:** Testnet-Gewinne taugen nicht für Renditeschätzungen, die Regeln zur Auswertung stehen im Abschnitt „Aktueller Stand und offene Punkte“ unter „Für die Auswertung der Testphase“. Die Trend-Dry-Run-Position vom 15.09. und die Stop-Offset-Kalibrierung hängen vom selben Ticker ab, ein Ausreißer könnte dort Einstiege oder Stop-Loss-Auslösungen erzeugen, die es auf dem echten Markt nicht gäbe. Dass es so war, ist nicht geprüft.

**Nachtrag 16.10.2026:** Die oben genannten 6,15 von 8,65 USDT waren unvollständig. Am 16.10.2026 hat Elias alle verkauften echten Grid-Positionen der letzten ca. 41 Tage per Skript gegen die Mainnet-Stundenkerzen geprüft (Kaufpreis mehr als 3 % unter dem Mainnet-Tief der Kaufstunde). Belegt sind zwei weitere Ereignisse am 09.10.2026 (05:17 und 07:03 UTC). Zusammen stammen 13,93 von inzwischen 16,82 USDT realisiert aus Ausreißer-Käufen, auf den 02.10. entfallen dabei wie oben 6,15 USDT. Details: Eintrag vom 16.10.2026.

### VPS abgeschlossen, keine Auswertung der VPS-Daten (07.10.2026)

Der VPS ist am 07.10.2026 zurückgebaut. Die drei Bot-Dienste (dca-bot, grid-bot, trend-bot) sind gestoppt und deaktiviert. Auf dem VPS wurden `.env` und Archivdatei gelöscht, der Claude-Code-Deploy-Schlüssel (claude-code-vps-deploy) wurde aus `authorized_keys` entfernt, und der VPS-Eintrag wurde aus `known_hosts` auf dem lokalen Rechner entfernt. Der Vertrag (Contabo Cloud VPS 4 (2026)) ist zum 12.10.2026 gekündigt und laut Kundenbereich bis 12.10.2026 abgerechnet, es gibt keine Zusatzposten.

**Entscheidung:** Es gibt keine Auswertung der VPS-Daten, und es wurde bewusst kein Snapshot behalten (reine Testnet-Daten). Gründe:

- Grid und Trend liefen dort im Dry-Run. Ihre Ergebnisse hängen vom Testnet-Ticker ab, der am 02.10. Ausreißer hatte (siehe Eintrag vom 06.10.2026).
- Es gab auf dem VPS keinen Allocator.
- Der Code-Stand war `10ce096`.
- DCA verkauft nie.

Der Stabilitätstest vom 09.09. liegt weiter unter `docs/test-reports/`.

**Folgen:** Der formale Cutover am 05.10. mit separatem Snapshot-Schritt entfällt. Damit gibt es auch keinen Vergleich VPS gegen Homeserver mehr. Die im Archiv dafür geplanten Schritte (Cutover mit Snapshot, finaler `data/`-Snapshot zum Vertragsende) sind nicht mehr vorgesehen. Der Abschnitt „Aktueller Stand und offene Punkte“ ist entsprechend angepasst.

### Werkzeug zum Schließen der Dry-Run-Trend-Position (07.10.2026)

**Begründung:** Die Dry-Run-Position vom 15.09.2026 (`c0e153c1-…`, Einstieg 76.960,01, `quote_spent` 15,0, `dry_run: true`, kein `symbol`-Feld, keine Stop-Order) belegt den einzigen Trend-Slot. Deshalb gab es im Testnet noch nie einen echten Trend-Einstieg, keine echte Stop-Order und keinen echten Ausstieg. Einen Take-Profit gibt es nicht, die Position schließt nur bei bestätigtem Abwärtssignal oder 10 % unter dem Einstieg. Laut Auswertung der öffentlichen Kerzen zeigt das Testnet an etwa 4 % der Stunden ein Tief mehr als 10 % unter dem Mainnet. Eine echte Position wird deshalb vermutlich bald durch einen Ausreißer ausgelöst. Das ist als Technik-Test gewollt, nicht als Kalibrierung.

**Werkzeug:** `python -m dca_bot.close_dry_run_trend`, Bericht als Standard. `--apply` braucht `--trade-id` und `--exit-price` und schreibt nur, wenn der Trend-Bot gestoppt ist (Prozess-Lock, vor dem Lesen geholt). Vor dem Schreiben entsteht die Kopie `trend_ledger.json.pre-close-<Zeitstempel>`, geschrieben wird atomar über `TrendLedger.record_exit()`, danach wird geprüft, dass sich nur dieser eine Eintrag geändert hat. Ein zweiter Lauf ändert nichts. Entscheidungen:

- Ausstiegspreis: Pflichtargument `--exit-price` (Mainnet-Kurs), kein Netzzugriff im Werkzeug.
- `exit_reason`: neuer Wert `manual_close`. Gelesen wird das Feld weder im Bot (nur `trend_strategy` schreibt es) noch im Positions-Audit, im Allocator, in `check_orders` oder in der Dashboard-App; die Backtests werten nur ihr eigenes Trade-Log aus.
- `record_exit()` statt Roh-Dicts. Die Stop-Loss-Sperre entsteht nur in `trend_strategy` und nur bei `stop_loss`; das Werkzeug importiert weder die Strategie noch `TrendStopLoss`.
- Die simulierte `realized_pnl` (Menge × Ausstiegspreis − `quote_spent`) zählt nirgends als Ergebnis: Dashboard-Summen, PnL-Verlauf und CSV-Export filtern auf `dry_run: false`, das Positions-Audit zählt Dry-Run nicht zum Bestand. Einzige sichtbare Folge: Die Trend-Karte der App zählt einen geschlossenen Trade mehr, weil sie dort nach Status zählt.
- Weigerung ohne Schreiben, wenn: das Ledger fehlt oder unlesbar ist, nicht genau eine offene Position existiert, die Position nicht `dry_run: true` ist, eines der Felder `client_order_id`, `stop_loss_order_id`, `exit_client_order_id` gesetzt ist oder Teilfüllungen verbucht sind, `--trade-id` nicht passt, die Pending-Datei Einträge hat oder unlesbar ist, die Stop-Loss-Sperre aktiv ist oder die Symbolprüfung etwas anderes als „passt“ meldet (für Pending-Datei, Sperre und Allocator-Zustand ist „nicht vorhanden“ in Ordnung).

**Was der Bot danach tut (geprüft im Code):** Der erste Zyklus läuft direkt beim Start. Die EMAs werden aus Mainnet-Tageskerzen bis gestern aufgebaut, dazu kommt der aktuelle Testnet-Kurs. „up“ heißt EMA20 über EMA50 mit mindestens 1 % Abstand, ein frischer Crossover ist nicht nötig. Es gibt keinen Cooldown und keine Regel gegen einen Einstieg am selben Tag. Der Betrag ist `TREND_AMOUNT_PER_TRADE` × `trend_fraction` des Allocators, unter 5 USDT wird übersprungen. Die Stop-Order liegt bei Einstieg × 0,90, Limit × 0,995. Ihr Mindestvolumen wird vorher nicht geprüft: Bei Kursen um 85.000 braucht sie mindestens 7·10⁻⁵ BTC, also etwa 6 USDT Einstiegsbetrag (`trend_fraction` ab etwa 0,40 bei 15 USDT). Das ist gerechnet, nicht am Testnet geprüft. Freies USDT wird vor dem Kauf nicht geprüft.

**Deploy:** Seit `980f3c3` hat sich auf master nur Doku geändert, Code erst mit diesem Werkzeug. Neu gestartet wird nur der Trend-Bot, DCA, Grid und Allocator laufen weiter.

**Tests:** `tests/test_close_dry_run_trend.py` mit 40 Tests (alle Weigerungen, Normalfall, Bericht schreibt nichts, keine Sperre, echte Position bleibt unverändert, Lock, Kontrolle nach dem Schreiben, Ende-zu-Ende: nach dem Schließen steigt der Bot bei „up“ echt ein und platziert die Stop-Order). Mutationsprobe: 31 Mutationen, alle erkannt. Die Tests liefen nur unter Windows; dort sperrt `process_lock.py` mit `msvcrt.locking`, unter Linux mit `fcntl.flock`. Deshalb belegt Schritt 6 des Ablaufs das Lock auf dem Server.

**Ablauf auf dem Homeserver:**

1. Uhrzeit wählen: nicht 00:20–00:35 UTC (Zwangstrennung), nicht 06:40–07:00 UTC (apt-Neustarts).
2. `git status` sauber, `git log -1` zeigt `980f3c3`, dann `git pull`.
3. `python -m dca_bot.symbol_guard --report`: Der Trend-Bot muss „würde starten“ melden.
4. `python -m dca_bot.close_dry_run_trend` (Bericht): genau eine offene Position `c0e153c1-…`, Dry-Run, keine Stop-Order, Pending-Datei leer, keine Sperre, Symbolprüfung passt.
5. `trend_fraction` und Zeitstempel in `data/allocator_state.json` ansehen (siehe Mindestvolumen oben), Mainnet-Kurs notieren.
6. Lock-Probe bei noch laufendem Trend-Bot, im Repo-Verzeichnis (dieselbe `.env` und damit dieselbe Lock-Datei wie der Dienst): `python -m dca_bot.close_dry_run_trend --apply --trade-id <volle ID> --exit-price <Mainnet-Kurs>`. Erwartung: Exit-Code 2 (`echo $?`), Meldung „ABGEBROCHEN“, nichts geschrieben, keine Sicherungskopie `trend_ledger.json.pre-close-*`.
7. `sudo systemctl stop trend-bot`
8. `python -m dca_bot.close_dry_run_trend --apply --trade-id <volle ID> --exit-price <Mainnet-Kurs>`
9. `python -m dca_bot.audit_positions`: Trend ohne offene Position, keine neue Diskrepanz.
10. `python -m dca_bot.check_orders`: freies USDT mindestens etwa 15.
11. `sudo systemctl start trend-bot`, dann `journalctl -u trend-bot -f`: Symbolprüfung, Kurs, Allocator-Anteil und effektiver Betrag, dann entweder `[TREND-EINSTIEG]` mit platzierter Stop-Order ohne `[TREND-FEHLER]` oder kein Einstieg, weil das Signal nicht „up“ ist.
12. Nach dem ersten Zyklus erneut `python -m dca_bot.audit_positions`. Anwendung und Deploy werden hier und unter „Deploy-Stand“ vermerkt.

Löst danach ein Ausreißer die Stop-Order aus, schließt der Bot mit `stop_loss`, und die Sperre greift. Der nächste Einstieg braucht dann `python -m dca_bot.reset_trend_stop_loss`.

**Nachtrag (16.10.2026): Ablauf gegen den heutigen Stand geprüft.** Der Eintrag oben bleibt unverändert. Auf dem Homeserver läuft seit dem 16.10.2026 `76f261b`, das Werkzeug (`2cd70f0`) ist darin enthalten. `close_dry_run_trend.py`, `tests/test_close_dry_run_trend.py` (40 Tests) und `TrendLedger.record_exit()` sind seitdem unverändert. Geändert hat sich:

- **Absatz „Deploy“:** entfällt. Das Werkzeug ist schon auf dem Server, ein eigener Deploy ist nicht nötig. Der Trend-Bot wird nur in Schritt 7 gestoppt und in Schritt 11 gestartet.
- **Schritt 1:** Sperrfenster jetzt 00:05 bis 00:35 UTC statt 00:20–00:35 UTC (Zwangstrennung, siehe „Aktueller Stand“, „Betrieb“). Das Fenster 06:40–07:00 UTC (apt-Neustarts) ist unverändert übernommen, aber nicht neu geprüft.
- **Schritt 2:** `git log -1` zeigt `76f261b`, `git pull` bringt nur noch neuere Doku.
- **Schritt 10:** Die Schwelle bleibt. Seit der Bereinigung vom 16.10.2026 sind die Grid-Stufen 0 bis 10 wieder frei, der Grid-Bot kann dort kaufen und bindet dabei USDT. Wie viel freies USDT bei der Anwendung bleibt, ist offen, Schritt 10 zeigt es.
- **Schritt 11:** Mit dem Fix vom 16.10.2026 kommen mögliche Ausgänge hinzu: `[TREND-EINSTIEG]` mit dem Zusatz „Teilfüllung“; `[TREND-STAUB]`, wenn eine Teilfüllung unter dem Mindestvolumen liegt (keine Stop-Order, keine Sperre); `[ORDER-OHNE-AUSFUEHRUNG]` mit `[TREND-FEHLER]` „nicht verbucht“ bei einem Einstieg ohne Ausführung (Slot bleibt frei, das wäre zugleich der Nachweis für Vorbedingung 7); `[ORDER-UNKLAR]` und `[TREND-EINSTIEG-UNGEKLAERT]` bei unklarem Status (Slot belegt bis zum nächsten Tageszyklus). Details: Log 16.10.2026, „Umgesetzt, Runde 1“.
- **Schritt 12:** Vermerkt wird nur die Anwendung, im Log. Ein Vermerk unter „Deploy-Stand“ entfällt, weil kein Deploy stattfindet.
- **Pausierter Status:** Die Pause (Vorbedingung 2, Schritt 13 des Ablaufs vom 16.10.2026) hing am Deploy des Fixes und ist damit nicht mehr nötig. Die Prozedur bleibt bis zur Freigabe durch Elias ausgesetzt. Status: freigabefähig, noch nicht durchgeführt.

Unverändert: Schritte 3, 6, 7, 8 und 9. Schritt 6 bleibt nötig. Die Lock-Probe vom 16.10.2026 belegt das Lock unter Linux nur für das Grid-Werkzeug und den Grid-Bot. Die Regel zum Mindestvolumen gilt für einen voll ausgeführten Einstieg weiter: Die neue Staub-Regel (T2) greift nur bei einer Teilfüllung.

Nicht sicher beurteilt:
- **Schritt 4:** Ob die Dry-Run-Position `c0e153c1-…` weiterhin die einzige offene Trend-Position ist, ohne Sperre und mit leerer Pending-Datei, ist von hier aus nicht geprüft. Das zeigt erst der Bericht.
- **Schritt 5:** Die Rechnung zum Mindestvolumen (7·10⁻⁵ BTC, etwa 6 USDT bei Kursen um 85.000) hängt vom Kurs ab und ist nicht neu gerechnet.

**Vermerk (16.10.2026, nach Messung der Zwangstrennung):** Für Schritt 1 gilt als Sperrfenster jetzt 23:50 bis 00:30 UTC statt 00:05 bis 00:35 UTC wie im Nachtrag oben. Messwerte und Begründung: „Aktueller Stand“, „Betrieb“.

**Vermerk (17.10.2026):** Die Prozedur ist am 17.10.2026 durchgeführt, der Status „freigabefähig, noch nicht durchgeführt“ im Nachtrag oben ist damit überholt. Ergebnis: Eintrag vom 17.10.2026.

### Market-Orders ohne Ausführung als Position verbucht (16.10.2026)

**Befund vom Homeserver.** Im Grid-Ledger standen elf offene, echte Einträge ohne Bestand: `quantity` 0, `quote_spent` 0, als Kaufpreis der Ticker des Zyklus (am 11.10. bei allen sieben 70.192,26). Ausgabe der Abfrage auf dem Homeserver vom 16.10.2026, ergänzt um die Ordermenge laut Börse:

| Stufe | `bought_at` (UTC) | Ledger-`id` | `client_order_id` | Ordermenge (BTC) |
|---|---|---|---|---|
| 0 | 2026-10-09T05:17:31 | `14f6af94-198f-47d0-91d0-33baf809d1d0` | `grid-33b3641be36f4e139d6c5fd3` | 0.00014000 |
| 1 | 2026-10-09T05:17:31 | `54918462-99c6-46dc-a0c9-10478d687e32` | `grid-21918cc10b2c4d7fa859380c` | 0.00014000 |
| 2 | 2026-10-09T05:17:32 | `c6564874-7359-4875-b4f2-8909599db89e` | `grid-1be308d2e7d14b0791bd1445` | 0.00014000 |
| 3 | 2026-10-09T05:17:33 | `f29b06f6-e113-47c8-b03c-8f4a9b0aa756` | `grid-4bdc0b39c3aa43088c0e82c2` | 0.00014000 |
| 4 | 2026-10-11T16:01:35 | `10418ef5-a18c-4241-adc5-8c9b8cdf3453` | `grid-f0f245ee4ac64a08bf933fae` | 0.00013000 |
| 5 | 2026-10-11T16:01:36 | `19a4550e-ecc1-45fb-834a-dc7a4cce1787` | `grid-752a27dc70224a708070cb37` | 0.00013000 |
| 6 | 2026-10-11T16:01:37 | `ed8c55fb-7c27-41f2-a7a8-1b7332014675` | `grid-d6a7e35b0665427bbd118d85` | 0.00013000 |
| 7 | 2026-10-11T16:01:38 | `7aab14a6-6bf3-48e0-8eeb-34d729fdc684` | `grid-5ac7a25d606446e4ba972cf8` | 0.00013000 |
| 8 | 2026-10-11T16:01:39 | `13f0fdee-b44c-4c7d-9f3b-17ec6d5ba9b3` | `grid-3932c321ec4f4907b6229765` | 0.00013000 |
| 9 | 2026-10-11T16:01:39 | `1a5f6c8a-88ee-4466-87f3-dd46b4bd870e` | `grid-c67242e66b0d440e8d20d89a` | 0.00013000 |
| 10 | 2026-10-11T16:01:40 | `c98bc132-506b-46db-a816-8d9b522a2019` | `grid-1fe9e148bbb041e5b74fa824` | 0.00013000 |

**Börsenprüfung, von Hand gemacht** (Elias, 16.10.2026, `python -m dca_bot.check_orders --client-order-id <ID>` einzeln für alle elf IDs): Status `EXPIRED`, ausgeführt 0.00000000 bei allen elf. Die vier vom 09.10.2026 lauteten über je 0.00014000 BTC, die sieben vom 11.10.2026 über je 0.00013000 BTC. Die Börsenzeit der Orders vom 11.10. liegt bei 16:01:35 bis 16:01:40 UTC. Für die vier vom 09.10. liegt nur `bought_at` aus dem Ledger vor (05:17 UTC).

**Abgrenzung.** Aus derselben Minute am 09.10.2026 stammen die echten Käufe der Stufen 4 bis 10 **mit** Bestand (05:17:43 bis 05:17:57 UTC, Menge 0.00011 bis 0.00014, Einsatz 9,07 bis 9,38, inzwischen alle `closed`). Sie gehören nicht dazu. Der Filter `status open, dry_run false, quantity 0, quote_spent 0` trifft auf dem Server genau die elf: Abfrage (a) 11 Zeilen, (b) beide Minuten 18 Zeilen (11 ohne und 7 mit Bestand), (c) halb leere Einträge keine. Das Journal vom 11.10. passt dazu: `[GRID-VERKAUF-FEHLGESCHLAGEN]` nach „Verkaufsmenge … 0“ für die Positionen der Stufen 0 bis 9 (`14f6af94` bis `1a5f6c8a`). Stufe 10 (`c98bc132`) fehlt dort, weil ihr Verkaufsziel nicht erreicht war.

**Folgen bis zur Bereinigung** (aus dem Code abgeleitet): Die Stufen 0 bis 10 gelten als belegt, der Grid-Bot kauft dort nicht. Jeder 5-Minuten-Zyklus versucht für jede dieser Positionen mit erreichtem Ziel einen Verkauf über Menge 0, der vor der Börse abbricht: je Position ein ERROR „Verkaufsmenge … 0“ und eine WARNING `[GRID-VERKAUF-FEHLGESCHLAGEN]`, Telegram einmal je Position und Prozesslauf. Bei zehn Positionen sind das rund 5.800 Logzeilen am Tag. Positions-Audit, Bestandsabgleich und Startprüfung sehen keinen Fehler, weil Menge 0 nichts beansprucht. In der Dashboard-App zählen die Einträge als offen, der CSV-Export führt sie als BUY-Zeilen mit Menge 0.

**Ursache.** `_place_order()` gab jede Antwort ohne Exception als ausgeführten Trade zurück. Status und `executedQty` wurden nur nach einem Verbindungs- oder Serverfehler bewertet (Rückfrage, Reconciliation), nicht im regulären Antwortweg. Bei `EXPIRED` mit 0 nahm `average_fill_price()` den Ticker als Ersatz, `net_executed_quantity()` ergab 0, `cummulativeQuoteQty` war 0, und alle drei Bots buchten das als Kauf, samt `[GRID-KAUF]`. Die Reconciliation bewertet `EXPIRED` mit 0 richtig als „ohne Wirkung“, sah diese Einträge aber nie: Der Pending-Eintrag war nach `confirm_booked()` sofort entfernt. Kein Test bildete eine Market-Order ohne Ausführung ab, alle Fakes füllten vollständig.

**Quelle.** Dass eine nur teilweise gefüllte Market-Order mit Status `EXPIRED` endet, gilt laut Binance Spot API Enums, geprüft am 16.10.2026 (Elias): https://developers.binance.com/docs/binance-spot-api-docs/enums (Order status `EXPIRED`). Die Regel gilt damit für die Spot-API allgemein, nicht nur fürs Testnet. Dass eine Market-Order auch mit Ausführung 0 so endet, ist **nur auf dem Testnet beobachtet** (09.10. und 11.10.2026), **nicht in der Doku belegt**. Für BTCEUR im Echtgeld-Betrieb ist der Fix deshalb Vorbedingung 7.

**Umgesetzt, Runde 1** (Plan und Entscheidungen vom 16.10.2026):

- **A1, Ausführungsstatus im regulären Antwortweg** (`binance_client._settle_market_response`): Die Antwort einer Market-Order wird vor dem Buchen mit derselben Regel bewertet wie in der Reconciliation (`classify_order_status`, also `order_lifecycle_state`). Beendet mit Ausführung, auch `EXPIRED` mit Teilmenge: wie bisher, der Pending-Eintrag bleibt bis `confirm_booked()`. Beendet ohne Ausführung: Pending-Eintrag weg, ERROR `[ORDER-OHNE-AUSFUEHRUNG] … Boerse meldet Status EXPIRED, ausgefuehrt 0 - kein Trade, nichts gebucht`, `None` an die Strategie. Die meldet einmal per Telegram (`[GRID-FEHLER]`, `[TREND-FEHLER]` bzw. `[FEHLER]` mit „nicht verbucht“), es gibt keinen `[GRID-KAUF]`, und die Stufe bzw. der Trend-Slot bleibt frei. Noch aktiv, kein oder unbekannter Status: unklar, der Eintrag bleibt, `[ORDER-UNKLAR]` mit „Boerse meldet Status …“, die Sperren aus K-B greifen bis zur Reconciliation. Die läuft zu Beginn jedes Zyklus und bei jedem Start, beim Grid also alle 5 Minuten, beim Trend einmal am Tag. Ein Trend-Einstieg mit unklarem Ausgang belegt den Platz deshalb bis zum nächsten Tageszyklus (`[TREND-EINSTIEG-UNGEKLAERT]`, kein zweiter Kauf), bleibt die Order an der Börse auch dann ungeklärt, entsprechend länger. Die Logtexte trennen diesen Weg ausdrücklich vom Weg nach einem Verbindungsfehler. Stop-Orders laufen nicht durch diese Prüfung (E1), eine Market-Antwort ohne Statusfeld gilt als unklar (E2). Beleg, dass Market-Antworten das Feld tragen: `docs/test-reports/2026-09-09_dca-3tage-stabilitaetstest.log` (`'status': 'FILLED'`). Der Vorabcheck im Ablauf bleibt trotzdem Pflicht.
- **A3, Ledger-Schutz** (`risk.require_plausible_entry`): `GridLedger.record_buy`, `TrendLedger.record_entry` und `TradeLedger.record` lehnen einen nicht als Dry-Run markierten Eintrag mit Menge ≤ 0 oder Einsatz ≤ 0 ab (`ImplausibleLedgerEntry`, auch bei NaN). Geprüft wird nur der neue Eintrag, die elf alten blockieren bis zur Bereinigung nichts. Die Exception fliegt vor `confirm_booked()`. Der Pending-Eintrag bleibt also stehen, und die Reconciliation fragt im nächsten Zyklus erneut.
- **T2, Teilfüllung beim Kauf:** Gebucht wird die ausgeführte Menge mit dem echten Einsatz, wie bisher, jetzt mit dem Zusatz „Teilfüllung“ in `[GRID-KAUF]`, `[TREND-EINSTIEG]` und `[KAUF]`. Liegt die gekaufte Menge unter dem Mindestvolumen (`order_utils.is_dust`, beim Grid zum Füllpreis, beim Trend zum Limit-Preis der Stop-Order), wird sie sofort als Staub geschlossen. Beim Grid geschieht das über die neuen Felder `dust_qty` und `close_reason: "dust"` (`[GRID-STAUB]`, Stufe frei, keine Sperre), beim Trend über `exit_reason: "dust_on_entry"` und das bestehende `dust_qty` (`[TREND-STAUB]`, keine Stop-Order, keine Sperre). `realized_pnl` ist −`quote_spent` wie bei K-A. Das ist vorsichtig bewertet, denn der Staub hat einen Restwert unter dem Mindestvolumen. Die Menge des Staubs ist die tatsächlich erhaltene, nicht auf die `stepSize` gerundet, sonst könnte sie 0 sein und A3 würde sie ablehnen. Dieselbe Regel gilt beim Nachtragen über die Reconciliation. DCA verkauft nie und bucht nur die ausgeführte Menge. Entscheidung: `dust_qty` und `close_reason` kommen beim Grid schon in Runde 1, nur für Staub beim Kauf.
- **Teilfüllung beim Verkauf, nur Absicherung:** Meldet die Börse bei einem Market-Verkauf weniger ausgeführt als bestellt (beendet, ausgeführt > 0, nicht `FILLED`), kommt `[GRID-TEILFUELLUNG-UNGEBUCHT]` bzw. `[TREND-TEILFUELLUNG-UNGEBUCHT]` in Log und Telegram, direkt in `place_market_sell()` und beim Nachtragen in `reconcile_pending_orders()`. Gebucht wird wie bisher die volle Menge, neue Felder braucht das nicht. Korrekt gebucht wird erst in Runde 2 (Vorbedingung 8). Ein Verkauf mit Ausführung 0 fällt unter A1: Die Position bleibt offen, beim Trend wird die Stop-Order neu gesetzt. Beim Grid wird ein Verkauf, der als `EXPIRED` mit 0 endet, in jedem 5-Minuten-Zyklus erneut versucht, solange das Ziel erreicht ist: je Zyklus und Position ein ERROR `[ORDER-OHNE-AUSFUEHRUNG]` und eine WARNING `[GRID-VERKAUF-FEHLGESCHLAGEN]`, per Telegram einmal je Position und Prozesslauf.
- **Werkzeug** `python -m dca_bot.remove_unfilled_grid_positions` (Entscheidung B1): Es entfernt offene, echte Grid-Positionen, deren Menge **und** Einsatz als Zahl genau 0 sind. Jede `client_order_id` wird vorher bei Binance nachgeschlagen (nur lesender Client wie im Positions-Audit), entfernt wird nur, was beendet ohne Ausführung ist. Einzeln verweigert werden: nicht gefunden (−2013), Abfrage gescheitert, noch aktiv, ausgeführt > 0 (laut, mit „Bestand existiert“), Status unlesbar, Order-Seite nicht BUY, keine `client_order_id`, fremdes Symbol, Verkaufsfelder gesetzt, Teilverkauf oder Staub verbucht. Ein verweigerter Eintrag bleibt stehen. Insgesamt verweigert wird bei fehlendem oder unlesbarem Ledger, Einträgen in der Pending-Datei oder einer unlesbaren Pending-Datei, nicht passender Symbolprüfung, fehlendem Binance-Zugang und bei einem echten offenen Eintrag, bei dem nur Menge oder nur Einsatz 0 ist oder die Werte keine Zahlen sind. Bericht ist der Standard. `--apply` braucht `--expect N`, holt das Lock des Grid-Bots vor dem Lesen, prüft unter dem Lock alles neu, schreibt nur bei genau N belegten Einträgen, legt vorher die Kopie `grid_positions.json.pre-remove-<Zeitstempel>` an, entfernt atomar über `GridLedger.remove_unfilled_positions()` (die selbst nichts anderes als Einträge ohne Bestand entfernt) und kontrolliert danach, dass genau diese Einträge fehlen und alle anderen unverändert sind. Exit-Codes: 0, 1 Weigerung, 2 Bot läuft, 3 Kontrolle fehlgeschlagen.

**Tests:** 62 neue, die Suite hat jetzt 981 Tests (vorher 919), alle grün. `tests/test_unfilled_market_orders.py` (32): A1 im echten `TradingClient` für Kauf und Verkauf mit `EXPIRED`, `CANCELED`, `REJECTED` und `EXPIRED_IN_MATCH` jeweils mit 0, Teilfüllung, `FILLED`, unklare und fehlende Status, Stop-Orders unverändert. Dazu die laute Meldung beim Teilverkauf (direkt und beim Nachtragen), A3 für alle drei Ledger, sowie Ende-zu-Ende auf dem geteilten Konto für Grid, Trend und DCA: Kauf und Verkauf mit Ausführung 0, Teilfüllung, Staub samt Bezugspreis (Grid Füllpreis, Trend Limit-Preis), Staub beim Nachtragen und A3 allein, wenn A1 umgangen wird. `FakeExchange` in `test_shared_account.py` hat dafür eine einstellbare Liquidität je Market-Order, die Eigentums-Invariante zählt Grid-Staub mit. `tests/test_remove_unfilled_grid_positions.py` (30) bildet die Lage auf dem Server nach, mit den elf IDs und den sieben gefüllten Käufen vom 09.10. (auch als offene Variante): Filter trifft genau die elf, Bericht schreibt nichts, je ein Test pro Weigerung, Lock, Kopie, Kontrolle und erneute Prüfung unter dem Lock, dazu Filter und Entfernen auf Ledger-Ebene (`is_unfilled_position`, `GridLedger.remove_unfilled_positions`). Die Fakes in `test_grid_sell_safety.py`, `test_trend_stop_loss.py` und `test_dca_fee_adjustment.py` liefern jetzt ein Statusfeld. `test_rollback_compat.py` prüft zusätzlich den Stand `980f3c3` und Dateien mit Grid- und Trend-Staub.

**Mutationsprobe:** 59 Mutationen gegen die neuen Prüfungen (A1, Meldung beim Teilverkauf, A3, T2/Staub, Filter und Werkzeug). Im ersten Lauf waren es 58, davon 57 erkannt. Überlebt hatte der Wegfall der Pflichtprüfung von `--expect`: Die spätere Prüfung „genau N belegt“ fing den Fall ab, aber erst nach Lock und Börsenabfrage. Der Test verlangt jetzt die Weigerung davor, danach erkannt. Nachgereicht: Mutation 59 (Grid-Staub zum Verkaufsziel statt zum Füllpreis) mit eigenem Test auf Stufe 1, erkannt. Damit 59 von 59 erkannt. Die Tests liefen nur unter Windows; das Lock unter Linux belegt Schritt 8 des Ablaufs.

**Rückweg:** `git checkout 980f3c3` und Neustart der Dienste. Der Rückweg-Test belegt für `980f3c3`, `46ca7a7` und `10ce096`: Der alte Code liest die neuen Dateien, arbeitet weiter und verliert `dust_qty`/`close_reason` beim Schreiben nicht. Teilverkäufe werden in Runde 1 nicht gebucht, offene Positionen haben also keine neuen Felder. Nach einem Rückweg fehlen A1 und A3, Einträge ohne Bestand können dann wieder entstehen. Die Bereinigung lässt sich mit der Kopie `.pre-remove-*` rückgängig machen, das brächte aber die elf Einträge zurück.

**Ablauf auf dem Homeserver** (`jq` ist dort nicht bestätigt, die Prüfungen laufen deshalb als Python-Skripte):

1. Uhrzeit wählen: nicht 00:20–00:35 UTC (Zwangstrennung), nicht 06:40–07:00 UTC (apt-Neustarts).
2. Vorabcheck, Pflicht: `journalctl -u grid-bot --since "2026-10-11 16:01" --until "2026-10-11 16:02" | grep "erfolgreich platziert"` muss in der Antwort `'status': 'EXPIRED'` zeigen, eine normale Kauf-Zeile `'status': 'FILLED'`. Fehlt das Feld, anhalten: A1 würde dann jede Market-Order als unklar führen.
3. `cp -a data data.bak-<Datum>`
4. `git status` sauber, `git log -1` zeigt `980f3c3`, dann `git pull`.
5. `python -m dca_bot.symbol_guard --report`: alle vier „würde starten“.
6. Prüfskript, erwartet (a) 11 mit genau den IDs aus der Tabelle oben, (b) 18, (c) 0, Trend und DCA je 0:
```bash
python - <<'EOF'
import json, os
from dotenv import load_dotenv
load_dotenv()
num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
grid = json.load(open(os.getenv("GRID_STATE_FILE", "data/grid_positions.json"), encoding="utf-8"))
a = [r for r in grid if r.get("status") == "open" and r.get("dry_run") is False
     and num(r.get("quantity")) and r["quantity"] == 0
     and num(r.get("quote_spent")) and r["quote_spent"] == 0]
print("(a) Kandidaten:", len(a))
for r in a:
    print("   ", r["level_index"], r["bought_at"][:19], r["id"], r["client_order_id"])
b = [r for r in grid if str(r.get("bought_at", ""))[:16] in ("2026-10-09T05:17", "2026-10-11T16:01")]
print("(b) beide Minuten:", len(b))
for r in b:
    print("   ", r["level_index"], r["bought_at"][:19], r["status"], r["quantity"], r["quote_spent"], r["dry_run"])
c = [r for r in grid if r.get("status") == "open" and r.get("dry_run") is False
     and (not (num(r.get("quantity")) and num(r.get("quote_spent")))
          or (r["quantity"] == 0) != (r["quote_spent"] == 0))]
print("(c) halb leer oder keine Zahlen:", len(c))
for name, var, default in (("Trend", "TREND_STATE_FILE", "data/trend_ledger.json"),
                           ("DCA", "DCA_BOT_STATE_FILE", "data/trade_ledger.json")):
    rows = json.load(open(os.getenv(var, default), encoding="utf-8"))
    zero = [r for r in rows if r.get("dry_run") is False and r.get("status", "open") == "open"
            and (r.get("quantity") == 0 or r.get("quote_spent") == 0)]
    print(f"{name}: echte Einträge mit Menge oder Einsatz 0:", len(zero))
EOF
```
7. `python -m dca_bot.remove_unfilled_grid_positions` (Bericht): 11 Kandidaten, alle „ohne Bestand belegt“, IDs wie in (a). Wird einer verweigert: anhalten.
8. Lock-Probe bei laufendem Grid-Bot: `python -m dca_bot.remove_unfilled_grid_positions --apply --expect 11`. Erwartung: Exit-Code 2 (`echo $?`), „ABGEBROCHEN“, keine Kopie `grid_positions.json.pre-remove-*`.
9. `sudo systemctl stop grid-bot`, dann `python -m dca_bot.remove_unfilled_grid_positions --apply --expect 11`: „GESCHRIEBEN: 11“.
10. `python -m dca_bot.audit_positions` (Grid hat elf offene Positionen weniger, keine neue Diskrepanz) und das Prüfskript, erwartet überall 0:
```bash
python - <<'EOF'
import json, os
from dotenv import load_dotenv
load_dotenv()
for name, var, default in (("Grid", "GRID_STATE_FILE", "data/grid_positions.json"),
                           ("Trend", "TREND_STATE_FILE", "data/trend_ledger.json"),
                           ("DCA", "DCA_BOT_STATE_FILE", "data/trade_ledger.json")):
    rows = json.load(open(os.getenv(var, default), encoding="utf-8"))
    zero = [r for r in rows if r.get("dry_run") is False and r.get("status", "open") == "open"
            and (r.get("quantity") == 0 or r.get("quote_spent") == 0)]
    print(f"{name}: {len(rows)} Einträge, davon echt und offen mit Menge oder Einsatz 0: {len(zero)}")
EOF
```
11. `sudo systemctl start grid-bot`, `journalctl -u grid-bot -f`: neue Code-Version, Symbolprüfung, erster Zyklus ohne „Verkaufsmenge … 0“.
12. `sudo systemctl restart dca-bot trend-bot allocator`. DCA kauft wegen W2 nicht sofort, der Trend-Bot hält weiter die Dry-Run-Position. Danach muss „Code-Version“ überall den neuen Hash zeigen.
13. Vermerk unter „Deploy-Stand“ und hier als eigener Absatz zur Bereinigung. Die Trend-Prozedur vom 07.10. bleibt pausiert, bis Elias sie freigibt.

**Ergebnis zu den Ticker-Ausreißern** (Elias, 16.10.2026, Skript von Hand auf dem Homeserver). Die echten Käufe der Stufen 4 und 5 vom 09.10.2026 (05:17:43 und 05:17:44 UTC) ergeben aus Einsatz und Menge rechnerisch etwa 72.139 und 66.600 USDT, die Stufen 6 bis 10 etwa 82.446. Geprüft wurden alle verkauften echten Grid-Positionen im Fenster der letzten ca. 41 Tage: Kaufpreis gegen das Mainnet-Tief der Kaufstunde (öffentliche Stundenkerzen), als Ausreißer zählt ein Kauf mehr als 3 % darunter. Ergebnis: realisiert gesamt 16,82 USDT, davon 13,93 USDT aus solchen Käufen, in drei Ereignissen:

| Zeitpunkt (UTC) | Stufen | Kaufpreise | Mainnet-Tief der Stunde | Gewinn (USDT) |
|---|---|---|---|---|
| 02.10.2026 13:30 | 8 bis 13 | 77.809 bis 79.480 | 86.466 | 6,15 |
| 09.10.2026 05:17 | 4 und 5 | 72.139 und 66.600 | 82.225 | 3,56 |
| 09.10.2026 07:03 | 7 bis 10 | 70.800 bis 79.902 | 82.494 | 4,23 |

Die exakte Gesamtsumme ist 13,93 USDT (Skript, aus den ungerundeten Einzelwerten). Die Ereignissummen der Tabelle sind aus gerundeten Zeilen gebildet, ihre Summe von 13,94 weicht deshalb um 0,01 ab (Rundung). Es bleiben rund 2,9 USDT aus normalem Betrieb (Näherung: 16,82 minus 13,93). Die Grenze von 3 % und das Stundentief als Maßstab sind Setzungen dieser Auswertung, Käufe knapp über der Grenze sind nicht einzeln bewertet. Die Käufe der Stufen 6 bis 10 um 05:17 liegen bei 82.446 und damit über dem Mainnet-Tief der Stunde. Der Eintrag vom 06.10.2026 hat dazu einen Nachtrag.

**Bereinigung und Deploy (16.10.2026)** (Elias, nach dem Ablauf oben; Vorabcheck, Lock-Probe und Kontrolle danach von Hand auf dem Server gemacht):

- **Vorabcheck, von Hand auf dem Server:** Die Market-Antworten im Journal tragen das Feld `status`: `'EXPIRED'` bei den Orders vom 11.10.2026, `'FILLED'` beim Kauf vom 14.10.2026.
- **Bericht des Werkzeugs:** 11 Kandidaten, alle von der Börse als ohne Wirkung bestätigt (`EXPIRED`, ausgeführt 0).
- **Lock-Probe, von Hand auf dem Server,** bei laufendem Grid-Bot (`--apply --expect 99`): Exit-Code 2, „ABGEBROCHEN“, keine Kopie.
- **Bereinigung:** Grid-Bot gestoppt, danach `--apply --expect 11`: Exit-Code 0, 11 Einträge entfernt, Kopie `data/grid_positions.json.pre-remove-20261016T143039Z` (auf dem Server). Außerdem eine Sicherung des ganzen Ordners als `data.bak-2026-10-16`.
- **Kontrolle danach, von Hand auf dem Server:** Grid-Ledger 36 Einträge (vorher 47), davon 4 offen. In `trade_ledger`, `grid_positions` und `trend_ledger` kein echter Eintrag ohne Menge oder Einsatz. Die Fehlerzeilen „Verkaufsmenge … 0“ im Journal enden mit dem Stoppen des Grid-Bots um 14:30 UTC.
- **Deploy `76f261b`:** Grid-Bot um 14:32 UTC, DCA, Trend und Allocator um 14:40 UTC neu gestartet, alle vier mit „Code-Version: 76f261b“, Symbolprüfungen „passt“, Bestandsabgleich in Ordnung. Vermerkt unter „Deploy-Stand“.
- **Vorbedingung 7 bleibt offen:** Der Fix ist deployt, der Nachweis im Echtbetrieb entsteht, sobald das Testnet wieder eine Market-Order ohne Ausführung liefert.
- **Trend-Prozedur vom 07.10.2026:** nicht mehr durch den Fix blockiert. Status: freigabefähig, noch nicht durchgeführt; Plan: nach einer ruhigen Nacht mit dem neuen Code (Zwangstrennung: wandert grob eine Minute pro Tag nach vorne; für den 17.10. rechnerisch etwa 00:15 UTC, Schätzung, seit dem 05.10. nicht gemessen). Der Ablauf dort hat einen Nachtrag vom 16.10.2026.
- **Sperrfenster für Eingriffe:** ab jetzt einheitlich 00:05 bis 00:35 UTC, nicht mehr 00:20–00:35 UTC wie in Schritt 1 des Ablaufs oben und des Ablaufs vom 07.10.2026. Grundlage sind die Messungen bis zum 05.10. (00:27 UTC), siehe „Aktueller Stand“, „Betrieb“.
- **Vermerk (16.10.2026, nach Messung):** Die Schätzung „für den 17.10. rechnerisch etwa 00:15 UTC“ ist durch Messwerte vom 05.10. bis 16.10. ersetzt (zuletzt 16.10. 00:14:31 UTC, Drift rund 1,1 Minuten pro Tag). Das Sperrfenster gilt ab sofort einheitlich als 23:50 bis 00:30 UTC statt 00:05 bis 00:35 UTC wie im Punkt darüber, weil der Beginn der Trennung 00:05 UTC bereits um den 20.10. erreicht. Das ist eine Fortschreibung des gemessenen Drifts, keine Messung, neu gemessen wird bis spätestens 25.10.2026. Details: „Aktueller Stand“, „Betrieb“.

**Offen, Runde 2** (eigener Plan nach Freigabe von Runde 1): Teilfüllung beim Verkauf korrekt buchen, mit `partial_exit_*`, `dust_qty`/`close_reason` für Teilverkäufe, `partial_exit_from_stop`, dem Umzug von `open_quantity` und `record_partial_exit`.

### Testnet-Ausfall mit HTTP 502 am 07.10.2026 (16.10.2026)

Am 07.10.2026 von 04:37 bis 10:32 UTC lieferte das Testnet HTTP 502 Bad Gateway: rund 72 fehlgeschlagene Grid-Zyklen in knapp sechs Stunden. Die Bots liefen danach ohne Eingriff weiter, Telegram meldete pro Fehlertyp nur einmal. Das war keine Zwangstrennung. Dazu passen die Fehlerzähler im Dashboard auf einem Screenshot vom 07.10.2026, 10:01 Ortszeit (etwa 08:01 UTC): „41 Fehlschläge in Folge“ bei der Grid-Karte und „1 Fehlschlag in Folge“ bei den Karten von DCA und Trend. Angaben von Elias, 16.10.2026.

### Trend-Prozedur durchgeführt, erste echte Trend-Position (17.10.2026)

Elias, nach dem Ablauf vom 07.10.2026 mit Nachtrag vom 16.10.2026; Nachtcheck, Lock-Probe, die Abfrage der Stop-Order und die Prüfungen zu den Ablaufschritten von Hand auf dem Server gemacht, Quelle jeweils die Ausgaben von Elias auf dem Homeserver. Kein Deploy, Code-Stand auf dem Homeserver weiter `76f261b`.

- **Vorabend, von Hand geprüft, 16.10.2026 um 23:10 UTC** (vor dem Eingriff, nicht unmittelbar davor):
  - Symbolbericht (Schritt 3): alle vier Bots „würde starten“.
  - Guthaben laut `check_orders` (Schritt 10): BTC frei 1.00022000, gebunden 0; USDT frei 9.990,16599670, gebunden 0; Kurs 81.741,84. Das freie USDT wurde am 17.10. nicht erneut geprüft, der Wert vom Vorabend gilt.
  - Allocator (Schritt 5): `trend_fraction` 0.9945196322990328, `updated_at` 2026-10-16T22:40:44Z.
- **Nachtcheck vor dem Eingriff, von Hand auf dem Server:** vier Dienste `active`, Server seit 23.09. ohne Neustart. Genau eine Fehlerzeile „Unerwarteter Fehler im Grid-Zyklus“, am 17.10.2026 um 00:13:36 UTC (Zwangstrennung, die erste unter dem neuen Code). 11 Grid-Zyklen in der Stunde 00:00 bis 01:00 UTC. Seit dem Deploy keine Treffer für `ORDER-OHNE`, `ORDER-UNKLAR`, `SYMBOL-KONFLIKT`, `DOPPELVERKAUF`, `TEILFUELLUNG` oder `STAUB`. Der Messwert ist unter „Aktueller Stand“, „Betrieb“ nachgetragen.
- **Vor dem Eingriff, von Hand geprüft, 17.10.2026 um etwa 09:21 UTC:**
  - Bericht des Werkzeugs (Schritt 4): genau eine offene Position `c0e153c1-f5d8-45a2-9797-aa66da375728`, `dry_run=True`, Stop-Order `None`, Pending-Datei nicht vorhanden, keine Sperre, „Keine Einwände“.
  - Allocator (Schritt 5): `trend_fraction` 0.9949580617151103, `updated_at` 2026-10-17T08:40:48Z (41 Minuten alt).
  - Mainnet-Kurs (Schritt 5): 81.719,30 bei der Abfrage, 81.734,75 beim Eingriff.
- **Lock-Probe, von Hand auf dem Server,** bei laufendem Trend-Bot (`--apply` mit erfundener `--trade-id`): Exit-Code 2, „ABGEBROCHEN“, keine Kopie. Das belegt das Lock unter Linux auch für das Trend-Werkzeug; die Lock-Probe vom 16.10.2026 galt nur dem Grid-Werkzeug.
- **Schließen der Dry-Run-Position:** Trend-Bot gestoppt, dann `python -m dca_bot.close_dry_run_trend --apply --trade-id c0e153c1-f5d8-45a2-9797-aa66da375728 --exit-price 81734.75` (Mainnet-Kurs): Exit-Code 0, Position als `manual_close` geschlossen, keine Stop-Loss-Sperre gesetzt, Kopie `data/trend_ledger.json.pre-close-20261017T092417Z` (auf dem Server). Die simulierte `realized_pnl` von +0,93062751 zählt nirgends als Ergebnis. Laut Analyse vom 07.10.2026 zählt die Trend-Karte der Dashboard-App den Eintrag als geschlossenen Trade, nicht als Ergebnis.
- **Nach dem Schließen, von Hand geprüft, 17.10.2026 um 09:24 UTC** (Schritt 9): `audit_positions` Trend „1 Einträge insgesamt, davon 0 offen (1 geschlossen)“.
- **Start und erster Zyklus:** Trend-Bot um 09:24:55 UTC gestartet, „Code-Version: 76f261b“. Erster Zyklus: Allocator-Anteil 99,5 %, effektiver Betrag 14,92, echter Market-Buy mit Status `FILLED`, ausgeführt 0.00018000 BTC, Einstieg 81.726,36. Danach Stop-Order erfolgreich platziert (09:24:59 UTC), kein `[TREND-FEHLER]`. Nächster Zyklus in 24 Stunden.
- **Stop-Order, an der Börse gelesen, von Hand auf dem Server** (`python -m dca_bot.check_orders --client-order-id trend-d0d0c6b741f444518c07fc3f`, um etwa 09:30 UTC): Status `NEW`, `SELL` / `STOP_LOSS_LIMIT`, orderId 3807835, Menge 0.00018000, Stop 73.553,72, Limit 73.185,95, Zeit 2026-10-17 09:24:59 UTC.
- **Ledger:** Position `bd1c3457-bdc0-4aa8-b1ee-ea2ee96c7a34`, Einstieg 81.726,36, Menge 0.00018, Einsatz 14,71, Modus ECHT, `stop_loss_order_id` 3807835, Limit 73.185,96. Das ist ein Cent mehr als an der Börse, vermutlich Rundung, nicht geprüft. Der Einsatz 14,71 liegt unter dem Allocator-Betrag 14,92, weil die Menge auf die Schrittweite 0.00001 abgerundet wird (0.00018 × 81.726,36 = 14,71).
- **Nach dem ersten Zyklus, von Hand geprüft, 17.10.2026 um etwa 09:30 UTC** (Schritt 12): `audit_positions` Trend: 2 Einträge, davon 1 offen; ID `bd1c3457-bdc0-4aa8-b1ee-ea2ee96c7a34`, Einstieg 81.726,36, Menge 0.00018000, Einsatz 14,71, Modus ECHT, Stop-Loss-Order 3807835 (Limit 73.185,96). Kontoabgleich BTC: DCA 0.00038000 (2 Dry-Run, zählen nicht), Grid 0.00054000, Trend 0.00018000, Summe 0.00110000; Konto frei 1.00022000, gebunden 0.00018000 (alles Trend, über das clientOrderId-Präfix), gesamt 1.00040000; „In Ordnung“, Überschuss 0.99930000.
- **Telegram:** Die Meldung `[TREND-EINSTIEG]` ist angekommen (Angabe von Elias, 17.10.2026).
- **Erste echte Trend-Position:** Das ist der erste echte Trend-Einstieg im Testnet und die erste echte Stop-Order des Trend-Bots an der Börse. Bis zum 17.10.2026 belegte die Dry-Run-Position vom 15.09. den einzigen Trend-Slot (Eintrag vom 07.10.2026).
- **Vorbedingung 2:** Trend-Prozedur durchgeführt, echter Einstieg mit Stop-Order, noch keine Fill-Daten. Löst ein Ausreißer die Stop-Order aus, schließt der Bot mit `stop_loss`, die Sperre greift, und der nächste Einstieg braucht `python -m dca_bot.reset_trend_stop_loss`. Das ist dann ein Technik-Test der Kette (Stop-Fill, Verbuchung, Sperre, manueller Reset), kein Kalibrierungswert.
- **Vorbedingung 7 bleibt offen:** Der Kaufpfad hat im Trend-Einstieg den Status `FILLED` korrekt bewertet, ein Fall ohne Ausführung ist weiter nicht aufgetreten.

---

## 7. Technische Referenz (aus der README hierher verschoben, 25.09.2026)

Dieser Abschnitt beschreibt den **aktuellen Stand** der Bots und ihrer
Sicherheitsmechanismen - anders als das chronologische Log (Abschnitt 6 im
Archiv `trading-bot-projekt-archiv.md`, seit dem 29.09.2026 „Log ab
29.09.2026“ oben). Verweise auf die Abschnitte 5, 6 und 6a–6i meinen das
Archiv. Bis zum 25.09.2026 stand er in der README, die dadurch auf über 1.200
Zeilen angewachsen war. Die README ist seitdem die schlanke Einstiegs- und
Setup-Dokumentation mit einer Kurzübersicht der Sicherheitsmechanismen;
die ausführlichen Texte stehen hier. Sie sind **wörtlich übernommen** -
angepasst wurden nur Verweise auf Abschnittsnummern, die sich durch den
Umzug geändert haben. Seitdem wird der Abschnitt als Referenz für den
aktuellen Stand gepflegt: Was hier nicht mehr stimmt, wird direkt
korrigiert, ohne Vermerk wie in den Log-Abschnitten. Wo ein Log-Eintrag
und dieser Abschnitt dasselbe beschreiben (z.B. W9 in Archiv 6g und 7.4),
ist die Überschneidung gewollt: Der Log-Eintrag hält fest, was damals
entschieden wurde, dieser Abschnitt den heutigen Stand. Bei Abweichungen
gilt Abschnitt 7. Konfiguration, Start und Werkzeuge: README.

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
  **Der Notaus beendet den Prozess** (regulär, Exit-Code 0, für alle vier
  Bots per Test festgehalten). `Restart=on-failure` startet ihn deshalb
  nicht neu: Wiederanlaufen heißt, erst alle Quellen zu bereinigen und
  dann den Service von Hand zu starten (`sudo systemctl start <service>`).
  Steht eine Quelle beim Start noch da, beendet er sich nach den
  Startprüfungen sofort wieder. Bis dahin läuft kein Zyklus und kommt
  kein Heartbeat; offene Grid-Positionen sind ohne Absicherung (W14).
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
  # Wiederanlaufen: erst die Datei entfernen, dann die Services starten
  rm STOP_ALL
  sudo systemctl start dca-bot grid-bot trend-bot allocator
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
  "kein Trade" gewertet, der Eintrag bleibt aber stehen (die Nachfrage
  kommt unmittelbar nach dem Timeout, eine noch laufende Order würde erst
  danach sichtbar) und gilt erst ab einem Alter von 60 s als endgültig
  unbekannt; unklar → **nicht geraten**, sondern `ERROR` + Telegram
  (`[ORDER-UNKLAR]`, mit dem fertigen Aufruf
  `python -m dca_bot.check_orders --client-order-id <id>` zum
  Nachschlagen), und der Eintrag bleibt stehen. Der Eintrag wird auch nach einer
  erfolgreichen Order erst entfernt, **nachdem** die Strategie den Trade
  im Ledger hat (`confirm_booked()`). Zu Beginn **jedes Zyklus** und beim
  Bot-Start arbeitet jeder Bot verbliebene Einträge ab und trägt fehlende
  Ledger-Einträge als `[REKONZILIATION]` nach (zur Laufzeit per Telegram
  nur einmal je Order und Prozesslauf). Das schließt auch das Fenster,
  das ohne jeden Netzwerkfehler durch einen Prozess-Kill zwischen Order
  und Ledger-Eintrag entstand.
- **Kein Kauf ohne Ausführung** (seit 16.10.2026,
  `binance_client._settle_market_response`): Auch eine reguläre Antwort
  auf eine Market-Order wird vor dem Buchen bewertet, mit derselben
  Regel wie in der Reconciliation. Beendet ohne Ausführung (z.B.
  `EXPIRED` mit `executedQty` 0) → Pending-Eintrag weg,
  `[ORDER-OHNE-AUSFUEHRUNG]` im Log, die Strategie bucht nichts und meldet
  „nicht verbucht“. Noch aktiv, kein oder unbekannter Status → unklar,
  Eintrag bleibt, `[ORDER-UNKLAR]`. Stop-Orders sind ausgenommen. Davor
  buchten alle drei Bots so eine Order als Kauf mit Menge 0 zum
  Tickerpreis (Log 16.10.2026). Ein Trend-Einstieg mit unklarem Ausgang
  belegt den Platz bis zum nächsten Tageszyklus, weil die Reconciliation
  erst zu Beginn des nächsten Zyklus erneut fragt. Ein Grid-Verkauf, der
  als `EXPIRED` mit 0 endet, wird in jedem Zyklus erneut versucht (je
  Zyklus ERROR und WARNING, Telegram einmal je Position und Prozesslauf).
- **Ledger-Schutz** (seit 16.10.2026, `risk.require_plausible_entry`):
  Kein Ledger nimmt einen echten Kauf oder Einstieg mit Menge ≤ 0 oder
  Einsatz ≤ 0 an. Geprüft wird nur der neue Eintrag. Die Exception fliegt
  vor `confirm_booked()`, der Pending-Eintrag bleibt für die
  Reconciliation stehen.
- **Teilfüllung einer Market-Order** (seit 16.10.2026): Beim Kauf wird die
  ausgeführte Menge gebucht, unter dem Mindestvolumen sofort als Staub
  geschlossen (`order_utils.is_dust`, Details in 7.2 und 7.3,
  `realized_pnl` = −`quote_spent`, vorsichtig bewertet). Beim Verkauf
  wird bis Runde 2 weiterhin die volle Menge gebucht, eine Teilfüllung
  aber laut gemeldet (`[GRID-TEILFUELLUNG-UNGEBUCHT]`/
  `[TREND-TEILFUELLUNG-UNGEBUCHT]`, direkt und beim Nachtragen).
- **Kein zweiter Verkauf, solange der erste ungeklärt ist** (seit
  27.09.2026): Steht für eine Position noch ein Verkauf oder eine
  Stop-Order in der Pending-Datei, verkauft der Bot sie nicht erneut und
  platziert keine weitere Stop-Order. Ohne diese Sperre ging ein zweiter
  Verkauf auf dem geteilten Konto durch, gedeckt vom Bestand eines
  anderen Bots. Die Verkaufs-ID steht im Ledger
  (`sell_client_order_id`/`exit_client_order_id`), das Nachtragen ist
  damit idempotent. Ein Verkauf zu einer Position, die mit einer anderen
  Order geschlossen wurde, wird als `[GRID-DOPPELVERKAUF]`/
  `[TREND-DOPPELVERKAUF]` gemeldet und bleibt bis zur manuellen Klärung in
  der Pending-Datei.
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
- **Heartbeat-Statusdateien für externe Betrachter**
  (`dca_bot/heartbeat_status.py`, seit 25.09.2026): Jeder der vier Bots
  schreibt nach jedem Zyklus eine eigene kleine JSON-Datei,
  `data/heartbeat_dca.json`, `data/heartbeat_grid.json`,
  `data/heartbeat_trend.json` und `data/heartbeat_allocator.json`
  (Pfade über `DCA_`/`GRID_`/`TREND_`/`ALLOCATOR_HEARTBEAT_STATUS_FILE`).
  Inhalt: `last_successful_cycle` (ISO-Zeitstempel in UTC oder `null`),
  `last_cycle_attempt` (letzter Versuch, erfolgreich oder nicht) und
  `consecutive_failures`. Was als Erfolg zählt, ist dasselbe wie beim
  Lebenszeichen oben, der Writer bekommt genau diesen Zeitstempel. Beim
  Notaus wird nichts geschrieben. Die Dateien sind **reine Ausgabe** für
  die Dashboard-App: Kein Bot liest seine eigene oder eine fremde
  Heartbeat-Datei, damit entsteht keine Kopplung zwischen den Prozessen.
  Eine Datei pro Bot statt einer gemeinsamen, weil vier unabhängige
  Prozesse sich sonst gegenseitig überschreiben könnten. Geschrieben wird
  atomar (temporäre Datei, fsync, `os.replace`) wie bei den Ledgern. Ein
  Schreibfehler wird abgefangen und einmal pro Fehlerserie geloggt, auf
  Handel, Notaus und Telegram wirkt er nicht. Die Werte gelten **pro
  Prozesslauf**: Nach einem Neustart beginnt alles wieder bei `null`/0,
  und bis zum ersten Zyklus zeigt die Datei noch den Stand des vorherigen
  Prozesses (bei DCA und Trend wegen der Startwartezeit bis zu 24 h).
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
  `GRID_LOWER_LIMIT`, `GRID_UPPER_LIMIT`, `GRID_SPACING_PCT`,
  `GRID_AMOUNT_PER_LEVEL`, `TREND_AMOUNT_PER_TRADE` - sowie
  `TREND_STOP_LIMIT_OFFSET_PCT`. Sie müssen ausdrücklich in der `.env` stehen
  und dürfen nicht auf die Testnet-Defaults zurückfallen: Live sind genau
  sie die Stellschraube für die tatsächliche Kapitalbindung, und ein
  vergessener Eintrag sähe im Log aus wie ein bewusst gewählter Wert.
  Seit dem 27.09.2026 (W-C) genügt „gesetzt“ nicht: Steht dort noch der
  Testwert aus `.env.example` (`LIVE_PLACEHOLDER_VALUES` in
  `config_guard.py`, numerisch verglichen), startet der Bot nicht. Ein
  Testwert, der nach der Kalibrierung bewusst gelten soll, wird über
  `LIVE_CONFIRMED_VALUES=NAME=WERT,…` bestätigt; die Bestätigung gilt nur
  für genau diesen Wert, unbekannte oder doppelte Namen brechen ab. Im
  Testnet wird beides nicht geprüft.
- **Fehlkonfiguration löst keine Neustartschleife aus**: Die Prüfung
  läuft zwangsläufig vor dem Logging-Setup. Statt eines nackten
  Tracebacks mit Exit-Code 1 (den `Restart=on-failure` endlos
  wiederholen würde, ohne je erfolgreich zu sein) gibt es eine klare
  Meldung auf stderr, nach Möglichkeit eine Telegram-Nachricht, und ein
  sauberes Ende. Gleiches Muster wie bei einem bereits laufenden Bot.
- **Kein Start auf den Dateien eines anderen Paars**
  (`dca_bot/symbol_guard.py`, seit 28.09.2026, Hintergrund in 6g
  „Symbolbindung“): Jeder der vier Prozesse prüft beim Start, noch vor der
  Reconciliation, ob seine Dateien zu dem Paar aus `*_SYMBOL` gehören. Der
  Bot prüft sein Ledger (alle Einträge, offene und geschlossene), seine
  Pending-Datei, seine Stop-Loss-Sperre und bei aktivem Opt-in den
  Allocator-Zustand. Der Allocator prüft seinen eigenen Zustand. Einträge
  ohne Feld `symbol` stammen aus der Zeit davor und gelten als BTCUSDT
  (`LEGACY_SYMBOL`). Die Regel gilt beim Lesen, die Dateien werden dafür
  nicht umgeschrieben. Gehört etwas zu einem anderen Paar, startet der
  Bot nicht. Er schreibt eine `ERROR`-Zeile mit der Liste, was wo steht,
  schickt `[SYMBOL-KONFLIKT]` samt Lösungsweg per Telegram und endet mit
  Exit-Code 0 wie bei einer Fehlkonfiguration. Einzige Ausnahme ist eine
  Sperrdatei mit unlesbarem Inhalt: Sie ergibt eine Warnung im Log und
  einmal pro Start per Telegram (`[SYMBOL-WARNUNG]`), keinen Abbruch, und
  die Sperre wirkt weiter. Dazu prüft `config_guard.py` die Paare
  untereinander: Der Allocator verlangt, dass `DCA_SYMBOL` und
  `TREND_SYMBOL` seinem `ALLOCATOR_SYMBOL` entsprechen. DCA und Trend
  prüfen das nur bei gesetztem Opt-in (`*_ALLOCATOR_STATE_FILE`). Zur
  Laufzeit gilt eine Zuteilung, die für ein anderes Paar gerechnet ist,
  wie eine veraltete: 0,0, also 100 % DCA und kein Trend-Einstieg.

  **Vor jedem Neustart:** `python -m dca_bot.symbol_guard --report` zeigt,
  was der Start tun würde. Ein Startabbruch lässt den Dienst still aus:
  kein Heartbeat, und offene Grid-Positionen sind dann ungeschützt. Der
  Bericht listet je Bot und Datei, ob das Feld vorhanden ist und ob das
  Paar passt, und sagt „würde starten“, „würde starten, mit Warnung“ oder
  „würde NICHT starten“ mit Grund. Exit-Code 0 nur, wenn jeder Bot starten
  würde, sonst 1. Er liest nur, braucht weder Lock noch Zugangsdaten, legt
  keine Datei an und nutzt dieselben Prüffunktionen wie der Start.
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
  dafür nicht jeden Fall erkennt. **Was sie nicht kann:** wissen, wem das
  freie Guthaben gehört. Freies BTC des DCA-Bots deckt einen Überverkauf
  von Grid oder Trend ab. Gegen einen Doppelverkauf schützt deshalb nicht
  diese Prüfung, sondern die Sperre über die Pending-Datei (oben).
  Ein **nicht abrufbares** Guthaben lässt
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
  Kaufstufen (Stufen − 1) × `GRID_AMOUNT_PER_LEVEL` - kein zusätzliches
  Tageslimit nötig.
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
  (`[GRID-VERKAUF-FEHLGESCHLAGEN]` im Log und per Telegram). Nach einer
  **eindeutigen** Ablehnung versucht der nächste Zyklus den Verkauf
  automatisch erneut, da ihr Sell-Target weiterhin erreicht ist. Ist der
  Ausgang **unklar** (Pending-Eintrag steht noch), wird nicht erneut
  verkauft (`[GRID-VERKAUF-UNGEKLAERT]`), bis die Reconciliation zu
  Beginn eines Zyklus ihn geklärt hat: ausgeführt → Position mit genau
  dieser Order geschlossen, ohne Wirkung → regulärer Verkauf. Ebenso gilt
  eine Stufe mit ungeklärtem Kauf als belegt. Anders als beim Trend-Bot muss
  dabei keine Absicherung wiederhergestellt werden - der Grid-Bot
  platziert nie eine exchange-seitige Stop-Order und storniert vor einem
  Verkauf entsprechend auch keine. Die Telegram-Meldung kommt pro
  Position nur einmal je Prozesslauf (sonst im 5-Minuten-Takt), ins Log
  geht jeder Fehlschlag.
- **Staub beim Kauf** (seit 16.10.2026): Führt die Börse einen Kauf nur
  teilweise aus und liegt die gekaufte Menge zum Füllpreis unter dem
  Mindestvolumen, ließe sie sich nie verkaufen. Die Position wird dann
  sofort geschlossen: `close_reason` "dust", `dust_qty` die tatsächlich
  erhaltene Menge, `sell_price` leer, `realized_pnl` = −`quote_spent`
  (`[GRID-STAUB]`). Die Stufe ist danach frei, eine Sperre gibt es nicht.
  Eine verkaufbare Teilmenge wird normal gebucht (`[GRID-KAUF]` mit
  „Teilfüllung“). Eine Kauf-Order ohne Ausführung belegt keine Stufe mehr
  (7.1).
- **Telegram-Benachrichtigungen** (falls konfiguriert, siehe README Abschnitt 7):
  `[GRID-KAUF]`/`[GRID-KAUF DRY-RUN]`, `[GRID-VERKAUF]` (mit realisiertem
  Gewinn/Verlust dieser Position), `[GRID-VERKAUF-FEHLGESCHLAGEN]`,
  `[GRID-VERKAUF-GESPERRT]`,
  `[GRID-STOP-LOSS]`, `[GRID-NOTAUS]`, `[GRID-FEHLER]`,
  `[GRID-DOPPELVERKAUF]` (seit 27.09.2026, siehe 7.1), seit 16.10.2026
  außerdem `[GRID-STAUB]` und `[GRID-TEILFUELLUNG-UNGEBUCHT]`.
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

**Parameter** (seit 28.09.2026, E6 in 6g „Symbolbindung“): Paar, Spanne,
Abstand und Betrag kommen aus denselben Variablen wie beim Bot, also
`GRID_SYMBOL`, `GRID_LOWER_LIMIT`, `GRID_UPPER_LIMIT`, `GRID_SPACING_PCT`
und `GRID_AMOUNT_PER_LEVEL` aus der Umgebung oder der `.env`.
`GRID_STOP_LOSS_PCT` wird bewusst nicht gelesen, dafür gilt weiter
`--stop-loss-pct` (Default 15). Vorrang: Kommandozeile, Variable,
Standard. Eine leere Variable gilt als nicht gesetzt. Der Standard sind
die Werte, mit denen Abschnitt 6 gerechnet ist (BTCUSDT, 70.000 bis
90.000, 1,5 %, 15). Er steht bewusst in einer eigenen Konstante
(`DOCUMENTED_SYMBOL`) und hängt nicht am Default der Bots. Der Report
beginnt mit „Verwendete Werte“ und nennt je Wert die Herkunft („aus
GRID_LOWER_LIMIT“, „Standard, GRID_LOWER_LIMIT nicht gesetzt“ oder
„Kommandozeile“). **Achtung:** Auf einem Rechner mit `.env`, in der
Grid-Werte stehen, rechnet der Backtest mit diesen Werten. Wer die Zahlen
aus Abschnitt 6 nachrechnen will, gibt die Werte auf der Kommandozeile
an. Die anderen drei Backtests nehmen auf dieselbe Weise nur das Paar
ihres Bots (`DCA_SYMBOL`, `TREND_SYMBOL`, `ALLOCATOR_SYMBOL`).

Fehlen in den abgerufenen Kerzen welche, oder setzen die Daten erst nach
dem angefragten Beginn ein (Paar später gelistet), warnt
`fetch_historical_klines()` mit `[KERZEN-LUECKE]` (E7). Das ist nur eine
Warnung, die Rechnung läuft über die Lücke hinweg, als hätte es den
Zeitraum nicht gegeben. Dieselbe Funktion versorgt den Live-Vorlauf von
Trend-Bot und Allocator, dort kann die Warnung also auch im Betrieb
auftauchen.

**Wichtiger Unterschied zu DCA/Trend:** `GRID_LOWER_LIMIT`/`GRID_UPPER_LIMIT`
sind kein skaleninvarianter Wert, sondern ein absoluter Preisbereich,
gekoppelt an das heutige Kursniveau. Gegen die historischen Testzeiträume
(BTC damals deutlich niedriger) getestet, läge die unveränderte Live-Spanne
sofort außerhalb des Kurses -> 0 Trades, sofortiger Trendbruch-Stop-Loss.
Der Backtest zeigt deshalb standardmäßig zwei Ergebnisse pro Zeitraum: das
literale (mit den verwendeten Werten, siehe oben) und einen klar als "ANALYSE,
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
  `[TREND-NOTAUS]`, `[TREND-FEHLER]`, seit 27.09.2026 außerdem
  `[TREND-TEILFUELLUNG]` und `[TREND-DOPPELVERKAUF]`, seit 16.10.2026
  `[TREND-STAUB]` auch beim Einstieg und `[TREND-TEILFUELLUNG-UNGEBUCHT]`.

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
  behandelt. Die Storno-Antwort wird nach `executedQty` ausgewertet: hat
  die Order schon teilweise verkauft, wird das verbucht und nur der Rest
  verkauft (siehe „Teilweise gefüllte Stop-Order“ unten).
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
- **Teilweise gefüllte Stop-Order** (`PARTIALLY_FILLED`): solange sie
  lebt, wird sie gemeldet (Log + Telegram), aber bewusst **nicht**
  korrigiert – sie kann noch vollständig füllen, jede jetzt notierte
  Teilmenge wäre im nächsten Moment falsch. Bei 24-Stunden-Takt ist das
  höchstens eine Erinnerung pro Tag. **Endet** sie mit einer Teilfüllung
  (storniert durch den eigenen Ausstieg, abgelaufen, manuell storniert),
  wird die Teilfüllung verbucht und danach nur der **Rest** verkauft, als
  Stop-Loss-Ausstieg mit Latch, auch wenn der Ausstieg vom Signal kam
  (`[TREND-TEILFUELLUNG]`). Verbucht wird rein zusätzlich:
  `partial_exit_qty`, `partial_exit_quote` (brutto),
  `partial_exit_proceeds` (netto) und `partial_exit_order_ids`, atomar und
  über die orderId idempotent. `quantity` und `quote_spent` bleiben die
  Werte des Einstiegs; verkauft, abgesichert und abgeglichen wird die
  offene Menge `open_quantity()` = `quantity − partial_exit_qty`.
  `realized_pnl` enthält beide Teile, `exit_price` ist der
  mengengewichtete Durchschnitt. Ob eine beendete Order die Position
  geschlossen hat, entscheidet die Menge (Toleranz eine `stepSize`),
  nicht der Status `FILLED`. Liegt der Rest unter dem Mindestvolumen,
  wird die Position geschlossen und der Rest als `dust_qty` gemeldet
  (`[TREND-STAUB]`, Telegram; Menge im Base-, Wert und Ergebnis im
  Quote-Asset des Paars aus `exchangeInfo`, bis zum 28.09.2026 stand
  dort fest „USDT“). Bis zum 27.09.2026 verkaufte der Ausstieg
  hier die volle Menge, auf dem geteilten Konto aus fremdem Bestand, und
  eine beendete Order mit Teilfüllung schloss die ganze Position mit dem
  Teilerlös.
- **Staub beim Einstieg** (seit 16.10.2026): Führt die Börse den
  Einstieg nur teilweise aus und liegt die Menge zum Limit-Preis der
  Stop-Order unter dem Mindestvolumen, würde die Stop-Order abgelehnt.
  Der Trade wird dann sofort geschlossen: `exit_reason`
  "dust_on_entry", `dust_qty` die erhaltene Menge, `realized_pnl` =
  −`quote_spent`, keine Stop-Order, **keine** Sperre (`[TREND-STAUB]`).
  Eine absicherbare Teilmenge wird normal gebucht und mit genau dieser
  Menge abgesichert. Ein Einstieg ohne Ausführung belegt den Slot nicht
  mehr (7.1).
- **Eine einzige Regel für Order-Status:** die Bewertung, ob eine Order
  gefüllt, noch aktiv, beendet oder unlesbar ist, steht genau einmal im
  Projekt (`order_lifecycle_state()` in `pending_orders.py`) und wird
  vom Zyklus-Check, vom Pending-Orders-Pfad (7.1) und seit dem
  16.10.2026 auch von der Bewertung jeder regulären Market-Antwort
  verwendet. Vorher hatten die ersten beiden eigene, leicht
  unterschiedliche Regeln.
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
  entfernt, statt eine tote Order als Absicherung auszuweisen. Das gilt
  nach einer **eindeutigen** Ablehnung. Ist der Ausgang des Verkaufs
  **unklar** (Pending-Eintrag steht noch), fragt der Bot bis zu dreimal im
  Abstand von 20 s nach (`UNCLEAR_SELL_RECHECKS`,
  `UNCLEAR_SELL_RECHECK_SECONDS`): ausgeführt → Ausstieg verbuchen; ohne
  Wirkung oder nach 60 s weiter unbekannt → neue Stop-Order wie oben;
  weiter unklar → **keine** neue Stop-Order (sie wäre, falls der Verkauf
  durchging, aus fremdem Bestand gedeckt), dafür `[TREND-WARNUNG]`
  „möglicherweise ungeschützt“. Bis der Eintrag geklärt ist, gibt es für
  diesen Trade keinen erneuten Ausstieg (`[TREND-AUSSTIEG-UNGEKLAERT]`) und
  keine neue Stop-Order; der fehlende Schutz wird gezählt und ab 3 Zyklen
  gemeldet. Ein ungeklärter Kauf sperrt neue Einstiege.
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

Je Ledger nennt das Skript die Paare, die darin vorkommen, etwa
`Paare im Ledger: BTCUSDT: 12 (davon 12 ohne Feld, gelten als BTCUSDT)`.
Einträge ohne Feld `symbol` stammen aus der Zeit vor der Symbolbindung
und gelten als BTCUSDT (7.1). Führt ein Ledger ein anderes Paar als das
konfigurierte, steht darunter ein `ACHTUNG` mit dem Hinweis auf
`python -m dca_bot.symbol_guard --report`, denn der Bot startet so nicht.

#### Bot-übergreifender Kontoabgleich

Sind Binance-Zugangsdaten vorhanden, hängt das Skript einen zweiten
Teil an: Es fragt den **tatsächlichen** Kontostand und die offenen
Orders ab und stellt ihnen die **Summe** dessen gegenüber, was alle drei
Ledger als offen führen, je Base-Asset und über alle Paare hinweg.

```
==============================================================================
KONTOABGLEICH BTC (BTCUSDT: dca, grid, trend) - alle Bots gegen den Bestand
==============================================================================

Bot      Paar          laut Ledger offen  Hinweis
------------------------------------------------------------------------------
dca      BTCUSDT              0.00780000
grid     BTCUSDT              0.00116000  2 Dry-Run (zählt nicht)
trend    BTCUSDT              0.00019505
------------------------------------------------------------------------------
SUMME                         0.00915505
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
- **Gruppiert nach Base-Asset, nicht nach Symbol** (seit 28.09.2026,
  Symbolbindung in 6g). Jedes Ledger ergibt einen Anspruch je Paar, das
  darin offen vorkommt; welches Paar ein Eintrag hat, steht in ihm selbst.
  Die Ansprüche werden dann nach dem Base-Asset ihres Paars aus
  `exchangeInfo` zusammengefasst. Grund: BTCUSDT und BTCEUR handeln
  dasselbe BTC auf demselben Konto. Nach Symbol getrennt hätten DCA auf
  BTCUSDT (0,3 BTC) und Grid auf BTCEUR (0,2 BTC) bei 0,4 BTC auf dem
  Konto jeweils gedeckt ausgesehen, der Fehlbetrag von 0,1 BTC wäre
  unsichtbar geblieben. Das Guthaben wird einmal je Base-Asset abgefragt,
  die offenen Orders aus allen Paaren der Gruppe. Verschiedene
  Base-Assets bleiben getrennt, eine Summe über sie wäre sinnlos. Im
  Normalfall (alle drei auf demselben Paar) gibt es genau eine Gruppe.
- **Ein unvollständiger Abgleich sagt das.** Sind die Handelsregeln eines
  Paars nicht abrufbar, fehlen dessen Ansprüche in der Summe. Das steht
  dann als `ACHTUNG: … er ist UNVOLLSTÄNDIG` über dem Abgleich, damit ein
  „In Ordnung“ nicht auf einer zu kleinen Summe beruht.
- **Ein Überschuss ist kein Befund.** Hält das Konto mehr, als die
  Ledger beanspruchen, kann das manueller Bestand oder eine Altlast
  sein. Nur die andere Richtung wird als Problem gemeldet - und dann mit
  dem ausdrücklichen Hinweis, die Ledger-Dateien **nicht** blind
  anzupassen, bevor geklärt ist, welche Seite recht hat.
- Die Toleranz stammt aus demselben `balance_guard`, nach dem auch die
  Bots entscheiden - zwei getrennte Toleranzen für dieselbe Frage wären
  der sichere Weg zu einem Audit, das einem Bot widerspricht.

#### Orders nachschlagen (`check_orders.py`, seit 27.09.2026)

Das Gegenstück zum Audit für eine einzelne Order: `python -m
dca_bot.check_orders --client-order-id <id>` (README 8.4). Binance findet
eine Order nur unter dem Symbol, unter dem sie platziert wurde; unter
jedem anderen antwortet es mit −2013, als gäbe es sie nicht. Gesucht wird
deshalb in dieser Reihenfolge (seit 28.09.2026, Symbolbindung in 6g):
zuerst unter dem Paar, unter dem die eigene Buchhaltung des Bots die
Order führt (Pending-Eintrag oder Ledger-Eintrag, Altbestand ohne Feld
als BTCUSDT), dann unter dem konfigurierten Paar des Bots, den das
Präfix der clientOrderId verrät, dann unter allen übrigen konfigurierten
Paaren. Mit `--symbol <paar>` wird nur unter diesem gesucht. Bis zum
28.09.2026 wurde bei bekanntem Präfix nur unter dem aktuellen Paar des
Bots gesucht, eine Order aus der Zeit vor einem Paarwechsel galt damit
als „nie angenommen“.

Nachgeschlagen wird mit `get_order_by_client_id()` und bewertet mit
`order_lifecycle_state()`, also mit denselben Regeln, nach denen der Bot
selbst entscheidet. Ein Treffer entscheidet. Ist eine der Abfragen
gescheitert, lautet das Ergebnis „keine Aussage“. „Nie angenommen“ sagt
das Skript nur, wenn jede Abfrage −2013 ergab **und** darunter das
maßgebliche Paar war, also das aus `--symbol` oder aus der eigenen
Buchhaltung. Ohne ein solches Paar heißt −2013 nur „unter diesen Paaren
nicht gefunden“, mit dem Hinweis, gegebenenfalls mit `--symbol` erneut zu
suchen. Dazu der Abgleich mit
der eigenen Buchhaltung: Steht die ID in der Pending-Datei des Bots, steht
sie im Ledger (`client_order_id`, `sell_client_order_id`,
`exit_client_order_id`, bei der Trend-Stop-Order `stop_loss_order_id` über
die orderId)? Ohne Argumente zeigt das Skript je Symbol Kurs, Guthaben
(Base- und Quote-Asset aus `exchangeInfo`) und die letzten Orders mit
clientOrderId und Bot; das ist zugleich der Verbindungstest. Es nutzt den
Client des Audits (`_build_read_only_client()`) und kann damit
strukturell keine Orders platzieren.

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

`test_shared_account.py` (seit 27.09.2026) ist die einzige Testdatei, die
das **geteilte Konto** abbildet: echter `TradingClient` und echte
Strategien über einem `FakeExchange`, der den rohen python-binance-Client
ersetzt und Deckung, Storno-Semantik, Mindestvolumen und Netzwerkfehler
wie Binance behandelt. Geprüft wird eine Eigentums-Invariante pro Bot,
unabhängig vom Codepfad (Details in 6g, „Systemcheck vom 27.09.2026“).
Die übrigen Fakes starten weiterhin mit reichlich freiem Guthaben - neue
Verkaufspfade gehören deshalb auch hier getestet. Seit dem 16.10.2026
lässt sich je Market-Order einstellen, welchen Anteil der `FakeExchange`
ausführt (`set_liquidity`). Unter 1 endet die Order mit `EXPIRED`, bei 0
mit ausgeführt 0, wie im Testnet am 09.10. und 11.10.2026.

`test_unfilled_market_orders.py` (seit 16.10.2026) deckt Market-Orders
ohne oder mit nur teilweiser Ausführung ab: die Bewertung im echten
`TradingClient`, den Ledger-Schutz aller drei Ledger und die Wege durch
alle drei Strategien auf dem geteilten Konto.
`test_remove_unfilled_grid_positions.py` bildet für das
Bereinigungswerkzeug die Lage auf dem Homeserver vom 16.10.2026 nach.

Die ganze Suite: `python -m unittest discover -s tests -t .`

---

*Lebendes Projektdokument, seit dem 29.09.2026 in zwei Dateien. Hier: der aktuelle Stand mit den offenen Punkten und Abschnitt 7 (technische Referenz), beide werden direkt korrigiert, sowie das Log ab 29.09.2026, das wie jedes Log nur datierte Vermerke bekommt. In `trading-bot-projekt-archiv.md`: Recherche, Planung und das chronologische Log bis 28.09.2026 (Abschnitte 1–6i), unverändert verschoben. Entstanden am 13.09.2026 durch Zusammenführen zweier parallel gepflegter Versionen (Chat-Artefakt + lokale Claude-Code-Fortschreibung).*

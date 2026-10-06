# Trading-Bot-Projekt: Planung, Fortschritts-Log und technische Referenz

**Stand:** 7. Oktober 2026
**Status:** Testnet-Betrieb, kein Live-Geld. Der Sicherheitsreview (K1–K5, W1–W18, Infrastruktur) ist seit dem 16.09. abgeschlossen. Der Homeserver läuft faktisch seit dem 16.09.2026 als vollständiges System, mit allen vier Bausteinen und aktivem Allocator-Opt-in für DCA und Trend. Der aktuelle Trading-Status dort wurde am 25.09.2026 verifiziert (siehe 6h). Der VPS ist seit dem 07.10.2026 abgeschlossen (Dienste gestoppt, Zugang entfernt, Vertrag gekündigt zum 12.10.), die VPS-Daten werden nicht ausgewertet, und der formale Cutover am 05.10. mit Snapshot-Schritt entfällt (siehe Log 07.10.2026). Die Testphase ist auf ca. 2–3 Monate verlängert, also bis etwa Mitte November bis Mitte Dezember 2026. Seit dem Review sind mehrere Fund-und-Fix-Serien abgeschlossen: die Verbesserungsvorschläge (6i, 17.09.), die Dry-Run-Beträge (22.09.), die Code-Überprüfung vom 25.09. und der Systemcheck vom 27.09. mit K-A/K-B und W-A bis W-G (alle 6g). Die technische Referenz zum aktuellen Stand steht in Abschnitt 7.

---

*Ältere, abgeschlossene Historie (Abschnitte 1–6i: Recherche, Planung und das chronologische Log bis 28.09.2026) steht unverändert in `trading-bot-projekt-archiv.md` und muss nur bei Bedarf gelesen werden, etwa bei einer Rückfrage zur ursprünglichen Strategiewahl. Verweise wie „siehe 6g“ in Code und Doku meinen die Abschnitte dort. Was davon heute noch offen ist, fasst der Abschnitt „Aktueller Stand und offene Punkte“ zusammen.*

---

## Aktueller Stand und offene Punkte

*Stand 07.10.2026 für VPS, Deploy-Stand, Termine und Auswertung der Testphase, übrige Angaben Stand 29.09.2026. Dieser Abschnitt beschreibt wie Abschnitt 7 den aktuellen Stand und wird direkt korrigiert. Die Herleitung steht jeweils im Archiv (`trading-bot-projekt-archiv.md`), Abschnittsnummern und Überschriften sind dort unverändert.*

### Betrieb

- **Homeserver** (vollständiges System seit 16.09.2026): alle vier Bots als systemd-Services im Testnet. DCA, Grid und Trend handeln mit echten Testnet-Orders (`*_BOT_ENABLE_TRADING=true`, verifiziert 25.09.), das Allocator-Opt-in für DCA und Trend ist aktiv. `GRID_AMOUNT_PER_LEVEL` = 9,38, maximale Kapitalbindung ca. 150,08. Details: Archiv 6e, 6h, 6g „W16 umgesetzt“.
- **VPS:** abgeschlossen seit 07.10.2026. Die drei Bot-Dienste (dca-bot, grid-bot, trend-bot) sind gestoppt und deaktiviert, `.env` und Archivdatei auf dem VPS sind gelöscht, der Claude-Code-Deploy-Schlüssel (claude-code-vps-deploy) ist aus `authorized_keys` entfernt, der VPS-Eintrag aus `known_hosts` auf dem lokalen Rechner ebenfalls. Es gibt keine Auswertung der VPS-Daten und keinen behaltenen Snapshot. Details: Log 07.10.2026.
- **Paar:** im Testnet BTCUSDT, alle „€“-Beträge sind dort USDT. Für echtes Geld wird BTCEUR verwendet (Entscheidung 28.09.2026). Details: Archiv 5b (Vermerk 28.09.), 6g „Symbolbindung“.

### Deploy-Stand

- Deployed: `980f3c3` auf Homeserver am 29.09.2026. Belege: das Journal vom 29.09.2026 (10:17 UTC) mit „Code-Version: 980f3c3“ bei Grid, Trend und Allocator, und laut Ausgabe von `git log -1` auf dem Homeserver am 06.10.2026. Damit laufen dort W-C bis W-G samt Nachtrag (`a67e7dc` bis `46ca7a7`) und die Symbolbindung (`e2a37bd` bis `9ef7d60`). Auf master seitdem nur Doku sowie `close_dry_run_trend` (nicht deployed). Bei jedem Deploy nach dem Pull und vor dem Neustart: `python -m dca_bot.symbol_guard --report`.
- Deploys werden ab jetzt **hier** vermerkt, als `Deployed: <hash> auf Homeserver am <Datum>`. Das ersetzt den Vermerk vom 29.09.2026 in Archiv 6g. Details zum Rückweg auf den alten Code: Archiv 6g „Symbolbindung“.

### Termine

- **12.10.2026, Vertragsende VPS** (Contabo Cloud VPS 4 (2026), gekündigt zum 12.10.2026, laut Kundenbereich bis dahin abgerechnet, keine Zusatzposten): kein Handlungsbedarf mehr.
- **Testphase** auf dem Homeserver bis etwa Mitte November bis Mitte Dezember 2026. Details: Archiv 6h.

### Vorbedingungen für echtes Kapital (300 €: 150 € Grid, 150 € Allocator-Topf)

1. **Positionsgrößen:** offen sind `DCA_QUOTE_AMOUNT`, `TREND_AMOUNT_PER_TRADE`, Grid-Spanne und `GRID_SPACING_PCT`. Beim Paarwechsel sind alle Beträge und die Spanne neu in Euro festzulegen. Details: Archiv 5b, 6d Punkt 3.
2. **Datenbasis für `TREND_STOP_LIMIT_OFFSET_PCT`**, bisher n = 2 simulierte Exits. **Derzeit fließen keine Kalibrierungsdaten:** Die Dry-Run-Position vom 15.09. belegt den einzigen Trend-Slot. Nötig sind erst ihr Ausstieg, dann ein echter Einstieg, dann eine an der Börse gefüllte Stop-Order. Schließt sie über den internen Stop-Loss, sperrt der Latch neue Einstiege bis zum manuellen Reset. Details: Archiv 6f, 6h „Trend-Bot: Die Kalibrierungsdaten fließen noch nicht“.
   Das Werkzeug `python -m dca_bot.close_dry_run_trend` schließt die Dry-Run-Position im Ledger, ohne Sperre; auf dem Homeserver ist es noch nicht angewendet (Ablauf: Log 07.10.2026). Als Datenbasis für den Offset taugt das Testnet aber kaum: Laut Auswertung der öffentlichen Kerzen zeigt es an etwa 4 % der Stunden ein Tief mehr als 10 % unter dem Mainnet. Eine echte Stop-Order wird dort vermutlich von einem Ausreißer ausgelöst, nicht vom Markt. Gefüllte Stop-Orders im Testnet belegen die Technik, nicht den Offset.
3. **Abschließender Sicherheitsreview** kurz vor dem Live-Gang. Details: Archiv 6d, 6h.
4. **Paarwechsel auf BTCEUR**, noch nicht geplant: alle vier `*_SYMBOL`, Grid-Spanne und Beträge in Euro, frische Ledger oder bewusst weitergeführter Altbestand. Offen sind außerdem die Dashboard-App und der Pilot. Nicht verifiziert ist, ob Binance bei einer Abfrage unter dem falschen Symbol mit −2013 antwortet, das lässt sich erst im Pilot prüfen. Details: Archiv 6g „Symbolbindung“, 6h.
5. **„Gebühren mit BNB bezahlen“ ausgeschaltet.** Details: Archiv 6h.
6. **Unterkonten pro Bot:** vor dem Live-Gang bewusst entscheiden, keine harte Vorbedingung. Fällt die Entscheidung dafür, braucht es Code (eigene Schlüssel je Bot, Audit über mehrere Konten) vor dem Live-Gang. Details: Archiv 6h (Ergänzung 29.09.), 6g „Systemcheck vom 27.09.2026“.

### Bewusst zurückgestellt oder vorgemerkt

- **W14, Grid ohne börsenseitigen Stop-Loss:** eine eigene Architekturentscheidung zwischen einer Sammel-Stop-Order und n Einzel-Stop-Orders. Bis dahin sperrt der Trendbruch-Stop nur Käufe, und die Kapitalbindung ist durch Stufen × Betrag gedeckelt. Details: Archiv 6g „W14“.
- **Automatischer Stop-Loss-Reset (Punkt 16):** im Backtest durchgespielt, n = 1. Entschieden wird mit echten Daten, bis dahin wird manuell zurückgesetzt. Details: Archiv 6i „Punkt 16 als Backtest-Experiment“.
- **Punkt 13 (gemeinsame Bot-Runtime) und F2 (Notaus pausiert statt zu beenden):** zurückgestellt, kein fester Zeitpunkt (der ursprüngliche Cutover am 05.10. entfällt). Voraussetzung: keine offenen Deploys und eine ruhige Woche, weil beide Punkte alle vier Einstiegspunkte anfassen. Details: Archiv 6i „Offen aus der Liste“, 6g „W-F“.
- **DCA-Portfolio-Stop-Loss in den Backtests:** wird nicht abgebildet, die DCA-Zahlen in 5a und 6 überschätzen deshalb den Kapitaleinsatz im Bärenmarkt. Details: Archiv 6g „W-G“.
- **Archivierung der Ledger-Dateien:** kein akuter Bedarf, nur zusammen mit der Dashboard-App. Details: Archiv 6g „Vorgemerkt: langfristiges Datenwachstum“.
- **Füllpreis alter Ledger-Einträge rückwirkend korrigieren:** vorgemerkt für den Steuer-Export. Einträge von vor K2 haben keine `clientOrderId`. Details: Archiv 6g „Priorität 4“.
- **Punkt 15 (SQLite):** bei der heutigen Datenmenge noch Jahre entfernt. Details: Archiv 6i.

### Für die Auswertung der Testphase

- In den Homeserver-Ledgern von DCA und Trend stehen Dry-Run- und echte Einträge nebeneinander, die Auswertung muss nach `dry_run` trennen. Das Grid-Ledger ist durchgehend echt. Details: Archiv 6h „Umstellung auf echte Orders“.
- Einen Vergleich VPS gegen Homeserver gibt es nicht: Die VPS-Daten werden nicht ausgewertet (Entscheidung 07.10.2026, Gründe im Log). Details: Archiv 6g „Beobachtung zur Allocator-Wirkung“, 5a.
- Die Dry-Run-Werte des VPS-Grid sind am 22.09. korrigiert. Die `.pre-fix`-Kopie wird nicht mehr gebraucht, weil die VPS-Daten nicht ausgewertet werden. Details: Archiv 6g „Folgefund aus K3“.
- Staub (`dust_qty`) rechnet das Positions-Audit keinem Bot zu, er erscheint als Überschuss. Details: Archiv 6g „Systemcheck vom 27.09.2026“.
- **Ticker-Ausreißer im Testnet:** Testnet-Gewinne sind dadurch verzerrt und taugen nicht für Renditeschätzungen. Als Ursache wird ein dünnes Orderbuch vermutet, das ist nicht gemessen. Beispiel 02.10.2026: Vom realisierten Grid-Ergebnis von 8,65 USDT (Auswertung vom 06.10.) entfallen 6,31 USDT auf diesen einen Tag, davon 6,15 USDT auf sechs Stufen (8 bis 13). Sie wurden am 02.10. zwischen 13:30:13 und 13:30:16 UTC zu 77.809 bis 79.480 USDT gekauft und zwischen 13:35:17 und 13:35:30 UTC zu 86.928 bis 86.962 USDT verkauft, je Stufe 0,82 bis 1,09 USDT, normale Zyklen bringen 0,14 bis 0,21 USDT. Die Mainnet-Stundenkerze von 13:00 UTC hatte ihr Tief bei 86.465,72, die Testnet-Kerze bei 75.745,57, das Mainnet-Tagestief lag bei 83.888 (Stundenkerzen, 18:00 UTC). Alle sechs Kaufpreise liegen unter dem Mainnet-Tagestief. Ansatz zur Bereinigung: Kauf- und Verkaufszeitpunkte der Grid-Trades gegen die Mainnet-Stundenkerzen prüfen. Aussagen über die Strategie stützen sich auf die Backtests (Mainnet-Kerzen), das Testnet belegt vor allem die Technik. Vom selben Ticker hängen auch die Trend-Dry-Run-Position vom 15.09. und die Kalibrierung von `TREND_STOP_LIMIT_OFFSET_PCT` ab: Ein Ausreißer könnte dort Einstiege oder Stop-Loss-Auslösungen erzeugen, die es auf dem echten Markt nicht gäbe. Details: Log 06.10.2026.

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
- **Telegram-Benachrichtigungen** (falls konfiguriert, siehe README Abschnitt 7):
  `[GRID-KAUF]`/`[GRID-KAUF DRY-RUN]`, `[GRID-VERKAUF]` (mit realisiertem
  Gewinn/Verlust dieser Position), `[GRID-VERKAUF-FEHLGESCHLAGEN]`,
  `[GRID-VERKAUF-GESPERRT]`,
  `[GRID-STOP-LOSS]`, `[GRID-NOTAUS]`, `[GRID-FEHLER]`,
  `[GRID-DOPPELVERKAUF]` (seit 27.09.2026, siehe 7.1).
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
  `[TREND-TEILFUELLUNG]` und `[TREND-DOPPELVERKAUF]`.

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
Verkaufspfade gehören deshalb auch hier getestet.

Die ganze Suite: `python -m unittest discover -s tests -t .`

---

*Lebendes Projektdokument, seit dem 29.09.2026 in zwei Dateien. Hier: der aktuelle Stand mit den offenen Punkten und Abschnitt 7 (technische Referenz), beide werden direkt korrigiert, sowie das Log ab 29.09.2026, das wie jedes Log nur datierte Vermerke bekommt. In `trading-bot-projekt-archiv.md`: Recherche, Planung und das chronologische Log bis 28.09.2026 (Abschnitte 1–6i), unverändert verschoben. Entstanden am 13.09.2026 durch Zusammenführen zweier parallel gepflegter Versionen (Chat-Artefakt + lokale Claude-Code-Fortschreibung).*

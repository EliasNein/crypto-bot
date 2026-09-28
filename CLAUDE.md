# Trading-Bot – Projektkontext für Claude Code

## Überblick
Vier eigenständige, testnet-only Python-Bausteine gegen Binance:
- DCA: kauft alle 24h fest, verkauft nie
- Grid: geometrische Preisstufen, 5-Min-Takt, kauft/verkauft pro Stufe
- Trend: EMA-20/50-Crossover, long-only, echte STOP_LOSS_LIMIT-Order an der Börse
- Allocator: berechnet nur den Trend-Anteil (0-1), platziert selbst nie Orders

Projektdokument: trading-bot-projekt.md - aktueller Stand und offene
Punkte, Log ab 29.09.2026, technische Referenz (Abschnitt 7). Die
Historie bis 28.09.2026 (Abschnitte 1-6i: Recherche, Reviews, Systemcheck,
Symbolbindung) steht unverändert in trading-bot-projekt-archiv.md und wird
nur bei Bedarf gelesen. Verweise wie „siehe 6g“ meinen das Archiv.

## Sicherheitsprinzipien (K1-K5, W1-W18, seit 16.09. abgeschlossen)
- Dry-Run per Default, Notaus auf 5 unabhängigen Wegen
- Keine Order ohne Ledger-Eintrag (clientOrderId-Idempotenz, Reconciliation)
- Dry-Run-Positionen werden nie echt verkauft
- Alle Ledger atomar geschrieben, Prozess-Lock verhindert Doppelstarts
- Ein Zyklusfehler beendet nie den ganzen Bot

## Aktueller Stand
- Homeserver: alle vier Bots live (Testnet). Code-Stand auf master siehe
  git log. ACHTUNG: Das ist nicht automatisch der Stand auf den Servern -
  deren tatsächlicher Commit-Hash steht in trading-bot-projekt.md,
  Abschnitt „Aktueller Stand und offene Punkte“, unter „Deploy-Stand“
  (Stand 28.09.2026: 10ce096 auf beiden Servern). Neue Deploys werden
  dort vermerkt.
- VPS: nur DCA live, endet 12.10.2026
- Für echtes Geld: BTCEUR (nicht USDT, im EWR nicht handelbar)
- Kapital geplant: 150€ Grid / 150€ Allocator-Topf (DCA+Trend)

## Tests
python -m unittest discover -s tests -t .
Mutationsproben gehören zu jeder sicherheitsrelevanten Änderung.

## Arbeitsweise, die ich erwarte
- Bei sicherheitsrelevanten Änderungen: erst vollständigen Plan vorlegen,
  auf Bestätigung warten, dann erst implementieren
- Offene Entscheidungen (mehrere Optionen) mir vorlegen, nicht selbst wählen
- Jede neue Sicherheitsprüfung bekommt eine Mutation zum Nachweis
- Änderungen an Doku als datierte Vermerke ergänzen, nie alte Einträge
  überschreiben oder löschen
- Ausnahme: Abschnitt 7 ('Technische Referenz') und der Abschnitt
  „Aktueller Stand und offene Punkte“ beschreiben den aktuellen Stand und
  werden direkt korrigiert, nie mit datierten Vermerken versehen - dort
  zählt nur, was jetzt gilt. Die Regel zu datierten Vermerken gilt für die
  chronologischen Log-Abschnitte: „Log ab 29.09.2026“ in
  trading-bot-projekt.md und die Abschnitte 6, 6g usw. im Archiv. Neue
  Log-Einträge kommen ins „Log ab 29.09.2026“, nicht ins Archiv.
- Commit erst nach meiner Freigabe, gepusht wird nur auf ausdrückliche Bitte

## Umfang des Einlesens
Nicht bei jeder Aufgabe alles lesen. Zwei Modi:

- Gezielt (Standard): Bei einer klar umrissenen Aufgabe (ein Bug, eine
  einzelne Funktion, eine Doku-Korrektur) nur die tatsächlich betroffenen
  Module lesen, nicht den ganzen dca_bot/-Ordner. Bei Unsicherheit, welche
  Module betroffen sind, gezielt danach suchen (grep/Suche), nicht
  vorsorglich alles öffnen.
- Vollständig: Nur bei ausdrücklich verlangten Audits, Sicherheitsüber-
  prüfungen oder wenn ich das Wort "vollständig"/"kompletter Systemcheck"
  verwende. Dann wie bisher: alles lesen, nichts überspringen.

Im Zweifel nachfragen, welcher Modus gemeint ist, statt zu raten.
# Terra-Kit

(c) Oliver Bedernik · Alle Rechte vorbehalten.

Werkzeugsatz für Lernmaterial nach dem **Terra-Standard 4.0**. Inhalt wird ausschließlich als `werk.json` geschrieben; Lernskript (Buchsatz), Wissenslandkarte, Exam und Anki-Deck entstehen daraus automatisch und einheitlich.

## Prinzip

Daten statt Nachbau: Gestaltung, Satz, Register und Prüfungen liegen im Code, nicht in der Interpretation des Schreibenden. Seit 4.0 ist das Lernskript ein Buch: **Kapitel mit Abschnitten und Bausteinen** in Fließtext, mit Randbelegen, Spitzmarken, Einbettungen und einem Umbruch mit Korrekturläufen. Die Karte zeigt dieselben Abschnitte verdichtet; Exam und Deck verweisen auf dieselben Abschnittscodes.

## Bestandteile

| Datei | Zweck |
|---|---|
| `schema.json` | Datenmodell 4.0: Kapitel → Abschnitte → Bausteine; Repetitorium (L) mit eigenen Abschnitten |
| `schema_3.json` | altes Datenmodell (Provinzen, Kacheln); nur noch für `umsetzen.py` |
| `validate.py` | Prüfung in fünf Stufen: Schema, Typografie, Kapitel und Bausteine samt Rechenprobe und Bildprüfung, Satzregeln des Buchsatzes, Formeln; Abdeckung beim Referenzwerk; Exam gegen sein Werk |
| `skript.py` | Lernskript im Buchsatz (Paged.js 0.4.3 in Chromium): Titelseite, Titelei, Kapitel, Repetitorium, Anhang, Randbelege, Register, Lesezeichen, Satzprüfung, Kontaktabzug |
| `satz.py` | Hilfsbibliothek: Markup, Typografie, Trennung, KaTeX, Kurve, Organigramm, T-Konto, Zeitleiste, Bild, Quellenverzeichnis, Kontaktabzug |
| `diagramm.py` | Flussdiagramme und BPMN mit Bahnen, Farbschlüssel der Rollen |
| `relief.py` | Höhenlinien der Titelseite (aus dem Titel abgeleitet, ohne Stoffbezug) |
| `sicht.py` | Kachelsicht: verdichtet jeden Abschnitt für Karte, Exam und Anki |
| `karte.py` | interaktive Wissenslandkarte als eine selbstständige HTML-Datei |
| `exam.py` | Prüfung interaktiv (HTML) und mit `--pdf` als A4-Bogen mit Lösungsteil |
| `anki.py` | importierbares Anki-Deck (.apkg, auch AnkiDroid) |
| `umsetzen.py` | Werk oder Exam 3.x → Standard 4.0, mit Nacharbeitsliste |
| `pruefliste.py` | Prüfliste für den Advocatus diaboli (Normen, Rechtsprechung, Daten, Zahlen, Rechnungen, Bildrechte, Randbelege, Auflagen) |
| `diff.py` | Diff-Bericht zweier Fassungen, trägt ins Änderungsprotokoll ein |
| `rechenprobe.py` | rechnet Rechenwege dezimal exakt nach (ohne `eval`), erzeugt Quellenkritik bei abweichender Quelle |
| `bild.py` | bettet verknüpfte Rasterbilder ein, verkleinert, entfernt EXIF |
| `referenzwerk.json` | „Terra Exemplaris“ 4.0: jeder Baustein, jede Abbildungsart, jeder Sonderfall des Satzes (Abdeckungsprüfung) |
| `referenz_historica.json` | „Terra Historica Constitutionalis“ 2.0: ganzes Werk, sieben Kapitel und Repetitorium, 39 Abschnitte, 52 Randbelege; Muster für Werke |
| `exam_historica.json` | Referenzexam zur Historica: 28 Fragen, 20 mit Sachverhalt, 16 Mehrfachauswahl |
| `tests/run_tests.py` | 97 Tests: Referenzwerke und Referenzexam sauber, Validator (66 eingeschleuste Fehler), Exam (10), Exam, Umsetzer, Kachelsicht, Karte, Anki, Prüfliste, Diff, Rechenprobe, Version, Workflow |
| `tests/buch_test.py` | Testreihe Buchsatz: Prüfregeln, Gleiten, Nahtliste, Satz in Chromium (Vermerk auf jeder Seite, Metadaten, Lesezeichen, Randbelege, Anriss), Titelseiten, Relief |
| `tests/karte_test.py`, `tests/exam_test.py` | Browsertests von Karte und Exam (Funktion, Überlappung, Mobil, Dunkelmodus) |
| `vorlage/buch.css` | Satzvorlage des Buchsatzes (auf `skript.css` der Terrae aufbauend) |
| `vorlage/karte.*`, `vorlage/exam.*`, `vorlage/farben.css` | Oberflächen von Karte und Exam |
| `vorlage/montage.js`, `vorlage/umbruch.js` | Seitenmontage des A4-Prüfungsbogens (Exam); das Lernskript setzt seit 4.0 Paged.js |

## Verwendung

```bash
bash einrichten.sh                       # Abhängigkeiten, beide Testreihen, Referenzwerk; endet mit „Terra-Kit bereit.“
python3 validate.py werk.json            # Exitcode 0 = keine Fehler; --streng: Warnungen zählen als Fehler
python3 pruefliste.py werk.json          # Prüfliste für den Advocatus diaboli (pruefliste.md)
python3 skript.py werk.json --aus ausgabe/            # Lernskript (PDF, Bericht, Kontaktabzug, Nahtliste)
python3 karte.py werk.json --aus ausgabe/             # Wissenslandkarte zur Veröffentlichung
python3 validate.py exam.json werk.json               # Exam prüfen, mit Prüfungsmatrix
python3 exam.py exam.json werk.json --aus ausgabe/ --pdf   # Prüfung interaktiv und als A4-Bogen
python3 anki.py werk.json --aus ausgabe/              # Anki-Deck (.apkg)
python3 diff.py alt.json neu.json --eintragen         # Diff-Bericht ins Änderungsprotokoll
python3 umsetzen.py alt.json neu.json --liste nacharbeit.md   # Werk 3.x → 4.0
python3 umsetzen.py --exam exam_alt.json exam_neu.json        # Exam 3.x → 4.0
python3 bild.py werk.json --einbetten                 # verknüpfte Bilder einbetten
python3 tests/run_tests.py && python3 tests/buch_test.py   # vor jeder Freigabe
```

Freigabe einer Kit-Version nur, wenn beide Testreihen vollständig bestehen **und** `skript.py` für beide Referenzwerke mit 0 Fehlern und 0 Warnungen endet.

## Datenstandard 4.0

```
werk.json
├─ meta        Titel, Untertitel, Reihe, Lehrveranstaltung, Version, Stand, Urheber, Provinzregister, Titelseite
├─ modul       Domäne, Primär- und Sekundärquelle, Zitierstil (AZR oder APA7), Prüfdimensionen
├─ quellen     Kurzzitat, Sigle für Randbelege (@Sigle), Randsigle (rand), Gattung und Felder oder Vollangabe
├─ rollen      Farbschlüssel (Rolle → Name, Farbe) für Diagramme, Zeitstrahl, Merkband, Tabellenköpfe
├─ kapitel[]   Code A bis G, Nummer, Namen, Leitfrage, In 60 Sekunden, Einleitung, Abschnitte, Abschluss, Kontrollfragen
│  └─ abschnitte[]  Code (A1 …, stabil), Titel, Anker, Fundstelle, wichtig, Bausteine
├─ repetitorium Code L; eigene Abschnitte (L1 …), danach die generierten Teile Klausurfallen, Quellenkritik,
│               Lexicon, Selbsttest, Änderungsprotokoll
└─ personen, abkuerzungen, lexicon, quellenkritik, motto, aenderungen
```

**Bausteine:** `absatz` (Fließtext) · `definition` · `kernsatz` (atomar, Fachbegriff fett: wird Anki-Lücke) · `kern` (Kernliste „**Begriff:** Erklärung“, Punkte einzeln `wichtig`) · `aufzaehlung` · `spitzmarke` (`merke`, `feinheit`, `klausurhinweis` als „Cave!“, `austriacum`, `aktualisierung`, `luecke`) · `zitat` (Normwortlaut mit Fundstelle) · `latinum` · `merkband` (Reihenfolge in zwei bis sechs Schritten) · `steckbrief` · `glossar` · `akteure` (Personen des Werks) · `tabelle` (Arten `uebersicht` und `vergleich`, Spaltenrollen, Aussage, Lesehilfe) · `abbildung` (`zeitstrahl` maßstabgetreu, `zeitleiste`, `diagramm` als Fluss oder BPMN, `baum`, `kurve`, `tkonto`, `svg`, `bild`) · `fallbeispiel` (Sachverhalt und Lösungsskizze) · `formel` · `rechenweg` (mit Rechenprobe).

**Inline:** `**fett**` (Fachbegriff, ins Sachregister) · `*kursiv*` · `[[D7]]`, `[[ADM:D7]]` (Verweis mit Seitenzahl) · `{{abb:id}}`, `{{tab:id}}` (Ankündigung einer Einbettung, Pflicht vor ihr) · `^[@Sigle (Fundstelle); @Sigle2]` (Randbeleg).

**Regeln (Validator):** Abschnitt beginnt mit Überleitung oder Definition; höchstens drei Kernsätze und eine Abbildung je Abschnitt; jede Einbettung vorher angekündigt; Kerninhalte (`wichtig`) höchstens ein Drittel der Abschnitte und ein Viertel der Bausteine; Normzitate mit Gesetzesangabe; Fundstellen nach AZR (Jahr/Nummer: `RGBl 1867/142`); Lesehilfe nur bei anspruchsvollen Grafiken und Tabellen (BPMN mit Bahnen, Fluss mit zwei Entscheidungen, große Vergleiche); jede Quelle belegt.

## Lernskript im Buchsatz

Titelseite (Standard „band-relief“ mit Relief im Papier und Provinzregister; weitere Arten über `meta.titelseite`, Abwandlungen über `meta.titel_stil`) · Impressum mit Motto und Zitiervorschlag · Inhalt zweispaltig · Zum Gebrauch · Abkürzungen und Zitierweise (nach Zitierstil) · Kapitel mit Provinzkopf, Einleitung, Abschnitten, „Auf einen Blick“, Kernsätzen und Kontrollfragen · Repetitorium · Abbildungsverzeichnis · Quellenverzeichnis nach Gattungen mit Abschnittschips (ab zwölf Belegen kapitelweise) · Sachregister (Begriffe, Latein, Personen, Normen, Gesetzblätter; überlange Gruppen werden geteilt).

**Satz:** Paged.js umbricht; das Kit prüft den Satz im Browser und korrigiert in bis zu 24 Läufen: Einbettungen gleiten hinter den folgenden Text (nie in den Kapitelabschluss, höchstens in den nächsten Abschnitt), Einzelzeilen werden über die Laufweite ausgeglichen, ein Abschnitt beginnt nie am Seitenfuß (je Lauf der erste je Kapitel), Spitzmarken bleiben bei ihrem Inhalt. Ein Rückbau prüft jeden erzwungenen Seitenwechsel erneut. Tabellen mit mehr als 14 Zeilen laufen über die Seite und wiederholen ihren Kopf; kleinere bleiben ganz.

**Randbelege:** `^[@Sigle (Fundstelle)]` setzt rechts neben der Zeile die Randsigle mit Fundstelle, verlinkt ins Quellenverzeichnis. Hindernisse (Köpfe, Abbildungen, Tabellen) werden umgangen; vor einem Hindernis weicht ein Beleg nach oben aus, wenn das näher liegt. Der Bericht nennt den größten Versatz.

**Prüfungen im Satz:** Blocksatz, geteilte Absätze und Einzelzeilen, Überschrift oder Tabellenkopf am Seitenfuß, Anriss, geteilte Einbettung, Verweisziele, Randbelege (Überlappung, Satzspiegel, Versatz), Titelseite (Überschneidung, Seitengrenze), Vermerk „(c) Oliver Bedernik“ auf jeder Seite und in den Metadaten, Lesezeichen. Ergebnis in `_bericht.json`, Kontaktabzug in `_kontakt.png` (Seiten mit Abbildung markiert), Nahtliste der Übergänge in `nahtliste.md`.

**Zeitstrahl:** maßstabgetreu; die Achse teilt sich nach der Spanne in Monate (bis 18 Monate), Jahre (bis 15 Jahre) oder Jahrzehnte.

## Karte, Exam und Anki

**Karte:** jeder Abschnitt ein Feld in verdichteter Form (`sicht.py`): Definition samt Normwortlaut, Kernsätze und Merkband als Kernblock, Kernliste, Tabellen, Abbildungen (Diagramm als Grafik, Zeitstrahl als Zeitleiste), Spitzmarken, Latinum; ohne Fließtext und Randbelege. Kerninhalte (`wichtig`) erscheinen als ★. Bedienung wie bisher (Ziehen, Zoomen, Register mit Suche, Minikarte, Dunkelmodus).

**Exam:** eigene `exam.json` (Standard 4.0) mit `abschnitte` je Frage; Grafik zum Sachverhalt als Abbildung wie im Werk (ohne `typ` und `id`). Regeln wie bisher: 24 bis 30 Fragen, zwei Drittel mit Sachverhalt, etwa die Hälfte Mehrfachauswahl, jede Dimension mindestens dreimal und höchstens doppelt so oft wie die seltenste.

**Anki:** Kernsätze als Lückenkarten (Fett = Lücke), Definition, Normwortlaut, Kernliste, Merke, Feinheit, Cave, Latinum, Lexicon, Kontrollfragen, Tabellen, Abbildungen; Unterdecks je Kapitel, Schlagwörter `Provinz::`, `Abschnitt::`, `Relevanz::`, `Art::`. Die Exam-Auswertung erzeugt den Suchbegriff für die Abschnitte falsch beantworteter Fragen.

## Umsetzung von Werken 3.x

`umsetzen.py` überführt Provinz → Kapitel, Kachel → Abschnitt (Codes bleiben), Bausteine in ihre 4.0-Form (Normwortlaut → Zitat, Kernfakten → Kernsätze, Merkhilfe → Merke, Beispiel → Fallbeispiel, Schemata → Tabelle oder Abbildung, Fluss → Diagramm), Kachelquellen → Randbeleg am ersten Textbaustein (Quellen erhalten bei Bedarf eine Sigle), Selbsttest → Kontrollfragen, Provinz L → Repetitorium mit eigenen Abschnitten. Was ein Mensch entscheiden muss (Einleitungen, Kerninhalte, Lösungen der Fallbeispiele, Überleitungen), steht in der Nacharbeitsliste. Ein umgesetztes Werk ist schemagültig, aber erst nach der Redaktion ein Buch.

## Freie SVG-Diagramme

Keine festen Farben; nur die Klassen `t-flaeche`, `t-akzent`, `t-linie`, `t-text`, `t-klein`. Pflicht: `viewBox` und `beschreibung`. Skripte und Event-Handler sind verboten.

## Rechenprobe

Ein Rechenweg kann eine `probe` tragen; das Kit rechnet jede Zeile dezimal exakt nach (34 Stellen, kaufmännische Rundung) und meldet jede Abweichung als Fehler. Erlaubt sind `+ − · / ** ^`, Klammern und `wurzel`, `ln`, `exp`, `log10`, `abs`, `min`, `max`, `runden(x, n)`. Nennt die `quelle` ein anderes Endergebnis, ergänzt das Kit die Quellenkritik automatisch. **Grenze:** Die Probe prüft die Rechnung, nicht ob die Ausgangswerte zur Aufgabe passen.

## Quellen

Jede Quelle hat ein **Kurzzitat** (`kurz`) und eine **Gattung** (literatur, beitrag, kommentar, aufsatz, lv, daten, online, norm, entscheidung, materialien) mit Pflichtangaben, oder eine Vollangabe (`voll`). Randbelege nennen die Quelle über ihre **Sigle** (`sigle`, sonst `kurz`, wenn es nur aus Buchstaben und Ziffern besteht); am Rand steht `rand` (höchstens 14 Zeichen), sonst `kurz`. Der Validator prüft: Kurzzitate und Siglen eindeutig, Pflichtangaben, jede Quelle belegt (Randbeleg, Abschnittsquelle oder Quellenkritik).

## Versionierung

Jede freigegebene Fassung erhält einen Git-Tag (`v4.0.0` …), ein Release mit ZIP als Rückfallebene und den Abschnitt der Version aus diesem Änderungsprotokoll. `versionspruefung.py` meldet neuere Fassungen.

## Änderungen

**4.0.0** (November 2026) „Buchsatz“

- **Datenstandard 4.0:** Kapitel mit Abschnitten und Bausteinen statt Provinzen mit Kacheln; Fließtext, Randbelege, Einleitungen, Kapitelabschluss, Kontrollfragen, Farbschlüssel (Rollen), Personen; Kerninhalte über `wichtig` statt Relevanzmarken. Codes bleiben stabil (A1 …).
- **Lernskript im Buchsatz** (`skript.py`, bisher Entwurf `buch.py`): Paged.js mit Korrekturläufen, Randbelege statt Fußnoten, Titelseite „band-relief“ (Relief im Papier, Provinzregister ohne Überschneidung), Register, Lesezeichen; Kachelsatz (Seitenmontage) für das Lernskript abgelöst.
- **Neu im Buchsatz:** Formel, Rechenweg mit Rechenprobe, Kurve, T-Konto, Organigramm, freies SVG, Rasterbild, Zeitleiste; Zeitstrahl mit Achse in Monaten, Jahren oder Jahrzehnten; lange Tabellen über die Seite mit wiederholtem Kopf; Akteure mit eigenem Tabellenkopf; Zitierweise nach Zitierstil; Fundstellen nach AZR (Jahr/Nummer) im Register der Gesetzblätter.
- **Satz:** Anriss-Korrektur je Kapitel im selben Lauf (bis 24 Läufe); Randbelege weichen vor Hindernissen auch nach oben aus; kleine Quellengruppen bleiben mit ihrer Überschrift beisammen; viel belegte Quellen kapitelweise; Registergruppen über Spaltenhöhe werden geteilt; Rechenwege von der Blocksatzprüfung ausgenommen.
- **validate.py 4.0:** Schema, Typografie, Kapitel und Codes, Bausteine, Quellen mit Siglen, Satzregeln des Buchsatzes, Formeln, Abdeckung des Referenzwerks; Probesatz (Auszug) zulässig; Exam mit `abschnitte`.
- **Kachelsicht** (`sicht.py`) für Karte, Exam und Anki; Anki-Schlagwort `Abschnitt::` (Exam-Brücke angepasst).
- **Umsetzer** `umsetzen.py` für Werke und Exams 3.x; Prüfliste mit Randbelegen und Kapiteleinleitungen; Diff mit Einleitungen und Kontrollfragen.
- **Referenzwerke:** Terra Exemplaris 4.0 (Abdeckung aller Bausteine und Sonderfälle) und Terra Historica Constitutionalis 2.0 als ganzes Werk; Referenzexam angepasst (Silvesterpatent, Pillersdorfsche Verfassung, Auflösung des Reichstages nach der Quellenkritik).
- **Testreihen neu:** `tests/run_tests.py` für 4.0, `tests/buch_test.py` am Auszug der Historica; Workflow führt beide aus.

**3.7.1** (November 2026) „Ohne Diagonale“

- Diagonales Wasserzeichen entfernt: im Lernskript (Seitenüberlagerung), in Karte und Exam (Hintergrundmuster). Der Vermerk „(c) Oliver Bedernik“ steht weiterhin in Fußzeile jeder Seite, auf der Titelseite, in jeder Grafik, im Impressum, in den PDF-Metadaten und als Signet in Karte und Exam; die PDF-Prüfung „Wasserzeichen auf jeder Seite“ bleibt scharf.
- Neuer Test: kein diagonales Wasserzeichen, Vermerk auf jeder Seite (123 Tests).

**3.7.0** (November 2026) „Gewichtung, Tabellen, Format“
- Kernfakten (ein bis drei je Kachel) und Merkhilfe: Kernsatz am Kachelanfang, Anki-Lückenkarten, Abschnitt L·K im Repetitorium, Kernfakten der Provinz im Rest der letzten Provinzseite, Hinweis auf nicht abgefragte Kernfakten.
- Tabellenreform: mehr Luft, Spaltenrollen (Begriffsspalte halbfett und nie getrennt), Übersicht als Begriffsliste, Vergleich gestürzt, Aussage unter der Tabelle (bei Teilung nur unter dem letzten Teil).
- Formatreform: Gerüstwörter leise, Feinheit ohne Fläche, Latinum als Leiste.
- Umbruch weicher zugunsten des Seitenbilds: Zuschlag unter 75 %, Teilung nach Bindung gewichtet, Kleinrest und Anriss stärker gesperrt (1000); Kurven bis 115 %, wo Platz bleibt; Verursacher schwacher Seiten im Bericht.
- Referenzwerk 0.4 (A1, B1, B4, L1, L3). Testreihe 122 Tests.
- Ergebnis an Terra Concurrentiae v1.1 (ohne Kernfakten, unverändertes Werk): 62 Seiten, Füllstand 83 %, eine übrige Seite unter 75 % (74 %), 16 Fortsetzungen, 0 Kleinreste, 0 Anrisse, 0 Fehler, 0 Warnungen.

**3.6.0** (Oktober 2026) „Satzspiegel und Umbruch“
- Globaler Seitenumbruch für Inhaltsseiten (`vorlage/umbruch.js`): Messsäule, Planung mit geringsten Gesamtkosten, Satz nach Plan, Korrektur bei Messabweichung, Rückfallebene gierig mit Warnung; deterministisch. Gewichte fest im Code, begründet. Schalter `--umbruch gierig` zur Fehlersuche.
- Abbildungen atmen zwischen 75 % und 100 %: Kurven über die Plothöhe bei gleicher Schrift, übrige über die Skala mit Mindestschrift 6,5 pt.
- Generierte Abschnitte teilbar: Klausurfallen und Selbsttest als Tabellen mit wiederholtem Kopf (zuvor Überlauf bei vielen Einträgen); Kachelverweise mit Seitenzahl.
- Randspalt beseitigt: Ursache war eine überlange URL im Quellenverzeichnis, über die Chromium alle Seiten verkleinerte, dazu die Seitenhöhe von 296,6 mm. URLs brechen jetzt um; Seitenhintergrund reicht bis an die Blattkante. Neue Prüfungen: Überstand nach rechts, reinweiße Blattkante.
- Prüfungsbogen (`exam.py --pdf`) nutzt denselben Umbruch.
- Notverkleinerung bei Abbildungen fester Höhe (`hoehe_mm`) wirkt jetzt (bis 3.5 blieb die Höhe unverändert).
- Bericht und Konsole: Fortsetzungen, Kleinreste, Anrisse, Leerraum je Seite, Skala und kleinste Schrift je Abbildung, Korrekturen, Planungsdauer, Front (Teilungsstrafe gegen Seiten und Füllstand); Hinweis auf Kacheln, die höher als eine Seite sind, und auf Grafikschrift unter 6,5 pt.
- Messskript `tests/umbruch_messung.py`. Testreihe 109 Tests.
- Ergebnis an Terra Concurrentiae v1.1: 61 Seiten (wie 3.5 nach Behebung des Überlaufs), Fortsetzungen 26 auf 10, Kleinreste 4 auf 0, Anrisse 10 auf 0, Füllstand 80,9 %, 0 Fehler, 0 Warnungen.

**3.5.0** (Oktober 2026)
- Organigramm (`baum`): Layout vom Kit, Richtung unten oder rechts, Kantenlabel, Knoten betont oder neben; Silbentrennung im Kasten.
- Rasterbild (`bild`): verknüpft oder eingebettet, Pflicht zu Quelle, Lizenz und Alternativtext; Prüfung von Format, Größe, Auflösung und Lizenz; Bildnachweis unter dem Bild. Neues Werkzeug `bild.py --einbetten`.
- Kurvenmarkierungen mit Hilfslinien.
- Rechenprobe (`rechenprobe.py`): dezimal exakt, ohne `eval`; Abweichung ist ein Fehler; abweichende Quelle ergänzt die Quellenkritik automatisch; Vermerk „✓ nachgerechnet“.
- Abbildungen nummeriert; Abbildungsverzeichnis ab drei Abbildungen, mit Lesezeichen je Abbildung; Marke „Abb“ im Kontaktabzug; PDF-Prüfung, ob jedes Rasterbild im PDF steckt.
- Wasserzeichen in jeder vom Kit gesetzten Grafik; in Anki in eigenen Rasterbildern eingebrannt, fremde Bilder unverändert.
- Exam: Grafik zum Sachverhalt; Referenzexam q11 mit Organigramm.
- Prüfliste: Rechnungen mit Stand der Probe und Ausgangswerten, Bildrechte.
- Symbolschrift deckt ∞ ≈ ≠ ≤ ≥ ab (zuvor Ersatzschrift).
- Workflow auf Node 24 (`checkout@v6`, `setup-python@v6`, `setup-node@v6`); Referenzexam wird mitgesetzt. `einrichten.sh` prüft vorab poppler-utils und DejaVu Sans und installiert sie bei Bedarf (`apt-get update` inbegriffen).
- Referenzwerk 0.3: A6 und B4 (Organigramme), L4 (Prüfbild), Rechenprobe in B1 und B4, Markierung in B1. Testreihe 96 Tests.

**3.4.0** (Oktober 2026)
- Querverweise im Lernskript tragen die Seitenzahl („D3, S 17“), beide Teile anklickbar; Karte, Exam und Anki bleiben ohne Seitenzahl.
- Lesezeichenleiste neu aus der Montage: Provinzen mit Code, jede Kachel als „D7 Titel“, generierte Abschnitte des Repetitoriums, Anhang. Zuvor leitete Chromium sie aus Überschriften ab (ohne Codes, mit Fehlern wie „IWeitere Quellen“). Fehlende Sprungziele meldet der Renderer als Fehler.
- Sachregister am Ende: Begriffe aus Lexicon und Latinum mit allen Fundstellen, in juristischen Domänen dazu ein Normenregister nach Gesetz und numerisch geordnet; doppelte Seiten entfallen, alle Zahlen anklickbar.
- Exam: Die Auswertung erzeugt einen Anki-Suchbegriff für die Kacheln aller falsch beantworteten Fragen, mit Kopierknopf.
- Workflow: Release ohne Kommandozeile über Actions → Prüfung → „Run workflow“; Beschreibung kommt aus diesem Abschnitt der README; ein bereits bestehender Release wird ergänzt statt den Lauf abzubrechen.

**3.3.0** (Oktober 2026)
- Automatische Prüfung auf GitHub (`.github/workflows/pruefung.yml`): jeder Push startet die Testreihe; ein Tag `vX.Y.Z` wird nur bei grüner Testreihe und passender Datei `VERSION` zum Release, samt ZIP für die Rückfallebene.
- Versionswarnung: `einrichten.sh` meldet eine neuere freigegebene Version (über die Release-Weiterleitung, nicht die ratenbegrenzte API).
- Version zentral in der Datei `VERSION`; zuvor meldete der Validator 3.1.3 in Kit 3.2.0.
- `pruefliste.py`: Normzitate, Rechtsprechung, Daten, Zahlen und Auflagen je Kachel als Tabelle.
- `diff.py`: Diff-Bericht zwischen zwei Fassungen, auf Wunsch als Eintrag im Änderungsprotokoll.
- Validator: Warnung, wenn der letzte Protokolleintrag nicht zur Werkversion passt; Exam-Warnung bei unausgewogenen Prüfdimensionen (mehr als das Doppelte der seltensten).
- `einrichten.sh` bricht bei Installationsfehlern mit sichtbarer Meldung ab statt stumm.
- Referenzexam: Frage q6 auf den Legitimationstyp geschärft (Ausgewogenheit).

**3.2.0** (Oktober 2026)
- Quellenverzeichnis neu: Legende, Gliederung nach Gattungen mit römischen Ziffern, drei Spalten (Kurzzitat, Vollangabe, verwendet in) mit Kachelchips in Provinzfarbe, Schluss mit Grundlagen, Quellenkritik und Stand.
- Strukturierte Quellen mit Zitierform nach AZR oder APA 7; Verwendungsnachweis über `kachel.quellen`; Validatorregeln dazu. Altes Format bleibt gültig.
- Hochzahlen (⁴, ⁵ …) werden als echte Hochstellung gesetzt; vorher fehlten sie in der Auszeichnungsschrift und lösten eine Ersatzschrift aus.
- Die Infotafel der Karte zeigt die Quellen in derselben Zitierform.
- Referenzwerk Terra Exemplaris auf strukturierte Quellen umgestellt; Terra Historica bleibt bewusst im alten Format (Prüfung der Abwärtskompatibilität).
- Einrichtung meldet „Terra-Kit bereit“ nur, wenn alle Tests bestanden sind.

**3.1.2** (Oktober 2026)
- Impressum (Seite 2) entschlackt: nur noch Werkzeile mit Literaturkapitel, Haftungshinweis, **Zitiervorschlag** (Bezeichnung fett), Verweis auf das Quellenverzeichnis, Satzvermerk und Copyright.
- Neu: Quellenverzeichnis als eigene Seite am Schluss, gegliedert in Primärquellen, Sekundärquellen (je als Liste), verwendete Quellen (Tabelle) und Entstehung; im Inhaltsverzeichnis verlinkt.
- Titelseite: Kursnummern (etwa „1393“) werden aus der Lehrveranstaltungszeile entfernt.
- Titelseite: Die Registerübersicht beginnt erst unterhalb des tatsächlichen Titelblocks und teilt den Raum bis zur Fußzeile auf; bei wenig Platz einzeilige Kompaktform. Neue Prüfung: Textblöcke der Titelseite dürfen einander nicht überlagern.
- Kürzel im Quellenverzeichnis mit Versalziffern (vorher tiefgestellt wirkende Mediävalziffern).

**3.1.1** (Oktober 2026)
- Behoben: Auf Seite 2 des Lernskripts (Impressum) überlagerten sich Quellenangaben und Fußzeile. Ursache: Der obere Abstand des Mottos schlug durch den Satzspiegel nach außen durch (Margin Collapsing) und verschob den gesamten Satzspiegel um 50 mm nach unten. Der Satzspiegel ist jetzt ein eigenständiger Layoutbereich (`display: flow-root`).
- Neue Prüfung in der Seitenmontage: Lage des Satzspiegels auf jeder Seite; frei positionierte Elemente müssen im Satzspiegel und auf dem Blatt liegen. Beides hätte den Fehler sofort gemeldet.

**3.1.0** (Oktober 2026): erste freigegebene Fassung.

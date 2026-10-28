# Terra-Kit

(c) Oliver Bedernik · Alle Rechte vorbehalten.

Werkzeugsatz für Lernmaterial nach dem **Terra-Standard 3.1**. Inhalt wird ausschließlich als `werk.json` geschrieben; Karte, Lernskript, Exam und Anki-Deck werden daraus automatisch und einheitlich erzeugt.

## Prinzip

Daten statt Nachbau: Gestaltung, Seitenmontage und Prüfungen liegen im Code, nicht in der Interpretation des Schreibenden. Jedes Werk sieht gleich aus; Karte, Skript und Exam bleiben inhaltsgleich.

## Bestandteile

| Datei | Zweck | Status |
|---|---|---|
| `schema.json` | Datenmodell eines Terra-Werks | fertig |
| `validate.py` | Prüfung in vier Stufen (Struktur, Typografie, Logik samt Rechenprobe und Bildprüfung, Formeln) | fertig, 3.5.0 |
| `rechenprobe.py` | rechnet Rechenwege dezimal exakt nach (ohne `eval`), erzeugt Quellenkritik bei abweichender Quelle | neu, 3.5.0 |
| `bild.py` | bettet verknüpfte Rasterbilder in werk.json oder exam.json ein, verkleinert, entfernt EXIF | neu, 3.5.0 |
| `referenzwerk.json` | „Terra Exemplaris“: enthält jeden Baustein, jede Schemavariante, jeden Sonderfall | fertig, 0.3 |
| `referenz_historica.json` | „Terra Historica Constitutionalis“: zweites Prüfwerk mit acht Provinzen (Höchstzahl), 39 Kacheln, zweiseitigem Verzeichnis, Strukturdiagramm; zugleich erste Überführung einer Bestandskarte mit Quellenkritik | fertig, 1.0 |
| `tests/run_tests.py` | 96 Tests: Prüfwerke, Referenzexam, beide Decks, Quellen und Zitierformen, Grafik, Rechenprobe, Bildrechte; jeder eingeschleuste Fehler erkannt | fertig |
| `skript.py` | Lernskript A4 mit Seitenmontage, Umbruch- und PDF-Prüfung | fertig, 3.1.0 |
| `vorlage/skript.css` | Satzspiegel, Bausteinoptik, Druckregeln | fertig |
| `vorlage/montage.js` | Seitenmontage, Tabellenteilung, Silbentrennung, Prüfung im Browser | fertig |
| `karte.py` | interaktive Wissenslandkarte als eine selbstständige HTML-Datei zur Veröffentlichung | fertig, 3.1.0 |
| `vorlage/karte.css`, `vorlage/karte.js` | Arbeitsfläche, Gebiete, Kamera, Minikarte, Register, Dunkelmodus | fertig |
| `tests/karte_test.py` | Browsertest der Karte (Funktion, Überlappung, Mobil, Dunkelmodus) | fertig |
| `exam.py` | Prüfung: interaktiv (HTML) und mit `--pdf` als A4-Prüfungsbogen mit Lösungsteil | fertig, 3.1.0 |
| `schema_exam.json` | Datenmodell eines Exams (verweist auf die Kacheln genau eines Werks) | fertig |
| `exam_historica.json` | Referenzexam „Examen Historicum Constitutionale“: 28 Fragen, 20 Fallbeispiele, 16 Mehrfachauswahl, ein Organigramm zum Sachverhalt (q11) | fertig, 1.1 |
| `vorlage/exam.css`, `vorlage/exam.js`, `vorlage/exam_druck.css` | Oberfläche, Ablauf und Druckbild der Prüfung | fertig |
| `vorlage/farben.css` | gemeinsame Farb- und Dunkelmodusregeln für Karte und Exam | fertig |
| `tests/exam_test.py` | Browsertest des gesamten Prüfungsablaufs | fertig |
| `anki.py` | importierbares Anki-Deck (.apkg, auch AnkiDroid) mit Unterdecks je Provinz, Abbildungen und eingebetteten Schriften | fertig, 3.1.0 |

## Verwendung

```bash
pip install -r requirements.txt --break-system-packages
npm install                        # Schriften und KaTeX, fest versioniert (package.json)
python3 validate.py werk.json      # Exitcode 0 = keine Fehler
python3 validate.py werk.json --streng   # Warnungen zählen als Fehler
python3 pruefliste.py werk.json          # Prüfliste für den Advocatus diaboli (pruefliste.md)
python3 diff.py alt.json neu.json --eintragen   # Diff-Bericht, trägt ins Änderungsprotokoll ein
python3 versionspruefung.py              # neuere freigegebene Kit-Version verfügbar?
python3 tests/run_tests.py         # vor jeder Freigabe einer Kit-Version
python3 skript.py werk.json --aus ausgabe/   # Lernskript A4 (Format B)
python3 karte.py werk.json --aus ausgabe/    # Wissenslandkarte (Format A), zur Veröffentlichung
python3 validate.py exam.json werk.json      # Exam prüfen, mit Prüfungsmatrix
python3 exam.py exam.json werk.json --aus ausgabe/ --pdf   # Prüfung interaktiv und als A4-Bogen
python3 anki.py werk.json --aus ausgabe/     # Anki-Deck (.apkg)
python3 bild.py werk.json --einbetten        # verknüpfte Bilder einbetten (werk.json bleibt selbsttragend)
python3 karte.py werk.json --aus /tmp/k --lokal && python3 tests/karte_test.py /tmp/k/<datei>_karte_lokal.html
```

Freigabe einer Kit-Version nur, wenn die Testreihe vollständig besteht **und** `skript.py` für beide Prüfwerke (`referenzwerk.json`, `referenz_historica.json`) mit 0 Fehlern und 0 Warnungen endet.

**Die zwei Prüfwerke im Vergleich:** „Terra Exemplaris“ deckt die *Breite* ab (jeder Baustein, jede Schemavariante, Formeln, Querformat, überhohe Tabelle). „Terra Historica Constitutionalis“ deckt die *Größe* ab (acht Provinzen, volles Farbspektrum, mehrseitiges Inhaltsverzeichnis, Daumenregister mit acht Reitern, 38 Seiten) und dient als Muster für die Überführung bestehender Karten.

## Lernskript: Aufbau

Titelseite (Reihe, Autor, Titel, Ausgabe, Ort und Jahr, Registerübersicht) · Impressum mit Motto, Zitiervorschlag und Quellen · Inhalt (zweispaltig, Provinzblöcke in Provinzfarbe) · Zum Gebrauch (Aufbau, Anatomie einer Kachel, Bausteine des Werks) · Abkürzungen und Zitierweise (automatisch aus dem Text, ab fünf Treffern) · Provinzen · Repetitorium mit generierten Abschnitten.

**Provinzfarben** kommen aus einer festen Palette mit gleicher Helligkeit und Sättigung (OKLCH L 0,47, C ≈ 0,085); nur der Farbton wandert entlang des Farbkreises. Ohne Angabe im Werk gilt die Folge A indigo, B petrol, C moos, D bronze, E terrakotta, F wein, G pflaume, L tinte. Flächentöne: gleicher Farbton bei L 0,94, C 0,02. Alle Farben erreichen mit weißer Schrift mindestens Kontrast 6,6:1; der kleinste Farbabstand zweier Provinzen beträgt ΔE 20. Die Palette steht nur in `skript.py` (`PALETTE`), nirgends sonst.

Farbschema für Titelseite und Inhaltsverzeichnis über `meta.farbschema`: `nacht` (Standard), `bordeaux`, `tanne`, `graphit`. Die Provinzfarben bleiben davon unberührt. Reihentitel über `meta.reihe` (Standard „Lernskripten zur Prüfungsvorbereitung“), Lehrveranstaltung erscheint als Zusatzzeile unter dem Untertitel. Haftungshinweis und Zitierweise richten sich nach der Domäne.

Jede Inhaltsseite trägt einen lebenden Kolumnentitel (aktuelle Provinz) und ein **Daumenregister**: farbiger Reiter mit römischer Ziffer am rechten Rand, Position nach Provinzreihenfolge.

## Lernskript: wie die Seitenmontage arbeitet

1. `validate.py` prüft das Werk; bei Fehlern bricht der Satz ab.
2. Jede Kachel wird in atomare Einheiten zerlegt: Kachelkopf mit erstem Baustein, danach jeder weitere Baustein.
3. `montage.js` setzt die Einheiten im Druckmodus von Chromium auf feste A4-Seiten und misst nach jeder Einheit, ob sie passt.
4. Passt eine Einheit nicht: ganze Einheit auf die nächste Seite. Ist sie höher als eine Seite: Tabellen werden zwischen Zeilen geteilt (Kopf wiederholt, Vermerk „Fortsetzung“, mindestens drei Zeilen je Teil), Abbildungen bis 75 % verkleinert.
5. Breite Tabellen (`breit: true`) erhalten eine Querformatseite.
6. Silbentrennung: Trennstellen nach österreichischem Wörterbuch (pyphen, de_AT) werden als Möglichkeit gesetzt. Nach der Montage werden zuerst die Tabellenspalten eingefroren, dann alle Trennstellen auf dem endgültigen Satz gemessen (Kriterium: Zeichen davor und danach auf verschiedenen Zeilen; die Glyphenbreite täuscht bei Ligaturen wie ft, ff, fl), dann alle ungenutzten auf einmal entfernt. An echten Umbrüchen bleibt das weiche Trennzeichen stehen, wie es ISO 32000 vorsieht; PDF-Leser fügen das Wort bei Suche und Kopieren zusammen. Höhen aller Einheiten werden vorher und nachher verglichen; jede Verschiebung ist ein Fehler.
7. Danach geprüft: Überlauf je Seite, Einheiten über Seitengrenzen, Seitenzahl und Ausrichtung im PDF, Wasserzeichen auf jeder Seite, Gedankenstriche, weiche Trennzeichen im Textlayer, Schrifteinbettung, Ersatzschriften. Ergebnis in `_bericht.json`, Kontaktabzug aller Seiten in `_kontakt.png`.

Symbolschrift: Zeichen, die in den Hausschriften fehlen (▸ ◆ ★ ○ ⚠ → ✓, seit 3.5 auch ∞ ≈ ≠ ≤ ≥), kommen bewusst aus genau einer Schrift (DejaVu Sans, `/usr/share/fonts/truetype/dejavu`), nicht aus zufälligen Ersatzschriften.

## Inline-Auszeichnung in Texten

| Syntax | Wirkung |
|---|---|
| `**Text**` | fett |
| `*Text*` | kursiv |
| `==Text==` | ohne Wirkung: Textmarker seit Oktober 2026 entfernt, der Validator warnt |
| `[[D7]]` | Verweis auf Kachel im selben Werk |
| `[[ADM:D7]]` | Verweis auf Kachel einer anderen Terra (Sigle aus `meta.kurz`) |

## Freie SVG-Diagramme

Keine festen Farben. Nur diese Klassen verwenden; der Renderer färbt sie für Hell- und Dunkelmodus:

| Klasse | Element |
|---|---|
| `t-flaeche` | Standardfläche |
| `t-akzent` | hervorgehobene Fläche (Provinzfarbe) |
| `t-linie` | Linien, Pfeile, Rahmen |
| `t-text` | Beschriftung |
| `t-klein` | Nebenbeschriftung |

Pflicht: `viewBox` und `beschreibung` (Alternativtext). Skripte und Event-Handler sind verboten.

## Grafik (3.5): Organigramm, Rasterbild, Markierungen

**Organigramm** (`variante: "baum"`): Knoten mit `id`, `text` und `eltern` (fehlt nur bei der Wurzel); optional `label` (Beschriftung der Kante vom Elternknoten) und `art` (`normal`, `betont` in Provinzfarbe, `neben` gestrichelt). Das Layout berechnet das Kit: Blätter in Lesereihenfolge, Eltern mittig, rechtwinklige Verbinder. Richtung `unten` (Wurzel oben, bis sechs Blätter, bis fünf Ebenen) oder `rechts` (Wurzel links, bis 14 Blätter, bis vier Ebenen); ohne Angabe wählt das Kit nach der Zahl der Blätter. Lange Wörter werden am Bindestrich, sonst nach Silben getrennt, kein Wort ragt aus dem Kasten. In der Karte erhalten Kacheln mit Organigramm doppelte Breite. Für Instanzenzüge, Zuständigkeiten, Gliederungen eines Begriffs; Entscheidungswege bleiben beim Flussdiagramm.

**Rasterbild** (`variante: "bild"`): PNG, JPEG oder WebP, entweder verknüpft (`datei`, relativ zur werk.json) oder eingebettet (`daten`, data-URI). Pflicht: `beschreibung` (Alternativtext), `quelle`, `lizenz`; bei CC-BY-Lizenzen zusätzlich `urheber`. Optional `breite` in Prozent (30 bis 100). Geprüft werden Format, MIME-Typ, Größe (Warnung ab 1,5 MB, Fehler ab 4 MB), Auflösung auf der gesetzten Breite (Warnung unter 150 dpi, Fehler unter 96 dpi) und die Lizenz (eigenes Werk, gemeinfrei, CC, Zitat nach § 42f UrhG, freies Werk nach § 7 UrhG). Verknüpfte Bilder erzeugen eine Warnung: `python3 bild.py werk.json --einbetten` bettet sie ein, verkleinert auf höchstens 2.400 px und entfernt Metadaten (auch GPS-Ortsangaben). Unter jedem Bild steht der Bildnachweis.

**Kurvenmarkierung** (`markierungen` der Kurve, bis vier): Punkt mit gestrichelten Hilfslinien zu beiden Achsen und Beschriftung, etwa Gleichgewicht oder Rechenbeispiel.

**Abbildungen** (Kurve, Flussdiagramm, freies SVG, Organigramm, Bild) sind in Skript und Karte fortlaufend nummeriert („Abb 3“). Ab drei Abbildungen erhält das Lernskript im Anhang ein **Abbildungsverzeichnis** mit Nachweis, Kachel und Seite; die Lesezeichenleiste führt jede Abbildung einzeln. Im Kontaktabzug tragen Seiten mit Abbildungen die Marke „Abb“. Mehr als eine Abbildung je Kachel löst eine Warnung aus (Grafikdichte).

**Wasserzeichen:** Jede vom Kit gesetzte Grafik trägt „(c) Oliver Bedernik“ im Bild, unten rechts. Eigene Rasterbilder (Lizenz „eigenes Werk“) erhalten es im Anki-Deck eingebrannt. **Fremde Bilder bleiben unverändert:** Ein Urhebervermerk auf fremdem Werk wiese die Urheberschaft falsch zu und kann Lizenzbedingungen verletzen; Seite, Karte und Kartenfuß tragen das Wasserzeichen ohnehin.

**Exam:** Eine Frage mit Sachverhalt kann eine `grafik` tragen (jede Schemavariante); sie erscheint im Sachverhalt, interaktiv und im Prüfungsbogen, ohne Abbildungsnummer.

## Rechenprobe (3.5)

Ein Rechenweg kann eine `probe` tragen; das Kit rechnet jede Zeile dezimal exakt nach (34 Stellen, kaufmännische Rundung) und meldet jede Abweichung als Fehler.

```json
"probe": {
  "werte":    {"C": 10000, "i": "0.05", "n": 3},
  "rechnung": [{"name": "q",  "ausdruck": "1 + i",      "ergebnis": "1.05"},
               {"name": "PV", "ausdruck": "C / q ** n", "ergebnis": "8638.38"}],
  "stellen": 2,
  "quelle":   {"kurz": "Online-Zinsrechner (Stand 2026)", "wert": "8638.37"}
}
```

Zahlen mit Dezimalpunkt; erlaubt sind `+ − · / ** ^`, Klammern und `wurzel`, `ln`, `exp`, `log10`, `abs`, `min`, `max`, `runden(x, n)`. Benannte Zeilen stehen den folgenden ungerundet zur Verfügung. Der Ergebnistext muss den nachgerechneten Wert nennen (Warnung). Nennt die `quelle` ein anderes Endergebnis, ergänzt das Kit die Quellenkritik automatisch. Bestandene Proben tragen im Skript, in der Karte und im Deck den Vermerk „✓ nachgerechnet“. In Werken ohne Probe warnt der Validator; `pruefliste.py` führt jeden Rechenweg samt Ausgangswerten. **Grenze:** Die Probe prüft die Rechnung, nicht ob die Ausgangswerte zur Aufgabe passen; das bleibt Aufgabe des Advocatus diaboli.

## Was der Validator durchsetzt

**Fehler:** Gedankenstriche · unpaarige Auszeichnung · fehlerhafte oder tote Verweise · Rechenprobe falsch oder nicht berechenbar · Organigramm ohne genau eine Wurzel, mit Kreis, fehlendem Elternknoten oder zu breit bzw. zu tief · Bild unlesbar, im falschen Format, zu groß oder zu gering aufgelöst, CC BY ohne Urheber · Kurvenmarkierung außerhalb der Achse · Provinzcodes nicht lückenlos ab A oder L nicht zuletzt · Kachelcodes falsch, doppelt oder ungeordnet · Bausteinreihenfolge · mehr als vier gerahmte Bausteine oder fünf Textmarker je Kachel · Austriacum in der Rechtsdomäne · „auslassbar“ ohne Beleg · unvollständige Tabellenzeilen, mehr als neun Spalten · T-Konto unausgeglichen · Kurve unsortiert · Flussdiagramm mit Aufwärtskanten, unerreichbaren Knoten, unbeschrifteten Antworten · SVG mit festen Farben oder Skript · nicht setzbare Formeln · im Referenzwerk jede fehlende Abdeckung.

**Warnungen:** Rechenweg ohne Probe · Ergebnistext ohne nachgerechneten Wert · Bild verknüpft statt eingebettet, groß, unscharf oder mit unbekannter Lizenz · mehr als eine Abbildung je Kachel · Bindestrich als Gedankenstrich · gerade Anführungszeichen · „§7“ ohne Abstand · „Art.“ und „Abs.“ mit Punkt · Rechtsprechung ohne Geschäftszahl · fehlende Seitenangabe · überlange Titel · mehr als drei Viertel Kernstoff · doppelte Latinismen · zu wenige Selbsttestfragen.

## Versionierung

Jede freigegebene Fassung erhält einen Git-Tag (`v3.1`, `v3.2` …). Die Projektanweisungen verweisen auf genau einen Tag. Freigabe nur, wenn `tests/run_tests.py` vollständig besteht.

## Wissenslandkarte: wie sie arbeitet

Satz der Kacheln, Diagramme und Tabellen kommt unverändert aus `skript.py`; Karte und Skript sind dadurch nicht nur inhalts-, sondern auch satzgleich. Formeln erscheinen als MathML (veröffentlichte Seiten dürfen keine fremden Schriftdateien laden); Schriften über Google Fonts. Die Silbentrennung übernimmt der Browser (`hyphens: auto`, `lang="de-AT"`).

Jede Provinz ist ein Gebiet; ihre Kacheln werden als Mauerwerk gesetzt, breite Tabellen erhalten doppelte Breite. Die Gebiete werden in gleichmäßig gefüllten Reihen angeordnet, und zwar so, dass die ganze Karte beim Einpassen den größten Maßstab erreicht. Aus der Ferne erscheinen die Provinznamen als Landesnamen in fester Bildschirmgröße.

Bedienung: Ziehen, Mausrad, Trackpad, Zwei-Finger-Geste, Tastatur (+, −, 0, /, Pfeile, Esc); Provinzleiste; Minikarte; Register mit Volltextsuche; Filter „Kernstoff“; anklickbare Querverweise mit Adresse (`#k-D7`); Darstellung Automatisch, Hell, Dunkel; letzte Ansicht wird im Browser gespeichert. Wasserzeichen als diagonales Muster im Hintergrund und als Signet.

## Exam: wie es arbeitet

Fragen werden nicht gesetzt, sondern geschrieben: Jedes Exam ist eine eigene `exam.json`, die auf die Kacheln genau eines Werks verweist. Der Validator setzt den Exam-Standard durch: 24 bis 30 Fragen, mindestens zwei Drittel mit Sachverhalt, etwa die Hälfte Mehrfachauswahl, je vier Optionen mit eigener Begründung, jede Provinz (außer L) mindestens zweimal, jede Prüfdimension des Domänenmoduls mindestens dreimal; er gibt die Prüfungsmatrix aus.

Interaktiv: Startseite mit Eckdaten, Regeln, Zeitlimit (abschaltbar, automatische Abgabe) und Modus Durum; Fortschrittsbalken, Uhr, Navigation, Markieren, Übersichtsraster, Abgabe mit Hinweis auf Offenes; Fortschritt im Browser gespeichert. Auswertung mit lateinischem Urteil (Summa cum laude ab 90 %, Magna cum laude ab 80 %, Cum laude ab 70 %, Rite ab 60 %, sonst Non sufficit), Ergebnis je Provinz und Durchsicht mit Filter „nur falsche“; jede Option als richtig gewählt, falsch gewählt oder richtig, aber nicht gewählt gekennzeichnet, mit Begründung, Fundstelle und Verweis auf die Kachel der Karte.

A4-Bogen: Deckblatt mit Namensfeld, Fragen in Seitenmontage (nie geteilt), Lösungsteil auf neuer Seite.

## Anki: wie es arbeitet

Je Baustein eine oder mehrere Karten: Definition (Fallbeispiel nur zur Veranschaulichung auf der Rückseite), Kernpunkte als Stichpunktliste, Merke, Feinheit, Klausurfalle, Österreichbezug, Aktualisierung, Normwortlaut, Latinum und Lexicon, Formel (MathJax) und Rechenweg, Zeitleiste (Datum → Ereignis), Tabelle (je Zeile), Abgrenzung (je Kriterium), Abbildungen als Bild, Provinz (Leitfrage → In 60 Sekunden), Selbsttest und Quellenkritik.

Unterdecks je Provinz unter `Terra::<Werk>`; Schlagwörter `Provinz::`, `Kachel::`, `Relevanz::`, `Art::` (etwa nur Kernstoff lernen: Suche `tag:Relevanz::kern`). Die Kennung jeder Notiz ergibt sich aus Werk-Sigle und Baustein; ein erneuter Import nach einer Korrektur aktualisiert die Karten und erhält den Lernfortschritt. Hausschriften sind eingebettet; Dunkelmodus von Anki und AnkiDroid wird unterstützt. Kartenfuß mit „(c) Oliver Bedernik“, Werk und Fundstelle.

## Quellen: wie sie erfasst werden

Jede Quelle hat ein **Kurzzitat** (`kurz`), unter dem sie im Werk angeführt wird, und eine **Gattung**. Das Kit setzt daraus die Vollangabe im Zitierstil des Moduls: **AZR** (österreichische Rechtssprache) in den Domänen recht und gemischt, sonst **APA 7** (Autor-Jahr); abweichend über `modul.zitierstil`. Jede Kachel nennt in `quellen` die Kurzzitate, auf die sie sich stützt; daraus entsteht die Spalte „Verwendet in“.

| Gattung | Pflichtangaben | weitere Felder |
|---|---|---|
| literatur | titel, jahr; autoren oder hrsg oder institution | untertitel, auflage, ort, verlag, zusatz |
| beitrag | autoren, titel, in (Sammelwerk), jahr | hrsg, auflage, seiten |
| kommentar | autoren, hrsg, in (Werk), fundstelle (§§), jahr | auflage |
| aufsatz | autoren, titel, in (Zeitschrift), jahr | band, heft, seiten |
| lv | titel, jahr; autoren oder institution | art (etwa Foliensatz) |
| daten | titel, jahr, abruf; autoren oder institution | art, url |
| online | titel, abruf; url oder institution | jahr |
| norm | abk, titel, fundstelle | zusatz |
| entscheidung | gericht, datum (JJJJ-MM-TT), gz | name, slg, ecli |
| materialien | titel, fundstelle | zusatz |

Namen als „Nachname, Vorname“; Körperschaften ohne Komma. Für AZR mit Initiale (etwa „F. Bydlinski“) „Bydlinski, F.“ angeben. Hochzahlen wie „ABGB⁴“ dürfen als Unicode-Zeichen geschrieben werden; das Kit setzt sie als echte Hochstellung. Das alte Format (`kurz` und `voll`) bleibt gültig, erscheint unter „Weitere Quellen“ und erzeugt einen Hinweis.

Der Validator prüft: Kurzzitate eindeutig, Pflichtangaben je Gattung, jede zitierte Quelle verzeichnet, jede strukturierte Quelle von mindestens einer Kachel zitiert.

## Änderungen

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

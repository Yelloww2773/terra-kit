#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit · Testreihe für validate.py

Jeder Test beschädigt eine Kopie des Referenzwerks gezielt und prüft, ob der
Validator genau diesen Fehler meldet. Zusätzlich muss das unveränderte
Referenzwerk fehlerfrei sein. Vor jeder Freigabe einer Kit-Version ausführen:

    python3 tests/run_tests.py
"""
import copy
import json
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
from validate import validiere  # noqa: E402

STRICHE_TEST = ("\u2012", "\u2013", "\u2014", "\u2015")
BASIS = json.loads((KIT / "referenzwerk.json").read_text(encoding="utf-8"))


def kachel(w, code):
    for p in w["provinzen"]:
        for k in p["kacheln"]:
            if k["code"] == code:
                return k
    raise KeyError(code)


def baustein(w, code, typ, variante=None):
    for b in kachel(w, code)["bausteine"]:
        if b["typ"] == typ and (variante is None or b.get("variante") == variante):
            return b
    raise KeyError((code, typ, variante))


# (Name, Mutation, erwartete Meldung, Stufe F = Fehler / W = Warnung)
TESTS = [
    ("Geviertstrich", lambda w: baustein(w, "A1", "definition").__setitem__("text", "Text \u2014 mit Strich."), "Geviertstrich", "F"),
    ("Halbgeviertstrich", lambda w: kachel(w, "B1").__setitem__("titel", "Barwert \u2013 Grundlagen"), "Halbgeviertstrich", "F"),
    ("Bindestrich als Gedankenstrich", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "Das gilt - meistens."), "Bindestrich als Gedankenstrich", "W"),
    ("gerade Anführungszeichen", lambda w: baustein(w, "B2", "merke").__setitem__("text", 'Der "Kunde" zahlt.'), "gerades Anführungszeichen", "W"),
    ("Fettung offen", lambda w: baustein(w, "A2", "klausurfalle").__setitem__("text", "Nur **zulasten des Täters."), "unpaariges **", "F"),
    ("Marker offen", lambda w: baustein(w, "B2", "merke").__setitem__("text", "Die ==Vorsteuer ist eine Forderung."), "unpaariges ==", "F"),
    ("§ ohne Leerzeichen", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "Siehe §7 ABGB."), "§ ohne Leerzeichen", "W"),
    ("Art mit Punkt", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "Siehe Art. 7 EMRK."), "ohne Punkt", "W"),
    ("Rsp ohne GZ", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "So entschied der OGH."), "keine Geschäftszahl", "W"),
    ("toter Verweis", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "Siehe [[A9]]."), "zeigt auf keine Kachel", "F"),
    ("kaputter Verweis", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "Siehe [[a1]]."), "fehlerhaft", "F"),
    ("Kachelcode falsche Provinz", lambda w: kachel(w, "B3").__setitem__("code", "A6"), "passt nicht zu Provinz", "F"),
    ("Kachelcode doppelt", lambda w: kachel(w, "A4").__setitem__("code", "A3"), "doppelt vergeben", "F"),
    ("L nicht zuletzt", lambda w: w["provinzen"].reverse(), "Code L", "F"),
    ("Reihenfolge", lambda w: kachel(w, "A1")["bausteine"].reverse(), "Bausteinreihenfolge", "F"),
    ("zu viele Rahmen", lambda w: kachel(w, "B1")["bausteine"].append({"typ": "luecke", "text": "x", "grund": "y"}), "gerahmte Bausteine", "F"),
    ("Textmarker ohne Wirkung", lambda w: baustein(w, "A1", "kern")["punkte"].append("==a=="), "ohne Wirkung", "W"),
    ("Austriacum in Recht", lambda w: w["modul"].__setitem__("domaene", "recht"), "Austriacum in der Rechtsdomäne", "F"),
    ("auslassbar ohne Beleg", lambda w: kachel(w, "A5").pop("beleg_auslassbar"), "beleg_auslassbar", "F"),
    ("unbekanntes Feld", lambda w: baustein(w, "A1", "definition").__setitem__("txt", "Tippfehler"), "'txt' was unexpected", "F"),
    ("unbekannter Bausteintyp", lambda w: kachel(w, "A1")["bausteine"].append({"typ": "notiz", "text": "x"}), "is not one of", "F"),
    ("T-Konto unausgeglichen", lambda w: baustein(w, "B2", "schema", "tkonto")["konten"][0]["soll"][0].__setitem__("betrag", 999), "≠ Haben", "F"),
    ("Tabellenzeile kurz", lambda w: baustein(w, "L3", "schema", "tabelle")["zeilen"][0].pop(), "Zellen, Kopf hat", "F"),
    ("Kurve unsortiert", lambda w: baustein(w, "B1", "schema", "kurve")["reihen"][0]["punkte"].reverse(), "nicht streng aufsteigend", "F"),
    ("Fluss Aufwärtskante", lambda w: baustein(w, "A2", "schema", "fluss")["kanten"].append({"von": "e4", "nach": "f1"}), "nicht abwärts", "F"),
    ("Fluss unerreichbar", lambda w: baustein(w, "A2", "schema", "fluss")["kanten"].pop(), "nicht erreichbar", "F"),
    ("Fluss Frage ohne Label", lambda w: baustein(w, "A2", "schema", "fluss")["kanten"][1].pop("label"), "ohne Beschriftung", "F"),
    ("SVG feste Farbe", lambda w: baustein(w, "A5", "schema", "svg").__setitem__("svg", baustein(w, "A5", "schema", "svg")["svg"].replace('class="t-akzent"', 'fill="#c00"')), "fester Farbe", "F"),
    ("SVG ohne Beschreibung", lambda w: baustein(w, "A5", "schema", "svg").pop("beschreibung"), "beschreibung", "F"),
    ("Formel kaputt", lambda w: baustein(w, "B1", "formel").__setitem__("tex", "PV = \\frac{C_n}{"), "Formel nicht setzbar", "F"),
    ("Selbsttest auf fehlende Kachel", lambda w: w["selbsttest"][0].__setitem__("kachel", "C1"), "existiert nicht", "F"),
    ("Abdeckung SVG fehlt", lambda w: kachel(w, "A5")["bausteine"].pop(1), "Schemavariante „svg“ fehlt", "F"),
    ("VfGH als Institution ohne Warnung", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "Der VfGH ist das Hüter der Verfassung."), "__keine__", "N"),
    ("Protokoll hinkt nach", lambda w: w["meta"].__setitem__("version", "9.9"), "letzter Eintrag gilt Version", "W"),
    ("Urheber verändert", lambda w: w["meta"].__setitem__("urheber", "anonym"), "(c) Oliver Bedernik", "F"),
    # 3.5: Organigramm, Rasterbild, Kurvenmarkierung, Rechenprobe, Grafikdichte
    ("Baum: Elternknoten fehlt", lambda w: baustein(w, "A6", "schema", "baum")["knoten"][3].__setitem__("eltern", "x"), "Elternknoten „x“ fehlt", "F"),
    ("Baum: zwei Wurzeln", lambda w: baustein(w, "A6", "schema", "baum")["knoten"][1].pop("eltern"), "2 Wurzeln", "F"),
    ("Baum: Kreis", lambda w: baustein(w, "A6", "schema", "baum")["knoten"][0].__setitem__("eltern", "a1"), "Wurzeln", "F"),
    ("Baum: zu breit nach unten", lambda w: (baustein(w, "A6", "schema", "baum").__setitem__("richtung", "unten"),
        baustein(w, "A6", "schema", "baum")["knoten"].append({"id": "l3", "text": "teleologische Reduktion", "eltern": "l"})), "trägt höchstens 6", "F"),
    ("Baum: zu tief nach rechts", lambda w: baustein(w, "B4", "schema", "baum")["knoten"].append({"id": "x", "text": "x", "eltern": "s"}), "trägt höchstens 4", "F"),
    ("Bild ohne Lizenz", lambda w: baustein(w, "L4", "schema", "bild").pop("lizenz"), "'lizenz' is a required property", "F"),
    ("Bild mit unbekannter Lizenz", lambda w: baustein(w, "L4", "schema", "bild").__setitem__("lizenz", "aus dem Internet"), "nicht erkannt", "W"),
    ("CC BY ohne Urheber", lambda w: baustein(w, "L4", "schema", "bild").__setitem__("lizenz", "CC BY 4.0"), "Namensnennung", "F"),
    ("Bild mit falschem MIME-Typ", lambda w: baustein(w, "L4", "schema", "bild").__setitem__("daten", baustein(w, "L4", "schema", "bild")["daten"].replace("image/jpeg", "image/png", 1)), "angegeben als image/png", "F"),
    ("Bild zu gering aufgelöst", lambda w: baustein(w, "L4", "schema", "bild").__setitem__("daten", _kleinbild(300)), "Auflösung", "F"),
    ("Bild datei und daten zugleich", lambda w: baustein(w, "L4", "schema", "bild").__setitem__("datei", "a.png"), "genau eines der Felder", "F"),
    ("Markierung außerhalb der Achse", lambda w: baustein(w, "B1", "schema", "kurve")["markierungen"][0].__setitem__("x", 20), "außerhalb der x-Achse", "F"),
    ("Rechenprobe: falsches Ergebnis", lambda w: baustein(w, "B1", "rechenweg")["probe"]["rechnung"][2].__setitem__("ergebnis", "8638.39"), "Rechenprobe Zeile 3", "F"),
    ("Rechenprobe: unbekannte Größe", lambda w: baustein(w, "B1", "rechenweg")["probe"]["rechnung"][2].__setitem__("ausdruck", "C / g"), "unbekannte Größe „g“", "F"),
    ("Rechenprobe: Ergebnistext ohne Wert", lambda w: baustein(w, "B1", "rechenweg").__setitem__("ergebnis", "rund 8.600 €"), "nennt den nachgerechneten Wert", "W"),
    ("Rechenprobe: Python statt Rechnung", lambda w: baustein(w, "B1", "rechenweg")["probe"]["rechnung"][0].__setitem__("ausdruck", "__import__('os')"), "nicht erlaubt", "F"),
    ("Grafikdichte", lambda w: kachel(w, "A6")["bausteine"].insert(2, copy.deepcopy(baustein(w, "A5", "schema", "svg"))), "Grafikdichte", "W"),
    # 3.7: Tabellenfelder, Kernfakten, Prüfpflicht, Abdeckung
    ("Tabelle: Spaltenrollen passen nicht", lambda w: baustein(w, "L3", "schema", "tabelle").__setitem__("spalten", ["begriff", "text"]), "Spaltenrollen für 3 Spalten", "F"),
    ("Kernfakten: mehr als drei", lambda w: kachel(w, "A1").__setitem__("kernfakten", ["Ein Satz."] * 4), "is too long", "F"),
    ("Kernfakten ohne Selbsttest", lambda w: w.__setitem__("selbsttest", [s for s in w["selbsttest"] if s["kachel"] != "B1"]), "nicht im Selbsttest abgefragt: B1", "H"),
    ("Tabelle ohne Aussage", lambda w: baustein(w, "L3", "schema", "tabelle").pop("aussage"), "ohne Aussage", "H"),
    ("Abdeckung Übersichtstabelle fehlt", lambda w: baustein(w, "L1", "schema", "tabelle").__setitem__("art", "tabelle"), "keine Tabelle der Art „uebersicht“", "F"),
    ("Abdeckung Rechenprobe fehlt", lambda w: [baustein(w, c, "rechenweg").pop("probe") for c in ("B1", "B4")], "kein Rechenweg mit Rechenprobe", "F"),
]


def _kleinbild(breite):
    import base64, io
    from PIL import Image
    puffer = io.BytesIO()
    Image.new("RGB", (breite, breite // 2), (200, 190, 170)).save(puffer, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(puffer.getvalue()).decode()


def main():
    fehlschlaege = 0
    basis = validiere(copy.deepcopy(BASIS))
    if basis.fehler or basis.warnungen:
        print("✗ Referenzwerk ist nicht sauber:")
        for z in basis.fehler + basis.warnungen:
            print("   ", z)
        fehlschlaege += 1
    else:
        print("✓ Referenzwerk: 0 Fehler, 0 Warnungen")
    # Zweites Referenzwerk: acht Provinzen, mehrseitiges Verzeichnis, Bestandsüberführung
    hic = validiere(json.loads((KIT / "referenz_historica.json").read_text(encoding="utf-8")))
    if hic.fehler or hic.warnungen:
        print("✗ Referenz Historica ist nicht sauber:")
        for z in hic.fehler + hic.warnungen:
            print("   ", z)
        fehlschlaege += 1
    else:
        print("✓ Referenz Historica (8 Provinzen, 39 Kacheln): 0 Fehler, 0 Warnungen")

    for name, mutation, erwartet, stufe in TESTS:
        w = copy.deepcopy(BASIS)
        mutation(w)
        b = validiere(w)
        if stufe == "N":
            ok = not any("Geschäftszahl" in z for z in b.warnungen)
            print(("✓ " if ok else "✗ ") + name)
            fehlschlaege += 0 if ok else 1
            continue
        zeilen = {"F": b.fehler, "W": b.warnungen, "H": b.hinweise}[stufe]
        if any(erwartet in z for z in zeilen):
            print(f"✓ {name}")
        else:
            fehlschlaege += 1
            print(f"✗ {name}: erwartet „{erwartet}“ als {dict(F='Fehler', W='Warnung', H='Hinweis')[stufe]}")
            for z in (b.fehler + b.warnungen)[:4]:
                print("     gemeldet:", z)
    # Exam: Referenzexam sauber, eingeschleuste Fehler erkannt
    from validate import validiere_exam
    hic_w = json.loads((KIT / "referenz_historica.json").read_text(encoding="utf-8"))
    ex = json.loads((KIT / "exam_historica.json").read_text(encoding="utf-8"))
    b = validiere_exam(copy.deepcopy(ex), hic_w)
    ok = not b.fehler and not b.warnungen
    print(("✓ " if ok else "✗ ") + "Referenzexam: 0 Fehler, 0 Warnungen"); fehlschlaege += 0 if ok else 1
    EXAMTESTS = [
        ("Einfachauswahl mit zwei richtigen", lambda e: e["fragen"][1]["optionen"][1].__setitem__("richtig", True), "genau eine verlangt"),
        ("Kachel fehlt im Werk", lambda e: e["fragen"][0]["kacheln"].append("C9"), "existiert im Werk nicht"),
        ("Fallquote zu niedrig", lambda e: [f.pop("sachverhalt", None) for f in e["fragen"][:12]], "mindestens zwei Drittel"),
        ("Provinz unterabgedeckt", lambda e: [f.__setitem__("provinz", "D") for f in e["fragen"] if f["provinz"] == "F"], "Provinz F nur 0-mal"),
        ("Dimension unbekannt", lambda e: e["fragen"][0].__setitem__("dimension", "Bauchgefühl"), "nicht im Domänenmodul"),
        ("Gedankenstrich im Exam", lambda e: e["fragen"][0].__setitem__("frage", "Welche \u2014 Aussagen?"), "Gedankenstrich"),
        ("Grafik ohne Sachverhalt", lambda e: e["fragen"][10].pop("sachverhalt"), "Grafik ohne Sachverhalt"),
        ("Grafik fehlerhaft", lambda e: e["fragen"][10]["grafik"]["knoten"][1].__setitem__("eltern", "zz"), "Elternknoten „zz“ fehlt"),
        ("Grafik mit unbekannter Variante", lambda e: e["fragen"][10]["grafik"].__setitem__("variante", "karte"), "is not one of"),
    ]
    for name, mut, erw in EXAMTESTS:
        e = copy.deepcopy(ex); mut(e); bb = validiere_exam(e, hic_w)
        ok = any(erw in z for z in bb.fehler)
        print(("✓ " if ok else "✗ ") + "Exam: " + name); fehlschlaege += 0 if ok else 1
    # Anki: beide Prüfwerke als Deck bauen und wie Anki öffnen
    import tempfile, anki
    for datei in ("referenzwerk.json", "referenz_historica.json"):
        w = json.loads((KIT / datei).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            pfad, notizen, zaehler, bilder = anki.baue(w, Path(tmp))
            bf = anki.pruefe(pfad, notizen)
        ok = not bf["fehler"] and bf["notizen"] > 50
        print(("✓ " if ok else "✗ ") + f"Anki {datei}: {bf['notizen']} Karten, {len(bilder)} Abbildungen" + ("" if ok else f" {bf['fehler']}"))
        fehlschlaege += 0 if ok else 1
    # Quellen (3.2): Verwendungsnachweis, Pflichtfelder, Zitierformen
    import skript as SK
    from validate import validiere as _val
    ex_w = json.loads((KIT / "referenzwerk.json").read_text(encoding="utf-8"))
    def _mut(fn):
        w = copy.deepcopy(ex_w); fn(w); return _val(w)
    QTESTS = [
        ("Kachel zitiert unbekannte Quelle", lambda: _mut(lambda w: w["provinzen"][0]["kacheln"][0]["quellen"].append("Unbekannt 1999")).fehler, "im Quellenverzeichnis fehlt"),
        ("Kurzzitat doppelt", lambda: _mut(lambda w: w["quellen"].append(dict(w["quellen"][0]))).fehler, "doppelt vergeben"),
        ("Pflichtangabe fehlt", lambda: _mut(lambda w: next(q for q in w["quellen"] if q.get("gattung") == "literatur").pop("jahr")).fehler, "Pflichtangabe jahr fehlt"),
        ("Quelle von keiner Kachel zitiert", lambda: _mut(lambda w: w["quellen"].append({"kurz": "Waise 2020", "gattung": "literatur", "autoren": ["Waise, W."], "titel": "T", "jahr": "2020"})).warnungen, "von keiner Kachel zitiert"),
        ("APA: zwei Autoren mit Komma und &", lambda: [SK.zitat_text({"gattung": "literatur", "autoren": ["Fouquin, Michel", "Hugot, Jules"], "titel": "T", "jahr": "2016", "verlag": "V", "kurz": "x"}, "APA")], "Fouquin, M., & Hugot, J. (2016). T. V."),
        ("APA: Zeitschriftenaufsatz", lambda: [SK.zitat_text({"gattung": "aufsatz", "autoren": ["Markowitz, Harry"], "titel": "Portfolio selection", "in": "The Journal of Finance", "band": "7", "heft": "1", "seiten": "77 bis 91", "jahr": "1952", "kurz": "x"}, "APA")], "Markowitz, H. (1952). Portfolio selection. The Journal of Finance, 7(1), 77 bis 91."),
        ("AZR: Kommentar mit Auflage", lambda: [SK.zitat_voll({"gattung": "kommentar", "autoren": ["Kodek, Georg"], "hrsg": ["Rummel, Peter", "Lukas, Meinhard"], "in": "ABGB", "auflage": 4, "fundstelle": "§§ 6, 7", "jahr": "2015", "kurz": "x"}, "AZR")], "ABGB<sup>4</sup> §§\u00a06, 7 (2015)"),
        ("Entscheidung mit Sammlung und ECLI", lambda: [SK.zitat_text({"gattung": "entscheidung", "gericht": "EuGH", "datum": "2010-12-22", "gz": "C-208/09", "name": "Sayn-Wittgenstein", "ecli": "ECLI:EU:C:2010:806", "kurz": "x"}, "AZR")], "EuGH 22.12.2010, C-208/09, Sayn-Wittgenstein, ECLI:EU:C:2010:806"),
        ("Hochzahlen als echte Hochstellung", lambda: [SK.md("ABGB⁴")], '<sup class="hz">4</sup>'),
    ]
    for name, fn, erw in QTESTS:
        try:
            ergebnis = fn(); ok = any(erw in z for z in ergebnis)
        except Exception as ex:
            ok = False; ergebnis = [repr(ex)]
        print(("✓ " if ok else "✗ ") + "Quellen: " + name + ("" if ok else f"  → {ergebnis[:2]}")); fehlschlaege += 0 if ok else 1
    # Werkzeuge 3.3: Version, Versionswarnung, Ausgewogenheit, Prüfliste, Diff, Workflow
    import re as _re, versionspruefung as VP, pruefliste as PL, diff as DF
    hic_x = json.loads((KIT / "referenz_historica.json").read_text(encoding="utf-8"))
    ver = (KIT / "VERSION").read_text(encoding="utf-8").strip()
    def _version_einheitlich():
        import validate, exam as EX, karte as KA
        return {validate.VERSION, EX.VERSION, KA.VERSION, SK.VERSION, anki.VERSION} == {ver} and _re.fullmatch(r"\d+\.\d+\.\d+", ver)
    def _ausgewogen():
        e = copy.deepcopy(ex)
        for d in ("Kontinuität und Rezeption", "Fundstelle und Status"):
            next(f for f in e["fragen"] if f["dimension"] == d)["dimension"] = "Abgrenzung"
        return any("Ausgewogenheit" in z for z in validiere_exam(e, hic_w).warnungen)
    def _pruefliste():
        z = PL.eintraege(json.loads((KIT / "referenzwerk.json").read_text(encoding="utf-8")))
        h = PL.eintraege(hic_x)
        kat = {x["kategorie"] for x in z}
        return ({"Norm", "Zahl", "Datum", "Auflage"} <= kat and any(x["wert"] == "5 %" for x in z)
                and any(x["wert"] == "1814/15" and x["kategorie"] == "Datum" for x in h)
                and not any(x["kategorie"] == "Rechtsprechung" and x["wert"] == "1814/15" for x in h))
    def _diff():
        n = copy.deepcopy(BASIS); n["provinzen"][0]["kacheln"][0]["titel"] += " X"
        n["provinzen"][0]["kacheln"][1]["bausteine"][0]["text"] = "y"; weg = n["provinzen"][1]["kacheln"].pop()["code"]
        b = DF.vergleiche(BASIS, n); t = DF.als_text(b)
        return (b["entfernt"] == [weg] and b["umbenannt"][0][0] == "A1" and b["geaendert"][0][0] == "A2"
                and DF.als_text(DF.vergleiche(BASIS, BASIS)) == "" and not any(c in t for c in STRICHE_TEST))
    def _workflow():
        y = (KIT / ".github/workflows/pruefung.yml").read_text(encoding="utf-8")
        return "needs: testreihe" in y and "v$(cat VERSION)" in y and "run_tests.py" in y
    NEU = [
        ("Version einheitlich aus Datei VERSION", _version_einheitlich),
        ("Versionswarnung: Vergleich", lambda: [VP.bewerte("3.3.0", t)[0] for t in ("v3.4.0", "v3.3.0", "v3.2.0", "v3.3.a")] == ["veraltet", "aktuell", "neuer", "unklar"]
                                                and VP.bewerte("3.10.0", "v3.9.0")[0] == "neuer"),
        ("Exam: Ausgewogenheit gewarnt", _ausgewogen),
        ("Prüfliste: Kategorien und Jahresspannen", _pruefliste),
        ("Diff: neu, entfernt, umbenannt, geändert", _diff),
        ("Workflow: Release nur nach grüner Testreihe", _workflow),
    ]
    # Bedienung am Bildschirm (3.4)
    import exam as EXM
    def _seitenverweis():
        ohne = SK.md("Siehe [[A1]].")
        SK.SEITENVERWEIS = True
        try:
            mit = SK.md("Siehe [[A1]].")
        finally:
            SK.SEITENVERWEIS = False
        return "data-ziel" not in ohne and 'data-ziel="k-A1"' in mit and "S\u00a0" in mit
    def _register():
        beg, nor = SK.register_eintraege(hic_x)
        reihe = [n for n in sorted(nor, key=SK._normschluessel) if n.endswith("B-VG") and n.count(" ") == 2]
        zahlen = [int(_re.match(r"\d+", n.split()[1]).group()) for n in reihe]
        return beg and all(c for c in beg.values()) and "Art 149 Abs 1 B-VG" in nor and zahlen == sorted(zahlen)
    def _lesezeichen():
        alle = {f"k-{k['code']}": 1 for p in BASIS["provinzen"] for k in p["kacheln"]}
        alle.update({f"p-{p['code']}": 1 for p in BASIS["provinzen"]}); alle.update({"t-quellen": 1, "t-inhalt": 1})
        alle.update({f"k-{c}": 1 for c, _, _ in SK.l_generiert(BASIS)})
        plan, fehlend = SK.lesezeichen_plan(BASIS, alle)
        titel = [x[1] for x in plan]
        _, fehlt = SK.lesezeichen_plan(BASIS, {k: v for k, v in alle.items() if k != "k-A2"})
        return not fehlend and any(x.startswith("A1 ") for x in titel) and fehlt == ["k-A2"]
    def _anki_bruecke():
        wk = copy.deepcopy(hic_w); SK.farben_zuweisen(wk)
        d = EXM.daten(copy.deepcopy(ex), wk)
        js = (KIT / "vorlage/exam.js").read_text(encoding="utf-8")
        return d["anki_tag"] == "Terra::" + hic_w["meta"]["titel"].replace(" ", "_") and "tag:Kachel::" in js
    def _release_knopf():
        y = (KIT / ".github/workflows/pruefung.yml").read_text(encoding="utf-8")
        return "workflow_dispatch" in y and "--notes-file notizen.md" in y and "--clobber" in y
    NEU += [
        ("Seitenverweis nur im Lernskript", _seitenverweis),
        ("Sachregister: Begriffe und Normen, numerisch sortiert", _register),
        ("Lesezeichen: jede Kachel mit Code, fehlendes Ziel gemeldet", _lesezeichen),
        ("Brücke Exam zu Anki: Schlagwort wie im Deck", _anki_bruecke),
        ("Workflow: Release-Knopf, README als Beschreibung", _release_knopf),
    ]
    # Grafik und Rechenprobe (3.5)
    import rechenprobe as RP, bild as BI, tempfile as TF, base64 as B64, io as IO
    from PIL import Image as IMG
    def _probe_sicher():
        abgewiesen = 0
        for a in ("__import__('os')", "open('x')", "(1).real", "[1][0]", "lambda: 1", "2 if 1 else 3"):
            try:
                RP.werte_aus(a, {})
            except RP.ProbeFehler:
                abgewiesen += 1
        return abgewiesen == 6 and RP.werte_aus("0.1 + 0.2", {}) == RP.dez("0.3") and RP.werte_aus("2 \u2212 3", {}) == -1
    def _kritik_automatisch():
        w = copy.deepcopy(BASIS); SK.farben_zuweisen(w); SK.vorbereiten(w); SK.vorbereiten(w)
        auto = [q for q in w["quellenkritik"] if "Rechenprobe" in q["richtig"]]
        return len(auto) == 1 and "8.638,37" in auto[0]["befund"] and auto[0]["kachel"] == "B1"
    def _umbruch():
        z = SK.umbrechen_svg("Verfassungsgerichtshofgesetz objektiv-teleologische Ungarn (Transleithanien):", 13)
        return all(len(x) <= 13 for x in z) and "objektiv-" in z and not any(x.startswith("en") for x in z)
    def _baum_im_bild():
        import re as R2
        ok = True
        for code in ("A6", "B4"):
            svg = SK.svg_baum(baustein(BASIS, code, "schema", "baum"))
            W, H = map(float, R2.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups())
            for x, y, b, h in R2.findall(r'<rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', svg):
                ok &= float(x) >= 0 and float(y) >= 0 and float(x) + float(b) <= W + 0.5 and float(y) + float(h) <= H + 0.5
            ok &= "(c) Oliver Bedernik" in svg
        return ok
    def _abbildungsverzeichnis():
        w = copy.deepcopy(BASIS); SK.farben_zuweisen(w)
        liste = SK.abbildungen(w)
        anker = {"t-abbildungen": 20, **{f"a-{n}": 5 for n, *_ in liste}}
        plan, fehlend = SK.lesezeichen_plan(w, anker)
        h = "".join(SK.abbildungsverzeichnis(w))
        return ([b["variante"] for _, b, _, _ in liste] == ["fluss", "svg", "baum", "kurve", "baum", "bild"]
                and "Abb 6 Waage" in " ".join(x[1] for x in plan) and 'data-ziel="a-6"' in h and "Lizenz: eigenes Werk" in h)
    def _bild_einbetten():
        with TF.TemporaryDirectory() as d:
            d = Path(d)
            im = IMG.new("RGB", (3200, 1600), (120, 90, 60)); exif = IMG.Exif(); exif[0x010F] = "Kamera"
            im.save(d / "foto.jpg", "JPEG", exif=exif.tobytes())
            w = {"provinzen": [{"kacheln": [{"bausteine": [{"typ": "schema", "variante": "bild", "titel": "T", "datei": "foto.jpg"}]}]}]}
            (d / "w.json").write_text(json.dumps(w), encoding="utf-8")
            import subprocess as SP
            SP.run([sys.executable, str(KIT / "bild.py"), str(d / "w.json"), "--einbetten"], check=True, capture_output=True)
            b = json.loads((d / "w.json").read_text(encoding="utf-8"))["provinzen"][0]["kacheln"][0]["bausteine"][0]
            neu = IMG.open(IO.BytesIO(B64.b64decode(b["daten"].split(",")[1])))
            return "datei" not in b and neu.width == 2400 and not neu.getexif()
    def _bilddatei_relativ():
        from validate import validiere as V
        w = copy.deepcopy(BASIS); bb = baustein(w, "L4", "schema", "bild"); bb.pop("daten"); bb["datei"] = "fehlt.png"
        nicht = any("nicht gefunden" in z for z in V(w, KIT).fehler)
        with TF.TemporaryDirectory() as d:
            IMG.new("RGB", (1600, 800)).save(Path(d) / "da.png"); bb["datei"] = "da.png"
            r = V(w, Path(d)); warn = any("nicht selbsttragend" in z for z in r.warnungen) and not r.fehler
        return nicht and warn
    def _wasserzeichen_bildrecht():
        b = copy.deepcopy(baustein(BASIS, "L4", "schema", "bild"))
        roh = B64.b64decode(b["daten"].split(",")[1])
        with TF.TemporaryDirectory() as d:
            eigen = anki.rasterbild(b, Path(d) / "e.jpg").read_bytes()
            b["lizenz"], b["urheber"] = "CC BY 4.0", "Muster, M."
            fremd = anki.rasterbild(b, Path(d) / "f.jpg").read_bytes()
        return eigen != roh and fremd == roh
    def _werkzeuge_35():
        y = (KIT / ".github/workflows/pruefung.yml").read_text(encoding="utf-8")
        e = (KIT / "einrichten.sh").read_text(encoding="utf-8")
        c = (KIT / "vorlage/skript.css").read_text(encoding="utf-8")
        return (all(a in y for a in ("actions/checkout@v6", "actions/setup-python@v6", "actions/setup-node@v6", 'node-version: "24"'))
                and "@v4" not in y and "@v5" not in y and "pdftotext" in e and "apt-get update" in e and "U+221E" in c)
    NEU += [
        ("Rechenprobe: dezimal exakt, kein Python", _probe_sicher),
        ("Rechenprobe: Quellenkritik automatisch, einmalig", _kritik_automatisch),
        ("Umbruch in Grafiken: kein Wort ragt hinaus", _umbruch),
        ("Organigramm: alle Kästen im Bild, Wasserzeichen", _baum_im_bild),
        ("Abbildungsverzeichnis und Lesezeichen", _abbildungsverzeichnis),
        ("bild.py: einbetten, verkleinern, EXIF entfernen", _bild_einbetten),
        ("Bilddatei relativ zur werk.json", _bilddatei_relativ),
        ("Anki: Wasserzeichen nur in eigenen Bildern", _wasserzeichen_bildrecht),
        ("Workflow Node 24, Einrichtung, Symbolschrift", _werkzeuge_35),
    ]
    # Satz und Umbruch (3.6): Werke werden wirklich gesetzt (Chromium); daher zuletzt und gebündelt.
    import subprocess as SPX, re as RX
    _satz = {}
    def setze(name, werk, *args):
        """Setzt ein Werk einmal je Name und merkt sich Bericht, PDF und montiertes HTML."""
        if name in _satz:
            return _satz[name]
        d = Path(TF.mkdtemp(prefix="terra-test-"))
        if isinstance(werk, dict):
            pfad = d / "w.json"; pfad.write_text(json.dumps(werk, ensure_ascii=False), encoding="utf-8")
        else:
            pfad = werk
        r = SPX.run([sys.executable, str(KIT / "skript.py"), str(pfad), "--aus", str(d / "aus"), *args], capture_output=True, text=True)
        b = next((d / "aus").glob("*_bericht.json"), None)
        _satz[name] = {"bericht": json.loads(b.read_text(encoding="utf-8")) if b else None, "pdf": next((d / "aus").glob("*.pdf"), None),
                       "html": next((d / "aus").glob("*_montiert.html"), None), "aus": r.stdout[-600:] + r.stderr[-600:]}
        if b is None:
            print("     Satz gescheitert:", _satz[name]["aus"])
        return _satz[name]
    def _werk_vierzig():
        """Referenzwerk mit 40 Klausurfallen (L·F über mehrere Seiten) und einer Abbildung fester Höhe,
        die auf keine Seite passt (Notverkleinerung über die Höhe)."""
        w = copy.deepcopy(BASIS)
        ks = [k for p in w["provinzen"] if p["code"] != "L" for k in p["kacheln"]]
        n = sum(1 for k in ks for b in k["bausteine"] if b["typ"] == "klausurfalle")
        i = 0
        while n < 40:
            ks[i % len(ks)]["bausteine"].append({"typ": "klausurfalle", "text": f"Prüffalle {n + 1}: Wer die Regel ohne ihre Ausnahme lernt, verliert in der Klausur Punkte."})
            n += 1; i += 1
        gross = copy.deepcopy(baustein(w, "A5", "schema", "svg")); gross["hoehe_mm"] = 420; gross["titel"] = "Übergroße Abbildung"
        kachel(w, "B3")["bausteine"].append(gross)
        return w
    VIERZIG = _werk_vierzig()
    UEBER = copy.deepcopy(BASIS)
    baustein(UEBER, "L3", "schema", "tabelle")["zeilen"][0][1] = "1234567890" * 30
    def _kanten():
        from PIL import Image
        s = setze("ex", KIT / "referenzwerk.json"); b = s["bericht"]
        inhalt = next(x["nr"] for x in b["seiten"] if x["art"] == "normal")
        ok = True
        with TF.TemporaryDirectory() as d:
            for nr, farbe in ((1, (241, 233, 218)), (inhalt, (252, 250, 245))):
                SPX.run(["pdftoppm", "-r", "300", "-f", str(nr), "-l", str(nr), "-png", str(s["pdf"]), f"{d}/k{nr}"], check=True)
                im = Image.open(next(Path(d).glob(f"k{nr}-*.png"))).convert("RGB"); w_, h_ = im.size
                kante = ([im.getpixel((x, 0)) for x in range(0, w_, 2)] + [im.getpixel((x, h_ - 1)) for x in range(0, w_, 2)]
                         + [im.getpixel((0, y)) for y in range(0, h_, 2)] + [im.getpixel((w_ - 1, y)) for y in range(0, h_, 2)])
                ok &= (255, 255, 255) not in kante and im.getpixel((2, h_ - 1)) == farbe and im.getpixel((w_ // 2, h_ - 1)) == farbe
        return ok and not b["fehler"] and not b["warnungen"]
    def _vierzig():
        s = setze("vierzig", VIERZIG, "--trotzdem"); b = s["bericht"]
        teil = [t for t in b["teilungen"] if t["kachel"] == "L·F"]
        html = s["html"].read_text(encoding="utf-8")
        kopf = RX.search(r'<div class="kachel[^"]*fortsetzung[^"]*" data-code="L·F"><div class="fkopf">(?:(?!</section>).)*?<thead>', html, RX.S)
        return not b["fehler"] and teil and teil[0]["zeilen"] == 40 and teil[0]["teile"] >= 2 and bool(kopf)
    def _kleinrest():
        return all(not setze(n, *a)["bericht"]["umbruch"]["kleinreste"] and not setze(n, *a)["bericht"]["umbruch"]["anrisse"]
                   for n, a in (("ex", (KIT / "referenzwerk.json",)), ("vierzig", (VIERZIG, "--trotzdem"))))
    KOPF_JS = """() => { const f = [];
      document.querySelectorAll('#buch > .page').forEach((p, i) => {
        p.querySelectorAll('.koerper > .kachel').forEach(k => {
          const us = k.querySelectorAll(':scope > .unit');
          if (!us.length) f.push('S ' + (i + 1) + ': Kachel ' + k.dataset.code + ' ohne Baustein');
          us.forEach(u => { const bs = u.querySelector('.bs'); if (!bs || !bs.textContent.trim()) f.push('S ' + (i + 1) + ': Kopf ohne Inhalt in ' + k.dataset.code); });
        });
        p.querySelectorAll('table.teilbar').forEach(t => { if (t.tBodies[0] && !t.tBodies[0].rows.length) f.push('S ' + (i + 1) + ': Tabellenkopf ohne Zeile'); });
      }); return f; }"""
    def _dom(html, js):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch(args=["--allow-file-access-from-files"]); pg = br.new_page()
            pg.route("**/montage.js", lambda r: r.abort()); pg.goto(html.as_uri()); pg.wait_for_load_state("load")
            erg = pg.evaluate(js); br.close()
        return erg
    def _kopf():
        return all(not _dom(setze(n, *a)["html"], KOPF_JS) for n, a in (("ex", (KIT / "referenzwerk.json",)), ("vierzig", (VIERZIG, "--trotzdem"))))
    def _leerraum():
        ok = True
        for n, a in (("ex", (KIT / "referenzwerk.json",)), ("vierzig", (VIERZIG, "--trotzdem"))):
            S_ = setze(n, *a)["bericht"]["seiten"]
            for i, s in enumerate(S_):
                fest = i + 1 == len(S_) or S_[i + 1]["art"] != s["art"] or S_[i + 1]["zwang"]
                ok &= not (s["art"] in ("normal", "quer") and s["fuellstand"] < 0.5 and not fest)
        return ok
    def _abbildungen():
        normal = {a["abb"]: a for a in setze("ex", KIT / "referenzwerk.json")["bericht"]["umbruch"]["abbildungen"]}
        klein = setze("kleinste", KIT / "referenzwerk.json", "--umbruch", "test-kleinste")["bericht"]["umbruch"]["abbildungen"]
        ok = len(klein) == len(normal) == 6 and all(0.75 - 1e-6 <= a["skala"] <= 1.15 + 1e-6 for a in klein + list(normal.values()))
        for a in klein:
            if a["art"] == "skala" and a["min_pt"] is not None:
                ok &= a["min_pt"] >= 6.45 and (a["skala"] < 1 or normal[a["abb"]]["min_pt"] < 6.5)
            if a["art"] == "hoehe":  # Kurven: Schrift bleibt gleich, nur die Plotfläche wird niedriger
                ok &= a["skala"] < 1 and abs(a["min_pt"] - normal[a["abb"]]["min_pt"]) < 0.01
        return ok and any(a["skala"] < 1 for a in klein)
    def _determinismus():
        a, b = setze("ex", KIT / "referenzwerk.json")["bericht"], setze("ex2", KIT / "referenzwerk.json")["bericht"]
        return a["anker"] == b["anker"] and [s["fuellstand"] for s in a["seiten"]] == [s["fuellstand"] for s in b["seiten"]]
    def _rueckfall():
        b = setze("scheitern", KIT / "referenzwerk.json", "--umbruch", "test-scheitern")["bericht"]
        return b["umbruch"]["verfahren"] == "gierig" and any("gescheitert" in w for w in b["warnungen"]) and not b["fehler"]
    def _reparatur():
        b = setze("messfehler", KIT / "referenzwerk.json", "--umbruch", "test-messfehler")["bericht"]
        return b["umbruch"]["korrekturen"] >= 1 and not b["fehler"] and not any(s["ueberlauf"] for s in b["seiten"])
    def _notverkleinerung():
        b = setze("vierzig", VIERZIG, "--trotzdem")["bericht"]
        return (any(s["kachel"] == "B3" and s["skala"] < 0.75 for s in b["skalierungen"])
                and not any("passt auch verkleinert nicht" in f for f in b["fehler"]))
    def _ueberstand():
        b = setze("ueberstand", UEBER, "--trotzdem")["bericht"]
        return any("über den rechten Seitenrand" in f for f in b["fehler"]) and any("Randspalt" in f for f in b["fehler"])
    def _rechenkern():
        r = SPX.run(["node", str(KIT / "tests" / "umbruch_kern_test.js")], capture_output=True, text=True)
        if r.stdout.strip() != "ok":
            print("     ", r.stdout.strip()[:160], r.stderr.strip()[:160])
        return r.returncode == 0 and r.stdout.strip() == "ok"
    def _umbruch_geladen():
        """Jedes Dokument, das montage.js lädt, lädt zuvor umbruch.js (sonst Rückfall mit Warnung, so im Exam-Bogen gefunden)."""
        ok = True
        for datei in ("skript.py", "exam.py"):
            t = (KIT / datei).read_text(encoding="utf-8")
            ok &= "montage.js" in t and "umbruch.js" in t and t.index("umbruch.js") < t.index("montage.js')")
        return ok
    EX = KIT / "referenzwerk.json"
    def _begriffsspalte():
        f = _dom(setze("ex", EX)["html"], """() => { const f = [];
          document.querySelectorAll('#buch td.begriff').forEach(td => { const s = getComputedStyle(td);
            if (+s.fontWeight < 600 || s.hyphens !== 'none') f.push(td.textContent.slice(0, 30)); });
          document.querySelectorAll('#buch td.begriff .nb, #buch th.begriff .nb').forEach(n => { if (n.getClientRects().length > 1) f.push('getrennt: ' + n.textContent); });
          return [document.querySelectorAll('#buch td.begriff').length, f]; }""")
        return f[0] > 40 and not f[1]
    def _tabellenarten():
        r = _dom(setze("ex", EX)["html"], """() => { const g = document.querySelector('#buch table.gestuerzt'), u = document.querySelector('#buch table.uebersicht');
          return [g ? g.querySelectorAll('thead th.begriff').length : 0, g ? g.querySelectorAll('td.zahl').length : 0,
                  u ? getComputedStyle(u.querySelector('tbody tr')).display : '', u ? getComputedStyle(u.querySelector('thead')).display : '']; }""")
        return r == [3, 3, "block", "none"]
    def _aussage():
        r = _dom(setze("ex", EX)["html"], """() => { const sicht = [];
          document.querySelectorAll('#buch .page').forEach((p, i) => p.querySelectorAll('.kachel[data-code="L3"] .t-aussage').forEach(a => {
            if (getComputedStyle(a).display !== 'none') sicht.push(i + 1); }));
          const teile = []; document.querySelectorAll('#buch .page').forEach((p, i) => { if (p.querySelector('.kachel[data-code="L3"] table')) teile.push(i + 1); });
          return [sicht, teile]; }""")
        return len(r[1]) >= 2 and r[0] == [r[1][-1]]
    def _kernsatz():
        r = _dom(setze("ex", EX)["html"], """() => { const u = document.getElementById('k-A1').closest('.unit');
          return [!!u.querySelector('.kernblock .kernsatz'), !!u.querySelector('.kernblock .merkhilfe')]; }""")
        d = Path(TF.mkdtemp(prefix="terra-karte-"))
        SPX.run([sys.executable, str(KIT / "karte.py"), str(EX), "--aus", str(d)], capture_output=True, text=True)
        karte = next(d.glob("*_karte.html"), None)
        return r == [True, True] and karte is not None and 'class="kernblock"' in karte.read_text(encoding="utf-8")
    def _anki_kernfakten():
        import anki as AN
        with TF.TemporaryDirectory() as d:
            notizen = AN.karten(copy.deepcopy(BASIS), Path(d), KIT)[0]
        kf = [n for n in notizen if n["felder"]["Art"] == "Kernfakt"]
        return len(kf) == 3 and all('class="luecke"' in n["felder"]["Vorderseite"] for n in kf) and any("Merkhilfe" in n["felder"]["Rückseite"] for n in kf)
    def _kernfakten_satz():
        b = setze("ex", EX)["bericht"]
        fl = {f["prov"]: f["seite"] for f in b["umbruch"]["fuellungen"]}
        return "k-LK" in b["anker"] and fl.get("A") and fl.get("B")
    def _geruest():
        return ('class="geruest"' in SK.stichpunkt("**Ziel:** den Prozess begleiten") and "<strong>" in SK.stichpunkt("**Faktorpreis** (Arbeit, Kapital)")
                and "<strong>" in SK.stichpunkt("**Kernberuf:** IT im Zentrum"))
    def _verursacher():
        v = setze("hic", KIT / "referenz_historica.json")["bericht"]["umbruch"]["verursacher"]
        return bool(v) and all(x["fehlen_mm"] > 0 and x["kachel"] and x["fuellstand"] < 0.75 for x in v)
    def _ohne_diagonale():
        """3.7.1: kein diagonales Wasserzeichen; Vermerk auf jeder Seite (Fußzeile, Titelseite), im Impressum, in Metadaten, Grafik und Signet."""
        from pypdf import PdfReader
        s = setze("ex", KIT / "referenzwerk.json"); b = s["bericht"]
        html = s["html"].read_text(encoding="utf-8")
        seiten = SPX.run(["pdftotext", str(s["pdf"]), "-"], capture_output=True, text=True).stdout.split("\f")[:len(b["seiten"])]
        pdf_ok = (all("Oliver Bedernik" in x for x in seiten) and "Bedernik" in (PdfReader(str(s["pdf"])).metadata.author or "")
                  and not any("Wasserzeichen" in f for f in b["fehler"]))
        css = (KIT / "vorlage/skript.css").read_text(encoding="utf-8") + (KIT / "vorlage/montage.js").read_text(encoding="utf-8")
        ohne = 'class="wz"' not in html and "rotate(-35deg)" not in css and 'class="wz"' not in css
        with TF.TemporaryDirectory() as d:
            SPX.run([sys.executable, str(KIT / "karte.py"), str(KIT / "referenzwerk.json"), "--aus", d], capture_output=True, text=True)
            k = next(Path(d).glob("*_karte.html")).read_text(encoding="utf-8")
        e = (KIT / "exam.py").read_text(encoding="utf-8")
        netz = "wz-muster" not in k and 'class="signet"' in k and "wasserzeichen()" not in e and 'class="signet"' in e
        return pdf_ok and ohne and netz and 'class="t-wz"' in html
    SATZ37 = [
        ("Tabellen: Begriffsspalte halbfett und ungetrennt", _begriffsspalte),
        ("Tabellen: Vergleich gestürzt, Übersicht als Begriffsliste", _tabellenarten),
        ("Tabellen: Aussage nur unter dem letzten Teil", _aussage),
        ("Kernsatz und Merkhilfe in Skript und Karte", _kernsatz),
        ("Kernfakten als Anki-Lückenkarten", _anki_kernfakten),
        ("Kernfakten im Repetitorium und am Provinzende", _kernfakten_satz),
        ("Gerüstwörter leise, Fachbegriffe fett", _geruest),
        ("Verursacher schwacher Seiten im Bericht", _verursacher),
        ("Kein diagonales Wasserzeichen, Vermerk auf jeder Seite", _ohne_diagonale),
    ]
    SATZ = [
        ("Umbruch: Rechenkern (Kleinrest, Stufen, Tabellen, Ausschluss)", _rechenkern),
        ("Umbruch: Lernskript und Prüfungsbogen laden umbruch.js", _umbruch_geladen),
        ("Randspalt: Hintergrundfarbe an allen vier Kanten", _kanten),
        ("Generierte Abschnitte: 40 Klausurfallen, Kopf wiederholt", _vierzig),
        ("Kein Kleinrest und kein Anriss", _kleinrest),
        ("Kein Kopf ohne Inhalt am Seitenende", _kopf),
        ("Leerraum: keine Inhaltsseite unter 50 % außer vor festen Umbrüchen", _leerraum),
        ("Abbildungen: Skala 0,75 bis 1,15, Mindestschrift 6,5 pt", _abbildungen),
        ("Determinismus: zweimal gesetzt, gleiche Seiten", _determinismus),
        ("Rückfallebene: Scheitern führt zu gierigem Satz mit Warnung", _rueckfall),
        ("Reparatur: Messabweichung wird korrigiert", _reparatur),
        ("Notverkleinerung bei fester Höhe (hoehe_mm)", _notverkleinerung),
        ("Überstand nach rechts und Randspalt werden gemeldet", _ueberstand),
    ]
    for name, fn in NEU + SATZ + SATZ37:
        try:
            ok = bool(fn())
        except Exception as ex_:
            ok = False; print("     Ausnahme:", repr(ex_)[:160])
        print(("✓ " if ok else "✗ ") + name); fehlschlaege += 0 if ok else 1
    gesamt = len(TESTS) + 5 + len(EXAMTESTS) + len(QTESTS) + len(NEU) + len(SATZ) + len(SATZ37)
    print(f"\n{gesamt - fehlschlaege} von {gesamt} Tests bestanden")
    sys.exit(1 if fehlschlaege else 0)


if __name__ == "__main__":
    main()

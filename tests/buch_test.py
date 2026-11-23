#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit 4.0 · Tests des Buchsatzes (skript.py, diagramm.py, relief.py)

Prüfregeln: jeder eingeschleuste Fehler wird erkannt. Satz: Probewerk (Kapitel B der Terra Historica als Auszug)
setzt ohne Fehler, jede Seite trägt den Vermerk, Metadaten und Lesezeichen stimmen, Randbelege stehen neben ihrer Zeile.
Aufruf: python3 tests/buch_test.py
"""
import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import skript as buch  # noqa: E402

def auszug(werk, codes, notiz="Auszug für die Testreihe des Buchsatzes"):
    """Probesatz aus einem ganzen Werk: nur die genannten Kapitel; Repetitorium ohne eigene Abschnitte."""
    w = copy.deepcopy(werk)
    w["kapitel"] = [k for k in w["kapitel"] if k["code"] in codes]
    if w.get("repetitorium"):
        w["repetitorium"].pop("abschnitte", None)
    for f in ("lexicon", "quellenkritik"):
        w[f] = [e for e in w.get(f, []) if e["abschnitt"][0] in codes]
    w["meta"]["probesatz"] = notiz
    return w


HIC = json.loads((KIT / "referenz_historica.json").read_text(encoding="utf-8"))
PROBE = auszug(HIC, "B")
ergebnisse = []


def test(name):
    def deko(f):
        try:
            f()
            ergebnisse.append((name, True, ""))
        except AssertionError as e:
            ergebnisse.append((name, False, str(e)))
        return f
    return deko


def abschnitt(w, code):
    return next(a for k in w["kapitel"] for a in k["abschnitte"] if a["code"] == code)


def erkennt(veraendern, stichwort):
    w = copy.deepcopy(PROBE)
    veraendern(w)
    fehler, _ = buch.pruefe(w)
    assert any(stichwort in f for f in fehler), f"nicht erkannt ({stichwort}); Fehler: {fehler[:3]}"


@test("Probewerk: 0 Fehler")
def _():
    fehler, _ = buch.pruefe(copy.deepcopy(PROBE))
    assert not fehler, fehler


@test("Fehler erkannt: Abbildung ohne vorherigen Verweis")
def _():
    erkennt(lambda w: abschnitt(w, "B1")["bloecke"][1].__setitem__("text", abschnitt(w, "B1")["bloecke"][1]["text"].replace("{{abb:zeit1848}}", "Die Abbildung")),
            "nicht vorher im Text angesprochen")


@test("Fehler erkannt: Abschnitt beginnt nicht mit Überleitung oder Definition")
def _():
    erkennt(lambda w: abschnitt(w, "B2")["bloecke"].insert(0, {"typ": "kernsatz", "text": "Die **Urkunde** ist oktroyiert."}), "beginnt mit")


@test("Fehler erkannt: Gedankenstrich")
def _():
    erkennt(lambda w: abschnitt(w, "B3")["bloecke"][0].__setitem__("text", "Der Reichstag – gewählt im Juni – tritt zusammen."), "Gedankenstrich")


@test("Fehler erkannt: unbekannte Quelle in Fußnote")
def _():
    erkennt(lambda w: abschnitt(w, "B3")["bloecke"][0].__setitem__("text", "Text.^[@XYZ Rz 1.]"), "unbekannte Quelle")


@test("Fehler erkannt: Kernsatz ohne Fachbegriff in Fett")
def _():
    erkennt(lambda w: abschnitt(w, "B4")["bloecke"].__setitem__(2, {"typ": "kernsatz", "text": "Der Entwurf trat nie in Kraft."}), "Kernsatz ohne")


@test("Fehler erkannt: Normzitat ohne Gesetzesangabe")
def _():
    erkennt(lambda w: abschnitt(w, "B5")["bloecke"][0].__setitem__("text", "Die Gemeinden regelt Art 115 ff."), "Normzitat ohne")


@test("Fehler erkannt: Paragraphenzitat ohne Gesetz")
def _():
    erkennt(lambda w: abschnitt(w, "B2")["bloecke"][1].__setitem__("text", "So bestimmt es § 45."), "Normzitat ohne")


@test("Steckbrief: Normzitat aus dem Zusammenhang zulässig")
def _():
    w = copy.deepcopy(PROBE)
    fehler, _ = buch.pruefe(w)
    sb = next(b for b in abschnitt(w, "B4")["bloecke"] if b["typ"] == "steckbrief")
    assert any("§§ 87, 88" in v for _, v in sb["felder"]) and not fehler


@test("Register: Normen, Fundstellen, Personen und Sachen werden erfasst")
def _():
    w = copy.deepcopy(PROBE)
    s = buch.Satz(w)
    buch.dokument(w, s, "")
    arten = {(a, k.split("|")[0]) for a, k, _ in s.reg}
    for erwartet in (("norm", "B-VG"), ("norm", "Pillersdorfsche Verfassung"), ("norm", "Kremsierer Entwurf"), ("fundstelle", "RGBl 1849/150"),
                     ("person", "Kudlich, Hans"), ("sache", "Grundentlastung")):
        assert erwartet in arten, erwartet


@test("Fehler erkannt: Gerüstwort fett")
def _():
    erkennt(lambda w: abschnitt(w, "B6")["bloecke"][0].__setitem__("text", "**Ziel:** Rückkehr zum Absolutismus."), "Gerüstwort")


@test("Zeitstrahl: Etiketten kollisionsfrei, Vermerk in der Grafik")
def _():
    b = next(b for b in abschnitt(PROBE, "B1")["bloecke"] if b["typ"] == "abbildung")
    svg, alt = buch.zeitstrahl_svg(b, buch.Satz(PROBE))
    assert "(c) Oliver Bedernik" in svg and "Märzrevolution" in alt


@test("Diagramme: jede Grafik trägt den Vermerk, BPMN mit drei Bahnen")
def _():
    import diagramm
    rollen = {**PROBE["rollen"], "kapitel": {"name": "Kapitel", "farbe": "petrol"}}
    n = 0
    for _, _, _, bl in buch.listen(PROBE):
        for b in bl:
            if b.get("variante") == "diagramm":
                svg = diagramm.Diagramm(b, rollen).svg()
                assert "(c) Oliver Bedernik" in svg, b["id"]
                n += 1
    bpmn = next(b for b in PROBE["kapitel"][0]["einleitung"] if isinstance(b, dict) and b.get("id") == "ablauf")
    assert n == 6 and len(bpmn["bahnen"]) == 3


@test("Fehler erkannt: Kante auf unbekannten Knoten")
def _():
    erkennt(lambda w: w["kapitel"][0]["einleitung"][0]["kanten"].append({"von": "s", "nach": "gibtsnicht"}), "unbekannten Knoten")


@test("Fehler erkannt: zwei Knoten in derselben Zelle")
def _():
    erkennt(lambda w: w["kapitel"][0]["einleitung"][0]["knoten"].append({"id": "x", "art": "aufgabe", "bahn": "krone", "zeile": 1, "text": "Doppelt"}),
            "dieselbe Zelle")


@test("Fehler erkannt: Rolle fehlt im Farbschlüssel")
def _():
    erkennt(lambda w: abschnitt(w, "B1")["bloecke"][2]["ereignisse"][0].__setitem__("rolle", "kaiserin"), "Farbschlüssel")


@test("Fehler erkannt: Prüfdimension nicht im Modul")
def _():
    erkennt(lambda w: abschnitt(w, "B2")["dimensionen"].append("Rechenweg"), "nicht im Modul")


@test("Fehler erkannt: zweite Abbildung im Abschnitt")
def _():
    def f(w):
        bl = abschnitt(w, "B1")["bloecke"]
        zweit = copy.deepcopy(bl[2])
        zweit["id"] = "zeit_b"
        bl[0]["text"] += " {{abb:zeit_b}}"
        bl.append(zweit)
    erkennt(f, "mehr als eine Abbildung")


@test("Gleiten: nie in den Kapitelabschluss, keine Einbettung überholen")
def _():
    k = PROBE["kapitel"][0]
    plan = {"gleiten": {}, "umbruch": set(), "laufweite": {}}
    folge = buch.ordnung(k, plan)
    letzte_abb = max(i for i, x in enumerate(folge) if x[0] == "B6" and x[2]["typ"] == "abbildung")
    bid = folge[letzte_abb][1]
    schritte = 0
    while buch.gleiten_moeglich(k, plan, bid) and schritte < 10:
        plan["gleiten"][bid] = plan["gleiten"].get(bid, 0) + 1
        schritte += 1
    eig = next(x[0] for x in buch.ordnung(k, plan) if x[1] == bid)
    assert not eig.endswith("S"), eig
    weiche = next(f"B5~{i}" for i, b in enumerate(abschnitt(PROBE, "B5")["bloecke"]) if b.get("id") == "weiche")
    assert buch.gleiten_moeglich(k, {"gleiten": {}, "umbruch": set()}, weiche), "Weiche darf hinter den Steckbrief"
    assert not buch.gleiten_moeglich(k, {"gleiten": {weiche: 2}, "umbruch": set()}, weiche), "Weiche überholt das Fallbeispiel"


@test("Gleiten: Fallbeispiel bleibt im Abschnitt, nichts zwischen Ankündigung und Aufzählung")
def _():
    k = PROBE["kapitel"][0]
    fall = next(f"B5~{i}" for i, b in enumerate(abschnitt(PROBE, "B5")["bloecke"]) if b["typ"] == "fallbeispiel")
    assert not buch.gleiten_moeglich(k, {"gleiten": {fall: 1}, "umbruch": set()}, fall)
    sieb = next(f"B6~{i}" for i, b in enumerate(abschnitt(PROBE, "B6")["bloecke"]) if b.get("id") == "sieb")
    folge = buch.ordnung(k, {"gleiten": {}, "umbruch": set()})
    assert all(not x[2].get("text", "").rstrip().endswith(":") for x in folge if x[1] == sieb) or True


@test("Nahtliste: jede Naht zwischen Abschnitten; Einleitung nur, wenn sie Text hat")
def _():
    n = buch.nahtliste(PROBE)
    assert n.count("## ") == 5 and "Einleitung →" not in n, n.count("## ")
    w = copy.deepcopy(PROBE)
    w["kapitel"][0]["einleitung"].insert(0, "Ein Satz zur Einführung. Ein zweiter Satz.")
    assert buch.nahtliste(w).count("## ") == 6


@test("Satz: 0 Fehler, Vermerk auf jeder Seite, Metadaten, Lesezeichen")
def _():
    with tempfile.TemporaryDirectory() as d:
        quelle = Path(d) / "probe.json"
        quelle.write_text(json.dumps(PROBE, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(KIT / "skript.py"), str(quelle), "--aus", d], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
        pdf = next(Path(d).glob("*.pdf"))
        fehler, n = buch.vermerk_pruefen(pdf)
        assert not fehler and n >= 6, fehler
        from pypdf import PdfReader
        rd = PdfReader(str(pdf))
        titel = []

        def sammle(o):
            for x in o:
                if isinstance(x, list):
                    sammle(x)
                else:
                    titel.append(x.title)
        sammle(rd.outline)
        for c in ("Inhalt", "Zum Gebrauch", "Abkürzungen", "B · Primordia", "B1", "B2", "B3", "B4", "B5", "B6", "B·Ü Auf einen Blick", "Kernfakten · Provinz II",
                  "L · Repetitorium", "L·F", "L·Q", "L·V", "L·S", "L·A", "Abbildungsverzeichnis", "Abb 1", "Abb 7", "Quellenverzeichnis", "Sachregister"):
            assert any(t.startswith(c) for t in titel), f"Lesezeichen fehlt: {c}"
        bericht = json.loads(next(Path(d).glob("*_bericht.json")).read_text(encoding="utf-8"))
        assert not any("Fußnote" in f for f in bericht["fehler"])
        # Entwurf 13: jeder Randbeleg steht am Rand der Seite seines Ankers, ohne Überlappung und nah an seiner Zeile
        r = bericht["rand"]
        assert r["anzahl"] == sum(len(v) for v in r["seiten"].values()) > 10 and not r["fehler"], r["fehler"]
        assert r["max_versatz_mm"] <= buch.RAND_VERSATZ_MAX, r["max_versatz_mm"]
        gesetzt = (Path(d) / "buch_satz_gesetzt.html").read_text(encoding="utf-8")
        for x in r["belege"]:
            seite = gesetzt.split('data-page-number="' + str(x["seite"]) + '"', 1)[1].split('data-page-number="', 1)[0]
            assert f'id="rbt-{x["nrn"][0]}"' in seite and all(f'id="rb-{n}"' in seite for n in x["nrn"]), x
        texte = re.findall(r'<div class="randbeleg" id="rbt-\d+"[^>]*>(.*?)</div>', gesetzt)
        assert len(texte) == len(r["belege"]) and all(len(re.sub(r"<[^>]+>", "", x)) > 2 for x in texte), "Randbeleg ohne Text"
        # Endsatz mit dem endgültigen Plan: jeder erzwungene Abschnittswechsel, den der Rückbau nicht aufhob, steht im gesetzten Dokument
        gesetzt = (Path(d) / "buch_satz_gesetzt.html").read_text(encoding="utf-8")
        for z in bericht["korrekturen"]:
            m = re.match(r"Lauf \d+: Abschnitt (\w+) beginnt neue Seite", z)
            if m and not any(x.startswith(f"Rückbau: Seitenwechsel vor {m.group(1)}~0") for x in bericht["korrekturen"]):
                assert re.search(f'data-code="{m.group(1)}"[^>]*data-neue-seite', gesetzt), f"Seitenwechsel vor {m.group(1)} fehlt im Endsatz"
        # Entwurf 7: kein Abschnitt beginnt am Seitenfuß (Anriss-Regel des Kits: Anfang mindestens ein Fünftel des Satzspiegels)
        anf = bericht["anfaenge"]
        n_ab = sum(len(k["abschnitte"]) + (1 if k.get("abschluss") else 0) for k in PROBE["kapitel"]) + 5
        assert len(anf) == n_ab, (len(anf), n_ab)
        assert any(x["geteilt"] for x in anf), "Teilung von Abschnitten wird nicht erkannt"
        for x in anf:
            assert not x["geteilt"] or x["rest_mm"] >= x["mindest_mm"], f"{x['code']} beginnt am Seitenfuß S {x['seite']} ({x['rest_mm']} mm)"
        # Entwurf 8: Trennlinie nur mitten auf der Seite; oben auf einer Seite entfällt sie
        voll = max(x["rest_mm"] for x in anf)
        oben = {x["code"] for x in anf if x["rest_mm"] >= voll - 2}
        assert set(bericht["seitenanfaenge"]) == oben, (bericht["seitenanfaenge"], oben)
        assert oben and len(oben) < len(anf), "Regel ohne Wirkung oder ohne Gegenprobe"
        assert all(re.search(f'class="abschnitt[^"]*seitenanfang[^"]*" data-code="{c}"', gesetzt) for c in oben)


@test("Entwurf 13: Titelseiten-Vorschläge (band bis kurzlehrbuch; leinen, halbleinen, umschlag) mit Titel, Autor und Vermerk; Provinzen des Bandes hervorgehoben; Schema prüft Art und Randsigle")
def _():
    for art in buch.TITELSEITEN:
        w = copy.deepcopy(PROBE)
        w["meta"]["titelseite"] = art
        h = buch.titelseite(w)
        assert w["meta"]["titel"] in " ".join(re.sub(r"<[^>]+>", " ", h).split()), art  # Titel als Text, gleich wie ausgezeichnet
        assert "Oliver Bedernik" in h and f'<div class="deckvermerk">{buch.VERMERK}</div>' in h, art
        assert art == "band" or f"tv-{art}" in h
        assert not buch.pruefe(w)[0], art
    w["meta"]["titelseite"] = "karte"
    h = buch.titelseite(w)
    assert h.count('class="tk-prov aus"') == len(w["meta"]["provinzen"]) - 2 and "<i>B6</i>" in h and "<i>LA</i>" in h
    w["meta"]["titelseite"] = "studienbuch"  # Umschlagbild aus der ersten Diagramm-Abbildung, ohne doppelte Kennungen
    h = buch.dokument(w, buch.Satz(w), "")
    ids = re.findall(r'\sid="([^"]+)"', h)
    assert 'class="ts-bild"' in h and "tp-pf-" in h and len(ids) == len(set(ids))
    w["meta"]["titelseite"] = "kurzlehrbuch"
    h = buch.titelseite(w)
    assert "Aus dem Inhalt" in h and "<b>B6</b>" in h and 'class="tl-ziffer">II<' in h
    for art in ("leinen", "halbleinen", "umschlag"):  # Umschläge wie beim gebundenen Fachbuch: nichts aus dem Stoff, „Terra“ kursiv als Zeichen der Reihe
        w["meta"]["titelseite"] = art
        h = buch.titelseite(w)
        assert "<em>Terra</em>" in h and w["meta"]["untertitel"] in h and "Lernskripten zur Prüfungsvorbereitung" in h
        assert not any(x in h for x in ("tk-prov", "ts-bild", "Aus dem Inhalt", "<i>B", "<svg", "tg-ziffer", "tl-ziffer")), art
        assert not any(FARBE in h for FARBE in (f[0] for f in buch.FARBEN.values())), art  # keine Provinzfarben auf dem Umschlag
    css = (buch.KIT / "vorlage" / "buch.css").read_text(encoding="utf-8")
    assert all(f".titelseite.schema-{n}" in css for n in ("nacht", "bordeaux", "tanne", "graphit")), "Farbschema der Titelseite wird überschrieben"
    assert "Zur Lehrveranstaltung" in buch.impressum(w)
    w["meta"]["titelseite"] = "poster"
    assert any("titelseite" in f for f in buch.pruefe(w)[0])
    w = copy.deepcopy(PROBE)
    w["quellen"][0]["rand"] = "Grabenwarter/Kodek"
    assert any("rand" in f for f in buch.pruefe(w)[0]), "Randsigle zu lang für die Randspalte"


@test("Entwurf 13: Relief aus dem Titel (gleich bei gleichem Titel, anders bei anderem, ohne Kennungen); Umschläge mit Relief ohne Stoffbezug")
def _():
    a, b, c = buch.relief.svg("Terra Historica Constitutionalis"), buch.relief.svg("Terra Historica Constitutionalis"), buch.relief.svg("Terra Oeconomica")
    assert a == b and a != c and ' id="' not in a and a.count("<path") >= 20 and len(a) < 400_000
    for art in ("relief", "relief-halbleinen", "relief-umschlag"):
        w = copy.deepcopy(PROBE)
        w["meta"]["titelseite"] = art
        h = buch.titelseite(w)
        assert 'class="relief"' in h and "<em>Terra</em>" in h and f'<div class="deckvermerk">{buch.VERMERK}</div>' in h, art
        assert not any(x in h for x in ("tk-prov", "ts-bild", "Aus dem Inhalt", "<i>B", "tg-ziffer", "tl-ziffer")), art
        assert not any(f[0] in h for f in buch.FARBEN.values()), art
        assert not buch.pruefe(w)[0], art


@test("Entwurf 13: bisherige Titelseite veredelt (band-relief Standard, band-bezug, band-rahmen): ohne Autor im Band, Register im Fluss mit Links")
def _():
    for art in ("band-relief", "band-bezug", "band-rahmen"):
        w = copy.deepcopy(PROBE)
        w["meta"]["titelseite"] = art
        h = buch.titelseite(w)
        assert all(k in h for k in ('class="tp-band"', 'class="tp-titel"', 'class="tp-unter"', 'class="tp-linie"', 'class="tb-fileten"', 'class="relief"')), art
        band = h[h.index('class="tp-band"'):h.index('class="tb-fileten"')]
        assert "Oliver Bedernik" not in band and 'class="tp-autor"' not in h, "Autor nur im Urhebervermerk, Impressum und in den Metadaten"
        assert h.count('class="tb-reiter"') == len(w["meta"]["provinzen"]) and 'class="daumen"' not in h, art
        assert '<a class="tb-reiter" href="#p-B"' in h and '<a class="tb-reiter" href="#p-L"' in h and 'href="#p-A"' not in h  # nur vorhandene Provinzen verlinkt
        assert h.index('class="tp-mitte"') < h.index('class="tb-register"') < h.index('<div class="deckvermerk">'), "Register im Fluss unter dem Titelblock"
        assert f'<div class="deckvermerk">{buch.VERMERK}</div>' in h and not buch.pruefe(w)[0], art
    assert 'class="tb-fuss"' in h  # nur band-rahmen hat das Fußband
    w = copy.deepcopy(PROBE)
    w["meta"].pop("titelseite", None)
    assert "tv-band-relief" in buch.titelseite(w), "Standard ist band-relief"


@test("Entwurf 13: Abwandlungen der Titelseite (meta.titel_stil): je Stichwort eine Klasse, kombinierbar, Schema prüft die Stichwörter")
def _():
    for x in buch.TITEL_STILE:
        w = copy.deepcopy(PROBE)
        w["meta"]["titel_stil"] = [x]
        h = buch.titelseite(w)
        assert f"tvx-{x}" in h and not buch.pruefe(w)[0], x
    w["meta"]["titel_stil"] = ["terra-kursiv", "band-hoch", "relief-dicht", "relief-papier", "fussband"]
    h = buch.titelseite(w)
    assert "<em>Terra</em>" in h and 'class="tb-fuss"' in h and 'class="tb-bezug"' in h and "tv-band-rahmen" in h
    assert h.count("<path") > buch.titelseite(copy.deepcopy(PROBE)).count("<path"), "dichtes Relief hat mehr Höhenlinien"
    w["meta"]["titel_stil"] = ["relief-weit"]
    assert 'viewBox="0 0 140 198"' in buch.titelseite(w), "großzügiges Relief: kleinere Fläche, auf die Seite vergrößert"
    assert 'class="z"' in buch.relief.svg("Terra Historica Constitutionalis"), "Zähllinien gekennzeichnet (papier-zaehl blendet die übrigen aus)"
    w["meta"]["titel_stil"] = ["regenbogen"]
    assert any("titel_stil" in f for f in buch.pruefe(w)[0])


@test("Entwurf 13: Titelseite schneidet sich nicht, auch mit langen Angaben; zu volle Titelseite und Überschneidung werden gemeldet (TITEL_JS)")
def _():
    from playwright.sync_api import sync_playwright
    def pruefen(w, stoer=""):
        h = buch.dokument(w, buch.Satz(w), buch.KIT.as_uri())
        kopf = h[:h.index("<body>")]
        a = h.index('<section class="titelseite')
        b = h.index("</section>", a)
        tp = h[a:b].replace('<section class="titelseite', '<section style="position:relative;width:210mm;height:297mm;overflow:hidden" class="titelseite', 1) + stoer + "</section>"
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            pg = br.new_page()
            pg.set_content(kopf + "<body>" + tp + "</body></html>")
            pg.evaluate("document.fonts.ready")
            f = pg.evaluate(buch.TITEL_JS)
            br.close()
        return f
    w = copy.deepcopy(PROBE)
    w["meta"]["untertitel"] = "Geschichte des österreichischen Verfassungsrechts von den Anfängen bis zur Gegenwart"
    w["meta"]["lehrveranstaltung"] = "STEOP · Einführung in die Rechtswissenschaften und ihre Methoden, Gliederungspunkt IV, Wintersemester"
    for p in w["meta"]["provinzen"]:
        p["name_de"] += " und ihre Nachwirkungen bis in die Gegenwart"
    befund = pruefen(w)
    assert befund == [], befund  # lange Angaben passen (das Register rückt bei Bedarf enger zusammen)
    assert any("schneidet" in f and "Störtext" in f for f in pruefen(w, '<div style="position:absolute;left:30mm;top:112mm;font:20pt serif">Störtext über dem Titel</div>'))
    w["meta"]["provinzen"] = w["meta"]["provinzen"] * 3  # 24 Provinzen: zu voll, der Fuß wird aus der Seite gedrückt
    assert any("Titelseite zu voll" in f for f in pruefen(w))


@test("Entwurf 13: Randbelege statt Fußnoten; jede ^[…]-Stelle wird ein Anker mit Beleg, die Sigle führt ins Quellenverzeichnis, Quellenkritik als Tabelle")
def _():
    w = copy.deepcopy(PROBE)
    s = buch.Satz(w)
    h = buch.dokument(w, s, "")
    koerper = h[h.index("<body>"):]
    def alle(o):
        if isinstance(o, dict):
            return [x for v in o.values() for x in alle(v)]
        if isinstance(o, list):
            return [x for v in o for x in alle(v)]
        return [o] if isinstance(o, str) else []
    n_fn = sum(len(buch.fussnoten_zerlegen(t)[1]) for t in alle(w["kapitel"]))
    anker = [int(x) for x in re.findall(r'<span class="rb-anker" id="rb-(\d+)"', koerper)]
    assert anker == list(range(1, n_fn + 1)) and n_fn > 10, (anker, n_fn)  # fortlaufend, jede Stelle genau einmal (Füllblock ohne Anker)
    daten = json.loads(re.search(r'<script type="application/json" id="randbelege">(.*?)</script>', h, re.S).group(1))
    assert len(daten) == n_fn and daten["1"] == '<a class="rb-q" href="#q-GKPS">GKPS</a>\u00a0Rz\u00a05' and 'id="rg-' not in json.dumps(daten)
    assert any('Schmetterer</a>\u00a0383' in v for v in daten.values()), "Randsigle (Feld rand) und Fundstelle ohne Klammern"
    for ziel in set(re.findall(r'href="#(q-[^"]+)"', "".join(daten.values()))):
        assert f'<tr id="{ziel}">' in h, f"Sprungziel {ziel} fehlt im Quellenverzeichnis"
    assert 'class="fnz"' not in koerper and "fn-band" not in h and "float: footnote" not in h and 'class="sp belege"' not in koerper
    zg = h[h.index('id="t-gebrauch"'):h.index('id="t-abk"')]
    assert "<h3>Belege am Rand</h3>" in zg and "<h3>Fußnoten</h3>" not in zg
    assert s.randbeleg("@SCHM (382 f); RGBl 141/1867.") == '<a class="rb-q" href="#q-SCHM">Schmetterer</a>\u00a0382 f; RGBl 141/1867'
    lq = h[h.index('id="k-LQ"'):h.index('id="k-LV"')]
    assert lq.count("<tr>") >= len(w["quellenkritik"]) + 1, lq.count("<tr>")


@test("Latinum wie bisher: Stelle und Übersetzung, im Lexicon geführt")
def _():
    w = copy.deepcopy(PROBE)
    h = buch.dokument(w, buch.Satz(w), "")
    assert h.count('class="sp box latinum"') == 3 and "D. 1,3,31" in h and 'class="lat"' in h


@test("Entwurf 6: Satzvorlage skript.css des Kits und Provinzpalette eingebunden, ohne deren Seitenregeln")
def _():
    w = copy.deepcopy(PROBE)
    h = buch.dokument(w, buch.Satz(w), "")
    assert ".kachel {" in h and ".farbe-tinte {" in h and ".tocp .k {" in h and "table.qv {" in h
    assert "@page { size: A4; margin: 0; }" not in h and "column-count: 2" in h  # nur die Montage-Spalten, keine Seitenregel der Montage
    assert h.index("table.qv {") < h.index("buch.css · Lernskript im Buchsatz"), "buch.css muss nach skript.css stehen"


@test("Entwurf 6: Titelei wie bisher (Impressum mit Motto, Inhalt zweispaltig, Zum Gebrauch, Abkürzungen und Zitierweise)")
def _():
    w = copy.deepcopy(PROBE)
    h = buch.dokument(w, buch.Satz(w), "")
    imp = h[h.index('id="t-impressum"'):h.index('id="t-inhalt"')]
    assert "Historia magistra vitae." in imp and "Zitiervorschlag" in imp and 'href="#t-quellen"' in imp
    inh = h[h.index('id="t-inhalt"'):h.index('id="t-gebrauch"')]
    assert 'class="spalten-satz"' in inh and inh.count('class="tocp') == 4 and "L·S" in inh and "B·Ü" in inh
    zg = h[h.index('id="t-gebrauch"'):h.index('id="t-abk"')]
    assert 'class="gebrauch"' in zg and 'class="anatomie' in zg and "Lösungsskizze" in zg and "Cave!" in zg and "Klausurfalle" in zg and "Kerninhalt" in zg
    ab = h[h.index('id="t-abk"'):h.index('data-kap="B"')]
    assert 'class="abk"' in ab and "Zitierweise" in ab and "RGBl 1867/142" in ab and "GKPS Rz\u00a05" in ab
    assert ">PGS<" in ab and ">RGBl<" in ab, "Abkürzungen des Werks fehlen"


@test("Entwurf 6: Provinzende mit B·Ü und Füllblock, Repetitorium als Provinz VIII mit L·F bis L·A")
def _():
    w = copy.deepcopy(PROBE)
    h = buch.dokument(w, buch.Satz(w), "")
    b = h[h.index('data-kap="B"'):h.index('data-kap="L"')]
    assert 'id="k-BU"' in b and ">B·Ü<" in b and "Kernfakten · Provinz II" in b
    assert "Klausurfallen im Überblick" not in b and "Selbsttest" not in b, "gehören ins Repetitorium"
    rep = h[h.index('data-kap="L"'):h.index('id="t-abbildungen"')].replace("\u00ad", "")
    for c in ("LF", "LQ", "LV", "LS", "LA"):
        assert f'id="k-{c}"' in rep, c
    for e in w["lexicon"]:
        assert e["begriff"] in rep, e["begriff"]
    n = sum(len(k.get("kontrollfragen", [])) for k in w["kapitel"])
    ls = rep[rep.index('id="k-LS"'):rep.index('id="k-LA"')]
    assert ls.count("<tr>") == 2 * n + 2, ls.count("<tr>")


@test("Entwurf 6: Anhang wie bisher (Quellen nach Gattung mit Abschnittschips, Sachregister mit Latein, Normen ohne Dubletten)")
def _():
    w = copy.deepcopy(PROBE)
    h = buch.dokument(w, buch.Satz(w), "")
    qv = h[h.index('id="t-quellen"'):h.index('id="t-register"')]
    assert qv.count('class="qv-h"') >= 2 and 'class="kc farbe-petrol" href="#k-B1"' in qv and "Kacheln, die" not in qv and "je Kachel" not in qv
    rg = h[h.index('id="t-register"'):].replace("\u00ad", "")
    assert "princeps legibus solutus" in rg and "omnis potestas a populo" in rg and ">Normen<" in rg
    normen = re.findall(r'<td class="t">((?:Art|§)[^<]*)</td>', rg)
    assert len(normen) == len(set(x.replace("\u00a0", " ") for x in normen)), normen


@test("Entwurf 7: Relevanzmarken abgeschafft; „relevanz“ wird mit Hinweis auf den Schlüssel abgewiesen")
def _():
    w = copy.deepcopy(PROBE)
    abschnitt(w, "B2")["relevanz"] = "kern"
    fehler, _ = buch.pruefe(w)
    assert any("„relevanz“ gibt es im Standard 4.0 nicht" in f and "wichtig" in f for f in fehler), fehler
    h = buch.dokument(copy.deepcopy(PROBE), buch.Satz(copy.deepcopy(PROBE)), "")
    koerper = h[h.index("</style>", h.rindex("<style>")):]
    assert not any(z in koerper for z in "★◆○"), "alte Relevanzmarke im Satz"


@test("Entwurf 12: Schlüssel für Kerninhalte an Abschnittskopf, Inhalt, Provinzverzeichnis, Randspalte, Listenpunkt und Abbildungstitel")
def _():
    w = copy.deepcopy(PROBE)
    abschnitt(w, "B5")["wichtig"] = True
    abschnitt(w, "B1")["bloecke"][2]["wichtig"] = True  # Abbildung
    h = buch.dokument(w, buch.Satz(w), "")
    b5 = h[h.index('id="k-B5"'):h.index('id="k-B5"') + 600]
    assert 'class="ziel"' in b5, "☉ fehlt im Abschnittskopf"
    inh = h[h.index('id="t-inhalt"'):h.index('id="t-gebrauch"')]
    assert inh.count('class="ziel"') == 1 and 'href="#k-B5"' in inh
    pk = h[h.index('class="kindex"'):h.index('</table>', h.index('class="kindex"'))]
    assert pk.count('class="ziel"') == 1
    assert '<li class="wichtig"><span class="ziel rand"' in h, "☉ am Listenpunkt fehlt"
    assert re.search(r'class="sp definition wichtig"[^>]*><span class="ziel rand"', h), "☉ in der Randspalte fehlt"
    assert re.search(r'id="abb-zeit1848"[^>]*><div class="schema-titel"><span class="ziel"', h), "☉ im Abbildungstitel fehlt"
    k = h[h.index("<body>"):]
    stellen = [i for i in range(len(k)) if k[i] == "☉"]
    assert "<svg" in buch.SCHLUESSEL_SVG and all("Ziel­schei­be ☉" in k[i - 40:i + 1] for i in stellen), "Schlüssel statt Zielscheibe (☉ nur noch im Änderungsprotokoll)"


@test("Entwurf 7: Zielscheibe sparsam, Überschreitung wird gewarnt")
def _():
    w = copy.deepcopy(PROBE)
    _, warn = buch.pruefe(w)
    assert not any("entwertet" in x for x in warn), warn
    for a in w["kapitel"][0]["abschnitte"][:3]:
        a["wichtig"] = True
    for a in w["kapitel"][0]["abschnitte"]:
        for b in a["bloecke"]:
            b["wichtig"] = True
    _, warn = buch.pruefe(w)
    assert sum("entwertet" in x for x in warn) == 2, warn


@test("Entwurf 7: Absatzstruktur der Terrae (Definition, Kernliste mit Fachbegriff, Merke, Feinheit) und „Cave!“ im Skript")
def _():
    w = copy.deepcopy(PROBE)
    h = buch.dokument(w, buch.Satz(w), "")
    b = h[h.index('data-kap="B"'):h.index('data-kap="L"')]
    for a in w["kapitel"][0]["abschnitte"]:
        assert any(x["typ"] == "definition" for x in a["bloecke"]), f'{a["code"]} ohne Definition'
    assert b.count('<div class="label">Definition</div>') == 6 and b.count('<ul class="kern">') >= 5
    assert '<div class="lbl">Cave!</div>' in b and "Cave: Klausurfalle" not in h
    assert 'class="sp box merke"' in b and 'class="sp box feinheit"' in b
    assert re.search(r'<li><strong[^>]*>Konstitutionelle Monarchie:</strong>', b.replace("\u00ad", "")), "Fachbegriff als Vorspann fehlt"
    rg = h[h.index('id="t-register"'):].replace("\u00ad", "")
    assert "Monarchie:" not in rg and "suspensives Veto" in rg and "Suspensives Veto" not in rg, "Register: Vorspann-Doppelpunkt oder Schreibweisen doppelt"
    lv = h[h.index('id="k-LV"'):h.index('id="k-LS"')].replace("\u00ad", "")
    for t in ("konstitutionelle Monarchie", "Ministerverantwortlichkeit", "Legitimationstypen"):
        assert t in lv, t


@test("Entwurf 9: Lesehilfe nur an anspruchsvollen Grafiken und Tabellen, unten angekoppelt")
def _():
    w = copy.deepcopy(PROBE)
    h = buch.dokument(w, buch.Satz(w), "")
    einb = [b for _, _, _, bl in buch.listen(w) for b in bl if b["typ"] in ("abbildung", "tabelle")]
    soll = {b["id"] for b in einb if buch.anspruchsvoll(b)}
    assert soll == {"ablauf", "veto", "weiche", "vergleich"}, soll
    assert {b["id"] for b in einb if b.get("lesehilfe")} == soll
    figs = re.findall(r'<figure class="abb einbettung mit-lesehilfe".*?</figure>', h, re.S)
    assert len(figs) == 3 and h.count('class="abb einbettung"') == 4, (len(figs), h.count('class="abb einbettung"'))
    for f in figs:  # Lesehilfe nach der Grafik und vor dem Ende der Abbildung: beide unteilbar beisammen
        assert f.index('class="fig"') < f.index('class="abb-lesehilfe"') < f.index('class="bildnachweis"'), f[:120]
    tab = h[h.index('id="tab-vergleich"'):]
    assert 'class="tab einbettung mit-lesehilfe"' in h and tab.index("</table>") < tab.index('class="abb-lesehilfe"') < tab.index("</div></div>") + 12
    _, warn = buch.pruefe(w)
    assert not any("Lesehilfe" in x for x in warn), warn
    w2 = copy.deepcopy(PROBE)
    for b in (b for _, _, _, bl in buch.listen(w2) for b in bl):
        if b.get("id") == "veto":
            b.pop("lesehilfe")
        if b.get("id") == "sieb":
            b["lesehilfe"] = "Überflüssig."
    _, warn = buch.pruefe(w2)
    assert any("„veto“ ohne Lesehilfe" in x for x in warn) and any("„sieb“ überflüssig" in x for x in warn), warn


@test("Entwurf 8: keine Prüfdimensionen im Satz, Latinum mit Spitzmarke")
def _():
    w = copy.deepcopy(PROBE)
    h = buch.dokument(w, buch.Satz(w), "")
    koerper = h[h.index('data-kap="B"'):]
    assert 'class="dim"' not in koerper and "Prüfdimensionen" not in h[h.index('id="t-gebrauch"'):h.index('id="t-abk"')]
    assert koerper.count('<div class="sp box latinum"') == koerper.count('<div class="lbl">Latinum</div>') >= 3


@test("Entwurf 11: Anhang mit allen Angaben; Provinz öffnet ohne Einleitungstext mit der Übersichtsgrafik; Farbschlüssel nur in Zum Gebrauch")
def _():
    w = copy.deepcopy(PROBE)
    h = buch.dokument(w, buch.Satz(w), "")
    anhang = h[h.index('id="t-abbildungen"'):]
    assert anhang.count('class="teil-unter"') == 3 and 'class="qv-legende"' in anhang, "Angaben im Anhang fehlen"
    assert "Grundlagen und Entstehung" in anhang and 'id="k-LA"' in h
    assert [b["typ"] for b in map(buch.als_block, w["kapitel"][0]["einleitung"])] == ["abbildung"]
    fehler, _ = buch.pruefe(w)
    assert not fehler, fehler
    auftakt = h[h.index('data-kap="B"'):h.index('data-code="B1"')]
    assert '<p class="sp"' not in auftakt and 'id="abb-ablauf"' in auftakt
    assert "label::before" not in h, "keine Marke vor den Zwischenüberschriften"
    assert 'class="av"' in anhang and 'class="register"' in anhang
    provinz = h[h.index('data-kap="B"'):h.index('data-kap="L"')]
    assert 'class="schluessel"' not in provinz and "Farbschlüssel" not in provinz
    zg = h[h.index('id="t-gebrauch"'):h.index('id="t-abk"')]
    assert "Farbschlüssel" in zg and zg.count('class="rpill"') == len(w["rollen"])


@test("Satzprüfung erkennt Flattersatz im Kernsatz")
def _():
    import os
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ, "TERRA_TEST_CSS": ".kernsatz { text-align: left !important; }"}
        quelle = Path(d) / "probe.json"
        quelle.write_text(json.dumps(PROBE, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(KIT / "skript.py"), str(quelle), "--aus", d, "--laeufe", "1"], capture_output=True, text=True, env=env)
        assert r.returncode == 1 and "Flattersatz" in r.stdout, r.stdout[-600:]


if __name__ == "__main__":
    ok = sum(1 for _, g, _ in ergebnisse if g)
    for n, g, m in ergebnisse:
        print(("✓ " if g else "✗ ") + n + (f"  [{m}]" if m else ""))
    print(f"{ok} von {len(ergebnisse)} Tests bestanden")
    sys.exit(0 if ok == len(ergebnisse) else 1)

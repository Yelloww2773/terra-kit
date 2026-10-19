#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit · anki.py (Standard 3.1)

Erzeugt aus einer werk.json ein importierbares Anki-Deck (.apkg, auch für AnkiDroid).

Kartenlogik: je Baustein eine oder mehrere Karten (siehe README). Fallbeispiele nur zur
Veranschaulichung auf der Rückseite der Definitionskarte. Abbildungen (Kurve, Fluss, SVG,
T-Konto) als Bilder. Unterdecks je Provinz, Schlagwörter je Kachel und Relevanz.
Feste Kennungen: Ein erneuter Import aktualisiert Karten, statt sie zu verdoppeln.

Aufruf:  python3 anki.py werk.json [--aus ORDNER]
"""
import argparse
import hashlib
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

import genanki

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT))
import skript as S  # noqa: E402
from validate import validiere  # noqa: E402

VERSION = "3.1.1"
esc = S.esc
FS = KIT / "node_modules" / "@fontsource"
SCHRIFTEN = [  # (Datei in node_modules, Familie, Gewicht, Stil, Zeichenbereich)
    ("cormorant-garamond/files/cormorant-garamond-latin-600-normal.woff2", "Terra Titel", 600, "normal", "latin"),
    ("cormorant-garamond/files/cormorant-garamond-latin-500-italic.woff2", "Terra Titel", 500, "italic", "latin"),
    ("cormorant-garamond/files/cormorant-garamond-latin-ext-500-normal.woff2", "Terra Titel", 600, "normal", "ext"),
    ("spectral/files/spectral-latin-400-normal.woff2", "Terra Text", 400, "normal", "latin"),
    ("spectral/files/spectral-latin-400-italic.woff2", "Terra Text", 400, "italic", "latin"),
    ("spectral/files/spectral-latin-600-normal.woff2", "Terra Text", 600, "normal", "latin"),
    ("spectral/files/spectral-latin-ext-400-normal.woff2", "Terra Text", 400, "normal", "ext"),
    ("spectral/files/spectral-latin-ext-400-italic.woff2", "Terra Text", 400, "italic", "ext"),
    ("alegreya-sans/files/alegreya-sans-latin-400-normal.woff2", "Terra UI", 400, "normal", "latin"),
    ("alegreya-sans/files/alegreya-sans-latin-700-normal.woff2", "Terra UI", 700, "normal", "latin"),
]
BEREICH = {"latin": "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215",
           "ext": "U+0100-02AF, U+1E00-1EFF, U+2020, U+20A0-20AB, U+20AD-20CF, U+2C60-2C7F, U+A720-A7FF"}


def stabile_id(*teile):
    return int(hashlib.sha1("|".join(teile).encode("utf-8")).hexdigest()[:12], 16) % (1 << 31) + (1 << 30)


def css():
    faces = "\n".join(
        f'@font-face {{ font-family: "{fam}"; font-weight: {w}; font-style: {st}; src: url("_terra_{Path(d).name}") format("woff2"); unicode-range: {BEREICH[b]}; }}'
        for d, fam, w, st, b in SCHRIFTEN)
    return faces + """
.card { --papier: #FCFAF5; --kachel: #FFFDF8; --tinte: #1F2A44; --tinte2: #4A5468; --linie: #D9CFBC; --ocker: #A8742A;
  --merke: #F8EED6; --merke-bar: #C9A24A; --fein: #EFEDE8; --fein-bar: #6F7884; --falle: #F7E4E1; --falle-bar: #A33B32;
  font-family: "Terra Text", Georgia, serif; font-size: 18px; line-height: 1.5; color: var(--tinte); background: var(--papier); text-align: left; }
.nightMode.card, .night_mode .card, .card.night_mode { --papier: #1A1D23; --kachel: #22262D; --tinte: #E9E4D8; --tinte2: #B8B2A5; --linie: #3B414C; --ocker: #D6A95E;
  --merke: #3A321F; --merke-bar: #C9A24A; --fein: #2C3036; --fein-bar: #8A949E; --falle: #3E2522; --falle-bar: #E07A64; }
.terra { max-width: 680px; margin: 0 auto; padding: 14px 16px 10px; }
.kontext { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px; padding-bottom: 8px; margin-bottom: 14px; border-bottom: 2px solid var(--p); }
.chip { font: 700 12px "Terra UI", sans-serif; color: #fff; background: var(--p); padding: 3px 7px; border-radius: 3px; }
.nightMode .chip, .night_mode .chip { color: #15171C; background: var(--pd, var(--p)); }
.kontext .kt { font: 600 19px "Terra Titel", Georgia, serif; }
.kontext .kt b { color: var(--p); margin-right: 6px; font-variant-numeric: lining-nums; font-feature-settings: "lnum" 1; }
.nightMode .kontext .kt b, .night_mode .kontext .kt b { color: var(--pd, var(--p)); }
.kontext .rel { color: var(--ocker); font-size: 14px; }
.art { font: 700 12px "Terra UI", sans-serif; letter-spacing: .08em; text-transform: uppercase; color: var(--tinte2); margin-bottom: 4px; }
.frage { font-size: 20px; font-weight: 400; }
.frage.lat { font: italic 500 24px "Terra Titel", Georgia, serif; }
hr#answer { border: 0; border-top: 1px dashed var(--linie); margin: 16px 0; }
.antwort ul { margin: 4px 0; padding-left: 22px; } .antwort li { margin-bottom: 4px; }
.antwort .zitat { margin: 6px 0; padding: 8px 12px; border-left: 4px double var(--p); background: var(--kachel); font-style: italic; }
.antwort .quelle, .norm { display: block; margin-top: 6px; font: 600 13px "Terra UI", sans-serif; color: var(--ocker); }
.box { margin-top: 10px; padding: 8px 12px; border-left: 4px solid var(--merke-bar); background: var(--merke); border-radius: 0 4px 4px 0; }
.box.fein { border-color: var(--fein-bar); background: var(--fein); } .box.falle { border-color: var(--falle-bar); background: var(--falle); }
.bsp { margin-top: 14px; font-size: 15.5px; border: 1px solid var(--tinte); border-radius: 3px; }
.bsp summary { cursor: pointer; padding: 6px 10px; font: 700 13px "Terra UI", sans-serif; background: var(--tinte); color: var(--papier); }
.bsp div { padding: 8px 12px; } .bsp .sv { font-style: italic; }
.bild img { max-width: 100%; height: auto; margin-top: 8px; border-radius: 4px; background: #FFFDF8; }
.vw { color: var(--p); font: 600 15px "Terra UI", sans-serif; white-space: nowrap; }
mark { background: none; color: inherit; }
.fuss { margin-top: 18px; padding-top: 6px; border-top: 1px solid var(--linie); font: 400 11.5px "Terra UI", sans-serif; color: var(--tinte2); opacity: .8; }
"""


VORNE = """<div class="terra" style="--p: {{Farbe}}; --pd: {{FarbeDunkel}}">
<div class="kontext"><span class="chip">{{Provinz}}</span><span class="kt"><b>{{Code}}</b>{{Kacheltitel}}</span><span class="rel">{{Relevanz}}</span></div>
<div class="art">{{Art}}</div><div class="frage {{Klasse}}">{{Vorderseite}}</div>
<div class="fuss">(c) Oliver Bedernik · {{Werk}}{{#Fundstelle}} · {{Fundstelle}}{{/Fundstelle}}</div></div>"""
HINTEN = """<div class="terra" style="--p: {{Farbe}}; --pd: {{FarbeDunkel}}">
<div class="kontext"><span class="chip">{{Provinz}}</span><span class="kt"><b>{{Code}}</b>{{Kacheltitel}}</span><span class="rel">{{Relevanz}}</span></div>
<div class="art">{{Art}}</div><div class="frage {{Klasse}}">{{Vorderseite}}</div>
<hr id="answer">
<div class="antwort">{{Rückseite}}</div>
{{#Bild}}<div class="bild">{{Bild}}</div>{{/Bild}}
{{#Beispiel}}<details class="bsp"><summary>Fallbeispiel (nur zur Veranschaulichung)</summary><div>{{Beispiel}}</div></details>{{/Beispiel}}
<div class="fuss">(c) Oliver Bedernik · {{Werk}}{{#Fundstelle}} · {{Fundstelle}}{{/Fundstelle}}</div></div>"""
FELDER = ["Vorderseite", "Rückseite", "Art", "Klasse", "Bild", "Beispiel", "Provinz", "Code", "Kacheltitel", "Relevanz",
          "Fundstelle", "Farbe", "FarbeDunkel", "Werk", "Schlüssel"]


def modell():
    return genanki.Model(stabile_id("terra-modell", VERSION.split(".")[0]), "Terra · Karte",
                         fields=[{"name": f} for f in FELDER],
                         templates=[{"name": "Terra", "qfmt": VORNE, "afmt": HINTEN}], css=css(), sort_field_index=0)


def nur_text(h):
    return re.sub(r"<a class=\"vw\" href=\"#k-([^\"]+)\">[^<]*</a>", r'<span class="vw">→ \1</span>', h)


def m(t, latein=False):
    return nur_text(S.md(t, latein=latein))


def liste(punkte):
    return "<ul>" + "".join(f"<li>{m(p)}</li>" for p in punkte) + "</ul>"


def tex(t, block=True):
    return ("\\[" if block else "\\(") + html.escape(t, quote=False) + ("\\]" if block else "\\)")


# ── Abbildungen ──────────────────────────────────────────────────────────
def render_bilder(auftraege, ordner):
    """auftraege: [(dateiname, schema_html, farbe)] → PNG-Dateien in ordner."""
    if not auftraege:
        return []
    from playwright.sync_api import sync_playwright
    kopf = (S.schrift_links() + f'<link rel="stylesheet" href="{(KIT / "vorlage" / "skript.css").as_uri()}"><style>{S.palette_css()}'
            "body{background:#FFFDF8;margin:0} .bildrahmen{width:640px;padding:14px 16px;background:#FFFDF8}</style>")
    pfade = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--allow-file-access-from-files"])
        pg = br.new_page(device_scale_factor=2)
        seite = ordner / "_bild_vorlage.html"
        for name, inhalt, farbe in auftraege:
            seite.write_text(f'<html lang="de-AT"><head><meta charset="utf-8">{kopf}</head><body><div class="bildrahmen farbe-{farbe}">{inhalt}</div></body></html>',
                             encoding="utf-8")
            pg.goto(seite.as_uri()); pg.wait_for_function("document.fonts.ready.then(() => true)"); pg.wait_for_timeout(120)
            ziel = ordner / name
            pg.locator(".bildrahmen").screenshot(path=str(ziel))
            pfade.append(ziel)
        br.close()
        seite.unlink()
    return pfade


# ── Karten ───────────────────────────────────────────────────────────────
def karten(werk, ordner):
    S._HYPH = None
    S.farben_zuweisen(werk)
    import karte as KA  # Dunkelvarianten der Provinzfarben
    kx = S.katex_alle(werk, output="mathml")  # nur zur Kontrolle; Anki setzt Formeln mit MathJax
    dunkel = {}
    for n, (p, _) in S.PALETTE.items():
        L, C, h = KA.hex_oklch(p)
        dunkel[n] = KA.oklch_hex(0.76, C * (1.0 if C < 0.04 else 1.1), h)
    w = werk["meta"]
    kurz = w.get("kurz") or w["titel"].split()[-1][:3].upper()
    notizen, bilder = [], []
    zaehler = Counter()

    def neu(p, k, art, vorne, hinten, schluessel, klasse="", bild="", beispiel="", fundstelle=None, code=None, titel=None, rel=None):
        zaehler[art] += 1
        rel = rel if rel is not None else (k["relevanz"] if k else "kern")
        notizen.append({
            "felder": {"Vorderseite": vorne, "Rückseite": hinten, "Art": art, "Klasse": klasse, "Bild": bild, "Beispiel": beispiel,
                       "Provinz": f'{p["nr"]} {esc(p["name_lat"])}', "Code": code if code is not None else (k["code"] if k else p["code"]),
                       "Kacheltitel": esc(titel if titel is not None else (k["titel"] if k else p["name_de"])),
                       "Relevanz": S.RELEVANZ.get(rel, ("", ""))[0],
                       "Fundstelle": S.typo(esc(fundstelle if fundstelle is not None else ((k["anker"] + (" · " + k["seite"] if k.get("seite") else "")) if k else ""))),
                       "Farbe": S.PALETTE[p["farbe"]][0], "FarbeDunkel": dunkel[p["farbe"]], "Werk": esc(w["titel"]), "Schlüssel": schluessel},
            "guid": genanki.guid_for(kurz, schluessel),
            "tags": [f'Terra::{w["titel"].replace(" ", "_")}', f'Provinz::{p["code"]}', f'Kachel::{(k or {}).get("code", p["code"])}', f"Relevanz::{rel}", f"Art::{art.replace(' ', '_')}"],
            "deck": f'{p["nr"]} {p["name_lat"]}'})

    for p in werk["provinzen"]:
        neu(p, None, "In 60 Sekunden", m(p["leitfrage"]), liste(p["kompakt"]), f'{p["code"]}:kompakt', code=p["code"],
            titel=p["name_de"], fundstelle=", ".join(p["anker"]), rel="kern")
        for k in p["kacheln"]:
            beispiele = [b for b in k["bausteine"] if b["typ"] == "beispiel"]
            bsp = "".join(f'<div class="sv">{m(b["sachverhalt"])}</div>' + (f'<div><b>Lösung:</b> {m(b["loesung"])}</div>' if b.get("loesung") else "")
                          for b in beispiele)
            for i, b in enumerate(k["bausteine"]):
                t, sk = b["typ"], f'{k["code"]}:{i}'
                if t == "definition":
                    neu(p, k, "Definition", "Wie lautet die Definition?", m(b["text"]), sk, beispiel=bsp)
                    if b.get("zitat"):
                        neu(p, k, "Normwortlaut", f'Wortlaut: {S.typo(esc(b["zitat"]["quelle"]))}',
                            f'<div class="zitat">„{m(b["zitat"]["text"], latein=True)}“</div>', sk + ":zitat", fundstelle=b["zitat"]["quelle"])
                elif t == "kern":
                    neu(p, k, "Kernpunkte", esc(b["titel"]) if b.get("titel") else "Welche Kernpunkte gelten?", liste(b["punkte"]), sk)
                elif t in ("merke", "feinheit", "klausurfalle"):
                    art = {"merke": "Merke", "feinheit": "Feinheit", "klausurfalle": "Klausurfalle"}[t]
                    cls = {"merke": "", "feinheit": " fein", "klausurfalle": " falle"}[t]
                    frage = {"merke": "Was ist hier zu merken?", "feinheit": "Welche Feinheit gilt hier?", "klausurfalle": "Welche Klausurfalle droht hier?"}[t]
                    neu(p, k, art, frage, f'<div class="box{cls}">{m(b["text"])}</div>', sk)
                elif t == "austriacum":
                    neu(p, k, "Österreichbezug", "Welcher Bezug zum österreichischen Recht besteht?", m(b["text"]) + f'<span class="norm">{S.typo(esc(b["norm"]))}</span>', sk)
                elif t == "aktualisierung":
                    neu(p, k, "Aktualisierung", "Was hat sich nach Redaktionsschluss der Quelle geändert?", m(b["text"]) + f'<span class="norm">seit {b["datum"]} · {esc(b["quelle"])}</span>', sk)
                elif t == "latinum":
                    neu(p, k, "Latinum", m(b["lat"], latein=True), m(b["de"]) + f'<span class="quelle">{m(b["stelle"], latein=True)}</span>', sk, klasse="lat")
                elif t == "formel":
                    var = "".join(f"<li>{tex(v['symbol'], False)}: {m(v['bedeutung'])}</li>" for v in b.get("variablen", []))
                    neu(p, k, "Formel", f'Wie lautet die Formel {esc(b.get("nummer", ""))}?'.replace(" ?", "?"), tex(b["tex"]) + (f"<ul>{var}</ul>" if var else ""), sk)
                elif t == "rechenweg":
                    schritte = "".join(f"<li>{m(s['text'])}" + (f"<br>{tex(s['tex'], False)}" if s.get("tex") else "") + "</li>" for s in b["schritte"])
                    neu(p, k, "Rechenweg", m(b.get("aufgabe") or k["titel"]), f"<ol>{schritte}</ol><b>Ergebnis:</b> {m(b['ergebnis'])}", sk)
                elif t == "schema":
                    v, titel = b["variante"], b["titel"]
                    if v == "zeitleiste":
                        for j, e in enumerate(b["ereignisse"]):
                            neu(p, k, "Zeitleiste", f'{esc(e["datum"])}<br><small>{esc(titel)}</small>', m(e["text"]), f"{sk}:{j}")
                    elif v == "abgrenzung":
                        for j, kr in enumerate(b["kriterien"]):
                            neu(p, k, "Abgrenzung", f'{m(kr["kriterium"])}<br><small>{esc(b["links"])} oder {esc(b["rechts"])}?</small>',
                                f'<ul><li><b>{esc(b["links"])}:</b> {m(kr["links"])}</li><li><b>{esc(b["rechts"])}:</b> {m(kr["rechts"])}</li></ul>', f"{sk}:{j}")
                    elif v == "tabelle":
                        for j, z in enumerate(b["zeilen"]):
                            rest = "".join(f'<li><b>{esc(h)}:</b> {m(c)}</li>' for h, c in zip(b["kopf"][1:], z[1:]))
                            neu(p, k, "Tabelle", f'{m(z[0], latein=True)}<br><small>{esc(titel)}: {esc(", ".join(b["kopf"][1:]))}?</small>', f"<ul>{rest}</ul>", f"{sk}:{j}")
                    else:  # kurve, fluss, svg, tkonto als Bild
                        name = f"terra_{kurz}_{k['code']}_{i}.png"
                        bilder.append((name, S.schema_html(b), p["farbe"]))
                        hinten = f'<b>Buchungssatz:</b> {m(b["buchungssatz"])}' if v == "tkonto" and b.get("buchungssatz") else (m(b["beschreibung"]) if v == "svg" else "")
                        neu(p, k, "Abbildung", f'{esc(titel)}', hinten, sk, bild=f'<img src="{name}">')
        # Lexicon-Einträge der Provinz L und Werk-Lexikon
    lp = next((p for p in werk["provinzen"] if p["code"] == "L"), werk["provinzen"][-1])
    kmap = {k["code"]: (p, k) for p in werk["provinzen"] for k in p["kacheln"]}
    for j, e in enumerate(werk.get("lexicon", [])):
        p, k = kmap.get(e["kachel"], (lp, None))
        neu(p, k, "Latinum" if e.get("sprache", "la") == "la" else "Terminus", m(e["begriff"], latein=True), m(e["bedeutung"]), f"lex:{j}", klasse="lat")
    for j, s in enumerate(werk.get("selbsttest", [])):
        p, k = kmap.get(s["kachel"], (lp, None))
        neu(p, k, "Selbsttest", m(s["frage"]), m(s["antwort"]), f"test:{j}")
    for j, q in enumerate(werk.get("quellenkritik", [])):
        p, k = kmap.get(q["kachel"], (lp, None))
        neu(p, k, "Quellenkritik", f'Was ist falsch an: {m(q["befund"])}', m(q["richtig"]) + f'<span class="quelle">{m(q["quelle"])}</span>', f"kritik:{j}")
    return notizen, render_bilder(bilder, ordner), zaehler


def baue(werk, aus):
    w = werk["meta"]
    aus.mkdir(parents=True, exist_ok=True)
    medien = aus / "medien"
    medien.mkdir(exist_ok=True)
    notizen, bildpfade, zaehler = karten(werk, medien)
    mod = modell()
    decks = {}
    stamm = f'Terra::{w["titel"]}'
    for n in notizen:
        dn = f'{stamm}::{n["deck"]}'
        if dn not in decks:
            decks[dn] = genanki.Deck(stabile_id("terra-deck", w["titel"], n["deck"]), dn)
        decks[dn].add_note(genanki.Note(model=mod, fields=[n["felder"][f] for f in FELDER], guid=n["guid"], tags=n["tags"]))
    schriften = []
    for d, *_ in SCHRIFTEN:
        ziel = medien / f"_terra_{Path(d).name}"
        ziel.write_bytes((FS / d).read_bytes())
        schriften.append(ziel)
    paket = genanki.Package(list(decks.values()))
    paket.media_files = [str(p) for p in bildpfade + schriften]
    datei = aus / (S.dateiname(werk) + "_Anki.apkg")
    paket.write_to_file(str(datei))
    return datei, notizen, zaehler, bildpfade


def pruefe(datei, notizen):
    """Öffnet das Paket wie Anki: Anzahl Notizen, Medien, Gedankenstriche, Kennungen eindeutig."""
    import sqlite3, tempfile, zipfile
    befund = {"fehler": []}
    with tempfile.TemporaryDirectory() as t, zipfile.ZipFile(datei) as z:
        z.extractall(t)
        con = sqlite3.connect(Path(t) / "collection.anki2")
        befund["notizen"] = con.execute("select count(*) from notes").fetchone()[0]
        befund["karten"] = con.execute("select count(*) from cards").fetchone()[0]
        felder = [r[0] for r in con.execute("select flds from notes")]
        guids = [r[0] for r in con.execute("select guid from notes")]
        medien = json.loads((Path(t) / "media").read_text())
        befund["medien"] = len(medien)
        fehlend = [n for n in medien.values() if not (Path(t) / [k for k, v in medien.items() if v == n][0]).exists()]
        if fehlend:
            befund["fehler"].append(f"Mediendateien fehlen: {fehlend[:3]}")
        bilder = set(re.findall(r'src="([^"]+)"', " ".join(felder)))
        if bilder - set(medien.values()):
            befund["fehler"].append(f"Bild ohne Mediendatei: {sorted(bilder - set(medien.values()))[:3]}")
    if befund["notizen"] != len(notizen):
        befund["fehler"].append(f"{befund['notizen']} Notizen im Paket, {len(notizen)} erzeugt")
    if len(set(guids)) != len(guids):
        befund["fehler"].append("Kennungen nicht eindeutig")
    striche = sum(len(re.findall("[\u2012\u2013\u2014\u2015]", f)) for f in felder)
    if striche:
        befund["fehler"].append(f"{striche} Gedankenstriche in Kartenfeldern")
    return befund


def main():
    ap = argparse.ArgumentParser(description="Terra-Anki-Deck")
    ap.add_argument("werk")
    ap.add_argument("--aus", default=".")
    a = ap.parse_args()
    werk = json.loads(Path(a.werk).read_text(encoding="utf-8"))
    v = validiere(werk)
    if v.fehler:
        print("\n".join(v.fehler))
        sys.exit("Abbruch: werk.json fehlerhaft")
    datei, notizen, zaehler, bilder = baue(werk, Path(a.aus).resolve())
    b = pruefe(datei, notizen)
    print(f"Deck: {datei.name} · {datei.stat().st_size // 1024} KB · {b['notizen']} Notizen, {b['karten']} Karten, {len(bilder)} Abbildungen, {b['medien']} Mediendateien")
    print("Karten je Art: " + ", ".join(f"{k} {n}" for k, n in zaehler.most_common()))
    for z in b["fehler"]:
        print("FEHLER  ", z)
    print(f"Ergebnis: {len(b['fehler'])} Fehler")
    sys.exit(1 if b["fehler"] else 0)


if __name__ == "__main__":
    main()

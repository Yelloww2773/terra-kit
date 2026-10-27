#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit · karte.py (Standard 3.1)

Erzeugt aus einer werk.json die interaktive Wissenslandkarte (Format A) als eine
selbstständige HTML-Datei zur Veröffentlichung als Artifact.

Satz der Kacheln, Formeln und Diagramme kommt unverändert aus skript.py (eine Quelle).
Formeln als MathML (keine fremden Schriftdateien nötig). Schriften über Google Fonts;
mit --lokal stattdessen aus node_modules (für Tests ohne Netz).

Aufruf:  python3 karte.py werk.json [--aus ORDNER] [--lokal]
"""
import argparse
import html
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT))
import skript as S  # noqa: E402
from validate import validiere  # noqa: E402

VERSION = (Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8").strip()
GOOGLE = ("https://fonts.googleapis.com/css2?family=Alegreya+Sans:ital,wght@0,400;0,500;0,700;1,400"
          "&family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,500;1,600"
          "&family=Spectral:ital,wght@0,400;0,500;0,600;1,400;1,600&display=swap")
esc = S.esc


# ── Farbraum: Dunkelvarianten der Provinzpalette (gleicher Farbton) ───────
def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _delin(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_oklch(hx):
    r, g, b = (_lin(int(hx[i:i + 2], 16) / 255) for i in (1, 3, 5))
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def oklch_hex(L, C, h):
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    l_, m_, s_ = L + 0.3963377774 * a + 0.2158037573 * b, L - 0.1055613458 * a - 0.0638541728 * b, L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    return "#" + "".join(f"{round(max(0, min(1, _delin(max(0, v)))) * 255):02X}" for v in rgb)


def palette_dunkel_css():
    zeilen = []
    for n, (p, _) in S.PALETTE.items():
        L, C, h = hex_oklch(p)
        neutral = C < 0.04
        zeilen.append(f".farbe-{n} {{ --p: {oklch_hex(0.76, C * (1.0 if neutral else 1.1), h)}; --p-hell: {oklch_hex(0.30, 0.02 if neutral else 0.035, h)}; }}")
    blk = "\n".join(zeilen)
    return (f"@media (prefers-color-scheme: dark) {{\n:root:not([data-theme=\"light\"]) {{}}\n" +
            "\n".join(f":root:not([data-theme=\"light\"]) {z}" for z in zeilen) + "\n}\n" +
            "\n".join(f":root[data-theme=\"dark\"] {z}" for z in zeilen))


# ── Bausteine ────────────────────────────────────────────────────────────
def kachel_html(k, farbe, kx):
    breit = any(b.get("typ") == "schema" and b.get("variante") == "tabelle" and b.get("breit") for b in k["bausteine"])
    inhalt = S.kachelkopf(k) + "".join(
        f'<div class="unit"><div class="bs bs-{b["typ"]}">{S.baustein_html(b, kx)}</div></div>' for b in k["bausteine"])
    return (f'<article class="kachel karte-kachel farbe-{farbe}{" breit" if breit else ""}" data-code="{k["code"]}" '
            f'data-rel="{k["relevanz"]}">{inhalt}</article>')


def gen_kachel_html(code, unit_html):
    return f'<article class="kachel karte-kachel farbe-tinte" data-code="{code}" data-rel="kern">{unit_html}</article>'


def klartext(h):
    t = re.sub(r"<annotation[^>]*>.*?</annotation>", " ", h, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t).replace("\u00ad", "")
    return re.sub(r"\s+", " ", t).strip()


def such(t):
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("ß", "ss")


def provinzkopf(p):
    kompakt = "".join(f"<li>{S.md(s)}</li>" for s in p["kompakt"])
    return (f'<header class="rkopf"><span class="pchip">Provinz {p["nr"]} ({p["code"]})</span>'
            f'<h2>{S.md(p["name_lat"], latein=True)}</h2><div class="rde">{S.md(p["name_de"], latein=True)}</div>'
            f'<div class="leitfrage"><b>Leitfrage</b>{S.md(p["leitfrage"])}</div>'
            f'<div class="kompakt"><b>In 60 Sekunden</b><ol>{kompakt}</ol></div>'
            f'<div class="panker">{S.typo(" · ".join(esc(a) for a in p["anker"]))}{" · " + esc(p["seiten"]) if p.get("seiten") else ""}</div></header>')


def startfeld(werk):
    m, mo = werk["meta"], werk["motto"]
    typen = {b["typ"] for p in werk["provinzen"] for k in p["kacheln"] for b in k["bausteine"]}
    proben = []
    for t, txt in [("merke", "prüfungsrelevanter Kernsatz"), ("feinheit", "Nuance, Ausnahme, Streitstand"),
                   ("klausurfalle", "typischer Prüfungsfehler"), ("austriacum", "Bezug zum österreichischen Recht"),
                   ("aktualisierung", "Rechtslage nach Redaktionsschluss der Quelle"), ("luecke", "in der Quelle fehlend, sinngemäß ergänzt")]:
        if t in typen:
            proben.append(f'<div class="box {t}"><div class="lbl">{S.LABEL[t]}</div>{txt}</div>')
    if "latinum" in typen:
        proben.append('<div class="box latinum"><span class="lat">Latinum</span><span class="stelle">Proverbium oder Fachbegriff mit Übersetzung und Stelle</span></div>')
    reihe = m.get("reihe") or "Lernskripten zur Prüfungsvorbereitung"
    lv = f'<div class="lv">{S.md(m["lehrveranstaltung"], latein=True)}</div>' if m.get("lehrveranstaltung") else ""
    return (
        '<section class="region start farbe-tinte" id="r-start" data-farbe="tinte">'
        f'<div class="landname">{esc(m["titel"].replace("Terra ", "", 1))}<small>Terra</small></div>'
        f'<div class="kartusche startkopf"><div class="reihe">{S.md(reihe, latein=True)}</div><h1>{esc(m["titel"])}</h1>'
        f'<div class="unter">{S.md(m["untertitel"], latein=True)}</div>{lv}'
        f'<div class="ausgabe">Version {esc(m["version"])} · {S.stand_text(werk)} · (c) Oliver Bedernik</div></div>'
        '<div class="startinhalt"><div>'
        f'<h3>Motto</h3><div class="box latinum"><span class="lat">{S.md(mo["lat"], latein=True)}</span><span class="de">{S.md(mo["de"])}</span>'
        f'<span class="stelle">{S.md(mo["stelle"], latein=True)}</span></div>'
        '<h3 style="margin-top:18px">Bedienung</h3><dl class="bedienung">'
        '<dt>Bewegen</dt><dd>Ziehen mit Maus oder Finger; Trackpad mit zwei Fingern; Pfeiltasten.</dd>'
        '<dt>Zoomen</dt><dd>Mausrad, Zwei-Finger-Geste oder die Knöpfe unten; Taste 0 zeigt die ganze Karte.</dd>'
        '<dt>Springen</dt><dd>Provinzleiste unten, Register oder Suche (Taste /); Doppelklick auf eine Kachel holt sie heran.</dd>'
        '<dt>Verweise</dt><dd>Codes wie A1 im Text sind anklickbar und führen zur Kachel.</dd></dl></div>'
        f'<div><h3>Bausteine</h3>{"".join(proben)}'
        '<p style="font-size:13px;color:var(--tinte-2);margin-top:10px">★ Kernstoff · ◆ Vertiefung · ○ laut Lehrveranstaltung auslassbar. '
        'Die Marken sind eine Einschätzung.</p></div></div></section>')


def info_paneel(werk):
    m, mo = werk["meta"], werk["modul"]
    erste = werk["provinzen"][0]["kacheln"][0]["code"]
    zeilen = [("Werk", f'{esc(m["titel"])}: {S.md(m["untertitel"])}'), ("Ausgabe", f'Version {esc(m["version"])}, {S.stand_text(werk)}')]
    if m.get("lehrveranstaltung"):
        zeilen.append(("Lehrveranstaltung", S.md(m["lehrveranstaltung"])))
    zeilen += [("Primärquelle", S.md(mo["primaerquelle"])), ("Sekundärquelle", S.md(mo["sekundaerquelle"])),
               ("Quellen", "; ".join(S.zitat_voll(q, S.zitierstil(werk)) for q in werk.get("quellen", [])) or "keine"),
               ("Zitiervorschlag", f'<i>Bedernik</i>, {esc(m["titel"])} ({m["stand"][:4]}) Kachel {erste}'),
               ("Inhaltsgleich", "Lernskript (PDF) und Exam aus derselben Datenquelle, gleiche Kachelcodes"),
               ("Tastatur", "+ und − zoomen, 0 ganze Karte, / Suche, Pfeiltasten bewegen, Esc schließt"),
               ("Urheber", "<b>(c) Oliver Bedernik</b>. Alle Rechte vorbehalten." + S.HAFTUNG.get(mo["domaene"], "").replace(" und ersetzt", " Ersetzt") + ".")]
    dl = "".join(f"<dt>{a}</dt><dd>{b}</dd>" for a, b in zeilen)
    return (f'<aside class="paneel" id="info" aria-label="Über diese Karte"><header><h2>Über diese Karte</h2>'
            f'<button class="knopf schliessen" aria-label="Schließen">✕</button></header><div class="inhalt info"><dl>{dl}</dl></div></aside>')


ICON = {
    "suche": '<svg viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21"/></svg>',
    "register": '<svg viewBox="0 0 24 24"><path d="M5 5h14M5 10h14M5 15h9M5 20h9"/></svg>',
    "stern": '<svg viewBox="0 0 24 24"><path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z"/></svg>',
    "mini": '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><rect x="12" y="11" width="6" height="5"/></svg>',
    "thema": '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 0 0 16Z" fill="currentColor"/></svg>',
    "info": '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>',
    "plus": '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
    "minus": '<svg viewBox="0 0 24 24"><path d="M5 12h14"/></svg>',
    "fit": '<svg viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
    "ganz": '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="8" height="7"/><rect x="13" y="4" width="8" height="7"/><rect x="3" y="13" width="8" height="7"/><rect x="13" y="13" width="8" height="7"/></svg>',
}


def wasserzeichen():
    return ('<svg class="wz-muster" aria-hidden="true" width="100%" height="100%"><defs><pattern id="wzp" width="560" height="320" '
            'patternUnits="userSpaceOnUse" patternTransform="rotate(-28)"><text x="24" y="170" fill="currentColor" '
            'style="font: 600 46px \'Cormorant Garamond\', Georgia, serif">(c) Oliver Bedernik</text></pattern></defs>'
            '<rect width="100%" height="100%" fill="url(#wzp)"/></svg>')


def css_basis():
    c = (KIT / "vorlage" / "skript.css").read_text(encoding="utf-8")
    c = re.sub(r"@font-face \{[^}]*Terra Symbole[^}]*\}\s*", "", c)
    c = re.sub(r"@page[^{]*\{[^}]*\}\s*", "", c)
    c = re.sub(r'"Terra Symbole", ', "", c)
    return c


def schriften(lokal):
    if not lokal:
        return ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                f'<link rel="stylesheet" href="{GOOGLE}">')
    return S.schrift_links().split('\n<link rel="stylesheet" href="file:///' + str(S.NM / "katex").lstrip("/"))[0]


def baue(werk, lokal=False):
    S._HYPH = None  # Browser trennt selbst (hyphens: auto, lang de-AT)
    S.farben_zuweisen(werk)
    kx = S.katex_alle(werk, output="mathml")
    m = werk["meta"]
    gen = S.l_generiert(werk)
    regionen, index, knoepfe = [startfeld(werk)], [], []
    knoepfe.append('<button class="pknopf farbe-tinte" data-ziel="r-start"><i>T</i><span>Start</span></button>')
    for p in werk["provinzen"]:
        kacheln, eintraege = [], []
        for k in p["kacheln"]:
            h = kachel_html(k, p["farbe"], kx)
            kacheln.append(h)
            sym = S.RELEVANZ[k["relevanz"]][0]
            eintraege.append({"code": k["code"], "anzeige": k["code"], "titel": esc(k["titel"]), "anker": esc(k["anker"]),
                              "rel": k["relevanz"], "sym": sym, "such": such(k["code"] + " " + klartext(h))})
        if p["code"] == "L":
            for code, titel, unit in gen:
                h = gen_kachel_html(code, unit)
                kacheln.append(h)
                eintraege.append({"code": code, "anzeige": "L·" + code[1], "titel": esc(titel), "anker": "generiert",
                                  "rel": "kern", "sym": "", "such": such("L" + code[1] + " " + klartext(h))})
        regionen.append(f'<section class="region farbe-{p["farbe"]}" id="r-{p["code"]}" data-farbe="{p["farbe"]}">'
                        f'<div class="landname">{S.md(p["name_lat"], latein=True)}<small>Provinz {p["nr"]}</small></div>'
                        f'{provinzkopf(p)}{"".join(kacheln)}</section>')
        index.append({"code": p["code"], "nr": p["nr"], "name": esc(p["name_lat"]), "farbe": p["farbe"], "kacheln": eintraege})
        knoepfe.append(f'<button class="pknopf farbe-{p["farbe"]}" data-ziel="r-{p["code"]}" title="{esc(p["name_lat"])}: {esc(p["name_de"])}">'
                       f'<i>{p["nr"]}</i><span>{esc(p["name_lat"])}</span></button>')
    daten = json.dumps({"titel": m["titel"], "provinzen": index}, ensure_ascii=False).replace("</", "<\\/")
    css = (css_basis() + "\n" + S.palette_css() + "\n" + (KIT / "vorlage" / "farben.css").read_text(encoding="utf-8") + "\n"
           + (KIT / "vorlage" / "karte.css").read_text(encoding="utf-8") + "\n" + palette_dunkel_css())
    css += "\n.karte-kachel { hyphens: auto; -webkit-hyphens: auto; }\n"
    js = (KIT / "vorlage" / "karte.js").read_text(encoding="utf-8")
    titel = f'{m["titel"]} · Wissenslandkarte'
    return f"""<!DOCTYPE html>
<html lang="de-AT">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="author" content="(c) Oliver Bedernik">
<meta name="description" content="{esc(m['untertitel'])}: interaktive Wissenslandkarte, Version {esc(m['version'])}">
<title>{esc(titel)}</title>
{schriften(lokal)}
<style>
{css}
</style>
</head>
<body>
<header class="kopf">
  <div class="titel"><b>{esc(m["titel"])}</b><span>{esc(m["untertitel"])}</span></div>
  <label class="suche">{ICON["suche"]}<input id="suche" type="search" placeholder="Suchen: Begriff, Norm, Code" aria-label="Kacheln durchsuchen" autocomplete="off"></label>
  <button class="knopf" id="k-register" aria-pressed="false" aria-label="Register">{ICON["register"]}<span class="lbl">Register</span></button>
  <button class="knopf" id="k-kern" aria-pressed="false" aria-label="Nur Kernstoff">{ICON["stern"]}<span class="lbl">Kernstoff</span></button>
  <button class="knopf" id="k-mini" aria-pressed="true" aria-label="Minikarte">{ICON["mini"]}</button>
  <button class="knopf" id="k-thema">{ICON["thema"]}<span class="lbl">Automatisch</span></button>
  <button class="knopf" id="k-info" aria-pressed="false" aria-label="Über diese Karte">{ICON["info"]}</button>
</header>
<main class="flaeche" id="flaeche" aria-label="Wissenslandkarte">
  {wasserzeichen()}
  <div class="welt" id="welt">
{"".join(regionen)}
  </div>
</main>
<nav class="fuss" aria-label="Provinzen und Zoom">
  <div class="provinzen">{"".join(knoepfe)}</div>
  <div class="zoom">
    <button class="knopf" id="k-minus" aria-label="Verkleinern">{ICON["minus"]}</button>
    <button class="knopf" id="k-plus" aria-label="Vergrößern">{ICON["plus"]}</button>
    <button class="knopf optional" id="k-fit" aria-label="Provinz einpassen" title="Provinz einpassen">{ICON["fit"]}</button>
    <button class="knopf" id="k-ganz" aria-label="Ganze Karte" title="Ganze Karte">{ICON["ganz"]}</button>
  </div>
</nav>
<div class="mini" id="mini" aria-label="Minikarte"><svg xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet"></svg></div>
<aside class="paneel" id="register" aria-label="Register"><header><h2>Register</h2><span id="reg-zahl" style="font:400 13px var(--f-ui);color:var(--tinte-2)"></span>
  <button class="knopf schliessen" aria-label="Schließen">✕</button></header><div class="inhalt" id="reg-liste"></div></aside>
{info_paneel(werk)}
<div class="signet" aria-hidden="true">(c) Oliver Bedernik</div>
<script id="terra-daten" type="application/json">{daten}</script>
<script>
{js}
</script>
</body>
</html>"""


def main():
    ap = argparse.ArgumentParser(description="Terra-Wissenslandkarte")
    ap.add_argument("werk")
    ap.add_argument("--aus", default=".")
    ap.add_argument("--lokal", action="store_true", help="Schriften aus node_modules (Tests ohne Netz)")
    a = ap.parse_args()
    werk = json.loads(Path(a.werk).read_text(encoding="utf-8"))
    v = validiere(werk)
    if v.fehler:
        print("\n".join(v.fehler))
        sys.exit("Abbruch: werk.json fehlerhaft")
    aus = Path(a.aus).resolve()
    aus.mkdir(parents=True, exist_ok=True)
    datei = aus / (S.dateiname(werk) + ("_karte_lokal.html" if a.lokal else "_karte.html"))
    inhalt = baue(werk, a.lokal)
    datei.write_text(inhalt, encoding="utf-8")
    striche = len(re.findall("[\u2012\u2013\u2014\u2015]", klartext(inhalt)))
    print(f"Karte: {datei.name} · {len(inhalt) // 1024} KB · Gedankenstriche im Text: {striche}")
    sys.exit(1 if striche else 0)


if __name__ == "__main__":
    main()

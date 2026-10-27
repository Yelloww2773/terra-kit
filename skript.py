#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit · skript.py (Standard 3.1)

Erzeugt aus einer werk.json das Lernskript (Format B) als A4-PDF.

Ablauf: Validierung → Einheiten bauen → Seitenmontage in Chromium (Druckmodus)
→ PDF mit Lesezeichen → Metadaten → Prüfungen → Kontaktabzug → Bericht.

Aufruf:  python3 skript.py werk.json [--aus ORDNER] [--trotzdem]
Ergebnis: Terra_<Name>_v<Version>_<JJJJ-MM>.pdf, dazu .html, _bericht.json, _kontakt.png
"""
import argparse
import datetime as dt
import html
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT))
from validate import validiere  # noqa: E402

VERSION = (Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8").strip()
NM = KIT / "node_modules"
MONATE = ["Jänner", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember"]
# Provinzfarben: gleiche Helligkeit und Sättigung (OKLCH L 0,47, C ≈ 0,085), nur der Farbton
# wandert entlang des Farbkreises. Benachbarte Provinzen sind verwandt; das Daumenregister
# verläuft als ruhiges Spektrum. Flächentöne: gleicher Farbton, OKLCH L 0,94, C 0,02.
PALETTE = {
    "indigo": ("#405A8B", "#E4ECF9"),
    "petrol": ("#19666E", "#DDEFF1"),
    "moos": ("#406637", "#E4EFE2"),
    "bronze": ("#745519", "#F2EADD"),
    "terrakotta": ("#854832", "#F8E7E1"),
    "wein": ("#854451", "#F8E6E8"),
    "pflaume": ("#6F4B7A", "#F1E7F4"),
    "tinte": ("#353D4D", "#E8EBF1"),
}
FOLGE = ["indigo", "petrol", "moos", "bronze", "terrakotta", "wein", "pflaume"]
ALT = {"blau": "indigo", "gruen": "moos", "ocker": "bronze", "rot": "wein", "violett": "pflaume", "braun": "terrakotta", "grau": "tinte"}


def farben_zuweisen(werk):
    """Provinzfarbe nach Position (A = indigo …, L = tinte); explizite Angabe gewinnt, alte Namen werden übersetzt."""
    i = 0
    for p in werk["provinzen"]:
        f = p.get("farbe")
        if f:
            p["farbe"] = ALT.get(f, f)
        elif p["code"] == "L":
            p["farbe"] = "tinte"
        else:
            p["farbe"] = FOLGE[i % len(FOLGE)]
        if p["code"] != "L":
            i += 1
    return werk


def palette_css():
    return "\n".join(f".farbe-{n} {{ --p: {a}; --p-hell: {b}; }}" for n, (a, b) in PALETTE.items())


RELEVANZ = {"kern": ("★", "Kernstoff"), "vertiefung": ("◆", "Vertiefung"), "auslassbar": ("○", "auslassbar")}
LABEL = {"merke": "Merke", "feinheit": "Feinheit", "klausurfalle": "Cave: Klausurfalle",
         "austriacum": "Austriacum", "aktualisierung": "Aktualisierung", "luecke": "Lücke"}

try:
    import pyphen
    _HYPH = pyphen.Pyphen(lang="de_AT")
except Exception:  # Silbentrennung ist Komfort, kein Muss
    _HYPH = None


# ── Text: Typografie, Trennung, Auszeichnung ──────────────────────────────
NBSP, SCHMAL = "\u00a0", "\u202f"
SEITENVERWEIS = False  # wird nur beim Setzen des Lernskripts eingeschaltet (Karte, Exam und Anki bleiben ohne Seitenzahl)


def typo(s):
    s = re.sub(r"(§§?) (?=\d)", lambda m: m.group(1) + NBSP, s)
    s = re.sub(r"\b(Art|Abs|Z|Nr|lit|Rz|S|Gl\.) (?=[\d(])", lambda m: m.group(1) + NBSP, s)
    s = re.sub(r"\blit (?=[a-z]\b)", "lit" + NBSP, s)
    for a, b in (("z. B.", "z.\u202fB."), ("d. h.", "d.\u202fh."), ("u. a.", "u.\u202fa."), ("p. a.", "p.\u202fa."), ("o. Ä.", "o.\u202fÄ.")):
        s = s.replace(a, b)
    s = re.sub(r"(\d) (%|€|Prozentpunkte|Jahre|Jahren|mm|pt)\b", lambda m: m.group(1) + NBSP + m.group(2), s)
    s = re.sub(r"(\d) (%|€)", lambda m: m.group(1) + NBSP + m.group(2), s)
    s = re.sub(r"(\d[a-z]?) (?=[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]*-?[A-ZÄÖÜ])", lambda m: m.group(1) + NBSP, s)
    s = s.replace("...", "…")
    return s


def trenne(s):
    if not _HYPH:
        return s
    return re.sub(r"(?<![&#\w])([A-Za-zÄÖÜäöüß]{9,})", lambda m: _HYPH.inserted(m.group(1), hyphen="\u00ad"), s)


HOCH = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
RE_HOCH = re.compile("[⁰¹²³⁴⁵⁶⁷⁸⁹]+")


def hochzahlen(h):
    """Hochgestellte Unicode-Ziffern (etwa Auflagen „ABGB⁴“) als echte Hochstellung: einheitliche Größe, in jeder Schrift vorhanden."""
    return RE_HOCH.sub(lambda m: f'<sup class="hz">{m.group(0).translate(HOCH)}</sup>', h)


def md(text, latein=False, ziele=None):
    """Inline-Auszeichnung → HTML, mit echter Hochstellung von Hochzahlen."""
    return hochzahlen(_md(text, latein=latein, ziele=ziele))


def _md(text, latein=False, ziele=None):
    """Inline-Auszeichnung → HTML. ziele: Menge gültiger Kachelcodes für Links."""
    s = html.escape(text, quote=False)
    s = typo(s)
    if not latein:
        s = trenne(s)

    def verweis(m):
        fremd, ziel = m.group(1), m.group(2)
        if fremd:
            return f'<span class="vw-ext">{fremd}{NBSP}{ziel}</span>'
        if SEITENVERWEIS:  # nur im Lernskript: Seitenzahl wird nach der Montage eingesetzt (Platzhalter hält die Breite)
            return (f'<a class="vw" href="#k-{ziel}">{ziel}</a><span class="vs">,{NBSP}S{NBSP}'
                    f'<a href="#k-{ziel}" data-ziel="k-{ziel}">00</a></span>')
        return f'<a class="vw" href="#k-{ziel}">{ziel}</a>'
    s = re.sub(r"\[\[(?:([A-Z]{2,5}):)?([A-GL][1-9][0-9]?)\]\]", verweis, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"==(.+?)==", r"\1", s)  # Textmarker entfällt (Entscheidung Oktober 2026)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    return s


def esc(s):
    return html.escape(s, quote=True)


def zahl(x, nachkomma=2):
    t = f"{x:,.{nachkomma}f}"
    return t.replace(",", "§").replace(".", ",").replace("§", ".")


# ── Formeln (KaTeX, serverseitig) ─────────────────────────────────────────
def katex_alle(werk, output="html"):
    liste = []
    for p in werk["provinzen"]:
        for k in p["kacheln"]:
            for b in k["bausteine"]:
                if b["typ"] == "formel":
                    liste.append([b["tex"], True])
                    for v in b.get("variablen", []):
                        liste.append([v["symbol"], False])
                if b["typ"] == "rechenweg":
                    for st in b["schritte"]:
                        if st.get("tex"):
                            liste.append(["\\displaystyle " + st["tex"], False])
    if not liste:
        return {}
    js = r"""
const k = require(process.argv[1]); const fs = require('fs');
const l = JSON.parse(fs.readFileSync(0, 'utf8')); const aus = {};
for (const [t, d] of l) aus[(d ? 'D:' : 'I:') + t] = k.renderToString(t, {displayMode: d, throwOnError: true, output: process.argv[2]});
console.log(JSON.stringify(aus));"""
    r = subprocess.run(["node", "-e", js, str(NM / "katex"), output], input=json.dumps(liste),
                       capture_output=True, text=True, timeout=120)
    if r.returncode:
        sys.exit("KaTeX-Fehler: " + r.stderr[:400])
    return json.loads(r.stdout)


# ── Diagramme ─────────────────────────────────────────────────────────────
def schoene_schritte(lo, hi, n=5):
    span = (hi - lo) or 1
    roh = span / n
    p = 10 ** math.floor(math.log10(roh))
    for f in (1, 2, 2.5, 5, 10):
        if roh <= f * p:
            return f * p
    return 10 * p


def svg_kurve(b):
    W, H, L, R, T, U = 600, 300, 66, 18, 22, 46
    pw, ph = W - L - R, H - T - U
    xs = [pt[0] for r in b["reihen"] for pt in r["punkte"]]
    ys = [pt[1] for r in b["reihen"] for pt in r["punkte"]]
    x0, x1 = min(xs), max(xs)
    ymin, ymax = min(0, min(ys)), max(0, max(ys))
    sy = schoene_schritte(ymin, ymax)
    y0, y1 = math.floor(ymin / sy) * sy, math.ceil(ymax * 1.04 / sy) * sy
    sx = schoene_schritte(x0, x1, 10) if x1 - x0 > 12 else 1
    X = lambda v: L + (v - x0) / ((x1 - x0) or 1) * pw
    Y = lambda v: T + ph - (v - y0) / ((y1 - y0) or 1) * ph
    nk = 0 if sy >= 1 else 2
    o = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img">']
    v = y0
    while v <= y1 + 1e-9:
        o.append(f'<line class="t-gitter" x1="{L}" x2="{L+pw}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>')
        o.append(f'<text class="t-klein" x="{L-6}" y="{Y(v)+3.5:.1f}" text-anchor="end">{zahl(v, nk)}</text>')
        v += sy
    v = x0
    while v <= x1 + 1e-9:
        o.append(f'<line class="t-achse" x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{T+ph}" y2="{T+ph+4}"/>')
        o.append(f'<text class="t-klein" x="{X(v):.1f}" y="{T+ph+15}" text-anchor="middle">{zahl(v, 0)}</text>')
        v += sx
    o.append(f'<line class="t-achse" x1="{L}" x2="{L+pw}" y1="{Y(0):.1f}" y2="{Y(0):.1f}"/>')
    o.append(f'<line class="t-achse" x1="{L}" x2="{L}" y1="{T}" y2="{T+ph}"/>')
    for i, r in enumerate(b["reihen"]):
        pts = " ".join(f"{X(a):.1f},{Y(c):.1f}" for a, c in r["punkte"])
        o.append(f'<polyline class="t-reihe{i%4}" points="{pts}"/>')
        for a, c in r["punkte"]:
            o.append(f'<circle class="t-punkt{i%4}" cx="{X(a):.1f}" cy="{Y(c):.1f}" r="2.1"/>')
    lx, ly = L + pw - 150, T + 8
    o.append(f'<rect x="{lx-8}" y="{ly-10}" width="158" height="{14*len(b["reihen"])+8}" fill="var(--kachel)" stroke="var(--linie)" stroke-width="0.6"/>')
    for i, r in enumerate(b["reihen"]):
        yy = ly + 14 * i
        o.append(f'<line class="t-reihe{i%4}" x1="{lx}" x2="{lx+26}" y1="{yy}" y2="{yy}"/>')
        o.append(f'<text class="t-klein" x="{lx+32}" y="{yy+3.5}">{esc(r["name"])}</text>')
    ex = lambda a: esc(a["label"]) + (f' ({esc(a["einheit"])})' if a.get("einheit") else "")
    o.append(f'<text class="t-text" x="{L+pw/2:.0f}" y="{H-8}" text-anchor="middle">{ex(b["x"])}</text>')
    o.append(f'<text class="t-text" transform="translate(15 {T+ph/2:.0f}) rotate(-90)" text-anchor="middle">{ex(b["y"])}</text>')
    o.append("</svg>")
    return "".join(o).replace('fill="var(--kachel)" stroke="var(--linie)"', 'class="t-flaeche"')


def umbrechen(text, n=26):
    zeilen, z = [], ""
    for w in typo(text).split(" "):
        if z and len(z) + 1 + len(w) > n:
            zeilen.append(z)
            z = w
        else:
            z = (z + " " + w).strip()
    if z:
        zeilen.append(z)
    return zeilen


def svg_fluss(b):
    W, CW, BW = 600, 150, 136
    kn = {k["id"]: dict(k, zeilen=umbrechen(k["text"])) for k in b["knoten"]}
    zeilen_max = max(len(k["zeilen"]) for k in kn.values())
    bh = 14 * zeilen_max + 12
    RH = bh + 34
    rows = max(k["zeile"] for k in kn.values())
    H = rows * RH - 34 + 12
    cx = lambda k: (k["spalte"] - 0.5) * CW
    top = lambda k: 6 + (k["zeile"] - 1) * RH
    o = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img">',
         '<defs><marker id="pf" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path class="pfeil" d="M0,0 L10,5 L0,10 z"/></marker></defs>']
    for e in b["kanten"]:
        a, z = kn[e["von"]], kn[e["nach"]]
        sx, sy, tx, ty = cx(a), top(a) + bh, cx(z), top(z)
        if abs(sx - tx) < 1:
            d = f"M{sx:.0f},{sy} V{ty-1}"
        else:
            my = sy + 16
            d = f"M{sx:.0f},{sy} V{my} H{tx:.0f} V{ty-1}"
        o.append(f'<path class="kante" d="{d}" marker-end="url(#pf)"/>')
        if e.get("label"):
            lx, ly = (sx + 5, sy + 12) if abs(sx - tx) < 1 else (tx + 5, ty - 6)
            o.append(f'<text class="t-label" x="{lx:.0f}" y="{ly:.0f}">{esc(e["label"])}</text>')
    for k in kn.values():
        x, y = cx(k) - BW / 2, top(k)
        o.append(f'<g class="n-{k["art"]}"><rect x="{x:.0f}" y="{y}" width="{BW}" height="{bh}" rx="{8 if k["art"]=="start" else 3}"/>')
        n = len(k["zeilen"])
        y0 = y + bh / 2 - (n - 1) * 7 + 4
        for i, z in enumerate(k["zeilen"]):
            o.append(f'<text class="t-text" x="{cx(k):.0f}" y="{y0+14*i:.1f}" text-anchor="middle">{esc(z).replace(NBSP, "&#160;")}</text>')
        o.append("</g>")
    o.append("</svg>")
    return "".join(o)


# ── Bausteine ─────────────────────────────────────────────────────────────
def tabelle(kopf, zeilen, klasse="t", lat_spalten=(), teilbar=True):
    cls = f"{klasse}{' teilbar' if teilbar else ''}"
    o = [f'<table class="{cls}"><thead><tr>' + "".join(f"<th>{md(h, latein=True)}</th>" for h in kopf) + "</tr></thead><tbody>"]
    for z in zeilen:
        zellen = []
        for i, c in enumerate(z):
            lat = i in lat_spalten
            klasse = ' class="lat"' if lat else ""
            zellen.append(f"<td{klasse}>{md(c, latein=lat)}</td>")
        o.append("<tr>" + "".join(zellen) + "</tr>")
    o.append("</tbody></table>")
    return "".join(o)


def schema_html(b):
    v = b["variante"]
    titel = f'<div class="schema-titel">{md(b["titel"], latein=True)}</div>'
    if v == "tabelle":
        lat = tuple(i for i, h in enumerate(b["kopf"]) if h.lower() in ("terminus", "latinum", "begriff"))
        return titel + tabelle(b["kopf"], b["zeilen"], lat_spalten=lat)
    if v == "abgrenzung":
        zeilen = [[k["kriterium"], k["links"], k["rechts"]] for k in b["kriterien"]]
        return titel + tabelle(["Kriterium", b["links"], b["rechts"]], zeilen, klasse="t abgr")
    if v == "zeitleiste":
        o = ['<table class="t zeit teilbar"><thead style="display:none"><tr><th></th><th></th></tr></thead><tbody>']
        for e in b["ereignisse"]:
            o.append(f'<tr><td class="d">{esc(e["datum"])}</td><td class="e">{md(e["text"])}</td></tr>')
        return titel + "".join(o) + "</tbody></table>"
    if v == "tkonto":
        o = ['<div class="tkonten">']
        for k in b["konten"]:
            n = max(len(k["soll"]), len(k["haben"]), 1)
            zeilen = []
            for i in range(n):
                s = k["soll"][i] if i < len(k["soll"]) else None
                h = k["haben"][i] if i < len(k["haben"]) else None
                f = lambda e: (f'<td class="tx">{md(e["text"])}</td><td class="b">{zahl(e["betrag"])}</td>' if e
                               else '<td class="tx"></td><td class="b"></td>')
                zeilen.append(f"<tr>{f(s)}{f(h).replace('class=\"tx\"', 'class=\"tx h\"', 1)}</tr>")
            ss = sum(e["betrag"] for e in k["soll"]); sh = sum(e["betrag"] for e in k["haben"])
            sz = lambda v: f'<td class="b s">{zahl(v)}</td>' if v else '<td class="b"></td>'
            summe = f'<tr class="sum"><td class="tx"></td>{sz(ss)}<td class="tx h"></td>{sz(sh)}</tr>'
            o.append(f'<table class="tk"><caption>{md(k["name"], latein=True)}</caption><thead><tr><th colspan="2">Soll</th><th colspan="2" class="h">Haben</th></tr></thead><tbody>{"".join(zeilen)}{summe}</tbody></table>')
        o.append("</div>")
        if b.get("buchungssatz"):
            o.append(f'<div class="buchungssatz"><b>Buchungssatz</b>{md(b["buchungssatz"])}</div>')
        return titel + "".join(o)
    if v == "kurve":
        alt = "; ".join(f'{r["name"]}: ' + ", ".join(f"{zahl(a, 0)} → {zahl(c)}" for a, c in r["punkte"]) for r in b["reihen"])
        return titel + f'<div class="fig skalierbar">{svg_kurve(b)}<span class="alt">{esc(alt)}</span></div>'
    if v == "fluss":
        return titel + f'<div class="fig skalierbar">{svg_fluss(b)}</div>'
    if v == "svg":
        stil = f' style="max-width:100%;height:{b["hoehe_mm"]}mm"' if b.get("hoehe_mm") else ""
        svg = b["svg"].replace("<svg", f'<svg{stil}', 1) if stil else b["svg"]
        return titel + f'<div class="fig skalierbar">{svg}<span class="alt">{esc(b["beschreibung"])}</span></div>'
    raise ValueError(v)


def baustein_html(b, kx):
    t = b["typ"]
    if t == "definition":
        z = ""
        if b.get("zitat"):
            z = f'<blockquote class="zitat"><span class="w">„{md(b["zitat"]["text"], latein=True)}“</span><span class="q">{md(b["zitat"]["quelle"])}</span></blockquote>'
        return f'<div class="label">Definition</div><p>{md(b["text"])}</p>{z}'
    if t == "kern":
        lbl = f'<div class="label">{md(b["titel"])}</div>' if b.get("titel") else ""
        return lbl + '<ul class="kern">' + "".join(f"<li>{md(p)}</li>" for p in b["punkte"]) + "</ul>"
    if t == "formel":
        nr = f'<span class="nr">{esc(b["nummer"])}</span>' if b.get("nummer") else ""
        var = ""
        if b.get("variablen"):
            var = '<table class="var">' + "".join(
                f'<tr><td>{kx["I:" + v["symbol"]]}</td><td>{md(v["bedeutung"])}</td></tr>' for v in b["variablen"]) + "</table>"
        return f'<div class="label">Formel</div><div class="formel">{kx["D:" + b["tex"]]}{nr}</div>{var}'
    if t == "rechenweg":
        auf = f'<div class="aufgabe">{md(b["aufgabe"])}</div>' if b.get("aufgabe") else ""
        li = "".join(f'<li>{md(s["text"])}' + (f'<span class="tex">{kx["I:\\displaystyle " + s["tex"]]}</span>' if s.get("tex") else "") + "</li>"
                     for s in b["schritte"])
        return f'<div class="label">Rechenweg</div><div class="rechenweg">{auf}<ol>{li}</ol><div class="ergebnis">Ergebnis: {md(b["ergebnis"])}</div></div>'
    if t == "schema":
        return schema_html(b)
    if t == "beispiel":
        lo = f'<div class="fb-teil fb-lo"><div class="fb-lbl">Lösungsskizze</div>{md(b["loesung"])}</div>' if b.get("loesung") else ""
        return (f'<div class="fallbeispiel"><div class="fb-kopf">Fallbeispiel</div>'
                f'<div class="fb-teil"><div class="fb-lbl">Sachverhalt</div><div class="sv">{md(b["sachverhalt"])}</div></div>{lo}</div>')
    if t in ("merke", "feinheit", "klausurfalle"):
        return f'<div class="box {t}"><div class="lbl">{LABEL[t]}</div>{md(b["text"])}</div>'
    if t == "austriacum":
        return f'<div class="box austriacum"><div class="lbl">{LABEL[t]} <span class="norm">{md(b["norm"])}</span></div>{md(b["text"])}</div>'
    if t == "aktualisierung":
        d = dt.date.fromisoformat(b["datum"])
        return (f'<div class="box aktualisierung"><div class="lbl">{LABEL[t]} <span class="meta">seit {d.day}. {MONATE[d.month-1]} {d.year} · {md(b["quelle"])}</span></div>'
                f'{md(b["text"])}</div>')
    if t == "latinum":
        return (f'<div class="box latinum"><span class="lat">{md(b["lat"], latein=True)}</span>'
                f'<span class="de">{md(b["de"])}</span><span class="stelle">{md(b["stelle"], latein=True)}</span></div>')
    if t == "luecke":
        return f'<div class="box luecke"><div class="lbl">{LABEL[t]} <span class="grund">sinngemäß ergänzt · {md(b["grund"])}</span></div>{md(b["text"])}</div>'
    raise ValueError(t)


# ── Einheiten ─────────────────────────────────────────────────────────────
def einheit(inhalt, **attr):
    spann = attr.pop("spann", None)
    a = " ".join(f'data-{k.replace("_", "-")}="{esc(str(v))}"' for k, v in attr.items() if v not in (None, False, ""))
    return f'<div class="unit{" spann" if spann else ""}" {a}>{inhalt}</div>'


def kachelkopf(k, code=None, titel=None, anker=None, rel=True):
    code = code or k["code"]
    sym, name = RELEVANZ.get(k.get("relevanz", ""), ("", ""))
    r = f'<span class="rel" title="{name}">{sym}</span>' if rel and sym else ""
    anker = anker if anker is not None else (esc(k["anker"]) + (f'<span class="seite">{esc(k["seite"])}</span>' if k.get("seite") else ""))
    return (f'<div class="kkopf" id="k-{code}"><span class="code">{esc(code)}</span>'
            f'<h2>{md(titel or k["titel"], latein=True)}</h2>{r}<span class="kanker">{typo(anker)}</span></div>')


def kachel_einheiten(k, prov, kx, farbe):
    out = []
    for i, b in enumerate(k["bausteine"]):
        quer = b.get("typ") == "schema" and b.get("variante") == "tabelle" and b.get("breit")
        inhalt = (kachelkopf(k) if i == 0 else "") + f'<div class="bs bs-{b["typ"]}">{baustein_html(b, kx)}</div>'
        out.append(einheit(inhalt, kachel=k["code"], prov=prov, farbe=farbe, titel=k["titel"], quer="1" if quer else ""))
    return out


def l_generiert(werk):
    """Repetitorium: automatisch erzeugte Abschnitte (Codes L·F, L·Q, L·V, L·S, L·A)."""
    kacheln = [(k, p["code"]) for p in werk["provinzen"] for k in p["kacheln"]]
    teile = []
    fallen = [(k["code"], b["text"]) for k, _ in kacheln for b in k["bausteine"] if b["typ"] == "klausurfalle"]
    if fallen:
        li = "".join(f'<li>{md(t)} <a class="vw" href="#k-{c}">{c}</a></li>' for c, t in fallen)
        teile.append(("LF", "Klausurfallen im Überblick", f'<ol class="fallen">{li}</ol>'))
    if werk.get("quellenkritik"):
        z = [[q["quelle"], q["befund"], q["richtig"], f'[[{q["kachel"]}]]'] for q in werk["quellenkritik"]]
        teile.append(("LQ", "Quellenkritik", tabelle(["Quelle", "Befund", "Richtig ist", "Kachel"], z)))
    lex = {}
    for k, _ in kacheln:
        for b in k["bausteine"]:
            if b["typ"] == "latinum":
                lex[b["lat"]] = (b["de"], k["code"])
    for e in werk.get("lexicon", []):
        lex[e["begriff"]] = (e["bedeutung"], e["kachel"])
    if lex:
        z = [[b, d, f"[[{c}]]"] for b, (d, c) in sorted(lex.items(), key=lambda x: x[0].lower())]
        teile.append(("LV", "Lexicon", tabelle(["Begriff", "Bedeutung", "Kachel"], z, lat_spalten=(0,))))
    if werk.get("selbsttest"):
        fr = "".join(f'<li>{md(s["frage"])} <a class="vw" href="#k-{s["kachel"]}">{s["kachel"]}</a></li>' for s in werk["selbsttest"])
        an = "".join(f'<li>{md(s["antwort"])}</li>' for s in werk["selbsttest"])
        teile.append(("LS", "Selbsttest", f'<div class="selbsttest"><ol>{fr}</ol><div class="loes"><div class="label">Auflösung</div><ol>{an}</ol></div></div>'))
    if werk.get("aenderungen"):
        z = [[a["version"], dt.date.fromisoformat(a["datum"]).strftime("%d.%m.%Y"), a["text"]] for a in werk["aenderungen"]]
        teile.append(("LA", "Änderungsprotokoll", tabelle(["Version", "Datum", "Änderung"], z)))
    out = []
    for code, titel, inhalt in teile:
        anzeige = "L·" + code[1]
        kopf = (f'<div class="kkopf" id="k-{code}"><span class="code">{anzeige}</span><h2>{titel}</h2>'
                f'<span class="kanker">generiert</span></div>')
        out.append((code, titel, einheit(kopf + f'<div class="bs">{inhalt}</div>', kachel=anzeige, prov="L", farbe="grau", titel=titel)))
    return out


def provinzkopf(p):
    kompakt = "".join(f"<li>{md(s)}</li>" for s in p["kompakt"])
    kach = p["kacheln"]
    half = math.ceil(len(kach) / 2)
    zeilen = []
    for i in range(half):
        zellen = []
        for k in (kach[i], kach[i + half] if i + half < len(kach) else None):
            zellen.append(f'<td><span class="c">{k["code"]}</span>{md(k["titel"], latein=True)}</td>' if k else "<td></td>")
        zeilen.append("<tr>" + "".join(zellen) + "</tr>")
    seiten = f' · {esc(p["seiten"])}' if p.get("seiten") else ""
    return (f'<div class="provkopf"><span class="pchip">Provinz {p["nr"]} ({p["code"]})</span>'
            f'<h1 class="ptitel" id="p-{p["code"]}">{md(p["name_lat"], latein=True)}</h1><div class="pde">{md(p["name_de"], latein=True)}</div>'
            f'<div class="leitfrage"><b>Leitfrage</b>{md(p["leitfrage"])}</div>'
            f'<div class="kompakt"><b>In 60 Sekunden</b><ol>{kompakt}</ol></div>'
            f'<div class="panker">{typo(" · ".join(esc(a) for a in p["anker"]))}{seiten}</div></div>'
            f'<table class="kindex">{"".join(zeilen)}</table>')


def stand_text(werk):
    j, m = map(int, werk["meta"]["stand"].split("-"))
    return f'{werk["modul"]["stand_art"]} {MONATE[m-1]} {j}'


def jahr(werk):
    return werk["meta"]["stand"][:4]


KURSNUMMER = re.compile(r"^\s*(?:(?:LV|LVA|Kurs|Nr\.?)\s*-?\s*)?\d{3,6}[a-z]?\b[\s,.:·]*", re.I)


def ohne_kursnummer(text):
    """„1393 Volkswirtschaftslehre …“ → „Volkswirtschaftslehre …“; Titelseite zeigt keine LV-Nummern."""
    return KURSNUMMER.sub("", text).strip()


def titelseite(werk):
    m = werk["meta"]
    reihe = m.get("reihe") or "Lernskripten zur Prüfungsvorbereitung"
    ort = m.get("ort", "Wien")
    zusatz = f'<div class="tp-lv">{md(ohne_kursnummer(m["lehrveranstaltung"]), latein=True)}</div>' if m.get("lehrveranstaltung") else ""
    return einheit(
        f'<div class="tp-band"><div class="tp-reihe">{md(reihe, latein=True)}</div><div class="tp-autor">Oliver Bedernik</div></div>'
        f'<div class="tp-mitte"><h1 class="tp-titel">{esc(m["titel"])}</h1>'
        f'<div class="tp-unter">{md(m["untertitel"], latein=True)}</div>{zusatz}'
        f'<div class="tp-linie"></div>'
        f'<div class="tp-ausgabe">Version {esc(m["version"])} · {stand_text(werk)}</div></div>'
        f'<div class="tp-fuss"><span>{esc(ort)} {jahr(werk)}</span></div>',
        seite="deck", name="Titelseite")


HAFTUNG = {"recht": " und ersetzt keine Rechtsberatung", "gemischt": " und ersetzt keine Rechts-, Steuer- oder Finanzberatung",
           "wirtschaft": " und ersetzt keine Steuer- oder Finanzberatung"}
JURISTISCH = ("recht", "gemischt")


def impressum(werk):
    m, mo = werk["meta"], werk["modul"]
    motto = werk["motto"]
    erste = werk["provinzen"][0]["kacheln"][0]["code"]
    zeilen = [
        f'<b>{esc(m["titel"])}</b>. {md(m["untertitel"])}. Version {esc(m["version"])}, {stand_text(werk)}.',
        'Alle Angaben ohne Gewähr. Das Skript dient dem Studium' + HAFTUNG.get(mo["domaene"], "") + '.',
        f'<b>Zitiervorschlag:</b> <i>Bedernik</i>, {esc(m["titel"])} ({jahr(werk)}) Kachel {erste}.',
        'Quellen und Entstehung: siehe Quellenverzeichnis, Seite <span data-ziel="t-quellen"></span>.',
        f'Satz: Terra-Kit {VERSION}; Schriften Cormorant Garamond, Spectral und Alegreya Sans.',
        f'<b>© Oliver Bedernik, {esc(m.get("ort", "Wien"))} {jahr(werk)}.</b> Alle Rechte vorbehalten.',
    ]
    return einheit(
        f'<div class="epigraph"><div class="ep-lat">{md(motto["lat"], latein=True)}</div>'
        f'<div class="ep-de">{md(motto["de"])}</div><div class="ep-st">{md(motto["stelle"], latein=True)}</div></div>'
        f'<div class="impressum" id="t-impressum">' + "".join(f"<p>{z}</p>" for z in zeilen) + '</div>',
        seite="titelei", neue_seite="1", name="Impressum")


# ── Quellen: Zitierformen ──────────────────────────────────────────────────
ROEMISCH = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


def zitierstil(werk):
    mo = werk["modul"]
    return mo.get("zitierstil") or ("AZR" if mo["domaene"] in ("recht", "gemischt") else "APA")


def _t(x):
    return typo(esc(x)) if x else ""


def _au(x):
    return f'<span class="au">{_t(x)}</span>'


def _datum(iso):
    j, m, t = iso.split("-")
    return f"{int(t)}.{int(m)}.{j}"


def _initialen(vornamen):
    teile = []
    for wort in vornamen.split():
        if wort.endswith("."):
            teile.append(wort)
        else:
            teile.append("-".join(x[0] + "." for x in wort.split("-") if x))
    return " ".join(teile)


def _apa_name(n, initialen_vorn=False):
    if "," not in n:
        return _au(n)  # Körperschaft
    nach, vor = [x.strip() for x in n.split(",", 1)]
    ini = _initialen(vor)
    return f"{ini} {_au(nach)}" if initialen_vorn else f"{_au(nach)}, {ini}"


def _apa_autoren(namen, initialen_vorn=False):
    n = [_apa_name(x, initialen_vorn) for x in namen]
    if len(n) > 20:
        n = n[:19] + ["…", n[-1]]
        return ", ".join(n)
    if len(n) == 1:
        return n[0]
    if initialen_vorn:
        return ", ".join(n[:-1]) + " &amp; " + n[-1] if len(n) > 2 else n[0] + " &amp; " + n[1]
    return ", ".join(n[:-1]) + ", &amp; " + n[-1]


def _azr_name(n):
    if "," not in n:
        return _au(n)
    nach, vor = [x.strip() for x in n.split(",", 1)]
    return _au(f"{vor} {nach}") if vor.endswith(".") and len(vor) <= 4 else _au(nach)


def _azr_autoren(namen):
    return "/".join(_azr_name(x) for x in namen)


def _sup(n):
    return f"<sup>{n}</sup>" if n else ""


def zitat_voll(q, stil):
    """Vollangabe einer Quelle als HTML nach AZR (österreichische Rechtssprache) oder APA 7 (Autor-Jahr)."""
    if q.get("voll"):
        return md(q["voll"], latein=True)
    g = q["gattung"]
    zus = f' {_t(q["zusatz"])}' if q.get("zusatz") else ""
    # Rechtsquellen, Materialien und Entscheidungen in beiden Stilen in der Form der Rechtssprache
    if g == "norm":
        return f'{_t(q["titel"])} {_t(q["fundstelle"])}{zus}'
    if g == "materialien":
        return f'{_t(q["titel"])}, {_t(q["fundstelle"])}{zus}'
    if g == "entscheidung":
        t = f'{_t(q["gericht"])} {_datum(q["datum"])}, {_t(q["gz"])}'
        if q.get("name"):
            t += f', <i>{_t(q["name"])}</i>'
        if q.get("slg"):
            t += f' = {_t(q["slg"])}'
        if q.get("ecli"):
            t += f', {_t(q["ecli"])}'
        return t + zus
    wer = q.get("autoren") or q.get("hrsg") or ([q["institution"]] if q.get("institution") else [])
    if stil == "AZR":
        a = _azr_autoren(wer)
        if g == "literatur":
            return f'{a}, {_t(q["titel"])}{_sup(q.get("auflage"))} ({_t(q["jahr"])}){zus}'
        if g == "beitrag":
            h = f' in {_azr_autoren(q["hrsg"])} (Hrsg),' if q.get("hrsg") else " in"
            return f'{a}, {_t(q["titel"])},{h} {_t(q["in"])}{_sup(q.get("auflage"))} ({_t(q["jahr"])}){" " + _t(q["seiten"]) if q.get("seiten") else ""}{zus}'
        if g == "kommentar":
            return f'{a} in {_azr_autoren(q["hrsg"])}, {_t(q["in"])}{_sup(q.get("auflage"))} {_t(q["fundstelle"])} ({_t(q["jahr"])}){zus}'
        if g == "aufsatz":
            ort = f'{_t(q["in"])} {_t(q["band"])} ({_t(q["jahr"])})' if q.get("band") else f'{_t(q["in"])} {_t(q["jahr"])},'
            return f'{a}, {_t(q["titel"])}, {ort} {_t(q.get("seiten", ""))}'.rstrip(" ,") + zus
        if g == "lv":
            inst = f', {_t(q["institution"])}' if q.get("autoren") and q.get("institution") else ""
            art = f' ({_t(q["art"])})' if q.get("art") else ""
            return f'{a}, {_t(q["titel"])}{art} ({_t(q["jahr"])}){inst}{zus}'
        # daten, online
        jahr = f' ({_t(q["jahr"])})' if q.get("jahr") else ""
        url = f', <span class="url">{esc(q["url"])}</span>' if q.get("url") else ""
        return f'{a}, {_t(q["titel"])}{jahr}{url} (abgerufen am {_datum(q["abruf"])}){zus}'
    # APA 7, deutschsprachige Fassung
    a = _apa_autoren(wer)
    if not q.get("autoren") and q.get("hrsg"):
        a += " (Hrsg.)"
    jahr = f' ({_t(q["jahr"])})' if q.get("jahr") else " (o. J.)"
    titel = _t(q.get("titel", "")) + (f': {_t(q["untertitel"])}' if q.get("untertitel") else "")
    aufl = f' ({q["auflage"]}. Aufl.)' if q.get("auflage") else ""
    if g == "literatur":
        return f'{a}{jahr}. <i>{titel}</i>{aufl}. {_t(q.get("verlag", ""))}.'.replace(" .", "") + zus
    if g in ("beitrag", "kommentar"):
        h = f'{_apa_autoren(q["hrsg"], True)} (Hrsg.), ' if q.get("hrsg") else ""
        teil = _t(q["fundstelle"]) if g == "kommentar" else titel
        s_ = f' (S. {_t(q["seiten"])})' if q.get("seiten") else ""
        ver = f' {_t(q["verlag"])}.' if q.get("verlag") else ""
        return f'{a}{jahr}. {teil}. In {h}<i>{_t(q["in"])}</i>{aufl}{s_}.{ver}{zus}'
    if g == "aufsatz":
        band = f', <i>{_t(q["band"])}</i>' if q.get("band") else ""
        heft = f'({_t(q["heft"])})' if q.get("heft") else ""
        seiten = f', {_t(q["seiten"])}' if q.get("seiten") else ""
        return f'{a}{jahr}. {titel}. <i>{_t(q["in"])}</i>{band}{heft}{seiten}.{zus}'
    if g == "lv":
        art = _t(q.get("art") or "Lehrveranstaltungsunterlage")
        inst = f' {_t(q["institution"])}.' if q.get("autoren") and q.get("institution") else ""
        return f'{a}{jahr}. <i>{titel}</i> [{art}].{inst}{zus}'
    art = f' [{_t(q.get("art") or "Datensatz")}]' if g == "daten" else ""
    inst = f' {_t(q["institution"])}.' if q.get("autoren") and q.get("institution") else ""
    url = f', <span class="url">{esc(q["url"])}</span>' if q.get("url") else ""
    return f'{a}{jahr}. <i>{titel}</i>{art}.{inst} Abgerufen am {_datum(q["abruf"])}{url}.{zus}'


def zitat_text(q, stil):
    """Vollangabe als reiner Text (Infotafel der Karte, Prüfungen)."""
    return re.sub(r"<[^>]+>", "", zitat_voll(q, stil)).replace("&amp;", "&")


def verwendung(werk):
    """Kurzzitat → [(Kachelcode, Provinzfarbe)]. Aus kachel.quellen; im Altbestand ersatzweise aus dem Quellenanker."""
    kach = [(k, p["farbe"]) for p in werk["provinzen"] for k in p["kacheln"]]
    gefuehrt = any(k.get("quellen") for k, _ in kach)
    out = {}
    for q in werk.get("quellen", []):
        z = q["kurz"]
        if gefuehrt:
            out[z] = [(k["code"], f) for k, f in kach if z in k.get("quellen", [])]
        else:
            out[z] = [(k["code"], f) for k, f in kach if re.search(r"(?<!\w)" + re.escape(z) + r"(?!\w)", k.get("anker", ""))]
    return out


GLIEDERUNG = {
    "AZR": [(("norm",), "Rechtsquellen"), (("materialien",), "Materialien"), (("entscheidung",), "Rechtsprechung"),
            (("literatur", "kommentar", "beitrag", "aufsatz"), "Literatur"), (("lv",), "Lehrveranstaltungsunterlagen"),
            (("daten",), "Daten und Statistiken"), (("online",), "Online-Quellen"), ((None,), "Weitere Quellen")],
    "APA": [(("literatur", "beitrag", "kommentar", "aufsatz"), "Literatur"), (("lv",), "Lehrveranstaltungsunterlagen"),
            (("daten",), "Daten und Statistiken"), (("online",), "Online-Quellen"), (("norm",), "Rechtsquellen"),
            (("materialien",), "Materialien"), (("entscheidung",), "Entscheidungen"), ((None,), "Weitere Quellen")],
}
STIL_TEXT = {"AZR": "nach den Abkürzungs- und Zitierregeln der österreichischen Rechtssprache (AZR)",
             "APA": "nach der Autor-Jahr-Methode in Anlehnung an APA 7"}


def _sortierschluessel(t):
    t = re.sub(r"<[^>]+>", "", t).casefold()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss"), ("é", "e"), ("á", "a")):
        t = t.replace(a, b)
    return t


def quellenverzeichnis(werk):
    """Eigene Seite am Ende: Legende, Gliederung nach Gattungen mit Kurzzitat, Vollangabe und Verwendung, Schluss."""
    m, mo = werk["meta"], werk["modul"]
    stil = zitierstil(werk)
    nutz = verwendung(werk)
    out = [einheit(
        '<div class="titelzeile"><div class="tz-ober">Anhang</div><h1 class="teil" id="t-quellen">Quellenverzeichnis</h1>'
        f'<div class="teil-unter">{esc(m["titel"])}, Version {esc(m["version"])}, {stand_text(werk)}</div></div>'
        '<div class="qv-legende"><div><b>Kurzzitat</b>So wird die Quelle in Karte, Skript und Exam angeführt.</div>'
        f'<div><b>Vollangabe</b>Zitiert {STIL_TEXT[stil]}; Autorinnen und Autoren in Kapitälchen.</div>'
        '<div><b>Verwendet in</b>Kacheln, die sich auf die Quelle stützen; Farbe der Provinz.</div></div>',
        seite="titelei", neue_seite="1", name="Quellenverzeichnis")]
    nr = 0
    for gattungen, titel in GLIEDERUNG[stil]:
        qs = [q for q in werk.get("quellen", []) if q.get("gattung") in gattungen]
        if not qs:
            continue
        qs.sort(key=lambda q: _sortierschluessel(q.get("abk") or q["kurz"]))
        zeilen = []
        for q in qs:
            chips = "".join(f'<a class="kc farbe-{f}" href="#k-{c}">{c}</a>' for c, f in nutz.get(q["kurz"], []))
            zeilen.append(f'<tr><td class="kurz">{md(q["kurz"], latein=True)}</td><td class="voll">{zitat_voll(q, stil)}</td><td class="wo">{chips}</td></tr>')
        out.append(einheit(
            f'<h2 class="qv-h"><span class="nr">{ROEMISCH[nr]}</span>{titel}</h2>'
            '<table class="qv teilbar"><thead><tr><th>Kurzzitat</th><th>Vollangabe</th><th>Verwendet in</th></tr></thead>'
            f'<tbody>{"".join(zeilen)}</tbody></table>', seite="titelei", name=f"Quellen {titel}"))
        nr += 1
    abrufe = sorted(q["abruf"] for q in werk.get("quellen", []) if q.get("abruf"))
    links = ((f'{md(m["kicker"])}. ' if m.get("kicker") else "")
             + f'Primärquelle: {md(mo["primaerquelle"])}. Sekundärquelle: {md(mo["sekundaerquelle"])}. '
             + f'Inhaltsgleich mit der Wissenslandkarte {esc(m["titel"])}; Kachelcodes stimmen in Karte, Skript und Exam überein.')
    rechts = ""
    if werk.get("quellenkritik"):
        rechts += 'Abweichungen von den Quellen und ihre Korrektur: Repetitorium, Abschnitt Quellenkritik, Seite <span data-ziel="k-LQ"></span>. '
    if abrufe:
        rechts += f'Online-Quellen zuletzt abgerufen am {_datum(abrufe[-1])}. '
    rechts += f'{stand_text(werk)}; Quellenanker je Kachel: {md(mo["anker"])}.'
    out.append(einheit(f'<div class="qv-schluss"><div><b>Grundlagen und Entstehung</b>{links}</div>'
                       f'<div><b>Quellenkritik und Stand</b>{rechts}</div></div>', seite="titelei", name="Quellen Schluss"))
    return out


def inhaltsverzeichnis(werk, generiert, mit_abk):
    out = [einheit('<div class="titelzeile"><div class="tz-ober">Titelei</div><h1 class="teil" id="t-inhalt">Inhalt</h1>'
                   '<div class="teil-unter">Jede Provinz beginnt auf einer neuen Seite und trägt ihre Farbe, auch im Daumenregister am Seitenrand. '
                   'Codes und Seitenzahlen sind im PDF anklickbar; die Lesezeichenleiste bildet die Gliederung ab.</div></div>',
                   seite="spalten", neue_seite="1", name="Inhalt", spann="1")]
    vorn = [("t-gebrauch", "Zum Gebrauch")] + ([("t-abk", "Abkürzungen und Zitierweise" if werk["modul"]["domaene"] in JURISTISCH else "Abkürzungen und Verweise")] if mit_abk else [])
    z = "".join(f'<tr><td class="t"><a href="#{i}">{t}</a></td><td class="n"><span data-ziel="{i}"></span></td></tr>' for i, t in vorn)
    out.append(einheit(f'<div class="tocp tocv farbe-grau"><table>{z}</table></div>', seite="spalten", name="Verzeichnis Titelei"))
    for p in werk["provinzen"]:
        rows = []
        for k in p["kacheln"]:
            sym = RELEVANZ[k["relevanz"]][0]
            rows.append(f'<tr><td class="c">{k["code"]}</td><td class="t"><a href="#k-{k["code"]}">{md(k["titel"], latein=True)}</a>'
                        f'<span class="rs">{sym}</span></td><td class="n"><span data-ziel="k-{k["code"]}"></span></td></tr>')
        if p["code"] == "L":
            for code, titel, _ in generiert:
                rows.append(f'<tr><td class="c">L·{code[1]}</td><td class="t"><a href="#k-{code}">{titel}</a></td>'
                            f'<td class="n"><span data-ziel="k-{code}"></span></td></tr>')
        kopf = (f'<div class="k"><span class="pchip">{p["nr"]} ({p["code"]})</span>'
                f'<a class="pt" href="#p-{p["code"]}">{md(p["name_lat"], latein=True)}</a>'
                f'<div class="pd">{md(p["name_de"], latein=True)}</div><span class="n"><span data-ziel="p-{p["code"]}"></span></span></div>')
        out.append(einheit(f'<div class="tocp farbe-{p["farbe"]}">{kopf}<table>{"".join(rows)}</table></div>',
                           seite="spalten", name=f'Verzeichnis {p["code"]}'))
    out.append(einheit('<div class="tocp tocv farbe-grau"><table><tr><td class="t"><a href="#t-quellen">Quellenverzeichnis</a></td>'
                       '<td class="n"><span data-ziel="t-quellen"></span></td></tr>'
                       + ('<tr><td class="t"><a href="#t-register">Sachregister</a></td><td class="n"><span data-ziel="t-register"></span></td></tr>'
                          if sachregister(werk) else '') + '</table></div>', seite="spalten", name="Verzeichnis Anhang"))
    return out


def zum_gebrauch(werk):
    m = werk["meta"]
    kach = [k for p in werk["provinzen"] for k in p["kacheln"]]
    typen = {b["typ"] for k in kach for b in k["bausteine"]}
    zitat = any(b.get("zitat") for k in kach for b in k["bausteine"])
    p0, k0 = werk["provinzen"][0], werk["provinzen"][0]["kacheln"][0]
    n_prov, n_kach = len(werk["provinzen"]), len(kach)
    links = (
        f'<h3>Aufbau</h3><p>Das Skript gliedert sich in <b>{n_prov} Provinzen</b> mit zusammen <b>{n_kach} Kacheln</b>. '
        f'Jede Kachel entspricht einer Kachel der Wissenslandkarte und trägt deren Code. Die letzte Provinz (L) ist das '
        f'<b>Repetitorium</b>: Prüfungsroute, Klausurfallen, Quellenkritik, Lexicon und Selbsttest.</p>'
        f'<h3>Anatomie einer Kachel</h3>'
        f'<div class="anatomie farbe-{p0["farbe"]}"><div class="an-kopf"><span class="an-code">{k0["code"]}</span>'
        f'<span class="an-titel">{md(k0["titel"], latein=True)}</span><span class="an-anker">{typo(esc(k0["anker"]))}</span></div>'
        f'<div class="an-leg"><span>Code</span><span>Titel und Relevanz</span><span>Quellenanker</span></div></div>'
        f'<h3>Relevanz</h3><p><span class="sym">★</span> Kernstoff · <span class="sym">◆</span> Vertiefung · '
        f'<span class="sym">○</span> laut Lehrveranstaltung auslassbar. Die Marken sind eine Einschätzung, keine Prüfungsauskunft.</p>'
        f'<h3>Verweise</h3><p><a class="vw" href="#k-{k0["code"]}">{k0["code"]}</a> verweist auf eine Kachel dieses Skripts und ist anklickbar; '
        f'<span class="vw-ext">ADM{NBSP}D7</span> auf Kachel D7 einer anderen Terra, erkennbar an deren Sigle. '
        f'Der Prüfungsverweis „Karte: D7“ eines Exams führt zum selben Code.</p>'
        f'<h3>Daumenregister</h3><p>Am rechten Seitenrand markiert ein farbiger Reiter mit römischer Ziffer die Provinz. '
        f'Die Farbe kehrt im Kachelrahmen, im Provinzkopf und im Inhaltsverzeichnis wieder.</p>'
        f'<h3>{esc(werk["modul"]["stand_art"])}</h3><p>Primärquelle ist {md(werk["modul"]["primaerquelle"])}. '
        + ('Normtexte erscheinen im Originalwortlaut, auch in historischer Orthographie. ' if zitat else '')
        + f'Maßgeblich ist der {stand_text(werk)}.</p>'
    )
    proben = []
    if zitat:
        proben.append('<blockquote class="zitat"><span class="w">„Wortlaut einer Norm, unverändert aus der Primärquelle.“</span><span class="q">Fundstelle</span></blockquote>')
    reihen = [("merke", "Der prüfungsrelevante Kernsatz der Kachel."),
              ("feinheit", "Dogmatische Nuance, Ausnahme oder Streitstand."),
              ("klausurfalle", "Typischer Fehler, verwechselte Größe oder Frist, Regel ohne ihre Ausnahme."),
              ("austriacum", "Bezug zum österreichischen Recht mit Normzitat."),
              ("aktualisierung", "Rechtslage nach Redaktionsschluss der Quelle."),
              ("luecke", "In der Quelle nicht enthalten, sinngemäß ergänzt.")]
    for t, txt in reihen:
        if t in typen:
            proben.append(f'<div class="box {t}"><div class="lbl">{LABEL[t]}</div>{txt}</div>')
    if "latinum" in typen:
        proben.append('<div class="box latinum"><span class="lat">Proverbium Latinum</span><span class="de">Übersetzung</span><span class="stelle">Quelle oder Stelle</span></div>')
    if "beispiel" in typen:
        proben.append('<div class="fallbeispiel"><div class="fb-kopf">Fallbeispiel</div><div class="fb-teil"><div class="fb-lbl">Sachverhalt</div>'
                      '<div class="sv">Kurzer, eindeutig gefasster Fall.</div></div><div class="fb-teil fb-lo"><div class="fb-lbl">Lösungsskizze</div>'
                      + ('Subsumtion in Schritten, mit Normzitat.' if werk["modul"]["domaene"] in JURISTISCH else 'Lösung in Schritten, mit Quellenanker.')
                      + '</div></div>')
    if typen & {"formel", "rechenweg"}:
        proben.append('<p class="hinweis">Formeln tragen die Gleichungsnummer der Quelle; Rechenwege zeigen jeden Zwischenschritt.</p>')
    proben.append('<p class="hinweis">Fachtermini stehen kursiv und sind im <b>Lexicon</b> des Repetitoriums mit Kachelverweis gesammelt.</p>')
    rechts = '<h3>Bausteine</h3>' + "".join(proben)
    return einheit(f'<div class="titelzeile"><div class="tz-ober">Titelei</div><h1 class="teil" id="t-gebrauch">Zum Gebrauch</h1></div>'
                   f'<table class="gebrauch"><tr><td>{links}</td><td>{rechts}</td></tr></table>',
                   seite="titelei", neue_seite="1", name="Zum Gebrauch")


ABK = {
    "AB": "Ausschussbericht", "ABGB": "Allgemeines bürgerliches Gesetzbuch", "Abs": "Absatz", "AEUV": "Vertrag über die Arbeitsweise der EU",
    "AktG": "Aktiengesetz", "AngG": "Angestelltengesetz", "ArbVG": "Arbeitsverfassungsgesetz", "Art": "Artikel",
    "ASVG": "Allgemeines Sozialversicherungsgesetz", "AußStrG": "Außerstreitgesetz", "AVG": "Allgemeines Verwaltungsverfahrensgesetz 1991",
    "BAO": "Bundesabgabenordnung", "BFG": "Bundesfinanzgericht", "BGBl": "Bundesgesetzblatt", "BVwG": "Bundesverwaltungsgericht",
    "B-VG": "Bundes-Verfassungsgesetz", "D.": "Digesten (Corpus Iuris Civilis)", "DSG": "Datenschutzgesetz", "EGMR": "Europäischer Gerichtshof für Menschenrechte",
    "EheG": "Ehegesetz", "EMRK": "Europäische Menschenrechtskonvention", "EO": "Exekutionsordnung", "EPG": "Eingetragene Partnerschaft-Gesetz",
    "ErläutRV": "Erläuterungen zur Regierungsvorlage", "EStG": "Einkommensteuergesetz 1988", "EU": "Europäische Union", "EuGH": "Gerichtshof der Europäischen Union",
    "EUV": "Vertrag über die Europäische Union", "FinStrG": "Finanzstrafgesetz", "GewO": "Gewerbeordnung 1994", "Gl.": "Gleichung",
    "GmbHG": "GmbH-Gesetz", "GRC": "Charta der Grundrechte der EU", "GuV": "Gewinn- und Verlustrechnung", "hA": "herrschende Ansicht",
    "hL": "herrschende Lehre", "hM": "herrschende Meinung", "Hs": "Halbsatz", "idF": "in der Fassung", "idgF": "in der geltenden Fassung",
    "IFG": "Informationsfreiheitsgesetz", "IO": "Insolvenzordnung", "iVm": "in Verbindung mit", "JGS": "Justizgesetzsammlung", "JN": "Jurisdiktionsnorm",
    "KSchG": "Konsumentenschutzgesetz", "KStG": "Körperschaftsteuergesetz 1988", "lit": "litera (Buchstabe)", "LVwG": "Landesverwaltungsgericht",
    "MRG": "Mietrechtsgesetz", "OGH": "Oberster Gerichtshof", "RIS": "Rechtsinformationssystem des Bundes", "ROCE": "Return on Capital Employed",
    "ROE": "Return on Equity", "ROI": "Return on Investment", "Rsp": "Rechtsprechung", "Rz": "Randzahl", "StGB": "Strafgesetzbuch",
    "StGG": "Staatsgrundgesetz 1867", "StPO": "Strafprozessordnung 1975", "stRsp": "ständige Rechtsprechung", "UGB": "Unternehmensgesetzbuch",
    "UrhG": "Urheberrechtsgesetz", "USt": "Umsatzsteuer", "UStG": "Umsatzsteuergesetz 1994", "UWG": "Bundesgesetz gegen den unlauteren Wettbewerb 1984",
    "VerG": "Vereinsgesetz 2002", "VfGG": "Verfassungsgerichtshofgesetz 1953", "VfGH": "Verfassungsgerichtshof", "VfSlg": "Sammlung der Erkenntnisse des VfGH",
    "vgl": "vergleiche", "VStG": "Verwaltungsstrafgesetz 1991", "VwGG": "Verwaltungsgerichtshofgesetz 1985", "VwGH": "Verwaltungsgerichtshof",
    "VwGVG": "Verwaltungsgerichtsverfahrensgesetz", "VwSlg": "Sammlung der Erkenntnisse des VwGH", "WEG": "Wohnungseigentumsgesetz 2002",
    "Z": "Ziffer", "zB": "zum Beispiel", "ZPO": "Zivilprozessordnung",
}


def abkuerzungen(werk):
    texte = " ".join(t for pfad, t in _strings(werk) if not pfad.endswith((".svg", ".tex")))
    gefunden = []
    for k in ABK:
        muster = r"(?<![\w-])" + re.escape(k) + (r"(?=\s?\d)" if k == "Z" else r"(?![\w-])")
        if re.search(muster, texte):
            gefunden.append(k)
    gefunden.sort(key=lambda x: x.lower().replace("ä", "a").replace("ö", "o").replace("ü", "u"))
    if len(gefunden) < 5:
        return []
    half = math.ceil(len(gefunden) / 2)
    zeilen = []
    for i in range(half):
        a = gefunden[i]
        b = gefunden[i + half] if i + half < len(gefunden) else None
        zeilen.append([a, ABK[a], b or "", ABK[b] if b else ""])
    tab = '<table class="abk teilbar"><thead><tr><th>Abk.</th><th>Bedeutung</th><th>Abk.</th><th>Bedeutung</th></tr></thead><tbody>' + "".join(
        f'<tr><td class="a">{esc(a)}</td><td>{esc(b)}</td><td class="a">{esc(c)}</td><td>{esc(d)}</td></tr>' for a, b, c, d in zeilen) + "</tbody></table>"
    juristisch = werk["modul"]["domaene"] in JURISTISCH
    zit = [("Paragraph", "§ 915 Hs 2 ABGB", "ohne Punkt nach Abkürzungen, österreichische Legistik"),
           ("Artikel", "Art 7 Abs 1 B-VG", "Absatz und Ziffer werden nachgestellt: Art 10 Abs 1 Z 6 B-VG"),
           ("Digesten", "Celsus, D. 1,3,17", "Buch, Titel, Fragment; Autor vorangestellt"),
           ("Entscheidung", "VwGH 14.5.1992, 92/16/0015", "Gericht, Datum, Geschäftszahl; OGH etwa 1 Ob 33/97b"),
           ("Querverweis", "→ A1, → ADM D7", "Kachelcode; mit Sigle für Kacheln einer anderen Terra")]
    if not juristisch:
        zit = [zit[-1]]
    zt = ('<h2 class="unter">Zitierweise</h2><table class="t zit"><thead><tr><th>Form</th><th>Beispiel</th><th>Hinweis</th></tr></thead><tbody>'
          + "".join(f"<tr><td><b>{a}</b></td><td>{typo(esc(b))}</td><td>{esc(c)}</td></tr>" for a, b, c in zit) + "</tbody></table>")
    titel = "Abkürzungen und Zitierweise" if juristisch else "Abkürzungen und Verweise"
    zt = zt.replace("Zitierweise</h2>", ("Zitierweise" if juristisch else "Verweise") + "</h2>")
    return [einheit(f'<div class="titelzeile"><div class="tz-ober">Titelei</div><h1 class="teil" id="t-abk">{titel}</h1></div>{tab}',
                    seite="titelei", neue_seite="1", name="Abkürzungen"),
            einheit(zt, seite="titelei", name="Zitierweise")]


def _strings(obj, pfad="$"):
    if isinstance(obj, str):
        yield pfad, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(v, f"{pfad}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _strings(v, f"{pfad}[{i}]")


def baue_einheiten(werk, kx):
    global SEITENVERWEIS
    SEITENVERWEIS = True
    try:
        return _baue_einheiten(werk, kx)
    finally:
        SEITENVERWEIS = False


def _baue_einheiten(werk, kx):
    gen = l_generiert(werk)
    abk = abkuerzungen(werk)
    out = [titelseite(werk), impressum(werk)] + inhaltsverzeichnis(werk, gen, bool(abk)) + [zum_gebrauch(werk)] + abk
    for p in werk["provinzen"]:
        out.append(einheit(f'<div class="farbe-{p["farbe"]}">{provinzkopf(p)}</div>', neue_seite="1", prov=p["code"],
                           provstart="1", nr=p["nr"], pname=p["name_lat"], farbe=p["farbe"], name=f'Provinz {p["code"]}'))
        for k in p["kacheln"]:
            out += kachel_einheiten(k, p["code"], kx, p["farbe"])
        if p["code"] == "L":
            out += [u for _, _, u in gen]
    out += quellenverzeichnis(werk)
    out += sachregister(werk)
    return out


# Sachregister (3.4) ─────────────────────────────────────────────────────────
def _klartext(t):
    return re.sub(r"\[\[[^\]]*\]\]|[*=]", "", t)


def register_eintraege(werk):
    """{Stichwort: [Kachelcodes]} aus Lexicon und Latinum, in juristischen Domänen dazu Normen.

    Ein Stichwort verweist auf seine Definitionskachel und jede weitere Kachel, die es
    wörtlich nennt. Seitenzahlen setzt erst die Montage; doppelte Seiten fallen dort weg.
    """
    from pruefliste import RE_NORM
    texte = {}
    for p in werk["provinzen"]:
        for k in p["kacheln"]:
            texte[k["code"]] = " ".join(_klartext(x) for _, x in _strings(k) if isinstance(x, str))
    begriffe, normen = {}, {}
    quelle = [(b["lat"], k["code"]) for p in werk["provinzen"] for k in p["kacheln"] for b in k["bausteine"] if b["typ"] == "latinum"]
    quelle += [(e["begriff"], e["kachel"]) for e in werk.get("lexicon", [])]
    for wort, heim in quelle:
        wort = _klartext(wort).strip()
        muster = re.compile(r"(?<!\w)" + re.escape(wort) + r"(?!\w)", re.I)
        codes = [heim] + [c for c, t in texte.items() if c != heim and muster.search(t)]
        begriffe[wort] = sorted(set(codes), key=lambda c: list(texte).index(c) if c in texte else 999)
    if werk["modul"]["domaene"] in JURISTISCH:
        for c, t in texte.items():
            for m in RE_NORM.finditer(t):
                n = re.sub(r"\s+", " ", m.group()).strip(" ,")
                if re.search(r"[A-Z]{2,}|StGG|EMRK", n.split(" ", 1)[-1]) and len(n.split()) >= 3:
                    normen.setdefault(n, [])
                    if c not in normen[n]:
                        normen[n].append(c)
    return begriffe, normen


def _normschluessel(n):
    """Nach Gesetz, dann numerisch nach Artikel bzw. Paragraph: Art 2 vor Art 10 vor Art 149."""
    teile = n.split()
    gesetz = teile[-1] if len(teile) > 2 else ""
    m = re.search(r"\d+", n)
    return (gesetz, 0 if n.startswith("Art") else 1, int(m.group()) if m else 0, n)


def _registerzeilen(eintraege):
    z = []
    for wort, codes in eintraege:
        n = ", ".join(f'<a href="#k-{c}" data-ziel="k-{c}">00</a>' for c in codes)
        z.append(f'<tr><td class="t">{md(wort, latein=True)}</td><td class="rz">{n}</td></tr>')
    return z


def sachregister(werk):
    begriffe, normen = register_eintraege(werk)
    if not begriffe and not normen:
        return []
    out = [einheit('<div class="titelzeile"><div class="tz-ober">Anhang</div><h1 class="teil" id="t-register">Sachregister</h1>'
                   '<div class="teil-unter">Seitenzahlen führen zur Kachel; die erste Zahl ist die Definitionsstelle, sofern vorhanden.</div></div>',
                   seite="spalten", neue_seite="1", name="Sachregister", spann="1")]
    gruppen = {}
    for wort in sorted(begriffe, key=_sortierschluessel):
        gruppen.setdefault(_sortierschluessel(wort)[:1].upper() or "#", []).append((wort, begriffe[wort]))
    for buchst, eintr in gruppen.items():
        out.append(einheit(f'<div class="register"><div class="rb">{esc(buchst)}</div><table>{"".join(_registerzeilen(eintr))}</table></div>',
                           seite="spalten", name=f"Register {buchst}"))
    if normen:
        out.append(einheit('<div class="register"><div class="rb rn">Normen</div><table>'
                           + "".join(_registerzeilen(sorted(normen.items(), key=lambda x: _normschluessel(x[0])))) + '</table></div>',
                           seite="spalten", name="Register Normen"))
    return out


def schrift_links():
    css = []
    for fam, gew in (("cormorant-garamond", ["400", "500", "600", "700", "400-italic", "600-italic"]),
                     ("spectral", ["400", "500", "600", "400-italic", "600-italic"]),
                     ("alegreya-sans", ["400", "500", "700", "400-italic"])):
        for g in gew:
            f = NM / "@fontsource" / fam / f"{g}.css"
            if f.exists():
                css.append(f'<link rel="stylesheet" href="{f.as_uri()}">')
    css.append(f'<link rel="stylesheet" href="{(NM / "katex" / "dist" / "katex.min.css").as_uri()}">')
    return "\n".join(css)


def dokument(werk, einheiten):
    m = werk["meta"]
    meta = {
        "kopf_links": f'<b>{esc(m["titel"])}</b> · {esc(m["untertitel"])}',
        "fuss_links": esc(stand_text(werk)),
        "provinzen": [{"code": p["code"], "nr": p["nr"], "farbe": p["farbe"], "name": p["name_lat"], "de": esc(p["name_de"])} for p in werk["provinzen"]],
    }
    return f"""<!DOCTYPE html>
<html lang="de-AT"><head><meta charset="utf-8">
<title>{esc(m["titel"])} · {esc(m["untertitel"])}</title>
<meta name="author" content="(c) Oliver Bedernik">
{schrift_links()}
<link rel="stylesheet" href="{(KIT / 'vorlage' / 'skript.css').as_uri()}">
<style>{palette_css()}</style>
<script id="meta" type="application/json">{json.dumps(meta, ensure_ascii=False)}</script>
</head><body class="schema-{m.get("farbschema", "nacht")}">
<main id="buch"></main>
<div id="quelle">{"".join(einheiten)}</div>
<script src="{(KIT / 'vorlage' / 'montage.js').as_uri()}"></script>
</body></html>"""


# ── Montage, PDF, Prüfung ─────────────────────────────────────────────────
def montiere(html_pfad, pdf_pfad, werk):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--allow-file-access-from-files"])
        pg = br.new_page()
        pg.emulate_media(media="print")
        pg.goto(html_pfad.as_uri())
        pg.wait_for_function("window.__fertig === true", timeout=180_000)
        bericht = pg.evaluate("window.__bericht")
        html_pfad.with_name(html_pfad.stem + "_montiert.html").write_text(pg.content(), encoding="utf-8")
        pg.pdf(path=str(pdf_pfad), prefer_css_page_size=True, print_background=True, outline=False, tagged=True)
        br.close()
    return bericht


def metadaten(pdf_pfad, werk, anker=None, bericht=None):
    from pypdf import PdfReader, PdfWriter
    r = PdfReader(str(pdf_pfad))
    w = PdfWriter(clone_from=r)
    m = werk["meta"]
    w.add_metadata({"/Title": f'{m["titel"]} · {m["untertitel"]}', "/Author": "(c) Oliver Bedernik",
                    "/Subject": f'Lernskript, {stand_text(werk)}, Version {m["version"]}',
                    "/Keywords": ", ".join(["Terra", m["titel"], werk["modul"]["domaene"]] + [p["name_de"] for p in werk["provinzen"]]),
                    "/Creator": f"Terra-Kit {VERSION}"})
    lesezeichen(w, werk, anker or {}, fehlend := [])
    w.page_mode = "/UseOutlines"
    with open(pdf_pfad, "wb") as f:
        w.write(f)
    if bericht is not None and fehlend:
        bericht["fehler"].append("Lesezeichen ohne Ziel: " + ", ".join(fehlend[:8]))


def lesezeichen_plan(werk, anker):
    """[(Ebene, Titel, Seite)] der Lesezeichenleiste: Titelei, Provinzen mit Kachelcodes, Anhang.
    Seiten stammen aus der Montage (anker: id → Seitenzahl, 1-basiert)."""
    plan, fehlend = [], []

    def ein(ebene, titel, ziel):
        if ziel in anker:
            plan.append((ebene, titel, anker[ziel]))
        else:
            fehlend.append(ziel)
    for ziel, titel in (("t-inhalt", "Inhalt"), ("t-gebrauch", "Zum Gebrauch"), ("t-abk", "Abkürzungen")):
        if ziel in anker:
            plan.append((0, titel, anker[ziel]))
    gen = {c: t for c, t, _ in l_generiert(werk)}
    for p in werk["provinzen"]:
        ein(0, f'{p["code"]} · {_klartext(p["name_lat"])}', f'p-{p["code"]}')
        for k in p["kacheln"]:
            ein(1, f'{k["code"]} {_klartext(k["titel"])}', f'k-{k["code"]}')
        if p["code"] == "L":
            for c, t in gen.items():
                ein(1, f"L·{c[1]} {t}", f"k-{c}")
    ein(0, "Quellenverzeichnis", "t-quellen")
    if "t-register" in anker:
        plan.append((0, "Sachregister", anker["t-register"]))
    return plan, fehlend


def lesezeichen(w, werk, anker, fehlend):
    plan, f = lesezeichen_plan(werk, anker)
    fehlend += f
    eltern = {}
    for ebene, titel, seite in plan:
        eltern[ebene] = w.add_outline_item(titel, seite - 1, parent=eltern.get(ebene - 1))


def pruefe_pdf(pdf_pfad, bericht, werk=None):
    from pypdf import PdfReader
    r = PdfReader(str(pdf_pfad))
    n = len(r.pages)
    if n != len(bericht["seiten"]):
        bericht["fehler"].append(f"PDF hat {n} Seiten, Montage {len(bericht['seiten'])} (Leerseiten durch Rundung?)")
    for i, (p, s) in enumerate(zip(r.pages, bericht["seiten"])):
        b, h = float(p.mediabox.width), float(p.mediabox.height)
        quer = b > h
        if quer != (s["art"] == "quer"):
            bericht["fehler"].append(f"Seite {i+1}: Ausrichtung im PDF passt nicht zur Montage")
    txt = subprocess.run(["pdftotext", "-layout", str(pdf_pfad), "-"], capture_output=True, text=True).stdout
    seiten_txt = txt.split("\f")
    ohne = [i + 1 for i, t in enumerate(seiten_txt[:n]) if "Oliver Bedernik" not in t]
    if ohne:
        bericht["fehler"].append(f"Wasserzeichen im Text nicht gefunden auf Seite(n) {ohne}")
    mitten = re.findall(r"\b[a-zäöüß]{1,}-[a-zäöüß]{2,}\b", txt.replace("\u00ad", ""))
    quelltext = " ".join(t for _, t in _strings(werk)).lower() if werk else ""
    mitten = [m for m in mitten if m.lower() not in quelltext]  # echte Bindestrichwörter stehen so im Werk
    if mitten:
        bericht["warnungen"].append(f"Trennstrich mitten im Wort, prüfen: {sorted(set(mitten))[:8]}")
    # Weiche Trennzeichen dürfen nur an tatsächlichen Zeilenenden stehen (ISO 32000);
    # ihre Zahl im Textlayer muss der Zahl der gesetzten Umbrüche entsprechen.
    weich, gesetzt = txt.count("\u00ad"), bericht.get("silbentrennung", {}).get("umbrochen", 0)
    if weich != gesetzt:
        bericht["fehler"].append(f"{weich} weiche Trennzeichen im Textlayer, aber {gesetzt} Umbrüche gesetzt (Suche gestört)")
    striche = len(re.findall("[\u2012\u2013\u2014\u2015]", txt))
    if striche:
        bericht["fehler"].append(f"{striche} Gedankenstrich(e) im PDF-Text")
    fonts = subprocess.run(["pdffonts", str(pdf_pfad)], capture_output=True, text=True).stdout.splitlines()[2:]
    nicht = [f.split()[0] for f in fonts if len(f.split()) >= 6 and f.split()[-5] != "yes"]
    if nicht:
        bericht["fehler"].append(f"nicht eingebettete Schriften: {nicht}")
    bericht["schriften"] = sorted({re.sub(r"^[A-Z]{6}\+", "", f.split()[0]) for f in fonts if f.strip()})
    fremd = [f for f in bericht["schriften"] if not re.match(r"(CormorantGaramond|Spectral|AlegreyaSans|KaTeX_|DejaVuSans)", f)]
    if fremd:
        bericht["warnungen"].append(f"Ersatzschriften eingebettet (fehlende Glyphen): {fremd}")
    seiten = bericht["seiten"]
    # Unvermeidbar und daher nicht gemeldet: Seiten vor einem erzwungenen Neubeginn (neue Provinz, Lösungsteil)
    leer = [s["nr"] for i, s in enumerate(seiten) if s["art"] in ("normal", "quer") and s["fuellstand"] < 0.25
            and not (i + 1 < len(seiten) and seiten[i + 1].get("zwang"))]
    if leer:
        bericht["warnungen"].append(f"Seiten unter 25 % Füllstand: {leer}")
    return n


def kontaktabzug(pdf_pfad, ziel):
    from PIL import Image, ImageDraw
    tmp = ziel.with_suffix("")
    subprocess.run(["pdftoppm", "-r", "28", "-png", str(pdf_pfad), str(tmp)], check=True)
    bilder = sorted(tmp.parent.glob(tmp.name + "-*.png"))
    ims = [Image.open(b) for b in bilder]
    sp = 6
    zellw = max(i.width for i in ims) + 14
    zellh = max(i.height for i in ims) + 24
    zeilen = math.ceil(len(ims) / sp)
    blatt = Image.new("RGB", (sp * zellw + 14, zeilen * zellh + 14), (142, 138, 130))
    d = ImageDraw.Draw(blatt)
    for k, im in enumerate(ims):
        x, y = 14 + (k % sp) * zellw, 14 + (k // sp) * zellh
        blatt.paste(im, (x, y + (zellh - 24 - im.height) // 2))
        d.text((x, y + zellh - 20), f"S. {k+1}", fill=(255, 255, 255))
    blatt.save(ziel)
    for b in bilder:
        b.unlink()


def dateiname(werk):
    m = werk["meta"]
    return "Terra_" + "_".join(m["titel"].split()[1:]) + f'_v{m["version"]}_{m["stand"]}'


def main():
    ap = argparse.ArgumentParser(description="Terra-Lernskript A4")
    ap.add_argument("werk")
    ap.add_argument("--aus", default=".")
    ap.add_argument("--trotzdem", action="store_true", help="trotz Validierungsfehlern rendern")
    a = ap.parse_args()
    t0 = time.time()
    werk = json.loads(Path(a.werk).read_text(encoding="utf-8"))
    v = validiere(werk)
    print(f"Validierung: {len(v.fehler)} Fehler, {len(v.warnungen)} Warnungen")
    if v.fehler and not a.trotzdem:
        print("\n".join(v.fehler))
        sys.exit("Abbruch: werk.json fehlerhaft")
    aus = Path(a.aus).resolve()
    aus.mkdir(parents=True, exist_ok=True)
    name = dateiname(werk)
    html_pfad, pdf_pfad = aus / f"{name}.html", aus / f"{name}.pdf"
    farben_zuweisen(werk)
    kx = katex_alle(werk)
    html_pfad.write_text(dokument(werk, baue_einheiten(werk, kx)), encoding="utf-8")
    bericht = montiere(html_pfad, pdf_pfad, werk)
    metadaten(pdf_pfad, werk, bericht.get("anker"), bericht)
    n = pruefe_pdf(pdf_pfad, bericht, werk)
    kontaktabzug(pdf_pfad, aus / f"{name}_kontakt.png")
    bericht["dauer_s"] = round(time.time() - t0, 1)
    bericht["validierung"] = {"fehler": v.fehler, "warnungen": v.warnungen, "hinweise": v.hinweise}
    (aus / f"{name}_bericht.json").write_text(json.dumps(bericht, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"PDF: {pdf_pfad.name} · {n} Seiten · {bericht['dauer_s']} s")
    print("Füllstand: " + " ".join(f'{s["nr"]}:{round(s["fuellstand"]*100)}%{"Q" if s["art"]=="quer" else ""}' for s in bericht["seiten"]))
    st = bericht.get("silbentrennung", {})
    print(f'Silbentrennung: {st.get("umbrochen", 0)} Trennungen gesetzt, {st.get("entfernt", 0)} ungenutzte Trennstellen entfernt')
    for t in bericht["teilungen"]:
        print(f'Tabellenteilung {t["kachel"]}: {t["zeilen"]} Zeilen auf {t["teile"]} Teile, Seiten {t["seiten"]}')
    for s in bericht["skalierungen"]:
        print(f'Skalierung {s["kachel"]}: {round(s["skala"]*100)} % auf Seite {s["seite"]}')
    for z in bericht["fehler"]:
        print("FEHLER  ", z)
    for z in bericht["warnungen"]:
        print("WARNUNG ", z)
    print(f"Ergebnis: {len(bericht['fehler'])} Fehler, {len(bericht['warnungen'])} Warnungen")
    sys.exit(1 if bericht["fehler"] else 0)


if __name__ == "__main__":
    main()

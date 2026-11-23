#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit 4.0 (Entwurf) · diagramm.py

Flussdiagramme und BPMN-Schwimmbahnen als SVG, aus Daten statt von Hand gezeichnet.

Raster: Knoten sitzen in Spalte und Zeile; Bahnen (BPMN) sind Spalten. Kanten laufen orthogonal
zwischen Anschlüssen (oben, unten, links, rechts); ohne Angabe wählt der Satz sie selbst.
Knotenarten: start, ende, abbruch (Terminierung), ereignis, aufgabe, zustand, frage, ergebnis, notiz.
Kantenarten: fluss (Pfeil), nachricht (gestrichelt, BPMN-Nachrichtenfluss), bezug (punktiert, Anmerkung).
Farben kommen aus den Rollen des Werks (Farbschlüssel), nicht aus der einzelnen Grafik.
Jede Grafik trägt den Vermerk (c) Oliver Bedernik.
"""
import html
from functools import lru_cache
from pathlib import Path

KIT = Path(__file__).resolve().parent
FONTS = KIT / "node_modules" / "@fontsource" / "alegreya-sans" / "files"
VERMERK = "(c) Oliver Bedernik"
W = 680  # Einheiten; 680 Einheiten = 170 mm Satzbreite

# Drei Töne je Farbe: dunkel (Linie, Schrift), mittel (Fläche mit weißer Schrift), hell (Füllung)
def _mische(a, b, t):
    """Mischt zwei Hexfarben: t = Anteil von a."""
    ca, cb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02X}" for x, y in zip(ca, cb))


# Drei Töne je Farbe aus der Provinzpalette des Kits (skript.PALETTE): dunkel, mittel (gemischt), hell
_PALETTE = {"indigo": ("#405A8B", "#E4ECF9"), "petrol": ("#19666E", "#DDEFF1"), "moos": ("#406637", "#E4EFE2"),
            "bronze": ("#745519", "#F2EADD"), "terrakotta": ("#854832", "#F8E7E1"), "wein": ("#854451", "#F8E6E8"),
            "pflaume": ("#6F4B7A", "#F1E7F4"), "tinte": ("#353D4D", "#E8EBF1")}
FARBEN = {n: (d, _mische(d, h, 0.62), h) for n, (d, h) in _PALETTE.items()}
FARBEN["grau"] = FARBEN["tinte"]
TINTE = "#1F2A44"
_ZAEHLER = [0]


@lru_cache(maxsize=None)
def _font(gewicht, groesse):
    from PIL import ImageFont
    datei = FONTS / f"alegreya-sans-latin-{gewicht}-normal.woff"
    return ImageFont.truetype(str(datei), max(1, round(groesse * 10)))


def breite(text, groesse, gewicht=400):
    """Textbreite in SVG-Einheiten (gemessen an der Hausschrift, nicht geschätzt)."""
    return _font(gewicht, groesse).getlength(text) / 10


def umbrechen(text, maxb, groesse, gewicht=400):
    """Zeilenfall nach gemessener Breite; Normzitate („§ 160“, „Art 2“) bleiben beisammen."""
    import re as _re
    text = _re.sub(r"(§§?|Art|Abs|RGBl|PGS) (?=\d)", lambda m: m.group(1) + "\u00a0", text)
    zeilen, z = [], ""
    for wort in [w for w in text.split(" ") if w]:
        probe = (z + " " + wort).strip()
        if breite(probe, groesse, gewicht) <= maxb or not z:
            z = probe
        else:
            zeilen.append(z)
            z = wort
    if z:
        zeilen.append(z)
    return zeilen


def e(s):
    return html.escape(str(s), quote=True)


class Diagramm:
    FS, FSU, FSL = 11.6, 10.2, 10.2  # Schrift: Knoten, Unterzeile, Kantenbeschriftung
    LH = 13.8

    def __init__(self, b, rollen):
        self.b, self.rollen = b, rollen
        self.stil = b.get("stil", "fluss")
        self.bahnen = b.get("bahnen", [])
        self.knoten = {k["id"]: dict(k) for k in b["knoten"]}
        bidx = {x["rolle"]: i for i, x in enumerate(self.bahnen)}
        for k in self.knoten.values():
            if self.stil == "fluss" and k["art"] in ("start", "ende"):
                k["art"] = "ergebnis"
            if "bahn" in k:
                k["spalte"] = bidx[k["bahn"]]
                k.setdefault("rolle", k["bahn"])
        self.ncol = len(self.bahnen) or max(k["spalte"] for k in self.knoten.values()) + 1
        self.cw = W / self.ncol
        self.kopf = 30 if self.bahnen else 4

    def farbe(self, rolle, default="petrol"):
        r = self.rollen.get(rolle, {}).get("farbe", rolle if rolle in FARBEN else default)
        return FARBEN.get(r, FARBEN[default])

    # ── Größen ──
    def masse(self):
        for k in self.knoten.values():
            art = k["art"]
            bw = k.get("breite_anteil", 1.0) * self.cw - (34 if art in ("frage",) and self.stil == "fluss" else 22)
            k["w"] = bw
            if art in ("start", "ende", "abbruch", "ereignis"):
                k["r"] = 12
                lb = min(self.cw / 2 - 22, 150)
                k["zeilen"] = umbrechen(k.get("text", ""), lb, self.FS, 500)
                k["unter_z"] = umbrechen(k.get("unter", ""), lb, self.FSU) if k.get("unter") else []
                n = len(k["zeilen"]) + len(k["unter_z"])
                k["h"] = max(26, n * self.LH + 2)
                k["w"] = 26
                continue
            if art == "frage" and self.stil == "bpmn":
                k["zeilen"] = umbrechen(k.get("text", ""), self.cw / 2 - 26, self.FSU, 500)
                k["unter_z"] = []
                k["w"] = k["h"] = 34
                continue
            innen = bw - (34 if art == "frage" else 18)
            gew = 700 if art in ("ergebnis",) else 500
            k["zeilen"] = umbrechen(k.get("text", ""), innen, self.FS, gew)
            k["unter_z"] = umbrechen(k["unter"], innen, self.FSU) if k.get("unter") else []
            k["liste_z"] = [umbrechen(p, innen - 9, self.FSU) for p in k.get("liste", [])]
            n = len(k["zeilen"]) * self.LH + len(k["unter_z"]) * 12.5 + sum(len(z) for z in k["liste_z"]) * 12.5
            n += 4 if k["liste_z"] else 0
            k["h"] = max(36, n + 16)

    def raster(self):
        nrow = max(k["zeile"] for k in self.knoten.values()) + 1
        hoehen = [max([k["h"] for k in self.knoten.values() if k["zeile"] == r] + [20]) for r in range(nrow)]
        luft = self.b.get("zeilenabstand", 30)
        y = self.kopf + luft * 0.6
        self.zeilen_y = []
        for h in hoehen:
            self.zeilen_y.append(y + h / 2)
            y += h + luft
        self.hoehe = y - luft * 0.4 + 6
        for k in self.knoten.values():
            sp = k["spalte"] + k.get("versatz", 0)
            k["cx"] = self.cw * sp + self.cw / 2
            k["cy"] = self.zeilen_y[k["zeile"]]
            if k["art"] in ("start", "ende", "abbruch", "ereignis") or (k["art"] == "frage" and self.stil == "bpmn"):
                k["cy"] = self.zeilen_y[k["zeile"]]

    # ── Anschlüsse und Wege ──
    def port(self, k, seite, versatz=0):
        if k["art"] in ("start", "ende", "abbruch", "ereignis"):
            rx = ry = k["r"]
        else:
            rx, ry = k["w"] / 2, (k["h"] / 2 if k["art"] != "frage" or self.stil == "fluss" else k["h"] / 2)
        return {"oben": (k["cx"] + versatz, k["cy"] - ry), "unten": (k["cx"] + versatz, k["cy"] + ry),
                "links": (k["cx"] - rx, k["cy"] + versatz), "rechts": (k["cx"] + rx, k["cy"] + versatz)}[seite]

    def auto(self, a, z):
        if a["spalte"] == z["spalte"]:
            return ("unten", "oben") if z["zeile"] > a["zeile"] else ("oben", "unten")
        if a["zeile"] == z["zeile"]:
            return ("rechts", "links") if z["spalte"] > a["spalte"] else ("links", "rechts")
        seite = "rechts" if z["spalte"] > a["spalte"] else "links"
        if a["art"] == "frage":
            return (seite, "oben" if z["zeile"] > a["zeile"] else "unten")
        return ("unten", "oben") if z["zeile"] > a["zeile"] else ("oben", "unten")

    def weg(self, k):
        a, z = self.knoten[k["von"]], self.knoten[k["nach"]]
        aus, ein = k.get("aus"), k.get("ein")
        if not aus or not ein:
            aa, ee = self.auto(a, z)
            aus, ein = aus or aa, ein or ee
        p, q = self.port(a, aus, k.get("aus_versatz", 0)), self.port(z, ein, k.get("ein_versatz", 0))
        senk = ("oben", "unten")
        if aus in senk and ein in senk:
            if abs(p[0] - q[0]) < 0.5:
                pts = [p, q]
            else:
                ym = k.get("mitte_y", (p[1] + q[1]) / 2)
                if ym == "unter":  # Bogen unter der Zeile hindurch (überspringt Nachbarknoten)
                    zeile = [x for x in self.knoten.values() if x["zeile"] == a["zeile"]]
                    ym = max(x["cy"] + x["h"] / 2 for x in zeile) + 14
                    self.extra_unten = max(getattr(self, "extra_unten", 0), 34 if k.get("text") else 22)
                pts = [p, (p[0], ym), (q[0], ym), q]
        elif aus not in senk and ein in senk:
            pts = [p, (q[0], p[1]), q]
        elif aus in senk and ein not in senk:
            pts = [p, (p[0], q[1]), q]
        else:
            if abs(p[1] - q[1]) < 0.5:
                pts = [p, q]
            else:
                xm = k.get("mitte_x", (p[0] + q[0]) / 2)
                pts = [p, (xm, p[1]), (xm, q[1]), q]
        return pts, aus

    # ── Zeichnen ──
    def text(self, x, y, s, groesse, gewicht=400, farbe=TINTE, anker="middle", kursiv=False):
        st = ' font-style="italic"' if kursiv else ""
        return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anker}" font-family="Alegreya Sans" font-size="{groesse}" '
                f'font-weight="{gewicht}" fill="{farbe}"{st}>{e(s)}</text>')

    def knoten_svg(self, k):
        d, m, h = self.farbe(k.get("rolle", "kapitel"))
        x, y, w, hh, art = k["cx"], k["cy"], k["w"], k["h"], k["art"]
        o = []
        if art in ("start", "ende", "abbruch", "ereignis"):
            sw = {"start": 1.6, "ende": 3.6, "abbruch": 3.6, "ereignis": 1.4}[art]
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{k["r"]}" fill="#FFFFFF" stroke="{d}" stroke-width="{sw}"/>')
            if art == "ereignis":
                o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{k["r"] - 3}" fill="none" stroke="{d}" stroke-width="1.2"/>')
            if art == "abbruch":
                o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" fill="{d}"/>')
            n = len(k["zeilen"]) + len(k["unter_z"])
            ty = y - (n * self.LH) / 2 + 10
            lx, la = (x - 18, "end") if k.get("beschriftung") == "links" else (x + 18, "start")
            for z in k["zeilen"]:
                o.append(self.text(lx, ty, z, self.FS, 700, d, la))
                ty += self.LH
            for z in k["unter_z"]:
                o.append(self.text(lx, ty, z, self.FSU, 400, "#4A5468", la))
                ty += self.LH
            return "".join(o)
        if art == "frage" and self.stil == "bpmn":
            r = 17
            o.append(f'<path d="M{x:.1f},{y - r:.1f} L{x + r:.1f},{y:.1f} L{x:.1f},{y + r:.1f} L{x - r:.1f},{y:.1f} Z" fill="{h}" stroke="{d}" stroke-width="1.5"/>')
            zeichen = k.get("zeichen", "×")
            if zeichen == "+":
                o.append(f'<path d="M{x - 7:.1f},{y:.1f} H{x + 7:.1f} M{x:.1f},{y - 7:.1f} V{y + 7:.1f}" stroke="{d}" stroke-width="2.6"/>')
            else:
                o.append(f'<path d="M{x - 5.5:.1f},{y - 5.5:.1f} L{x + 5.5:.1f},{y + 5.5:.1f} M{x + 5.5:.1f},{y - 5.5:.1f} L{x - 5.5:.1f},{y + 5.5:.1f}" stroke="{d}" stroke-width="2.4"/>')
            ty = y - (len(k["zeilen"]) * 12) / 2 + 9
            lx, la = (x - 24, "end") if k.get("beschriftung") == "links" else (x + 24, "start")
            for z in k["zeilen"]:
                o.append(self.text(lx, ty, z, self.FSU, 500, d, la, kursiv=True))
                ty += 12
            return "".join(o)
        x0, y0 = x - w / 2, y - hh / 2
        if art == "frage":
            sp = 14
            o.append(f'<path d="M{x0:.1f},{y:.1f} L{x0 + sp:.1f},{y0:.1f} H{x0 + w - sp:.1f} L{x0 + w:.1f},{y:.1f} L{x0 + w - sp:.1f},{y0 + hh:.1f} H{x0 + sp:.1f} Z" '
                     f'fill="{h}" stroke="{d}" stroke-width="1.6"/>')
        elif art == "ergebnis" and k["liste_z"]:
            o.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{hh:.1f}" rx="8" fill="{h}" stroke="{d}" stroke-width="2.2"/>')
        elif art == "ergebnis":
            o.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{hh:.1f}" rx="{min(hh / 2, 16):.1f}" fill="{d}"/>')
        elif art == "notiz":
            o.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{hh:.1f}" rx="3" fill="{h}" stroke="{d}" stroke-width="1" stroke-dasharray="3 2.5"/>')
        elif art == "zustand":
            o.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{hh:.1f}" rx="3" fill="#FFFFFF" stroke="{d}" stroke-width="1.4"/>'
                     f'<rect x="{x0:.1f}" y="{y0:.1f}" width="5" height="{hh:.1f}" fill="{d}"/>')
        else:  # aufgabe
            o.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{hh:.1f}" rx="7" fill="{h}" stroke="{d}" stroke-width="1.4"/>')
        weiss = art == "ergebnis" and not k["liste_z"]
        blk = len(k["zeilen"]) * self.LH + len(k["unter_z"]) * 12.5 + sum(len(z) for z in k["liste_z"]) * 12.5 + (4 if k["liste_z"] else 0)
        ty = y - blk / 2 + 10
        links = bool(k["liste_z"])
        tx = x0 + 11 if links else x
        anker = "start" if links else "middle"
        for z in k["zeilen"]:
            o.append(self.text(tx, ty, z, self.FS, 700 if art == "ergebnis" else 500, "#FFFFFF" if weiss else d, anker))
            ty += self.LH
        for z in k["unter_z"]:
            o.append(self.text(tx, ty - 1, z, self.FSU, 400, "#FFFFFF" if weiss else "#4A5468", anker))
            ty += 12.5
        if k["liste_z"]:
            ty += 4
            for punkt in k["liste_z"]:
                o.append(f'<circle cx="{x0 + 14:.1f}" cy="{ty - 3.6:.1f}" r="2" fill="{d}"/>')
                for z in punkt:
                    o.append(self.text(x0 + 21, ty, z, self.FSU, 400, "#FFFFFF" if weiss else TINTE, "start"))
                    ty += 12.5
        return "".join(o)

    def kante_svg(self, k):
        pts, aus = self.weg(k)
        art = k.get("art", "fluss")
        a = self.knoten[k["von"]]
        d = self.farbe(k.get("rolle", a.get("rolle", "kapitel")))[0] if art != "bezug" else "#7A8292"
        pfad = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        stil = {"fluss": f'stroke="{d}" stroke-width="1.5" marker-end="url(#pf-{k["_i"]})"',
                "nachricht": f'stroke="{d}" stroke-width="1.4" stroke-dasharray="6 4" marker-end="url(#po-{k["_i"]})" marker-start="url(#kr-{k["_i"]})"',
                "bezug": 'stroke="#7A8292" stroke-width="1.1" stroke-dasharray="1.5 3"'}[art]
        o = [f'<defs><marker id="pf-{k["_i"]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
             f'<path d="M0,0 L10,5 L0,10 Z" fill="{d}"/></marker>'
             f'<marker id="po-{k["_i"]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
             f'<path d="M0,0 L10,5 L0,10 Z" fill="#FFFFFF" stroke="{d}" stroke-width="1.2"/></marker>'
             f'<marker id="kr-{k["_i"]}" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="7" markerHeight="7">'
             f'<circle cx="5" cy="5" r="3.6" fill="#FFFFFF" stroke="{d}" stroke-width="1.2"/></marker></defs>',
             f'<path d="{pfad}" fill="none" {stil} stroke-linejoin="round"/>']
        if k.get("text") and k.get("text_an") == "mitte":
            stuecke = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1) if abs(pts[i][1] - pts[i + 1][1]) < 0.5]
            (x1, y1), (x2, y2) = max(stuecke, key=lambda st: abs(st[1][0] - st[0][0]))
            o.append(f'<text x="{(x1 + x2) / 2:.1f}" y="{y1 + 13:.1f}" text-anchor="middle" font-family="Alegreya Sans" font-size="{self.FSL}" font-weight="700" '
                     f'fill="{d}" stroke="#FFFFFF" stroke-width="3" paint-order="stroke">{e(k["text"])}</text>')
        elif k.get("text") and k.get("text_an") == "ende":
            (x1, y1), (x2, y2) = pts[-2], pts[-1]
            if abs(y1 - y2) < 0.5:
                lx, ly, anker = (x2 - 10, y2 - 6, "end") if x2 > x1 else (x2 + 10, y2 - 6, "start")
            else:
                lx, ly, anker = x2 + 6, y2 - 8, "start"
            lx += k.get("text_dx", 0)
            ly += k.get("text_dy", 0)
            o.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anker}" font-family="Alegreya Sans" font-size="{self.FSL}" font-weight="700" '
                     f'fill="{d}" stroke="#FFFFFF" stroke-width="3" paint-order="stroke">{e(k["text"])}</text>')
        elif k.get("text"):
            (x1, y1), (x2, y2) = pts[0], pts[1]
            senk = abs(x1 - x2) < 0.5
            if senk:
                lx, ly, anker = x1 + 6, y1 + (14 if y2 > y1 else -6), "start"
            else:
                lx, ly, anker = x1 + (8 if x2 > x1 else -8), y1 - 5, "start" if x2 > x1 else "end"
            lx += k.get("text_dx", 0)
            ly += k.get("text_dy", 0)
            o.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anker}" font-family="Alegreya Sans" font-size="{self.FSL}" font-weight="700" '
                     f'fill="{d}" stroke="#FFFFFF" stroke-width="3" paint-order="stroke">{e(k["text"])}</text>')
        return "".join(o)

    def svg(self):
        self.masse()
        self.raster()
        for k in self.b.get("kanten", []):  # Wege vorab berechnen (Platzbedarf unter der Zeile)
            self.weg(k)
        H = self.hoehe + 16 + getattr(self, "extra_unten", 0)
        o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H:.0f}" role="img" aria-label="{e(self.b["titel"])}">']
        for i, bahn in enumerate(self.bahnen):
            d, m, h = self.farbe(bahn["rolle"])
            x = i * self.cw
            o.append(f'<rect x="{x + 2:.1f}" y="0" width="{self.cw - 4:.1f}" height="{H - 14:.1f}" rx="5" fill="{h}" opacity="0.55"/>')
            o.append(f'<rect x="{x + 2:.1f}" y="0" width="{self.cw - 4:.1f}" height="22" rx="5" fill="{d}"/>')
            o.append(self.text(x + self.cw / 2, 15.2, bahn["name"], 11.4, 700, "#FFFFFF"))
        _ZAEHLER[0] += 1
        for i, k in enumerate(self.b.get("kanten", [])):
            k["_i"] = f'd{_ZAEHLER[0]}-{i}'
        for k in [k for k in self.b.get("kanten", []) if k.get("art") == "bezug"]:
            o.append(self.kante_svg(k))
        for k in self.knoten.values():
            o.append(self.knoten_svg(k))
        for k in [k for k in self.b.get("kanten", []) if k.get("art") != "bezug"]:
            o.append(self.kante_svg(k))
        o.append(f'<text class="t-wz" x="{W - 3}" y="{H - 3:.0f}" text-anchor="end">{VERMERK}</text>')
        o.append("</svg>")
        return "".join(o)

    def klartext(self):
        teile = []
        for k in self.b.get("kanten", []):
            a, z = self.knoten[k["von"]], self.knoten[k["nach"]]
            teile.append(f'{a.get("text", "")} → {z.get("text", "")}' + (f' ({k["text"]})' if k.get("text") else ""))
        return "; ".join(teile)


def pruefe_diagramm(b):
    """Strukturprüfung: Kennungen, Raster, Kanten, Bahnen. → Liste der Fehler."""
    f = []
    ids = [k["id"] for k in b["knoten"]]
    for i in {i for i in ids if ids.count(i) > 1}:
        f.append(f'Knoten doppelt: {i}')
    bahnen = {x["rolle"] for x in b.get("bahnen", [])}
    belegt = {}
    for k in b["knoten"]:
        if b.get("bahnen") and k.get("bahn") not in bahnen:
            f.append(f'Knoten {k["id"]}: Bahn fehlt oder unbekannt')
        if not b.get("bahnen") and "spalte" not in k:
            f.append(f'Knoten {k["id"]}: Spalte fehlt')
        zelle = (k.get("bahn", k.get("spalte")), k.get("zeile"))
        if zelle in belegt:
            f.append(f'Knoten {k["id"]} und {belegt[zelle]} belegen dieselbe Zelle')
        belegt[zelle] = k["id"]
    for k in b.get("kanten", []):
        for s in ("von", "nach"):
            if k[s] not in ids:
                f.append(f'Kante verweist auf unbekannten Knoten {k[s]}')
    return f

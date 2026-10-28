#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit · bild.py (3.5)

Bettet verknüpfte Rasterbilder (variante „bild“ mit „datei“) als data-URI in eine
werk.json oder exam.json ein, damit die Datei selbsttragend bleibt: Sie wird bei jedem
Werk mitgeliefert, die Bilddateien gehen dagegen leicht verloren.

Dabei wird jedes Bild auf höchstens 2.400 px Breite verkleinert (das sind gut 360 dpi
auf voller Satzspiegelbreite) und von Metadaten befreit (EXIF, auch GPS-Ortsangaben).
Das Format bleibt erhalten. Bereits eingebettete Bilder werden mit --alle ebenso behandelt.

    python3 bild.py werk.json --einbetten [--alle] [--max-breite 2400]
"""
import argparse
import base64
import io
import json
import sys
from pathlib import Path

MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def aufbereiten(roh, max_breite):
    """→ (Bytes, MIME, Breite vorher, Breite nachher)"""
    from PIL import Image
    im = Image.open(io.BytesIO(roh))
    fmt = im.format
    if fmt not in MIME:
        raise ValueError(f"Format {fmt} nicht erlaubt (PNG, JPEG, WebP)")
    vorher = im.width
    if im.width > max_breite:
        im = im.resize((max_breite, round(im.height * max_breite / im.width)), Image.LANCZOS)
    aus = io.BytesIO()
    if fmt == "JPEG":
        im.convert("RGB").save(aus, "JPEG", quality=88, optimize=True, progressive=True)
    elif fmt == "PNG":
        im.save(aus, "PNG", optimize=True)
    else:
        im.save(aus, "WEBP", quality=88)
    return aus.getvalue(), MIME[fmt], vorher, im.width


def durchlaufe(obj, ordner, max_breite, alle, bericht):
    if isinstance(obj, dict):
        if obj.get("variante") == "bild" and (obj.get("datei") or (alle and obj.get("daten"))):
            if obj.get("datei"):
                pfad = ordner / obj["datei"]
                if not pfad.is_file():
                    bericht.append(f"FEHLER   {obj.get('titel')}: Datei {obj['datei']} nicht gefunden")
                    return
                roh, herkunft = pfad.read_bytes(), obj["datei"]
            else:
                roh, herkunft = base64.b64decode(obj["daten"].split(",", 1)[1]), "eingebettet"
            neu, mime, vorher, nachher = aufbereiten(roh, max_breite)
            obj.pop("datei", None)
            obj["daten"] = f"data:{mime};base64," + base64.b64encode(neu).decode("ascii")
            bericht.append(f"eingebettet  {obj.get('titel')}: {herkunft}, {vorher} → {nachher} px, "
                           f"{len(roh) // 1024} → {len(neu) // 1024} KB")
            return
        for v in obj.values():
            durchlaufe(v, ordner, max_breite, alle, bericht)
    elif isinstance(obj, list):
        for v in obj:
            durchlaufe(v, ordner, max_breite, alle, bericht)


def main():
    ap = argparse.ArgumentParser(description="Terra: Bilder einbetten")
    ap.add_argument("json")
    ap.add_argument("--einbetten", action="store_true", required=True)
    ap.add_argument("--alle", action="store_true", help="auch bereits eingebettete Bilder verkleinern und bereinigen")
    ap.add_argument("--max-breite", type=int, default=2400)
    a = ap.parse_args()
    pfad = Path(a.json).resolve()
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    bericht = []
    durchlaufe(daten, pfad.parent, a.max_breite, a.alle, bericht)
    if any(z.startswith("FEHLER") for z in bericht):
        print("\n".join(bericht))
        sys.exit("Abbruch: nichts geschrieben")
    if bericht:
        pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(bericht) or "keine verknüpften Bilder gefunden")
    print(f"{len(bericht)} Bild(er) eingebettet → {pfad.name}")


if __name__ == "__main__":
    main()

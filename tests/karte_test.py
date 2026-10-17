# (c) Oliver Bedernik · Terra-Kit · Browsertest der Wissenslandkarte
# Aufruf: python3 karte.py werk.json --lokal --aus /tmp/k && python3 tests/karte_test.py /tmp/k/<datei>_karte_lokal.html [name]
# Prüft: Konsolenfehler, Überlappungen, Querverweis, Suche, Dunkelmodus, mobilen Überlauf, Tippflächen; erzeugt Screenshots.
import sys, json
from playwright.sync_api import sync_playwright
datei = sys.argv[1]; name = sys.argv[2] if len(sys.argv) > 2 else "karte"
fehler = []
with sync_playwright() as p:
    b = p.chromium.launch(args=["--allow-file-access-from-files"])
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.on("console", lambda m: fehler.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: fehler.append(str(e)))
    pg.goto("file://" + datei); pg.wait_for_function("window.__terra && window.__terra.bereit", timeout=20000); pg.wait_for_timeout(400)
    pg.screenshot(path=f"{name}_1_gesamt.png")
    # Überlappung von Kacheln und Gebieten
    ueber = pg.evaluate("""() => {
      const out = []; const rs = [...document.querySelectorAll('.region')];
      for (let i=0;i<rs.length;i++) for (let j=i+1;j<rs.length;j++){const a=rs[i]._box,b=rs[j]._box; if(a.x<b.x+b.b&&b.x<a.x+a.b&&a.y<b.y+b.h&&b.y<a.y+a.h) out.push('Gebiete '+rs[i].id+'/'+rs[j].id);}
      for (const r of rs){ const ks=[...r.querySelectorAll('.karte-kachel')].map(k=>({c:k.dataset.code,x:k.offsetLeft,y:k.offsetTop,b:k.offsetWidth,h:k.offsetHeight}));
        for (let i=0;i<ks.length;i++){ const a=ks[i]; if (a.y+a.h > r.offsetHeight+1 || a.x+a.b > r.offsetWidth+1) out.push('Kachel ragt aus Gebiet: '+a.c);
          for (let j=i+1;j<ks.length;j++){const c=ks[j]; if(a.x<c.x+c.b&&c.x<a.x+a.b&&a.y<c.y+c.h&&c.y<a.y+a.h) out.push('Kacheln '+a.c+'/'+c.c);} } }
      return out; }""")
    # Querverweis anklicken: erste .vw-Verknüpfung
    pg.evaluate("window.__terra.zuKachel('A1', false)"); pg.wait_for_timeout(700)
    pg.screenshot(path=f"{name}_2_kachel.png")
    ziel = pg.evaluate("""() => { const a = document.querySelector('#welt a.vw'); if(!a) return null; a.click(); return a.getAttribute('href'); }""")
    pg.wait_for_timeout(700)
    hash_ = pg.evaluate("location.hash")
    # Suche
    pg.click("#suche"); pg.keyboard.type("Neutralit" if "Historica" in datei else "Barwert"); pg.wait_for_timeout(300)
    treffer = pg.evaluate("document.querySelectorAll('#reg-liste .reg-eintrag').length")
    pg.screenshot(path=f"{name}_3_suche.png")
    pg.keyboard.press("Enter"); pg.wait_for_timeout(700)
    # Dunkelmodus
    pg.keyboard.press("Escape"); pg.click("#k-thema"); pg.click("#k-thema"); pg.wait_for_timeout(200)
    thema = pg.evaluate("document.documentElement.dataset.theme")
    pg.evaluate("window.__terra.ganzeKarte(true)"); pg.wait_for_timeout(300)
    pg.screenshot(path=f"{name}_4_dunkel.png")
    pg.evaluate("window.__terra.zuKachel('B1', false)"); pg.wait_for_timeout(700)
    pg.screenshot(path=f"{name}_5_dunkel_kachel.png")
    # Mobil
    m = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    m.on("pageerror", lambda e: fehler.append("mobil: " + str(e)))
    m.goto("file://" + datei); m.wait_for_function("window.__terra && window.__terra.bereit", timeout=20000); m.wait_for_timeout(400)
    m.screenshot(path=f"{name}_6_mobil.png")
    ueberlauf = m.evaluate("document.documentElement.scrollWidth > innerWidth || document.body.scrollWidth > innerWidth")
    kleine = m.evaluate("""() => [...document.querySelectorAll('.kopf button, .fuss button')].filter(b=>{const r=b.getBoundingClientRect(); return r.width && (r.width<44||r.height<40);}).map(b=>b.id||b.textContent.trim()).slice(0,6)""")
    m.click("#k-register"); m.wait_for_timeout(400); m.screenshot(path=f"{name}_7_mobil_register.png")
    b.close()
print(json.dumps({"konsolenfehler": fehler, "ueberlappungen": ueber, "verweis": ziel, "hash_nach_klick": hash_, "suchtreffer": treffer,
                  "thema": thema, "mobil_seitlicher_ueberlauf": ueberlauf, "zu_kleine_knoepfe": kleine}, ensure_ascii=False, indent=1))

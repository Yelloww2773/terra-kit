/* (c) Oliver Bedernik · Terra-Kit · montage.js · Seitenmontage (Standard 3.1)
   Verteilt atomare Einheiten aus #quelle auf feste Seiten in #buch.
   Seitenarten: deck (Titelseite), titelei (ohne Kolumnentitel), spalten (zweispaltig,
   Inhaltsverzeichnis), normal, quer. Einheiten werden nie geteilt; Ausnahme Tabellen
   (nur zwischen Zeilen, Kopf wiederholt). Überhohe Abbildungen werden bis 75 % verkleinert.
   Danach: Daumenregister, Seitenzahlen, Verzeichnis, Silbentrennung fixieren, Prüfung. */
(async function () {
  await document.fonts.ready;
  const META = JSON.parse(document.getElementById('meta').textContent);
  const PROV = META.provinzen;
  const QUELLE = document.getElementById('quelle');
  const BUCH = document.getElementById('buch');
  const einheiten = Array.from(QUELLE.children);
  const bericht = { seiten: [], teilungen: [], skalierungen: [], fehler: [], warnungen: [] };
  const begonnen = new Set();
  const MIN_ZEILEN = 3, MIN_SKALA = 0.75, TOL = 0.75;
  let seite = null, koerper = null, art = null, akt = null;

  /* Daumenregister: Reiter am rechten Rand, Position nach Provinzreihenfolge */
  function daumen(p, nurAktuelle, oben) {
    const H = p.classList.contains('quer') ? 210 : 297, n = PROV.length, o = oben || 28, u = 30;
    const h = Math.min(30, (H - o - u) / n - 2.5);
    let html = '';
    PROV.forEach((v, i) => {
      if (nurAktuelle && (!akt || akt.code !== v.code)) return;
      const etikett = p.classList.contains('deck') ? '<em><b>Provinz ' + v.nr + '</b>' + v.de + '</em>' : '';
      html += '<div class="daumen farbe-' + v.farbe + '" style="top:' + (o + i * (h + 2.5)).toFixed(1) +
              'mm;height:' + h.toFixed(1) + 'mm"><span>' + v.nr + '</span>' + etikett + '</div>';
    });
    p.insertAdjacentHTML('beforeend', html);
  }

  function neueSeite(a) {
    const p = document.createElement('section');
    p.className = 'page ' + a;
    const wz = '<div class="wz" aria-hidden="true"><span>(c) Oliver Bedernik</span></div>';
    const rechts = (a === 'normal' || a === 'quer') && akt ? 'Provinz ' + akt.nr + ' · ' + akt.name : '';
    const kopf = '<div class="kopfzeile"><span class="l">' + META.kopf_links + '</span><span class="r">' + rechts + '</span></div>';
    const fuss = '<div class="fusszeile"><span class="l">' + META.fuss_links + '</span><span class="m">(c) Oliver Bedernik</span><span class="r seitennr"></span></div>';
    if (a === 'deck') p.innerHTML = '<div class="koerper"></div>' + wz;
    else p.innerHTML = kopf + '<div class="koerper"></div>' + fuss + wz;
    BUCH.appendChild(p);
    if (a === 'deck') daumen(p, false, 150);
    else if (a === 'spalten') daumen(p, false);
    else if (a === 'normal' || a === 'quer') daumen(p, true);
    seite = p; koerper = p.querySelector('.koerper'); art = a;
    return p;
  }

  function inhaltUnten() {
    let max = koerper.getBoundingClientRect().top;
    for (const c of koerper.children) max = Math.max(max, c.getBoundingClientRect().bottom);
    return max;
  }
  function ueberlauf() {
    const kb = koerper.getBoundingClientRect();
    if (art === 'spalten') {
      for (const c of koerper.children) {
        for (const r of c.getClientRects()) if (r.right > kb.right + TOL || r.bottom > kb.bottom + TOL) return true;
      }
      return false;
    }
    return inhaltUnten() > kb.bottom + TOL;
  }
  function leer() { return koerper.children.length === 0; }
  function seitenart(u) { return u.dataset.seite || (u.dataset.quer ? 'quer' : 'normal'); }

  function behaelter(u) {
    const code = u.dataset.kachel;
    if (!code) return koerper;
    const letzte = koerper.lastElementChild;
    if (letzte && letzte.classList.contains('kachel') && letzte.dataset.code === code) return letzte;
    const k = document.createElement('div');
    k.className = 'kachel farbe-' + (u.dataset.farbe || 'tinte');
    k.dataset.code = code;
    if (begonnen.has(code)) {
      k.classList.add('fortsetzung');
      k.innerHTML = '<div class="fkopf"><span class="code">' + code + '</span>' + u.dataset.titel + ' <i>(Fortsetzung)</i></div>';
    }
    koerper.appendChild(k);
    return k;
  }
  function zurueck(u, ziel) {
    if (u.parentNode) u.parentNode.removeChild(u);
    if (ziel !== koerper && ziel.querySelectorAll('.unit').length === 0) ziel.remove();
  }
  function versuche(u) {
    const ziel = behaelter(u);
    ziel.appendChild(u);
    if (!ueberlauf()) { if (u.dataset.kachel) begonnen.add(u.dataset.kachel); return true; }
    zurueck(u, ziel);
    return false;
  }
  function passtAufLeereSeite(u) {
    const alt = [seite, koerper, art];
    const probe = neueSeite(alt[2]);
    const ziel = behaelter(u); ziel.appendChild(u);
    const ok = !ueberlauf();
    zurueck(u, ziel);
    probe.remove();
    [seite, koerper, art] = alt;
    return ok;
  }

  function teileTabelle(u) {
    const vorlage = u.cloneNode(true);
    const zeilen = Array.from(u.querySelector('table.teilbar').tBodies[0].rows);
    let rest = zeilen, teil = 0;
    const seitenNr = [];
    while (rest.length) {
      const stueck = vorlage.cloneNode(true);
      if (teil > 0) {
        stueck.querySelectorAll('.kkopf, .vor-tabelle').forEach(e => e.remove());
        stueck.querySelectorAll('[id]').forEach(e => e.removeAttribute('id'));
        const st = stueck.querySelector('.schema-titel');
        if (st) st.insertAdjacentHTML('beforeend', '<span class="forts">(Fortsetzung)</span>');
      }
      const tb = stueck.querySelector('table.teilbar').tBodies[0];
      tb.innerHTML = '';
      const ziel = behaelter(u);
      ziel.appendChild(stueck);
      let n = 0;
      for (const r of rest) {
        tb.appendChild(r);
        if (ueberlauf()) { tb.removeChild(r); break; }
        n++;
      }
      const hatteInhalt = koerper.children.length > 1 || (ziel !== koerper && ziel.querySelectorAll('.unit').length > 1);
      if (n === 0 || (n < MIN_ZEILEN && n < rest.length && hatteInhalt)) {
        zurueck(stueck, ziel);
        if (leer()) { bericht.fehler.push('Tabellenzeile höher als eine Seite: ' + (u.dataset.kachel || u.dataset.name || '?')); return; }
        neueSeite(art);
        continue;
      }
      rest = rest.slice(n);
      if (u.dataset.kachel) begonnen.add(u.dataset.kachel);
      seitenNr.push(BUCH.children.length);
      if (rest.length) {
        stueck.insertAdjacentHTML('beforeend', '<div class="weiter">Fortsetzung auf der nächsten Seite</div>');
        while (ueberlauf() && tb.rows.length > 1) { const r = tb.rows[tb.rows.length - 1]; rest.unshift(r); tb.removeChild(r); }
        neueSeite(art);
      }
      teil++;
    }
    bericht.teilungen.push({ kachel: u.dataset.kachel || u.dataset.name, teile: teil, seiten: seitenNr, zeilen: zeilen.length });
  }

  function skaliere(u) {
    const fig = u.querySelector('.skalierbar');
    const ziel = behaelter(u);
    ziel.appendChild(u);
    const svg = fig.querySelector('svg');
    const h0 = fig.getBoundingClientRect().height;
    const zuviel = inhaltUnten() - koerper.getBoundingClientRect().bottom + 2;
    const skala = Math.max(0.3, (h0 - zuviel) / h0);
    svg.style.width = (skala * 100).toFixed(1) + '%';
    if (u.dataset.kachel) begonnen.add(u.dataset.kachel);
    bericht.skalierungen.push({ kachel: u.dataset.kachel, skala: +skala.toFixed(3), seite: BUCH.children.length });
    if (skala < MIN_SKALA) bericht.warnungen.push('Abbildung in ' + u.dataset.kachel + ' auf ' + Math.round(skala * 100) + ' % verkleinert (unter Mindestmaß)');
    if (ueberlauf()) bericht.fehler.push('Abbildung in ' + u.dataset.kachel + ' passt auch verkleinert nicht');
  }

  for (const u of einheiten) {
    if (u.dataset.provstart) akt = { code: u.dataset.prov, nr: u.dataset.nr, name: u.dataset.pname, farbe: u.dataset.farbe };
    const sa = seitenart(u);
    const zwang = u.dataset.neueSeite === '1';
    if (!seite || art !== sa || (zwang && !leer()) || sa === 'deck') {
      if (!(seite && leer() && art === sa)) neueSeite(sa);
    }
    if (versuche(u)) continue;
    if (!leer() && passtAufLeereSeite(u)) { neueSeite(art); if (versuche(u)) continue; }
    if (u.querySelector('table.teilbar')) { teileTabelle(u); continue; }
    if (u.querySelector('.skalierbar')) { if (!leer()) neueSeite(art); skaliere(u); continue; }
    const ziel = behaelter(u); ziel.appendChild(u);
    if (u.dataset.kachel) begonnen.add(u.dataset.kachel);
    bericht.fehler.push('Einheit passt auf keine leere Seite: ' + (u.dataset.kachel || u.dataset.name || '?'));
  }
  QUELLE.remove();

  /* Nachbearbeitung: offene Kartenränder, Seitenzahlen, Verzeichnis */
  const karten = Array.from(BUCH.querySelectorAll('.kachel'));
  karten.forEach((k, i) => { const n = karten[i + 1]; if (n && n.dataset.code === k.dataset.code) k.classList.add('offen-unten'); });
  const seiten = Array.from(BUCH.children);
  const N = seiten.length;
  seiten.forEach((p, i) => { const s = p.querySelector('.seitennr'); if (s) s.textContent = 'Seite ' + (i + 1) + ' von ' + N; });
  const seiteVon = el => seiten.indexOf(el.closest('.page')) + 1;
  document.querySelectorAll('[data-ziel]').forEach(span => {
    const z = document.getElementById(span.dataset.ziel);
    if (z) span.textContent = seiteVon(z); else bericht.fehler.push('Verzeichnis: Ziel fehlt ' + span.dataset.ziel);
  });

  /* Silbentrennung fixieren. Am Umbruch rendert Chromium das weiche Trennzeichen
     sichtbar (Breite > 0). Nur dort bleibt ein echter Trennstrich; alle anderen
     Trennstellen werden entfernt, damit der Textlayer durchsuchbar bleibt.
     Reihenfolge ist entscheidend: (1) Tabellenspalten einfrieren, (2) ALLE Trennstellen
     auf dem endgültigen Satz messen, (3) erst dann alle Änderungen anwenden,
     (4) Höhen vorher und nachher vergleichen. */
  const hoehe = () => Array.from(BUCH.querySelectorAll('.unit, .kachel, tr')).map(e => e.getBoundingClientRect().height);
  const h0 = hoehe();
  BUCH.querySelectorAll('table').forEach(t => {
    const muster = Array.from(t.rows).find(r => r.cells.length && Array.from(r.cells).every(c => c.colSpan === 1 && c.getBoundingClientRect().width > 0));
    if (!muster) return;
    const cg = document.createElement('colgroup');
    for (const c of muster.cells) { const col = document.createElement('col'); col.style.width = c.getBoundingClientRect().width + 'px'; cg.appendChild(col); }
    t.style.width = t.getBoundingClientRect().width + 'px';
    t.insertBefore(cg, t.firstChild);
    t.style.tableLayout = 'fixed';
  });
  const h1 = hoehe();
  const diff = (a, b) => a.filter((h, i) => Math.abs(h - b[i]) > 0.5).length;
  const durchEinfrieren = diff(h0, h1);

  const walker = document.createTreeWalker(BUCH, NodeFilter.SHOW_TEXT,
    { acceptNode: n => n.nodeValue.indexOf('\u00AD') >= 0 ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP });
  const plan = [];
  const rg = document.createRange();
  let n; while ((n = walker.nextNode())) {
    const t = n.nodeValue, brueche = new Set();
    for (let i = 0; i < t.length; i++) {
      if (t[i] !== '\u00AD') continue;
      /* Kriterium: Liegen das Zeichen davor und danach auf verschiedenen Zeilen?
         (Die Breite des Trennzeichens allein täuscht bei Ligaturen wie ft, ff, fl.) */
      rg.setStart(n, Math.max(0, i - 1)); rg.setEnd(n, Math.min(t.length, i + 2));
      const zeilen = new Set(Array.from(rg.getClientRects()).filter(r => r.width > 0).map(r => Math.round(r.top)));
      if (zeilen.size > 1) brueche.add(i);
    }
    plan.push([n, brueche]);
  }
  /* Anwenden: Am tatsächlichen Umbruch bleibt das weiche Trennzeichen stehen; das ist
     die Darstellung, die ISO 32000 für Silbentrennung vorsieht (Leser fügen das Wort bei
     Suche und Kopieren wieder zusammen). Ungenutzte Trennstellen werden entfernt.
     Kein Ersatz durch Bindestrich: Das würde den Zeilenumbruch verändern. */
  let trennungen = 0, entfernt = 0;
  for (const [knoten, brueche] of plan) {
    const t = knoten.nodeValue; let neu = '';
    for (let i = 0; i < t.length; i++) {
      if (t[i] !== '\u00AD') { neu += t[i]; continue; }
      if (brueche.has(i)) { neu += t[i]; trennungen++; } else { entfernt++; }
    }
    knoten.nodeValue = neu;
  }
  const h2 = hoehe();
  const durchFixierung = diff(h1, h2);
  const elemente = Array.from(BUCH.querySelectorAll('.unit, .kachel, tr'));
  bericht.verschoben_detail = elemente.map((e, i) => [e, h1[i], h2[i]]).filter(([e, a, b]) => Math.abs(a - b) > 0.5)
    .map(([e, a, b]) => e.tagName + ' ' + (a.toFixed(1)) + '→' + b.toFixed(1) + ' ' + e.textContent.replace(/\s+/g, ' ').slice(0, 90));
  bericht.silbentrennung = { umbrochen: trennungen, entfernt, verschoben_einfrieren: durchEinfrieren, verschoben_fixierung: durchFixierung };
  if (durchEinfrieren) bericht.fehler.push('Spalten einfrieren hat ' + durchEinfrieren + ' Elemente in der Höhe verändert');
  if (durchFixierung) bericht.fehler.push('Silbentrennung hat ' + durchFixierung + ' Elemente in der Höhe verändert (Satz verschoben)');

  /* Prüfung: Überlauf, Grenzschnitte, Füllstand */
  seiten.forEach((p, i) => {
    const k = p.querySelector('.koerper');
    const kb = k.getBoundingClientRect();
    const spalten = p.classList.contains('spalten');
    let unten = kb.top, rechts = kb.left;
    for (const c of k.children) for (const r of c.getClientRects()) { unten = Math.max(unten, r.bottom); rechts = Math.max(rechts, r.right); }
    const fuell = (unten - kb.top) / kb.height;
    const ueber = unten > kb.bottom + TOL || rechts > kb.right + TOL;
    let schnitte = 0;
    p.querySelectorAll('.unit').forEach(u => {
      for (const r of u.getClientRects()) if (r.bottom > kb.bottom + TOL || r.top < kb.top - TOL || r.right > kb.right + TOL) { schnitte++; break; }
    });
    const nurKopf = k.children.length === 1 && k.querySelector('.provkopf') && !k.querySelector('.kachel');
    const a = ['deck', 'titelei', 'spalten', 'quer'].find(x => p.classList.contains(x)) || 'normal';
    const erste = k.querySelector('.unit');
    bericht.seiten.push({ nr: i + 1, art: a, zwang: !!(erste && erste.dataset.neueSeite === '1'), fuellstand: +Math.min(fuell, 9.99).toFixed(3),
      einheiten: p.querySelectorAll('.unit').length, ueberlauf: ueber, schnitte });
    if (ueber) bericht.fehler.push('Seite ' + (i + 1) + ': Überlauf');
    if (schnitte) bericht.fehler.push('Seite ' + (i + 1) + ': ' + schnitte + ' Einheit(en) über der Satzspiegelgrenze');
    if (nurKopf) bericht.warnungen.push('Seite ' + (i + 1) + ': Provinzkopf allein auf der Seite');
  });
  window.__bericht = bericht;
  window.__fertig = true;
})();

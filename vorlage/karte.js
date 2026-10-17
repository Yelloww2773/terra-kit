/* (c) Oliver Bedernik · Terra-Kit · karte.js · Wissenslandkarte (Standard 3.1)
   Layout der Territorien, Kamera (Verschieben, Zoomen, Fliegen), Minikarte, Register,
   Querverweise, Relevanzfilter, Hell/Dunkel, gespeicherte Ansicht. Keine Bibliotheken. */
(function () {
  'use strict';
  const D = JSON.parse(document.getElementById('terra-daten').textContent);
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const flaeche = $('#flaeche'), welt = $('#welt');
  const SPEICHER = 'terra:' + D.titel;
  const KACHEL = 440, LUECKE = 22, RAND = 28, ABSTAND = 90;
  const ruhig = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const speichere = (k, v) => { try { localStorage.setItem(SPEICHER + ':' + k, JSON.stringify(v)); } catch (e) {} };
  const lade = k => { try { const v = localStorage.getItem(SPEICHER + ':' + k); return v ? JSON.parse(v) : null; } catch (e) { return null; } };

  /* ── Theme ─────────────────────────────────────────────────────── */
  const THEMEN = ['auto', 'light', 'dark'], THEMA_TXT = { auto: 'Automatisch', light: 'Hell', dark: 'Dunkel' };
  function setzeThema(t) {
    if (t === 'auto') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', t);
    const k = $('#k-thema'); k.title = 'Darstellung: ' + THEMA_TXT[t]; k.setAttribute('aria-label', k.title); $('#k-thema .lbl').textContent = THEMA_TXT[t];
    try { localStorage.setItem('terra:thema', t); } catch (e) {}
  }
  let thema = 'auto'; try { thema = localStorage.getItem('terra:thema') || 'auto'; } catch (e) {}
  setzeThema(thema);
  $('#k-thema').addEventListener('click', () => { thema = THEMEN[(THEMEN.indexOf(thema) + 1) % 3]; setzeThema(thema); });

  /* ── Aufbereitung im DOM ───────────────────────────────────────── */
  $$('.karte-kachel table').forEach(t => { if (t.closest('.tabwrap')) return; const w = document.createElement('div'); w.className = 'tabwrap'; t.parentNode.insertBefore(w, t); w.appendChild(t); });
  $$('.selbsttest .loes').forEach(l => { const d = document.createElement('details'); d.innerHTML = '<summary>Auflösung zeigen</summary>'; l.parentNode.insertBefore(d, l); d.appendChild(l); });

  /* ── Layout: Territorien im Regalprinzip, Kacheln als Mauerwerk ── */
  let welt_b = 0, welt_h = 0;
  const regionen = $$('.region');
  function layout() {
    const masse = [];
    for (const r of regionen) {
      const kacheln = $$('.karte-kachel', r);
      const n = kacheln.length;
      let sp = r.classList.contains('start') ? 2 : (n <= 3 ? Math.max(n, 1) : n <= 8 ? 3 : 4);
      if (kacheln.some(k => k.classList.contains('breit'))) sp = Math.max(sp, 2);
      const breite = RAND * 2 + sp * KACHEL + (sp - 1) * LUECKE;
      r.style.width = breite + 'px';
      const kopf = r.querySelector('.rkopf, .startkopf');
      const kopfH = kopf ? kopf.getBoundingClientRect().height / kamera.s + 28 : 0;
      const hoehen = new Array(sp).fill(kopfH + 24);
      for (const k of kacheln) {
        if (k.classList.contains('breit') && sp >= 2) {
          let best = 0, bestH = Infinity;
          for (let i = 0; i < sp - 1; i++) { const h = Math.max(hoehen[i], hoehen[i + 1]); if (h < bestH) { bestH = h; best = i; } }
          k.style.left = (RAND + best * (KACHEL + LUECKE)) + 'px'; k.style.top = bestH + 'px';
          const kh = k.getBoundingClientRect().height / kamera.s;
          hoehen[best] = hoehen[best + 1] = bestH + kh + LUECKE;
        } else {
          let i = hoehen.indexOf(Math.min(...hoehen));
          k.style.left = (RAND + i * (KACHEL + LUECKE)) + 'px'; k.style.top = hoehen[i] + 'px';
          hoehen[i] += k.getBoundingClientRect().height / kamera.s + LUECKE;
        }
      }
      const inhaltH = r.classList.contains('start') ? (r.querySelector('.startinhalt').getBoundingClientRect().bottom - r.getBoundingClientRect().top) / kamera.s + 34 : Math.max(...hoehen) + RAND - LUECKE + 8;
      masse.push({ r, b: breite, h: Math.max(inhaltH, kopfH + 60) });
    }
    /* Gebiete im Regalprinzip; Zeilenlänge so gewählt, dass die Karte dem
       Seitenverhältnis der Arbeitsfläche möglichst nahekommt (keine leeren Ränder). */
    const g0 = flaeche.getBoundingClientRect(), vb = Math.max(320, g0.width - 80), vh = Math.max(240, g0.height - 80);
    const setze = proZeile => {
      const zeilen = Math.ceil(masse.length / proZeile), gleich = Math.ceil(masse.length / zeilen);  // gleichmäßig verteilen
      let x = 0, y = 0, zeilenH = 0, maxB = 0; const pos = [];
      masse.forEach((m, i) => {
        if (i > 0 && i % gleich === 0) { y += zeilenH + ABSTAND; x = 0; zeilenH = 0; }
        pos.push([x, y]); x += m.b + ABSTAND; zeilenH = Math.max(zeilenH, m.h); maxB = Math.max(maxB, x - ABSTAND);
      });
      return { pos, b: maxB, h: y + zeilenH };
    };
    let best = null;
    for (let n = 1; n <= masse.length; n++) {
      const v = setze(n), s = Math.min(vb / v.b, vh / v.h);   // Ziel: größter Maßstab beim Einpassen
      if (!best || s > best.s * 1.0001) best = Object.assign(v, { s });
    }
    masse.forEach((m, i) => {
      const [x, y] = best.pos[i];
      m.r.style.left = x + 'px'; m.r.style.top = y + 'px'; m.r.style.height = m.h + 'px'; m.x = x; m.y = y;
      const ln = m.r.querySelector('.landname'); if (ln) ln.style.top = Math.max(40, m.h / 2) + 'px';
    });
    const maxB = best.b, y = best.h, zeilenH = 0;
    welt_b = maxB; welt_h = y + zeilenH;
    welt.style.width = welt_b + 'px'; welt.style.height = welt_h + 'px';
    regionen.forEach((r, i) => { r._box = masse[i]; });
    zeichneMini();
  }

  /* ── Kamera ────────────────────────────────────────────────────── */
  const kamera = { x: 0, y: 0, s: 1 };
  let sMin = 0.05; const sMax = 2.4;
  function anwenden() {
    welt.style.transform = 'translate(' + kamera.x + 'px,' + kamera.y + 'px) scale(' + kamera.s + ')';
    flaeche.classList.toggle('fern', kamera.s < 0.34);
    welt.classList.toggle('fern', kamera.s < 0.34);
    welt.style.setProperty('--inv', (1 / kamera.s).toFixed(3));  /* Landesnamen: feste Bildschirmgröße */
    aktualisiereMini(); aktuelleProvinz();
    clearTimeout(anwenden._t); anwenden._t = setTimeout(() => speichere('ansicht', kamera), 300);
  }
  function groesse() { const r = flaeche.getBoundingClientRect(); return { b: r.width, h: r.height }; }
  function passend(box, rand) {
    const g = groesse(), m = rand == null ? 40 : rand;
    const s = Math.min((g.b - 2 * m) / box.b, (g.h - 2 * m) / box.h, sMax);
    return { s, x: (g.b - box.b * s) / 2 - box.x * s, y: (g.h - box.h * s) / 2 - box.y * s };
  }
  function ganzeKarte(sofort) { const z = passend({ x: 0, y: 0, b: welt_b, h: welt_h }); sMin = Math.min(0.6 * z.s, 0.2); fliege(z, sofort); }
  function fliege(z, sofort) {
    z.s = Math.max(sMin, Math.min(sMax, z.s));
    if (sofort || ruhig) { Object.assign(kamera, z); anwenden(); return; }
    const a = Object.assign({}, kamera), t0 = performance.now(), dauer = 480;
    cancelAnimationFrame(fliege._r);
    const schritt = t => {
      const p = Math.min(1, (t - t0) / dauer), e = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
      kamera.s = a.s + (z.s - a.s) * e; kamera.x = a.x + (z.x - a.x) * e; kamera.y = a.y + (z.y - a.y) * e; anwenden();
      if (p < 1) fliege._r = requestAnimationFrame(schritt);
    };
    fliege._r = requestAnimationFrame(schritt);
  }
  function zoomUm(faktor, px, py) {
    const s = Math.max(sMin, Math.min(sMax, kamera.s * faktor)), f = s / kamera.s;
    kamera.x = px - (px - kamera.x) * f; kamera.y = py - (py - kamera.y) * f; kamera.s = s; anwenden();
  }
  function boxVon(el) {
    let x = 0, y = 0, e = el;
    while (e && e !== welt) { x += e.offsetLeft; y += e.offsetTop; e = e.offsetParent; }
    return { x, y, b: el.offsetWidth, h: el.offsetHeight };
  }
  function zuKachel(code, aufblitzen) {
    const k = document.getElementById('k-' + code);
    const kachel = k && k.closest('.karte-kachel');
    if (!kachel) return false;
    const box = boxVon(kachel), g = groesse();
    const s = Math.min(1.05, Math.max(0.62, (g.h - 60) / box.h), (g.b - 40) / box.b);
    fliege({ s, x: g.b / 2 - (box.x + box.b / 2) * s, y: Math.max(20, g.h / 2 - box.h * s / 2) - box.y * s });
    if (aufblitzen !== false) { kachel.classList.add('blitz'); setTimeout(() => kachel.classList.remove('blitz'), 1600); }
    try { history.replaceState(null, '', '#k-' + code); } catch (e) {}
    return true;
  }
  function zuRegion(r) { fliege(passend(r._box, 30)); }

  /* Zeiger: Ziehen, Zwei-Finger-Zoom, Doppeltippen */
  const zeiger = new Map(); let zug = null, pinch = null;
  flaeche.addEventListener('pointerdown', e => {
    if (e.target.closest('a, button, input, summary, details, .tabwrap')) return;
    zeiger.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (zeiger.size === 1) zug = { x: e.clientX, y: e.clientY, kx: kamera.x, ky: kamera.y, bewegt: false };
    if (zeiger.size === 2) {
      const [a, b] = Array.from(zeiger.values());
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), s: kamera.s, kx: kamera.x, ky: kamera.y, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
      zug = null;
    }
  });
  flaeche.addEventListener('pointermove', e => {
    if (!zeiger.has(e.pointerId)) return;
    zeiger.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const r = flaeche.getBoundingClientRect();
    if (pinch && zeiger.size === 2) {
      const [a, b] = Array.from(zeiger.values());
      const s = Math.max(sMin, Math.min(sMax, pinch.s * Math.hypot(a.x - b.x, a.y - b.y) / pinch.d)), f = s / pinch.s;
      const mx = (a.x + b.x) / 2 - r.left, my = (a.y + b.y) / 2 - r.top, m0x = pinch.mx - r.left, m0y = pinch.my - r.top;
      kamera.s = s; kamera.x = mx - (m0x - pinch.kx) * f; kamera.y = my - (m0y - pinch.ky) * f; anwenden();
    } else if (zug) {
      const dx = e.clientX - zug.x, dy = e.clientY - zug.y;
      if (!zug.bewegt && Math.hypot(dx, dy) > 4) { zug.bewegt = true; flaeche.classList.add('zieht'); flaeche.setPointerCapture(e.pointerId); }
      if (zug.bewegt) { kamera.x = zug.kx + dx; kamera.y = zug.ky + dy; anwenden(); }
    }
  });
  const ende = e => { zeiger.delete(e.pointerId); if (zeiger.size < 2) pinch = null; if (zeiger.size === 0) { zug = null; flaeche.classList.remove('zieht'); } };
  ['pointerup', 'pointercancel', 'pointerleave'].forEach(t => flaeche.addEventListener(t, ende));
  flaeche.addEventListener('wheel', e => {
    e.preventDefault();
    const r = flaeche.getBoundingClientRect();
    const trackpadSchwenk = !e.ctrlKey && (Math.abs(e.deltaX) > 0.5 || (e.deltaMode === 0 && Math.abs(e.deltaY) < 40));
    if (trackpadSchwenk) { kamera.x -= e.deltaX; kamera.y -= e.deltaY; anwenden(); return; }
    const d = e.deltaMode === 1 ? e.deltaY * 30 : e.deltaY;
    zoomUm(Math.exp(-d * (e.ctrlKey ? 0.01 : 0.0016)), e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });
  flaeche.addEventListener('dblclick', e => { const k = e.target.closest('.karte-kachel'); if (k) zuKachel(k.dataset.code); });
  welt.addEventListener('click', e => {
    const a = e.target.closest('a.vw');
    if (a) { e.preventDefault(); zuKachel(a.getAttribute('href').slice(3)); return; }
    const kopf = e.target.closest('.kkopf');
    if (kopf && !(zug && zug.bewegt)) zuKachel(kopf.closest('.karte-kachel').dataset.code, false);
  });

  /* ── Minikarte ─────────────────────────────────────────────────── */
  const mini = $('#mini'), miniSvg = $('#mini svg');
  function zeichneMini() {
    miniSvg.setAttribute('viewBox', '0 0 ' + welt_b + ' ' + welt_h);
    miniSvg.innerHTML = regionen.map(r => {
      const b = r._box; if (!b) return '';
      return '<rect class="farbe-' + (r.dataset.farbe || 'tinte') + '" x="' + b.x + '" y="' + b.y + '" width="' + b.b + '" height="' + b.h +
             '" rx="40" style="fill:var(--p-hell);stroke:var(--p);stroke-width:' + (welt_b / 140) + '"/>';
    }).join('') + '<rect class="vp" x="0" y="0" width="1" height="1"/>';
  }
  function aktualisiereMini() {
    const vp = miniSvg.querySelector('.vp'); if (!vp) return;
    const g = groesse();
    vp.setAttribute('x', -kamera.x / kamera.s); vp.setAttribute('y', -kamera.y / kamera.s);
    vp.setAttribute('width', g.b / kamera.s); vp.setAttribute('height', g.h / kamera.s);
  }
  function miniZiel(e) {
    const r = miniSvg.getBoundingClientRect(), g = groesse();
    const wx = (e.clientX - r.left) / r.width * welt_b, wy = (e.clientY - r.top) / r.height * welt_h;
    kamera.x = g.b / 2 - wx * kamera.s; kamera.y = g.h / 2 - wy * kamera.s; anwenden();
  }
  let miniZug = false;
  mini.addEventListener('pointerdown', e => { miniZug = true; mini.setPointerCapture(e.pointerId); miniZiel(e); });
  mini.addEventListener('pointermove', e => { if (miniZug) miniZiel(e); });
  mini.addEventListener('pointerup', () => { miniZug = false; });
  $('#k-mini').addEventListener('click', e => { mini.hidden = !mini.hidden; e.currentTarget.setAttribute('aria-pressed', String(!mini.hidden)); speichere('mini', !mini.hidden); });

  /* ── Provinzleiste ─────────────────────────────────────────────── */
  $$('.pknopf').forEach(b => b.addEventListener('click', () => zuRegion(document.getElementById(b.dataset.ziel))));
  function aktuelleProvinz() {
    const g = groesse(), cx = (g.b / 2 - kamera.x) / kamera.s, cy = (g.h / 2 - kamera.y) / kamera.s;
    let treffer = null;
    for (const r of regionen) { const b = r._box; if (b && cx >= b.x && cx <= b.x + b.b && cy >= b.y && cy <= b.y + b.h) treffer = r.id; }
    $$('.pknopf').forEach(b => b.classList.toggle('aktiv', b.dataset.ziel === treffer));
  }
  $('#k-plus').addEventListener('click', () => { const g = groesse(); zoomUm(1.35, g.b / 2, g.h / 2); });
  $('#k-minus').addEventListener('click', () => { const g = groesse(); zoomUm(1 / 1.35, g.b / 2, g.h / 2); });
  $('#k-ganz').addEventListener('click', () => ganzeKarte());
  $('#k-fit').addEventListener('click', () => {
    const akt = $('.pknopf.aktiv'); if (akt) zuRegion(document.getElementById(akt.dataset.ziel)); else ganzeKarte();
  });

  /* ── Register und Suche ────────────────────────────────────────── */
  const regPaneel = $('#register'), regListe = $('#reg-liste'), sucheFeld = $('#suche');
  const norm = s => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ß/g, 'ss');
  let nurKern = false;
  function zeigeRegister(q) {
    const n = norm(q || '').trim(), woerter = n.split(/\s+/).filter(Boolean);
    let html = '', zahl = 0;
    for (const p of D.provinzen) {
      const ks = p.kacheln.filter(k => (!nurKern || k.rel === 'kern') && woerter.every(w => k.such.includes(w)));
      if (!ks.length) continue;
      zahl += ks.length;
      html += '<div class="reg-gruppe farbe-' + p.farbe + '"><h3><i>' + p.nr + '</i>' + p.name + '</h3>' +
        ks.map(k => '<button class="reg-eintrag" data-code="' + k.code + '"><b>' + k.anzeige + '</b><span>' + k.titel +
          (k.anker ? '<em>' + k.anker + '</em>' : '') + '</span><small>' + (k.sym || '') + '</small></button>').join('') + '</div>';
    }
    regListe.innerHTML = zahl ? html : '<p class="reg-leer">Keine Kachel passt zu „' + (q || '') + '“. Andere Schreibweise oder Kachelcode (etwa D4) versuchen.</p>';
    $('#reg-zahl').textContent = zahl + ' Kacheln';
  }
  regListe.addEventListener('click', e => {
    const b = e.target.closest('.reg-eintrag'); if (!b) return;
    zuKachel(b.dataset.code);
    if (matchMedia('(max-width: 760px)').matches) oeffne(null);
  });
  function oeffne(id) {
    $$('.paneel').forEach(p => p.classList.toggle('offen', p.id === id && !p.classList.contains('offen')));
    $('#k-register').setAttribute('aria-pressed', String($('#register').classList.contains('offen')));
    $('#k-info').setAttribute('aria-pressed', String($('#info').classList.contains('offen')));
  }
  $('#k-register').addEventListener('click', () => { oeffne('register'); zeigeRegister(sucheFeld.value); });
  $('#k-info').addEventListener('click', () => oeffne('info'));
  $$('.paneel .schliessen').forEach(b => b.addEventListener('click', () => oeffne(null)));
  sucheFeld.addEventListener('focus', () => $('.suche').classList.add('offen'));
  sucheFeld.addEventListener('blur', () => { if (!sucheFeld.value) $('.suche').classList.remove('offen'); });
  sucheFeld.addEventListener('input', () => { if (!regPaneel.classList.contains('offen')) oeffne('register'); zeigeRegister(sucheFeld.value); });
  sucheFeld.addEventListener('keydown', e => {
    if (e.key === 'Enter') { const b = $('.reg-eintrag', regListe); if (b) { zuKachel(b.dataset.code); sucheFeld.blur(); } }
    if (e.key === 'Escape') { sucheFeld.value = ''; zeigeRegister(''); sucheFeld.blur(); oeffne(null); }
  });
  $('#k-kern').addEventListener('click', e => {
    nurKern = !nurKern; e.currentTarget.setAttribute('aria-pressed', String(nurKern));
    $$('.karte-kachel').forEach(k => k.classList.toggle('gedimmt', nurKern && k.dataset.rel !== 'kern'));
    zeigeRegister(sucheFeld.value);
  });

  /* Tastatur */
  document.addEventListener('keydown', e => {
    if (e.target.closest('input')) return;
    const g = groesse();
    if (e.key === '+' || e.key === '=') zoomUm(1.25, g.b / 2, g.h / 2);
    else if (e.key === '-') zoomUm(0.8, g.b / 2, g.h / 2);
    else if (e.key === '0') ganzeKarte();
    else if (e.key === '/') { e.preventDefault(); sucheFeld.focus(); }
    else if (e.key === 'Escape') oeffne(null);
    else if (e.key.startsWith('Arrow')) {
      const d = 120; kamera.x += e.key === 'ArrowLeft' ? d : e.key === 'ArrowRight' ? -d : 0; kamera.y += e.key === 'ArrowUp' ? d : e.key === 'ArrowDown' ? -d : 0; anwenden();
    } else return;
    e.preventDefault();
  });

  /* ── Start ─────────────────────────────────────────────────────── */
  function start() {
    layout();
    const miniAn = lade('mini'); if (miniAn === false || (miniAn === null && innerWidth < 760)) { mini.hidden = true; $('#k-mini').setAttribute('aria-pressed', 'false'); }
    ganzeKarte(true);
    const h = location.hash.match(/^#k-([A-Z]{1,2}\d{0,2})$/);
    const alt = lade('ansicht');
    window.__terra = { kamera, zuKachel, ganzeKarte, layout, bereit: true };
    if (h && zuKachel(h[1], true)) return;
    if (alt && alt.s) { Object.assign(kamera, alt); anwenden(); }
  }
  let neu; addEventListener('resize', () => { clearTimeout(neu); neu = setTimeout(aktualisiereMini, 150); });
  (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(start);
})();

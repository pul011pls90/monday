/* Карта навыков — metro map.
   Topics are numbered interchanges, subtopics are labelled stretches of line, skills are stations.
   Desktop: the line snakes left→right, right→left in rows. Phone: one vertical line, each station a full-width row.
   The line is SVG; every station and interchange is a real <button> laid over it (keyboard + screen readers). */
(() => {
  const stage = document.querySelector('[data-metro-stage]');
  if (!stage) return;
  const data = JSON.parse(document.getElementById('metro-data').textContent);
  const T = JSON.parse(document.getElementById('metro-i18n').textContent);
  const NS = 'http://www.w3.org/2000/svg';
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const starsOf = (k) => (k.acc == null ? 0 : k.acc >= 0.95 ? 3 : k.acc >= 0.8 ? 2 : k.acc >= 0.6 ? 1 : 0);
  const starRow = (n) => `<span class="mt-stars" aria-label="${n}/3">${'★'.repeat(n)}<em>${'★'.repeat(3 - n)}</em></span>`;

  // the route as a flat sequence
  const seq = [];
  data.topics.forEach((t, ti) => {
    Object.assign(t, { n: ti + 1, done: 0, total: 0, stars: 0 });
    seq.push({ type: 'topic', t });
    t.subtopics.forEach((s) => {
      seq.push({ type: 'sub', t, s });
      s.skills.forEach((k) => {
        seq.push({ type: 'skill', t, s, k });
        t.total++; t.stars += starsOf(k); if (k.state === 'mastered') t.done++;
      });
      seq.push({ type: 'subend', t, s });
    });
  });
  const firstOpen = (t) => t.subtopics.flatMap((s) => s.skills).find((k) => k.state !== 'mastered' && k.n) || t.subtopics[0].skills.find((k) => k.n);

  const legend = document.querySelector('.mt-legend');
  let grid = null, lastW = 0;
  if (data.exam) fetch(T.countries).then((r) => r.json()).then((g) => { grid = g[data.exam] || null; draw(); }).catch(() => {});

  function draw() {
    const W = stage.clientWidth;
    lastW = W;
    const phone = W < 720;
    stage.innerHTML = '';
    stage.classList.toggle('is-vertical', phone);

    // ---------------------------------------------------------------- layout
    const P = []; // placed: {node, x, y, s, row}
    let path = '', total = 0, H = 0;
    const subSpans = [];
    if (phone) {
      const x = 34; let y = 46, s = 0, open = null;
      const step = (g) => { y += g; s += g; };
      seq.forEach((node, i) => {
        if (node.type === 'topic') { if (i) step(34); P.push({ node, x, y, s }); step(64); }
        else if (node.type === 'sub') { open = { node, x, y: y - 6 }; step(26); }
        else if (node.type === 'skill') { P.push({ node, x, y, s }); step(52); }
        else { subSpans.push(open); step(4); }
      });
      H = y + 56; total = s; path = `M${x},46 L${x},${y - 40}`;
    } else {
      const r = 74, pad = 28 + r, x0 = pad, x1 = W - pad, L = x1 - x0, top = 104;
      let u = 6, row = 0, s = 6, open = null;
      const pos = () => ({ x: row % 2 ? x1 - u : x0 + u, y: top + row * 2 * r, s, row });
      const adv = (g) => {
        if (u + g > L) { s += L - u + Math.PI * r + 30; row++; u = 30; } else { u += g; s += g; }
      };
      let lastTopic = null;   // topic names are up to 184px wide: two on one row keep at least that apart
      seq.forEach((node, i) => {
        if (node.type === 'topic') {
          if (i) adv(76);
          if (lastTopic && lastTopic.row === row && u - lastTopic.u < 200) adv(200 - (u - lastTopic.u));
          P.push({ node, ...pos() }); lastTopic = { row, u }; adv(70);
        }
        else if (node.type === 'sub') { if (seq[i - 1].type !== 'topic') adv(22); open = { node, ...pos(), parts: [] }; }
        else if (node.type === 'skill') { if (seq[i - 1].type !== 'sub' || seq[i - 2].type !== 'topic') adv(40); P.push({ node, ...pos() }); }
        else { subSpans.push(open); }
      });
      const rows = row + 1, endU = u + 36;
      total = s + 36;
      path = `M${x0},${top}`;
      for (let k = 0; k < rows; k++) {
        const y = top + k * 2 * r, dirR = k % 2 === 0;
        if (k < rows - 1) path += ` L${dirR ? x1 : x0},${y} A${r},${r} 0 0 ${dirR ? 1 : 0} ${dirR ? x1 : x0},${y + 2 * r}`;
        else path += ` L${dirR ? x0 + Math.min(L, endU) : x1 - Math.min(L, endU)},${y}`;
      }
      H = top + (rows - 1) * 2 * r + 150;   // room for a two-line topic name above the legend
    }
    stage.style.height = H + 'px';
    const cur = P.find((p) => p.node.type === 'skill' && p.node.k.id === data.current);
    const doneLen = cur ? cur.s : total;

    // ---------------------------------------------------------------- svg: country dots, line, done part
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'mt-svg'); svg.setAttribute('width', W); svg.setAttribute('height', H); svg.setAttribute('aria-hidden', 'true');
    if (grid) {
      const gw = grid[0].length, gh = grid.length, cell = Math.min((W - 40) / gw, (H - 40) / gh);
      const ox = (W - gw * cell) / 2, oy = (H - gh * cell) / 2;
      const g = document.createElementNS(NS, 'g'); g.setAttribute('class', 'mt-country');
      let d = '';
      grid.forEach((line, r) => [...line].forEach((ch, c) => { if (ch === '#') d += `M${ox + c * cell + cell / 2},${oy + r * cell + cell / 2}h0`; }));
      const p = document.createElementNS(NS, 'path'); p.setAttribute('d', d); p.style.strokeWidth = Math.max(2, cell * 0.38); g.appendChild(p);
      svg.appendChild(g);
    }
    for (const [cls, dash] of [['mt-line', null], ['mt-line mt-line--done', `${doneLen} ${total + 2000}`]]) {
      const p = document.createElementNS(NS, 'path'); p.setAttribute('d', path); p.setAttribute('class', cls);
      if (dash) p.setAttribute('stroke-dasharray', dash);
      svg.appendChild(p);
    }
    stage.appendChild(svg);
    if (legend) stage.appendChild(legend);

    // ---------------------------------------------------------------- subtopic labels (always above the line; width limited by neighbours)
    const spans = subSpans.filter(Boolean).map((sp) => {
      const mine = P.filter((p) => p.node.type === 'skill' && p.node.s === sp.node.s);
      const row = mine.filter((p) => p.row === mine[0].row);
      return { sp, a: Math.min(...row.map((p) => p.x)), b: Math.max(...row.map((p) => p.x)), y: row[0].y, row: row[0].row };
    });
    // measure with the page's own font; a label is never cut inside a word
    const ctx = document.createElement('canvas').getContext('2d');
    ctx.font = `700 11px ${getComputedStyle(stage).fontFamily}`;
    // labels are spaced capitals on one line: measure them that way (.1em tracking per letter)
    const tw = (s) => ctx.measureText(s.toUpperCase()).width + s.length * 1.1;
    // topic names sit under their interchange: reserve that space on the "below" side
    const boxes = { above: [], below: [], high: [] };
    P.filter((p) => p.node.type === 'topic').forEach((p) => {
      boxes.below.push({ row: p.row, l: p.x - 92, r: p.x + 92 });
      boxes.high.push({ row: p.row + 1, l: p.x - 92, r: p.x + 92 }); // the topic name of the row above reaches down here
    });
    const free = (side, row, l, r) => !boxes[side].some((b) => b.row === row && l < b.r + 8 && r > b.l - 8);
    spans.forEach((it) => {
      const name = it.sp.node.s.name;
      const el = document.createElement('span'); el.className = 'mt-sub'; el.textContent = name; el.title = name;
      if (phone) { el.style.left = it.sp.x + 28 + 'px'; el.style.top = it.sp.y + 'px'; stage.appendChild(el); return; }
      // one line, always above the track; too long for its stretch → ellipsis, full name on hover
      const c = (it.a + it.b) / 2, room = Math.max(it.b - it.a + 40, 120);
      const w = Math.ceil(Math.min(tw(name), Math.max(room, 150))) + 4;
      // try right above, then one level higher, then the same nudged sideways; the label stays near its stations.
      // When both levels are taken nearby, it goes under the track rather than on top of another name.
      let spot = null;
      for (const sides of [['above', 'high'], ['below']]) {
        for (const dx of [0, -30, 30, -60, 60, -100, 100, -150, 150]) {
          const side = sides.find((sd) => free(sd, it.row, c + dx - w / 2, c + dx + w / 2));
          if (side) { spot = { side, x: c + dx }; break; }
        }
        if (spot) break;
      }
      spot = spot || { side: 'above', x: c };
      boxes[spot.side].push({ row: it.row, l: spot.x - w / 2, r: spot.x + w / 2 });
      el.classList.add('is-' + spot.side);
      el.style.left = spot.x + 'px'; el.style.top = it.y + 'px'; el.style.width = w + 'px';
      stage.appendChild(el);
    });

    // ---------------------------------------------------------------- interchanges + stations
    P.forEach((p) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.style.left = p.x + 'px'; b.style.top = p.y + 'px';
      if (p.node.type === 'topic') {
        const t = p.node.t, isCur = cur && cur.node.t === t, full = t.done === t.total;
        b.className = 'mt-ix' + (full ? ' is-done' : '') + (isCur ? ' is-current' : '') + (t.weak ? ' is-weak' : '');
        b.innerHTML = `<b class="num">${t.n}</b><span class="mt-ix__label"><strong>${esc(t.name)}</strong><small><span class="num">${t.done}/${t.total}</span> · ★ <span class="num">${t.stars}</span></small></span>`;
        b.setAttribute('aria-label', `${t.n}. ${t.name}`);
        b.addEventListener('click', (e) => { e.stopPropagation(); openTopic(t, p, b); });
      } else {
        const k = p.node.k, isCur = cur === p, st = starsOf(k);
        b.className = `mt-st is-${k.n ? k.state : 'noq'}` + (isCur ? ' is-current' : '');
        b.innerHTML = `<i></i>` + (phone ? `<span class="mt-st__name">${esc(k.name)}</span>${k.state === 'mastered' || st ? starRow(st) : ''}` : '')
          + (isCur ? `<span class="mt-here">${esc(T.here)}</span>` : '');
        b.setAttribute('aria-label', k.name); if (!phone) b.title = k.name;
        b.addEventListener('click', (e) => { e.stopPropagation(); openSkill(p, b); });
      }
      stage.appendChild(b);
    });
  }

  // ---------------------------------------------------------------- the card (popover on desktop, bottom sheet on phone)
  let card = null;
  const close = () => { if (card) { card.remove(); card = null; } };
  function place(el, p) {
    stage.appendChild(el); card = el;
    if (stage.classList.contains('is-vertical')) return;
    const w = el.offsetWidth, x = Math.min(Math.max(p.x - w / 2, 12), stage.clientWidth - w - 12);
    el.style.left = x + 'px'; el.style.top = p.y + 26 + 'px';
  }
  function openSkill(p, btn) {
    close();
    const k = p.node.k, st = starsOf(k);
    const meta = !k.n ? T.noq : k.state === 'mastered' ? T.mastered : k.acc != null ? `${T.acc} ${Math.round(k.acc * 100)}%` : `${T.new} · ${k.n} ${T.questions}`;
    const el = document.createElement('div'); el.className = 'mt-card'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', k.name);
    el.innerHTML = `<button type="button" class="mt-card__x" aria-label="${esc(T.close)}">×</button>
      <span class="mt-card__where">${p.node.t.n} · ${esc(p.node.t.name)} · ${esc(p.node.s.name)}</span>
      <b class="mt-card__title">${esc(k.name)}</b>
      <span class="mt-card__meta">${starRow(st)}<span>${esc(meta)}</span></span>
      ${k.n ? `<button class="mt-card__go" type="submit" form="mt-start" name="skill_id" value="${k.id}">${esc(k.state === 'mastered' ? T.repeat : T.start)} →</button>` : ''}`;
    el.addEventListener('click', (e) => e.stopPropagation());
    el.querySelector('.mt-card__x').addEventListener('click', () => { close(); btn.focus(); });
    place(el, p);
    (el.querySelector('.mt-card__go') || el.querySelector('.mt-card__x')).focus({ preventScroll: true });
  }
  function openTopic(t, p, btn) {
    close();
    const k = firstOpen(t);
    const el = document.createElement('div'); el.className = 'mt-card'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', t.name);
    el.innerHTML = `<button type="button" class="mt-card__x" aria-label="${esc(T.close)}">×</button>
      <span class="mt-card__where">${esc(T.topic)} ${t.n} · ${t.total} ${esc(T.skills)}</span>
      <b class="mt-card__title">${esc(t.name)}</b>
      <span class="mt-card__meta"><span class="mt-stars">★</span><span><span class="num">${t.stars}/${t.total * 3}</span> · ${t.done}/${t.total} ${esc(T.mastered)}</span></span>
      ${k ? `<span class="mt-card__meta">${esc(T.from)}: ${esc(k.name)}</span><button class="mt-card__go" type="submit" form="mt-start" name="skill_id" value="${k.id}">${esc(T.go)} →</button>` : ''}`;
    el.addEventListener('click', (e) => e.stopPropagation());
    el.querySelector('.mt-card__x').addEventListener('click', () => { close(); btn.focus(); });
    place(el, p);
  }
  document.addEventListener('click', close);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });

  draw();
  let tm = null;
  addEventListener('resize', () => { clearTimeout(tm); tm = setTimeout(() => { if (stage.clientWidth !== lastW) { close(); draw(); } }, 120); });
  // phone: bring the current station into view on load
  const here = stage.querySelector('.mt-st.is-current');
  if (here && stage.classList.contains('is-vertical')) here.scrollIntoView({ block: 'center' });
})();

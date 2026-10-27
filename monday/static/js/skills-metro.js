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
      const r = 64, pad = 28 + r, x0 = pad, x1 = W - pad, L = x1 - x0, top = 104;
      let u = 6, row = 0, s = 6, open = null;
      const pos = () => ({ x: row % 2 ? x1 - u : x0 + u, y: top + row * 2 * r, s, row });
      const adv = (g) => {
        if (u + g > L) { s += L - u + Math.PI * r + 30; row++; u = 30; } else { u += g; s += g; }
      };
      seq.forEach((node, i) => {
        if (node.type === 'topic') { if (i) adv(54); P.push({ node, ...pos() }); adv(58); }
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
      H = top + (rows - 1) * 2 * r + 120;
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
    spans.forEach((it) => {
      const el = document.createElement('span'); el.className = 'mt-sub'; el.textContent = it.sp.node.s.name; el.title = it.sp.node.s.name;
      if (phone) { el.style.left = it.sp.x + 28 + 'px'; el.style.top = it.sp.y + 'px'; stage.appendChild(el); return; }
      const same = spans.filter((o) => o.row === it.row && o !== it);
      const prev = same.filter((o) => o.b < it.a).sort((x, y) => y.b - x.b)[0], next = same.filter((o) => o.a > it.b).sort((x, y) => x.a - y.a)[0];
      const left = prev ? (prev.b + it.a) / 2 : it.a - 70, right = next ? (it.b + next.a) / 2 : it.b + 70, c = (it.a + it.b) / 2;
      el.style.left = c + 'px'; el.style.top = it.y + 'px'; el.style.width = Math.max(56, 2 * Math.min(c - left, right - c) - 8) + 'px';
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

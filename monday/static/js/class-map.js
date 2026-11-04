/* Карта класса — the teacher's students and topics as a 3D network (no libraries).
   Layout: a small force simulation in 3D with a radial pull — topics sit in the core, subtopics around them,
   students on the outer shell — so the whole network reads as a sphere. Drawn on a canvas with perspective;
   drag to rotate, wheel / pinch to zoom, click a point to see its links. The lists beside the map carry the
   same findings as text (they are the accessible version and also focus the map). */
(() => {
  const canvas = document.querySelector('[data-cm-stage]');
  if (!canvas) return;
  const data = JSON.parse(document.getElementById('cm-data').textContent);
  const T = JSON.parse(document.getElementById('cm-i18n').textContent);
  const tip = document.querySelector('[data-cm-tip]');
  const panel = document.querySelector('[data-cm-panel]');
  const spinBtn = document.querySelector('[data-cm-spin]');
  const ctx = canvas.getContext('2d');
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const pct = (a) => (a == null ? '—' : Math.round(a * 100) + '%');
  const reduced = document.documentElement.dataset.motion === 'reduce' ||
    (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);

  // ------------------------------------------------------------------ graph
  const nodes = data.nodes.map((n) => ({ ...n, x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0, nb: new Set() }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const links = data.links.map((l) => ({ ...l, s: byId.get(l.source), t: byId.get(l.target) })).filter((l) => l.s && l.t);
  links.forEach((l) => { l.s.nb.add(l.t.id); l.t.nb.add(l.s.id); });

  const R = 300; // radius of the outer shell, in world units
  const SHELL = { topic: 0.28, subtopic: 0.62, student: 1 };
  const radiusOf = (n) => (n.kind === 'topic' ? 7 : n.kind === 'subtopic'
    ? 3.2 + Math.min(5, Math.sqrt(n.answers || 0) * 0.55) : 3.6 + Math.min(4, (n.weak || 0) * 0.7));

  // deterministic start: the same class always opens in the same shape
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const topicIdx = new Map(nodes.filter((n) => n.kind === 'topic').map((n, i, a) => [n.id, [i, a.length]]));
  const onSphere = (r, k, total, jitter) => { // golden-spiral point k of total, slightly jittered
    const yy = 1 - 2 * (k + 0.5) / Math.max(1, total);
    const rr = Math.sqrt(Math.max(0, 1 - yy * yy));
    const th = k * 2.399963 + jitter * (rnd() - 0.5);
    return [Math.cos(th) * rr * r, yy * r, Math.sin(th) * rr * r];
  };
  nodes.forEach((n, i) => {
    if (n.kind === 'topic') {
      const [k, total] = topicIdx.get(n.id);
      [n.x, n.y, n.z] = onSphere(R * SHELL.topic, k, total, 0.2);
    } else {
      const anchor = n.kind === 'subtopic' ? byId.get(n.topic) : null;
      const [x, y, z] = onSphere(R * SHELL[n.kind], i, nodes.length, 6);
      [n.x, n.y, n.z] = anchor ? [x * 0.4 + anchor.x * 1.6, y * 0.4 + anchor.y * 1.6, z * 0.4 + anchor.z * 1.6] : [x, y, z];
    }
  });

  // Every node lives on the sphere of its shell (a hard constraint), so the forces only arrange points *on* the
  // spheres: repulsion spreads them evenly, springs pull a student towards their weak subtopics and a subtopic
  // towards its topic. The result is a ball that reads the same from every side.
  const toShell = (n) => {
    const d = Math.sqrt(n.x * n.x + n.y * n.y + n.z * n.z) || 1;
    const r = R * SHELL[n.kind] / d;
    n.x *= r; n.y *= r; n.z *= r;
  };
  function simulate(steps) {
    const N = nodes.length;
    nodes.forEach(toShell);
    for (let it = 0; it < steps; it++) {
      const alpha = 1 - it / steps;
      for (let i = 0; i < N; i++) { // repulsion, mostly between nodes of the same shell
        const a = nodes[i];
        for (let j = i + 1; j < N; j++) {
          const b = nodes[j];
          let dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
          let d2 = dx * dx + dy * dy + dz * dz;
          if (d2 < 1) { dx = rnd() - 0.5; dy = rnd() - 0.5; dz = rnd() - 0.5; d2 = 1; }
          const f = (a.kind === b.kind ? 60000 : 10000) / d2;
          const d = Math.sqrt(d2);
          a.vx += dx / d * f; a.vy += dy / d * f; a.vz += dz / d * f;
          b.vx -= dx / d * f; b.vy -= dy / d * f; b.vz -= dz / d * f;
        }
      }
      links.forEach((l) => { // springs: attraction only, proportional to distance
        const k = l.kind === 'tree' ? 0.03 : 0.008; // tuned: even sphere, linked points still ~half as far apart as random ones
        const dx = l.t.x - l.s.x, dy = l.t.y - l.s.y, dz = l.t.z - l.s.z;
        l.s.vx += dx * k; l.s.vy += dy * k; l.s.vz += dz * k;
        l.t.vx -= dx * k; l.t.vy -= dy * k; l.t.vz -= dz * k;
      });
      const cap = 24 * alpha + 0.5;
      nodes.forEach((n) => {
        const sp = Math.sqrt(n.vx * n.vx + n.vy * n.vy + n.vz * n.vz);
        const m = sp > cap ? cap / sp : 1;
        n.x += n.vx * m; n.y += n.vy * m; n.z += n.vz * m;
        n.vx *= 0.4; n.vy *= 0.4; n.vz *= 0.4;
        toShell(n);
      });
    }
  }
  simulate(nodes.length > 400 ? 160 : 300);

  // ------------------------------------------------------------------ camera
  const VIEW0 = { yaw: 0.5, pitch: -0.25, zoom: 1 };
  const view = { ...VIEW0 };
  let target = null; // {yaw, pitch} when turning towards a node
  let spinning = !reduced;
  let W = 0, H = 0, dpr = 1, scale = 1;
  const D = 900; // camera distance

  function project(n) {
    const cy = Math.cos(view.yaw), sy = Math.sin(view.yaw), cp = Math.cos(view.pitch), sp = Math.sin(view.pitch);
    const x1 = n.x * cy + n.z * sy, z1 = -n.x * sy + n.z * cy;
    const y2 = n.y * cp - z1 * sp, z2 = n.y * sp + z1 * cp;
    const k = (D / (D - z2)) * scale * view.zoom;
    n.sx = W / 2 + x1 * k; n.sy = H / 2 - y2 * k; n.sz = z2; n.k = k;
  }

  // ------------------------------------------------------------------ colours (follow the theme)
  let C = {};
  function readColours() {
    const cs = getComputedStyle(document.documentElement);
    const v = (name) => cs.getPropertyValue(name).trim();
    C = { text: v('--text'), muted: v('--muted'), line: v('--line-strong'), surface: v('--surface'), accent: v('--accent'),
      green: v('--ok'), yellow: v('--warn'), red: v('--bad'), none: v('--muted'), font: v('--font') };
  }
  readColours();
  new MutationObserver(() => { readColours(); draw(); }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  const fill = (n) => (n.kind === 'topic' ? C.text : n.kind === 'subtopic' ? C[n.color] || C.none : C.accent);

  // ------------------------------------------------------------------ drawing
  let hover = null, selected = null;
  const focusSet = () => (selected ? new Set([selected.id, ...selected.nb]) : null);

  function draw() {
    if (!W) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    nodes.forEach(project);
    const fs = focusSet();
    const depth = (z) => 0.28 + 0.72 * Math.min(1, Math.max(0, (z + R) / (2 * R)));

    links.forEach((l) => {
      const on = fs ? fs.has(l.s.id) && fs.has(l.t.id) && (l.s === selected || l.t === selected) : true;
      ctx.globalAlpha = (on ? 1 : 0.08) * depth((l.s.sz + l.t.sz) / 2) * (l.kind === 'weak' ? 0.75 : 0.45);
      ctx.strokeStyle = l.kind === 'weak' ? C.red : C.line;
      ctx.lineWidth = l.kind === 'weak' ? (on && fs ? 2 : 1.2) : 1;
      ctx.beginPath(); ctx.moveTo(l.s.sx, l.s.sy); ctx.lineTo(l.t.sx, l.t.sy); ctx.stroke();
    });

    const order = [...nodes].sort((a, b) => a.sz - b.sz);
    order.forEach((n) => {
      const on = !fs || fs.has(n.id);
      const r = radiusOf(n) * Math.max(0.55, n.k / scale);
      ctx.globalAlpha = (on ? 1 : 0.15) * depth(n.sz);
      ctx.fillStyle = fill(n);
      ctx.beginPath(); ctx.arc(n.sx, n.sy, r, 0, Math.PI * 2); ctx.fill();
      if (n.kind === 'student' && n.weak >= 3) { // needs a look: red ring
        ctx.strokeStyle = C.red; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(n.sx, n.sy, r + 3, 0, Math.PI * 2); ctx.stroke();
      }
      if (n === selected || n === hover) {
        ctx.globalAlpha = 1; ctx.strokeStyle = C.text; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(n.sx, n.sy, r + (n.kind === 'student' && n.weak >= 3 ? 6 : 3), 0, Math.PI * 2); ctx.stroke();
      }
      n.sr = r;
    });

    // labels: topics always; the selection and its neighbours
    ctx.textBaseline = 'middle';
    order.forEach((n) => {
      const show = n.kind === 'topic' ? (!fs || fs.has(n.id)) : fs && fs.has(n.id);
      if (!show) return;
      ctx.globalAlpha = Math.max(0.45, depth(n.sz));
      ctx.font = `${n.kind === 'topic' ? 700 : n === selected ? 700 : 500} ${n.kind === 'topic' ? 13 : 12}px ${C.font}`;
      const label = n.name.length > 34 ? n.name.slice(0, 33) + '…' : n.name;
      const x = n.sx + n.sr + 6, y = n.sy;
      ctx.lineWidth = 4; ctx.strokeStyle = C.surface; ctx.lineJoin = 'round';
      ctx.strokeText(label, x, y);
      ctx.fillStyle = C.text; ctx.fillText(label, x, y);
    });
    ctx.globalAlpha = 1;
  }

  // ------------------------------------------------------------------ loop
  let last = 0, idleFrames = 0;
  function frame(t) {
    const dt = Math.min(50, t - (last || t)); last = t;
    let moved = false;
    if (target) {
      const dy = Math.atan2(Math.sin(target.yaw - view.yaw), Math.cos(target.yaw - view.yaw));
      const dp = target.pitch - view.pitch;
      const k = reduced ? 1 : 0.14;
      view.yaw += dy * k; view.pitch += dp * k;
      if (Math.abs(dy) < 0.002 && Math.abs(dp) < 0.002) { view.yaw = target.yaw; view.pitch = target.pitch; target = null; }
      moved = true;
    } else if (spinning && !dragging && !selected) {
      view.yaw += dt * 0.00012; moved = true;
    }
    if (moved || idleFrames < 2) { draw(); idleFrames = moved ? 0 : idleFrames + 1; }
    requestAnimationFrame(frame);
  }

  function resize() {
    const r = canvas.getBoundingClientRect();
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = r.width; H = r.height;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    scale = Math.min(W, H) / (2.9 * R);
    idleFrames = 0; draw();
  }
  new ResizeObserver(resize).observe(canvas);

  // ------------------------------------------------------------------ picking & panel
  function pick(x, y) {
    let best = null, bestD = Infinity;
    nodes.forEach((n) => {
      const d = Math.hypot(n.sx - x, n.sy - y);
      const reach = Math.max(10, n.sr + 4);
      if (d <= reach && (d < bestD - 2 || (Math.abs(d - bestD) <= 2 && n.sz > best.sz))) { best = n; bestD = d; }
    });
    return best;
  }

  const urlStudent = (id) => T.studentUrl.replace(/0$/, String(id));
  const urlTree = (id) => T.treeUrl.replace(/open=0/, 'open=' + id);
  const nbOf = (n, kind) => [...n.nb].map((id) => byId.get(id)).filter((m) => m.kind === kind && (kind !== 'topic'))
    .filter((m) => links.some((l) => l.kind === 'weak' && ((l.s === n && l.t === m) || (l.t === n && l.s === m))))
    .sort((a, b) => a.name.localeCompare(b.name));
  const chipList = (items) => (items.length
    ? `<ul class="cm-mini">${items.map((m) => `<li><button type="button" class="cm-link" data-cm-focus="${m.id}">${esc(m.name)}</button></li>`).join('')}</ul>`
    : `<p class="small muted">${esc(T.none)}</p>`);
  const kindLabel = { topic: T.topic, subtopic: T.subtopic, student: T.student };

  function showPanel(n) {
    if (!n) {
      panel.innerHTML = panel.dataset.empty;
      return;
    }
    const stats = n.kind === 'topic' ? '' : (n.answers
      ? `<div class="cm-stats"><span><b class="num">${pct(n.acc)}</b> ${esc(T.acc)}</span><span><b class="num">${n.answers}</b> ${esc(T.answers)}</span></div>`
      : `<p class="small muted">${esc(T.noanswers)}</p>`);
    let body = '';
    if (n.kind === 'subtopic') {
      const topic = byId.get(n.topic);
      body = `<p class="small muted">${esc(topic ? topic.name : '')}</p>${stats}
        <span class="eyebrow">${esc(T.weakStudents)}</span>${chipList(nbOf(n, 'student'))}
        <a class="btn btn--secondary btn--sm" href="${esc(urlTree(n.topic_id))}">${esc(T.openTree)}</a>`;
    } else if (n.kind === 'student') {
      body = `${n.exam ? `<p class="small muted">${esc(n.exam)}</p>` : ''}${stats}
        <span class="eyebrow">${esc(T.weakSubs)}</span>${chipList(nbOf(n, 'subtopic'))}
        <a class="btn btn--secondary btn--sm" href="${esc(urlStudent(n.record_id))}">${esc(T.openStudent)}</a>`;
    } else {
      const subs = [...n.nb].map((id) => byId.get(id)).filter((m) => m.kind === 'subtopic').sort((a, b) => a.name.localeCompare(b.name));
      body = chipList(subs);
    }
    panel.innerHTML = `<span class="eyebrow">${esc(kindLabel[n.kind])}</span><h3 class="cm-name">${esc(n.name)}</h3>${body}`;
  }
  panel.dataset.empty = panel.innerHTML;

  function select(n, turn) {
    selected = n;
    showPanel(n);
    document.querySelectorAll('.cm-row').forEach((b) => b.classList.toggle('is-active', !!n && b.dataset.cmFocus === n.id));
    if (n && turn) {
      const yaw = Math.atan2(-n.x, n.z);
      const z1 = -n.x * Math.sin(yaw) + n.z * Math.cos(yaw);
      target = { yaw, pitch: Math.max(-1.2, Math.min(1.2, Math.atan2(n.y, z1))) };
    }
    idleFrames = 0; draw();
  }

  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-cm-focus]');
    if (!b) return;
    const n = byId.get(b.dataset.cmFocus);
    if (n) { select(n, true); if (b.closest('.cm-side') && window.innerWidth < 960) canvas.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center' }); }
  });

  // ------------------------------------------------------------------ pointer: rotate, zoom, pick
  const pointers = new Map();
  let dragging = false, downAt = null, pinch0 = null;
  canvas.addEventListener('pointerdown', (e) => {
    canvas.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    downAt = { x: e.clientX, y: e.clientY, moved: false };
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch0 = { d: Math.hypot(a.x - b.x, a.y - b.y), zoom: view.zoom };
    }
  });
  canvas.addEventListener('pointermove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const p = pointers.get(e.pointerId);
    if (!p) { // hover
      const n = pick(e.clientX - rect.left, e.clientY - rect.top);
      if (n !== hover) { hover = n; canvas.style.cursor = n ? 'pointer' : 'grab'; idleFrames = 0; draw(); }
      if (n) {
        tip.hidden = false;
        tip.innerHTML = `<b>${esc(n.name)}</b>${n.kind !== 'topic' && n.answers ? `<span>${pct(n.acc)} · ${n.answers} ${esc(T.answers)}</span>` : ''}`;
        tip.style.left = (e.clientX - rect.left + 14) + 'px'; tip.style.top = (e.clientY - rect.top + 14) + 'px';
      } else tip.hidden = true;
      return;
    }
    if (pointers.size === 2 && pinch0) {
      p.x = e.clientX; p.y = e.clientY;
      const [a, b] = [...pointers.values()];
      view.zoom = Math.max(0.5, Math.min(4, pinch0.zoom * Math.hypot(a.x - b.x, a.y - b.y) / pinch0.d));
      downAt.moved = true; idleFrames = 0; draw();
      return;
    }
    const dx = e.clientX - p.x, dy = e.clientY - p.y;
    p.x = e.clientX; p.y = e.clientY;
    if (Math.abs(e.clientX - downAt.x) + Math.abs(e.clientY - downAt.y) > 4) { downAt.moved = true; dragging = true; target = null; }
    if (dragging) {
      view.yaw += dx * 0.006;
      view.pitch = Math.max(-1.3, Math.min(1.3, view.pitch + dy * 0.006));
      tip.hidden = true; canvas.style.cursor = 'grabbing'; idleFrames = 0; draw();
    }
  });
  const up = (e) => {
    const rect = canvas.getBoundingClientRect();
    if (pointers.has(e.pointerId) && downAt && !downAt.moved && pointers.size === 1 && e.type === 'pointerup') {
      select(pick(e.clientX - rect.left, e.clientY - rect.top), false);
    }
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinch0 = null;
    if (!pointers.size) { dragging = false; canvas.style.cursor = hover ? 'pointer' : 'grab'; }
  };
  canvas.addEventListener('pointerup', up);
  canvas.addEventListener('pointercancel', up);
  canvas.addEventListener('pointerleave', () => { if (!pointers.size) { hover = null; tip.hidden = true; idleFrames = 0; draw(); } });
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    view.zoom = Math.max(0.5, Math.min(4, view.zoom * Math.exp(-e.deltaY * 0.0015)));
    idleFrames = 0; draw();
  }, { passive: false });

  // ------------------------------------------------------------------ controls
  const setSpin = (on) => { spinning = on; spinBtn.setAttribute('aria-pressed', on ? 'true' : 'false'); };
  setSpin(spinning);
  spinBtn.addEventListener('click', () => setSpin(!spinning));
  document.querySelector('[data-cm-reset]').addEventListener('click', () => {
    view.zoom = VIEW0.zoom; target = { yaw: VIEW0.yaw, pitch: VIEW0.pitch }; select(null, false);
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && selected) select(null, false); });

  resize();
  requestAnimationFrame(frame);
})();

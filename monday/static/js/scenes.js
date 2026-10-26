/* Monday — Monday test hero scenes: one living scene per weekday.
 *
 * Пн mountains · Вт dipole field · Ср dragon fractal · Чт formula spiral · Пт π spiral → π
 * Сб sphere of numbers · Вс world map of lights. The canvas carries its settings:
 *   data-scene="0…6"  data-mode="before|live|after"  data-topics='["…"]' (the student's weak topics)
 * Before the start the scene is calm and dimmer, while the test is live it is faster and brighter.
 * The cursor works as a lens, a click sends a pulse (sphere: new digits, map: new lights).
 * Phones: fewer elements and 30 fps; off-screen or hidden tabs pause; "reduce motion" shows a still frame.
 */
(function () {
  "use strict";
  const cv = document.querySelector("[data-scene]");
  if (!cv) return;
  const ctx = cv.getContext("2d");
  const stage = cv.parentElement;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const small = matchMedia("(max-width: 640px)").matches;
  const TAU = Math.PI * 2;
  const C = { navy: "#0c1872", ink: "#070f4d", royal: "#2747d8", pale: "#8fa6ff", mist: "#c9d3ff", paper: "#f3f5ff" };
  const MONO = '"IBM Plex Mono", ui-monospace, Menlo, monospace';
  let TOPICS_IN = [];
  try { TOPICS_IN = JSON.parse(cv.dataset.topics || "[]"); } catch (e) { TOPICS_IN = []; }
  const MODE = { before: { speed: .7, veil: .22 }, live: { speed: 1.5, veil: 0 }, after: { speed: .9, veil: .12 } };
  const mode = MODE[cv.dataset.mode] ? cv.dataset.mode : "before";
  let W = 0, H = 0, dpr = 1;
  const speed = 1, density = small ? .7 : 1;
  let playing = !reduce, t = reduce ? 6 : 0, last = performance.now(), lastDraw = 0, visible = true;
  const ptr = { x: -1e4, y: -1e4, on: 0, pulse: -1e4, px: 0, py: 0 };
  let cur = Math.max(0, Math.min(6, parseInt(cv.dataset.scene, 10) || 0));
  let SHIFT = 0;
  let state = {};

  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const ease = (x) => (x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const rnd = (a, b) => a + Math.random() * (b - a);
  const hash = (n) => { const s = Math.sin(n * 127.1) * 43758.5453; return s - Math.floor(s); };

  function resize() {
    const r = stage.getBoundingClientRect();
    dpr = Math.min(1.5, window.devicePixelRatio || 1);
    W = r.width; H = r.height;
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    state = {}; // scenes rebuild their caches at the new size
  }
  const lens = (x, y, rad) => ptr.on * Math.max(0, 1 - Math.hypot(x - ptr.x, y - ptr.y) / rad);
  const pulseAt = (x, y) => { const d = Math.hypot(x - ptr.px, y - ptr.py), age = (t - ptr.pulse) * 520; return Math.max(0, 1 - Math.abs(d - age) / 60) * Math.max(0, 1 - age / 900); };

  /* -------------------------------------------------------------- 1. mountains (pixel background) */
  function mountains() {
    const px = Math.max(5, Math.round(Math.min(W, H) / 70 / density));
    const cols = Math.ceil(W / px) + 1, rows = Math.ceil(H / px);
    // sky: vertical pixel gradient
    for (let r = 0; r < rows; r++) {
      const k = r / rows;
      ctx.fillStyle = `rgb(${Math.round(12 + 30 * k)},${Math.round(24 + 50 * k)},${Math.round(114 + 70 * k)})`;
      ctx.fillRect(0, r * px, W, px + 1);
    }
    const layers = [
      { base: .44, amp: .16, f: 1.1, sp: 1.2, col: [150, 170, 240] },
      { base: .55, amp: .14, f: 1.6, sp: 2.2, col: [96, 120, 222] },
      { base: .65, amp: .12, f: 2.2, sp: 3.6, col: [54, 76, 190] },
      { base: .75, amp: .09, f: 3.0, sp: 5.4, col: [26, 42, 140] },
      { base: .86, amp: .06, f: 4.2, sp: 8.0, col: [8, 14, 70] },
    ];
    layers.forEach((L, li) => {
      const off = t * L.sp;
      for (let c = 0; c < cols; c++) {
        const x = (c * px + off * px) / W;
        const n = Math.sin(x * L.f * 3.1 + li * 7) * .55 + Math.sin(x * L.f * 7.3 + li) * .28 + Math.sin(x * L.f * 17.9 + li * 3) * .12 + Math.sin(x * L.f * 41.0) * .05;
        let top = Math.round((L.base - L.amp * n) * rows);
        const lx = c * px + px / 2;
        const l = lens(lx, top * px, 90);
        top -= Math.round(l * 3);
        // misty top edge: the first rows of each ridge are lighter
        for (let r = Math.max(0, top); r < rows; r++) {
          const fade = clamp((r - top) / 5, 0, 1);
          const [a, b, d] = L.col;
          const m = (1 - fade) * 28 + pulseAt(lx, r * px) * 60;
          ctx.fillStyle = `rgb(${Math.round(a + m)},${Math.round(b + m)},${Math.round(d + m)})`;
          ctx.fillRect(c * px, r * px, px - 1, px - 1);
        }
      }
    });
    // as a background the scene sits under the hero text: a translucent navy veil
    ctx.fillStyle = "rgba(12,24,114,0.3)";
    ctx.fillRect(0, 0, W, H);
    return "пиксель " + px + "px · 5 слоёв";
  }

  /* -------------------------------------------------------------- 2. dipole field */
  function field() {
    if (!state.lines) {
      const lines = [];
      const Ls = [.22, .36, .52, .7, .9, 1.0];
      const nPhi = Math.round(10 * density);
      for (const L of Ls) for (let k = 0; k < nPhi; k++) {
        const phi = k / nPhi * TAU + L * 2, pts = [];
        for (let i = 1; i < 140; i++) { const th = i / 140 * Math.PI; const r = L * Math.sin(th) ** 2; pts.push([r * Math.sin(th), r * Math.cos(th), phi]); }
        lines.push(pts);
      }
      const rings = [];
      for (let k = 1; k <= 9; k++) rings.push(Math.pow(k / 9, 1.6) * .78);
      state.lines = lines; state.rings = rings;
      state.grain = Array.from({ length: 4000 }, () => [Math.random(), Math.random()]);
    }
    const R = Math.min(W, H) * .44, cx = W / 2, cy = H / 2;
    const rot = t * .25, tilt = -.32;
    const cr = Math.cos(rot), sr = Math.sin(rot), ct = Math.cos(tilt), st = Math.sin(tilt);
    const proj = (x, y, z) => {
      const X = x * cr + z * sr, Z = -x * sr + z * cr;
      const Y = y * ct - Z * st, Z2 = y * st + Z * ct;
      const s = 3 / (3 + Z2);
      return [cx + X * R * s, cy - Y * R * s, Z2];
    };
    for (const pts of state.lines) {
      pts.forEach(([rho, y, phi], i) => {
        const [x, yy, z] = proj(rho * Math.cos(phi), y, rho * Math.sin(phi));
        const flow = (Math.sin(i * .35 - t * 4 + phi * 3) + 1) / 2;
        const depth = clamp(.55 - z * .5, .15, 1);
        const l = lens(x, yy, 80) + pulseAt(x, yy);
        ctx.globalAlpha = depth * (.25 + .75 * flow ** 3) + l * .5;
        ctx.fillStyle = flow > .92 ? C.paper : C.mist;
        const s = 1.2 + flow ** 4 * 1.6 + l * 2;
        ctx.fillRect(x - s / 2, yy - s / 2, s, s);
      });
    }
    state.rings.forEach((rr, k) => {
      const n = Math.round(80 + rr * 260);
      for (let i = 0; i < n; i++) {
        const a = i / n * TAU + t * (.6 - k * .04);
        const [x, y, z] = proj(Math.cos(a) * rr, 0, Math.sin(a) * rr);
        ctx.globalAlpha = clamp(.6 - z * .4, .2, .95);
        ctx.fillStyle = C.paper;
        ctx.fillRect(x - .7, y - .7, 1.4, 1.4);
      }
    });
    // axis
    for (let i = -60; i <= 60; i++) { const [x, y] = proj(0, i / 60 * .98, 0); ctx.globalAlpha = .55; ctx.fillStyle = C.paper; ctx.fillRect(x - .6, y - .6, 1.2, 1.2); }
    ctx.globalAlpha = .05; ctx.fillStyle = C.paper;
    for (const [a, b] of state.grain) ctx.fillRect(a * W, b * H, 1, 1);
    ctx.globalAlpha = 1;
    return "r = L·sin²θ · " + state.lines.length + " линий";
  }

  /* -------------------------------------------------------------- 3. dragon fractal */
  function dragon() {
    const MAX = 12;
    if (!state.pts) { state.pts = [[0, 0], [1, 0]]; state.n = 0; state.t0 = t; }
    const PER = .9 + state.n * .14;
    let p = (t - state.t0) / PER;
    if (p >= 1) {
      // fold done: bake the copy into the curve
      const P = state.pts, pv = P[P.length - 1], add = [];
      for (let i = P.length - 2; i >= 0; i--) { const dx = P[i][0] - pv[0], dy = P[i][1] - pv[1]; add.push([pv[0] - dy, pv[1] + dx]); }
      state.pts = P.concat(add); state.n++; state.t0 = t; p = 0;
      if (state.n >= MAX) { state.pts = [[0, 0], [1, 0]]; state.n = 0; }
    }
    const P = state.pts, pv = P[P.length - 1];
    const a = ease(clamp(p * 1.25, 0, 1)) * Math.PI / 2, ca = Math.cos(a), sa = Math.sin(a);
    const copy = [];
    for (let i = P.length - 2; i >= 0; i--) { const dx = P[i][0] - pv[0], dy = P[i][1] - pv[1]; copy.push([pv[0] + dx * ca - dy * sa, pv[1] + dx * sa + dy * ca]); }
    const all = P.concat(copy);
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const [x, y] of all) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
    const pad = .14, s = Math.min(W * (1 - 2 * pad) / Math.max(1e-6, x1 - x0), H * (1 - 2 * pad) / Math.max(1e-6, y1 - y0));
    const ox = W / 2 - (x0 + x1) / 2 * s, oy = H / 2 - (y0 + y1) / 2 * s + H * .02;
    const line = (arr, col, w) => { ctx.strokeStyle = col; ctx.lineWidth = w; ctx.beginPath(); arr.forEach(([x, y], i) => (i ? ctx.lineTo(ox + x * s, oy + y * s) : ctx.moveTo(ox + x * s, oy + y * s))); ctx.stroke(); };
    ctx.lineJoin = "miter"; ctx.lineCap = "square";
    const w = clamp(s * .22, 1, 4);
    line(P, C.paper, w);
    line([pv].concat(copy), C.pale, w);
    // pivot
    ctx.fillStyle = C.paper; ctx.beginPath(); ctx.arc(ox + pv[0] * s, oy + pv[1] * s, 3.5, 0, TAU); ctx.fill();
    // labels in IBM Plex Mono
    const n = state.n + 1, f = Math.max(11, Math.min(15, W / 60));
    ctx.font = `500 ${f}px ${MONO}`; ctx.fillStyle = C.mist; ctx.textBaseline = "top";
    const rx = W - SHIFT - 24, ry = 64;   // top right, under the "live" badge, clear of the greeting
    ctx.textAlign = "right";
    ctx.fillText(`ИТЕРАЦИЯ ${String(n).padStart(2, "0")} / ${MAX}`, rx, ry);
    ctx.fillText(`отрезков: 2^${n} = ${2 ** n}`, rx, ry + f * 1.6);
    ctx.fillText("X → X+YF+   Y → −FX−Y   угол 90°", rx, ry + f * 3.2);
    ctx.textAlign = "left";
    return "кривая дракона";
  }

  /* -------------------------------------------------------------- 4. login spiral + halftone */
  function spiral() {
    const ITEMS = ["π", "∫", "√x", "Σ", "x²", "sin α", "∞", "Δ", "e^iπ", "log₂", "f(x)", "∠", "≈", "a²+b²", "θ", "dy/dx", "○", "△", "□", "lim"];
    if (!state.items) {
      const n = Math.round(54 * density);
      state.items = Array.from({ length: n }, (_, i) => ({ arm: i % 3, z: rnd(-1500, 400), txt: ITEMS[i % ITEMS.length], spin: rnd(-1, 1), j: rnd(-30, 30) }));
    }
    const cx = W * .55, cy = H * .5, F = 820 * Math.min(W, H) / 640;
    // halftone dots
    const g = Math.max(14, Math.round(Math.min(W, H) / 34));
    for (let y = g / 2; y < H; y += g) for (let x = g / 2; x < W; x += g) {
      const base = (x / W + y / H) / 2;
      const wave = (Math.sin((x + y) / 90 - t * 1.4) + 1) / 2;
      const ring = (Math.sin(Math.hypot(x - cx, y - cy) / 40 - t * 2.2) + 1) / 2;
      const l = lens(x, y, 120) + pulseAt(x, y);
      const r = g * (.06 + .22 * base ** 1.5 + .08 * wave + .05 * ring + .25 * l);
      ctx.fillStyle = l > .2 ? C.pale : "#2a3aa0";
      ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fill();
    }
    // spiral items, far to near
    const items = state.items;
    for (const it of items) { it.z += 58 * (1 / 60) * speed * (playing ? 1 : 0); if (it.z > 430) { it.z = -1500; it.j = rnd(-30, 30); } }
    items.sort((a, b) => a.z - b.z);
    for (const it of items) {
      const a = it.arm * TAU / 3 + it.z * .0034 + t * .16;
      const rad = 210 + it.j;
      const sc = F / (F - it.z);
      const x = cx + Math.cos(a) * rad * sc * (Math.min(W, H) / 640), y = cy + Math.sin(a) * rad * sc * (Math.min(W, H) / 640);
      const alpha = clamp((it.z + 1500) / 600, 0, 1) * clamp((430 - it.z) / 160, 0, 1);
      ctx.save(); ctx.translate(x, y); ctx.rotate(Math.sin(t * .8 + it.spin * 3) * .25 * it.spin);
      ctx.globalAlpha = alpha; ctx.fillStyle = C.paper;
      ctx.font = `500 ${Math.round(13 * sc)}px ${MONO}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(it.txt, 0, 0); ctx.restore();
    }
    ctx.globalAlpha = 1;
    return "3 рукава · " + items.length + " знаков";
  }

  /* -------------------------------------------------------------- 5. π spiral → π */
  function piDigits(n) {
    const unity = 10n ** BigInt(n + 10);
    const atanInv = (x) => { x = BigInt(x); let sum = 0n, term = unity / x, k = 1n, sign = 1n; const x2 = x * x; while (term !== 0n) { sum += sign * term / k; term /= x2; k += 2n; sign = -sign; } return sum; };
    return (4n * (4n * atanInv(5) - atanInv(239))).toString().slice(0, n);
  }
  function piScene() {
    if (!state.digits) {
      const N = Math.round(620 * density);
      const d = piDigits(N);
      state.digits = ("3." + d.slice(1)).split("");
      // target points: pixels of a big "π" glyph
      const S = 240, oc = document.createElement("canvas"); oc.width = oc.height = S;
      const o = oc.getContext("2d"); o.fillStyle = "#fff"; o.font = `600 ${S * .9}px ${MONO}`; o.textAlign = "center"; o.textBaseline = "middle"; o.fillText("π", S / 2, S * .54);
      const data = o.getImageData(0, 0, S, S).data, pts = [];
      for (let y = 0; y < S; y += 3) for (let x = 0; x < S; x += 3) if (data[(y * S + x) * 4 + 3] > 128) pts.push([x / S - .5, y / S - .5]);
      for (let i = pts.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [pts[i], pts[j]] = [pts[j], pts[i]]; }
      state.target = pts;
    }
    const D = state.digits, N = D.length, R = Math.min(W, H) * .46, cx = W / 2, cy = H / 2;
    const LOOP = 14, ph = (t % LOOP) / LOOP;           // 0–.62 spiral · .62–.72 gather · .72–.86 hold π · .86–1 release
    const m = ph < .62 ? 0 : ph < .72 ? ease((ph - .62) / .1) : ph < .86 ? 1 : 1 - ease((ph - .86) / .14);
    const flow = t * 1.2;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    // spiral positions with near-constant spacing between digits
    let theta = 0;
    const turns = 7.5, rot = -t * .15;
    for (let i = 0; i < N; i++) {
      const u = ((i + flow) % N) / N;                      // digits drift inward along the spiral
      const r = R * (1 - u) ** .85 + 6;
      theta = u * turns * TAU;
      const sx = cx + Math.cos(theta + rot) * r, sy = cy + Math.sin(theta + rot) * r;
      const tp = state.target[i % state.target.length];
      const tx = cx + tp[0] * R * 1.7, ty = cy + tp[1] * R * 1.7;
      const x = sx + (tx - sx) * m, y = sy + (ty - sy) * m;
      const size = (6 + 15 * (1 - u)) * (1 - m) + 7 * m;
      const l = lens(x, y, 70) + pulseAt(x, y);
      ctx.globalAlpha = clamp(.25 + .75 * (1 - u), .2, 1) * (1 - m) + .95 * m;
      ctx.fillStyle = l > .25 ? C.pale : C.paper;
      ctx.save(); ctx.translate(x, y); ctx.rotate((theta + rot + Math.PI / 2) * (1 - m));
      ctx.font = `500 ${Math.max(5, size * (1 + l * .6))}px ${MONO}`; ctx.fillText(D[i], 0, 0); ctx.restore();
    }
    ctx.globalAlpha = 1;
    return ph < .62 ? `π = ${D.slice(0, 12).join("")}…` : "π";
  }

  /* -------------------------------------------------------------- 6. sphere of numbers */
  function numSphere() {
    if (!state.pts) {
      const n = small ? 400 : 650, pts = [];
      for (let i = 0; i < n; i++) {
        const y = 1 - (i + .5) / n * 2, r = Math.sqrt(1 - y * y), a = i * Math.PI * (3 - Math.sqrt(5));
        pts.push({ x: Math.cos(a) * r, y, z: Math.sin(a) * r, d: String(Math.floor(Math.random() * 10)), next: rnd(0, 6), flip: -1 });
      }
      state.pts = pts;
    }
    const R = Math.min(W, H) * .28, cx = W / 2, cy = H / 2;
    const rot = t * .35, tilt = .35 + Math.sin(t * .2) * .1;
    const cr = Math.cos(rot), sr = Math.sin(rot), ct = Math.cos(tilt), st = Math.sin(tilt);
    const out = state.pts.map((p) => {
      if (t > p.next) { p.d = String(Math.floor(Math.random() * 10)); p.next = t + rnd(2, 8); }
      if (p.flip > 0 && t > p.flip) { p.d = String(Math.floor(Math.random() * 10)); p.flip = -1; p.pop = t; }
      const X = p.x * cr + p.z * sr, Z = -p.x * sr + p.z * cr;
      const Y = p.y * ct - Z * st, Z2 = p.y * st + Z * ct;
      const s = 3 / (3 - Z2);
      return { x: cx + X * R * s, y: cy - Y * R * s, z: Z2, d: p.d, pop: p.pop };
    }).sort((a, b) => a.z - b.z);
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    for (const p of out) {
      const k = (p.z + 1) / 2, l = lens(p.x, p.y, 70) + pulseAt(p.x, p.y);
      ctx.globalAlpha = .12 + .88 * k ** 1.6;
      ctx.fillStyle = l > .25 ? C.pale : C.paper;
      const pop = p.pop ? Math.max(0, 1 - (t - p.pop) / .5) : 0;
      if (pop) ctx.fillStyle = C.pale;
      ctx.font = `${k > .75 ? 600 : 400} ${Math.round((5 + 9 * k ** 2 + l * 6) * (1 + pop * .8))}px ${MONO}`;
      ctx.fillText(p.d, p.x, p.y);
    }
    ctx.globalAlpha = 1;
    return state.pts.length + " цифр";
  }

  /* -------------------------------------------------------------- 7. world map of lights + clouds */
  const WORLD = [".....................#...##....###.####################............##.............................#.................................", "..................###.#.##..##.##........##############............................##...........#######.........###.................", "................###...##.#.###.###........###########.............................#........##########.###..##.......................", "....#..............#####...#.#######.......###########............................#...######.###########################.......#....", ".###################..#...#.##.#..###......#########................########.....###############################################....", ".#.###########################.....##.#...#######..................#######..#######################################################.", "...##########################.#.#..###.....####.......##..........#########.###################################################.....", ".###########################......##........##.............#....####..#################################################...###.......", "...####....################......####.#.........................#####..###########################################.......#..........", "....#.......#################.....######....................#....#.#..###########################################......###..........", "..............##################.########..................#.#...#..############################################.......##...........", "...............#################.#########................#.###.##################################################.....#............", "................#####################.#..#....................###################################################.#...#.............", "................######################....#..................####################################################...................", ".................######################.......................####.######.######################################....................", "................####################.......................####...#.####.....#################################...##.................", "................###################........................###...#.####.##################################.##....#..................", ".................#################.........................###.....#..#.##################################..#....#..................", "..................################............................####.........###############################..#...#...................", "...................##############..........................#######.........###############################...##.....................", "...................#.###########..........................##########.######################################.........................", "....................#######...............................######################.#########################..........................", "......................####......#........................#################.######..#######################..........................", ".....................#.###..............................###################.#######....##################...........................", ".......................###.......#......................###################.########...#.######.#######.............................", "........................###..#.....##...................####################.######......####...#####...............................", ".........................#####..........................####################..####.......###......###.....#.........................", "............................####........................#####################.##.........##.......####..............................", "..............................#.........................######################...........##.......####.....#........................", "...............................#..#####..................########################.........#.........#......#........................", "................................#########................#######################...........#......#........#........................", "..................................#########................#.#..################.................#.#....##..........................", "..................................#########.......................#############...................##...##...........................", ".................................##########......................#############....................##..###...........................", "................................##############...................############......................##.###..#.##.#...................", "................................################..................##########........................#.....#....####..#..............", ".................................################..................#########.........................##..........###................", ".................................################..................#########.....................................#..................", "..................................##############...................##########.......................................................", "..................................##############...................##########..#.............................###....................", "...................................#############..................###########.##............................####..#.................", "....................................###########...................#########...##...........................#########................", "....................................###########....................########...##.........................###########................", "....................................##########.....................########...#.........................#############...............", "....................................########.......................#######....#.........................##############..............", "....................................########........................######..............................##############..............", "....................................########........................#####...............................##############..............", "....................................#######..........................###................................####...#######..............", "....................................######..............................................................#........####...............", "...................................######........................................................................####...............", "...................................####.......................................................................................#.....", "...................................###.............................................................................#.........#......", "...................................###.....................................................................................##.......", "...................................##...............................................................................................", "..................................###...............................................................................................", "...................................##...............................................................................................", "...................................##...............................................................................................", "...................................................................................................................................."];
  const CITIES = [ // [lat, lon] — Central Asia first: Bishkek is the hub of the arcs
    [42.87, 74.59], [43.24, 76.95], [41.3, 69.24], [38.56, 68.78], [51.17, 71.43], [55.75, 37.62], [37.57, 126.98],
    [35.68, 139.69], [39.9, 116.4], [31.23, 121.47], [28.61, 77.21], [1.35, 103.82], [25.2, 55.27], [41.01, 28.98],
    [51.5, -0.12], [48.86, 2.35], [52.52, 13.4], [40.71, -74.0], [34.05, -118.24], [43.65, -79.38], [19.43, -99.13],
    [-23.55, -46.63], [-34.6, -58.38], [30.04, 31.24], [6.52, 3.38], [-1.29, 36.82], [-33.92, 18.42], [-33.87, 151.21],
    [-37.81, 144.96], [22.32, 114.17], [13.75, 100.5], [59.33, 18.07], [64.15, -21.94], [61.22, -149.9], [-12.05, -77.04],
  ];
  const TOPICS = TOPICS_IN.length ? TOPICS_IN : ["логарифмы", "проценты", "векторы", "тригонометрия", "дроби", "вероятность"];
  function worldMap() {
    const rows = WORLD.length, cols = WORLD[0].length;
    const cell = Math.min(W * .94 / cols, H * .9 / rows), ox = (W - cell * cols) / 2, oy = (H - cell * rows) / 2;
    const at = (lat, lon) => [ox + ((lon + 168) / 358) * (cols - 1) * cell + cell / 2, oy + ((78 - lat) / 134) * (rows - 1) * cell + cell / 2];
    if (!state.lights) {
      const pick = CITIES.slice(1).sort(() => Math.random() - .5).slice(0, Math.round(14 * density));
      state.lights = [CITIES[0], ...pick].map((c, i) => ({ c, born: t + i * .12, tw: rnd(0, TAU), topic: null }));
      // topic labels only on lights far from the hub and from each other, so they never overlap
      let k = 0; const labelled = [CITIES[0]];
      for (const L of state.lights.slice(1)) {
        if (k >= TOPICS.length) break;
        if (labelled.every((q) => Math.hypot(q[0] - L.c[0], q[1] - L.c[1]) > 22)) { L.topic = TOPICS[k++]; labelled.push(L.c); }
      }
      // pixel clouds: blobs on the map's own grid, drifting right
      const blob = () => { const w = Math.round(rnd(9, 17)), h = Math.round(rnd(3, 6)), cells = [];
        for (let r = 0; r < h; r++) for (let c = 0; c < w; c++) {
          const nx = (c - w / 2) / (w / 2), ny = (r - h / 2) / (h / 2), edge = nx * nx + ny * ny * 1.4 + rnd(-.25, .25);
          if (edge < 1) cells.push([c, r, clamp(1 - edge, .25, 1)]);
        } return { cells, w, h }; };
      state.clouds = Array.from({ length: small ? 4 : 6 }, () => ({ x: rnd(-.1, 1), y: rnd(.04, .8), v: rnd(.005, .012), ...blob() }));
    }
    // one light fades out and a new city lights up every ~25 s (no sudden reload)
    if (!state.swapAt) state.swapAt = t + 25;
    if (t > state.swapAt && state.lights.length > 2) {
      state.swapAt = t + 22 + rnd(0, 8);
      const used = new Set(state.lights.map((L) => L.c.join()));
      const free = CITIES.slice(1).filter((c) => !used.has(c.join()));
      const i = 1 + Math.floor(Math.random() * (state.lights.length - 1));
      const old = state.lights[i];
      if (free.length && !old.dying) { old.dying = t; state.lights.push({ c: free[Math.floor(Math.random() * free.length)], born: t + 1.2, tw: rnd(0, TAU), topic: old.topic }); }
    }
    state.lights = state.lights.filter((L) => !L.dying || t - L.dying < 1.2);
    // faint graticule
    ctx.strokeStyle = "rgba(201,211,255,.08)"; ctx.lineWidth = 1;
    for (let k = 1; k < 4; k++) { ctx.beginPath(); ctx.ellipse(W / 2, H / 2, W * .6 * k / 3, H * .7, 0, 0, TAU); ctx.stroke(); }
    ctx.beginPath(); ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2); ctx.moveTo(W / 2, 0); ctx.lineTo(W / 2, H); ctx.stroke();
    // cloud shadow sampler
    const cloudGrid = new Map();
    for (const c of state.clouds) { const c0 = Math.round(c.x * cols), r0 = Math.round(c.y * rows); for (const [dc, dr, a] of c.cells) cloudGrid.set((r0 + dr) * 1000 + c0 + dc, a); }
    const shade = (x, y) => cloudGrid.get(Math.round((y - oy - cell / 2) / cell) * 1000 + Math.round((x - ox - cell / 2) / cell)) || 0;
    // land dots
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      if (WORLD[r][c] !== "#") continue;
      const x = ox + c * cell + cell / 2, y = oy + r * cell + cell / 2;
      const l = lens(x, y, 90) + pulseAt(x, y);
      ctx.globalAlpha = (.42 + .3 * l) * (1 - .55 * shade(x, y));
      ctx.fillStyle = l > .3 ? C.pale : C.mist;
      ctx.beginPath(); ctx.arc(x, y, cell * (.26 + .12 * l), 0, TAU); ctx.fill();
    }
    // arcs from the hub
    const hub = at(...state.lights[0].c);
    state.lights.slice(1).forEach((L) => {
      const p = clamp((t - L.born) / 1.6, 0, 1); if (!p || L.dying) return;
      const [x, y] = at(...L.c), mx = (hub[0] + x) / 2, my = Math.min(hub[1], y) - Math.hypot(x - hub[0], y - hub[1]) * .28;
      ctx.globalAlpha = .38; ctx.strokeStyle = C.mist; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(...hub);
      const N = 30; for (let i = 1; i <= N * p; i++) { const u = i / N; ctx.lineTo((1 - u) ** 2 * hub[0] + 2 * (1 - u) * u * mx + u * u * x, (1 - u) ** 2 * hub[1] + 2 * (1 - u) * u * my + u * u * y); }
      ctx.stroke();
      // a spark travelling along the finished arc
      if (p === 1) { const u = ((t * .35 + L.tw) % 1); ctx.globalAlpha = .9; ctx.fillStyle = C.paper; ctx.beginPath(); ctx.arc((1 - u) ** 2 * hub[0] + 2 * (1 - u) * u * mx + u * u * x, (1 - u) ** 2 * hub[1] + 2 * (1 - u) * u * my + u * u * y, 1.6, 0, TAU); ctx.fill(); }
    });
    // lights
    state.lights.forEach((L, i) => {
      const p = clamp((t - L.born) / .6, 0, 1) * (L.dying ? clamp(1 - (t - L.dying) / 1.2, 0, 1) : 1); if (!p) return;
      const [x, y] = at(...L.c), tw = .65 + .35 * Math.sin(t * 2.4 + L.tw), rad = cell * (i ? 2.6 : 3.6) * p * tw;
      const g = ctx.createRadialGradient(x, y, 0, x, y, rad);
      g.addColorStop(0, "rgba(255,255,255,.95)"); g.addColorStop(.25, "rgba(201,211,255,.55)"); g.addColorStop(1, "rgba(143,166,255,0)");
      ctx.globalAlpha = 1; ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, rad, 0, TAU); ctx.fill();
      ctx.fillStyle = C.paper; ctx.beginPath(); ctx.arc(x, y, cell * .45, 0, TAU); ctx.fill();
      if (L.topic && p === 1) { ctx.globalAlpha = .85; ctx.font = `500 ${Math.max(10, cell * 1.3)}px ${MONO}`; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(L.topic, x + cell * 1.6, y - cell * 1.2); }
    });
    // pixel clouds drift over the map
    for (const c of state.clouds) {
      c.x += c.v * (playing ? 1 : 0) * speed / 60; if (c.x > 1.15) { c.x = -.2; c.y = rnd(.04, .8); }
      const c0 = Math.round(c.x * cols), r0 = Math.round(c.y * rows);
      for (const [dc, dr, a] of c.cells) {
        ctx.globalAlpha = .34 * a; ctx.fillStyle = C.paper;
        ctx.fillRect(ox + (c0 + dc) * cell + 1, oy + (r0 + dr) * cell + 1, cell - 2, cell - 2);
      }
    }
    ctx.globalAlpha = 1;
    return state.lights.length + " огней";
  }

  const DRAW = [mountains, field, dragon, spiral, piScene, numSphere, worldMap];
  function draw() {
    ctx.globalAlpha = 1; ctx.clearRect(0, 0, W, H);
    // the scene is the hero's background: centred objects move to the right half so the text stays readable
    const shift = SHIFT = W > 900 && [1, 2, 4, 5].includes(cur) ? W * .2 : 0;
    ctx.save(); ctx.translate(shift, 0);
    DRAW[cur]();
    ctx.restore();
    if (MODE[mode].veil) { ctx.globalAlpha = MODE[mode].veil; ctx.fillStyle = C.ink; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
  }
  const FRAME = 1000 / 30;   // an ambient background: 30 fps is plenty and keeps laptops cool
  function loop(now) {
    const dt = Math.min(.05, (now - last) / 1000); last = now;
    ptr.on += ((ptr.x > -1e3 ? 1 : 0) - ptr.on) * .12;
    requestAnimationFrame(loop);
    if (!visible || document.hidden) return;
    if (FRAME && now - lastDraw < FRAME) return;
    lastDraw = now;
    if (playing) t += dt * speed * MODE[mode].speed;
    draw();
  }
  // the canvas sits under the text, so the hero tracks the cursor
  stage.addEventListener("pointermove", (e) => { const r = cv.getBoundingClientRect(), sh = W > 900 && [1, 2, 4, 5].includes(cur) ? W * .2 : 0; ptr.x = e.clientX - r.left - sh; ptr.y = e.clientY - r.top; });
  stage.addEventListener("pointerleave", () => { ptr.x = ptr.y = -1e4; });
  cv.addEventListener("click", (e) => {
    if (cur === 3 || cur === 6) return;   // dead click: the spiral and the world map ignore clicks
    const r = cv.getBoundingClientRect(), sh = W > 900 && [1, 2, 4, 5].includes(cur) ? W * .2 : 0;
    ptr.px = e.clientX - r.left - sh; ptr.py = e.clientY - r.top; ptr.pulse = t;
    if (cur === 2 && state.t0 !== undefined) state.t0 -= 2;
    if (cur === 4) t += 14 * .62 - (t % 14);
    if (cur === 5 && state.pts) state.pts.forEach((q) => { q.flip = t + (q.y + 1) * .35 + Math.random() * .1; });
    if (reduce) draw();
  });
  new ResizeObserver(() => { resize(); if (reduce) draw(); }).observe(stage);
  new IntersectionObserver((e) => { visible = e[0].isIntersecting; last = performance.now(); }).observe(stage);
  // demo: every scene plays for 20 s, then the hero fades to the next one
  const cycle = (cv.dataset.cycle || "").split(",").filter(Boolean).map(Number);
  const greetEl = document.querySelector("[data-scene-greet]");
  let lines = [];
  try { lines = JSON.parse(cv.dataset.lines || "[]"); } catch (e) { lines = []; }
  if (cycle.length > 1 && !reduce) {
    let k = Math.max(0, cycle.indexOf(cur));
    setInterval(() => {
      cv.classList.add("is-fading"); if (greetEl && mode === "before") greetEl.classList.add("is-fading");
      setTimeout(() => {
        k = (k + 1) % cycle.length; cur = cycle[k]; state = {}; t = 0;
        if (greetEl && mode === "before" && lines[cur]) greetEl.textContent = lines[cur];
        draw();
        cv.classList.remove("is-fading"); if (greetEl) greetEl.classList.remove("is-fading");
      }, 1400);
    }, 20000);
  }
  resize();
  if (reduce) draw(); else requestAnimationFrame(loop);
})();

/* countdown tiles: days · hours · minutes · seconds to the start; reloads when the test opens */
(function () {
  const box = document.querySelector("[data-countdown]");
  if (!box) return;
  const end = Date.now() + Number(box.dataset.seconds) * 1000;
  const cells = { d: box.querySelector("[data-d]"), h: box.querySelector("[data-h]"), m: box.querySelector("[data-m]"), s: box.querySelector("[data-s]") };
  const pad = (n) => String(n).padStart(2, "0");
  const tick = () => {
    const left = Math.max(0, Math.round((end - Date.now()) / 1000));
    cells.d.textContent = Math.floor(left / 86400);
    cells.h.textContent = pad(Math.floor(left % 86400 / 3600));
    cells.m.textContent = pad(Math.floor(left % 3600 / 60));
    cells.s.textContent = pad(left % 60);
    for (const k of "dhms") window.MondayPixel(box.querySelector(`[data-pix="${k}"]`), cells[k].textContent, innerWidth < 640 ? 4 : (Number(box.dataset.cell) || 6));
    if (left === 0) { setTimeout(() => location.reload(), 1500); return; }
    setTimeout(tick, 1000 - (Date.now() % 1000));
  };
  tick();
})();

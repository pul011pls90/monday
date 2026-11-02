/* Monday — Home hero: a bitmap sky. Dithered pixel clouds drift across the blue, over a thin grid;
 * a few grid tiles glow pink/orange and change on their own. The cursor blows the clouds apart,
 * lights the tile under it, and a click paints that tile. Quiet under the text so it stays readable.
 */
(function () {
  "use strict";
  const hero = document.querySelector("[data-hero]");
  if (!hero) return;
  const canvas = hero.querySelector("[data-hero-dots]");
  // background mode (home page): the sky fills the whole window behind the cards, quieter, and follows the cursor
  const bg = hero.hasAttribute("data-hero-bg");
  const ctx = canvas.getContext("2d");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };

  const PX = 5;            // one bitmap pixel
  const CELL = 150;        // grid tile
  const FADE = 48;         // soft edge of the quiet zones under the text
  const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map((v) => (v + 0.5) / 16);
  const PINK = "#FF2E93", ORANGE = "#FFAA6B";

  let W = 0, H = 0, dpr = 1, textBoxes = [], cols = 0, rows = 0, ink = "255, 255, 255";
  const pointer = { x: 0, y: 0, cx: 0, cy: 0, presence: 0, inside: false };
  const tiles = new Map();  // "i,j" -> { a: current alpha, to: target alpha, painted }

  // value noise + fbm: the cloud field
  const hash = (x, y) => { const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return s - Math.floor(s); };
  function noise(x, y) {
    const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  }
  const fbm = (x, y) => noise(x, y) * 0.55 + noise(x * 2.1, y * 2.1) * 0.3 + noise(x * 4.3, y * 4.3) * 0.15;

  function resize() {
    const r = hero.getBoundingClientRect();
    W = r.width; H = r.height;
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = false;
    cols = Math.ceil(W / CELL); rows = Math.ceil(H / CELL);
    ink = getComputedStyle(hero).getPropertyValue("--sky-ink").trim() || "255, 255, 255"; // white on blue, blue on white
    textBoxes = Array.from(hero.querySelectorAll(".home-hero__count, .home-goal, .home-strip, .home-hero__note, .result-hero")).map((b) => {
      const q = b.getBoundingClientRect();
      return [q.left - r.left, q.top - r.top, q.right - r.left, q.bottom - r.top];
    });
  }

  // the sky lives in the right part of the card; the text column on the left stays clean
  const quietAt = (x, y) => {
    if (bg) return 1;
    let q = smooth(W * 0.36, W * 0.52, x);
    if (q <= 0) return 0;
    for (const b of textBoxes) {
      const ex = (x - (b[0] + b[2]) / 2) / ((b[2] - b[0]) / 2 + FADE);
      const ey = (y - (b[1] + b[3]) / 2) / ((b[3] - b[1]) / 2 + FADE);
      q = Math.min(q, smooth(0.85, 1.4, Math.hypot(ex, ey)));
    }
    return q;
  };

  // every whole tile in the sky reacts to hover and click; the text blocks over the sky have solid backgrounds,
  // so tiles simply pass behind them. Tiles that touch no text at all are the ones that light up by themselves.
  // the sky starts at 40% of the card, or right of the left text column if that reaches further
  const skyLeft = () => bg ? 0 : Math.max(W * 0.4, ...textBoxes.filter((x) => x[0] < W * 0.4).map((x) => x[2] + 16));
  const inSky = (i, j) => j >= 0 && j < rows && i < cols && i * CELL >= skyLeft();
  const tileFree = (i, j) => {
    const l = i * CELL, t = j * CELL, r = l + CELL, b = t + CELL;
    if (!bg && l < W * 0.45) return false;
    return !textBoxes.some((x) => l < x[2] + 12 && r > x[0] - 12 && t < x[3] + 12 && b > x[1] - 12);
  };

  // tiles change by themselves now and then, so the sky never stands still
  function shuffleTiles() {
    if (bg) return;  // no pink tiles behind the page: they would show through text that has no card under it
    tiles.forEach((t) => { if (!t.painted) t.to = 0; });
    const free = [];
    for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) if (tileFree(i, j)) free.push(`${i},${j}`);
    const n = Math.min(free.length, 1 + Math.floor(Math.random() * 2));
    for (let k = 0; k < n; k++) {
      const key = free.splice(Math.floor(Math.random() * free.length), 1)[0];
      const t = tiles.get(key) || { a: 0, to: 0, painted: false };
      t.to = 0.45; tiles.set(key, t);
    }
  }

  function draw(t) {
    ctx.clearRect(0, 0, W, H);
    const pi = Math.floor(pointer.cx / CELL), pj = Math.floor(pointer.cy / CELL);
    const pc = !bg && pointer.presence > 0.01 && inSky(pi, pj) ? `${pi},${pj}` : null;

    // tiles: pink squares under the clouds (hover fades in fast and out quickly, so no trail is left behind)
    tiles.forEach((tile, key) => {
      const target = Math.max(tile.to, tile.painted ? 0.55 : 0, key === pc ? 0.35 * pointer.presence : 0);
      tile.a += (target - tile.a) * (target > tile.a ? 0.12 : 0.1);
      if (tile.a < 0.01) return;
      const [i, j] = key.split(",").map(Number);
      ctx.globalAlpha = tile.a;
      ctx.fillStyle = PINK;
      ctx.fillRect(i * CELL, j * CELL, CELL, CELL);
    });
    if (pc && !tiles.has(pc)) tiles.set(pc, { a: 0, to: 0, painted: false });
    ctx.globalAlpha = 1;

    // clouds: ordered-dither the fbm field into pixels; the cursor blows a hole into it
    const drift = t * 0.035, white = new Path2D(), warm = new Path2D(), sky = new Path2D();
    for (let y = 0, jy = 0; y < H; y += PX, jy++) {
      for (let x = 0, ix = 0; x < W; x += PX, ix++) {
        let d = fbm(x * 0.0045 + drift, y * 0.009 - drift * 0.3);
        d = smooth(0.38, 0.78, d);
        if (pointer.presence > 0.01) {
          const dx = x - pointer.cx, dy = y - pointer.cy;
          d *= 1 - Math.exp(-(dx * dx + dy * dy) / (2 * 70 * 70)) * pointer.presence * 0.95;
        }
        const q = quietAt(x, y);
        const th = BAYER[(jy & 3) * 4 + (ix & 3)];
        const key = `${Math.floor(x / CELL)},${Math.floor(y / CELL)}`;
        const tile = tiles.get(key), inTile = tile && tile.a > 0.15;
        if (d * q > th) (inTile ? warm : white).rect(x, y, PX - 1, PX - 1);
        else if (!inTile && (ix % 3 === 0) && (jy % 3 === 0) && q > 0.6) sky.rect(x + 1, y + 1, 2, 2); // sparse sky grain
      }
    }
    const k = bg ? 0.6 : 1;  // the background version is a little lighter
    ctx.fillStyle = `rgba(${ink}, ${0.1 * k})`; ctx.fill(sky);
    ctx.fillStyle = `rgba(${ink}, ${0.4 * k})`; ctx.fill(white);
    ctx.globalAlpha = 0.6; ctx.fillStyle = ORANGE; ctx.fill(warm); ctx.globalAlpha = 1;

    // the grid
    ctx.strokeStyle = `rgba(${ink}, ${bg ? 0.1 : 0.14})`; ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 1; i < cols; i++) { ctx.moveTo(i * CELL + 0.5, 0); ctx.lineTo(i * CELL + 0.5, H); }
    for (let j = 1; j < rows; j++) { ctx.moveTo(0, j * CELL + 0.5); ctx.lineTo(W, j * CELL + 0.5); }
    ctx.stroke();
  }

  let last = 0;
  function frame(ms) {
    const t = ms / 1000;
    pointer.cx += (pointer.x - pointer.cx) * 0.18;
    pointer.cy += (pointer.y - pointer.cy) * 0.18;
    pointer.presence += ((pointer.inside ? 1 : 0) - pointer.presence) * 0.08;
    if (t - last > 3.5) { shuffleTiles(); last = t; }
    draw(t);
    if (!reduce) requestAnimationFrame(frame);
  }

  (bg ? window : hero).addEventListener("pointermove", (e) => {
    const r = hero.getBoundingClientRect();
    pointer.x = e.clientX - r.left; pointer.y = e.clientY - r.top;
    if (!pointer.inside) { pointer.cx = pointer.x; pointer.cy = pointer.y; }
    pointer.inside = true;
  });
  (bg ? document.documentElement : hero).addEventListener("pointerleave", () => { pointer.inside = false; });
  // a click on the sky (not on a link or button) paints that tile, a second click clears it
  if (!bg) hero.addEventListener("click", (e) => {
    if (e.target.closest("a, button, input, select, label")) return;
    const r = hero.getBoundingClientRect();
    const ci = Math.floor((e.clientX - r.left) / CELL), cj = Math.floor((e.clientY - r.top) / CELL);
    if (!inSky(ci, cj)) return;
    const key = `${ci},${cj}`;
    const t = tiles.get(key) || { a: 0, to: 0, painted: false };
    t.painted = !t.painted; if (!t.painted) t.to = 0;
    tiles.set(key, t);
    if (reduce) draw(performance.now() / 1000);
  });
  window.addEventListener("resize", () => { resize(); if (reduce) draw(0); });
  resize();
  shuffleTiles();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(resize);
  requestAnimationFrame(frame);
})();

/* Home: live countdown to the exam date (the day starts at local midnight) */
(function () {
  "use strict";
  const box = document.querySelector("[data-countdown]");
  if (!box) return;
  const [y, m, d] = box.dataset.countdown.split("-").map(Number);
  const end = new Date(y, m - 1, d).getTime();
  const cell = (k) => box.querySelector(`[data-cd="${k}"]`);
  const pad = (n) => String(n).padStart(2, "0");
  function tick() {
    let left = Math.max(0, Math.floor((end - Date.now()) / 1000));
    const days = Math.floor(left / 86400); left %= 86400;
    cell("d").textContent = days;
    cell("h").textContent = pad(Math.floor(left / 3600));
    cell("m").textContent = pad(Math.floor((left % 3600) / 60));
    cell("s").textContent = pad(left % 60);
  }
  tick();
  setInterval(tick, 1000);
})();

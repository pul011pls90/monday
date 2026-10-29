/* Monday — Monday test hero in the Home "bitmap sky" style.
 * The day's scene (scenes.js) keeps running on its own canvas, now invisible: it still gets the cursor and clicks.
 * This script samples that canvas every frame and re-prints it as dithered blue pixels on the 150px grid, over
 * faint drifting clouds. Grid tiles where the scene changes most flash pink and fade, the tile under the cursor
 * lights up, and the scene's text labels (dragon) are drawn as crisp text in the corner. Works for every scene.
 */
(function () {
  "use strict";
  const scene = document.querySelector("[data-scene]");
  const sky = document.querySelector("[data-sky-print]");
  if (!scene || !sky) return;
  const stage = sky.parentElement;
  const ctx = sky.getContext("2d");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };

  const PX = 5, CELL = 150, FADE = 40, FRAME = 1000 / 30;
  const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map((v) => (v + 0.5) / 16);
  const PINK = "#FF2E93", ORANGE = "#FFAA6B";
  const MONO = '"IBM Plex Mono", ui-monospace, Menlo, monospace';

  const SP = 2;            // fine pixel for the scene itself: small enough that its digits and labels stay readable
  let W = 0, H = 0, cols = 0, rows = 0, scols = 0, srows = 0, tcols = 0, trows = 0, ink = "43, 96, 229", solid = "#153893", quiet = [];
  let prev = null, heat = null;
  const tiles = new Map();                     // "i,j" -> alpha
  const ptr = { x: -1e4, y: -1e4, on: 0 };
  const waves = [];                            // click waves: { x, y, t0 }
  const small = document.createElement("canvas");
  const sctx = small.getContext("2d", { willReadFrequently: true });

  const hash = (x, y) => { const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return s - Math.floor(s); };
  function noise(x, y) {
    const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  }

  function resize() {
    const r = stage.getBoundingClientRect();
    W = r.width; H = r.height;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    sky.width = Math.round(W * dpr); sky.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cols = Math.ceil(W / PX); rows = Math.ceil(H / PX);
    scols = Math.ceil(W / SP); srows = Math.ceil(H / SP);
    tcols = Math.ceil(W / CELL); trows = Math.ceil(H / CELL);
    small.width = scols; small.height = srows;          // one sample per fine scene pixel
    prev = new Float32Array(scols * srows); heat = new Float32Array(tcols * trows);
    ink = getComputedStyle(stage).getPropertyValue("--sky-ink").trim() || "43, 96, 229";
    solid = getComputedStyle(stage).getPropertyValue("--sky-solid").trim() || "#153893";
    quiet = Array.from(stage.querySelectorAll(".mh__text, .mh__badge, .mh__score")).map((b) => {
      const q = b.getBoundingClientRect();
      return [q.left - r.left, q.top - r.top, q.right - r.left, q.bottom - r.top];
    });
  }
  const quietAt = (x, y) => {
    let q = 1;
    for (const b of quiet) {
      const ex = (x - (b[0] + b[2]) / 2) / ((b[2] - b[0]) / 2 + FADE);
      const ey = (y - (b[1] + b[3]) / 2) / ((b[3] - b[1]) / 2 + FADE);
      q = Math.min(q, smooth(0.85, 1.35, Math.hypot(ex, ey)));
    }
    return q;
  };
  // pink tiles live only in the left half of the card, never behind text; the right half is the scene's
  const tileFree = (i, j) => {
    const l = i * CELL, t = j * CELL, r = l + CELL, b = t + CELL;
    if (r > W / 2) return false;
    return !quiet.some((x) => l < x[2] + 12 && r > x[0] - 12 && t < x[3] + 12 && b > x[1] - 12);
  };
  let lastPick = 0;

  function draw(now) {
    const t = now / 1000;
    ctx.clearRect(0, 0, W, H);
    sky.style.opacity = scene.classList.contains("is-fading") ? "0" : "1";

    // sample the scene at the fine 2px pitch: thin lines, digits and labels survive
    sctx.clearRect(0, 0, scols, srows);
    sctx.imageSmoothingEnabled = true;
    sctx.drawImage(scene, 0, 0, scols, srows);
    const img = sctx.getImageData(0, 0, scols, srows).data;

    // where is the scene changing? that's where tiles flash pink (checked on every other fine pixel — plenty)
    heat.forEach((h, i) => { heat[i] = h * 0.9; });
    const vals = new Float32Array(scols * srows);
    for (let j = 0; j < srows; j++) {
      for (let i = 0; i < scols; i++) {
        const k = j * scols + i, o = k * 4;
        // the scenes draw light strokes over navy: only the light part is ink (navy fills have a dark red channel)
        const v = clamp((img[o + 3] / 255) * smooth(0.12, 0.6, Math.min(img[o], img[o + 1], img[o + 2]) / 255) * 2.2, 0, 1);
        vals[k] = v;
        if (((i | j) & 1) === 0) heat[Math.floor(i * SP / CELL) + Math.floor(j * SP / CELL) * tcols] += Math.abs(v - prev[k]) * 0.012;
      }
    }
    prev = vals;
    let hot = -1, hv = 0;
    for (let j = 0; j < trows; j++) for (let i = 0; i < tcols; i++) {
      const h = heat[j * tcols + i];
      if (h > hv && tileFree(i, j)) { hv = h; hot = j * tcols + i; }
    }
    const hi = Math.floor(ptr.x / CELL), hj = Math.floor(ptr.y / CELL);
    const hoverKey = ptr.on > 0.05 && tileFree(hi, hj) ? `${hi},${hj}` : null;
    if (hot >= 0 && hv > 0.08) {
      const key = `${hot % tcols},${Math.floor(hot / tcols)}`;
      tiles.set(key, Math.max(tiles.get(key) || 0, 0.45));
    } else if (t - lastPick > 3.5) {
      // the scene rarely moves on the left: light a free left tile now and then so the half never stands still
      const free = [];
      for (let j = 0; j < trows; j++) for (let i = 0; i < tcols; i++) if (tileFree(i, j)) free.push(`${i},${j}`);
      if (free.length) tiles.set(free[Math.floor(Math.random() * free.length)], 0.45);
      lastPick = t;
    }
    if (hoverKey) tiles.set(hoverKey, Math.max(tiles.get(hoverKey) || 0, 0.35 * ptr.on));

    // pink tiles first, then pixels over them
    tiles.forEach((a, key) => {
      const na = a * 0.97;
      if (na < 0.01) { tiles.delete(key); return; }
      tiles.set(key, na);
      const [i, j] = key.split(",").map(Number);
      ctx.globalAlpha = na; ctx.fillStyle = PINK; ctx.fillRect(i * CELL, j * CELL, CELL, CELL);
    });
    ctx.globalAlpha = 1;

    // clouds on the coarse 5px grid; the same pass records how quiet each spot must be (text, badges)
    const scenePx = new Path2D(), warm = new Path2D(), cloud = new Path2D();
    const drift = t * 0.035;
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        const x = i * PX, y = j * PX, q = quietAt(x + PX / 2, y + PX / 2);
        if (q <= 0.02) continue;
        const th = BAYER[(j & 3) * 4 + (i & 3)];
        // keep the clouds off the drawing: skip if the scene has ink anywhere in this coarse pixel's centre
        const si = Math.floor((x + PX / 2) / SP), sj = Math.floor((y + PX / 2) / SP);
        if (scene.dataset.cur === "0") continue;                    // mountains fill the sky themselves: no clouds
        if (vals[sj * scols + si] > 0.05) continue;
        const c = smooth(0.5, 0.85, noise(x * 0.0045 + drift, y * 0.009 - drift * 0.3) * 0.7 + noise(x * 0.01, y * 0.02 + drift) * 0.3);
        if (c * q * smooth(W * 0.3, W * 0.6, x) > th + 0.25) cloud.rect(x, y, PX - 1, PX - 1);
      }
    }
    // mountains are filled shapes, not lines: printed solid they became a wall through the text. Instead take the
    // scene's ridge line per column, lower it into the bottom ~45% of the card, print the ridge solid and the body
    // as a pale dither that fades downward, starting after the text column
    // Mountains are already a pixel scene of their own: show the original (recoloured for white by CSS, see
    // .mh.is-raw-scene) and print nothing of it here — the sky only adds its clouds, grid, tiles and waves
    const mountains = scene.dataset.cur === "0";
    stage.classList.toggle("is-raw-scene", mountains);
    // the scene on the fine 2px grid, solid; dithered only at soft edges so digits keep their shape.
    // It is drawn in full — the text sits in front of it (with a soft halo), so big scenes are never cut off
    for (let j = 0; j < (mountains ? 0 : srows); j++) {
      const y = j * SP, tj = Math.floor(y / CELL);
      for (let i = 0; i < scols; i++) {
        const v = vals[j * scols + i];
        if (v < 0.08) continue;
        const x = i * SP;
        if (v <= BAYER[(j & 3) * 4 + (i & 3)] * 0.5) continue;
        const inTile = (tiles.get(`${Math.floor(x / CELL)},${tj}`) || 0) > 0.15;
        (inTile ? warm : scenePx).rect(x, y, SP - 0.4, SP - 0.4);
      }
    }
    // world map: a moving graticule — curved meridians drift sideways like a turning globe, parallels sway gently
    if (scene.dataset.cur === "6") {
      const grat = new Path2D(), step = 120, shiftX = (t * 14) % step;
      for (let m = -1; m * step < W + step; m++) {
        const base = m * step + shiftX;
        for (let y = 0; y < H; y += SP * 3) {
          const bend = Math.sin((y / H) * Math.PI) * (base - W / 2) * 0.08;   // bowed outward, like a projection
          grat.rect(base + bend, y, SP - 0.4, SP - 0.4);
        }
      }
      for (let p = 1; p * step * 0.7 < H; p++) {
        const y0 = p * step * 0.7;
        for (let x = 0; x < W; x += SP * 3) grat.rect(x, y0 + Math.sin(x * 0.004 + t * 0.6 + p) * 6, SP - 0.4, SP - 0.4);
      }
      ctx.fillStyle = `rgba(${ink}, 0.35)`; ctx.fill(grat);
    }

    // click waves: a dithered ring of fine pixels that spreads out and thins away
    for (let w = waves.length - 1; w >= 0; w--) {
      const age = t - waves[w].t0;
      if (age > 1.4) { waves.splice(w, 1); continue; }
      const rad = 12 + age * 340, band = 10 + age * 6, life = 1 - age / 1.4;
      const { x: wx, y: wy } = waves[w];
      const x0 = Math.max(0, Math.floor((wx - rad - band) / SP)), x1 = Math.min(scols - 1, Math.ceil((wx + rad + band) / SP));
      const y0 = Math.max(0, Math.floor((wy - rad - band) / SP)), y1 = Math.min(srows - 1, Math.ceil((wy + rad + band) / SP));
      for (let j = y0; j <= y1; j++) {
        for (let i = x0; i <= x1; i++) {
          const d = Math.abs(Math.hypot(i * SP - wx, j * SP - wy) - rad);
          if (d > band) continue;
          if ((1 - d / band) * life > BAYER[(j & 3) * 4 + (i & 3)]) scenePx.rect(i * SP, j * SP, SP - 0.4, SP - 0.4);
        }
      }
    }
    ctx.fillStyle = `rgba(${ink}, 0.16)`; ctx.fill(cloud);
    // the drawing is the foreground: solid deep blue, while the clouds stay pale
    ctx.fillStyle = solid; ctx.fill(scenePx);
    ctx.fillStyle = ORANGE; ctx.fill(warm);

    // the grid
    ctx.strokeStyle = `rgba(${ink}, 0.12)`; ctx.lineWidth = 1; ctx.beginPath();
    for (let i = 1; i < tcols; i++) { ctx.moveTo(i * CELL + 0.5, 0); ctx.lineTo(i * CELL + 0.5, H); }
    for (let j = 1; j < trows; j++) { ctx.moveTo(0, j * CELL + 0.5); ctx.lineTo(W, j * CELL + 0.5); }
    ctx.stroke();

    // the scene's labels as crisp text, bottom right
    if (scene._hud) {
      const f = Math.max(11, Math.min(14, W / 70));
      ctx.font = `500 ${f}px ${MONO}`; ctx.textAlign = "right"; ctx.textBaseline = "bottom";
      ctx.fillStyle = getComputedStyle(stage).getPropertyValue("--text-2").trim() || "#5b6478";
      scene._hud.slice().reverse().forEach((line, k) => ctx.fillText(line, W - 28, H - 24 - k * f * 1.6));
      ctx.textAlign = "left";
    }
  }

  let lastDraw = 0, visible = true;
  function loop(now) {
    requestAnimationFrame(loop);
    if (!visible || document.hidden || now - lastDraw < FRAME) return;
    lastDraw = now;
    ptr.on += ((ptr.x > -1e3 ? 1 : 0) - ptr.on) * 0.25;
    draw(now);
  }
  stage.addEventListener("pointermove", (e) => { const r = stage.getBoundingClientRect(); ptr.x = e.clientX - r.left; ptr.y = e.clientY - r.top; });
  stage.addEventListener("pointerleave", () => { ptr.x = ptr.y = -1e4; });
  // every click on the sky (not on the button or links) sends a wave
  stage.addEventListener("click", (e) => {
    if (e.target.closest("a, button, input, select, label")) return;
    const r = stage.getBoundingClientRect();
    waves.push({ x: e.clientX - r.left, y: e.clientY - r.top, t0: performance.now() / 1000 });
    if (waves.length > 5) waves.shift();
  });
  new ResizeObserver(() => { resize(); if (reduce) draw(performance.now()); }).observe(stage);
  new IntersectionObserver((e) => { visible = e[0].isIntersecting; }).observe(stage);
  resize();
  if (reduce) { [100, 600, 1500].forEach((ms) => setTimeout(() => draw(performance.now()), ms)); }
  else requestAnimationFrame(loop);
})();

/* Monday — Monday test hero: a mosaic of small geometric tiles.
 *
 * The tiles (squares, circles, quarter-circles, triangles in three tones) float loosely, then snap
 * to a 14×14 grid and assemble the picture of the day. The cursor works as a lens (tiles grow and
 * brighten), a click scatters them and assembles the next picture. A few loose tiles keep drifting
 * around, so the field never looks frozen. With "reduce motion" the picture is drawn at once.
 *
 * Tile map characters:
 *   X x -   squares (strong / mid / soft)        O o c   circles (strong / mid / soft)
 *   q p b d quarter-circles rounding the TL / TR / BL / BR corner (strong), Q P B D — mid tone
 *   y u n m right triangles filling the BL / BR / TL / TR corner (strong), Y U N M — mid tone
 *   t       triangle pointing up (mid)           .       empty
 */
(function () {
  "use strict";

  const PICS = {
    rocket: [
      "......qp......", ".....qXXp.....", ".....X--X.....", ".....XccX.....", ".....X--X.....",
      ".....XxxX.....", ".....XxxX.....", "....yXxxXu....", "...yxXxxXxu...", "...xxXXXXxx...",
      "....d.oo.b....", "......oo......", "......cc......", ".......c......",
    ],
    mountain: [
      ".......Xxxm...", ".......Xxx....", ".......X......", "......yXu.....", ".....y-X-u....",
      "....y--X--u...", "...yXXXXXXXu..", "..yXxXXXXxXXu.", ".yXxxXXXXxxXXu", "yxxxXXXXXxxxXX",
      "XxxXXXXXXXXxxX", "..............", "c.c.c.c.c.c.c.", "..............",
    ],
    bulb: [
      "c............c", "....QxxxxP....", "...Q-c--c-P...", "..Q--------P..", "..x--o--o--x..",
      "..x---oo---x..", "..B---oo---D..", "...B--oo--D...", "....B-oo-D....", ".....XXXX.....",
      ".....xxxx.....", ".....XXXX.....", "......bd......", "c............c",
    ],
    stopwatch: [
      "......XX......", "......xx......", "....qXXXXp....", "...qx----xp...", "..qx---X--xp..",
      "..x----X---x..", "..x----X---x..", "..x----Oxx-x..", "..x--------x..", "..bx------xd..",
      "...bx----xd...", "....bXXXXd....", "..............", "..c.o.O.o.c...",
    ],
    target: [
      "....qXXXXp....", "...XxxxxxxX...", "..Xx------xX..", ".Xx-QxxxxP-xX.", ".Xx-x----x-xX.",
      ".Xx-x-OO-x-xX.", ".Xx-x-OO-x-xX.", ".Xx-x----x-xX.", ".Xx-BxxxxD-xX.", "..Xx------xX..",
      "...XxxxxxxX...", "....bXXXXd....", "..............", "..............",
    ],
    pi: [
      "..............", "..............", "..qXXXXXXXXXX.", ".qXXXXXXXXXXd.", ".d..xx...xx...",
      "....xx...xx...", "....xx...xx...", "....xx...xx...", "....xx...xx...", "....xx...xx...",
      "...Qxx...xxP..", "..QxD....Bxxc.", "..............", "..c.c.c.c.c.c.",
    ],
    crown: [
      "..............", ".O....O....O..", ".t....t....t..", ".X...yXu...X..", ".Xu.yXXXu.yX..",
      ".XXyXXXXXuXX..", ".XXXXXXXXXXX..", ".X-o-X-o-X-X..", ".XXXXXXXXXXX..", ".xxxxxxxxxxx..",
      "..............", "..c.c.c.c.c...", "..............", "..............",
    ],
  };
  const ORDER = ["rocket", "mountain", "bulb", "stopwatch", "target", "pi", "crown"];
  const N = 14;

  const canvas = document.querySelector("[data-mosaic]");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const greet = document.querySelector("[data-mosaic-greet]");
  const lines = JSON.parse((document.querySelector("[data-mosaic-lines]") || {}).textContent || "{}");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const TAU = Math.PI * 2;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  const rnd = (a, b) => a + Math.random() * (b - a);

  const css = getComputedStyle(canvas);
  const TONES = [css.getPropertyValue("--mosaic-1").trim() || "#ffffff",
                 css.getPropertyValue("--mosaic-2").trim() || "#7f9bff",
                 css.getPropertyValue("--mosaic-3").trim() || "#3b4fb8"];
  const toneOf = (ch) => ("XOqpbdyunm".includes(ch) ? 0 : "xoQPBDYUNMt".includes(ch) ? 1 : 2);

  let W = 0, H = 0, dpr = 1, S = 12, ox = 0, oy = 0;
  let pic = canvas.dataset.picture in PICS ? canvas.dataset.picture : ORDER[0];
  let tiles = [], drift = [];
  const pointer = { x: -999, y: -999, on: 0 };

  function resize() {
    const r = canvas.getBoundingClientRect();
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = r.width; H = r.height;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    S = Math.floor(Math.min(W, H) / (N + 1.5));
    ox = (W - S * N) / 2; oy = (H - S * N) / 2;
  }

  function build(name, from) {
    const now = performance.now();
    const grid = PICS[name];
    const old = from || [];
    const next = [];
    grid.forEach((row, r) => [...row].forEach((ch, c) => {
      if (ch === ".") return;
      const prev = old.length ? old[(next.length * 7) % old.length] : null;
      const dist = Math.hypot(c - N / 2, r - N / 2);
      next.push({
        ch, r, c, tone: toneOf(ch),
        sx: prev ? prev.x : rnd(-0.1, 1.1) * W, sy: prev ? prev.y : rnd(-0.1, 1.1) * H,
        sr: prev ? prev.rot : rnd(-Math.PI, Math.PI), ss: prev ? prev.scale : rnd(0.3, 0.7),
        at: now + (reduce ? -9999 : 200 + dist * 70 + rnd(0, 380)), dur: 900 + rnd(0, 500),
        x: 0, y: 0, rot: 0, scale: 1, phase: rnd(0, TAU),
      });
    }));
    tiles = next;
    if (greet && lines[name]) greet.textContent = lines[name];
  }

  function scatter() {
    // the current tiles fly out a little and become the start of the next picture
    const out = tiles.map((t) => ({ x: t.x + rnd(-60, 60), y: t.y + rnd(-60, 60), rot: rnd(-2, 2), scale: 0.5 }));
    pic = ORDER[(ORDER.indexOf(pic) + 1) % ORDER.length];
    build(pic, out);
  }

  function seedDrift() {
    drift = Array.from({ length: Math.round(clamp(W * H / 9000, 10, 26)) }, () => ({
      x: rnd(0, W), y: rnd(0, H), vx: rnd(-6, 6), vy: rnd(-10, -3), rot: rnd(0, TAU), vr: rnd(-0.4, 0.4),
      ch: "xocQtD-"[Math.floor(rnd(0, 7))], a: rnd(0.12, 0.3), s: rnd(0.35, 0.6),
    }));
  }

  function shape(ch, x, y, s, rot) {
    const k = ch.toLowerCase(), h = s / 2;
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot); ctx.beginPath();
    if (k === "x" || ch === "-") {
      const r = s * 0.12; ctx.roundRect ? ctx.roundRect(-h, -h, s, s, r) : ctx.rect(-h, -h, s, s);
    } else if (k === "o" || ch === "c") {
      ctx.arc(0, 0, h, 0, TAU);
    } else if ("qpbd".includes(k)) {
      const [cx, cy, a0] = { q: [h, h, Math.PI], p: [-h, h, 1.5 * Math.PI], b: [h, -h, 0.5 * Math.PI], d: [-h, -h, 0] }[k];
      ctx.moveTo(cx, cy); ctx.arc(cx, cy, s, a0, a0 + Math.PI / 2); ctx.closePath();
    } else if ("yunm".includes(k)) {
      const p = { y: [[-h, -h], [-h, h], [h, h]], u: [[h, -h], [h, h], [-h, h]], n: [[-h, -h], [h, -h], [-h, h]], m: [[-h, -h], [h, -h], [h, h]] }[k];
      ctx.moveTo(...p[0]); ctx.lineTo(...p[1]); ctx.lineTo(...p[2]); ctx.closePath();
    } else if (k === "t") {
      ctx.moveTo(0, -h); ctx.lineTo(h, h); ctx.lineTo(-h, h); ctx.closePath();
    }
    ctx.fill(); ctx.restore();
  }

  function frame(now) {
    ctx.clearRect(0, 0, W, H);
    pointer.on += ((pointer.x > -900 ? 1 : 0) - pointer.on) * 0.1;
    // loose tiles in the background
    for (const d of drift) {
      if (!reduce) { d.x += d.vx / 60; d.y += d.vy / 60; d.rot += d.vr / 60; }
      if (d.y < -20) { d.y = H + 20; d.x = rnd(0, W); }
      if (d.x < -20) d.x = W + 20; if (d.x > W + 20) d.x = -20;
      ctx.globalAlpha = d.a; ctx.fillStyle = TONES[2];
      shape(d.ch, d.x, d.y, S * d.s, d.rot);
    }
    const g = S * 0.66;   // small tiles with visible gaps, like grout
    for (const t of tiles) {
      const p = ease(clamp((now - t.at) / t.dur, 0, 1));
      const tx = ox + t.c * S + S / 2, ty = oy + t.r * S + S / 2;
      const breathe = reduce ? 0 : Math.sin(now / 900 + t.phase) * 0.04 * p;
      t.x = t.sx + (tx - t.sx) * p; t.y = t.sy + (ty - t.sy) * p;
      t.rot = t.sr * (1 - p); t.scale = t.ss + (1 - t.ss) * p + breathe;
      const lens = pointer.on * Math.max(0, 1 - Math.hypot(t.x - pointer.x, t.y - pointer.y) / (S * 3.2));
      ctx.globalAlpha = 0.35 + 0.65 * p;
      ctx.fillStyle = lens > 0.35 && t.tone > 0 ? TONES[t.tone - 1] : TONES[t.tone];
      shape(t.ch, t.x, t.y - lens * 3, g * (t.scale + lens * 0.28), t.rot);
    }
    ctx.globalAlpha = 1;
    if (!reduce) requestAnimationFrame(frame);
  }

  resize(); seedDrift(); build(pic);
  window.addEventListener("resize", () => { resize(); seedDrift(); });
  canvas.addEventListener("pointermove", (e) => { const r = canvas.getBoundingClientRect(); pointer.x = e.clientX - r.left; pointer.y = e.clientY - r.top; });
  canvas.addEventListener("pointerleave", () => { pointer.x = pointer.y = -999; });
  canvas.addEventListener("click", () => { if (!reduce) scatter(); else { pic = ORDER[(ORDER.indexOf(pic) + 1) % ORDER.length]; build(pic); frame(performance.now()); } });
  requestAnimationFrame(frame);
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
    if (left === 0) { setTimeout(() => location.reload(), 1500); return; }
    setTimeout(tick, 1000 - (Date.now() % 1000));
  };
  tick();
})();

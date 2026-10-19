/* Monday — Home hero: a small orbit of maths turns between the countdown and the stats, over the
 * same halftone dots as the login page. The dots react to the cursor (blue swirl); on the
 * first visit after signing in the items fly in from outside, so login → home reads as one move.
 */
(function () {
  "use strict";
  const hero = document.querySelector("[data-hero]");
  if (!hero) return;
  const canvas = hero.querySelector("[data-hero-dots]");
  const orbit = hero.querySelector("[data-hero-orbit]");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ctx = canvas.getContext("2d");
  const TAU = Math.PI * 2;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };

  let W = 0, H = 0, dpr = 1, ox = 0, oy = 0, rx = 200, ry = 70, textBoxes = [];
  const S = 12, MAXR = 3.1, LENS = 90;
  const pointer = { x: 0, y: 0, cx: 0, cy: 0, presence: 0, inside: false };

  if (orbit && window.renderMathInElement) {
    window.renderMathInElement(orbit, { delimiters: [{ left: "$", right: "$", display: false }], throwOnError: false });
  }
  const items = Array.from(orbit ? orbit.children : []).map((el, i, all) => ({
    el, phase: (i / all.length) * TAU, w: 0, h: 0, spin: 0.4 + Math.random() * 0.5, tilt: Math.random() * TAU,
  }));

  let arrive = false;
  try {
    arrive = !sessionStorage.getItem("monday-arrived");
    sessionStorage.setItem("monday-arrived", "1");
  } catch (_) { arrive = false; }
  const t0 = performance.now() / 1000;

  function resize() {
    const r = hero.getBoundingClientRect();
    W = r.width; H = r.height;
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // the orbit lives in the free space between the countdown (left) and the stats (right)
    // text areas the dots should stay quiet under (old and new hero layouts)
    const quiet = hero.querySelectorAll(".home-hero__count, .home-ring, .home-strip");
    const blocks = quiet.length ? Array.from(quiet) : Array.from(hero.children).filter((el) => !el.matches("canvas, [data-hero-orbit]"));
    const left = blocks[0] ? blocks[0].getBoundingClientRect() : null;
    const right = blocks[1] ? blocks[1].getBoundingClientRect() : null;
    textBoxes = blocks.map((b) => { const q = b.getBoundingClientRect(); return [q.left - r.left, q.top - r.top, q.right - r.left, q.bottom - r.top]; });
    const gapL = left ? left.right - r.left : W * 0.35, gapR = right && right.left - r.left > gapL + 80 ? right.left - r.left : W * 0.75;
    ox = (gapL + gapR) / 2;
    oy = H * 0.5;
    rx = clamp((gapR - gapL) * 0.36, 90, 220);
    ry = clamp(H * 0.36, 50, 110);
    items.forEach((it) => { it.w = it.el.offsetWidth; it.h = it.el.offsetHeight; });
  }

  function dots(t) {
    ctx.clearRect(0, 0, W, H);
    const cols = Math.ceil(W / S), rows = Math.ceil(H / S);
    const base = new Path2D();
    const lit = [];
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        let x = (i + 0.5) * S, y = (j + 0.5) * S;
        // strongest around the orbit, quiet under the text so it stays readable
        const gx = (x - ox) / (rx * 1.9), gy = (y - oy) / (H * 0.9);
        let f = Math.exp(-(gx * gx + gy * gy)) * (0.6 + 0.25 * Math.sin(x * 0.02 + y * 0.015 - t * 1.1));
        for (const b of textBoxes) {
          if (x > b[0] - 16 && x < b[2] + 16 && y > b[1] - 16 && y < b[3] + 16) { f *= 0.25; break; }
        }
        let hl = 0;
        if (pointer.presence > 0.01) {
          const dx = x - pointer.cx, dy = y - pointer.cy;
          const lens = Math.exp(-(dx * dx + dy * dy) / (2 * LENS * LENS)) * pointer.presence;
          if (lens > 0.02) {
            const a = lens * (0.7 + 0.3 * Math.sin(t * 2.4 - Math.hypot(dx, dy) * 0.05));
            const ca = Math.cos(a), sa = Math.sin(a);
            x = pointer.cx + (dx * ca - dy * sa) * (1 + lens * 0.15);
            y = pointer.cy + (dx * sa + dy * ca) * (1 + lens * 0.15);
            f = Math.max(f, 0) + lens * 0.8;
            hl = lens;
          }
        }
        const r = clamp(f, 0, 1) * MAXR;
        if (r < 0.35) continue;
        if (hl > 0.05) lit.push(x, y, r, hl);
        else { base.moveTo(x + r, y); base.arc(x, y, r, 0, TAU); }
      }
    }
    ctx.fillStyle = "rgba(255, 255, 255, 0.16)";
    ctx.fill(base);
    for (let k = 0; k < lit.length; k += 4) {
      ctx.fillStyle = `rgba(187, 207, 244, ${(0.2 + lit[k + 3] * 0.75).toFixed(3)})`;
      ctx.beginPath(); ctx.arc(lit[k], lit[k + 1], lit[k + 2], 0, TAU); ctx.fill();
    }
  }

  function orbitStep(t) {
    const since = t - t0;
    items.forEach((it, i) => {
      const th = it.phase + t * 0.22;
      const depth = Math.sin(th);                       // -1 at the back of the ring … 1 at the front
      let x = ox + Math.cos(th) * rx, y = oy + depth * ry * 0.55 - Math.cos(th) * ry * 0.35;
      let s = 0.78 + 0.3 * (depth + 1) / 2;
      let a = 0.45 + 0.55 * (depth + 1) / 2;
      if (arrive) {                                     // fly in from outside on the first visit
        const p = smooth(0, 1, (since - i * 0.08) / 1.3);
        const out = 1 - p;
        x += (x - ox) * out * 2.2;
        y += (y - oy) * out * 2.2 - out * 40;
        s *= 1 + out * 1.6;
        a *= p;
      }
      it.el.style.transform = `translate3d(${x - it.w / 2}px, ${y - it.h / 2}px, 0) scale(${s.toFixed(3)}) perspective(500px) rotateY(${(Math.sin(t * it.spin + it.tilt) * 28).toFixed(1)}deg)`;
      it.el.style.opacity = a.toFixed(3);
      it.el.style.zIndex = depth > 0 ? "3" : "1";
    });
  }

  function frame(ms) {
    const t = ms / 1000;
    pointer.cx += (pointer.x - pointer.cx) * 0.2;
    pointer.cy += (pointer.y - pointer.cy) * 0.2;
    pointer.presence += ((pointer.inside ? 1 : 0) - pointer.presence) * 0.08;
    dots(t);
    orbitStep(t);
    if (!reduce) requestAnimationFrame(frame);
  }

  hero.addEventListener("pointermove", (e) => {
    const r = hero.getBoundingClientRect();
    pointer.x = e.clientX - r.left; pointer.y = e.clientY - r.top;
    if (!pointer.inside) { pointer.cx = pointer.x; pointer.cy = pointer.y; }
    pointer.inside = true;
  });
  hero.addEventListener("pointerleave", () => { pointer.inside = false; });
  window.addEventListener("resize", resize);
  resize();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(resize);
  requestAnimationFrame(frame);
})();

/* Session bar: a field of halftone dots in the Monday blues around the wordmark (as on the sign-in page).
 * Two arcs sweep out from behind the word; a slow wave runs along them, the dots swell and fade; the cursor
 * pushes a soft bulge. Pauses in a hidden tab; static with reduced motion. */
(() => {
  const canvas = document.querySelector("[data-bar-dots]");
  if (!canvas) return;
  const bar = canvas.parentElement;
  const ctx = canvas.getContext("2d");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const BLUES = [[127, 163, 243], [66, 117, 233], [43, 96, 229], [36, 86, 217], [21, 56, 147]];
  let W = 0, H = 0, dpr = 1, dots = [], ptr = { x: -1e4, y: -1e4 };

  const build = () => {
    const r = bar.getBoundingClientRect();
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = r.width; H = r.height;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    dots = [];
    const word = bar.querySelector(".session-bar__brand");
    const wr = word && getComputedStyle(word).display !== "none" ? word.getBoundingClientRect() : null;
    const clear = wr ? { l: wr.left - r.left - 14, r: wr.right - r.left + 14, t: -10, b: wr.bottom - r.top + 6 } : null;
    const free = (x, y) => !clear || x < clear.l || x > clear.r || y < clear.t || y > clear.b;
    const cx = W / 2, cy = H * 2.2;           // arcs of big circles whose tops pass through the bar
    for (const side of [-1, 1]) {
      for (let ring = 0; ring < 4; ring++) {
        const R = H * 1.9 + ring * 9;
        for (let k = 0; k < 26; k++) {
          const a = (Math.PI / 2) + side * (0.14 + k * 0.035);   // from the word outwards
          const x = cx + Math.cos(a) * R * (2.4 + ring * 0.08);
          const y = cy - Math.sin(a) * R;
          if (x < 0 || x > W || y < -4 || y > H + 4 || !free(x, y)) continue;
          dots.push({ x, y, k, ring, side, c: BLUES[Math.min(4, ring + (k > 14 ? 1 : 0))] });
        }
      }
    }
    for (let n = 0; n < Math.round(W / 9); n++) {          // faint scatter across the bar
      const x = Math.random() * W, y = Math.random() * H;
      if (free(x, y)) dots.push({ x, y, k: Math.random() * 26, ring: 4, side: 0, c: BLUES[0], faint: true });
    }
  };

  const draw = (t) => {
    ctx.clearRect(0, 0, W, H);
    for (const d of dots) {
      const wave = 0.5 + 0.5 * Math.sin(t / 900 - d.k * 0.45 - d.ring * 0.7);
      const near = Math.max(0, 1 - Math.hypot(d.x - ptr.x, d.y - ptr.y) / 90);
      const fade = d.faint ? 0.18 : Math.max(0.15, 1 - d.k / 26);
      const r = (d.faint ? 0.9 : 1.1 + 2.1 * wave * fade) + near * 2.2;
      ctx.fillStyle = `rgba(${d.c[0]}, ${d.c[1]}, ${d.c[2]}, ${(d.faint ? 0.25 : 0.25 + 0.55 * wave) * fade + near * 0.3})`;
      ctx.beginPath(); ctx.arc(d.x, d.y, r, 0, Math.PI * 2); ctx.fill();
    }
  };

  let raf = 0;
  const loop = (t) => { draw(t); raf = requestAnimationFrame(loop); };
  const start = () => { if (!raf && !reduce && !document.hidden) raf = requestAnimationFrame(loop); };
  const stop = () => { cancelAnimationFrame(raf); raf = 0; };

  build();
  draw(0);
  start();
  new ResizeObserver(() => { build(); draw(performance.now()); }).observe(bar);
  document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
  bar.addEventListener("pointermove", (e) => { const r = bar.getBoundingClientRect(); ptr = { x: e.clientX - r.left, y: e.clientY - r.top }; });
  bar.addEventListener("pointerleave", () => { ptr = { x: -1e4, y: -1e4 }; });
})();

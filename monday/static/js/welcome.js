/* Monday — login page.
 *
 * 1. Spiral: maths items (formulas, symbols, shapes) ride a three-armed helix whose axis
 *    points at the viewer. Like planets in a solar system that is itself travelling, each
 *    item orbits the axis, spins on its own axis and moves towards you along the axis
 *    vector; when it passes the camera it re-enters far away.
 * 2. Sky: the Home "bitmap sky" — drifting clouds dithered into square blue pixels over a thin
 *    grid. The cursor works as a lens (the sky fills in and deepens) and a click sends a ripple
 *    and prints the next letter of MONDAY in the same pixels, shaded with the wordmark gradient.
 * Everything stays on its grid / its orbit, so the motion reads as one system.
 */
(function () {
  "use strict";

  const stage = document.querySelector(".auth__stage");
  const canvas = document.querySelector("[data-dots]");
  const spiralEl = document.querySelector("[data-spiral]");
  const source = document.querySelector("template[data-spiral-items]");
  if (!stage || !canvas || !spiralEl || !source) return;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ctx = canvas.getContext("2d");
  const TAU = Math.PI * 2;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };

  let W = 0, H = 0, dpr = 1, K = 1;   // K scales the spiral to the stage size
  const pointer = { x: -9999, y: -9999, cx: -9999, cy: -9999, nx: 0, ny: 0, sx: 0, sy: 0, inside: false, presence: 0 };
  const ripples = [];
  let boost = 0;            // click "warp": the spiral speeds up for a moment
  let center = { x: 0, y: 0 };

  /* ------------------------------------------------------------------ spiral items */

  const ARMS = 3;
  const Z_FAR = -1500, Z_NEAR = 430, F = 820;        // depth range and focal length
  const SPEED = 58;                                  // units per second towards the viewer
  const TWIST = 0.0034;                              // radians of orbit per unit of depth
  const ORBIT = 0.16;                                // whole system rotation, rad/s

  const templates = Array.from(source.content.children);
  const items = [];
  const COUNT = Math.max(36, templates.length);
  for (let i = 0; i < COUNT; i++) {
    const src = templates[i % templates.length];
    const el = document.createElement("div");
    const kinds = (src.dataset.k || "f").split(" ");
    el.className = `sp-item sp-${kinds[0]} ${kinds.slice(1).join(" ")}`;
    el.innerHTML = src.innerHTML;
    spiralEl.appendChild(el);
    const arm = i % ARMS;
    items.push({
      el, kind: kinds[0],
      z: Z_FAR + ((i * 0.6180339) % 1) * (Z_NEAR - Z_FAR),   // golden-ratio spacing: no clumps
      phase: arm * (TAU / ARMS) + (Math.random() - 0.5) * 0.5,
      radius: 200 + Math.random() * 110,
      spin: (Math.random() < 0.5 ? -1 : 1) * (0.25 + Math.random() * 0.5),
      tilt: Math.random() * TAU,
      w: 0, h: 0,
    });
  }
  if (window.renderMathInElement) {
    window.renderMathInElement(spiralEl, {
      delimiters: [{ left: "$", right: "$", display: false }], throwOnError: false,
    });
  }
  const measure = () => items.forEach((it) => { it.w = it.el.offsetWidth; it.h = it.el.offsetHeight; });

  let axisX = 0.16, axisY = -0.06;
  function updateAxis(t) {
    // the axis drifts slowly (the "solar system" travelling) and leans with the pointer
    axisX = 0.16 + pointer.sx * 0.12 + Math.sin(t * 0.11) * 0.05;
    axisY = -0.06 + pointer.sy * 0.10 + Math.cos(t * 0.09) * 0.04;
  }

  /* The three arms drawn as fine dotted trails — the orbits the items ride on. */
  function drawArms(t) {
    for (let arm = 0; arm < ARMS; arm++) {
      const phase = arm * (TAU / ARMS);
      for (let z = Z_FAR; z < Z_NEAR; z += 26) {
        const theta = phase + z * TWIST + t * ORBIT;
        const s = F / (F - z);
        const x = center.x + (Math.cos(theta) * 255 + z * axisX) * s * K;
        const y = center.y + (Math.sin(theta) * 255 * 0.82 + z * axisY) * s * K;
        const a = smooth(Z_FAR, Z_FAR + 700, z) * (1 - smooth(Z_NEAR - 260, Z_NEAR, z));
        if (a < 0.02) continue;
        const side = Math.round(2 + s * 2);     // square pixels, like the sky
        ctx.fillStyle = `rgba(43, 96, 229, ${(a * 0.4).toFixed(3)})`;
        ctx.fillRect(Math.round(x - side / 2), Math.round(y - side / 2), side, side);
      }
    }
  }

  function drawSpiral(t, dt) {
    const speed = SPEED * (1 + boost * 5);
    for (const it of items) {
      it.z += speed * dt;
      if (it.z > Z_NEAR) { it.z = Z_FAR + (it.z - Z_NEAR); it.radius = 200 + Math.random() * 110; }
      const theta = it.phase + it.z * TWIST + t * ORBIT;
      const x3 = Math.cos(theta) * it.radius + it.z * axisX;
      const y3 = Math.sin(theta) * it.radius * 0.82 + it.z * axisY;
      const s = F / (F - it.z);
      const px = center.x + x3 * s * K;
      const py = center.y + y3 * s * K;
      const fadeIn = smooth(Z_FAR + 160, Z_FAR + 760, it.z);
      const fadeOut = 1 - smooth(Z_NEAR - 220, Z_NEAR, it.z);
      const alpha = fadeIn * fadeOut;
      // own axis: shapes and bubbles turn fully, formulas only sway so they stay readable
      const own = it.kind === "s" || it.kind === "q"
        ? `rotateY(${(t * it.spin * 70 + it.tilt * 57) % 360}deg) rotate(${Math.sin(t * 0.7 + it.tilt) * 12}deg)`
        : `rotateY(${Math.sin(t * it.spin + it.tilt) * 32}deg) rotate(${Math.sin(t * 0.5 + it.tilt) * 8}deg)`;
      it.el.style.transform =
        `translate3d(${px - it.w / 2}px, ${py - it.h / 2}px, 0) scale(${(s * 0.7 * Math.sqrt(K)).toFixed(3)}) perspective(600px) ${own}`;
      it.el.style.opacity = alpha.toFixed(3);
      it.el.style.zIndex = String(Math.round(it.z + 2000));
    }
  }

  /* ------------------------------------------------------------------ bitmap sky (the Home style) */

  const PX = 5;                 // one bitmap pixel, as on Home
  const CELL = 150;             // grid tile, as on Home
  const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map((v) => (v + 0.5) / 16);
  const INK = "43, 96, 229";
  // colours the letters, ripples and the cursor take: the wordmark gradient, light → dark
  const STOPS = [[127, 163, 243], [66, 117, 233], [43, 96, 229], [36, 86, 217], [21, 56, 147], [2, 11, 41]];
  const SHADES = 12;            // the gradient is drawn in this many steps (one path each)
  const grad = (p) => {
    const x = clamp(p, 0, 1) * (STOPS.length - 1);
    const i = Math.min(STOPS.length - 2, Math.floor(x)), f = x - i, a = STOPS[i], b = STOPS[i + 1];
    return `rgb(${Math.round(a[0] + (b[0] - a[0]) * f)}, ${Math.round(a[1] + (b[1] - a[1]) * f)}, ${Math.round(a[2] + (b[2] - a[2]) * f)})`;
  };
  const SHADE = Array.from({ length: SHADES }, (_, n) => grad(n / (SHADES - 1)));
  let shift = 0;                // each click moves the colours one step deeper

  const hash = (x, y) => { const v = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return v - Math.floor(v); };
  function noise(x, y) {
    const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  }
  const fbm = (x, y) => noise(x, y) * 0.55 + noise(x * 2.1, y * 2.1) * 0.3 + noise(x * 4.3, y * 4.3) * 0.15;

  /* Letters: each click gathers the pixels into the next letter of MONDAY, then the whole word,
     then releases them. The change runs out from the click as a wave, and inside the letter the
     pixels switch on in dither order, so the letter prints itself onto the sky. */
  const WORD = ["M", "O", "N", "D", "A", "Y", "MONDAY"];
  let step = -1;                               // -1 = free sky
  let letterT = new Float32Array(0);           // target: 1 inside the letter
  let letterM = new Float32Array(0);           // current value, eases towards target
  let letterAt = new Float32Array(0);          // time each pixel starts changing (staggered wave)
  let letterBox = { top: 0, bottom: 1, cx: 0, cy: 0 };
  let active = 0;                              // eased "a letter is showing"
  const wordmark = document.querySelectorAll("[data-wordmark] span");

  function buildMask(text, at) {
    const off = document.createElement("canvas");
    off.width = Math.max(1, Math.round(W)); off.height = Math.max(1, Math.round(H));
    const c = off.getContext("2d");
    const single = text.length === 1;
    // the letter forms where you click (the sky stays around it)
    const size = single ? Math.round(Math.min(H * 0.34, W * 0.36)) : Math.round(Math.min(W * 0.2, H * 0.21));
    const halfW = single ? size * 0.45 : size * 1.05, halfH = single ? size * 0.5 : size * 1.1;
    const p = at || letterBox.at || { x: W * 0.55, y: H * 0.5 };
    const cx = clamp(p.x, halfW + 16, W - halfW - 16), cy = clamp(p.y, halfH + 16, H - halfH - 16);
    c.textAlign = "center"; c.textBaseline = "middle";
    c.fillStyle = "#000";
    c.font = `800 ${size}px Unbounded, sans-serif`;
    if (single) c.fillText(text, cx, cy);
    else {                                     // the whole word on two lines: MON / DAY
      c.fillText(text.slice(0, 3), cx, cy - size * 0.56);
      c.fillText(text.slice(3), cx, cy + size * 0.56);
    }
    const data = c.getImageData(0, 0, off.width, off.height).data;
    const target = new Float32Array(cols * rows);
    let top = H, bottom = 0;
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        const x = Math.round((i + 0.5) * PX), y = Math.round((j + 0.5) * PX);
        if (x >= off.width || y >= off.height) continue;
        if (data[(y * off.width + x) * 4 + 3] > 110) {
          target[j * cols + i] = 1;
          top = Math.min(top, y); bottom = Math.max(bottom, y);
        }
      }
    }
    letterBox = { top, bottom: Math.max(bottom, top + 1), cx, cy, at: { x: cx, y: cy } };
    return target;
  }

  function setStep(next, from) {
    step = next;
    const now = performance.now() / 1000;
    const target = step >= 0 ? buildMask(WORD[step], from) : new Float32Array(cols * rows);
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        const k = j * cols + i;
        const d = from ? Math.hypot((i + 0.5) * PX - from.x, (j + 0.5) * PX - from.y) : 0;
        letterAt[k] = now + d / 1100;          // the change travels out from the click
        letterT[k] = target[k];
      }
    }
    wordmark.forEach((el, n) => el.classList.toggle("is-lit", step >= 0 && (step === 6 || n <= step)));
  }

  function resetLetterArrays() {
    letterT = new Float32Array(cols * rows);
    letterM = new Float32Array(cols * rows);
    letterAt = new Float32Array(cols * rows);
    if (step >= 0) {
      const target = buildMask(WORD[step]);
      letterT = target; letterM = Float32Array.from(target);
    }
  }
  const LENS = 110;             // cursor lens radius (px)
  let cols = 0, rows = 0;

  function resize() {
    const r = stage.getBoundingClientRect();
    W = r.width; H = r.height;
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = false;
    cols = Math.ceil(W / PX);
    rows = Math.ceil(H / PX);
    K = clamp(Math.min(W / 860, H / 820), 0.42, 1.25);
    resetLetterArrays();
    measure();
  }

  function drawDots(t) {
    ctx.clearRect(0, 0, W, H);
    const now = t;
    for (let k = ripples.length - 1; k >= 0; k--) if (now - ripples[k].t0 > 2.2) ripples.splice(k, 1);
    active += ((step >= 0 ? 1 : 0) - active) * 0.06;
    const span = letterBox.bottom - letterBox.top;
    const drift = t * 0.035;
    const sky = new Path2D(), grain = new Path2D();
    const shades = Array.from({ length: SHADES }, () => new Path2D());
    const lens = pointer.presence > 0.01, L2 = 2 * LENS * LENS;
    for (let j = 0; j < rows; j++) {
      const y = j * PX, cyy = y + PX / 2;
      for (let i = 0; i < cols; i++) {
        const x = i * PX, cx = x + PX / 2;
        const k = j * cols + i;
        if (now >= letterAt[k]) letterM[k] += (letterT[k] - letterM[k]) * 0.11;
        const m = letterM[k];
        // drifting clouds, as on Home; quieter under the wordmark and next to the card, and while a letter shows
        let d = smooth(0.38, 0.78, fbm(x * 0.0045 + drift, y * 0.009 - drift * 0.3));
        let q = 1 - smooth(W - 170, W, x) * 0.75;
        q *= 1 - (1 - smooth(380, 520, x)) * smooth(H - 230, H - 140, y) * 0.9;
        d *= q * (1 - active * 0.45);
        let hl = 0, shade = 0;                 // hl: how strongly this pixel takes the gradient
        if (m > 0.01) {
          d = d * (1 - m) + 1.02 * m;
          if (letterT[k] > 0.5 || m > 0.3) { hl = m; shade = 0.08 + clamp((cyy - letterBox.top) / span, 0, 1) * 0.85; }
        }
        if (lens) {                            // cursor: a lens that fills in and deepens the sky
          const dx = cx - pointer.cx, dy = cyy - pointer.cy;
          const g = Math.exp(-(dx * dx + dy * dy) / L2) * pointer.presence;
          if (g > 0.02) {
            d += g * 0.55;
            if (g > hl) { hl = g; shade = shift + g * 0.5; }
          }
        }
        for (const r of ripples) {             // a click sends a wave whose trail runs through the gradient
          const age = now - r.t0;
          const behind = age * 480 - Math.hypot(cx - r.x, cyy - r.y);
          const shape = behind < 0 ? Math.exp(-(behind * behind) / (2 * 22 * 22)) : Math.max(0, 1 - behind / 260);
          const band = shape * (1 - age / 2.2);
          if (band > 0.01) {
            d += band * 0.6;
            if (band > hl) { hl = band; shade = r.shift + Math.max(0, behind) / 260 * 0.75; }
          }
        }
        if (d > BAYER[(j & 3) * 4 + (i & 3)]) {
          if (hl > 0.25) shades[Math.round(clamp(shade, 0, 1) * (SHADES - 1))].rect(x, y, PX - 1, PX - 1);
          else sky.rect(x, y, PX - 1, PX - 1);
        } else if (i % 3 === 0 && j % 3 === 0 && q > 0.6) grain.rect(x + 1, y + 1, 2, 2);   // sparse sky grain
      }
    }
    ctx.fillStyle = `rgba(${INK}, 0.06)`; ctx.fill(grain);
    ctx.fillStyle = `rgba(${INK}, 0.26)`; ctx.fill(sky);
    shades.forEach((path, n) => { ctx.fillStyle = SHADE[n]; ctx.fill(path); });
    // the grid
    ctx.strokeStyle = `rgba(${INK}, 0.09)`; ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = CELL; x < W; x += CELL) { ctx.moveTo(Math.round(x) + 0.5, 0); ctx.lineTo(Math.round(x) + 0.5, H); }
    for (let y = CELL; y < H; y += CELL) { ctx.moveTo(0, Math.round(y) + 0.5); ctx.lineTo(W, Math.round(y) + 0.5); }
    ctx.stroke();
  }

  /* ------------------------------------------------------------------ loop & input */

  let last = performance.now(), painted = -1e9;
  function frame(nowMs) {
    const t = nowMs / 1000;
    const dt = Math.min(0.05, (nowMs - last) / 1000);
    last = nowMs;
    pointer.sx += (pointer.nx - pointer.sx) * 0.05;     // eased parallax
    pointer.sy += (pointer.ny - pointer.sy) * 0.05;
    boost *= 0.94;
    // the lens trails the cursor slightly and fades in / out at the stage edges
    if (pointer.cx < -9000) { pointer.cx = pointer.x; pointer.cy = pointer.y; }
    pointer.cx += (pointer.x - pointer.cx) * 0.18;
    pointer.cy += (pointer.y - pointer.cy) * 0.18;
    pointer.presence += ((pointer.inside ? 1 : 0) - pointer.presence) * 0.08;
    center = {
      x: W * 0.5 - pointer.sx * 28 + Math.sin(t * 0.13) * 14,
      y: H * 0.46 - pointer.sy * 22 + Math.cos(t * 0.1) * 10,
    };
    updateAxis(t);
    if (nowMs - painted >= 32 || reduceMotion) {   // the sky at ~30 frames a second: it moves slowly, and costs half
      painted = nowMs;
      drawDots(t);
      drawArms(t);
    }
    spiralEl.style.opacity = (1 - active * 0.35).toFixed(3);
    drawSpiral(t, dt);
    if (!reduceMotion) requestAnimationFrame(frame);
  }

  stage.addEventListener("pointermove", (e) => {
    const r = stage.getBoundingClientRect();
    pointer.x = e.clientX - r.left;
    pointer.y = e.clientY - r.top;
    pointer.nx = (pointer.x / r.width) * 2 - 1;
    pointer.ny = (pointer.y / r.height) * 2 - 1;
    pointer.inside = true;
    if (reduceMotion) frame(performance.now());
  });
  stage.addEventListener("pointerleave", () => { pointer.inside = false; pointer.nx = 0; pointer.ny = 0; });
  stage.addEventListener("pointerdown", (e) => {
    const r = stage.getBoundingClientRect();
    const at = { x: e.clientX - r.left, y: e.clientY - r.top };
    shift = (shift + 0.125) % 0.5;
    ripples.push({ ...at, t0: performance.now() / 1000, shift });
    const next = step + 1 >= WORD.length ? -1 : step + 1;   // M → O → N → D → A → Y → MONDAY → free
    if (document.fonts && document.fonts.load) {
      document.fonts.load("800 200px Unbounded").then(() => setStep(next, at), () => setStep(next, at));
    } else setStep(next, at);
    boost = 1;
    if (reduceMotion) frame(performance.now());
  });

  window.addEventListener("resize", resize);
  resize();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(measure);
  window.addEventListener("load", measure);
  requestAnimationFrame(frame);

  /* ------------------------------------------------------------------ form helpers */

  document.querySelectorAll("[data-pass-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = btn.parentElement.querySelector("input");
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? btn.dataset.hide : btn.dataset.show;
    });
  });

  const reg = document.querySelector("[data-register]");
  if (reg) {
    const sync = () => {
      const teacher = (reg.querySelector("input[name=role]:checked") || {}).value === "teacher";
      reg.querySelectorAll("[data-student-only]").forEach((el) => (el.hidden = teacher));
      reg.querySelectorAll("[data-teacher-only]").forEach((el) => (el.hidden = !teacher));
    };
    reg.addEventListener("change", sync);
    sync();
  }

  document.querySelectorAll("[data-demo]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const email = document.getElementById("email"), pass = document.getElementById("password");
      if (email && pass) { email.value = btn.dataset.demo; pass.value = btn.dataset.pass; pass.focus(); }
    });
  });
})();

/* Monday — login page.
 *
 * 1. Spiral: maths items (formulas, symbols, shapes) ride a three-armed helix whose axis
 *    points at the viewer. Like planets in a solar system that is itself travelling, each
 *    item orbits the axis, spins on its own axis and moves towards you along the axis
 *    vector; when it passes the camera it re-enters far away.
 * 2. Dots: an ordered halftone grid (sizes grow towards the bottom-right). A slow diagonal
 *    wave and a ring wave from the spiral's centre run through it; the cursor works as a
 *    lens (dots grow, tint blue and part slightly) and a click sends a ripple.
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
        ctx.fillStyle = `rgba(31, 79, 224, ${(a * 0.35).toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(x, y, 0.9 + s * 1.1, 0, TAU);
        ctx.fill();
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

  /* ------------------------------------------------------------------ halftone dots */

  const S = 12;                 // grid step (denser grid, smaller dots)
  const MAXR = S * 0.3;         // biggest dot radius
  // colours the dots can take: each click switches to the next one (ripple + cursor lens)
  // gradient stops sampled from the reference image, light → dark
  const STOPS = [[187, 207, 244], [127, 163, 243], [66, 117, 233], [43, 96, 229], [36, 86, 217], [21, 56, 147], [2, 11, 41]];
  const GREY = [214, 217, 224];
  const grad = (p) => {                       // colour at position p (0 = light, 1 = dark)
    const x = clamp(p, 0, 1) * (STOPS.length - 1);
    const i = Math.min(STOPS.length - 2, Math.floor(x)), f = x - i, a = STOPS[i], b = STOPS[i + 1];
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
  };
  let shift = 0;                              // each click moves the whole effect one step deeper

  /* Letters: each click gathers the dots into the next letter of MONDAY, then the whole word,
     then releases them. Every dot keeps its grid slot; it only grows, takes the gradient and
     flies in from slightly further out, so the letter "assembles" from the field. */
  const WORD = ["M", "O", "N", "D", "A", "Y", "MONDAY"];
  let step = -1;                               // -1 = free field
  let letterT = new Float32Array(0);           // target: 1 inside the letter
  let letterM = new Float32Array(0);           // current value, eases towards target
  let letterAt = new Float32Array(0);          // time each dot starts moving (staggered wave)
  let letterBox = { top: 0, bottom: 1, cx: 0, cy: 0 };
  let active = 0;                              // eased "a letter is showing"
  const wordmark = document.querySelectorAll("[data-wordmark] span");

  function buildMask(text, at) {
    const off = document.createElement("canvas");
    off.width = Math.max(1, Math.round(W)); off.height = Math.max(1, Math.round(H));
    const c = off.getContext("2d");
    const single = text.length === 1;
    // the letter forms where you click, as a part of the field (the other dots stay around it)
    const size = single ? Math.round(Math.min(H * 0.34, W * 0.36)) : Math.round(Math.min(W * 0.2, H * 0.21));
    const halfW = single ? size * 0.45 : size * 1.05, halfH = single ? size * 0.5 : size * 1.1;
    const p = at || letterBox.at || { x: W * 0.55, y: H * 0.5 };
    const cx = clamp(p.x, halfW + 16, W - halfW - 16), cy = clamp(p.y, halfH + 16, H - halfH - 16);
    c.textAlign = "center"; c.textBaseline = "middle";
    c.fillStyle = "#000";
    if (single) {
      c.font = `800 ${size}px Unbounded, sans-serif`;
      c.fillText(text, cx, cy);
    } else {                                   // the whole word on two lines: MON / DAY
      c.font = `800 ${size}px Unbounded, sans-serif`;
      c.fillText(text.slice(0, 3), cx, cy - size * 0.56);
      c.fillText(text.slice(3), cx, cy + size * 0.56);
    }
    const data = c.getImageData(0, 0, off.width, off.height).data;
    const target = new Float32Array(cols * rows);
    let top = H, bottom = 0;
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        const x = Math.round((i + 0.5) * S), y = Math.round((j + 0.5) * S);
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
        const d = from ? Math.hypot((i + 0.5) * S - from.x, (j + 0.5) * S - from.y) : 0;
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
  const LENS = 120;             // cursor lens radius (px)
  let cols = 0, rows = 0;

  function resize() {
    const r = stage.getBoundingClientRect();
    W = r.width; H = r.height;
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cols = Math.ceil(W / S) + 1;
    rows = Math.ceil(H / S) + 1;
    K = clamp(Math.min(W / 860, H / 820), 0.42, 1.25);
    resetLetterArrays();
    measure();
  }

  function drawDots(t) {
    ctx.clearRect(0, 0, W, H);
    const now = t;
    for (let k = ripples.length - 1; k >= 0; k--) if (now - ripples[k].t0 > 2.2) ripples.splice(k, 1);

    const grey = new Path2D();
    const accents = [];
    active += ((step >= 0 ? 1 : 0) - active) * 0.06;
    const span = letterBox.bottom - letterBox.top;
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        let x = (i + 0.5) * S, y = (j + 0.5) * S;
        const k = j * cols + i;
        if (now >= letterAt[k]) letterM[k] += (letterT[k] - letterM[k]) * 0.13;
        const m = letterM[k];
        const u = x / W, v = y / H;
        // base field: empty top-left, large bottom-right, softened at the bottom edge
        let f = smooth(0.36, 1.18, u * 0.5 + v * 0.85);
        f *= 1 - smooth(0.9, 1.02, v) * 0.55;
        f *= 1 - smooth(W - 160, W, x) * 0.8;   // soften the edge next to the card
        // slow diagonal wave
        f += 0.08 * Math.sin(x * 0.011 + y * 0.007 - t * 1.05);
        // ring wave from the spiral's centre — ties the two systems together
        const dc = Math.hypot(x - center.x, y - center.y);
        f += 0.09 * Math.sin(dc * 0.028 - t * 1.7) * (1 - smooth(120, 620, dc)) * smooth(30, 140, dc);
        // keep the wordmark area calm (before the cursor effects, so the cursor still works there)
        f *= 1 - smooth(0, 1, (1 - smooth(380, 520, x)) * smooth(H - 230, H - 140, y)) * 0.85;
        // letters: the rest of the field steps back, letter dots gather in and take the gradient
        let letterCol = null;
        if (m > 0.01) {
          if (letterT[k] > 0.5) {               // arriving: fly in from a little further out
            const spread = (1 - m) * 0.5;
            x = letterBox.cx + (x - letterBox.cx) * (1 + spread);
            y = letterBox.cy + (y - letterBox.cy) * (1 + spread);
          }
          f = f * (1 - m) + 1.05 * m;
          letterCol = grad(0.08 + clamp((y - letterBox.top) / span, 0, 1) * 0.85);
        }
        // cursor: dots inside the lens turn blue, grow and swirl around the cursor.
        // Each dot is rotated about the (eased) cursor by an angle that is largest at the centre,
        // so the grid twists into a small vortex and relaxes back into order as you move away.
        let hl = 0, col = GREY;
        if (letterCol) { hl = m; col = letterCol; }
        if (pointer.presence > 0.01) {
          const dx = x - pointer.cx, dy = y - pointer.cy;
          const d2 = dx * dx + dy * dy;
          const lens = Math.exp(-d2 / (2 * LENS * LENS)) * pointer.presence;
          if (lens > 0.01) {
            const d = Math.sqrt(d2) || 1;
            const a = lens * (0.75 + 0.25 * Math.sin(t * 2.4 - d * 0.045));   // swirl angle
            const ca = Math.cos(a), sa = Math.sin(a);
            const push = 1 + lens * 0.18;                                      // open a little room
            x = pointer.cx + (dx * ca - dy * sa) * push;
            y = pointer.cy + (dx * sa + dy * ca) * push;
            f = Math.max(f, 0) + lens * 0.7;
            if (lens > hl) { hl = lens; col = grad(shift + lens * 0.5); }   // light at the lens edge, deep in the centre
          }
        }
        for (const r of ripples) {
          const age = now - r.t0;
          const d = Math.hypot(x - r.x, y - r.y);
          // a wave whose trail runs through the gradient: light at the front, deep behind it
          const behind = age * 480 - d;                       // distance behind the wave front
          const shape = behind < 0 ? Math.exp(-(behind * behind) / (2 * 22 * 22)) : Math.max(0, 1 - behind / 260);
          const band = shape * (1 - age / 2.2);
          if (band > 0.01) {
            f += band * 0.7;
            if (band > hl) { hl = band; col = grad(r.shift + Math.max(0, behind) / 260 * 0.75); }
          }
        }
        const rad = clamp(f, 0, 1) * MAXR;
        if (rad < 0.4) continue;
        if (hl > 0.06) accents.push(x, y, rad, Math.min(1, hl * 1.15), col);
        else { grey.moveTo(x + rad, y); grey.arc(x, y, rad, 0, TAU); }
      }
    }
    ctx.fillStyle = "#D6D9E0";
    ctx.fill(grey);
    for (let k = 0; k < accents.length; k += 5) {
      const hl = accents[k + 3], c = accents[k + 4];
      // grey → the current colour
      ctx.fillStyle = `rgb(${Math.round(GREY[0] + (c[0] - GREY[0]) * hl)}, ${Math.round(GREY[1] + (c[1] - GREY[1]) * hl)}, ${Math.round(GREY[2] + (c[2] - GREY[2]) * hl)})`;
      ctx.beginPath();
      ctx.arc(accents[k], accents[k + 1], accents[k + 2], 0, TAU);
      ctx.fill();
    }
  }

  /* ------------------------------------------------------------------ loop & input */

  let last = performance.now();
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
    drawDots(t);
    drawArms(t);
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

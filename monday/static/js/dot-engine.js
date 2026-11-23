/* Monday Academy — Living Dot Engine (Stage 2)
 * Single 2D canvas module: ambient field -> MONDAY wordmark -> score curve -> interactive curve + KaTeX equation -> idle.
 * External vanilla JS only, strict CSP, DPR<=2, IntersectionObserver & visibility pause, reduced-motion & saveData safe.
 */
(function () {
  "use strict";

  function safeSessionGet(key) {
    try {
      return window.sessionStorage ? window.sessionStorage.getItem(key) : null;
    } catch (_) {
      return null;
    }
  }

  function safeSessionSet(key, val) {
    try {
      if (window.sessionStorage) window.sessionStorage.setItem(key, val);
    } catch (_) {}
  }

  function shouldSkipIntro() {
    const rm = Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    const docRm = document.documentElement.getAttribute("data-motion") === "reduce";
    const saveData = Boolean(navigator.connection && navigator.connection.saveData);
    const lowCpu = typeof navigator.hardwareConcurrency === "number" && navigator.hardwareConcurrency <= 2;
    const alreadySeen = safeSessionGet("monday_intro_seen") === "1";
    return {
      skip: rm || docRm || saveData || lowCpu || alreadySeen,
      staticOnly: rm || docRm || saveData,
    };
  }

  // Fallback vector stroke coordinates for "M O N D A Y" in normalized [-0.44..0.44] x [-0.12..0.12]
  function buildFallbackWordPoints(count) {
    const strokes = [
      // M
      [-0.42, 0.10, -0.42, -0.10], [-0.42, -0.10, -0.36, 0.04], [-0.36, 0.04, -0.30, -0.10], [-0.30, -0.10, -0.30, 0.10],
      // O
      [-0.23, -0.10, -0.15, -0.10], [-0.15, -0.10, -0.15, 0.10], [-0.15, 0.10, -0.23, 0.10], [-0.23, 0.10, -0.23, -0.10],
      // N
      [-0.09, 0.10, -0.09, -0.10], [-0.09, -0.10, -0.01, 0.10], [-0.01, 0.10, -0.01, -0.10],
      // D
      [0.05, -0.10, 0.05, 0.10], [0.05, -0.10, 0.13, -0.06], [0.13, -0.06, 0.13, 0.06], [0.13, 0.06, 0.05, 0.10],
      // A
      [0.18, 0.10, 0.23, -0.10], [0.23, -0.10, 0.28, 0.10], [0.195, 0.02, 0.265, 0.02],
      // Y
      [0.33, -0.10, 0.38, 0.0], [0.43, -0.10, 0.38, 0.0], [0.38, 0.0, 0.38, 0.10],
    ];
    const pts = [];
    for (let i = 0; i < count; i++) {
      const seg = strokes[i % strokes.length];
      const t = ((i / strokes.length) % 1 + (i % 7) * 0.13) % 1;
      pts.push([
        seg[0] + (seg[2] - seg[0]) * t,
        seg[1] + (seg[3] - seg[1]) * t,
      ]);
    }
    return pts;
  }

  function sampleCanvasWordPoints(word, maxPts) {
    try {
      const off = document.createElement("canvas");
      const w = 360;
      const h = 96;
      off.width = w;
      off.height = h;
      const c = off.getContext("2d");
      if (!c) return buildFallbackWordPoints(maxPts);
      c.clearRect(0, 0, w, h);
      c.fillStyle = "#000";
      c.textAlign = "center";
      c.textBaseline = "middle";
      c.font = '800 54px "Unbounded", "Onest", sans-serif';
      c.fillText(word || "MONDAY", w / 2, h / 2);
      const data = c.getImageData(0, 0, w, h).data;
      const raw = [];
      for (let y = 4; y < h - 4; y += 3) {
        for (let x = 6; x < w - 6; x += 3) {
          if (data[(y * w + x) * 4 + 3] > 120) {
            raw.push([(x / w - 0.5) * 0.88, (y / h - 0.5) * 0.32]);
          }
        }
      }
      if (raw.length < 40) return buildFallbackWordPoints(maxPts);
      return raw;
    } catch (_) {
      return buildFallbackWordPoints(maxPts);
    }
  }

  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const easeOutQuart = (t) => 1 - Math.pow(1 - clamp(t, 0, 1), 4);

  document.querySelectorAll("[data-dot-stage]").forEach((stage) => {
    const canvas = stage.querySelector("[data-dot-canvas]");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const eqEl = stage.querySelector("[data-curve-eq]");
    const sliderEl = stage.querySelector("[data-curve-slider]");
    const skipBtn = stage.querySelector("[data-skip-intro]");
    const wordText = stage.getAttribute("data-dot-word") || "MONDAY";

    const policy = shouldSkipIntro();
    let introSkipped = policy.skip;
    let staticMode = policy.staticOnly;
    if (introSkipped && skipBtn) {
      skipBtn.hidden = true;
    }

    let W = 0;
    let H = 0;
    let dpr = 1;
    let N = 0;
    let spineCount = 0;

    // Typed buffers
    let ax = new Float32Array(0);
    let ay = new Float32Array(0);
    let wx = new Float32Array(0);
    let wy = new Float32Array(0);
    let rad = new Float32Array(0);
    let phase = new Float32Array(0);

    // Curve coefficients y = a*x^2 + b*x + c
    let coefA = 0.4;
    let coefB = -0.3;
    let coefC = 1.5;
    let targetA = 0.4;
    let targetB = -0.3;
    let targetC = 1.5;
    let lastEqKey = "";
    let lastEqTime = 0;

    // Feedback pulse state ("ok" | "warn" | "")
    let pulseKind = "";
    let pulseUntil = 0;

    // Frame performance ring buffer
    const frameTimes = [];
    let lastFrameTs = 0;
    let startTs = 0;
    let rafId = 0;
    let isIntersecting = true;
    let isTabVisible = !document.hidden;

    function formatSigned(val) {
      const sign = val >= 0 ? "+" : "−";
      return sign + " " + Math.abs(val).toFixed(1);
    }

    function updateEquationReadout(nowMs) {
      if (!eqEl) return;
      const qa = Math.round(coefA * 10) / 10;
      const qb = Math.round(coefB * 10) / 10;
      const qc = Math.round(coefC * 10) / 10;
      const key = `${qa.toFixed(1)}|${qb.toFixed(1)}|${qc.toFixed(1)}`;
      if (key === lastEqKey || nowMs - lastEqTime < 55) return;
      lastEqKey = key;
      lastEqTime = nowMs;

      const latex = `y = ${qa.toFixed(1)}x^2 ${formatSigned(qb)}x ${formatSigned(qc)}`;
      if (window.katex && typeof window.katex.render === "function") {
        try {
          window.katex.render(latex, eqEl, { throwOnError: false });
          return;
        } catch (_) {}
      }
      eqEl.textContent = `y = ${qa.toFixed(1)}x² ${formatSigned(qb)}x ${formatSigned(qc)}`;
    }

    function allocatePoints() {
      const rect = canvas.getBoundingClientRect();
      W = Math.max(260, Math.round(rect.width || 520));
      H = Math.max(200, Math.round(rect.height || 300));
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      N = W >= 1024 ? 680 : W >= 600 ? 440 : 280;
      spineCount = Math.floor(N * 0.65);

      ax = new Float32Array(N);
      ay = new Float32Array(N);
      wx = new Float32Array(N);
      wy = new Float32Array(N);
      rad = new Float32Array(N);
      phase = new Float32Array(N);

      const wordPts = sampleCanvasWordPoints(wordText, spineCount);
      for (let i = 0; i < N; i++) {
        // Deterministic pseudo-random ambient grid distribution
        const u = ((i * 73) % 997) / 997;
        const v = ((i * 199 + 41) % 991) / 991;
        ax[i] = (0.06 + u * 0.88) * W;
        ay[i] = (0.08 + v * 0.84) * H;
        phase[i] = (i * 0.6180339) % (Math.PI * 2);

        if (i < spineCount) {
          const wp = wordPts[i % wordPts.length];
          wx[i] = W * (0.5 + wp[0]);
          wy[i] = H * (0.48 + wp[1]);
          rad[i] = 2.5 + (i % 3) * 0.55;
        } else {
          wx[i] = ax[i];
          wy[i] = ay[i];
          rad[i] = 1.6 + (i % 2) * 0.5;
        }
      }
      updateEquationReadout(performance.now());
    }

    function curveYAt(normX, a, b, c) {
      // normX in [-1, 1] -> domain x in [-1.8, 1.8]
      const x = normX * 1.8;
      const val = a * x * x + b * x + c; // typical range [0.2 .. 4.5]
      const ny = 0.78 - (val - 0.3) * 0.155;
      return clamp(ny, 0.12, 0.88) * H;
    }

    function renderFrame(ts) {
      if (!startTs) startTs = ts;
      if (lastFrameTs) {
        const dt = ts - lastFrameTs;
        if (dt > 0 && dt < 200) {
          frameTimes.push(dt);
          if (frameTimes.length > 90) frameTimes.shift();
        }
      }
      lastFrameTs = ts;

      const elapsed = introSkipped ? 3.0 : (ts - startTs) / 1000;
      if (!introSkipped && elapsed >= 2.5) {
        introSkipped = true;
        safeSessionSet("monday_intro_seen", "1");
        if (skipBtn) skipBtn.hidden = true;
      }

      coefA += (targetA - coefA) * 0.14;
      coefB += (targetB - coefB) * 0.14;
      coefC += (targetC - coefC) * 0.14;
      updateEquationReadout(ts);

      ctx.clearRect(0, 0, W, H);
      const isDark = document.documentElement.getAttribute("data-theme") === "dark";

      // Subtle coordinate axes in curve phase
      const curvePhaseAlpha = introSkipped ? 1 : clamp((elapsed - 1.2) / 0.8, 0, 1);
      if (curvePhaseAlpha > 0.05) {
        ctx.strokeStyle = isDark ? `rgba(148, 163, 184, ${0.18 * curvePhaseAlpha})` : `rgba(31, 79, 224, ${0.14 * curvePhaseAlpha})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(W * 0.08, H * 0.78);
        ctx.lineTo(W * 0.92, H * 0.78);
        ctx.moveTo(W * 0.5, H * 0.12);
        ctx.lineTo(W * 0.5, H * 0.88);
        ctx.stroke();
      }

      const pulseActive = ts < pulseUntil;
      let primaryFill = isDark ? "#5B8CFF" : "#1F4FE0";
      if (pulseActive && pulseKind === "ok") {
        primaryFill = "#1E8E5A";
      } else if (pulseActive && pulseKind === "warn") {
        primaryFill = "#D97706";
      }
      const haloFill = isDark ? "rgba(127, 163, 243, 0.32)" : "rgba(127, 163, 243, 0.45)";

      const tWord = easeOutQuart((elapsed - 0.35) / 0.9);
      const tCurve = easeOutQuart((elapsed - 1.3) / 0.95);

      // Batch draw halo dots first, then spine dots
      ctx.fillStyle = haloFill;
      ctx.beginPath();
      for (let i = spineCount; i < N; i++) {
        const driftX = staticMode ? 0 : Math.sin(elapsed * 1.1 + phase[i]) * 3.5;
        const driftY = staticMode ? 0 : Math.cos(elapsed * 0.9 + phase[i]) * 3.5;
        const px = ax[i] + driftX;
        const py = ay[i] + driftY;
        const r = rad[i];
        ctx.moveTo(px + r, py);
        ctx.arc(px, py, r, 0, Math.PI * 2);
      }
      ctx.fill();

      ctx.fillStyle = primaryFill;
      ctx.beginPath();
      for (let i = 0; i < spineCount; i++) {
        const u = i / Math.max(1, spineCount - 1); // [0..1]
        const normX = (u - 0.5) * 2;               // [-1..1]
        const cx = W * (0.08 + u * 0.84);
        const wave = staticMode ? 0 : Math.sin(elapsed * 1.6 + u * 5.2) * 2.2;
        const cy = curveYAt(normX, coefA, coefB, coefC) + wave + ((i % 3) - 1) * 2.2;

        let px = ax[i];
        let py = ay[i];
        if (introSkipped) {
          px = cx;
          py = cy;
        } else if (elapsed < 1.3) {
          px = ax[i] + (wx[i] - ax[i]) * tWord;
          py = ay[i] + (wy[i] - ay[i]) * tWord;
        } else {
          px = wx[i] + (cx - wx[i]) * tCurve;
          py = wy[i] + (cy - wy[i]) * tCurve;
        }

        const r = pulseActive ? rad[i] * 1.25 : rad[i];
        ctx.moveTo(px + r, py);
        ctx.arc(px, py, r, 0, Math.PI * 2);
      }
      ctx.fill();

      if (!staticMode && isIntersecting && isTabVisible) {
        rafId = window.requestAnimationFrame(renderFrame);
      } else {
        rafId = 0;
      }
    }

    function startLoop() {
      if (staticMode) {
        renderFrame(performance.now());
        return;
      }
      if (!rafId && isIntersecting && isTabVisible) {
        lastFrameTs = 0;
        rafId = window.requestAnimationFrame(renderFrame);
      }
    }

    function stopLoop() {
      if (rafId) {
        window.cancelAnimationFrame(rafId);
        rafId = 0;
      }
    }

    function handlePointer(clientX, clientY) {
      const rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const ux = clamp((clientX - rect.left) / rect.width, 0, 1);
      const uy = clamp((clientY - rect.top) / rect.height, 0, 1);
      targetA = clamp(Math.round((-0.5 + (1 - uy) * 1.4) * 10) / 10, -0.6, 1.0);
      targetB = clamp(Math.round(((ux - 0.5) * 2.2) * 10) / 10, -1.2, 1.2);
      targetC = clamp(Math.round((0.8 + (1 - uy) * 1.6) * 10) / 10, 0.6, 2.8);
      if (sliderEl) {
        sliderEl.value = String(targetA);
      }
      if (staticMode) {
        coefA = targetA;
        coefB = targetB;
        coefC = targetC;
        renderFrame(performance.now());
      } else {
        startLoop();
      }
    }

    stage.addEventListener("pointermove", (e) => {
      handlePointer(e.clientX, e.clientY);
    });

    if (sliderEl) {
      sliderEl.addEventListener("input", () => {
        const v = parseFloat(sliderEl.value);
        if (!Number.isNaN(v)) {
          targetA = clamp(Math.round(v * 10) / 10, -0.6, 1.0);
          coefA = targetA;
          renderFrame(performance.now());
        }
      });
    }

    if (skipBtn) {
      skipBtn.addEventListener("click", () => {
        introSkipped = true;
        safeSessionSet("monday_intro_seen", "1");
        skipBtn.hidden = true;
        renderFrame(performance.now());
      });
    }

    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            isIntersecting = entry.isIntersecting;
            if (isIntersecting) startLoop();
            else stopLoop();
          });
        },
        { threshold: 0.02 }
      );
      io.observe(stage);
    }

    document.addEventListener("visibilitychange", () => {
      isTabVisible = !document.hidden;
      if (isTabVisible) startLoop();
      else stopLoop();
    });

    window.addEventListener("resize", () => {
      allocatePoints();
      renderFrame(performance.now());
    });

    // Wait up to 180ms for Unbounded display font before sampling, then allocate & draw immediately
    let initialized = false;
    function initOnce() {
      if (initialized) return;
      initialized = true;
      allocatePoints();
      startLoop();
    }

    if (document.fonts && document.fonts.ready) {
      const timer = window.setTimeout(initOnce, 180);
      document.fonts.ready.then(() => {
        window.clearTimeout(timer);
        initOnce();
      }).catch(initOnce);
    } else {
      initOnce();
    }

    window.__mondayDotEngine = {
      pulseFeedback(kind) {
        pulseKind = kind === "ok" ? "ok" : "warn";
        pulseUntil = performance.now() + 1400;
        renderFrame(performance.now());
        startLoop();
      },
      skipIntro() {
        introSkipped = true;
        safeSessionSet("monday_intro_seen", "1");
        if (skipBtn) skipBtn.hidden = true;
        renderFrame(performance.now());
      },
      getPerfStats() {
        const sorted = frameTimes.slice().sort((a, b) => a - b);
        const p95 = sorted.length ? sorted[Math.floor(sorted.length * 0.95)] : 0;
        const avg = sorted.length ? sorted.reduce((acc, v) => acc + v, 0) / sorted.length : 0;
        return {
          pointCount: N,
          dpr,
          samples: sorted.length,
          avgFrameMs: Math.round(avg * 100) / 100,
          p95FrameMs: Math.round(p95 * 100) / 100,
          isRunning: Boolean(rafId),
          introSkipped,
          staticMode,
        };
      },
    };
  });
})();

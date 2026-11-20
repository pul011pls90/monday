/* Monday — Guided Example Stepper + Programmatic SVG Visual Registry */
(function () {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}, text) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v !== undefined && v !== null) n.setAttribute(k, String(v));
    }
    if (text !== undefined) n.textContent = text;
    return n;
  };

  /* Safe expression evaluator for mathematical functions of x */
  function evalExpr(expr, x) {
    const safe = String(expr || "")
      .replace(/\^/g, "**")
      .replace(/\b(sin|cos|tan|abs|sqrt|exp|log)\b/g, "Math.$1")
      .replace(/\bpi\b/gi, "Math.PI");
    if (!/^[0-9xX+\-*/().,\sMathsincoabqrtlpPI]+$/.test(safe)) return NaN;
    try {
      const fn = new Function("x", `"use strict"; return (${safe});`);
      return fn(x);
    } catch (_) {
      return NaN;
    }
  }

  function niceStep(span, targetTicks = 6) {
    const raw = span / targetTicks;
    const pow = Math.pow(10, Math.floor(Math.log10(raw || 1)));
    const f = raw / pow;
    const step = f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10;
    return step * pow;
  }

  function renderLimitGraph(cfg, focus) {
    const W = 520, H = 320;
    const pad = { l: 46, r: 22, t: 24, b: 36 };
    const pw = W - pad.l - pad.r;
    const ph = H - pad.t - pad.b;

    const [xMin, xMax] = cfg.x_range || [-1.5, 1.5];
    const hole = cfg.hole || { x: 0, y: 2.5, label: "(0; 2,5)" };

    // Sample y values to determine y range cleanly
    const samples = [];
    for (let i = 0; i <= 240; i++) {
      const x = xMin + (xMax - xMin) * (i / 240);
      if (Math.abs(x - hole.x) < 1e-4) continue;
      const y = evalExpr(cfg.function, x);
      if (Number.isFinite(y) && Math.abs(y) < 50) samples.push([x, y]);
    }
    let yMin = Math.min(0, hole.y, ...samples.map((p) => p[1]));
    let yMax = Math.max(hole.y, ...samples.map((p) => p[1]));
    const yPad = Math.max(0.4, (yMax - yMin) * 0.16);
    yMin -= yPad * 0.45;
    yMax += yPad;

    const mapX = (x) => pad.l + ((x - xMin) / (xMax - xMin)) * pw;
    const mapY = (y) => pad.t + (1 - (y - yMin) / (yMax - yMin)) * ph;

    const svg = el("svg", {
      viewBox: `0 0 ${W} ${H}`,
      class: "fx-visual__svg",
      role: "img",
      "aria-label": cfg.aria_label || `График функции ${cfg.function}`,
    });

    // Gridlines & ticks
    const gridG = el("g", { class: "fx-svg-grid" });
    const xStep = niceStep(xMax - xMin, 6);
    for (let gx = Math.ceil(xMin / xStep) * xStep; gx <= xMax + 1e-9; gx += xStep) {
      const px = mapX(gx);
      gridG.appendChild(el("line", { x1: px.toFixed(1), y1: pad.t, x2: px.toFixed(1), y2: H - pad.b }));
      if (Math.abs(gx) > 1e-6) {
        gridG.appendChild(el("text", { x: px.toFixed(1), y: H - pad.b + 16, "text-anchor": "middle", class: "fx-svg-tick" }, gx.toFixed(1).replace(".", ",")));
      }
    }
    const yStep = niceStep(yMax - yMin, 5);
    for (let gy = Math.ceil(yMin / yStep) * yStep; gy <= yMax + 1e-9; gy += yStep) {
      const py = mapY(gy);
      gridG.appendChild(el("line", { x1: pad.l, y1: py.toFixed(1), x2: W - pad.r, y2: py.toFixed(1) }));
      if (Math.abs(gy) > 1e-6) {
        gridG.appendChild(el("text", { x: pad.l - 8, y: (py + 4).toFixed(1), "text-anchor": "end", class: "fx-svg-tick" }, gy.toFixed(1).replace(".", ",")));
      }
    }
    svg.appendChild(gridG);

    // Axes
    const axG = el("g", { class: "fx-svg-axes" });
    const y0 = Math.min(Math.max(mapY(0), pad.t), H - pad.b);
    const x0 = Math.min(Math.max(mapX(0), pad.l), W - pad.r);
    axG.appendChild(el("line", { x1: pad.l, y1: y0.toFixed(1), x2: W - pad.r, y2: y0.toFixed(1) }));
    axG.appendChild(el("line", { x1: x0.toFixed(1), y1: H - pad.b, x2: x0.toFixed(1), y2: pad.t }));
    axG.appendChild(el("text", { x: W - pad.r + 6, y: (y0 + 4).toFixed(1), class: "fx-svg-axis-lbl" }, "x"));
    axG.appendChild(el("text", { x: (x0 + 8).toFixed(1), y: pad.t + 8, class: "fx-svg-axis-lbl" }, "y"));
    axG.appendChild(el("text", { x: (x0 - 8).toFixed(1), y: (y0 + 15).toFixed(1), "text-anchor": "end", class: "fx-svg-tick" }, "0"));
    svg.appendChild(axG);

    // Curve (split around hole)
    const curveClass = focus === "same_curve" ? "fx-svg-curve is-hl" : "fx-svg-curve";
    const leftPts = samples.filter((p) => p[0] < hole.x).map((p) => `${mapX(p[0]).toFixed(1)} ${mapY(p[1]).toFixed(1)}`);
    const rightPts = samples.filter((p) => p[0] > hole.x).map((p) => `${mapX(p[0]).toFixed(1)} ${mapY(p[1]).toFixed(1)}`);
    if (leftPts.length > 1) svg.appendChild(el("path", { d: `M ${leftPts.join(" L ")}`, class: curveClass }));
    if (rightPts.length > 1) svg.appendChild(el("path", { d: `M ${rightPts.join(" L ")}`, class: curveClass }));

    // Guide lines to hole/point
    const hx = mapX(hole.x);
    const hy = mapY(hole.y);
    if (focus === "hole" || focus === "point") {
      svg.appendChild(el("line", { x1: pad.l, y1: hy.toFixed(1), x2: hx.toFixed(1), y2: hy.toFixed(1), class: "fx-svg-guide" }));
    }

    // Hole or filled limit point depending on focus
    if (focus === "hole") {
      svg.appendChild(el("circle", { cx: hx.toFixed(1), cy: hy.toFixed(1), r: 12, class: "fx-svg-halo" }));
    }
    const markerClass = focus === "point" ? "fx-svg-point is-hl" : "fx-svg-hole";
    svg.appendChild(el("circle", { cx: hx.toFixed(1), cy: hy.toFixed(1), r: 5.5, class: markerClass }));
    if (hole.label) {
      svg.appendChild(el("text", { x: (hx + 14).toFixed(1), y: (hy - 8).toFixed(1), class: "fx-svg-label" }, hole.label));
    }
    return svg;
  }

  /* Registry prepared for future visual types */
  const VISUAL_RENDERERS = {
    limit_graph: renderLimitGraph,
    unit_circle: null,
    right_triangle: null,
    wave_graph: null,
    area_graph: null,
    tangent_line: null,
  };

  function drawVisual(host, focus) {
    if (!host) return;
    let cfg = null;
    try { cfg = JSON.parse(host.dataset.visualJson || "null"); } catch (_) { return; }
    if (!cfg || !VISUAL_RENDERERS[cfg.type]) return;
    host.innerHTML = "";
    host.appendChild(VISUAL_RENDERERS[cfg.type](cfg, focus || "none"));
  }

  function initStepper(root) {
    const steps = Array.from(root.querySelectorAll("[data-step-idx]"));
    if (!steps.length) return;
    const prevBtn = root.querySelector("[data-step-prev]");
    const nextBtn = root.querySelector("[data-step-next]");
    const allBtn = root.querySelector("[data-step-all]");
    const counter = root.querySelector("[data-step-counter]");
    const visualHost = root.querySelector("[data-visual-inline]") || root.querySelector("[data-visual-json]");
    const zoomBtn = root.querySelector("[data-visual-zoom]");

    let cur = 0;
    let showAll = false;

    const update = () => {
      steps.forEach((st, idx) => {
        if (showAll) {
          st.hidden = false;
          st.classList.toggle("is-active", idx === cur);
          st.classList.remove("is-past");
        } else {
          st.hidden = idx !== cur;
          st.classList.toggle("is-active", idx === cur);
          st.classList.remove("is-past");
        }
      });
      if (counter) counter.textContent = `Шаг ${cur + 1} из ${steps.length}`;
      if (prevBtn) prevBtn.disabled = cur <= 0;
      if (nextBtn) nextBtn.disabled = cur >= steps.length - 1;
      if (allBtn) {
        allBtn.setAttribute("aria-pressed", String(showAll));
        allBtn.textContent = showAll ? "По шагам" : "Показать всё";
      }
      const focus = steps[cur] ? steps[cur].dataset.visualFocus : "none";
      if (visualHost && visualHost.dataset.visualJson) {
        drawVisual(visualHost, showAll ? "none" : focus);
      }
      const inlineSvg = visualHost && visualHost.querySelector("svg");
      if (inlineSvg) {
        if (showAll || !focus || focus === "none") inlineSvg.removeAttribute("data-focus");
        else inlineSvg.setAttribute("data-focus", focus);
      }
    };

    if (prevBtn) prevBtn.addEventListener("click", () => { if (cur > 0) { cur -= 1; update(); } });
    if (nextBtn) nextBtn.addEventListener("click", () => { if (cur < steps.length - 1) { cur += 1; update(); } });
    if (allBtn) allBtn.addEventListener("click", () => { showAll = !showAll; update(); });

    root.addEventListener("keydown", (e) => {
      if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
      if (e.key === "ArrowLeft" && cur > 0) { e.preventDefault(); cur -= 1; update(); }
      if (e.key === "ArrowRight" && cur < steps.length - 1) { e.preventDefault(); cur += 1; update(); }
    });

    const openZoom = () => {
      const svg = visualHost && visualHost.querySelector("svg");
      const lb = document.getElementById("lightbox");
      if (!svg || !lb) return;
      const clone = svg.cloneNode(true);
      clone.setAttribute("xmlns", NS);
      const origNodes = [svg, ...svg.querySelectorAll("*")];
      const cloneNodes = [clone, ...clone.querySelectorAll("*")];
      origNodes.forEach((src, idx) => {
        const cs = getComputedStyle(src);
        const dst = cloneNodes[idx];
        if (!dst) return;
        ["stroke", "stroke-width", "stroke-dasharray", "fill", "font-family", "font-size", "font-weight"].forEach((prop) => {
          const val = cs.getPropertyValue(prop);
          if (val && val !== "none" && prop !== "fill") dst.style[prop] = val;
          else if (prop === "fill") dst.style.fill = val || "none";
        });
      });
      clone.style.background = getComputedStyle(visualHost).backgroundColor || "#FFFFFF";
      const encoded = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(clone.outerHTML);
      const img = lb.querySelector("[data-lb-img]") || lb.querySelector("img");
      if (img) {
        img.src = encoded;
        img.alt = svg.getAttribute("aria-label") || "Рисунок";
        lb.classList.add("is-open");
        document.body.classList.add("is-lightbox-open");
      }
    };
    if (zoomBtn) zoomBtn.addEventListener("click", openZoom);
    if (visualHost) visualHost.addEventListener("click", openZoom);

    update();
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-fx-stepper]").forEach(initStepper);
  });
})();

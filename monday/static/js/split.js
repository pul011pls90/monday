/* Drag the divider between the questions and the answer sheet (bank booklet, ORT test). The width is remembered
   per page type; double click puts it back. Keyboard: ← → move it. Only where the two panels sit side by side. */
(() => {
  const MIN_MAIN = 420, STEP = 24;
  const wide = window.matchMedia("(min-width: 1240px)");
  document.querySelectorAll("[data-split]").forEach((layout) => {
    const main = layout.querySelector(":scope > .ort-main");
    const side = main && main.nextElementSibling;
    if (!side) return;
    const key = `monday.split.${layout.dataset.split}`;
    const minSide = layout.dataset.split === "test" ? 340 : 240;  // the test's sheet keeps its two columns of bubbles
    const read = () => { try { return parseInt(localStorage.getItem(key), 10) || 0; } catch (e) { return 0; } };
    const save = (v) => { try { v ? localStorage.setItem(key, v) : localStorage.removeItem(key); } catch (e) { /* private mode */ } };

    const handle = document.createElement("div");
    handle.className = "split-handle";
    handle.tabIndex = 0;
    handle.setAttribute("role", "separator");
    handle.setAttribute("aria-orientation", "vertical");
    handle.setAttribute("aria-label", layout.dataset.splitLabel || "");
    handle.title = layout.dataset.splitLabel || "";
    handle.innerHTML = "<span></span>";
    layout.appendChild(handle);

    const clamp = (v) => Math.max(minSide, Math.min(v, layout.clientWidth - MIN_MAIN));
    const place = (width) => {
      layout.style.setProperty("--split-side", `${width}px`);
      handle.setAttribute("aria-valuenow", String(Math.round(width)));
    };
    const apply = (width) => {
      const v = clamp(width);
      layout.style.gridTemplateColumns = `minmax(0, 1fr) ${v}px`;
      place(v);
      return v;
    };
    const fit = () => layout.style.setProperty("--split-height", `${main.offsetHeight}px`);  // beside the questions, not the page buttons
    const refresh = () => {
      layout.style.gridTemplateColumns = "";
      if (!wide.matches) return;
      const stored = read();
      if (stored) apply(stored);
      else place(side.getBoundingClientRect().width);
    };

    let drag = null;
    handle.addEventListener("pointerdown", (e) => {
      if (e.button) return;
      e.preventDefault();
      drag = { x: e.clientX, width: side.getBoundingClientRect().width };
      handle.setPointerCapture(e.pointerId);
      document.body.classList.add("is-splitting");
    });
    handle.addEventListener("pointermove", (e) => {
      if (drag) apply(drag.width - (e.clientX - drag.x));
    });
    const stop = () => {
      if (!drag) return;
      drag = null;
      document.body.classList.remove("is-splitting");
      save(Math.round(side.getBoundingClientRect().width));
    };
    handle.addEventListener("pointerup", stop);
    handle.addEventListener("pointercancel", stop);
    handle.addEventListener("dblclick", () => { save(0); refresh(); });
    handle.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      e.stopPropagation();  // the booklet turns pages with these keys
      save(apply(side.getBoundingClientRect().width + (e.key === "ArrowLeft" ? STEP : -STEP)));
    });

    wide.addEventListener("change", refresh);
    window.addEventListener("resize", refresh);
    if (window.ResizeObserver) new ResizeObserver(fit).observe(main);
    refresh();
    fit();
  });
})();

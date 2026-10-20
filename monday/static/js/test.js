/* Monday — test player and question-bank player.
 * grid  (SAT, CSCA, ЕНТ, ЕГЭ, ОГЭ): one question per screen, number grid to jump anywhere,
 *       "mark for review", eliminate options, review screen before handing in.
 * pages (ОРТ): several questions per page, Назад / Вперёд, bubble answer sheet below.
 * Shared: eliminate options, formula-sheet drawer (right), Desmos pane (left, resizable).
 * Without JavaScript every question is simply shown on one page.
 */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const store = (() => { try { return window.localStorage; } catch (_) { return null; } })();
  const read = (k, d) => { try { const v = store && store.getItem(k); return v === null || v === undefined ? d : JSON.parse(v); } catch (_) { return d; } };
  const write = (k, v) => { try { store && store.setItem(k, JSON.stringify(v)); } catch (_) {} };

  /* ------------------------------------------------------------ eliminate options */
  // Each [data-elim-scope] remembers its crossed options under its own key.
  $$("[data-elim-scope]").forEach((scope) => {
    const key = `monday-elim-${scope.dataset.elimKey}`;
    const crossed = read(key, {});
    const apply = () => $$(".option-row", scope).forEach((row) => row.classList.toggle("is-crossed", !!crossed[row.dataset.optionRowKey]));
    $$("[data-elim-toggle]", scope).forEach((b) => b.addEventListener("click", () => {
      const host = b.closest("[data-elim-host]") || scope;
      const on = !host.classList.contains("is-eliminating");
      host.classList.toggle("is-eliminating", on);
      b.setAttribute("aria-pressed", String(on));
    }));
    scope.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-strike]");
      if (!btn) return;
      const row = btn.closest(".option-row");
      const k = row.dataset.optionRowKey;
      crossed[k] = !crossed[k];
      if (!crossed[k]) delete crossed[k];
      btn.setAttribute("aria-pressed", String(!!crossed[k]));
      const input = $("input", row);
      if (crossed[k] && input && input.checked) {            // a crossed option can't stay chosen
        input.checked = false;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
      write(key, crossed);
      apply();
    });
    // choosing a crossed option un-crosses it
    scope.addEventListener("change", (e) => {
      const row = e.target.closest && e.target.closest(".option-row");
      if (row && e.target.checked && crossed[row.dataset.optionRowKey]) { delete crossed[row.dataset.optionRowKey]; write(key, crossed); apply(); }
    });
    apply();
  });

  /* ------------------------------------------------------------ formulas drawer (right) */
  $$("[data-drawer-open]").forEach((b) => b.addEventListener("click", () => {
    const d = $(`[data-drawer="${b.dataset.drawerOpen}"]`);
    if (!d) return;
    $$(".drawer").forEach((o) => { if (o !== d) o.hidden = true; });   // one drawer at a time
    d.hidden = !d.hidden;
    if (!d.hidden && window.MondayRenderMath) window.MondayRenderMath(d);
  }));
  $$("[data-drawer-close]").forEach((b) => b.addEventListener("click", () => (b.closest(".drawer").hidden = true)));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $$(".drawer").forEach((d) => (d.hidden = true)); });

  /* ------------------------------------------------------------ SAT answer entry: allowed characters, length, preview */
  const satForm = $("form[data-sat-entry]");
  if (satForm) {
    const clean = (v) => {
      v = v.replace(/[−–]/g, "-").replace(/[^0-9./-]/g, "");
      v = v.replace(/(?!^)-/g, "");                                    // minus only in front
      const sep = v.search(/[./]/);                                     // only one "." or "/"
      if (sep >= 0) v = v.slice(0, sep + 1) + v.slice(sep + 1).replace(/[./]/g, "");
      return v.slice(0, v.startsWith("-") ? 6 : 5);
    };
    const preview = (input) => {
      const box = input.closest(".q-card") && $("[data-entry-preview]", input.closest(".q-card"));
      if (!box) return;
      const v = input.value.trim();
      box.hidden = !v;
      if (!v) return;
      const m = v.match(/^(-?)(\d+)\/(\d+)$/);
      const tex = m ? `${m[1]}\\frac{${m[2]}}{${m[3]}}` : v;
      const out = $("[data-entry-math]", box);
      if (window.katex) { try { window.katex.render(tex, out, { throwOnError: false }); return; } catch (_) {} }
      out.textContent = v;
    };
    $$("input[name^=q]", satForm).forEach((input) => {
      if (input.type === "radio") return;
      input.setAttribute("maxlength", "6");
      input.setAttribute("inputmode", "decimal");
      input.addEventListener("input", () => {
        const v = clean(input.value);
        if (v !== input.value) input.value = v;
        preview(input);
      });
      preview(input);
    });
  }

  /* ------------------------------------------------------------ Desmos pane (left, resizable) */
  const pane = $("[data-calc-pane]");
  if (pane) {
    const root = document.documentElement;
    const box = $("[data-desmos]", pane);
    let calc = null, loading = false;
    const minW = 320;
    const maxW = () => Math.max(minW, Math.round(window.innerWidth * 0.7));
    const setWidth = (w) => {
      w = Math.max(minW, Math.min(maxW(), Math.round(w)));
      root.style.setProperty("--calc-w", `${w}px`);
      return w;
    };
    let width = setWidth(read("monday-calc-w", 460));
    const place = () => {   // pane sits between the sticky tool bar and the footer
      const head = $("[data-calc-top]");
      const foot = $("[data-calc-bottom]");
      const top = head ? head.getBoundingClientRect().bottom : 64;
      const bottom = foot && getComputedStyle(foot).display !== "none" ? window.innerHeight - foot.getBoundingClientRect().top : 0;
      root.style.setProperty("--calc-top", `${Math.max(0, top)}px`);
      root.style.setProperty("--calc-bottom", `${Math.max(0, bottom)}px`);
      if (calc && calc.resize) calc.resize();
    };
    const fail = () => { box.innerHTML = `<p class="muted small" style="padding:16px">${box.dataset.fail}</p>`; loading = false; };
    const load = () => {
      if (calc || loading) return;
      loading = true;
      const s = document.createElement("script");
      s.src = box.dataset.src;
      s.onload = () => {
        box.innerHTML = "";
        try { calc = window.Desmos.GraphingCalculator(box, { keypad: true, expressions: true, settingsMenu: false, border: false }); }
        catch (_) { fail(); }
      };
      s.onerror = fail;
      document.head.appendChild(s);
    };
    const open = (on) => {
      pane.hidden = !on;
      document.body.classList.toggle("has-calc", on);
      $$("[data-calc-open]").forEach((b) => b.setAttribute("aria-pressed", String(on)));
      if (on) { place(); load(); }
      write("monday-calc-open", on);
    };
    $$("[data-calc-open]").forEach((b) => b.addEventListener("click", () => open(pane.hidden)));
    $$("[data-calc-close]", pane).forEach((b) => b.addEventListener("click", () => open(false)));
    window.addEventListener("resize", () => { width = setWidth(width); if (!pane.hidden) place(); });
    window.addEventListener("scroll", () => { if (!pane.hidden) place(); }, { passive: true });

    // drag the right edge to resize; arrows work too
    const handle = $("[data-calc-resize]", pane);
    handle.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      document.body.classList.add("is-resizing");
      const move = (ev) => { width = setWidth(ev.clientX); if (calc && calc.resize) calc.resize(); };
      const up = () => {
        document.body.classList.remove("is-resizing");
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", up);
        handle.removeEventListener("pointercancel", up);
        write("monday-calc-w", width);
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up);
      handle.addEventListener("pointercancel", up);
    });
    handle.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      width = setWidth(width + (e.key === "ArrowRight" ? 40 : -40));
      write("monday-calc-w", width);
      if (calc && calc.resize) calc.resize();
    });
    if (read("monday-calc-open", false)) open(true);
  }

  /* ------------------------------------------------------------ timed tests */
  const form = $("#test-form");
  if (!form) return;
  const csrf = ($("input[name=csrf_token]", form) || {}).value || "";
  const save = (name, value) => {
    const body = new FormData();
    body.set("csrf_token", csrf); body.set("name", name); body.set("value", value);
    return fetch(form.dataset.autosave, { method: "POST", body, headers: { "X-CSRFToken": csrf }, credentials: "same-origin" }).catch(() => {});
  };
  const answered = (idx) => $$(`[name="q${idx}"]`, form).some((f) => (f.type === "radio" ? f.checked : f.value.trim() !== ""));
  const key = (k) => `monday-${form.dataset.attempt}-m${form.dataset.start}-${k}`;   // per module: module 2 starts at its own first question

  /* homework: can't be handed in with no answers; asks once when some are left empty */
  if (form.hasAttribute("data-require-answer")) {
    const earlier = parseInt(form.dataset.earlierAnswered || "0", 10) || 0;
    const start = parseInt(form.dataset.start, 10), end = parseInt(form.dataset.end, 10);
    const count = () => { let n = 0; for (let i = start; i < end; i += 1) if (answered(i)) n += 1; return n; };
    const finals = $$("button[type=submit]", form);
    const hints = $$("[data-submit-hint]", form);
    const refresh = () => {
      const none = earlier + count() === 0;
      finals.forEach((b) => { b.disabled = none; b.setAttribute("aria-disabled", String(none)); });
      hints.forEach((h) => { h.hidden = !none; h.textContent = form.dataset.emptyMsg; });
    };
    form.addEventListener("change", refresh);
    form.addEventListener("input", refresh);
    form.addEventListener("submit", (e) => {
      const n = count(), total = end - start;
      if (earlier + n === 0) { e.preventDefault(); refresh(); return; }
      if (n < total && !window.confirm(form.dataset.partialMsg.replace("{n}", String(total - n)).replace("{total}", String(total)))) {
        e.preventDefault();
      }
    });
    refresh();
  }

  /* grid navigation */
  if (form.dataset.nav === "grid") {
    const screens = $$(".q-screen", form);
    const review = $("[data-review]", form);
    const grid = $("[data-grid]", form), gridReview = $("[data-grid-review]", form), pop = $("[data-grid-pop]", form);
    const prev = $("[data-prev]", form), next = $("[data-next]", form), final = $("[data-final]", form);
    const counter = $("[data-counter]", form);
    let cur = 0, reviewing = false;
    try { cur = Math.min(screens.length - 1, parseInt(sessionStorage.getItem(key("cur")) || "0", 10) || 0); } catch (_) {}
    form.classList.add("is-paged");

    const idxOf = (i) => parseInt(screens[i].dataset.q, 10);
    const buildGrid = (target) => {
      target.innerHTML = "";
      screens.forEach((sc, i) => {
        const idx = idxOf(i);
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = String(idx + 1);
        if (answered(idx)) b.classList.add("is-answered");
        if ($("[data-mark]", sc).getAttribute("aria-pressed") === "true") b.classList.add("is-marked");
        if (i === cur && !reviewing) b.classList.add("is-current");
        b.addEventListener("click", () => { reviewing = false; show(i); pop.hidden = true; });
        target.appendChild(b);
      });
    };
    function show(i) {
      cur = Math.max(0, Math.min(screens.length - 1, i));
      try { sessionStorage.setItem(key("cur"), String(cur)); } catch (_) {}
      screens.forEach((sc, k) => (sc.hidden = reviewing || k !== cur));
      review.hidden = !reviewing;
      counter.textContent = String(cur + 1);
      prev.disabled = !reviewing && cur === 0;
      next.hidden = reviewing;
      final.hidden = !reviewing;
      const lastQ = cur === screens.length - 1;
      next.firstChild.textContent = lastQ ? next.dataset.reviewLabel : next.dataset.nextLabel;
      buildGrid(grid);
      if (reviewing) buildGrid(gridReview);
      window.scrollTo({ top: 0 });
      if (window.MondayRenderMath && !reviewing) window.MondayRenderMath(screens[cur]);
    }
    prev.addEventListener("click", () => { if (reviewing) { reviewing = false; show(screens.length - 1); } else show(cur - 1); });
    next.addEventListener("click", () => { if (cur === screens.length - 1) { reviewing = true; show(cur); } else show(cur + 1); });
    $("[data-grid-toggle]", form).addEventListener("click", (e) => {
      pop.hidden = !pop.hidden;
      e.currentTarget.setAttribute("aria-expanded", String(!pop.hidden));
      buildGrid(grid);
    });
    document.addEventListener("click", (e) => { if (!pop.hidden && !e.target.closest("[data-grid-pop], [data-grid-toggle]")) pop.hidden = true; });
    form.addEventListener("change", () => buildGrid(grid));
    document.addEventListener("keydown", (e) => {
      if (e.target.matches("input, textarea") || e.target.closest(".calc-pane")) return;
      if (e.key === "ArrowRight") next.click();
      if (e.key === "ArrowLeft" && !prev.disabled) prev.click();
    });

    // mark for review (saved with the answers as r<i>)
    $$("[data-mark]", form).forEach((b) => b.addEventListener("click", () => {
      const on = b.getAttribute("aria-pressed") !== "true";
      b.setAttribute("aria-pressed", String(on));
      save(`r${b.dataset.mark}`, on ? "1" : "");
      buildGrid(grid);
    }));
    show(cur);
  }

  /* ORT pages + answer sheet */
  if (form.dataset.nav === "pages") {
    const pages = $$(".ort-page", form);
    const dots = $$("[data-page-go]", form);
    let cur = 0;
    try { cur = Math.min(pages.length - 1, parseInt(sessionStorage.getItem(key("page")) || "0", 10) || 0); } catch (_) {}
    form.classList.add("is-paged");
    const show = (p) => {
      cur = Math.max(0, Math.min(pages.length - 1, p));
      try { sessionStorage.setItem(key("page"), String(cur)); } catch (_) {}
      pages.forEach((pg, k) => (pg.hidden = k !== cur));
      dots.forEach((d, k) => d.classList.toggle("is-current", k === cur));
      $("[data-page-prev]", form).disabled = cur === 0;
      $("[data-page-next]", form).disabled = cur === pages.length - 1;
      if (window.MondayRenderMath) window.MondayRenderMath(pages[cur]);
    };
    $("[data-page-prev]", form).addEventListener("click", () => { show(cur - 1); pages[cur].scrollIntoView({ block: "start" }); });
    $("[data-page-next]", form).addEventListener("click", () => { show(cur + 1); pages[cur].scrollIntoView({ block: "start" }); });
    dots.forEach((d) => d.addEventListener("click", () => show(parseInt(d.dataset.pageGo, 10))));
    $$("[data-goto]", form).forEach((a) => a.addEventListener("click", (e) => {
      e.preventDefault();
      const target = document.getElementById(`question-${parseInt(a.dataset.goto, 10) + 1}`);
      const page = target.closest(".ort-page");
      show(pages.indexOf(page));
      target.scrollIntoView({ block: "center" });
      target.classList.add("is-flash");
      setTimeout(() => target.classList.remove("is-flash"), 900);
    }));
    const markRows = () => $$("[data-sheet-row]", form).forEach((row) => row.classList.toggle("is-answered", answered(row.dataset.sheetRow)));
    form.addEventListener("change", markRows);
    form.addEventListener("input", markRows);
    markRows();
    show(cur);
  }
})();

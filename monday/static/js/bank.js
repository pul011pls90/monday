/* Monday — question bank: filter chips, topic checkboxes, and the SAT-style question player. */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const ss = (() => { try { return window.sessionStorage; } catch (_) { return null; } })();
  const ls = (() => { try { return window.localStorage; } catch (_) { return null; } })();

  /* ------------------------------------------------------------ bank page */
  const filters = $("[data-bank-filters]");
  if (filters) {
    // keep the scroll position across the reload a chip causes
    try { const y = ss && ss.getItem("monday-bank-y"); if (y) { window.scrollTo(0, parseInt(y, 10)); ss.removeItem("monday-bank-y"); } } catch (_) {}
    // any chip of the form — including the exam switch in the page head (form="bk-filters") — applies at once
    document.addEventListener("change", (e) => {
      if (e.target.form !== filters) return;
      try { ss && ss.setItem("monday-bank-y", String(window.scrollY)); } catch (_) {}
      filters.submit();
    });
    // phones: the filter boxes fold behind the «Фильтры» row; wider screens always show them
    const fold = $("[data-bank-fold]");
    const wide = window.matchMedia("(min-width: 641px)");
    const sync = () => { if (fold) fold.open = wide.matches; };
    sync();
    if (wide.addEventListener) wide.addEventListener("change", sync);
    if (fold) $("summary", fold).addEventListener("click", (e) => { if (wide.matches) e.preventDefault(); });
  }

  const tree = $("[data-bank-tree]");
  if (tree) {
    // remember which topics are open
    let open = [];
    try { open = JSON.parse((ls && ls.getItem("monday-bank-open")) || "[]"); } catch (_) {}
    $$("details[data-topic]", tree).forEach((d) => {
      if (open.includes(d.dataset.topic)) d.open = true;
      d.addEventListener("toggle", () => {
        open = $$("details[data-topic]", tree).filter((x) => x.open).map((x) => x.dataset.topic);
        try { ls && ls.setItem("monday-bank-open", JSON.stringify(open)); } catch (_) {}
      });
    });

    const text = $("[data-sel-text]", tree);
    const update = () => {
      const picked = $$("input[name=k]:checked", tree);
      const q = picked.reduce((a, c) => a + (parseInt(c.dataset.count, 10) || 0), 0);
      text.textContent = picked.length ? text.dataset.some.replace("{k}", picked.length).replace("{q}", q) : text.dataset.none;
      // sub-topic box: checked when all its skills are, half when some are
      $$(".bank-sub", tree).forEach((sub) => {
        const boxes = $$("input[name=k]:not(:disabled)", sub);
        const on = boxes.filter((b) => b.checked).length;
        const head = $("[data-sub-check]", sub);
        if (!head) return;
        head.checked = boxes.length > 0 && on === boxes.length;
        head.indeterminate = on > 0 && on < boxes.length;
      });
      $$(".bank-topic", tree).forEach((t) => t.classList.toggle("has-picked", !!$("input[name=k]:checked", t)));
    };
    tree.addEventListener("change", (e) => {
      if (e.target.matches("[data-sub-check]")) {
        $$("input[name=k]:not(:disabled)", e.target.closest(".bank-sub")).forEach((b) => (b.checked = e.target.checked));
      }
      update();
    });
    update();
  }

  /* ------------------------------------------------------------ question player */
  const form = $("[data-bank-play]");
  if (!form) return;
  const csrf = ($("input[name=csrf_token]", form) || {}).value || "";
  const qid = form.dataset.question;
  const post = (url, data) => {
    const body = new FormData();
    body.set("csrf_token", csrf);
    Object.entries(data).forEach(([k, v]) => body.set(k, v));
    return fetch(url, { method: "POST", body, headers: { "X-CSRFToken": csrf, "X-Requested-With": "fetch" }, credentials: "same-origin" });
  };

  // per-question timer: counts this visit; unsent seconds go with "check" or when leaving the page
  const timerEl = $("[data-qtimer]");
  let visit = 0, unsent = 0;
  const metaTime = $("[data-meta-time]"), base = metaTime ? Number(metaTime.dataset.base) || 0 : 0;
  const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  setInterval(() => {
    if (document.hidden) return;
    visit += 1; unsent += 1;
    timerEl.textContent = fmt(visit);
    if (metaTime) { const t = base + visit; metaTime.textContent = `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; }
  }, 1000);
  const flushTime = () => {
    if (unsent < 1) return;
    const body = new FormData();
    body.set("csrf_token", csrf); body.set("question_id", qid); body.set("seconds", String(unsent));
    unsent = 0;
    if (navigator.sendBeacon) navigator.sendBeacon(form.dataset.timeUrl, body);
    else fetch(form.dataset.timeUrl, { method: "POST", body, keepalive: true, credentials: "same-origin" }).catch(() => {});
  };
  window.addEventListener("pagehide", flushTime);
  document.addEventListener("visibilitychange", () => { if (document.hidden) flushTime(); });

  // mark for review
  const markBtn = $("[data-bank-mark]", form);
  markBtn.addEventListener("click", () => {
    const on = markBtn.getAttribute("aria-pressed") !== "true";
    markBtn.setAttribute("aria-pressed", String(on));
    post(form.dataset.markUrl, { question_id: qid, on: on ? "1" : "" }).catch(() => {});
  });

  // details popover
  const metaBtn = $("[data-meta-toggle]"), metaPop = $("[data-meta-pop]");
  metaBtn.addEventListener("click", () => { metaPop.hidden = !metaPop.hidden; metaBtn.setAttribute("aria-expanded", String(!metaPop.hidden)); });
  document.addEventListener("click", (e) => { if (!metaPop.hidden && !e.target.closest(".bank-meta")) { metaPop.hidden = true; metaBtn.setAttribute("aria-expanded", "false"); } });

  // grid popover
  const gridBtn = $("[data-grid-toggle]"), gridPop = $("[data-grid-pop]");
  if (matchMedia("(min-width: 1100px)").matches) document.body.appendChild(gridPop);  // side panel (see brand.css)
  gridBtn.addEventListener("click", () => {
    gridPop.hidden = !gridPop.hidden;
    gridBtn.setAttribute("aria-expanded", String(!gridPop.hidden));
    if (!gridPop.hidden) { const cur = $(".is-current", gridPop); if (cur) cur.scrollIntoView({ block: "nearest" }); }
  });
  document.addEventListener("click", (e) => { if (!gridPop.hidden && !e.target.closest("[data-grid-pop], [data-grid-toggle]")) gridPop.hidden = true; });
  $$("[data-grid-tab]", gridPop).forEach((tab) => tab.addEventListener("click", () => {
    $$("[data-grid-tab]", gridPop).forEach((t) => { const on = t === tab; t.classList.toggle("is-active", on); t.setAttribute("aria-selected", String(on)); });
    $$("[data-grid-panel]", gridPop).forEach((p) => { p.hidden = p.dataset.gridPanel !== tab.dataset.gridTab; });
    const cur = $(`[data-grid-panel="${tab.dataset.gridTab}"] .is-current`, gridPop);
    if (cur) cur.scrollIntoView({ block: "nearest" });
  }));

  // keyboard: ← → move between questions (not while typing or in the calculator)
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input[type=text], input:not([type]), textarea") || e.target.closest(".calc-pane")) return;
    const link = e.key === "ArrowRight" ? $("[data-next-link]") : e.key === "ArrowLeft" ? $("[data-prev-link]") : null;
    if (link) link.click();
  });

  // check + explanation
  const feedback = $("[data-feedback]", form);
  const explain = $("[data-explain]", form);
  const explainBtn = $("[data-explain-open]");
  const attemptsEl = $("[data-attempts]", form);
  const checkedEl = $("[data-checked]");
  const given = () => {
    if (form.dataset.answerType === "number") return ($("input[name=given]", form).value || "").trim();
    const c = $("input[name=given]:checked", form);
    return c ? c.value : "";
  };
  const say = (cls, text) => {
    feedback.hidden = false;
    feedback.className = `feedback ${cls}`;
    feedback.textContent = text;
  };
  const clearMarks = () => $$(".option__box", form).forEach((b) => b.classList.remove("is-correct", "is-wrong"));
  const showAnswer = (data) => {
    $("[data-explain-answer]", form).textContent = `${form.dataset.answerLabel} ${data.correct_text}`;
    $("[data-explain-text]", form).textContent = data.explanation;
    const v = $("[data-explain-video]", form);
    if (data.video_url) { v.href = data.video_url; v.hidden = false; }
    explain.hidden = false;
    if (form.dataset.answerType !== "number") {
      const right = $(`input[name=given][value="${data.correct}"]`, form);
      if (right) right.nextElementSibling.classList.add("is-correct");
    }
    if (window.MondayRenderMath) window.MondayRenderMath(explain);
  };
  const solved = (data) => {
    form.dataset.solved = "1";
    $$("input[name=given]", form).forEach((i) => (i.disabled = true));
    $("[data-check-btn]").disabled = true;
    showAnswer(data);
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (form.dataset.solved || form.dataset.busy) return;
    const value = given();
    if (!value) { say("feedback--bad", form.dataset.emptyLabel); return; }
    form.dataset.busy = "1";
    const seconds = unsent; unsent = 0;
    try {
      const res = await post(form.dataset.check, { i: form.dataset.i, given: value, seconds });
      const data = await res.json();
      if (!res.ok) { say("feedback--bad", data.error || ""); return; }
      attemptsEl.textContent = data.attempts;
      if (checkedEl) checkedEl.textContent = data.checked;
      explainBtn.disabled = false;
      clearMarks();
      const chosen = $("input[name=given]:checked", form);
      if (data.ok) {
        say("feedback--ok", form.dataset.correctLabel);
        if (chosen) chosen.nextElementSibling.classList.add("is-correct");
        solved(data);
      } else {
        say("feedback--bad", form.dataset.wrongLabel);
        if (chosen) chosen.nextElementSibling.classList.add("is-wrong");
        if (data.correct !== undefined) showAnswer(data);   // already revealed earlier
      }
    } catch (_) {
      unsent += seconds;
    } finally {
      delete form.dataset.busy;
    }
  });
  form.addEventListener("change", () => { if (!form.dataset.solved) { clearMarks(); feedback.hidden = true; } });

  explainBtn.addEventListener("click", async () => {
    if (!explain.hidden) { explain.hidden = true; return; }
    try {
      const res = await post(form.dataset.reveal, { i: form.dataset.i });
      const data = await res.json();
      if (res.ok) { showAnswer(data); explain.scrollIntoView({ behavior: "smooth", block: "nearest" }); }
      else say("feedback--bad", data.error || "");
    } catch (_) {}
  });

  // already solved earlier: show it as solved
  if (form.dataset.solved !== undefined && form.hasAttribute("data-solved")) {
    $$("input[name=given]", form).forEach((i) => (i.disabled = true));
    $("[data-check-btn]").disabled = true;
    const chosen = $("input[name=given]:checked", form);
    if (chosen) chosen.nextElementSibling.classList.add("is-correct");
    form.dataset.solved = "1";
  }
})();

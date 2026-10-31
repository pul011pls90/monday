/* Question bank booklet: answers on the sheet (or by clicking an option in the question), checked a page at a time. */
(() => {
  const form = document.querySelector("[data-bank-sheet]");
  if (!form) return;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const csrf = ($("input[name=csrf_token]", form) || {}).value || "";
  const math = (el) => window.MondayRenderMath && window.MondayRenderMath(el);
  const post = (url, data) => {
    const body = new FormData();
    body.set("csrf_token", csrf);
    Object.entries(data).forEach(([k, v]) => body.set(k, v));
    return fetch(url, { method: "POST", body, headers: { "X-CSRFToken": csrf, "X-Requested-With": "fetch" }, credentials: "same-origin" })
      .then((r) => r.json().catch(() => ({})).then((j) => ({ status: r.status, ...j })));
  };

  // the option in the question and the bubble on the sheet are the same answer
  form.addEventListener("change", (e) => {
    const m = /^([cq])(\d+)$/.exec(e.target.name || "");
    if (!m) return;
    const other = form.querySelector(`input[name="${m[1] === "c" ? "q" : "c"}${m[2]}"][value="${e.target.value}"]`);
    if (other) other.checked = true;
  });

  const card = (i) => form.querySelector(`[data-q="${i}"]`);
  const row = (i) => form.querySelector(`[data-sheet-row="${i}"]`);
  const given = (i) => {
    const r = row(i);
    const on = $("input[type=radio]:checked", r);
    if (on) return on.value;
    const t = $("input:not([type=radio])", r);
    return t ? t.value.trim() : "";
  };
  const showAnswer = (i, res) => {
    const c = card(i);
    const ex = $("[data-explain]", c);
    $("[data-explain-answer]", ex).textContent = `${form.dataset.answerLabel} ${res.correct_text.replace(/<[^>]+>/g, "")}`;
    $("[data-explain-text]", ex).textContent = res.explanation || "";
    ex.hidden = false;
    math(ex);
  };
  const mark = (i, ok) => {
    [card(i), row(i)].forEach((el) => { el.classList.toggle("is-ok", ok); el.classList.toggle("is-bad", !ok); });
    const fb = $("[data-fb]", card(i));
    fb.hidden = false;
    let b = $("b", fb);
    if (!b) { b = document.createElement("b"); fb.prepend(b); }
    b.textContent = ok ? form.dataset.okLabel : form.dataset.badLabel;
    $("[data-reveal-btn]", fb).hidden = false;
  };

  $("[data-check-page]", form).addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const note = $("[data-note]", form);
    const todo = $$("[data-sheet-row]", form).map((r) => r.dataset.sheetRow).filter((i) => given(i));
    note.hidden = todo.length > 0;
    note.textContent = form.dataset.noneLabel;
    if (!todo.length) return;
    btn.disabled = true;
    for (const i of todo) {
      const res = await post(form.dataset.check, { i, given: given(i) });
      if (res.status !== 200) continue;
      mark(i, res.ok);
      if (res.explanation) showAnswer(i, res);
      if (res.checked != null) {
        $("[data-checked]", form).textContent = res.checked;
        const bar = $("[data-checked-bar]", form);
        if (bar) bar.style.width = `${(100 * res.checked) / Number(form.dataset.total || 1)}%`;
      }
    }
    btn.disabled = false;
  });

  // ← → switch pages (not while typing an answer); the page map closes on outside click
  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey) return;
    const link = e.key === "ArrowRight" ? $("[data-next]") : e.key === "ArrowLeft" ? $("[data-prev]") : null;
    if (link) location.href = link.href;
  });
  const jumpEl = $("[data-jump]");
  if (jumpEl) jumpEl.addEventListener("toggle", () => {
    const cur = jumpEl.open && $(".is-current", jumpEl);
    const pop = $(".bb-jump__pop", jumpEl);
    if (cur && pop) pop.scrollTop = cur.offsetTop - pop.clientHeight / 2 + cur.offsetHeight / 2;
  });
  document.addEventListener("click", (e) => {
    const jump = $("[data-jump]");
    if (jump && jump.open && !jump.contains(e.target)) jump.open = false;
  });

  form.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-reveal-btn]");
    if (!b) return;
    const i = b.closest("[data-q]").dataset.q;
    const ex = $("[data-explain]", card(i));
    if (!ex.hidden) { ex.hidden = true; return; }
    const res = await post(form.dataset.reveal, { i });
    if (res.status === 200) showAnswer(i, res);
  });
})();

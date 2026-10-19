/* Monday — questions of the day: one question at a time, one answer each, instant review, summary at the end. */
(function () {
  "use strict";
  const box = document.querySelector("[data-daily-box]");
  if (!box) return;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const tabs = $$("[data-daily-tab]", box);
  const panels = $$("[data-daily-panel]", box);
  const total = parseInt(box.dataset.total, 10);
  const show = (k) => {
    tabs.forEach((t, i) => t.setAttribute("aria-selected", String(i === k)));
    panels.forEach((p, i) => (p.hidden = i !== k));
    window.scrollTo({ top: 0 });
    if (window.MondayRenderMath) window.MondayRenderMath(panels[k]);
  };
  tabs.forEach((t, i) => t.addEventListener("click", () => show(i)));
  const firstOpen = panels.slice(0, total).findIndex((p) => !p.hasAttribute("data-done"));
  show(firstOpen === -1 ? total : firstOpen);
  const nextOpen = (k) => { for (let i = k + 1; i < total; i += 1) if (!panels[i].hasAttribute("data-done")) return i; return total; };
  $$("[data-daily-next]", box).forEach((b) => b.addEventListener("click", () => show(nextOpen(panels.indexOf(b.closest("[data-daily-panel]"))))));

  let score = parseInt(($("[data-daily-score]", box) || {}).textContent || "0", 10);
  panels.slice(0, total).forEach((form, k) => {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (form.hasAttribute("data-done") || form.dataset.busy) return;
      const name = form.dataset.name;
      let given = "";
      if (form.dataset.answerType === "number") given = ($(`input[name="${name}"]`, form).value || "").trim();
      else { const c = $(`input[name="${name}"]:checked`, form); given = c ? c.value : ""; }
      const fb = $("[data-daily-feedback]", form);
      if (!given) { fb.className = "feedback feedback--bad"; fb.textContent = form.dataset.empty; return; }
      form.dataset.busy = "1";
      const body = new FormData(form);
      body.set("given", given);
      try {
        const res = await fetch(form.action, { method: "POST", body, headers: { "X-Requested-With": "fetch" }, credentials: "same-origin" });
        const data = await res.json();
        if (!res.ok) { fb.className = "feedback feedback--bad"; fb.textContent = data.error || ""; return; }
        form.setAttribute("data-done", "");
        $$(`input[name="${name}"]`, form).forEach((i) => (i.disabled = true));
        const sub = $("[data-daily-submit]", form); if (sub) sub.remove();
        $("[data-daily-next]", form).hidden = false;
        fb.className = `feedback ${data.ok ? "feedback--ok" : "feedback--bad"}`;
        fb.textContent = data.ok ? form.dataset.ok : `${form.dataset.bad} ${form.dataset.answerLabel} ${data.correct_text}`;
        if (form.dataset.answerType !== "number") {
          const chosen = $(`input[name="${name}"]:checked`, form);
          if (chosen) chosen.nextElementSibling.classList.add(data.ok ? "is-correct" : "is-wrong");
          const right = $(`input[name="${name}"][value="${data.correct}"]`, form);
          if (right) right.nextElementSibling.classList.add("is-correct");
        }
        $("[data-daily-expl]", form).textContent = data.explanation;
        $("[data-daily-explain]", form).hidden = false;
        if (data.rate) $("[data-daily-rate]", form).textContent = form.dataset.rate.replace("{ok}", data.rate.ok).replace("{total}", data.rate.total);
        tabs[k].classList.add(data.ok ? "is-ok" : "is-bad");
        if (data.ok) { score += 1; const sc = $("[data-daily-score]", box); if (sc) sc.textContent = score; }
        $$("[data-daily-streak]", box).forEach((st) => { if (data.streak !== undefined) st.textContent = data.streak; });
        if (window.MondayRenderMath) window.MondayRenderMath(form);
      } catch (_) {
      } finally { delete form.dataset.busy; }
    });
  });
})();

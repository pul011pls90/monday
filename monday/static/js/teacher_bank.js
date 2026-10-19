/* Monday — teacher question bank: filters apply at once, pick questions, add them to a work. */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const ss = (() => { try { return window.sessionStorage; } catch (_) { return null; } })();

  const filters = $("[data-bank-filters]");
  if (filters) {
    try { const y = ss && ss.getItem("monday-tbank-y"); if (y) { window.scrollTo(0, parseInt(y, 10)); ss.removeItem("monday-tbank-y"); } } catch (_) {}
    filters.addEventListener("change", (e) => {
      if (e.target.name === "q") return;
      try { ss && ss.setItem("monday-tbank-y", String(window.scrollY)); } catch (_) {}
      filters.submit();
    });
  }

  const form = $("[data-pick]");
  if (!form) return;
  const count = $("[data-pick-count]", form);
  const submit = $("[data-pick-submit]", form);
  const all = $("[data-pick-all]", form);
  const update = () => {
    const boxes = $$("input[name=qid]", form);
    const n = boxes.filter((b) => b.checked).length;
    count.textContent = n;
    submit.disabled = n === 0;
    boxes.forEach((b) => b.closest(".tbank-q").classList.toggle("is-picked", b.checked));
    if (all) { all.checked = n > 0 && n === boxes.length; all.indeterminate = n > 0 && n < boxes.length; }
  };
  form.addEventListener("change", (e) => {
    if (e.target === all) $$("input[name=qid]", form).forEach((b) => (b.checked = all.checked));
    update();
  });
  update();
})();

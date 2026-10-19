/* Monday — teacher: attendance without reloading, drag homework to another day. */
(function () {
  "use strict";
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  // attendance: one tap marks, tapping the same mark again clears it
  $$("form[data-att]").forEach((form) => {
    form.addEventListener("submit", async (e) => {
      if (!window.fetch) return;
      e.preventDefault();
      const btn = e.submitter;
      if (!btn) return;
      const was = btn.getAttribute("aria-pressed") === "true";
      const body = new FormData(form);
      body.set("status", was ? "" : btn.value);
      try {
        const res = await fetch(form.action, { method: "POST", body, headers: { "X-Requested-With": "fetch" }, credentials: "same-origin" });
        if (!res.ok) throw new Error();
        $$("button[name=status]", form).forEach((b) => b.setAttribute("aria-pressed", String(!was && b === btn)));
      } catch (_) { form.submit(); }
    });
  });

  // homework week: drag a card onto another day to move its due date
  const week = document.querySelector("[data-week]");
  if (!week) return;
  let dragged = null;
  $$("[data-hw]", week).forEach((card) => {
    card.addEventListener("dragstart", (e) => { dragged = card; card.classList.add("is-dragging"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", card.dataset.hw); });
    card.addEventListener("dragend", () => { card.classList.remove("is-dragging"); $$(".is-over", week).forEach((d) => d.classList.remove("is-over")); });
  });
  $$("[data-day]", week).forEach((day) => {
    day.addEventListener("dragover", (e) => { if (dragged) { e.preventDefault(); day.classList.add("is-over"); } });
    day.addEventListener("dragleave", () => day.classList.remove("is-over"));
    day.addEventListener("drop", async (e) => {
      e.preventDefault();
      day.classList.remove("is-over");
      if (!dragged) return;
      const card = dragged; dragged = null;
      const from = card.parentElement;
      day.querySelector(".t-week__items").appendChild(card);
      const body = new FormData();
      body.set("csrf_token", week.dataset.csrf);
      body.set("day", day.dataset.day);
      try {
        const res = await fetch(card.dataset.hw, { method: "POST", body, headers: { "X-Requested-With": "fetch", "X-CSRFToken": week.dataset.csrf }, credentials: "same-origin" });
        if (!res.ok) throw new Error();
        card.classList.add("is-moved");
        setTimeout(() => card.classList.remove("is-moved"), 900);
      } catch (_) { from.appendChild(card); }
    });
  });
})();

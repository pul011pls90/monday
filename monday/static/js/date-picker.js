/* Our calendar in place of the browser's, which can't be styled. Each date input stays in the form as a hidden field with
   the same name and value (YYYY-MM-DD); a button shows the date and opens the calendar. Touch screens keep the native
   picker, which is made for them. Keys: arrows move a day or a week, PageUp/PageDown a month, Enter picks, Esc closes. */
(() => {
  if (matchMedia("(pointer: coarse)").matches) return;
  const fields = document.querySelectorAll("input[type=date]");
  if (!fields.length) return;

  const labels = document.body.dataset;
  const lang = document.documentElement.lang || "ru";
  const pad = (n) => String(n).padStart(2, "0");
  const toIso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const fromIso = (s) => { const m = /^(\d{4})-(\d\d)-(\d\d)$/.exec(s || ""); return m ? new Date(+m[1], m[2] - 1, +m[3]) : null; };
  const noYearMark = (s) => s.replace(/\s*г\.$/, "");   // Russian dates end in "г."; the rest of the site writes them without it
  const dateText = new Intl.DateTimeFormat(lang, { day: "numeric", month: "long", year: "numeric" });
  const longDate = { format: (d) => noYearMark(dateText.format(d)) };
  const monthText = new Intl.DateTimeFormat(lang, { month: "long", year: "numeric" });
  const monthName = { format: (d) => noYearMark(monthText.format(d)) };
  const dayName = new Intl.DateTimeFormat(lang, { weekday: "short" });
  const weekdays = [...Array(7)].map((_, i) => dayName.format(new Date(2024, 0, 1 + i)).replace(".", ""));   // 1 Jan 2024 was a Monday
  const ICON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>';
  const ARROW = (d) => `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${d}"/></svg>`;

  let open = null;   // { input, button, box, month, cursor }

  function close(focusButton) {
    if (!open) return;
    open.box.remove();
    open.button.setAttribute("aria-expanded", "false");
    if (focusButton) open.button.focus();
    open = null;
  }

  function pick(iso) {
    const { input, button } = open;
    input.value = iso;
    show(input, button);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    close(true);
  }

  const allowed = (input, iso) => (!input.dataset.min || iso >= input.dataset.min) && (!input.dataset.max || iso <= input.dataset.max);

  function draw() {
    const { box, month, cursor, input } = open;
    const today = toIso(new Date()), chosen = input.value;
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const lead = (first.getDay() + 6) % 7, days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
    const cells = [];
    for (let i = 0; i < lead; i++) cells.push("<span></span>");
    for (let d = 1; d <= days; d++) {
      const iso = toIso(new Date(month.getFullYear(), month.getMonth(), d));
      const cls = [iso === chosen && "is-chosen", iso === today && "is-today", iso === toIso(cursor) && "is-cursor"].filter(Boolean).join(" ");
      cells.push(`<button type="button" class="${cls}" data-day="${iso}" ${allowed(input, iso) ? "" : "disabled"}${iso === chosen ? ' aria-current="date"' : ""} aria-label="${longDate.format(fromIso(iso))}">${d}</button>`);
    }
    const title = monthName.format(month);
    box.innerHTML = `
      <div class="dp__head">
        <b class="dp__title" aria-live="polite">${title[0].toUpperCase() + title.slice(1)}</b>
        <button type="button" class="dp__nav" data-move="-1" aria-label="${labels.datePrev}">${ARROW("M15 6l-6 6 6 6")}</button>
        <button type="button" class="dp__nav" data-move="1" aria-label="${labels.dateNext}">${ARROW("M9 6l6 6-6 6")}</button>
      </div>
      <div class="dp__week" aria-hidden="true">${weekdays.map((w) => `<span>${w}</span>`).join("")}</div>
      <div class="dp__days">${cells.join("")}</div>
      <div class="dp__foot"><button type="button" data-clear>${labels.dateClear}</button><button type="button" data-today>${labels.dateToday}</button></div>`;
  }

  function place() {
    const { button, box } = open;
    const r = button.getBoundingClientRect(), h = box.offsetHeight, w = box.offsetWidth;
    const below = innerHeight - r.bottom >= h + 12 || r.top < h + 12;
    box.style.left = `${Math.max(12, Math.min(r.left, innerWidth - w - 12))}px`;
    box.style.top = `${below ? r.bottom + 8 : r.top - h - 8}px`;
  }

  function goTo(date) {
    open.cursor = date;
    open.month = new Date(date.getFullYear(), date.getMonth(), 1);
    draw();
    const cell = open.box.querySelector(".is-cursor");
    if (cell) cell.focus();
  }

  function openFor(input, button) {
    if (open && open.input === input) { close(true); return; }
    close();
    const start = fromIso(input.value) || new Date();
    const box = document.createElement("div");
    box.className = "dp";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-label", button.getAttribute("aria-label") || labels.dateEmpty);
    (button.closest("dialog") || document.body).append(box);
    open = { input, button, box, cursor: start, month: new Date(start.getFullYear(), start.getMonth(), 1) };
    button.setAttribute("aria-expanded", "true");
    draw();
    place();
    const cell = box.querySelector(".is-cursor");
    if (cell) cell.focus();

    box.addEventListener("click", (e) => {
      const el = e.target.closest("button");
      if (!el) return;
      if (el.dataset.day) pick(el.dataset.day);
      else if (el.dataset.move) { open.month = new Date(open.month.getFullYear(), open.month.getMonth() + +el.dataset.move, 1); open.cursor = open.month; draw(); place(); }
      else if ("today" in el.dataset) pick(toIso(new Date()));
      else if ("clear" in el.dataset) pick("");
    });
    box.addEventListener("keydown", (e) => {
      const steps = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }, c = open.cursor;
      if (e.key in steps) { e.preventDefault(); goTo(new Date(c.getFullYear(), c.getMonth(), c.getDate() + steps[e.key])); }
      else if (e.key === "PageUp" || e.key === "PageDown") { e.preventDefault(); goTo(new Date(c.getFullYear(), c.getMonth() + (e.key === "PageUp" ? -1 : 1), 1)); }
      else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); }
    });
  }

  function show(input, button) {
    const d = fromIso(input.value);
    button.querySelector("span").textContent = d ? longDate.format(d) : labels.dateEmpty;
    button.classList.toggle("is-empty", !d);
  }

  fields.forEach((input) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "input date-field";
    button.innerHTML = `<span></span>${ICON}`;
    button.setAttribute("aria-haspopup", "dialog");
    button.setAttribute("aria-expanded", "false");
    if (input.getAttribute("aria-label")) button.setAttribute("aria-label", input.getAttribute("aria-label"));
    if (input.id) { button.id = input.id; input.removeAttribute("id"); }   // a <label for> now opens the calendar
    if (input.min) input.dataset.min = input.min;
    if (input.max) input.dataset.max = input.max;
    input.type = "hidden";
    input.after(button);
    show(input, button);
    button.addEventListener("click", () => openFor(input, button));
  });

  document.addEventListener("pointerdown", (e) => { if (open && !open.box.contains(e.target) && !open.button.contains(e.target)) close(); });
  addEventListener("resize", () => { if (open) place(); });
  addEventListener("scroll", () => { if (open) place(); }, { passive: true, capture: true });
})();

/* Monday — question picker (test editor and teacher bank).
 * Filters, search, sort, topic tree and pages load without reloading the page.
 * The chosen questions live in a "selection" provided by the page:
 *   editor → the ordered list on the right (#question_order is kept in sync)
 *   bank   → a basket on the right, sent as qid fields
 */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const root = $("[data-picker]");
  if (!root) return;
  const render = (el) => { if (window.MondayRenderMath) window.MondayRenderMath(el); };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /* ------------------------------------------------------------ the selection (order list or basket) */
  const list = $("[data-order-list]");
  const hidden = $("#question_order");
  const basketForm = $("[data-basket-form]");
  const empty = $("[data-order-empty]");
  const countEls = $$("[data-order-count]");
  const totals = $("[data-order-totals]");

  const items = () => $$("li[data-id]", list);
  const ids = () => items().map((li) => li.dataset.id);
  const has = (id) => ids().includes(String(id));
  const makeItem = (it) => {
    const li = document.createElement("li");
    li.dataset.id = it.id; li.dataset.topic = it.topic || ""; li.dataset.d = it.d || 2; li.dataset.min = it.min || 2;
    li.draggable = true;
    li.innerHTML = `<span class="order-list__grip" aria-hidden="true">⋮⋮</span><span class="math order-list__text">${esc(it.label)}</span>
      <span class="tools">
        <button type="button" data-move="-1" aria-label="Выше">↑</button>
        <button type="button" data-move="1" aria-label="Ниже">↓</button>
        <button type="button" data-remove aria-label="Убрать">×</button>
      </span>`;
    return li;
  };
  const sync = () => {
    const all = items();
    if (hidden) hidden.value = ids().join(",");
    if (basketForm) {
      $$("input[name=qid]", basketForm).forEach((i) => i.remove());
      ids().forEach((id) => { const i = document.createElement("input"); i.type = "hidden"; i.name = "qid"; i.value = id; basketForm.appendChild(i); });
      $$("[data-basket-submit]").forEach((b) => (b.disabled = all.length === 0));
    }
    if (empty) empty.hidden = all.length > 0;
    countEls.forEach((c) => (c.textContent = all.length));
    if (totals) {
      if (!all.length) { totals.innerHTML = ""; }
      else {
        const minutes = Math.round(all.reduce((a, li) => a + parseFloat(li.dataset.min || 2), 0));
        const diff = [0, 0, 0];
        const topics = {};
        all.forEach((li) => { diff[(parseInt(li.dataset.d, 10) || 2) - 1] += 1; const t = li.dataset.topic || "—"; topics[t] = (topics[t] || 0) + 1; });
        const top = Object.entries(topics).sort((a, b) => b[1] - a[1]).slice(0, 4)
          .map(([t, n]) => `<span class="tag tag--line tag--xs">${esc(t)} ${Math.round((100 * n) / all.length)}%</span>`).join("");
        totals.innerHTML = `<div class="order-totals__line"><b>${all.length}</b> ${totals.dataset.q} · ~<b>${minutes}</b> ${totals.dataset.min}</div>
          <div class="order-totals__diff" title="${totals.dataset.diff}"><span class="pk-diff pk-diff--1"><i></i><i></i><i></i></span>${diff[0]}
            <span class="pk-diff pk-diff--2"><i></i><i></i><i></i></span>${diff[1]} <span class="pk-diff pk-diff--3"><i></i><i></i><i></i></span>${diff[2]}</div>
          <div class="chips">${top}</div>`;
      }
    }
    $$(".pk-check", root).forEach((cb) => { cb.checked = has(cb.value); cb.closest(".pk-row").classList.toggle("is-picked", cb.checked); });
  };
  const add = (it) => { if (has(it.id)) return false; const li = makeItem(it); list.appendChild(li); render(li); return true; };
  const remove = (id) => { const li = $(`li[data-id="${id}"]`, list); if (li) li.remove(); };

  if (list) {
    list.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      const li = btn.closest("li");
      if (btn.hasAttribute("data-remove")) li.remove();
      if (btn.dataset.move === "-1" && li.previousElementSibling) li.parentNode.insertBefore(li, li.previousElementSibling);
      if (btn.dataset.move === "1" && li.nextElementSibling) li.parentNode.insertBefore(li.nextElementSibling, li);
      sync();
    });
    // drag to reorder
    let dragging = null;
    list.addEventListener("dragstart", (e) => { dragging = e.target.closest("li"); if (dragging) { dragging.classList.add("is-dragging"); e.dataTransfer.effectAllowed = "move"; } });
    list.addEventListener("dragend", () => { if (dragging) dragging.classList.remove("is-dragging"); dragging = null; sync(); });
    list.addEventListener("dragover", (e) => {
      if (!dragging) return;
      e.preventDefault();
      const after = items().filter((li) => li !== dragging).find((li) => e.clientY < li.getBoundingClientRect().top + li.offsetHeight / 2);
      if (after) list.insertBefore(dragging, after); else list.appendChild(dragging);
    });
    const clear = $("[data-order-clear]");
    if (clear) clear.addEventListener("click", () => { items().forEach((li) => li.remove()); sync(); });
  }

  /* ------------------------------------------------------------ filters, tree, pages */
  const state = { exam: root.dataset.exam, q: "", sort: "tree", keys: [], page: 1 };
  const openSecs = new Set();
  const treeBox = $("[data-pk-tree]", root);
  const listBox = $("[data-pk-list]", root);
  const flash = $("[data-pk-flash]", root);
  const resetBtn = $("[data-pk-reset]", root);
  const randomLabel = $("[data-pk-random-label]", root);
  const params = () => {
    const p = new URLSearchParams({ exam: state.exam, q: state.q, sort: state.sort, page: state.page });
    state.keys.forEach((k) => p.append("k", k));
    $$("[data-pk-f]:checked", root).forEach((cb) => p.append(cb.dataset.pkF, cb.value));
    return p;
  };
  let seq = 0;
  const load = async () => {
    const my = ++seq;
    listBox.classList.add("is-loading");
    try {
      const res = await fetch(`${root.dataset.url}?${params()}`, { credentials: "same-origin" });
      const data = await res.json();
      if (my !== seq) return;
      treeBox.innerHTML = data.tree;
      $$("[data-pk-sec]", treeBox).forEach((sec) => { if (openSecs.has(sec.dataset.pkSec)) sec.classList.add("is-open"); else if (sec.classList.contains("is-open")) openSecs.add(sec.dataset.pkSec); });
      listBox.innerHTML = data.list;
      render(listBox);
      sync();
      const active = state.q || state.keys.length || $$("[data-pk-f]:checked", root).length || state.sort !== "tree";
      resetBtn.hidden = !active;
      randomLabel.textContent = state.keys.length ? randomLabel.dataset.node : randomLabel.dataset.all;
    } finally { listBox.classList.remove("is-loading"); }
  };
  const reload = () => { state.page = 1; load(); };

  root.addEventListener("change", (e) => {
    if (e.target.matches("[data-pk-f]")) reload();
    if (e.target.matches("[data-pk-sort]")) { state.sort = e.target.value; reload(); }
    if (e.target.matches("[data-pk-key]")) {
      const k = e.target.value;
      state.keys = e.target.checked ? [...state.keys, k] : state.keys.filter((x) => x !== k);
      reload();
    }
    if (e.target.matches("[data-pk-exam]")) {
      state.exam = e.target.value; state.keys = []; reload();
      const be = $("[data-basket-exam]"); if (be) be.value = state.exam;
    }
    if (e.target.matches(".pk-check")) {
      const cb = e.target;
      if (cb.checked) add({ id: cb.value, label: cb.dataset.label, topic: cb.dataset.topic, d: cb.dataset.d, min: cb.dataset.min });
      else remove(cb.value);
      sync();
    }
  });
  let timer = null;
  $("[data-pk-q]", root).addEventListener("input", (e) => { clearTimeout(timer); timer = setTimeout(() => { state.q = e.target.value.trim(); reload(); }, 300); });
  $("[data-pk-q]", root).addEventListener("keydown", (e) => { if (e.key === "Enter") e.preventDefault(); });
  root.addEventListener("click", async (e) => {
    if (e.target.closest("[data-pk-clear]")) { e.preventDefault(); state.keys = []; reload(); return; }
    const tog = e.target.closest("[data-pk-toggle]");
    if (tog) {
      const sec = tog.closest("[data-pk-sec]");
      sec.classList.toggle("is-open");
      if (sec.classList.contains("is-open")) openSecs.add(sec.dataset.pkSec); else openSecs.delete(sec.dataset.pkSec);
      return;
    }
    const pg = e.target.closest("[data-pk-page]");
    if (pg) { state.page = parseInt(pg.dataset.pkPage, 10); await load(); root.scrollIntoView({ block: "start", behavior: "smooth" }); return; }
    const pv = e.target.closest("[data-pk-preview]");
    if (pv) {
      const box = $("[data-pk-preview-box]", pv.closest(".pk-row"));
      const open = box.hidden;
      pv.setAttribute("aria-expanded", String(open));
      if (open && !box.dataset.loaded) {
        const res = await fetch(pv.dataset.pkPreview, { credentials: "same-origin" });
        box.innerHTML = await res.text(); box.dataset.loaded = "1"; render(box);
      }
      box.hidden = !open;
    }
  });
  resetBtn.addEventListener("click", () => {
    $$("[data-pk-f]", root).forEach((cb) => (cb.checked = false));
    $("[data-pk-q]", root).value = ""; $("[data-pk-sort]", root).value = "tree";
    Object.assign(state, { q: "", sort: "tree", keys: [] });
    reload();
  });

  const say = (text) => { flash.textContent = text; setTimeout(() => { if (flash.textContent === text) flash.textContent = ""; }, 3500); };
  const addMany = (arr) => { let n = 0; arr.forEach((it) => { if (add(it)) n += 1; }); sync(); return n; };
  $("[data-pk-random]", root).addEventListener("click", async () => {
    const p = params(); p.set("n", "5"); p.set("exclude", ids().join(","));
    const res = await fetch(`${root.dataset.random}?${p}`, { credentials: "same-origin" });
    const data = await res.json();
    say(`+${addMany(data.items)}`);
  });
  $("[data-pk-plan-go]", root).addEventListener("click", async () => {
    const p = params();
    p.set("per", $("[data-plan-per]", root).value); p.set("e", $("[data-plan-e]", root).value);
    p.set("m", $("[data-plan-m]", root).value); p.set("h", $("[data-plan-h]", root).value);
    p.set("exclude", ids().join(","));
    const res = await fetch(`${root.dataset.plan}?${p}`, { credentials: "same-origin" });
    const data = await res.json();
    $(".pk-plan", root).removeAttribute("open");
    say(`+${addMany(data.items)}`);
  });

  // the test editor's exam field drives the picker
  if (root.dataset.examField) {
    const sel = document.getElementById(root.dataset.examField);
    if (sel) sel.addEventListener("change", () => { state.exam = sel.value; state.keys = []; reload(); });
    if (sel) state.exam = sel.value;
  }
  sync();
  load();
})();

/* filter dropdowns: one open at a time, a click elsewhere closes them */
document.addEventListener("click", (e) => {
  document.querySelectorAll(".pk-drop[open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; });
});

/* work editor: two steps (description → questions) on one form */
(function () {
  const nav = document.querySelector("[data-we-steps]");
  if (!nav) return;
  const form = nav.closest("form");
  const steps = Array.from(form.querySelectorAll("[data-we-step]"));
  const show = (n) => {
    steps.forEach((s) => (s.hidden = s.dataset.weStep !== String(n)));
    nav.querySelectorAll("[data-we-go]").forEach((b) => b.classList.toggle("is-on", b.dataset.weGo === String(n)));
    window.scrollTo({ top: 0 });
  };
  nav.hidden = false;
  form.querySelectorAll("[data-we-next]").forEach((x) => (x.hidden = false));
  form.addEventListener("click", (e) => { const b = e.target.closest("[data-we-go]"); if (b) show(b.dataset.weGo); });
  // a required field on the hidden step: open that step so the browser can point at it
  form.addEventListener("invalid", (e) => { const s = e.target.closest("[data-we-step]"); if (s && s.hidden) show(s.dataset.weStep); }, true);
  show(nav.dataset.start || 1);
})();

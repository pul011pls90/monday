/* Monday — ranking of the Monday test.
 *
 * Top 3 on a podium of pixel columns (they assemble from falling squares, 1st place shimmers),
 * places 4–10 as rows with 10 score dots and the movement since the week before, the student's own
 * row with a progress fill and the gap to the next place. Страна / Область / Школа switch in place:
 * rows that stay move to their new positions (FLIP), new ones slide in. Everything starts when the
 * card scrolls into view; reduced motion shows the final state.
 */
(function () {
  "use strict";
  const card = document.querySelector("[data-rank]");
  if (!card) return;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let data = {};
  try { data = JSON.parse(card.querySelector("[data-rank-data]").textContent); } catch (e) { data = {}; }
  const T = card.dataset;
  const podium = card.querySelector("[data-podium]"), list = card.querySelector("[data-rk-list]");
  const more = card.querySelector("[data-rk-more]"), meBox = card.querySelector("[data-rk-me]");
  const fade = (color, a) => { const m = color.match(/[\d.]+/g) || [0, 0, 0]; return `rgba(${m[0]},${m[1]},${m[2]},${a})`; };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const delta = (d) => d === false ? "" : d === null || d === undefined ? `<span class="rk-delta rk-delta--new">${esc(T.tNew)}</span>`
    : d > 0 ? `<span class="rk-delta rk-delta--up">▲${d}</span>` : d < 0 ? `<span class="rk-delta rk-delta--down">▼${-d}</span>` : `<span class="rk-delta">–</span>`;
  const dots = (r) => `<span class="rk-dots" aria-hidden="true">${Array.from({ length: r.total }, (_, i) => `<i class="${i < r.score ? "is-on" : ""}" style="--d:${i}"></i>`).join("")}</span>`;

  function renderPodium(top) {
    const order = [top[1], top[0], top[2]];                 // 2nd · 1st · 3rd
    const heights = [7, 9, 5];
    podium.innerHTML = order.map((r, k) => {
      if (!r) return `<div class="rk-col rk-col--empty"></div>`;
      const h = heights[k], cols = 7;
      let sq = "";
      for (let y = 0; y < h; y++) for (let x = 0; x < cols; x++) sq += `<i style="--d:${(h - 1 - y) * 3 + x % 3}"></i>`;
      return `<div class="rk-col rk-col--${r.place}${r.me ? " is-me" : ""}" data-id="${r.id}" style="--h:${h}">
        <div class="rk-col__who"><b>${esc(r.me ? T.tYou : r.name)}</b><span>${esc(r.region)}</span>${delta(r.delta)}</div>
        <canvas class="rk-col__score" data-score="${r.score}/${r.total}" aria-hidden="true"></canvas>
        <span class="sr-only">${r.place}. ${esc(r.name)} — ${r.score}/${r.total}</span>
        <div class="rk-col__bar" style="--cols:${cols}">${sq}<em>${r.place}</em></div>
      </div>`;
    }).join("");
    const ink = getComputedStyle(card).color;   // follows the light / dark theme
    podium.querySelectorAll("[data-score]").forEach((c) => window.MondayPixel && window.MondayPixel(c, c.dataset.score, 3, ink, fade(ink, .1)));
  }
  function renderList(top) {
    list.innerHTML = top.slice(3).map((r, i) => `
      <li class="rk-row${r.me ? " is-me" : ""}" data-id="${r.id}" style="--i:${i}">
        <span class="rk-row__place">${r.place}</span>
        <span class="rk-row__who"><b>${esc(r.me ? T.tYou : r.name)}</b><span>${esc(r.region)}</span>${delta(r.delta)}</span>
        ${dots(r)}
        <span class="rk-row__score">${r.score}/${r.total}</span>
      </li>`).join("");
  }
  function renderMe(d) {
    const me = d.me;
    if (!me) { meBox.innerHTML = d.count ? `<p class="small muted">${esc(T.tNotin)}</p>` : ""; return; }
    const gap = d.gap ? (d.gap.tasks > 0 ? T.tGap.replace("{p}", d.gap.place).replace("{n}", d.gap.tasks) : T.tGaptime.replace("{p}", d.gap.place)) : T.tTop;
    meBox.innerHTML = `<div class="rk-me" style="--fill:${me.total ? me.score / me.total : 0}">
      <span class="rk-me__place">#${me.place}</span>
      <span class="rk-me__who"><b>${esc(T.tYou)}</b><span>${esc(me.region)}</span>${delta(me.delta)}</span>
      <span class="rk-me__gap">${esc(gap)}</span>
      <span class="rk-me__score">${me.score}/${me.total}</span>
    </div>`;
  }
  function render(scope, animate) {
    const d = data[scope] || { top: [], count: 0 };
    // FLIP: remember where rows were
    const before = new Map([...card.querySelectorAll("[data-id]")].map((el) => [el.dataset.id + el.className.split(" ")[0], el.getBoundingClientRect()]));
    renderPodium(d.top); renderList(d.top); renderMe(d);
    more.textContent = d.count > 10 ? T.tMore.replace("{n}", d.count - 10) : (d.count ? "" : T.tEmpty);
    card.classList.toggle("is-empty", !d.count);
    if (!animate || reduce) return;
    card.querySelectorAll("[data-id]").forEach((el) => {
      const was = before.get(el.dataset.id + el.className.split(" ")[0]);
      if (was) {
        const now = el.getBoundingClientRect();
        el.animate([{ transform: `translate(${was.left - now.left}px, ${was.top - now.top}px)` }, { transform: "none" }], { duration: 520, easing: "cubic-bezier(.2,.8,.2,1)" });
        el.classList.add("is-kept");
      }
    });
  }

  // segmented switch: the highlight slides to the chosen scope; no page reload
  const seg = card.querySelector(".seg-switch"), thumb = seg.querySelector(".seg-switch__thumb");
  const moveThumb = (a) => { thumb.style.width = a.offsetWidth + "px"; thumb.style.transform = `translateX(${a.offsetLeft}px)`; };
  const links = [...seg.querySelectorAll("[data-scope-link]")];
  links.forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    links.forEach((x) => x.setAttribute("aria-selected", String(x === a)));
    moveThumb(a); card.dataset.scope = a.dataset.scopeLink;
    render(a.dataset.scopeLink, true);
    try { history.replaceState(null, "", a.href); } catch (err) { /* ignore */ }
  }));
  const current = links.find((a) => a.getAttribute("aria-selected") === "true") || links[0];
  requestAnimationFrame(() => moveThumb(current));
  window.addEventListener("resize", () => moveThumb(links.find((a) => a.getAttribute("aria-selected") === "true") || links[0]));

  render(card.dataset.scope, false);
  // pixel numbers in the "last test" card
  const drawLast = () => document.querySelectorAll("[data-pixtext]").forEach((c) => {
    const cs = getComputedStyle(c.parentElement), ink = cs.color, acc = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#2747d8";
    window.MondayPixel && window.MondayPixel(c, c.dataset.pixtext, 5, c.hasAttribute("data-accent") ? acc : ink, fade(ink, .07));
  });
  drawLast();
  // redraw the pixel numbers when the theme changes
  new MutationObserver(() => { drawLast(); render(card.dataset.scope, false); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  // play the entrance once, when the cards scroll into view
  const play = (el) => el.classList.add("is-in");
  if (reduce || !("IntersectionObserver" in window)) { document.querySelectorAll(".rk, .rk-last, .rk-duel").forEach(play); return; }
  const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { play(e.target); io.unobserve(e.target); } }), { threshold: .25 });
  document.querySelectorAll(".rk, .rk-last, .rk-duel").forEach((el) => io.observe(el));
})();

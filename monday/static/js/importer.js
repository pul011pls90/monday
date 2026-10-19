/* Monday — paste import preview (live preview + problem flags) and the review queue keyboard. */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const LET = "АБВГДЕЖЗ";

  /* ------------------------------------------------------------ import preview */
  const form = $("[data-import]");
  if (form) {
    const cards = $$("[data-imp-q]", form);
    const render = (el) => { if (window.MondayRenderMath) window.MondayRenderMath(el); };
    const check = (card) => {
      const include = $("[data-imp-include]", card).checked;
      const isNum = $("[data-imp-type][value=number]", card).checked;
      const opts = $$("[data-imp-opt]", card).map((i) => i.value.trim());
      const right = $("input[type=radio][name$='-correct']:checked", card);
      const probs = {
        text: !$("[data-imp-text]", card).value.trim(),
        options: !isNum && opts.filter(Boolean).length < 2,
        answer: isNum ? !/^-?\d+([.,]\d+)?(\/\d+)?$/.test($("[data-imp-num]", card).value.trim()) : !(right && opts[parseInt(right.value, 10)]),
        skill: !$("[data-imp-skill]", card).value,
      };
      $$("[data-flag]", card).forEach((f) => { if (f.dataset.flag in probs) f.hidden = !probs[f.dataset.flag]; });
      const bad = Object.values(probs).some(Boolean);
      card.classList.toggle("has-problem", include && bad);
      card.classList.toggle("is-off", !include);
      return include ? (bad ? "bad" : "ok") : "off";
    };
    const summary = () => {
      const c = { ok: 0, bad: 0, off: 0 };
      cards.forEach((card) => (c[check(card)] += 1));
      $("[data-imp-ok]", form).textContent = c.ok; $("[data-imp-bad]", form).textContent = c.bad; $("[data-imp-off]", form).textContent = c.off;
    };
    const preview = (card) => {
      const pvText = $("[data-imp-pv-text]", card);
      pvText.textContent = $("[data-imp-text]", card).value;
      const isNum = $("[data-imp-type][value=number]", card).checked;
      const ol = $("[data-imp-pv-opts]", card);
      ol.innerHTML = "";
      if (!isNum) {
        const right = $("input[type=radio][name$='-correct']:checked", card);
        $$("[data-imp-opt]", card).forEach((inp, i) => {
          if (!inp.value.trim()) return;
          const li = document.createElement("li");
          if (right && parseInt(right.value, 10) === i) li.className = "is-right";
          li.innerHTML = `<b>${LET[i]}</b> <span class="math"></span>`;
          li.querySelector("span").textContent = inp.value;
          ol.appendChild(li);
        });
      }
      render(card.querySelector(".imp-q__preview"));
    };
    cards.forEach((card) => {
      const setType = () => {
        const isNum = $("[data-imp-type][value=number]", card).checked;
        $("[data-imp-choice]", card).hidden = isNum;
        $("[data-imp-number]", card).hidden = !isNum;
        $$("input[type=radio][name$='-correct']", card).forEach((r) => (r.disabled = isNum));
        const num = $("[data-imp-num]", card);
        if (isNum) num.name = num.id.replace("num", "correct"); else num.removeAttribute("name");
      };
      setType();
      let t = null;
      card.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { preview(card); summary(); }, 250); });
      card.addEventListener("change", (e) => { if (e.target.matches("[data-imp-type]")) setType(); preview(card); summary(); });
    });
    summary();
  }

  /* ------------------------------------------------------------ review queue keyboard */
  const queue = $("[data-review]");
  if (queue) {
    const cards = $$("[data-rv]", queue);
    let cur = 0;
    const focus = (i) => { cur = Math.max(0, Math.min(cards.length - 1, i)); cards[cur].focus(); cards[cur].scrollIntoView({ block: "center", behavior: "smooth" }); };
    document.addEventListener("keydown", (e) => {
      if (e.target.matches("input, textarea, select") || e.metaKey || e.ctrlKey) return;
      const k = e.key.toLowerCase();
      if (k === "j") focus(cur + 1);
      else if (k === "k") focus(cur - 1);
      else if (k === "a") $("[data-rv-approve]", cards[cur]).click();
      else if (k === "e") $("[data-rv-edit]", cards[cur]).click();
      else if (k === "r") { e.preventDefault(); $("[data-rv-note]", cards[cur]).focus(); }
      else return;
    });
    queue.addEventListener("focusin", (e) => { const c = e.target.closest("[data-rv]"); if (c) cur = cards.indexOf(c); });
  }
})();

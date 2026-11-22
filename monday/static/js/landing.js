/* Monday Academy — CSP-safe controller for public landing interactive tabs & mini-challenge. */
(function () {
  "use strict";

  const root = document.querySelector("[data-landing-challenge]");
  if (!root) return;

  // Smooth scroll from hero CTA to #try-challenge
  document.addEventListener("click", (e) => {
    const scrollBtn = e.target.closest("[data-scroll-challenge]");
    if (scrollBtn) {
      const target = document.getElementById("try-challenge");
      if (target) {
        e.preventDefault();
        const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        target.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      }
    }
  });

  const tabs = Array.from(root.querySelectorAll("[data-subject-tab]"));
  const panels = Array.from(root.querySelectorAll("[data-subject-panel]"));

  function activateTab(key) {
    tabs.forEach((btn) => {
      const active = btn.getAttribute("data-subject-tab") === key;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    panels.forEach((panel) => {
      const show = panel.getAttribute("data-subject-panel") === key;
      panel.hidden = !show;
    });
  }

  root.addEventListener("click", (e) => {
    const tabBtn = e.target.closest("[data-subject-tab]");
    if (tabBtn) {
      activateTab(tabBtn.getAttribute("data-subject-tab"));
      return;
    }

    const optBtn = e.target.closest("[data-challenge-opt]");
    if (!optBtn) return;

    const panel = optBtn.closest("[data-subject-panel]");
    if (!panel) return;

    const allOpts = Array.from(panel.querySelectorAll("[data-challenge-opt]"));
    const isCorrect = optBtn.getAttribute("data-correct") === "true";

    allOpts.forEach((btn) => {
      btn.classList.remove("is-right", "is-wrong", "is-dimmed");
      if (btn.getAttribute("data-correct") === "true") {
        btn.classList.add("is-right");
      } else if (btn === optBtn && !isCorrect) {
        btn.classList.add("is-wrong");
      } else {
        btn.classList.add("is-dimmed");
      }
      btn.setAttribute("aria-pressed", btn === optBtn ? "true" : "false");
    });

    const explainEl = panel.querySelector("[data-challenge-explain]");
    const statusEl = panel.querySelector("[data-challenge-status]");
    if (statusEl) {
      statusEl.textContent = isCorrect
        ? statusEl.getAttribute("data-ok-text") || "Верно!"
        : statusEl.getAttribute("data-bad-text") || "Почти! Посмотри решение ниже:";
      statusEl.className = "br-explain__status " + (isCorrect ? "is-ok" : "is-bad");
    }
    if (explainEl) {
      explainEl.hidden = false;
    }
  });
})();

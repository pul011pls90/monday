/* Monday Academy — CSP-safe controller for public landing page & floating header. */
(function () {
  "use strict";

  function prefersReducedMotion() {
    return Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function smoothScrollTo(selectorOrEl) {
    const target =
      typeof selectorOrEl === "string"
        ? document.querySelector(selectorOrEl)
        : selectorOrEl;
    if (!target) return false;
    target.scrollIntoView({
      behavior: prefersReducedMotion() ? "auto" : "smooth",
      block: "start",
    });
    return true;
  }

  // 1. Floating Pill Header Mobile Menu Toggle
  const navToggle = document.querySelector("[data-nav-toggle]");
  const navPanel = document.querySelector("[data-nav-panel]");
  if (navToggle && navPanel) {
    navToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      const willOpen = navPanel.hidden;
      navPanel.hidden = !willOpen;
      navToggle.setAttribute("aria-expanded", willOpen ? "true" : "false");
    });

    document.addEventListener("click", (e) => {
      if (navPanel.hidden) return;
      if (!navPanel.contains(e.target) && !navToggle.contains(e.target)) {
        navPanel.hidden = true;
        navToggle.setAttribute("aria-expanded", "false");
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !navPanel.hidden) {
        navPanel.hidden = true;
        navToggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  // 2. Horizontal Exam Strip Left/Right Scroll Buttons
  document.querySelectorAll("[data-strip]").forEach((strip) => {
    const track = strip.querySelector("[data-strip-track]");
    if (!track) return;
    strip.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-strip-scroll]");
      if (!btn) return;
      const dir = btn.getAttribute("data-strip-scroll") === "left" ? -1 : 1;
      track.scrollBy({
        left: dir * 280,
        behavior: prefersReducedMotion() ? "auto" : "smooth",
      });
    });
  });

  // 2b. FAQ Accordion smooth toggle (closes sibling items when opening a new question)
  document.querySelectorAll("[data-faq-list]").forEach((faqList) => {
    const items = Array.from(faqList.querySelectorAll("details[data-faq-item]"));
    items.forEach((detail) => {
      detail.addEventListener("toggle", () => {
        if (!detail.open) return;
        items.forEach((other) => {
          if (other !== detail && other.open) {
            other.open = false;
          }
        });
      });
    });
  });

  // 3. Sandbox Mode Switcher (Математика | Экзамены) + Exam Subject Tabs
  const root = document.querySelector("[data-landing-challenge]");
  const modeBtns = root ? Array.from(root.querySelectorAll("[data-mode-btn]")) : [];
  const modePanels = root ? Array.from(root.querySelectorAll("[data-mode-panel]")) : [];
  const subjectTabs = root ? Array.from(root.querySelectorAll("[data-subject-tab]")) : [];
  const subjectPanels = root ? Array.from(root.querySelectorAll("[data-subject-panel]")) : [];

  function activateMode(modeKey) {
    if (!root || !modeKey) return;
    modeBtns.forEach((btn) => {
      const active = btn.getAttribute("data-mode-btn") === modeKey;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
      btn.setAttribute("tabindex", active ? "0" : "-1");
    });
    modePanels.forEach((panel) => {
      const show = panel.getAttribute("data-mode-panel") === modeKey;
      panel.hidden = !show;
    });
  }

  function activateSubjectTab(tabKey) {
    if (!root || !tabKey) return;
    subjectTabs.forEach((btn) => {
      const active = btn.getAttribute("data-subject-tab") === tabKey;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    subjectPanels.forEach((panel) => {
      const show = panel.getAttribute("data-subject-panel") === tabKey;
      panel.hidden = !show;
    });
  }

  // 4. Global smooth-scroll & Fanned Hero Card click-to-challenge
  document.addEventListener("click", (e) => {
    const heroCard = e.target.closest("[data-hero-card]");
    if (heroCard) {
      e.preventDefault();
      const targetMode = heroCard.getAttribute("data-challenge-mode") || "math";
      const targetTab = heroCard.getAttribute("data-challenge-tab");
      activateMode(targetMode);
      if (targetTab) {
        activateSubjectTab(targetTab);
      }
      smoothScrollTo("#try-challenge");
      return;
    }

    const scrollTrigger = e.target.closest("[data-scroll-to], [data-scroll-challenge]");
    if (scrollTrigger) {
      const sel = scrollTrigger.getAttribute("data-scroll-to") || "#try-challenge";
      if (smoothScrollTo(sel)) {
        e.preventDefault();
      }
    }
  });

  if (!root) return;

  // 5. Interactive Tile-Slot Algebra Builder (Mode 1: Математика)
  const builder = root.querySelector("[data-tile-builder]");
  if (builder) {
    const slots = Array.from(builder.querySelectorAll("[data-slot]"));
    const tiles = Array.from(builder.querySelectorAll("[data-tile]"));
    const explainEl = builder.querySelector("[data-tiles-explain]");
    const statusEl = builder.querySelector("[data-tiles-status]");

    function clearValidation() {
      slots.forEach((s) => s.classList.remove("is-right", "is-wrong"));
      if (explainEl) explainEl.hidden = true;
    }

    function evaluateSlots() {
      const allFilled = slots.every((s) => Boolean(s.getAttribute("data-value")));
      if (!allFilled) {
        clearValidation();
        return;
      }

      // Linear group slots (accept "2x 4x" without duplicate use of same term)
      const linSlots = slots.filter((s) => s.getAttribute("data-group") === "lin");
      const linValues = linSlots.map((s) => s.getAttribute("data-value"));
      const has2x = linValues.includes("2x");
      const has4x = linValues.includes("4x");

      let allCorrect = true;
      slots.forEach((slot) => {
        const val = slot.getAttribute("data-value") || "";
        const accepted = (slot.getAttribute("data-accept") || "").split(/\s+/).filter(Boolean);
        let slotOk = accepted.includes(val);
        if (slot.getAttribute("data-group") === "lin" && !(has2x && has4x)) {
          // If duplicate or missing linear partner, mark only slots not matching distinct 2x/4x
          const firstIdx = linValues.indexOf(val);
          const myIdx = linSlots.indexOf(slot);
          if (!accepted.includes(val) || firstIdx !== myIdx) {
            slotOk = false;
          }
        }
        slot.classList.toggle("is-right", slotOk);
        slot.classList.toggle("is-wrong", !slotOk);
        if (!slotOk) allCorrect = false;
      });

      if (statusEl) {
        statusEl.textContent = allCorrect
          ? statusEl.getAttribute("data-ok-text") || "Верно!"
          : statusEl.getAttribute("data-bad-text") || "Почти! Проверьте выделенные места:";
        statusEl.className = "br-explain__status " + (allCorrect ? "is-ok" : "is-bad");
      }
      if (explainEl) {
        explainEl.hidden = false;
      }
    }

    function resetBuilder() {
      slots.forEach((slot) => {
        slot.textContent = "?";
        slot.removeAttribute("data-value");
        slot.removeAttribute("data-tile-index");
        slot.classList.remove("is-filled", "is-right", "is-wrong");
      });
      tiles.forEach((tile) => {
        tile.disabled = false;
        tile.classList.remove("is-used");
      });
      if (explainEl) explainEl.hidden = true;
    }

    builder.addEventListener("click", (e) => {
      const resetBtn = e.target.closest("[data-tiles-reset]");
      if (resetBtn) {
        resetBuilder();
        return;
      }

      const slotBtn = e.target.closest("[data-slot]");
      if (slotBtn) {
        const tileIdx = slotBtn.getAttribute("data-tile-index");
        if (tileIdx !== null && tileIdx !== "") {
          const originTile = tiles[Number(tileIdx)];
          if (originTile) {
            originTile.disabled = false;
            originTile.classList.remove("is-used");
          }
        }
        slotBtn.textContent = "?";
        slotBtn.removeAttribute("data-value");
        slotBtn.removeAttribute("data-tile-index");
        slotBtn.classList.remove("is-filled", "is-right", "is-wrong");
        clearValidation();
        return;
      }

      const tileBtn = e.target.closest("[data-tile]");
      if (tileBtn && !tileBtn.disabled) {
        const emptySlot = slots.find((s) => !s.getAttribute("data-value"));
        if (!emptySlot) return;
        const val = tileBtn.getAttribute("data-tile") || tileBtn.textContent.trim();
        const tIdx = tiles.indexOf(tileBtn);
        emptySlot.textContent = val;
        emptySlot.setAttribute("data-value", val);
        emptySlot.setAttribute("data-tile-index", String(tIdx));
        emptySlot.classList.add("is-filled");
        tileBtn.disabled = true;
        tileBtn.classList.add("is-used");
        evaluateSlots();
      }
    });
  }

  // 6. Mode Switcher & Exam Mini-Problems (Mode 2: Экзамены)
  root.addEventListener("click", (e) => {
    const modeBtn = e.target.closest("[data-mode-btn]");
    if (modeBtn) {
      activateMode(modeBtn.getAttribute("data-mode-btn"));
      return;
    }

    const tabBtn = e.target.closest("[data-subject-tab]");
    if (tabBtn) {
      activateSubjectTab(tabBtn.getAttribute("data-subject-tab"));
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

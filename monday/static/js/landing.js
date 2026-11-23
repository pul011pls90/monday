/* Monday Academy — CSP-safe controller for public landing page, live hero question, stats counters, ORT mini-test & header. */
(function () {
  "use strict";

  function prefersReducedMotion() {
    return (
      Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) ||
      document.documentElement.getAttribute("data-motion") === "reduce" ||
      Boolean(navigator.connection && navigator.connection.saveData)
    );
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

  // 2. FAQ Accordion smooth toggle
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

  // 3. Stage 2 Live Hero & Exam-Page Public Sample Question Cards ([data-hero-question-card])
  document.querySelectorAll("[data-hero-question-card]").forEach((card) => {
    const checkUrl = card.getAttribute("data-check-url");
    if (!checkUrl) return;

    card.addEventListener("click", (e) => {
      const optBtn = e.target.closest("[data-live-opt]");
      if (!optBtn) return;

      const token = card.getAttribute("data-q-token") || "";
      const choice = optBtn.getAttribute("data-live-opt");
      if (!token || choice === null) return;

      const allOpts = Array.from(card.querySelectorAll("[data-live-opt]"));
      const feedbackEl = card.querySelector("[data-live-feedback]");
      const statusEl = card.querySelector("[data-live-status]");
      const ctaEl = card.querySelector("[data-live-cta]");
      const badgeEl = card.querySelector("[data-live-badge]");

      const csrfMeta = document.querySelector('meta[name="csrf-token"]');
      const headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "fetch",
      };
      if (csrfMeta && csrfMeta.content) {
        headers["X-CSRFToken"] = csrfMeta.content;
      }

      fetch(checkUrl, {
        method: "POST",
        headers,
        body: JSON.stringify({ token, choice: Number(choice) }),
      })
        .then((r) => r.json())
        .then((data) => {
          if (!data || !data.ok) return;
          if (data.correct) {
            allOpts.forEach((b) => {
              b.classList.remove("is-right", "is-wrong", "is-dimmed");
              b.classList.add(b === optBtn ? "is-right" : "is-dimmed");
              b.setAttribute("aria-pressed", b === optBtn ? "true" : "false");
            });
            if (badgeEl && data.badge) {
              badgeEl.textContent = data.badge;
            }
            if (statusEl) {
              statusEl.textContent = data.badge || "Верно!";
              statusEl.className = "br-explain__status is-ok";
            }
            if (ctaEl && data.exam_url) {
              ctaEl.setAttribute("href", data.exam_url);
              ctaEl.hidden = false;
            }
            if (feedbackEl) feedbackEl.hidden = false;
            if (window.__mondayDotEngine && typeof window.__mondayDotEngine.pulseFeedback === "function") {
              window.__mondayDotEngine.pulseFeedback("ok");
            }
          } else {
            optBtn.classList.remove("is-right");
            optBtn.classList.add("is-wrong");
            if (statusEl) {
              statusEl.textContent = data.hint || "Попробуйте выбрать другой вариант.";
              statusEl.className = "br-explain__status is-bad";
            }
            if (ctaEl) ctaEl.hidden = true;
            if (feedbackEl) feedbackEl.hidden = false;
            if (window.__mondayDotEngine && typeof window.__mondayDotEngine.pulseFeedback === "function") {
              window.__mondayDotEngine.pulseFeedback("warn");
            }
          }
        })
        .catch(() => {});
    });
  });

  // 4. Stage 3 Live Counters Strip Scroll-Triggered Animation ([data-public-stats-strip])
  document.querySelectorAll("[data-public-stats-strip]").forEach((strip) => {
    const counters = Array.from(strip.querySelectorAll("[data-count-to]"));
    if (!counters.length || prefersReducedMotion()) return;

    let animated = false;
    function runCountUp() {
      if (animated) return;
      animated = true;
      const duration = 620;
      const start = performance.now();
      const targets = counters.map((el) => ({
        el,
        to: Math.max(0, parseInt(el.getAttribute("data-count-to") || "0", 10) || 0),
      }));

      function step(now) {
        const t = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - t, 3);
        targets.forEach((item) => {
          item.el.textContent = String(Math.round(item.to * eased));
        });
        if (t < 1) {
          window.requestAnimationFrame(step);
        }
      }
      window.requestAnimationFrame(step);
    }

    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              runCountUp();
              io.disconnect();
            }
          });
        },
        { threshold: 0.15 }
      );
      io.observe(strip);
    } else {
      runCountUp();
    }
  });

  // 5. Sandbox Mode Switcher (Мини-тест ОРТ | По темам) + Subject Tabs + ORT Mini-Test
  const root = document.querySelector("[data-landing-challenge]");
  const modeBtns = root ? Array.from(root.querySelectorAll("[data-mode-btn]")) : [];
  const modePanels = root ? Array.from(root.querySelectorAll("[data-mode-panel]")) : [];
  const subjectTabs = root ? Array.from(root.querySelectorAll("[data-subject-tab]")) : [];
  const subjectPanels = root ? Array.from(root.querySelectorAll("[data-subject-panel]")) : [];

  const ortRoot = root ? root.querySelector("[data-ort-minitest]") : null;
  const ortSteps = ortRoot ? Array.from(ortRoot.querySelectorAll("[data-ort-step]")) : [];
  const ortCards = ortRoot ? Array.from(ortRoot.querySelectorAll("[data-ort-q]")) : [];
  const ortProgress = ortRoot ? ortRoot.querySelector("[data-ort-progress]") : null;

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

  function activateOrtQuestion(indexStr) {
    if (!ortRoot) return;
    const key = String(indexStr);
    ortSteps.forEach((btn) => {
      const active = btn.getAttribute("data-ort-step") === key;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    ortCards.forEach((card) => {
      const show = card.getAttribute("data-ort-q") === key;
      card.hidden = !show;
    });
    if (ortProgress && ortCards.length) {
      const idxNum = Number(key) + 1;
      ortProgress.textContent = idxNum + " / " + ortCards.length;
    }
  }

  // 6. Global smooth-scroll & Fanned Hero Card click-to-challenge
  document.addEventListener("click", (e) => {
    const heroCard = e.target.closest("[data-hero-card]");
    if (heroCard) {
      e.preventDefault();
      const targetMode = heroCard.getAttribute("data-challenge-mode") || "ort";
      const targetTab = heroCard.getAttribute("data-challenge-tab");
      const targetOrt = heroCard.getAttribute("data-ort-goto");
      activateMode(targetMode);
      if (targetTab) {
        activateSubjectTab(targetTab);
      }
      if (targetOrt !== null && targetOrt !== "") {
        activateOrtQuestion(targetOrt);
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

  // 7. Authentic ORT Mini-Test Bubble Sheet Controller (Mode 1: Мини-тест ОРТ)
  if (ortRoot) {
    ortRoot.addEventListener("click", (e) => {
      const stepBtn = e.target.closest("[data-ort-step]");
      if (stepBtn) {
        activateOrtQuestion(stepBtn.getAttribute("data-ort-step"));
        return;
      }

      const nextBtn = e.target.closest("[data-ort-next]");
      if (nextBtn) {
        activateOrtQuestion(nextBtn.getAttribute("data-ort-next"));
        return;
      }

      const bubbleBtn = e.target.closest("[data-ort-bubble]");
      if (!bubbleBtn) return;

      const qCard = bubbleBtn.closest("[data-ort-q]");
      if (!qCard) return;

      const qIdx = qCard.getAttribute("data-ort-q");
      const allBubbles = Array.from(qCard.querySelectorAll("[data-ort-bubble]"));
      const isCorrect = bubbleBtn.getAttribute("data-correct") === "true";

      allBubbles.forEach((b) => {
        b.classList.remove("is-selected", "is-right", "is-wrong");
        if (b === bubbleBtn) {
          b.classList.add("is-selected", isCorrect ? "is-right" : "is-wrong");
        } else if (b.getAttribute("data-correct") === "true") {
          b.classList.add("is-right");
        }
        b.setAttribute("aria-pressed", b === bubbleBtn ? "true" : "false");
      });

      const stepDot = ortSteps.find((s) => s.getAttribute("data-ort-step") === qIdx);
      if (stepDot) {
        stepDot.classList.toggle("is-ok", isCorrect);
        stepDot.classList.toggle("is-bad", !isCorrect);
      }

      const explainEl = qCard.querySelector("[data-ort-explain]");
      const statusEl = qCard.querySelector("[data-ort-status]");
      if (statusEl) {
        statusEl.textContent = isCorrect
          ? statusEl.getAttribute("data-ok-text") || "Верно!"
          : statusEl.getAttribute("data-bad-text") || "Почти! Посмотрите разбор:";
        statusEl.className = "br-explain__status " + (isCorrect ? "is-ok" : "is-bad");
      }
      if (explainEl) {
        explainEl.hidden = false;
      }
    });
  }

  // 8. Mode Switcher & Topic Mini-Problems (Mode 2: По темам)
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

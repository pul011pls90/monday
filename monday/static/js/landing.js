/* Monday Academy — CSP-safe controller for public landing page:
 * - FAQ accordion
 * - Unified ORT mini-test bubble sheet controller
 * - Pre-footer sun & clouds scroll reveal (IntersectionObserver)
 * - Exam-page public sample question check ([data-hero-question-card] on /exams/<slug>)
 * - Smooth anchor scrolling.
 */
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

  // 1. FAQ Accordion smooth toggle (closes sibling items when opening a new question)
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

  // 2. Pre-footer Sun & Clouds Reveal on Scroll (mobile/touch + desktop bottom scroll)
  const ctaReveal = document.querySelector("[data-cta-reveal]");
  if (ctaReveal) {
    if (prefersReducedMotion() || !("IntersectionObserver" in window)) {
      ctaReveal.classList.add("is-revealed");
    } else {
      const ctaIo = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              ctaReveal.classList.add("is-revealed");
            }
          });
        },
        { threshold: 0.22 }
      );
      ctaIo.observe(ctaReveal);
    }
  }

  // 3. Exam-Page Public Sample Question Cards ([data-hero-question-card] on /exams/<slug>)
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

  // 4. Unified Authentic ORT Mini-Test Bubble Sheet Controller
  const root = document.querySelector("[data-landing-challenge]");
  const ortRoot = root ? root.querySelector("[data-ort-minitest]") : null;
  const ortSteps = ortRoot ? Array.from(ortRoot.querySelectorAll("[data-ort-step]")) : [];
  const ortCards = ortRoot ? Array.from(ortRoot.querySelectorAll("[data-ort-q]")) : [];
  const ortProgress = ortRoot ? ortRoot.querySelector("[data-ort-progress]") : null;

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

  // 5. Global smooth-scroll & Fanned Hero Card click-to-challenge
  document.addEventListener("click", (e) => {
    const heroCard = e.target.closest("[data-hero-card]");
    if (heroCard) {
      e.preventDefault();
      const targetOrt = heroCard.getAttribute("data-ort-goto");
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

  if (!ortRoot) return;

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
})();

/* Monday Academy — CSP-safe controller for public landing page:
 * - Compact chrome height sync (navbar + optional admin preview bar)
 * - Sticky 3-chapter hero tracker (01 / 02 / 03)
 * - 3-layer math background (parallax topic emblems + scroll-drawn curve fallback)
 * - Duolingo-style dotted SVG route line in page gutter
 * - Fine-pointer-only card tilt & keyboard/touch topic emblem labels
 * - Live stats counters, Monday Test countdown, exam-page sample checks, ORT mini-test & header.
 */
(function () {
  "use strict";

  const isSaveData = Boolean(navigator.connection && navigator.connection.saveData);
  if (isSaveData) {
    document.documentElement.setAttribute("data-save-data", "1");
  }

  function prefersReducedMotion() {
    return (
      Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) ||
      document.documentElement.getAttribute("data-motion") === "reduce" ||
      isSaveData
    );
  }

  function isFinePointer() {
    return Boolean(window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches);
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

  // 0. Sync exact navbar + admin preview banner + marquee heights into CSS variables
  function syncChromeHeights() {
    const rootStyle = document.documentElement.style;
    const hdr = document.querySelector(".mp-header");
    const prev = document.querySelector("[data-preview-bar]");
    const dock = document.querySelector(".mp-strip--hero-dock");
    if (hdr) {
      rootStyle.setProperty("--mp-header-h", Math.round(hdr.getBoundingClientRect().height) + "px");
    }
    rootStyle.setProperty("--mp-preview-h", prev ? Math.round(prev.getBoundingClientRect().height) + "px" : "0px");
    if (dock) {
      rootStyle.setProperty("--mp-marquee-h", Math.round(dock.getBoundingClientRect().height) + "px");
    }
    const heroStage = document.querySelector("[data-hero-stage]");
    if (heroStage) {
      const screens = parseFloat(heroStage.getAttribute("data-hero-screens") || "3");
      if (Number.isFinite(screens) && screens >= 1 && screens <= 6) {
        heroStage.style.setProperty("--hero-screens", String(screens));
      }
    }
  }
  syncChromeHeights();
  let resizeRaf = 0;
  window.addEventListener(
    "resize",
    () => {
      if (resizeRaf) return;
      resizeRaf = window.requestAnimationFrame(() => {
        resizeRaf = 0;
        syncChromeHeights();
      });
    },
    { passive: true }
  );

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

  // 3. Sticky 3-Chapter Hero Progress Marker (01 / 02 / 03)
  const heroStage = document.querySelector("[data-hero-stage]");
  if (heroStage) {
    const chapters = Array.from(heroStage.querySelectorAll("[data-hero-chapter]"));
    const numEl = heroStage.querySelector("[data-chapter-num]");
    const labelEl = heroStage.querySelector("[data-chapter-label]");
    const stepBtns = Array.from(heroStage.querySelectorAll("[data-chapter-trigger]"));

    function setActiveChapter(idx) {
      const clamped = Math.max(0, Math.min(chapters.length - 1, Number(idx) || 0));
      const pad = String(clamped + 1).padStart(2, "0");
      if (numEl) numEl.textContent = pad;
      const chEl = chapters[clamped];
      if (labelEl && chEl) {
        labelEl.textContent = chEl.getAttribute("data-chapter-title") || "";
      }
      stepBtns.forEach((btn) => {
        const active = Number(btn.getAttribute("data-chapter-trigger")) === clamped;
        btn.classList.toggle("is-active", active);
        if (active) {
          btn.setAttribute("aria-current", "step");
        } else {
          btn.removeAttribute("aria-current");
        }
      });
      chapters.forEach((c, i) => {
        c.classList.toggle("is-active-chapter", i === clamped);
        if (i <= clamped) c.classList.add("is-inview");
      });
    }

    if ("IntersectionObserver" in window && chapters.length) {
      const chIo = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              const idx = entry.target.getAttribute("data-hero-chapter");
              setActiveChapter(idx);
            }
          });
        },
        { rootMargin: "-35% 0px -45% 0px", threshold: 0.05 }
      );
      chapters.forEach((ch) => chIo.observe(ch));
    }
  }

  // 4. Interactive Real-DB Topic Emblems (Hover, Keyboard Focus, Tap + Stats API Refresh)
  const topicLayer = document.querySelector("[data-topic-emblems]");
  const topicEmblems = topicLayer ? Array.from(topicLayer.querySelectorAll("[data-topic-emblem]")) : [];
  if (topicLayer && topicEmblems.length) {
    function closeAllEmblems(exceptEl) {
      topicEmblems.forEach((btn) => {
        if (btn === exceptEl) return;
        btn.classList.remove("is-open");
        btn.setAttribute("aria-expanded", "false");
      });
    }

    topicEmblems.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const willOpen = !btn.classList.contains("is-open");
        closeAllEmblems(willOpen ? btn : null);
        btn.classList.toggle("is-open", willOpen);
        btn.setAttribute("aria-expanded", willOpen ? "true" : "false");
      });
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest("[data-topic-emblem]")) {
        closeAllEmblems(null);
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeAllEmblems(null);
      }
    });

    // Hydrate cached per-topic question counts from /api/public/stats (respects threshold gating)
    const statsUrl = topicLayer.getAttribute("data-stats-url");
    if (statsUrl && !isSaveData) {
      fetch(statsUrl, { headers: { "X-Requested-With": "fetch" } })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (!data || !data.ok || !Array.isArray(data.topics)) return;
          data.topics.forEach((t) => {
            const cntEl = topicLayer.querySelector('[data-topic-count="' + CSS.escape(String(t.code)) + '"]');
            const btnEl = topicLayer.querySelector('[data-topic-emblem="' + CSS.escape(String(t.code)) + '"]');
            if (!cntEl) return;
            if (typeof t.count === "number") {
              cntEl.textContent = String(t.count) + " зад.";
              cntEl.hidden = false;
              if (btnEl && t.label) {
                btnEl.setAttribute("aria-label", t.label + " — " + t.count + " задач");
              }
            } else {
              cntEl.hidden = true;
            }
          });
        })
        .catch(() => {});
    }
  }

  // 5. Scroll Engine: Background Parallax (3 speeds), Curve Draw Fallback, & Route Line Progress
  const mathBg = document.querySelector("[data-math-bg]");
  const routeGutter = document.querySelector("[data-route-gutter]");
  const routeFill = routeGutter ? routeGutter.querySelector("[data-route-fill]") : null;
  const routeNodes = routeGutter ? Array.from(routeGutter.querySelectorAll("[data-route-node]")) : [];
  const routeSections = Array.from(document.querySelectorAll("[data-route-section]"));
  const supportsScrollTimeline =
    typeof CSS !== "undefined" && typeof CSS.supports === "function" && CSS.supports("animation-timeline", "scroll()");

  let scrollRaf = 0;
  let tabHidden = Boolean(document.hidden);

  document.addEventListener("visibilitychange", () => {
    tabHidden = Boolean(document.hidden);
  });

  function updateScrollVisuals() {
    scrollRaf = 0;
    if (tabHidden || prefersReducedMotion()) return;

    const scrollY = window.scrollY || window.pageYOffset || 0;
    const maxScroll = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    const progress = Math.max(0, Math.min(1, scrollY / maxScroll));

    // Layer C fallback if CSS animation-timeline: scroll() is not supported
    if (mathBg && !supportsScrollTimeline) {
      mathBg.style.setProperty("--curve-progress", progress.toFixed(4));
    }

    // Layer B 3-speed parallax (desktop margin lanes only)
    if (topicEmblems.length && window.innerWidth > 1340) {
      const speedPx = { "1": 0.06, "2": 0.11, "3": 0.16 };
      topicEmblems.forEach((btn) => {
        const sp = speedPx[btn.getAttribute("data-parallax-speed") || "1"] || 0.08;
        const offset = Math.max(-140, Math.min(140, -scrollY * sp));
        btn.style.setProperty("--parallax-y", offset.toFixed(1) + "px");
      });
    }

    // Route Line fill progress (desktop >= 1280px only)
    if (routeFill && window.innerWidth >= 1280) {
      routeFill.style.setProperty("--route-progress", progress.toFixed(4));
    }
  }

  if (!prefersReducedMotion() && (mathBg || routeGutter)) {
    window.addEventListener(
      "scroll",
      () => {
        if (scrollRaf || tabHidden) return;
        scrollRaf = window.requestAnimationFrame(updateScrollVisuals);
      },
      { passive: true }
    );
    updateScrollVisuals();
  }

  // Route Line milestone node lighting via IntersectionObserver
  if (routeNodes.length && routeSections.length && "IntersectionObserver" in window && !prefersReducedMotion()) {
    const order = routeNodes.map((n) => n.getAttribute("data-route-node"));
    function markRouteActive(key) {
      const activeIdx = order.indexOf(key);
      if (activeIdx < 0) return;
      routeNodes.forEach((node, idx) => {
        node.classList.toggle("is-active", idx === activeIdx);
        node.classList.toggle("is-passed", idx < activeIdx);
        if (idx === activeIdx) {
          node.setAttribute("aria-current", "location");
        } else {
          node.removeAttribute("aria-current");
        }
      });
    }

    const routeIo = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            markRouteActive(entry.target.getAttribute("data-route-section"));
          }
        });
      },
      { rootMargin: "-28% 0px -55% 0px", threshold: 0.01 }
    );
    routeSections.forEach((sec) => routeIo.observe(sec));
  }

  // 6. Fine-Pointer-Only 3D Tilt on Cards ([data-tilt-card])
  if (isFinePointer() && !prefersReducedMotion()) {
    document.querySelectorAll("[data-tilt-card]").forEach((card) => {
      let tiltRaf = 0;
      let nextRx = 0;
      let nextRy = 0;

      card.addEventListener("pointermove", (e) => {
        if (e.pointerType !== "mouse" && e.pointerType !== "pen") return;
        const rect = card.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        const px = (e.clientX - rect.left) / rect.width - 0.5;
        const py = (e.clientY - rect.top) / rect.height - 0.5;
        nextRx = (-py * 7).toFixed(2);
        nextRy = (px * 7).toFixed(2);
        if (tiltRaf) return;
        tiltRaf = window.requestAnimationFrame(() => {
          tiltRaf = 0;
          card.style.setProperty("--tilt-x", nextRx + "deg");
          card.style.setProperty("--tilt-y", nextRy + "deg");
        });
      });

      card.addEventListener("pointerleave", () => {
        card.style.setProperty("--tilt-x", "0deg");
        card.style.setProperty("--tilt-y", "0deg");
      });
    });
  }

  // 7. Live Monday Test Countdown (only runs when schedule is rendered)
  const countdownEls = Array.from(document.querySelectorAll("[data-monday-countdown]"));
  if (countdownEls.length) {
    function refreshCountdowns() {
      const now = Date.now();
      countdownEls.forEach((el) => {
        const iso = el.getAttribute("data-monday-countdown");
        const target = iso ? Date.parse(iso) : NaN;
        if (!Number.isFinite(target)) return;
        const diffMs = Math.max(0, target - now);
        const totalMin = Math.floor(diffMs / 60000);
        const days = Math.floor(totalMin / 1440);
        const hrs = Math.floor((totalMin % 1440) / 60);
        const mins = totalMin % 60;
        if (days > 0) {
          el.textContent = days + "д " + hrs + "ч " + mins + "м";
        } else {
          el.textContent = hrs + "ч " + mins + "м";
        }
      });
    }
    refreshCountdowns();
    window.setInterval(() => {
      if (!tabHidden) refreshCountdowns();
    }, 60000);
  }

  // 8. Exam-Page Public Sample Question Cards ([data-hero-question-card] on /exams/<slug>)
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

  // 9. Live Counters Strip Scroll-Triggered Animation ([data-public-stats-strip])
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

  // 10. Sandbox Mode Switcher (Мини-тест ОРТ | По темам) + Subject Tabs + ORT Mini-Test
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

  // 11. Global smooth-scroll & Chapter Math Card click-to-challenge
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

  // 12. Authentic ORT Mini-Test Bubble Sheet Controller (Mode 1: Мини-тест ОРТ)
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

  // 13. Mode Switcher & Topic Mini-Problems (Mode 2: По темам)
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

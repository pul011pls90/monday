/* Monday Academy — CSP-safe controller for public landing page:
 * - FAQ accordion
 * - 4-tab Interactive Sandbox Switcher (Bank Filter, Training Session Drill, ORT Mini-Test, Formula Reference + Trig Angles)
 * - Pre-footer sun & clouds scroll reveal (IntersectionObserver)
 * - Exam-page public sample question check ([data-hero-question-card] on /exams/<slug>)
 * - Smooth anchor scrolling.
 */
(function () {
  "use strict";

  function prefersReducedMotion() {
    return Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function renderMath(el) {
    if (!el || typeof window.renderMathInElement !== "function") return;
    try {
      window.renderMathInElement(el, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false },
        ],
        throwOnError: false,
      });
    } catch (_err) {
      // KaTeX auto-render fallback: keep raw text cleanly visible
    }
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

  // 4. Interactive 4-Tab Sandbox Controller (#try-challenge)
  const root = document.querySelector("[data-landing-challenge]");
  const demoTabs = root ? Array.from(root.querySelectorAll("[data-demo-tab]")) : [];
  const demoPanels = root ? Array.from(root.querySelectorAll("[data-demo-panel]")) : [];

  function activateDemoTab(tabKey) {
    if (!demoTabs.length) return;
    demoTabs.forEach((btn) => {
      const active = btn.getAttribute("data-demo-tab") === tabKey;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    demoPanels.forEach((panel) => {
      const show = panel.getAttribute("data-demo-panel") === tabKey;
      panel.hidden = !show;
      if (show) {
        renderMath(panel);
      }
    });
  }

  demoTabs.forEach((tabBtn, idx) => {
    tabBtn.addEventListener("click", () => {
      activateDemoTab(tabBtn.getAttribute("data-demo-tab"));
    });
    tabBtn.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      const delta = e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : -1;
      const nextTab = demoTabs[(idx + delta + demoTabs.length) % demoTabs.length];
      if (nextTab) {
        activateDemoTab(nextTab.getAttribute("data-demo-tab"));
        nextTab.focus();
      }
    });
  });

  // 4A. Tab 1: Question Bank Mini-Filter & Runner
  const bankRoot = root ? root.querySelector("[data-bank-demo]") : null;
  if (bankRoot) {
    const EXAM_LABELS = { ORT: "ОРТ", SAT: "SAT", EGE: "ЕГЭ" };
    const TOPIC_LABELS = { alg: "Алгебра", geo: "Геометрия" };
    const DIFF_LABELS = { easy: "Базовая", medium: "Средняя" };

    const BANK_QUESTIONS = {
      "ORT:alg:easy": {
        prompt: "Найдите значение $x$, если $4x - 7 = 21$.",
        options: ["$5$", "$6$", "$7$", "$8$"],
        correct: 2,
        steps: [
          "Прибавим $7$ к обеим частям уравнения: $4x = 28$.",
          "Разделим обе части на $4$: $x = 7$.",
        ],
      },
      "ORT:alg:medium": {
        prompt: "Если $\\frac{x + 3}{2} = \\frac{2x - 1}{3}$, чему равно $x$?",
        options: ["$9$", "$11$", "$13$", "$7$"],
        correct: 1,
        steps: [
          "Перемножим крест-накрест: $3(x + 3) = 2(2x - 1) \\Rightarrow 3x + 9 = 4x - 2$.",
          "Перенесём слагаемые: $x = 9 + 2 = 11$.",
        ],
      },
      "ORT:geo:easy": {
        prompt: "Два угла треугольника равны $48^\\circ$ и $67^\\circ$. Найдите третий угол.",
        options: ["$55^\\circ$", "$65^\\circ$", "$75^\\circ$", "$85^\\circ$"],
        correct: 1,
        steps: [
          "Сумма внутренних углов треугольника всегда равна $180^\\circ$.",
          "Вычитаем: $180^\\circ - (48^\\circ + 67^\\circ) = 180^\\circ - 115^\\circ = 65^\\circ$.",
        ],
      },
      "ORT:geo:medium": {
        prompt: "Периметр квадрата равен $36$. Найдите длину его диагонали.",
        options: ["$9$", "$9\\sqrt{2}$", "$12\\sqrt{2}$", "$18$"],
        correct: 1,
        steps: [
          "Сторона квадрата равна $a = 36 / 4 = 9$.",
          "Диагональ квадрата равна $d = a\\sqrt{2} = 9\\sqrt{2}$.",
        ],
      },
      "SAT:alg:easy": {
        prompt: "If $f(x) = 3x - 5$, what is the value of $f(4)$?",
        options: ["$5$", "$7$", "$12$", "$17$"],
        correct: 1,
        steps: [
          "Подставим $x = 4$ в выражение функции: $f(4) = 3(4) - 5$.",
          "Вычисляем: $12 - 5 = 7$.",
        ],
      },
      "SAT:alg:medium": {
        prompt: "The equation $x^2 - 8x + 15 = 0$ has solutions $r$ and $s$. What is $r + s$?",
        options: ["$-8$", "$8$", "$15$", "$23$"],
        correct: 1,
        steps: [
          "По теореме Виета для $ax^2 + bx + c = 0$ сумма корней равна $-b / a$.",
          "Здесь $a = 1$, $b = -8$, поэтому $r + s = -(-8)/1 = 8$.",
        ],
      },
      "SAT:geo:easy": {
        prompt: "A circle has radius $r = 6$. What is its area?",
        options: ["$12\\pi$", "$24\\pi$", "$36\\pi$", "$72\\pi$"],
        correct: 2,
        steps: [
          "Используем формулу площади круга: $S = \\pi r^2$.",
          "Подставляем $r = 6$: $S = \\pi \\cdot 6^2 = 36\\pi$.",
        ],
      },
      "SAT:geo:medium": {
        prompt: "In a right triangle, the legs are $5$ and $12$. What is $\\sin\\theta$ opposite the leg of length $5$?",
        options: ["$\\frac{5}{12}$", "$\\frac{5}{13}$", "$\\frac{12}{13}$", "$\\frac{13}{5}$"],
        correct: 1,
        steps: [
          "Найдём гипотенузу по теореме Пифагора: $c = \\sqrt{5^2 + 12^2} = \\sqrt{169} = 13$.",
          "Синус — отношение противолежащего катета к гипотенузе: $\\sin\\theta = \\frac{5}{13}$.",
        ],
      },
      "EGE:alg:easy": {
        prompt: "Найдите корень уравнения $\\log_2(x - 3) = 4$.",
        options: ["$11$", "$13$", "$19$", "$21$"],
        correct: 2,
        steps: [
          "По определению логарифма $x - 3 = 2^4 = 16$.",
          "Отсюда $x = 16 + 3 = 19$ (проверка: $19 - 3 > 0$).",
        ],
      },
      "EGE:alg:medium": {
        prompt: "Найдите значение выражения $\\frac{3^{7} \\cdot 3^{5}}{3^{9}}$.",
        options: ["$9$", "$27$", "$81$", "$243$"],
        correct: 1,
        steps: [
          "При умножении степени складываются: $3^7 \\cdot 3^5 = 3^{12}$.",
          "При делении показатели вычитаются: $3^{12 - 9} = 3^3 = 27$.",
        ],
      },
      "EGE:geo:easy": {
        prompt: "Основания трапеции равны $7$ и $13$, а высота равна $4$. Найдите площадь трапеции.",
        options: ["$28$", "$40$", "$52$", "$80$"],
        correct: 1,
        steps: [
          "Площадь трапеции равна полусумме оснований, умноженной на высоту: $S = \\frac{a + b}{2} \\cdot h$.",
          "Подставляем значения: $S = \\frac{7 + 13}{2} \\cdot 4 = 10 \\cdot 4 = 40$.",
        ],
      },
      "EGE:geo:medium": {
        prompt: "В равнобедренном треугольнике угол при вершине равен $120^\\circ$, а боковая сторона — $6$. Найдите высоту к основанию.",
        options: ["$3$", "$3\\sqrt{2}$", "$3\\sqrt{3}$", "$6$"],
        correct: 0,
        steps: [
          "Высота к основанию делит угол при вершине пополам: $120^\\circ / 2 = 60^\\circ$.",
          "В прямоугольном треугольнике $h = 6 \\cdot \\cos 60^\\circ = 6 \\cdot \\frac{1}{2} = 3$.",
        ],
      },
    };

    const bankState = { exam: "ORT", topic: "alg", diff: "easy" };
    const metaEl = bankRoot.querySelector("[data-bank-meta]");
    const promptEl = bankRoot.querySelector("[data-bank-prompt]");
    const optsEl = bankRoot.querySelector("[data-bank-opts]");
    const explainEl = bankRoot.querySelector("[data-bank-explain]");
    const statusEl = bankRoot.querySelector("[data-bank-status]");
    const stepsEl = bankRoot.querySelector("[data-bank-steps]");
    const cardEl = bankRoot.querySelector("[data-bank-card]");

    function renderBankQuestion(pulse) {
      const key = bankState.exam + ":" + bankState.topic + ":" + bankState.diff;
      const item = BANK_QUESTIONS[key] || BANK_QUESTIONS["ORT:alg:easy"];
      if (metaEl) {
        metaEl.textContent =
          EXAM_LABELS[bankState.exam] +
          " · " +
          TOPIC_LABELS[bankState.topic] +
          " · " +
          DIFF_LABELS[bankState.diff];
      }
      if (promptEl) {
        promptEl.textContent = item.prompt;
      }
      if (optsEl) {
        optsEl.textContent = "";
        const letters = ["A", "B", "C", "D"];
        item.options.forEach((optText, idx) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "br-opt";
          btn.setAttribute("data-bank-opt", String(idx));
          btn.textContent = letters[idx] + ") " + optText;
          optsEl.appendChild(btn);
        });
      }
      if (explainEl) explainEl.hidden = true;
      if (stepsEl) {
        stepsEl.textContent = "";
        item.steps.forEach((stepTxt) => {
          const li = document.createElement("li");
          li.textContent = stepTxt;
          stepsEl.appendChild(li);
        });
      }
      if (cardEl) {
        renderMath(cardEl);
        if (pulse) {
          cardEl.classList.remove("is-pulse");
          void cardEl.offsetWidth;
          cardEl.classList.add("is-pulse");
          window.setTimeout(() => cardEl.classList.remove("is-pulse"), 450);
        }
      }
    }

    bankRoot.addEventListener("click", (e) => {
      const chip = e.target.closest("[data-bank-filter]");
      if (chip) {
        const group = chip.getAttribute("data-bank-filter");
        const val = chip.getAttribute("data-value");
        if (group && val) {
          bankState[group] = val;
          bankRoot.querySelectorAll('[data-bank-filter="' + group + '"]').forEach((b) => {
            const active = b === chip;
            b.classList.toggle("is-active", active);
            b.setAttribute("aria-pressed", active ? "true" : "false");
          });
          renderBankQuestion(false);
        }
        return;
      }

      if (e.target.closest("[data-bank-show]")) {
        renderBankQuestion(true);
        return;
      }

      const optBtn = e.target.closest("[data-bank-opt]");
      if (!optBtn) return;

      const key = bankState.exam + ":" + bankState.topic + ":" + bankState.diff;
      const item = BANK_QUESTIONS[key] || BANK_QUESTIONS["ORT:alg:easy"];
      const chosenIdx = Number(optBtn.getAttribute("data-bank-opt"));
      const isRight = chosenIdx === item.correct;
      const allOpts = Array.from(bankRoot.querySelectorAll("[data-bank-opt]"));

      allOpts.forEach((b, idx) => {
        b.classList.remove("is-right", "is-wrong", "is-dimmed");
        if (idx === item.correct) {
          b.classList.add("is-right");
        } else if (idx === chosenIdx) {
          b.classList.add("is-wrong");
        } else {
          b.classList.add("is-dimmed");
        }
      });

      if (statusEl) {
        statusEl.textContent = isRight
          ? "Верно! Отличная точность."
          : "Почти! Посмотрите разбор в 2 шага:";
        statusEl.className = "br-explain__status " + (isRight ? "is-ok" : "is-bad");
      }
      if (explainEl) {
        explainEl.hidden = false;
        renderMath(explainEl);
      }
    });

    renderBankQuestion(false);
  }

  // 4B. Tab 2: Mini Training Session Launcher & 3-Question Drill
  const sessionRoot = root ? root.querySelector("[data-session-demo]") : null;
  if (sessionRoot) {
    const SESSION_MODES = {
      weak: {
        title: "Слабые темы · 5 мин",
        questions: [
          {
            prompt: "Сколько процентов составляет $18$ от $75$?",
            options: ["$20\\%$", "$24\\%$", "$25\\%$", "$30\\%$"],
            correct: 1,
            note: "$\\frac{18}{75} \\cdot 100\\% = \\frac{6}{25} \\cdot 100\\% = 24\\%$.",
          },
          {
            prompt: "Решите уравнение $5(x - 2) = 3x + 6$.",
            options: ["$4$", "$6$", "$8$", "$10$"],
            correct: 2,
            note: "Раскрываем скобки: $5x - 10 = 3x + 6 \\Rightarrow 2x = 16 \\Rightarrow x = 8$.",
          },
          {
            prompt: "Площадь прямоугольника равна $48$, а одна сторона равна $6$. Найдите периметр.",
            options: ["$24$", "$28$", "$32$", "$36$"],
            correct: 1,
            note: "Вторая сторона равна $48 / 6 = 8$, значит периметр $P = 2(6 + 8) = 28$.",
          },
        ],
      },
      mistakes: {
        title: "Работа над ошибками",
        questions: [
          {
            prompt: "Чему равно значение выражения $(-3)^2 - 3^2$?",
            options: ["$-18$", "$0$", "$9$", "$18$"],
            correct: 1,
            note: "$(-3)^2 = 9$, а $-3^2 = -9$. Их сумма: $9 - 9 = 0$.",
          },
          {
            prompt: "Упростите $\\sqrt{16 + 9}$.",
            options: ["$5$", "$7$", "$12$", "$25$"],
            correct: 0,
            note: "Сначала складываем под корнем: $\\sqrt{25} = 5$ (нельзя разбивать сумму под корнем!).",
          },
          {
            prompt: "При каком $x$ дробь $\\frac{x + 2}{x - 5}$ не определена?",
            options: ["$-2$", "$0$", "$5$", "$2$"],
            correct: 2,
            note: "Знаменатель не может быть равен нулю: $x - 5 = 0 \\Rightarrow x = 5$.",
          },
        ],
      },
      hard: {
        title: "Сложные задачи",
        questions: [
          {
            prompt: "При каком значении $k$ уравнение $x^2 - 6x + k = 0$ имеет ровно один корень?",
            options: ["$3$", "$6$", "$9$", "$12$"],
            correct: 2,
            note: "Дискриминант должен быть равен $0$: $D = (-6)^2 - 4k = 36 - 4k = 0 \\Rightarrow k = 9$.",
          },
          {
            prompt: "Вычислите $\\log_3 27 + \\log_2 \\frac{1}{8}$.",
            options: ["$-1$", "$0$", "$1$", "$6$"],
            correct: 1,
            note: "$\\log_3 27 = 3$, а $\\log_2(2^{-3}) = -3$. Сумма равна $3 - 3 = 0$.",
          },
          {
            prompt: "Ребро куба увеличили в $2$ раза. Во сколько раз увеличился его объём?",
            options: ["$2$", "$4$", "$6$", "$8$"],
            correct: 3,
            note: "Объём куба $V = a^3$, значит $(2a)^3 = 8a^3$ — объём вырос в $8$ раз.",
          },
        ],
      },
    };

    const launcherEl = sessionRoot.querySelector("[data-session-launcher]");
    const drillEl = sessionRoot.querySelector("[data-session-drill]");
    const summaryEl = sessionRoot.querySelector("[data-session-summary]");
    const badgeEl = sessionRoot.querySelector("[data-session-badge]");
    const modeNameEl = sessionRoot.querySelector("[data-drill-mode-name]");
    const stepLblEl = sessionRoot.querySelector("[data-drill-step-label]");
    const progressEl = sessionRoot.querySelector("[data-drill-progress]");
    const promptEl = sessionRoot.querySelector("[data-drill-prompt]");
    const optsEl = sessionRoot.querySelector("[data-drill-opts]");
    const explainEl = sessionRoot.querySelector("[data-drill-explain]");
    const statusEl = sessionRoot.querySelector("[data-drill-status]");
    const noteEl = sessionRoot.querySelector("[data-drill-note]");
    const nextBtn = sessionRoot.querySelector("[data-drill-next]");
    const scoreEl = sessionRoot.querySelector("[data-drill-score]");
    const summaryMsgEl = sessionRoot.querySelector("[data-drill-summary-msg]");

    const drillState = { mode: "weak", idx: 0, score: 0, answered: false };

    function showSessionView(viewName) {
      if (launcherEl) launcherEl.hidden = viewName !== "launcher";
      if (drillEl) drillEl.hidden = viewName !== "drill";
      if (summaryEl) summaryEl.hidden = viewName !== "summary";
    }

    function renderDrillQuestion() {
      const cfg = SESSION_MODES[drillState.mode] || SESSION_MODES.weak;
      const q = cfg.questions[drillState.idx];
      drillState.answered = false;

      if (modeNameEl) modeNameEl.textContent = cfg.title;
      if (stepLblEl) stepLblEl.textContent = (drillState.idx + 1) + " / " + cfg.questions.length;
      if (badgeEl) badgeEl.textContent = "Вопрос " + (drillState.idx + 1) + " из " + cfg.questions.length;
      if (progressEl) progressEl.setAttribute("data-drill-progress", String(drillState.idx + 1));
      if (promptEl) promptEl.textContent = q.prompt;
      if (optsEl) {
        optsEl.textContent = "";
        const letters = ["A", "B", "C", "D"];
        q.options.forEach((optText, i) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "br-opt";
          btn.setAttribute("data-drill-opt", String(i));
          btn.textContent = letters[i] + ") " + optText;
          optsEl.appendChild(btn);
        });
      }
      if (explainEl) explainEl.hidden = true;
      if (nextBtn) {
        nextBtn.textContent =
          drillState.idx === cfg.questions.length - 1
            ? "Показать результат →"
            : "Следующий вопрос →";
      }
      if (drillEl) renderMath(drillEl);
    }

    sessionRoot.addEventListener("click", (e) => {
      const modeBtn = e.target.closest("[data-session-mode]");
      if (modeBtn) {
        drillState.mode = modeBtn.getAttribute("data-session-mode") || "weak";
        sessionRoot.querySelectorAll("[data-session-mode]").forEach((b) => {
          const active = b === modeBtn;
          b.classList.toggle("is-active", active);
          b.setAttribute("aria-pressed", active ? "true" : "false");
        });
        return;
      }

      if (e.target.closest("[data-session-start]")) {
        drillState.idx = 0;
        drillState.score = 0;
        showSessionView("drill");
        renderDrillQuestion();
        return;
      }

      if (e.target.closest("[data-session-restart]")) {
        if (badgeEl) badgeEl.textContent = "3 задачи · 5 мин";
        showSessionView("launcher");
        return;
      }

      const optBtn = e.target.closest("[data-drill-opt]");
      if (optBtn && !drillState.answered) {
        const cfg = SESSION_MODES[drillState.mode] || SESSION_MODES.weak;
        const q = cfg.questions[drillState.idx];
        const chosen = Number(optBtn.getAttribute("data-drill-opt"));
        const isRight = chosen === q.correct;
        drillState.answered = true;
        if (isRight) drillState.score += 1;

        Array.from(sessionRoot.querySelectorAll("[data-drill-opt]")).forEach((b, i) => {
          b.disabled = true;
          if (i === q.correct) {
            b.classList.add("is-right");
          } else if (i === chosen) {
            b.classList.add("is-wrong");
          } else {
            b.classList.add("is-dimmed");
          }
        });

        if (statusEl) {
          statusEl.textContent = isRight ? "Верно! +1 к серии." : "Не совсем — разобрали решение:";
          statusEl.className = "br-explain__status " + (isRight ? "is-ok" : "is-bad");
        }
        if (noteEl) noteEl.textContent = q.note;
        if (explainEl) {
          explainEl.hidden = false;
          renderMath(explainEl);
        }
        return;
      }

      if (e.target.closest("[data-drill-next]")) {
        const cfg = SESSION_MODES[drillState.mode] || SESSION_MODES.weak;
        if (drillState.idx + 1 < cfg.questions.length) {
          drillState.idx += 1;
          renderDrillQuestion();
        } else {
          if (badgeEl) badgeEl.textContent = "Завершено";
          if (scoreEl) scoreEl.textContent = "Результат: " + drillState.score + " / " + cfg.questions.length;
          if (summaryMsgEl) {
            summaryMsgEl.textContent =
              drillState.score === cfg.questions.length
                ? "Идеально! Все задачи решены без ошибок — в личном кабинете Monday строит ещё более точную траекторию."
                : "Отличная разминка! Ошибки из сессии автоматически попадают в ваш журнал работы над ошибками.";
          }
          showSessionView("summary");
        }
      }
    });
  }

  // 4C. Tab 3 (Default): Unified Authentic ORT Mini-Test Bubble Sheet Controller
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
      if (show) renderMath(card);
    });
    if (ortProgress && ortCards.length) {
      const idxNum = Number(key) + 1;
      ortProgress.textContent = idxNum + " / " + ortCards.length;
    }
  }

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

  // 4D. Tab 4: Formula Reference Categories + Interactive Trig Angle Switcher
  const formulasRoot = root ? root.querySelector("[data-formulas-demo]") : null;
  if (formulasRoot) {
    const TRIG_VALUES = {
      "30": { sin: "$\\frac{1}{2}$", cos: "$\\frac{\\sqrt{3}}{2}$", tan: "$\\frac{\\sqrt{3}}{3}$" },
      "45": { sin: "$\\frac{\\sqrt{2}}{2}$", cos: "$\\frac{\\sqrt{2}}{2}$", tan: "$1$" },
      "60": { sin: "$\\frac{\\sqrt{3}}{2}$", cos: "$\\frac{1}{2}$", tan: "$\\sqrt{3}$" },
      "90": { sin: "$1$", cos: "$0$", tan: "не опр." },
    };

    const sinEl = formulasRoot.querySelector("[data-trig-sin]");
    const cosEl = formulasRoot.querySelector("[data-trig-cos]");
    const tanEl = formulasRoot.querySelector("[data-trig-tan]");
    const trigBox = formulasRoot.querySelector("[data-trig-widget]");

    formulasRoot.addEventListener("click", (e) => {
      const catBtn = e.target.closest("[data-formula-cat]");
      if (catBtn) {
        const cat = catBtn.getAttribute("data-formula-cat");
        formulasRoot.querySelectorAll("[data-formula-cat]").forEach((b) => {
          const active = b === catBtn;
          b.classList.toggle("is-active", active);
          b.setAttribute("aria-selected", active ? "true" : "false");
        });
        formulasRoot.querySelectorAll("[data-formula-panel]").forEach((p) => {
          const show = p.getAttribute("data-formula-panel") === cat;
          p.hidden = !show;
          if (show) renderMath(p);
        });
        return;
      }

      const angleBtn = e.target.closest("[data-trig-angle]");
      if (angleBtn) {
        const deg = angleBtn.getAttribute("data-trig-angle") || "30";
        const vals = TRIG_VALUES[deg] || TRIG_VALUES["30"];
        formulasRoot.querySelectorAll("[data-trig-angle]").forEach((b) => {
          const active = b === angleBtn;
          b.classList.toggle("is-active", active);
          b.setAttribute("aria-pressed", active ? "true" : "false");
        });
        if (sinEl) sinEl.textContent = vals.sin;
        if (cosEl) cosEl.textContent = vals.cos;
        if (tanEl) tanEl.textContent = vals.tan;
        if (trigBox) renderMath(trigBox);
      }
    });
  }

  // Ensure deferred KaTeX auto-render catches dynamically initialized content after page load
  window.addEventListener("load", () => {
    if (root) renderMath(root);
  });

  // 5. Global smooth-scroll & Fanned Hero Card click-to-challenge
  document.addEventListener("click", (e) => {
    const heroCard = e.target.closest("[data-hero-card]");
    if (heroCard) {
      e.preventDefault();
      activateDemoTab("tests");
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
})();

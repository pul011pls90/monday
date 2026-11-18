/* Monday — Student-View Question Redactor Modal + Simple Math Preview + Symbol Keyboard */
(function () {
  "use strict";

  const SYM_TO_LATEX = {
    "≤": "\\le ",
    "≥": "\\ge ",
    "≠": "\\neq ",
    "≈": "\\approx ",
    "±": "\\pm ",
    "·": "\\cdot ",
    "×": "\\times ",
    "÷": "\\div ",
    "∞": "\\infty ",
    "π": "\\pi ",
    "α": "\\alpha ",
    "β": "\\beta ",
    "γ": "\\gamma ",
    "θ": "\\theta ",
    "°": "^{\\circ}",
  };

  const convertExprToLatex = (expr) => {
    let s = String(expr || "").trim();
    s = s.replace(/\(([^()]+)\)\s*\/\s*\(([^()]+)\)/g, (_, a, b) => `\\frac{${a.trim()}}{${b.trim()}}`);
    s = s.replace(/\(([^()]+)\)\s*\/\s*([A-Za-z0-9]+)/g, (_, a, b) => `\\frac{${a.trim()}}{${b.trim()}}`);
    s = s.replace(/([A-Za-z0-9]+)\s*\/\s*\(([^()]+)\)/g, (_, a, b) => `\\frac{${a.trim()}}{${b.trim()}}`);
    s = s.replace(/([A-Za-z0-9]+)\s*\/\s*([A-Za-z0-9]+)/g, (_, a, b) => `\\frac{${a}}{${b}}`);
    s = s.replace(/√\s*\(([^()]+)\)/g, (_, a) => `\\sqrt{${a.trim()}}`);
    s = s.replace(/√\s*([A-Za-z0-9]+)/g, (_, a) => `\\sqrt{${a}}`);
    s = s.replace(/\^\(([^()]+)\)/g, (_, a) => `^{${a.trim()}}`);
    s = s.replace(/\^([A-Za-z0-9]+)/g, (_, a) => `^{${a}}`);
    s = s.replace(/_\(([^()]+)\)/g, (_, a) => `_{${a.trim()}}`);
    s = s.replace(/_([A-Za-z0-9]+)/g, (_, a) => `_{${a}}`);
    Object.entries(SYM_TO_LATEX).forEach(([sym, tex]) => {
      s = s.split(sym).join(tex);
    });
    return s.replace(/\s+/g, " ").trim();
  };

  const MATH_HINT_RE = /(\d+\s*\/\s*\d+|[A-Za-z0-9]\s*\/\s*[A-Za-z0-9]|√|\^|_|[≤≥≠≈±·×÷∞παβγθ°])/;
  const PROSE_SPAN_RE = /(\(?[A-Za-z0-9√][A-Za-z0-9√^_°παβγθ]*\)?(?:\s*[+\-*/=<>≤≥≠≈±·×÷]\s*\(?[A-Za-z0-9√][A-Za-z0-9√^_°παβγθ]*\)?)+|[A-Za-z0-9]+\/[A-Za-z0-9]+|√\([^()]+\)|√[A-Za-z0-9]+|[A-Za-z0-9]+\^\([^()]+\)|[A-Za-z0-9]+\^[A-Za-z0-9]+|[≤≥≠≈±∞παβγθ°]+)/g;

  const plainToLatex = (raw, isOption) => {
    const s = String(raw || "").trim();
    if (!s || s.includes("$")) return s;
    if (isOption) {
      return MATH_HINT_RE.test(s) ? `$${convertExprToLatex(s)}$` : s;
    }
    return s.replace(PROSE_SPAN_RE, (span) => {
      const t = span.trim();
      if (/^\d+$/.test(t)) return span;
      if (!MATH_HINT_RE.test(t) && !/[+\-*/=]/.test(t)) return span;
      return `$${convertExprToLatex(t)}$`;
    });
  };

  const wireLivePreview = (scope) => {
    const root = scope.querySelector("[data-redact-root]");
    if (!root) return;

    const pText = root.querySelector("[data-preview-text]");
    const pExplain = root.querySelector("[data-preview-explain]");
    const pExplainWrap = root.querySelector("[data-preview-explain-wrap]");
    const pAns = root.querySelector("[data-preview-answer]");

    let activeField = root.querySelector("[data-rd-text]");
    root.querySelectorAll("input[type='text'], input:not([type]), textarea").forEach((el) => {
      el.addEventListener("focus", () => { activeField = el; });
    });

    // Little symbol keyboard inserts at cursor position
    root.querySelectorAll("[data-math-kbd] [data-insert]").forEach((btn) => {
      btn.addEventListener("mousedown", (e) => e.preventDefault());
      btn.addEventListener("click", () => {
        const target = activeField || root.querySelector("[data-rd-text]");
        if (!target) return;
        const ins = btn.dataset.insert || "";
        const start = target.selectionStart ?? target.value.length;
        const end = target.selectionEnd ?? target.value.length;
        target.value = target.value.slice(0, start) + ins + target.value.slice(end);
        target.focus();
        target.setSelectionRange(start + ins.length, start + ins.length);
        target.dispatchEvent(new Event("input", { bubbles: true }));
      });
    });

    const renderMath = (el) => {
      if (el && window.MondayRenderMath) window.MondayRenderMath(el);
    };

    const inText = root.querySelector("[data-rd-text]");
    if (inText && pText) {
      inText.addEventListener("input", () => {
        pText.textContent = plainToLatex(inText.value, false) || "Задача с рисунком";
        renderMath(pText);
      });
    }

    const inExplain = root.querySelector("[data-rd-explain]");
    if (inExplain && pExplain && pExplainWrap) {
      inExplain.addEventListener("input", () => {
        const val = inExplain.value.trim();
        pExplainWrap.hidden = !val;
        pExplain.textContent = plainToLatex(val, false);
        renderMath(pExplain);
      });
    }

    const inAns = root.querySelector("[data-rd-answer]");
    if (inAns && pAns) {
      inAns.addEventListener("input", () => {
        pAns.textContent = plainToLatex(inAns.value, true);
        renderMath(pAns);
      });
    }

    root.querySelectorAll("[data-rd-opt]").forEach((inp) => {
      inp.addEventListener("input", () => {
        const idx = inp.dataset.rdOpt;
        const target = root.querySelector(`[data-preview-opt="${idx}"]`);
        if (target) {
          target.textContent = plainToLatex(inp.value, true);
          renderMath(target);
        }
      });
    });

    root.querySelectorAll("[data-rd-correct]").forEach((radio) => {
      radio.addEventListener("change", () => {
        const chosen = radio.value;
        root.querySelectorAll("[data-preview-opt-box]").forEach((box) => {
          box.classList.toggle("is-correct", box.dataset.previewOptBox === chosen);
        });
      });
    });

    renderMath(root);
  };

  const ensureModal = () => {
    let backdrop = document.querySelector("[data-q-redact-modal]");
    if (backdrop) return backdrop;
    backdrop = document.createElement("div");
    backdrop.className = "q-redact-backdrop";
    backdrop.setAttribute("data-q-redact-modal", "");
    backdrop.hidden = true;
    backdrop.innerHTML = `
      <div class="q-redact-dialog" role="dialog" aria-modal="true" aria-label="Исправление вопроса">
        <div class="q-redact-dialog__head">
          <h2>Исправление вопроса (вид ученика)</h2>
          <button type="button" class="icon-btn icon-btn--xs" data-redact-close aria-label="Закрыть">×</button>
        </div>
        <div class="q-redact-dialog__body" data-redact-body></div>
      </div>`;
    document.body.appendChild(backdrop);

    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop || e.target.closest("[data-redact-close]")) {
        backdrop.hidden = true;
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !backdrop.hidden) backdrop.hidden = true;
    });
    return backdrop;
  };

  document.addEventListener("click", async (e) => {
    const trigger = e.target.closest("[data-redact-url]");
    if (!trigger) return;
    e.preventDefault();
    const url = trigger.dataset.redactUrl;
    const modal = ensureModal();
    const body = modal.querySelector("[data-redact-body]");
    body.innerHTML = '<p class="small muted">Загрузка вопроса…</p>';
    modal.hidden = false;

    try {
      const res = await fetch(`${url}?modal=1`, { credentials: "same-origin" });
      if (!res.ok) throw new Error();
      body.innerHTML = await res.text();
      wireLivePreview(body);

      const form = body.querySelector("[data-redact-form]");
      const errBox = body.querySelector("[data-rd-error]");
      const okBox = body.querySelector("[data-rd-ok]");
      const subBtn = body.querySelector("[data-rd-submit]");
      if (form) {
        form.addEventListener("submit", async (ev) => {
          ev.preventDefault();
          if (errBox) errBox.hidden = true;
          if (okBox) okBox.hidden = true;
          if (subBtn) subBtn.disabled = true;
          try {
            const postRes = await fetch(form.action, {
              method: "POST",
              credentials: "same-origin",
              headers: { "X-Requested-With": "fetch" },
              body: new FormData(form),
            });
            const data = await postRes.json();
            if (!postRes.ok || !data.ok) {
              if (errBox) {
                errBox.textContent = data.error || "Не удалось отправить правку.";
                errBox.hidden = false;
              }
            } else {
              if (okBox) {
                okBox.textContent = data.message || "Правка отправлена администратору.";
                okBox.hidden = false;
              }
              setTimeout(() => { modal.hidden = true; }, 1100);
            }
          } catch (_) {
            if (errBox) {
              errBox.textContent = "Ошибка сети. Попробуйте ещё раз.";
              errBox.hidden = false;
            }
          } finally {
            if (subBtn) subBtn.disabled = false;
          }
        });
      }
    } catch (_) {
      window.location.href = url;
    }
  });

  // Wire standalone page if opened directly
  wireLivePreview(document);
})();

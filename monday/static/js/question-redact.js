/* Monday — Student-View Question Redactor Modal + Live Preview */
(function () {
  "use strict";

  const wireLivePreview = (scope) => {
    const root = scope.querySelector("[data-redact-root]");
    if (!root) return;

    const pText = root.querySelector("[data-preview-text]");
    const pExplain = root.querySelector("[data-preview-explain]");
    const pExplainWrap = root.querySelector("[data-preview-explain-wrap]");
    const pAns = root.querySelector("[data-preview-answer]");

    const renderMath = (el) => {
      if (el && window.MondayRenderMath) window.MondayRenderMath(el);
    };

    const inText = root.querySelector("[data-rd-text]");
    if (inText && pText) {
      inText.addEventListener("input", () => {
        pText.textContent = inText.value || "Задача с рисунком";
        renderMath(pText);
      });
    }

    const inExplain = root.querySelector("[data-rd-explain]");
    if (inExplain && pExplain && pExplainWrap) {
      inExplain.addEventListener("input", () => {
        const val = inExplain.value.trim();
        pExplainWrap.hidden = !val;
        pExplain.textContent = val;
        renderMath(pExplain);
      });
    }

    const inAns = root.querySelector("[data-rd-answer]");
    if (inAns && pAns) {
      inAns.addEventListener("input", () => {
        pAns.textContent = inAns.value;
        renderMath(pAns);
      });
    }

    root.querySelectorAll("[data-rd-opt]").forEach((inp) => {
      inp.addEventListener("input", () => {
        const idx = inp.dataset.rdOpt;
        const target = root.querySelector(`[data-preview-opt="${idx}"]`);
        if (target) {
          target.textContent = inp.value;
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

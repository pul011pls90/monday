/* Monday — small progressive enhancements. Every page works without this file. */
(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  /* ---------- maths: render $...$ with KaTeX ---------- */
  function renderMath(root) {
    if (!window.renderMathInElement) return;
    window.renderMathInElement(root || document.body, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
      ],
      throwOnError: false,
      ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code", "option", "input"],
      ignoredClasses: ["no-math"],
    });
  }
  window.MondayRenderMath = renderMath;
  window.addEventListener("load", () => renderMath());

  /* ---------- theme toggle without reload ---------- */
  $$("form[data-theme-toggle]").forEach((form) => {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const html = document.documentElement;
      const next = html.dataset.theme === "dark" ? "light" : "dark";
      html.dataset.theme = next;
      const data = new FormData(form);
      data.set("theme", next);
      try {
        await fetch(form.action, { method: "POST", body: data, headers: { "X-Requested-With": "fetch" } });
      } catch (_) { /* preference is still applied for this page */ }
    });
  });

  /* ---------- copy buttons ---------- */
  $$("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const target = document.getElementById(btn.dataset.copy);
      const text = target ? (target.value || target.textContent) : btn.dataset.copyText;
      try {
        await navigator.clipboard.writeText(text.trim());
        const old = btn.dataset.label || btn.textContent;
        btn.dataset.label = old;
        btn.textContent = btn.dataset.done || "Скопировано";
        setTimeout(() => (btn.textContent = old), 1600);
      } catch (_) {
        if (target && target.select) target.select();
      }
    });
  });

  /* ---------- Monday's own confirmation window (no browser pop-ups) ----------
     MondayConfirm({title, text, ok, cancel, danger}) → Promise<boolean> */
  window.MondayConfirm = (opts) => new Promise((resolve) => {
    const body = document.body.dataset;
    if (typeof HTMLDialogElement !== "function") { resolve(window.confirm([opts.title, opts.text].filter(Boolean).join("\n\n"))); return; }
    const dlg = document.createElement("dialog");
    dlg.className = "exit-dialog";
    dlg.innerHTML = `<h2></h2><p></p><div class="exit-dialog__actions"><button type="button" class="btn btn--secondary" data-no></button><button type="button" class="btn" data-yes></button></div>`;
    dlg.querySelector("h2").textContent = opts.title || "";
    const p = dlg.querySelector("p");
    if (opts.text) p.textContent = opts.text; else p.remove();
    const no = dlg.querySelector("[data-no]"), yes = dlg.querySelector("[data-yes]");
    no.textContent = opts.cancel || body.confirmCancel || "Отмена";
    yes.textContent = opts.ok || body.confirmOk || "OK";
    yes.classList.add(opts.danger ? "btn--danger-solid" : "btn--primary");
    let answer = false;
    const done = (v) => { answer = v; dlg.close(); };
    no.addEventListener("click", () => done(false));
    yes.addEventListener("click", () => done(true));
    dlg.addEventListener("click", (ev) => { if (ev.target === dlg) done(false); });
    dlg.addEventListener("close", () => { dlg.remove(); resolve(answer); });
    document.body.appendChild(dlg);
    dlg.showModal();
    yes.focus();
  });

  /* ---------- confirmations for destructive actions: <form data-confirm> or <button data-confirm> ---------- */
  document.addEventListener("submit", async (e) => {
    const form = e.target;
    const holder = (e.submitter && e.submitter.dataset.confirm) ? e.submitter : (form.dataset.confirm ? form : null);
    if (!holder || form.dataset.confirmed === "1") { if (form.dataset) delete form.dataset.confirmed; return; }
    e.preventDefault();
    e.stopImmediatePropagation();
    const ok = await window.MondayConfirm({ title: holder.dataset.confirm, ok: holder.dataset.confirmOk,
                                            danger: /удал|delete/i.test(holder.dataset.confirm) });
    if (!ok) return;
    form.dataset.confirmed = "1";
    if (form.requestSubmit) form.requestSubmit(e.submitter || undefined); else form.submit();
  }, true);

  /* ---------- image lightbox (delegated, so swapped-in content works too) ---------- */
  const lightbox = $("#lightbox");
  if (lightbox) {
    document.addEventListener("click", (e) => {
      const img = e.target.closest("img[data-lightbox]");
      if (!img) return;
      $("img", lightbox).src = img.src;
      lightbox.classList.add("is-open");
    });
    lightbox.addEventListener("click", () => lightbox.classList.remove("is-open"));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") lightbox.classList.remove("is-open");
    });
  }

  /* ---------- test timer: counts down and submits when time is up ---------- */
  const timer = $("[data-timer]");
  if (timer) {
    let left = parseInt(timer.dataset.timer, 10);
    const form = document.getElementById(timer.dataset.form);
    let submitted = false;
    const tick = () => {
      const m = Math.floor(left / 60), s = left % 60;
      timer.textContent = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
      timer.classList.toggle("is-low", left <= 60);
      if (left <= 0 && form && !submitted) {
        submitted = true;
        const flag = document.createElement("input");   // tells the server the time ran out (homework may then go in empty)
        flag.type = "hidden"; flag.name = "timeout"; flag.value = "1";
        form.appendChild(flag);
        form.submit();
        return;
      }
      left -= 1;
    };
    tick();
    setInterval(tick, 1000);
    if (form) {
      form.addEventListener("submit", () => (submitted = true));
      // No browser "Leave site?" prompt: answers are saved as you go. The × button asks in our own dialog.
    }
  }

  /* ---------- leaving a test: our own calm dialog instead of the browser's ---------- */
  $$("[data-exit-confirm]").forEach((link) => link.addEventListener("click", (e) => {
    if (typeof HTMLDialogElement !== "function") return;
    e.preventDefault();
    let dlg = document.getElementById("exit-dialog");
    if (!dlg) {
      dlg = document.createElement("dialog");
      dlg.id = "exit-dialog";
      dlg.className = "exit-dialog";
      dlg.innerHTML = `<h2></h2><p></p><div class="exit-dialog__actions"><button type="button" class="btn btn--secondary" data-stay></button><a class="btn btn--primary" data-go></a></div>`;
      document.body.appendChild(dlg);
      dlg.querySelector("[data-stay]").addEventListener("click", () => dlg.close());
      dlg.addEventListener("click", (ev) => { if (ev.target === dlg) dlg.close(); });
    }
    dlg.querySelector("h2").textContent = link.dataset.exitTitle;
    dlg.querySelector("p").textContent = link.dataset.exitText;
    dlg.querySelector("[data-stay]").textContent = link.dataset.exitStay;
    const go = dlg.querySelector("[data-go]");
    go.textContent = link.dataset.exitGo;
    go.href = link.href;
    dlg.showModal();
    dlg.querySelector("[data-stay]").focus();
  }));

  /* ---------- timed tests: answered counter + autosave of every answer ---------- */
  const testForm = $("form[data-test]");
  if (testForm) {
    const counter = $("[data-answered]");
    const saveState = $("[data-save-state]");
    const csrf = ($("input[name=csrf_token]", testForm) || {}).value || "";
    const update = () => {
      const names = new Set($$("input, select", testForm).map((i) => i.name).filter((n) => /^q\d+$/.test(n)));
      let answered = 0;
      names.forEach((n) => {
        const fields = $$(`[name="${n}"]`, testForm);
        if (fields.some((f) => (f.type === "radio" || f.type === "checkbox" ? f.checked : f.value.trim() !== ""))) answered += 1;
      });
      if (counter) counter.textContent = `${answered} / ${names.size}`;
    };
    const valueOf = (name) => {
      const fields = $$(`[name="${name}"]`, testForm);
      const checked = fields.find((f) => (f.type === "radio" || f.type === "checkbox") && f.checked);
      if (checked) return checked.value;
      const text = fields.find((f) => f.type !== "radio" && f.type !== "checkbox");
      return text ? text.value.trim() : "";
    };
    const pending = new Map();
    const save = async (name) => {
      if (!testForm.dataset.autosave) return;
      if (saveState) saveState.textContent = saveState.dataset.saving;
      const body = new FormData();
      body.set("csrf_token", csrf);
      body.set("name", name);
      body.set("value", valueOf(name));
      try {
        const res = await fetch(testForm.dataset.autosave, {
          method: "POST", body, headers: { "X-Requested-With": "fetch", "X-CSRFToken": csrf }, credentials: "same-origin",
        });
        if (saveState) saveState.textContent = res.ok ? saveState.dataset.saved : saveState.dataset.failed;
      } catch (_) {
        if (saveState) saveState.textContent = saveState.dataset.failed;
      }
    };
    const schedule = (name, delay) => {
      clearTimeout(pending.get(name));
      pending.set(name, setTimeout(() => save(name), delay));
    };
    testForm.addEventListener("input", (e) => { update(); if (/^q\d+$/.test(e.target.name || "")) schedule(e.target.name, 600); });
    testForm.addEventListener("change", (e) => { update(); if (/^q\d+$/.test(e.target.name || "")) schedule(e.target.name, 0); });
    testForm.addEventListener("keydown", (e) => {   // Enter in an answer box must not submit the whole test
      if (e.key === "Enter" && e.target.matches("input[type=text], input:not([type])")) e.preventDefault();
    });
    update();
  }

  /* ---------- practice sessions: answer, next and reason without reloading the page ---------- */
  document.addEventListener("submit", async (e) => {
    const form = e.target.closest("form[data-ajax]");
    if (!form || !window.fetch || !window.DOMParser) return;
    e.preventDefault();
    if (form.dataset.busy) return;
    form.dataset.busy = "1";
    const data = new FormData(form);
    if (e.submitter && e.submitter.name) data.set(e.submitter.name, e.submitter.value);
    const buttons = $$("button", form);
    buttons.forEach((b) => (b.disabled = true));
    try {
      const res = await fetch(form.getAttribute("action") || window.location.href, {   // form.action is shadowed by name="action" buttons
        method: "POST", body: data, headers: { "X-Requested-With": "fetch" }, credentials: "same-origin",
      });
      const target = new URL(res.url);
      if (!res.ok || target.pathname !== window.location.pathname) {
        window.location.assign(res.url);       // finished session → results page
        return;
      }
      const doc = new DOMParser().parseFromString(await res.text(), "text/html");
      ["[data-ajax-region]", ".session-bar"].forEach((sel) => {
        const fresh = $(sel, doc), old = $(sel);
        if (fresh && old) old.replaceWith(fresh);
      });
      document.body.className = doc.body.className;
      document.title = doc.title;
      const region = $("[data-ajax-region]");
      renderMath(region);
      const action = e.submitter ? e.submitter.value : data.get("action");
      if (action === "next") window.scrollTo({ top: 0 });
      const focusTarget = $(".feedback, .flash--error, .q-card input:not([disabled])", region);
      if (focusTarget && action !== "reason") {
        focusTarget.setAttribute("tabindex", "-1");
        focusTarget.focus({ preventScroll: action === "next" });
      }
    } catch (_) {
      form.removeAttribute("data-busy");
      buttons.forEach((b) => (b.disabled = false));
      form.submit();                            // no connection to JS path → normal submit
    }
  });

  /* question form: ticking a "kind of question" chip means the teacher sets the tags themselves */
  $$("[data-tag-chip]").forEach((cb) => cb.addEventListener("change", () => {
    const form = cb.closest("form");
    if (form && !form.querySelector("input[name=tags_set]")) {
      const h = document.createElement("input"); h.type = "hidden"; h.name = "tags_set"; h.value = "1"; form.appendChild(h);
    }
  }));

  /* work editor: picking and ordering questions lives in picker.js */

  /* ---------- work editor: test format → calculator default, module / page fields ---------- */
  const fmtSel = $("[data-format-select]");
  if (fmtSel) {
    const calc = $("[data-calc-box]");
    let calcTouched = false;
    if (calc) calc.addEventListener("change", () => (calcTouched = true));
    const examSel = $("#exam");
    const examToFormat = { SAT: "sat", ORT: "ort", ENT: "ent", EGE: "ege", OGE: "oge", CSCA: "csca" };
    const syncFmt = () => {
      const opt = fmtSel.selectedOptions[0];
      if (calc && !calcTouched) calc.checked = opt.dataset.calc === "1";
      $$("[data-format-info]").forEach((el) => { el.hidden = el.dataset.formatInfo !== fmtSel.value; });
      $$("[data-fmt-only]").forEach((el) => {
        el.hidden = el.dataset.fmtOnly === "modules" ? opt.dataset.modules !== "2" : opt.dataset.nav !== el.dataset.fmtOnly;
      });
    };
    fmtSel.addEventListener("change", syncFmt);
    if (examSel) examSel.addEventListener("change", () => { if (examToFormat[examSel.value]) { fmtSel.value = examToFormat[examSel.value]; syncFmt(); } });
    syncFmt();
  }

  /* ---------- question editor: tree selects, material blocks, answer type, live preview ---------- */
  const qeditor = $("[data-question-editor]");
  if (qeditor) {
    const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

    /* Topic → Subtopic → Node: each select shows only the children of the one before. */
    const selTopic = $("#topic_id", qeditor), selSub = $("#subtopic_id", qeditor), selNode = $("#skill_id", qeditor);
    /* Rebuild options instead of hiding them (Safari ignores hidden <option>). */
    const originals = new Map();
    const filterChildren = (select, parentId) => {
      if (!originals.has(select)) originals.set(select, select.innerHTML);
      const keep = select.value;
      const tmp = document.createElement("select");
      tmp.innerHTML = originals.get(select);
      if (!parentId) {
        select.innerHTML = originals.get(select);
      } else {
        const opts = $$("option", tmp).filter((o) => !o.dataset.parent || o.dataset.parent === parentId);
        select.innerHTML = "";
        opts.forEach((o) => { o.selected = false; select.appendChild(o); });
      }
      select.value = keep;
      if (select.value !== keep) select.value = "";
    };
    const syncTree = (changed) => {
      if (changed === selNode && selNode.value) {           // picking a node fills in its parents
        const subId = selNode.selectedOptions[0].dataset.parent;
        filterChildren(selSub, null);
        selSub.value = subId;
        const subOpt = selSub.selectedOptions[0];
        if (subOpt) selTopic.value = subOpt.dataset.parent;
      } else if (changed === selSub && selSub.value) {
        selTopic.value = selSub.selectedOptions[0].dataset.parent;
      } else if (changed === selTopic) {
        const sub = selSub.selectedOptions[0];
        if (!selTopic.value || (sub && sub.dataset.parent !== selTopic.value)) selSub.value = "";
      }
      if (changed === selSub || changed === selTopic) {
        const node = selNode.selectedOptions[0];
        if (node && node.dataset.parent && node.dataset.parent !== selSub.value) selNode.value = "";
      }
      filterChildren(selSub, selTopic.value);
      filterChildren(selNode, selSub.value);
    };
    if (selTopic && selSub && selNode) {
      [selTopic, selSub, selNode].forEach((sel) => sel.addEventListener("change", () => syncTree(sel)));
      syncTree(selNode);
    }

    /* Answer options: show up to six. */
    const optionAdd = $("[data-option-add]", qeditor);
    if (optionAdd) {
      optionAdd.addEventListener("click", () => {
        const next = $$("[data-option-row]", qeditor).find((r) => r.hidden);
        if (next) { next.hidden = false; $("[data-option-input]", next).focus(); }
        optionAdd.hidden = !$$("[data-option-row]", qeditor).some((r) => r.hidden);
      });
      optionAdd.hidden = !$$("[data-option-row]", qeditor).some((r) => r.hidden);
    }

    /* Material blocks: add from <template>, move, remove. */
    const matList = $("[data-mat-list]", qeditor);
    if (matList) {
      let nextIndex = parseInt(matList.dataset.nextIndex || "1", 10);
      $$("[data-mat-add]", qeditor).forEach((btn) => {
        btn.addEventListener("click", () => {
          const tpl = $(`template[data-mat-template="${btn.dataset.matAdd}"]`, qeditor);
          const html = tpl.innerHTML.replace(/__i__/g, String(nextIndex++));
          matList.insertAdjacentHTML("beforeend", html);
          const added = matList.lastElementChild;
          const first = $("input:not([type=hidden]), textarea", added);
          if (first) first.focus();
          updatePreview();
        });
      });
      matList.addEventListener("click", (e) => {
        const btn = e.target.closest("button");
        if (!btn) return;
        const block = btn.closest("[data-mat-block]");
        if (btn.hasAttribute("data-mat-remove")) block.remove();
        if (btn.dataset.matMove === "-1" && block.previousElementSibling) matList.insertBefore(block, block.previousElementSibling);
        if (btn.dataset.matMove === "1" && block.nextElementSibling) matList.insertBefore(block.nextElementSibling, block);
        updatePreview();
      });
    }

    /* Answer type */
    const typeInputs = $$("input[name=answer_type]", qeditor);
    const answerType = () => (typeInputs.find((i) => i.checked) || {}).value || "choice";
    const showType = () => {
      $$("[data-answer-type]", qeditor).forEach((el) => (el.hidden = el.dataset.answerType !== answerType()));
      updatePreview();
    };
    typeInputs.forEach((i) => i.addEventListener("change", showType));

    /* Picture */
    const file = $("input[type=file][name=image]", qeditor);
    const thumb = $("[data-image-thumb]", qeditor);
    const body = $("[data-preview-body]");
    let imageSrc = body ? body.dataset.img : "";
    if (file && thumb) {
      file.addEventListener("change", () => {
        const f = file.files && file.files[0];
        if (!f) return;
        thumb.src = URL.createObjectURL(f);
        thumb.hidden = false;
        imageSrc = thumb.src;
        updatePreview();
      });
    }
    const removeImage = $("input[name=remove_image]", qeditor);

    /* Word counter */
    const textArea = $("[name=text]", qeditor);
    const counter = $("[data-word-count]", qeditor);
    const limit = parseInt(textArea.dataset.wordLimit || "150", 10);
    const countWords = () => {
      const n = (textArea.value.match(/\S+/g) || []).length;
      if (counter) {
        counter.textContent = `${n} / ${limit}`;
        counter.classList.toggle("is-over", n > limit);
      }
    };

    /* Live preview: same markup as the student page (macros.question_body). */
    function materialBlocks() {
      return $$("[data-mat-block]", qeditor).map((block) => {
        const type = $("input[type=hidden]", block).value;
        const val = (suffix) => { const el = $(`[name$="_${suffix}"]`, block); return el ? el.value.trim() : ""; };
        return { type, text: val("text"), title: val("title"), left: val("left"), right: val("right"),
                 left_title: val("left_title"), right_title: val("right_title") };
      });
    }
    function updatePreview() {
      countWords();
      if (!body) return;
      const d = body.dataset;
      const blocks = materialBlocks().filter((b) => b.text || b.left || b.right);
      const hasImage = imageSrc && !(removeImage && removeImage.checked);
      const split = hasImage || blocks.length > 0;
      let mat = "";
      if (hasImage) mat += `<figure class="q-figure"><div class="q-figure__frame"><img src="${esc(imageSrc)}" alt=""></div></figure>`;
      blocks.forEach((b) => {
        if (b.type === "heading") mat += `<h3 class="q-mat-heading">${esc(b.text)}</h3>`;
        if (b.type === "passage") mat += `<div class="q-passage">${b.title ? `<div class="q-passage__title">${esc(b.title)}</div>` : ""}<div class="q-passage__text">${esc(b.text)}</div></div>`;
        if (b.type === "columns") mat += `<div class="q-columns"><div class="q-columns__col"><div class="q-columns__title">${esc(b.left_title)}</div><div class="q-columns__body">${esc(b.left)}</div></div><div class="q-columns__col"><div class="q-columns__title">${esc(b.right_title)}</div><div class="q-columns__body">${esc(b.right)}</div></div></div>`;
      });
      let answers = "";
      if (answerType() === "choice") {
        const letters = "АБВГДЕ";
        $$("[data-option-input]", qeditor).forEach((inp, i) => {
          if (!inp.value.trim()) return;
          answers += `<div class="option"><span class="option__box"><span class="option__letter">${letters[i]}</span><span>${esc(inp.value)}</span></span></div>`;
        });
        answers = `<div class="options">${answers}</div>`;
      } else {
        const kinds = $$("input[name=input_formats]:checked", qeditor).map((c) => d["hint" + c.value.charAt(0).toUpperCase() + c.value.slice(1)]);
        const p = ($("#precision", qeditor) || {}).value;
        const round = p === "1" ? " " + d.hintP1 : p === "2" ? " " + d.hintP2 : "";
        answers = `<div class="field answer-input"><label>${esc(d.labelAnswer)}</label><div class="input"></div>
          <span class="field__hint">${esc(d.hintKinds)} ${esc((kinds.length ? kinds : [d.hintWhole, d.hintFraction, d.hintDecimal]).join(", "))}.${esc(round)}</span></div>`;
      }
      const weight = parseInt(($("#weight", qeditor) || {}).value || "1", 10);
      const meta = weight > 1 ? `<div class="row row--between q-main__meta"><span></span><span class="tag tag--line tag--xs">${weight} ${esc(d.labelPoints)}</span></div>` : "";
      const text = textArea.value.trim();
      body.innerHTML = `<div class="q-layout ${split ? "q-layout--split" : "q-layout--single"}">
        ${split ? `<div class="q-material">${mat}</div>` : ""}
        <div class="q-main">${meta}${text ? `<div class="q-text">${esc(text)}</div>` : '<div class="q-text muted">…</div>'}${answers}</div></div>`;
      const layoutLabel = $("[data-preview-layout]");
      if (layoutLabel) layoutLabel.textContent = split ? d.labelSplit : d.labelSingle;
      const diff = $("[name=difficulty]", qeditor);
      const nodeText = selNode && selNode.selectedOptions[0] && selNode.value ? selNode.selectedOptions[0].text.replace(" ★", "") : ($("#new_node", qeditor) || {}).value || "";
      $("[data-preview-bar]").textContent = `${nodeText || "…"} · ${diff.options[diff.selectedIndex].text}`;
      renderMath(body);
    }
    qeditor.addEventListener("input", updatePreview);
    qeditor.addEventListener("change", updatePreview);
    window.addEventListener("load", showType);
    showType();

    $$("[data-insert]", qeditor).forEach((btn) => {
      btn.addEventListener("click", () => {
        const ta = textArea;
        const snippet = btn.dataset.insert;
        const start = ta.selectionStart, end = ta.selectionEnd;
        ta.value = ta.value.slice(0, start) + snippet + ta.value.slice(end);
        ta.focus();
        const caret = start + snippet.indexOf("□");
        if (snippet.includes("□")) {
          ta.value = ta.value.replace("□", "");
          ta.setSelectionRange(caret, caret);
        }
        updatePreview();
      });
    });
  }

  /* ---------- profile photo: choosing a file uploads it straight away ---------- */
  /* ---------- file pickers: show the chosen file name ---------- */
  $$("[data-file-pick]").forEach((input) => input.addEventListener("change", () => {
    const pick = input.closest(".file-pick");
    const name = $("[data-file-name]", pick);
    const f = input.files && input.files[0];
    name.textContent = f ? f.name : name.dataset.empty;
    pick.classList.toggle("has-file", !!f);
  }));

  $$("[data-avatar-input]").forEach((input) => {
    input.addEventListener("change", () => {
      const f = input.files && input.files[0];
      if (!f) return;
      const img = input.closest("label").querySelector(".avatar img");
      if (img) img.src = URL.createObjectURL(f);
      input.form.submit();
    });
  });

  /* ---------- auto-submit selects (filters, mistake reasons) ---------- */
  document.addEventListener("change", (e) => {
    const s = e.target.closest("select[data-autosubmit]");
    if (!s || !s.form) return;
    if (s.form.requestSubmit) s.form.requestSubmit(); else s.form.submit();
  });
})();

/* Phone side menu (☰): opens from the left with the sections that don't fit in the bottom bar. */
(function () {
  "use strict";
  const drawer = document.querySelector("[data-nav-drawer]");
  const opener = document.querySelector("[data-nav-open]");
  if (!drawer || !opener) return;
  let lastFocus = null;
  const open = () => {
    lastFocus = document.activeElement;
    drawer.hidden = false;
    requestAnimationFrame(() => drawer.classList.add("is-open"));
    document.body.classList.add("nav-open");
    opener.setAttribute("aria-expanded", "true");
    const first = drawer.querySelector(".nav-drawer__item");
    if (first) first.focus({ preventScroll: true });
  };
  const close = () => {
    drawer.classList.remove("is-open");
    document.body.classList.remove("nav-open");
    opener.setAttribute("aria-expanded", "false");
    setTimeout(() => { drawer.hidden = true; }, 220);
    if (lastFocus) lastFocus.focus({ preventScroll: true });
  };
  opener.addEventListener("click", open);
  drawer.addEventListener("click", (e) => { if (e.target.closest("[data-nav-close]")) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !drawer.hidden) close(); });
  window.addEventListener("resize", () => { if (window.innerWidth > 760 && !drawer.hidden) close(); });
})();

/* ---------- test review: one question at a time, picker at the bottom (collections) ---------- */
(() => {
  const root = document.querySelector("[data-rv]");
  if (!root) return;
  const $ = (s, el = root) => el.querySelector(s);
  const screens = [...root.querySelectorAll("[data-rv-screen]")];
  if (!screens.length) return;
  const foot = $("[data-rv-foot]"), pop = $("[data-rv-pop]"), counter = $("[data-rv-counter]");
  const prev = $("[data-rv-prev]"), next = $("[data-rv-next]");
  const cells = [...root.querySelectorAll("[data-rv-go]")];
  root.classList.add("is-paged");
  foot.hidden = false;
  document.body.classList.add("has-rv-foot");
  // phones: the app menu sits at the bottom — put the review bar right above it
  const rail = document.querySelector(".rail");
  const place = () => {
    const r = rail && rail.getBoundingClientRect();
    const atBottom = r && getComputedStyle(rail).position === "fixed" && r.top > window.innerHeight / 2;
    const h = atBottom ? Math.round(window.innerHeight - r.top) : 0;
    foot.style.bottom = `${h}px`;
    document.body.style.paddingBottom = `${h + foot.offsetHeight + 12}px`;
  };
  place();
  // desktop: the question card fills the screen between the top bar and the bottom bar, and each side
  // (explanation / question) scrolls on its own — no more scrolling the page up and down to compare them
  const fit = () => {
    const top = document.querySelector(".topbar");
    const topH = top && getComputedStyle(top).position !== "static" ? top.offsetHeight : 0;
    const footTop = foot.getBoundingClientRect().top;
    root.style.setProperty("--rv-h", `${Math.max(360, Math.round(footTop - topH - 24))}px`);
  };
  window.addEventListener("resize", () => { place(); fit(); });
  let cur = 0;
  const show = (i, scroll = true) => {
    cur = Math.max(0, Math.min(screens.length - 1, i));
    screens.forEach((s, k) => (s.hidden = k !== cur));
    counter.textContent = screens[cur].dataset.rvLabel || String(cur + 1);
    prev.disabled = cur === 0;
    next.disabled = cur === screens.length - 1;
    cells.forEach((c) => c.classList.toggle("is-current", parseInt(c.dataset.rvGo, 10) === cur));
    if (scroll) history.replaceState(null, "", `#q${cur + 1}`);   // only once the student moves (or opened a #qN link)
    if (window.MondayRenderMath) window.MondayRenderMath(screens[cur]);
    screens[cur].querySelectorAll(".rv-explain, .rv-question").forEach((col) => (col.scrollTop = 0));
    fit();
    if (scroll) toCard();
  };
  function toCard() {
    const top = document.querySelector(".topbar");
    const offset = (top && getComputedStyle(top).position !== "static" ? top.offsetHeight : 0) + 12;
    window.scrollTo({ top: screens[cur].getBoundingClientRect().top + window.scrollY - offset });
  }
  prev.addEventListener("click", () => show(cur - 1));
  next.addEventListener("click", () => show(cur + 1));
  $("[data-rv-toggle]").addEventListener("click", (e) => {
    pop.hidden = !pop.hidden;
    e.currentTarget.setAttribute("aria-expanded", String(!pop.hidden));
  });
  cells.forEach((c) => c.addEventListener("click", () => { pop.hidden = true; show(parseInt(c.dataset.rvGo, 10)); }));
  document.addEventListener("click", (e) => { if (!pop.hidden && !e.target.closest("[data-rv-pop], [data-rv-toggle]")) pop.hidden = true; });
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea")) return;
    if (e.key === "ArrowRight" && !next.disabled) show(cur + 1);
    if (e.key === "ArrowLeft" && !prev.disabled) show(cur - 1);
    if (e.key === "Escape") pop.hidden = true;
  });
  const m = location.hash.match(/^#q(\d+)$/);
  show(m ? parseInt(m[1], 10) - 1 : 0, !!m);
  if (!m) window.scrollTo(0, 0);   // fresh from the test: start at the score, the review is right below
  // maths and pictures above change the page height once they load — settle the card again
  if (m) window.addEventListener("load", () => setTimeout(() => { fit(); toCard(); }, 50));
})();



/* formula sheets: math keyboard, live preview, several formulas at once, "add to this section" */
(() => {
  const renderInto = (input) => {
    const box = input.parentElement.querySelector("[data-math-preview]");
    if (!box) return;
    const v = input.value.trim();
    box.textContent = v ? (v.includes("$") ? v : `$${v}$`) : "";
    if (window.MondayRenderMath) window.MondayRenderMath(box);
  };
  const wireRow = (row) => {
    const input = row.querySelector("[data-math-input]");
    if (!input) return;
    input.addEventListener("input", () => renderInto(input));
    row.querySelectorAll("[data-snip]").forEach((b) => b.addEventListener("mousedown", (e) => e.preventDefault()));
    row.querySelectorAll("[data-snip]").forEach((b) => b.addEventListener("click", () => {
      const snip = b.dataset.snip, mark = snip.indexOf("‸");
      const text = snip.replace("‸", "");
      const s = input.selectionStart ?? input.value.length, e = input.selectionEnd ?? s;
      const picked = input.value.slice(s, e);
      // selected text goes inside the braces: x → \sqrt{x}
      const put = mark >= 0 && picked ? text.slice(0, mark) + picked + text.slice(mark) : text;
      input.value = input.value.slice(0, s) + put + input.value.slice(e);
      const caret = s + (mark >= 0 ? mark + picked.length : put.length);
      input.focus(); input.setSelectionRange(caret, caret);
      renderInto(input);
    }));
    renderInto(input);
  };
  document.querySelectorAll("[data-formula-add]").forEach((form) => {
    const rows = form.querySelector("[data-rows]");
    const tpl = rows.querySelector("[data-row]").cloneNode(true);
    rows.querySelectorAll("[data-row]").forEach(wireRow);
    const sync = () => {
      const all = rows.querySelectorAll("[data-row]");
      all.forEach((r) => { r.querySelector("[data-row-del]").hidden = all.length < 2; });
    };
    form.querySelector("[data-row-add]").addEventListener("click", () => {
      const row = tpl.cloneNode(true);
      row.querySelectorAll("input").forEach((i) => { i.value = ""; });
      row.querySelector("[data-math-preview]").textContent = "";
      rows.appendChild(row); wireRow(row); sync();
      row.querySelector("input[name=topic]").focus();
    });
    rows.addEventListener("click", (e) => {
      const del = e.target.closest("[data-row-del]");
      if (del) { del.closest("[data-row]").remove(); sync(); }
    });
    sync();
  });
  document.querySelectorAll("[data-add-to]").forEach((btn) => btn.addEventListener("click", () => {
    const box = document.getElementById(`add-${btn.dataset.addTo}`);
    if (!box) return;
    box.open = true;
    const br = box.querySelector("[data-branch-input]");
    br.value = btn.dataset.branch;
    box.scrollIntoView({ block: "start", behavior: "smooth" });
    const topic = box.querySelector("input[name=topic]"); if (topic) topic.focus({ preventScroll: true });
  }));
})();

/* mistakes review: number picker in the bottom bar */
(() => {
  const foot = document.querySelector("[data-mr-foot]");
  if (!foot) return;
  document.body.classList.add("has-rv-foot");
  const btn = foot.querySelector("[data-mr-toggle]"), pop = foot.querySelector("[data-mr-pop]");
  btn.addEventListener("click", (e) => { e.stopPropagation(); pop.hidden = !pop.hidden; btn.setAttribute("aria-expanded", String(!pop.hidden)); });
  document.addEventListener("click", (e) => { if (!pop.hidden && !e.target.closest("[data-mr-pop]")) { pop.hidden = true; btn.setAttribute("aria-expanded", "false"); } });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") pop.hidden = true;
    if (e.target.closest("input, select, textarea")) return;
    const link = e.key === "ArrowRight" ? foot.querySelector(".btn--primary") : e.key === "ArrowLeft" ? foot.querySelector(".btn--secondary") : null;
    if (link && !link.classList.contains("is-disabled")) location.href = link.href;
  });
  // phones: the app menu sits at the bottom — keep the bar right above it
  const rail = document.querySelector(".rail");
  const place = () => {
    const r = rail && rail.getBoundingClientRect();
    const atBottom = r && getComputedStyle(rail).position === "fixed" && r.top > window.innerHeight / 2;
    foot.style.bottom = atBottom ? `${Math.round(window.innerHeight - r.top)}px` : "";
  };
  place(); window.addEventListener("resize", place);
})();

/* "+N" chips: show the rest of the list, "Свернуть" folds it back */
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-chip-more]");
  if (!b) return;
  e.preventDefault(); e.stopPropagation();
  const rest = b.previousElementSibling, open = rest.hidden;
  rest.hidden = !open;
  b.textContent = open ? b.dataset.close : b.dataset.open;
  b.setAttribute("aria-expanded", String(open));
  b.classList.toggle("is-open", open);
  b.classList.toggle("tag", !open); b.classList.toggle("tag--line", !open);
}, true);

/* ---------- pixel numbers: window.MondayPixel(canvas, text, cell, lit, unlit) draws text in a 5×7 dot-matrix font
   (used by the Monday test countdown and ranking podium; other numbers stay in the regular font) */
(function () {
  "use strict";
  const FONT = {
    0: ["01110", "10001", "10001", "10001", "10001", "10001", "01110"], 1: ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    2: ["01110", "10001", "00001", "00010", "00100", "01000", "11111"], 3: ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    4: ["00010", "00110", "01010", "10010", "11111", "00010", "00010"], 5: ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    6: ["00110", "01000", "10000", "11110", "10001", "10001", "01110"], 7: ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    8: ["01110", "10001", "10001", "01110", "10001", "10001", "01110"], 9: ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"], "#": ["01010", "11111", "01010", "01010", "01010", "11111", "01010"],
    "%": ["11001", "11010", "00010", "00100", "01000", "01011", "10011"], "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"], "–": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ".": ["00", "00", "00", "00", "00", "11", "11"], ",": ["00", "00", "00", "00", "11", "01", "10"], " ": ["00", "00", "00", "00", "00", "00", "00"],
  };
  window.MondayPixel = (cv, text, cell = 6, lit = "rgba(255,255,255,.88)", unlit = "rgba(255,255,255,.07)") => {
    if (!cv) return;
    const gap = Math.max(1, Math.round(cell / 5)), dpr = Math.min(2, window.devicePixelRatio || 1);
    const chars = [...String(text)].filter((ch) => FONT[ch]);
    const w = Math.max(1, chars.reduce((s, ch) => s + (FONT[ch][0].length + 1) * cell, 0) - cell), h = 7 * cell;
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.width = w + "px"; cv.style.height = h + "px";
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    let x0 = 0;
    for (const ch of chars) {
      const g = FONT[ch];
      g.forEach((row, r) => [...row].forEach((b, c) => {
        if (b !== "1" && !unlit) return;
        ctx.fillStyle = b === "1" ? lit : unlit;
        ctx.fillRect(x0 + c * cell, r * cell, cell - gap, cell - gap);
      }));
      x0 += (g[0].length + 1) * cell;
    }
  };
})();

// goal score: its allowed range follows the chosen exam
(() => {
  const goal = document.querySelector("[data-goal-for]");
  if (!goal) return;
  const form = goal.form, hint = form.querySelector("[data-goal-hint]");
  const tpl = hint ? hint.textContent.replace(/\d+/, "{a}").replace(/\d+(?!.*\d)/, "{b}") : "";
  const sync = () => {
    const el = form.querySelector("select[name=exam]");
    const src = el ? el.selectedOptions[0] : form.querySelector("input[name=exam]:checked");
    if (!src || !src.dataset.max) return;
    goal.min = src.dataset.min; goal.max = src.dataset.max;
    if (hint) hint.textContent = tpl.replace("{a}", src.dataset.min).replace("{b}", src.dataset.max);
  };
  form.addEventListener("change", (e) => { if (e.target.name === "exam") sync(); });
})();

// skills map: expand / collapse every topic at once
(() => {
  const btn = document.querySelector("[data-skills-all]");
  const tree = document.querySelector("[data-skills-tree]");
  if (!btn || !tree) return;
  const all = () => [...tree.querySelectorAll(".sk-topic > details")];
  const label = () => { btn.textContent = all().every((d) => d.open) ? btn.dataset.close : btn.dataset.open; };
  btn.addEventListener("click", () => { const open = !all().every((d) => d.open); all().forEach((d) => { d.open = open; }); label(); });
  tree.addEventListener("toggle", (e) => {
    const tile = e.target.parentElement;
    if (!tile || !tile.classList.contains("sk-topic")) return;  // nested popovers (edit boxes) are not tiles
    tile.classList.toggle("is-open", e.target.open);
    if (e.target.open && !all().every((d) => d.open)) e.target.scrollIntoView({ block: "nearest", behavior: "smooth" });
    label();
  }, true);
  label();
})();

// «Сообщить об ошибке»: send the report without leaving the question
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-report-send]");
  if (!btn) return;
  const box = btn.closest("[data-report-form]");
  const status = box.querySelector("[data-report-status]");
  const kind = box.querySelector("input[type=radio]:checked");
  const body = new FormData();
  body.append("csrf_token", box.dataset.csrf);
  body.append("question_id", box.dataset.question);
  body.append("kind", kind ? kind.value : "other");
  body.append("message", box.querySelector("textarea").value);
  btn.disabled = true;
  try {
    const r = await fetch(box.dataset.action, { method: "POST", body, headers: { "X-Requested-With": "fetch" } });
    const j = await r.json();
    status.textContent = j.message || "";
    status.className = "small " + (j.ok ? "qr__ok" : "qr__err");
    if (j.ok) {
      box.querySelector("textarea").value = "";
      setTimeout(() => { const d = box.closest("details"); if (d) d.open = false; status.textContent = ""; btn.disabled = false; }, 1800);
    } else btn.disabled = false;
  } catch (_err) { btn.disabled = false; }
});
// a reply to a report on the home page: dismiss it
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-report-seen]");
  if (!b) return;
  e.preventDefault();
  const card = b.closest("[data-report-card]");
  const body = new FormData();
  body.append("csrf_token", b.dataset.csrf);
  try { await fetch(b.dataset.action, { method: "POST", body, headers: { "X-Requested-With": "fetch" } }); } catch (_err) { /* ignore */ }
  if (card) card.remove();
});

// practice sessions: soft time limit in the header, a clock per question, «время вышло» banner.
// The header and the question are replaced after every answer, so look the elements up on each tick.
(() => {
  let clockKey = null, clockStart = 0;
  const fmt = (sec) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
  const tick = () => {
    const dl = document.querySelector("[data-deadline]");
    if (dl) {
      const left = Math.round((parseInt(dl.dataset.deadline, 10) - Date.now()) / 1000);
      dl.textContent = left > 0 ? fmt(left) : "0:00";
      dl.classList.toggle("is-low", left <= 60);
      const up = document.querySelector("[data-time-up]");
      if (up) up.hidden = left > 0;
    }
    const qc = document.querySelector("[data-qclock]");
    if (qc) {
      if (qc.dataset.qclock !== clockKey) { clockKey = qc.dataset.qclock; clockStart = Date.now(); }
      const out = qc.querySelector(".num");
      if (out) out.textContent = fmt(Math.floor((Date.now() - clockStart) / 1000));
    }
  };
  if (document.querySelector("[data-deadline], [data-qclock]")) { tick(); setInterval(tick, 1000); }
})();

// «Своя сессия»: presets, the question counter, topic picker and the pace hint
(() => {
  const box = document.querySelector("[data-sb]");
  if (!box) return;
  const form = box.querySelector("#sb-form");
  const range = form.querySelector("[data-sb-count]");
  const out = form.querySelector("[data-sb-count-out]");
  const pace = form.querySelector("[data-sb-pace]");
  const topics = form.querySelector("[data-sb-topics]");
  const P = JSON.parse(pace.dataset.pace);
  const need = { ladder: P["2"], easy: P["1"], medium: P["2"], hard: P["3"], mix: Math.round((P["1"] + P["2"] + P["3"]) / 3) };
  const val = (name) => { const el = form.querySelector(`input[name=${name}]:checked`); return el ? el.value : null; };
  const set = (name, v) => { const el = form.querySelector(`input[name=${name}][value="${v}"]`); if (el) el.checked = true; };
  const human = (s) => (s < 60 ? pace.dataset.tSec.replace("{n}", s) : pace.dataset.tMin.replace("{m}", Math.floor(s / 60)).replace("{s}", s % 60));
  const update = () => {
    out.textContent = range.value;
    topics.hidden = val("topics") !== "pick";
    const note = form.querySelector("[data-sb-ladder-note]");
    if (note) note.hidden = val("level") !== "ladder";
    const minutes = parseInt(val("minutes") || "0", 10), count = parseInt(range.value, 10);
    const text = pace.querySelector("[data-sb-pace-text]"), fix = pace.querySelector("[data-sb-fix]");
    fix.innerHTML = "";
    pace.className = "sb__pace";
    if (!minutes) { text.textContent = pace.dataset.tFree; return; }
    const per = Math.round((minutes * 60) / count), n = need[val("level")] || P["2"];
    if (per >= n) { text.textContent = pace.dataset.tOk.replace("{s}", human(per)); pace.classList.add("is-ok"); return; }
    if (per >= n * 0.6) { text.textContent = pace.dataset.tTight.replace("{s}", human(per)); pace.classList.add("is-tight"); return; }
    pace.classList.add("is-bad");
    text.textContent = pace.dataset.tBad.replace("{need}", human(n)).replace("{s}", human(per));
    const fitCount = Math.max(1, Math.floor((minutes * 60) / n));
    const opts = [...form.querySelectorAll("input[name=minutes]")].map((i) => parseInt(i.value, 10)).filter((m) => m > 0);
    const fitMin = opts.find((m) => (m * 60) / count >= n);
    const btn = (label, fn) => { const b = document.createElement("button"); b.type = "button"; b.className = "chip"; b.textContent = label; b.onclick = () => { fn(); update(); }; fix.appendChild(b); };
    btn(pace.dataset.tFixCount.replace("{n}", fitCount), () => { range.value = fitCount; });
    if (fitMin) btn(pace.dataset.tFixMin.replace("{m}", fitMin), () => set("minutes", fitMin));
  };
  box.querySelectorAll("[data-sb-preset]").forEach((b) => b.addEventListener("click", () => {
    const c = JSON.parse(b.dataset.sbPreset);
    if (c.minutes !== undefined) set("minutes", c.minutes);
    if (c.count) range.value = c.count;
    if (c.level) set("level", c.level);
    if (Array.isArray(c.topics)) {
      set("topics", "pick");
      form.querySelectorAll("input[name=topic]").forEach((cb) => { cb.checked = c.topics.includes(parseInt(cb.value, 10)); });
    } else if (c.topics) set("topics", c.topics);
    if (c.explain) set("explain", c.explain);
    box.querySelectorAll("[data-sb-preset]").forEach((x) => x.classList.toggle("is-active", x === b));
    update();
  }));
  form.addEventListener("input", update);
  form.addEventListener("change", update);
  update();
})();

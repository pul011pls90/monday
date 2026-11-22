/* Monday — single delegated CSP-safe controller for searchable comboboxes. */
(function () {
  "use strict";

  function parts(root) {
    return {
      hidden: root.querySelector("[data-combobox-value]"),
      search: root.querySelector("[data-combobox-search]"),
      clear: root.querySelector("[data-combobox-clear]"),
      list: root.querySelector("[data-combobox-list]"),
      empty: root.querySelector("[data-combobox-empty]"),
      sep: root.querySelector("[data-combobox-sep]"),
      options: Array.from(root.querySelectorAll("[data-combobox-option]")),
      groups: Array.from(root.querySelectorAll("[data-combobox-group]")),
    };
  }

  function isRequired(p) {
    return Boolean(p.hidden && p.hidden.dataset.comboboxRequired === "true");
  }

  function syncValidity(root) {
    const p = parts(root);
    if (!p.search || !isRequired(p)) return;
    if (p.hidden && p.hidden.value) {
      p.search.setCustomValidity("");
    } else {
      p.search.setCustomValidity("Выберите значение из списка");
    }
  }

  function openList(root) {
    const p = parts(root);
    if (!p.list) return;
    closeAll(root);
    p.list.hidden = false;
    root.classList.add("is-open");
    if (p.search) p.search.setAttribute("aria-expanded", "true");
  }

  function closeList(root, restoreLabel) {
    const p = parts(root);
    if (!p.list) return;
    p.list.hidden = true;
    root.classList.remove("is-open");
    if (p.search) {
      p.search.setAttribute("aria-expanded", "false");
      p.search.removeAttribute("aria-activedescendant");
      if (restoreLabel) {
        const val = p.hidden ? p.hidden.value : "";
        const matched = p.options.find((o) => o.dataset.value === val);
        p.search.value = matched ? matched.dataset.label || "" : "";
        filterOptions(root, "");
      }
    }
    p.options.forEach((o) => o.classList.remove("is-highlighted"));
  }

  function closeAll(exceptRoot) {
    document.querySelectorAll("[data-combobox].is-open").forEach((r) => {
      if (r !== exceptRoot) closeList(r, true);
    });
  }

  function filterOptions(root, query) {
    const p = parts(root);
    const q = String(query || "").trim().toLowerCase();
    const visibleGroupIds = new Set();
    let visibleCount = 0;
    let visibleSpecial = 0;
    let visibleRegular = 0;

    p.options.forEach((opt) => {
      const hay = `${opt.dataset.label || ""} ${opt.dataset.meta || ""}`.toLowerCase();
      const match = !q || hay.indexOf(q) !== -1;
      opt.hidden = !match;
      if (match) {
        visibleCount += 1;
        if (opt.dataset.comboboxGroupId) visibleGroupIds.add(opt.dataset.comboboxGroupId);
        if (opt.dataset.comboboxSpecial === "true") visibleSpecial += 1;
        else visibleRegular += 1;
      }
    });

    p.groups.forEach((g) => {
      g.hidden = !visibleGroupIds.has(g.dataset.comboboxGroup);
    });
    if (p.sep) {
      p.sep.hidden = !(visibleSpecial > 0 && visibleRegular > 0);
    }
    if (p.empty) {
      p.empty.hidden = visibleCount > 0;
    }
  }

  function maybeSubmit(root) {
    if (root.dataset.autoSubmit !== "true") return;
    const form = root.closest("form");
    if (form) {
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.submit();
    }
  }

  function selectOption(root, opt) {
    const p = parts(root);
    if (!opt || !p.hidden || !p.search) return;
    const val = opt.dataset.value || "";
    const lbl = opt.dataset.label || "";
    p.hidden.value = val;
    p.search.value = lbl;

    p.options.forEach((o) => {
      const sel = o === opt;
      o.classList.toggle("is-selected", sel);
      o.setAttribute("aria-selected", sel ? "true" : "false");
    });

    if (p.clear) p.clear.hidden = !val;
    syncValidity(root);
    filterOptions(root, "");
    closeList(root, false);
    maybeSubmit(root);
  }

  function clearSelection(root) {
    const p = parts(root);
    if (!p.hidden || !p.search) return;
    p.hidden.value = "";
    p.search.value = "";
    p.options.forEach((o) => {
      o.classList.remove("is-selected");
      o.setAttribute("aria-selected", "false");
    });
    if (p.clear) p.clear.hidden = true;
    syncValidity(root);
    filterOptions(root, "");
    closeList(root, false);
    maybeSubmit(root);
  }

  function moveHighlight(root, delta) {
    const p = parts(root);
    const visible = p.options.filter((o) => !o.hidden);
    if (!visible.length) return;
    let idx = visible.findIndex((o) => o.classList.contains("is-highlighted"));
    if (idx === -1) idx = visible.findIndex((o) => o.classList.contains("is-selected"));
    const nextIdx = idx === -1
      ? (delta > 0 ? 0 : visible.length - 1)
      : (idx + delta + visible.length) % visible.length;

    p.options.forEach((o) => o.classList.remove("is-highlighted"));
    const target = visible[nextIdx];
    target.classList.add("is-highlighted");
    if (p.search && target.id) p.search.setAttribute("aria-activedescendant", target.id);
    if (typeof target.scrollIntoView === "function") target.scrollIntoView({ block: "nearest" });
  }

  function initAll(scope) {
    const container = scope || document;
    container.querySelectorAll("[data-combobox]").forEach((root) => syncValidity(root));
  }

  // Open on focus / click of input or toggle
  document.addEventListener("focusin", (e) => {
    const input = e.target.closest("[data-combobox-search]");
    if (!input) return;
    const root = input.closest("[data-combobox]");
    if (!root) return;
    filterOptions(root, "");
    openList(root);
  });

  document.addEventListener("input", (e) => {
    const input = e.target.closest("[data-combobox-search]");
    if (!input) return;
    const root = input.closest("[data-combobox]");
    if (!root) return;
    const p = parts(root);
    if (!input.value.trim() && p.hidden) {
      p.hidden.value = "";
      if (p.clear) p.clear.hidden = true;
    } else if (p.hidden) {
      // Clear committed selection if user starts typing something else until they pick
      const matched = p.options.find((o) => (o.dataset.label || "") === input.value);
      p.hidden.value = matched ? matched.dataset.value || "" : "";
      if (p.clear) p.clear.hidden = !input.value;
    }
    syncValidity(root);
    filterOptions(root, input.value);
    openList(root);
  });

  document.addEventListener("click", (e) => {
    const clearBtn = e.target.closest("[data-combobox-clear]");
    if (clearBtn) {
      const root = clearBtn.closest("[data-combobox]");
      if (root) {
        e.preventDefault();
        clearSelection(root);
        parts(root).search?.focus();
      }
      return;
    }

    const toggleBtn = e.target.closest("[data-combobox-toggle]");
    if (toggleBtn) {
      const root = toggleBtn.closest("[data-combobox]");
      if (root) {
        e.preventDefault();
        if (root.classList.contains("is-open")) closeList(root, true);
        else {
          filterOptions(root, "");
          openList(root);
          parts(root).search?.focus();
        }
      }
      return;
    }

    const opt = e.target.closest("[data-combobox-option]");
    if (opt) {
      const root = opt.closest("[data-combobox]");
      if (root) {
        e.preventDefault();
        selectOption(root, opt);
      }
      return;
    }

    if (!e.target.closest("[data-combobox]")) {
      closeAll(null);
    }
  });

  document.addEventListener("keydown", (e) => {
    const input = e.target.closest("[data-combobox-search]");
    if (!input) return;
    const root = input.closest("[data-combobox]");
    if (!root) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!root.classList.contains("is-open")) openList(root);
      moveHighlight(root, 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!root.classList.contains("is-open")) openList(root);
      moveHighlight(root, -1);
    } else if (e.key === "Enter") {
      if (root.classList.contains("is-open")) {
        const p = parts(root);
        const hi = p.options.find((o) => !o.hidden && o.classList.contains("is-highlighted"))
          || p.options.find((o) => !o.hidden);
        if (hi) {
          e.preventDefault();
          selectOption(root, hi);
        }
      }
    } else if (e.key === "Escape") {
      if (root.classList.contains("is-open")) {
        e.preventDefault();
        e.stopPropagation();
        closeList(root, true);
      }
    }
  });

  document.addEventListener("DOMContentLoaded", () => initAll(document));

  document.addEventListener("change", (e) => {
    const ctrl = e.target.closest("form [data-auto-submit]");
    if (!ctrl || ctrl.closest("[data-combobox]")) return;
    const form = ctrl.closest("form");
    if (form) {
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.submit();
    }
  });

  window.MondayCombobox = {
    init: initAll,
    closeAll: closeAll,
  };
})();

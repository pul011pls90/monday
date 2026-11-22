/* Monday — single delegated CSP-safe controller for right-side slide-over drawers. */
(function () {
  "use strict";

  const activeFocusReturn = new WeakMap();
  const activeAbort = new WeakMap();

  function visibleDrawers() {
    return Array.from(document.querySelectorAll("[data-drawer-root]")).filter((el) => !el.hidden);
  }

  function applyPartialMarkup(root, html) {
    const bodyEl = root.querySelector("[data-drawer-body]");
    if (!bodyEl) return;
    bodyEl.innerHTML = html;

    const headSrc = bodyEl.querySelector("[data-drawer-partial-head]");
    const actionsSlot = root.querySelector("[data-drawer-actions]");
    if (actionsSlot) {
      if (headSrc) {
        actionsSlot.innerHTML = headSrc.innerHTML;
        actionsSlot.hidden = !actionsSlot.innerHTML.trim();
        headSrc.remove();
      } else {
        actionsSlot.innerHTML = "";
        actionsSlot.hidden = true;
      }
    }

    const titleSrc = bodyEl.querySelector("[data-drawer-partial-title]");
    const titleSlot = root.querySelector("[data-drawer-title]");
    if (titleSrc && titleSlot) {
      titleSlot.textContent = titleSrc.textContent.trim();
      titleSrc.remove();
    }

    const footSrc = bodyEl.querySelector("[data-drawer-partial-foot]");
    const footSlot = root.querySelector("[data-drawer-foot]");
    if (footSlot) {
      if (footSrc) {
        footSlot.innerHTML = footSrc.innerHTML;
        footSlot.hidden = !footSlot.innerHTML.trim();
        footSrc.remove();
      } else {
        footSlot.innerHTML = "";
        footSlot.hidden = true;
      }
    }

    if (window.MondayRenderMath) window.MondayRenderMath(bodyEl);
    if (window.MondayCombobox && typeof window.MondayCombobox.init === "function") {
      window.MondayCombobox.init(root);
    }
  }

  function showDrawer(root, opener) {
    if (!root) return;
    const savedScrollX = window.scrollX;
    const savedScrollY = window.scrollY;
    if (opener) activeFocusReturn.set(root, opener);

    root.hidden = false;
    requestAnimationFrame(() => root.classList.add("is-open"));

    const panel = root.querySelector("[data-drawer-panel]");
    if (panel && typeof panel.focus === "function") {
      try {
        panel.focus({ preventScroll: true });
      } catch (_e) {
        panel.focus();
      }
    }
    window.scrollTo(savedScrollX, savedScrollY);
  }

  function closeDrawer(root) {
    if (!root || root.hidden) return;
    const ctrl = activeAbort.get(root);
    if (ctrl) {
      ctrl.abort();
      activeAbort.delete(root);
    }
    root.classList.remove("is-open");

    const urlParam = (root.dataset.drawerUrlParam || "").trim();
    if (urlParam && window.history && window.history.replaceState) {
      const nextUrl = new URL(window.location.href);
      if (nextUrl.searchParams.has(urlParam)) {
        nextUrl.searchParams.delete(urlParam);
        window.history.replaceState(null, "", nextUrl);
      }
    } else if (window.location.hash === `#${root.id}` && window.history && window.history.replaceState) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }

    const finalize = () => {
      if (!root.classList.contains("is-open")) root.hidden = true;
    };
    setTimeout(finalize, 180);

    const opener = activeFocusReturn.get(root);
    if (opener && typeof opener.focus === "function" && document.contains(opener)) {
      try {
        opener.focus({ preventScroll: true });
      } catch (_e) {
        opener.focus();
      }
    }
    activeFocusReturn.delete(root);
  }

  async function loadDrawerUrl(root, url, opener, fallbackHref) {
    const bodyEl = root.querySelector("[data-drawer-body]");
    const actionsSlot = root.querySelector("[data-drawer-actions]");
    const footSlot = root.querySelector("[data-drawer-foot]");
    const prev = activeAbort.get(root);
    if (prev) prev.abort();

    const ctrl = new AbortController();
    activeAbort.set(root, ctrl);

    if (actionsSlot) {
      actionsSlot.innerHTML = "";
      actionsSlot.hidden = true;
    }
    if (footSlot) {
      footSlot.innerHTML = "";
      footSlot.hidden = true;
    }
    if (bodyEl) {
      bodyEl.innerHTML = '<div class="drawer__loading" role="status"><span class="small muted">Загрузка…</span></div>';
    }
    showDrawer(root, opener);

    try {
      const targetUrl = new URL(url, window.location.origin);
      targetUrl.searchParams.set("fragment", "1");
      const res = await fetch(targetUrl, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "fetch" },
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const html = await res.text();
      if (ctrl.signal.aborted) return;
      applyPartialMarkup(root, html);

      const urlParam = (root.dataset.drawerUrlParam || "").trim();
      if (urlParam && window.history && window.history.replaceState) {
        const nextUrl = new URL(window.location.href);
        const paramVal = targetUrl.searchParams.get(urlParam);
        if (paramVal) nextUrl.searchParams.set(urlParam, paramVal);
        window.history.replaceState(null, "", nextUrl);
      }
    } catch (err) {
      if (err && err.name === "AbortError") return;
      if (fallbackHref) {
        window.location.href = fallbackHref;
        return;
      }
      if (bodyEl) {
        bodyEl.innerHTML = '<p class="small muted">Не удалось загрузить карточку. Попробуйте обновить страницу.</p>';
      }
    }
  }

  document.addEventListener("click", (e) => {
    const closeBtn = e.target.closest("[data-drawer-close]");
    if (closeBtn) {
      const targetId = closeBtn.getAttribute("data-drawer-close");
      const root = targetId ? document.getElementById(targetId) : closeBtn.closest("[data-drawer-root]");
      if (root) {
        e.preventDefault();
        closeDrawer(root);
        return;
      }
    }

    const trigger = e.target.closest("[data-drawer-open]");
    if (trigger) {
      const drawerId = trigger.getAttribute("data-drawer-open");
      const root = drawerId ? document.getElementById(drawerId) : null;
      if (!root) return;
      e.preventDefault();
      const parentMenu = trigger.closest("details.menu");
      if (parentMenu) parentMenu.removeAttribute("open");

      const drawerTitle = trigger.getAttribute("data-drawer-title-text");
      if (drawerTitle) {
        const titleSlot = root.querySelector("[data-drawer-title]");
        if (titleSlot) titleSlot.textContent = drawerTitle;
      }

      const url = trigger.getAttribute("data-drawer-url");
      if (url && window.fetch) {
        const fallbackHref = trigger.getAttribute("href") || "";
        loadDrawerUrl(root, url, trigger, fallbackHref);
      } else {
        showDrawer(root, trigger);
        if (window.MondayCombobox && typeof window.MondayCombobox.init === "function") {
          window.MondayCombobox.init(root);
        }
      }
    }
  });

  document.addEventListener("submit", async (e) => {
    const form = e.target;
    if (!form || !form.matches || !form.matches("[data-drawer-ajax]")) return;
    const root = form.closest("[data-drawer-root]");
    if (!root || !window.fetch) return;
    e.preventDefault();

    const submitter = e.submitter || form.querySelector('button[type="submit"]');
    if (submitter) submitter.disabled = true;
    try {
      const res = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { "X-Requested-With": "fetch" },
      });
      const ct = (res.headers.get("content-type") || "").toLowerCase();
      if (ct.indexOf("text/html") !== -1) {
        const html = await res.text();
        if (html.indexOf("data-drawer-partial") !== -1) {
          applyPartialMarkup(root, html);
          return;
        }
      }
      if (res.redirected && res.url) {
        window.location.href = res.url;
        return;
      }
      window.location.reload();
    } catch (_err) {
      form.submit();
    } finally {
      if (submitter) submitter.disabled = false;
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const openOnes = visibleDrawers();
    if (!openOnes.length) return;
    closeDrawer(openOnes[openOnes.length - 1]);
  });

  // Support deep link hash #<drawer_id> (e.g. #new-lead or #student-new-drawer)
  window.addEventListener("DOMContentLoaded", () => {
    const hashId = (window.location.hash || "").replace(/^#/, "");
    if (hashId) {
      const root = document.getElementById(hashId);
      if (root && root.hasAttribute("data-drawer-root")) {
        showDrawer(root, null);
      }
    }
  });

  window.MondayDrawer = {
    open: showDrawer,
    close: closeDrawer,
    load: loadDrawerUrl,
  };
})();

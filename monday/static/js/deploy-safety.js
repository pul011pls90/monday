/* Deploy safety: offline-resilient outbox, multi-tab sync, site-status & version polling, and resume helpers. */
(function () {
  "use strict";

  const body = document.body;
  if (!body) return;

  const USER_ID = (body.dataset.userId || "").trim();
  const INITIAL_VERSION = (body.dataset.appVersion || "").trim();
  const STATUS_URL = body.dataset.siteStatusUrl || "/api/site-status";
  const VERSION_URL = body.dataset.versionUrl || "/api/version";
  const SAVE_URL = "/api/activity/save";
  const COMPLETE_URL = "/api/activity/complete";
  const CSRF_TOKEN =
    (document.querySelector('meta[name="csrf-token"]') || {}).content ||
    (document.querySelector('input[name="csrf_token"]') || {}).value ||
    "";

  const DB_NAME = "monday_deploy_safety";
  const STORE_NAME = "outbox";
  const LS_KEY = USER_ID ? `monday_outbox_u${USER_ID}` : "";
  const DISMISS_BANNER_KEY = "monday_ds_banner_collapsed";

  // --------------------------------------------------------------------------- utilities
  function uuid() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return "op-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
  }

  function withJitter(ms) {
    const spread = ms * 0.15;
    return Math.max(1000, Math.round(ms + (Math.random() * 2 - 1) * spread));
  }

  // --------------------------------------------------------------------------- IndexedDB + localStorage fallback
  let dbPromise = null;
  function openIDB() {
    if (dbPromise) return dbPromise;
    if (!("indexedDB" in window)) return Promise.resolve(null);
    dbPromise = new Promise((resolve) => {
      try {
        const req = window.indexedDB.open(DB_NAME, 1);
        req.onupgradeneeded = (e) => {
          const db = e.target.result;
          if (!db.objectStoreNames.contains(STORE_NAME)) {
            const store = db.createObjectStore(STORE_NAME, { keyPath: "seq", autoIncrement: true });
            store.createIndex("by_user", "userId", { unique: false });
          }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => resolve(null);
      } catch (_err) {
        resolve(null);
      }
    });
    return dbPromise;
  }

  function lsRead() {
    if (!LS_KEY) return [];
    try {
      const raw = window.localStorage.getItem(LS_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr : [];
    } catch (_e) {
      return [];
    }
  }

  function lsWrite(items) {
    if (!LS_KEY) return;
    try {
      if (!items.length) window.localStorage.removeItem(LS_KEY);
      else window.localStorage.setItem(LS_KEY, JSON.stringify(items));
    } catch (_e) {
      // ignore quota errors
    }
  }

  async function outboxAdd(item) {
    if (!USER_ID) return;
    const entry = { ...item, userId: USER_ID, enqueuedAt: Date.now() };
    const db = await openIDB();
    if (db) {
      try {
        await new Promise((resolve, reject) => {
          const tx = db.transaction(STORE_NAME, "readwrite");
          tx.objectStore(STORE_NAME).add(entry);
          tx.oncomplete = resolve;
          tx.onerror = reject;
        });
        return;
      } catch (_e) {
        // fallback to localStorage
      }
    }
    const items = lsRead();
    entry.seq = (items.length ? (items[items.length - 1].seq || 0) : 0) + 1;
    items.push(entry);
    lsWrite(items);
  }

  async function outboxList() {
    if (!USER_ID) return [];
    const db = await openIDB();
    if (db) {
      try {
        return await new Promise((resolve) => {
          const tx = db.transaction(STORE_NAME, "readonly");
          const idx = tx.objectStore(STORE_NAME).index("by_user");
          const req = idx.getAll(IDBKeyRange.only(USER_ID));
          req.onsuccess = () => resolve((req.result || []).sort((a, b) => (a.seq || 0) - (b.seq || 0)));
          req.onerror = () => resolve(lsRead());
        });
      } catch (_e) {
        // fallback
      }
    }
    return lsRead();
  }

  async function outboxRemove(seq) {
    if (!USER_ID) return;
    const db = await openIDB();
    if (db) {
      try {
        await new Promise((resolve) => {
          const tx = db.transaction(STORE_NAME, "readwrite");
          tx.objectStore(STORE_NAME).delete(seq);
          tx.oncomplete = resolve;
          tx.onerror = resolve;
        });
        return;
      } catch (_e) {
        // fallback
      }
    }
    lsWrite(lsRead().filter((it) => it.seq !== seq));
  }

  async function clearUserOutbox() {
    if (LS_KEY) {
      try { window.localStorage.removeItem(LS_KEY); } catch (_e) {}
    }
    const db = await openIDB();
    if (db && USER_ID) {
      try {
        const items = await outboxList();
        await new Promise((resolve) => {
          const tx = db.transaction(STORE_NAME, "readwrite");
          const store = tx.objectStore(STORE_NAME);
          items.forEach((it) => store.delete(it.seq));
          tx.oncomplete = resolve;
          tx.onerror = resolve;
        });
      } catch (_e) {}
    }
  }

  // Purge per-user outbox on logout
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (form && form.tagName === "FORM" && /\/logout\b/.test(form.getAttribute("action") || "")) {
      clearUserOutbox();
    }
  });

  // --------------------------------------------------------------------------- Multi-tab sync
  const bc = "BroadcastChannel" in window ? new BroadcastChannel("monday-activity-sync") : null;
  let currentVersion = 1;
  let activeEl = null;

  function broadcastSync(payload) {
    if (!USER_ID) return;
    const msg = { ...payload, userId: USER_ID, ts: Date.now() };
    if (bc) {
      try { bc.postMessage(msg); } catch (_e) {}
    }
    try {
      window.localStorage.setItem("monday_ds_sync_event", JSON.stringify(msg));
    } catch (_e) {}
  }

  function handleSyncMessage(msg) {
    if (!msg || msg.userId !== USER_ID || !activeEl) return;
    const myType = activeEl.dataset.dsType;
    const myId = activeEl.dataset.dsId;
    if (msg.type === myType && String(msg.activityId) === String(myId)) {
      if (typeof msg.version === "number" && msg.version > currentVersion) {
        currentVersion = msg.version;
      }
    }
  }

  if (bc) bc.addEventListener("message", (e) => handleSyncMessage(e.data));
  window.addEventListener("storage", (e) => {
    if (e.key === "monday_ds_sync_event" && e.newValue) {
      try { handleSyncMessage(JSON.parse(e.newValue)); } catch (_err) {}
    }
  });

  // --------------------------------------------------------------------------- Banner UI (Stage 3)
  let bannerHost = null;
  let lastMaint = { state: "off", message: "", expected_minutes: 15, starts_at: null };
  let connectionLost = !navigator.onLine;
  let newVersionAvailable = false;
  let recoveryTimer = null;
  let showSavedRecovery = false;
  let statusEtag = "";

  function ensureBannerHost() {
    if (bannerHost) return bannerHost;
    bannerHost = document.getElementById("ds-banner-host");
    if (!bannerHost) {
      bannerHost = document.createElement("div");
      bannerHost.id = "ds-banner-host";
      bannerHost.className = "ds-banner-host";
      document.body.prepend(bannerHost);
    }
    return bannerHost;
  }

  function minutesUntil(iso) {
    if (!iso) return null;
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return null;
    return Math.max(0, Math.ceil((t - Date.now()) / 60000));
  }

  function setSavePillState(kind) {
    const pill = document.querySelector("[data-ds-save-pill]");
    if (!pill) return;
    pill.dataset.state = kind;
    if (kind === "saving") {
      pill.textContent = pill.dataset.savingText || "Сохраняется…";
    } else if (kind === "offline") {
      pill.textContent = pill.dataset.offlineText || "Нет связи — ответы сохранены на этом устройстве";
    } else {
      pill.textContent = pill.dataset.savedText || "Сохранено";
    }
  }

  function updateServerActionLock(isActiveMaint) {
    document.querySelectorAll("[data-ds-server-action], form[data-test] button[type='submit']").forEach((btn) => {
      if (isActiveMaint) {
        if (!btn.hasAttribute("data-ds-was-disabled")) {
          btn.setAttribute("data-ds-was-disabled", btn.disabled ? "1" : "0");
        }
        btn.disabled = true;
        btn.title = "Идёт обновление платформы — отправка временно недоступна";
      } else if (btn.hasAttribute("data-ds-was-disabled")) {
        const was = btn.getAttribute("data-ds-was-disabled") === "1";
        btn.removeAttribute("data-ds-was-disabled");
        btn.disabled = was;
        btn.title = "";
      }
    });
  }

  function renderBanner() {
    const host = ensureBannerHost();
    const state = lastMaint.state || "off";
    let text = "";
    let showReload = false;
    let tone = "info";

    if (connectionLost) {
      text = "Связь потеряна. Не закрывайте страницу — ответы сохраняются локально.";
      tone = "warn";
    } else if (state === "active") {
      const mins = lastMaint.expected_minutes || 15;
      text = lastMaint.message
        ? `${lastMaint.message} (~${mins} мин). Ваши ответы сохранены на этом устройстве и отправятся автоматически, как только сайт вернётся.`
        : `Идёт обновление платформы (~${mins} мин). Ваши ответы сохранены на этом устройстве и отправятся автоматически, как только сайт вернётся.`;
      tone = "warn";
    } else if (state === "scheduled") {
      const minsLeft = minutesUntil(lastMaint.starts_at);
      const n = minsLeft !== null ? minsLeft : (lastMaint.expected_minutes || 15);
      text = lastMaint.message
        ? `${lastMaint.message} (через ${n} мин). Ответы сохраняются автоматически — вы сможете продолжить после перерыва.`
        : `Плановое обновление через ${n} мин. Ответы сохраняются автоматически — вы сможете продолжить после перерыва.`;
      tone = "info";
    } else if (showSavedRecovery) {
      text = "Прогресс сохранён.";
      tone = "ok";
    } else if (newVersionAvailable) {
      text = activeEl
        ? "Доступна новая версия платформы. Можно обновить после завершения задания."
        : "Доступна новая версия платформы.";
      showReload = !activeEl;
      tone = "info";
    }

    updateServerActionLock(state === "active");

    if (!text) {
      host.innerHTML = "";
      host.hidden = true;
      return;
    }

    const collapsed = window.sessionStorage.getItem(DISMISS_BANNER_KEY) === "1" && state !== "active" && !connectionLost;
    host.hidden = false;
    host.innerHTML = `
      <div class="ds-banner ds-banner--${tone}${collapsed ? " is-collapsed" : ""}" role="status" aria-live="polite">
        <div class="ds-banner__body">
          <span class="ds-banner__dot" aria-hidden="true"></span>
          <span class="ds-banner__text">${escapeHtml(text)}</span>
        </div>
        <div class="ds-banner__actions">
          ${showReload ? `<button type="button" class="btn btn--primary btn--sm ds-banner__btn" data-ds-reload>Обновить</button>` : ""}
          <button type="button" class="btn btn--ghost btn--sm ds-banner__btn" data-ds-toggle aria-expanded="${collapsed ? "false" : "true"}">${collapsed ? "Показать" : "Свернуть"}</button>
        </div>
      </div>
    `;

    const toggleBtn = host.querySelector("[data-ds-toggle]");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        const next = !collapsed;
        window.sessionStorage.setItem(DISMISS_BANNER_KEY, next ? "1" : "0");
        renderBanner();
      });
    }
    const reloadBtn = host.querySelector("[data-ds-reload]");
    if (reloadBtn) {
      reloadBtn.addEventListener("click", async () => {
        const pending = await outboxList();
        if (pending.length) {
          await flushOutbox();
        }
        window.location.reload();
      });
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // --------------------------------------------------------------------------- Outbox Flush (Stage 2)
  let flushing = false;
  let backoffMs = 1500;
  let flushTimer = null;

  async function postJson(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": CSRF_TOKEN,
      },
      body: JSON.stringify(payload),
    });
    if (res.status === 502 || res.status === 503 || res.status === 504) {
      const err = new Error("HTTP " + res.status);
      err.isServerUnavailable = true;
      throw err;
    }
    const data = await res.json().catch(() => ({}));
    return { status: res.status, data };
  }

  function scheduleFlush(delayMs) {
    if (flushTimer) clearTimeout(flushTimer);
    flushTimer = setTimeout(() => flushOutbox(), withJitter(delayMs));
  }

  async function flushOutbox() {
    if (!USER_ID || flushing) return;
    const items = await outboxList();
    if (!items.length) {
      backoffMs = 1500;
      if (connectionLost && navigator.onLine) {
        connectionLost = false;
        showSavedRecovery = true;
        clearTimeout(recoveryTimer);
        recoveryTimer = setTimeout(() => {
          showSavedRecovery = false;
          renderBanner();
        }, 4000);
        renderBanner();
      }
      setSavePillState("saved");
      return;
    }

    flushing = true;
    setSavePillState("saving");
    let hadItems = items.length > 0;
    try {
      for (const item of items) {
        const endpoint = item.kind === "complete" ? COMPLETE_URL : SAVE_URL;
        const { status, data } = await postJson(endpoint, item.payload);
        if (status === 409 && data && data.record) {
          if (typeof data.record.version === "number") {
            currentVersion = data.record.version;
          }
          await outboxRemove(item.seq);
          continue;
        }
        if (status >= 200 && status < 300) {
          if (data && data.record && typeof data.record.version === "number") {
            currentVersion = data.record.version;
            broadcastSync({
              type: data.record.type,
              activityId: data.record.activity_id,
              version: data.record.version,
              updatedAt: data.record.updated_at,
            });
          }
          await outboxRemove(item.seq);
        } else {
          // 4xx validation error -> drop bad item so queue isn't wedged
          await outboxRemove(item.seq);
        }
      }
      backoffMs = 1500;
      const wasLost = connectionLost;
      connectionLost = false;
      setSavePillState("saved");
      if (wasLost && hadItems) {
        showSavedRecovery = true;
        clearTimeout(recoveryTimer);
        recoveryTimer = setTimeout(() => {
          showSavedRecovery = false;
          renderBanner();
        }, 4500);
      }
      renderBanner();
    } catch (_err) {
      connectionLost = true;
      setSavePillState("offline");
      renderBanner();
      backoffMs = Math.min(30000, backoffMs * 2);
      scheduleFlush(backoffMs);
    } finally {
      flushing = false;
    }
  }

  // --------------------------------------------------------------------------- Activity State Collector
  function collectActivitySnapshot() {
    if (!activeEl) return null;
    const type = activeEl.dataset.dsType || "test";
    const activityId = activeEl.dataset.dsId || "";
    const title = activeEl.dataset.dsTitle || document.title.replace(/\s*·\s*Monday\s*$/, "");
    const subtitle = activeEl.dataset.dsSubtitle || "";
    const resumeUrl = activeEl.dataset.dsResumeUrl || window.location.pathname + window.location.search;

    const answers = {};
    let answered = 0;
    const total = parseInt(activeEl.dataset.dsTotal || "0", 10) || 0;

    // Collect form inputs
    const form = activeEl.tagName === "FORM" ? activeEl : activeEl.querySelector("form");
    if (form) {
      const seen = new Set();
      form.querySelectorAll("input, textarea, select").forEach((inp) => {
        const name = inp.name;
        if (!name || name === "csrf_token") return;
        if (inp.type === "radio") {
          if (inp.checked) {
            answers[name] = inp.value;
            seen.add(name);
          }
        } else if (inp.type === "checkbox") {
          if (!Array.isArray(answers[name])) answers[name] = [];
          if (inp.checked) {
            answers[name].push(inp.value);
            seen.add(name);
          }
        } else if (inp.value && inp.value.trim() !== "") {
          answers[name] = inp.value;
          seen.add(name);
        }
      });
      answered = seen.size;
    }

    // Current question index
    let qIndex = parseInt(activeEl.dataset.dsQuestionIndex || "0", 10) || 0;
    const activeDot = document.querySelector(".q-nav__dot.is-current, .steps .is-current");
    if (activeDot && activeDot.dataset && activeDot.dataset.q !== undefined) {
      qIndex = parseInt(activeDot.dataset.q, 10) || qIndex;
    }

    // Remaining timer seconds
    let remainingSeconds = null;
    const timerEl = document.querySelector("[data-timer]");
    if (timerEl) {
      const parsed = parseInt(timerEl.dataset.remaining || timerEl.dataset.timer || "", 10);
      if (!Number.isNaN(parsed)) remainingSeconds = Math.max(0, parsed);
    }

    return {
      type,
      activity_id: activityId,
      title,
      subtitle,
      resume_url: resumeUrl,
      answered: Math.max(answered, parseInt(activeEl.dataset.dsAnswered || "0", 10) || 0),
      total,
      if_version: currentVersion,
      client_updated_at: new Date().toISOString(),
      state: {
        question_index: qIndex,
        answers,
        remaining_seconds: remainingSeconds,
        filters: activeEl.dataset.dsFilters ? safeJson(activeEl.dataset.dsFilters) : {},
      },
    };
  }

  function safeJson(s) {
    try { return JSON.parse(s); } catch (_e) { return {}; }
  }

  async function enqueueSave(extra) {
    if (!USER_ID || !activeEl) return;
    const snap = collectActivitySnapshot();
    if (!snap) return;
    if (extra && typeof extra === "object") Object.assign(snap, extra);
    snap.client_op_id = uuid();
    setSavePillState("saving");
    await outboxAdd({ kind: "save", payload: snap });
    await flushOutbox();
  }

  async function markComplete(type, activityId, status) {
    if (!USER_ID) return;
    await outboxAdd({
      kind: "complete",
      payload: {
        type,
        activity_id: String(activityId || ""),
        status: status || "completed",
        client_op_id: uuid(),
      },
    });
    await flushOutbox();
  }

  // --------------------------------------------------------------------------- Restore saved state & timer (Stage 4)
  function initActivity() {
    activeEl = document.querySelector("[data-ds-activity]");
    if (!activeEl) return;

    const initialVer = parseInt(activeEl.dataset.dsVersion || "1", 10);
    if (!Number.isNaN(initialVer)) currentVersion = initialVer;

    // Show out-of-range fallback notice if flagged
    const params = new URLSearchParams(window.location.search);
    if (params.get("ds_oob") === "1") {
      const note = document.createElement("div");
      note.className = "flash flash--info ds-oob-note";
      note.setAttribute("role", "status");
      note.textContent = "Сохранённый вопрос больше недоступен — открыт ближайший вопрос.";
      activeEl.prepend(note);
    }

    // Track timer remaining seconds cleanly
    const timerEl = document.querySelector("[data-timer]");
    if (timerEl) {
      let rem = parseInt(timerEl.dataset.timer || "", 10);
      if (!Number.isNaN(rem)) {
        timerEl.dataset.remaining = String(rem);
        setInterval(() => {
          const cur = parseInt(timerEl.dataset.remaining || timerEl.dataset.timer || "0", 10);
          if (!Number.isNaN(cur) && cur > 0) {
            timerEl.dataset.remaining = String(cur - 1);
          }
        }, 1000);
      }
    }

    // Debounced input save
    let debounceTimer = null;
    activeEl.addEventListener("change", () => {
      clearTimeout(debounceTimer);
      enqueueSave();
    });
    activeEl.addEventListener("input", (e) => {
      if (e.target && (e.target.tagName === "TEXTAREA" || e.target.type === "text" || e.target.type === "number")) {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => enqueueSave(), 450);
      }
    });

    // Save on navigation between questions
    document.addEventListener("click", (e) => {
      const nav = e.target.closest(".q-nav__dot, [data-step], .pager a, [data-ds-nav]");
      if (nav) {
        if (nav.dataset && nav.dataset.q !== undefined) {
          activeEl.dataset.dsQuestionIndex = nav.dataset.q;
        }
        enqueueSave();
      }
    });

    // Save on visibilitychange / pagehide
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") enqueueSave();
    });
    window.addEventListener("pagehide", () => {
      enqueueSave();
    });

    // Periodic 15-second autosave while activity is open
    setInterval(() => {
      if (document.visibilityState === "visible") enqueueSave();
    }, 15000);

    // Initial save when entering an activity (or resume)
    setTimeout(() => enqueueSave(), 600);

    // Wire "Начать заново" discard link if present
    document.querySelectorAll("[data-ds-discard]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.preventDefault();
        const msg = btn.dataset.confirm || "Начать заново? Текущий прогресс будет сброшен.";
        const ok = await askConfirm({ title: msg, ok: btn.dataset.confirmOk || "Начать заново", danger: true });
        if (!ok) return;
        await markComplete(activeEl.dataset.dsType, activeEl.dataset.dsId, "abandoned");
        const href = btn.getAttribute("href");
        if (href) window.location.href = href;
        else window.location.reload();
      });
    });
  }

  // --------------------------------------------------------------------------- Site-status & Version polling (Stage 3)
  let pollTimer = null;

  async function pollSiteStatus() {
    if (document.visibilityState === "hidden") return;
    try {
      const headers = {};
      if (statusEtag) headers["If-None-Match"] = statusEtag;
      const res = await fetch(STATUS_URL, { headers, credentials: "same-origin" });
      if (res.status === 502 || res.status === 503 || res.status === 504) {
        connectionLost = true;
        renderBanner();
        schedulePoll(20000);
        return;
      }
      if (res.status === 200) {
        statusEtag = res.headers.get("ETag") || "";
        const nextMaint = await res.json();
        const prevState = lastMaint.state;
        lastMaint = nextMaint;
        if (prevState !== nextMaint.state && (nextMaint.state === "scheduled" || nextMaint.state === "active")) {
          enqueueSave();
        }
      }
      const wasLost = connectionLost;
      connectionLost = false;
      if (wasLost) flushOutbox();
    } catch (_err) {
      connectionLost = true;
    }

    // Check build version alongside
    try {
      const vres = await fetch(VERSION_URL, { credentials: "same-origin", cache: "no-store" });
      if (vres.ok) {
        const vdata = await vres.json();
        if (INITIAL_VERSION && vdata && vdata.version && vdata.version !== INITIAL_VERSION) {
          newVersionAvailable = true;
        }
      }
    } catch (_e) {}

    renderBanner();
    const fast = lastMaint.state === "scheduled" || lastMaint.state === "active" || connectionLost;
    schedulePoll(fast ? 20000 : 60000);
  }

  function schedulePoll(ms) {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(() => pollSiteStatus(), withJitter(ms));
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      pollSiteStatus();
      flushOutbox();
    } else if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  });

  window.addEventListener("online", () => {
    connectionLost = false;
    pollSiteStatus();
    flushOutbox();
  });

  window.addEventListener("offline", () => {
    connectionLost = true;
    setSavePillState("offline");
    renderBanner();
  });

  // --------------------------------------------------------------------------- Resume Card on Home (Stage 4)
  function askConfirm(opts) {
    if (typeof window.MondayConfirm === "function") return window.MondayConfirm(opts);
    return Promise.resolve(window.confirm(opts.title || ""));
  }

  async function initResumeCard() {
    const host = document.getElementById("ds-resume-card");
    if (!host || !USER_ID) return;
    if (window.sessionStorage.getItem("monday_ds_resume_later") === "1") return;
    try {
      const res = await fetch("/api/activity/latest", { credentials: "same-origin", cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      const records = (data && Array.isArray(data.records) ? data.records : []).slice(0, 3);
      if (!records.length) return;

      const itemsHtml = records.map((rec) => {
        const progress = rec.total ? `${rec.answered || 0} / ${rec.total}` : `${rec.answered || 0}`;
        const url = rec.resume_url || "/";
        const sep = url.includes("?") ? "&" : "?";
        const resumeHref = `${url}${sep}resume=1`;
        const title = (rec.title || "Незавершённое задание").trim();
        let sub = (rec.subtitle || "").trim();
        if (sub === title) {
          sub = "";
        } else if (sub.startsWith(title + " · ")) {
          sub = sub.slice(title.length + 3).trim();
        }
        return `
          <div class="ds-resume__item" data-ds-resume-item>
            <div class="ds-resume__meta">
              <span class="ds-resume__name">${escapeHtml(title)}</span>
              <span class="ds-resume__sub">${escapeHtml(sub ? `${sub} · ` : "")}Прогресс: ${escapeHtml(progress)}</span>
            </div>
            <div class="ds-resume__btns">
              <a class="btn btn--primary btn--sm ds-resume__btn" data-ds-resume-continue data-title="${escapeHtml(title)}" href="${escapeHtml(resumeHref)}">Продолжить</a>
              <button type="button" class="btn btn--ghost btn--sm ds-resume__btn" data-ds-resume-discard data-type="${escapeHtml(rec.type)}" data-id="${escapeHtml(rec.activity_id)}">Начать заново</button>
            </div>
          </div>
        `;
      }).join("");

      host.hidden = false;
      host.innerHTML = `
        <div class="ds-resume__head">
          <h2 class="ds-resume__title">Продолжим с того места, где остановились?</h2>
          <button type="button" class="btn btn--ghost btn--sm ds-resume__btn" data-ds-resume-later>Позже</button>
        </div>
        <div class="ds-resume__list">${itemsHtml}</div>
      `;

      const laterBtn = host.querySelector("[data-ds-resume-later]");
      if (laterBtn) {
        laterBtn.addEventListener("click", () => {
          window.sessionStorage.setItem("monday_ds_resume_later", "1");
          host.hidden = true;
        });
      }

      host.querySelectorAll("[data-ds-resume-continue]").forEach((link) => {
        link.addEventListener("click", async (e) => {
          e.preventDefault();
          const ok = await askConfirm({
            title: `Продолжить «${link.dataset.title || "тест"}»?`,
            body: "Вы продолжите с того места, где остановились.",
            ok: "Продолжить",
          });
          if (ok) window.location.href = link.getAttribute("href");
        });
      });

      host.querySelectorAll("[data-ds-resume-discard]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const ok = await askConfirm({
            title: "Начать заново? Текущий прогресс будет сброшен.",
            ok: "Начать заново",
            danger: true,
          });
          if (!ok) return;
          await markComplete(btn.dataset.type, btn.dataset.id, "abandoned");
          const row = btn.closest("[data-ds-resume-item]");
          if (row) row.remove();
          if (!host.querySelector("[data-ds-resume-item]")) {
            host.hidden = true;
          }
        });
      });
    } catch (_e) {}
  }

  // Expose public API for custom triggers & tests
  window.MondayDeploySafety = {
    saveNow: () => enqueueSave(),
    flushOutbox,
    markComplete,
    pollNow: pollSiteStatus,
    clearUserOutbox,
    getLastMaintenance: () => lastMaint,
  };

  initActivity();
  initResumeCard();
  pollSiteStatus();
  flushOutbox();
})();

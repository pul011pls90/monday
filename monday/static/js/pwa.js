/* Monday — PWA Service Worker registration, safe next-launch updates, logout cache cleanup, and offline retry. */
(function () {
  "use strict";

  const RUNTIME_CACHE_PREFIX = "monday-runtime-";

  async function clearRuntimeCachesViaClientAndSW() {
    const tasks = [];
    if ("caches" in window) {
      tasks.push(
        window.caches.keys().then((names) =>
          Promise.all(
            names
              .filter((n) => n.startsWith(RUNTIME_CACHE_PREFIX))
              .map((n) => window.caches.delete(n))
          )
        ).catch(() => {})
      );
    }
    if ("serviceWorker" in navigator) {
      tasks.push(
        navigator.serviceWorker.ready
          .then((reg) => {
            const target = navigator.serviceWorker.controller || reg.active;
            if (!target) return;
            return new Promise((resolve) => {
              let settled = false;
              const finish = () => {
                if (!settled) {
                  settled = true;
                  resolve();
                }
              };
              const ch = new MessageChannel();
              ch.port1.onmessage = finish;
              setTimeout(finish, 180);
              target.postMessage({ type: "CLEAR_RUNTIME_CACHES" }, [ch.port2]);
            });
          })
          .catch(() => {})
      );
    }
    await Promise.all(tasks);
  }

  function consumeCookieFlag(name) {
    const prefix = name + "=";
    const hit = document.cookie.split(";").some((part) => part.trim().startsWith(prefix));
    if (hit) {
      document.cookie = name + "=; Max-Age=0; Path=/; SameSite=Lax";
    }
    return hit;
  }

  function markUpdateAvailable(worker) {
    window.__mondaySwUpdateReady = true;
    document.documentElement.dataset.swUpdateAvailable = "1";
    window.dispatchEvent(
      new CustomEvent("monday:sw-update-available", { detail: { worker: worker } })
    );
    // Deliberately do NOT call skipWaiting() or reload() here so open forms/tests are never lost;
    // the waiting worker activates cleanly on the next app launch.
  }

  function initServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .then((reg) => {
        if (reg.waiting && navigator.serviceWorker.controller) {
          markUpdateAvailable(reg.waiting);
        }
        reg.addEventListener("updatefound", () => {
          const next = reg.installing;
          if (!next) return;
          next.addEventListener("statechange", () => {
            if (next.state === "installed" && navigator.serviceWorker.controller) {
              markUpdateAvailable(next);
            }
          });
        });
      })
      .catch(() => {});
  }

  // Clear runtime caches if redirected here right after POST /logout
  if (consumeCookieFlag("monday_sw_clear")) {
    clearRuntimeCachesViaClientAndSW();
  }

  // Also clear runtime caches before submitting any logout form (bounded wait so submit stays snappy)
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (!form || !form.matches || !form.matches('form[action$="/logout"]')) return;
    if (form.dataset.pwaCleared === "1") return;
    if (!("caches" in window) && !("serviceWorker" in navigator)) return;
    e.preventDefault();
    form.dataset.pwaCleared = "1";
    Promise.race([
      clearRuntimeCachesViaClientAndSW(),
      new Promise((resolve) => setTimeout(resolve, 180)),
    ]).finally(() => {
      form.submit();
    });
  });

  // Offline fallback retry button
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-offline-retry]");
    if (!btn) return;
    btn.disabled = true;
    window.location.reload();
  });

  window.addEventListener("load", initServiceWorker);

  window.MondayPWA = {
    clearRuntimeCaches: clearRuntimeCachesViaClientAndSW,
  };
})();

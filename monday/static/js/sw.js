/* Monday — minimal, security-first Service Worker (static shell + /offline only). */
(function (globalScope) {
  "use strict";

  const CFG = (globalScope && globalScope.__MONDAY_SW_CONFIG) || {};
  const CACHE_VERSION = String(CFG.version || "dev-v1");
  const PRECACHE_PREFIX = "monday-precache-";
  const RUNTIME_PREFIX = "monday-runtime-";
  const PRECACHE_NAME = PRECACHE_PREFIX + CACHE_VERSION;
  const RUNTIME_CACHE = RUNTIME_PREFIX + CACHE_VERSION;
  const OFFLINE_URL = "/offline";
  const PRECACHE_URLS = Array.isArray(CFG.precacheUrls) && CFG.precacheUrls.length
    ? CFG.precacheUrls
    : [OFFLINE_URL];

  // Routes that must NEVER be cached in CacheStorage (authenticated HTML, APIs, uploads, role panels, auth).
  const NEVER_CACHE_PREFIXES = [
    "/api/",
    "/uploads/",
    "/admin",
    "/manager",
    "/academic",
    "/teacher",
    "/assistant",
    "/student",
    "/home",
    "/bank",
    "/daily",
    "/course",
    "/roadmap",
    "/fx",
    "/formulas",
    "/reports",
    "/picker",
    "/login",
    "/register",
    "/logout",
    "/join",
    "/auth",
    "/pending",
    "/account",
    "/profile",
    "/onboarding",
    "/sessions",
    "/settings",
    "/about",
    "/sw.js",
    "/manifest.webmanifest",
  ];

  // Only these versioned/static asset subtrees and extensions are eligible for runtime static caching.
  const CACHEABLE_STATIC_PREFIXES = [
    "/static/css/",
    "/static/js/",
    "/static/fonts/",
    "/static/img/",
    "/static/vendor/",
  ];

  const CACHEABLE_STATIC_EXT_RE = /\.(?:css|js|woff2?|ttf|otf|png|jpg|jpeg|webp|svg|ico)$/i;

  function matchesPrefix(pathname, prefix) {
    if (prefix.endsWith("/")) return pathname.startsWith(prefix);
    return pathname === prefix || pathname.startsWith(prefix + "/");
  }

  function isStaticAssetPath(pathname) {
    return (
      CACHEABLE_STATIC_PREFIXES.some((p) => pathname.startsWith(p)) &&
      CACHEABLE_STATIC_EXT_RE.test(pathname)
    );
  }

  function classifyRequest(opts) {
    const method = String((opts && opts.method) || "GET").toUpperCase();
    const origin = String((opts && opts.origin) || "");
    const rawUrl = String((opts && opts.url) || "");
    const mode = String((opts && opts.mode) || "");
    const accept = String((opts && opts.accept) || "");

    if (method !== "GET") {
      return { action: "bypass", cacheable: false, reason: "non_get" };
    }

    let parsed;
    try {
      parsed = new URL(rawUrl, origin || "https://monday.local");
    } catch (_e) {
      return { action: "bypass", cacheable: false, reason: "invalid_url" };
    }

    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return { action: "bypass", cacheable: false, reason: "non_http" };
    }

    if (origin && parsed.origin !== origin) {
      return { action: "bypass", cacheable: false, reason: "cross_origin" };
    }

    const pathname = parsed.pathname || "/";
    const isNavigation = mode === "navigate" || accept.indexOf("text/html") !== -1;

    if (pathname === OFFLINE_URL) {
      return {
        action: isNavigation ? "network-first-navigation" : "precache-shell",
        cacheable: false,
        reason: "offline_fallback",
      };
    }

    if (NEVER_CACHE_PREFIXES.some((p) => matchesPrefix(pathname, p))) {
      return {
        action: isNavigation ? "network-first-navigation" : "bypass",
        cacheable: false,
        reason: "never_cache_route",
      };
    }

    if (isNavigation) {
      return {
        action: "network-first-navigation",
        cacheable: false,
        reason: "navigation_html",
      };
    }

    if (isStaticAssetPath(pathname)) {
      const hasVersion = parsed.searchParams.has("v");
      return {
        action: hasVersion ? "cache-first-static" : "network-first-static",
        cacheable: true,
        reason: hasVersion ? "versioned_static" : "unversioned_static_asset",
      };
    }

    return { action: "bypass", cacheable: false, reason: "non_cacheable_path" };
  }

  function isCacheableResponse(reqOpts, res) {
    const decision = classifyRequest(reqOpts);
    if (!decision.cacheable) return false;
    if (!res || !res.ok || res.status !== 200) return false;
    if (res.type && res.type !== "basic") return false;
    const ct = res.headers && typeof res.headers.get === "function"
      ? String(res.headers.get("content-type") || "").toLowerCase()
      : "";
    if (ct.indexOf("text/html") !== -1 || ct.indexOf("application/json") !== -1) {
      return false;
    }
    return true;
  }

  function cachesToDeleteOnActivate(cacheNames) {
    return (cacheNames || []).filter((name) => {
      if (!name) return false;
      if (name === PRECACHE_NAME || name === RUNTIME_CACHE) return false;
      return name.startsWith(PRECACHE_PREFIX) || name.startsWith(RUNTIME_PREFIX) || name.startsWith("monday-");
    });
  }

  function runtimeCachesToDeleteOnLogout(cacheNames) {
    return (cacheNames || []).filter((name) => name && name.startsWith(RUNTIME_PREFIX));
  }

  const exported = {
    CACHE_VERSION: CACHE_VERSION,
    PRECACHE_NAME: PRECACHE_NAME,
    RUNTIME_CACHE: RUNTIME_CACHE,
    OFFLINE_URL: OFFLINE_URL,
    PRECACHE_URLS: PRECACHE_URLS,
    NEVER_CACHE_PREFIXES: NEVER_CACHE_PREFIXES,
    classifyRequest: classifyRequest,
    isCacheableResponse: isCacheableResponse,
    cachesToDeleteOnActivate: cachesToDeleteOnActivate,
    runtimeCachesToDeleteOnLogout: runtimeCachesToDeleteOnLogout,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = exported;
  }
  if (globalScope) {
    globalScope.__MondaySW = exported;
  }

  const IN_SERVICE_WORKER =
    globalScope &&
    typeof globalScope.addEventListener === "function" &&
    typeof caches !== "undefined" &&
    typeof clients !== "undefined" &&
    (typeof ServiceWorkerGlobalScope === "undefined" || globalScope instanceof ServiceWorkerGlobalScope);

  if (!IN_SERVICE_WORKER) return;

  async function clearRuntimeCaches() {
    const names = await caches.keys();
    const targets = runtimeCachesToDeleteOnLogout(names);
    await Promise.all(targets.map((name) => caches.delete(name)));
    return targets;
  }

  async function offlineFallbackResponse() {
    const cache = await caches.open(PRECACHE_NAME);
    const cached = await cache.match(OFFLINE_URL, { ignoreSearch: true });
    if (cached) return cached;
    return new Response(
      "<!doctype html><html lang='ru'><meta charset='utf-8'><title>Офлайн · Monday</title>" +
        "<body style='font-family:system-ui,sans-serif;padding:32px;text-align:center'>" +
        "<h1>Нет подключения к интернету</h1>" +
        "<p>Проверьте соединение и попробуйте снова.</p>" +
        "<button type='button' onclick='location.reload()'>Повторить</button>" +
        "</body></html>",
      { status: 503, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } }
    );
  }

  globalScope.addEventListener("install", (event) => {
    // Do NOT call skipWaiting() here so active tests/forms are never interrupted mid-session;
    // updates apply cleanly on next launch (or explicit SKIP_WAITING when idle).
    event.waitUntil(
      caches.open(PRECACHE_NAME).then(async (cache) => {
        await Promise.all(
          PRECACHE_URLS.map(async (url) => {
            try {
              const req = new Request(url, { cache: "reload" });
              const res = await fetch(req);
              if (res && res.ok) {
                await cache.put(url, res);
              }
            } catch (_e) {
              // Ignore single-asset failure on install so SW install remains resilient.
            }
          })
        );
      })
    );
  });

  globalScope.addEventListener("activate", (event) => {
    event.waitUntil(
      caches.keys().then(async (names) => {
        const obsolete = cachesToDeleteOnActivate(names);
        await Promise.all(obsolete.map((name) => caches.delete(name)));
      })
    );
  });

  globalScope.addEventListener("message", (event) => {
    const data = (event && event.data) || {};
    if (data.type === "CLEAR_RUNTIME_CACHES" || data.type === "LOGOUT") {
      event.waitUntil(
        clearRuntimeCaches().then((deleted) => {
          if (event.ports && event.ports[0]) {
            event.ports[0].postMessage({ ok: true, deleted: deleted });
          }
        })
      );
      return;
    }
    if (data.type === "SKIP_WAITING") {
      globalScope.skipWaiting();
    }
  });

  globalScope.addEventListener("fetch", (event) => {
    const req = event.request;
    const reqInfo = {
      method: req.method,
      url: req.url,
      mode: req.mode,
      accept: req.headers ? req.headers.get("accept") || "" : "",
      origin: globalScope.location ? globalScope.location.origin : "",
    };
    const decision = classifyRequest(reqInfo);

    if (decision.action === "bypass") {
      return;
    }

    if (decision.action === "network-first-navigation") {
      event.respondWith(
        fetch(req).catch(() => offlineFallbackResponse())
      );
      return;
    }

    if (decision.action === "cache-first-static") {
      event.respondWith(
        (async () => {
          const cached = await caches.match(req);
          if (cached) return cached;
          const res = await fetch(req);
          if (isCacheableResponse(reqInfo, res)) {
            const cache = await caches.open(RUNTIME_CACHE);
            cache.put(req, res.clone());
          }
          return res;
        })()
      );
      return;
    }

    if (decision.action === "network-first-static") {
      event.respondWith(
        (async () => {
          try {
            const res = await fetch(req);
            if (isCacheableResponse(reqInfo, res)) {
              const cache = await caches.open(RUNTIME_CACHE);
              cache.put(req, res.clone());
            }
            return res;
          } catch (_e) {
            const cached = await caches.match(req);
            if (cached) return cached;
            throw _e;
          }
        })()
      );
    }
  });
})(typeof self !== "undefined" ? self : globalThis);

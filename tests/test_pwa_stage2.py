"""Stage 2 PWA tests: Service Worker routing rules, never-cache personalized routes, /offline, logout clear, CSP."""
from __future__ import annotations

import json
import os
import re
import subprocess

from config import Config
from monday import create_app
from monday.extensions import db
from monday.models import StudentProfile, User
from test_app import client, login

JSC_BIN = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc"


def _eval_sw_js(sw_source: str, test_script: str) -> dict:
    """Execute the served /sw.js script inside Apple JavaScriptCore (jsc) and return parsed JSON output."""
    assert os.path.isfile(JSC_BIN), "jsc helper required for Stage 2 JS unit tests"
    harness = f"""
var self = this;
var location = {{ origin: "https://monday.kg" }};
var module = undefined;
if (typeof URL === "undefined") {{
  this.URL = function(input, base) {{
    var s = String(input || "");
    if (s.indexOf("://") === -1 && base) {{
      var b = String(base).replace(/\\/$/, "");
      s = s.charAt(0) === "/" ? b + s : b + "/" + s;
    }}
    var m = /^(https?):\\/\\/([^\\/?#]+)([^?#]*)(\\?[^#]*)?/.exec(s);
    if (!m) throw new Error("Invalid URL: " + s);
    this.protocol = m[1] + ":";
    this.host = m[2];
    this.origin = this.protocol + "//" + this.host;
    this.pathname = m[3] || "/";
    this.search = m[4] || "";
    var params = {{}};
    if (this.search.length > 1) {{
      this.search.slice(1).split("&").forEach(function(pair) {{
        var kv = pair.split("=");
        params[decodeURIComponent(kv[0])] = kv.length > 1 ? decodeURIComponent(kv[1]) : "";
      }});
    }}
    this.searchParams = {{ has: function(k) {{ return Object.prototype.hasOwnProperty.call(params, k); }} }};
  }};
}}
{sw_source}
var result = (function() {{
{test_script}
}})();
print(JSON.stringify(result));
"""
    proc = subprocess.run([JSC_BIN, "-e", harness], capture_output=True, text=True, check=True)
    return json.loads(proc.stdout.strip())


def test_sw_and_offline_endpoints_served_with_safe_headers():
    c = client()

    # /sw.js served from root with correct headers & strict CSP
    r_sw = c.get("/sw.js")
    assert r_sw.status_code == 200
    assert r_sw.headers.get("Content-Type", "").startswith("application/javascript")
    assert r_sw.headers.get("Service-Worker-Allowed") == "/"
    cc = r_sw.headers.get("Cache-Control", "")
    assert "no-cache" in cc and "must-revalidate" in cc

    csp = r_sw.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp and "worker-src 'self' blob:" in csp

    sw_body = r_sw.data.decode("utf-8")
    m = re.search(r"self\.__MONDAY_SW_CONFIG\s*=\s*(\{.*?\});", sw_body)
    assert m, "SW config banner missing"
    cfg = json.loads(m.group(1))
    assert cfg["version"].startswith("v1-")
    assert "/offline" in cfg["precacheUrls"]

    # Every precached shell URL must resolve 200 OK
    for url in cfg["precacheUrls"]:
        r_pc = c.get(url)
        assert r_pc.status_code == 200, f"Precache asset {url} returned {r_pc.status_code}"

    # /offline renders Russian copy + retry button and contains zero session/CSRF/user data even when logged in
    c_auth = client()
    login(c_auth, "admin@monday.kg", "monday2026")
    r_off = c_auth.get("/offline")
    assert r_off.status_code == 200
    html = r_off.data.decode("utf-8")
    assert "Нет подключения к интернету" in html
    assert "data-offline-retry" in html and "Повторить" in html
    assert 'name="csrf-token"' not in html
    assert "data-user-id" not in html
    assert "monday2026" not in html and "admin@monday.kg" not in html


def test_sw_and_offline_exempt_from_site_lock_and_forced_password_change(tmp_path):
    class LockCfg(Config):
        TESTING = True
        SECRET_KEY = "sw-lock-secret"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'sw_lock.db'}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SQLALCHEMY_ENGINE_OPTIONS = {}
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        SEED_DEMO = False
        IMPORT_PACKS = False

    app = create_app(LockCfg, seed_if_empty=False)
    with app.app_context():
        db.create_all()
        adm = User(email="adm@sw.kg", name="Adm", role="admin", is_approved=True)
        adm.set_password("StrongPass123!")
        stu = User(email="stu@sw.kg", name="Stu", role="student", is_approved=True, must_change_password=True)
        stu.set_password("StrongPass123!")
        stu.profile = StudentProfile(exam="SAT", grade="11", onboarded=True)
        db.session.add_all([adm, stu])
        db.session.commit()

    c_adm = app.test_client()
    c_adm.post("/login", data={"email": "adm@sw.kg", "password": "StrongPass123!"})
    c_adm.post("/admin/maintenance", data={"action": "lock", "message": "Lock", "expected_minutes": "10"})

    c_anon = app.test_client()
    assert c_anon.get("/sw.js").status_code == 200
    assert c_anon.get("/offline").status_code == 200

    c_adm.post("/admin/maintenance", data={"action": "unlock"})
    c_stu = app.test_client()
    c_stu.post("/login", data={"email": "stu@sw.kg", "password": "StrongPass123!"})
    assert c_stu.get("/sw.js").status_code == 200
    assert c_stu.get("/offline").status_code == 200


def test_sw_routing_rules_static_cacheable_and_personalized_never_cacheable():
    c = client()
    sw_source = c.get("/sw.js").data.decode("utf-8")

    js_check = """
var sw = self.__MondaySW;
var origin = "https://monday.kg";

var staticCacheable = [
  "/static/css/monday.css?v=abc123",
  "/static/css/brand.css?v=def456",
  "/static/js/app.js?v=111222",
  "/static/js/pwa.js?v=333444",
  "/static/vendor/katex/katex.min.css?v=999",
  "/static/img/icon-192.png?v=aaa",
  "/static/img/apple-touch-icon.png?v=bbb",
  "/static/fonts/onest-cyrillic-400-normal.woff2",
  "/static/img/formulas/triangle.svg"
].map(function(p) {
  return { path: p, res: sw.classifyRequest({ method: "GET", url: origin + p, mode: "no-cors", origin: origin }) };
});

var neverCacheUrls = [
  { method: "GET", url: origin + "/", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/home", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/home", mode: "cors", accept: "*/*" },
  { method: "GET", url: origin + "/bank", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/daily", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/course/1", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/roadmap", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/fx", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/formulas", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/profile", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/settings", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/admin/", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/admin/course", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/manager", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/manager/leads", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/academic/schedule", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/teacher/", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/teacher/students", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/assistant/", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/api/site-status", mode: "cors", accept: "application/json" },
  { method: "GET", url: origin + "/api/version", mode: "cors", accept: "application/json" },
  { method: "POST", url: origin + "/api/activity/save", mode: "cors", accept: "application/json" },
  { method: "GET", url: origin + "/uploads/avatar-1.png", mode: "no-cors", accept: "image/*" },
  { method: "GET", url: origin + "/uploads/solutions/a1_2_deadbeef.png", mode: "no-cors", accept: "image/*" },
  { method: "GET", url: origin + "/uploads/packs/sat/fig1.png", mode: "no-cors", accept: "image/*" },
  { method: "GET", url: origin + "/static/data/countries.json?v=1", mode: "cors", accept: "application/json" },
  { method: "GET", url: origin + "/login", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/register", mode: "navigate", accept: "text/html" },
  { method: "POST", url: origin + "/logout", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/join/MND-ABCDEF123456", mode: "navigate", accept: "text/html" },
  { method: "GET", url: origin + "/sw.js", mode: "same-origin", accept: "*/*" },
  { method: "GET", url: origin + "/manifest.webmanifest", mode: "cors", accept: "*/*" },
  { method: "GET", url: "https://www.desmos.com/api/v1.12/calculator.js", mode: "no-cors", accept: "*/*" },
  { method: "GET", url: "https://www.youtube-nocookie.com/embed/abc", mode: "navigate", accept: "text/html" },
  { method: "GET", url: "https://accounts.google.com/o/oauth2/v2/auth", mode: "navigate", accept: "text/html" }
].map(function(opts) {
  opts.origin = origin;
  return { url: opts.method + " " + opts.url, res: sw.classifyRequest(opts) };
});

function fakeHeaders(ct) { return { get: function(k) { return k.toLowerCase() === "content-type" ? ct : null; } }; }
var cssReq = { method: "GET", url: origin + "/static/css/monday.css?v=1", mode: "no-cors", origin: origin };
var apiReq = { method: "GET", url: origin + "/api/site-status", mode: "cors", origin: origin };
var respChecks = {
  cssOk: sw.isCacheableResponse(cssReq, { ok: true, status: 200, type: "basic", headers: fakeHeaders("text/css") }),
  cssHtmlSpoof: sw.isCacheableResponse(cssReq, { ok: true, status: 200, type: "basic", headers: fakeHeaders("text/html; charset=utf-8") }),
  cssJsonSpoof: sw.isCacheableResponse(cssReq, { ok: true, status: 200, type: "basic", headers: fakeHeaders("application/json") }),
  css404: sw.isCacheableResponse(cssReq, { ok: false, status: 404, type: "basic", headers: fakeHeaders("text/css") }),
  cssOpaque: sw.isCacheableResponse(cssReq, { ok: true, status: 200, type: "opaque", headers: fakeHeaders("text/css") }),
  apiOk: sw.isCacheableResponse(apiReq, { ok: true, status: 200, type: "basic", headers: fakeHeaders("application/json") })
};

return {
  precacheName: sw.PRECACHE_NAME,
  runtimeCache: sw.RUNTIME_CACHE,
  staticCacheable: staticCacheable,
  neverCacheUrls: neverCacheUrls,
  respChecks: respChecks,
  activateDeletes: sw.cachesToDeleteOnActivate([
    sw.PRECACHE_NAME,
    sw.RUNTIME_CACHE,
    "monday-precache-old123",
    "monday-runtime-old123",
    "other-app-cache"
  ]),
  logoutDeletes: sw.runtimeCachesToDeleteOnLogout([
    sw.PRECACHE_NAME,
    sw.RUNTIME_CACHE,
    "monday-runtime-older"
  ])
};
"""
    out = _eval_sw_js(sw_source, js_check)

    assert out["precacheName"].startswith("monday-precache-v1-")
    assert out["runtimeCache"].startswith("monday-runtime-v1-")

    for item in out["staticCacheable"]:
        assert item["res"]["cacheable"] is True, f"Expected cacheable: {item}"

    for item in out["neverCacheUrls"]:
        assert item["res"]["cacheable"] is False, f"Personalized/excluded route must NEVER cache: {item}"

    rc = out["respChecks"]
    assert rc["cssOk"] is True
    assert rc["cssHtmlSpoof"] is False
    assert rc["cssJsonSpoof"] is False
    assert rc["css404"] is False
    assert rc["cssOpaque"] is False
    assert rc["apiOk"] is False

    # Activate cleanup deletes old Monday caches, preserves current caches & third-party keys
    assert sorted(out["activateDeletes"]) == ["monday-precache-old123", "monday-runtime-old123"]
    # Logout cleanup deletes all monday-runtime-* caches owned by the worker
    assert sorted(out["logoutDeletes"]) == sorted([out["runtimeCache"], "monday-runtime-older"])


def test_logout_sets_sw_clear_cookie_and_base_loads_pwa_js():
    c = client()
    login(c, "student@monday.kg", "student123")
    r_home = c.get("/home")
    assert r_home.status_code == 200
    assert "/static/js/pwa.js" in r_home.data.decode("utf-8")

    r_out = c.post("/logout", follow_redirects=False)
    assert r_out.status_code == 302
    cookies = r_out.headers.getlist("Set-Cookie")
    assert any(c_hdr.startswith("monday_sw_clear=1;") for c_hdr in cookies), cookies


def test_sw_live_browser_registration_offline_fallback_and_logout_clear():
    """End-to-end Playwright Chromium verification: SW registration, CSP, offline fallback, no HTML caching, logout clear."""
    import threading
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    from test_app import APP

    prev_server_name = APP.config.get("SERVER_NAME")
    APP.config["SERVER_NAME"] = None
    server = make_server("127.0.0.1", 0, APP)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"

    csp_violations = []
    console_errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            page = ctx.new_page()
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" and "ERR_INTERNET_DISCONNECTED" not in msg.text and "Failed to load resource" not in msg.text else None)
            page.add_init_script("""
                window.__cspViolations = [];
                document.addEventListener("securitypolicyviolation", (e) => {
                  window.__cspViolations.push({ directive: e.violatedDirective, blocked: e.blockedURI });
                });
            """)

            # 1. Login as student on /login -> /home
            page.goto(f"{base_url}/login", wait_until="networkidle")
            page.fill('input[name="email"]', "student@monday.kg")
            page.fill('input[name="password"]', "student123")
            page.click('button[type="submit"]')
            page.wait_for_url(f"{base_url}/home")

            # Wait for SW registration and activation + controller claim on subsequent reload
            sw_scope = page.evaluate("""async () => {
                const reg = await navigator.serviceWorker.ready;
                return reg.scope;
            }""")
            assert sw_scope == f"{base_url}/"

            page.reload(wait_until="networkidle")
            has_controller = page.evaluate("() => Boolean(navigator.serviceWorker.controller)")
            assert has_controller is True

            # Visit personalized & API pages; confirm NEVER stored in CacheStorage
            page.goto(f"{base_url}/bank", wait_until="networkidle")
            page.evaluate("() => fetch('/api/site-status')")
            cached_urls = page.evaluate("""async () => {
                const names = await caches.keys();
                const out = {};
                for (const name of names) {
                  const cache = await caches.open(name);
                  const reqs = await cache.keys();
                  out[name] = reqs.map(r => r.url);
                }
                return out;
            }""")
            from urllib.parse import urlparse
            all_paths = [urlparse(u).path for urls in cached_urls.values() for u in urls]
            for forbidden in ("/home", "/bank", "/bank/", "/login", "/api/site-status"):
                assert forbidden not in all_paths, f"Forbidden URL cached: {forbidden} in {all_paths}"
            assert all(p == "/offline" or p.startswith("/static/") for p in all_paths), all_paths
            assert "/offline" in all_paths

            # 2. Simulate offline navigation -> Russian fallback rendered
            ctx.set_offline(True)
            page.goto(f"{base_url}/home", wait_until="domcontentloaded")
            offline_text = page.text_content("body")
            assert "Нет подключения к интернету" in offline_text
            assert page.locator("[data-offline-retry]").count() == 1
            ctx.set_offline(False)

            # 3. Recover online & check Logout clears runtime caches
            page.goto(f"{base_url}/home", wait_until="networkidle")
            page.evaluate("""async () => {
                const c = await caches.open("monday-runtime-testseed");
                await c.put("/static/css/monday.css", new Response("body{}"));
            }""")
            page.click('[data-acct-menu] summary')
            page.click('[data-acct-menu] form[action$="/logout"] button[type="submit"]')
            page.wait_for_url(f"{base_url}/login")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(150)
            after_logout = page.evaluate("""async () => {
                const names = await caches.keys();
                const runtime = names.filter(n => n.startsWith("monday-runtime-"));
                const urls = [];
                for (const n of runtime) {
                  const c = await caches.open(n);
                  for (const r of await c.keys()) urls.push(r.url);
                }
                return { runtime: runtime, urls: urls };
            }""")
            # Old runtime cache and logged-in page runtime entries (e.g. bank.js, hero.js) are cleared on logout
            assert "monday-runtime-testseed" not in after_logout["runtime"]
            assert not any("bank.js" in u or "hero.js" in u or "bank-tiles.css" in u for u in after_logout["urls"]), after_logout

            csp_violations = page.evaluate("() => window.__cspViolations")
            assert csp_violations == [], f"CSP violations detected: {csp_violations}"
            browser.close()
    finally:
        server.shutdown()
        APP.config["SERVER_NAME"] = prev_server_name


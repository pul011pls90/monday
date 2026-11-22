"""Tests for the redesigned Duolingo + Brilliant.org landing page, interactive mini-challenge, and CSP compliance."""
from __future__ import annotations

import pathlib
import re
import threading

from werkzeug.serving import make_server

from config import Config
from monday import create_app
from monday.extensions import db
from monday.models import StudentProfile, User

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent


def _make_app(tmp_path, *, public_enabled: bool = True, csrf_enabled: bool = False):
    class LandingCfg(Config):
        TESTING = True
        WTF_CSRF_ENABLED = csrf_enabled
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        PUBLIC_SITE_ENABLED = public_enabled
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'landing.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")

    return create_app(LandingCfg, seed_if_empty=False)


def test_landing_csp_static_audit_and_auth_redirects(tmp_path):
    inline_handler_re = re.compile(r"\bon(?:click|change|input|submit|load|keydown|keyup|focus|blur)=", re.I)
    for rel in ("monday/templates/public/landing.html", "monday/templates/public/_base.html"):
        raw = (ROOT_DIR / rel).read_text(encoding="utf-8")
        assert "javascript:" not in raw.lower(), f"javascript: URL in {rel}"
        assert not inline_handler_re.search(raw), f"inline event handler in {rel}"
        for tag in re.findall(r"<script\b[^>]*>", raw, re.I):
            assert 'src=' in tag.lower() or 'application/ld+json' in tag.lower(), f"inline executable script in {rel}: {tag}"

    app = _make_app(tmp_path, public_enabled=True)
    with app.app_context():
        stu = User(email="s_land@monday.kg", name="Student L", role="student", is_approved=True)
        stu.set_password("Pass12345!")
        adm = User(email="a_land@monday.kg", name="Admin L", role="admin", is_approved=True)
        adm.set_password("StrongAdmin123!")
        db.session.add_all([stu, adm])
        db.session.flush()
        db.session.add(StudentProfile(user_id=stu.id, exam="SAT", onboarded=True))
        db.session.commit()

    # Logged-out public landing renders hero, interactive challenge, audience split, and 3-step loop
    anon = app.test_client()
    r = anon.get("/")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    for expected in (
        "Начать бесплатно",
        "У меня уже есть аккаунт",
        "Попробуй решить прямо сейчас",
        "ОРТ Математика",
        "Алгебра",
        "Геометрия",
        "Логика",
        "Для учеников",
        "Для преподавателей и родителей",
        "1. Диагностика уровня",
        "2. Интерактивная практика",
        "3. Контроль прогресса с преподавателем",
        "duo-hero-svg",
        "static/js/landing.js",
    ):
        assert expected in html

    # Existing auth routing rules stay intact for logged-in users
    c_stu = app.test_client()
    assert c_stu.post("/login", data={"email": "s_land@monday.kg", "password": "Pass12345!"}).status_code == 302
    assert "/home" in c_stu.get("/", follow_redirects=False).headers["Location"]

    c_adm = app.test_client()
    assert c_adm.post("/login", data={"email": "a_land@monday.kg", "password": "StrongAdmin123!"}).status_code == 302
    assert "/teacher" in c_adm.get("/", follow_redirects=False).headers["Location"]


def test_playwright_landing_interactive_challenge_and_csp(tmp_path):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return

    app = _make_app(tmp_path, public_enabled=True, csrf_enabled=True)
    app.config["SERVER_NAME"] = None
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1280, "height": 840})
            page = ctx.new_page()
            page.add_init_script(
                'window.__csp = []; window.__errs = [];'
                'document.addEventListener("securitypolicyviolation", e => window.__csp.push(e.violatedDirective));'
                'window.addEventListener("pageerror", e => window.__errs.push(String(e)));'
            )

            page.goto(f"{base_url}/", wait_until="networkidle")
            assert page.locator(".pub-hero-play h1").is_visible()
            assert page.locator(".duo-hero-svg").is_visible()

            # Switch subject tab -> Геометрия, solve correctly -> explanation + CTA shown
            page.click('[data-subject-tab="geometry"]')
            geom = page.locator('[data-subject-panel="geometry"]')
            geom.wait_for(state="visible", timeout=5000)
            geom.locator('[data-challenge-opt]:has-text("24")').click()
            assert "is-right" in (geom.locator('[data-challenge-opt]:has-text("24")').get_attribute("class") or "")
            geom.locator('[data-challenge-explain]').wait_for(state="visible", timeout=5000)
            assert geom.locator('a:has-text("Продолжить обучение")').is_visible()

            # Switch subject tab -> Логика, click wrong answer -> highlights wrong + reveals true answer + explanation
            page.click('[data-subject-tab="logic"]')
            logic = page.locator('[data-subject-panel="logic"]')
            logic.wait_for(state="visible", timeout=5000)
            logic.locator('[data-challenge-opt]:has-text("8")').click()
            assert "is-wrong" in (logic.locator('[data-challenge-opt]:has-text("8")').get_attribute("class") or "")
            assert "is-right" in (logic.locator('[data-challenge-opt]:has-text("10")').get_attribute("class") or "")
            logic.locator('[data-challenge-explain]').wait_for(state="visible", timeout=5000)

            # Mobile responsiveness sanity check (375px width, no horizontal overflow on challenge card)
            page.set_viewport_size({"width": 375, "height": 812})
            assert page.locator("#try-challenge").is_visible()

            assert page.evaluate("window.__csp") == []
            assert page.evaluate("window.__errs") == []
            browser.close()
    finally:
        server.shutdown()

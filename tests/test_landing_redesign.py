"""Tests for the redesigned Brilliant.org + Duolingo landing page, interactive sandbox, black footer, and CSP compliance."""
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
    for rel in (
        "monday/templates/public/landing.html",
        "monday/templates/public/_base.html",
        "monday/templates/public/question_bank.html",
        "monday/templates/public/offline_courses.html",
        "monday/templates/public/online_courses.html",
        "monday/templates/public/pricing.html",
        "monday/templates/public/faq.html",
        "monday/templates/public/contact.html",
        "monday/templates/public/about.html",
        "monday/templates/info/_legal_header.html",
        "monday/templates/info/terms.html",
        "monday/templates/info/privacy.html",
        "monday/templates/info/refund.html",
    ):
        raw = (ROOT_DIR / rel).read_text(encoding="utf-8")
        assert "javascript:" not in raw.lower(), f"javascript: URL in {rel}"
        assert not inline_handler_re.search(raw), f"inline event handler in {rel}"
        for tag in re.findall(r"<script\b[^>]*>", raw, re.I):
            assert "src=" in tag.lower() or "application/ld+json" in tag.lower(), f"inline executable script in {rel}: {tag}"

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

    # Logged-out public landing renders floating pill navbar, hero + fanned arc, sandbox, sky band, wave CTA, and black footer
    anon = app.test_client()
    for pub_url in (
        "/",
        "/question-bank",
        "/offline-courses",
        "/online",
        "/pricing",
        "/faq",
        "/contact",
        "/about",
        "/terms",
        "/privacy",
        "/refund",
        "/login",
        "/register",
    ):
        resp = anon.get(pub_url)
        assert resp.status_code == 200, f"{pub_url} returned {resp.status_code}"
        if pub_url not in ("/login", "/register"):
            assert "mp-footer" in resp.data.decode("utf-8"), f"Missing unified black footer on {pub_url}"

    r = anon.get("/")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    for expected in (
        "Персональный тренажёр по",
        "математике и экзаменам",
        "Я ученик",
        "Я преподаватель или родитель",
        "У меня уже есть аккаунт",
        "Закрасьте 1/2 фигуры",
        "(x + 2)(x + 1) = x² + [ ] + 2",
        "f(x) = x² − 4x + 5",
        "6–8–10 → S = ?",
        "sin(x) = cos(x)",
        "ОРТ / SAT прогноз баллов",
        "Интерактивный тренажёр, а не просто ответы",
        "ОРТ Математика",
        "Алгебра",
        "Геометрия",
        "Логика",
        "Учись в любое время, с любого устройства",
        "Для учеников",
        "Для преподавателей и родителей",
        "1. Диагностика уровня",
        "2. Интерактивная практика",
        "3. Контроль прогресса с преподавателем",
        "Начни подготовку с Monday сегодня",
        "Начать бесплатно",
        "https://instagram.com/monday_edc",
        "mailto:temirlanmanasev@gmail.com",
        "© 2026 Monday Academy",
        "static/js/landing.js",
    ):
        assert expected in html, f"Missing expected copy on /: {expected}"

    # Unfinished 'Графики' (tesla) mode must never be advertised as live
    assert "двигай точки, меняй уравнения" not in html

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
            assert page.locator(".mp-hero h1").is_visible()
            assert page.locator(".mp-fan").is_visible()

            # Verify White (#FFFFFF) canvas, Soft Light Blue (#EEF4FF -> rgb(238, 244, 255)) hero pill, and strictly black (#000000) footer
            body_bg = page.locator("body.pub-body").evaluate("el => getComputedStyle(el).backgroundColor")
            assert body_bg == "rgb(255, 255, 255)"
            pill_bg = page.locator(".mp-hero__pill").evaluate("el => getComputedStyle(el).backgroundColor")
            assert pill_bg == "rgb(238, 244, 255)"
            footer_bg = page.locator(".mp-footer").evaluate("el => getComputedStyle(el).backgroundColor")
            assert footer_bg == "rgb(0, 0, 0)"

            # Verify zero horizontal overflow and centered hero H1 at 1440px, 1024px, and 390px viewports
            for vw, vh in ((1440, 900), (1024, 800), (390, 844)):
                page.set_viewport_size({"width": vw, "height": vh})
                metrics = page.evaluate(
                    "() => {"
                    "  const r = document.querySelector('.mp-hero h1').getBoundingClientRect();"
                    "  return {"
                    "    scrollW: document.documentElement.scrollWidth,"
                    "    innerW: window.innerWidth,"
                    "    h1Left: r.left,"
                    "    h1Right: r.right,"
                    "    h1Center: r.left + r.width / 2"
                    "  };"
                    "}"
                )
                assert metrics["scrollW"] <= metrics["innerW"] + 1, f"Horizontal overflow at {vw}px: {metrics}"
                assert metrics["h1Left"] >= 0 and metrics["h1Right"] <= metrics["innerW"] + 1, f"H1 clipped at {vw}px: {metrics}"
                assert abs(metrics["h1Center"] - metrics["innerW"] / 2) <= 24, f"H1 not centered at {vw}px: {metrics}"

            page.set_viewport_size({"width": 1280, "height": 840})

            # Mode 1 (Математика): solve tile-slot algebra builder (2x, 4x, 8) -> explanation shown
            builder = page.locator("[data-tile-builder]")
            assert builder.is_visible()
            builder.locator('[data-tile="2x"]').click()
            builder.locator('[data-tile="4x"]').click()
            builder.locator('[data-tile="8"]').click()
            builder.locator("[data-tiles-explain]").wait_for(state="visible", timeout=5000)
            assert "is-right" in (builder.locator("[data-slot]").nth(0).get_attribute("class") or "")
            assert "is-right" in (builder.locator("[data-slot]").nth(2).get_attribute("class") or "")

            # Reset builder -> slots cleared back to '?'
            builder.locator("[data-tiles-reset]").click()
            assert builder.locator("[data-tiles-explain]").is_hidden()

            # Switch to Mode 2 (Экзамены) -> switch subject tab -> Геометрия -> solve correctly
            page.click('[data-mode-btn="exam"]')
            page.click('[data-subject-tab="geometry"]')
            geom = page.locator('[data-subject-panel="geometry"]')
            geom.wait_for(state="visible", timeout=5000)
            geom.locator('[data-challenge-opt]:has-text("24")').click()
            assert "is-right" in (geom.locator('[data-challenge-opt]:has-text("24")').get_attribute("class") or "")
            geom.locator("[data-challenge-explain]").wait_for(state="visible", timeout=5000)
            assert geom.locator('a:has-text("Продолжить обучение")').is_visible()

            # Switch subject tab -> Логика, click wrong answer -> highlights wrong + reveals true answer + explanation
            page.click('[data-subject-tab="logic"]')
            logic = page.locator('[data-subject-panel="logic"]')
            logic.wait_for(state="visible", timeout=5000)
            logic.locator('[data-challenge-opt]:has-text("8")').click()
            assert "is-wrong" in (logic.locator('[data-challenge-opt]:has-text("8")').get_attribute("class") or "")
            assert "is-right" in (logic.locator('[data-challenge-opt]:has-text("10")').get_attribute("class") or "")
            logic.locator("[data-challenge-explain]").wait_for(state="visible", timeout=5000)

            # Mobile responsiveness sanity check (375px width + mobile nav toggle)
            page.set_viewport_size({"width": 375, "height": 812})
            assert page.locator("#try-challenge").is_visible()
            page.click("[data-nav-toggle]")
            assert page.locator("[data-nav-panel]").is_visible()

            assert page.evaluate("window.__csp") == []
            assert page.evaluate("window.__errs") == []
            browser.close()
    finally:
        server.shutdown()


def test_render_welcome_first_and_open_access_without_subscription(tmp_path, monkeypatch):
    """Default Render links open on welcoming page -> /login, and students get full access without subscription."""
    from monday.models import ContentNode, Question
    from monday.public_site import is_public_site_enabled
    from monday.subscriptions import has_course_access, has_question_bank_access, subscription_status_summary

    monkeypatch.setenv("RENDER", "true")

    class RenderDefaultCfg(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SESSION_COOKIE_SECURE = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'render_open.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        PUBLIC_SAMPLE_MEDIA_FOLDER = str(tmp_path / "public_sample_media")

    app = create_app(RenderDefaultCfg, seed_if_empty=False)

    # All Render blueprints default to welcoming page first and open access without subscription
    for fname in ("render.yaml", "render.staging.yaml", "render.production.yaml"):
        txt = (ROOT_DIR / fname).read_text(encoding="utf-8")
        assert "PUBLIC_SITE_ENABLED" in txt and 'value: "1"' in txt, fname
        assert "SUBSCRIPTION_REQUIRED" in txt and 'value: "0"' in txt, fname

    # Even with RENDER=true & SESSION_COOKIE_SECURE=True (and legal preflight not completed), / serves welcome page
    app.testing = False
    try:
        with app.test_request_context("/"):
            assert is_public_site_enabled() is True
    finally:
        app.testing = True

    c = app.test_client()
    r_root = c.get("/", follow_redirects=False)
    assert r_root.status_code == 200
    root_html = r_root.data.decode("utf-8")
    assert "У меня уже есть аккаунт" in root_html
    assert 'href="/login"' in root_html

    # Clicking login opens /login page cleanly
    r_login = c.get("/login")
    assert r_login.status_code == 200

    # Newly registered student needs NO subscription or teacher link ("accept everyone")
    r_reg = c.post(
        "/register",
        data={
            "role": "student",
            "name": "Open Student",
            "email": "open_stu@monday.kg",
            "password": "OpenPass123!",
        },
        follow_redirects=False,
    )
    assert r_reg.status_code == 302

    with app.app_context():
        node = ContentNode(code="open_alg", name="Algebra", level="node", exams=["SAT"])
        db.session.add(node)
        db.session.flush()
        db.session.add(
            Question(
                skill=node,
                exams=["SAT"],
                difficulty=1,
                text="2+2?",
                options=["3", "4"],
                correct="1",
                status="published",
            )
        )
        stu = User.query.filter_by(email="open_stu@monday.kg").first()
        assert stu is not None
        stu.profile.exam = "SAT"
        stu.profile.onboarded = True
        db.session.commit()
        assert has_question_bank_access(stu) is True
        assert has_course_access(stu) is True
        summary = subscription_status_summary(stu)
        assert summary["tier"] == "open"
        assert summary["has_full_access"] is True

    for ok_url in ("/home", "/bank/", "/formulas", "/profile/export.csv", "/subscription"):
        assert c.get(ok_url).status_code == 200, ok_url
    assert "Открытый бесплатный доступ" in c.get("/subscription").data.decode("utf-8")
    # Teacher-only homework remains isolated when student has no teacher link
    assert c.get("/homework").status_code == 403

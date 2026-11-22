"""Tests for Admin stat-card click safety, CSP compliance, and role-aware structured user drawer."""
from __future__ import annotations

import pathlib
import re
import threading

from werkzeug.serving import make_server

from config import Config
from monday import create_app
from monday.extensions import db
from monday.models import (
    AcademicCourse,
    AuditLog,
    ContentNode,
    Question,
    StudentProfile,
    StudentRecord,
    SubscriptionPlan,
    TeacherAssignment,
    User,
)

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent


def _make_app(tmp_path, *, csrf_enabled: bool = False):
    class AdminDrawerCfg(Config):
        TESTING = True
        WTF_CSRF_ENABLED = csrf_enabled
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'admin_drawer.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")

    return create_app(AdminDrawerCfg, seed_if_empty=False)


def _login(client, email: str, password: str):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=False)


def _seed_admin_panel_users(app):
    with app.app_context():
        admin = User(email="adm@drawer.test", name="Root Admin", role="admin", is_approved=True)
        admin.set_password("StrongAdmin123!")
        other_admin = User(email="adm2@drawer.test", name="Second Admin", role="admin", is_approved=True)
        other_admin.set_password("StrongAdmin123!")
        manager = User(email="mgr@drawer.test", name="Sales Manager", role="sales_manager", is_approved=True)
        manager.set_password("StrongManager123!")
        teacher = User(email="teach@drawer.test", name="Aibek Math", role="teacher", is_approved=True)
        teacher.set_password("StrongTeacher123!")
        student = User(email="stu@drawer.test", name="Bota Student", role="student", is_approved=True)
        student.set_password("Pass12345!")

        db.session.add_all([admin, other_admin, manager, teacher, student])
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, exam="SAT", goal_score=750, onboarded=True))

        node = ContentNode(code="ad_n", name="Linear Equations", level="node", exams=["SAT"])
        course = AcademicCourse(code="sat_m", name="SAT Math", exam="SAT", is_active=True)
        db.session.add_all([node, course])
        db.session.flush()
        db.session.add(
            Question(
                skill=node,
                author=teacher,
                exams=["SAT"],
                difficulty=1,
                text="2x = 6",
                options=["2", "3"],
                correct="1",
                status="published",
            )
        )

        rec = StudentRecord(
            teacher_id=teacher.id,
            student_user_id=student.id,
            course_id=course.id,
            name="Bota Student",
            exam="SAT",
        )
        db.session.add(rec)
        db.session.flush()
        db.session.add(
            TeacherAssignment(
                student_record_id=rec.id,
                teacher_user_id=teacher.id,
                course_id=course.id,
                assigned_by_id=manager.id,
            )
        )
        db.session.add(
            SubscriptionPlan(
                code="adm_qbank",
                name="Месяц Банк",
                price_amount=800,
                currency="USD",
                duration_days=30,
                is_active=True,
            )
        )
        db.session.commit()
        return {
            "admin_id": admin.id,
            "other_admin_id": other_admin.id,
            "manager_id": manager.id,
            "teacher_id": teacher.id,
            "student_id": student.id,
        }


def test_admin_stat_blocks_never_carry_drawer_triggers_and_csp_clean(tmp_path):
    inline_handler_re = re.compile(r"\bon(?:click|change|input|submit|keydown|keyup|focus|blur)=", re.I)
    for rel in ("monday/templates/admin/index.html", "monday/templates/admin/_panel_body.html"):
        raw = (ROOT_DIR / rel).read_text(encoding="utf-8")
        assert "javascript:" not in raw.lower(), f"javascript: URL found in {rel}"
        assert not inline_handler_re.search(raw), f"inline event handler found in {rel}"
        for tag in re.findall(r"<script\b[^>]*>", raw, re.I):
            assert "src=" in tag.lower(), f"inline script block found in {rel}: {tag}"

    app = _make_app(tmp_path)
    ids = _seed_admin_panel_users(app)
    c = app.test_client()
    assert _login(c, "adm@drawer.test", "StrongAdmin123!").status_code == 302

    overview_html = c.get("/admin/").data.decode("utf-8")
    # Stat-card anchors navigate by tab URL only and never carry drawer trigger attributes
    stat_tags = re.findall(r'<a[^>]*class="card admin-stat[^"]*"[^>]*>', overview_html)
    assert len(stat_tags) == 4
    for tag in stat_tags:
        assert "data-drawer-open" not in tag
        assert "data-drawer-url" not in tag
        assert "data-user-id" not in tag
    assert 'data-drawer-requires-user="1"' in overview_html
    assert 'id="admin-person-drawer"' in overview_html
    m_drawer = re.search(r'<div[^>]*id="admin-person-drawer"[^>]*>', overview_html)
    assert m_drawer and "is-open" not in m_drawer.group(0) and "hidden" in m_drawer.group(0)

    students_html = c.get("/admin/?tab=students").data.decode("utf-8")
    assert f'data-user-id="{ids["student_id"]}"' in students_html
    assert 'data-drawer-open="admin-person-drawer"' in students_html
    assert "fragment=1" in students_html


def test_admin_user_drawer_role_aware_subcards_and_actions(tmp_path):
    app = _make_app(tmp_path)
    ids = _seed_admin_panel_users(app)
    c = app.test_client()
    assert _login(c, "adm@drawer.test", "StrongAdmin123!").status_code == 302

    # 1. Student drawer includes all 5 structured sub-cards + academic stats + Последние результаты
    stu_frag = c.get(f"/admin/?tab=students&user={ids['student_id']}&fragment=1")
    assert stu_frag.status_code == 200
    stu_html = stu_frag.data.decode("utf-8")
    assert "adm-drawer-stack" in stu_html
    assert "adm-subcard--head" in stu_html
    assert "Симулировать вид аккаунта" in stu_html
    assert 'data-copy-text="stu@drawer.test"' in stu_html
    assert "Учёба и статистика" in stu_html
    assert "освоено" in stu_html and "прогноз" in stu_html and "навыков" in stu_html
    assert "Последние результаты" in stu_html
    assert "Роль и безопасность" in stu_html
    assert "Сменить роль" in stu_html
    assert "Сбросить пароль" in stu_html
    assert "Подписка на банк вопросов" in stu_html
    assert "adm-grid-2" in stu_html
    assert "Выдать подписку вручную" in stu_html
    assert "adm-subcard--danger" in stu_html
    assert "Опасная зона" in stu_html
    assert "Заблокировать аккаунт" in stu_html

    # 2. Teacher drawer shows active students count & subject, NEVER student KPIs or subscription form
    teach_frag = c.get(f"/admin/?tab=teachers&user={ids['teacher_id']}&fragment=1")
    assert teach_frag.status_code == 200
    teach_html = teach_frag.data.decode("utf-8")
    assert "Преподавание" in teach_html
    assert "Активных учеников" in teach_html
    assert "SAT Math" in teach_html
    assert "Назначить методистом" in teach_html
    assert "освоено" not in teach_html
    assert "прогноз" not in teach_html
    assert "Последние результаты" not in teach_html
    assert "Подписка на банк вопросов" not in teach_html

    # 3. Manager & Admin drawers show account metadata card ONLY (no student KPIs/results)
    mgr_frag = c.get(f"/admin/?tab=managers&user={ids['manager_id']}&fragment=1")
    assert mgr_frag.status_code == 200
    mgr_html = mgr_frag.data.decode("utf-8")
    assert "Аккаунт и активность" in mgr_html
    assert "освоено" not in mgr_html
    assert "Последние результаты" not in mgr_html
    assert "Подписка на банк вопросов" not in mgr_html

    adm_frag = c.get(f"/admin/?tab=admins&user={ids['other_admin_id']}&fragment=1")
    assert adm_frag.status_code == 200
    adm_html = adm_frag.data.decode("utf-8")
    assert "Аккаунт и активность" in adm_html
    assert "освоено" not in adm_html
    assert "Последние результаты" not in adm_html

    # 4. Actions preserve audit logging cleanly
    r_grant = c.post(
        f"/admin/users/{ids['student_id']}/subscription/grant",
        data={"status": "active", "days": "15", "next": "/admin/?tab=students"},
    )
    assert r_grant.status_code == 302
    with app.app_context():
        assert AuditLog.query.filter_by(action="subscription_manual_grant", entity_id=ids["student_id"]).count() == 0
        assert AuditLog.query.filter_by(action="subscription_manual_grant", entity_type="bank_subscription").count() == 1


def test_playwright_admin_stat_click_and_user_drawer_csp_clean(tmp_path):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return

    app = _make_app(tmp_path, csrf_enabled=True)
    ids = _seed_admin_panel_users(app)
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

            page.goto(f"{base_url}/login", wait_until="networkidle")
            page.fill('input[name="email"]', "adm@drawer.test")
            page.fill('input[name="password"]', "StrongAdmin123!")
            page.click('button[type="submit"]')
            page.wait_for_url(f"{base_url}/teacher/**")
            page.goto(f"{base_url}/admin/", wait_until="networkidle")

            # Clicking top stat block switches to tab=students and NEVER opens #admin-person-drawer
            page.click('.admin-stats a[href*="tab=students"]')
            page.wait_for_url("**tab=students**", timeout=5000)
            drawer = page.locator("#admin-person-drawer")
            assert drawer.is_hidden()

            # Synthetic guard check: malformed trigger missing user-id/url must NOT open #admin-person-drawer
            page.evaluate("""() => {
              const btn = document.createElement('button');
              btn.setAttribute('data-drawer-open', 'admin-person-drawer');
              btn.id = '__bad_trigger';
              document.body.appendChild(btn);
              btn.click();
              btn.remove();
            }""")
            assert drawer.is_hidden()

            # Valid student row opens drawer with structured sub-cards & closes cleanly on Escape
            page.click(f'a.people__who[data-user-id="{ids["student_id"]}"]')
            page.locator("#admin-person-drawer.drawer-layer.is-open").wait_for(state="visible", timeout=5000)
            page.locator('#admin-person-drawer .adm-subcard:has-text("Подписка на банк вопросов")').wait_for(state="visible", timeout=5000)
            page.locator('#admin-person-drawer .adm-subcard--danger:has-text("Заблокировать аккаунт")').wait_for(state="visible", timeout=5000)
            page.keyboard.press("Escape")
            page.locator("#admin-person-drawer").wait_for(state="hidden", timeout=5000)

            assert page.evaluate("window.__csp") == []
            assert page.evaluate("window.__errs") == []
            browser.close()
    finally:
        server.shutdown()


def test_admin_public_site_demo_preview_buttons_and_rbac(tmp_path):
    app = _make_app(tmp_path)
    app.config["PUBLIC_SITE_ENABLED"] = False
    ids = _seed_admin_panel_users(app)

    # Anonymous & non-admin cannot use /admin/preview or bypass PUBLIC_SITE_ENABLED=False
    anon = app.test_client()
    assert anon.get("/admin/preview", follow_redirects=False).status_code == 302
    assert anon.get("/question-bank").status_code == 404

    stu = app.test_client()
    assert _login(stu, "stu@drawer.test", "Pass12345!").status_code == 302
    assert stu.get("/admin/preview").status_code == 403
    assert stu.get("/question-bank").status_code == 404

    # Admin dashboard contains Demo Site button and design showcase bar
    adm = app.test_client()
    assert _login(adm, "adm@drawer.test", "StrongAdmin123!").status_code == 302
    adm_html = adm.get("/admin/").data.decode("utf-8")
    assert "Демо-сайт (О Monday)" in adm_html
    assert "Демо-просмотр сайта о Monday и новых страниц" in adm_html
    assert "Подписка и Stripe (вид ученика)" in adm_html

    # Clicking preview enables Admin-only public site view even when PUBLIC_SITE_ENABLED=False
    r_landing = adm.get("/admin/preview?page=landing", follow_redirects=True)
    assert r_landing.status_code == 200
    landing_html = r_landing.data.decode("utf-8")
    assert "Демо-предпросмотр" in landing_html
    assert "Monday Academy" in landing_html
    assert "О школе" in landing_html

    for page_key in ("about", "question-bank", "pricing", "offline", "online", "faq", "contact", "terms", "privacy", "refund"):
        r_pg = adm.get(f"/admin/preview?page={page_key}", follow_redirects=True)
        assert r_pg.status_code == 200, f"Preview failed for page={page_key}"
        assert "Демо-предпросмотр" in r_pg.data.decode("utf-8")

    # Exiting preview returns to normal admin routing (/ goes to /teacher/)
    r_exit = adm.post("/admin/preview/exit", follow_redirects=False)
    assert r_exit.status_code == 302 and "/admin" in r_exit.headers["Location"]
    assert "/teacher" in adm.get("/", follow_redirects=False).headers["Location"]

    # Direct shortcut to Student Subscription & Stripe UI opens /subscription via simulation
    r_sub = adm.post("/admin/preview/subscription", follow_redirects=True)
    assert r_sub.status_code == 200
    assert "Подписка на банк вопросов" in r_sub.data.decode("utf-8")

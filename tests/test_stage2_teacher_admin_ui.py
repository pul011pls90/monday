"""Stage 2 QA tests: Teacher & Admin frosted shell, slider, drawers, role badges, and RBAC."""
from __future__ import annotations

import os
import re
import tempfile

from flask_migrate import upgrade

from config import Config
from monday.extensions import db
from monday.models import StudentProfile, User


def _make_app(*, csrf_enabled: bool = True):
    tmp = tempfile.mkdtemp()

    class Stage2Config(Config):
        TESTING = True
        WTF_CSRF_ENABLED = csrf_enabled
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "stage2.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    from monday import create_app

    app = create_app(Stage2Config, seed_if_empty=False)
    with app.app_context():
        upgrade()
    return app


def _seed_user(app, email: str, name: str, role: str, *, pw: str = "StrongStaff12!", **extra) -> int:
    with app.app_context():
        u = User(email=email, name=name, role=role, is_approved=True, is_blocked=False, **extra)
        u.set_password(pw)
        db.session.add(u)
        db.session.flush()
        if role == "student":
            db.session.add(StudentProfile(user_id=u.id, exam="ORT", onboarded=True))
        db.session.commit()
        return u.id


def _login(client, email: str, pw: str = "StrongStaff12!"):
    # Read login page CSRF token when WTF_CSRF_ENABLED=True
    r0 = client.get("/login")
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r0.data)
    payload = {"email": email, "password": pw}
    if m:
        payload["csrf_token"] = m.group(1).decode("utf-8")
    r = client.post("/login", data=payload)
    assert r.status_code == 302
    return client


def test_teacher_pages_render_frosted_shell_slider_and_csrf():
    app = _make_app(csrf_enabled=True)
    _seed_user(app, "tch@monday.kg", "Айбек Учитель", "teacher")

    c = app.test_client()
    _login(c, "tch@monday.kg")

    teacher_urls = [
        "/teacher/",
        "/teacher/students",
        "/teacher/works",
        "/teacher/review",
        "/teacher/bank",
        "/teacher/questions",
        "/teacher/tree",
        "/teacher/reports",
        "/teacher/account",
        "/assistant/",
    ]
    for url in teacher_urls:
        res = c.get(url)
        assert res.status_code == 200, f"{url} returned {res.status_code}"
        html = res.get_data(as_text=True)
        assert '<div class="app-shell-panel">' in html, f"{url} missing .app-shell-panel"
        assert '<body class="mgr"' not in html, f"{url} must not carry body.mgr"
        if '<form method="post"' in html.lower():
            assert 'name="csrf_token"' in html, f"{url} missing CSRF token on POST form"

    acct_html = c.get("/teacher/account").get_data(as_text=True)
    assert 'id="shell-alpha-slider"' in acct_html
    assert 'min="60"' in acct_html
    assert 'max="100"' in acct_html
    assert "monday_shell_alpha" in acct_html


def test_admin_pages_render_shell_external_drawers_and_role_badges():
    app = _make_app(csrf_enabled=True)
    _seed_user(app, "adm@monday.kg", "Главный Админ", "admin")
    _seed_user(app, "tch@monday.kg", "Учитель", "teacher")
    _seed_user(app, "ast@monday.kg", "Ассистент", "assistant")
    _seed_user(app, "mgr@monday.kg", "Менеджер На Смене", "sales_manager", is_on_shift=True)
    _seed_user(app, "sup@monday.kg", "Супервайзер", "supervisor", is_on_shift=False)
    _seed_user(app, "stu@monday.kg", "Ученик", "student")

    c = app.test_client()
    _login(c, "adm@monday.kg")

    admin_urls = [
        "/admin/",
        "/admin/analytics/",
        "/admin/course",
        "/admin/roadmap",
        "/admin/maintenance",
        "/teacher/students",
        "/review/questions",
    ]
    for url in admin_urls:
        res = c.get(url)
        assert res.status_code == 200, f"{url} returned {res.status_code}"
        html = res.get_data(as_text=True)
        assert '<div class="app-shell-panel">' in html, f"{url} missing .app-shell-panel"
        assert '<body class="mgr"' not in html, f"{url} must not carry body.mgr"

    # Drawers with position:fixed must live outside .app-shell-panel so backdrop-filter doesn't trap them
    for url, marker in [("/admin/", "data-person-panel"), ("/admin/analytics/", "data-an-drawer")]:
        html = c.get(url).get_data(as_text=True)
        shell_pos = html.index('<div class="app-shell-panel">')
        main_end = html.index("</main>")
        drawer_pos = html.index(marker)
        assert drawer_pos > main_end > shell_pos, f"{marker} on {url} must sit in body_end outside .app-shell-panel"

    # Role tags on /teacher/students (admin mode)
    users_html = c.get("/teacher/students").get_data(as_text=True)
    assert "tag--accent" in users_html
    assert "tag--ok" in users_html
    assert "tag--warn" in users_html
    assert "tag--soft" in users_html

    # Shift & role badges for sales_manager & supervisor in /admin/?tab=managers & supervisors
    mgr_html = c.get("/admin/?tab=managers").get_data(as_text=True)
    assert "менеджер продаж" in mgr_html
    assert "на смене" in mgr_html
    sup_html = c.get("/admin/?tab=supervisors").get_data(as_text=True)
    assert "супервайзер" in sup_html
    assert "не на смене" in sup_html


def test_teacher_admin_rbac_and_student_untouched():
    app = _make_app(csrf_enabled=True)
    _seed_user(app, "stu@monday.kg", "Ученик", "student")
    _seed_user(app, "mgr@monday.kg", "Менеджер", "sales_manager")
    _seed_user(app, "tch@monday.kg", "Учитель", "teacher")

    # Student: sees no .app-shell-panel on student pages, gets 403 on teacher & admin
    c_stu = app.test_client()
    _login(c_stu, "stu@monday.kg")
    for url in ["/home", "/skills", "/sessions", "/collections", "/profile"]:
        res = c_stu.get(url)
        assert res.status_code == 200, f"student {url} -> {res.status_code}"
        html = res.get_data(as_text=True)
        assert '<div class="app-shell-panel">' not in html, f"student {url} leaked .app-shell-panel"
        assert '<body class="mgr"' not in html
    for url in ["/teacher/", "/teacher/bank", "/admin/", "/admin/analytics/", "/admin/course", "/admin/roadmap", "/admin/maintenance"]:
        assert c_stu.get(url).status_code == 403

    # Sales manager: blocked 403 from teacher & admin
    c_mgr = app.test_client()
    _login(c_mgr, "mgr@monday.kg")
    for url in ["/teacher/", "/teacher/students", "/admin/", "/admin/analytics/", "/admin/maintenance"]:
        assert c_mgr.get(url).status_code == 403

    # Teacher: blocked 403 from admin routes
    c_tch = app.test_client()
    _login(c_tch, "tch@monday.kg")
    for url in ["/admin/", "/admin/analytics/", "/admin/course", "/admin/roadmap", "/admin/maintenance"]:
        assert c_tch.get(url).status_code == 403

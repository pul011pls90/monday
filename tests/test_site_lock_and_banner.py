"""Tests for deploy-safety banner dismissal fix and admin site-lock (only admin & manager can enter)."""
from __future__ import annotations

import os

from config import Config
from monday import create_app
from monday.extensions import db
from monday.models import AuditLog, MaintenanceState, StudentProfile, User


def _make_lock_app(tmp_path):
    class LockCfg(Config):
        TESTING = True
        SECRET_KEY = "site-lock-secret"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'lock.db'}"
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
        for email, name, role in (
            ("adm@lock.kg", "Admin Lock", "admin"),
            ("mgr@lock.kg", "Manager Lock", "sales_manager"),
            ("sup@lock.kg", "Supervisor Lock", "supervisor"),
            ("tch@lock.kg", "Teacher Lock", "teacher"),
            ("ast@lock.kg", "Assistant Lock", "assistant"),
            ("stu@lock.kg", "Student Lock", "student"),
        ):
            u = User(email=email, name=name, role=role, is_approved=True)
            u.set_password("StrongPass123!")
            if role == "student":
                u.profile = StudentProfile(exam="SAT", grade="11", onboarded=True)
            db.session.add(u)
        db.session.commit()
    return app


def _login(c, email):
    return c.post("/login", data={"email": email, "password": "StrongPass123!"}, follow_redirects=False)


def test_site_lock_toggle_blocks_non_admin_manager_and_keeps_same_notice(tmp_path):
    app = _make_lock_app(tmp_path)

    c_adm = app.test_client()
    assert _login(c_adm, "adm@lock.kg").status_code == 302
    assert "Закрыть доступ на сайт" in c_adm.get("/admin/").data.decode("utf-8")

    # Non-admin cannot close website
    c_mgr_bad = app.test_client()
    _login(c_mgr_bad, "mgr@lock.kg")
    assert c_mgr_bad.post("/admin/maintenance", data={"action": "lock"}).status_code == 403

    # Log in student, teacher, assistant, supervisor BEFORE locking
    c_stu = app.test_client()
    _login(c_stu, "stu@lock.kg")
    c_tch = app.test_client()
    _login(c_tch, "tch@lock.kg")
    c_ast = app.test_client()
    _login(c_ast, "ast@lock.kg")
    c_sup = app.test_client()
    _login(c_sup, "sup@lock.kg")

    # Admin clicks "Закрыть сайт" with custom message
    r_lock = c_adm.post(
        "/admin/maintenance",
        data={"action": "lock", "message": "Плановые техработы", "expected_minutes": "20", "next": "/admin/"},
        follow_redirects=False,
    )
    assert r_lock.status_code == 302
    assert "Открыть сайт для всех" in c_adm.get("/admin/").data.decode("utf-8")

    # /api/site-status returns locked + message
    st_json = c_adm.get("/api/site-status").get_json()
    assert st_json["state"] == "locked"
    assert "Плановые техработы" in st_json["message"]

    # Admin, sales_manager, and supervisor CAN still enter
    assert c_adm.get("/admin/").status_code == 200
    assert c_mgr_bad.get("/manager").status_code == 200
    assert c_sup.get("/manager").status_code == 200

    # Student, teacher, assistant, and anonymous users get 503 with the same notification
    for cli, path in (
        (c_stu, "/home"),
        (c_tch, "/teacher/"),
        (c_ast, "/assistant/"),
        (app.test_client(), "/"),
        (app.test_client(), "/register"),
    ):
        res = cli.get(path)
        assert res.status_code == 503
        html = res.data.decode("utf-8")
        assert "Плановые техработы" in html
        assert "Ваши ответы сохранены на этом устройстве" in html

    # Student cannot log in while site is locked (503), while manager CAN log in
    r_stu_login = _login(app.test_client(), "stu@lock.kg")
    assert r_stu_login.status_code == 503
    r_mgr_login = _login(app.test_client(), "mgr@lock.kg")
    assert r_mgr_login.status_code == 302

    # Autosave progress endpoint stays open so queued answers aren't lost
    r_save = c_stu.post(
        "/api/activity/save",
        json={"type": "bank", "activity_id": "sat", "answered": 1, "total": 5, "state": {"q": 1}},
    )
    assert r_save.status_code == 200

    # Admin clicks "Открыть сайт для всех" -> normal users regain access
    r_unlock = c_adm.post("/admin/maintenance", data={"action": "unlock", "next": "/admin/"}, follow_redirects=False)
    assert r_unlock.status_code == 302
    assert c_stu.get("/home").status_code == 200
    assert c_tch.get("/teacher/").status_code == 200

    with app.app_context():
        assert AuditLog.query.filter_by(action="site_maintenance_update").count() == 2


def test_deploy_safety_js_allows_hiding_active_banner():
    js_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "monday", "static", "js", "deploy-safety.js")
    with open(js_path, encoding="utf-8") as f:
        src = f.read()
    assert 'state !== "active"' not in src
    assert "DISMISS_BANNER_KEY" in src
    assert "Скрыть" in src

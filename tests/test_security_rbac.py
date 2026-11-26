"""Stage 1 RBAC, staff 12-char password policy, /change-password hardening, and TESTING-only exemption tests."""
from __future__ import annotations

import logging
import pytest
from flask import Flask

from config import Config
from monday import create_app
from monday.access import (
    STAFF_MIN_PASSWORD_LEN,
    STUDENT_MIN_PASSWORD_LEN,
    admin_required,
    manager_required,
    min_password_length,
    role_required,
    student_required,
    teacher_required,
)
from monday.extensions import db
from monday.models import User
from monday.rate_limit import _exempt_testing_apps, reset_rate_limits


class _SecTestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


@pytest.fixture
def sec_app():
    app = create_app(_SecTestConfig)
    with app.app_context():
        db.create_all()
        for role, approved in [
            ("student", True),
            ("teacher", True),
            ("manager", True),
            ("admin", True),
        ]:
            u = User(name=f"Test {role}", email=f"{role}@sec.test", role=role, is_approved=approved)
            u.set_password("OldPass123456!")
            db.session.add(u)
        db.session.commit()
    return app


def test_exempt_testing_apps_strict_boolean_guard():
    """_exempt_testing_apps must ONLY return True when TESTING is boolean True."""
    prod_app = Flask("prod")
    assert _exempt_testing_apps(prod_app) is False

    dev_app = Flask("dev")
    dev_app.config.from_object(Config)
    assert _exempt_testing_apps(dev_app) is False

    for non_bool_true in (False, None, 0, 1, "1", "true", "True"):
        a = Flask("probe")
        a.config["TESTING"] = non_bool_true
        assert _exempt_testing_apps(a) is False

    ok = Flask("ok")
    ok.config["TESTING"] = True
    assert _exempt_testing_apps(ok) is True


def test_staff_12_char_password_policy(sec_app, caplog):
    """Staff (admin, manager, teacher) require 12+ chars; students require 8+ chars; rotation logs audit."""
    assert min_password_length("admin") == STAFF_MIN_PASSWORD_LEN == 12
    assert min_password_length("manager") == STAFF_MIN_PASSWORD_LEN == 12
    assert min_password_length("teacher") == STAFF_MIN_PASSWORD_LEN == 12
    assert min_password_length("student") == STUDENT_MIN_PASSWORD_LEN == 8

    with sec_app.test_client() as client:
        for staff_role in ("teacher", "manager", "admin"):
            with sec_app.app_context():
                u = User.query.filter_by(email=f"{staff_role}@sec.test").first()
            with client.session_transaction() as sess:
                sess["_user_id"] = str(u.id)
                sess["_fresh"] = True

            # 11 chars rejected for staff
            r_short = client.post("/change-password", data={"current": "OldPass123456!", "new": "Short11Char"})
            assert r_short.status_code == 400

            # 12+ chars accepted and logged
            with caplog.at_level(logging.INFO):
                r_ok = client.post("/change-password", data={"current": "OldPass123456!", "new": "ValidStaff12!"}, headers={"Accept": "application/json"})
                assert r_ok.status_code == 200
            assert any("AUDIT password_changed" in rec.message and f"role={staff_role}" in rec.message for rec in caplog.records)


def test_change_password_csrf_and_rate_limit(sec_app):
    """Verify CSRF enforcement and rate limiting when TESTING=False."""
    reset_rate_limits()
    sec_app.config["WTF_CSRF_ENABLED"] = True
    sec_app.config["TESTING"] = False
    try:
        with sec_app.app_context():
            u = User.query.filter_by(email="student@sec.test").first()
        with sec_app.test_client() as client:
            with client.session_transaction() as sess:
                sess["_user_id"] = str(u.id)
                sess["_fresh"] = True
            # Missing CSRF token -> 400
            r_no_csrf = client.post("/change-password", data={"current": "OldPass123456!", "new": "NewStudent12!"})
            assert r_no_csrf.status_code == 400

            # Disable CSRF to exercise rate limiter (10 allowed, 11th -> 429)
            sec_app.config["WTF_CSRF_ENABLED"] = False
            for _ in range(10):
                r = client.post("/change-password", data={"current": "wrong", "new": "NewStudent12!"})
                assert r.status_code == 400
            r_limited = client.post("/change-password", data={"current": "wrong", "new": "NewStudent12!"})
            assert r_limited.status_code == 429
    finally:
        sec_app.config["TESTING"] = True
        sec_app.config["WTF_CSRF_ENABLED"] = False
        reset_rate_limits()


def test_rbac_role_matrix(sec_app):
    """Verify student, teacher, manager, admin, and role_required decorators."""
    @sec_app.route("/_test_rbac/manager")
    @manager_required
    def _mgr():
        return "ok"

    @sec_app.route("/_test_rbac/admin")
    @admin_required
    def _adm():
        return "ok"

    @sec_app.route("/_test_rbac/teacher")
    @teacher_required
    def _tch():
        return "ok"

    @sec_app.route("/_test_rbac/video")
    @role_required("student", "admin")
    def _vid():
        return "ok"

    with sec_app.test_client() as client:
        for role, expected in [
            ("student", {"/_test_rbac/manager": 403, "/_test_rbac/admin": 403, "/_test_rbac/teacher": 403, "/_test_rbac/video": 200}),
            ("teacher", {"/_test_rbac/manager": 403, "/_test_rbac/admin": 403, "/_test_rbac/teacher": 200, "/_test_rbac/video": 403}),
            ("manager", {"/_test_rbac/manager": 200, "/_test_rbac/admin": 403, "/_test_rbac/teacher": 403, "/_test_rbac/video": 403}),
            ("admin", {"/_test_rbac/manager": 200, "/_test_rbac/admin": 200, "/_test_rbac/teacher": 200, "/_test_rbac/video": 200}),
        ]:
            with sec_app.app_context():
                u = User.query.filter_by(email=f"{role}@sec.test").first()
            with client.session_transaction() as sess:
                sess["_user_id"] = str(u.id)
                sess["_fresh"] = True
            for path, code in expected.items():
                assert client.get(path).status_code == code, f"{role} -> {path}"

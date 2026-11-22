"""Tests for Admin-only support request deletion (RBAC, CSRF, cascades, audit logging, CSP-safe confirmation)."""
from __future__ import annotations

import os
import re
import threading

from werkzeug.serving import make_server

from config import Config
from monday import storage
from monday.extensions import db
from monday.models import AuditLog, Report, SupportAttachment, User


def _make_app(tmp_path, *, csrf_enabled: bool = True):
    class SupportDelConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = csrf_enabled
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'support_del.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")

    from monday import create_app

    return create_app(SupportDelConfig, seed_if_empty=False)


def _seed_user(app, email: str, name: str, role: str, password: str = "Pass12345!") -> int:
    with app.app_context():
        u = User(email=email, name=name, role=role, is_approved=True)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return u.id


def _login(client, email: str, csrf_enabled: bool = False, password: str = "Pass12345!"):
    data = {"email": email, "password": password}
    if csrf_enabled:
        html = client.get("/login").data.decode("utf-8")
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
        assert m, "Missing csrf_token on /login"
        data["csrf_token"] = m.group(1)
    resp = client.post("/login", data=data)
    assert resp.status_code == 302


def _create_report_with_attachment(app, author_id: int, *, status: str = "open", sender_role: str = "student"):
    with app.app_context():
        rep = Report(
            author_id=author_id,
            sender_role=sender_role,
            kind="other",
            message="Помогите с входом в личный кабинет, прилагаю скриншот ошибки.",
            status=status,
        )
        db.session.add(rep)
        db.session.flush()
        att = SupportAttachment(
            message_id=rep.id,
            storage_key=f"testdel_{rep.id}",
            mime="image/webp",
            width=400,
            height=300,
            bytes_original=12345,
            bytes_stored=2345,
            sha256="a" * 64,
        )
        db.session.add(att)
        storage.save(att.full_object_name(), b"full-webp-bytes", "image/webp")
        storage.save(att.thumb_object_name(), b"thumb-webp-bytes", "image/webp")
        db.session.commit()
        return rep.id, att.id, att.full_object_name(), att.thumb_object_name()


def test_admin_can_delete_support_request_with_attachments_and_audit_log(tmp_path):
    app = _make_app(tmp_path, csrf_enabled=True)
    adm_id = _seed_user(app, "adm@supdel.kg", "Главный Админ", "admin")
    stu_id = _seed_user(app, "stu@supdel.kg", "Айсулу Ученик", "student")
    tch_id = _seed_user(app, "tch@supdel.kg", "Учитель Банка", "teacher")

    rep_id, att_id, full_obj, thumb_obj = _create_report_with_attachment(
        app, stu_id, status="fixed", sender_role="student"
    )
    upload_dir = tmp_path / "uploads"
    assert (upload_dir / full_obj).is_file()
    assert (upload_dir / thumb_obj).is_file()

    # Teacher inbox does not expose admin request delete action
    c_tch = app.test_client()
    _login(c_tch, "tch@supdel.kg", csrf_enabled=True)
    tch_html = c_tch.get("/teacher/reports?tab=done").data.decode("utf-8")
    assert f"/admin/support/{rep_id}/delete" not in tch_html

    # Admin sees delete form + CSRF + data-confirm, and deletion redirects cleanly preserving tab/role
    c_adm = app.test_client()
    _login(c_adm, "adm@supdel.kg", csrf_enabled=True)
    inbox_html = c_adm.get("/teacher/reports?tab=done&role=student").data.decode("utf-8")
    action_url = f"/admin/support/{rep_id}/delete"
    assert action_url in inbox_html
    assert "data-confirm=" in inbox_html
    assert ">Удалить<" in inbox_html or "<span>Удалить</span>" in inbox_html

    m = re.search(
        rf'<form[^>]*action="{re.escape(action_url)}"[^>]*>([\s\S]*?)</form>',
        inbox_html,
    )
    assert m, "Delete form not found on admin inbox"
    csrf_m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', m.group(1))
    assert csrf_m, "Missing csrf_token in delete form"

    resp = c_adm.post(
        action_url,
        data={"csrf_token": csrf_m.group(1), "tab": "done", "role": "student"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "tab=done" in resp.headers["Location"]
    assert "role=student" in resp.headers["Location"]

    with app.app_context():
        assert db.session.get(Report, rep_id) is None
        assert db.session.get(SupportAttachment, att_id) is None
        assert not (upload_dir / full_obj).exists()
        assert not (upload_dir / thumb_obj).exists()

        audit = (
            AuditLog.query.filter_by(action="support_request_delete", entity_id=rep_id)
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.actor_id == adm_id
        assert audit.entity_type == "support_request"
        assert audit.old_value["request_id"] == rep_id
        assert audit.old_value["author_id"] == stu_id
        assert audit.old_value["author_email"] == "stu@supdel.kg"
        assert audit.old_value["sender_role"] == "student"
        assert audit.old_value["attachment_count"] == 1
        assert "Помогите с входом" in audit.old_value["message_snippet"]


def test_admin_delete_support_request_json_and_404(tmp_path):
    app = _make_app(tmp_path, csrf_enabled=False)
    _seed_user(app, "adm2@supdel.kg", "Admin Two", "admin")
    stu_id = _seed_user(app, "stu2@supdel.kg", "Stu Two", "student")
    rep_id, _, _, _ = _create_report_with_attachment(app, stu_id)

    c_adm = app.test_client()
    _login(c_adm, "adm2@supdel.kg")

    assert c_adm.post("/admin/support/999999/delete").status_code == 404

    res = c_adm.delete(f"/admin/support/{rep_id}/delete")
    assert res.status_code == 200
    assert res.get_json() == {"ok": True, "deleted_id": rep_id}
    with app.app_context():
        assert db.session.get(Report, rep_id) is None


def test_non_admin_roles_blocked_from_deleting_support_requests(tmp_path):
    app = _make_app(tmp_path, csrf_enabled=False)
    _seed_user(app, "adm3@supdel.kg", "Admin", "admin")
    stu_id = _seed_user(app, "stu3@supdel.kg", "Student", "student")
    _seed_user(app, "mgr3@supdel.kg", "Manager", "sales_manager")
    _seed_user(app, "sup3@supdel.kg", "Supervisor", "supervisor")
    _seed_user(app, "tch3@supdel.kg", "Teacher", "teacher")
    _seed_user(app, "ast3@supdel.kg", "Assistant", "assistant")

    rep_id, att_id, full_obj, _ = _create_report_with_attachment(app, stu_id)

    # Anonymous user redirected to login
    anon = app.test_client()
    r_anon = anon.post(f"/admin/support/{rep_id}/delete", follow_redirects=False)
    assert r_anon.status_code == 302
    assert "/login" in r_anon.headers["Location"]

    for email in ("stu3@supdel.kg", "mgr3@supdel.kg", "sup3@supdel.kg", "tch3@supdel.kg", "ast3@supdel.kg"):
        c = app.test_client()
        _login(c, email)
        assert c.post(f"/admin/support/{rep_id}/delete").status_code == 403
        assert c.delete(f"/admin/support/{rep_id}/delete").status_code == 403

    with app.app_context():
        assert db.session.get(Report, rep_id) is not None
        assert db.session.get(SupportAttachment, att_id) is not None
        assert (tmp_path / "uploads" / full_obj).is_file()
        assert AuditLog.query.filter_by(action="support_request_delete").count() == 0


def test_missing_csrf_token_is_rejected_on_support_delete(tmp_path):
    app = _make_app(tmp_path, csrf_enabled=True)
    _seed_user(app, "adm4@supdel.kg", "Admin", "admin")
    stu_id = _seed_user(app, "stu4@supdel.kg", "Student", "student")
    rep_id, _, _, _ = _create_report_with_attachment(app, stu_id)

    c_adm = app.test_client()
    _login(c_adm, "adm4@supdel.kg", csrf_enabled=True)

    r_no_csrf = c_adm.post(f"/admin/support/{rep_id}/delete", data={"tab": "open"})
    assert r_no_csrf.status_code == 400
    r_del_no_csrf = c_adm.delete(f"/admin/support/{rep_id}/delete")
    assert r_del_no_csrf.status_code == 400

    with app.app_context():
        assert db.session.get(Report, rep_id) is not None


def test_playwright_admin_support_delete_confirmation_csp_clean(tmp_path):
    """Verify accessible confirmation modal prevents misclick, confirms deletion cleanly, and passes strict CSP."""
    from playwright.sync_api import sync_playwright

    app = _make_app(tmp_path, csrf_enabled=True)
    _seed_user(app, "adm.pw@supdel.kg", "Admin PW", "admin")
    stu_id = _seed_user(app, "stu.pw@supdel.kg", "Stu PW", "student")
    rep_id, _, _, _ = _create_report_with_attachment(app, stu_id)

    app.config["SERVER_NAME"] = None
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.add_init_script(
                'window.__csp = []; window.__errs = [];'
                'document.addEventListener("securitypolicyviolation", e => window.__csp.push(e.violatedDirective));'
                'window.addEventListener("pageerror", e => window.__errs.push(String(e)));'
            )
            page.goto(f"{base_url}/login", wait_until="networkidle")
            page.fill('input[name="email"]', "adm.pw@supdel.kg")
            page.fill('input[name="password"]', "Pass12345!")
            page.click('button[type="submit"]')
            page.wait_for_url(f"{base_url}/teacher/**")

            page.goto(f"{base_url}/teacher/reports", wait_until="networkidle")
            card = page.locator(f"#r{rep_id}")
            card.wait_for(state="visible", timeout=5000)

            # First click opens confirmation dialog; cancel preserves the report
            card.locator(f'form[action="/admin/support/{rep_id}/delete"] button[type="submit"]').click()
            dlg = page.locator("dialog[open]")
            dlg.wait_for(state="visible", timeout=5000)
            dlg.locator("[data-no]").click()
            dlg.wait_for(state="hidden", timeout=5000)
            assert card.is_visible()

            # Second click and confirm removes the report cleanly
            card.locator(f'form[action="/admin/support/{rep_id}/delete"] button[type="submit"]').click()
            dlg = page.locator("dialog[open]")
            dlg.wait_for(state="visible", timeout=5000)
            with page.expect_navigation(wait_until="networkidle"):
                dlg.locator("[data-yes]").click()

            assert page.locator(f"#r{rep_id}").count() == 0
            assert page.evaluate("window.__csp") == []
            assert page.evaluate("window.__errs") == []
            browser.close()
    finally:
        server.shutdown()

"""Stage 4 & Stage 5 tests: Support purge CLI, account deletion cleanup, admin deletion + audit, storage dashboard, persistence, XSS, CSP, responsive QA."""
from __future__ import annotations

import io
import logging
import os
import threading
from datetime import timedelta

from PIL import Image
from werkzeug.serving import make_server

from config import Config
from monday import create_app, storage
from monday.extensions import db
from monday.models import AuditLog, Report, StudentProfile, SupportAttachment, User, utcnow


def _tiny_png_bytes(color=(31, 79, 224)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")
    return buf.getvalue()


def _make_cfg(tmp_path, upload_dir):
    class Cfg(Config):
        TESTING = True
        SECRET_KEY = "sup-stage45-secret"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 's45.db'}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SQLALCHEMY_ENGINE_OPTIONS = {}
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        UPLOAD_FOLDER = str(upload_dir)
        SEED_DEMO = False
        IMPORT_PACKS = False

    return Cfg


def test_stage4_purge_cli_account_delete_admin_delete_and_storage_stats(tmp_path, caplog):
    upload_dir = tmp_path / "persist_uploads"
    app = create_app(_make_cfg(tmp_path, upload_dir), seed_if_empty=False)

    with app.app_context():
        db.create_all()
        s1 = User(email="s1@s4.kg", name="Student Four", role="student", is_approved=True)
        s1.set_password("StrongPass123!")
        s1.profile = StudentProfile(exam="SAT", grade="11", onboarded=True)

        s2 = User(email="s2@s4.kg", name="Student Del", role="student", is_approved=True)
        s2.set_password("StrongPass123!")
        s2.profile = StudentProfile(exam="SAT", grade="11", onboarded=True)

        tch = User(email="t1@s4.kg", name="Teacher Four", role="teacher", is_approved=True)
        tch.set_password("StrongPass123!")

        adm = User(email="adm@s4.kg", name="Admin Four", role="admin", is_approved=True)
        adm.set_password("StrongPass123!")

        db.session.add_all([s1, s2, tch, adm])
        db.session.commit()

    c_s1 = app.test_client()
    c_s1.post("/login", data={"email": "s1@s4.kg", "password": "StrongPass123!"})
    # Create 3 support messages with images for s1:
    # 1) old closed (>90d) -> purged
    # 2) recent closed (10d) -> kept
    # 3) open old (>90d) -> kept (still open!)
    for text in ("old-closed-secret-msg", "recent-closed-msg", "old-open-msg", "admin-del-msg"):
        r = c_s1.post(
            "/support",
            data={"subject": "Техническая проблема", "message": text, "images": (io.BytesIO(_tiny_png_bytes()), "shot.png")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 302

    c_s2 = app.test_client()
    c_s2.post("/login", data={"email": "s2@s4.kg", "password": "StrongPass123!"})
    assert c_s2.post(
        "/support",
        data={"subject": "Техническая проблема", "message": "student2-acc", "images": (io.BytesIO(_tiny_png_bytes()), "s2.png")},
        content_type="multipart/form-data",
    ).status_code == 302

    with app.app_context():
        old_dt = utcnow() - timedelta(days=120)
        recent_dt = utcnow() - timedelta(days=10)
        r_old_closed = Report.query.filter(Report.message.contains("old-closed-secret-msg")).one()
        r_old_closed.status = "fixed"
        r_old_closed.handled_at = old_dt

        r_recent_closed = Report.query.filter(Report.message.contains("recent-closed-msg")).one()
        r_recent_closed.status = "rejected"
        r_recent_closed.handled_at = recent_dt

        r_old_open = Report.query.filter(Report.message.contains("old-open-msg")).one()
        r_old_open.created_at = old_dt

        r_admin_del = Report.query.filter(Report.message.contains("admin-del-msg")).one()
        admin_del_att_id = r_admin_del.attachments[0].id
        admin_del_full = os.path.join(upload_dir, r_admin_del.attachments[0].full_object_name())

        old_closed_att_id = r_old_closed.attachments[0].id
        old_closed_full = os.path.join(upload_dir, r_old_closed.attachments[0].full_object_name())
        old_closed_thumb = os.path.join(upload_dir, r_old_closed.attachments[0].thumb_object_name())

        recent_att_id = r_recent_closed.attachments[0].id
        open_att_id = r_old_open.attachments[0].id

        s2_obj = User.query.filter_by(email="s2@s4.kg").one()
        s2_att = SupportAttachment.query.join(Report).filter(Report.author_id == s2_obj.id).one()
        s2_att_id = s2_att.id
        s2_full = os.path.join(upload_dir, s2_att.full_object_name())
        db.session.commit()

        assert os.path.isfile(old_closed_full) and os.path.isfile(old_closed_thumb)

    # 1. Dry-run CLI: nothing deleted, logs count not content
    runner = app.test_cli_runner()
    with caplog.at_level(logging.INFO):
        res_dry = runner.invoke(args=["support-purge-images", "--days", "90", "--dry-run"])
    assert res_dry.exit_code == 0
    assert "[DRY RUN]" in res_dry.output and "1 support attachment" in res_dry.output
    assert "old-closed-secret-msg" not in res_dry.output
    assert "old-closed-secret-msg" not in caplog.text
    assert os.path.isfile(old_closed_full)

    # 2. Real CLI purge + idempotent re-run
    res_real = runner.invoke(args=["support-purge-images", "--days", "90"])
    assert res_real.exit_code == 0
    assert "Purged 1 support attachment" in res_real.output
    assert not os.path.exists(old_closed_full)
    assert not os.path.exists(old_closed_thumb)
    with app.app_context():
        assert db.session.get(SupportAttachment, old_closed_att_id) is None
        assert db.session.get(SupportAttachment, recent_att_id) is not None
        assert db.session.get(SupportAttachment, open_att_id) is not None

    res_again = runner.invoke(args=["support-purge-images", "--days", "90"])
    assert res_again.exit_code == 0
    assert "Purged 0 support attachment" in res_again.output

    # 3. Non-admin cannot delete attachment (403); admin deletes + audit-logged + "Изображение удалено"
    c_tch = app.test_client()
    c_tch.post("/login", data={"email": "t1@s4.kg", "password": "StrongPass123!"})
    assert c_tch.post(f"/admin/support/attachments/{admin_del_att_id}/delete").status_code == 403
    assert c_s1.post(f"/admin/support/attachments/{admin_del_att_id}/delete").status_code == 403

    c_adm = app.test_client()
    c_adm.post("/login", data={"email": "adm@s4.kg", "password": "StrongPass123!"})
    r_adm_del = c_adm.post(f"/admin/support/attachments/{admin_del_att_id}/delete", follow_redirects=False)
    assert r_adm_del.status_code == 302
    assert not os.path.exists(admin_del_full)
    assert c_adm.get(f"/support/attachments/{admin_del_att_id}").status_code == 404

    with app.app_context():
        att_after = db.session.get(SupportAttachment, admin_del_att_id)
        assert att_after.deleted_at is not None
        audit = AuditLog.query.filter_by(action="support.attachment.delete", entity_id=admin_del_att_id).one()
        assert audit.entity_type == "support_attachment"

    assert "Изображение удалено" in c_s1.get("/support").data.decode("utf-8")
    assert "Изображение удалено" in c_adm.get("/teacher/reports").data.decode("utf-8")

    # 4. Admin overview section "Хранилище поддержки"
    admin_html = c_adm.get("/admin/").data.decode("utf-8")
    assert "Хранилище поддержки" in admin_html
    assert "активных вложений" in admin_html
    assert "занято места" in admin_html
    assert "средний размер" in admin_html
    assert "самое старое" in admin_html

    # 5. Account deletion removes student's attachments + stored files
    assert os.path.isfile(s2_full)
    r_del_acc = c_s2.post("/profile", data={"action": "delete", "password": "StrongPass123!"}, follow_redirects=False)
    assert r_del_acc.status_code == 302
    assert not os.path.exists(s2_full)
    with app.app_context():
        assert db.session.get(SupportAttachment, s2_att_id) is None


def test_stage5_redeploy_persistence_xss_csp_and_viewports(tmp_path):
    """QA: persistence across simulated redeploy, XSS escaping, CSP strictness, and desktop/iPhone/iPad layouts."""
    from playwright.sync_api import sync_playwright

    shared_uploads = tmp_path / "persistent_storage"
    cfg = _make_cfg(tmp_path, shared_uploads)

    # Boot App Instance 1 (pre-redeploy)
    app1 = create_app(cfg, seed_if_empty=False)
    with app1.app_context():
        db.create_all()
        stu = User(email="qa@s5.kg", name='Student <script>alert(1)</script>', role="student", is_approved=True)
        stu.set_password("StrongPass123!")
        stu.profile = StudentProfile(exam="SAT", grade="11", onboarded=True)
        adm = User(email="adm@s5.kg", name="Admin QA", role="admin", is_approved=True)
        adm.set_password("StrongPass123!")
        db.session.add_all([stu, adm])
        db.session.commit()

    c1 = app1.test_client()
    c1.post("/login", data={"email": "qa@s5.kg", "password": "StrongPass123!"})
    xss_payload = '<script>window.__xss=1</script><img src=x onerror=alert(1)>'
    r_post = c1.post(
        "/support",
        data={
            "subject": "Техническая проблема",
            "message": xss_payload,
            "images": (io.BytesIO(_tiny_png_bytes((20, 140, 90))), "<svg onload=alert(1)>.png"),
        },
        content_type="multipart/form-data",
    )
    assert r_post.status_code == 302
    with app1.app_context():
        att_id = SupportAttachment.query.one().id

    # Dispose App Instance 1 and boot App Instance 2 (simulated redeploy against same DB + persistent storage)
    with app1.app_context():
        db.engine.dispose()

    app2 = create_app(cfg, seed_if_empty=False)
    c2_adm = app2.test_client()
    c2_adm.post("/login", data={"email": "adm@s5.kg", "password": "StrongPass123!"})

    # Stored attachment remains accessible 200 OK after redeploy
    r_img = c2_adm.get(f"/support/attachments/{att_id}")
    assert r_img.status_code == 200
    assert r_img.headers.get("Content-Type") == "image/webp"

    # XSS escaped + strict CSP preserved on inbox and support pages
    inbox_resp = c2_adm.get("/teacher/reports")
    assert inbox_resp.status_code == 200
    inbox_html = inbox_resp.data.decode("utf-8")
    assert "<script>window.__xss=1</script>" not in inbox_html
    assert "&lt;script&gt;window.__xss=1&lt;/script&gt;" in inbox_html
    assert "onload=alert(1)" not in inbox_html
    csp = inbox_resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp and "object-src 'none'" in csp

    # Viewport & CSP visual check in Chromium across desktop, iPhone, iPad
    prev_server_name = app2.config.get("SERVER_NAME")
    app2.config["SERVER_NAME"] = None
    server = make_server("127.0.0.1", 0, app2)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            page = ctx.new_page()
            page.add_init_script("""
                window.__csp = [];
                window.__xssExecuted = false;
                document.addEventListener("securitypolicyviolation", (e) => window.__csp.push(e.violatedDirective));
            """)
            page.goto(f"{base_url}/login", wait_until="networkidle")
            page.fill('input[name="email"]', "adm@s5.kg")
            page.fill('input[name="password"]', "StrongPass123!")
            page.click('button[type="submit"]')
            page.wait_for_url(f"{base_url}/teacher/")

            for url in (f"{base_url}/admin/", f"{base_url}/teacher/reports", f"{base_url}/support"):
                page.goto(url, wait_until="networkidle")
                for vw, vh in [(1280, 800), (390, 844), (768, 1024)]:
                    page.set_viewport_size({"width": vw, "height": vh})
                    overflow = page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth")
                    assert overflow is False, f"Horizontal overflow at {url} on {vw}x{vh}"

            assert page.evaluate("() => window.__csp") == []
            assert page.evaluate("() => Boolean(window.__xss)") is False
            browser.close()
    finally:
        server.shutdown()
        app2.config["SERVER_NAME"] = prev_server_name

"""QA tests for Manager CRM visual hierarchy markup, CSRF tokens on every POST form, RBAC matrix, and /manager/account."""
import os
import re
import tempfile

from flask_migrate import upgrade

from config import Config
from monday.extensions import db
from monday.models import AuditLog, Lead, User


def _make_csrf_app():
    tmp = tempfile.mkdtemp()

    class ManagerUiConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = True
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "mgr_ui.db") + "?check_same_thread=False"
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    from monday import create_app

    app = create_app(ManagerUiConfig, seed_if_empty=False)
    with app.app_context():
        upgrade()
    return app


def _seed(app, email: str, name: str, role: str, pw: str = "StrongPass12!") -> int:
    with app.app_context():
        u = User(email=email, name=name, role=role, is_approved=True, is_blocked=False, is_on_shift=True)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        return u.id


def _extract_csrf(html: str) -> str:
    m = re.search(r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"', html)
    assert m, "Expected csrf_token hidden input on page"
    return m.group(1)


def _login_csrf(client, email: str, pw: str = "StrongPass12!"):
    page = client.get("/login")
    assert page.status_code == 200
    tok = _extract_csrf(page.get_data(as_text=True))
    resp = client.post("/login", data={"email": email, "password": pw, "csrf_token": tok}, follow_redirects=False)
    assert resp.status_code in (302, 200)


def _assert_every_post_form_has_csrf(html: str, path: str):
    forms = re.findall(r'<form\b[^>]*method=["\']post["\'][^>]*>.*?</form>', html, flags=re.IGNORECASE | re.DOTALL)
    assert forms, f"Expected at least one POST form on {path}"
    for idx, form_html in enumerate(forms):
        assert 'name="csrf_token"' in form_html, f"POST form #{idx} on {path} is missing csrf_token"


def test_manager_pages_200_hierarchy_and_csrf_tokens():
    app = _make_csrf_app()
    mgr_id = _seed(app, "mgr@example.com", "Aibek Manager", "sales_manager")
    sup_id = _seed(app, "sup@example.com", "Bermet Supervisor", "supervisor")

    with app.app_context():
        lead = Lead(
            full_name="Test Lead",
            phone="+996555001122",
            phone_e164="+996555001122",
            source="instagram",
            status="new",
            assigned_manager_id=mgr_id,
        )
        db.session.add(lead)
        db.session.commit()
        lead_id = lead.id

    c = app.test_client()
    _login_csrf(c, "sup@example.com")

    for path in (
        "/manager",
        "/manager/leads",
        f"/manager/leads/{lead_id}",
        "/manager/pipeline",
        "/manager/finance",
        "/manager/account",
    ):
        resp = c.get(path)
        assert resp.status_code == 200, f"GET {path} returned {resp.status_code}"
        html = resp.get_data(as_text=True)
        assert '<body class="mgr"' in html
        assert 'class="crm-workspace' not in html
        _assert_every_post_form_has_csrf(html, path)

    # /manager/leads status chips with counts + horizontal filter toolbar + inline status + drawer
    leads_html = c.get("/manager/leads?status=new").get_data(as_text=True)
    assert "mgr-tabs" in leads_html
    assert "mgr-tab__count" in leads_html
    assert "mgr-filter-row" in leads_html
    assert "mgr-inline-status" in leads_html

    # /manager/leads/<id> sticky header + pill back button + expandable note + collapsible convert details
    detail_html = c.get(f"/manager/leads/{lead_id}").get_data(as_text=True)
    assert "mgr-sticky-head" in detail_html
    assert "crm-back-btn" in detail_html
    assert "crm-activity-note" in detail_html
    assert "crm-convert-details" in detail_html

    # /manager/audit reachable for supervisor (GET page)
    assert c.get("/manager/audit").status_code == 200
    assert sup_id > 0


def test_manager_account_profile_password_and_csrf_enforcement():
    app = _make_csrf_app()
    mgr_id = _seed(app, "mgr2@example.com", "Old Name", "sales_manager")
    c = app.test_client()
    _login_csrf(c, "mgr2@example.com")

    # Missing CSRF rejected (400)
    no_csrf = c.post("/manager/account", data={"action": "profile", "name": "Hacker Name"})
    assert no_csrf.status_code == 400

    acct_html = c.get("/manager/account").get_data(as_text=True)
    assert "mgr-row-stack" in acct_html
    assert "Изменить" in acct_html
    # sales_manager must NOT see admin/audit links on /manager/account
    assert "/manager/audit" not in acct_html
    assert "/admin/" not in acct_html
    tok = _extract_csrf(acct_html)

    # Short name rejected (unchanged in DB)
    bad_name = c.post(
        "/manager/account",
        data={"action": "profile", "name": "A", "csrf_token": tok},
        follow_redirects=True,
    )
    assert bad_name.status_code == 200
    with app.app_context():
        assert db.session.get(User, mgr_id).name == "Old Name"

    # Valid name update persists and writes AuditLog
    ok_name = c.post(
        "/manager/account",
        data={"action": "profile", "name": "Aibek Updated", "csrf_token": tok},
        follow_redirects=True,
    )
    assert ok_name.status_code == 200
    with app.app_context():
        assert db.session.get(User, mgr_id).name == "Aibek Updated"
        log = AuditLog.query.filter_by(action="manager_profile_update", entity_id=mgr_id).first()
        assert log is not None

    # Password shorter than 12 chars rejected
    tok2 = _extract_csrf(c.get("/manager/account").get_data(as_text=True))
    short_pw = c.post(
        "/manager/account",
        data={"action": "password", "current": "StrongPass12!", "new": "short123", "csrf_token": tok2},
        follow_redirects=True,
    )
    assert short_pw.status_code == 200
    with app.app_context():
        assert db.session.get(User, mgr_id).check_password("StrongPass12!")

    # Valid >=12 char password updates password
    tok3 = _extract_csrf(c.get("/manager/account").get_data(as_text=True))
    good_pw = c.post(
        "/manager/account",
        data={"action": "password", "current": "StrongPass12!", "new": "NewStrongPass99!", "csrf_token": tok3},
        follow_redirects=True,
    )
    assert good_pw.status_code == 200
    with app.app_context():
        assert db.session.get(User, mgr_id).check_password("NewStrongPass99!")


def test_rbac_matrix_manager_routes_return_403_for_unauthorized_roles():
    app = _make_csrf_app()
    _seed(app, "st@example.com", "Student User", "student")
    _seed(app, "tc@example.com", "Teacher User", "teacher")
    mgr_id = _seed(app, "sm@example.com", "Sales User", "sales_manager")
    sup_id = _seed(app, "sup2@example.com", "Sup User", "supervisor")

    with app.app_context():
        lead = Lead(full_name="Other Lead", phone="+996555998877", status="new", assigned_manager_id=sup_id)
        db.session.add(lead)
        db.session.commit()
        other_lead_id = lead.id
        own_lead = Lead(full_name="Own Lead", phone="+996555998866", status="new", assigned_manager_id=mgr_id)
        db.session.add(own_lead)
        db.session.commit()
        own_lead_id = own_lead.id

    # 1. Student & Teacher denied across Manager CRM routes (GET/POST with valid CSRF token)
    for email in ("st@example.com", "tc@example.com"):
        c = app.test_client()
        _login_csrf(c, email)
        home = c.get("/", follow_redirects=True).get_data(as_text=True)
        tok = _extract_csrf(home)
        for p in ("/manager", "/manager/leads", f"/manager/leads/{own_lead_id}", "/manager/pipeline", "/manager/finance", "/manager/account"):
            assert c.get(p).status_code == 403, f"{email} unexpectedly got non-403 on {p}"
        assert c.post("/manager/account", data={"action": "profile", "name": "Bypass", "csrf_token": tok}).status_code == 403
        assert c.post(f"/manager/leads/{own_lead_id}/status", data={"status": "contacted", "csrf_token": tok}).status_code == 403

    # 2. sales_manager blocked from supervisor-only & admin/teacher routes and other manager's lead
    sm_c = app.test_client()
    _login_csrf(sm_c, "sm@example.com")
    tok_sm = _extract_csrf(sm_c.get("/manager/account").get_data(as_text=True))
    assert sm_c.get("/manager/audit").status_code == 403
    assert sm_c.get("/admin/").status_code == 403
    assert sm_c.get("/teacher/").status_code == 403
    assert sm_c.get(f"/manager/leads/{other_lead_id}").status_code == 403
    assert sm_c.post(f"/manager/leads/{own_lead_id}/delete", data={"reason": "test", "csrf_token": tok_sm}).status_code == 403

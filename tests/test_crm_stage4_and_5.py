"""Stage 4 (Lead Intake + Webhook + Round-Robin) and Stage 5 (Idempotent Lead -> Student Conversion) tests."""
import json
import os
import re
import tempfile

from config import Config
from monday.extensions import db
from monday.models import AuditLog, Lead, LeadActivity, LeadTask, StudentRecord, User
from test_app import APP, client, login


def _mk_user(email: str, name: str, role: str, password: str = "Pass12345") -> int:
    with APP.app_context():
        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(email=email, name=name, role=role, is_approved=True)
            u.set_password(password)
            db.session.add(u)
        else:
            u.role = role
            u.is_approved = True
            u.is_blocked = False
            u.set_password(password)
        db.session.commit()
        return u.id


def test_stage4_public_apply_webhook_auth_and_round_robin_assignment():
    # Use isolated app with explicit CRM_WEBHOOK_SECRET and 2 sales managers for deterministic round-robin
    tmp = tempfile.mkdtemp()

    class IntakeConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        CRM_WEBHOOK_SECRET = "super-secret-hook-token-99"
        CRM_SLA_MINUTES = 15
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "intake.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")
        SERVER_NAME = "localhost"

    from monday import create_app
    app = create_app(IntakeConfig, seed_if_empty=False)
    with app.app_context():
        m1 = User(email="rr1@example.com", name="RR Manager 1", role="sales_manager", is_approved=True)
        m1.set_password("Pass12345")
        m2 = User(email="rr2@example.com", name="RR Manager 2", role="sales_manager", is_approved=True)
        m2.set_password("Pass12345")
        db.session.add_all([m1, m2])
        db.session.commit()
        m1_id, m2_id = m1.id, m2.id

    c = app.test_client()

    # 1. Public site form GET & POST -> assigns to Manager 1 + creates SLA notification task
    assert c.get("/apply").status_code == 200
    r_pub = c.post("/apply", data={
        "full_name": "Site Applicant",
        "phone": "+996700111222",
        "interest": "SAT Math",
        "mode_preference": "online",
        "note": "Evening classes preferred",
    })
    assert r_pub.status_code == 302 and "sent=1" in r_pub.headers["Location"]

    # 2. Webhook rejects missing/wrong secret (401) and accepts valid secret (201) -> rotates to Manager 2
    assert c.post("/api/leads/webhook", json={"full_name": "No Auth", "phone": "123"}).status_code == 401
    assert c.post(
        "/api/leads/webhook",
        json={"full_name": "Bad Auth", "phone": "123"},
        headers={"X-Webhook-Secret": "wrong"},
    ).status_code == 401

    r_wh1 = c.post(
        "/api/leads/webhook",
        json={
            "full_name": "TG Bot Lead",
            "messenger_handle": "@tg_student",
            "source": "telegram",
            "interest": "ORT",
        },
        headers={"X-Webhook-Secret": "super-secret-hook-token-99"},
    )
    assert r_wh1.status_code == 201
    d1 = r_wh1.get_json()
    assert d1["ok"] is True and d1["assigned_manager_id"] == m2_id

    # 3. Third lead wraps round-robin back to Manager 1 (via Authorization: Bearer header)
    r_wh2 = c.post(
        "/api/leads/webhook",
        json={"full_name": "WA Bot Lead", "phone": "+996555333444", "source": "whatsapp"},
        headers={"Authorization": "Bearer super-secret-hook-token-99"},
    )
    assert r_wh2.status_code == 201
    assert r_wh2.get_json()["assigned_manager_id"] == m1_id

    with app.app_context():
        l1 = Lead.query.filter_by(full_name="Site Applicant").first()
        l2 = Lead.query.filter_by(full_name="TG Bot Lead").first()
        assert l1.assigned_manager_id == m1_id and l1.source == "site"
        assert l2.assigned_manager_id == m2_id and l2.source == "telegram"
        # Notification tasks created for assigned managers
        assert LeadTask.query.filter_by(lead_id=l1.id, assignee_id=m1_id).count() == 1
        assert LeadTask.query.filter_by(lead_id=l2.id, assignee_id=m2_id).count() == 1

    # 4. Unconfigured webhook secret -> 503
    app.config["CRM_WEBHOOK_SECRET"] = ""
    assert c.post("/api/leads/webhook", json={"full_name": "X", "phone": "1"}).status_code == 503


def test_stage5_lead_conversion_create_and_link_idempotent_with_audit():
    mgr_id = _mk_user("s5.mgr@example.com", "Stage5 Manager", "sales_manager")
    c_mgr = login(client(), "s5.mgr@example.com", "Pass12345")

    with APP.app_context():
        aibek = User.query.filter_by(email="aibek@monday.kg").first()
        aibek_id = aibek.id
        lead_create = Lead(
            full_name="New Conv Student",
            phone="+996700444555",
            source="instagram",
            interest="SAT",
            status="negotiation",
            assigned_manager_id=mgr_id,
        )
        lead_link = Lead(
            full_name="Link Existing Student",
            phone="+996700666777",
            source="referral",
            interest="ORT",
            status="trial_done",
            assigned_manager_id=mgr_id,
        )
        db.session.add_all([lead_create, lead_link])
        db.session.flush()
        db.session.add(LeadActivity(lead_id=lead_create.id, actor_id=mgr_id, type="note", body="Keep my history"))
        db.session.commit()
        lc_id, ll_id = lead_create.id, lead_link.id
        existing_stu_id = User.query.filter_by(email="student@monday.kg").first().id

    # 1. Convert by creating a new student + teacher StudentRecord -> returns 200 no-store with one-time password
    r_conv = c_mgr.post(
        f"/manager/leads/{lc_id}/convert",
        data={
            "convert_mode": "create",
            "student_email": "converted.s5@example.com",
            "exam": "SAT",
            "teacher_id": str(aibek_id),
            "reason": "Paid full course",
        },
    )
    assert r_conv.status_code == 200
    assert "no-store" in r_conv.headers.get("Cache-Control", "")
    body = r_conv.data.decode()
    m_pw = re.search(r"Временный пароль: (\w+)", body)
    assert m_pw is not None
    # Temp password must NOT be stored in session cookie
    with c_mgr.session_transaction() as sess:
        assert m_pw.group(1) not in json.dumps(dict(sess))

    with APP.app_context():
        lc = db.session.get(Lead, lc_id)
        stu = User.query.filter_by(email="converted.s5@example.com").first()
        assert stu is not None and stu.role == "student"
        assert lc.converted_student_id == stu.id and lc.status == "won"
        # History preserved!
        assert LeadActivity.query.filter_by(lead_id=lc_id, body="Keep my history").count() == 1
        # Teacher StudentRecord linked by permanent IDs
        rec = StudentRecord.query.filter_by(teacher_id=aibek_id, student_user_id=stu.id).first()
        assert rec is not None
        # Audit entry written
        audits = AuditLog.query.filter_by(action="lead_convert", entity_type="lead", entity_id=lc_id).all()
        assert len(audits) == 1 and audits[0].new_value["converted_student_id"] == stu.id
        stu_id = stu.id

    # 2. Idempotency: re-posting /convert must NOT create duplicate student or duplicate audit entry
    r_again = c_mgr.post(
        f"/manager/leads/{lc_id}/convert",
        data={"convert_mode": "create", "student_email": "different@example.com"},
    )
    assert r_again.status_code == 302
    with APP.app_context():
        assert db.session.get(Lead, lc_id).converted_student_id == stu_id
        assert User.query.filter_by(email="different@example.com").first() is None
        assert AuditLog.query.filter_by(action="lead_convert", entity_type="lead", entity_id=lc_id).count() == 1

    # 3. Convert by linking an existing student by permanent ID
    r_link = c_mgr.post(
        f"/manager/leads/{ll_id}/convert",
        data={"convert_mode": "link", "existing_student_id": str(existing_stu_id)},
    )
    assert r_link.status_code == 302
    with APP.app_context():
        ll = db.session.get(Lead, ll_id)
        assert ll.converted_student_id == existing_stu_id and ll.status == "won"
        assert AuditLog.query.filter_by(action="lead_convert", entity_type="lead", entity_id=ll_id).count() == 1

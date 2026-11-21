"""Stage 3 Manager UI tests: dashboard, lead list, lead card, pipeline, SLA badge, supervisor scoping & audit."""
import os
import tempfile
from datetime import timedelta

from config import Config
from monday.extensions import db
from monday.models import AuditLog, Lead, LeadActivity, LeadTask, User, utcnow


def test_stage3_sales_manager_full_lead_lifecycle_sla_and_isolation():
    tmp = tempfile.mkdtemp()

    class Stage3Config(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "stage3.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    from monday import create_app

    app = create_app(Stage3Config, seed_if_empty=False)

    def _mk_user(email: str, name: str, role: str, password: str = "Pass12345") -> int:
        with app.app_context():
            u = User(email=email, name=name, role=role, is_approved=True)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            return u.id

    def _login(email: str, password: str):
        c = app.test_client()
        assert c.post("/login", data={"email": email, "password": password}).status_code == 302
        return c

    m1_id = _mk_user("s3.m1@example.com", "Manager One", "sales_manager")
    m2_id = _mk_user("s3.m2@example.com", "Manager Two", "sales_manager")
    sup_id = _mk_user("s3.sup@example.com", "Supervisor One", "supervisor")

    c_m1 = _login("s3.m1@example.com", "Pass12345")
    c_m2 = _login("s3.m2@example.com", "Pass12345")
    c_sup = _login("s3.sup@example.com", "Pass12345")

    # 1. Manager 1 creates a lead via UI
    r_new = c_m1.post("/manager/leads/new", data={
        "full_name": "Nurlan S3",
        "phone": "+996555000111",
        "source": "instagram",
        "interest": "SAT Math",
        "mode_preference": "online",
        "note": "Wants trial this week",
    })
    assert r_new.status_code == 302
    with app.app_context():
        lead = Lead.query.filter_by(full_name="Nurlan S3").order_by(Lead.id.desc()).first()
        assert lead is not None and lead.assigned_manager_id == m1_id and lead.status == "new"
        # Backdate created_at by 25 minutes to verify red Speed-to-Lead SLA badge (> 15 min)
        lead.created_at = utcnow() - timedelta(minutes=25)
        db.session.commit()
        lead_id = lead.id

    # 2. Dashboard & Lead list show red overdue SLA badge; Manager 2 gets 403 on Manager 1's lead!
    dash_html = c_m1.get("/manager").data.decode()
    assert "Nurlan S3" in dash_html and 'data-sla-badge="overdue"' in dash_html

    list_html = c_m1.get("/manager/leads?sla=overdue&source=instagram&q=Nurlan").data.decode()
    assert "Nurlan S3" in list_html and 'data-sla-badge="overdue"' in list_html

    assert c_m2.get(f"/manager/leads/{lead_id}").status_code == 403
    assert c_m2.post(f"/manager/leads/{lead_id}/status", data={"status": "contacted"}).status_code == 403
    assert "Nurlan S3" not in c_m2.get("/manager/leads").data.decode()

    # 3. Adding a call activity clears unanswered SLA and auto-advances status new -> contacted
    r_act = c_m1.post(f"/manager/leads/{lead_id}/activity", data={"type": "call", "body": "Spoke with parent"})
    assert r_act.status_code == 302
    with app.app_context():
        l = db.session.get(Lead, lead_id)
        assert l.first_contact_at is not None and l.last_contact_at is not None
        assert l.status == "contacted"

    # 4. Add a follow-up task and toggle it done
    due_str = (utcnow() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    r_t = c_m1.post(f"/manager/leads/{lead_id}/tasks", data={"note": "Confirm trial time", "due_at": due_str})
    assert r_t.status_code == 302
    with app.app_context():
        task = LeadTask.query.filter_by(lead_id=lead_id).first()
        assert task is not None and task.done_at is None
        tid = task.id
    assert "Confirm trial time" in c_m1.get("/manager").data.decode()
    assert c_m1.post(f"/manager/tasks/{tid}/toggle").status_code == 302
    with app.app_context():
        assert db.session.get(LeadTask, tid).done_at is not None

    # 5. Pipeline board renders and advances status
    pipe_html = c_m1.get("/manager/pipeline").data.decode()
    assert "Nurlan S3" in pipe_html
    r_mv = c_m1.post(f"/manager/leads/{lead_id}/status", data={"status": "trial_scheduled", "next": "/manager/pipeline"})
    assert r_mv.status_code == 302 and "/manager/pipeline" in r_mv.headers["Location"]
    with app.app_context():
        assert db.session.get(Lead, lead_id).status == "trial_scheduled"

    # 6. Sales Manager CANNOT reassign or delete (403); Supervisor CAN see all, reassign, audit & delete!
    assert c_m1.post(f"/manager/leads/{lead_id}/reassign", data={"assigned_manager_id": m2_id}).status_code == 403
    assert c_m1.post(f"/manager/leads/{lead_id}/delete").status_code == 403

    assert "Nurlan S3" in c_sup.get("/manager/leads").data.decode()
    r_re = c_sup.post(f"/manager/leads/{lead_id}/reassign", data={"assigned_manager_id": m2_id, "reason": "Load balancing"})
    assert r_re.status_code == 302
    with app.app_context():
        assert db.session.get(Lead, lead_id).assigned_manager_id == m2_id
        al = AuditLog.query.filter_by(action="lead_reassign", entity_type="lead", entity_id=lead_id).first()
        assert al is not None and al.actor_id == sup_id
        assert al.old_value == {"assigned_manager_id": m1_id} and al.new_value == {"assigned_manager_id": m2_id}
        assert al.reason == "Load balancing"

    # Manager 2 can now view the reassigned lead; Supervisor sees audit entry in UI
    assert c_m2.get(f"/manager/leads/{lead_id}").status_code == 200
    audit_html = c_sup.get("/manager/audit?action=lead_reassign").data.decode()
    assert "lead_reassign" in audit_html and "Load balancing" in audit_html

    # Supervisor deletes lead -> recorded in AuditLog
    r_del = c_sup.post(f"/manager/leads/{lead_id}/delete", data={"reason": "Duplicate test entry"})
    assert r_del.status_code == 302
    with app.app_context():
        assert db.session.get(Lead, lead_id) is None
        al_del = AuditLog.query.filter_by(action="lead_delete", entity_type="lead", entity_id=lead_id).first()
        assert al_del is not None and al_del.reason == "Duplicate test entry"

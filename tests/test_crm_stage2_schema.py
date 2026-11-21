"""Stage 2 CRM schema & AuditLog tests."""
from datetime import timedelta

from monday.audit import write_audit_log
from monday.extensions import db
from monday.models import (
    AuditLog,
    LEAD_ACTIVITY_TYPES,
    LEAD_SOURCES,
    LEAD_STATUSES,
    Lead,
    LeadActivity,
    LeadTask,
    User,
    utcnow,
)
from test_app import APP, client, login


def test_stage2_crm_models_and_cascade_relationships():
    assert set(LEAD_SOURCES) == {"instagram", "whatsapp", "telegram", "site", "referral", "other"}
    assert LEAD_STATUSES == ("new", "contacted", "trial_scheduled", "trial_done", "negotiation", "won", "lost")
    assert set(LEAD_ACTIVITY_TYPES) == {"call", "message", "note", "status_change", "reassign"}

    with APP.app_context():
        mgr = User.query.filter_by(email="stage2.mgr@example.com").first()
        if not mgr:
            mgr = User(email="stage2.mgr@example.com", name="Stage2 Manager", role="sales_manager")
            mgr.set_password("Pass12345")
            db.session.add(mgr)
            db.session.flush()

        lead = Lead(
            full_name="Aigul Test",
            phone="+996700112233",
            messenger_handle="@aigul_tg",
            source="instagram",
            interest="SAT Math",
            mode_preference="online",
            status="new",
            assigned_manager_id=mgr.id,
        )
        db.session.add(lead)
        db.session.flush()

        act = LeadActivity(lead_id=lead.id, actor_id=mgr.id, type="call", body="Initial call placed")
        task = LeadTask(lead_id=lead.id, assignee_id=mgr.id, due_at=utcnow() + timedelta(hours=2), note="Send trial link")
        db.session.add_all([act, task])
        write_audit_log(
            actor_id=mgr.id,
            action="lead_test",
            entity_type="lead",
            entity_id=lead.id,
            old_value=None,
            new_value={"status": "new"},
            reason="stage2 schema check",
        )
        db.session.commit()

        loaded = db.session.get(Lead, lead.id)
        assert loaded is not None
        assert loaded.assigned_manager_id == mgr.id
        assert loaded.converted_student_id is None
        assert len(loaded.activities) == 1 and loaded.activities[0].type == "call"
        assert len(loaded.tasks) == 1 and loaded.tasks[0].assignee_id == mgr.id

        # Cascade delete removes activities & tasks cleanly
        lead_id = loaded.id
        db.session.delete(loaded)
        db.session.commit()
        assert LeadActivity.query.filter_by(lead_id=lead_id).count() == 0
        assert LeadTask.query.filter_by(lead_id=lead_id).count() == 0


def test_stage2_role_change_writes_audit_log():
    with APP.app_context():
        u = User.query.filter_by(email="stage2.audit.role@example.com").first()
        if not u:
            u = User(email="stage2.audit.role@example.com", name="Role Audit Target", role="student")
            u.set_password("Pass12345")
            db.session.add(u)
            db.session.commit()
        uid = u.id

    adm = login(client(), "admin@monday.kg", "monday2026")
    r = adm.post(f"/admin/users/{uid}/role", data={"role": "sales_manager", "reason": "Hired into sales"})
    assert r.status_code == 302
    with APP.app_context():
        entry = (
            AuditLog.query.filter_by(action="role_change", entity_type="user", entity_id=uid)
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert entry is not None
        assert entry.old_value == {"role": "student"}
        assert entry.new_value == {"role": "sales_manager"}
        assert entry.reason == "Hired into sales"

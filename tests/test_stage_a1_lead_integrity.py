"""Stage A1 tests: phone normalization, dedup across intake channels, CLI dry-run + merge, shift/load-balanced concurrent round-robin, and pipeline state machine."""
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from flask_migrate import upgrade

from config import Config
from monday.extensions import db
from monday.models import AuditLog, Lead, LeadActivity, LeadTask, User
from monday.phone_utils import normalize_messenger, normalize_phone


def _make_isolated_app():
    tmp = tempfile.mkdtemp()

    class StageA1Config(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        CRM_WEBHOOK_SECRET = "a1-secret-tok"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "stage_a1.db") + "?check_same_thread=False"
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    from monday import create_app

    app = create_app(StageA1Config, seed_if_empty=False)
    with app.app_context():
        upgrade()
    return app


def _seed(app, email: str, name: str, role: str, is_on_shift: bool = True, pw: str = "StrongPass12!") -> int:
    with app.app_context():
        u = User(email=email, name=name, role=role, is_approved=True, is_blocked=False, is_on_shift=is_on_shift)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        return u.id


def _login(client, email: str, pw: str = "StrongPass12!"):
    return client.post("/login", data={"email": email, "password": pw})


def test_phone_normalizer_kg_variants_international_and_invalid():
    # Three KG variants of the same number must normalize identically
    assert normalize_phone("+996 555 12-34-56") == "+996555123456"
    assert normalize_phone("0 (555) 123-456") == "+996555123456"
    assert normalize_phone("996555123456") == "+996555123456"
    assert normalize_phone("00996 555 123 456") == "+996555123456"

    # Valid other international numbers pass through
    assert normalize_phone("+7 (701) 555-01-99") == "+77015550199"
    assert normalize_phone("+1 415 555 0199") == "+14155550199"

    # Invalid numbers return None without raising exceptions
    for bad in (None, "", "   ", "abc", "+996123", "0555", "123", "+0001234567", "+12", "996000000000"):
        assert normalize_phone(bad) is None

    assert normalize_messenger(" @Aidana_TG ") == "aidana_tg"
    assert normalize_messenger("https://t.me/Aidana_TG/") == "aidana_tg"


def test_deduplication_across_apply_webhook_manual_and_closed_previous_link():
    app = _make_isolated_app()
    m1_id = _seed(app, "m1@example.com", "Mgr 1", "sales_manager")
    c = app.test_client()
    hdr = {"X-Webhook-Secret": "a1-secret-tok"}

    # 1. /apply with +996555111222
    assert c.post("/apply", data={"full_name": "Ainura", "phone": "+996 555 111 222", "note": "First inquiry"}).status_code == 302

    # 2. Webhook with 0(555)111-222 -> deduped into the SAME open lead, no new SLA task!
    r2 = c.post("/api/leads/webhook", json={"full_name": "Ainura K", "phone": "0 (555) 111-222", "source": "whatsapp", "note": "Ping 2"}, headers=hdr)
    assert r2.status_code == 200 and r2.get_json()["deduplicated"] is True

    # 3. Manual /manager/leads/new with 996555111222 -> deduped into same open lead!
    _login(c, "m1@example.com")
    c.post("/manager/leads/new", data={"full_name": "Ainura", "phone": "996555111222", "source": "telegram", "note": "Manual note"})

    with app.app_context():
        leads = Lead.query.all()
        assert len(leads) == 1
        l = leads[0]
        assert l.phone_e164 == "+996555111222"
        assert l.last_contact_at is not None
        assert LeadTask.query.filter_by(lead_id=l.id).count() == 1
        assert LeadActivity.query.filter_by(lead_id=l.id).count() >= 3

        # Messenger dedupe on @same_handle vs https://t.me/same_handle
        c.post("/api/leads/webhook", json={"full_name": "TG User", "messenger_handle": "@same_handle", "source": "telegram"}, headers=hdr)
        c.post("/api/leads/webhook", json={"full_name": "TG User", "messenger_handle": "https://t.me/SAME_HANDLE", "source": "telegram"}, headers=hdr)
        assert Lead.query.filter_by(messenger_norm="same_handle").count() == 1

        # Close first lead as lost -> repeat contact creates a NEW lead linked via previous_lead_id!
        l.status = "lost"
        l.lost_reason = "No budget right now"
        db.session.commit()
        first_id = l.id

    r_new = c.post("/api/leads/webhook", json={"full_name": "Ainura Return", "phone": "0555111222", "source": "site"}, headers=hdr)
    assert r_new.status_code == 201 and r_new.get_json()["deduplicated"] is False
    with app.app_context():
        l_ret = db.session.get(Lead, r_new.get_json()["lead_id"])
        assert l_ret.previous_lead_id == first_id


def test_find_duplicates_cli_dry_run_and_supervisor_merge():
    app = _make_isolated_app()
    m1_id = _seed(app, "m1@example.com", "Mgr 1", "sales_manager")
    sup_id = _seed(app, "sup@example.com", "Sup", "supervisor")

    with app.app_context():
        l1 = Lead(full_name="Dup One", phone="+996555888999", phone_e164="+996555888999", assigned_manager_id=m1_id)
        l2 = Lead(full_name="Dup Two", phone="0555888999", phone_e164="+996555888999", assigned_manager_id=m1_id)
        db.session.add_all([l1, l2])
        db.session.flush()
        db.session.add(LeadActivity(lead_id=l2.id, actor_id=m1_id, type="note", body="Activity from l2"))
        db.session.add(LeadTask(lead_id=l2.id, assignee_id=m1_id, due_at=l2.created_at, note="Task from l2"))
        db.session.commit()
        l1_id, l2_id = l1.id, l2.id

    # Dry-run CLI reports duplicates without mutating DB
    res = app.test_cli_runner().invoke(args=["crm-find-duplicates"])
    assert res.exit_code == 0
    assert "+996555888999" in res.output and str(l1_id) in res.output and str(l2_id) in res.output

    # Sales manager cannot merge (403); Supervisor merges l2 -> l1 with audit log
    c_mgr = app.test_client()
    _login(c_mgr, "m1@example.com")
    assert c_mgr.post(f"/manager/leads/{l1_id}/merge", data={"duplicate_lead_id": str(l2_id)}).status_code == 403

    c_sup = app.test_client()
    _login(c_sup, "sup@example.com")
    r_m = c_sup.post(f"/manager/leads/{l1_id}/merge", data={"duplicate_lead_id": str(l2_id), "reason": "Same parent"})
    assert r_m.status_code == 302
    with app.app_context():
        assert db.session.get(Lead, l2_id) is None
        assert LeadActivity.query.filter_by(lead_id=l1_id, body="Activity from l2").count() == 1
        assert LeadTask.query.filter_by(lead_id=l1_id, note="Task from l2").count() == 1
        assert AuditLog.query.filter_by(action="lead_merge", entity_id=l1_id).count() == 1


def test_shift_filter_load_balancing_supervisor_fallback_and_concurrent_round_robin():
    app = _make_isolated_app()
    m1_id = _seed(app, "m1@example.com", "Mgr 1", "sales_manager", is_on_shift=True)
    m2_id = _seed(app, "m2@example.com", "Mgr 2", "sales_manager", is_on_shift=False)  # off shift!
    m3_id = _seed(app, "m3@example.com", "Mgr 3", "sales_manager", is_on_shift=True)
    sup_id = _seed(app, "sup@example.com", "Sup", "supervisor", is_on_shift=True)

    # Pre-seed 2 open leads on m1 so load balancer MUST prefer m3 (0 open leads), skipping off-shift m2!
    with app.app_context():
        db.session.add_all([
            Lead(full_name="Pre1", phone="+996500000001", phone_e164="+996500000001", assigned_manager_id=m1_id),
            Lead(full_name="Pre2", phone="+996500000002", phone_e164="+996500000002", assigned_manager_id=m1_id),
        ])
        db.session.commit()

    # Parallel concurrent webhook submissions
    def _send(idx: int):
        cl = app.test_client()
        return cl.post(
            "/api/leads/webhook",
            json={"full_name": f"Concurrent {idx}", "phone": f"+9967001000{idx:02d}", "source": "site"},
            headers={"X-Webhook-Secret": "a1-secret-tok"},
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_send, range(4)))
    for r in results:
        assert r.status_code == 201
        assert r.get_json()["assigned_manager_id"] in (m1_id, m3_id)

    with app.app_context():
        # m2 is off shift -> MUST have 0 leads!
        assert Lead.query.filter_by(assigned_manager_id=m2_id).count() == 0
        # Load balanced cleanly: initial m1(2), m3(0) + 4 new leads = m1(3), m3(3)!
        assert Lead.query.filter_by(assigned_manager_id=m1_id).count() == 3
        assert Lead.query.filter_by(assigned_manager_id=m3_id).count() == 3

        # Put BOTH m1 and m3 off shift -> must fall back to Supervisor!
        db.session.get(User, m1_id).is_on_shift = False
        db.session.get(User, m3_id).is_on_shift = False
        db.session.commit()

    r_sup = _send(99)
    assert r_sup.status_code == 201 and r_sup.get_json()["assigned_manager_id"] == sup_id


def test_pipeline_state_machine_invalid_transitions_lost_reason_and_override():
    app = _make_isolated_app()
    m1_id = _seed(app, "m1@example.com", "Mgr 1", "sales_manager")
    _seed(app, "sup@example.com", "Sup", "supervisor")
    stu_id = _seed(app, "stu@example.com", "Student", "student", pw="StudentPw1!")

    with app.app_context():
        l = Lead(full_name="Pipeline Guard", phone="+996555777888", phone_e164="+996555777888", assigned_manager_id=m1_id, status="new")
        db.session.add(l)
        db.session.commit()
        lid = l.id

    c_mgr = app.test_client()
    _login(c_mgr, "m1@example.com")

    # 1. Invalid transitions from 'new': new->won, new->trial_done, new->negotiation MUST fail & keep status='new'
    for bad_target in ("won", "trial_done", "negotiation"):
        c_mgr.post(f"/manager/leads/{lid}/status", data={"status": bad_target})
        with app.app_context():
            assert db.session.get(Lead, lid).status == "new", f"new->{bad_target} should be blocked"

    # 2. new->lost without lost_reason MUST fail; with lost_reason succeeds; lost->won MUST fail
    c_mgr.post(f"/manager/leads/{lid}/status", data={"status": "lost", "lost_reason": ""})
    with app.app_context():
        assert db.session.get(Lead, lid).status == "new"

    c_mgr.post(f"/manager/leads/{lid}/status", data={"status": "lost", "lost_reason": "Postponed exam"})
    with app.app_context():
        assert db.session.get(Lead, lid).status == "lost"

    c_mgr.post(f"/manager/leads/{lid}/status", data={"status": "won"})
    with app.app_context():
        assert db.session.get(Lead, lid).status == "lost"

    # Reopen lost->contacted->trial_scheduled, block trial_scheduled->won & trial_scheduled->new
    c_mgr.post(f"/manager/leads/{lid}/status", data={"status": "contacted"})
    c_mgr.post(f"/manager/leads/{lid}/status", data={"status": "trial_scheduled"})
    for bad_target in ("won", "new"):
        c_mgr.post(f"/manager/leads/{lid}/status", data={"status": bad_target})
        with app.app_context():
            assert db.session.get(Lead, lid).status == "trial_scheduled"

    # Mark won+converted_student_id -> Sales manager CANNOT leave won; Supervisor without reason CANNOT; Supervisor WITH override+reason CAN & logs AuditLog!
    with app.app_context():
        lead = db.session.get(Lead, lid)
        lead.status = "won"
        lead.converted_student_id = stu_id
        db.session.commit()

    c_mgr.post(f"/manager/leads/{lid}/status", data={"status": "lost", "lost_reason": "Ref", "supervisor_override": "1", "override_reason": "Bypass attempt"})
    with app.app_context():
        assert db.session.get(Lead, lid).status == "won"

    c_sup = app.test_client()
    _login(c_sup, "sup@example.com")
    c_sup.post(f"/manager/leads/{lid}/status", data={"status": "lost", "lost_reason": "Refunded"})
    with app.app_context():
        assert db.session.get(Lead, lid).status == "won"

    c_sup.post(
        f"/manager/leads/{lid}/status",
        data={"status": "lost", "lost_reason": "Full refund", "supervisor_override": "1", "override_reason": "Customer cancelled"},
    )
    with app.app_context():
        assert db.session.get(Lead, lid).status == "lost"
        assert AuditLog.query.filter_by(action="lead_status_override", entity_id=lid).count() == 1


def test_manual_lead_create_round_robin_and_explicit_supervisor_pick():
    app = _make_isolated_app()
    m1_id = _seed(app, "m1@example.com", "Mgr 1", "sales_manager", is_on_shift=True)
    m2_id = _seed(app, "m2@example.com", "Mgr 2", "sales_manager", is_on_shift=True)
    _seed(app, "sup@example.com", "Sup", "supervisor", is_on_shift=True)

    c_sup = app.test_client()
    _login(c_sup, "sup@example.com")

    # 1. Supervisor creates without explicit assignee -> round-robin assigns to m1, then m2
    assert c_sup.post("/manager/leads/new", data={"full_name": "Auto One", "phone": "+996555010101"}).status_code == 302
    assert c_sup.post("/manager/leads/new", data={"full_name": "Auto Two", "phone": "+996555020202"}).status_code == 302
    # 2. Supervisor explicitly picks m1 even though both have 1 lead -> honors explicit pick
    assert c_sup.post(
        "/manager/leads/new",
        data={"full_name": "Manual Pick", "phone": "+996555030303", "assigned_manager_id": str(m1_id)},
    ).status_code == 302

    with app.app_context():
        assert Lead.query.filter_by(full_name="Auto One").first().assigned_manager_id == m1_id
        assert Lead.query.filter_by(full_name="Auto Two").first().assigned_manager_id == m2_id
        assert Lead.query.filter_by(full_name="Manual Pick").first().assigned_manager_id == m1_id

    # 3. Sales manager creates manually while m1 has 2 leads and m2 has 1 lead -> routes to m2 without 403!
    c_m1 = app.test_client()
    _login(c_m1, "m1@example.com")
    r_m1 = c_m1.post("/manager/leads/new", data={"full_name": "WalkIn To Least", "phone": "+996555040404"})
    assert r_m1.status_code == 302 and r_m1.headers["Location"].endswith("/manager/leads")
    with app.app_context():
        assert Lead.query.filter_by(full_name="WalkIn To Least").first().assigned_manager_id == m2_id

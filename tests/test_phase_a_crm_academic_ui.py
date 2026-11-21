"""Phase A CRM & Academic Ops UI upgrade tests: 4-bucket tasks, dual pipeline/student health, unified timeline, Student 360, multi-view schedule + conflict detection, and enriched lesson register."""
import os
import tempfile
from datetime import timedelta

from flask_migrate import upgrade

from config import Config
from monday.audit import write_audit_log
from monday.extensions import db
from monday.models import (
    AcademicCourse,
    GroupEnrollment,
    Lead,
    LeadActivity,
    LeadTask,
    Lesson,
    LessonAttendance,
    Location,
    StudyGroup,
    User,
    utcnow,
)


def _make_isolated_app():
    tmp = tempfile.mkdtemp()

    class PhaseAConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "phase_a.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    from monday import create_app

    app = create_app(PhaseAConfig, seed_if_empty=False)
    with app.app_context():
        upgrade()
    return app


def _seed(app, email: str, name: str, role: str, pw: str = "StrongPass12!") -> int:
    with app.app_context():
        u = User(email=email, name=name, role=role, is_approved=True, is_blocked=False)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        return u.id


def _login(client, email: str, pw: str = "StrongPass12!"):
    return client.post("/login", data={"email": email, "password": pw})


def test_phase_a_4bucket_tasks_dual_pipeline_student_health_and_unified_timeline():
    app = _make_isolated_app()
    m1_id = _seed(app, "m1@example.com", "Mgr 1", "sales_manager")
    m2_id = _seed(app, "m2@example.com", "Mgr 2", "sales_manager")
    sup_id = _seed(app, "sup@example.com", "Supervisor", "supervisor")
    t_id = _seed(app, "teach@example.com", "Teacher A", "teacher")
    s1_id = _seed(app, "s1@example.com", "Risk Student", "student", pw="StudentPw1!")
    s2_id = _seed(app, "s2@example.com", "Other Mgr Student", "student", pw="StudentPw1!")

    now = utcnow()
    with app.app_context():
        l1 = Lead(full_name="Lead One", phone="+996500111", assigned_manager_id=m1_id, converted_student_id=s1_id, status="won")
        l2 = Lead(full_name="Lead Two", phone="+996500222", assigned_manager_id=m2_id, converted_student_id=s2_id, status="won")
        db.session.add_all([l1, l2])
        db.session.flush()
        l1_id = l1.id

        # Tasks across all 4 buckets: Overdue, Today (+2h if same UTC day, else we check ids/sections), This Week (+3d), Later (+14d)
        db.session.add_all([
            LeadTask(lead_id=l1.id, assignee_id=m1_id, due_at=now - timedelta(hours=3), note="Task Overdue A"),
            LeadTask(lead_id=l1.id, assignee_id=m1_id, due_at=now + timedelta(minutes=30), note="Task Soon B"),
            LeadTask(lead_id=l1.id, assignee_id=m1_id, due_at=now + timedelta(days=3), note="Task Week C"),
            LeadTask(lead_id=l1.id, assignee_id=m1_id, due_at=now + timedelta(days=14), note="Task Later D"),
            LeadTask(lead_id=l2.id, assignee_id=m2_id, due_at=now + timedelta(days=14), note="Other Mgr Task E"),
        ])

        # Activities + Audit log + Academic attendance for unified timeline & at-risk health bucket
        db.session.add(LeadActivity(lead_id=l1.id, actor_id=m1_id, type="call", body="Initial discovery call"))
        write_audit_log(actor_id=sup_id, action="lead_convert", entity_type="lead", entity_id=l1.id, reason="Paid package")

        course = AcademicCourse(code="SAT-A", name="SAT Prep", exam="SAT")
        loc = Location(name="Campus 1", room="202")
        db.session.add_all([course, loc])
        db.session.flush()

        grp = StudyGroup(name="SAT Group 1", course_id=course.id, teacher_id=t_id, default_location_id=loc.id)
        db.session.add(grp)
        db.session.flush()

        db.session.add(GroupEnrollment(group_id=grp.id, student_user_id=s1_id, course_id=course.id, status="active"))
        les1 = Lesson(group_id=grp.id, teacher_id=t_id, starts_at=now - timedelta(days=2), lesson_mode="offline", location_id=loc.id)
        les2 = Lesson(group_id=grp.id, teacher_id=t_id, starts_at=now - timedelta(days=1), lesson_mode="offline", location_id=loc.id)
        db.session.add_all([les1, les2])
        db.session.flush()
        db.session.add_all([
            LessonAttendance(lesson_id=les1.id, student_user_id=s1_id, status="absent", marked_by_id=t_id),
            LessonAttendance(lesson_id=les2.id, student_user_id=s1_id, status="absent", marked_by_id=t_id),
        ])
        db.session.commit()

    # 1. Manager 1 dashboard shows all 4 task buckets and hides Other Mgr's task
    c_m1 = app.test_client()
    _login(c_m1, "m1@example.com")
    dash = c_m1.get("/manager").data.decode()
    assert "Task Overdue A" in dash
    assert "Task Week C" in dash
    assert "Task Later D" in dash
    assert "Other Mgr Task E" not in dash

    # Supervisor sees Other Mgr Task E under ?scope=all
    c_sup = app.test_client()
    _login(c_sup, "sup@example.com")
    dash_all = c_sup.get("/manager?scope=all").data.decode()
    assert "Task Overdue A" in dash_all and "Other Mgr Task E" in dash_all

    # 2. Dual pipeline mode=students puts s1 in Risk (2+ absences); Manager 1 cannot access Other Mgr's s2!
    stu_board = c_m1.get("/manager/pipeline?mode=students").data.decode()
    assert "Risk Student" in stu_board and "Other Mgr Student" not in stu_board
    assert c_m1.get(f"/manager/students/{s1_id}").status_code == 200
    assert c_m1.get(f"/manager/students/{s2_id}").status_code == 403
    assert c_sup.get(f"/manager/students/{s2_id}").status_code == 200

    # 3. Unified timeline tabs on lead_detail & student_detail filter categories cleanly
    lead_all = c_m1.get(f"/manager/leads/{l1_id}?tab=all").data.decode()
    assert "Initial discovery call" in lead_all
    assert "Paid package" in lead_all
    assert "SAT Group 1" in lead_all

    lead_comms = c_m1.get(f"/manager/leads/{l1_id}?tab=comms").data.decode()
    assert "Initial discovery call" in lead_comms
    assert "Paid package" not in lead_comms

    stu_acad = c_m1.get(f"/manager/students/{s1_id}?tab=academic").data.decode()
    assert "SAT Group 1" in stu_acad and "Initial discovery call" not in stu_acad


def test_phase_a_schedule_multiview_conflicts_and_lesson_register():
    app = _make_isolated_app()
    _seed(app, "sup@example.com", "Supervisor", "supervisor")
    t_id = _seed(app, "teach@example.com", "Teacher A", "teacher")
    s1_id = _seed(app, "st1@example.com", "Aliya", "student", pw="StudentPw1!")

    now = utcnow()
    slot_time = now.replace(hour=14, minute=0, second=0, microsecond=0)
    with app.app_context():
        loc = Location(name="Campus North", room="305")
        course = AcademicCourse(code="ORT-X", name="ORT Math", exam="ORT")
        db.session.add_all([loc, course])
        db.session.flush()
        g1 = StudyGroup(name="Group Alpha", course_id=course.id, teacher_id=t_id, default_location_id=loc.id)
        g2 = StudyGroup(name="Group Beta", course_id=course.id, teacher_id=t_id, default_location_id=loc.id)
        db.session.add_all([g1, g2])
        db.session.flush()
        db.session.add(GroupEnrollment(group_id=g1.id, student_user_id=s1_id, course_id=course.id, status="active"))
        # Overlapping lessons sharing same teacher & room at exact same timestamp!
        l1 = Lesson(group_id=g1.id, teacher_id=t_id, starts_at=slot_time, duration_min=90, lesson_mode="offline", location_id=loc.id)
        l2 = Lesson(group_id=g2.id, teacher_id=t_id, starts_at=slot_time + timedelta(minutes=30), duration_min=60, lesson_mode="offline", location_id=loc.id)
        db.session.add_all([l1, l2])
        db.session.commit()
        l1_id = l1.id

    c_sup = app.test_client()
    _login(c_sup, "sup@example.com")

    week_param = slot_time.date().isoformat()
    for view_name in ("list", "week", "rooms", "teachers"):
        r = c_sup.get(f"/academic/schedule?view={view_name}&week={week_param}")
        assert r.status_code == 200
        body = r.data.decode()
        assert "Group Alpha" in body and "Group Beta" in body
        assert "пересечения" in body or "acad-event--conflict" in body or "Конфликт" in body

    # Enriched lesson_detail shows enrollment status & 1-click attendance pills
    reg = c_sup.get(f"/academic/lessons/{l1_id}").data.decode()
    assert "Aliya" in reg
    assert "active" in reg
    assert "att-pills" in reg


def test_crm_workspace_headers_wide_grids_csrf_and_rail_badges():
    import re
    app = _make_isolated_app()
    m1_id = _seed(app, "m1@example.com", "Mgr", "sales_manager")
    sup_id = _seed(app, "sup@example.com", "Supervisor", "supervisor")
    t_id = _seed(app, "t@example.com", "Teacher", "teacher")
    s1_id = _seed(app, "s1@example.com", "Stu", "student", pw="StudentPw1!")

    now = utcnow()
    with app.app_context():
        l1 = Lead(full_name="Unanswered Lead", phone="+996500999", assigned_manager_id=m1_id, converted_student_id=s1_id, status="new")
        db.session.add(l1)
        db.session.flush()
        db.session.add(LeadTask(lead_id=l1.id, assignee_id=m1_id, due_at=now + timedelta(hours=1), note="Call now"))
        course = AcademicCourse(code="C1", name="Course 1", exam="SAT")
        db.session.add(course)
        db.session.flush()
        grp = StudyGroup(name="G1", course_id=course.id, teacher_id=t_id)
        db.session.add(grp)
        db.session.flush()
        les = Lesson(group_id=grp.id, teacher_id=t_id, starts_at=now, lesson_mode="online")
        db.session.add(les)
        db.session.commit()
        lead_id, les_id = l1.id, les.id

    # Verify manager sees live .rail__count badges
    c_mgr = app.test_client()
    _login(c_mgr, "m1@example.com")
    dash_mgr = c_mgr.get("/manager").data.decode()
    assert 'class="rail__count"' in dash_mgr

    # Verify supervisor renders all upgraded CRM & Academic pages with body.mgr + free-standing layout (no wrapper card) + valid CSRF on every POST form
    c_sup = app.test_client()
    _login(c_sup, "sup@example.com")
    wide_routes = ("/manager", "/manager/leads", "/manager/pipeline", "/manager/finance", "/academic/schedule")
    all_routes = wide_routes + (
        "/manager/pipeline?mode=students",
        f"/manager/leads/{lead_id}",
        f"/manager/students/{s1_id}",
        "/manager/audit",
        "/manager/account",
        f"/academic/lessons/{les_id}",
    )
    for route in all_routes:
        resp = c_sup.get(route)
        assert resp.status_code == 200, f"{route} -> {resp.status_code}"
        html = resp.data.decode()
        assert '<body class="mgr"' in html, f"Missing body.mgr on {route}"
        assert 'class="crm-workspace"' not in html, f"Legacy wrapper card .crm-workspace still present on {route}"
        assert ('class="mgr-head' in html or 'class="set-hero"' in html or 'class="t-hero-bar"' in html), f"Missing page header on {route}"
        if route in wide_routes:
            assert "page--wide" in html, f"Missing .page--wide on {route}"
        for form_match in re.finditer(r'<form[^>]*method="post"[^>]*>([\s\S]*?)</form>', html, flags=re.IGNORECASE):
            assert 'name="csrf_token"' in form_match.group(1), f"Missing csrf_token in POST form on {route}"

    leads_html = c_sup.get("/manager/leads").data.decode()
    assert "t-add-card" not in leads_html
    assert "data-lead-drawer-open" in leads_html
    assert "crm-filter-grid" in leads_html
    assert "crm-drawer" in leads_html

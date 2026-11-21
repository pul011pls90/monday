"""Adversarial audit & security hardening test suite across Stage 1 auth, Manager CRM, Intake, Academic Ops, and CSP/CSRF."""
import json
import os
import re
import tempfile
from datetime import datetime, timedelta

from flask_migrate import upgrade

from config import Config
from monday.extensions import db
from monday.models import (
    AcademicCourse,
    AuditLog,
    GroupEnrollment,
    Lead,
    Lesson,
    LessonAttendance,
    Location,
    StudyGroup,
    User,
    utcnow,
)


def _make_isolated_app(csrf_enabled: bool = False, webhook_secret: str = "audit-webhook-secret-99"):
    tmp = tempfile.mkdtemp()

    class AuditConfig(Config):
        TESTING = not csrf_enabled
        WTF_CSRF_ENABLED = csrf_enabled
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SESSION_COOKIE_SECURE = False
        CRM_WEBHOOK_SECRET = webhook_secret
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "audit.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    from monday import create_app

    app = create_app(AuditConfig, seed_if_empty=False)
    with app.app_context():
        upgrade()
    return app


def _seed_user(app, email: str, name: str, role: str, password: str = "StrongStaffPw12!", must_change: bool = False) -> int:
    with app.app_context():
        u = User(
            email=email,
            name=name,
            role=role,
            is_approved=True,
            is_blocked=False,
            must_change_password=must_change,
            auth_provider="password",
        )
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return u.id


def _login(client, email: str, password: str, csrf_enabled: bool = False):
    data = {"email": email, "password": password}
    if csrf_enabled:
        html = client.get("/login").data.decode()
        tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', html).group(1)
        data["csrf_token"] = tok
    return client.post("/login", data=data)


def test_forced_password_rotation_bypass_prevention_and_api_json():
    app = _make_isolated_app(csrf_enabled=False)
    mgr_pw = "TempMgrPass123!"
    stu_pw = "TempStu123"
    _seed_user(app, "mgr.rot@example.com", "Mgr Rot", "sales_manager", mgr_pw, must_change=True)
    _seed_user(app, "stu.rot@example.com", "Stu Rot", "student", stu_pw, must_change=True)

    c_mgr = app.test_client()
    r = _login(c_mgr, "mgr.rot@example.com", mgr_pw)
    assert r.status_code == 302 and "/change-password" in r.headers["Location"]

    # Direct bypass requests across manager, academic, and profile pages must redirect to /change-password
    for path in ("/manager", "/manager/leads", "/manager/pipeline", "/manager/account", "/academic/schedule", "/profile"):
        resp = c_mgr.get(path)
        assert resp.status_code == 302, f"Expected 302 redirect on {path}, got {resp.status_code}"
        assert "/change-password" in resp.headers["Location"]

    # API / JSON endpoints must return 403 JSON instead of HTML redirect or executing action
    r_api = c_mgr.get("/api/activity/latest")
    assert r_api.status_code == 403
    assert r_api.get_json() == {"ok": False, "error": "password_change_required"}

    r_api_post = c_mgr.post("/api/course/check", json={"lesson": "x", "answer": "y"})
    assert r_api_post.status_code == 403
    assert r_api_post.get_json()["error"] == "password_change_required"

    # Allowlisted health & language switch endpoints remain usable while must_change_password=True
    assert c_mgr.get("/api/version").status_code == 200
    assert c_mgr.get("/api/site-status").status_code == 200
    r_lang = c_mgr.post("/prefs/lang", data={"lang": "en", "next": "/change-password"})
    assert r_lang.status_code == 302 and "/change-password" in r_lang.headers["Location"]
    assert "lang=en" in r_lang.headers.get("Set-Cookie", "")

    # Student with must_change_password=True is also locked out of student API & home until password changed
    c_stu = app.test_client()
    assert _login(c_stu, "stu.rot@example.com", stu_pw).status_code == 302
    assert c_stu.get("/home").status_code == 302
    assert "/change-password" in c_stu.get("/profile").headers["Location"]
    assert c_stu.get("/api/activity/latest").status_code == 403


def test_rbac_and_idor_across_roles():
    app = _make_isolated_app(csrf_enabled=False)
    m1_id = _seed_user(app, "m1@example.com", "Mgr One", "sales_manager")
    m2_id = _seed_user(app, "m2@example.com", "Mgr Two", "sales_manager")
    sup_id = _seed_user(app, "sup@example.com", "Supervisor", "supervisor")
    t1_id = _seed_user(app, "t1@example.com", "Teacher One", "teacher")
    t2_id = _seed_user(app, "t2@example.com", "Teacher Two", "teacher")
    stu_id = _seed_user(app, "st@example.com", "Student One", "student", password="StudentPassword1!")

    with app.app_context():
        l_m2 = Lead(full_name="Other Manager Lead", phone="+996700000002", assigned_manager_id=m2_id)
        db.session.add(l_m2)
        course = AcademicCourse(code="SAT1", name="SAT Prep", exam="SAT")
        db.session.add(course)
        db.session.flush()
        grp_t2 = StudyGroup(name="Group T2", course_id=course.id, teacher_id=t2_id)
        db.session.add(grp_t2)
        db.session.flush()
        les_t2 = Lesson(group_id=grp_t2.id, teacher_id=t2_id, starts_at=utcnow() + timedelta(days=1), lesson_mode="offline")
        db.session.add(les_t2)
        db.session.commit()
        l_m2_id = l_m2.id
        les_t2_id = les_t2.id

    # 1. Sales manager RBAC & IDOR checks
    c_m1 = app.test_client()
    _login(c_m1, "m1@example.com", "StrongStaffPw12!")
    for forbidden in (
        "/manager/audit",
        "/admin/",
        "/teacher/",
        f"/manager/leads/{l_m2_id}",
    ):
        assert c_m1.get(forbidden).status_code == 403, f"Expected 403 for sales_manager on {forbidden}"

    for forbidden_post in (
        f"/manager/leads/{l_m2_id}/edit",
        f"/manager/leads/{l_m2_id}/status",
        f"/manager/leads/{l_m2_id}/convert",
        f"/manager/leads/{l_m2_id}/delete",
        f"/manager/leads/{l_m2_id}/reassign",
        "/academic/locations/new",
        "/academic/courses/new",
        "/academic/groups/new",
        "/academic/lessons/new",
    ):
        assert c_m1.post(forbidden_post, data={}).status_code == 403, f"Expected 403 POST on {forbidden_post}"

    # 2. Supervisor can reach audit, pipeline, schedule, but not /admin/
    c_sup = app.test_client()
    _login(c_sup, "sup@example.com", "StrongStaffPw12!")
    assert c_sup.get("/manager/audit").status_code == 200
    assert c_sup.get("/manager/pipeline").status_code == 200
    assert c_sup.get("/academic/schedule").status_code == 200
    assert c_sup.get("/admin/").status_code == 403

    # 3. Teacher cannot access CRM or another teacher's lesson
    c_t1 = app.test_client()
    _login(c_t1, "t1@example.com", "StrongStaffPw12!")
    assert c_t1.get("/manager").status_code == 403
    assert c_t1.get("/academic/schedule").status_code == 200
    assert c_t1.get(f"/academic/lessons/{les_t2_id}").status_code == 403
    assert c_t1.post(f"/academic/lessons/{les_t2_id}/attendance", data={"student_user_id": stu_id, "status": "present"}).status_code == 403

    # 4. Student cannot access manager, academic, teacher, or admin routes
    c_stu = app.test_client()
    _login(c_stu, "st@example.com", "StudentPassword1!")
    for path in ("/manager", "/manager/leads", "/academic/schedule", "/teacher/", "/admin/"):
        assert c_stu.get(path).status_code == 403, f"Expected 403 for student on {path}"


def test_crm_intake_malformed_json_search_escaping_pagination_and_convert():
    app = _make_isolated_app(csrf_enabled=False, webhook_secret="secret-tok-123")
    _seed_user(app, "m1@example.com", "Mgr One", "sales_manager")
    sup_id = _seed_user(app, "sup@example.com", "Supervisor", "supervisor")

    c = app.test_client()
    headers = {"X-Webhook-Secret": "secret-tok-123", "Content-Type": "application/json"}

    # Non-dict JSON payloads must return 400 (never AttributeError 500)
    for bad_payload in (["a"], "just-a-string", 12345, True, None):
        r = c.post("/api/leads/webhook", data=json.dumps(bad_payload), headers=headers)
        assert r.status_code == 400, f"Payload {bad_payload!r} returned {r.status_code}"

    # Malformed public /apply must return 400 validation error and not 500 or create lead
    r_bad_apply = c.post("/apply", data={"full_name": "A", "phone": ""}, follow_redirects=True)
    assert r_bad_apply.status_code == 400

    # Create 55 leads + 1 special wildcard-containing lead to test escaping and pagination
    with app.app_context():
        leads = [Lead(full_name=f"Normal Lead {i:02d}", phone=f"+99670000{i:04d}") for i in range(55)]
        leads.append(Lead(full_name="100% Discount_Lead", phone="+996555999999"))
        db.session.add_all(leads)
        db.session.commit()
        special_id = leads[-1].id

    c_sup = app.test_client()
    _login(c_sup, "sup@example.com", "StrongStaffPw12!")

    # LIKE wildcard '%' must match ONLY the lead containing literal '%', not all 56 leads!
    r_pct = c_sup.get("/manager/leads?q=%")
    assert r_pct.status_code == 200
    body_pct = r_pct.data.decode()
    assert "100% Discount_Lead" in body_pct
    assert "Normal Lead 00" not in body_pct

    # Pagination page 1 shows 50 leads + Next button; page 2 shows remaining 6 leads; invalid query params never 500
    r_p1 = c_sup.get("/manager/leads?page=1")
    assert r_p1.status_code == 200
    assert "page=2" in r_p1.data.decode()
    r_p2 = c_sup.get("/manager/leads?page=2")
    assert r_p2.status_code == 200
    assert "Normal Lead" in r_p2.data.decode() or "100% Discount_Lead" in r_p2.data.decode()
    assert c_sup.get("/manager/leads?page=-999&date_from=not-a-date&date_to=bad&manager=abc").status_code == 200

    # Convert lead with bogus exam=HACKED stores exam=None, forces password change, and writes audit log
    r_conv = c_sup.post(
        f"/manager/leads/{special_id}/convert",
        data={"convert_mode": "create", "student_email": "converted.student@example.com", "exam": "HACKED"},
    )
    assert r_conv.status_code == 200
    assert "no-store" in r_conv.headers.get("Cache-Control", "")
    assert "Временный пароль:" in r_conv.data.decode()

    with app.app_context():
        stu = User.query.filter_by(email="converted.student@example.com").first()
        assert stu is not None
        assert stu.must_change_password is True
        assert stu.profile.exam is None
        al = AuditLog.query.filter_by(action="lead_convert", entity_type="lead", entity_id=special_id).first()
        assert al is not None


def test_academic_ops_validation_xss_and_attendance_constraints():
    app = _make_isolated_app(csrf_enabled=False)
    _seed_user(app, "sup@example.com", "Supervisor", "supervisor")
    t_id = _seed_user(app, "teach@example.com", "Teacher A", "teacher")
    s1_id = _seed_user(app, "s1@example.com", "Enrolled Student", "student", password="StudentPassword1!")
    s2_id = _seed_user(app, "s2@example.com", "Outsider Student", "student", password="StudentPassword1!")

    with app.app_context():
        loc = Location(name="Main Campus", room="101")
        course = AcademicCourse(code="ORT-MATH", name="ORT Math", exam="ORT")
        db.session.add_all([loc, course])
        db.session.commit()
        course_id = course.id

    c_sup = app.test_client()
    _login(c_sup, "sup@example.com", "StrongStaffPw12!")

    # Invalid default_location_id must sanitize to None without FK 500
    r_grp = c_sup.post(
        "/academic/groups/new",
        data={"name": "ORT Group A", "course_id": course_id, "teacher_id": t_id, "default_location_id": "999999"},
    )
    assert r_grp.status_code == 302
    with app.app_context():
        grp = StudyGroup.query.filter_by(name="ORT Group A").first()
        assert grp is not None and grp.default_location_id is None
        grp_id = grp.id

    # XSS javascript: and data: meeting_url schemes must be rejected cleanly
    for evil_url in ("javascript:alert(document.cookie)", "data:text/html,<script>alert(1)</script>"):
        r_xss = c_sup.post(
            "/academic/lessons/new",
            data={"group_id": grp_id, "starts_at": "2030-05-01T15:00", "lesson_mode": "online", "meeting_url": evil_url},
        )
        assert r_xss.status_code == 302
    with app.app_context():
        assert Lesson.query.count() == 0

    # Valid https:// meeting_url & invalid location_id/teacher_id fallback succeed cleanly
    r_ok = c_sup.post(
        "/academic/lessons/new",
        data={
            "group_id": grp_id,
            "starts_at": "2030-05-01T15:00",
            "lesson_mode": "online",
            "meeting_url": "https://meet.google.com/abc-defg-hij",
            "location_id": "999999",
            "teacher_id": "999999",
        },
    )
    assert r_ok.status_code == 302
    with app.app_context():
        les = Lesson.query.first()
        assert les is not None and les.teacher_id == t_id and les.meeting_url.startswith("https://")
        les_id = les.id

    # Schedule page renders safely and never renders unsafe href
    sched_html = c_sup.get("/academic/schedule?date_from=bad&date_to=bad").data.decode()
    assert "javascript:" not in sched_html
    assert "https://meet.google.com/abc-defg-hij" in sched_html

    # Marking attendance for an UNENROLLED student (s2) must abort 400!
    r_outsider = c_sup.post(f"/academic/lessons/{les_id}/attendance", data={"student_user_id": s2_id, "status": "present"})
    assert r_outsider.status_code == 400

    # Enroll s1, verify duplicate enroll does not duplicate active GroupEnrollment, then mark attendance for s1
    assert c_sup.post(f"/academic/groups/{grp_id}/enroll", data={"student_user_id": s1_id}).status_code == 302
    assert c_sup.post(f"/academic/groups/{grp_id}/enroll", data={"student_user_id": s1_id}).status_code == 302
    with app.app_context():
        assert GroupEnrollment.query.filter_by(group_id=grp_id, student_user_id=s1_id, left_at=None).count() == 1
        enr_id = GroupEnrollment.query.filter_by(group_id=grp_id, student_user_id=s1_id, left_at=None).first().id

    assert c_sup.post(f"/academic/lessons/{les_id}/attendance", data={"student_user_id": s1_id, "status": "present"}).status_code == 302
    with app.app_context():
        assert LessonAttendance.query.filter_by(lesson_id=les_id, student_user_id=s1_id).count() == 1

    # Close enrollment -> sets left_at + writes audit log
    assert c_sup.post(f"/academic/enrollments/{enr_id}/close", data={"status": "completed", "reason": "Finished"}).status_code == 302
    with app.app_context():
        enr = db.session.get(GroupEnrollment, enr_id)
        assert enr.left_at is not None and enr.status == "completed"
        assert AuditLog.query.filter_by(action="enrollment_close", entity_id=enr_id).first() is not None


def test_csrf_no_store_csp_and_empty_template_safety():
    app = _make_isolated_app(csrf_enabled=True)
    _seed_user(app, "sup@example.com", "Supervisor", "supervisor")

    c = app.test_client()
    # Auth pages set Cache-Control: no-store to prevent bfcache CSRF token reuse
    for auth_path in ("/login", "/register"):
        r = c.get(auth_path)
        assert r.status_code == 200
        assert "no-store" in r.headers.get("Cache-Control", "")
        csp = r.headers.get("Content-Security-Policy", "")
        assert "https://www.desmos.com" in csp
        assert "font-src 'self' data: https://www.desmos.com" in csp
        assert "https://www.youtube.com" in csp and "https://www.youtube-nocookie.com" in csp
        assert "https://accounts.google.com" in csp

    # Missing CSRF token returns friendly 400 HTML page (not 500) and JSON 400 on /api/*
    r_no_csrf = c.post("/login", data={"email": "sup@example.com", "password": "StrongStaffPw12!"})
    assert r_no_csrf.status_code == 400
    assert "CSRF" in r_no_csrf.data.decode()

    r_api_no_csrf = c.post("/api/course/check", json={"a": 1})
    assert r_api_no_csrf.status_code == 400
    assert r_api_no_csrf.get_json() == {"ok": False, "error": "csrf_error"}

    # Sign in properly and check all Manager & Academic templates render cleanly on completely empty DB
    assert _login(c, "sup@example.com", "StrongStaffPw12!", csrf_enabled=True).status_code == 302
    for route in ("/manager", "/manager/leads", "/manager/pipeline", "/manager/audit", "/manager/account", "/academic/schedule"):
        res = c.get(route)
        assert res.status_code == 200, f"Empty DB template error on {route}: {res.status_code}"

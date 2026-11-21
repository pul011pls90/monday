"""Stage 6 (Academic Operations) + Stage 7 (QA) + Stage 8 (Security headers/CSP on new pages) tests."""
from datetime import timedelta

from monday.extensions import db
from monday.models import (
    AcademicCourse,
    AuditLog,
    GroupEnrollment,
    Lesson,
    LessonAttendance,
    Location,
    StudyGroup,
    User,
    utcnow,
)
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


def test_stage6_academic_lifecycle_online_offline_attendance_retro_audit_and_rbac():
    _mk_user("s6.mgr@example.com", "S6 Manager", "sales_manager")
    sup_id = _mk_user("s6.sup@example.com", "S6 Supervisor", "supervisor")
    _mk_user("s6.ast@example.com", "S6 Assistant", "assistant")

    c_sup = login(client(), "s6.sup@example.com", "Pass12345")
    c_mgr = login(client(), "s6.mgr@example.com", "Pass12345")
    c_tch = login(client(), "aibek@monday.kg", "teacher123")
    c_tch2 = login(client(), "nurai@monday.kg", "teacher123")
    c_stu = login(client(), "student@monday.kg", "student123")
    c_ast = login(client(), "s6.ast@example.com", "Pass12345")

    with APP.app_context():
        aibek_id = User.query.filter_by(email="aibek@monday.kg").first().id
        stu_id = User.query.filter_by(email="student@monday.kg").first().id

    # 1. Student & Content Assistant blocked from schedule (403); Sales Manager cannot mutate (403)
    assert c_stu.get("/academic/schedule").status_code == 403
    assert c_ast.get("/academic/schedule").status_code == 403
    assert c_mgr.post("/academic/locations/new", data={"name": "Blocked Loc"}).status_code == 403
    assert c_tch.post("/academic/courses/new", data={"code": "BLK", "name": "Blocked"}).status_code == 403

    # 2. Supervisor creates Location, AcademicCourse, StudyGroup, and enrolls Student (many-to-many with history)
    assert c_sup.post("/academic/locations/new", data={"name": "Bishkek Center", "address": "Chuy 100", "room": "204"}).status_code == 302
    assert c_sup.post("/academic/courses/new", data={"code": "SAT-S6", "name": "SAT Math Intensive", "exam": "SAT"}).status_code == 302
    with APP.app_context():
        loc = Location.query.filter_by(name="Bishkek Center").first()
        course = AcademicCourse.query.filter_by(code="SAT-S6").first()
        assert loc is not None and course is not None
        loc_id, course_id = loc.id, course.id

    assert c_sup.post("/academic/groups/new", data={
        "name": "SAT-Morning-A",
        "course_id": str(course_id),
        "teacher_id": str(aibek_id),
        "default_location_id": str(loc_id),
    }).status_code == 302
    with APP.app_context():
        grp = StudyGroup.query.filter_by(name="SAT-Morning-A").first()
        assert grp is not None and grp.teacher_id == aibek_id
        grp_id = grp.id

    assert c_sup.post(f"/academic/groups/{grp_id}/enroll", data={"student_user_id": str(stu_id)}).status_code == 302
    with APP.app_context():
        enr = GroupEnrollment.query.filter_by(group_id=grp_id, student_user_id=stu_id, left_at=None).first()
        assert enr is not None and enr.course_id == course_id
        enr_id = enr.id

    # 3. Create 1 Offline lesson (location_id) & 1 Online lesson (meeting_url) -> lesson_mode lives on Lesson
    recent_dt = (utcnow() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    old_dt = (utcnow() - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")

    assert c_sup.post("/academic/lessons/new", data={
        "group_id": str(grp_id),
        "starts_at": recent_dt,
        "lesson_mode": "offline",
        "location_id": str(loc_id),
        "topic": "Linear Functions",
    }).status_code == 302
    assert c_sup.post("/academic/lessons/new", data={
        "group_id": str(grp_id),
        "starts_at": old_dt,
        "lesson_mode": "online",
        "meeting_url": "https://meet.google.com/abc-defg-hij",
        "topic": "Quadratics Online",
    }).status_code == 302

    with APP.app_context():
        l_off = Lesson.query.filter_by(group_id=grp_id, lesson_mode="offline").first()
        l_on = Lesson.query.filter_by(group_id=grp_id, lesson_mode="online").first()
        assert l_off is not None and l_off.location_id == loc_id and l_off.meeting_url == ""
        assert l_on is not None and l_on.location_id is None and "meet.google.com" in l_on.meeting_url
        l_off_id, l_on_id = l_off.id, l_on.id

    # 4. Online/Offline schedule filtering works; Manager has READ-ONLY access (GET 200, POST attendance 403)
    sched_on = c_mgr.get("/academic/schedule?lesson_mode=online").data.decode()
    assert "Quadratics Online" in sched_on and "Linear Functions" not in sched_on
    sched_off = c_mgr.get("/academic/schedule?lesson_mode=offline").data.decode()
    assert "Linear Functions" in sched_off and "Quadratics Online" not in sched_off

    assert c_mgr.get(f"/academic/lessons/{l_off_id}").status_code == 200
    assert c_mgr.post(f"/academic/lessons/{l_off_id}/attendance", data={
        "student_user_id": str(stu_id), "status": "present",
    }).status_code == 403

    # 5. Assigned teacher marks attendance; unrelated teacher gets 403
    assert c_tch2.get(f"/academic/lessons/{l_off_id}").status_code == 403
    assert c_tch2.post(f"/academic/lessons/{l_off_id}/attendance", data={
        "student_user_id": str(stu_id), "status": "present",
    }).status_code == 403

    assert c_tch.post(f"/academic/lessons/{l_off_id}/attendance", data={
        "student_user_id": str(stu_id), "status": "late", "note": "5 min late",
    }).status_code == 302
    with APP.app_context():
        att = LessonAttendance.query.filter_by(lesson_id=l_off_id, student_user_id=stu_id).first()
        assert att is not None and att.status == "late" and att.note == "5 min late"

    # 6. Retroactive edit (>24h old lesson): initial mark OK, then teacher editing retroactively -> 403;
    #    Supervisor editing retroactively writes AuditLog(action='attendance_retro_edit')!
    assert c_sup.post(f"/academic/lessons/{l_on_id}/attendance", data={
        "student_user_id": str(stu_id), "status": "absent",
    }).status_code == 302
    assert c_tch.post(f"/academic/lessons/{l_on_id}/attendance", data={
        "student_user_id": str(stu_id), "status": "excused", "reason": "Doctor note",
    }).status_code == 403

    assert c_sup.post(f"/academic/lessons/{l_on_id}/attendance", data={
        "student_user_id": str(stu_id), "status": "excused", "note": "Medical certificate", "reason": "Parent sent note",
    }).status_code == 302
    with APP.app_context():
        att_on = LessonAttendance.query.filter_by(lesson_id=l_on_id, student_user_id=stu_id).first()
        assert att_on.status == "excused"
        al = AuditLog.query.filter_by(action="attendance_retro_edit", entity_type="lesson_attendance", entity_id=att_on.id).first()
        assert al is not None and al.actor_id == sup_id
        assert al.old_value["status"] == "absent" and al.new_value["status"] == "excused"
        assert al.reason == "Parent sent note"

    # 7. Closing enrollment preserves history (`left_at` set, row NOT deleted) + writes AuditLog
    assert c_sup.post(f"/academic/enrollments/{enr_id}/close", data={"status": "transferred", "reason": "Moved to evening"}).status_code == 302
    with APP.app_context():
        enr_closed = db.session.get(GroupEnrollment, enr_id)
        assert enr_closed is not None and enr_closed.left_at is not None and enr_closed.status == "transferred"
        assert AuditLog.query.filter_by(action="enrollment_close", entity_type="group_enrollment", entity_id=enr_id).count() == 1


def test_stage8_security_headers_and_csp_valid_on_all_new_pages():
    _mk_user("s8.sup@example.com", "S8 Supervisor", "supervisor")
    c_sup = login(client(), "s8.sup@example.com", "Pass12345")
    anon = client()

    for c_obj, path in [
        (anon, "/apply"),
        (c_sup, "/manager"),
        (c_sup, "/manager/leads"),
        (c_sup, "/manager/pipeline"),
        (c_sup, "/manager/audit"),
        (c_sup, "/manager/account"),
        (c_sup, "/academic/schedule"),
    ]:
        r = c_obj.get(path)
        assert r.status_code == 200, f"{path} returned {r.status_code}"
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        csp = r.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp and "object-src 'none'" in csp

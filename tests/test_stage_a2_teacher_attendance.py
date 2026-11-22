"""QA & RBAC tests for Stage A2 Teacher attendance marking & Manager live propagation."""
import secrets
from datetime import timedelta

from monday.extensions import db
from monday.models import (
    AcademicCourse,
    AuditLog,
    GroupEnrollment,
    Lesson,
    LessonAttendance,
    LessonPassUsage,
    MembershipPlan,
    StudentPass,
    StudentProfile,
    StudyGroup,
    User,
    utcnow,
)
from test_app import APP, client, login


def _mk_user(email: str, name: str, role: str, password: str) -> int:
    with APP.app_context():
        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(email=email, name=name, role=role, is_approved=True, auth_provider="password")
            db.session.add(u)
        else:
            u.name = name
            u.role = role
            u.is_approved = True
            u.is_blocked = False
            u.auth_provider = "password"
        u.set_password(password)
        db.session.flush()
        if role == "student" and not StudentProfile.query.filter_by(user_id=u.id).first():
            db.session.add(
                StudentProfile(
                    user_id=u.id,
                    exam="SAT",
                    onboarded=True,
                )
            )
        db.session.commit()
        return u.id


def test_teacher_attendance_batch_idor_audit_pass_idempotency_and_manager_live_counts():
    pw_map = {role: secrets.token_urlsafe(12) for role in ("t1", "t2", "sup", "mgr", "adm", "s1", "s2", "s3")}
    t1_id = _mk_user("a2.teacher1@example.com", "A2 Teacher One", "teacher", pw_map["t1"])
    _mk_user("a2.teacher2@example.com", "A2 Teacher Two", "teacher", pw_map["t2"])
    sup_id = _mk_user("a2.sup@example.com", "A2 Supervisor", "supervisor", pw_map["sup"])
    _mk_user("a2.mgr@example.com", "A2 Manager", "sales_manager", pw_map["mgr"])
    _mk_user("a2.adm@example.com", "A2 Admin", "admin", pw_map["adm"])
    s1_id = _mk_user("a2.stu1@example.com", "Student One A2", "student", pw_map["s1"])
    s2_id = _mk_user("a2.stu2@example.com", "Student Two A2", "student", pw_map["s2"])
    s3_id = _mk_user("a2.stu3@example.com", "Student Three A2", "student", pw_map["s3"])

    with APP.app_context():
        course = AcademicCourse(code="A2-SAT", name="A2 SAT Prep", exam="SAT", is_active=True)
        db.session.add(course)
        db.session.flush()

        grp = StudyGroup(
            name="A2 Group Alpha",
            course_id=course.id,
            teacher_id=t1_id,
            is_active=True,
        )
        db.session.add(grp)
        db.session.flush()

        for sid in (s1_id, s2_id, s3_id):
            db.session.add(
                GroupEnrollment(
                    group_id=grp.id,
                    student_user_id=sid,
                    course_id=course.id,
                    status="active",
                )
            )

        plan = MembershipPlan(
            name="A2 8-Lesson Plan",
            course_id=course.id,
            total_lessons=8,
            duration_days=30,
            price_amount=8000,
        )
        db.session.add(plan)
        db.session.flush()

        s1_pass = StudentPass(
            student_user_id=s1_id,
            plan_id=plan.id,
            status="active",
            lessons_total=8,
            lessons_remaining=8,
            agreed_price=8000,
            paid_amount=8000,
            created_by_id=sup_id,
        )
        db.session.add(s1_pass)

        lesson = Lesson(
            group_id=grp.id,
            teacher_id=t1_id,
            lesson_mode="online",
            meeting_url="https://meet.example.com/a2-alpha",
            starts_at=utcnow() - timedelta(minutes=20),
            duration_min=90,
            topic="Algebra Practice",
        )
        db.session.add(lesson)
        db.session.commit()
        lesson_id = lesson.id
        s1_pass_id = s1_pass.id

    c_t1 = login(client(), "a2.teacher1@example.com", pw_map["t1"])
    c_t2 = login(client(), "a2.teacher2@example.com", pw_map["t2"])
    c_mgr = login(client(), "a2.mgr@example.com", pw_map["mgr"])
    c_sup = login(client(), "a2.sup@example.com", pw_map["sup"])
    c_adm = login(client(), "a2.adm@example.com", pw_map["adm"])
    c_s1 = login(client(), "a2.stu1@example.com", pw_map["s1"])

    # 1. Assigned teacher sees group lesson on Teacher dashboard + /teacher/lessons redirects cleanly
    dash_html = c_t1.get("/teacher/").data.decode()
    assert "A2 Group Alpha" in dash_html
    assert f"/academic/lessons/{lesson_id}" in dash_html
    assert c_t1.get("/teacher/lessons").status_code == 302

    # 2. Unassigned teacher B cannot view or mutate Teacher A's lesson (403 IDOR)
    assert c_t2.get(f"/academic/lessons/{lesson_id}").status_code == 403
    assert (
        c_t2.post(
            f"/academic/lessons/{lesson_id}/attendance",
            data={"batch": "1", f"status_{s1_id}": "present"},
        ).status_code
        == 403
    )
    t2_sched = c_t2.get("/academic/schedule").data.decode()
    assert "A2 Group Alpha" not in t2_sched

    # 3. Student is blocked from schedule & lesson attendance routes
    assert c_s1.get("/academic/schedule").status_code == 403
    assert c_s1.get(f"/academic/lessons/{lesson_id}").status_code == 403
    assert (
        c_s1.post(
            f"/academic/lessons/{lesson_id}/attendance",
            data={"student_user_id": str(s1_id), "status": "present"},
        ).status_code
        == 403
    )

    # 4. Assigned teacher batch-marks s1=present, s2=absent, s3=present
    r_batch = c_t1.post(
        f"/academic/lessons/{lesson_id}/attendance",
        data={
            "batch": "1",
            f"status_{s1_id}": "present",
            f"note_{s1_id}": "Answered warmly",
            f"status_{s2_id}": "absent",
            f"note_{s2_id}": "Sick",
            f"status_{s3_id}": "present",
        },
    )
    assert r_batch.status_code == 302

    with APP.app_context():
        rows = {
            r.student_user_id: r
            for r in LessonAttendance.query.filter_by(lesson_id=lesson_id).all()
        }
        assert len(rows) == 3
        assert rows[s1_id].status == "present" and rows[s1_id].note == "Answered warmly"
        assert rows[s2_id].status == "absent" and rows[s2_id].note == "Sick"
        assert rows[s3_id].status == "present"

        logs = AuditLog.query.filter_by(action="attendance_mark", entity_type="lesson_attendance").all()
        logged_students = {l.new_value.get("student_id") for l in logs if isinstance(l.new_value, dict)}
        assert {s1_id, s2_id, s3_id}.issubset(logged_students)

        # Pass usage deducted exactly once
        sp = db.session.get(StudentPass, s1_pass_id)
        assert sp.lessons_remaining == 7
        assert LessonPassUsage.query.filter_by(lesson_id=lesson_id, student_user_id=s1_id).count() == 1

    # 5. Re-saving same status (batch and single) never double-deducts pass credits
    assert (
        c_t1.post(
            f"/academic/lessons/{lesson_id}/attendance",
            data={"batch": "1", f"status_{s1_id}": "present", f"note_{s1_id}": "Updated note"},
        ).status_code
        == 302
    )
    assert (
        c_t1.post(
            f"/academic/lessons/{lesson_id}/attendance",
            data={"student_user_id": str(s1_id), "status": "present", "note": "Updated note"},
        ).status_code
        == 302
    )
    with APP.app_context():
        sp = db.session.get(StudentPass, s1_pass_id)
        assert sp.lessons_remaining == 7
        assert LessonPassUsage.query.filter_by(lesson_id=lesson_id, student_user_id=s1_id).count() == 1

    # 6. Sales Manager & Supervisor see live updated counts & statuses read-only, and Sales Manager gets 403 on POST
    mgr_sched = c_mgr.get("/academic/schedule?view=list").data.decode()
    assert "3/3" in mgr_sched
    mgr_lesson = c_mgr.get(f"/academic/lessons/{lesson_id}").data.decode()
    assert "Присутствовал" in mgr_lesson
    assert "Отсутствовал" in mgr_lesson
    assert "Учитель: A2 Teacher One" in mgr_lesson
    sup_pipe = c_sup.get("/manager/pipeline?mode=students").data.decode()
    assert "Student One A2" in sup_pipe
    assert "Student Two A2" in sup_pipe
    assert "Присутствовал" in sup_pipe
    assert "Отсутствовал" in sup_pipe
    assert (
        c_mgr.post(
            f"/academic/lessons/{lesson_id}/attendance",
            data={"batch": "1", f"status_{s2_id}": "present"},
        ).status_code
        == 403
    )

    # 7. Supervisor and Admin can also mark attendance cleanly
    assert (
        c_sup.post(
            f"/academic/lessons/{lesson_id}/attendance",
            data={"student_user_id": str(s2_id), "status": "excused", "note": "Called ahead"},
        ).status_code
        == 302
    )
    assert (
        c_adm.post(
            f"/academic/lessons/{lesson_id}/attendance",
            data={"student_user_id": str(s2_id), "status": "late", "note": "Joined at +15m"},
        ).status_code
        == 302
    )

    # 8. CSRF enabled rejects POST without csrf_token with 400
    prev_csrf = APP.config.get("WTF_CSRF_ENABLED", False)
    APP.config["WTF_CSRF_ENABLED"] = True
    try:
        r_no_csrf = c_t1.post(
            f"/academic/lessons/{lesson_id}/attendance",
            data={"batch": "1", f"status_{s1_id}": "present"},
        )
        assert r_no_csrf.status_code == 400
    finally:
        APP.config["WTF_CSRF_ENABLED"] = prev_csrf

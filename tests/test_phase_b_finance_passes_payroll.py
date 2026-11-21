"""Phase B Finance, Passes, Atomic Attendance Credit Deduction & Teacher Payroll tests."""
import os
import tempfile
from datetime import timedelta

from flask_migrate import upgrade

from config import Config
from monday.extensions import db
from monday.models import (
    AcademicCourse,
    AuditLog,
    GroupEnrollment,
    Lead,
    Lesson,
    LessonPassUsage,
    MembershipPlan,
    PaymentTransaction,
    StudentPass,
    StudyGroup,
    TeacherPayRate,
    User,
    utcnow,
)


def _make_isolated_app():
    tmp = tempfile.mkdtemp()

    class PhaseBConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "phase_b.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    from monday import create_app

    app = create_app(PhaseBConfig, seed_if_empty=False)
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


def test_phase_b_pass_issuance_atomic_attendance_deduction_retro_restore_and_payments():
    app = _make_isolated_app()
    m1_id = _seed(app, "m1@example.com", "Mgr 1", "sales_manager")
    m2_id = _seed(app, "m2@example.com", "Mgr 2", "sales_manager")
    sup_id = _seed(app, "sup@example.com", "Supervisor", "supervisor")
    t_id = _seed(app, "teach@example.com", "Teacher A", "teacher")
    s1_id = _seed(app, "s1@example.com", "Student Alpha", "student", pw="StudentPw1!")
    s2_id = _seed(app, "s2@example.com", "Student Beta", "student", pw="StudentPw1!")

    now = utcnow()
    with app.app_context():
        db.session.add_all([
            Lead(full_name="Lead Alpha", phone="+996555001", assigned_manager_id=m1_id, converted_student_id=s1_id, status="won"),
            Lead(full_name="Lead Beta", phone="+996555002", assigned_manager_id=m2_id, converted_student_id=s2_id, status="won"),
        ])
        course = AcademicCourse(code="SAT-FIN", name="SAT Intensive", exam="SAT")
        db.session.add(course)
        db.session.flush()
        grp = StudyGroup(name="SAT Group", course_id=course.id, teacher_id=t_id)
        db.session.add(grp)
        db.session.flush()
        db.session.add(GroupEnrollment(group_id=grp.id, student_user_id=s1_id, course_id=course.id, status="active"))
        l1 = Lesson(group_id=grp.id, teacher_id=t_id, starts_at=now - timedelta(hours=2), lesson_mode="offline")
        l2 = Lesson(group_id=grp.id, teacher_id=t_id, starts_at=now - timedelta(days=10), lesson_mode="offline")
        db.session.add_all([l1, l2])
        db.session.commit()
        course_id, l1_id, l2_id = course.id, l1.id, l2.id

    c_sup = app.test_client()
    _login(c_sup, "sup@example.com")
    c_m1 = app.test_client()
    _login(c_m1, "m1@example.com")
    c_tch = app.test_client()
    _login(c_tch, "teach@example.com")

    # 1. Sales manager cannot create plans or payroll rates (403); Supervisor can
    assert c_m1.post("/manager/plans/new", data={"name": "Blocked Plan", "price_amount": "1000"}).status_code == 403
    assert c_sup.post(
        "/manager/plans/new",
        data={"name": "SAT 2-Lesson Pack", "course_id": str(course_id), "total_lessons": "2", "duration_days": "30", "price_amount": "5000"},
    ).status_code == 302
    with app.app_context():
        plan = MembershipPlan.query.filter_by(name="SAT 2-Lesson Pack").first()
        assert plan is not None
        plan_id = plan.id

    # 2. Manager 1 issues pass for s1 (their lead) with partial prepayment 3000 -> debt = 2000; blocked on s2 (403 IDOR)
    assert c_m1.post(f"/manager/students/{s2_id}/passes/new", data={"plan_id": str(plan_id)}).status_code == 403
    r_issue = c_m1.post(
        f"/manager/students/{s1_id}/passes/new",
        data={"plan_id": str(plan_id), "initial_payment": "3000", "method": "mbank", "note": "First installment"},
    )
    assert r_issue.status_code == 302
    with app.app_context():
        sp = StudentPass.query.filter_by(student_user_id=s1_id).first()
        assert sp is not None and sp.lessons_remaining == 2 and sp.paid_amount == 3000 and sp.debt_amount == 2000
        sp_id = sp.id

    # 3. Teacher marks s1 present twice on l1 -> idempotent! Only 1 LessonPassUsage & remaining == 1
    assert c_tch.post(f"/academic/lessons/{l1_id}/attendance", data={"student_user_id": str(s1_id), "status": "present"}).status_code == 302
    assert c_tch.post(f"/academic/lessons/{l1_id}/attendance", data={"student_user_id": str(s1_id), "status": "late", "note": "updated"}).status_code == 302
    with app.app_context():
        sp = db.session.get(StudentPass, sp_id)
        assert sp.lessons_remaining == 1 and sp.status == "active"
        assert LessonPassUsage.query.filter_by(lesson_id=l1_id, student_user_id=s1_id).count() == 1

    # Marking s1 present on old lesson l2 consumes last lesson -> status='depleted'; then supervisor retro-reverses to excused -> restores to active & 1 remaining!
    assert c_sup.post(f"/academic/lessons/{l2_id}/attendance", data={"student_user_id": str(s1_id), "status": "present"}).status_code == 302
    with app.app_context():
        sp = db.session.get(StudentPass, sp_id)
        assert sp.lessons_remaining == 0 and sp.status == "depleted"

    assert c_sup.post(
        f"/academic/lessons/{l2_id}/attendance",
        data={"student_user_id": str(s1_id), "status": "excused", "reason": "Medical exemption"},
    ).status_code == 302
    with app.app_context():
        sp = db.session.get(StudentPass, sp_id)
        assert sp.lessons_remaining == 1 and sp.status == "active"

    # 4. Payments & refunds: M1 pays remaining 2000; M1 cannot issue refund (403); Supervisor cannot refund > paid_amount; valid refund 500 works & logs audit
    assert c_m1.post(f"/manager/students/{s1_id}/payments/new", data={"pass_id": str(sp_id), "amount": "2000", "method": "cash", "kind": "payment"}).status_code == 302
    assert c_m1.post(f"/manager/students/{s1_id}/payments/new", data={"pass_id": str(sp_id), "amount": "500", "method": "cash", "kind": "refund"}).status_code == 403
    c_sup.post(f"/manager/students/{s1_id}/payments/new", data={"pass_id": str(sp_id), "amount": "99999", "method": "cash", "kind": "refund"})
    c_sup.post(f"/manager/students/{s1_id}/payments/new", data={"pass_id": str(sp_id), "amount": "500", "method": "cash", "kind": "refund", "note": "Partial refund"})
    with app.app_context():
        sp = db.session.get(StudentPass, sp_id)
        assert sp.paid_amount == 4500 and sp.debt_amount == 500
        assert AuditLog.query.filter_by(action="payment_refund").count() == 1

    # 5. Teacher Payroll RBAC & Accrual on /manager/finance and /academic/schedule?view=teachers
    assert c_m1.post("/manager/payroll/rates/new", data={"teacher_id": str(t_id), "rate_type": "per_lesson", "rate_amount": "1500"}).status_code == 403
    assert c_sup.post("/manager/payroll/rates/new", data={"teacher_id": str(t_id), "rate_type": "per_lesson", "rate_amount": "1500"}).status_code == 302

    fin_sup = c_sup.get("/manager/finance").data.decode()
    assert "4500" in fin_sup and "3000 KGS" in fin_sup  # 2 lessons * 1500 KGS = 3000 KGS
    fin_mgr = c_m1.get("/manager/finance").data.decode()
    assert "Начисления учителям" not in fin_mgr  # payroll hidden from sales manager

    sched_sup = c_sup.get(f"/academic/schedule?view=teachers&week={now.date().isoformat()}").data.decode()
    assert "1500 KGS" in sched_sup  # l1 is in this week -> 1500 KGS
    sched_tch = c_tch.get(f"/academic/schedule?view=teachers&week={now.date().isoformat()}").data.decode()
    assert "1500 KGS" not in sched_tch  # teacher does NOT see payroll accruals

    # 6. Student 360 & lesson register show live pass balance
    reg = c_sup.get(f"/academic/lessons/{l1_id}").data.decode()
    assert "1/2" in reg and "Долг" in reg and "500" in reg
    s360 = c_m1.get(f"/manager/students/{s1_id}?tab=finance").data.decode()
    assert "Partial refund" in s360 and "SAT 2-Lesson Pack" in s360

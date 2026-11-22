"""Stage 5 QA suite: End-to-end tests for Stages 2, 3, and 4 (Manager UI, Student Claim Flow, Teacher/Student Visibility)."""
from __future__ import annotations

import json
import threading
from datetime import timedelta

import pytest

from config import Config
from monday import create_app
from monday.extensions import db
from monday.models import (
    AcademicCourse,
    Assignment,
    Attempt,
    AttemptAnswer,
    AuditLog,
    Lead,
    LeadActivity,
    PaymentTransaction,
    Skill,
    StudentPass,
    StudentProfile,
    StudentRecord,
    TeacherAssignment,
    User,
    Work,
    WorkVersion,
    utcnow,
)
from monday.student_links import claim_code


def _build_qa_app(tmp_path, *, ratelimit=False):
    class QaCfg(Config):
        TESTING = True
        SECRET_KEY = "qa-stage5-secret"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'qa.db'}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SQLALCHEMY_ENGINE_OPTIONS = {}
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = ratelimit
        RATELIMIT_STORAGE_URI = "memory://"
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        INVITE_CODE_TTL_DAYS = 14
        NEW_TEACHER_SEES_EARLIER_PROGRESS = False
        SEED_DEMO = True
        IMPORT_PACKS = False

    app = create_app(QaCfg, seed_if_empty=True)
    with app.app_context():
        users = {}
        specs = [
            ("qa.mgr@monday.kg", "Manager QA", "sales_manager", True),
            ("qa.sup@monday.kg", "Supervisor QA", "supervisor", True),
            ("qa.adm@monday.kg", "Admin QA", "admin", True),
            ("qa.t1@monday.kg", "Преподаватель Первый", "teacher", True),
            ("qa.t2@monday.kg", "Преподаватель Второй", "teacher", True),
            ("qa.asst@monday.kg", "Assistant QA", "assistant", True),
            ("qa.stu1@monday.kg", "Айдана Тест", "student", True),
            ("qa.stu2@monday.kg", "Бектур Беков", "student", True),
        ]
        for email, name, role, approved in specs:
            u = User.query.filter_by(email=email).first()
            if not u:
                u = User(email=email, name=name, role=role, is_approved=approved)
                u.set_password("StrongPass123!")
                if role == "student":
                    u.profile = StudentProfile(exam="SAT", grade="11", onboarded=True)
                db.session.add(u)
        if not AcademicCourse.query.filter_by(code="QA_SAT").first():
            db.session.add(AcademicCourse(code="QA_SAT", name="SAT Prep", exam="SAT", is_active=True))
        db.session.commit()
    return app


def _login(client, email, password="StrongPass123!"):
    r = client.post("/login", data={"email": email, "password": password}, follow_redirects=False)
    assert r.status_code in (200, 302)
    return client


def test_stage2_rbac_manager_ui_lead_convert_idempotency_and_history(tmp_path):
    app = _build_qa_app(tmp_path)
    with app.app_context():
        t1 = User.query.filter_by(email="qa.t1@monday.kg").one()
        t2 = User.query.filter_by(email="qa.t2@monday.kg").one()
        mgr = User.query.filter_by(email="qa.mgr@monday.kg").one()
        course = AcademicCourse.query.filter_by(code="QA_SAT").one()
        lead = Lead(
            full_name="Айдана Асанова",
            phone="+996555998877",
            source="whatsapp",
            status="negotiation",
            assigned_manager_id=mgr.id,
        )
        db.session.add(lead)
        db.session.commit()
        t1_id, t2_id, course_id, lead_id = t1.id, t2.id, course.id, lead.id

    # 1. Manager creates student via "Новый ученик"
    c_mgr = _login(app.test_client(), "qa.mgr@monday.kg")
    r_new = c_mgr.post(
        "/manager/students/new",
        data={
            "name": "Нурлан Садыков",
            "phone": "+996700112233",
            "email": "nurlan@example.com",
            "teacher_id": str(t1_id),
            "course_id": str(course_id),
        },
    )
    assert r_new.status_code == 200
    assert "no-store" in r_new.headers.get("Cache-Control", "")
    html_new = r_new.data.decode("utf-8")
    assert "MND-" in html_new
    assert "/join/MND-" in html_new
    assert "WhatsApp" in html_new
    assert "Действует до" in html_new

    with app.app_context():
        rec = StudentRecord.query.filter_by(name="Нурлан Садыков").one()
        rec_id = rec.id
        code_first = rec.invite_code
        assert rec.code_status_label == "Ожидает"

    # 2. Students list shows teacher column, code status column, filter by teacher
    r_list = c_mgr.get(f"/manager/students?teacher_id={t1_id}")
    assert r_list.status_code == 200
    list_html = r_list.data.decode("utf-8")
    assert "Нурлан Садыков" in list_html
    assert "Преподаватель Первый" in list_html
    assert "Ожидает" in list_html

    # 3. RBAC matrix on every manager route: allowed = sales_manager, supervisor, admin; 403 = teacher, student
    for ok_email in ("qa.mgr@monday.kg", "qa.sup@monday.kg", "qa.adm@monday.kg"):
        c_ok = _login(app.test_client(), ok_email)
        assert c_ok.get("/manager/students").status_code == 200
        assert c_ok.get("/manager/students/new").status_code == 200
        assert c_ok.get(f"/manager/students/records/{rec_id}").status_code == 200
        assert c_ok.get(f"/manager/teachers/{t1_id}").status_code == 200

    for bad_email in ("qa.t1@monday.kg", "qa.stu1@monday.kg", "qa.asst@monday.kg"):
        c_bad = _login(app.test_client(), bad_email)
        assert c_bad.get("/manager/students").status_code == 403
        assert c_bad.get("/manager/students/new").status_code == 403
        assert c_bad.post("/manager/students/new", data={"name": "X"}).status_code == 403
        assert c_bad.get(f"/manager/students/records/{rec_id}").status_code == 403
        assert c_bad.post(f"/manager/students/records/{rec_id}/code/regenerate").status_code == 403
        assert c_bad.post(f"/manager/students/records/{rec_id}/code/revoke").status_code == 403
        assert c_bad.post(f"/manager/students/records/{rec_id}/teacher/change", data={"new_teacher_id": t2_id, "reason": "x"}).status_code == 403
        assert c_bad.get(f"/manager/teachers/{t1_id}").status_code == 403
        assert c_bad.post(f"/manager/leads/{lead_id}/convert", data={"convert_mode": "code", "teacher_id": t1_id}).status_code == 403

    # 4. Regenerate & revoke code buttons + change teacher requires reason
    r_regen = c_mgr.post(f"/manager/students/records/{rec_id}/code/regenerate")
    assert r_regen.status_code == 200 and "no-store" in r_regen.headers.get("Cache-Control", "")
    with app.app_context():
        rec = db.session.get(StudentRecord, rec_id)
        code_second = rec.invite_code
        assert code_second and code_second != code_first

    # Missing reason does NOT change teacher
    c_mgr.post(
        f"/manager/students/records/{rec_id}/teacher/change",
        data={"new_teacher_id": str(t2_id), "course_id": str(course_id), "reason": "   "},
        follow_redirects=True,
    )
    with app.app_context():
        assert db.session.get(StudentRecord, rec_id).teacher_id == t1_id

    # With reason -> updates teacher and preserves history
    r_chg = c_mgr.post(
        f"/manager/students/records/{rec_id}/teacher/change",
        data={"new_teacher_id": str(t2_id), "course_id": str(course_id), "reason": "Пожелание ученика"},
        follow_redirects=True,
    )
    assert r_chg.status_code == 200
    card_html = r_chg.data.decode("utf-8")
    assert "Преподаватель Первый" in card_html
    assert "Преподаватель Второй" in card_html
    assert "Пожелание ученика" in card_html

    # Manager read-only teacher view reflects change
    assert "Нурлан Садыков" not in c_mgr.get(f"/manager/teachers/{t1_id}").data.decode("utf-8")
    assert "Нурлан Садыков" in c_mgr.get(f"/manager/teachers/{t2_id}").data.decode("utf-8")

    # 5. Idempotent lead conversion ("Конвертировать в ученика")
    r_c1 = c_mgr.post(
        f"/manager/leads/{lead_id}/convert",
        data={"convert_mode": "code", "name": "Айдана Асанова", "phone": "+996555998877", "teacher_id": str(t1_id), "course_id": str(course_id)},
    )
    assert r_c1.status_code == 200
    with app.app_context():
        recs = StudentRecord.query.filter_by(source_lead_id=lead_id).all()
        assert len(recs) == 1
        lead_code = recs[0].invite_code
        assert lead_code in r_c1.data.decode("utf-8")

    r_c2 = c_mgr.post(
        f"/manager/leads/{lead_id}/convert",
        data={"convert_mode": "code", "name": "Другое Имя", "teacher_id": str(t2_id)},
    )
    assert r_c2.status_code == 200
    with app.app_context():
        recs = StudentRecord.query.filter_by(source_lead_id=lead_id).all()
        assert len(recs) == 1
        assert recs[0].invite_code == lead_code
        assert recs[0].teacher_id == t1_id
        assert AuditLog.query.filter_by(action="lead_convert", entity_type="lead", entity_id=lead_id).count() == 1


def test_stage3_student_claim_flow_no_oracle_confirmation_concurrency_and_ratelimit(tmp_path):
    app = _build_qa_app(tmp_path, ratelimit=False)
    with app.app_context():
        t1 = User.query.filter_by(email="qa.t1@monday.kg").one()
        mgr = User.query.filter_by(email="qa.mgr@monday.kg").one()
        rec_wait = StudentRecord(
            teacher_id=t1.id,
            created_by_user_id=mgr.id,
            name="Айдана Асанова",
            phone="+996555000999",
            exam="SAT",
        )
        rec_wait.rotate_invite_code()
        db.session.add(rec_wait)
        db.session.flush()
        db.session.add(TeacherAssignment(student_record_id=rec_wait.id, teacher_user_id=t1.id, assigned_by_id=mgr.id))

        rec_extra = StudentRecord(teacher_id=t1.id, created_by_user_id=mgr.id, name="Вторая Запись")
        rec_extra.rotate_invite_code()
        db.session.add(rec_extra)
        db.session.flush()
        db.session.add(TeacherAssignment(student_record_id=rec_extra.id, teacher_user_id=t1.id, assigned_by_id=mgr.id))
        db.session.commit()
        code_wait = rec_wait.invite_code
        code_extra = rec_extra.invite_code

    # 1. Logged-out /join/<code> reveals nothing and returns identical response for valid & invalid codes
    c_anon1 = app.test_client()
    r_v = c_anon1.get(f"/join/{code_wait}", follow_redirects=False)
    c_anon2 = app.test_client()
    r_bad = c_anon2.get("/join/MND-DOESNOTEXIST1", follow_redirects=False)
    assert r_v.status_code == 302 and r_bad.status_code == 302
    assert r_v.headers["Location"] == r_bad.headers["Location"]
    reg_v = c_anon1.get(r_v.headers["Location"]).data.decode("utf-8")
    reg_bad = c_anon2.get(r_bad.headers["Location"]).data.decode("utf-8")
    assert "Айдана" not in reg_v
    assert "Преподаватель" not in reg_v
    import re
    def _strip_tokens(html: str, raw_code: str) -> str:
        s = html.replace(raw_code, "CODE_PLACEHOLDER")
        s = re.sub(r'(<input[^>]*name="csrf_token"[^>]*value=")[^"]+(")', r"\1CSRF\2", s)
        s = re.sub(r'(<meta[^>]*name="csrf-token"[^>]*content=")[^"]+(")', r"\1CSRF\2", s)
        return s
    assert _strip_tokens(reg_v, code_wait) == _strip_tokens(reg_bad, "MND-DOESNOTEXIST1")

    # 2. Student logs in with pending session invite_code -> lands on confirmation screen showing ONLY "Вы — Айдана А.?"
    r_login = c_anon1.post(
        "/login",
        data={"email": "qa.stu1@monday.kg", "password": "StrongPass123!"},
        follow_redirects=False,
    )
    assert r_login.status_code == 302
    assert f"/join/{code_wait}" in r_login.headers["Location"]
    r_conf = c_anon1.get(r_login.headers["Location"])
    conf_html = r_conf.data.decode("utf-8")
    assert r_conf.status_code == 200
    assert "Вы — Айдана А.?" in conf_html
    assert "Асанова" not in conf_html
    assert "Преподаватель Первый" not in conf_html  # teacher hidden until confirmed

    # Confirm via POST -> claims record
    r_claim = c_anon1.post(f"/join/{code_wait}", data={"action": "confirm"}, follow_redirects=True)
    assert r_claim.status_code == 200
    assert "Преподаватель Первый" in r_claim.data.decode("utf-8")

    # Student already linked to a different record cannot claim another code
    r_second_confirm = c_anon1.get(f"/join/{code_extra}")
    assert "обратитесь к менеджеру" in r_second_confirm.data.decode("utf-8").lower()
    r_prof_second = c_anon1.post("/profile", data={"action": "join", "invite_code": code_extra}, follow_redirects=True)
    assert "обратитесь к менеджеру" in r_prof_second.data.decode("utf-8").lower()

    # Non-student POST to /join returns 403
    c_t = _login(app.test_client(), "qa.t1@monday.kg")
    assert c_t.post(f"/join/{code_extra}", data={"action": "confirm"}).status_code == 403

    # 3. Concurrent claim race on code_extra between two unlinked student accounts -> exactly one succeeds
    with app.app_context():
        s_a = User(email="race.a@monday.kg", name="Race A", role="student", is_approved=True)
        s_a.set_password("StrongPass123!")
        s_a.profile = StudentProfile(exam="SAT", onboarded=True)
        s_b = User(email="race.b@monday.kg", name="Race B", role="student", is_approved=True)
        s_b.set_password("StrongPass123!")
        s_b.profile = StudentProfile(exam="SAT", onboarded=True)
        db.session.add_all([s_a, s_b])
        db.session.commit()
        uid_a, uid_b = s_a.id, s_b.id

    barrier = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def race_claim(uid):
        with app.app_context():
            barrier.wait(timeout=5)
            u = db.session.get(User, uid)
            ok, msg = claim_code(u, code_extra)
            with lock:
                results.append((uid, ok, msg))
            db.session.remove()

    th1 = threading.Thread(target=race_claim, args=(uid_a,))
    th2 = threading.Thread(target=race_claim, args=(uid_b,))
    th1.start()
    th2.start()
    th1.join(timeout=10)
    th2.join(timeout=10)
    assert sum(1 for _, ok, _ in results if ok) == 1
    assert sum(1 for _, ok, _ in results if not ok) == 1

    # 4. Rate limit on /join/<code> (separate ratelimit=True app)
    rl_app = _build_qa_app(tmp_path / "rl", ratelimit=True)
    c_rl = _login(rl_app.test_client(), "qa.stu1@monday.kg")
    statuses = [c_rl.get("/join/MND-FAKECODE0001").status_code for _ in range(17)]
    assert 429 in statuses


def test_stage4_teacher_and_student_visibility_after_teacher_change(tmp_path):
    app = _build_qa_app(tmp_path)
    with app.app_context():
        t1 = User.query.filter_by(email="qa.t1@monday.kg").one()
        t2 = User.query.filter_by(email="qa.t2@monday.kg").one()
        mgr = User.query.filter_by(email="qa.mgr@monday.kg").one()
        stu = User.query.filter_by(email="qa.stu2@monday.kg").one()
        course = AcademicCourse.query.filter_by(code="QA_SAT").one()
        skill = Skill.query.first()
        # Create a lead with sensitive CRM notes & student financial debt
        lead = Lead(
            full_name="Бектур Беков",
            phone="+996555333444",
            status="won",
            converted_student_id=stu.id,
            assigned_manager_id=mgr.id,
        )
        db.session.add(lead)
        db.session.flush()
        db.session.add(LeadActivity(lead_id=lead.id, actor_id=mgr.id, type="note", body="SECRET_CRM_DEBT_NOTE"))

        from monday.models import MembershipPlan
        plan = MembershipPlan(name="VIP Plan", price_amount=15000, currency="KGS", total_lessons=12, is_active=True)
        db.session.add(plan)
        db.session.flush()
        sp = StudentPass(student_user_id=stu.id, plan_id=plan.id, agreed_price=15000, paid_amount=5000, status="active")
        db.session.add(sp)

        # Create unclaimed manager student first -> verify teacher list hides phone/email/notes & shows "ожидает регистрации"
        from monday.student_links import change_teacher, create_student_with_code
        unclaimed_rec, _ = create_student_with_code(
            mgr, "Скрытый Неподключенный", "+996777123999", "secret.email@example.com", t1.id, course.id, lead_id=None
        )
        unclaimed_id = unclaimed_rec.id

        # Create claimed student assigned to t1, with an EARLIER practice attempt + a homework assignment created by t1
        claimed_rec, claimed_code = create_student_with_code(
            mgr, stu.name, "+996555333444", None, t1.id, course.id, lead_id=lead.id
        )
        claimed_id = claimed_rec.id
        claim_code(stu, claimed_code)

        # Published work by t1 assigned to claimed_rec
        w = Work(author_id=t1.id, title="T1 Old Homework", kind="homework", exam="SAT", status="published")
        db.session.add(w)
        db.session.flush()
        wv = WorkVersion(work_id=w.id, number=1, title=w.title, items=[{"id": 1, "text": "2+2?", "answer_type": "exact", "answer": "4", "weight": 1}])
        db.session.add(wv)
        db.session.flush()
        w.current_version_id = wv.id
        asn = Assignment(work_id=w.id, teacher_id=t1.id, record_id=claimed_id, due_at=utcnow() + timedelta(days=3))
        db.session.add(asn)

        w2 = Work(author_id=t2.id, title="T2 Own Work", kind="homework", exam="SAT", status="published")
        db.session.add(w2)
        db.session.flush()
        wv2 = WorkVersion(work_id=w2.id, number=1, title=w2.title, items=[{"id": 1, "text": "3+3?", "answer_type": "exact", "answer": "6", "weight": 1}])
        db.session.add(wv2)
        db.session.flush()
        w2.current_version_id = wv2.id

        # Earlier practice attempt BEFORE teacher change (at utcnow() - 2 days)
        past_ts = utcnow() - timedelta(days=2)
        past_att = Attempt(user_id=stu.id, mode="franklin", started_at=past_ts, finished_at=past_ts + timedelta(minutes=5), score=1, total=1)
        db.session.add(past_att)
        db.session.flush()
        if skill:
            db.session.add(AttemptAnswer(attempt_id=past_att.id, index=0, skill_id=skill.id, is_correct=True, answered_at=past_ts))
        db.session.commit()
        asn_id, w1_id, w2_id, wv_id, stu_id, t1_id, t2_id, mgr_id, course_id = asn.id, w.id, w2.id, wv.id, stu.id, t1.id, t2.id, mgr.id, course.id

    # Verify unclaimed manager student on T1 views: shows "ожидает регистрации", hides phone/email
    c_t1 = _login(app.test_client(), "qa.t1@monday.kg")
    t1_list = c_t1.get("/teacher/students").data.decode("utf-8")
    assert "Скрытый Неподключенный" in t1_list
    assert "ожидает регистрации" in t1_list
    assert "+996777123999" not in t1_list
    assert "secret.email@example.com" not in t1_list
    t1_det = c_t1.get(f"/teacher/students/{unclaimed_id}").data.decode("utf-8")
    assert "ожидает регистрации" in t1_det
    assert "+996777123999" not in t1_det

    # T2 cannot access T1's students -> 403
    c_t2 = _login(app.test_client(), "qa.t2@monday.kg")
    assert c_t2.get(f"/teacher/students/{claimed_id}").status_code == 403
    assert c_t2.post("/teacher/assign", data={"work_id": str(w2_id), "record_ids": str(claimed_id)}).status_code == 403

    # Student checks home & profile BEFORE change -> sees T1; NO CRM notes or debt visible
    c_stu = _login(app.test_client(), "qa.stu2@monday.kg")
    home_before = c_stu.get("/home").data.decode("utf-8")
    prof_before = c_stu.get("/profile").data.decode("utf-8")
    assert "Преподаватель Первый" in home_before
    assert "Преподаватель Первый" in prof_before
    assert "SECRET_CRM_DEBT_NOTE" not in home_before
    assert "10000" not in prof_before  # debt hidden

    # Student submits T1's homework
    with app.app_context():
        sub_ts = utcnow() - timedelta(hours=1)
        hw_att = Attempt(user_id=stu_id, assignment_id=asn_id, work_version_id=wv_id, mode="homework", started_at=sub_ts, finished_at=sub_ts, score=1, total=1)
        db.session.add(hw_att)
        db.session.commit()

    # Now manager changes teacher from T1 -> T2
    with app.app_context():
        from monday.student_links import change_teacher
        change_teacher(db.session.get(User, mgr_id), claimed_id, t2_id, course_id, "Перевод в другую группу")

    # T1 loses access to student progress & assigning new homework -> 403
    assert "Бектур Беков" not in c_t1.get("/teacher/students").data.decode("utf-8")
    assert c_t1.get(f"/teacher/students/{claimed_id}").status_code == 403
    assert c_t1.post("/teacher/assign", data={"work_id": str(w1_id), "record_ids": str(claimed_id)}).status_code == 403
    # T1 retains READ-ONLY access to homework T1 created, but POST grading -> 403
    r_t1_rev = c_t1.get(f"/teacher/review/{asn_id}")
    assert r_t1_rev.status_code == 200
    assert "Только просмотр" in r_t1_rev.data.decode("utf-8")
    assert c_t1.post(f"/teacher/review/{asn_id}", data={"action": "check", "teacher_comment": "Try grade"}).status_code == 403

    # T2 gains access + grading rights on existing submission!
    assert "Бектур Беков" in c_t2.get("/teacher/students").data.decode("utf-8")
    t2_det_before = c_t2.get(f"/teacher/students/{claimed_id}").data.decode("utf-8")
    assert "SECRET_CRM_DEBT_NOTE" not in t2_det_before
    # Current teacher CAN grade existing submission
    r_t2_grade = c_t2.post(
        f"/teacher/review/{asn_id}",
        data={"action": "check", "teacher_comment": "Проверено новым учителем"},
        follow_redirects=True,
    )
    assert r_t2_grade.status_code == 200
    assert "Проверено новым учителем" in r_t2_grade.data.decode("utf-8")

    # Progress cutoff: NEW_TEACHER_SEES_EARLIER_PROGRESS = False -> T2 sees 0 skills from past_ts (before started_at)
    with app.app_context():
        from monday.services import skill_stats
        from monday.student_links import teacher_progress_since
        rec = db.session.get(StudentRecord, claimed_id)
        t2_u = db.session.get(User, t2_id)
        cutoff = teacher_progress_since(t2_u, rec)
        assert cutoff is not None
        assert skill_stats(stu_id, since=cutoff) == {}

        # Toggle config constant True -> earlier progress becomes visible
        app.config["NEW_TEACHER_SEES_EARLIER_PROGRESS"] = True
        assert teacher_progress_since(t2_u, rec) is None
        assert skill_stats(stu_id, since=None) != {}

    # Student now sees NEW teacher on home & profile, AND still sees existing homework!
    home_after = c_stu.get("/home").data.decode("utf-8")
    prof_after = c_stu.get("/profile").data.decode("utf-8")
    hw_after = c_stu.get("/homework").data.decode("utf-8")
    assert "Преподаватель Второй" in home_after and "Преподаватель Первый" not in home_after
    assert "Преподаватель Второй" in prof_after and "Преподаватель Первый" not in prof_after
    assert "T1 Old Homework" in hw_after

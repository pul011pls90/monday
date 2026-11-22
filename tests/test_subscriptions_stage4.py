"""Stage 4 tests: subscription lifecycle, grandfathering backfill, atomic free quota, gating matrix, and Supabase smoke/preflight."""
from __future__ import annotations

import json
import os
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from config import Config
from monday import create_app
from monday.constants import EXAMS
from monday.extensions import db
from monday.models import (
    AcademicCourse,
    AuditLog,
    ContentNode,
    CourseLesson,
    CourseUnit,
    DailyPick,
    DailyQuestionAccess,
    GroupEnrollment,
    Location,
    Question,
    StudentProfile,
    StudentRecord,
    StudyGroup,
    Subscription,
    SubscriptionEvent,
    SubscriptionPlan,
    TeacherAssignment,
    User,
    Work,
    today as local_today,
    utcnow,
)
from monday.services import publish_work

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_app(tmp_path, **overrides):
    class Cfg(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        PUBLIC_SITE_ENABLED = True
        PUBLIC_LEGAL_REVIEWED = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'stage4.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        PUBLIC_SAMPLE_MEDIA_FOLDER = str(tmp_path / "public_sample_media")

    for k, v in overrides.items():
        setattr(Cfg, k, v)
    return create_app(Cfg, seed_if_empty=False)


def _login(client, email: str, password: str = "Pass123456!"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=False)


def test_self_study_signup_flag_remains_disabled_by_default():
    assert Config.SELF_STUDY_SIGNUP_ENABLED is False


def test_stage4_gating_matrix_across_all_roles_and_tiers(tmp_path):
    from monday import storage
    from monday.public_samples import set_question_public_sample
    from monday.subscriptions import grant_manual_subscription

    app = _make_app(tmp_path, FREE_DAILY_QUESTION_LIMIT=2, COURSE_INCLUDED_IN_SUBSCRIPTION=True)

    with app.app_context():
        node = ContentNode(code="s4_alg", name="Algebra", level="node", exams=["ORT", "SAT"])
        db.session.add(node)
        db.session.flush()

        admin = User(email="admin@s4.test", name="Admin S4", role="admin", is_approved=True)
        admin.set_password("StrongAdmin123!")
        teacher = User(email="teacher@s4.test", name="Teacher S4", role="teacher", is_approved=True)
        teacher.set_password("StrongTeacher123!")
        assistant = User(email="asst@s4.test", name="Asst S4", role="assistant", is_approved=True)
        assistant.set_password("StrongAsst123!")
        manager = User(email="mgr@s4.test", name="Mgr S4", role="sales_manager", is_approved=True)
        manager.set_password("StrongMgr123!")
        supervisor = User(email="sup@s4.test", name="Sup S4", role="supervisor", is_approved=True)
        supervisor.set_password("StrongSup123!")

        enrolled_ta = User(email="enrolled_ta@s4.test", name="Enrolled TA", role="student")
        enrolled_ta.set_password("Pass123456!")
        enrolled_ta.profile = StudentProfile(exam="SAT", onboarded=True)

        enrolled_grp = User(email="enrolled_grp@s4.test", name="Enrolled Grp", role="student")
        enrolled_grp.set_password("Pass123456!")
        enrolled_grp.profile = StudentProfile(exam="SAT", onboarded=True)

        enrolled_invite = User(email="enrolled_inv@s4.test", name="Enrolled Inv", role="student")
        enrolled_invite.set_password("Pass123456!")
        enrolled_invite.profile = StudentProfile(exam="SAT", onboarded=True)

        subscriber = User(email="sub@s4.test", name="Paid Subscriber", role="student")
        subscriber.set_password("Pass123456!")
        subscriber.profile = StudentProfile(exam="SAT", onboarded=True)

        trial_sub = User(email="trial@s4.test", name="Trial Subscriber", role="student")
        trial_sub.set_password("Pass123456!")
        trial_sub.profile = StudentProfile(exam="SAT", onboarded=True)

        legacy_user = User(
            email="legacy@s4.test",
            name="Legacy User",
            role="student",
            legacy_access_until=utcnow() + timedelta(days=10),
        )
        legacy_user.set_password("Pass123456!")
        legacy_user.profile = StudentProfile(exam="SAT", onboarded=True)

        expired_sub_user = User(
            email="expired@s4.test",
            name="Expired User",
            role="student",
            legacy_access_until=utcnow() - timedelta(days=1),
        )
        expired_sub_user.set_password("Pass123456!")
        expired_sub_user.profile = StudentProfile(exam="SAT", onboarded=True)

        free_user = User(email="free@s4.test", name="Free User", role="student")
        free_user.set_password("Pass123456!")
        free_user.profile = StudentProfile(exam="SAT", onboarded=True)

        db.session.add_all([
            admin, teacher, assistant, manager, supervisor,
            enrolled_ta, enrolled_grp, enrolled_invite,
            subscriber, trial_sub, legacy_user, expired_sub_user, free_user,
        ])
        db.session.flush()

        # Enrollment branch 1: StudentRecord + open TeacherAssignment
        sr_ta = StudentRecord(teacher_id=teacher.id, student_user_id=enrolled_ta.id, name="Enrolled TA", exam="SAT")
        db.session.add(sr_ta)
        db.session.flush()
        db.session.add(TeacherAssignment(
            student_record_id=sr_ta.id,
            teacher_user_id=teacher.id,
            assigned_by_id=admin.id,
        ))

        # Enrollment branch 2: Active GroupEnrollment without StudentRecord
        course = AcademicCourse(code="SAT-GRP", name="SAT Group Course", exam="SAT", is_active=True)
        db.session.add(course)
        db.session.flush()
        grp = StudyGroup(name="SAT-A", course_id=course.id, teacher_id=teacher.id, is_active=True)
        db.session.add(grp)
        db.session.flush()
        db.session.add(GroupEnrollment(group_id=grp.id, student_user_id=enrolled_grp.id, course_id=course.id, status="active"))

        # Enrollment branch 3: Legacy/Invite-code StudentRecord link without TeacherAssignment rows
        db.session.add(StudentRecord(teacher_id=teacher.id, student_user_id=enrolled_invite.id, name="Invited", exam="SAT"))

        # Subscription grant for subscriber; expired subscription for expired_sub_user
        plan = SubscriptionPlan(code="qbank_m", name="Подписка на банк вопросов", price_amount=800, currency="USD", duration_days=30)
        db.session.add(plan)
        db.session.flush()
        grant_manual_subscription(admin, subscriber, plan, status="active", duration_days=30)
        grant_manual_subscription(admin, trial_sub, plan, status="trialing", duration_days=7)
        db.session.add(
            Subscription(
                user_id=expired_sub_user.id,
                plan_id=plan.id,
                status="active",
                starts_at=utcnow() - timedelta(days=40),
                current_period_end=utcnow() - timedelta(days=2),
                granted_by_id=admin.id,
            )
        )

        # Content: 1 public sample + 3 gated questions + published 5-question Work + SAT CourseUnit/Lesson
        sample_img = storage.save("q-pub-sample.png", PNG_1PX, "image/png")
        priv_img = storage.save("q-priv-fig.png", PNG_1PX, "image/png")
        q_sample = Question(
            author=teacher, skill=node, exams=["SAT", "ORT"], difficulty=1,
            text="Sample $1+1$", image_path=sample_img, options=["1", "2"], correct="1", status="published",
        )
        qs_priv = []
        for idx in range(3):
            q = Question(
                author=teacher, skill=node, exams=["SAT"], difficulty=2,
                text=f"Private Q{idx + 1}", image_path=(priv_img if idx == 0 else None),
                options=["A", "B", "C", "D"], correct="0", status="published",
            )
            qs_priv.append(q)
        db.session.add_all([q_sample, *qs_priv])
        db.session.flush()
        set_question_public_sample(q_sample, True)

        work = Work(
            author=teacher,
            kind="collection",
            category="thematic",
            exam="SAT",
            title="Mini SAT",
            status="draft",
            draft_question_ids=[qs_priv[0].id, qs_priv[1].id, qs_priv[2].id],
        )
        db.session.add(work)
        db.session.flush()
        publish_work(work)

        cu = CourseUnit(exam="SAT", number=1, slug="u1", title_ru="Алгебра")
        db.session.add(cu)
        db.session.flush()
        cl = CourseLesson(unit_id=cu.id, slug="l1", position=1, title_ru="Урок 1", kind="article", article_md="Текст урока")
        db.session.add(cl)
        db.session.commit()

        q_priv_ids = [q.id for q in qs_priv]
        q_sample_id = q_sample.id
        pub_key = q_sample.public_image_key
        work_id = work.id

    # 1. Anonymous user blocked on gated routes and /uploads, allowed on /question-bank/media/<key>
    c_anon = app.test_client()
    assert c_anon.get(f"/question-bank/media/{pub_key}").status_code == 200
    assert c_anon.get(f"/uploads/{priv_img}", follow_redirects=False).status_code == 302
    assert c_anon.get("/bank/", follow_redirects=False).status_code == 302
    assert c_anon.get("/sessions", follow_redirects=False).status_code == 302
    assert c_anon.get("/collections", follow_redirects=False).status_code == 302
    assert c_anon.get("/formulas", follow_redirects=False).status_code == 302
    assert c_anon.get("/api/trigonometry-formulas", follow_redirects=False).status_code == 302
    assert c_anon.get("/profile/export.csv", follow_redirects=False).status_code == 302
    assert c_anon.post("/api/course/check", json={"lesson_id": 1}).status_code in (401, 403)
    assert c_anon.post("/api/roadmap/node/x/complete", json={"done": True}).status_code in (401, 403)

    # 2. CRM manager & supervisor receive 403 on ALL student question-bank, /api/*, and /uploads/<question_figure>
    for crm_email, crm_pw in (("mgr@s4.test", "StrongMgr123!"), ("sup@s4.test", "StrongSup123!")):
        c_crm = app.test_client()
        assert _login(c_crm, crm_email, crm_pw).status_code == 302
        for url in (
            "/bank/", "/sessions", "/collections", "/formulas", "/formulas/trigonometry",
            "/api/trigonometry-formulas", "/profile/export.csv", "/profile/export.pdf",
            "/homework", "/roadmap/SAT/u1/l1", f"/uploads/{priv_img}", f"/uploads/{sample_img}",
        ):
            assert c_crm.get(url).status_code == 403, (crm_email, url)
        assert c_crm.post("/api/course/check", json={}).status_code == 403
        assert c_crm.post("/api/roadmap/node/x/complete", json={}).status_code == 403

    # 2b. Content staff roles (teacher, assistant, admin): authoring & question media allowed
    c_tch = app.test_client()
    assert _login(c_tch, "teacher@s4.test", "StrongTeacher123!").status_code == 302
    for ok_url in ("/teacher/questions", "/teacher/bank", "/teacher/picker/", "/teacher/works", "/formulas/trigonometry", "/api/trigonometry-formulas", f"/uploads/{priv_img}"):
        assert c_tch.get(ok_url).status_code == 200, ok_url
    assert c_tch.get("/admin/analytics/export.csv").status_code == 403

    c_asst = app.test_client()
    assert _login(c_asst, "asst@s4.test", "StrongAsst123!").status_code == 302
    for ok_url in ("/assistant/", "/assistant/mine", "/formulas/trigonometry", "/api/trigonometry-formulas", f"/uploads/{priv_img}"):
        assert c_asst.get(ok_url).status_code == 200, ok_url
    assert c_asst.get("/review/questions").status_code == 403

    c_adm = app.test_client()
    assert _login(c_adm, "admin@s4.test", "StrongAdmin123!").status_code == 302
    for ok_url in ("/review/questions", "/dev/visuals", "/admin/course", "/admin/roadmap", "/admin/analytics/export.csv", "/api/trigonometry-formulas", f"/uploads/{priv_img}"):
        assert c_adm.get(ok_url).status_code == 200, ok_url

    # 3. All 3 enrollment branches + legacy user get full access (enrolled_ta/inv see homework too)
    for email, has_hw in (
        ("enrolled_ta@s4.test", True),
        ("enrolled_grp@s4.test", False),  # active GroupEnrollment without TeacherAssignment link: full bank access, no teacher homework
        ("enrolled_inv@s4.test", True),
        ("legacy@s4.test", False),
    ):
        c = app.test_client()
        assert _login(c, email).status_code == 302
        for url in (
            "/bank/", "/sessions", "/collections", "/formulas", "/formulas/trigonometry",
            "/api/trigonometry-formulas", "/profile/export.csv", "/profile/export.pdf",
            "/roadmap/SAT/u1/l1", f"/uploads/{priv_img}",
        ):
            assert c.get(url).status_code == 200, (email, url)
        assert c.post("/api/roadmap/node/x/complete", json={"done": True}).status_code == 200
        assert c.post("/api/course/complete", json={"exam": "SAT", "unit_slug": "u1", "lesson_slug": "l1"}).status_code == 200
        assert c.get("/homework").status_code == (200 if has_hw else 403), (email, has_hw)
        if email == "legacy@s4.test":
            home_html = c.get("/home").data.decode("utf-8")
            assert "/subscription" in home_html
            assert "ранний полный доступ" in home_html.lower()

    # 4. Paid & trialing subscribers: full bank, formulas, exports, course (when COURSE_INCLUDED_IN_SUBSCRIPTION=True); NO teacher homework
    for sub_email in ("sub@s4.test", "trial@s4.test"):
        c_sub = app.test_client()
        assert _login(c_sub, sub_email).status_code == 302
        for url in (
            "/bank/", "/sessions", "/collections", "/formulas", "/formulas/trigonometry",
            "/api/trigonometry-formulas", "/profile/export.csv", "/profile/export.pdf",
            "/roadmap/SAT/u1/l1", f"/uploads/{priv_img}", "/subscription",
        ):
            assert c_sub.get(url).status_code == 200, (sub_email, url)
        assert c_sub.post("/api/roadmap/node/x/complete", json={"done": True}).status_code == 200
        assert c_sub.get("/homework").status_code == 403
        assert c_sub.get("/teacher/questions").status_code == 403
        sub_home = c_sub.get("/home").data.decode("utf-8")
        assert 'href="/homework"' not in sub_home
        assert "Преподаватель пока не назначен" not in sub_home

    # Toggle COURSE_INCLUDED_IN_SUBSCRIPTION=False -> subscriber blocked on /roadmap & /api/course/*, enrolled Monday student still 200!
    app.config["COURSE_INCLUDED_IN_SUBSCRIPTION"] = False
    c_paid = app.test_client()
    assert _login(c_paid, "sub@s4.test").status_code == 302
    assert c_paid.get("/roadmap/SAT/u1/l1").status_code == 403
    assert c_paid.post("/api/course/check", json={"a": 1}).status_code == 403
    assert c_paid.post("/api/course/complete", json={"exam": "SAT", "unit_slug": "u1", "lesson_slug": "l1"}).status_code == 403
    c_enr = app.test_client()
    assert _login(c_enr, "enrolled_ta@s4.test").status_code == 302
    assert c_enr.get("/roadmap/SAT/u1/l1").status_code == 200
    app.config["COURSE_INCLUDED_IN_SUBSCRIPTION"] = True

    # 5. Free-tier user & expired-sub user: 403 on premium/teacher routes, free samples unlimited, daily limit = 2 distinct Qs
    for free_email in ("free@s4.test", "expired@s4.test"):
        c_free = app.test_client()
        assert _login(c_free, free_email).status_code == 302
        # Allowed overview/profile pages
        for ok_url in ("/home", "/skills", "/bank/", "/sessions", "/collections", "/profile", "/subscription"):
            assert c_free.get(ok_url).status_code == 200, (free_email, ok_url)
        # Paid & teacher-only routes blocked with 403
        for denied_url in (
            "/formulas", "/formulas/trigonometry", "/api/trigonometry-formulas",
            "/profile/export.csv", "/profile/export.pdf",
            "/homework", "/roadmap/SAT/u1/l1",
            f"/uploads/{priv_img}",  # not yet unlocked today -> 403!
        ):
            assert c_free.get(denied_url).status_code == 403, (free_email, denied_url)
        assert c_free.post("/api/course/check", json={}).status_code == 403
        assert c_free.post("/api/roadmap/node/x/complete", json={"done": True}).status_code == 403
        # Public sample figure IS allowed even on free tier!
        assert c_free.get(f"/uploads/{sample_img}").status_code == 200

    # Exercise atomic daily quota on free_user (limit = 2)
    c_free = app.test_client()
    assert _login(c_free, "free@s4.test").status_code == 302
    # Start a 3-question work (> limit 2) -> 403!
    assert c_free.post(f"/works/{work_id}/start").status_code == 403

    # Unlock via bank: create attempt containing sample + 3 private questions, verify quota stops strictly at 2 distinct non-sample Qs
    from monday.models import Attempt
    with app.app_context():
        u_free = User.query.filter_by(email="free@s4.test").first()
        u_free_id = u_free.id
        att = Attempt(user_id=u_free_id, mode="bank", plan=[q_sample_id, *q_priv_ids], position=0, total=4, draft={"exam": "SAT"})
        db.session.add(att)
        db.session.commit()
        att_id = att.id

    # Sample question does NOT consume daily quota
    assert c_free.get(f"/bank/s/{att_id}?i=0").status_code == 200
    with app.app_context():
        assert DailyQuestionAccess.query.filter_by(user_id=u_free_id, access_date=local_today()).count() == 0

    # Unlock Q1 and Q2 (fills limit 2)
    assert c_free.get(f"/bank/s/{att_id}?i=1").status_code == 200
    assert c_free.get(f"/uploads/{priv_img}").status_code == 200  # Q1 figure is now unlocked today!
    assert c_free.get(f"/bank/s/{att_id}?i=2").status_code == 200
    # Revisit Q1 again -> still 200 without increasing quota!
    assert c_free.post(f"/bank/s/{att_id}/check", data={"i": "1", "given": "0"}).status_code == 200

    # Q3 (3rd distinct non-sample question) exceeds limit=2 -> 403!
    assert c_free.get(f"/bank/s/{att_id}?i=3").status_code == 403
    assert c_free.post(f"/bank/s/{att_id}/check", data={"i": "3", "given": "0"}).status_code == 403

    # Resets on next local day: shifting yesterday's rows back 1 day restores full limit=2 today
    with app.app_context():
        DailyQuestionAccess.query.filter_by(user_id=u_free_id).update({"access_date": local_today() - timedelta(days=1)})
        db.session.commit()
    assert c_free.get(f"/bank/s/{att_id}?i=3").status_code == 200


def test_free_tier_daily_quota_atomic_under_concurrency(tmp_path):
    from monday.subscriptions import claim_free_question_access

    app = _make_app(tmp_path, FREE_DAILY_QUESTION_LIMIT=3)
    with app.app_context():
        node = ContentNode(code="c_alg", name="Alg", level="node", exams=["ORT"])
        u = User(email="race_free@s4.test", name="Race Free", role="student")
        u.set_password("Pass123456!")
        db.session.add_all([node, u])
        db.session.flush()
        qids = []
        for idx in range(12):
            q = Question(skill=node, exams=["ORT"], text=f"Q{idx}", options=["a", "b"], correct="0", status="published")
            db.session.add(q)
            db.session.flush()
            qids.append(q.id)
        db.session.commit()
        uid = u.id

    def worker(qid: int) -> bool:
        with app.app_context():
            ok, *_ = claim_free_question_access(uid, [qid])
            return ok

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(worker, qids))

    assert sum(1 for r in results if r) == 3
    with app.app_context():
        assert DailyQuestionAccess.query.filter_by(user_id=uid, access_date=local_today()).count() == 3


def test_grandfathering_migration_backfill_and_legacy_report_cli(tmp_path):
    import subprocess
    from sqlalchemy import create_engine, text

    db_file = tmp_path / "mig_legacy.db"
    db_url = f"sqlite:///{db_file}"
    repo_root = os.path.dirname(os.path.dirname(__file__))
    flask_bin = "/Users/apple/Desktop/Monday/venv/bin/flask"
    env = {**os.environ, "DATABASE_URL": db_url, "LEGACY_ACCESS_DAYS": "30"}

    # Upgrade to Stage 3 head BEFORE Stage 4 grandfathering migration
    subprocess.run([flask_bin, "--app", "app", "db", "upgrade", "g3b4c5d6e7f8"], cwd=repo_root, env=env, check=True, capture_output=True)

    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO "user" (email, name, password_hash, role, is_approved, language, theme, is_blocked, is_methodist, auth_provider, session_version, must_change_password, is_on_shift, login_count, total_visits, average_visit_duration, created_at)
            VALUES
              ('legacy.stu@test.kg', 'Legacy Stu', 'x', 'student', 1, 'ru', 'light', 0, 0, 'password', 1, 0, 1, 0, 0, 0, CURRENT_TIMESTAMP),
              ('enrolled.stu@test.kg', 'Enrolled Stu', 'x', 'student', 1, 'ru', 'light', 0, 0, 'password', 1, 0, 1, 0, 0, 0, CURRENT_TIMESTAMP),
              ('blocked.stu@test.kg', 'Blocked Stu', 'x', 'student', 1, 'ru', 'light', 1, 0, 'password', 1, 0, 1, 0, 0, 0, CURRENT_TIMESTAMP),
              ('tch.s4@test.kg', 'Teacher S4', 'x', 'teacher', 1, 'ru', 'light', 0, 0, 'password', 1, 0, 1, 0, 0, 0, CURRENT_TIMESTAMP)
        """))
        enr_id = conn.execute(text("SELECT id FROM \"user\" WHERE email='enrolled.stu@test.kg'")).scalar_one()
        tch_id = conn.execute(text("SELECT id FROM \"user\" WHERE email='tch.s4@test.kg'")).scalar_one()
        conn.execute(
            text("INSERT INTO student_record (teacher_id, student_user_id, name, manual_progress, notes) VALUES (:t, :s, 'Enrolled', 0, '')"),
            {"t": tch_id, "s": enr_id},
        )
    engine.dispose()

    # Read-only pre-migration check BEFORE h4c5d6e7f8a9 exists: must succeed without user.legacy_access_until column!
    rep_pre = subprocess.run([flask_bin, "--app", "app", "legacy-access-report"], cwd=repo_root, env=env, check=True, capture_output=True, text=True)
    assert "Schema has user.legacy_access_until: False" in rep_pre.stdout
    assert "Total active student accounts: 2" in rep_pre.stdout
    assert "Already enrolled / teacher-linked students: 1" in rep_pre.stdout
    assert "Unlinked students still needing backfill (legacy_access_until IS NULL): 1" in rep_pre.stdout

    # Run Stage 4 migration upgrade -> backfill applies ONLY to unlinked active student!
    subprocess.run([flask_bin, "--app", "app", "db", "upgrade"], cwd=repo_root, env=env, check=True, capture_output=True)

    engine = create_engine(db_url)
    with engine.begin() as conn:
        rows = dict(conn.execute(text('SELECT email, legacy_access_until FROM "user"')).fetchall())
    engine.dispose()
    assert rows["legacy.stu@test.kg"] is not None
    assert rows["enrolled.stu@test.kg"] is None
    assert rows["blocked.stu@test.kg"] is None
    assert rows["tch.s4@test.kg"] is None

    # Read-only post-migration CLI report exits 0 and prints exact counts without modifying rows
    rep = subprocess.run([flask_bin, "--app", "app", "legacy-access-report"], cwd=repo_root, env=env, check=True, capture_output=True, text=True)
    assert "Schema has user.legacy_access_until: True" in rep.stdout
    assert "Total active student accounts: 2" in rep.stdout
    assert "Already enrolled / teacher-linked students: 1" in rep.stdout
    assert "Unlinked students already grandfathered (legacy_access_until SET): 1" in rep.stdout

    # New registration after deploy gets legacy_access_until=None and lands on free tier
    class MigCfg(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = db_url
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        PUBLIC_SAMPLE_MEDIA_FOLDER = str(tmp_path / "public_sample_media")

    app = create_app(MigCfg, seed_if_empty=False)
    c = app.test_client()
    r = c.post("/register", data={"name": "New Free", "email": "newfree@test.kg", "password": "NewUser123!", "role": "student"})
    assert r.status_code == 302
    with app.app_context():
        new_u = User.query.filter_by(email="newfree@test.kg").first()
        assert new_u is not None and new_u.legacy_access_until is None


def test_manual_subscription_lifecycle_and_audit_log(tmp_path):
    app = _make_app(tmp_path)
    with app.app_context():
        admin = User(email="adm@sub.test", name="Admin", role="admin", is_approved=True)
        admin.set_password("StrongAdmin123!")
        stu = User(email="stu@sub.test", name="Self Study", role="student")
        stu.set_password("Pass123456!")
        stu.profile = StudentProfile(exam="SAT", onboarded=True)
        db.session.add_all([admin, stu])
        db.session.commit()
        stu_id = stu.id

    c_stu = app.test_client()
    assert _login(c_stu, "stu@sub.test").status_code == 302
    assert c_stu.get("/formulas").status_code == 403
    assert c_stu.post(f"/admin/users/{stu_id}/subscription/grant", data={"status": "active"}).status_code == 403

    c_adm = app.test_client()
    assert _login(c_adm, "adm@sub.test", "StrongAdmin123!").status_code == 302
    r_plan = c_adm.post(
        "/admin/subscriptions/plans",
        data={"code": "qbank_pro", "name": "Pro банк", "price_amount": "1200", "currency": "USD", "duration_days": "60"},
        headers={"X-Requested-With": "fetch"},
    )
    assert r_plan.status_code == 200
    plan_id = r_plan.get_json()["plan_id"]

    r_grant = c_adm.post(
        f"/admin/users/{stu_id}/subscription/grant",
        data={"status": "trialing", "days": "14", "note": "Manual Stage 4 grant"},
        headers={"X-Requested-With": "fetch"},
    )
    assert r_grant.status_code == 200
    sub_id = r_grant.get_json()["subscription_id"]
    assert c_stu.get("/formulas").status_code == 200

    r_chg = c_adm.post(
        f"/admin/subscriptions/{sub_id}/plan",
        data={"plan_id": str(plan_id), "note": "Upgrade plan"},
        headers={"X-Requested-With": "fetch"},
    )
    assert r_chg.status_code == 200

    r_can = c_adm.post(
        f"/admin/subscriptions/{sub_id}/cancel",
        data={"note": "Requested cancel"},
        headers={"X-Requested-With": "fetch"},
    )
    assert r_can.status_code == 200
    assert c_stu.get("/formulas").status_code == 403

    with app.app_context():
        ev_types = [e.event_type for e in SubscriptionEvent.query.filter_by(subscription_id=sub_id).order_by(SubscriptionEvent.id).all()]
        assert ev_types == ["manual_grant", "plan_change", "cancel"]
        audit_actions = [a.action for a in AuditLog.query.filter_by(entity_type="bank_subscription", entity_id=sub_id).order_by(AuditLog.id).all()]
        assert audit_actions == ["subscription_manual_grant", "subscription_plan_change", "subscription_cancel"]


def test_supabase_storage_smoke_preflight_and_error_isolation(tmp_path, monkeypatch):
    from monday import storage
    from monday.public_site import collect_site_preflight_blockers

    # 1. Production mode preflight blocks ephemeral local sample disk without Supabase or Render persistent disk
    ephem_app = _make_app(tmp_path, IS_PRODUCTION=True, PUBLIC_SAMPLE_PERSISTENT_DISK=False)
    clean_dir = tmp_path / "clean_tpl"
    clean_dir.mkdir()
    (clean_dir / "about.html").write_text("<h1>Monday Academy</h1>", encoding="utf-8")
    full_contacts = {
        "instagram": "https://instagram.com/x",
        "telegram": "https://t.me/x",
        "whatsapp": "https://wa.me/996700111222",
        "trial_lesson": "https://monday.kg/contact",
        "address": "Токтогула 77",
    }
    with ephem_app.app_context():
        node = ContentNode(code="sp", name="All", level="node", exams=list(EXAMS.keys()))
        db.session.add(node)
        db.session.add(Location(name="L1", address="Addr", working_hours="09-18", phone="+996", photo="x.jpg", is_active=True, is_public=True))
        db.session.add(AcademicCourse(code="C1", name="Course", public_summary="Summary", is_active=True, is_public=True))
        db.session.add(Question(skill=node, exams=list(EXAMS.keys()), text="2+2", options=["3", "4"], correct="1", status="published", is_public_sample=True))
        db.session.commit()
        blockers = collect_site_preflight_blockers(contacts_override=full_contacts, template_dirs=(clean_dir,))
        assert any("ephemeral local disk" in b for b in blockers)

    # 2. Local CLI smoke test works cleanly
    runner = ephem_app.test_cli_runner()
    res_local = runner.invoke(args=["site-media-smoke"])
    assert res_local.exit_code == 0 and "local_disk" in res_local.output

    # 3. Supabase mode: paginated list API + orphan check + 503 error isolation without leaking secret key
    supa_app = _make_app(
        tmp_path / "supa",
        IS_PRODUCTION=True,
        SUPABASE_URL="https://demo.supabase.co",
        SUPABASE_SERVICE_KEY="sb_secret_super_sensitive_token_123",
        SUPABASE_BUCKET="uploads",
    )
    fake_store: dict[str, bytes] = {}
    calls: list[dict] = []

    def fake_api(path, data=None, headers=None, timeout=20, method=None):
        calls.append({"path": path, "method": method})
        if path.startswith("object/list/uploads"):
            payload = json.loads(data.decode("utf-8"))
            prefix = payload["prefix"]
            offset = payload["offset"]
            limit = payload["limit"]
            matched = []
            for k in sorted(fake_store):
                if prefix and not k.startswith(prefix + "/"):
                    continue
                tail = k[len(prefix) + 1:] if prefix else k
                matched.append({"name": tail, "id": "id-" + tail})
            # Force pagination cleanly across offset slices
            page_limit = min(limit, 1) if matched else limit
            batch = matched[offset:offset + page_limit]
            return json.dumps(batch).encode("utf-8")
        if path.startswith("object/authenticated/uploads/"):
            obj = path.split("object/authenticated/uploads/", 1)[1]
            if obj not in fake_store:
                raise urllib.error.HTTPError("https://demo.supabase.co", 404, "Not Found", {}, None)
            return fake_store[obj]
        if path.startswith("object/uploads/") and method == "DELETE":
            obj = path.split("object/uploads/", 1)[1]
            fake_store.pop(obj, None)
            return b"{}"
        if path.startswith("object/uploads/"):
            obj = path.split("object/uploads/", 1)[1]
            fake_store[obj] = data or b""
            return b'{"Key":"' + obj.encode("utf-8") + b'"}'
        raise AssertionError(f"Unexpected path {path}")

    monkeypatch.setattr(storage, "_api", fake_api)

    # CLI smoke test in Supabase mode
    res_supa = supa_app.test_cli_runner().invoke(args=["site-media-smoke"])
    assert res_supa.exit_code == 0 and "supabase" in res_supa.output
    assert "sb_secret" not in res_supa.output

    # Preflight orphan check in Supabase mode catches stale bucket object via paginated list API
    fake_store["public-samples/" + ("a" * 32) + ".png"] = PNG_1PX
    fake_store["public-samples/" + ("b" * 32) + ".png"] = PNG_1PX
    with supa_app.app_context():
        node = ContentNode(code="sp2", name="All", level="node", exams=list(EXAMS.keys()))
        db.session.add(node)
        db.session.add(Location(name="L1", address="Addr", working_hours="09-18", phone="+996", photo="x.jpg", is_active=True, is_public=True))
        db.session.add(AcademicCourse(code="C1", name="Course", public_summary="Summary", is_active=True, is_public=True))
        db.session.add(Question(skill=node, exams=list(EXAMS.keys()), text="2+2", options=["3", "4"], correct="1", status="published", is_public_sample=True))
        db.session.commit()
        supa_blockers = collect_site_preflight_blockers(contacts_override=full_contacts, template_dirs=(clean_dir,))
        assert any("Orphaned public sample media object exists in Supabase Storage" in b for b in supa_blockers)

        # Simulate upstream 500 error during media read -> 503 response, zero secret leakage
        q_bad = Question(
            skill=node, exams=["ORT"], text="With img", image_path="q-x.png",
            options=["1", "2"], correct="0", status="published",
            is_public_sample=True, public_image_key=("c" * 32) + ".png",
        )
        db.session.add(q_bad)
        db.session.commit()
        bad_key = q_bad.public_image_key

    def failing_api(*args, **kwargs):
        raise urllib.error.URLError("upstream timeout with sb_secret_super_sensitive_token_123")

    monkeypatch.setattr(storage, "_api", failing_api)
    r_err = supa_app.test_client().get(f"/question-bank/media/{bad_key}")
    assert r_err.status_code == 503
    body_err = r_err.data.decode("utf-8")
    assert "sb_secret" not in body_err
    assert "demo.supabase.co" not in body_err

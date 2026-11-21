"""Targeted security tests for all P1 (High-Priority) blockers."""
import json
import os
import re
import tempfile

from config import Config
from monday.extensions import db
from monday.models import CourseLesson, CourseMastery, CourseUnit, Question, StudentProfile, StudentRecord, User
from test_app import APP, client, login


# --------------------------------------------------------------------------- P1-6: Server-side course mastery


def test_p1_6_course_complete_ignores_client_spoofed_scores_and_grades_server_side():
    c = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        unit = CourseUnit(exam="SAT", number=99, slug="p1-sec-unit", title_ru="Security Test Unit")
        db.session.add(unit)
        db.session.flush()
        quiz = CourseLesson(
            unit_id=unit.id,
            slug="p1-sec-quiz",
            position=1,
            title_ru="Unit Quiz",
            kind="quiz",
            inline_quiz_json=json.dumps([
                {"id": "q1", "prompt": "1+1=?", "type": "number", "answer": "2"},
                {"id": "q2", "prompt": "2+2=?", "type": "number", "answer": "4"},
            ]),
        )
        db.session.add(quiz)
        db.session.commit()
        uid = unit.id

    try:
        # 1. Spoofing /api/course/complete directly without answering via /api/course/check is rejected (400)
        r_spoof = c.post(
            "/api/course/complete",
            json={"exam": "SAT", "unit_slug": "p1-sec-unit", "lesson_slug": "p1-sec-quiz", "score": 2, "total": 2},
        )
        assert r_spoof.status_code == 400 and r_spoof.get_json()["error"] == "no_graded_answers"

        # 2. Answer both WRONG via /check, then spoof score=2 in /complete -> server grades 0/2 -> familiar (not mastered!)
        assert c.get("/roadmap/SAT/p1-sec-unit/p1-sec-quiz").status_code == 200
        r_c1 = c.post("/api/course/check", json={"exam": "SAT", "unit_slug": "p1-sec-unit", "lesson_slug": "p1-sec-quiz", "question_id": "q1", "given": "999"})
        assert r_c1.status_code == 200 and r_c1.get_json()["is_correct"] is False
        # Re-submitting q1 right after seeing correct_answer in the same run must NOT overwrite first graded result
        c.post("/api/course/check", json={"exam": "SAT", "unit_slug": "p1-sec-unit", "lesson_slug": "p1-sec-quiz", "question_id": "q1", "given": "2"})
        c.post("/api/course/check", json={"exam": "SAT", "unit_slug": "p1-sec-unit", "lesson_slug": "p1-sec-quiz", "question_id": "q2", "given": "999"})

        r_comp = c.post(
            "/api/course/complete",
            json={"exam": "SAT", "unit_slug": "p1-sec-unit", "lesson_slug": "p1-sec-quiz", "score": 2, "total": 2},
        )
        assert r_comp.status_code == 200
        d = r_comp.get_json()
        assert d["score"] == 0 and d["total"] == 2 and d["level"] == "familiar"

        # 3. Fresh run with genuinely correct answers -> mastered
        assert c.get("/roadmap/SAT/p1-sec-unit/p1-sec-quiz").status_code == 200
        assert c.post("/api/course/check", json={"exam": "SAT", "unit_slug": "p1-sec-unit", "lesson_slug": "p1-sec-quiz", "question_id": "q1", "given": "2"}).get_json()["is_correct"] is True
        assert c.post("/api/course/check", json={"exam": "SAT", "unit_slug": "p1-sec-unit", "lesson_slug": "p1-sec-quiz", "question_id": "q2", "given": "4"}).get_json()["is_correct"] is True
        r_ok = c.post(
            "/api/course/complete",
            json={"exam": "SAT", "unit_slug": "p1-sec-unit", "lesson_slug": "p1-sec-quiz", "score": 0, "total": 99},
        )
        assert r_ok.status_code == 200
        d2 = r_ok.get_json()
        assert d2["score"] == 2 and d2["total"] == 2 and d2["level"] == "mastered"
    finally:
        with APP.app_context():
            CourseMastery.query.filter_by(lesson_key="p1-sec-unit:p1-sec-quiz").delete()
            u = db.session.get(CourseUnit, uid)
            if u:
                db.session.delete(u)
            db.session.commit()


# --------------------------------------------------------------------------- P1-7: Endpoint & Redact Lockdown


def test_p1_7_dev_visuals_trig_api_and_draft_question_redact_locked_down():
    anon = client()
    stu = login(client(), "student@monday.kg", "student123")
    tch = login(client(), "aibek@monday.kg", "teacher123")
    other_tch = login(client(), "nurai@monday.kg", "teacher123")
    adm = login(client(), "admin@monday.kg", "monday2026")

    # /dev/visuals: admin-only
    assert anon.get("/dev/visuals").status_code == 302
    assert stu.get("/dev/visuals").status_code == 403
    assert tch.get("/dev/visuals").status_code == 403
    assert adm.get("/dev/visuals").status_code == 200

    # /api/trigonometry-formulas: login required
    assert anon.get("/api/trigonometry-formulas").status_code == 302
    assert stu.get("/api/trigonometry-formulas").status_code == 200

    # Draft question redact: author & admin allowed; other teacher gets 404
    with APP.app_context():
        aibek = User.query.filter_by(email="aibek@monday.kg").first()
        dq = Question(author_id=aibek.id, text="Secret draft $x+1$", answer_type="number", correct="2", status="draft")
        db.session.add(dq)
        db.session.commit()
        dq_id = dq.id
    try:
        assert tch.get(f"/teacher/questions/{dq_id}/redact?modal=1").status_code == 200
        assert adm.get(f"/teacher/questions/{dq_id}/redact?modal=1").status_code == 200
        assert other_tch.get(f"/teacher/questions/{dq_id}/redact?modal=1").status_code == 404
        assert other_tch.post(f"/teacher/questions/{dq_id}/redact", data={"text": "hijack"}).status_code == 404
    finally:
        with APP.app_context():
            obj = db.session.get(Question, dq_id)
            if obj:
                db.session.delete(obj)
            db.session.commit()


# --------------------------------------------------------------------------- P1-8: Sessions, Secrets, Redirects, Rate Limit


def test_p1_8_session_revocation_no_cookie_temp_pw_safe_next_and_no_hardcoded_desmos(monkeypatch):
    # 1. No hardcoded DESMOS_API_KEY in Config default
    monkeypatch.delenv("DESMOS_API_KEY", raising=False)
    import importlib
    import config
    importlib.reload(config)
    assert config.Config.DESMOS_API_KEY == ""
    assert config.Config.REMEMBER_COOKIE_SAMESITE == "Lax"
    assert config.Config.REMEMBER_COOKIE_DURATION.days <= 30

    # 2. _safe_next blocks backslash and protocol-relative open redirects
    from monday.auth import _safe_next
    assert _safe_next("/home") == "/home"
    assert _safe_next("/\\evil.com") is None
    assert _safe_next("//evil.com") is None
    assert _safe_next("https://evil.com") is None

    # 3. Password change revokes OTHER active sessions while keeping current session logged in
    email = "p1.session.rev@example.com"
    c1 = client()
    c1.post("/register", data={"name": "Sess User", "email": email, "password": "OldPassword1", "role": "student"})
    c1.post("/onboarding", data={"exam": "ORT", "name": "Sess User", "grade": "11"})
    c2 = login(client(), email, "OldPassword1")
    assert c2.get("/home").status_code == 200

    # c1 changes password -> c2 must be immediately revoked (302 to /login), c1 stays signed in
    c1.post("/profile", data={"action": "password", "current": "OldPassword1", "new": "NewPassword2"})
    assert c1.get("/home").status_code == 200
    assert c2.get("/home").status_code == 302

    # 4. Admin password reset renders one-time password with Cache-Control: no-store and NEVER stores it in session cookie
    with APP.app_context():
        uid = User.query.filter_by(email=email).first().id
    adm = login(client(), "admin@monday.kg", "monday2026")
    resp = adm.post(f"/admin/users/{uid}/reset-password")
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("Cache-Control", "")
    body = resp.data.decode()
    m = re.search(r"Временный пароль для [^:]+: (\w+)\.", body)
    assert m is not None
    raw_pw = m.group(1)
    # Ensure temp password is NOT flashed into session cookie
    with adm.session_transaction() as sess:
        assert raw_pw not in json.dumps(dict(sess))
    # c1 session must ALSO be invalidated by admin password reset
    assert c1.get("/home").status_code == 302


def test_p1_8_rate_limiter_enforces_limits_on_login_and_join():
    tmp = tempfile.mkdtemp()

    class RateLimitConfig(Config):
        TESTING = True
        RATELIMIT_ENABLED = True
        RATELIMIT_STORAGE_URI = "memory://"
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "rl.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")
        SERVER_NAME = "localhost"

    from flask_migrate import upgrade
    from monday import create_app
    app = create_app(RateLimitConfig, seed_if_empty=False)
    with app.app_context():
        upgrade()
    c = app.test_client()
    codes = [c.post("/login", data={"email": "nobody@example.com", "password": "bad"}).status_code for _ in range(12)]
    assert 429 in codes

    join_codes = [c.get("/join/MND-FAKECODE1234").status_code for _ in range(17)]
    assert 429 in join_codes


# --------------------------------------------------------------------------- P1-9: Staging blueprint


def test_p1_9_staging_blueprint_isolated_and_safe():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "render.staging.yaml"), encoding="utf-8") as f:
        text = f.read()
    assert "name: monday-staging" in text
    assert "name: monday-staging-db" in text
    assert "preDeployCommand: flask --app app db upgrade" in text
    assert "key: SEED_DEMO" in text and "key: DATA_FIXES" in text and "key: COOKIE_SECURE" in text

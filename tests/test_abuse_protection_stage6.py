"""Stage 6 tests: abuse & scraping protection, velocity guards, 404 enumeration blocking, rate limiting, and anti-indexing headers."""
from __future__ import annotations

from datetime import timedelta

from config import Config
from monday import create_app, storage
from monday.extensions import db
from monday.models import (
    AuditLog,
    ContentNode,
    Lead,
    Question,
    StudentProfile,
    SubscriptionPlan,
    User,
    utcnow,
)
from monday.public_samples import set_question_public_sample
from monday.subscriptions import grant_manual_subscription

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
        ABUSE_PROTECTION_IN_TESTING = True
        PUBLIC_SITE_ENABLED = True
        PUBLIC_LEGAL_REVIEWED = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'stage6.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        PUBLIC_SAMPLE_MEDIA_FOLDER = str(tmp_path / "public_sample_media")

    for k, v in overrides.items():
        setattr(Cfg, k, v)
    return create_app(Cfg, seed_if_empty=False)


def _login(client, email: str, password: str = "Pass123456!"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=False)


def _seed_student_with_bank_questions(app, count: int = 5):
    with app.app_context():
        topic = ContentNode(code="s6_top", name="Stage 6 Top", level="topic", exams=["ORT"])
        db.session.add(topic)
        db.session.flush()
        sub = ContentNode(code="s6_sub", name="Stage 6 Sub", level="subtopic", parent_id=topic.id, exams=["ORT"])
        db.session.add(sub)
        db.session.flush()
        node = ContentNode(code="s6_alg", name="Stage 6 Algebra", level="node", parent_id=sub.id, exams=["ORT"])
        db.session.add(node)
        db.session.flush()

        admin = User(email="admin@s6.test", name="Admin", role="admin", is_approved=True)
        admin.set_password("StrongAdmin123!")
        student = User(email="student@s6.test", name="Student", role="student", is_approved=True)
        student.set_password("Pass123456!")
        db.session.add_all([admin, student])
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, exam="ORT", onboarded=True))

        plan = SubscriptionPlan(
            code="s6_monthly",
            name="Подписка на банк вопросов",
            duration_days=30,
            price_amount=800,
            currency="USD",
            is_active=True,
        )
        db.session.add(plan)
        db.session.flush()

        grant_manual_subscription(
            admin,
            student,
            plan,
            status="active",
            duration_days=30,
            note="stage6_test",
        )

        saved_img = storage.save("s6-stem.png", PNG_1PX, "image/png")
        qs = []
        for idx in range(count):
            q = Question(
                skill_id=node.id,
                author_id=admin.id,
                text=f"Stage6 Prompt {idx}",
                options=["A", "B", "C", "D"],
                correct="0",
                explanation=f"SECRET_EXPLANATION_MARKER_{idx}",
                answer_type="choice",
                status="published",
                exams=["ORT"],
                image_path=saved_img if idx == 0 else None,
            )
            db.session.add(q)
            qs.append(q)
        db.session.flush()

        set_question_public_sample(qs[0], True)
        sample_key = qs[0].public_image_key
        qids = [q.id for q in qs]
        db.session.commit()
        return {
            "student_email": student.email,
            "qids": qids,
            "sample_key": sample_key,
            "priv_img": saved_img,
        }


def test_question_scrape_velocity_guard_blocks_and_audits(tmp_path):
    app = _make_app(
        tmp_path,
        QBANK_SCRAPE_WINDOW_SECONDS=60,
        QBANK_SCRAPE_MAX_PER_WINDOW=3,
        QBANK_SCRAPE_MAX_PER_HOUR=10,
    )
    seeded = _seed_student_with_bank_questions(app, count=5)

    client = app.test_client()
    assert _login(client, seeded["student_email"]).status_code == 302

    r_start = client.post("/bank/start", data={"exam": "ORT", "view": "one"}, follow_redirects=False)
    assert r_start.status_code == 302
    play_url = r_start.headers["Location"]

    # First 3 distinct questions pass cleanly
    for i in range(3):
        resp = client.get(f"{play_url}?i={i}")
        assert resp.status_code == 200

    # Revisiting the same 3 questions does not count as new distinct harvests
    for i in range(3):
        resp = client.get(f"{play_url}?i={i}")
        assert resp.status_code == 200

    # 4th distinct question trips the scrape velocity guard
    blocked = client.get(f"{play_url}?i=3")
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") == "60"

    # Second hit in cooldown still returns 429, without audit-log flooding
    blocked_again = client.get(f"{play_url}?i=4")
    assert blocked_again.status_code == 429

    with app.app_context():
        logs = AuditLog.query.filter_by(action="abuse_scrape_velocity_blocked").all()
        assert len(logs) == 1
        assert "bank.play" in str((logs[0].new_value or {}).get("source") or "")


def test_404_enumeration_probe_guard_blocks_public_and_uploads(tmp_path):
    app = _make_app(
        tmp_path,
        ABUSE_404_WINDOW_SECONDS=60,
        ABUSE_404_MAX_PER_WINDOW=4,
    )
    seeded = _seed_student_with_bank_questions(app, count=2)

    anon = app.test_client()
    for i in range(4):
        r = anon.get(f"/question-bank/media/nonexistent_{i}.png")
        assert r.status_code == 404

    blocked_pub = anon.get("/question-bank/media/nonexistent_4.png")
    assert blocked_pub.status_code == 429
    assert blocked_pub.headers.get("Retry-After") == "60"

    with app.app_context():
        pub_logs = AuditLog.query.filter_by(action="abuse_enumeration_blocked").all()
        assert len(pub_logs) == 1

    # Authenticated student probing missing /uploads/ paths hits separate user-scoped probe guard
    student = app.test_client()
    assert _login(student, seeded["student_email"]).status_code == 302
    for i in range(4):
        r = student.get(f"/uploads/questions/missing_{i}.png")
        assert r.status_code == 404

    blocked_up = student.get("/uploads/questions/missing_4.png")
    assert blocked_up.status_code == 429
    assert blocked_up.headers.get("Retry-After") == "60"


def test_rate_limits_and_429_json_vs_html(tmp_path):
    app = _make_app(
        tmp_path,
        RATELIMIT_ENABLED=True,
        RATELIMIT_STORAGE_URI="memory://",
        QBANK_RATE_LIMIT_EXPORT="2 per minute",
        QBANK_RATE_LIMIT_ACTION="2 per minute",
        QBANK_RATE_LIMIT_VIEW="30 per minute",
    )
    seeded = _seed_student_with_bank_questions(app, count=3)
    client = app.test_client()
    assert _login(client, seeded["student_email"]).status_code == 302

    # Export limit (HTML 429 response)
    assert client.get("/profile/export.csv").status_code == 200
    assert client.get("/profile/export.csv").status_code == 200
    r_exp_429 = client.get("/profile/export.csv")
    assert r_exp_429.status_code == 429
    assert int(r_exp_429.headers.get("Retry-After") or "0") > 0
    assert "text/html" in (r_exp_429.headers.get("Content-Type") or "")

    # Action limit returning JSON 429 when Accept/X-Requested-With indicates JSON/fetch
    r_start = client.post("/bank/start", data={"exam": "ORT", "view": "one"}, follow_redirects=False)
    assert r_start.status_code == 302
    att_url = r_start.headers["Location"]
    for _ in range(2):
        assert client.post(
            f"{att_url}/check",
            data={"i": "0", "given": "0"},
            headers={"Accept": "application/json"},
        ).status_code == 200
    r_json_429 = client.post(
        f"{att_url}/check",
        data={"i": "0", "given": "0"},
        headers={"Accept": "application/json"},
    )
    assert r_json_429.status_code == 429
    assert int(r_json_429.headers.get("Retry-After") or "0") > 0
    payload = r_json_429.get_json()
    assert payload == {"ok": False, "error": "too_many_requests"}


def test_anti_indexing_and_no_cache_headers_on_gated_routes(tmp_path):
    app = _make_app(tmp_path)
    seeded = _seed_student_with_bank_questions(app, count=2)
    client = app.test_client()

    # Public routes remain indexable
    r_pub = client.get("/question-bank")
    assert r_pub.status_code == 200
    assert "noindex" not in (r_pub.headers.get("X-Robots-Tag") or "").lower()

    r_media = client.get(f"/question-bank/media/{seeded['sample_key']}")
    assert r_media.status_code == 200
    assert "noindex" not in (r_media.headers.get("X-Robots-Tag") or "").lower()
    assert "public" in (r_media.headers.get("Cache-Control") or "").lower()

    # Logged-in gated routes carry X-Robots-Tag noindex/nofollow/noarchive and private cache control
    assert _login(client, seeded["student_email"]).status_code == 302
    for path in ("/bank/", "/sessions", "/formulas"):
        r = client.get(path)
        assert r.status_code == 200
        robots = (r.headers.get("X-Robots-Tag") or "").lower()
        cache = (r.headers.get("Cache-Control") or "").lower()
        assert "noindex" in robots and "nofollow" in robots and "noarchive" in robots
        assert "private" in cache and "no-store" in cache

    r_up = client.get(f"/uploads/{seeded['priv_img']}")
    assert r_up.status_code == 200
    robots_up = (r_up.headers.get("X-Robots-Tag") or "").lower()
    cache_up = (r_up.headers.get("Cache-Control") or "").lower()
    assert "noindex" in robots_up and "nofollow" in robots_up and "noarchive" in robots_up
    assert "private" in cache_up and "public" not in cache_up


def test_no_pre_leaked_answers_in_interactive_question_templates(tmp_path):
    app = _make_app(tmp_path)
    seeded = _seed_student_with_bank_questions(app, count=3)
    client = app.test_client()
    assert _login(client, seeded["student_email"]).status_code == 302

    # Bank single-question play & booklet sheet before answering
    r_start = client.post("/bank/start", data={"exam": "ORT", "view": "one"}, follow_redirects=False)
    assert r_start.status_code == 302
    play_url = r_start.headers["Location"]

    r_play = client.get(play_url)
    assert r_play.status_code == 200
    play_html = r_play.get_data(as_text=True)
    assert "SECRET_EXPLANATION_MARKER_" not in play_html

    r_sheet = client.get(f"{play_url}/sheet")
    assert r_sheet.status_code == 200
    sheet_html = r_sheet.get_data(as_text=True)
    assert "SECRET_EXPLANATION_MARKER_" not in sheet_html

    # Timed practice session before answering
    r_sess = client.post("/sessions/start/sprint", data={"exam": "ORT"}, follow_redirects=False)
    assert r_sess.status_code == 302
    r_sess_play = client.get(r_sess.headers["Location"])
    assert r_sess_play.status_code == 200
    sess_html = r_sess_play.get_data(as_text=True)
    assert "SECRET_EXPLANATION_MARKER_" not in sess_html


def test_public_apply_honeypot_and_rate_limit(tmp_path):
    app = _make_app(
        tmp_path,
        RATELIMIT_ENABLED=True,
        RATELIMIT_STORAGE_URI="memory://",
    )
    client = app.test_client()

    # Bot filling honeypot `website` gets silent 200 and no DB lead
    r_bot = client.post(
        "/apply",
        data={
            "full_name": "Spam Bot",
            "phone": "+996700000001",
            "website": "https://spam.example",
        },
    )
    assert r_bot.status_code == 200
    with app.app_context():
        assert Lead.query.count() == 0

    # Normal POST submissions hit the existing 5/minute limit on /apply
    for i in range(4):
        r_ok = client.post(
            "/apply",
            data={"full_name": f"Applicant {i}", "phone": f"+99670011223{i}"},
            follow_redirects=False,
        )
        assert r_ok.status_code in (200, 302)

    r_429 = client.post(
        "/apply",
        data={"full_name": "Applicant 5", "phone": "+996700112299"},
        follow_redirects=False,
    )
    assert r_429.status_code == 429
    assert int(r_429.headers.get("Retry-After") or "0") > 0

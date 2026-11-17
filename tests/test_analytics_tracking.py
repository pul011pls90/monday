"""Tests for Step 2: Analytics tracking middleware, GeoIP, IP hashing, UA parsing, and exclusions."""
import os
import tempfile
from datetime import timedelta

from config import Config


def _make_app():
    tmp = tempfile.mkdtemp()

    class TrackingTestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "tracking_test.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")
        SERVER_NAME = "localhost"

    from monday import create_app
    return create_app(TrackingTestConfig)


def test_user_agent_parser_variants():
    from monday.analytics_tracking import parse_user_agent

    assert parse_user_agent(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ) == ("mobile", "iOS", "Safari")

    assert parse_user_agent(
        "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/119.0 Mobile/15E148 Safari/604.1"
    ) == ("tablet", "iOS", "Chrome")

    assert parse_user_agent(
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    ) == ("mobile", "Android", "Chrome")

    assert parse_user_agent(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    ) == ("desktop", "Windows", "Edge")

    assert parse_user_agent(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/121.0"
    ) == ("desktop", "macOS", "Firefox")


def test_tracking_lifecycle_exclusions_and_login_linking():
    from monday.analytics_tracking import VISITOR_COOKIE_NAME
    from monday.models import PageView, StudentProfile, User, Visit, db

    app = _make_app()
    with app.app_context():
        student = User(email="stu@monday.kg", name="Студент Тест", role="student", language="ru")
        student.set_password("pass123")
        student.profile = StudentProfile(exam="ORT", region="Бишкек", onboarded=True)
        admin = User(email="adm@monday.kg", name="Админ", role="admin", language="ru")
        admin.set_password("pass123")
        db.session.add_all([student, admin])
        db.session.commit()
        student_id = student.id
        admin_id = admin.id

    c = app.test_client()
    ua_desktop = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
    raw_ip = "203.0.113.42"

    # 1. Anonymous visit on /login with Geo headers and referer
    r1 = c.get(
        "/login",
        headers={
            "User-Agent": ua_desktop,
            "X-Forwarded-For": raw_ip,
            "CF-IPCountry": "KG",
            "CF-IPCity": "Bishkek",
            "Referer": "https://t.me/monday_edu",
        },
    )
    assert r1.status_code == 200
    assert VISITOR_COOKIE_NAME in r1.headers.get("Set-Cookie", "")

    with app.app_context():
        visits = Visit.query.all()
        assert len(visits) == 1
        v = visits[0]
        assert v.user_id is None
        assert v.country == "KG"
        assert v.city == "Bishkek"
        assert v.device_type == "desktop"
        assert v.os == "macOS"
        assert v.browser == "Chrome"
        assert v.referer == "https://t.me/monday_edu"
        assert v.ip_hash and raw_ip not in v.ip_hash and len(v.ip_hash) == 64
        assert v.page_count == 1
        pvs = PageView.query.filter_by(visit_id=v.id).order_by(PageView.created_at.asc()).all()
        assert len(pvs) == 1 and pvs[0].path == "/login"
        # Backdate first pageview by 15s to verify time_spent_seconds computation on next hit
        pvs[0].created_at = pvs[0].created_at - timedelta(seconds=15)
        db.session.commit()
        v_id = v.id

    # 2. Second anonymous hit on /about reuses Visit & updates time_spent_seconds
    r2 = c.get("/about", headers={"User-Agent": ua_desktop})
    assert r2.status_code == 200
    with app.app_context():
        assert Visit.query.count() == 1
        v = db.session.get(Visit, v_id)
        assert v.page_count == 2
        pvs = PageView.query.filter_by(visit_id=v_id).order_by(PageView.created_at.asc()).all()
        assert len(pvs) == 2
        assert pvs[0].time_spent_seconds >= 14
        assert pvs[1].path == "/about"
        assert pvs[1].time_spent_seconds == 0

    # 3. Exclusions: static, api, bots must NOT create visits or pageviews
    assert c.get("/static/css/brand.css").status_code == 200
    assert c.get("/api/version").status_code == 200
    assert c.get("/login", headers={"User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"}).status_code == 200
    with app.app_context():
        assert Visit.query.count() == 1
        assert PageView.query.count() == 2

    # 4. Login links the active anonymous Visit to the student user
    r_login = c.post("/login", data={"email": "stu@monday.kg", "password": "pass123"}, follow_redirects=True, headers={"User-Agent": ua_desktop})
    assert r_login.status_code == 200
    with app.app_context():
        v = db.session.get(Visit, v_id)
        assert v.user_id == student_id
        assert v.page_count == 3  # /home tracked after redirect

    # 5. Session timeout (> 30 min) creates a new Visit
    with app.app_context():
        v = db.session.get(Visit, v_id)
        v.ended_at = v.ended_at - timedelta(minutes=35)
        db.session.commit()

    assert c.get("/about", headers={"User-Agent": ua_desktop}).status_code == 200
    with app.app_context():
        assert Visit.query.count() == 2

    # 6. Interactive POST heartbeat for logged-in student keeps Visit online without adding PageView noise
    with app.app_context():
        pvs_before = PageView.query.count()
        visits_before = Visit.query.count()
    r_hb = c.post("/goal", data={"goal_score": "195"}, headers={"User-Agent": ua_desktop})
    assert r_hb.status_code in (200, 302)
    with app.app_context():
        assert Visit.query.count() == visits_before
        assert PageView.query.count() == pvs_before

    # 7. Admin user browsing must NOT be tracked at all; Admin /teacher/bank shares student design
    adm_client = app.test_client()
    with adm_client.session_transaction() as sess:
        sess["_user_id"] = str(admin_id)
    assert adm_client.get("/admin/").status_code == 200
    r_tbank = adm_client.get("/teacher/bank")
    assert r_tbank.status_code == 200
    tbank_html = r_tbank.data.decode("utf-8")
    assert "page-sky" in tbank_html and "bk-filter-box" in tbank_html and "Фильтры" in tbank_html
    assert adm_client.get("/about").status_code == 200
    with app.app_context():
        assert Visit.query.count() == visits_before
        assert Visit.query.filter_by(user_id=admin_id).count() == 0

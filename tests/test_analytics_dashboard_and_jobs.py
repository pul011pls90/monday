"""End-to-end tests for Steps 3, 4, and 5: Analytics APIs, UI, Live Feed, Drawer, CSV, and Daily Cron Job."""
import os
import tempfile
from datetime import timedelta

from config import Config


def _make_app():
    tmp = tempfile.mkdtemp()

    class FullAnalyticsConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "full_analytics.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")
        SERVER_NAME = "localhost"

    from monday import create_app
    return create_app(FullAnalyticsConfig)


def _seed_analytics_fixture(app):
    from monday.models import (
        Attempt,
        AttemptAnswer,
        PageView,
        StudentProfile,
        StudentRecord,
        User,
        Visit,
        db,
        utcnow,
    )

    now = utcnow()
    with app.app_context():
        admin = User(email="admin@monday.kg", name="Admin User", role="admin", language="ru")
        admin.set_password("pw")

        teacher = User(email="teacher@monday.kg", name="Айбек Мугалим", role="teacher", language="ru", is_approved=True)
        teacher.set_password("pw")

        student = User(email="aliya@monday.kg", name="Алия Кайратова", role="student", language="ru")
        student.set_password("pw")
        student.profile = StudentProfile(
            exam="ORT",
            goal_score=200,
            grade="11",
            country="Кыргызстан",
            region="Бишкек",
            school="Школа №61",
            onboarded=True,
        )

        db.session.add_all([admin, teacher, student])
        db.session.flush()

        rec = StudentRecord(teacher_id=teacher.id, name=student.name, exam="ORT", student_user_id=student.id)
        db.session.add(rec)

        # Learning data for student: 1 attempt, 2 answers (1 correct, 1 wrong -> 50% accuracy)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        att_start = max(today_start, now - timedelta(hours=2))
        att_end = max(today_start, now - timedelta(hours=1))
        att = Attempt(user_id=student.id, mode="franklin", started_at=att_start, finished_at=att_end, score=1, total=2)
        db.session.add(att)
        db.session.flush()
        db.session.add_all([
            AttemptAnswer(attempt_id=att.id, question_id=1, is_correct=True, answered_at=att_end),
            AttemptAnswer(attempt_id=att.id, question_id=2, is_correct=False, answered_at=att_end),
        ])

        # Two visits for student (returning visitor!)
        v1 = Visit(
            session_cookie_id="cookie-student-1",
            user_id=student.id,
            ip_hash="h1",
            country="KG",
            city="Bishkek",
            device_type="mobile",
            os="iOS",
            browser="Safari",
            language="ru",
            started_at=now - timedelta(days=3, minutes=10),
            ended_at=now - timedelta(days=3),
            page_count=2,
        )
        v2 = Visit(
            session_cookie_id="cookie-student-1",
            user_id=student.id,
            ip_hash="h1",
            country="KG",
            city="Bishkek",
            device_type="desktop",
            os="macOS",
            browser="Chrome",
            language="ru",
            started_at=now - timedelta(minutes=2),
            ended_at=now - timedelta(seconds=30),
            page_count=1,
        )
        # Anonymous online visit
        v3 = Visit(
            session_cookie_id="cookie-anon-live",
            user_id=None,
            ip_hash="h2",
            country="KZ",
            city="Almaty",
            device_type="desktop",
            os="Windows",
            browser="Edge",
            language="kk",
            referer="https://google.com",
            started_at=now - timedelta(minutes=3),
            ended_at=now - timedelta(seconds=10),
            page_count=1,
        )
        # Old anonymous visit with stale PageView (> 90 days)
        v_old = Visit(
            session_cookie_id="cookie-anon-old",
            user_id=None,
            ip_hash="h3",
            country="UZ",
            city="Tashkent",
            device_type="tablet",
            os="Android",
            browser="Chrome",
            language="uz",
            started_at=now - timedelta(days=95),
            ended_at=now - timedelta(days=95),
            page_count=1,
        )
        db.session.add_all([v1, v2, v3, v_old])
        db.session.flush()

        db.session.add_all([
            PageView(visit_id=v1.id, path="/home", created_at=v1.started_at, time_spent_seconds=300),
            PageView(visit_id=v1.id, path="/bank", created_at=v1.ended_at, time_spent_seconds=0),
            PageView(visit_id=v2.id, path="/sessions", created_at=v2.started_at, time_spent_seconds=90),
            PageView(visit_id=v3.id, path="/login", created_at=v3.started_at, time_spent_seconds=0),
            PageView(visit_id=v_old.id, path="/about", created_at=v_old.started_at, time_spent_seconds=45),
        ])
        db.session.commit()

        return {
            "admin_id": admin.id,
            "student_id": student.id,
            "anon_visit_id": v3.id,
        }


def test_analytics_permissions_and_ui_rendering():
    app = _make_app()
    ids = _seed_analytics_fixture(app)

    anon = app.test_client()
    assert anon.get("/admin/analytics/").status_code == 302
    assert anon.get("/admin/analytics/api/summary").status_code == 302

    stu = app.test_client()
    with stu.session_transaction() as sess:
        sess["_user_id"] = str(ids["student_id"])
    assert stu.get("/admin/analytics/").status_code == 403
    assert stu.get("/admin/analytics/api/visits").status_code == 403
    assert stu.get("/admin/analytics/export.csv").status_code == 403
    assert stu.post(f"/admin/analytics/api/user/{ids['student_id']}/block").status_code == 403

    adm = app.test_client()
    with adm.session_transaction() as sess:
        sess["_user_id"] = str(ids["admin_id"])

    # Admin dashboard shares Student .page-sky aesthetic and links to analytics
    r_adm = adm.get("/admin/")
    assert r_adm.status_code == 200
    adm_html = r_adm.data.decode("utf-8")
    assert "page-sky" in adm_html
    assert "/admin/analytics/" in adm_html

    # Admin left rail keeps all 8 Admin items in priority order (native Student .rail) + Настройки,
    # without УПРАВЛЕНИЕ/КОНТЕНТ headings and while leaving .acct-menu clean.
    rail_chunk = adm_html.split('<nav class="rail"')[1].split("</nav>")[0]
    for admin_label in ("Админ", "Аналитика", "CRM", "Расписание", "Модерация", "Правки", "Вопросы", "Карта", "Настройки"):
        assert admin_label in rail_chunk
    assert "УПРАВЛЕНИЕ" not in rail_chunk and "КОНТЕНТ" not in rail_chunk
    acct_chunk = adm_html.split('<details class="acct-menu"')[1].split("</details>")[0]
    assert "Администратор" in acct_chunk
    assert "Карта" not in acct_chunk and "Модерация" not in acct_chunk

    # Student login records LoginEvent + login_count and shows in /admin/ panel
    stu_login = app.test_client()
    r_sl = stu_login.post(
        "/login",
        data={"email": "aliya@monday.kg", "password": "pw"},
        headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148 Safari/604.1"},
    )
    assert r_sl.status_code == 302
    r_adm_stu = adm.get(f"/admin/?tab=students&user={ids['student_id']}")
    assert r_adm_stu.status_code == 200
    adm_stu_html = r_adm_stu.data.decode("utf-8")
    assert "Всего входов" in adm_stu_html
    assert "История входов" in adm_stu_html
    assert "mobile" in adm_stu_html and "iOS" in adm_stu_html and "Safari" in adm_stu_html

    r_acc = adm.get("/teacher/account")
    assert r_acc.status_code == 200
    acc_html = r_acc.data.decode("utf-8")
    assert "Инструменты и разделы" in acc_html
    assert "/admin/analytics/" in acc_html

    # /teacher/students as Admin renders "Пользователи" sorted by role with auth method and seen page
    r_users = adm.get("/teacher/students")
    assert r_users.status_code == 200
    u_html = r_users.data.decode("utf-8")
    assert "Пользователи" in u_html
    assert "Способ входа" in u_html
    assert "Какую страницу видит" in u_html
    assert "Алия Кайратова" in u_html and "Айбек Мугалим" in u_html and "Admin User" in u_html
    tbody = u_html.split("<tbody>")[1].split("</tbody>")[0]
    assert tbody.index("Алия Кайратова") < tbody.index("Айбек Мугалим") < tbody.index("Admin User")
    assert adm.get("/teacher/students?role=teacher").status_code == 200

    r_dash = adm.get("/admin/analytics/")
    assert r_dash.status_code == 200
    html = r_dash.data.decode("utf-8")
    for token in ("page-sky", "an-kpis", "an-daily-chart", "data-heatmap", "data-an-drawer", "Экспорт в CSV", "Лента визитов"):
        assert token in html


def test_analytics_apis_filters_csv_live_drawer_and_daily_job():
    from monday.analytics_jobs import run_daily_analytics_maintenance
    from monday.models import PageView, User, db

    app = _make_app()
    ids = _seed_analytics_fixture(app)

    adm = app.test_client()
    with adm.session_transaction() as sess:
        sess["_user_id"] = str(ids["admin_id"])

    # 1. Summary KPIs + Charts
    r_sum = adm.get("/admin/analytics/api/summary?days=14")
    assert r_sum.status_code == 200
    summary = r_sum.get_json()
    kpis = summary["kpis"]
    assert kpis["online_now"] == 2  # student v2 + anon v3
    assert kpis["visitors_30d"] == 2
    assert kpis["new_registrations_30d"] == 3
    assert kpis["retention_pct"] == 50.0  # 1 returning (student) of 2 recent actors (student + anon_live)

    charts = summary["charts"]
    assert len(charts["daily_series"]) == 14
    assert len(charts["heatmap"]["matrix"]) == 7
    assert len(charts["heatmap"]["matrix"][0]) == 24
    assert charts["heatmap"]["peak"] >= 1

    # 2. Visits Data Grid + Filters (Cyrillic search, kind, device, exam, region, language, status)
    assert adm.get("/admin/analytics/api/visits?kind=registered").get_json()["total"] == 2
    assert adm.get("/admin/analytics/api/visits?kind=anonymous").get_json()["total"] == 2
    assert adm.get("/admin/analytics/api/visits?q=алия").get_json()["total"] == 2
    assert adm.get("/admin/analytics/api/visits?exam=ORT&device=mobile").get_json()["total"] == 1
    assert adm.get("/admin/analytics/api/visits?region=Бишкек&language=ru").get_json()["total"] == 2
    assert adm.get("/admin/analytics/api/visits?status=online").get_json()["total"] == 2

    # 3. CSV Export with filters
    r_csv = adm.get("/admin/analytics/export.csv?kind=anonymous")
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.mimetype
    csv_text = r_csv.data.decode("utf-8-sig")
    assert "Almaty" in csv_text and "Алия" not in csv_text

    # 4. Live Feed
    r_live = adm.get("/admin/analytics/api/live?limit=10")
    assert r_live.status_code == 200
    live_items = r_live.get_json()["items"]
    assert len(live_items) == 4
    assert live_items[0]["last_path"] in ("/login", "/sessions")

    # 5. Slide-out User Drawer & Anonymous Visit Drawer
    r_user = adm.get(f"/admin/analytics/api/user/{ids['student_id']}")
    assert r_user.status_code == 200
    u_data = r_user.get_json()
    assert u_data["profile"]["school"] == "Школа №61"
    assert u_data["profile"]["teachers"] == ["Айбек Мугалим"]
    assert u_data["learning"]["attempts_count"] == 1
    assert u_data["learning"]["answered_questions"] == 2
    assert u_data["learning"]["accuracy_pct"] == 50.0
    assert u_data["learning"]["streak_days"] == 1
    assert len(u_data["timeline"]) == 2
    assert u_data["timeline"][1]["pages"][0]["path"] == "/home"

    r_anon_drawer = adm.get(f"/admin/analytics/api/visit/{ids['anon_visit_id']}")
    assert r_anon_drawer.status_code == 200
    assert r_anon_drawer.get_json()["kind"] == "anonymous_visit"

    # 6. Block / Unblock action & self-block guard
    assert adm.post(f"/admin/analytics/api/user/{ids['admin_id']}/block", json={"blocked": True}).status_code == 400
    r_blk = adm.post(f"/admin/analytics/api/user/{ids['student_id']}/block", json={"blocked": True})
    assert r_blk.status_code == 200 and r_blk.get_json()["is_blocked"] is True
    assert adm.get("/admin/analytics/api/visits?status=blocked").get_json()["total"] == 2
    r_unblk = adm.post(f"/admin/analytics/api/user/{ids['student_id']}/block", json={"blocked": False})
    assert r_unblk.status_code == 200 and r_unblk.get_json()["is_blocked"] is False

    # 7. Step 5: Daily Cron Job (purge > 90 days PageView + update cached User counters)
    with app.app_context():
        assert PageView.query.count() == 5
        job_res = run_daily_analytics_maintenance(retention_days=90)
        assert job_res["deleted_page_views"] == 1  # only 95-day-old PageView deleted
        assert PageView.query.count() == 4
        stu_obj = db.session.get(User, ids["student_id"])
        assert stu_obj.total_visits == 2
        assert stu_obj.average_visit_duration == 345  # avg of 600s and 90s = 345s

    # CLI execution smoke check
    cli_res = app.test_cli_runner().invoke(args=["analytics-daily-job"])
    assert cli_res.exit_code == 0
    assert "Deleted page_views=0" in cli_res.output

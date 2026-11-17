"""Tests for Step 1 of the analytics module: Visit, PageView, User counters, and additive schema migration."""
import os
import tempfile
from datetime import timedelta

from sqlalchemy import inspect, text

from config import Config


def _make_isolated_app():
    tmp = tempfile.mkdtemp()

    class AnalyticsTestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "analytics_test.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")
        SERVER_NAME = "localhost"

    from monday import create_app
    return create_app(AnalyticsTestConfig)


def test_analytics_tables_columns_and_models():
    from monday.analytics_schema import ensure_analytics_schema
    from monday.models import PageView, User, Visit, db, utcnow

    app = _make_isolated_app()
    with app.app_context():
        insp = inspect(db.engine)
        assert "visit" in insp.get_table_names()
        assert "page_view" in insp.get_table_names()

        user_cols = {c["name"] for c in insp.get_columns("user")}
        assert {"total_visits", "average_visit_duration"}.issubset(user_cols)

        # Idempotent re-run must not fail
        ensure_analytics_schema()

        # Anonymous visit + PageViews + duration calculation
        t0 = utcnow()
        t1 = t0 + timedelta(seconds=95)
        anon_visit = Visit(
            session_cookie_id="anon-cookie-uuid",
            ip_hash="sha256-salted-hash",
            country="KG",
            city="Bishkek",
            device_type="mobile",
            os="iOS",
            browser="Safari",
            referer="https://instagram.com",
            language="ru",
            started_at=t0,
            ended_at=t1,
            page_count=2,
        )
        db.session.add(anon_visit)
        db.session.flush()

        assert len(anon_visit.id) == 36
        assert anon_visit.user_id is None
        assert anon_visit.duration_seconds == 95

        pv1 = PageView(visit_id=anon_visit.id, path="/", created_at=t0, time_spent_seconds=40)
        pv2 = PageView(visit_id=anon_visit.id, path="/bank", created_at=t1, time_spent_seconds=55)
        db.session.add_all([pv1, pv2])
        db.session.commit()

        assert len(pv1.id) == 36
        assert anon_visit.page_views[0].path == "/"
        assert anon_visit.page_views[1].path == "/bank"

        # Registered user visit + cached counters
        user = User(email="analytics@monday.kg", name="Test Student", role="student")
        user.set_password("secret123")
        db.session.add(user)
        db.session.flush()
        assert user.total_visits == 0
        assert user.average_visit_duration == 0

        anon_visit.user_id = user.id
        db.session.commit()
        assert user.visits.count() == 1

        # Cascade delete removes associated PageViews
        db.session.delete(anon_visit)
        db.session.commit()
        assert PageView.query.filter_by(visit_id=anon_visit.id).count() == 0


def test_analytics_migration_adds_columns_to_existing_legacy_user_table():
    from monday.analytics_schema import ensure_analytics_schema
    from monday.models import db

    app = _make_isolated_app()
    with app.app_context():
        # Simulate an older user table missing the new columns
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "page_view"'))
            conn.execute(text('DROP TABLE IF EXISTS "visit"'))
            conn.execute(text('ALTER TABLE "user" DROP COLUMN "total_visits"'))
            conn.execute(text('ALTER TABLE "user" DROP COLUMN "average_visit_duration"'))

        ensure_analytics_schema()

        insp = inspect(db.engine)
        assert "visit" in insp.get_table_names()
        assert "page_view" in insp.get_table_names()
        user_cols = {c["name"] for c in insp.get_columns("user")}
        assert {"total_visits", "average_visit_duration"}.issubset(user_cols)

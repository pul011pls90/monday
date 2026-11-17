"""Additive schema migration helper for the analytics module (Visit, PageView, User counters)."""
from __future__ import annotations

from sqlalchemy import inspect, text

from .models import PageView, Visit, db


def ensure_analytics_schema() -> None:
    """Create analytics tables/indexes and add cached visit columns to User if missing.

    Safe to run repeatedly on both SQLite and PostgreSQL without touching existing rows.
    """
    for model in (Visit, PageView):
        model.__table__.create(bind=db.engine, checkfirst=True)

    insp = inspect(db.engine)
    if insp.has_table("user"):
        have = {c["name"] for c in insp.get_columns("user")}
        alters = []
        for col_name, ddl in (
            ("total_visits", "INTEGER NOT NULL DEFAULT 0"),
            ("average_visit_duration", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if col_name not in have:
                alters.append(f'ALTER TABLE "user" ADD COLUMN "{col_name}" {ddl}')
        if alters:
            with db.engine.begin() as conn:
                for stmt in alters:
                    conn.execute(text(stmt))
                conn.execute(text('UPDATE "user" SET total_visits = 0 WHERE total_visits IS NULL'))
                conn.execute(text('UPDATE "user" SET average_visit_duration = 0 WHERE average_visit_duration IS NULL'))

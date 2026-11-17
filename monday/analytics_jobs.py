"""Daily analytics maintenance jobs: 90-day PageView retention purge & User counter aggregation."""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from datetime import datetime, timedelta

from .models import AppMeta, PageView, User, Visit, db, utcnow

log = logging.getLogger(__name__)

RETENTION_DAYS = 90
_META_KEY = "analytics_last_daily_job"


def purge_old_page_views(retention_days: int = RETENTION_DAYS, *, now: datetime | None = None) -> int:
    """Delete PageView rows older than `retention_days` (default 90 days)."""
    now = now or utcnow()
    cutoff = now - timedelta(days=max(1, int(retention_days)))
    deleted = (
        PageView.query.filter(PageView.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.session.commit()
    return int(deleted or 0)


def recalculate_user_visit_counters() -> int:
    """Recompute cached `total_visits` and `average_visit_duration` on all User rows."""
    stats: dict[int, list[int]] = defaultdict(list)
    rows = (
        db.session.query(Visit.user_id, Visit.started_at, Visit.ended_at)
        .filter(Visit.user_id.isnot(None))
        .all()
    )
    for uid, started_at, ended_at in rows:
        dur = 0
        if started_at and ended_at:
            dur = max(0, int((ended_at - started_at).total_seconds()))
        stats[uid].append(dur)

    updated = 0
    for user in User.query.all():
        durations = stats.get(user.id)
        if durations:
            new_total = len(durations)
            new_avg = round(sum(durations) / new_total)
        else:
            new_total = 0
            new_avg = 0

        if user.total_visits != new_total or user.average_visit_duration != new_avg:
            user.total_visits = new_total
            user.average_visit_duration = new_avg
            updated += 1

    db.session.commit()
    return updated


def run_daily_analytics_maintenance(retention_days: int = RETENTION_DAYS, *, now: datetime | None = None) -> dict:
    """Run full daily analytics maintenance (purge stale PageViews + update User visit counters)."""
    now = now or utcnow()
    deleted_pvs = purge_old_page_views(retention_days=retention_days, now=now)
    updated_users = recalculate_user_visit_counters()

    meta = db.session.get(AppMeta, _META_KEY)
    if meta is None:
        meta = AppMeta(key=_META_KEY, value=now.isoformat())
        db.session.add(meta)
    else:
        meta.value = now.isoformat()
    db.session.commit()

    result = {
        "deleted_page_views": deleted_pvs,
        "updated_users": updated_users,
        "ran_at": now.isoformat(),
    }
    log.info("Analytics daily maintenance finished: %s", result)
    return result


def start_daily_maintenance_if_due(app) -> None:
    """Fallback daemon check at startup for hosts without an external cron scheduler."""
    if app.config.get("TESTING") or not app.config.get("ANALYTICS_AUTO_JOB", True):
        return

    try:
        meta = db.session.get(AppMeta, _META_KEY)
        if meta and meta.value:
            last_run = datetime.fromisoformat(meta.value)
            if utcnow() - last_run < timedelta(hours=24):
                return
    except Exception:
        pass

    def _worker():
        with app.app_context():
            try:
                run_daily_analytics_maintenance()
            except Exception as exc:
                db.session.rollback()
                log.warning("Background analytics maintenance failed: %s", exc)

    threading.Thread(target=_worker, daemon=True, name="analytics-daily-job").start()

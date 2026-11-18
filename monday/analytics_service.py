"""Analytics aggregation queries, filtered visits, user learning card data, and CSV export."""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from .models import Attempt, AttemptAnswer, DailyAnswer, LoginEvent, PageView, StudentProfile, StudentRecord, User, Visit, db, utcnow
from .services import progress_summary

ONLINE_WINDOW_MINUTES = 5
WEEKDAY_LABELS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def compute_kpis(now: datetime | None = None) -> dict:
    """Compute top-level KPI metrics for the analytics dashboard."""
    now = now or utcnow()
    online_cutoff = now - timedelta(minutes=ONLINE_WINDOW_MINUTES)
    today_start = datetime(now.year, now.month, now.day)
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)

    online_now = (
        db.session.query(func.count(func.distinct(Visit.session_cookie_id)))
        .filter(Visit.ended_at >= online_cutoff)
        .scalar()
        or 0
    )

    visitors_today = (
        db.session.query(func.count(func.distinct(Visit.session_cookie_id)))
        .filter(Visit.started_at >= today_start)
        .scalar()
        or 0
    )
    visits_today = Visit.query.filter(Visit.started_at >= today_start).count()

    visitors_7d = (
        db.session.query(func.count(func.distinct(Visit.session_cookie_id)))
        .filter(Visit.started_at >= d7)
        .scalar()
        or 0
    )
    visitors_30d = (
        db.session.query(func.count(func.distinct(Visit.session_cookie_id)))
        .filter(Visit.started_at >= d30)
        .scalar()
        or 0
    )

    new_reg_today = User.query.filter(User.created_at >= today_start).count()
    new_reg_7d = User.query.filter(User.created_at >= d7).count()
    new_reg_30d = User.query.filter(User.created_at >= d30).count()

    # Retention (30 days): share of visitors (by user_id if logged in, else session_cookie_id) with >= 2 visits
    recent_rows = (
        db.session.query(Visit.user_id, Visit.session_cookie_id)
        .filter(Visit.started_at >= d30)
        .all()
    )
    actor_counts: Counter = Counter()
    for uid, cid in recent_rows:
        actor_key = f"u:{uid}" if uid is not None else f"c:{cid}"
        actor_counts[actor_key] += 1
    total_actors = len(actor_counts)
    returning_actors = sum(1 for cnt in actor_counts.values() if cnt >= 2)
    retention_pct = round(100.0 * returning_actors / total_actors, 1) if total_actors else 0.0

    return {
        "online_now": online_now,
        "visitors_today": visitors_today,
        "visits_today": visits_today,
        "visitors_7d": visitors_7d,
        "visitors_30d": visitors_30d,
        "new_registrations_today": new_reg_today,
        "new_registrations_7d": new_reg_7d,
        "new_registrations_30d": new_reg_30d,
        "retention_pct": retention_pct,
        "returning_visitors": returning_actors,
        "total_visitors_30d": total_actors,
    }


def compute_charts(days: int = 30, date_from: str | None = None, date_to: str | None = None) -> dict:
    """Build daily line-chart series and 7x24 weekday-hour activity heatmap."""
    now = utcnow()
    today = now.date()
    d_to = _parse_date(date_to) or today
    d_from = _parse_date(date_from)
    if d_from is None:
        days = max(1, min(int(days or 30), 365))
        d_from = d_to - timedelta(days=days - 1)
    if d_from > d_to:
        d_from, d_to = d_to, d_from

    start_dt = datetime(d_from.year, d_from.month, d_from.day)
    end_dt = datetime(d_to.year, d_to.month, d_to.day, 23, 59, 59, 999999)

    rows = (
        db.session.query(Visit.started_at, Visit.session_cookie_id, Visit.user_id, Visit.device_type, Visit.country)
        .filter(Visit.started_at >= start_dt, Visit.started_at <= end_dt)
        .all()
    )

    per_day_visits: Counter = Counter()
    per_day_reg: Counter = Counter()
    per_day_anon: Counter = Counter()
    per_day_cookies: dict[date, set[str]] = defaultdict(set)
    heatmap = [[0] * 24 for _ in range(7)]
    devices: Counter = Counter()
    countries: Counter = Counter()

    for started_at, cid, uid, dev, country in rows:
        if started_at is None:
            continue
        day = started_at.date()
        per_day_visits[day] += 1
        if uid is not None:
            per_day_reg[day] += 1
        else:
            per_day_anon[day] += 1
        per_day_cookies[day].add(cid)
        heatmap[started_at.weekday()][started_at.hour] += 1
        devices[dev or "desktop"] += 1
        if country:
            countries[country] += 1

    span = (d_to - d_from).days + 1
    daily_series = []
    for i in range(span):
        d = d_from + timedelta(days=i)
        daily_series.append({
            "date": d.isoformat(),
            "label": d.strftime("%d.%m"),
            "visits": per_day_visits[d],
            "unique_visitors": len(per_day_cookies[d]),
            "registered": per_day_reg[d],
            "anonymous": per_day_anon[d],
        })

    peak_cell = max((cell for row in heatmap for cell in row), default=0)

    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "daily_series": daily_series,
        "heatmap": {
            "days": WEEKDAY_LABELS_RU,
            "matrix": heatmap,
            "peak": peak_cell,
        },
        "devices": {
            "desktop": devices["desktop"],
            "mobile": devices["mobile"],
            "tablet": devices["tablet"],
        },
        "top_countries": [{"country": k, "count": v} for k, v in countries.most_common(8)],
    }


def _visit_row_dict(v: Visit, online_cutoff: datetime) -> dict:
    u = v.user
    p = u.profile if u else None
    is_anon = u is None
    return {
        "visit_id": v.id,
        "session_cookie_id": v.session_cookie_id[:8] if v.session_cookie_id else "",
        "is_anonymous": is_anon,
        "is_online": bool(v.ended_at and v.ended_at >= online_cutoff),
        "user_id": u.id if u else None,
        "user_name": u.name if u else "Аноним",
        "user_email": u.email if u else "",
        "user_initials": u.initials if u else "?",
        "role": u.role if u else "anonymous",
        "exam": p.exam if p else None,
        "region": (p.region if p and p.region else None),
        "language": (u.language if u else v.language) or "",
        "is_blocked": bool(u.is_blocked) if u else False,
        "is_approved": bool(u.is_approved) if u else True,
        "country": v.country or "",
        "city": v.city or "",
        "device_type": v.device_type or "desktop",
        "os": v.os or "",
        "browser": v.browser or "",
        "referer": v.referer or "",
        "started_at": v.started_at.isoformat() if v.started_at else "",
        "ended_at": v.ended_at.isoformat() if v.ended_at else "",
        "duration_seconds": v.duration_seconds,
        "page_count": v.page_count or 0,
    }


def query_filtered_visits(args, page: int = 1, per_page: int = 25, paginate: bool = True) -> dict:
    """Filter visits by tab kind, user attributes, geo, device, status, date range, and search query."""
    now = utcnow()
    online_cutoff = now - timedelta(minutes=ONLINE_WINDOW_MINUTES)

    kind = (args.get("kind") or "all").strip().lower()
    role = (args.get("role") or "").strip().lower()
    exam = (args.get("exam") or "").strip()
    region = (args.get("region") or "").strip()
    language = (args.get("language") or "").strip().lower()
    device = (args.get("device") or "").strip().lower()
    status = (args.get("status") or "").strip().lower()
    q = (args.get("q") or "").strip().casefold()
    d_from = _parse_date(args.get("date_from"))
    d_to = _parse_date(args.get("date_to"))

    query = (
        Visit.query.options(joinedload(Visit.user).joinedload(User.profile))
        .order_by(Visit.started_at.desc())
    )

    if kind == "registered":
        query = query.filter(Visit.user_id.isnot(None))
    elif kind == "anonymous":
        query = query.filter(Visit.user_id.is_(None))

    if device in ("desktop", "mobile", "tablet"):
        query = query.filter(Visit.device_type == device)

    if d_from is not None:
        query = query.filter(Visit.started_at >= datetime(d_from.year, d_from.month, d_from.day))
    if d_to is not None:
        query = query.filter(Visit.started_at <= datetime(d_to.year, d_to.month, d_to.day, 23, 59, 59, 999999))

    if status == "online":
        query = query.filter(Visit.ended_at >= online_cutoff)

    # Apply SQL-free attribute filters (accurate Cyrillic casefold + profile joins without duplicate rows)
    rows = query.all()
    filtered: list[Visit] = []
    for v in rows:
        u = v.user
        p = u.profile if u else None

        if role:
            if u is None or u.role != role:
                continue
        if exam:
            if p is None or p.exam != exam:
                continue
        if region:
            reg_low = region.casefold()
            u_reg = (p.region or "").casefold() if p else ""
            v_country = (v.country or "").casefold()
            v_city = (v.city or "").casefold()
            if reg_low not in (u_reg, v_country, v_city):
                continue
        if language:
            v_lang = ((u.language if u else v.language) or "").lower()
            if v_lang != language:
                continue
        if status == "blocked":
            if u is None or not u.is_blocked:
                continue
        elif status == "active":
            if u is not None and u.is_blocked:
                continue
        elif status == "pending":
            if u is None or u.is_approved:
                continue
        if q:
            haystack = " ".join(
                filter(None, [
                    u.name if u else "аноним",
                    u.email if u else "",
                    v.country or "",
                    v.city or "",
                ])
            ).casefold()
            if q not in haystack:
                continue
        filtered.append(v)

    total = len(filtered)
    if paginate:
        per_page = max(1, min(int(per_page or 25), 100))
        pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(int(page or 1), pages))
        shown = filtered[(page - 1) * per_page : page * per_page]
    else:
        pages = 1
        page = 1
        shown = filtered

    # Facets for filter dropdowns
    regions_set = sorted(
        {
            r[0].strip()
            for r in db.session.query(StudentProfile.region).filter(StudentProfile.region.isnot(None)).all()
            if r[0] and r[0].strip()
        }
    )
    countries_set = sorted(
        {
            c[0].strip()
            for c in db.session.query(Visit.country).filter(Visit.country.isnot(None)).all()
            if c[0] and c[0].strip()
        }
    )
    langs_set = sorted(
        {
            l[0].strip().lower()
            for l in db.session.query(Visit.language).filter(Visit.language.isnot(None)).all()
            if l[0] and l[0].strip()
        }
        | {
            l[0].strip().lower()
            for l in db.session.query(User.language).filter(User.language.isnot(None)).all()
            if l[0] and l[0].strip()
        }
    )

    return {
        "items": [_visit_row_dict(v, online_cutoff) for v in shown],
        "total": total,
        "page": page,
        "pages": pages,
        "per_page": per_page if paginate else total,
        "facets": {
            "regions": regions_set,
            "countries": countries_set,
            "languages": langs_set,
        },
    }


def _csv_safe(val) -> str:
    s = "" if val is None else str(val)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def export_visits_csv(args) -> str:
    """Build UTF-8 CSV report matching the current grid filters."""
    result = query_filtered_visits(args, paginate=False)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Visit ID",
        "Тип",
        "Имя",
        "Email",
        "Роль",
        "Экзамен",
        "Регион",
        "Страна",
        "Город",
        "Язык",
        "Устройство",
        "ОС",
        "Браузер",
        "Начало (UTC)",
        "Окончание (UTC)",
        "Длительность (сек)",
        "Страниц",
        "Источник",
    ])
    for it in result["items"]:
        writer.writerow([
            _csv_safe(it["visit_id"]),
            "Анонимный" if it["is_anonymous"] else "Зарегистрированный",
            _csv_safe(it["user_name"]),
            _csv_safe(it["user_email"]),
            _csv_safe(it["role"]),
            _csv_safe(it["exam"] or ""),
            _csv_safe(it["region"] or ""),
            _csv_safe(it["country"] or ""),
            _csv_safe(it["city"] or ""),
            _csv_safe(it["language"] or ""),
            _csv_safe(it["device_type"]),
            _csv_safe(it["os"]),
            _csv_safe(it["browser"]),
            _csv_safe(it["started_at"]),
            _csv_safe(it["ended_at"]),
            it["duration_seconds"],
            it["page_count"],
            _csv_safe(it["referer"]),
        ])
    return "\ufeff" + buf.getvalue()


def get_live_feed(limit: int = 40, kind: str = "all") -> list[dict]:
    """Return latest visits in reverse chronological order with their latest page view."""
    now = utcnow()
    online_cutoff = now - timedelta(minutes=ONLINE_WINDOW_MINUTES)
    limit = max(1, min(int(limit or 40), 100))

    q = Visit.query.options(joinedload(Visit.user).joinedload(User.profile)).order_by(Visit.ended_at.desc())
    if kind == "registered":
        q = q.filter(Visit.user_id.isnot(None))
    elif kind == "anonymous":
        q = q.filter(Visit.user_id.is_(None))
    visits = q.limit(limit).all()

    visit_ids = [v.id for v in visits]
    latest_pv_map: dict[str, PageView] = {}
    if visit_ids:
        pvs = (
            PageView.query.filter(PageView.visit_id.in_(visit_ids))
            .order_by(PageView.created_at.desc())
            .all()
        )
        for pv in pvs:
            if pv.visit_id not in latest_pv_map:
                latest_pv_map[pv.visit_id] = pv

    out = []
    for v in visits:
        row = _visit_row_dict(v, online_cutoff)
        lp = latest_pv_map.get(v.id)
        row["last_path"] = lp.path if lp else "/"
        row["last_time_spent"] = lp.time_spent_seconds if lp else 0
        out.append(row)
    return out


def _user_streak_days(user_id: int) -> int:
    """Compute consecutive days of learning activity ending today or yesterday."""
    days_active: set[date] = set()
    for (dt,) in db.session.query(Attempt.started_at).filter(Attempt.user_id == user_id).all():
        if dt:
            days_active.add(dt.date())
    for (dt,) in (
        db.session.query(AttemptAnswer.answered_at)
        .join(Attempt, Attempt.id == AttemptAnswer.attempt_id)
        .filter(Attempt.user_id == user_id)
        .all()
    ):
        if dt:
            days_active.add(dt.date())
    for (dt,) in db.session.query(DailyAnswer.answered_at).filter(DailyAnswer.user_id == user_id).all():
        if dt:
            days_active.add(dt.date())

    if not days_active:
        return 0
    today = utcnow().date()
    cursor = today if today in days_active else (today - timedelta(days=1))
    if cursor not in days_active:
        return 0
    streak = 0
    while cursor in days_active:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def get_user_drawer_detail(user_id: int) -> dict | None:
    """Full profile, aggregated learning stats, and visit/pageview timeline for slide-out drawer."""
    u = db.session.get(User, user_id)
    if u is None:
        return None
    p = u.profile

    teachers = [
        r.teacher.name
        for r in StudentRecord.query.filter_by(student_user_id=u.id).all()
        if r.teacher
    ]

    # Learning statistics aggregated from existing models
    attempts_count = Attempt.query.filter_by(user_id=u.id).count()
    finished_attempts = Attempt.query.filter(Attempt.user_id == u.id, Attempt.finished_at.isnot(None)).count()

    att_answers = (
        db.session.query(AttemptAnswer.is_correct)
        .join(Attempt, Attempt.id == AttemptAnswer.attempt_id)
        .filter(Attempt.user_id == u.id)
        .all()
    )
    daily_answers = db.session.query(DailyAnswer.is_correct).filter(DailyAnswer.user_id == u.id).all()
    all_answers = att_answers + daily_answers
    answered_questions = len(all_answers)
    correct_answers = sum(1 for (ok,) in all_answers if ok is True)
    accuracy_pct = round(100.0 * correct_answers / answered_questions, 1) if answered_questions else 0.0

    streak_days = _user_streak_days(u.id)
    summary = progress_summary(u.id, p.exam) if (u.role == "student" and p and p.exam) else None

    # Visit + PageView timeline
    user_visits = (
        Visit.query.options(joinedload(Visit.page_views))
        .filter(Visit.user_id == u.id)
        .order_by(Visit.started_at.desc())
        .limit(20)
        .all()
    )
    now = utcnow()
    online_cutoff = now - timedelta(minutes=ONLINE_WINDOW_MINUTES)

    timeline = []
    for v in user_visits:
        timeline.append({
            "visit_id": v.id,
            "started_at": v.started_at.isoformat() if v.started_at else "",
            "ended_at": v.ended_at.isoformat() if v.ended_at else "",
            "duration_seconds": v.duration_seconds,
            "page_count": v.page_count or 0,
            "is_online": bool(v.ended_at and v.ended_at >= online_cutoff),
            "country": v.country or "",
            "city": v.city or "",
            "device_type": v.device_type or "desktop",
            "os": v.os or "",
            "browser": v.browser or "",
            "referer": v.referer or "",
            "pages": [
                {
                    "path": pv.path,
                    "created_at": pv.created_at.isoformat() if pv.created_at else "",
                    "time_spent_seconds": pv.time_spent_seconds or 0,
                }
                for pv in v.page_views[:50]
            ],
        })

    live_total_visits = u.visits.count()
    live_avg_dur = (
        round(sum(v.duration_seconds for v in user_visits) / len(user_visits))
        if user_visits
        else 0
    )
    recent_logins = [
        {
            "auth_provider": le.auth_provider,
            "device_type": le.device_type,
            "os": le.os or "",
            "browser": le.browser or "",
            "country": le.country or "",
            "city": le.city or "",
            "created_at": le.created_at.isoformat() if le.created_at else "",
        }
        for le in LoginEvent.query.filter_by(user_id=u.id).order_by(LoginEvent.created_at.desc()).limit(8).all()
    ]

    return {
        "kind": "user",
        "profile": {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "initials": u.initials,
            "role": u.role,
            "auth_provider": u.auth_provider or "password",
            "login_count": u.login_count or 0,
            "recent_logins": recent_logins,
            "language": u.language,
            "is_blocked": bool(u.is_blocked),
            "is_approved": bool(u.is_approved),
            "created_at": u.created_at.isoformat() if u.created_at else "",
            "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else "",
            "total_visits": u.total_visits or live_total_visits,
            "average_visit_duration": u.average_visit_duration or live_avg_dur,
            "school": (p.school if p else None) or "",
            "grade": (p.grade if p else None) or "",
            "exam": (p.exam if p else None) or "",
            "exam_date": p.exam_date.isoformat() if (p and p.exam_date) else "",
            "goal_score": p.goal_score if p else None,
            "region": (p.region if p else None) or "",
            "country": (p.country if p else None) or "",
            "teachers": teachers,
        },
        "learning": {
            "attempts_count": attempts_count,
            "finished_attempts": finished_attempts,
            "answered_questions": answered_questions,
            "correct_answers": correct_answers,
            "accuracy_pct": accuracy_pct,
            "streak_days": streak_days,
            "mastery_pct": summary.get("mastery_pct") if summary else None,
            "predicted": summary.get("predicted") if summary else None,
        },
        "timeline": timeline,
    }


def get_visit_drawer_detail(visit_id: str) -> dict | None:
    """Timeline and metadata for a single visit (useful for anonymous visitors)."""
    v = (
        Visit.query.options(joinedload(Visit.page_views), joinedload(Visit.user).joinedload(User.profile))
        .filter(Visit.id == visit_id)
        .first()
    )
    if v is None:
        return None
    if v.user_id is not None:
        return get_user_drawer_detail(v.user_id)

    now = utcnow()
    online_cutoff = now - timedelta(minutes=ONLINE_WINDOW_MINUTES)
    return {
        "kind": "anonymous_visit",
        "visit": _visit_row_dict(v, online_cutoff),
        "pages": [
            {
                "path": pv.path,
                "created_at": pv.created_at.isoformat() if pv.created_at else "",
                "time_spent_seconds": pv.time_spent_seconds or 0,
            }
            for pv in v.page_views[:100]
        ],
    }

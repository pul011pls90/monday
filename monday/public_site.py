"""Public welcome website & question-bank showcase (Stage 2)."""
from __future__ import annotations

import os
import pathlib
import random
import re
import time
from collections import Counter
from datetime import timedelta

from flask import Blueprint, Response, abort, current_app, jsonify, make_response, render_template, request, url_for
from flask_babel import gettext as _
from sqlalchemy import func

from . import storage
from .abuse import check_404_probe_guard, rate_limit_value, record_404_probe
from .access import admin_required
from .constants import COLLECTION_EXAMS, CONTACTS, EXAMS, MODES, OLYMPIAD_EXAM, UNIVERSITY_EXAM
from .exam_content import (
    collect_exam_content_preflight_blockers,
    list_exam_content_slugs,
    load_exam_page_content,
)
from .extensions import db, limiter
from .manager import MODE_PREF_LABELS
from .models import (
    AcademicCourse,
    Attempt,
    AttemptAnswer,
    ContentNode,
    Location,
    Question,
    Work,
    local_midnight_utc,
    today as local_today,
)
from .public_samples import (
    get_public_samples_by_exam,
    is_valid_public_sample_key,
    list_local_public_sample_files,
    mime_for_public_sample_key,
    public_media_copy_exists,
    read_public_sample_bytes,
    sanitize_public_sample,
    verify_public_sample_token,
)
from .services import next_monday_test_start

bp = Blueprint("public_site", __name__)

_STATS_CACHE: dict[str, object] = {"ts": 0.0, "data": None}
_MARKER_RE = re.compile(r"(\[требует подтверждения|\bTODO\b|\bLorem\b)", re.I)
_TEMPLATES_ROOT = pathlib.Path(__file__).resolve().parent / "templates"


def is_production_mode(app=None) -> bool:
    """Detect production deployment (explicit IS_PRODUCTION, FLASK/APP_ENV, Render, or COOKIE_SECURE)."""
    target = app or current_app
    if target.config.get("IS_PRODUCTION"):
        return True
    if target.testing:
        return False
    env_name = (os.environ.get("FLASK_ENV") or os.environ.get("APP_ENV") or "").strip().lower()
    if env_name == "production":
        return True
    if os.environ.get("RENDER", "").strip().lower() == "true":
        return True
    if bool(target.config.get("SESSION_COOKIE_SECURE", False)) and not target.debug:
        return True
    return False


def collect_site_preflight_blockers(
    *,
    contacts_override: dict | None = None,
    template_dirs: tuple[pathlib.Path, ...] | None = None,
    exam_data_dir: pathlib.Path | None = None,
) -> list[str]:
    """Return every launch blocker preventing safe PUBLIC_SITE_ENABLED rollout in production."""
    blockers: list[str] = []

    pub_locs = Location.query.filter_by(is_active=True, is_public=True).all()
    if not pub_locs:
        blockers.append("No active public Location rows (is_public=True) with address, working hours, and phone.")
    else:
        for loc in pub_locs:
            missing = []
            if not (loc.address or "").strip():
                missing.append("address")
            if not (loc.working_hours or "").strip():
                missing.append("working_hours")
            if not (loc.phone or "").strip():
                missing.append("phone")
            if missing:
                blockers.append(f"Public Location #{loc.id} ({loc.name}) missing: {', '.join(missing)}.")
            if not (loc.photo or "").strip():
                blockers.append(f"Public Location #{loc.id} ({loc.name}) missing photo.")
            for val in (loc.public_name, loc.address, loc.working_hours):
                if val and _MARKER_RE.search(val):
                    blockers.append(f"Public Location #{loc.id} contains unfinished marker text.")
                    break

    pub_courses = AcademicCourse.query.filter_by(is_active=True, is_public=True).all()
    valid_courses = [c for c in pub_courses if (c.public_summary or "").strip()]
    if not valid_courses:
        blockers.append("No active public AcademicCourse rows (is_public=True) with non-empty public_summary.")
    for c in pub_courses:
        if not (c.public_summary or "").strip():
            blockers.append(f"Public AcademicCourse #{c.id} ({c.name}) missing public_summary.")
        elif _MARKER_RE.search(c.public_summary):
            blockers.append(f"Public AcademicCourse #{c.id} contains unfinished marker text.")

    dirs_to_scan = template_dirs or (_TEMPLATES_ROOT / "public", _TEMPLATES_ROOT / "info")
    for d in dirs_to_scan:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.html")):
            txt = p.read_text(encoding="utf-8", errors="replace")
            m = _MARKER_RE.search(txt)
            if m:
                blockers.append(f"Template {p.parent.name}/{p.name} contains unfinished marker '{m.group(1)}'.")

    if not current_app.config.get("PUBLIC_LEGAL_REVIEWED", False):
        blockers.append("Legal pages (Terms/Privacy/Refund) are not marked reviewed (PUBLIC_LEGAL_REVIEWED=0).")
    if template_dirs is None:
        from .legal import collect_legal_config_blockers

        blockers.extend(collect_legal_config_blockers())

    if current_app.config.get("STRIPE_ENABLED", False):
        if not (current_app.config.get("STRIPE_SECRET_KEY") or "").strip():
            blockers.append("STRIPE_ENABLED=1 but STRIPE_SECRET_KEY is missing.")
        if not (current_app.config.get("STRIPE_WEBHOOK_SECRET") or "").strip():
            blockers.append("STRIPE_ENABLED=1 but STRIPE_WEBHOOK_SECRET is missing.")

    contacts = contacts_override if contacts_override is not None else CONTACTS
    empty_contacts = [k for k in ("instagram", "telegram", "whatsapp", "trial_lesson", "address") if not str(contacts.get(k) or "").strip()]
    if empty_contacts:
        blockers.append(f"Empty public contact link(s)/field(s): {', '.join(empty_contacts)}.")

    if Question.query.filter_by(status="published").count() == 0:
        blockers.append("Zero published questions in database for live statistics.")

    # Stage 3 checks: advertised exam public samples & strict public media copy integrity
    flagged_questions = Question.query.filter_by(is_public_sample=True).all()
    published_samples = [
        q for q in flagged_questions
        if q.status == "published" and q.answer_type != "written"
    ]
    for exam_code in EXAMS:
        if not any(exam_code in (q.exams or []) for q in published_samples):
            blockers.append(f"No published public sample question for advertised exam '{exam_code}'.")

    for q in flagged_questions:
        if q.status != "published":
            blockers.append(f"Flagged public sample Question #{q.id} is not published (status={q.status}).")

    unflagged_with_key = Question.query.filter(
        Question.is_public_sample.is_(False),
        Question.public_image_key.isnot(None),
    ).all()
    for q in unflagged_with_key:
        if (q.public_image_key or "").strip():
            blockers.append(f"Unflagged Question #{q.id} still has a public media copy ({q.public_image_key}).")

    # Sample media storage integrity checks (local persistent disk vs Supabase Storage)
    sample_folder = current_app.config.get("PUBLIC_SAMPLE_MEDIA_FOLDER") or ""
    if is_production_mode(current_app) and not storage.using_supabase():
        abs_folder = os.path.abspath(sample_folder) if sample_folder else ""
        abs_instance = os.path.abspath(current_app.instance_path)
        abs_repo = os.path.abspath(os.path.dirname(current_app.root_path))
        persistent_flag = current_app.config.get("PUBLIC_SAMPLE_PERSISTENT_DISK")
        in_ephemeral_tree = bool(
            abs_folder
            and (
                abs_folder == abs_instance
                or abs_folder.startswith(abs_instance + os.sep)
                or abs_folder == abs_repo
                or abs_folder.startswith(abs_repo + os.sep)
            )
        )
        on_render_without_disk = (
            os.environ.get("RENDER", "").strip().lower() == "true"
            and not abs_folder.startswith("/var/data")
            and persistent_flag is not True
        )
        if persistent_flag is False or not abs_folder or in_ephemeral_tree or on_render_without_disk:
            blockers.append(
                "Production sample media uses ephemeral local disk without Supabase Storage or a persistent disk mount."
            )

    if storage.using_supabase():
        try:
            bucket_keys = set(storage.list_all_objects("public-samples/"))
        except Exception as exc:
            blockers.append(f"Supabase sample media listing failed ({type(exc).__name__}).")
            bucket_keys = None
        if bucket_keys is not None:
            valid_bucket_objs = {
                f"public-samples/{q.public_image_key}"
                for q in flagged_questions
                if q.status == "published" and q.public_image_key and (q.image_path or "").strip()
            }
            for q in flagged_questions:
                if (q.image_path or "").strip():
                    obj = f"public-samples/{q.public_image_key}" if is_valid_public_sample_key(q.public_image_key) else None
                    if not obj or obj not in bucket_keys:
                        blockers.append(f"Public sample Question #{q.id} is missing its public media copy.")
            for obj_key in sorted(bucket_keys - valid_bucket_objs):
                blockers.append(f"Orphaned public sample media object exists in Supabase Storage: {obj_key}.")
    else:
        for q in flagged_questions:
            if (q.image_path or "").strip():
                if not is_valid_public_sample_key(q.public_image_key) or not public_media_copy_exists(q.public_image_key):
                    blockers.append(f"Public sample Question #{q.id} is missing its public media copy.")

        valid_keys = {
            q.public_image_key
            for q in flagged_questions
            if q.status == "published" and q.public_image_key and (q.image_path or "").strip()
        }
        for fname in list_local_public_sample_files():
            if fname not in valid_keys:
                blockers.append(f"Orphaned public sample media file exists for unflagged/non-sample question: {fname}.")

    if template_dirs is None or exam_data_dir is not None:
        min_exam_samples = int(current_app.config.get("PUBLIC_EXAM_PAGE_MIN_SAMPLES", 1) or 1)
        blockers.extend(
            collect_exam_content_preflight_blockers(
                data_dir=exam_data_dir,
                min_samples_per_page=min_exam_samples,
            )
        )

    return blockers


def enforce_public_site_prod_guard(app) -> None:
    """Log an error and block PUBLIC_SITE_ENABLED in production while any preflight blocker remains."""
    app.config["_PUBLIC_SITE_BLOCKED_IN_PROD"] = False
    if not app.config.get("PUBLIC_SITE_ENABLED", False) or not is_production_mode(app):
        return
    try:
        blockers = collect_site_preflight_blockers()
    except Exception as exc:
        app.config["_PUBLIC_SITE_BLOCKED_IN_PROD"] = True
        app.logger.propagate = True
        app.logger.error("PUBLIC_SITE_ENABLED=1 ignored in production: preflight check failed (%s).", exc)
        return
    if blockers:
        app.config["_PUBLIC_SITE_BLOCKED_IN_PROD"] = True
        app.logger.propagate = True
        app.logger.error(
            "PUBLIC_SITE_ENABLED=1 ignored in production due to %s site-preflight blocker(s): %s",
            len(blockers),
            "; ".join(blockers[:5]),
        )


def is_public_site_enabled() -> bool:
    if not current_app.config.get("PUBLIC_SITE_ENABLED", False):
        return False
    if current_app.config.get("_PUBLIC_SITE_BLOCKED_IN_PROD"):
        return False
    if is_production_mode(current_app):
        enforce_public_site_prod_guard(current_app)
        if current_app.config.get("_PUBLIC_SITE_BLOCKED_IN_PROD"):
            return False
    return True


def clear_public_stats_cache() -> None:
    _STATS_CACHE["ts"] = 0.0
    _STATS_CACHE["data"] = None


def get_public_stats() -> dict:
    """Compute live database counts for public pages with short in-memory TTL cache."""
    ttl = max(0, int(current_app.config.get("PUBLIC_STATS_TTL_SECONDS", 60) or 0))
    now_mono = time.monotonic()
    cached = _STATS_CACHE.get("data")
    if ttl > 0 and not current_app.config.get("TESTING") and cached is not None and (now_mono - float(_STATS_CACHE["ts"])) < ttl:
        return cached  # type: ignore[return-value]

    published_questions = Question.query.filter_by(status="published").all()
    by_exam: Counter = Counter()
    for q in published_questions:
        for ex in (q.exams or []):
            by_exam[str(ex)] += 1

    all_nodes = ContentNode.query.filter_by(archived=False).all()
    node_by_id = {n.id: n for n in all_nodes}
    topic_nodes = [n for n in all_nodes if n.level == "topic"]
    topics_count = len(topic_nodes)
    skills_count = sum(1 for n in all_nodes if n.level == "node")

    # Map every ContentNode id to its root topic node (code & normalized name) for real per-topic counts
    root_topic_by_id: dict[int, ContentNode] = {}
    for n in all_nodes:
        cur = n
        seen_ids: set[int] = set()
        while cur and cur.parent_id and cur.parent_id in node_by_id and cur.id not in seen_ids:
            seen_ids.add(cur.id)
            cur = node_by_id[cur.parent_id]
        if cur:
            root_topic_by_id[n.id] = cur

    by_topic_code: Counter = Counter()
    by_topic_name: Counter = Counter()
    for q in published_questions:
        if q.skill_id and q.skill_id in root_topic_by_id:
            rt = root_topic_by_id[q.skill_id]
            if rt.code:
                by_topic_code[str(rt.code)] += 1
            if rt.name:
                by_topic_name[str(rt.name).strip().lower()] += 1

    min_topic_q = int(current_app.config.get("PUBLIC_STATS_MIN_TOPIC_QUESTIONS", 1) or 0)
    emblem_specs = (
        ("b-alg", _("Алгебра"), ("алгебра",), "algebra", 1),
        ("b-geo", _("Геометрия"), ("геометрия",), "geometry", 2),
        ("b-trig", _("Тригонометрия"), ("тригонометрия",), "trig", 3),
        ("b-fn", _("Функции"), ("функции",), "functions", 1),
        ("b-stat", _("Вероятность"), ("вероятность и статистика", "вероятность"), "probability", 2),
        ("b-logic", _("Логика"), ("логика и сравнение", "логика и данные", "логика"), "logic", 3),
    )
    topic_emblems = []
    for t_code, t_label, name_aliases, t_icon, t_speed in emblem_specs:
        db_node = next(
            (
                tn for tn in topic_nodes
                if tn.code == t_code or (tn.name or "").strip().lower() in name_aliases
            ),
            None,
        )
        if db_node is None:
            continue
        raw_cnt = int(by_topic_code.get(t_code, 0))
        if raw_cnt == 0:
            raw_cnt = sum(int(by_topic_name.get(al, 0)) for al in name_aliases)
        topic_emblems.append(
            {
                "code": t_code,
                "label": str(t_label),
                "db_name": db_node.name,
                "icon": t_icon,
                "speed": t_speed,
                "count": raw_cnt if raw_cnt >= min_topic_q else None,
            }
        )

    collections_count = Work.query.filter_by(status="published", kind="collection").count()
    languages_count = len(current_app.config.get("LANGUAGES", {}) or {})

    # Questions solved today and this week in Asia/Bishkek (LOCAL_TZ = UTC+6)
    today_start_utc = local_midnight_utc()
    week_start_utc = today_start_utc - timedelta(days=local_today().weekday())
    solved_today = AttemptAnswer.query.filter(AttemptAnswer.answered_at >= today_start_utc).count()
    solved_week = AttemptAnswer.query.filter(AttemptAnswer.answered_at >= week_start_utc).count()

    # Last Monday Test distinct finished participant count
    last_monday_work = (
        Work.query.filter_by(kind="monday", status="published")
        .order_by(Work.week_start.desc(), Work.id.desc())
        .first()
    )
    last_monday_participants = 0
    if last_monday_work and last_monday_work.versions:
        ver_ids = [v.id for v in last_monday_work.versions]
        last_monday_participants = int(
            db.session.query(func.count(func.distinct(Attempt.user_id)))
            .filter(Attempt.work_version_id.in_(ver_ids), Attempt.finished_at.isnot(None))
            .scalar()
            or 0
        )

    next_monday_info = None
    if bool(current_app.config.get("MONDAY_TEST_SCHEDULE_PUBLIC", False)):
        nxt = next_monday_test_start()
        next_monday_info = {
            "iso": nxt.strftime("%Y-%m-%dT%H:%M:%S+06:00"),
            "label": nxt.strftime("%d.%m · %H:%M"),
        }

    known_exam_slugs = set(list_exam_content_slugs())
    exam_cards = []
    for code, meta in EXAMS.items():
        slug_lower = code.lower()
        exam_cards.append(
            {
                "code": code,
                "slug": slug_lower if slug_lower in known_exam_slugs else None,
                "label": str(meta["label"]),
                "country": str(meta.get("country", "")),
                "note": str(meta.get("note", "")),
                "count": int(by_exam.get(code, 0)),
            }
        )
    for extra_code, extra_label, extra_note in (
        (OLYMPIAD_EXAM, _("Олимпиады"), _("олимпиадные задачи")),
        (UNIVERSITY_EXAM, "Calculus I", _("университетская математика")),
    ):
        exam_cards.append(
            {
                "code": extra_code,
                "slug": None,
                "label": str(extra_label),
                "country": "",
                "note": str(extra_note),
                "count": int(by_exam.get(extra_code, 0)),
            }
        )

    pub_q_cnt = len(published_questions)
    min_q = int(current_app.config.get("PUBLIC_STATS_MIN_QUESTIONS", 10) or 0)
    min_top = int(current_app.config.get("PUBLIC_STATS_MIN_TOPICS", 3) or 0)
    min_col = int(current_app.config.get("PUBLIC_STATS_MIN_COLLECTIONS", 1) or 0)
    min_lang = int(current_app.config.get("PUBLIC_STATS_MIN_LANGUAGES", 2) or 0)
    min_td = int(current_app.config.get("PUBLIC_STATS_MIN_SOLVED_TODAY", 10) or 0)
    min_wk = int(current_app.config.get("PUBLIC_STATS_MIN_SOLVED_WEEK", 25) or 0)
    min_mp = int(current_app.config.get("PUBLIC_STATS_MIN_MONDAY_PARTICIPANTS", 10) or 0)

    visible = {
        "published_questions": pub_q_cnt if pub_q_cnt >= min_q else None,
        "topics_count": topics_count if topics_count >= min_top else None,
        "collections_count": collections_count if collections_count >= min_col else None,
        "languages_count": languages_count if languages_count >= min_lang else None,
        "solved_today": solved_today if solved_today >= min_td else None,
        "solved_week": solved_week if solved_week >= min_wk else None,
        "last_monday_participants": last_monday_participants if last_monday_participants >= min_mp else None,
        "next_monday_test": next_monday_info,
    }

    data = {
        "published_questions": pub_q_cnt,
        "topics_count": topics_count,
        "skills_count": skills_count,
        "collections_count": collections_count,
        "languages_count": languages_count,
        "solved_today": solved_today,
        "solved_week": solved_week,
        "last_monday_participants": last_monday_participants,
        "next_monday_test": next_monday_info,
        "visible": visible,
        "topic_emblems": topic_emblems,
        "exams_count": len(exam_cards),
        "exam_cards": exam_cards,
    }
    _STATS_CACHE["ts"] = now_mono
    _STATS_CACHE["data"] = data
    return data


def _public_pricing_meta() -> dict:
    amount_minor = int(current_app.config.get("PUBLIC_QBANK_PRICE_AMOUNT", 800) or 800)
    currency = (current_app.config.get("PUBLIC_QBANK_PRICE_CURRENCY") or "USD").strip().upper()
    if amount_minor % 100 == 0:
        formatted = f"{amount_minor // 100}"
    else:
        formatted = f"{amount_minor / 100:.2f}"
    symbol = "$" if currency == "USD" else f"{currency} "
    return {
        "amount_minor": amount_minor,
        "currency": currency,
        "display_price": f"{symbol}{formatted}",
    }


def _public_locations() -> list[dict]:
    rows = Location.query.filter_by(is_active=True, is_public=True).order_by(Location.id.asc()).all()
    return [r.to_public_dict() for r in rows]


def _public_courses() -> list[dict]:
    rows = AcademicCourse.query.filter_by(is_active=True, is_public=True).order_by(AcademicCourse.id.asc()).all()
    return [r.to_public_dict() for r in rows]


def _utm_context() -> dict:
    keys = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
    return {k: (request.args.get(k) or "").strip()[:120] for k in keys}


def _seo_context(*, title: str, description: str, endpoint_url: str | None = None) -> dict:
    canonical = endpoint_url or request.base_url
    return {
        "seo_title": title,
        "seo_description": description,
        "canonical_url": canonical,
    }


def is_admin_public_preview() -> bool:
    """True only when an active unblocked Admin explicitly launched public-site preview mode."""
    from flask import session
    from flask_login import current_user

    if not current_user.is_authenticated:
        return False
    if not getattr(current_user, "is_admin", False) or getattr(current_user, "is_blocked", False):
        return False
    return bool(session.get("_adm_public_preview"))


def _require_public_flag():
    if not is_public_site_enabled() and not is_admin_public_preview():
        abort(404)


def resolve_highlighted_exam() -> dict | None:
    """Resolve optional ?exam=<slug> or bot deep-link ?source=exam_<slug> / ?utm_source=exam_<slug> safely."""
    candidates = [
        (request.args.get("exam") or "").strip().lower(),
        (request.args.get("source") or "").strip().lower(),
        (request.args.get("utm_source") or "").strip().lower(),
    ]
    known_slugs = set(list_exam_content_slugs())
    for raw in candidates:
        if not raw:
            continue
        slug = raw[5:] if raw.startswith("exam_") else raw
        code = slug.upper()
        if code in EXAMS:
            meta = EXAMS[code]
            return {
                "code": code,
                "slug": slug if slug in known_slugs else None,
                "label": str(meta["label"]),
                "country": str(meta.get("country", "")),
                "note": str(meta.get("note", "")),
            }
    return None


def render_landing_page():
    stats = get_public_stats()
    pricing = _public_pricing_meta()
    locations = _public_locations()
    courses = _public_courses()
    highlighted = resolve_highlighted_exam()
    org_ld = {
        "@context": "https://schema.org",
        "@type": "EducationalOrganization",
        "name": "Monday Academy",
        "url": url_for("auth.index", _external=True),
        "description": "Подготовка к экзаменам по математике (ОРТ, SAT, ЕНТ, ЕГЭ, ОГЭ, CSCA) и банк вопросов для самостоятельной подготовки.",
    }
    return render_template(
        "public/landing.html",
        **_seo_context(
            title=_("Monday Academy — курсы математики и банк вопросов"),
            description=_("Подготовка к ОРТ, SAT, ЕНТ, ЕГЭ, ОГЭ и CSCA с преподавателями офлайн и онлайн, а также самостоятельный банк вопросов Monday."),
            endpoint_url=url_for("auth.index", _external=True),
        ),
        stats=stats,
        pricing=pricing,
        locations=locations,
        courses=courses,
        modes=MODES,
        MODE_PREF_LABELS=MODE_PREF_LABELS,
        utm=_utm_context(),
        sent=(request.args.get("sent") == "1"),
        org_json_ld=org_ld,
        highlighted_exam=highlighted,
        hero_scroll_screens=float(current_app.config.get("HERO_SCROLL_STAGE_SCREENS", 3) or 3),
        default_interest=(highlighted["label"] if highlighted else ""),
    )


def render_about_page():
    return render_template(
        "public/about.html",
        **_seo_context(
            title=_("О школе Monday Academy"),
            description=_("Миссия, учебная платформа, формат работы и направления подготовки Monday Academy."),
            endpoint_url=url_for("auth.about", _external=True),
        ),
        stats=get_public_stats(),
    )


@bp.route("/offline-courses")
def offline_courses():
    _require_public_flag()
    locations = _public_locations()
    local_businesses = [
        {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": f"Monday Academy — {loc['name']}",
            "address": {"@type": "PostalAddress", "streetAddress": loc["address"]},
            **({"telephone": loc["phone"]} if loc["phone"] else {}),
            **({"openingHours": loc["working_hours"]} if loc["working_hours"] else {}),
        }
        for loc in locations
    ]
    return render_template(
        "public/offline_courses.html",
        **_seo_context(
            title=_("Офлайн-курсы и филиалы"),
            description=_("Очные занятия в мини-группах и филиалы Monday Academy."),
        ),
        locations=locations,
        local_business_ld=local_businesses,
        MODE_PREF_LABELS=MODE_PREF_LABELS,
        utm=_utm_context(),
        sent=(request.args.get("sent") == "1"),
    )


@bp.route("/online")
def online_courses():
    _require_public_flag()
    return render_template(
        "public/online_courses.html",
        **_seo_context(
            title=_("Онлайн-курсы по математике"),
            description=_("Онлайн-подготовка к ОРТ, SAT, ЕНТ, ЕГЭ, ОГЭ и школьной математике на платформе Monday."),
        ),
        courses=_public_courses(),
        stats=get_public_stats(),
        MODE_PREF_LABELS=MODE_PREF_LABELS,
        utm=_utm_context(),
        sent=(request.args.get("sent") == "1"),
    )


@bp.route("/question-bank")
@limiter.limit(lambda: rate_limit_value("PUBLIC_RATE_LIMIT_PAGE", "120 per minute"))
def question_bank():
    _require_public_flag()
    return render_template(
        "public/question_bank.html",
        **_seo_context(
            title=_("Банк вопросов для самостоятельной подготовки"),
            description=_("Тренируйтесь самостоятельно по темам и сложности: режимы сессий, сборники, журнал ошибок и прогноз баллов."),
        ),
        stats=get_public_stats(),
        pricing=_public_pricing_meta(),
        modes=MODES,
        sample_groups=get_public_samples_by_exam(),
        self_study_signup_enabled=bool(current_app.config.get("SELF_STUDY_SIGNUP_ENABLED", False)),
    )


@bp.route("/question-bank/media/<key>")
@limiter.limit(lambda: rate_limit_value("QBANK_RATE_LIMIT_VIEW", "120 per minute; 1000 per hour"))
def public_sample_media(key: str):
    """Serve copied stem media ONLY for currently published is_public_sample questions via DB lookup."""
    check_404_probe_guard()
    if not is_valid_public_sample_key(key):
        record_404_probe("public_site.public_sample_media")
        abort(404)
    q = Question.query.filter_by(public_image_key=key).first()
    if not q or not q.is_public_sample or q.status != "published":
        record_404_probe("public_site.public_sample_media")
        abort(404)
    db_key = q.public_image_key
    if not is_valid_public_sample_key(db_key):
        record_404_probe("public_site.public_sample_media")
        abort(404)
    try:
        data = read_public_sample_bytes(db_key)
    except Exception as exc:
        current_app.logger.error("Public sample media read failed (%s)", type(exc).__name__)
        abort(503)
    if data is None:
        abort(404)
    resp = Response(data, status=200, mimetype=mime_for_public_sample_key(db_key))
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


@bp.route("/pricing")
@limiter.limit(lambda: rate_limit_value("PUBLIC_RATE_LIMIT_PAGE", "120 per minute"))
def pricing():
    _require_public_flag()
    return render_template(
        "public/pricing.html",
        **_seo_context(
            title=_("Тарифы и форматы обучения"),
            description=_("Бесплатный старт, подписка на банк вопросов без преподавателя и обучение в Monday Academy."),
        ),
        pricing=_public_pricing_meta(),
        stats=get_public_stats(),
    )


def _faq_items() -> list[dict[str, str]]:
    return [
        {
            "q": _("Чем отличается «Подписка на банк вопросов» от «Абонемента» в школу?"),
            "a": _("Подписка на банк вопросов открывает самостоятельный доступ к задачам, сессиям и пробным тестам без преподавателя. Абонемент используется для занятий с преподавателем онлайн или в аудитории."),
        },
        {
            "q": _("Какие экзамены доступны на платформе?"),
            "a": _("ОРТ, SAT, ЕНТ, ЕГЭ, ОГЭ, CSCA, а также олимпиадные и университетские сборники по математике."),
        },
        {
            "q": _("Можно ли попробовать бесплатно до оплаты?"),
            "a": _("Да, на странице банка вопросов доступны бесплатные примеры задач, а на занятия в школе можно оставить заявку на пробный урок."),
        },
        {
            "q": _("Работает ли платформа на телефоне и планшете?"),
            "a": _("Да, Monday адаптирован для iPhone, Android и iPad и поддерживает установку на главный экран как веб-приложение."),
        },
    ]


@bp.route("/faq")
def faq():
    _require_public_flag()
    faqs = _faq_items()
    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": str(item["q"]),
                "acceptedAnswer": {"@type": "Answer", "text": str(item["a"])},
            }
            for item in faqs
        ],
    }
    return render_template(
        "public/faq.html",
        **_seo_context(
            title=_("Частые вопросы"),
            description=_("Ответы на вопросы о курсах Monday Academy, банке вопросов и регистрации."),
        ),
        faqs=faqs,
        faq_json_ld=faq_ld,
    )


@bp.route("/contact")
@limiter.limit(lambda: rate_limit_value("PUBLIC_RATE_LIMIT_PAGE", "120 per minute"))
def contact():
    _require_public_flag()
    locations = _public_locations()
    return render_template(
        "public/contact.html",
        **_seo_context(
            title=_("Контакты и запись"),
            description=_("Свяжитесь с Monday Academy или оставьте заявку на подбор группы и расписания."),
        ),
        locations=locations,
        MODE_PREF_LABELS=MODE_PREF_LABELS,
        utm=_utm_context(),
        sent=(request.args.get("sent") == "1"),
    )


@bp.route("/api/public/stats")
@limiter.limit(lambda: rate_limit_value("PUBLIC_RATE_LIMIT_STATS", "60 per minute"))
def api_public_stats():
    """Return 60s-cached, threshold-gated aggregate counters and per-topic counts (zero personal data or user IDs)."""
    _require_public_flag()
    stats = get_public_stats()
    resp = jsonify(
        {
            "ok": True,
            "timezone": "Asia/Bishkek",
            "counters": stats["visible"],
            "topics": [
                {"code": t["code"], "label": t["label"], "count": t["count"]}
                for t in stats.get("topic_emblems", [])
            ],
        }
    )
    resp.headers["Cache-Control"] = "public, max-age=60"
    return resp


@bp.route("/api/public/hero-question/check", methods=["POST"])
@limiter.limit(lambda: rate_limit_value("PUBLIC_RATE_LIMIT_HERO_CHECK", "30 per minute; 200 per hour"))
def api_hero_question_check():
    """Verify answer choice against an opaque short-lived public sample token (Stage 2)."""
    _require_public_flag()
    check_404_probe_guard()
    payload = request.get_json(silent=True) if request.is_json else request.form
    payload = payload or {}
    token = str(payload.get("token") or "").strip()
    raw_choice = payload.get("choice")

    decoded = verify_public_sample_token(token)
    if decoded is None:
        return jsonify({"ok": False, "error": "invalid_or_expired_token"}), 400
    qid, exam_code = decoded

    q = db.session.get(Question, qid)
    if q is None or q.status != "published" or not q.is_public_sample:
        record_404_probe("public_site.api_hero_question_check")
        return jsonify({"ok": False, "error": "sample_not_found"}), 404

    try:
        choice_idx = int(str(raw_choice).strip())
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid_choice"}), 400

    opts = list(q.options or [])
    if choice_idx < 0 or (opts and choice_idx >= len(opts)):
        return jsonify({"ok": False, "error": "invalid_choice"}), 400

    is_correct = str(choice_idx) == str(q.correct).strip()
    san = sanitize_public_sample(q, exam_code)
    topic_label = san["topic_name"] or san["skill_name"] or _("Математика")
    exam_label = san["exam_label"]
    known_slugs = set(list_exam_content_slugs())
    slug_lower = exam_code.lower()
    exam_url = (
        url_for("public_site.exam_page", slug=slug_lower)
        if slug_lower in known_slugs
        else url_for("public_site.question_bank")
    )

    if is_correct:
        return jsonify(
            {
                "ok": True,
                "correct": True,
                "badge": _("Это вопрос %(ex)s · %(top)s", ex=exam_label, top=topic_label),
                "exam_code": exam_code,
                "exam_label": exam_label,
                "topic_label": topic_label,
                "exam_url": exam_url,
            }
        )
    return jsonify(
        {
            "ok": True,
            "correct": False,
            "hint": _("Подсказка: упростите выражения в условии и попробуйте выбрать другой вариант."),
        }
    )


def _render_exam_page_by_slug(slug: str):
    _require_public_flag()
    doc = load_exam_page_content(slug)
    if doc is None:
        abort(404)

    exam_code = doc["code"]
    sample_rows = (
        Question.query.filter_by(status="published", is_public_sample=True)
        .order_by(Question.id.asc())
        .all()
    )
    per_exam = int(current_app.config.get("PUBLIC_SAMPLE_PER_EXAM", 4) or 4)
    matched_samples = [
        sanitize_public_sample(q, exam_code)
        for q in sample_rows
        if exam_code in (q.exams or []) and (q.answer_type or "choice") != "written"
    ][: max(1, per_exam)]

    canonical = url_for("public_site.exam_page", slug=doc["slug"], _external=True)
    org_ld = {
        "@context": "https://schema.org",
        "@type": "EducationalOrganization",
        "name": "Monday Academy",
        "url": url_for("auth.index", _external=True),
        "description": doc["seo_description"],
    }
    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["q"],
                "acceptedAnswer": {"@type": "Answer", "text": item["a"]},
            }
            for item in doc["faqs"]
        ],
    }
    return render_template(
        "public/exam_page.html",
        **_seo_context(
            title=doc["seo_title"],
            description=doc["seo_description"],
            endpoint_url=canonical,
        ),
        exam=doc,
        samples=matched_samples,
        stats=get_public_stats(),
        pricing=_public_pricing_meta(),
        MODE_PREF_LABELS=MODE_PREF_LABELS,
        utm=_utm_context(),
        sent=(request.args.get("sent") == "1"),
        org_json_ld=org_ld,
        faq_json_ld=faq_ld,
    )


@bp.route("/exams/<slug>")
@limiter.limit(lambda: rate_limit_value("PUBLIC_RATE_LIMIT_PAGE", "120 per minute"))
def exam_page(slug: str):
    return _render_exam_page_by_slug(slug)


@bp.route("/ort")
@limiter.limit(lambda: rate_limit_value("PUBLIC_RATE_LIMIT_PAGE", "120 per minute"))
def exam_ort_alias():
    return _render_exam_page_by_slug("ort")


@bp.route("/robots.txt")
def robots_txt():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /manager/",
        "Disallow: /teacher/",
        "Disallow: /assistant/",
        "Disallow: /student/",
        "Disallow: /academic/",
        "Disallow: /api/",
        "Disallow: /uploads/",
        "Disallow: /home",
        "Disallow: /sessions",
        "Disallow: /bank/",
        "Disallow: /daily/",
        f"Sitemap: {url_for('public_site.sitemap_xml', _external=True)}",
    ]
    resp = Response("\n".join(lines) + "\n", status=200, mimetype="text/plain")
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    return resp


def _xml_escape(text: str) -> str:
    from markupsafe import escape
    return str(escape(text))


@bp.route("/sitemap.xml")
@limiter.limit(lambda: rate_limit_value("PUBLIC_RATE_LIMIT_PAGE", "120 per minute"))
def sitemap_xml():
    urls = [
        url_for("auth.about", _external=True),
        url_for("auth.terms", _external=True),
        url_for("auth.privacy", _external=True),
        url_for("auth.refund", _external=True),
        url_for("crm_intake.public_apply", _external=True),
    ]
    if is_public_site_enabled():
        urls = [
            url_for("auth.index", _external=True),
            url_for("auth.about", _external=True),
            url_for("public_site.offline_courses", _external=True),
            url_for("public_site.online_courses", _external=True),
            url_for("public_site.question_bank", _external=True),
            url_for("public_site.pricing", _external=True),
            url_for("public_site.faq", _external=True),
            url_for("public_site.contact", _external=True),
            url_for("crm_intake.public_apply", _external=True),
            url_for("auth.terms", _external=True),
            url_for("auth.privacy", _external=True),
            url_for("auth.refund", _external=True),
        ]
        for slug in list_exam_content_slugs():
            doc = load_exam_page_content(slug)
            if doc and doc.get("all_verified"):
                urls.append(url_for("public_site.exam_page", slug=slug, _external=True))
    else:
        urls.insert(0, url_for("auth.login", _external=True))

    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc in urls:
        body.append(f"  <url><loc>{_xml_escape(loc)}</loc></url>")
    body.append("</urlset>")
    resp = make_response("\n".join(body) + "\n", 200)
    resp.headers["Content-Type"] = "application/xml; charset=utf-8"
    return resp


_ADMIN_PREVIEW_TARGETS = {
    "landing": "auth.index",
    "ort": "public_site.exam_ort_alias",
    "about": "auth.about",
    "question-bank": "public_site.question_bank",
    "pricing": "public_site.pricing",
    "offline": "public_site.offline_courses",
    "online": "public_site.online_courses",
    "faq": "public_site.faq",
    "contact": "public_site.contact",
    "terms": "auth.terms",
    "privacy": "auth.privacy",
    "refund": "auth.refund",
}


@bp.route("/admin/preview")
@admin_required
def admin_preview():
    """Enable Admin-only public website preview mode and open the requested page (defaults to landing about Monday)."""
    from flask import redirect, session

    session["_adm_public_preview"] = True
    page = (request.args.get("page") or "landing").strip().lower()
    endpoint = _ADMIN_PREVIEW_TARGETS.get(page, "auth.index")
    return redirect(url_for(endpoint))


@bp.route("/admin/preview/exit", methods=["POST"])
@admin_required
def admin_preview_exit():
    """Leave Admin public-site preview mode and return cleanly to /admin/."""
    from flask import redirect, session

    session.pop("_adm_public_preview", None)
    return redirect(url_for("admin.index"))


@bp.route("/admin/preview/subscription", methods=["POST"])
@admin_required
def admin_preview_subscription():
    """Jump straight into simulated Student view on /subscription to inspect Checkout & plans UI."""
    from flask import redirect, session
    from flask_login import current_user, login_user
    from .admin import _resolve_dummy_user
    from .audit import write_audit_log
    from .extensions import db

    real_admin = current_user._get_current_object()
    target = _resolve_dummy_user("student")
    write_audit_log(
        actor_id=real_admin.id,
        action="admin_simulate_start",
        entity_type="user",
        entity_id=target.id,
        new_value={"role": target.role, "target": "student.subscription"},
    )
    db.session.commit()
    session.pop("_adm_public_preview", None)
    session["_sim_admin_id"] = real_admin.id
    session["_sim_admin_ver"] = int(real_admin.session_version or 1)
    login_user(target)
    return redirect(url_for("student.subscription"))

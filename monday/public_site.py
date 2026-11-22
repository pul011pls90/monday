"""Public welcome website & question-bank showcase (Stage 2)."""
from __future__ import annotations

import os
import pathlib
import re
import time
from collections import Counter

from flask import Blueprint, Response, abort, current_app, make_response, render_template, request, url_for
from flask_babel import gettext as _

from . import storage
from .abuse import check_404_probe_guard, rate_limit_value, record_404_probe
from .constants import COLLECTION_EXAMS, CONTACTS, EXAMS, MODES, OLYMPIAD_EXAM, UNIVERSITY_EXAM
from .extensions import limiter
from .manager import MODE_PREF_LABELS
from .models import AcademicCourse, ContentNode, Location, Question, Work
from .public_samples import (
    get_public_samples_by_exam,
    is_valid_public_sample_key,
    list_local_public_sample_files,
    mime_for_public_sample_key,
    public_media_copy_exists,
    read_public_sample_bytes,
)

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

    topics_count = ContentNode.query.filter_by(archived=False, level="topic").count()
    skills_count = ContentNode.query.filter_by(archived=False, level="node").count()
    collections_count = Work.query.filter_by(status="published", kind="collection").count()

    exam_cards = []
    for code, meta in EXAMS.items():
        exam_cards.append(
            {
                "code": code,
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
                "label": str(extra_label),
                "country": "",
                "note": str(extra_note),
                "count": int(by_exam.get(extra_code, 0)),
            }
        )

    data = {
        "published_questions": len(published_questions),
        "topics_count": topics_count,
        "skills_count": skills_count,
        "collections_count": collections_count,
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


def _require_public_flag():
    if not is_public_site_enabled():
        abort(404)


def render_landing_page():
    stats = get_public_stats()
    pricing = _public_pricing_meta()
    locations = _public_locations()
    courses = _public_courses()
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

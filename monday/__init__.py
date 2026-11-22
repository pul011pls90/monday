"""Monday — application factory."""
import os
import sys
from datetime import date, datetime

import click
from flask import Flask, abort, g, has_request_context, make_response, redirect, render_template, request, send_from_directory, session, url_for
from flask_babel import format_date, format_datetime
from flask_babel import gettext as _
from flask_login import current_user, login_required

from config import Config

from .extensions import babel, csrf, db, limiter, login_manager, migrate

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations")


def select_locale():
    if not has_request_context():
        return Config.BABEL_DEFAULT_LOCALE
    langs = Config.LANGUAGES
    if current_user and current_user.is_authenticated and current_user.language in langs:
        return current_user.language
    cookie = request.cookies.get("lang")
    if cookie in langs:
        return cookie
    return Config.BABEL_DEFAULT_LOCALE


def create_app(config_object=Config, *, seed_if_empty=True):
    app = Flask(__name__, instance_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance"))
    app.config.from_object(config_object)
    # Render (and most hosts) end HTTPS in front of the app: trust their X-Forwarded-For/Proto/Host for one hop so
    # request.remote_addr reflects the real client IP and _external links start with https://.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    app.config.setdefault(
        "PUBLIC_SAMPLE_MEDIA_FOLDER",
        os.path.join(os.path.dirname(app.config["UPLOAD_FOLDER"]), "public_sample_media"),
    )
    os.makedirs(app.config["PUBLIC_SAMPLE_MEDIA_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db, directory=MIGRATIONS_DIR, render_as_batch=True)
    csrf.init_app(app)
    app.config.setdefault("RATELIMIT_ENABLED", not app.config.get("TESTING", False))
    limiter.init_app(app)
    _register_speed(app)
    _register_security_headers(app)
    babel.init_app(app, locale_selector=select_locale)

    # names of the shared skill map are stored in Russian; show them in the page's language
    from flask_babel import get_locale, gettext as _gt
    from .content_names import NAME_SET

    def _finalize(value):
        if isinstance(value, str) and value in NAME_SET and str(get_locale()) != "ru":
            return _gt(value)
        return value
    app.jinja_env.finalize = _finalize
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = None
    login_manager.session_protection = "basic" if app.config.get("TESTING") else "strong"

    from .models import LoginEvent, PageView, User, Visit

    @login_manager.user_loader
    def load_user(user_id):
        raw = str(user_id or "")
        if ":" in raw:
            uid_s, ver_s = raw.split(":", 1)
            if not (uid_s.isdigit() and ver_s.isdigit()):
                return None
            u = db.session.get(User, int(uid_s))
            if not u or (u.session_version or 1) != int(ver_s):
                return None
            return u
        if not raw.isdigit():
            return None
        u = db.session.get(User, int(raw))
        if not u or (u.session_version or 1) != 1:
            return None
        return u

    from . import academic, admin, assistant, auth, bank, crm_intake, daily, manager, picker, student, teacher
    app.register_blueprint(auth.bp)
    app.register_blueprint(student.bp)
    app.register_blueprint(bank.bp)
    app.register_blueprint(daily.bp)
    app.register_blueprint(picker.bp)
    app.register_blueprint(assistant.bp)
    app.register_blueprint(assistant.review_bp)
    app.register_blueprint(teacher.bp)
    app.register_blueprint(manager.bp)
    app.register_blueprint(crm_intake.bp)
    app.register_blueprint(academic.bp)
    from . import reports
    app.register_blueprint(reports.bp)
    app.register_blueprint(admin.bp)
    from . import analytics_admin
    app.register_blueprint(analytics_admin.bp)
    from . import content_i18n
    app.register_blueprint(content_i18n.bp)
    app.add_template_filter(content_i18n.localize, 'loc')
    from . import deploy_safety
    app.register_blueprint(deploy_safety.bp)
    deploy_safety.register_maintenance_lock(app)
    from . import roadmap
    app.register_blueprint(roadmap.bp)
    from . import course
    app.register_blueprint(course.bp)
    from . import fx
    app.register_blueprint(fx.bp)
    from . import public_site
    app.register_blueprint(public_site.bp)
    from services.crm_bot.telegram_bot import bot_bp as crm_telegram_bot_bp
    app.register_blueprint(crm_telegram_bot_bp)
    from .trig_formulas import init_trig_block
    init_trig_block(app)

    def branch_groups(entries):
        """Formula-sheet entries grouped by section, ignoring case and extra spaces; first spelling wins."""
        groups = {}
        for e in sorted(entries, key=lambda e: (e.position or 0, e.id or 0)):
            key = " ".join((e.branch or "").split()).casefold()
            groups.setdefault(key, [" ".join((e.branch or "").split()), []])[1].append(e)
        return [(label, items) for label, items in groups.values()]

    def math_wrap(text):
        """A formula typed without $…$ is still shown as maths."""
        text = (text or "").strip()
        return text if not text or "$" in text else f"${text}$"
    app.add_template_filter(branch_groups, "branch_groups")
    app.add_template_filter(math_wrap, "math_wrap")

    def sheet_image(path):
        """A sheet entry's picture: the student's upload, or a drawing that came with a Monday template."""
        from .formulas import IMAGE_PREFIX
        if path.startswith(IMAGE_PREFIX):
            return url_for("static", filename="img/formulas/" + path[len(IMAGE_PREFIX):])
        return url_for("uploaded_file", filename=path)
    app.add_template_filter(sheet_image, "sheet_image")

    _register_template_helpers(app)
    _register_errors(app)
    _register_cli(app)
    from .analytics_tracking import register_analytics_middleware
    register_analytics_middleware(app)

    @app.route("/manifest.webmanifest")
    def pwa_manifest():
        """Serve Web App Manifest with versioned static icon URLs."""
        import json
        from flask import make_response

        manifest = {
            "id": "/",
            "name": "Monday",
            "short_name": "Monday",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#FFFFFF",
            "theme_color": "#F7F8FB",
            "lang": "ru",
            "icons": [
                {
                    "src": url_for("static", filename="img/icon-192.png"),
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": url_for("static", filename="img/icon-512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": url_for("static", filename="img/icon-maskable-512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ],
        }
        resp = make_response(json.dumps(manifest, ensure_ascii=False))
        resp.headers["Content-Type"] = "application/manifest+json; charset=utf-8"
        resp.cache_control.public = True
        resp.cache_control.max_age = 3600
        return resp

    @app.route("/offline")
    def pwa_offline():
        """Serve unpersonalized Russian offline fallback shell (no session/CSRF data)."""
        resp = make_response(render_template("offline.html"))
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        resp.cache_control.public = True
        resp.cache_control.max_age = 3600
        return resp

    @app.route("/sw.js")
    def pwa_sw():
        """Serve root-scoped Service Worker with deterministic cache version & versioned static shell."""
        import hashlib
        import json

        precache_urls = [
            url_for("pwa_offline"),
            url_for("static", filename="css/fonts.css"),
            url_for("static", filename="vendor/katex/katex.min.css"),
            url_for("static", filename="css/monday.css"),
            url_for("static", filename="css/brand.css"),
            url_for("static", filename="js/app.js"),
            url_for("static", filename="js/pwa.js"),
            url_for("static", filename="img/icon-192.png"),
            url_for("static", filename="img/apple-touch-icon.png"),
        ]
        sw_path = os.path.join(app.static_folder, "js", "sw.js")
        with open(sw_path, "rb") as f:
            sw_bytes = f.read()
        digest = hashlib.sha256()
        digest.update(str(app.config.get("APP_VERSION") or "").encode("utf-8"))
        digest.update(sw_bytes)
        for u in precache_urls:
            digest.update(u.encode("utf-8"))
        sw_ver = "v1-" + digest.hexdigest()[:12]
        config_banner = (
            "self.__MONDAY_SW_CONFIG = "
            + json.dumps({"version": sw_ver, "precacheUrls": precache_urls}, ensure_ascii=False)
            + ";\n"
        )
        resp = make_response(config_banner + sw_bytes.decode("utf-8"))
        resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
        return resp

    @app.before_request
    def _track_user():
        """Blocked accounts are signed out; everyone else gets 'last seen' (at most every 5 minutes)."""
        from datetime import timedelta
        from flask_login import current_user, logout_user
        from .models import utcnow
        if not current_user.is_authenticated:
            return None
        if current_user.is_blocked:
            logout_user()
            return redirect(url_for("auth.login"))
        if session.get("_sim_admin_id"):
            return None
        now = utcnow()
        if not current_user.last_seen_at or now - current_user.last_seen_at > timedelta(minutes=5):
            current_user.last_seen_at = now
            db.session.commit()
        return None

    def _authorize_upload(filename):
        """Enforce per-object ownership/role authorization on /uploads/<path:filename>."""
        import re
        from .models import Attempt, AttemptAnswer, Question, SheetEntry, StudentRecord, User
        if not filename or filename.startswith("/") or "\\" in filename or ".." in filename.split("/"):
            abort(404)
        if filename.startswith("support/"):
            abort(403)
        if filename.startswith("solutions/"):
            m = re.fullmatch(r"solutions/a(\d+)_\d+_[0-9a-f]+\.[a-z0-9]+", filename)
            if not m:
                abort(404)
            att = db.session.get(Attempt, int(m.group(1)))
            if not att:
                abort(404)
            attached = (
                AttemptAnswer.query.filter_by(attempt_id=att.id, photo_path=filename).first() is not None
                or filename in (att.draft or {}).values()
            )
            if not attached:
                abort(404)
            if current_user.is_admin or att.user_id == current_user.id:
                return
            from .student_links import teacher_open_records_query
            if current_user.is_teacher and teacher_open_records_query(current_user.id).filter(
                StudentRecord.student_user_id == att.user_id
            ).first():
                return
            abort(403)
        if filename.startswith("sheet-"):
            entry = SheetEntry.query.filter_by(image_path=filename).first()
            if not entry:
                abort(404)
            if current_user.is_admin or entry.sheet.user_id == current_user.id:
                return
            abort(403)
        if filename.startswith("avatar-"):
            owner = User.query.filter_by(avatar_path=filename).first()
            if not owner:
                abort(404)
            if current_user.is_admin or owner.id == current_user.id:
                return
            from .student_links import teacher_open_records_query
            if current_user.is_teacher and teacher_open_records_query(current_user.id).filter(
                StudentRecord.student_user_id == owner.id
            ).first():
                return
            if owner.is_teacher and teacher_open_records_query(owner.id).filter(
                StudentRecord.student_user_id == current_user.id
            ).first():
                return
            abort(403)
        q = Question.query.filter_by(image_path=filename).first()
        if q is None:
            from .abuse import record_404_probe
            record_404_probe("uploaded_file")
            abort(404)
        from .subscriptions import has_question_bank_access as _has_qbank, has_unlocked_image_today, is_content_staff
        if q.status == "published":
            if (
                is_content_staff(current_user)
                or _has_qbank(current_user)
                or q.is_public_sample
                or (current_user.role == "student" and has_unlocked_image_today(current_user.id, filename))
            ):
                if not q.is_public_sample:
                    from .abuse import enforce_question_scrape_guard
                    enforce_question_scrape_guard(current_user, [q.id], source="uploaded_file")
                return
            abort(403)
        if current_user.is_admin or q.author_id == current_user.id or (current_user.can_review and q.status == "pending"):
            return
        abort(403)

    from .abuse import abuse_rate_key, check_404_probe_guard, rate_limit_value

    @app.route("/uploads/<path:filename>")
    @limiter.limit(lambda: rate_limit_value("QBANK_RATE_LIMIT_VIEW", "120 per minute; 1000 per hour"), key_func=abuse_rate_key)
    @access.question_bank_access_required(tier="free_quota")
    @login_required
    def uploaded_file(filename):
        """Pack figures come from the repository; everything else from the uploads folder or Supabase Storage."""
        from . import storage
        check_404_probe_guard()
        if filename.startswith("packs/"):
            parts = filename.split("/")
            if len(parts) != 3 or not parts[1] or not parts[2] or ".." in parts:
                from .abuse import record_404_probe
                record_404_probe("uploaded_file")
                abort(404)
            _, pack, name = parts
            from .packs import PACK_DIR, available
            if pack not in available():
                from .abuse import record_404_probe
                record_404_probe("uploaded_file")
                abort(404)
            from .models import Question
            from .subscriptions import has_question_bank_access as _has_qbank, has_unlocked_image_today, is_content_staff
            q_pack = Question.query.filter_by(image_path=filename).first()
            if not (
                is_content_staff(current_user)
                or _has_qbank(current_user)
                or Question.query.filter_by(image_path=filename, is_public_sample=True, status="published").first() is not None
                or (current_user.role == "student" and has_unlocked_image_today(current_user.id, filename))
            ):
                abort(403)
            if q_pack and not q_pack.is_public_sample:
                from .abuse import enforce_question_scrape_guard
                enforce_question_scrape_guard(current_user, [q_pack.id], source="uploaded_file_pack")
            return send_from_directory(os.path.join(PACK_DIR, pack, "figures"), name)
        _authorize_upload(filename)
        if storage.using_supabase():
            try:
                url = storage.signed_url(filename)
            except Exception as exc:
                app.logger.error("Storage signed_url failed (%s)", type(exc).__name__)
                abort(503)
            if not url:
                abort(404)
            return redirect(url)
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.before_request
    def _enforce_password_change():
        if not current_user.is_authenticated:
            return None
        if not getattr(current_user, "must_change_password", False):
            return None
        if session.get("_sim_admin_id"):
            return None
        ep = request.endpoint or ""
        if ep in (
            "auth.force_password_change",
            "auth.logout",
            "auth.toggle_theme",
            "auth.set_language",
            "static",
            "pwa_manifest",
            "pwa_sw",
            "pwa_offline",
            "deploy_safety.api_version",
            "deploy_safety.api_site_status",
        ):
            return None
        if request.path.startswith("/api/") or request.is_json:
            from flask import jsonify
            return jsonify({"ok": False, "error": "password_change_required"}), 403
        return redirect(url_for("auth.force_password_change"))

    with app.app_context():
        if any(cmd in sys.argv for cmd in ("reset-db", "db", "create-manager", "legacy-access-report")):  # CLI commands manage schema/actions directly without startup seeding
            return app
        from sqlalchemy import inspect as _sa_inspect
        if app.config.get("TESTING"):
            from flask_migrate import upgrade as _alembic_upgrade
            if os.path.isdir(MIGRATIONS_DIR) and os.path.isfile(os.path.join(MIGRATIONS_DIR, "env.py")):
                _alembic_upgrade(directory=MIGRATIONS_DIR)
            else:
                db.create_all()
        elif not _sa_inspect(db.engine).has_table("user"):
            app.logger.error("Database schema is not initialized. Run: flask --app app db upgrade")
            return app
        _lock_supabase_api()
        from .storage import ensure_bucket
        ensure_bucket()
        if seed_if_empty and not User.query.first():
            if app.config.get("SEED_DEMO", True):
                from .seed import seed_demo
                seed_demo()
            else:
                _bootstrap_admin(app)
        from .taxonomy import ensure_taxonomy
        ensure_taxonomy()  # move an older skill map onto the master map (once per version)
        from .packs import ensure_packs
        ensure_packs()  # ready-made questions and collections from monday/data/packs (once per pack)
        from .cleanup import run_fixes
        run_fixes()  # one-time data fixes (disabled in production via DATA_FIXES=0)
        if app.config.get("SEED_DEMO", True):
            from .seed import refresh_demo_mondays
            refresh_demo_mondays()  # demo Monday tests + demo students' results follow the calendar
        from .analytics_jobs import start_daily_maintenance_if_due
        start_daily_maintenance_if_due(app)
        from .public_site import enforce_public_site_prod_guard
        enforce_public_site_prod_guard(app)

    return app


def _register_security_headers(app):
    """Attach baseline HTTP security headers (and HSTS when running behind HTTPS)."""
    from urllib.parse import urlparse

    supabase_origin = ""
    raw_sb = (app.config.get("SUPABASE_URL") or "").strip()
    if raw_sb:
        parsed = urlparse(raw_sb)
        if parsed.scheme and parsed.netloc:
            supabase_origin = f" {parsed.scheme}://{parsed.netloc}"

    csp = app.config.get("CONTENT_SECURITY_POLICY") or (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://www.desmos.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        f"img-src 'self' data: blob: https://www.desmos.com{supabase_origin}; "
        "font-src 'self' data: https://www.desmos.com; "
        f"connect-src 'self' https://www.desmos.com https://cdn.jsdelivr.net{supabase_origin}; "
        "worker-src 'self' blob:; "
        "manifest-src 'self'; "
        "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com; "
        "frame-ancestors 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self' https://accounts.google.com"
    )

    @app.after_request
    def _set_security_headers(response):
        from flask import request as _req

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", csp)
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

        ep = _req.endpoint or ""
        view_fn = app.view_functions.get(ep)
        is_gated = bool(view_fn and getattr(view_fn, "_question_bank_gated", False))
        bp_name = _req.blueprint or ""
        if is_gated or bp_name in (
            "bank", "daily", "student", "course", "roadmap",
            "teacher", "assistant", "review", "admin", "manager", "academic", "reports",
        ) or _req.path.startswith("/uploads/"):
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")
            if ep != "uploaded_file" and "Cache-Control" not in response.headers:
                response.headers["Cache-Control"] = "private, no-store"
        return response


def _lock_supabase_api():
    """Supabase also publishes the tables through its own web API (PostgREST). Monday never uses it, so row level
    security is switched on with no rules: the API sees nothing, while the app (the tables' owner) works as before."""
    url = str(db.engine.url)
    if db.engine.dialect.name != "postgresql" or "supabase" not in url:
        return
    from sqlalchemy import text
    with db.engine.begin() as conn:
        for (name,) in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND NOT rowsecurity")):
            conn.execute(text(f'ALTER TABLE public."{name}" ENABLE ROW LEVEL SECURITY'))


def _register_template_helpers(app):
    from .constants import BIG_TEST_QUESTIONS, TEST_FORMATS
    from .taxonomy import TAGS as QUESTION_TAGS
    from .constants import (DIFFICULTIES, EXAMS, HOMEWORK_STATES, MISTAKE_REASONS, MODES, QUESTION_STATUSES,
                            LATIN_FORMATS, OLYMPIAD_EXAM, REPORT_KINDS, UNIVERSITY_EXAM, WEEKDAYS, WORK_CATEGORIES, WORK_KINDS, WORK_STATUSES, CONTACTS)

    from .models import utcnow

    def _monday_live():
        from .student import monday_window_open
        try:
            return monday_window_open()
        except Exception:
            return False

    def _open_reports():
        from .reports import open_count
        try:
            return open_count(current_user)
        except Exception:
            return 0

    def _crm_badges():
        cached = getattr(g, "_crm_badges_cache", None)
        if cached is not None:
            return cached
        empty = {"unanswered": 0, "tasks": 0}
        if not current_user.is_authenticated or current_user.role not in ("sales_manager", "supervisor", "admin"):
            g._crm_badges_cache = empty
            return empty
        try:
            from .models import Lead, LeadTask
            lq = Lead.query.filter(Lead.first_contact_at.is_(None), Lead.status.notin_(("won", "lost")))
            if not current_user.has_perm("crm.leads.view_all"):
                lq = lq.filter(Lead.assigned_manager_id == current_user.id)
            tq = LeadTask.query.filter(LeadTask.done_at.is_(None), LeadTask.assignee_id == current_user.id)
            res = {"unanswered": lq.count(), "tasks": tq.count()}
        except Exception:
            res = empty
        g._crm_badges_cache = res
        return res

    @app.context_processor
    def inject_globals():
        from .admin import SIM_ROLES, verified_sim_admin

        if current_user.is_authenticated:
            theme = current_user.theme
        else:
            theme = request.cookies.get("theme", "light")
        prefs = (current_user.prefs or {}) if current_user.is_authenticated else {}
        sim_admin = verified_sim_admin()
        if current_user.is_authenticated:
            from .subscriptions import subscription_status_summary

            sub_status = subscription_status_summary(current_user)
        else:
            sub_status = {
                "tier": "anonymous",
                "has_full_access": False,
                "has_teacher_link": False,
                "active_subscription": None,
                "legacy_access_until": None,
                "daily_used": 0,
                "daily_limit": int(app.config.get("FREE_DAILY_QUESTION_LIMIT", 10) or 10),
                "daily_remaining": int(app.config.get("FREE_DAILY_QUESTION_LIMIT", 10) or 10),
            }
        return {
            "THEME": theme if theme in ("light", "dark") else "light",
            "THEME_AUTO": theme == "system",
            "PREFS": prefs,
            "SIM_ADMIN": sim_admin,
            "SIM_ROLES": SIM_ROLES,
            "SUBSCRIPTION_STATUS": sub_status,
            "HAS_TEACHER_LINK": bool(sub_status["has_teacher_link"]),
            "LEGACY_ACCESS_UNTIL": sub_status["legacy_access_until"],
            "COURSE_INCLUDED_IN_SUBSCRIPTION": bool(app.config.get("COURSE_INCLUDED_IN_SUBSCRIPTION", True)),
            "SHOW_JOURNAL": bool(app.config.get("SHOW_JOURNAL", False)),
            "LANGUAGES": app.config["LANGUAGES"],
            "CURRENT_LANG": select_locale(),
            "EXAMS": EXAMS,
            "UNIVERSITY_EXAM": UNIVERSITY_EXAM,
            "LATIN_FORMATS": LATIN_FORMATS,
            "MODES": MODES,
            "monday_live": _monday_live,
            "TEST_FORMATS": TEST_FORMATS, "BIG_TEST_QUESTIONS": BIG_TEST_QUESTIONS, "QUESTION_TAGS": QUESTION_TAGS,
            "WORK_KINDS": WORK_KINDS,
            "WORK_CATEGORIES": WORK_CATEGORIES,
            "WORK_STATUSES": WORK_STATUSES,
            "QUESTION_STATUSES": QUESTION_STATUSES,
            "DIFFICULTIES": DIFFICULTIES,
            "MISTAKE_REASONS": MISTAKE_REASONS,
            "REPORT_KINDS": REPORT_KINDS,
            "open_reports": _open_reports,
            "crm_badges": _crm_badges,
            "HOMEWORK_STATES": HOMEWORK_STATES,
            "WEEKDAYS": WEEKDAYS,
            "CONTACTS": CONTACTS,
            "now": utcnow(),
        }

    from .services import work_bullets, work_topics
    app.add_template_filter(work_topics, "work_topics")
    app.add_template_filter(work_bullets, "work_bullets")

    @app.template_filter("has_cyrillic")
    def has_cyrillic(text):
        return any("Ѐ" <= ch <= "ӿ" for ch in str(text or ""))

    @app.template_filter("exam_label")
    def exam_label(code):
        if code == OLYMPIAD_EXAM:
            return _("Олимпиада")
        if code == UNIVERSITY_EXAM:
            return "Calculus I"
        return EXAMS.get(code, {}).get("label", code or "")

    @app.template_filter("d")
    def fmt_date(value, fmt="d MMMM"):
        if not value:
            return ""
        if isinstance(value, datetime):
            return format_datetime(value, fmt)
        return format_date(value, fmt)

    @app.template_filter("answer")
    def fmt_answer(value):
        """A numeric answer with several accepted values ("7|-7") shown as "7 или -7"."""
        from .services import display_answer
        return display_answer(value)

    @app.template_filter("dt")
    def fmt_datetime(value, fmt="d MMM, HH:mm"):
        return format_datetime(value, fmt) if value else ""

    @app.template_filter("minutes")
    def fmt_minutes(value):
        if not value:
            return "—"
        hours, mins = divmod(int(value), 60)
        if hours and mins:
            return _("%(h)s ч %(m)s мин", h=hours, m=mins)
        if hours:
            return _("%(h)s ч", h=hours)
        return _("%(m)s мин", m=mins)

    @app.template_filter("duration")
    def fmt_duration(seconds):
        if not seconds:
            return "—"
        m, s = divmod(int(seconds), 60)
        if m and s:
            return _("%(m)s мин %(s)s с", m=m, s=s)
        if m:
            return _("%(m)s мин", m=m)
        return _("%(s)s с", s=s)

    import math
    app.add_template_filter(math.cos, "cos")
    app.add_template_filter(math.sin, "sin")

    @app.template_filter("plural_ru")
    def plural_ru(n, one, few, many):
        """Russian plural forms: 1 вопрос, 2 вопроса, 5 вопросов."""
        n = abs(int(n))
        if n % 10 == 1 and n % 100 != 11:
            return one
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return few
        return many


def _register_errors(app):
    from flask import jsonify, make_response, render_template, request
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"ok": False, "error": "csrf_error"}), 400
        return (
            render_template(
                "errors/error.html",
                code=400,
                message=_("Сессия формы устарела или отсутствует CSRF-токен. Обновите страницу и попробуйте снова."),
            ),
            400,
        )

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/error.html", code=403, message=_("Нет доступа к этой странице.")), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/error.html", code=404, message=_("Такой страницы нет.")), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template("errors/error.html", code=413, message=_("Файл слишком большой (максимум 8 МБ).")), 413

    @app.errorhandler(429)
    def too_many_requests(e):
        is_json_req = (
            request.path.startswith("/api/")
            or request.is_json
            or request.headers.get("X-Requested-With") == "fetch"
            or (request.accept_mimetypes.best == "application/json" and not request.accept_mimetypes.accept_html)
        )
        if is_json_req:
            resp = make_response(jsonify({"ok": False, "error": "too_many_requests"}), 429)
            resp.headers.setdefault("Retry-After", "60")
            return resp
        resp = make_response(
            render_template(
                "errors/error.html",
                code=429,
                message=_("Слишком много запросов подряд. Подождите минуту и попробуйте снова."),
            ),
            429,
        )
        resp.headers.setdefault("Retry-After", "60")
        return resp

    @app.errorhandler(503)
    def service_unavailable(e):
        from .deploy_safety import get_maintenance_state
        maint = get_maintenance_state()
        retry_sec = str(max(60, int((maint.expected_minutes or 15) * 60)))
        if request.path.startswith("/api/") or request.is_json or (
            request.accept_mimetypes.best == "application/json"
            and not request.accept_mimetypes.accept_html
        ):
            resp = make_response(jsonify({
                "ok": False,
                "error": "maintenance",
                "maintenance": maint.to_dict(),
            }), 503)
        else:
            resp = make_response(render_template("errors/503.html", maint=maint), 503)
        resp.headers["Retry-After"] = retry_sec
        return resp


def _register_cli(app):
    @app.cli.command("reset-db")
    @click.option("--no-seed", is_flag=True, help="Create empty tables without demo data.")
    def reset_db(no_seed):
        """Drop all tables and recreate them via Alembic migrations (demo data included by default)."""
        from flask_migrate import upgrade as _alembic_upgrade
        from sqlalchemy import text
        db.drop_all()
        with db.engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        _alembic_upgrade(directory=MIGRATIONS_DIR)
        if not no_seed:
            from .seed import seed_demo
            seed_demo()
            from .taxonomy import ensure_taxonomy
            from .packs import ensure_packs
            ensure_taxonomy()
            ensure_packs()
        click.echo("Database recreated.")

    @app.cli.command("import-pack")
    @click.argument("pack_id", required=False)
    @click.option("--draft", is_flag=True, help="Import as drafts (review before students see them).")
    def import_pack_cmd(pack_id, draft):
        """Import a content pack from monday/data/packs (all of them when no name is given)."""
        from .packs import available, import_pack
        for pid in ([pack_id] if pack_id else available()):
            q, w = import_pack(pid, publish=not draft)
            click.echo(f"{pid}: " + (f"{q} questions, {w} collections" if q else "already imported"))

    @app.cli.command("migrate-analytics")
    def migrate_analytics_cmd():
        """Create visit/page_view tables and add cached visit columns to User."""
        from .analytics_schema import ensure_analytics_schema
        ensure_analytics_schema()
        click.echo("Analytics schema up to date.")

    @app.cli.command("analytics-daily-job")
    @click.option("--days", default=90, show_default=True, help="Delete PageView records older than N days.")
    def analytics_daily_job_cmd(days):
        """Purge PageViews older than 90 days and refresh cached User visit counters."""
        from .analytics_jobs import run_daily_analytics_maintenance
        res = run_daily_analytics_maintenance(retention_days=days)
        click.echo(f"Deleted page_views={res['deleted_page_views']}, updated_users={res['updated_users']}")

    @app.cli.command("create-manager")
    @click.option("--email", required=True, help="Manager email address.")
    @click.option("--name", required=True, help="Manager display name.")
    @click.option(
        "--role",
        default="sales_manager",
        show_default=True,
        type=click.Choice(["sales_manager", "supervisor"]),
        help="CRM role to assign.",
    )
    def create_manager_cmd(email, name, role):
        """Provision a Sales Manager (or Supervisor) with a one-time random password and audit log."""
        import secrets
        from .audit import write_audit_log
        from .models import User

        norm_email = (email or "").strip().lower()
        clean_name = (name or "").strip()
        if "@" not in norm_email or "." not in norm_email.split("@")[-1]:
            raise click.ClickException("Invalid email address.")
        if len(clean_name) < 2:
            raise click.ClickException("Name must be at least 2 characters.")
        if User.query.filter_by(email=norm_email).first() is not None:
            raise click.ClickException(f"User with email {norm_email} already exists.")

        # 20-char cryptographically random password mixing upper, lower, digits, and symbols (no fixed defaults).
        upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"
        lower = "abcdefghijkmnopqrstuvwxyz"
        digits = "23456789"
        symbols = "!@#$%^&*-_=+"
        alphabet = upper + lower + digits + symbols
        chars = [
            secrets.choice(upper),
            secrets.choice(lower),
            secrets.choice(digits),
            secrets.choice(symbols),
        ] + [secrets.choice(alphabet) for _ in range(16)]
        # Fisher-Yates shuffle with secrets.randbelow
        for i in range(len(chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            chars[i], chars[j] = chars[j], chars[i]
        raw_password = "".join(chars)

        user = User(
            email=norm_email,
            name=clean_name,
            role=role,
            is_approved=True,
            is_blocked=False,
            auth_provider="password",
            must_change_password=True,
        )
        user.set_password(raw_password)
        db.session.add(user)
        db.session.flush()
        write_audit_log(
            actor_id=None,
            action="manager_create",
            entity_type="user",
            entity_id=user.id,
            old_value=None,
            new_value={"email": user.email, "name": user.name, "role": user.role, "must_change_password": True},
            reason="cli:create-manager",
        )
        db.session.commit()

        click.echo(f"Created {role} account (id={user.id})")
        click.echo(f"Email:    {user.email}")
        click.echo(f"Password: {raw_password}")
        click.echo(f"Note:     One-time password — user will be forced to change it on first login.")

    @app.cli.command("crm-find-duplicates")
    def crm_find_duplicates_cmd():
        """Dry-run report of open duplicate leads grouped by phone_e164 and normalized messenger handle."""
        from collections import defaultdict
        from .models import Lead

        open_leads = Lead.query.filter(Lead.status.notin_(("won", "lost"))).order_by(Lead.id.asc()).all()
        by_phone = defaultdict(list)
        by_msg = defaultdict(list)
        for l in open_leads:
            if l.phone_e164:
                by_phone[l.phone_e164].append(l)
            if l.messenger_norm:
                by_msg[l.messenger_norm].append(l)

        found = 0
        for phone_val, grp in by_phone.items():
            if len(grp) > 1:
                found += 1
                desc = ", ".join(f"#{x.id} {x.full_name} [{x.status}]" for x in grp)
                click.echo(f"[PHONE {phone_val}] {desc}")
        for msg_val, grp in by_msg.items():
            if len(grp) > 1:
                found += 1
                desc = ", ".join(f"#{x.id} {x.full_name} [{x.status}]" for x in grp)
                click.echo(f"[MESSENGER @{msg_val}] {desc}")
        if not found:
            click.echo("No duplicate open leads found.")

    @app.cli.command("support-purge-images")
    @click.option("--days", default=90, show_default=True, type=int, help="Delete attachments for threads closed more than N days ago.")
    @click.option("--dry-run", is_flag=True, help="Report counts without deleting files or database rows.")
    def support_purge_images_cmd(days, dry_run):
        """Delete support attachment files and DB rows for threads closed more than --days ago."""
        from .support_images import purge_closed_support_images

        res = purge_closed_support_images(days=days, dry_run=dry_run)
        prefix = "[DRY RUN] " if res["dry_run"] else ""
        click.echo(f"{prefix}Purged {res['attachments']} support attachment(s), {res['bytes_freed']} bytes (days={res['days']}).")

    @app.cli.command("seed-crm-macros")
    def seed_crm_macros_cmd():
        """Idempotently seed Optima-style ReplyTemplate macros from docs/crm_bot/reply_macros.md."""
        from services.crm_bot.macros_loader import seed_reply_templates

        created = seed_reply_templates()
        click.echo(f"Seeded CRM reply macros (created={created}).")

    @app.cli.command("run-telegram-bot")
    @click.option("--allow-fallback", is_flag=True, help="Allow heuristic classification if GEMINI_API_KEY is unset.")
    def run_telegram_bot_cmd(allow_fallback):
        """Start the CRM Telegram Lead Bot via local long polling."""
        from services.crm_bot.classifier import CrmBotConfigError
        from services.crm_bot.telegram_bot import run_polling_bot

        try:
            click.echo("Starting Monday CRM Telegram Bot (long polling)...")
            run_polling_bot(app, allow_fallback=allow_fallback)
        except CrmBotConfigError as exc:
            raise click.ClickException(str(exc))

    @app.cli.command("site-preflight")
    def site_preflight_cmd():
        """List every launch blocker for the public website; exits non-zero if any blocker exists."""
        from .public_site import collect_site_preflight_blockers

        blockers = collect_site_preflight_blockers()
        if blockers:
            click.echo(f"Found {len(blockers)} launch blocker(s):")
            for item in blockers:
                click.echo(f" - {item}")
            raise SystemExit(1)
        click.echo("OK: public site preflight passed (0 blockers).")

    @app.cli.command("site-media-smoke")
    def site_media_smoke_cmd():
        """Smoke test media storage: upload, read back, list, and delete a temporary object."""
        import secrets
        from . import storage

        backend = "supabase" if storage.using_supabase() else "local_disk"
        prefix = "smoke-tests"
        key = f"{prefix}/smoke_{secrets.token_hex(8)}.txt"
        payload = f"monday-smoke-{secrets.token_hex(6)}".encode("utf-8")
        try:
            storage.save(key, payload, "text/plain")
            got = storage.read_bytes(key)
            if got != payload:
                raise RuntimeError("Read-back payload mismatch.")
            if storage.using_supabase():
                listed = storage.list_all_objects(prefix)
                if key not in listed:
                    raise RuntimeError("Uploaded smoke key missing from Supabase Storage list API.")
            else:
                smoke_dir = os.path.join(app.config["UPLOAD_FOLDER"], prefix)
                fname = os.path.basename(key)
                if not os.path.isdir(smoke_dir) or fname not in os.listdir(smoke_dir):
                    raise RuntimeError("Uploaded smoke file missing from local disk directory.")
            storage.delete(key)
            if storage.read_bytes(key) is not None:
                raise RuntimeError("Deleted smoke key still readable.")
        except Exception as exc:
            click.echo(f"FAIL ({backend}): {type(exc).__name__}: {exc}", err=True)
            raise SystemExit(1)
        click.echo(f"OK: site-media-smoke passed on backend '{backend}' (uploaded, read, listed, deleted).")

    @app.cli.command("legacy-access-report")
    def legacy_access_report_cmd():
        """Read-only report of student accounts affected by legacy_access_until grandfathering."""
        from .subscriptions import count_legacy_backfill_candidates

        stats = count_legacy_backfill_candidates()
        click.echo(f"Schema has user.legacy_access_until: {stats['schema_has_legacy_column']}")
        click.echo(f"LEGACY_ACCESS_DAYS={app.config.get('LEGACY_ACCESS_DAYS', 30)}")
        click.echo(f"Total active student accounts: {stats['total_students']}")
        click.echo(f"Already enrolled / teacher-linked students: {stats['enrolled_students']}")
        click.echo(f"Unlinked students still needing backfill (legacy_access_until IS NULL): {stats['would_backfill_if_null']}")
        click.echo(f"Unlinked students already grandfathered (legacy_access_until SET): {stats['already_grandfathered']}")
        click.echo(
            f"Total unlinked non-enrolled student accounts: {stats['would_backfill_if_null'] + stats['already_grandfathered']}"
        )


def _bootstrap_admin(app):
    """Production: an empty database gets one admin (ADMIN_EMAIL / ADMIN_PASSWORD) instead of the demo data."""
    from .models import LoginEvent, PageView, User, Visit
    email, password = app.config.get("ADMIN_EMAIL"), app.config.get("ADMIN_PASSWORD")
    if not email or not password:
        app.logger.warning("Empty database and no ADMIN_EMAIL/ADMIN_PASSWORD: no admin created.")
        return
    admin = User(email=email.strip().lower(), name="Admin", role="admin", is_approved=True)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()


def _register_speed(app):
    """Fewer and smaller requests per page.

    - Static files get ?v=<file version> in their URLs and are cached by browsers for a year:
      no more re-checking ~15 files on every page (a round trip each).
    - HTML, CSS and JS go out gzip-compressed (about 5x smaller).
    """
    import hashlib

    from flask_compress import Compress
    app.config.setdefault("COMPRESS_MIMETYPES", ["text/html", "text/css", "application/javascript", "text/javascript",
                                                 "application/json", "application/manifest+json", "image/svg+xml", "text/plain"])
    app.config.setdefault("COMPRESS_MIN_SIZE", 600)
    app.config.setdefault("COMPRESS_ALGORITHM", ["gzip"])
    Compress(app)

    versions = {}

    def version(filename):
        path = os.path.join(app.static_folder, filename)
        try:
            stamp = os.stat(path).st_mtime_ns
        except OSError:
            return None
        cached = versions.get(filename)
        if cached and cached[0] == stamp:
            return cached[1]
        with open(path, "rb") as f:
            v = hashlib.md5(f.read()).hexdigest()[:10]
        versions[filename] = (stamp, v)
        return v

    @app.url_defaults
    def _static_version(endpoint, values):
        if endpoint == "static" and "filename" in values and "v" not in values:
            v = version(values["filename"])
            if v:
                values["v"] = v

    @app.after_request
    def _cache_headers(resp):
        if request.endpoint in ("static", "uploaded_file"):
            resp.cache_control.no_cache = None
        if request.endpoint == "static" and request.args.get("v"):
            resp.cache_control.public = True
            resp.cache_control.max_age = 31536000
            resp.cache_control.immutable = True
        elif request.endpoint == "static":  # fonts and images referenced from CSS (no version in the URL)
            resp.cache_control.public = True
            resp.cache_control.max_age = 604800
        elif request.endpoint == "uploaded_file":
            resp.cache_control.private = True
            resp.cache_control.max_age = 3600 if resp.status_code in (301, 302) else 86400   # signed links last 2 h
        return resp

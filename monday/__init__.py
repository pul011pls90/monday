"""Monday — application factory."""
import os
import sys
from datetime import date, datetime

import click
from flask import Flask, g, redirect, request, send_from_directory, session, url_for
from flask_babel import format_date, format_datetime
from flask_babel import gettext as _
from flask_login import current_user, login_required

from config import Config

from .extensions import babel, csrf, db, login_manager


def select_locale():
    langs = Config.LANGUAGES
    if current_user.is_authenticated and current_user.language in langs:
        return current_user.language
    cookie = request.cookies.get("lang")
    if cookie in langs:
        return cookie
    return Config.BABEL_DEFAULT_LOCALE


def create_app(config_object=Config, *, seed_if_empty=True):
    app = Flask(__name__, instance_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance"))
    app.config.from_object(config_object)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
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

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from . import admin, assistant, auth, bank, daily, picker, student, teacher
    app.register_blueprint(auth.bp)
    app.register_blueprint(student.bp)
    app.register_blueprint(bank.bp)
    app.register_blueprint(daily.bp)
    app.register_blueprint(picker.bp)
    app.register_blueprint(assistant.bp)
    app.register_blueprint(assistant.review_bp)
    app.register_blueprint(teacher.bp)
    app.register_blueprint(admin.bp)
    from . import content_i18n
    app.register_blueprint(content_i18n.bp)
    app.add_template_filter(content_i18n.localize, 'loc')

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

    _register_template_helpers(app)
    _register_errors(app)
    _register_cli(app)

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
        now = utcnow()
        if not current_user.last_seen_at or now - current_user.last_seen_at > timedelta(minutes=5):
            current_user.last_seen_at = now
            db.session.commit()
        return None

    @app.route("/uploads/<path:filename>")
    @login_required
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    with app.app_context():
        if "reset-db" in sys.argv:  # the CLI command below rebuilds the tables itself
            return app
        db.create_all()
        _check_schema()
        if seed_if_empty and not User.query.first():
            from .seed import seed_demo
            seed_demo()
        from .taxonomy import ensure_taxonomy
        ensure_taxonomy()  # move an older skill map onto the master map (once per version)
        from .packs import ensure_packs
        ensure_packs()  # ready-made questions and collections from monday/data/packs (once per pack)
        from .cleanup import run_fixes
        run_fixes()  # one-time data fixes (demo collections removed, demo student renamed)

    return app


def _check_schema():
    """Keep an existing local database in step with the models.

    New columns that may be empty (or have a simple default) are added automatically,
    so updates like "profile picture" don't wipe the demo data. Anything bigger stops
    the app with a clear message (until real migrations are added for production).
    """
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    missing, added = [], []
    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            default = col.default.arg if col.default is not None and col.default.is_scalar else None
            if col.nullable or default is not None:
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(db.engine.dialect)}'
                if default is not None:
                    ddl += " DEFAULT " + (f"'{default}'" if isinstance(default, str) else str(int(default) if isinstance(default, bool) else default))
                with db.engine.begin() as conn:
                    conn.execute(text(ddl))
                added.append(f"{table.name}.{col.name}")
            else:
                missing.append(f"{table.name}.{col.name}")
    if missing:
        raise SystemExit(
            "\nThe database was created by an older version of Monday (missing: "
            + ", ".join(missing[:5]) + ("…" if len(missing) > 5 else "") + ").\n"
            "Recreate it with demo data:\n\n    flask --app app reset-db\n\nthen start again: python3 app.py\n")


def _register_template_helpers(app):
    from .constants import BIG_TEST_QUESTIONS, TEST_FORMATS
    from .taxonomy import TAGS as QUESTION_TAGS
    from .constants import (DIFFICULTIES, EXAMS, HOMEWORK_STATES, MISTAKE_REASONS, MODES, QUESTION_STATUSES,
                            WEEKDAYS, WORK_CATEGORIES, WORK_KINDS, WORK_STATUSES)

    from .models import utcnow

    @app.context_processor
    def inject_globals():
        if current_user.is_authenticated:
            theme = current_user.theme
        else:
            theme = request.cookies.get("theme", "light")
        return {
            "THEME": theme if theme in ("light", "dark") else "light",
            "LANGUAGES": app.config["LANGUAGES"],
            "CURRENT_LANG": select_locale(),
            "EXAMS": EXAMS,
            "MODES": MODES,
            "TEST_FORMATS": TEST_FORMATS, "BIG_TEST_QUESTIONS": BIG_TEST_QUESTIONS, "QUESTION_TAGS": QUESTION_TAGS,
            "WORK_KINDS": WORK_KINDS,
            "WORK_CATEGORIES": WORK_CATEGORIES,
            "WORK_STATUSES": WORK_STATUSES,
            "QUESTION_STATUSES": QUESTION_STATUSES,
            "DIFFICULTIES": DIFFICULTIES,
            "MISTAKE_REASONS": MISTAKE_REASONS,
            "HOMEWORK_STATES": HOMEWORK_STATES,
            "WEEKDAYS": WEEKDAYS,
            "now": utcnow(),
        }

    @app.template_filter("exam_label")
    def exam_label(code):
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
    from flask import render_template

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/error.html", code=403, message=_("Нет доступа к этой странице.")), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/error.html", code=404, message=_("Такой страницы нет.")), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template("errors/error.html", code=413, message=_("Файл слишком большой (максимум 8 МБ).")), 413


def _register_cli(app):
    @app.cli.command("reset-db")
    @click.option("--no-seed", is_flag=True, help="Create empty tables without demo data.")
    def reset_db(no_seed):
        """Drop all tables and recreate them (demo data included by default)."""
        db.drop_all()
        db.create_all()
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

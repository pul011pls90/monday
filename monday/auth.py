"""Login, registration, invite codes, theme and language switches."""
from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, flash, make_response, redirect, render_template, request, session, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required, login_user, logout_user

from config import Config

from .extensions import db
from .models import utcnow
from .models import StudentProfile, StudentRecord, User

bp = Blueprint("auth", __name__)


def _home_for(user):
    if user.is_assistant:
        return url_for("assistant.home")
    if user.is_teacher:
        return url_for("teacher.dashboard") if user.is_approved else url_for("auth.pending")
    if not (user.profile and user.profile.onboarded):
        return url_for("student.onboarding")
    return url_for("student.home")


def _safe_next(target):
    if target and urlparse(target).netloc == "" and target.startswith("/"):
        return target
    return None


def link_invite_code(user, code):
    """Attach a student account to a teacher's table row. Returns (ok, message)."""
    code = (code or "").strip().upper()
    if not code:
        return False, _("Введите код.")
    if not code.startswith("MND-"):
        code = "MND-" + code
    record = StudentRecord.query.filter_by(invite_code=code).first()
    if not record:
        return False, _("Код не найден. Проверьте его у учителя.")
    if record.student_user_id and record.student_user_id != user.id:
        return False, _("Этот код уже использован другим учеником.")
    if StudentRecord.query.filter_by(teacher_id=record.teacher_id, student_user_id=user.id).filter(
            StudentRecord.id != record.id).first():
        return False, _("Вы уже подключены к этому учителю.")
    record.student_user_id = user.id
    record.linked_at = utcnow()
    if user.profile and not user.profile.exam and record.exam:
        user.profile.exam = record.exam
    db.session.commit()
    return True, _("Вы подключены к учителю: %(name)s.", name=record.teacher.name)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(request.form.get("password", "")):
            flash(_("Неверный email или пароль."), "error")
            return render_template("auth/welcome.html", tab="login", form=request.form), 401
        if user.is_blocked:
            flash(_("Аккаунт заблокирован. Напишите администратору."), "error")
            return render_template("auth/welcome.html", tab="login", form=request.form), 403
        login_user(user, remember=bool(request.form.get("remember")))
        pending_code = session.pop("invite_code", None)
        if pending_code and user.role == "student":
            ok, msg = link_invite_code(user, pending_code)
            flash(msg, "success" if ok else "error")
        return redirect(_safe_next(request.args.get("next")) or _home_for(user))
    return render_template("auth/welcome.html", tab="login", form={})


@bp.route("/login/google")
def google_login():
    """Sign in with Google. Needs GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (OAuth) — not set up yet."""
    from flask import current_app
    if not current_app.config.get("GOOGLE_CLIENT_ID"):
        flash(_("Вход через Google заработает после подключения ключей Google. Пока войдите по email."), "info")
        return redirect(url_for("auth.login"))
    flash(_("Вход через Google скоро появится."), "info")  # OAuth flow goes here
    return redirect(url_for("auth.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))
    form = request.form if request.method == "POST" else {"invite_code": session.get("invite_code", "")}
    if request.method == "POST":
        name = form.get("name", "").strip()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        role = "teacher" if form.get("role") == "teacher" else "student"
        errors = []
        if len(name) < 2:
            errors.append(_("Укажите имя."))
        if "@" not in email or "." not in email.split("@")[-1]:
            errors.append(_("Укажите корректный email."))
        if len(password) < 8:
            errors.append(_("Пароль должен быть не короче 8 символов."))
        if User.query.filter_by(email=email).first():
            errors.append(_("Этот email уже зарегистрирован."))
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("auth/welcome.html", tab="register", form=form), 400
        user = User(name=name, email=email, role=role, is_approved=(role == "student"),
                    language=request.cookies.get("lang", "ru") if request.cookies.get("lang") in Config.LANGUAGES else "ru",
                    theme=request.cookies.get("theme", "light") if request.cookies.get("theme") in ("light", "dark") else "light")
        user.set_password(password)
        if role == "student":
            user.profile = StudentProfile()
        db.session.add(user)
        db.session.commit()
        login_user(user)
        code = form.get("invite_code", "").strip() or session.pop("invite_code", None)
        session.pop("invite_code", None)
        if code and role == "student":
            ok, msg = link_invite_code(user, code)
            flash(msg, "success" if ok else "error")
        return redirect(_home_for(user))
    return render_template("auth/welcome.html", tab="register", form=form)


@bp.route("/join/<code>")
def join(code):
    """Link a teacher sends: /join/MND-4K7Q."""
    record = StudentRecord.query.filter_by(invite_code=code.upper()).first()
    if not record:
        flash(_("Код приглашения не найден."), "error")
        return redirect(url_for("auth.login"))
    if current_user.is_authenticated:
        if current_user.role != "student":
            flash(_("Код приглашения предназначен для ученика."), "error")
            return redirect(_home_for(current_user))
        ok, msg = link_invite_code(current_user, code)
        flash(msg, "success" if ok else "error")
        return redirect(_home_for(current_user))
    session["invite_code"] = record.invite_code
    flash(_("%(name)s приглашает вас в Monday. Зарегистрируйтесь или войдите — код подключится автоматически.",
            name=record.teacher.name), "info")
    return redirect(url_for("auth.register"))


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/pending")
@login_required
def pending():
    if current_user.is_approved:
        return redirect(_home_for(current_user))
    return render_template("auth/pending.html")


@bp.route("/prefs/theme", methods=["POST"])
def toggle_theme():
    current = current_user.theme if current_user.is_authenticated else request.cookies.get("theme", "light")
    new = request.form.get("theme") or ("dark" if current == "light" else "light")
    if new not in ("light", "dark"):
        new = "light"
    if current_user.is_authenticated:
        current_user.theme = new
        db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        resp = make_response({"theme": new})
    else:
        resp = make_response(redirect(_safe_next(request.form.get("next")) or url_for("auth.index")))
    resp.set_cookie("theme", new, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return resp


@bp.route("/prefs/lang", methods=["POST"])
def set_language():
    lang = request.form.get("lang", "ru")
    if lang not in Config.LANGUAGES:
        lang = "ru"
    if current_user.is_authenticated:
        current_user.language = lang
        db.session.commit()
    resp = make_response(redirect(_safe_next(request.form.get("next")) or url_for("auth.index")))
    resp.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return resp


@bp.route("/prefs/avatar", methods=["POST"])
@login_required
def set_avatar():
    """Upload or remove the profile picture (students and teachers)."""
    import os
    import uuid
    from flask import current_app
    from werkzeug.utils import secure_filename
    nxt = _safe_next(request.form.get("next")) or url_for("auth.index")
    if request.form.get("remove") == "1":
        current_user.avatar_path = None
        db.session.commit()
        flash(_("Фото удалено."), "success")
        return redirect(nxt)
    upload = request.files.get("avatar")
    if not upload or not upload.filename:
        flash(_("Выберите фото."), "error")
        return redirect(nxt)
    ext = secure_filename(upload.filename).rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        flash(_("Фото: только PNG, JPG или WEBP."), "error")
        return redirect(nxt)
    from .images import store_image
    current_user.avatar_path = store_image(upload, f"avatar-{current_user.id}-{uuid.uuid4().hex[:8]}", kind="avatar")
    db.session.commit()
    flash(_("Фото обновлено."), "success")
    return redirect(nxt)

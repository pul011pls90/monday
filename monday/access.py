"""Role checks and password policy helpers used as route decorators."""
from functools import wraps

from flask import abort, redirect, url_for
from flask_login import current_user

STAFF_ROLES = ("admin", "manager", "teacher")
STUDENT_MIN_PASSWORD_LEN = 8
STAFF_MIN_PASSWORD_LEN = 12


def min_password_length(role: str | None) -> int:
    """Staff accounts (admin, manager, teacher) require at least 12 characters; students require 8."""
    return STAFF_MIN_PASSWORD_LEN if role in STAFF_ROLES else STUDENT_MIN_PASSWORD_LEN


def role_required(*roles):
    """Generic RBAC guard for attaching Stage 2/3 routes to specific roles."""
    allowed = set(roles)
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role not in allowed:
                abort(403)
            if current_user.role == "teacher" and not current_user.is_approved:
                return redirect(url_for("auth.pending"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def manager_required(view):
    """Managers and admins (Stage 3 CRM / Kanban / attendance / finance)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if current_user.role not in ("manager", "admin"):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def student_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if current_user.role == "assistant":
            return redirect(url_for("assistant.home"))
        if current_user.role != "student":
            return redirect(url_for("teacher.dashboard"))
        if not (current_user.profile and current_user.profile.onboarded):
            return redirect(url_for("student.onboarding"))
        return view(*args, **kwargs)
    return wrapped


def teacher_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_teacher:
            abort(403)
        if not current_user.is_approved:
            return redirect(url_for("auth.pending"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def staff_required(view):
    """Teachers, admins and assistants: the question bank, the question form, the account page."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if current_user.role not in ("teacher", "admin", "assistant"):
            abort(403)
        if current_user.role == "teacher" and not current_user.is_approved:
            return redirect(url_for("auth.pending"))
        return view(*args, **kwargs)
    return wrapped


def assistant_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if current_user.role not in ("assistant", "admin"):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def reviewer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.can_review:
            abort(403)
        return view(*args, **kwargs)
    return wrapped

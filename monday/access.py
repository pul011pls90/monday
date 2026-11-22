"""Central RBAC permission map and route decorators."""
from functools import wraps

from flask import abort, jsonify, redirect, request, url_for
from flask_login import current_user

ROLES = ("student", "teacher", "assistant", "sales_manager", "supervisor", "admin")
CRM_ROLES = ("sales_manager", "supervisor", "admin")
SUPERVISOR_ROLES = ("supervisor", "admin")
STAFF_ROLES = frozenset({"teacher", "assistant", "sales_manager", "supervisor", "admin"})

MIN_PASSWORD_LEN_STUDENT = 8
MIN_PASSWORD_LEN_STAFF = 12


def min_password_length(role: str | None) -> int:
    """Minimum password length: 12 chars for staff/manager/admin accounts, 8 for students."""
    return MIN_PASSWORD_LEN_STAFF if role in STAFF_ROLES else MIN_PASSWORD_LEN_STUDENT

# Central server-side permission map: permission key -> set of allowed roles.
PERMISSIONS = {
    # Core workspaces
    "student.workspace": frozenset({"student"}),
    "teacher.workspace": frozenset({"teacher", "admin"}),
    "assistant.workspace": frozenset({"assistant", "admin"}),
    "staff.content": frozenset({"teacher", "assistant", "admin"}),
    "admin.manage": frozenset({"admin"}),
    "admin.roles.change": frozenset({"admin"}),

    # CRM / Sales Manager & Supervisor
    "crm.access": frozenset({"sales_manager", "supervisor", "admin"}),
    "crm.leads.view_own": frozenset({"sales_manager", "supervisor", "admin"}),
    "crm.leads.view_all": frozenset({"supervisor", "admin"}),
    "crm.leads.create": frozenset({"sales_manager", "supervisor", "admin"}),
    "crm.leads.edit_own": frozenset({"sales_manager", "supervisor", "admin"}),
    "crm.leads.edit_all": frozenset({"supervisor", "admin"}),
    "crm.leads.reassign": frozenset({"supervisor", "admin"}),
    "crm.leads.delete": frozenset({"supervisor", "admin"}),
    "crm.leads.convert": frozenset({"sales_manager", "supervisor", "admin"}),
    "crm.audit.view": frozenset({"supervisor", "admin"}),

    # Academic operations (MVP-1, Stage 6)
    "academic.schedule.read": frozenset({"teacher", "sales_manager", "supervisor", "admin"}),
    "academic.schedule.manage": frozenset({"supervisor", "admin"}),
    "academic.attendance.read": frozenset({"teacher", "sales_manager", "supervisor", "admin"}),
    "academic.attendance.mark": frozenset({"teacher", "supervisor", "admin"}),
    "academic.attendance.edit_retro": frozenset({"supervisor", "admin"}),

    # Finance, Passes & Teacher Payroll (Phase B)
    "crm.finance.read": frozenset({"sales_manager", "supervisor", "admin"}),
    "crm.finance.record": frozenset({"sales_manager", "supervisor", "admin"}),
    "crm.finance.manage": frozenset({"supervisor", "admin"}),
    "academic.payroll.read": frozenset({"supervisor", "admin"}),
    "academic.payroll.manage": frozenset({"supervisor", "admin"}),
}


def has_permission(user, perm: str) -> bool:
    """Return True iff `user` is authenticated, active, approved (for teachers), and holds `perm`."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_blocked", False):
        return False
    role = getattr(user, "role", None)
    if role == "teacher" and not getattr(user, "is_approved", False):
        return False
    allowed = PERMISSIONS.get(perm)
    return bool(allowed and role in allowed)


def role_required(*roles):
    """Allow only authenticated users whose role is in `roles`; return 403 otherwise."""
    allowed = frozenset(roles)

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.is_blocked:
                abort(403)
            if current_user.role not in allowed:
                abort(403)
            if current_user.role == "teacher" and not current_user.is_approved:
                return redirect(url_for("auth.pending"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def permission_required(perm: str):
    """Enforce a named permission from PERMISSIONS; redirect anonymous to login, 403 on violation."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role == "teacher" and not current_user.is_approved:
                return redirect(url_for("auth.pending"))
            if not has_permission(current_user, perm):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def student_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if current_user.role in ("sales_manager", "supervisor"):
            abort(403)
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
    """Teachers, admins and content assistants: question bank, question form, staff account page."""
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


def manager_required(view):
    """Sales Managers, Supervisors and Admins."""
    return permission_required("crm.access")(view)


def supervisor_required(view):
    """Supervisors and Admins (all-leads visibility, reassignment, audit log)."""
    return permission_required("crm.audit.view")(view)


def has_question_bank_access(user) -> bool:
    """Delegate to centralized Stage 4 access check (staff, enrollment, subscription, or valid legacy grace)."""
    from .subscriptions import has_question_bank_access as _has_access

    return _has_access(user)


def _deny_gated_request(error_code: str, *, json_only: bool = False):
    is_json_req = (
        json_only
        or request.is_json
        or request.headers.get("X-Requested-With") == "fetch"
        or (request.accept_mimetypes.best == "application/json" and not request.accept_mimetypes.accept_html)
    )
    if not current_user.is_authenticated:
        if is_json_req:
            return jsonify({"ok": False, "error": "auth_required"}), 401
        return redirect(url_for("auth.login"))
    if request.path.startswith("/api/") or is_json_req:
        return jsonify({"ok": False, "error": error_code}), 403
    abort(403)


def question_bank_access_required(view_or_tier=None, *, tier: str = "full"):
    """Enforce question-bank, course, teacher-linked, and free-tier boundaries on all content routes.

    Usable both as `@question_bank_access_required` (tier='full') and
    `@question_bank_access_required(tier='free_quota' | 'course' | 'teacher_linked')`.
    """

    def _decorate(fn, selected_tier: str):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            from .subscriptions import (
                has_course_access,
                has_teacher_link,
                is_content_staff,
            )

            if not current_user.is_authenticated:
                return _deny_gated_request("auth_required")
            if getattr(current_user, "is_blocked", False):
                return _deny_gated_request("account_blocked")

            if selected_tier == "teacher_linked":
                # Homework & teacher sections are visible and callable only for students with a teacher link
                if getattr(current_user, "role", None) != "student" or not has_teacher_link(current_user):
                    return _deny_gated_request("teacher_link_required")
                return fn(*args, **kwargs)

            if selected_tier == "course":
                if not has_course_access(current_user):
                    return _deny_gated_request("course_subscription_required")
                return fn(*args, **kwargs)

            if selected_tier == "free_quota":
                # Free-tier students may enter and consume up to FREE_DAILY_QUESTION_LIMIT distinct questions/day;
                # staff (teacher/assistant/admin) and full-access students pass immediately, while managers get 403.
                if not (is_content_staff(current_user) or getattr(current_user, "role", None) == "student"):
                    return _deny_gated_request("forbidden")
                return fn(*args, **kwargs)

            # Default tier="full": requires content staff, enrolled student, active/trialing sub, or legacy_access_until
            if not has_question_bank_access(current_user):
                return _deny_gated_request("subscription_required")
            return fn(*args, **kwargs)

        wrapped._question_bank_gated = True
        wrapped._question_bank_tier = selected_tier
        return wrapped

    if callable(view_or_tier):
        return _decorate(view_or_tier, tier)
    chosen = str(view_or_tier or tier or "full")
    return lambda fn: _decorate(fn, chosen)


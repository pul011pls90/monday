"""Central RBAC permission map and route decorators."""
from functools import wraps

from flask import abort, redirect, url_for
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

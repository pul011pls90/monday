"""Admin: overview, teacher applications, question moderation, people (students, teachers, admins)."""
import secrets
from collections import Counter, defaultdict
from datetime import timedelta

from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, session, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required, login_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from .access import ROLES, admin_required, min_password_length
from .audit import write_audit_log
from .constants import EXAMS
from .extensions import db, limiter
from .models import (
    Attempt,
    AttemptAnswer,
    ContentNode,
    LoginEvent,
    Question,
    StudentProfile,
    StudentRecord,
    User,
    Work,
    utcnow,
)
from .services import content_gaps, progress_summary, temporary_password

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.context_processor
def _inject_site_maint():
    from .deploy_safety import get_maintenance_state
    try:
        return {"site_maint": get_maintenance_state()}
    except Exception:
        return {"site_maint": None}

TABS = ("overview", "apps", "moderation", "students", "teachers", "managers", "supervisors", "assistants", "admins")
PEOPLE = {
    "students": "student",
    "teachers": "teacher",
    "managers": "sales_manager",
    "supervisors": "supervisor",
    "assistants": "assistant",
    "admins": "admin",
}
PER_PAGE = 25
THIN = 3  # a skill with fewer published questions than this needs content

# Canonical dummy accounts & fallback sandbox profiles for 1-click Admin Role Simulation
SIM_ROLES = (
    ("student", "Ученик", "student@monday.kg", "sim.student@monday.kg", "Демо Ученик"),
    ("teacher", "Учитель", "aibek@monday.kg", "sim.teacher@monday.kg", "Демо Учитель"),
    ("assistant", "Ассистент", "assistant@monday.kg", "sim.assistant@monday.kg", "Демо Ассистент"),
    ("sales_manager", "Менеджер продаж", "manager@monday.kg", "sim.sales@monday.kg", "Демо Менеджер"),
    ("supervisor", "Супервайзер", "sup@monday.kg", "sim.supervisor@monday.kg", "Демо Супервайзер"),
)
SIM_ROLE_MAP = {row[0]: row for row in SIM_ROLES}


def verified_sim_admin():
    """Return the underlying real admin User iff the current session holds a verified simulation marker."""
    if not current_user.is_authenticated:
        return None
    admin_id = session.get("_sim_admin_id")
    admin_ver = session.get("_sim_admin_ver")
    if not admin_id or admin_ver is None:
        return None
    try:
        uid = int(admin_id)
        ver = int(admin_ver)
    except (TypeError, ValueError):
        return None
    admin = db.session.get(User, uid)
    if not admin or not admin.is_admin or admin.is_blocked:
        return None
    if int(admin.session_version or 1) != ver:
        return None
    return admin


def _resolve_dummy_user(role: str, *, sandbox_only: bool = False) -> User:
    """Return an active password-auth dummy account for `role`, creating a sandbox user if absent."""
    spec = SIM_ROLE_MAP.get(role)
    if spec is None:
        abort(400)
    _role, _label, preferred_email, sandbox_email, default_name = spec

    user = None if sandbox_only else User.query.filter_by(email=preferred_email, role=role).first()
    if user and user.auth_provider == "google":
        user = None
    if user is None:
        user = User.query.filter_by(email=sandbox_email).first()
        if user and user.auth_provider == "google":
            user = None
    if user is None:
        user = User(
            email=sandbox_email,
            name=default_name,
            role=role,
            auth_provider="password",
            is_approved=True,
            is_blocked=False,
            must_change_password=False,
        )
        # Random unguessable password so sandbox accounts are never reachable via public /login
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        db.session.flush()
    else:
        user.role = role
        user.is_approved = True
        user.is_blocked = False
        user.must_change_password = False

    if role == "student":
        if not user.profile:
            user.profile = StudentProfile(user_id=user.id, exam="SAT", onboarded=True)
        else:
            if not user.profile.exam:
                user.profile.exam = "SAT"
            user.profile.onboarded = True
    return user


def _sim_landing_url(target: User) -> str:
    if target.role in ("sales_manager", "supervisor"):
        return url_for("manager.dashboard")
    if target.role == "assistant":
        return url_for("assistant.home")
    if target.role == "teacher":
        return url_for("teacher.dashboard") if target.is_approved else url_for("auth.pending")
    if target.profile and target.profile.onboarded:
        return url_for("student.home")
    return url_for("student.onboarding")


def _last_active(user_ids):
    """Last time each user did anything: last_seen_at, or their latest attempt."""
    rows = (db.session.query(Attempt.user_id, func.max(Attempt.started_at))
            .filter(Attempt.user_id.in_(user_ids)).group_by(Attempt.user_id).all()) if user_ids else []
    last = dict(rows)
    return last


def _overview():
    now = utcnow()
    days = 30
    start = (now - timedelta(days=days - 1)).date()
    signup_dates = db.session.query(User.created_at).filter(User.created_at >= now - timedelta(days=days)).all()
    signups = Counter(dt.date() for (dt,) in signup_dates if dt)
    series = [{"day": start + timedelta(days=i), "n": signups.get(start + timedelta(days=i), 0)} for i in range(days)]
    peak = max([d["n"] for d in series] + [1])
    week = now - timedelta(days=7)
    active_ids = {u for (u,) in db.session.query(Attempt.user_id).filter(Attempt.started_at >= week).distinct()}
    active_ids |= {u for (u,) in db.session.query(User.id).filter(User.last_seen_at >= week).all()}
    tests_week = Attempt.query.filter(Attempt.finished_at >= week, Attempt.work_version_id.isnot(None)).count()
    tests_month = Attempt.query.filter(Attempt.finished_at >= now - timedelta(days=30),
                                       Attempt.work_version_id.isnot(None)).count()
    answers_week = (
        db.session.query(func.count(AttemptAnswer.id))
        .join(Attempt, Attempt.id == AttemptAnswer.attempt_id)
        .filter(Attempt.started_at >= week)
        .scalar()
        or 0
    )

    # content health: skills (third level) with too few published questions, per exam
    thin_rows = content_gaps(THIN)
    by_exam = Counter(ex for row in thin_rows for ex, _c in row["gaps"])
    thin, thin_total = thin_rows, len(thin_rows)
    return {"series": series, "peak": peak, "signups_month": sum(signups.values()),
            "active_week": len(active_ids), "tests_week": tests_week, "tests_month": tests_month,
            "answers_week": answers_week, "thin": thin[:20], "thin_total": thin_total, "thin_by_exam": by_exam}


def _people(role, args):
    q = (args.get("q") or "").strip().lower()
    exam = args.get("exam") or ""
    teacher = args.get("teacher", type=int)
    joined = args.get("joined") or ""
    users = (
        User.query.options(joinedload(User.profile))
        .filter_by(role=role)
        .order_by(User.created_at.desc())
        .all()
    )
    if q:
        users = [u for u in users if q in u.name.lower() or q in u.email.lower()]
    if role == "student" and exam:
        users = [u for u in users if u.profile and u.profile.exam == exam]
    if role == "student" and teacher:
        linked = {r.student_user_id for r in StudentRecord.query.filter_by(teacher_id=teacher).all()}
        users = [u for u in users if u.id in linked]
    if joined in ("7", "30"):
        since = utcnow() - timedelta(days=int(joined))
        users = [u for u in users if u.created_at and u.created_at >= since]
    return users


@bp.route("/")
@admin_required
def index():
    tab = request.args.get("tab", "overview")
    if tab not in TABS:
        tab = "overview"
    pending_teachers = User.query.filter_by(role="teacher", is_approved=False).order_by(User.created_at).all()
    pending_works = Work.query.filter_by(status="pending").order_by(Work.updated_at).all()
    counts = dict(db.session.query(User.role, func.count(User.id)).group_by(User.role).all())
    for r in ROLES:
        counts.setdefault(r, 0)
    pending_questions = Question.query.filter_by(status="pending").count()
    ctx = {"tab": tab, "pending_teachers": pending_teachers, "pending_works": pending_works, "counts": counts,
           "pending_questions": pending_questions, "sim_roles": SIM_ROLES,
           "args": request.args, "teachers_all": User.query.filter_by(role="teacher").order_by(User.name).all()}

    if tab == "overview":
        from .support_images import support_storage_stats
        ctx["ov"] = _overview()
        ctx["support_storage"] = support_storage_stats()
    if tab in PEOPLE:
        role = PEOPLE[tab]
        users = _people(role, request.args)
        page = max(1, request.args.get("page", 1, type=int))
        pages = max(1, (len(users) + PER_PAGE - 1) // PER_PAGE)
        page = min(page, pages)
        shown = users[(page - 1) * PER_PAGE: page * PER_PAGE]
        ids = [u.id for u in shown]
        last = _last_active(ids)
        extra = {}
        if role == "teacher":
            rec = dict(db.session.query(StudentRecord.teacher_id, func.count(StudentRecord.id))
                       .filter(StudentRecord.teacher_id.in_(ids)).group_by(StudentRecord.teacher_id).all()) if ids else {}
            works = dict(db.session.query(Work.author_id, func.count(Work.id))
                         .filter(Work.author_id.in_(ids)).group_by(Work.author_id).all()) if ids else {}
            extra = {i: {"students": rec.get(i, 0), "works": works.get(i, 0)} for i in ids}
        elif role == "assistant":
            extra = _assistant_stats_bulk(ids)
        elif role == "student":
            links = defaultdict(list)
            for r in (
                StudentRecord.query.options(joinedload(StudentRecord.teacher))
                .filter(StudentRecord.student_user_id.in_(ids))
                .all()
                if ids else []
            ):
                if r.teacher:
                    links[r.student_user_id].append(r.teacher.name)
            extra = {i: {"teachers": links.get(i, [])} for i in ids}
        last_login = {}
        if ids:
            for le in (LoginEvent.query.filter(LoginEvent.user_id.in_(ids))
                       .order_by(LoginEvent.created_at.desc()).all()):
                if le.user_id not in last_login:
                    last_login[le.user_id] = le
        ctx.update(users=shown, total=len(users), page=page, pages=pages, extra=extra,
                   last_login=last_login,
                   last={u.id: max([d for d in (u.last_seen_at, last.get(u.id)) if d] or [None]) for u in shown})
    user_id = request.args.get("user", type=int)
    ctx["panel"] = _panel(user_id) if user_id else None
    if request.args.get("fragment") and user_id:
        return render_template("admin/_panel_body.html", **ctx)
    return render_template("admin/index.html", **ctx)


def _assistant_stats_bulk(user_ids):
    if not user_ids:
        return {}
    week = utcnow() - timedelta(days=7)
    qs = Question.query.options(joinedload(Question.skill)).filter(Question.author_id.in_(user_ids)).all()
    by_author = defaultdict(list)
    for q in qs:
        by_author[q.author_id].append(q)
    out = {}
    for uid in user_ids:
        uqs = by_author[uid]
        reviewed = [q for q in uqs if q.reviewed_at]
        approved = [q for q in reviewed if q.status == "published"]
        topics = Counter(q.skill.topic for q in uqs if q.skill).most_common(3)
        out[uid] = {
            "total": len(uqs),
            "week": sum(1 for q in uqs if q.created_at and q.created_at >= week),
            "pending": sum(1 for q in uqs if q.status == "pending"),
            "approved_pct": round(100 * len(approved) / len(reviewed)) if reviewed else None,
            "topics": topics,
        }
    return out


def _assistant_stats(user_id):
    return _assistant_stats_bulk([user_id])[user_id]


def _panel(user_id):
    u = db.session.get(User, user_id) or abort(404)
    data = {"user": u, "role": u.role}
    attempts = (Attempt.query.options(joinedload(Attempt.work_version))
                .filter_by(user_id=u.id).filter(Attempt.finished_at.isnot(None))
                .order_by(Attempt.finished_at.desc()).limit(6).all())
    data["attempts"] = attempts
    last_attempt = Attempt.query.filter_by(user_id=u.id).order_by(Attempt.started_at.desc()).first()
    login_events = (LoginEvent.query.filter_by(user_id=u.id)
                    .order_by(LoginEvent.created_at.desc()).limit(10).all())
    data["login_events"] = login_events
    data["last_login"] = login_events[0] if login_events else None
    data["last"] = max([d for d in (u.last_seen_at, last_attempt.started_at if last_attempt else None,
                                    login_events[0].created_at if login_events else None) if d] or [None])
    if u.role == "student":
        data["teachers"] = [
            r.teacher
            for r in StudentRecord.query.options(joinedload(StudentRecord.teacher))
            .filter_by(student_user_id=u.id)
            .all()
            if r.teacher
        ]
        exam = u.profile.exam if u.profile else None
        data["summary"] = progress_summary(u.id, exam) if exam else None
        from .models import Subscription, SubscriptionPlan
        from .subscriptions import get_or_create_default_plan, subscription_status_summary

        get_or_create_default_plan()
        db.session.flush()
        data["subscription_status"] = subscription_status_summary(u)
        data["subscription_plans"] = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.price_amount.asc()).all()
        data["subscriptions"] = (
            Subscription.query.filter_by(user_id=u.id)
            .order_by(Subscription.id.desc())
            .limit(5)
            .all()
        )
    elif u.role == "assistant":
        data["astats"] = _assistant_stats(u.id)
    elif u.role == "teacher":
        from .student_links import teacher_open_records_query

        records = StudentRecord.query.filter_by(teacher_id=u.id).order_by(StudentRecord.name).all()
        open_records = teacher_open_records_query(u.id).all()
        subj_set = {r.exam for r in open_records if getattr(r, "exam", None)}
        for r in open_records:
            if getattr(r, "course", None) and getattr(r.course, "name", None):
                subj_set.add(r.course.name)
        data["records"] = records
        data["active_students_count"] = len(open_records)
        data["teacher_subjects"] = sorted(subj_set)
        data["works"] = Work.query.filter_by(author_id=u.id).count()
        data["questions"] = Question.query.filter_by(author_id=u.id).count()
    return data


def _back():
    target = request.form.get("next") or ""
    return redirect(target if target.startswith("/admin") and not target.startswith("//") else url_for("admin.index"))


@bp.route("/simulate", methods=["POST"])
@login_required
def simulate():
    """Let an admin enter any non-admin dummy role or user workspace for live preview."""
    real_admin = current_user._get_current_object() if current_user.is_admin else verified_sim_admin()
    if real_admin is None or not real_admin.is_admin or real_admin.is_blocked:
        abort(403)

    role = (request.form.get("role") or "").strip().lower()
    user_id = request.form.get("user_id", type=int)

    if user_id:
        target = db.session.get(User, user_id) or abort(404)
        if target.is_admin or target.is_blocked:
            flash(_("Нельзя симулировать заблокированный аккаунт или другого админа."), "error")
            return _back()
    elif role in SIM_ROLE_MAP:
        target = _resolve_dummy_user(role)
    else:
        abort(400)

    write_audit_log(
        actor_id=real_admin.id,
        action="admin_simulate_start",
        entity_type="user",
        entity_id=target.id,
        old_value={"admin_id": real_admin.id},
        new_value={"role": target.role, "email": target.email},
    )
    session["_sim_admin_id"] = real_admin.id
    session["_sim_admin_ver"] = int(real_admin.session_version or 1)
    session["_sim_role"] = target.role
    login_user(target)
    db.session.commit()
    return redirect(_sim_landing_url(target))


@bp.route("/simulate/exit", methods=["POST"])
@login_required
def simulate_exit():
    """Restore the underlying verified admin session after role simulation."""
    admin = verified_sim_admin()
    if admin is None:
        session.pop("_sim_admin_id", None)
        session.pop("_sim_admin_ver", None)
        session.pop("_sim_role", None)
        abort(403)

    write_audit_log(
        actor_id=admin.id,
        action="admin_simulate_stop",
        entity_type="user",
        entity_id=current_user.id,
        old_value={"role": current_user.role, "email": current_user.email},
        new_value={"admin_id": admin.id},
    )
    login_user(admin)
    session.pop("_sim_admin_id", None)
    session.pop("_sim_admin_ver", None)
    session.pop("_sim_role", None)
    db.session.commit()
    flash(_("Режим симуляции завершён."), "info")
    return redirect(url_for("admin.index"))


def _overview_ctx(tab: str = "overview"):
    pending_teachers = User.query.filter_by(role="teacher", is_approved=False).order_by(User.created_at).all()
    pending_works = Work.query.filter_by(status="pending").order_by(Work.updated_at).all()
    counts = dict(db.session.query(User.role, func.count(User.id)).group_by(User.role).all())
    for r in ROLES:
        counts.setdefault(r, 0)
    pending_questions = Question.query.filter_by(status="pending").count()
    ctx = {
        "tab": tab,
        "pending_teachers": pending_teachers,
        "pending_works": pending_works,
        "counts": counts,
        "pending_questions": pending_questions,
        "sim_roles": SIM_ROLES,
        "args": request.args,
        "teachers_all": User.query.filter_by(role="teacher").order_by(User.name).all(),
    }
    if tab == "overview":
        from .support_images import support_storage_stats
        ctx["ov"] = _overview()
        ctx["support_storage"] = support_storage_stats()
    return ctx


@bp.route("/simulate/credentials", methods=["POST"])
@limiter.limit("20 per minute", methods=["POST"])
@admin_required
def simulate_credentials():
    """Issue fresh working passwords for dummy role accounts and show them once (no-store)."""
    req_role = (request.form.get("role") or "all").strip().lower()
    if req_role == "all":
        roles = [row[0] for row in SIM_ROLES]
    elif req_role in SIM_ROLE_MAP:
        roles = [req_role]
    else:
        abort(400)

    dummy_creds = []
    for r in roles:
        u = _resolve_dummy_user(r, sandbox_only=True)
        raw_pw = secrets.token_urlsafe(10)
        u.set_password(raw_pw)
        u.must_change_password = False
        u.is_approved = True
        u.is_blocked = False
        write_audit_log(
            actor_id=current_user.id,
            action="admin_dummy_password_issue",
            entity_type="user",
            entity_id=u.id,
            new_value={"role": u.role, "email": u.email},
        )
        dummy_creds.append({
            "user_id": u.id,
            "role": r,
            "label": SIM_ROLE_MAP[r][1],
            "email": u.email,
            "name": u.name,
            "password": raw_pw,
        })

    db.session.commit()
    ctx = _overview_ctx("overview")
    ctx["dummy_creds"] = dummy_creds
    resp = make_response(render_template("admin/index.html", **ctx))
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


@bp.route("/users/<int:user_id>/approve", methods=["POST"])
@admin_required
def approve(user_id):
    u = db.session.get(User, user_id) or abort(404)
    u.is_approved = request.form.get("decision") != "reject"
    if not u.is_approved:
        u.role = "student"
        if not u.profile:
            u.profile = StudentProfile()
        flash(_("Заявка отклонена: %(name)s теперь ученик.", name=u.name), "info")
    else:
        flash(_("%(name)s подтверждён как учитель.", name=u.name), "success")
    db.session.commit()
    return _back()


@bp.route("/users/<int:user_id>/role", methods=["POST"])
@admin_required
def set_role(user_id):
    u = db.session.get(User, user_id) or abort(404)
    role = request.form.get("role")
    if u.id == current_user.id:
        flash(_("Нельзя менять собственную роль."), "error")
    elif role in ROLES:
        old_role = u.role
        u.role = role
        u.is_approved = True
        if role == "student" and not u.profile:
            u.profile = StudentProfile()
        if old_role != role:
            from .audit import write_audit_log
            write_audit_log(
                actor_id=current_user.id,
                action="role_change",
                entity_type="user",
                entity_id=u.id,
                old_value={"role": old_role},
                new_value={"role": role},
                reason=request.form.get("reason", ""),
            )
        db.session.commit()
        flash(_("%(name)s: роль изменена.", name=u.name), "success")
    return _back()


@bp.route("/users/<int:user_id>/methodist", methods=["POST"])
@admin_required
def methodist(user_id):
    u = db.session.get(User, user_id) or abort(404)
    if u.role != "teacher":
        abort(400)
    u.is_methodist = request.form.get("on") == "1"
    db.session.commit()
    flash(_("%(name)s теперь методист: проверяет вопросы ассистентов.", name=u.name) if u.is_methodist
          else _("%(name)s больше не методист.", name=u.name), "success")
    return _back()


@bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def reset_password(user_id):
    u = db.session.get(User, user_id) or abort(404)
    if u.is_admin:
        flash(_("Пароль администратора меняется только в его настройках."), "error")
        return _back()
    raw = temporary_password(u)
    db.session.commit()
    notice = _("Временный пароль для %(name)s: %(password)s. Он показан один раз.", name=u.name, password=raw)
    pending_teachers = User.query.filter_by(role="teacher", is_approved=False).order_by(User.created_at).all()
    pending_works = Work.query.filter_by(status="pending").order_by(Work.updated_at).all()
    counts = {r: User.query.filter_by(role=r).count() for r in ROLES}
    pending_questions = Question.query.filter_by(status="pending").count()
    resp = make_response(render_template(
        "admin/index.html", tab="overview", ov=_overview(), pending_teachers=pending_teachers,
        pending_works=pending_works, counts=counts, pending_questions=pending_questions,
        args=request.args, teachers_all=User.query.filter_by(role="teacher").order_by(User.name).all(),
        panel=_panel(u.id), one_time_notice=notice,
    ))
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


@bp.route("/users/<int:user_id>/block", methods=["POST"])
@admin_required
def block(user_id):
    u = db.session.get(User, user_id) or abort(404)
    if u.id == current_user.id:
        flash(_("Нельзя заблокировать себя."), "error")
        return _back()
    u.is_blocked = request.form.get("on") == "1"
    if u.is_blocked:
        u.invalidate_sessions()
    db.session.commit()
    flash(_("%(name)s заблокирован.", name=u.name) if u.is_blocked else _("%(name)s разблокирован.", name=u.name),
          "info" if u.is_blocked else "success")
    return _back()


@bp.route("/works/<int:work_id>/review", methods=["POST"])
@admin_required
def review_work(work_id):
    """Big public tests wait here before students can see them."""
    w = db.session.get(Work, work_id) or abort(404)
    if w.status != "pending":
        abort(400)
    w.status = "published" if request.form.get("decision") == "approve" else "draft"
    db.session.commit()
    flash(_("«%(t)s» опубликован.", t=w.title) if w.status == "published"
          else _("«%(t)s» возвращён автору в черновики.", t=w.title), "success")
    return redirect(url_for("admin.index", tab="moderation"))


@bp.route("/questions/<int:question_id>/public-sample", methods=["POST"])
@limiter.limit("30 per minute")
@admin_required
def toggle_public_sample(question_id):
    """Toggle a published question as a public sample and sync/delete its copied stem media."""
    from .public_samples import set_question_public_sample

    q = db.session.get(Question, question_id) or abort(404)
    enabled = (request.form.get("enabled") or "").strip() == "1"
    was_enabled = bool(q.is_public_sample)
    old_key = q.public_image_key
    try:
        set_question_public_sample(q, enabled)
    except ValueError as exc:
        if request.headers.get("X-Requested-With") == "fetch":
            return {"ok": False, "error": str(exc)}, 400
        flash(str(exc), "error")
        return _back()

    write_audit_log(
        actor_id=current_user.id,
        action="question_public_sample_toggle",
        entity_type="question",
        entity_id=q.id,
        old_value={"is_public_sample": was_enabled, "public_image_key": old_key},
        new_value={"is_public_sample": q.is_public_sample, "public_image_key": q.public_image_key},
    )
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return {"ok": True, "is_public_sample": q.is_public_sample, "public_image_key": q.public_image_key}
    flash(
        _("Вопрос добавлен в бесплатные примеры.") if q.is_public_sample else _("Вопрос убран из бесплатных примеров."),
        "success",
    )
    return _back()


@bp.route("/users/<int:user_id>/subscription/grant", methods=["POST"])
@limiter.limit("30 per minute")
@admin_required
def subscription_grant(user_id):
    """Manually grant an active or trialing question-bank subscription (audited)."""
    from .models import SubscriptionPlan
    from .subscriptions import get_or_create_default_plan, grant_manual_subscription

    u = db.session.get(User, user_id) or abort(404)
    if u.role != "student":
        abort(400)
    plan_id = request.form.get("plan_id", type=int)
    plan = db.session.get(SubscriptionPlan, plan_id) if plan_id else get_or_create_default_plan()
    if not plan:
        abort(404)
    status = (request.form.get("status") or "active").strip()
    days = request.form.get("days", type=int)
    note = (request.form.get("note") or "").strip()
    try:
        sub = grant_manual_subscription(
            current_user._get_current_object(),
            u,
            plan,
            status=status,
            duration_days=days,
            note=note,
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return _back()
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return {"ok": True, "subscription_id": sub.id, "status": sub.status}
    flash(_("Подписка на банк вопросов выдана."), "success")
    return _back()


@bp.route("/subscriptions/<int:sub_id>/plan", methods=["POST"])
@limiter.limit("30 per minute")
@admin_required
def subscription_change_plan(sub_id):
    """Change the SubscriptionPlan on an existing subscription (audited)."""
    from .models import Subscription, SubscriptionPlan
    from .subscriptions import change_subscription_plan

    sub = db.session.get(Subscription, sub_id) or abort(404)
    plan_id = request.form.get("plan_id", type=int) or abort(400)
    plan = db.session.get(SubscriptionPlan, plan_id) or abort(404)
    note = (request.form.get("note") or "").strip()
    change_subscription_plan(current_user._get_current_object(), sub, plan, note=note)
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return {"ok": True, "subscription_id": sub.id, "plan_id": sub.plan_id}
    flash(_("Тариф подписки обновлён."), "success")
    return _back()


@bp.route("/subscriptions/<int:sub_id>/cancel", methods=["POST"])
@limiter.limit("30 per minute")
@admin_required
def subscription_cancel(sub_id):
    """Immediately cancel a subscription (audited)."""
    from .models import Subscription
    from .subscriptions import cancel_subscription

    sub = db.session.get(Subscription, sub_id) or abort(404)
    note = (request.form.get("note") or "").strip()
    cancel_subscription(current_user._get_current_object(), sub, note=note)
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return {"ok": True, "subscription_id": sub.id, "status": sub.status}
    flash(_("Подписка отменена."), "info")
    return _back()


@bp.route("/subscriptions/plans", methods=["POST"])
@limiter.limit("20 per minute")
@admin_required
def subscription_plan_create():
    """Create a configurable SubscriptionPlan (audited)."""
    from .models import SubscriptionPlan

    code = (request.form.get("code") or "").strip().lower()[:48]
    name = (request.form.get("name") or "").strip()[:120]
    price_amount = request.form.get("price_amount", type=int)
    currency = (request.form.get("currency") or "USD").strip().upper()[:8]
    duration_days = max(1, int(request.form.get("duration_days", type=int) or 30))
    stripe_price_id = (request.form.get("stripe_price_id") or "").strip()[:64] or None
    if not code or not name or price_amount is None or price_amount < 0:
        abort(400)
    if SubscriptionPlan.query.filter_by(code=code).first():
        abort(409)
    plan = SubscriptionPlan(
        code=code,
        name=name,
        description=(request.form.get("description") or "").strip(),
        price_amount=price_amount,
        currency=currency,
        duration_days=duration_days,
        stripe_price_id=stripe_price_id,
        is_active=True,
    )
    db.session.add(plan)
    db.session.flush()
    write_audit_log(
        actor_id=current_user.id,
        action="subscription_plan_created",
        entity_type="subscription_plan",
        entity_id=plan.id,
        new_value={"code": plan.code, "price_amount": plan.price_amount, "currency": plan.currency, "duration_days": duration_days, "stripe_price_id": stripe_price_id},
    )
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return {"ok": True, "plan_id": plan.id}
    flash(_("План подписки создан."), "success")
    return _back()


@bp.route("/account", methods=["GET", "POST"])
@limiter.limit("20 per minute", methods=["POST"])
@admin_required
def account():
    """Admin settings & account preferences matching /manager/account layout."""
    min_len = min_password_length(current_user.role)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "profile":
            new_name = (request.form.get("name") or "").strip()
            if len(new_name) < 2 or len(new_name) > 120:
                flash(_("Имя должно быть от 2 до 120 символов."), "error")
            else:
                user_obj = current_user._get_current_object()
                old_name = user_obj.name
                if new_name != old_name:
                    user_obj.name = new_name
                    write_audit_log(
                        actor_id=user_obj.id,
                        action="admin_profile_update",
                        entity_type="user",
                        entity_id=user_obj.id,
                        old_value={"name": old_name},
                        new_value={"name": new_name},
                    )
                    db.session.commit()
                flash(_("Профиль обновлён."), "success")
        elif action == "password":
            cur_pw = request.form.get("current", "")
            new_pw = request.form.get("new", "")
            if not current_user.check_password(cur_pw):
                flash(_("Текущий пароль неверный."), "error")
            elif len(new_pw) < min_len:
                flash(_("Новый пароль должен быть не короче %(n)s символов.", n=min_len), "error")
            else:
                user_obj = current_user._get_current_object()
                user_obj.set_password(new_pw)
                user_obj.must_change_password = False
                write_audit_log(
                    actor_id=user_obj.id,
                    action="admin_password_change",
                    entity_type="user",
                    entity_id=user_obj.id,
                    old_value=None,
                    new_value={"session_version": user_obj.session_version},
                )
                db.session.commit()
                login_user(user_obj)
                flash(_("Пароль изменён."), "success")
        return redirect(url_for("admin.account"))

    return render_template("admin/account.html", min_pw_len=min_len)


@bp.app_template_filter("ago")
def ago(dt):
    """'сегодня', 'вчера', '5 дн. назад', or a date."""
    if not dt:
        return _("ещё не заходил")
    days = (utcnow().date() - dt.date()).days
    if days <= 0:
        return _("сегодня")
    if days == 1:
        return _("вчера")
    if days < 30:
        return _("%(n)s дн. назад", n=days)
    from flask_babel import format_date
    return format_date(dt, "d MMM y")


EXAM_CODES = list(EXAMS.keys())

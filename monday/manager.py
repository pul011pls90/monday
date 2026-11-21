"""Manager CRM & Supervisor workspace (Stage 3 UI: dashboard, leads, lead card, pipeline, audit)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta

from flask import Blueprint, abort, current_app, flash, make_response, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from .access import CRM_ROLES, manager_required, min_password_length, permission_required, supervisor_required
from .audit import write_audit_log
from .auth import _safe_next
from .constants import EXAMS
from .extensions import db
from .models import (
    AcademicCourse,
    AuditLog,
    GroupEnrollment,
    LEAD_ACTIVITY_TYPES,
    LEAD_MODE_PREFERENCES,
    LEAD_SOURCES,
    LEAD_STATUSES,
    LEAD_TEMPERATURES,
    Lead,
    LeadActivity,
    LeadTask,
    Lesson,
    LessonAttendance,
    MembershipPlan,
    PASS_STATUSES,
    PAYMENT_KINDS,
    PAYMENT_METHODS,
    PAY_RATE_TYPES,
    PaymentTransaction,
    StudentPass,
    StudentProfile,
    StudentRecord,
    StudyGroup,
    TeacherPayRate,
    User,
    local_midnight_utc,
    utcnow,
)
from .services import temporary_password

bp = Blueprint("manager", __name__, url_prefix="/manager")

STATUS_LABELS = {
    "new": "Новый",
    "contacted": "Связались",
    "trial_scheduled": "Пробный назначен",
    "trial_done": "Пробный пройден",
    "negotiation": "Переговоры",
    "won": "Оплатил / Ученик",
    "lost": "Отказ",
}

SOURCE_LABELS = {
    "instagram": "Instagram",
    "whatsapp": "WhatsApp",
    "telegram": "Telegram",
    "site": "Сайт",
    "referral": "Рекомендация",
    "other": "Другое",
}

ACTIVITY_LABELS = {
    "call": "Звонок",
    "message": "Сообщение",
    "note": "Заметка",
    "status_change": "Смена статуса",
    "reassign": "Переназначение / объединение",
}

TEMPERATURE_LABELS = {
    "cold": "Холодный",
    "warm": "Тёплый",
    "hot": "Горячий",
}

ALLOWED_LEAD_TRANSITIONS = {
    "new": frozenset({"contacted", "trial_scheduled", "lost"}),
    "contacted": frozenset({"trial_scheduled", "trial_done", "negotiation", "lost"}),
    "trial_scheduled": frozenset({"contacted", "trial_done", "negotiation", "lost"}),
    "trial_done": frozenset({"trial_scheduled", "negotiation", "won", "lost"}),
    "negotiation": frozenset({"trial_scheduled", "trial_done", "won", "lost"}),
    "won": frozenset(),
    "lost": frozenset({"new", "contacted"}),
}

MODE_PREF_LABELS = {
    "": "Не указано",
    "online": "Онлайн",
    "offline": "Офлайн",
    "any": "Любой",
}

METHOD_LABELS = {
    "cash": "Наличные",
    "mbank": "MBank",
    "transfer": "Перевод",
    "card": "Карта",
}

PASS_STATUS_LABELS = {
    "active": "Активен",
    "frozen": "Заморожен",
    "depleted": "Исчерпан",
    "expired": "Истёк",
    "cancelled": "Отменён",
}

RATE_TYPE_LABELS = {
    "per_lesson": "За урок",
    "per_student": "За ученика",
    "fixed_month": "Оклад в мес.",
}


def _sla_threshold_minutes() -> int:
    try:
        return max(1, int(current_app.config.get("CRM_SLA_MINUTES", 15) or 15))
    except Exception:
        return 15


def _format_duration_minutes(total_minutes: int) -> str:
    mins = max(0, int(total_minutes))
    if mins < 60:
        return f"{mins} мин"
    hours, rem = divmod(mins, 60)
    if hours < 24:
        return f"{hours}ч {rem}м" if rem else f"{hours}ч"
    days, rem_h = divmod(hours, 24)
    return f"{days}д {rem_h}ч" if rem_h else f"{days}д"


def _lead_sla(lead: Lead, now: datetime | None = None) -> dict:
    """Compute speed-to-lead metrics: unanswered wait time & overdue badge (> threshold)."""
    now = now or utcnow()
    threshold = _sla_threshold_minutes()
    created = lead.created_at or now
    if lead.first_contact_at is not None:
        resp_min = max(0, int((lead.first_contact_at - created).total_seconds() // 60))
        return {
            "unanswered": False,
            "overdue": False,
            "minutes": resp_min,
            "label": _format_duration_minutes(resp_min),
            "threshold": threshold,
        }
    if lead.status in ("won", "lost"):
        return {
            "unanswered": False,
            "overdue": False,
            "minutes": 0,
            "label": "—",
            "threshold": threshold,
        }
    wait_min = max(0, int((now - created).total_seconds() // 60))
    return {
        "unanswered": True,
        "overdue": wait_min >= threshold,
        "minutes": wait_min,
        "label": _format_duration_minutes(wait_min),
        "threshold": threshold,
    }


def _crm_managers():
    return (
        User.query.filter(User.role.in_(CRM_ROLES), User.is_blocked.is_(False))
        .order_by(User.name.asc())
        .all()
    )


def _leads_scope(query=None):
    q = query if query is not None else Lead.query
    if not current_user.has_perm("crm.leads.view_all"):
        q = q.filter(Lead.assigned_manager_id == current_user.id)
    return q


def _get_lead_or_403(lead_id: int) -> Lead:
    lead = db.session.get(Lead, lead_id)
    if lead is None:
        abort(404)
    if not current_user.has_perm("crm.leads.view_all") and lead.assigned_manager_id != current_user.id:
        abort(403)
    return lead


def _parse_date(raw: str | None) -> date | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _parse_due_at(raw: str | None) -> datetime:
    s = (raw or "").strip()
    if s:
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s[:16], fmt)
                if fmt == "%Y-%m-%d":
                    dt = dt.replace(hour=12, minute=0)
                return dt
            except ValueError:
                continue
    return utcnow() + timedelta(hours=2)


def _safe_back(fallback_endpoint: str, **fallback_kwargs):
    nxt = _safe_next(request.form.get("next") or request.args.get("next"))
    if nxt and nxt.startswith("/manager"):
        return redirect(nxt)
    return redirect(url_for(fallback_endpoint, **fallback_kwargs))


def _common_ctx() -> dict:
    return {
        "LEAD_STATUSES": LEAD_STATUSES,
        "LEAD_SOURCES": LEAD_SOURCES,
        "LEAD_ACTIVITY_TYPES": LEAD_ACTIVITY_TYPES,
        "LEAD_MODE_PREFERENCES": LEAD_MODE_PREFERENCES,
        "LEAD_TEMPERATURES": LEAD_TEMPERATURES,
        "STATUS_LABELS": STATUS_LABELS,
        "SOURCE_LABELS": SOURCE_LABELS,
        "ACTIVITY_LABELS": ACTIVITY_LABELS,
        "MODE_PREF_LABELS": MODE_PREF_LABELS,
        "TEMPERATURE_LABELS": TEMPERATURE_LABELS,
        "sla_threshold": _sla_threshold_minutes(),
        "lead_sla": _lead_sla,
    }


# --------------------------------------------------------------------------- Dashboard


@bp.route("", strict_slashes=False)
@manager_required
def dashboard():
    """Manager / Supervisor CRM dashboard: KPIs, SLA alerts, 4-bucket task board, funnel counts."""
    now = utcnow()
    day_start = local_midnight_utc()
    day_end = day_start + timedelta(days=1)
    week_end = day_start + timedelta(days=7)

    leads = (
        _leads_scope(Lead.query.options(joinedload(Lead.assigned_manager)))
        .order_by(Lead.created_at.desc())
        .all()
    )
    funnel = Counter(l.status for l in leads)
    new_leads = [l for l in leads if l.status == "new"]
    unanswered_leads = sorted(
        [l for l in leads if l.first_contact_at is None and l.status not in ("won", "lost")],
        key=lambda l: l.created_at or now,
    )
    sla_overdue_leads = [l for l in unanswered_leads if _lead_sla(l, now)["overdue"]]

    scope = "all" if (current_user.has_perm("crm.leads.view_all") and request.args.get("scope") == "all") else "mine"
    task_q = LeadTask.query.options(joinedload(LeadTask.lead), joinedload(LeadTask.assignee)).filter(
        LeadTask.done_at.is_(None)
    )
    if scope == "mine":
        task_q = task_q.filter(LeadTask.assignee_id == current_user.id)
    open_tasks = task_q.order_by(LeadTask.due_at.asc()).all()

    overdue_tasks = [t for t in open_tasks if t.due_at and t.due_at < now]
    today_tasks = [t for t in open_tasks if t.due_at and now <= t.due_at < day_end]
    week_tasks = [t for t in open_tasks if t.due_at and day_end <= t.due_at < week_end]
    later_tasks = [t for t in open_tasks if (t.due_at is None) or (t.due_at >= week_end)]

    return render_template(
        "manager/dashboard.html",
        **_common_ctx(),
        now_utc=now,
        scope=scope,
        total_leads=len(leads),
        new_count=len(new_leads),
        sla_overdue_count=len(sla_overdue_leads),
        overdue_tasks=overdue_tasks,
        today_tasks=today_tasks,
        week_tasks=week_tasks,
        later_tasks=later_tasks,
        unanswered_leads=unanswered_leads[:12],
        funnel={s: funnel.get(s, 0) for s in LEAD_STATUSES},
        managers=_crm_managers(),
    )


# --------------------------------------------------------------------------- Lead List & Creation


@bp.route("/leads")
@manager_required
def leads():
    """Dense filterable lead list with search, SLA badges, and quick status updates."""
    now = utcnow()
    status = (request.args.get("status") or "").strip()
    source = (request.args.get("source") or "").strip()
    manager_id = request.args.get("manager", type=int)
    sla_filter = (request.args.get("sla") or "").strip()
    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"))
    q = (request.args.get("q") or "").strip()

    query = _leads_scope(Lead.query.options(joinedload(Lead.assigned_manager), joinedload(Lead.converted_student)))
    if status in LEAD_STATUSES:
        query = query.filter(Lead.status == status)
    if source in LEAD_SOURCES:
        query = query.filter(Lead.source == source)
    if current_user.has_perm("crm.leads.view_all") and manager_id:
        query = query.filter(Lead.assigned_manager_id == manager_id)
    if date_from:
        query = query.filter(Lead.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.filter(Lead.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    if q:
        escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped_q}%"
        query = query.filter(
            or_(
                Lead.full_name.ilike(like, escape="\\"),
                Lead.phone.ilike(like, escape="\\"),
                Lead.messenger_handle.ilike(like, escape="\\"),
                Lead.interest.ilike(like, escape="\\"),
            )
        )

    rows = query.order_by(Lead.created_at.desc()).all()
    if sla_filter == "overdue":
        rows = [l for l in rows if _lead_sla(l, now)["overdue"]]

    per_page = 50
    total = len(rows)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(total_pages, request.args.get("page", 1, type=int) or 1))
    page_rows = rows[(page - 1) * per_page : page * per_page]

    raw_status_counts = dict(
        _leads_scope(db.session.query(Lead.status, db.func.count(Lead.id)))
        .group_by(Lead.status)
        .all()
    )
    status_counts = {s: int(raw_status_counts.get(s, 0)) for s in LEAD_STATUSES}
    total_all_leads = sum(status_counts.values())

    return render_template(
        "manager/leads.html",
        **_common_ctx(),
        now_utc=now,
        leads=page_rows,
        managers=_crm_managers(),
        status_counts=status_counts,
        total_all_leads=total_all_leads,
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
        filters={
            "status": status,
            "source": source,
            "manager": manager_id or "",
            "sla": sla_filter,
            "date_from": request.args.get("date_from") or "",
            "date_to": request.args.get("date_to") or "",
            "q": q,
        },
    )


@bp.route("/leads/new", methods=["POST"])
@permission_required("crm.leads.create")
def lead_create():
    full_name = (request.form.get("full_name") or "").strip()
    phone = (request.form.get("phone") or "").strip() or None
    messenger_handle = (request.form.get("messenger_handle") or "").strip() or None
    source = (request.form.get("source") or "other").strip()
    if source not in LEAD_SOURCES:
        source = "other"
    interest = (request.form.get("interest") or "").strip()
    mode_pref = (request.form.get("mode_preference") or "").strip()
    if mode_pref not in LEAD_MODE_PREFERENCES:
        mode_pref = ""

    if len(full_name) < 2:
        flash(_("Укажите имя лида (минимум 2 символа)."), "error")
        return _safe_back("manager.leads")
    if not phone and not messenger_handle:
        flash(_("Укажите телефон или мессенджер для связи."), "error")
        return _safe_back("manager.leads")

    explicit_mgr_id = None
    if current_user.has_perm("crm.leads.reassign"):
        req_mgr = request.form.get("assigned_manager_id", type=int)
        if req_mgr:
            target = db.session.get(User, req_mgr)
            if target and target.role in CRM_ROLES and not target.is_blocked:
                explicit_mgr_id = target.id

    from .crm_intake import ingest_or_dedupe_lead

    note = (request.form.get("note") or "").strip()
    lead, deduped = ingest_or_dedupe_lead(
        full_name=full_name,
        phone=phone,
        messenger_handle=messenger_handle,
        source=source,
        interest=interest,
        mode_preference=mode_pref,
        note=note,
        explicit_manager_id=explicit_mgr_id,
        actor_id=current_user.id,
    )
    if deduped:
        flash(_("Найден открытый дубликат «%(name)s» — обращение добавлено в историю без создания нового лида.", name=lead.full_name), "info")
    else:
        mgr_name = lead.assigned_manager.name if lead.assigned_manager else "—"
        flash(_("Лид «%(name)s» добавлен (менеджер: %(mgr)s).", name=lead.full_name, mgr=mgr_name), "success")
    if not current_user.has_perm("crm.leads.view_all") and lead.assigned_manager_id != current_user.id:
        return redirect(url_for("manager.leads"))
    return redirect(url_for("manager.lead_detail", lead_id=lead.id))


# --------------------------------------------------------------------------- Lead Card & Actions


def _build_unified_timeline(lead: Lead | None = None, student_id: int | None = None) -> list[dict]:
    """Merge LeadActivity, AuditLog, GroupEnrollment, and LessonAttendance into a sorted unified timeline."""
    events: list[dict] = []
    if lead is not None:
        activities = (
            LeadActivity.query.options(joinedload(LeadActivity.actor))
            .filter_by(lead_id=lead.id)
            .all()
        )
        for a in activities:
            events.append({
                "ts": a.created_at,
                "category": "comms" if a.type in ("call", "message", "note") else "system",
                "badge": ACTIVITY_LABELS.get(a.type, a.type),
                "body": a.body,
                "actor_name": a.actor.name if a.actor else _("Система"),
                "id": a.id,
            })
        audit_rows = (
            AuditLog.query.options(joinedload(AuditLog.actor))
            .filter(AuditLog.entity_type == "lead", AuditLog.entity_id == lead.id)
            .all()
        )
        for al in audit_rows:
            summary = al.action
            if al.reason:
                summary = f"{al.action}: {al.reason}"
            events.append({
                "ts": al.timestamp,
                "category": "system",
                "badge": f"audit · {al.action}",
                "body": summary,
                "actor_name": al.actor.name if al.actor else _("Система"),
                "id": al.id,
            })
        if student_id is None and lead.converted_student_id:
            student_id = lead.converted_student_id

    if student_id is not None:
        enrs = (
            GroupEnrollment.query.options(joinedload(GroupEnrollment.group), joinedload(GroupEnrollment.course))
            .filter_by(student_user_id=student_id)
            .all()
        )
        for enr in enrs:
            gname = enr.group.name if enr.group else f"#{enr.group_id}"
            cname = enr.course.name if enr.course else ""
            events.append({
                "ts": enr.enrolled_at,
                "category": "academic",
                "badge": _("Зачисление"),
                "body": f"{gname}" + (f" ({cname})" if cname else ""),
                "actor_name": _("Учебный отдел"),
                "id": enr.id,
            })
            if enr.left_at is not None:
                events.append({
                    "ts": enr.left_at,
                    "category": "academic",
                    "badge": _("Завершение"),
                    "body": f"{gname} · {enr.status}" + (f" — {enr.note}" if enr.note else ""),
                    "actor_name": _("Учебный отдел"),
                    "id": enr.id,
                })
        atts = (
            LessonAttendance.query.options(
                joinedload(LessonAttendance.lesson).joinedload(Lesson.group),
                joinedload(LessonAttendance.marked_by),
            )
            .filter_by(student_user_id=student_id)
            .order_by(LessonAttendance.marked_at.desc())
            .limit(40)
            .all()
        )
        att_labels = {"present": "Был", "absent": "Отсутствовал", "late": "Опоздал", "excused": "Уважит. причина"}
        for att in atts:
            gname = att.lesson.group.name if (att.lesson and att.lesson.group) else f"Урок #{att.lesson_id}"
            events.append({
                "ts": att.marked_at,
                "category": "academic",
                "badge": att_labels.get(att.status, att.status),
                "body": f"{gname}" + (f" · {att.note}" if att.note else ""),
                "actor_name": att.marked_by.name if att.marked_by else _("Учитель"),
                "id": att.id,
            })
        txs = (
            PaymentTransaction.query.options(joinedload(PaymentTransaction.recorded_by))
            .filter_by(student_user_id=student_id)
            .order_by(PaymentTransaction.paid_at.desc())
            .limit(40)
            .all()
        )
        for tx in txs:
            sign = "-" if tx.kind == "refund" else "+"
            events.append({
                "ts": tx.paid_at,
                "category": "finance",
                "badge": _("Возврат") if tx.kind == "refund" else _("Оплата"),
                "body": f"{sign}{tx.amount} KGS ({METHOD_LABELS.get(tx.method, tx.method)})" + (f" · {tx.note}" if tx.note else ""),
                "actor_name": tx.recorded_by.name if tx.recorded_by else _("Система"),
                "id": tx.id,
            })

    events.sort(key=lambda e: (e["ts"] or datetime.min, e["id"]), reverse=True)
    return events


def _render_lead_detail(lead: Lead, *, one_time_notice: str | None = None):
    now = utcnow()
    tab = (request.args.get("tab") or "all").strip().lower()
    if tab not in ("all", "comms", "system", "academic"):
        tab = "all"
    activities = (
        LeadActivity.query.options(joinedload(LeadActivity.actor))
        .filter_by(lead_id=lead.id)
        .order_by(LeadActivity.created_at.desc(), LeadActivity.id.desc())
        .all()
    )
    timeline = _build_unified_timeline(lead=lead)
    filtered_timeline = timeline if tab == "all" else [e for e in timeline if e["category"] == tab]
    tasks = (
        LeadTask.query.options(joinedload(LeadTask.assignee))
        .filter_by(lead_id=lead.id)
        .order_by(LeadTask.done_at.isnot(None), LeadTask.due_at.asc())
        .all()
    )
    existing_students = (
        User.query.filter_by(role="student", is_blocked=False)
        .order_by(User.created_at.desc())
        .limit(100)
        .all()
    )
    teachers = (
        User.query.filter_by(role="teacher", is_approved=True, is_blocked=False)
        .order_by(User.name.asc())
        .all()
    )
    duplicate_candidates = []
    if current_user.has_perm("crm.leads.reassign") and lead.status not in ("won", "lost"):
        cand_filters = []
        if lead.phone_e164:
            cand_filters.append(Lead.phone_e164 == lead.phone_e164)
        if lead.messenger_norm:
            cand_filters.append(Lead.messenger_norm == lead.messenger_norm)
        if cand_filters:
            duplicate_candidates = (
                Lead.query.filter(Lead.id != lead.id, Lead.status.notin_(("won", "lost")), or_(*cand_filters))
                .order_by(Lead.id.desc())
                .all()
            )
    return render_template(
        "manager/lead_detail.html",
        **_common_ctx(),
        now_utc=now,
        lead=lead,
        sla=_lead_sla(lead, now),
        activities=activities,
        timeline=filtered_timeline,
        timeline_counts={
            "all": len(timeline),
            "comms": sum(1 for e in timeline if e["category"] == "comms"),
            "system": sum(1 for e in timeline if e["category"] == "system"),
            "academic": sum(1 for e in timeline if e["category"] == "academic"),
        },
        active_tab=tab,
        tasks=tasks,
        managers=_crm_managers(),
        existing_students=existing_students,
        teachers=teachers,
        duplicate_candidates=duplicate_candidates,
        one_time_notice=one_time_notice,
    )


@bp.route("/leads/<int:lead_id>")
@manager_required
def lead_detail(lead_id: int):
    lead = _get_lead_or_403(lead_id)
    return _render_lead_detail(lead)


@bp.route("/leads/<int:lead_id>/convert", methods=["POST"])
@permission_required("crm.leads.convert")
def lead_convert(lead_id: int):
    """Idempotent Lead -> Student conversion: link existing student by ID or create a new student account."""
    lead = _get_lead_or_403(lead_id)
    if lead.converted_student_id is not None:
        flash(_("Лид уже конвертирован в ученика #%(id)s.", id=lead.converted_student_id), "info")
        return redirect(url_for("manager.lead_detail", lead_id=lead.id))

    mode = (request.form.get("convert_mode") or "create").strip()
    teacher_id = request.form.get("teacher_id", type=int)
    reason = (request.form.get("reason") or "").strip()
    now = utcnow()
    old_status = lead.status
    one_time_notice = None

    if mode == "link":
        existing_id = request.form.get("existing_student_id", type=int)
        student = db.session.get(User, existing_id) if existing_id else None
        if not student or student.role != "student" or student.is_blocked:
            flash(_("Выберите существующий активный аккаунт ученика."), "error")
            return redirect(url_for("manager.lead_detail", lead_id=lead.id))
        created_new = False
    else:
        email = (request.form.get("student_email") or "").strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            flash(_("Укажите корректный email для аккаунта ученика."), "error")
            return redirect(url_for("manager.lead_detail", lead_id=lead.id))
        if User.query.filter_by(email=email).first() is not None:
            flash(_("Аккаунт с этим email уже существует — используйте привязку к существующему ученику."), "error")
            return redirect(url_for("manager.lead_detail", lead_id=lead.id))

        student = User(
            name=lead.full_name,
            email=email,
            role="student",
            is_approved=True,
            must_change_password=True,
            auth_provider="password",
        )
        raw_pw = temporary_password(student)
        raw_exam = (request.form.get("exam") or "").strip().upper()
        exam_code = raw_exam if raw_exam in EXAMS else None
        student.profile = StudentProfile(exam=exam_code, onboarded=bool(exam_code))
        db.session.add(student)
        db.session.flush()
        created_new = True
        one_time_notice = _(
            "Лид конвертирован! Создан ученик %(name)s (%(email)s). Временный пароль: %(password)s — показан один раз.",
            name=student.name,
            email=student.email,
            password=raw_pw,
        )

    # Optionally attach a teacher StudentRecord by permanent internal IDs
    linked_record_id = None
    if teacher_id:
        teacher = db.session.get(User, teacher_id)
        if teacher and teacher.role == "teacher" and teacher.is_approved and not teacher.is_blocked:
            rec = StudentRecord.query.filter_by(teacher_id=teacher.id, student_user_id=student.id).first()
            if rec is None:
                rec = StudentRecord(
                    teacher_id=teacher.id,
                    student_user_id=student.id,
                    previous_student_user_id=student.id,
                    name=student.name,
                    exam=student.profile.exam if student.profile else None,
                    linked_at=now,
                )
                db.session.add(rec)
                db.session.flush()
            linked_record_id = rec.id

    lead.converted_student_id = student.id
    lead.status = "won"
    if lead.first_contact_at is None:
        lead.first_contact_at = now
    lead.last_contact_at = now

    db.session.add(
        LeadActivity(
            lead_id=lead.id,
            actor_id=current_user.id,
            type="status_change",
            body=f"Конвертирован в ученика #{student.id} ({student.name})",
        )
    )
    write_audit_log(
        actor_id=current_user.id,
        action="lead_convert",
        entity_type="lead",
        entity_id=lead.id,
        old_value={"status": old_status, "converted_student_id": None},
        new_value={
            "status": "won",
            "converted_student_id": student.id,
            "created_new_student": created_new,
            "student_record_id": linked_record_id,
        },
        reason=reason,
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash(_("Не удалось завершить конвертацию: конфликт данных (email или запись уже существует)."), "error")
        return redirect(url_for("manager.lead_detail", lead_id=lead.id))

    if one_time_notice:
        resp = make_response(_render_lead_detail(lead, one_time_notice=one_time_notice))
        resp.headers["Cache-Control"] = "no-store, max-age=0"
        return resp
    flash(_("Лид привязан к ученику %(name)s (#%(id)s).", name=student.name, id=student.id), "success")
    return redirect(url_for("manager.lead_detail", lead_id=lead.id))


@bp.route("/leads/<int:lead_id>/edit", methods=["POST"])
@manager_required
def lead_edit(lead_id: int):
    from .phone_utils import normalize_messenger, normalize_phone

    lead = _get_lead_or_403(lead_id)
    full_name = (request.form.get("full_name") or "").strip()
    if len(full_name) < 2:
        flash(_("Имя лида должно быть не короче 2 символов."), "error")
        return redirect(url_for("manager.lead_detail", lead_id=lead.id))
    lead.full_name = full_name
    lead.phone = (request.form.get("phone") or "").strip() or None
    lead.phone_e164 = normalize_phone(lead.phone)
    lead.messenger_handle = (request.form.get("messenger_handle") or "").strip() or None
    lead.messenger_norm = normalize_messenger(lead.messenger_handle)
    source = (request.form.get("source") or lead.source).strip()
    if source in LEAD_SOURCES:
        lead.source = source
    lead.interest = (request.form.get("interest") or "").strip()
    mode_pref = (request.form.get("mode_preference") or "").strip()
    if mode_pref in LEAD_MODE_PREFERENCES:
        lead.mode_preference = mode_pref
    temp = (request.form.get("temperature") or lead.temperature).strip().lower()
    if temp in LEAD_TEMPERATURES:
        lead.temperature = temp
    db.session.commit()
    flash(_("Карточка лида обновлена."), "success")
    return redirect(url_for("manager.lead_detail", lead_id=lead.id))


@bp.route("/leads/<int:lead_id>/status", methods=["POST"])
@manager_required
def lead_status(lead_id: int):
    lead = _get_lead_or_403(lead_id)
    new_status = (request.form.get("status") or "").strip()
    if new_status not in LEAD_STATUSES:
        abort(400)
    old_status = lead.status
    lost_reason = (request.form.get("lost_reason") or "").strip()
    override = request.form.get("supervisor_override") == "1"
    override_reason = (request.form.get("override_reason") or "").strip()
    now = utcnow()

    if new_status == old_status and not (new_status == "lost" and lost_reason != lead.lost_reason):
        return _safe_back("manager.lead_detail", lead_id=lead.id)

    # Enforce pipeline transition rules
    is_override = False
    if old_status == "won" and new_status != "won":
        if lead.converted_student_id is not None:
            if not current_user.has_perm("crm.leads.reassign"):
                flash(_("Только супервайзер может изменить статус уже конвертированного лида."), "error")
                return _safe_back("manager.lead_detail", lead_id=lead.id)
            if not override or not override_reason:
                flash(_("Для смены статуса конвертированного лида отметьте переопределение и укажите причину."), "error")
                return _safe_back("manager.lead_detail", lead_id=lead.id)
            is_override = True
        elif not current_user.has_perm("crm.leads.reassign") or not override or not override_reason:
            flash(_("Нельзя откатить статус «Оплатил / Ученик» без переопределения супервайзера с причиной."), "error")
            return _safe_back("manager.lead_detail", lead_id=lead.id)
        else:
            is_override = True
    elif new_status != old_status and new_status not in ALLOWED_LEAD_TRANSITIONS.get(old_status, frozenset()):
        if old_status == "new" and new_status == "won":
            flash(_("Нельзя перевести лид из «Новый» сразу в «Оплатил / Ученик» без конвертации или прохождения этапов."), "error")
        else:
            flash(
                _("Недопустимый переход статуса: «%(a)s» → «%(b)s».", a=STATUS_LABELS.get(old_status, old_status), b=STATUS_LABELS.get(new_status, new_status)),
                "error",
            )
        return _safe_back("manager.lead_detail", lead_id=lead.id)

    if new_status == "lost" and not lost_reason:
        flash(_("Укажите причину отказа для перевода лида в статус «Отказ»."), "error")
        return _safe_back("manager.lead_detail", lead_id=lead.id)

    lead.status = new_status
    if new_status == "lost":
        lead.lost_reason = lost_reason
    elif old_status == "lost":
        lead.lost_reason = ""
    if new_status in ("contacted", "trial_scheduled", "trial_done", "negotiation", "won"):
        if lead.first_contact_at is None:
            lead.first_contact_at = now
        lead.last_contact_at = now
    body = f"{STATUS_LABELS.get(old_status, old_status)} → {STATUS_LABELS.get(new_status, new_status)}"
    if new_status == "lost" and lead.lost_reason:
        body += f" ({lead.lost_reason})"
    if is_override:
        body += f" [Override: {override_reason}]"
        write_audit_log(
            actor_id=current_user.id,
            action="lead_status_override",
            entity_type="lead",
            entity_id=lead.id,
            old_value={"status": old_status, "converted_student_id": lead.converted_student_id},
            new_value={"status": new_status, "converted_student_id": lead.converted_student_id},
            reason=override_reason,
        )
    db.session.add(
        LeadActivity(lead_id=lead.id, actor_id=current_user.id, type="status_change", body=body)
    )
    db.session.commit()
    flash(_("Статус обновлён: %(s)s.", s=STATUS_LABELS.get(new_status, new_status)), "success")
    return _safe_back("manager.lead_detail", lead_id=lead.id)


@bp.route("/leads/<int:lead_id>/activity", methods=["POST"])
@manager_required
def lead_add_activity(lead_id: int):
    lead = _get_lead_or_403(lead_id)
    act_type = (request.form.get("type") or "note").strip()
    if act_type not in ("call", "message", "note"):
        act_type = "note"
    body = (request.form.get("body") or "").strip()
    if not body:
        flash(_("Напишите текст заметки или итог контакта."), "error")
        return redirect(url_for("manager.lead_detail", lead_id=lead.id))
    now = utcnow()
    db.session.add(LeadActivity(lead_id=lead.id, actor_id=current_user.id, type=act_type, body=body))
    if act_type in ("call", "message"):
        if lead.first_contact_at is None:
            lead.first_contact_at = now
        lead.last_contact_at = now
        if lead.status == "new":
            lead.status = "contacted"
            db.session.add(
                LeadActivity(
                    lead_id=lead.id,
                    actor_id=current_user.id,
                    type="status_change",
                    body=f"{STATUS_LABELS['new']} → {STATUS_LABELS['contacted']}",
                )
            )
    db.session.commit()
    flash(_("Активность добавлена."), "success")
    return redirect(url_for("manager.lead_detail", lead_id=lead.id))


@bp.route("/leads/<int:lead_id>/tasks", methods=["POST"])
@manager_required
def lead_add_task(lead_id: int):
    lead = _get_lead_or_403(lead_id)
    note = (request.form.get("note") or "").strip()
    if not note:
        flash(_("Укажите текст задачи."), "error")
        return redirect(url_for("manager.lead_detail", lead_id=lead.id))
    due_at = _parse_due_at(request.form.get("due_at"))
    assignee_id = lead.assigned_manager_id or current_user.id
    if current_user.has_perm("crm.leads.reassign"):
        req_assignee = request.form.get("assignee_id", type=int)
        if req_assignee:
            target = db.session.get(User, req_assignee)
            if target and target.role in CRM_ROLES and not target.is_blocked:
                assignee_id = target.id
    db.session.add(LeadTask(lead_id=lead.id, assignee_id=assignee_id, due_at=due_at, note=note))
    db.session.commit()
    flash(_("Задача запланирована."), "success")
    return redirect(url_for("manager.lead_detail", lead_id=lead.id))


@bp.route("/tasks/<int:task_id>/toggle", methods=["POST"])
@manager_required
def task_toggle(task_id: int):
    task = db.session.get(LeadTask, task_id) or abort(404)
    lead = _get_lead_or_403(task.lead_id)
    task.done_at = None if task.done_at else utcnow()
    db.session.commit()
    return _safe_back("manager.lead_detail", lead_id=lead.id)


@bp.route("/leads/<int:lead_id>/reassign", methods=["POST"])
@permission_required("crm.leads.reassign")
def lead_reassign(lead_id: int):
    lead = db.session.get(Lead, lead_id) or abort(404)
    target_id = request.form.get("assigned_manager_id", type=int)
    target = db.session.get(User, target_id) if target_id else None
    if not target or target.role not in CRM_ROLES or target.is_blocked:
        flash(_("Выберите активного менеджера."), "error")
        return _safe_back("manager.lead_detail", lead_id=lead.id)

    old_id = lead.assigned_manager_id
    if old_id == target.id:
        flash(_("Лид уже закреплён за этим менеджером."), "info")
        return _safe_back("manager.lead_detail", lead_id=lead.id)

    old_user = db.session.get(User, old_id) if old_id else None
    reason = (request.form.get("reason") or "").strip()
    lead.assigned_manager_id = target.id
    # Keep open tasks aligned with the new owner
    for t in LeadTask.query.filter_by(lead_id=lead.id, done_at=None).all():
        t.assignee_id = target.id

    body = f"{old_user.name if old_user else '—'} → {target.name}"
    if reason:
        body += f" ({reason})"
    db.session.add(LeadActivity(lead_id=lead.id, actor_id=current_user.id, type="reassign", body=body))
    write_audit_log(
        actor_id=current_user.id,
        action="lead_reassign",
        entity_type="lead",
        entity_id=lead.id,
        old_value={"assigned_manager_id": old_id},
        new_value={"assigned_manager_id": target.id},
        reason=reason,
    )
    db.session.commit()
    flash(_("Лид переназначен на %(name)s.", name=target.name), "success")
    return _safe_back("manager.lead_detail", lead_id=lead.id)


@bp.route("/leads/<int:lead_id>/delete", methods=["POST"])
@permission_required("crm.leads.delete")
def lead_delete(lead_id: int):
    lead = db.session.get(Lead, lead_id) or abort(404)
    reason = (request.form.get("reason") or "").strip()
    snapshot = {
        "full_name": lead.full_name,
        "phone": lead.phone,
        "messenger_handle": lead.messenger_handle,
        "source": lead.source,
        "status": lead.status,
        "assigned_manager_id": lead.assigned_manager_id,
        "converted_student_id": lead.converted_student_id,
    }
    write_audit_log(
        actor_id=current_user.id,
        action="lead_delete",
        entity_type="lead",
        entity_id=lead.id,
        old_value=snapshot,
        new_value=None,
        reason=reason,
    )
    db.session.delete(lead)
    db.session.commit()
    flash(_("Лид удалён (запись сохранена в аудите)."), "info")
    return redirect(url_for("manager.leads"))


@bp.route("/leads/<int:lead_id>/merge", methods=["POST"])
@permission_required("crm.leads.reassign")
def lead_merge(lead_id: int):
    """Supervisor-only merge of a duplicate lead into the surviving lead with full history/task transfer."""
    survivor = db.session.get(Lead, lead_id) or abort(404)
    dup_id = request.form.get("duplicate_lead_id", type=int)
    dup = db.session.get(Lead, dup_id) if dup_id else None
    if not dup or dup.id == survivor.id:
        flash(_("Выберите другой лид-дубликат для объединения."), "error")
        return redirect(url_for("manager.lead_detail", lead_id=survivor.id))
    if (
        dup.converted_student_id is not None
        and survivor.converted_student_id is not None
        and dup.converted_student_id != survivor.converted_student_id
    ):
        flash(_("Нельзя объединить лиды, привязанные к разным ученикам."), "error")
        return redirect(url_for("manager.lead_detail", lead_id=survivor.id))

    reason = (request.form.get("reason") or "").strip()
    moved_activities = LeadActivity.query.filter_by(lead_id=dup.id).update({"lead_id": survivor.id})
    moved_tasks = LeadTask.query.filter_by(lead_id=dup.id).update({"lead_id": survivor.id})
    Lead.query.filter_by(previous_lead_id=dup.id).update({"previous_lead_id": survivor.id})

    if not survivor.phone and dup.phone:
        survivor.phone = dup.phone
    if not survivor.phone_e164 and dup.phone_e164:
        survivor.phone_e164 = dup.phone_e164
    if not survivor.messenger_handle and dup.messenger_handle:
        survivor.messenger_handle = dup.messenger_handle
    if not survivor.messenger_norm and dup.messenger_norm:
        survivor.messenger_norm = dup.messenger_norm
    if not survivor.interest and dup.interest:
        survivor.interest = dup.interest
    if not survivor.ai_summary and dup.ai_summary:
        survivor.ai_summary = dup.ai_summary
    if not survivor.converted_student_id and dup.converted_student_id:
        survivor.converted_student_id = dup.converted_student_id

    dup_snapshot = {
        "duplicate_id": dup.id,
        "full_name": dup.full_name,
        "phone": dup.phone,
        "phone_e164": dup.phone_e164,
        "messenger_handle": dup.messenger_handle,
        "status": dup.status,
        "assigned_manager_id": dup.assigned_manager_id,
    }
    db.session.add(
        LeadActivity(
            lead_id=survivor.id,
            actor_id=current_user.id,
            type="reassign",
            body=f"Объединён дубликат #{dup.id} ({dup.full_name})" + (f": {reason}" if reason else ""),
        )
    )
    write_audit_log(
        actor_id=current_user.id,
        action="lead_merge",
        entity_type="lead",
        entity_id=survivor.id,
        old_value=dup_snapshot,
        new_value={
            "surviving_lead_id": survivor.id,
            "moved_activities": moved_activities,
            "moved_tasks": moved_tasks,
        },
        reason=reason,
    )
    db.session.delete(dup)
    db.session.commit()
    flash(_("Дубликат #%(d)s объединён с лидом #%(s)s.", d=dup_id, s=survivor.id), "success")
    return redirect(url_for("manager.lead_detail", lead_id=survivor.id))


@bp.route("/shift", methods=["POST"])
@manager_required
def toggle_shift():
    """Toggle `is_on_shift` for self (or another manager when supervisor/admin)."""
    target_id = request.form.get("user_id", type=int) or current_user.id
    if target_id != current_user.id and not current_user.has_perm("crm.leads.reassign"):
        abort(403)
    target = db.session.get(User, target_id) or abort(404)
    if target.role not in CRM_ROLES:
        abort(400)
    old_val = bool(target.is_on_shift)
    target.is_on_shift = not old_val
    write_audit_log(
        actor_id=current_user.id,
        action="manager_shift_toggle",
        entity_type="user",
        entity_id=target.id,
        old_value={"is_on_shift": old_val},
        new_value={"is_on_shift": target.is_on_shift},
    )
    db.session.commit()
    flash(
        _("%(n)s теперь на смене.", n=target.name) if target.is_on_shift else _("%(n)s ушёл со смены.", n=target.name),
        "info",
    )
    return _safe_back("manager.dashboard")


# --------------------------------------------------------------------------- Pipeline Kanban


@bp.route("/pipeline")
@manager_required
def pipeline():
    """Dual-view board: 7-column Sales Pipeline OR 4-column Active Student Health board."""
    now = utcnow()
    mode = (request.args.get("mode") or "leads").strip().lower()
    if mode not in ("leads", "students"):
        mode = "leads"
    source = (request.args.get("source") or "").strip()
    manager_id = request.args.get("manager", type=int)

    if mode == "students":
        leads_q = _leads_scope(
            Lead.query.filter(Lead.converted_student_id.isnot(None)).options(joinedload(Lead.converted_student))
        )
        converted_leads = leads_q.all()
        converted_by_student = {l.converted_student_id: l for l in converted_leads if l.converted_student_id}

        if current_user.has_perm("crm.leads.view_all"):
            students = (
                User.query.filter_by(role="student", is_blocked=False)
                .order_by(User.name.asc())
                .limit(250)
                .all()
            )
        else:
            students = [l.converted_student for l in converted_leads if l.converted_student and not l.converted_student.is_blocked]

        student_ids = [s.id for s in students]
        enr_by_student: dict[int, list[GroupEnrollment]] = {sid: [] for sid in student_ids}
        att_by_student: dict[int, list[LessonAttendance]] = {sid: [] for sid in student_ids}
        pass_by_student: dict[int, list[StudentPass]] = {sid: [] for sid in student_ids}
        if student_ids:
            enrs = (
                GroupEnrollment.query.options(joinedload(GroupEnrollment.group))
                .filter(GroupEnrollment.student_user_id.in_(student_ids))
                .order_by(GroupEnrollment.enrolled_at.desc())
                .all()
            )
            for e in enrs:
                enr_by_student.setdefault(e.student_user_id, []).append(e)
            since = now - timedelta(days=30)
            atts = (
                LessonAttendance.query.join(Lesson, Lesson.id == LessonAttendance.lesson_id)
                .filter(LessonAttendance.student_user_id.in_(student_ids), Lesson.starts_at >= since)
                .all()
            )
            for a in atts:
                att_by_student.setdefault(a.student_user_id, []).append(a)
            sp_rows = (
                StudentPass.query.options(joinedload(StudentPass.plan))
                .filter(StudentPass.student_user_id.in_(student_ids))
                .order_by(StudentPass.status != "active", StudentPass.id.desc())
                .all()
            )
            for sp in sp_rows:
                pass_by_student.setdefault(sp.student_user_id, []).append(sp)

        health_cols = {
            "unassigned": [],
            "at_risk": [],
            "healthy": [],
            "paused": [],
        }
        health_labels = {
            "unassigned": _("Без группы"),
            "at_risk": _("Риск (2+ пропуска)"),
            "healthy": _("Стабильно"),
            "paused": _("Завершил / Пауза"),
        }
        for s in students:
            enrs = enr_by_student.get(s.id, [])
            active_enrs = [e for e in enrs if e.left_at is None]
            atts = att_by_student.get(s.id, [])
            total_att = len(atts)
            present_cnt = sum(1 for a in atts if a.status in ("present", "late"))
            absent_cnt = sum(1 for a in atts if a.status == "absent")
            att_pct = int(round((present_cnt / total_att) * 100)) if total_att else 100
            passes = pass_by_student.get(s.id, [])
            active_pass = next((p for p in passes if p.status == "active"), None)
            total_debt = sum(p.debt_amount for p in passes if p.status != "cancelled")
            card = {
                "student": s,
                "lead": converted_by_student.get(s.id),
                "active_groups": [e.group.name for e in active_enrs if e.group],
                "total_att": total_att,
                "present_cnt": present_cnt,
                "absent_cnt": absent_cnt,
                "att_pct": att_pct,
                "active_pass": active_pass,
                "total_debt": total_debt,
            }
            if active_enrs:
                bucket = "at_risk" if absent_cnt >= 2 else "healthy"
            elif enrs:
                bucket = "paused"
            else:
                bucket = "unassigned"
            health_cols[bucket].append(card)

        return render_template(
            "manager/pipeline.html",
            **_common_ctx(),
            now_utc=now,
            mode="students",
            health_cols=health_cols,
            health_labels=health_labels,
            managers=_crm_managers(),
            filters={"source": source, "manager": manager_id or ""},
        )

    query = _leads_scope(Lead.query.options(joinedload(Lead.assigned_manager)))
    if source in LEAD_SOURCES:
        query = query.filter(Lead.source == source)
    if current_user.has_perm("crm.leads.view_all") and manager_id:
        query = query.filter(Lead.assigned_manager_id == manager_id)

    all_leads = query.order_by(Lead.created_at.desc()).all()
    columns = {s: [] for s in LEAD_STATUSES}
    for lead in all_leads:
        columns.setdefault(lead.status, []).append(lead)

    next_status_map = {
        "new": "contacted",
        "contacted": "trial_scheduled",
        "trial_scheduled": "trial_done",
        "trial_done": "negotiation",
        "negotiation": "won",
    }

    return render_template(
        "manager/pipeline.html",
        **_common_ctx(),
        now_utc=now,
        mode="leads",
        columns=columns,
        next_status_map=next_status_map,
        managers=_crm_managers(),
        filters={"source": source, "manager": manager_id or ""},
    )


def _authorize_student_crm(student_id: int) -> tuple[User, Lead | None]:
    student = User.query.options(joinedload(User.profile)).filter_by(id=student_id, role="student").first() or abort(404)
    lead = Lead.query.options(joinedload(Lead.assigned_manager)).filter_by(converted_student_id=student.id).first()
    if not current_user.has_perm("crm.leads.view_all"):
        if not lead or lead.assigned_manager_id != current_user.id:
            abort(403)
    return student, lead


@bp.route("/students/<int:student_id>")
@manager_required
def student_detail(student_id: int):
    """Manager CRM Student 360 card: profile, lead origin, enrollments, attendance, passes & payments, unified timeline."""
    student, lead = _authorize_student_crm(student_id)

    tab = (request.args.get("tab") or "all").strip().lower()
    if tab not in ("all", "comms", "system", "academic", "finance"):
        tab = "all"

    enrollments = (
        GroupEnrollment.query.options(joinedload(GroupEnrollment.group), joinedload(GroupEnrollment.course))
        .filter_by(student_user_id=student.id)
        .order_by(GroupEnrollment.left_at.isnot(None), GroupEnrollment.enrolled_at.desc())
        .all()
    )
    atts = LessonAttendance.query.filter_by(student_user_id=student.id).all()
    att_counts = Counter(a.status for a in atts)
    passes = (
        StudentPass.query.options(joinedload(StudentPass.plan))
        .filter_by(student_user_id=student.id)
        .order_by(StudentPass.status != "active", StudentPass.created_at.desc())
        .all()
    )
    payments = (
        PaymentTransaction.query.options(joinedload(PaymentTransaction.recorded_by), joinedload(PaymentTransaction.student_pass))
        .filter_by(student_user_id=student.id)
        .order_by(PaymentTransaction.paid_at.desc(), PaymentTransaction.id.desc())
        .limit(50)
        .all()
    )
    plans = MembershipPlan.query.filter_by(is_active=True).order_by(MembershipPlan.price_amount.asc()).all()
    total_debt = sum(p.debt_amount for p in passes if p.status != "cancelled")

    timeline = _build_unified_timeline(lead=lead, student_id=student.id)
    filtered_timeline = timeline if tab == "all" else [e for e in timeline if e["category"] == tab]

    return render_template(
        "manager/student_detail.html",
        **_common_ctx(),
        student=student,
        lead=lead,
        enrollments=enrollments,
        att_counts=att_counts,
        att_total=len(atts),
        passes=passes,
        payments=payments,
        plans=plans,
        total_debt=total_debt,
        PASS_STATUS_LABELS=PASS_STATUS_LABELS,
        PAYMENT_METHODS=PAYMENT_METHODS,
        METHOD_LABELS=METHOD_LABELS,
        timeline=filtered_timeline,
        timeline_counts={
            "all": len(timeline),
            "academic": sum(1 for e in timeline if e["category"] == "academic"),
            "finance": sum(1 for e in timeline if e["category"] == "finance"),
            "comms": sum(1 for e in timeline if e["category"] == "comms"),
            "system": sum(1 for e in timeline if e["category"] == "system"),
        },
        active_tab=tab,
    )


# --------------------------------------------------------------------------- Finance, Passes & Payroll (Phase B)


def _scoped_student_ids_for_manager() -> list[int] | None:
    """Return None when user views all students; otherwise IDs of students converted from their leads."""
    if current_user.has_perm("crm.leads.view_all"):
        return None
    rows = (
        db.session.query(Lead.converted_student_id)
        .filter(Lead.assigned_manager_id == current_user.id, Lead.converted_student_id.isnot(None))
        .all()
    )
    return [sid for (sid,) in rows if sid]


@bp.route("/finance")
@permission_required("crm.finance.read")
def finance():
    """Membership plans, student passes/debts, immutable payment ledger, and supervisor teacher payroll."""
    now = utcnow()
    since_30 = now - timedelta(days=30)
    scoped_ids = _scoped_student_ids_for_manager()

    tx_q = PaymentTransaction.query.options(
        joinedload(PaymentTransaction.student),
        joinedload(PaymentTransaction.recorded_by),
        joinedload(PaymentTransaction.student_pass).joinedload(StudentPass.plan),
    )
    pass_q = StudentPass.query.options(joinedload(StudentPass.student), joinedload(StudentPass.plan))
    if scoped_ids is not None:
        if scoped_ids:
            tx_q = tx_q.filter(PaymentTransaction.student_user_id.in_(scoped_ids))
            pass_q = pass_q.filter(StudentPass.student_user_id.in_(scoped_ids))
        else:
            tx_q = tx_q.filter(PaymentTransaction.id == -1)
            pass_q = pass_q.filter(StudentPass.id == -1)

    recent_tx = tx_q.order_by(PaymentTransaction.paid_at.desc(), PaymentTransaction.id.desc()).limit(100).all()
    all_passes = pass_q.order_by(StudentPass.created_at.desc()).all()

    rev_30d = sum(
        (-tx.amount if tx.kind == "refund" else tx.amount)
        for tx in recent_tx
        if tx.paid_at and tx.paid_at >= since_30
    )
    active_passes = [p for p in all_passes if p.status == "active"]
    debt_passes = [p for p in all_passes if p.status != "cancelled" and p.debt_amount > 0]
    total_debt = sum(p.debt_amount for p in debt_passes)
    expiring_passes = [
        p
        for p in active_passes
        if (p.lessons_remaining is not None and p.lessons_remaining <= 2)
        or (p.expires_at is not None and p.expires_at <= now + timedelta(days=7))
    ]

    plans = MembershipPlan.query.options(joinedload(MembershipPlan.course)).order_by(MembershipPlan.price_amount.asc()).all()
    courses = AcademicCourse.query.filter_by(is_active=True).order_by(AcademicCourse.name.asc()).all()

    payroll_rows = []
    pay_rates = []
    teachers = []
    if current_user.has_perm("academic.payroll.read"):
        teachers = User.query.filter_by(role="teacher", is_approved=True, is_blocked=False).order_by(User.name.asc()).all()
        pay_rates = (
            TeacherPayRate.query.options(joinedload(TeacherPayRate.teacher), joinedload(TeacherPayRate.course))
            .filter_by(is_active=True)
            .order_by(TeacherPayRate.created_at.desc())
            .all()
        )
        rates_by_teacher: dict[int, list[TeacherPayRate]] = {}
        for r in pay_rates:
            rates_by_teacher.setdefault(r.teacher_id, []).append(r)

        recent_lessons = (
            Lesson.query.options(joinedload(Lesson.group), joinedload(Lesson.attendances))
            .filter(Lesson.starts_at >= since_30, Lesson.starts_at <= now + timedelta(days=1))
            .all()
        )
        lessons_by_teacher: dict[int, list[Lesson]] = {}
        for l in recent_lessons:
            if l.teacher_id:
                lessons_by_teacher.setdefault(l.teacher_id, []).append(l)

        for tch in teachers:
            t_rates = rates_by_teacher.get(tch.id, [])
            t_lessons = lessons_by_teacher.get(tch.id, [])
            accrued = 0
            for l in t_lessons:
                cid = l.group.course_id if l.group else None
                rate = next((r for r in t_rates if r.course_id == cid), None) or next((r for r in t_rates if r.course_id is None), None)
                if rate:
                    if rate.rate_type == "per_lesson":
                        accrued += rate.rate_amount
                    elif rate.rate_type == "per_student":
                        accrued += rate.rate_amount * sum(1 for a in l.attendances if a.status in ("present", "late"))
            fixed = next((r for r in t_rates if r.rate_type == "fixed_month"), None)
            if fixed and not accrued:
                accrued = fixed.rate_amount
            payroll_rows.append({
                "teacher": tch,
                "lesson_count": len(t_lessons),
                "accrued": accrued,
                "rates": t_rates,
            })

    return render_template(
        "manager/finance.html",
        **_common_ctx(),
        now_utc=now,
        rev_30d=rev_30d,
        total_debt=total_debt,
        active_passes_count=len(active_passes),
        expiring_passes=expiring_passes,
        debt_passes=debt_passes,
        recent_tx=recent_tx,
        plans=plans,
        courses=courses,
        teachers=teachers,
        pay_rates=pay_rates,
        payroll_rows=payroll_rows,
        PASS_STATUS_LABELS=PASS_STATUS_LABELS,
        PAYMENT_METHODS=PAYMENT_METHODS,
        METHOD_LABELS=METHOD_LABELS,
        PAY_RATE_TYPES=PAY_RATE_TYPES,
        RATE_TYPE_LABELS=RATE_TYPE_LABELS,
    )


@bp.post("/plans/new")
@permission_required("crm.finance.manage")
def plan_create():
    name = (request.form.get("name") or "").strip()
    course_id = request.form.get("course_id", type=int) or None
    total_lessons = request.form.get("total_lessons", type=int)
    duration_days = max(1, min(365, request.form.get("duration_days", 30, type=int) or 30))
    price_amount = max(0, request.form.get("price_amount", 0, type=int) or 0)
    if len(name) < 2:
        flash(_("Укажите название тарифа."), "error")
        return redirect(url_for("manager.finance"))
    if course_id and not db.session.get(AcademicCourse, course_id):
        course_id = None
    if total_lessons is not None and total_lessons <= 0:
        total_lessons = None
    plan = MembershipPlan(
        name=name,
        course_id=course_id,
        total_lessons=total_lessons,
        duration_days=duration_days,
        price_amount=price_amount,
    )
    db.session.add(plan)
    db.session.commit()
    flash(_("Тариф «%(n)s» добавлен.", n=plan.name), "success")
    return redirect(url_for("manager.finance"))


@bp.post("/students/<int:student_id>/passes/new")
@permission_required("crm.finance.record")
def student_pass_create(student_id: int):
    student, _lead = _authorize_student_crm(student_id)
    plan_id = request.form.get("plan_id", type=int)
    plan = db.session.get(MembershipPlan, plan_id) if plan_id else None
    if not plan:
        flash(_("Выберите тариф абонемента."), "error")
        return redirect(url_for("manager.student_detail", student_id=student.id))

    enrollment_id = request.form.get("enrollment_id", type=int) or None
    if enrollment_id:
        enr = db.session.get(GroupEnrollment, enrollment_id)
        if not enr or enr.student_user_id != student.id:
            enrollment_id = None

    raw_price = request.form.get("agreed_price", type=int)
    agreed_price = max(0, raw_price if raw_price is not None else plan.price_amount)
    initial_pay = max(0, request.form.get("initial_payment", 0, type=int) or 0)
    method = (request.form.get("method") or "cash").strip().lower()
    if method not in PAYMENT_METHODS:
        method = "cash"
    note = (request.form.get("note") or "").strip()

    now = utcnow()
    sp = StudentPass(
        student_user_id=student.id,
        plan_id=plan.id,
        enrollment_id=enrollment_id,
        status="active",
        lessons_total=plan.total_lessons,
        lessons_remaining=plan.total_lessons,
        starts_at=now,
        expires_at=now + timedelta(days=max(1, plan.duration_days)),
        agreed_price=agreed_price,
        paid_amount=min(agreed_price, initial_pay) if agreed_price else initial_pay,
        note=note,
        created_by_id=current_user.id,
    )
    db.session.add(sp)
    db.session.flush()
    if initial_pay > 0:
        db.session.add(
            PaymentTransaction(
                student_user_id=student.id,
                pass_id=sp.id,
                amount=initial_pay,
                method=method,
                kind="payment",
                note=note or f"Оплата при выдаче: {plan.name}",
                recorded_by_id=current_user.id,
                paid_at=now,
            )
        )
    write_audit_log(
        actor_id=current_user.id,
        action="pass_issue",
        entity_type="student_pass",
        entity_id=sp.id,
        new_value={"student_id": student.id, "plan": plan.name, "agreed_price": agreed_price, "initial_pay": initial_pay},
    )
    db.session.commit()
    flash(_("Абонемент «%(p)s» выдан ученику.", p=plan.name), "success")
    return redirect(url_for("manager.student_detail", student_id=student.id))


@bp.post("/students/<int:student_id>/payments/new")
@permission_required("crm.finance.record")
def student_payment_create(student_id: int):
    student, _lead = _authorize_student_crm(student_id)
    amount = request.form.get("amount", type=int) or 0
    kind = (request.form.get("kind") or "payment").strip().lower()
    method = (request.form.get("method") or "cash").strip().lower()
    pass_id = request.form.get("pass_id", type=int) or None
    note = (request.form.get("note") or "").strip()

    if kind not in PAYMENT_KINDS or method not in PAYMENT_METHODS or amount <= 0:
        flash(_("Укажите корректную сумму (> 0), способ и тип операции."), "error")
        return redirect(url_for("manager.student_detail", student_id=student.id))
    if kind == "refund" and not current_user.has_perm("crm.finance.manage"):
        abort(403)

    sp = db.session.get(StudentPass, pass_id) if pass_id else None
    if pass_id and (not sp or sp.student_user_id != student.id):
        flash(_("Указанный абонемент не принадлежит ученику."), "error")
        return redirect(url_for("manager.student_detail", student_id=student.id))

    if sp is not None:
        if kind == "refund" and amount > sp.paid_amount:
            flash(_("Сумма возврата превышает оплаченную сумму по абонементу."), "error")
            return redirect(url_for("manager.student_detail", student_id=student.id))
        sp.paid_amount = sp.paid_amount - amount if kind == "refund" else sp.paid_amount + amount

    tx = PaymentTransaction(
        student_user_id=student.id,
        pass_id=sp.id if sp else None,
        amount=amount,
        method=method,
        kind=kind,
        note=note,
        recorded_by_id=current_user.id,
        paid_at=utcnow(),
    )
    db.session.add(tx)
    db.session.flush()
    write_audit_log(
        actor_id=current_user.id,
        action="payment_refund" if kind == "refund" else "payment_record",
        entity_type="payment_transaction",
        entity_id=tx.id,
        new_value={"student_id": student.id, "pass_id": tx.pass_id, "amount": amount, "method": method, "kind": kind},
        reason=note,
    )
    db.session.commit()
    flash(_("Операция на %(a)s KGS сохранена.", a=amount), "success")
    return redirect(url_for("manager.student_detail", student_id=student.id))


@bp.post("/passes/<int:pass_id>/status")
@permission_required("crm.finance.manage")
def pass_update_status(pass_id: int):
    sp = db.session.get(StudentPass, pass_id) or abort(404)
    new_status = (request.form.get("status") or "").strip().lower()
    if new_status not in PASS_STATUSES:
        abort(400)
    old_status = sp.status
    if old_status != new_status:
        sp.status = new_status
        write_audit_log(
            actor_id=current_user.id,
            action="pass_status_change",
            entity_type="student_pass",
            entity_id=sp.id,
            old_value={"status": old_status},
            new_value={"status": new_status},
            reason=(request.form.get("reason") or "").strip(),
        )
        db.session.commit()
        flash(_("Статус абонемента обновлён."), "success")
    return redirect(url_for("manager.student_detail", student_id=sp.student_user_id))


@bp.post("/payroll/rates/new")
@permission_required("academic.payroll.manage")
def payroll_rate_create():
    teacher_id = request.form.get("teacher_id", type=int)
    course_id = request.form.get("course_id", type=int) or None
    rate_type = (request.form.get("rate_type") or "per_lesson").strip().lower()
    rate_amount = max(0, request.form.get("rate_amount", 0, type=int) or 0)
    teacher = db.session.get(User, teacher_id) if teacher_id else None
    if not teacher or teacher.role not in ("teacher", "admin") or rate_type not in PAY_RATE_TYPES or rate_amount <= 0:
        flash(_("Укажите учителя, тип ставки и сумму (> 0)."), "error")
        return redirect(url_for("manager.finance"))
    if course_id and not db.session.get(AcademicCourse, course_id):
        course_id = None
    # Deactivate existing matching rule for the same (teacher_id, course_id) so one active rate governs
    TeacherPayRate.query.filter_by(teacher_id=teacher.id, course_id=course_id, is_active=True).update({"is_active": False})
    r = TeacherPayRate(
        teacher_id=teacher.id,
        course_id=course_id,
        rate_type=rate_type,
        rate_amount=rate_amount,
        is_active=True,
    )
    db.session.add(r)
    db.session.flush()
    write_audit_log(
        actor_id=current_user.id,
        action="payroll_rate_set",
        entity_type="teacher_pay_rate",
        entity_id=r.id,
        new_value={"teacher_id": teacher.id, "course_id": course_id, "rate_type": rate_type, "rate_amount": rate_amount},
    )
    db.session.commit()
    flash(_("Ставка для %(n)s сохранена.", n=teacher.name), "success")
    return redirect(url_for("manager.finance"))


# --------------------------------------------------------------------------- Supervisor / Admin Audit Log


@bp.route("/audit")
@supervisor_required
def audit():
    """Audit log viewer for Supervisors & Admins."""
    action = (request.args.get("action") or "").strip()
    entity_type = (request.args.get("entity_type") or "").strip()
    actor_id = request.args.get("actor_id", type=int)

    query = AuditLog.query.options(joinedload(AuditLog.actor))
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if actor_id:
        query = query.filter(AuditLog.actor_id == actor_id)

    logs = query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(200).all()
    actions = [a for (a,) in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all() if a]
    entity_types = [e for (e,) in db.session.query(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type).all() if e]
    actors = User.query.filter(User.role.in_(("sales_manager", "supervisor", "admin", "teacher"))).order_by(User.name).all()

    return render_template(
        "manager/audit.html",
        logs=logs,
        actions=actions,
        entity_types=entity_types,
        actors=actors,
        filters={"action": action, "entity_type": entity_type, "actor_id": actor_id or ""},
    )


# --------------------------------------------------------------------------- Manager Account Settings


@bp.route("/account", methods=["GET", "POST"])
@manager_required
def account():
    """Profile, interface preferences, password change & role summary for CRM staff."""
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
                        action="manager_profile_update",
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
                db.session.commit()
                login_user(user_obj)
                flash(_("Пароль изменён."), "success")
        return redirect(url_for("manager.account"))

    role_labels = {
        "admin": _("Администратор"),
        "supervisor": _("Супервайзер CRM"),
        "sales_manager": _("Менеджер продаж"),
    }
    if current_user.is_crm_supervisor:
        role_perms = [
            _("Просмотр и редактирование всех лидов команды"),
            _("Переназначение, объединение дубликатов и удаление лидов"),
            _("Управление тарифами, абонементами и ставками учителей"),
            _("Редактирование расписания, групп и ретроспективной посещаемости"),
            _("Доступ к журналу аудита действий CRM"),
        ]
    else:
        role_perms = [
            _("Создание лидов и работа со своими закреплёнными лидами"),
            _("Смена этапов воронки, звонки, переписка и задачи SLA"),
            _("Конвертация лидов в учеников и выдача абонементов"),
            _("Приём оплат по абонементам и просмотр расписания групп"),
        ]

    return render_template(
        "manager/account.html",
        min_pw_len=min_len,
        role_label=role_labels.get(current_user.role, current_user.role),
        role_perms=role_perms,
        sla_threshold=_sla_threshold_minutes(),
    )

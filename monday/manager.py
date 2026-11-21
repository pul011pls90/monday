"""Manager CRM & Supervisor workspace (Stage 3 UI: dashboard, leads, lead card, pipeline, audit)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta

from flask import Blueprint, abort, current_app, flash, make_response, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_user
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from .access import CRM_ROLES, manager_required, permission_required, supervisor_required
from .audit import write_audit_log
from .auth import _safe_next
from .extensions import db
from .models import (
    AuditLog,
    LEAD_ACTIVITY_TYPES,
    LEAD_MODE_PREFERENCES,
    LEAD_SOURCES,
    LEAD_STATUSES,
    Lead,
    LeadActivity,
    LeadTask,
    StudentProfile,
    StudentRecord,
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
    "reassign": "Переназначение",
}

MODE_PREF_LABELS = {
    "": "Не указано",
    "online": "Онлайн",
    "offline": "Офлайн",
    "any": "Любой",
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
        "STATUS_LABELS": STATUS_LABELS,
        "SOURCE_LABELS": SOURCE_LABELS,
        "ACTIVITY_LABELS": ACTIVITY_LABELS,
        "MODE_PREF_LABELS": MODE_PREF_LABELS,
        "sla_threshold": _sla_threshold_minutes(),
        "lead_sla": _lead_sla,
    }


# --------------------------------------------------------------------------- Dashboard


@bp.route("", strict_slashes=False)
@manager_required
def dashboard():
    """Manager / Supervisor CRM dashboard: KPIs, SLA alerts, tasks today, funnel counts."""
    now = utcnow()
    day_start = local_midnight_utc()
    day_end = day_start + timedelta(days=1)

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

    task_q = LeadTask.query.options(joinedload(LeadTask.lead), joinedload(LeadTask.assignee)).filter(
        LeadTask.done_at.is_(None)
    )
    if current_user.has_perm("crm.leads.view_all") and request.args.get("scope") == "all":
        pass
    else:
        task_q = task_q.filter(LeadTask.assignee_id == current_user.id)
    open_tasks = task_q.order_by(LeadTask.due_at.asc()).all()

    overdue_tasks = [t for t in open_tasks if t.due_at and t.due_at < now]
    today_tasks = [t for t in open_tasks if t.due_at and now <= t.due_at < day_end]

    return render_template(
        "manager/dashboard.html",
        **_common_ctx(),
        now_utc=now,
        total_leads=len(leads),
        new_count=len(new_leads),
        sla_overdue_count=len(sla_overdue_leads),
        overdue_tasks=overdue_tasks,
        today_tasks=today_tasks,
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
        like = f"%{q}%"
        query = query.filter(
            or_(
                Lead.full_name.ilike(like),
                Lead.phone.ilike(like),
                Lead.messenger_handle.ilike(like),
                Lead.interest.ilike(like),
            )
        )

    rows = query.order_by(Lead.created_at.desc()).all()
    if sla_filter == "overdue":
        rows = [l for l in rows if _lead_sla(l, now)["overdue"]]

    return render_template(
        "manager/leads.html",
        **_common_ctx(),
        now_utc=now,
        leads=rows,
        managers=_crm_managers(),
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

    assigned_id = current_user.id
    if current_user.has_perm("crm.leads.reassign"):
        req_mgr = request.form.get("assigned_manager_id", type=int)
        if req_mgr:
            target = db.session.get(User, req_mgr)
            if target and target.role in CRM_ROLES and not target.is_blocked:
                assigned_id = target.id

    lead = Lead(
        full_name=full_name,
        phone=phone,
        messenger_handle=messenger_handle,
        source=source,
        interest=interest,
        mode_preference=mode_pref,
        status="new",
        assigned_manager_id=assigned_id,
    )
    db.session.add(lead)
    db.session.flush()
    note = (request.form.get("note") or "").strip()
    if note:
        db.session.add(LeadActivity(lead_id=lead.id, actor_id=current_user.id, type="note", body=note))
    db.session.commit()
    flash(_("Лид «%(name)s» добавлен.", name=lead.full_name), "success")
    return redirect(url_for("manager.lead_detail", lead_id=lead.id))


# --------------------------------------------------------------------------- Lead Card & Actions


def _render_lead_detail(lead: Lead, *, one_time_notice: str | None = None):
    now = utcnow()
    activities = (
        LeadActivity.query.options(joinedload(LeadActivity.actor))
        .filter_by(lead_id=lead.id)
        .order_by(LeadActivity.created_at.desc(), LeadActivity.id.desc())
        .all()
    )
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
    return render_template(
        "manager/lead_detail.html",
        **_common_ctx(),
        now_utc=now,
        lead=lead,
        sla=_lead_sla(lead, now),
        activities=activities,
        tasks=tasks,
        managers=_crm_managers(),
        existing_students=existing_students,
        teachers=teachers,
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
            auth_provider="password",
        )
        raw_pw = temporary_password(student)
        exam_code = (request.form.get("exam") or "").strip().upper() or None
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
    db.session.commit()

    if one_time_notice:
        resp = make_response(_render_lead_detail(lead, one_time_notice=one_time_notice))
        resp.headers["Cache-Control"] = "no-store, max-age=0"
        return resp
    flash(_("Лид привязан к ученику %(name)s (#%(id)s).", name=student.name, id=student.id), "success")
    return redirect(url_for("manager.lead_detail", lead_id=lead.id))


@bp.route("/leads/<int:lead_id>/edit", methods=["POST"])
@manager_required
def lead_edit(lead_id: int):
    lead = _get_lead_or_403(lead_id)
    full_name = (request.form.get("full_name") or "").strip()
    if len(full_name) < 2:
        flash(_("Имя лида должно быть не короче 2 символов."), "error")
        return redirect(url_for("manager.lead_detail", lead_id=lead.id))
    lead.full_name = full_name
    lead.phone = (request.form.get("phone") or "").strip() or None
    lead.messenger_handle = (request.form.get("messenger_handle") or "").strip() or None
    source = (request.form.get("source") or lead.source).strip()
    if source in LEAD_SOURCES:
        lead.source = source
    lead.interest = (request.form.get("interest") or "").strip()
    mode_pref = (request.form.get("mode_preference") or "").strip()
    if mode_pref in LEAD_MODE_PREFERENCES:
        lead.mode_preference = mode_pref
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
    now = utcnow()

    if new_status != old_status or (new_status == "lost" and lost_reason != lead.lost_reason):
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


# --------------------------------------------------------------------------- Pipeline Kanban


@bp.route("/pipeline")
@manager_required
def pipeline():
    """7-column status Kanban board with SLA badges and 1-click stage transitions."""
    now = utcnow()
    source = (request.args.get("source") or "").strip()
    manager_id = request.args.get("manager", type=int)

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
        columns=columns,
        next_status_map=next_status_map,
        managers=_crm_managers(),
        filters={"source": source, "manager": manager_id or ""},
    )


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
    """Password change & preferences for sales managers and supervisors."""
    if request.method == "POST":
        action = request.form.get("action")
        if action == "password":
            cur_pw = request.form.get("current", "")
            new_pw = request.form.get("new", "")
            if not current_user.check_password(cur_pw):
                flash(_("Текущий пароль неверный."), "error")
            elif len(new_pw) < 8:
                flash(_("Новый пароль должен быть не короче 8 символов."), "error")
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                login_user(current_user._get_current_object())
                flash(_("Пароль изменён."), "success")
        return redirect(url_for("manager.account"))
    return render_template("manager/account.html")

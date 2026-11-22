"""Service layer for manager-created student records, connection codes, and teacher assignment history."""
from __future__ import annotations

from datetime import datetime

from flask import current_app
from flask_babel import gettext as _
from sqlalchemy import exists, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from .access import has_permission
from .audit import write_audit_log
from .constants import EXAMS
from .extensions import db
from .models import AcademicCourse, Assignment, Lead, StudentRecord, TeacherAssignment, User, utcnow
from .phone_utils import normalize_phone


class StudentLinkError(Exception):
    """Base error raised by student-link service operations."""

    status_code = 400


class StudentLinkPermissionError(StudentLinkError):
    """Raised when an actor lacks RBAC permission for the requested action."""

    status_code = 403


class StudentLinkNotFoundError(StudentLinkError):
    """Raised when a target record, teacher, course, or lead does not exist."""

    status_code = 404


class StudentLinkValidationError(StudentLinkError):
    """Raised when input arguments fail domain validation."""

    status_code = 400


class StudentLinkConflictError(StudentLinkError):
    """Raised on conflicting assignment or code state."""

    status_code = 409


def code_last4(code: str | None) -> str | None:
    """Return only the last 4 characters of a connection code for safe audit logging."""
    cleaned = (code or "").strip()
    return cleaned[-4:] if len(cleaned) >= 4 else None


def normalize_invite_code(code: str | None) -> str:
    """Normalize student invite codes to canonical MND-XXXXXXXXXXXX uppercase form."""
    raw = (code or "").strip().upper()
    if not raw:
        return ""
    if not raw.startswith("MND-"):
        raw = "MND-" + raw
    return raw


def masked_student_name(full_name: str | None) -> str:
    """Return only first name + surname initial ('Айдана А.') for claim confirmation."""
    parts = [p for p in (full_name or "").strip().split() if p]
    if not parts:
        return _("Ученик")
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0].upper()}."


def _is_manager_actor(actor: User | None) -> bool:
    return bool(
        has_permission(actor, "crm.leads.convert")
        or (actor and not getattr(actor, "is_blocked", False) and getattr(actor, "is_admin", False))
    )


def _can_manage_record_code(actor: User | None, record: StudentRecord) -> bool:
    if _is_manager_actor(actor):
        return True
    if has_permission(actor, "teacher.workspace") and actor and can_teacher_access(actor, record):
        return True
    return False


def _validate_active_teacher(teacher_id: int | None) -> User:
    if not teacher_id:
        raise StudentLinkValidationError(_("Выберите активного преподавателя."))
    teacher = db.session.get(User, int(teacher_id))
    if not teacher or teacher.role != "teacher" or not teacher.is_approved or teacher.is_blocked:
        raise StudentLinkValidationError(_("Преподаватель не найден или неактивен."))
    return teacher


def _validate_course(course_id: int | None) -> AcademicCourse | None:
    if course_id is None:
        return None
    course = db.session.get(AcademicCourse, int(course_id))
    if not course:
        raise StudentLinkNotFoundError(_("Предмет (курс) не найден."))
    return course


def _validate_email(email_optional: str | None) -> str | None:
    email = (email_optional or "").strip().lower()
    if not email:
        return None
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 255:
        raise StudentLinkValidationError(_("Укажите корректный email."))
    return email


def _validate_phone(phone: str | None) -> str | None:
    raw = (phone or "").strip()
    if not raw:
        return None
    norm = normalize_phone(raw)
    if norm:
        return norm
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) < 6 or len(raw) > 40:
        raise StudentLinkValidationError(_("Укажите корректный номер телефона."))
    return raw


def _open_assignments_query(record_id: int, course_id: int | None = None, *, filter_course: bool = False):
    q = TeacherAssignment.query.filter(
        TeacherAssignment.student_record_id == record_id,
        TeacherAssignment.ended_at.is_(None),
    )
    if filter_course:
        if course_id is None:
            q = q.filter(TeacherAssignment.course_id.is_(None))
        else:
            q = q.filter(TeacherAssignment.course_id == course_id)
    return q


def sync_legacy_teacher_id(record: StudentRecord) -> int | None:
    """Keep legacy StudentRecord.teacher_id synced with open TeacherAssignment rows."""
    open_rows = (
        _open_assignments_query(record.id)
        .order_by(TeacherAssignment.started_at.desc(), TeacherAssignment.id.desc())
        .all()
    )
    if not open_rows:
        has_any = TeacherAssignment.query.filter_by(student_record_id=record.id).first() is not None
        if not has_any and record.teacher_id is not None:
            return record.teacher_id
        record.teacher_id = None
        return None
    preferred = next((row for row in open_rows if row.course_id == record.course_id), None) or open_rows[0]
    record.teacher_id = preferred.teacher_user_id
    return record.teacher_id


def _lock_record(record_id: int) -> StudentRecord:
    """Acquire a row lock on StudentRecord (FOR UPDATE on Postgres) to serialize mutations."""
    q = StudentRecord.query.filter_by(id=int(record_id))
    bind = db.session.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        q = q.with_for_update()
    record = q.populate_existing().first()
    if not record:
        raise StudentLinkNotFoundError(_("Карточка ученика не найдена."))
    return record


def create_student_with_code(
    actor: User | None,
    name: str,
    phone: str | None,
    email_optional: str | None = None,
    teacher_id: int | None = None,
    course_id: int | None = None,
    lead_id: int | None = None,
    *,
    ttl_days: int | None = None,
    commit: bool = True,
) -> tuple[StudentRecord, str]:
    """Create a StudentRecord, open its initial TeacherAssignment, and generate a one-time invite code."""
    if not _is_manager_actor(actor):
        raise StudentLinkPermissionError(_("Недостаточно прав для создания записи ученика."))

    clean_name = (name or "").strip()
    if len(clean_name) < 2 or len(clean_name) > 120:
        raise StudentLinkValidationError(_("Имя ученика должно быть от 2 до 120 символов."))

    clean_phone = _validate_phone(phone)
    clean_email = _validate_email(email_optional)
    teacher = _validate_active_teacher(teacher_id)
    course = _validate_course(course_id)

    lead = None
    if lead_id is not None:
        lead = db.session.get(Lead, int(lead_id))
        if not lead:
            raise StudentLinkNotFoundError(_("Лид не найден."))

    now = utcnow()
    exam_code = course.exam if course and course.exam in EXAMS else None

    try:
        record = StudentRecord(
            teacher_id=teacher.id,
            created_by_user_id=actor.id,
            source_lead_id=lead.id if lead else None,
            course_id=course.id if course else None,
            name=clean_name,
            phone=clean_phone,
            email=clean_email,
            exam=exam_code,
            created_at=now,
        )
        plain_code = record.rotate_invite_code(ttl_days=ttl_days)
        db.session.add(record)
        db.session.flush()

        assignment = TeacherAssignment(
            student_record_id=record.id,
            teacher_user_id=teacher.id,
            course_id=course.id if course else None,
            started_at=now,
            assigned_by_id=actor.id,
        )
        db.session.add(assignment)
        db.session.flush()
        sync_legacy_teacher_id(record)

        write_audit_log(
            actor_id=actor.id,
            action="student_code_created",
            entity_type="student_record",
            entity_id=record.id,
            new_value={
                "code_last4": code_last4(plain_code),
                "expires_at": record.invite_expires_at.isoformat() if record.invite_expires_at else None,
                "source_lead_id": record.source_lead_id,
                "course_id": record.course_id,
            },
        )
        write_audit_log(
            actor_id=actor.id,
            action="teacher_assigned",
            entity_type="student_record",
            entity_id=record.id,
            new_value={
                "assignment_id": assignment.id,
                "teacher_id": teacher.id,
                "course_id": assignment.course_id,
            },
        )
        if commit:
            db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise StudentLinkConflictError(_("Не удалось создать запись ученика из-за конфликта данных.")) from exc

    return record, plain_code


def regenerate_code(
    actor: User | None,
    record_id: int,
    *,
    ttl_days: int | None = None,
) -> tuple[StudentRecord, str]:
    """Revoke any previous pending code and generate a fresh one-time invite code."""
    try:
        record = _lock_record(record_id)
        if not _can_manage_record_code(actor, record):
            raise StudentLinkPermissionError(_("Недостаточно прав для перевыпуска кода."))
        if record.student_user_id is not None or record.claimed_at is not None:
            raise StudentLinkConflictError(_("Ученик уже привязан к аккаунту — новый код не требуется."))

        old_last4 = code_last4(record.invite_code)
        new_code = record.rotate_invite_code(ttl_days=ttl_days)
        db.session.flush()

        write_audit_log(
            actor_id=actor.id if actor else None,
            action="student_code_regenerated",
            entity_type="student_record",
            entity_id=record.id,
            old_value={"code_last4": old_last4},
            new_value={
                "code_last4": code_last4(new_code),
                "expires_at": record.invite_expires_at.isoformat() if record.invite_expires_at else None,
            },
        )
        db.session.commit()
    except StudentLinkError:
        db.session.rollback()
        raise
    except IntegrityError as exc:
        db.session.rollback()
        raise StudentLinkConflictError(_("Конфликт при обновлении кода.")) from exc

    return record, new_code


def revoke_code(actor: User | None, record_id: int, reason: str = "") -> StudentRecord:
    """Revoke the current invite code for an unclaimed StudentRecord."""
    try:
        record = _lock_record(record_id)
        if not _can_manage_record_code(actor, record):
            raise StudentLinkPermissionError(_("Недостаточно прав для отзыва кода."))
        if record.student_user_id is not None:
            raise StudentLinkConflictError(_("Ученик уже привязан — код больше не активен."))

        old_last4 = code_last4(record.invite_code)
        record.revoke_invite_code()
        db.session.flush()

        write_audit_log(
            actor_id=actor.id if actor else None,
            action="student_code_revoked",
            entity_type="student_record",
            entity_id=record.id,
            old_value={"code_last4": old_last4},
            new_value={"revoked_at": record.invite_revoked_at.isoformat() if record.invite_revoked_at else None},
            reason=reason,
        )
        db.session.commit()
    except StudentLinkError:
        db.session.rollback()
        raise

    return record


def assign_teacher(
    actor: User | None,
    record_id: int,
    teacher_id: int,
    course_id: int | None = None,
    reason: str = "",
) -> TeacherAssignment:
    """Assign an initial teacher for (record_id, course_id) when no open assignment exists."""
    if not _is_manager_actor(actor):
        raise StudentLinkPermissionError(_("Недостаточно прав для назначения преподавателя."))

    teacher = _validate_active_teacher(teacher_id)
    course = _validate_course(course_id)
    cid = course.id if course else None

    try:
        record = _lock_record(record_id)
        existing = _open_assignments_query(record.id, cid, filter_course=True).first()
        if existing:
            if existing.teacher_user_id == teacher.id:
                sync_legacy_teacher_id(record)
                db.session.commit()
                return existing
            raise StudentLinkConflictError(
                _("По этому предмету уже назначен другой преподаватель. Используйте смену преподавателя.")
            )

        now = utcnow()
        assignment = TeacherAssignment(
            student_record_id=record.id,
            teacher_user_id=teacher.id,
            course_id=cid,
            started_at=now,
            assigned_by_id=actor.id,
            change_reason=(reason or "").strip() or None,
        )
        db.session.add(assignment)
        db.session.flush()
        sync_legacy_teacher_id(record)

        write_audit_log(
            actor_id=actor.id,
            action="teacher_assigned",
            entity_type="student_record",
            entity_id=record.id,
            new_value={
                "assignment_id": assignment.id,
                "teacher_id": teacher.id,
                "course_id": cid,
            },
            reason=reason,
        )
        db.session.commit()
    except StudentLinkError:
        db.session.rollback()
        raise
    except IntegrityError as exc:
        db.session.rollback()
        raise StudentLinkConflictError(_("Открытое назначение для этого предмета уже существует.")) from exc

    return assignment


def change_teacher(
    actor: User | None,
    record_id: int,
    new_teacher_id: int,
    course_id: int | None = None,
    reason: str = "",
) -> TeacherAssignment:
    """Atomically close the current open assignment for (record_id, course_id) and open a new one."""
    if not _is_manager_actor(actor):
        raise StudentLinkPermissionError(_("Недостаточно прав для смены преподавателя."))

    new_teacher = _validate_active_teacher(new_teacher_id)
    course = _validate_course(course_id)
    cid = course.id if course else None
    clean_reason = (reason or "").strip()

    try:
        record = _lock_record(record_id)
        now = utcnow()
        open_rows = (
            _open_assignments_query(record.id, cid, filter_course=True)
            .order_by(TeacherAssignment.started_at.desc(), TeacherAssignment.id.desc())
            .all()
        )
        if open_rows and open_rows[0].teacher_user_id == new_teacher.id:
            raise StudentLinkValidationError(_("Этот преподаватель уже назначен по данному предмету."))

        old_teacher_id = open_rows[0].teacher_user_id if open_rows else record.teacher_id
        closed_ids = []
        for row in open_rows:
            row.ended_at = now
            row.ended_by_id = actor.id
            if clean_reason and not row.change_reason:
                row.change_reason = clean_reason
            closed_ids.append(row.id)
        db.session.flush()

        new_assignment = TeacherAssignment(
            student_record_id=record.id,
            teacher_user_id=new_teacher.id,
            course_id=cid,
            started_at=now,
            assigned_by_id=actor.id,
            change_reason=clean_reason or None,
        )
        db.session.add(new_assignment)
        db.session.flush()
        sync_legacy_teacher_id(record)

        write_audit_log(
            actor_id=actor.id,
            action="teacher_changed",
            entity_type="student_record",
            entity_id=record.id,
            old_value={
                "teacher_id": old_teacher_id,
                "course_id": cid,
                "closed_assignment_ids": closed_ids,
            },
            new_value={
                "teacher_id": new_teacher.id,
                "course_id": cid,
                "assignment_id": new_assignment.id,
            },
            reason=clean_reason,
        )
        db.session.commit()
    except StudentLinkError:
        db.session.rollback()
        raise
    except IntegrityError as exc:
        db.session.rollback()
        raise StudentLinkConflictError(_("Конфликт при смене преподавателя — повторите запрос.")) from exc

    return new_assignment


def _validate_claim_candidate(user: User | None, record: StudentRecord | None) -> tuple[bool, str]:
    """Evaluate claim eligibility rules returning specific localized errors for authenticated students."""
    if not record:
        return False, _("Такого кода нет — обратитесь к менеджеру или преподавателю.")
    if record.invite_revoked_at is not None:
        return False, _("Такого кода нет: код отозван — обратитесь к менеджеру.")
    if record.invite_is_expired:
        return False, _("Такого кода нет: код истёк — обратитесь к менеджеру.")
    if record.student_user_id and record.student_user_id != user.id:
        return False, _("Этот код уже использован другим учеником — обратитесь к менеджеру.")
    if record.claimed_at is not None or record.student_user_id == user.id:
        return False, _("Этот код уже использован — обратитесь к менеджеру.")
    if (
        record.previous_student_user_id
        and record.previous_student_user_id != user.id
        and Assignment.query.filter_by(record_id=record.id).first() is not None
    ):
        return False, _("Эта строка уже содержит задания другого ученика. Попроси учителя создать новую строку.")

    other_linked = (
        StudentRecord.query.filter(
            StudentRecord.student_user_id == user.id,
            StudentRecord.id != record.id,
        ).first()
    )
    if other_linked is not None:
        return False, _("Этот аккаунт уже привязан к другой записи — обратитесь к менеджеру.")

    sync_legacy_teacher_id(record)
    return True, ""


def inspect_code_for_student(user: User | None, code: str | None) -> tuple[bool, StudentRecord | None, str]:
    """Validate a code for an authenticated student confirmation step without claiming yet."""
    if not user or getattr(user, "role", None) != "student" or getattr(user, "is_blocked", False):
        return False, None, _("Код приглашения предназначен для ученика.")

    norm = normalize_invite_code(code)
    if not norm:
        return False, None, _("Введи код.")

    record = StudentRecord.query.filter_by(invite_code=norm).first()
    ok, err = _validate_claim_candidate(user, record)
    if not ok:
        return False, None, err
    return True, record, ""


def claim_code(user: User | None, code: str | None) -> tuple[bool, str]:
    """Atomically claim a one-time invite code on behalf of a student account. Returns (ok, message)."""
    if not user or getattr(user, "role", None) != "student" or getattr(user, "is_blocked", False):
        return False, _("Код приглашения предназначен для ученика.")

    norm = normalize_invite_code(code)
    if not norm:
        return False, _("Введи код.")

    q = StudentRecord.query.filter_by(invite_code=norm)
    bind = db.session.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        q = q.with_for_update()
    record = q.populate_existing().first()

    ok, err = _validate_claim_candidate(user, record)
    if not ok:
        return False, err

    now = utcnow()
    res = db.session.execute(
        update(StudentRecord)
        .where(
            StudentRecord.id == record.id,
            StudentRecord.student_user_id.is_(None),
            StudentRecord.claimed_at.is_(None),
            StudentRecord.invite_revoked_at.is_(None),
        )
        .values(
            student_user_id=user.id,
            previous_student_user_id=user.id,
            linked_at=now,
            claimed_at=now,
            claimed_by_user_id=user.id,
        )
    )
    if res.rowcount != 1:
        db.session.rollback()
        return False, _("Этот код уже использован — обратитесь к менеджеру.")

    db.session.refresh(record)
    if user.profile and not user.profile.exam and record.exam:
        user.profile.exam = record.exam
    if record.source_lead_id and record.source_lead and record.source_lead.converted_student_id is None:
        record.source_lead.converted_student_id = user.id

    write_audit_log(
        actor_id=user.id,
        action="student_code_claimed",
        entity_type="student_record",
        entity_id=record.id,
        old_value={"student_user_id": None, "claimed_at": None},
        new_value={
            "student_user_id": user.id,
            "claimed_by_user_id": user.id,
            "teacher_id": record.teacher_id,
            "code_last4": code_last4(norm),
        },
    )
    db.session.commit()
    teacher_name = record.teacher.name if record.teacher else _("Преподаватель")
    return True, _("Готово, ты подключён к учителю: %(name)s.", name=teacher_name)


# --------------------------------------------------------------------------- Stage 4 visibility helpers


def can_teacher_access(teacher: User | None, student_record: StudentRecord | None, at: datetime | None = None) -> bool:
    """Single source of truth for whether a teacher can access a StudentRecord (open assignment or at `at`)."""
    if not teacher or not student_record or getattr(teacher, "is_blocked", False):
        return False
    if getattr(teacher, "is_admin", False):
        return True
    if teacher.role != "teacher" or not teacher.is_approved:
        return False

    q = TeacherAssignment.query.filter(
        TeacherAssignment.student_record_id == student_record.id,
        TeacherAssignment.teacher_user_id == teacher.id,
    )
    if at is None:
        if q.filter(TeacherAssignment.ended_at.is_(None)).first() is not None:
            return True
        # Legacy fallback ONLY for raw test-created records that never inserted TeacherAssignment rows
        has_any = TeacherAssignment.query.filter_by(student_record_id=student_record.id).first() is not None
        return (not has_any) and (student_record.teacher_id == teacher.id)

    return (
        q.filter(
            TeacherAssignment.started_at <= at,
            or_(TeacherAssignment.ended_at.is_(None), TeacherAssignment.ended_at > at),
        ).first()
        is not None
    )


def teacher_open_records_query(teacher_id: int):
    """Return a query of StudentRecords where `teacher_id` has an OPEN assignment (plus legacy zero-history rows)."""
    open_match = exists().where(
        TeacherAssignment.student_record_id == StudentRecord.id,
        TeacherAssignment.teacher_user_id == teacher_id,
        TeacherAssignment.ended_at.is_(None),
    )
    legacy_match = db.and_(
        StudentRecord.teacher_id == teacher_id,
        ~exists().where(TeacherAssignment.student_record_id == StudentRecord.id),
    )
    return StudentRecord.query.filter(or_(open_match, legacy_match))


def teacher_progress_since(teacher: User | None, student_record: StudentRecord | None) -> datetime | None:
    """Return earliest timestamp from which `teacher` may view student progress (None if unrestricted)."""
    if not teacher or not student_record or getattr(teacher, "is_admin", False):
        return None
    try:
        if current_app.config.get("NEW_TEACHER_SEES_EARLIER_PROGRESS", False):
            return None
    except RuntimeError:
        pass
    open_rows = (
        TeacherAssignment.query.filter(
            TeacherAssignment.student_record_id == student_record.id,
            TeacherAssignment.teacher_user_id == teacher.id,
            TeacherAssignment.ended_at.is_(None),
        )
        .order_by(TeacherAssignment.started_at.asc(), TeacherAssignment.id.asc())
        .all()
    )
    if open_rows:
        return open_rows[0].started_at
    return None


def student_current_teachers(user_id: int) -> list[dict]:
    """Return active/open teacher assignment summaries for a student account."""
    records = StudentRecord.query.filter_by(student_user_id=user_id).all()
    if not records:
        return []
    rec_ids = [r.id for r in records]
    open_tas = (
        TeacherAssignment.query.options(
            joinedload(TeacherAssignment.teacher),
            joinedload(TeacherAssignment.course),
            joinedload(TeacherAssignment.student_record),
        )
        .filter(
            TeacherAssignment.student_record_id.in_(rec_ids),
            TeacherAssignment.ended_at.is_(None),
        )
        .order_by(TeacherAssignment.started_at.asc(), TeacherAssignment.id.asc())
        .all()
    )
    result = []
    seen = set()
    recs_with_history = {
        row[0]
        for row in db.session.query(TeacherAssignment.student_record_id)
        .filter(TeacherAssignment.student_record_id.in_(rec_ids))
        .distinct()
        .all()
    }
    for ta in open_tas:
        if ta.teacher and not ta.teacher.is_blocked:
            key = (ta.teacher.id, ta.course_id)
            if key not in seen:
                seen.add(key)
                result.append({"teacher": ta.teacher, "course": ta.course, "record": ta.student_record})
    for r in records:
        if r.id not in recs_with_history and r.teacher and not r.teacher.is_blocked:
            key = (r.teacher.id, r.course_id)
            if key not in seen:
                seen.add(key)
                result.append({"teacher": r.teacher, "course": r.course, "record": r})
    return result


def teacher_ids_for_student(user_id: int) -> set[int]:
    """Return active teacher IDs from open assignments (used by content tree & daily picks)."""
    return {item["teacher"].id for item in student_current_teachers(user_id)}

"""Stage 6: Academic Operations (Locations, Courses, Groups, Enrollments with history, Lessons, Attendance)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user
from sqlalchemy.orm import joinedload

from .access import permission_required
from .audit import write_audit_log
from .extensions import db
from .models import (
    AcademicCourse,
    ENROLLMENT_STATUSES,
    GroupEnrollment,
    LESSON_ATTENDANCE_STATUSES,
    LESSON_MODES,
    Lesson,
    LessonAttendance,
    Location,
    StudyGroup,
    User,
    utcnow,
)

bp = Blueprint("academic", __name__, url_prefix="/academic")

LESSON_MODE_LABELS = {
    "online": "Онлайн",
    "offline": "Офлайн",
}

ATTENDANCE_LABELS = {
    "present": "Был",
    "absent": "Отсутствовал",
    "late": "Опоздал",
    "excused": "Уважит. причина",
}

RETRO_WINDOW_HOURS = 24


def _parse_date(raw: str | None) -> date | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _parse_dt(raw: str | None) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:16], fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=16, minute=0)
            return dt
        except ValueError:
            continue
    return None


def _can_access_lesson(lesson: Lesson) -> bool:
    if current_user.role in ("sales_manager", "supervisor", "admin"):
        return True
    if current_user.role == "teacher":
        return lesson.teacher_id == current_user.id or (lesson.group and lesson.group.teacher_id == current_user.id)
    return False


# --------------------------------------------------------------------------- Schedule & Online/Offline Report


@bp.route("/schedule")
@permission_required("academic.schedule.read")
def schedule():
    mode_filter = (request.args.get("lesson_mode") or "").strip().lower()
    group_id = request.args.get("group_id", type=int)
    location_id = request.args.get("location_id", type=int)
    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"))

    q = Lesson.query.options(
        joinedload(Lesson.group).joinedload(StudyGroup.course),
        joinedload(Lesson.teacher),
        joinedload(Lesson.location),
        joinedload(Lesson.attendances),
    )
    if current_user.role == "teacher":
        q = q.join(StudyGroup, StudyGroup.id == Lesson.group_id).filter(
            (Lesson.teacher_id == current_user.id) | (StudyGroup.teacher_id == current_user.id)
        )
    if mode_filter in LESSON_MODES:
        q = q.filter(Lesson.lesson_mode == mode_filter)
    if group_id:
        q = q.filter(Lesson.group_id == group_id)
    if location_id:
        q = q.filter(Lesson.location_id == location_id)
    if date_from:
        q = q.filter(Lesson.starts_at >= datetime.combine(date_from, time.min))
    if date_to:
        q = q.filter(Lesson.starts_at < datetime.combine(date_to + timedelta(days=1), time.min))

    lessons = q.order_by(Lesson.starts_at.desc()).limit(200).all()

    # Online / Offline breakdown report
    mode_counts = Counter(l.lesson_mode for l in lessons)
    att_by_mode = {"online": Counter(), "offline": Counter()}
    for l in lessons:
        bucket = att_by_mode.get(l.lesson_mode)
        if bucket is not None:
            for a in l.attendances:
                bucket[a.status] += 1

    groups_q = StudyGroup.query.options(
        joinedload(StudyGroup.course),
        joinedload(StudyGroup.teacher),
        joinedload(StudyGroup.default_location),
        joinedload(StudyGroup.enrollments).joinedload(GroupEnrollment.student),
    ).order_by(StudyGroup.name.asc())
    if current_user.role == "teacher":
        groups_q = groups_q.filter(StudyGroup.teacher_id == current_user.id)
    groups = groups_q.all()

    return render_template(
        "academic/schedule.html",
        lessons=lessons,
        groups=groups,
        locations=Location.query.filter_by(is_active=True).order_by(Location.name.asc()).all(),
        courses=AcademicCourse.query.filter_by(is_active=True).order_by(AcademicCourse.name.asc()).all(),
        teachers=User.query.filter_by(role="teacher", is_approved=True, is_blocked=False).order_by(User.name.asc()).all(),
        students=User.query.filter_by(role="student", is_blocked=False).order_by(User.name.asc()).limit(150).all(),
        mode_counts=mode_counts,
        att_by_mode=att_by_mode,
        LESSON_MODES=LESSON_MODES,
        LESSON_MODE_LABELS=LESSON_MODE_LABELS,
        ATTENDANCE_LABELS=ATTENDANCE_LABELS,
        filters={
            "lesson_mode": mode_filter,
            "group_id": group_id or "",
            "location_id": location_id or "",
            "date_from": request.args.get("date_from") or "",
            "date_to": request.args.get("date_to") or "",
        },
    )


# --------------------------------------------------------------------------- Management CRUD (Supervisor / Admin)


@bp.post("/locations/new")
@permission_required("academic.schedule.manage")
def location_create():
    name = (request.form.get("name") or "").strip()
    if len(name) < 2:
        flash(_("Укажите название локации."), "error")
        return redirect(url_for("academic.schedule"))
    loc = Location(
        name=name,
        address=(request.form.get("address") or "").strip(),
        room=(request.form.get("room") or "").strip(),
    )
    db.session.add(loc)
    db.session.commit()
    flash(_("Локация «%(n)s» добавлена.", n=loc.name), "success")
    return redirect(url_for("academic.schedule"))


@bp.post("/courses/new")
@permission_required("academic.schedule.manage")
def course_create():
    code = (request.form.get("code") or "").strip().upper()
    name = (request.form.get("name") or "").strip()
    exam = (request.form.get("exam") or "").strip().upper()
    if not code or len(name) < 2:
        flash(_("Укажите код и название курса."), "error")
        return redirect(url_for("academic.schedule"))
    if AcademicCourse.query.filter_by(code=code).first():
        flash(_("Курс с таким кодом уже существует."), "error")
        return redirect(url_for("academic.schedule"))
    c = AcademicCourse(code=code, name=name, exam=exam)
    db.session.add(c)
    db.session.commit()
    flash(_("Курс «%(n)s» создан.", n=c.name), "success")
    return redirect(url_for("academic.schedule"))


@bp.post("/groups/new")
@permission_required("academic.schedule.manage")
def group_create():
    name = (request.form.get("name") or "").strip()
    course_id = request.form.get("course_id", type=int)
    teacher_id = request.form.get("teacher_id", type=int) or None
    default_location_id = request.form.get("default_location_id", type=int) or None
    course = db.session.get(AcademicCourse, course_id) if course_id else None
    if len(name) < 2 or not course:
        flash(_("Укажите название группы и курс."), "error")
        return redirect(url_for("academic.schedule"))
    if teacher_id:
        t = db.session.get(User, teacher_id)
        if not t or t.role not in ("teacher", "admin"):
            teacher_id = None
    g = StudyGroup(
        name=name,
        course_id=course.id,
        teacher_id=teacher_id,
        default_location_id=default_location_id,
    )
    db.session.add(g)
    db.session.commit()
    flash(_("Группа «%(n)s» создана.", n=g.name), "success")
    return redirect(url_for("academic.schedule"))


@bp.post("/groups/<int:group_id>/enroll")
@permission_required("academic.schedule.manage")
def group_enroll(group_id: int):
    group = db.session.get(StudyGroup, group_id) or abort(404)
    student_id = request.form.get("student_user_id", type=int)
    student = db.session.get(User, student_id) if student_id else None
    if not student or student.role != "student":
        flash(_("Выберите ученика."), "error")
        return redirect(url_for("academic.schedule"))
    existing = GroupEnrollment.query.filter_by(
        group_id=group.id, student_user_id=student.id, left_at=None
    ).first()
    if existing:
        flash(_("Ученик уже состоит в этой группе."), "info")
        return redirect(url_for("academic.schedule"))
    enr = GroupEnrollment(
        group_id=group.id,
        student_user_id=student.id,
        course_id=group.course_id,
        status="active",
        note=(request.form.get("note") or "").strip(),
    )
    db.session.add(enr)
    db.session.commit()
    flash(_("%(s)s зачислен в группу «%(g)s».", s=student.name, g=group.name), "success")
    return redirect(url_for("academic.schedule"))


@bp.post("/enrollments/<int:enrollment_id>/close")
@permission_required("academic.schedule.manage")
def enrollment_close(enrollment_id: int):
    """Close an active enrollment while preserving full historical record (`left_at`)."""
    enr = db.session.get(GroupEnrollment, enrollment_id) or abort(404)
    if enr.left_at is None:
        new_status = (request.form.get("status") or "completed").strip()
        if new_status not in ENROLLMENT_STATUSES or new_status == "active":
            new_status = "completed"
        old_val = {"status": enr.status, "left_at": None}
        enr.left_at = utcnow()
        enr.status = new_status
        write_audit_log(
            actor_id=current_user.id,
            action="enrollment_close",
            entity_type="group_enrollment",
            entity_id=enr.id,
            old_value=old_val,
            new_value={"status": enr.status, "left_at": enr.left_at.isoformat()},
            reason=(request.form.get("reason") or "").strip(),
        )
        db.session.commit()
        flash(_("Запись о зачислении закрыта (история сохранена)."), "info")
    return redirect(url_for("academic.schedule"))


@bp.post("/lessons/new")
@permission_required("academic.schedule.manage")
def lesson_create():
    group_id = request.form.get("group_id", type=int)
    group = db.session.get(StudyGroup, group_id) if group_id else None
    starts_at = _parse_dt(request.form.get("starts_at"))
    lesson_mode = (request.form.get("lesson_mode") or "offline").strip().lower()
    if lesson_mode not in LESSON_MODES:
        lesson_mode = "offline"
    if not group or not starts_at:
        flash(_("Укажите группу и дату/время занятия."), "error")
        return redirect(url_for("academic.schedule"))

    location_id = request.form.get("location_id", type=int) or (group.default_location_id if lesson_mode == "offline" else None)
    meeting_url = (request.form.get("meeting_url") or "").strip()
    teacher_id = request.form.get("teacher_id", type=int) or group.teacher_id
    duration_min = max(15, min(360, request.form.get("duration_min", 90, type=int) or 90))

    lesson = Lesson(
        group_id=group.id,
        teacher_id=teacher_id,
        starts_at=starts_at,
        duration_min=duration_min,
        lesson_mode=lesson_mode,
        location_id=location_id if lesson_mode == "offline" else None,
        meeting_url=meeting_url if lesson_mode == "online" else "",
        topic=(request.form.get("topic") or "").strip(),
    )
    db.session.add(lesson)
    db.session.commit()
    flash(_("Урок добавлен в расписание."), "success")
    return redirect(url_for("academic.lesson_detail", lesson_id=lesson.id))


# --------------------------------------------------------------------------- Lesson Detail & Attendance


@bp.route("/lessons/<int:lesson_id>")
@permission_required("academic.attendance.read")
def lesson_detail(lesson_id: int):
    lesson = (
        Lesson.query.options(
            joinedload(Lesson.group).joinedload(StudyGroup.course),
            joinedload(Lesson.teacher),
            joinedload(Lesson.location),
            joinedload(Lesson.attendances).joinedload(LessonAttendance.student),
        )
        .filter_by(id=lesson_id)
        .first()
        or abort(404)
    )
    if not _can_access_lesson(lesson):
        abort(403)

    # Roster: students active in this group at lesson time (enrolled_at <= lesson end and (left_at is None or left_at >= starts_at))
    enrollments = (
        GroupEnrollment.query.options(joinedload(GroupEnrollment.student))
        .filter(
            GroupEnrollment.group_id == lesson.group_id,
            (GroupEnrollment.left_at.is_(None)) | (GroupEnrollment.left_at >= lesson.starts_at),
        )
        .order_by(GroupEnrollment.enrolled_at.asc())
        .all()
    )
    att_by_student = {a.student_user_id: a for a in lesson.attendances}
    # Ensure any already-marked student is also shown even if later removed
    roster_ids = {e.student_user_id for e in enrollments}
    extra_students = [a.student for a in lesson.attendances if a.student_user_id not in roster_ids and a.student]
    roster = [e.student for e in enrollments if e.student] + extra_students

    now = utcnow()
    is_retro_window_passed = lesson.starts_at < (now - timedelta(hours=RETRO_WINDOW_HOURS))
    can_mark = current_user.has_perm("academic.attendance.mark") and (
        not is_retro_window_passed or current_user.has_perm("academic.attendance.edit_retro")
    )

    return render_template(
        "academic/lesson_detail.html",
        lesson=lesson,
        roster=roster,
        att_by_student=att_by_student,
        is_retro_window_passed=is_retro_window_passed,
        can_mark=can_mark,
        LESSON_MODE_LABELS=LESSON_MODE_LABELS,
        LESSON_ATTENDANCE_STATUSES=LESSON_ATTENDANCE_STATUSES,
        ATTENDANCE_LABELS=ATTENDANCE_LABELS,
    )


@bp.post("/lessons/<int:lesson_id>/attendance")
@permission_required("academic.attendance.mark")
def lesson_mark_attendance(lesson_id: int):
    lesson = db.session.get(Lesson, lesson_id) or abort(404)
    if not _can_access_lesson(lesson):
        abort(403)

    student_id = request.form.get("student_user_id", type=int)
    status = (request.form.get("status") or "").strip().lower()
    note = (request.form.get("note") or "").strip()
    reason = (request.form.get("reason") or "").strip()

    student = db.session.get(User, student_id) if student_id else None
    if not student or student.role != "student" or status not in LESSON_ATTENDANCE_STATUSES:
        abort(400)

    now = utcnow()
    existing = LessonAttendance.query.filter_by(lesson_id=lesson.id, student_user_id=student.id).first()
    is_past_edit = existing is not None and lesson.starts_at < now
    is_retro_locked = existing is not None and lesson.starts_at < (now - timedelta(hours=RETRO_WINDOW_HOURS))

    if is_retro_locked and not current_user.has_perm("academic.attendance.edit_retro"):
        abort(403)

    if existing is None:
        row = LessonAttendance(
            lesson_id=lesson.id,
            student_user_id=student.id,
            status=status,
            note=note,
            marked_by_id=current_user.id,
            marked_at=now,
            updated_at=now,
        )
        db.session.add(row)
        db.session.commit()
        flash(_("Посещаемость отмечена."), "success")
        return redirect(url_for("academic.lesson_detail", lesson_id=lesson.id))

    old_val = {"status": existing.status, "note": existing.note}
    if existing.status != status or existing.note != note:
        if is_retro_locked and not reason:
            flash(_("Для ретро-правки посещаемости укажите причину."), "error")
            return redirect(url_for("academic.lesson_detail", lesson_id=lesson.id))
        existing.status = status
        existing.note = note
        existing.marked_by_id = current_user.id
        existing.updated_at = now
        if is_past_edit:
            write_audit_log(
                actor_id=current_user.id,
                action="attendance_retro_edit",
                entity_type="lesson_attendance",
                entity_id=existing.id,
                old_value=old_val,
                new_value={"status": status, "note": note, "lesson_id": lesson.id, "student_user_id": student.id},
                reason=reason,
            )
        db.session.commit()
        flash(_("Посещаемость обновлена."), "success")
    return redirect(url_for("academic.lesson_detail", lesson_id=lesson.id))

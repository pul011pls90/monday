"""Stage 6: Academic Operations (Locations, Courses, Groups, Enrollments with history, Lessons, Attendance)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from urllib.parse import urlparse

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
    LessonPassUsage,
    Location,
    StudentPass,
    StudyGroup,
    TeacherPayRate,
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


def _safe_meeting_url(raw: str | None) -> str | None:
    """Allow only empty strings or http/https URLs with a valid host to prevent javascript:/data: XSS."""
    s = (raw or "").strip()
    if not s:
        return ""
    parsed = urlparse(s)
    if parsed.scheme.lower() in ("http", "https") and bool(parsed.netloc):
        return s
    return None


# --------------------------------------------------------------------------- Schedule & Online/Offline Report


def _detect_lesson_conflicts(lessons: list[Lesson]) -> set[int]:
    """Return IDs of lessons sharing an overlapping time window with the same room or teacher."""
    conflicts: set[int] = set()
    intervals = [
        (l, l.starts_at, l.starts_at + timedelta(minutes=l.duration_min or 90))
        for l in lessons
    ]
    for i, (la, sa, ea) in enumerate(intervals):
        for lb, sb, eb in intervals[i + 1 :]:
            if sa < eb and sb < ea:
                same_room = (
                    la.lesson_mode == "offline"
                    and lb.lesson_mode == "offline"
                    and la.location_id is not None
                    and la.location_id == lb.location_id
                )
                same_teacher = la.teacher_id is not None and la.teacher_id == lb.teacher_id
                if same_room or same_teacher:
                    conflicts.add(la.id)
                    conflicts.add(lb.id)
    return conflicts


@bp.route("/schedule")
@permission_required("academic.schedule.read")
def schedule():
    view = (request.args.get("view") or "list").strip().lower()
    if view not in ("list", "week", "rooms", "teachers"):
        view = "list"
    mode_filter = (request.args.get("lesson_mode") or "").strip().lower()
    group_id = request.args.get("group_id", type=int)
    location_id = request.args.get("location_id", type=int)
    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"))

    today_d = utcnow().date()
    week_anchor = _parse_date(request.args.get("week")) or today_d
    week_start = week_anchor - timedelta(days=week_anchor.weekday())
    week_days = [week_start + timedelta(days=i) for i in range(7)]

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
    if view in ("week", "rooms", "teachers") and not date_from and not date_to:
        q = q.filter(
            Lesson.starts_at >= datetime.combine(week_start, time.min),
            Lesson.starts_at < datetime.combine(week_start + timedelta(days=7), time.min),
        )
        lessons = q.order_by(Lesson.starts_at.asc()).limit(400).all()
    else:
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

    locations = Location.query.filter_by(is_active=True).order_by(Location.name.asc()).all()
    teachers = User.query.filter_by(role="teacher", is_approved=True, is_blocked=False).order_by(User.name.asc()).all()

    lessons_by_day: dict[date, list[Lesson]] = {d: [] for d in week_days}
    for l in lessons:
        ld = l.starts_at.date()
        if ld in lessons_by_day:
            lessons_by_day[ld].append(l)

    conflict_ids = _detect_lesson_conflicts(lessons)

    room_lanes = []
    if view == "rooms":
        for loc in locations:
            by_day = {d: [] for d in week_days}
            for l in lessons:
                if l.lesson_mode == "offline" and l.location_id == loc.id and l.starts_at.date() in by_day:
                    by_day[l.starts_at.date()].append(l)
            room_lanes.append({"label": loc.name + (f" · {loc.room}" if loc.room else ""), "by_day": by_day})
        online_by_day = {d: [] for d in week_days}
        for l in lessons:
            if l.lesson_mode == "online" and l.starts_at.date() in online_by_day:
                online_by_day[l.starts_at.date()].append(l)
        room_lanes.append({"label": _("Онлайн (все ссылки)"), "by_day": online_by_day})

    teacher_lanes = []
    if view == "teachers":
        can_payroll = current_user.has_perm("academic.payroll.read")
        rates_by_teacher: dict[int, list[TeacherPayRate]] = {}
        if can_payroll and teachers:
            for r in TeacherPayRate.query.filter_by(is_active=True).all():
                rates_by_teacher.setdefault(r.teacher_id, []).append(r)
        visible_teachers = [t for t in teachers if current_user.role != "teacher" or t.id == current_user.id]
        for tch in visible_teachers:
            by_day = {d: [] for d in week_days}
            total_min = 0
            tch_lessons = []
            for l in lessons:
                if l.teacher_id == tch.id and l.starts_at.date() in by_day:
                    by_day[l.starts_at.date()].append(l)
                    total_min += l.duration_min or 90
                    tch_lessons.append(l)
            est_pay = None
            if can_payroll:
                t_rates = rates_by_teacher.get(tch.id, [])
                if t_rates:
                    accrued = 0
                    for l in tch_lessons:
                        cid = l.group.course_id if l.group else None
                        rate = next((r for r in t_rates if r.course_id == cid), None) or next((r for r in t_rates if r.course_id is None), None)
                        if rate:
                            if rate.rate_type == "per_lesson":
                                accrued += rate.rate_amount
                            elif rate.rate_type == "per_student":
                                accrued += rate.rate_amount * sum(1 for a in l.attendances if a.status in ("present", "late"))
                    if not accrued:
                        fixed = next((r for r in t_rates if r.rate_type == "fixed_month"), None)
                        if fixed:
                            accrued = fixed.rate_amount
                    est_pay = accrued
            teacher_lanes.append({"teacher": tch, "hours": round(total_min / 60, 1), "by_day": by_day, "est_pay": est_pay})

    return render_template(
        "academic/schedule.html",
        view=view,
        today_d=today_d,
        week_start=week_start,
        prev_week=(week_start - timedelta(days=7)).isoformat(),
        next_week=(week_start + timedelta(days=7)).isoformat(),
        week_days=week_days,
        lessons=lessons,
        lessons_by_day=lessons_by_day,
        room_lanes=room_lanes,
        teacher_lanes=teacher_lanes,
        conflict_ids=conflict_ids,
        groups=groups,
        locations=locations,
        courses=AcademicCourse.query.filter_by(is_active=True).order_by(AcademicCourse.name.asc()).all(),
        teachers=teachers,
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
            "week": week_start.isoformat(),
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
    if default_location_id and not db.session.get(Location, default_location_id):
        default_location_id = None
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
    if location_id and not db.session.get(Location, location_id):
        location_id = None
    raw_meeting_url = request.form.get("meeting_url")
    meeting_url = _safe_meeting_url(raw_meeting_url) if lesson_mode == "online" else ""
    if meeting_url is None:
        flash(_("Ссылка на урок должна начинаться с http:// или https://."), "error")
        return redirect(url_for("academic.schedule"))
    teacher_id = request.form.get("teacher_id", type=int) or group.teacher_id
    if teacher_id:
        t = db.session.get(User, teacher_id)
        if not t or t.role not in ("teacher", "admin"):
            teacher_id = group.teacher_id
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
    enrollment_by_student = {e.student_user_id: e for e in enrollments}
    extra_students = [a.student for a in lesson.attendances if a.student_user_id not in roster_ids and a.student]
    roster = [e.student for e in enrollments if e.student] + extra_students

    group_att_summary: dict[int, dict[str, int]] = {}
    pass_by_student: dict[int, StudentPass] = {}
    roster_user_ids = [st.id for st in roster]
    if roster_user_ids:
        hist_rows = (
            LessonAttendance.query.join(Lesson, Lesson.id == LessonAttendance.lesson_id)
            .filter(Lesson.group_id == lesson.group_id, LessonAttendance.student_user_id.in_(roster_user_ids))
            .all()
        )
        for hr in hist_rows:
            bucket = group_att_summary.setdefault(hr.student_user_id, {"present": 0, "late": 0, "absent": 0, "excused": 0, "total": 0})
            bucket[hr.status] = bucket.get(hr.status, 0) + 1
            bucket["total"] += 1
        all_passes = (
            StudentPass.query.options(joinedload(StudentPass.plan))
            .filter(StudentPass.student_user_id.in_(roster_user_ids))
            .order_by(StudentPass.status != "active", StudentPass.expires_at.asc(), StudentPass.id.desc())
            .all()
        )
        for sp in all_passes:
            pass_by_student.setdefault(sp.student_user_id, sp)

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
        enrollment_by_student=enrollment_by_student,
        group_att_summary=group_att_summary,
        pass_by_student=pass_by_student,
        is_retro_window_passed=is_retro_window_passed,
        can_mark=can_mark,
        LESSON_MODE_LABELS=LESSON_MODE_LABELS,
        LESSON_ATTENDANCE_STATUSES=LESSON_ATTENDANCE_STATUSES,
        ATTENDANCE_LABELS=ATTENDANCE_LABELS,
    )


def _sync_pass_usage(lesson: Lesson, student_id: int, new_status: str, now: datetime) -> None:
    """Atomically deduct 1 pass lesson credit on first present/late mark or refund on retro reversal."""
    usage = LessonPassUsage.query.filter_by(lesson_id=lesson.id, student_user_id=student_id).first()
    if new_status in ("present", "late"):
        if usage is not None:
            return
        course_id = lesson.group.course_id if lesson.group else None
        candidates = (
            StudentPass.query.options(joinedload(StudentPass.plan))
            .filter(
                StudentPass.student_user_id == student_id,
                StudentPass.status == "active",
                (StudentPass.expires_at.is_(None)) | (StudentPass.expires_at >= now),
            )
            .order_by(StudentPass.expires_at.asc(), StudentPass.id.asc())
            .all()
        )
        chosen = next((p for p in candidates if p.plan and p.plan.course_id == course_id), None) or next(
            (p for p in candidates if p.plan and p.plan.course_id is None), None
        ) or (candidates[0] if candidates else None)
        if chosen is None:
            return
        if chosen.lessons_remaining is not None:
            if chosen.lessons_remaining <= 0:
                chosen.status = "depleted"
                return
            chosen.lessons_remaining -= 1
            if chosen.lessons_remaining <= 0:
                chosen.status = "depleted"
        db.session.add(LessonPassUsage(lesson_id=lesson.id, student_user_id=student_id, pass_id=chosen.id))
    elif usage is not None:
        sp = db.session.get(StudentPass, usage.pass_id)
        if sp is not None and sp.lessons_remaining is not None:
            sp.lessons_remaining += 1
            if sp.status == "depleted" and sp.lessons_remaining > 0:
                sp.status = "active"
        db.session.delete(usage)


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
    if existing is None:
        enrolled = GroupEnrollment.query.filter_by(group_id=lesson.group_id, student_user_id=student.id).first()
        if enrolled is None:
            abort(400)
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
        _sync_pass_usage(lesson, student.id, status, now)
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
        _sync_pass_usage(lesson, student.id, status, now)
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

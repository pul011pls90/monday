"""Teacher side: dashboard, students, works (tests & homework), question bank, assigning and checking."""
import os
from collections import defaultdict
import re
import uuid
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user
from werkzeug.utils import secure_filename

from .models import local_date, local_midnight_utc, local_now, today as local_today  # noqa: F401
from .access import staff_required, teacher_required
from .constants import EXAMS, MISTAKE_REASONS, TRUSTED_TEACHER_THRESHOLD, WORK_KINDS
from .extensions import db
from .models import utcnow
from .models import (INPUT_FORMATS, MATERIAL_TYPES, QUESTION_WORD_LIMIT, Assignment, Attempt, AttemptAnswer,
                     ContentNode, Question, Skill, StudentRecord, Work, new_invite_code)
from .services import (content_tree, homework_state, latest_attempt, mistake_breakdown, parse_number,
                       progress_summary, publish_work, record_progress, skill_map, visible_nodes)

bp = Blueprint("teacher", __name__, url_prefix="/teacher")

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def _my_records():
    return StudentRecord.query.filter_by(teacher_id=current_user.id)


def _own_record(record_id):
    r = db.session.get(StudentRecord, record_id)
    if not r or (r.teacher_id != current_user.id and not current_user.is_admin):
        abort(404)
    return r


def _own_work(work_id):
    w = db.session.get(Work, work_id)
    if not w or (w.author_id != current_user.id and not current_user.is_admin):
        abort(404)
    return w


def _own_question(question_id):
    q = db.session.get(Question, question_id)
    if not q:
        abort(404)
    reviewer_may = current_user.can_review and q.status == "pending"
    if q.author_id != current_user.id and not current_user.is_admin and not reviewer_may:
        abort(404)
    return q


def _after_question_save():
    if current_user.is_assistant:
        return redirect(url_for("assistant.mine"))
    if request.form.get("back") == "review" and current_user.can_review:
        return redirect(url_for("review.queue"))
    return redirect(url_for("teacher.questions"))


# --------------------------------------------------------------------------- content tree helpers


def _can_see_node(node):
    return node is not None and not node.archived and (
        node.owner_id is None or node.owner_id == current_user.id or current_user.is_admin)


def _can_edit_node(node):
    return node is not None and (node.owner_id == current_user.id or (current_user.is_admin and node.owner_id is None))


def _tree_json():
    """The tree for the cascading selects in editors."""
    out = []
    for t in content_tree(current_user):
        out.append({"id": t["node"].id, "name": t["node"].name, "own": not t["node"].is_shared, "subs": [
            {"id": s["node"].id, "name": s["node"].name, "own": not s["node"].is_shared,
             "nodes": [{"id": n.id, "name": n.name, "own": not n.is_shared} for n in s["nodes"]]}
            for s in t["subtopics"]]})
    return out


def _new_node(level, name, parent, exams):
    node = ContentNode(level=level, name=name[:160], parent=parent, exams=list(exams or []),
                       owner_id=None if current_user.is_admin else current_user.id,
                       position=1000 + (len(parent.children) if parent is not None else 0))
    db.session.add(node)
    return node


def _resolve_node(form, exams):
    """The tree node a question goes to: an existing one, or new entries typed by the teacher.

    Form fields: topic_id, subtopic_id, skill_id (selects) and new_topic, new_subtopic, new_node (text).
    """
    new_topic = form.get("new_topic", "").strip()
    new_sub = form.get("new_subtopic", "").strip()
    new_leaf = form.get("new_node", "").strip()
    if not (new_topic or new_sub or new_leaf):
        node = db.session.get(ContentNode, form.get("skill_id", type=int) or 0)
        if not _can_see_node(node) or node.level != "node":
            return None, _("Выберите навык: тема → подтема → навык.")
        return node, None
    if new_topic and not (new_sub and new_leaf):
        return None, _("Для новой темы укажите и подтему, и навык.")
    if new_sub and not new_leaf:
        return None, _("Для новой подтемы укажите и навык.")
    if new_topic:
        topic = _new_node("topic", new_topic, None, exams)
    else:
        topic = db.session.get(ContentNode, form.get("topic_id", type=int) or 0)
        if new_sub and (not _can_see_node(topic) or topic.level != "topic"):
            return None, _("Выберите тему для новой подтемы.")
    if new_sub:
        sub = _new_node("subtopic", new_sub, topic, exams)
    else:
        sub = db.session.get(ContentNode, form.get("subtopic_id", type=int) or 0)
        if not _can_see_node(sub) or sub.level != "subtopic":
            return None, _("Выберите подтему для нового навыка.")
    return _new_node("node", new_leaf, sub, exams), None


# --------------------------------------------------------------------------- dashboard


@bp.route("/")
@teacher_required
def dashboard():
    from .daily import teacher_daily
    from .insights import class_dots, fresh_mistakes, homework_week, monday_results
    from .models import Attendance
    from .services import week_start
    records = _my_records().all()
    today = local_today()
    weekday = today.weekday()
    today_lessons = sorted([r for r in records if weekday in (r.lesson_days or []) and r.lesson_time],
                           key=lambda r: r.lesson_time)
    marks = {m.record_id: m.status for m in Attendance.query.filter(
        Attendance.day == today, Attendance.record_id.in_([r.id for r in today_lessons] or [0])).all()}
    now_hm = local_now().strftime("%H:%M")
    next_lesson = next((r for r in today_lessons if r.lesson_time >= now_hm), None)
    to_check = []
    for a in Assignment.query.filter_by(teacher_id=current_user.id, checked_at=None).all():
        if a.record.student_user_id and latest_attempt(a, a.record.student_user_id):
            to_check.append(a)
    behind = []
    for r in records:
        progress = record_progress(r)
        overdue = sum(1 for a in r.assignments
                      if r.student_user_id and homework_state(a, r.student_user_id) == "overdue")
        if progress < 40 or overdue:
            behind.append({"record": r, "progress": progress, "overdue": overdue})
    offset = request.args.get("week", 0, type=int)
    start = week_start(today) + timedelta(weeks=offset)
    pending_q = Question.query.filter_by(author_id=current_user.id, status="pending").count()
    return render_template("teacher/dashboard.html", today_lessons=today_lessons, marks=marks, next_lesson=next_lesson,
                           to_check=to_check, behind=behind, records=records, pending_q=pending_q,
                           week=homework_week(current_user.id, start), week_offset=offset, today=today,
                           mistakes=fresh_mistakes(records), dots=class_dots(current_user, records),
                           monday=monday_results(records), daily=teacher_daily(current_user, records))


@bp.route("/daily/<int:pick_id>/remove", methods=["POST"])
@teacher_required
def daily_remove(pick_id):
    from .models import DailyPick
    p = db.session.get(DailyPick, pick_id)
    if not p or p.teacher_id != current_user.id:
        abort(404)
    if p.answers:
        flash(_("На этот вопрос уже отвечали — убрать нельзя."), "error")
    else:
        db.session.delete(p)
        db.session.commit()
        flash(_("Вопрос дня убран."), "success")
    return redirect(url_for("teacher.dashboard") + "#daily-h")


@bp.route("/attendance", methods=["POST"])
@teacher_required
def attendance():
    from .models import ATTENDANCE, Attendance
    r = _own_record(request.form.get("record_id", type=int) or 0)
    status = request.form.get("status")
    try:
        day = date.fromisoformat(request.form.get("day") or local_today().isoformat())
    except ValueError:
        abort(400)
    mark = Attendance.query.filter_by(record_id=r.id, day=day).first()
    if status not in ATTENDANCE:
        if mark:
            db.session.delete(mark)
    elif mark:
        mark.status = status
    else:
        db.session.add(Attendance(record_id=r.id, day=day, status=status))
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return {"status": status if status in ATTENDANCE else None}
    target = request.form.get("next") or ""
    return redirect(target if target.startswith("/teacher") else url_for("teacher.dashboard"))


@bp.route("/assignments/<int:assignment_id>/due", methods=["POST"])
@teacher_required
def assignment_due(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a or a.teacher_id != current_user.id:
        abort(404)
    try:
        day = date.fromisoformat(request.form.get("day", ""))
    except ValueError:
        abort(400)
    keep = a.due_at.time() if a.due_at else datetime.strptime("23:59", "%H:%M").time()
    a.due_at = datetime.combine(day, keep)
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return {"due": a.due_at.isoformat()}
    return redirect(url_for("teacher.dashboard"))


# --------------------------------------------------------------------------- students


@bp.route("/students")
@teacher_required
def students():
    sort = request.args.get("sort", "time")
    q = request.args.get("q", "").strip().lower()
    records = _my_records().all()
    if q:
        records = [r for r in records if q in r.name.lower() or q in (r.grade or "").lower()]
    rows = [{"r": r, "progress": record_progress(r)} for r in records]
    keys = {
        "name": lambda x: x["r"].name.lower(),
        "grade": lambda x: x["r"].grade or "",
        "time": lambda x: x["r"].lesson_time or "99:99",
        "progress": lambda x: -x["progress"],
    }
    rows.sort(key=keys.get(sort, keys["time"]))
    return render_template("teacher/students.html", rows=rows, sort=sort, q=q, editing=None)


def _fill_record(r, form):
    errors = []
    name = form.get("name", "").strip()
    if len(name) < 2:
        errors.append(_("Укажите имя ученика."))
    time_ = form.get("lesson_time", "").strip()
    if time_ and not TIME_RE.match(time_):
        errors.append(_("Время урока в формате ЧЧ:ММ, например 16:00."))
    exam = form.get("exam") or None
    if exam and exam not in EXAMS:
        errors.append(_("Неизвестный экзамен."))
    if errors:
        return errors
    r.name = name
    r.grade = form.get("grade", "").strip() or None
    r.lesson_time = time_.zfill(5) if time_ else None
    r.lesson_days = sorted({int(d) for d in form.getlist("lesson_days") if d.isdigit() and 0 <= int(d) <= 6})
    r.exam = exam
    try:
        r.goal_score = int(form.get("goal_score")) if form.get("goal_score") else None
    except ValueError:
        r.goal_score = None
    r.goal_text = form.get("goal_text", "").strip() or None
    if not r.student_user_id:
        try:
            r.manual_progress = max(0, min(100, int(form.get("manual_progress") or 0)))
        except ValueError:
            pass
    r.notes = form.get("notes", "").strip()
    return []


@bp.route("/students/new", methods=["POST"])
@teacher_required
def student_new():
    r = StudentRecord(teacher_id=current_user.id, invite_code=new_invite_code())
    errors = _fill_record(r, request.form)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("teacher.students") + "#add")
    db.session.add(r)
    db.session.commit()
    flash(_("Ученик добавлен. Отправьте ему код %(code)s, чтобы подключить его аккаунт.", code=r.invite_code),
          "success")
    return redirect(url_for("teacher.student_detail", record_id=r.id))


@bp.route("/students/<int:record_id>")
@teacher_required
def student_detail(record_id):
    r = _own_record(record_id)
    data = {}
    if r.student_user_id:
        exam = r.exam or (r.student.profile.exam if r.student.profile else None)
        data["summary"] = progress_summary(r.student_user_id, exam)
        data["topics"] = skill_map(r.student_user_id, exam)
        data["breakdown"] = mistake_breakdown(r.student_user_id, utcnow() - timedelta(days=30))
        data["recent"] = (Attempt.query.filter(Attempt.user_id == r.student_user_id, Attempt.finished_at.isnot(None))
                          .order_by(Attempt.finished_at.desc()).limit(8).all())
    assignments = [(a, homework_state(a, r.student_user_id) if r.student_user_id else "new",
                    latest_attempt(a, r.student_user_id) if r.student_user_id else None)
                   for a in sorted(r.assignments, key=lambda a: a.created_at, reverse=True)]
    join_url = url_for("auth.join", code=r.invite_code, _external=True)
    from .insights import attendance_summary, score_trend
    from .models import Attendance
    from .services import open_mistakes
    if r.student_user_id:
        data["trend"] = score_trend(r.student_user_id)
        data["mistakes"] = open_mistakes(r.student_user_id)[:8]
    att = attendance_summary(r)
    progress = record_progress(r)
    overdue = sum(1 for _a, st, _l in assignments if st == "overdue")
    # Standing = knowledge minus penalties (attendance and discipline are shown apart from knowledge)
    penalty = 3 * att["absent"] + 1 * att["late"] + 2 * overdue
    today_mark = Attendance.query.filter_by(record_id=r.id, day=local_today()).first()
    return render_template("teacher/student_detail.html", r=r, data=data, assignments=assignments,
                           join_url=join_url, progress=progress, att=att, overdue=overdue, penalty=penalty,
                           standing=max(0, progress - penalty), today_mark=today_mark.status if today_mark else None)


@bp.route("/attempts/<int:attempt_id>/written", methods=["GET", "POST"])
@teacher_required
def written_review(attempt_id):
    """Written answers (part 2) of one finished attempt of the teacher's student: photo, student's own mark, criteria."""
    from .services import rescore
    att = db.session.get(Attempt, attempt_id)
    if not att or not att.finished_at:
        abort(404)
    linked = StudentRecord.query.filter_by(teacher_id=current_user.id, student_user_id=att.user_id).first()
    if not linked and not current_user.is_admin:
        abort(404)
    items = att.work_version.items
    rows = [(a, items[a.index]) for a in att.answers
            if a.index < len(items) and items[a.index].get("answer_type") == "written"]
    if request.method == "POST":
        idx = request.form.get("idx", type=int)
        pts = request.form.get("points", type=int)
        for a, item in rows:
            if a.index == idx and pts is not None and 0 <= pts <= int(item.get("weight") or 1):
                a.points, a.points_by = pts, "teacher"
        rescore(att)
        db.session.commit()
        flash(_("Оценка сохранена."), "success")
        return redirect(url_for("teacher.written_review", attempt_id=att.id) + f"#w{idx}")
    return render_template("teacher/written_review.html", att=att, rows=rows, record=linked)


@bp.route("/students/<int:record_id>/edit", methods=["POST"])
@teacher_required
def student_edit(record_id):
    r = _own_record(record_id)
    errors = _fill_record(r, request.form)
    if errors:
        for e in errors:
            flash(e, "error")
    else:
        db.session.commit()
        flash(_("Изменения сохранены."), "success")
    return redirect(url_for("teacher.student_detail", record_id=r.id))


@bp.route("/students/<int:record_id>/code", methods=["POST"])
@teacher_required
def student_new_code(record_id):
    r = _own_record(record_id)
    if r.student_user_id:
        flash(_("Ученик уже подключён — новый код не нужен."), "info")
    else:
        r.invite_code = new_invite_code()
        db.session.commit()
        flash(_("Новый код: %(code)s. Старый больше не работает.", code=r.invite_code), "success")
    return redirect(url_for("teacher.student_detail", record_id=r.id))


@bp.route("/students/<int:record_id>/unlink", methods=["POST"])
@teacher_required
def student_unlink(record_id):
    r = _own_record(record_id)
    r.student_user_id = None
    r.linked_at = None
    r.invite_code = new_invite_code()
    db.session.commit()
    flash(_("Аккаунт отвязан. Строка в таблице сохранена."), "success")
    return redirect(url_for("teacher.student_detail", record_id=r.id))


@bp.route("/students/<int:record_id>/delete", methods=["POST"])
@teacher_required
def student_delete(record_id):
    r = _own_record(record_id)
    db.session.delete(r)
    db.session.commit()
    flash(_("Ученик удалён из таблицы. Его аккаунт и результаты сохранены."), "success")
    return redirect(url_for("teacher.students"))


# --------------------------------------------------------------------------- works (tests, collections, homework)


@bp.route("/works")
@teacher_required
def works():
    status = request.args.get("status", "published")
    kind = request.args.get("kind", "")
    query = Work.query
    if not current_user.is_admin:
        query = query.filter_by(author_id=current_user.id)
    else:
        query = query.filter(Work.kind != "monday") if request.args.get("mine") else query
    if status in ("draft", "pending", "published", "archived"):
        query = query.filter_by(status=status)
    if kind in WORK_KINDS:
        query = query.filter_by(kind=kind)
    items = query.order_by(Work.updated_at.desc()).all()
    counts = {}
    base = Work.query if current_user.is_admin else Work.query.filter_by(author_id=current_user.id)
    for s in ("draft", "pending", "published", "archived"):
        counts[s] = base.filter_by(status=s).count()
    stats = {}
    for w in items:
        vids = [v.id for v in w.versions]
        stats[w.id] = {
            "attempts": Attempt.query.filter(Attempt.work_version_id.in_(vids), Attempt.finished_at.isnot(None)).count()
            if vids else 0,
            "assigned": Assignment.query.filter_by(work_id=w.id).count(),
        }
    view = request.args.get("view", "tree")
    sections, full_works = _works_by_tree(items) if view == "tree" else ([], [])
    return render_template("teacher/works.html", items=items, status=status, kind=kind, counts=counts, stats=stats,
                           view=view, sections=sections, full_works=full_works)


def _work_place(work, questions_by_id):
    """(topic, subtopic) a work belongs to; None for full exam variants."""
    if work.node is not None:
        return work.node.topic_node, work.node.subtopic_node
    if work.category == "full" or work.kind == "monday":
        return None
    subs = {}
    for qid in work.draft_question_ids or []:
        q = questions_by_id.get(qid)
        if q and q.skill and q.skill.subtopic_node:
            subs[q.skill.subtopic_node.id] = subs.get(q.skill.subtopic_node.id, 0) + 1
    if not subs:
        return None
    best = db.session.get(ContentNode, max(subs, key=subs.get))
    return best.topic_node, best


def _works_by_tree(items):
    """Publish page grid: Topic → Subtopic cards holding works and the teacher's question count."""
    ids = {i for w in items for i in (w.draft_question_ids or [])}
    questions_by_id = {q.id: q for q in Question.query.filter(Question.id.in_(ids)).all()} if ids else {}
    my_questions = Question.query.filter(Question.author_id == current_user.id, Question.status != "draft").all()
    qcount = {}
    for q in my_questions:
        sub = q.skill.subtopic_node if q.skill else None
        if sub:
            qcount[sub.id] = qcount.get(sub.id, 0) + 1
    placed, full_works = {}, []
    for w in items:
        place = _work_place(w, questions_by_id)
        if place is None:
            full_works.append(w)
            continue
        topic, sub = place
        key = (topic.id if topic else 0, sub.id if sub else 0)
        placed.setdefault(key, []).append(w)
    sections = []
    for t in content_tree(current_user):
        cards = []
        topic_level = placed.get((t["node"].id, 0), [])
        if topic_level:
            cards.append({"sub": None, "works": topic_level, "questions": 0})
        for s_ in t["subtopics"]:
            works = placed.get((t["node"].id, s_["node"].id), [])
            n = qcount.get(s_["node"].id, 0)
            if works or n:
                cards.append({"sub": s_["node"], "works": works, "questions": n})
        if cards:
            sections.append({"topic": t["node"], "cards": cards})
    return sections, full_works


@bp.route("/works/new", methods=["GET", "POST"])
@teacher_required
def work_new():
    kind = request.args.get("kind", "collection")
    if kind not in WORK_KINDS or (kind == "monday" and not current_user.is_admin):
        kind = "collection"
    work = Work(author_id=current_user.id, kind=kind, category="thematic", exam="ORT", title="",
                time_limit_min=20, status="draft", draft_question_ids=[],
                node_id=request.args.get("node", type=int), format="ort", calculator=False, per_page=4)
    if request.method == "POST":
        return _save_work(work, is_new=True)
    return _render_editor(work)


@bp.route("/works/<int:work_id>/edit", methods=["GET", "POST"])
@teacher_required
def work_edit(work_id):
    work = _own_work(work_id)
    if request.method == "POST":
        return _save_work(work, is_new=False)
    return _render_editor(work)


def _render_editor(work, status_code=200):
    exam = work.exam
    skill_id = None
    questions = []  # the picker loads questions itself (picker.py)
    selected_ids = list(work.draft_question_ids or [])
    selected = [db.session.get(Question, i) for i in selected_ids]
    selected = [q for q in selected if q]
    return render_template("teacher/work_edit.html", work=work, questions=questions, selected=selected,
                           selected_ids=set(selected_ids), tree=content_tree(current_user), filter_exam=exam,
                           filter_skill=skill_id), status_code


def _save_work(work, is_new):
    f = request.form
    work.title = f.get("title", "").strip()
    work.description = f.get("description", "").strip()
    work.exam = f.get("exam") if f.get("exam") in EXAMS else work.exam
    work.category = f.get("category") if f.get("category") in ("full", "thematic") else work.category
    node = db.session.get(ContentNode, f.get("node_id", type=int) or 0)
    work.node = node if _can_see_node(node) and node.level in ("topic", "subtopic") else None
    from .constants import TEST_FORMATS
    work.format = f.get("format") if f.get("format") in TEST_FORMATS else work.format or "plain"
    work.calculator = f.get("calculator") == "1"
    work.module_split = f.get("module_split", type=int) or None
    work.per_page = max(1, min(10, f.get("per_page", type=int) or 4))
    if is_new:
        kind = f.get("kind")
        if kind in WORK_KINDS and (kind != "monday" or current_user.is_admin):
            work.kind = kind
    try:
        work.time_limit_min = max(1, min(300, int(f.get("time_limit_min") or 20)))
    except ValueError:
        pass
    ids = []
    for raw in f.get("question_order", "").split(","):
        if raw.strip().isdigit() and int(raw) not in ids:
            ids.append(int(raw))
    work.draft_question_ids = ids
    if work.kind == "monday":
        try:
            work.week_start = datetime.strptime(f.get("week_start"), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            pass

    action = f.get("action", "save")
    if not work.title:
        flash(_("Укажите название."), "error")
        return _render_editor(work, 400)
    if action == "publish" and not ids:
        flash(_("Добавьте хотя бы один вопрос перед публикацией."), "error")
        return _render_editor(work, 400)

    if is_new:
        db.session.add(work)
    if action == "publish":
        republish = work.current_version is not None
        review = _needs_review(work)
        version = publish_work(work, note=f.get("version_note", "").strip() or None)
        if review:
            work.status = "pending"
            db.session.commit()
            flash(_("Большой тест отправлен администратору. Ученики увидят его после одобрения."), "info")
            return redirect(url_for("teacher.works", status="pending"))
        db.session.commit()
        if republish:
            flash(_("Опубликована версия %(n)s. Старые результаты учеников сохранены.", n=version.number), "success")
        else:
            flash(_("Работа опубликована."), "success")
        return redirect(url_for("teacher.works", status="published"))
    db.session.commit()
    flash(_("Черновик сохранён."), "success")
    return redirect(url_for("teacher.work_edit", work_id=work.id))


@bp.route("/works/<int:work_id>/status", methods=["POST"])
@teacher_required
def work_status(work_id):
    work = _own_work(work_id)
    target = request.form.get("status")
    if target == "archived" and work.status == "published":
        work.status = "archived"
        flash(_("Работа перенесена в архив. Ученики её больше не видят."), "success")
    elif target == "published" and work.status == "archived" and work.current_version:
        work.status = "published"
        flash(_("Работа снова опубликована."), "success")
    db.session.commit()
    return redirect(url_for("teacher.works", status=work.status))


@bp.route("/works/<int:work_id>/duplicate", methods=["POST"])
@teacher_required
def work_duplicate(work_id):
    src = _own_work(work_id)
    copy = Work(author_id=current_user.id, kind=src.kind if src.kind != "monday" else "collection",
                category=src.category, exam=src.exam, title=_("%(t)s (копия)", t=src.title),
                description=src.description, time_limit_min=src.time_limit_min, status="draft",
                draft_question_ids=list(src.draft_question_ids or []), node_id=src.node_id, format=src.format,
                calculator=src.calculator, module_split=src.module_split, per_page=src.per_page)
    db.session.add(copy)
    db.session.commit()
    flash(_("Создана копия-черновик."), "success")
    return redirect(url_for("teacher.work_edit", work_id=copy.id))


@bp.route("/works/<int:work_id>/delete", methods=["POST"])
@teacher_required
def work_delete(work_id):
    work = _own_work(work_id)
    if work.versions:
        flash(_("Опубликованные работы нельзя удалить — перенесите их в архив."), "error")
        return redirect(url_for("teacher.works", status=work.status))
    db.session.delete(work)
    db.session.commit()
    flash(_("Черновик удалён."), "success")
    return redirect(url_for("teacher.works", status="draft"))


# --------------------------------------------------------------------------- assigning & checking homework


@bp.route("/assign", methods=["GET", "POST"])
@teacher_required
def assign():
    works = (Work.query.filter_by(author_id=current_user.id, status="published")
             .filter(Work.kind.in_(["homework", "collection"])).order_by(Work.title).all())
    records = _my_records().order_by(StudentRecord.name).all()
    if request.method == "POST":
        work = db.session.get(Work, request.form.get("work_id", type=int))
        if not work or work.author_id != current_user.id or work.status != "published":
            flash(_("Выберите опубликованную работу."), "error")
            return redirect(url_for("teacher.assign"))
        ids = [int(i) for i in request.form.getlist("record_ids") if i.isdigit()]
        chosen = [r for r in records if r.id in ids]
        if not chosen:
            flash(_("Выберите хотя бы одного ученика."), "error")
            return redirect(url_for("teacher.assign", work_id=work.id))
        due = None
        if request.form.get("due_date"):
            try:
                due = datetime.strptime(f"{request.form['due_date']} {request.form.get('due_time') or '23:59'}",
                                        "%Y-%m-%d %H:%M")
            except ValueError:
                flash(_("Неверная дата сдачи."), "error")
                return redirect(url_for("teacher.assign", work_id=work.id))
        for r in chosen:
            db.session.add(Assignment(work=work, teacher_id=current_user.id, record=r, due_at=due,
                                      message=request.form.get("message", "").strip()))
        db.session.commit()
        not_linked = [r.name for r in chosen if not r.student_user_id]
        flash(_("Задание выдано: %(n)s уч.", n=len(chosen)), "success")
        if not_linked:
            flash(_("Ещё не подключены к Monday: %(names)s. Они увидят задание после ввода кода.",
                    names=", ".join(not_linked)), "info")
        return redirect(url_for("teacher.review"))
    return render_template("teacher/assign.html", works=works, records=records,
                           selected_work=request.args.get("work_id", type=int),
                           selected_record=request.args.get("record_id", type=int),
                           default_due=(local_today() + timedelta(days=3)).isoformat())


@bp.route("/review")
@teacher_required
def review():
    show = request.args.get("show", "submitted")
    rows = []
    for a in (Assignment.query.filter_by(teacher_id=current_user.id)
              .order_by(Assignment.created_at.desc()).all()):
        uid = a.record.student_user_id
        state = homework_state(a, uid) if uid else "new"
        rows.append({"a": a, "state": state, "last": latest_attempt(a, uid) if uid else None})
    counts = {k: sum(1 for r in rows if r["state"] == k) for k in ("submitted", "checked")}
    counts["open"] = sum(1 for r in rows if r["state"] in ("new", "in_progress", "overdue"))
    if show == "open":
        rows = [r for r in rows if r["state"] in ("new", "in_progress", "overdue")]
    else:
        rows = [r for r in rows if r["state"] == show]
    return render_template("teacher/review.html", rows=rows, show=show, counts=counts)


@bp.route("/review/<int:assignment_id>", methods=["GET", "POST"])
@teacher_required
def review_detail(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a or (a.teacher_id != current_user.id and not current_user.is_admin):
        abort(404)
    uid = a.record.student_user_id
    last = latest_attempt(a, uid) if uid else None
    if request.method == "POST":
        if request.form.get("action") == "reopen":
            a.checked_at = None
            flash(_("Задание снова открыто для проверки."), "success")
        else:
            a.teacher_comment = request.form.get("teacher_comment", "").strip()
            a.checked_at = utcnow()
            flash(_("Проверено. Ученик увидит ваш комментарий."), "success")
        db.session.commit()
        return redirect(url_for("teacher.review_detail", assignment_id=a.id))
    rows = []
    if last:
        items = last.work_version.items
        rows = [{"item": items[ans.index] if ans.index < len(items) else None, "answer": ans} for ans in last.answers]
    return render_template("teacher/review_detail.html", a=a, last=last, rows=rows,
                           state=homework_state(a, uid) if uid else "new")


# --------------------------------------------------------------------------- abilities map (content tree)


@bp.route("/tree")
@teacher_required
def tree():
    show_archived = request.args.get("archived") == "1" and current_user.is_admin
    nodes = visible_nodes(current_user, include_archived=show_archived)
    counts = {}
    for q in Question.query.filter(Question.status == "published").all():
        counts[q.skill_id] = counts.get(q.skill_id, 0) + 1
    mine = {}
    for q in Question.query.filter_by(author_id=current_user.id).all():
        mine[q.skill_id] = mine.get(q.skill_id, 0) + 1
    by_parent = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)
    return render_template("teacher/tree.html", by_parent=by_parent, counts=counts, mine=mine,
                           can_edit=_can_edit_node, show_archived=show_archived)


@bp.route("/tree/add", methods=["POST"])
@teacher_required
def tree_add():
    level = request.form.get("level")
    name = request.form.get("name", "").strip()
    parent = db.session.get(ContentNode, request.form.get("parent_id", type=int) or 0)
    expected_parent = {"topic": None, "subtopic": "topic", "node": "subtopic"}
    if level not in expected_parent or len(name) < 2:
        flash(_("Введите название (минимум 2 символа)."), "error")
        return redirect(url_for("teacher.tree"))
    if expected_parent[level] is None:
        parent = None
    elif not _can_see_node(parent) or parent.level != expected_parent[level]:
        flash(_("Неверное место в дереве."), "error")
        return redirect(url_for("teacher.tree"))
    exams = [e for e in request.form.getlist("exams") if e in EXAMS] or (list(parent.exams or []) if parent else list(EXAMS))
    node = _new_node(level, name, parent, exams)
    db.session.commit()
    flash(_("Добавлено: %(name)s.", name=node.name) + ("" if current_user.is_admin else " " + _("Видно вам и вашим ученикам.")),
          "success")
    return redirect(url_for("teacher.tree", _anchor=f"n{node.parent_id or node.id}"))


@bp.route("/tree/<int:node_id>/edit", methods=["POST"])
@teacher_required
def tree_edit(node_id):
    node = db.session.get(ContentNode, node_id)
    if not _can_edit_node(node):
        abort(403)
    action = request.form.get("action", "rename")
    if action == "archive":
        node.archived = True
        flash(_("«%(name)s» перенесено в архив. Результаты учеников сохранены.", name=node.name), "success")
    elif action == "restore":
        node.archived = False
        flash(_("Восстановлено."), "success")
    else:
        name = request.form.get("name", "").strip()
        if len(name) >= 2:
            node.name = name[:160]
        if node.level == "node":
            try:
                node.weight = max(1, min(5, int(request.form.get("weight", node.weight or 1))))
            except ValueError:
                pass
        exams = [e for e in request.form.getlist("exams") if e in EXAMS]
        if exams:
            node.exams = exams
        flash(_("Сохранено."), "success")
    db.session.commit()
    return redirect(url_for("teacher.tree", _anchor=f"n{node.parent_id or node.id}"))


# --------------------------------------------------------------------------- question bank


@bp.route("/questions")
@teacher_required
def questions():
    mine = request.args.get("mine", "1") == "1"
    exam = request.args.get("exam", "")
    node_id = request.args.get("node", type=int) or request.args.get("skill", type=int)
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip().lower()
    query = Question.query
    if mine:
        query = query.filter_by(author_id=current_user.id)
    else:
        query = query.filter(Question.status == "published")
    if status:
        query = query.filter_by(status=status)
    items = query.order_by(Question.updated_at.desc()).all()
    if node_id:
        items = [x for x in items if _in_branch(x.skill, node_id)]
    if exam:
        items = [x for x in items if exam in (x.exams or [])]
    if q:
        items = [x for x in items if q in (x.text or "").lower()
                 or any(q in (b.get("text") or "").lower() for b in (x.material or []))]
    return render_template("teacher/questions.html", items=items, mine=mine, exam=exam, node_id=node_id,
                           status=status, q=q, tree=content_tree(current_user))


# --------------------------------------------------------------------------- question bank (pick questions into works)



@bp.route("/bank")
@teacher_required
def bank():
    """The picker page: find questions, collect them in a basket, send to a work or to the questions of the day."""
    exam = request.args.get("exam") if request.args.get("exam") in EXAMS else "ORT"
    works = (Work.query.filter(Work.author_id == current_user.id, Work.status != "archived")
             .order_by(Work.updated_at.desc()).all())
    return render_template("teacher/bank.html", exam=exam, works=works)


@bp.route("/bank/add", methods=["POST"])
@teacher_required
def bank_add():
    ids = [int(x) for x in request.form.getlist("qid") if x.isdigit()]
    allowed = {x.id for x in Question.query.filter(Question.id.in_(ids)).all()
               if x.status == "published" or x.author_id == current_user.id} if ids else set()
    ids = [i for i in dict.fromkeys(ids) if i in allowed]   # keep the order the teacher picked
    if not ids:
        flash(_("Отметьте хотя бы один вопрос."), "error")
        return redirect(request.referrer or url_for("teacher.bank"))
    target = request.form.get("work")
    if target in ("daily-today", "daily-tomorrow"):
        from .daily import add_picks
        day = local_today() + timedelta(days=1 if target == "daily-tomorrow" else 0)
        exam = request.form.get("exam") if request.form.get("exam") in EXAMS else None
        added, skipped = add_picks(current_user, ids, day, exam)
        if added:
            flash(_("Вопросов дня на %(d)s: добавлено %(n)s.", d=day.strftime("%d.%m"), n=added), "success")
        if skipped:
            flash(_("Не добавлено %(n)s: в день не больше 3 вопросов, повторы пропускаются.", n=skipped), "info")
        return redirect(url_for("teacher.dashboard") + "#daily-h")
    if target == "new":
        kind = request.form.get("kind") if request.form.get("kind") in ("collection", "homework") else "homework"
        exam = request.form.get("exam") if request.form.get("exam") in EXAMS else "ORT"
        from .constants import FORMAT_FOR_EXAM, TEST_FORMATS
        fmt = FORMAT_FOR_EXAM.get(exam, "plain")
        work = Work(author_id=current_user.id, kind=kind, category="thematic", exam=exam,
                    title=_("Новая работа · %(n)s вопр.", n=len(ids)), time_limit_min=max(10, 2 * len(ids)),
                    status="draft", draft_question_ids=ids, format=fmt,
                    calculator=TEST_FORMATS[fmt]["calculator"], per_page=4)
        db.session.add(work)
        db.session.commit()
        flash(_("Создана работа из %(n)s вопросов — задайте название и опубликуйте.", n=len(ids)), "success")
        return redirect(url_for("teacher.work_edit", work_id=work.id))
    work = _own_work(int(target) if (target or "").isdigit() else 0)
    have = list(work.draft_question_ids or [])
    added = [i for i in ids if i not in have]
    work.draft_question_ids = have + added
    db.session.commit()
    flash(_("Добавлено в «%(t)s»: %(n)s. Уже были: %(k)s.", t=work.title or _("без названия"), n=len(added),
            k=len(ids) - len(added)), "success")
    return redirect(url_for("teacher.work_edit", work_id=work.id))


def _in_branch(node, branch_id):
    while node is not None:
        if node.id == branch_id:
            return True
        node = node.parent
    return False


def _allowed_image(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]


WORD_RE = re.compile(r"\S+")
_MATERIAL_KEY = re.compile(r"^m(\d+)_type$")


def _parse_material(form):
    """Material blocks in the order they appear in the form: m<i>_type, m<i>_title, m<i>_text, ..."""
    blocks = []
    for key in form.keys():
        m = _MATERIAL_KEY.match(key)
        if not m:
            continue
        i, kind = m.group(1), form.get(key)
        get = lambda f: form.get(f"m{i}_{f}", "").strip()  # noqa: E731
        if kind == "heading" and get("text"):
            blocks.append({"type": "heading", "text": get("text")[:200]})
        elif kind == "passage" and get("text"):
            blocks.append({"type": "passage", "title": get("title")[:160], "text": get("text")[:6000]})
        elif kind == "columns" and (get("left") or get("right")):
            blocks.append({"type": "columns", "left_title": get("left_title")[:60] or _("Колонка А"),
                           "left": get("left")[:1000], "right_title": get("right_title")[:60] or _("Колонка Б"),
                           "right": get("right")[:1000]})
    return blocks


def _fill_question(qn, form, files):
    errors = []
    qn.text = form.get("text", "").strip()
    words = len(WORD_RE.findall(qn.text))
    if words > QUESTION_WORD_LIMIT:
        errors.append(_("Текст вопроса — до %(n)s слов (сейчас %(w)s). Длинный текст вынесите в блок «Текст для чтения».",
                        n=QUESTION_WORD_LIMIT, w=words))
    qn.explanation = form.get("explanation", "").strip()
    qn.video_url = form.get("video_url", "").strip() or None
    if qn.video_url and not qn.video_url.startswith(("https://", "http://")):
        errors.append(_("Ссылка на видео должна начинаться с https://"))
    qn.language = form.get("language", "ru") if form.get("language") in current_app.config["LANGUAGES"] else "ru"
    qn.exams = [e for e in form.getlist("exams") if e in EXAMS]
    if not qn.exams:
        errors.append(_("Отметьте хотя бы один экзамен."))
    node, err = _resolve_node(form, qn.exams)
    if err:
        errors.append(err)
    qn.skill = node
    try:
        qn.difficulty = max(1, min(3, int(form.get("difficulty", 2))))
    except ValueError:
        qn.difficulty = 2
    try:
        qn.weight = max(1, min(10, int(form.get("weight", 1))))
    except ValueError:
        qn.weight = 1
    qn.material = _parse_material(form)

    qn.answer_type = "number" if form.get("answer_type") == "number" else "choice"
    if qn.answer_type == "choice":
        raw = [form.get(f"option{i}", "").strip() for i in range(6)]
        correct = form.get("correct_option", "")
        # drop empty options but keep the "correct" mark on the right one
        kept = [(i, o) for i, o in enumerate(raw) if o]
        qn.options = [o for _i, o in kept]
        index_map = {i: n for n, (i, _o) in enumerate(kept)}
        if len(kept) < 2:
            errors.append(_("Нужно минимум два варианта ответа."))
        if not correct.isdigit() or int(correct) not in index_map:
            errors.append(_("Отметьте верный вариант."))
            qn.correct = correct or "0"
        else:
            qn.correct = str(index_map[int(correct)])
        qn.precision = None
    else:
        qn.options = []
        val = form.get("correct_number", "").strip()
        parts = []
        for part in [p.strip() for p in val.split("|") if p.strip()] or [""]:
            value, fmt = parse_number(part)
            if value is None:
                errors.append(_("Верный ответ должен быть числом: целым, дробью (3/4) или десятичным (0,75)."))
                break
            parts.append(part.replace(",", ".") if fmt == "decimal" else part)
        qn.correct = "|".join(parts) if parts else val
        qn.input_formats = [f for f in form.getlist("input_formats") if f in INPUT_FORMATS] or list(INPUT_FORMATS)
        precision = form.get("precision", "")
        qn.precision = int(precision) if precision in ("1", "2") else None

    upload = files.get("image")
    if upload and upload.filename:
        if not _allowed_image(upload.filename):
            errors.append(_("Изображение: только PNG, JPG или WEBP."))
        else:
            ext = secure_filename(upload.filename).rsplit(".", 1)[-1].lower()
            name = f"q-{uuid.uuid4().hex[:12]}.{ext}"
            upload.save(os.path.join(current_app.config["UPLOAD_FOLDER"], name))
            qn.image_path = name
    if form.get("remove_image") == "1":
        qn.image_path = None
    if not qn.text and not qn.image_path:
        errors.append(_("Добавьте текст вопроса или изображение."))
    from .taxonomy import TAGS, auto_tags
    if form.get("tags_set"):
        qn.tags = [t for t in form.getlist("tags") if t in TAGS]
    else:
        qn.tags = auto_tags(qn)
    return errors


def _render_question(qn, status_code=200):
    return render_template("teacher/question_edit.html", qn=qn, tree=_tree_json(),
                           word_limit=QUESTION_WORD_LIMIT), status_code


def _question_status_for_author():
    """Teachers' questions go straight to the bank; assistants' wait for an admin or a methodist."""
    return "pending" if current_user.is_assistant else "published"


def _needs_review(work):
    from .constants import BIG_TEST_QUESTIONS
    return (not current_user.is_admin and work.kind == "collection"
            and len(work.draft_question_ids or []) >= BIG_TEST_QUESTIONS and work.status != "published")


@bp.route("/questions/new", methods=["GET", "POST"])
@staff_required
def question_new():
    qn = Question(author_id=current_user.id, exams=["ORT"], difficulty=2, answer_type="choice", weight=1,
                  options=["", "", "", ""], correct="0", language="ru", material=[],
                  input_formats=list(INPUT_FORMATS), skill_id=request.args.get("node", type=int))
    if request.method == "POST":
        errors = _fill_question(qn, request.form, request.files)
        if errors:
            for e in errors:
                flash(e, "error")
            db.session.rollback()
            return _render_question(qn, 400)
        qn.status = "draft" if request.form.get("action") == "draft" else _question_status_for_author()
        db.session.add(qn)
        db.session.commit()
        if qn.status == "pending":
            flash(_("Вопрос отправлен на проверку методисту. После одобрения он появится в банке."), "success")
        elif qn.status == "published":
            flash(_("Вопрос опубликован в банке."), "success")
        else:
            flash(_("Черновик сохранён."), "success")
        if request.form.get("then") == "another":
            return redirect(url_for("teacher.question_new"))
        return _after_question_save()
    return _render_question(qn)


@bp.route("/questions/<int:question_id>/edit", methods=["GET", "POST"])
@staff_required
def question_edit(question_id):
    qn = _own_question(question_id)
    if request.method == "POST":
        errors = _fill_question(qn, request.form, request.files)
        if errors:
            for e in errors:
                flash(e, "error")
            db.session.rollback()
            return _render_question(qn, 400)
        if request.form.get("action") == "draft":
            qn.status = "draft"
        elif qn.status != "published":
            qn.status = _question_status_for_author()
        if qn.author_id != current_user.id and qn.status == "published" and current_user.can_review:
            qn.reviewed_by_id, qn.reviewed_at, qn.review_note = current_user.id, utcnow(), None  # edited = approved
        db.session.commit()
        flash(_("Вопрос сохранён. Уже опубликованные работы не меняются — переопубликуйте их, чтобы включить правку."),
              "success")
        return _after_question_save()
    return _render_question(qn)


@bp.route("/questions/<int:question_id>/delete", methods=["POST"])
@staff_required
def question_delete(question_id):
    qn = _own_question(question_id)
    used = AttemptAnswer.query.filter_by(question_id=qn.id).first()
    if used:
        qn.status = "draft"
        flash(_("На вопрос уже отвечали ученики, поэтому он скрыт (перенесён в черновики), а не удалён."), "info")
    else:
        db.session.delete(qn)
        flash(_("Вопрос удалён."), "success")
    db.session.commit()
    return _after_question_save()


# --------------------------------------------------------------------------- account


@bp.route("/account", methods=["GET", "POST"])
@staff_required
def account():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "profile":
            name = request.form.get("name", "").strip()
            if len(name) >= 2:
                current_user.name = name
            lang = request.form.get("language")
            if lang in current_app.config["LANGUAGES"]:
                current_user.language = lang
            db.session.commit()
            flash(_("Сохранено."), "success")
        elif action == "password":
            if not current_user.check_password(request.form.get("current", "")):
                flash(_("Текущий пароль неверный."), "error")
            elif len(request.form.get("new", "")) < 8:
                flash(_("Новый пароль должен быть не короче 8 символов."), "error")
            else:
                current_user.set_password(request.form["new"])
                db.session.commit()
                flash(_("Пароль изменён."), "success")
        return redirect(url_for("teacher.account"))
    stats = {
        "students": _my_records().count(),
        "linked": _my_records().filter(StudentRecord.student_user_id.isnot(None)).count(),
        "questions": Question.query.filter_by(author_id=current_user.id, status="published").count(),
        "works": Work.query.filter_by(author_id=current_user.id, status="published").count(),
    }
    return render_template("teacher/account.html", stats=stats, threshold=TRUSTED_TEACHER_THRESHOLD)

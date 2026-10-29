"""Admin: overview, teacher applications, question moderation, people (students, teachers, admins)."""
from collections import Counter, defaultdict
from datetime import timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user
from sqlalchemy import func

from .access import admin_required
from .constants import EXAMS
from .extensions import db
from .models import (Attempt, ContentNode, Question, StudentProfile, StudentRecord, User, Work, utcnow)
from .services import content_gaps, progress_summary

bp = Blueprint("admin", __name__, url_prefix="/admin")

TABS = ("overview", "apps", "moderation", "students", "teachers", "assistants", "admins")
PEOPLE = {"students": "student", "teachers": "teacher", "assistants": "assistant", "admins": "admin"}
PER_PAGE = 25
THIN = 3  # a skill with fewer published questions than this needs content


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
    signups = Counter(u.created_at.date() for u in User.query.filter(User.created_at >= now - timedelta(days=days)).all()
                      if u.created_at)
    series = [{"day": start + timedelta(days=i), "n": signups.get(start + timedelta(days=i), 0)} for i in range(days)]
    peak = max([d["n"] for d in series] + [1])
    week = now - timedelta(days=7)
    active_ids = {u for (u,) in db.session.query(Attempt.user_id).filter(Attempt.started_at >= week).distinct()}
    active_ids |= {u.id for u in User.query.filter(User.last_seen_at >= week).all()}
    tests_week = Attempt.query.filter(Attempt.finished_at >= week, Attempt.work_version_id.isnot(None)).count()
    tests_month = Attempt.query.filter(Attempt.finished_at >= now - timedelta(days=30),
                                       Attempt.work_version_id.isnot(None)).count()
    answers_week = sum(len(a.answers) for a in Attempt.query.filter(Attempt.started_at >= week).all())

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
    users = User.query.filter_by(role=role).order_by(User.created_at.desc()).all()
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
    counts = {r: User.query.filter_by(role=r).count() for r in ("student", "teacher", "assistant", "admin")}
    pending_questions = Question.query.filter_by(status="pending").count()
    ctx = {"tab": tab, "pending_teachers": pending_teachers, "pending_works": pending_works, "counts": counts,
           "pending_questions": pending_questions,
           "args": request.args, "teachers_all": User.query.filter_by(role="teacher").order_by(User.name).all()}

    if tab == "overview":
        ctx["ov"] = _overview()
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
            extra = {i: _assistant_stats(i) for i in ids}
        elif role == "student":
            links = defaultdict(list)
            for r in StudentRecord.query.filter(StudentRecord.student_user_id.in_(ids)).all() if ids else []:
                links[r.student_user_id].append(r.teacher.name)
            extra = {i: {"teachers": links.get(i, [])} for i in ids}
        ctx.update(users=shown, total=len(users), page=page, pages=pages, extra=extra,
                   last={u.id: max([d for d in (u.last_seen_at, last.get(u.id)) if d] or [None]) for u in shown})
    user_id = request.args.get("user", type=int)
    if user_id:
        ctx["panel"] = _panel(user_id)
    if request.args.get("fragment") and user_id:
        return render_template("admin/_panel_body.html", **ctx)
    return render_template("admin/index.html", **ctx)


def _assistant_stats(user_id):
    qs = Question.query.filter_by(author_id=user_id).all()
    week = utcnow() - timedelta(days=7)
    reviewed = [q for q in qs if q.reviewed_at]
    approved = [q for q in reviewed if q.status == "published"]
    topics = Counter(q.skill.topic for q in qs if q.skill).most_common(3)
    return {"total": len(qs), "week": sum(1 for q in qs if q.created_at and q.created_at >= week),
            "pending": sum(1 for q in qs if q.status == "pending"),
            "approved_pct": round(100 * len(approved) / len(reviewed)) if reviewed else None, "topics": topics}


def _panel(user_id):
    u = db.session.get(User, user_id) or abort(404)
    data = {"user": u, "role": u.role}
    attempts = (Attempt.query.filter_by(user_id=u.id).filter(Attempt.finished_at.isnot(None))
                .order_by(Attempt.finished_at.desc()).limit(6).all())
    data["attempts"] = attempts
    last_attempt = Attempt.query.filter_by(user_id=u.id).order_by(Attempt.started_at.desc()).first()
    data["last"] = max([d for d in (u.last_seen_at, last_attempt.started_at if last_attempt else None) if d] or [None])
    if u.role == "student":
        data["teachers"] = [r.teacher for r in StudentRecord.query.filter_by(student_user_id=u.id).all()]
        exam = u.profile.exam if u.profile else None
        data["summary"] = progress_summary(u.id, exam) if exam else None
    elif u.role == "assistant":
        data["astats"] = _assistant_stats(u.id)
    elif u.role == "teacher":
        records = StudentRecord.query.filter_by(teacher_id=u.id).order_by(StudentRecord.name).all()
        data["records"] = records
        data["works"] = Work.query.filter_by(author_id=u.id).count()
        data["questions"] = Question.query.filter_by(author_id=u.id).count()
    return data


def _back():
    target = request.form.get("next") or ""
    return redirect(target if target.startswith("/admin") else url_for("admin.index"))


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
    elif role in ("student", "teacher", "assistant", "admin"):
        u.role = role
        u.is_approved = True
        if role == "student" and not u.profile:
            u.profile = StudentProfile()
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


@bp.route("/users/<int:user_id>/block", methods=["POST"])
@admin_required
def block(user_id):
    u = db.session.get(User, user_id) or abort(404)
    if u.id == current_user.id:
        flash(_("Нельзя заблокировать себя."), "error")
        return _back()
    u.is_blocked = request.form.get("on") == "1"
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

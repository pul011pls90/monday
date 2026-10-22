"""Error reports: anyone flags a question (or a map entry), staff fix it and reply.

Students press «Сообщить об ошибке» under a question. The report reaches
- the question's author,
- the student's own teachers,
- admins (they can edit every question, including the compilations).
The reply is shown to the student on the home page until they dismiss it.
"""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required
from sqlalchemy import or_

from .access import teacher_required
from .constants import REPORT_KINDS
from .extensions import db
from .models import ContentNode, Question, Report, StudentRecord, utcnow

bp = Blueprint("reports", __name__)


def visible_reports(user):
    """Reports this staff member handles."""
    q = Report.query
    if user.is_admin:
        return q
    students = [r.student_user_id for r in StudentRecord.query.filter_by(teacher_id=user.id).all() if r.student_user_id]
    own_q = db.session.query(Question.id).filter(Question.author_id == user.id)
    own_n = db.session.query(ContentNode.id).filter(ContentNode.owner_id == user.id)
    return q.filter(or_(Report.author_id.in_(students or [-1]), Report.question_id.in_(own_q), Report.node_id.in_(own_n)))


def open_count(user):
    if not user.is_authenticated or not user.is_teacher:
        return 0
    return visible_reports(user).filter(Report.status == "open").count()


def can_edit_question(user, q):
    return q is not None and (user.is_admin or q.author_id == user.id)


@bp.route("/report", methods=["POST"])
@login_required
def create():
    qid = request.form.get("question_id", type=int)
    nid = request.form.get("node_id", type=int)
    kind = request.form.get("kind") if request.form.get("kind") in REPORT_KINDS else "other"
    message = (request.form.get("message") or "").strip()[:2000]
    question = db.session.get(Question, qid) if qid else None
    node = db.session.get(ContentNode, nid) if nid else None
    wants_json = request.headers.get("X-Requested-With") == "fetch"
    if not question and not node:
        abort(400)
    if kind == "other" and not message:
        msg = _("Опишите, что не так.")
        if wants_json:
            return jsonify(ok=False, message=msg), 400
        flash(msg, "error")
        return redirect(request.referrer or url_for("auth.index"))
    dup = Report.query.filter_by(author_id=current_user.id, question_id=qid, node_id=nid, status="open").first()
    if dup:
        dup.kind, dup.message = kind, message or dup.message
    else:
        db.session.add(Report(author_id=current_user.id, question_id=question.id if question else None,
                              node_id=node.id if node else None, kind=kind if question else "node", message=message))
    db.session.commit()
    msg = _("Спасибо! Учитель посмотрит и исправит.")
    if wants_json:
        return jsonify(ok=True, message=msg)
    flash(msg, "success")
    return redirect(request.referrer or url_for("auth.index"))


@bp.route("/report/<int:report_id>/seen", methods=["POST"])
@login_required
def seen(report_id):
    r = db.session.get(Report, report_id)
    if not r or r.author_id != current_user.id:
        abort(404)
    r.seen = True
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True)
    return redirect(request.referrer or url_for("auth.index"))


@bp.route("/teacher/reports")
@teacher_required
def inbox():
    tab = request.args.get("tab", "open")
    q = visible_reports(current_user)
    q = q.filter(Report.status == "open") if tab == "open" else q.filter(Report.status != "open")
    items = q.order_by(Report.created_at.desc()).limit(200).all()
    counts = {"open": visible_reports(current_user).filter(Report.status == "open").count(),
              "done": visible_reports(current_user).filter(Report.status != "open").count()}
    return render_template("teacher/reports.html", items=items, tab=tab, counts=counts,
                           can_edit=lambda x: can_edit_question(current_user, x))


@bp.route("/teacher/reports/<int:report_id>", methods=["POST"])
@teacher_required
def handle(report_id):
    r = visible_reports(current_user).filter(Report.id == report_id).first()
    if not r:
        abort(404)
    action = request.form.get("action")
    if action in ("fixed", "rejected"):
        r.status, r.handled_by_id, r.handled_at = action, current_user.id, utcnow()
        r.reply = (request.form.get("reply") or "").strip()[:2000] or None
        r.seen = False
        # every other open report on the same question is answered with it
        if r.question_id:
            for other in Report.query.filter(Report.question_id == r.question_id, Report.status == "open", Report.id != r.id):
                other.status, other.handled_by_id, other.handled_at, other.reply = action, current_user.id, utcnow(), r.reply
        flash(_("Ответ отправлен ученику.") if action == "fixed" else _("Сообщение отклонено, ученик увидит ответ."), "success")
    elif action == "reopen":
        r.status, r.handled_at = "open", None
    db.session.commit()
    return redirect(url_for("reports.inbox", tab=request.form.get("tab", "open")))

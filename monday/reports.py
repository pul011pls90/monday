"""Error reports: anyone flags a question (or a map entry), staff fix it and reply.

Students press «Сообщить об ошибке» under a question. The report reaches
- the question's author,
- the student's own teachers,
- admins (they can edit every question, including the compilations).
The reply is shown to the student on the home page until they dismiss it.
"""
from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload, selectinload

from . import storage
from .access import admin_required, teacher_required
from .constants import REPORT_KINDS
from .extensions import db
from .models import ContentNode, Question, Report, StudentRecord, SupportAttachment, User, utcnow

bp = Blueprint("reports", __name__)

ROLE_META = (
    ("student", "Ученик", "rp-role--student"),
    ("teacher", "Учитель", "rp-role--teacher"),
    ("assistant", "Ассистент", "rp-role--assistant"),
    ("sales_manager", "Менеджер", "rp-role--manager"),
    ("supervisor", "Супервайзер", "rp-role--supervisor"),
    ("admin", "Админ", "rp-role--admin"),
)
ROLE_LABELS = {code: label for code, label, _cls in ROLE_META}
ROLE_CLASSES = {code: cls for code, _label, cls in ROLE_META}

_ADMIN_USER_TABS = {
    "sales_manager": "managers",
    "supervisor": "supervisors",
    "assistant": "assistants",
    "admin": "admins",
}


def visible_reports(user):
    """Reports this staff member handles."""
    q = Report.query
    if user.is_admin:
        return q
    from .student_links import teacher_open_records_query
    students = [r.student_user_id for r in teacher_open_records_query(user.id).all() if r.student_user_id]
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
        db.session.add(Report(author_id=current_user.id, sender_role=current_user.role,
                              question_id=question.id if question else None,
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


def _sender_profile_urls(viewer, items):
    """Resolve authorized profile/record links for senders shown in reports.inbox."""
    teacher_records = {}
    if viewer.is_teacher and not viewer.is_admin:
        from .student_links import teacher_open_records_query
        for rec in teacher_open_records_query(viewer.id).all():
            if rec.student_user_id and rec.student_user_id not in teacher_records:
                teacher_records[rec.student_user_id] = rec.id

    urls = {}
    for r in items:
        author = r.author
        if not author or (author.is_blocked and "@deleted.monday" in (author.email or "")):
            urls[r.id] = None
            continue
        if viewer.is_admin:
            if author.role == "student":
                urls[r.id] = url_for("manager.student_detail", student_id=author.id)
            elif author.role == "teacher":
                urls[r.id] = url_for("manager.teacher_detail", teacher_id=author.id)
            elif author.role in _ADMIN_USER_TABS:
                urls[r.id] = url_for("admin.index", tab=_ADMIN_USER_TABS[author.role], q=author.email)
            else:
                urls[r.id] = None
        elif viewer.is_teacher and author.role == "student" and author.id in teacher_records:
            urls[r.id] = url_for("teacher.student_detail", record_id=teacher_records[author.id])
        else:
            urls[r.id] = None
    return urls


@bp.route("/teacher/reports")
@teacher_required
def inbox():
    tab = request.args.get("tab", "open")
    role_filter = (request.args.get("role") or "").strip()
    if role_filter not in ROLE_LABELS:
        role_filter = ""

    base_q = visible_reports(current_user)
    status_q = base_q.filter(Report.status == "open") if tab == "open" else base_q.filter(Report.status != "open")

    # Per-role open/unread counts + active-tab counts
    open_by_role = dict(
        base_q.filter(Report.status == "open")
        .with_entities(Report.sender_role, func.count(Report.id))
        .group_by(Report.sender_role)
        .all()
    )
    tab_by_role = dict(
        status_q.with_entities(Report.sender_role, func.count(Report.id))
        .group_by(Report.sender_role)
        .all()
    )

    if role_filter:
        status_q = status_q.filter(Report.sender_role == role_filter)

    items = (
        status_q.options(
            joinedload(Report.author).joinedload(User.profile),
            joinedload(Report.handled_by),
            joinedload(Report.question).joinedload(Question.skill),
            joinedload(Report.node),
            selectinload(Report.attachments),
        )
        .order_by(Report.created_at.desc(), Report.id.desc())
        .limit(200)
        .all()
    )
    counts = {
        "open": base_q.filter(Report.status == "open").count(),
        "done": base_q.filter(Report.status != "open").count(),
    }
    sender_urls = _sender_profile_urls(current_user, items)
    return render_template(
        "teacher/reports.html",
        items=items,
        tab=tab,
        role_filter=role_filter,
        role_meta=ROLE_META,
        role_labels=ROLE_LABELS,
        role_classes=ROLE_CLASSES,
        open_by_role=open_by_role,
        tab_by_role=tab_by_role,
        sender_urls=sender_urls,
        counts=counts,
        can_edit=lambda x: can_edit_question(current_user, x),
    )


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


@bp.route("/support/attachments/<int:attachment_id>")
def attachment_view(attachment_id):
    """Serve compressed WebP support image/thumbnail strictly to the sender, allowed teacher, or admin."""
    if not current_user.is_authenticated:
        abort(401)
    if current_user.is_blocked:
        abort(403)
    att = db.session.get(SupportAttachment, attachment_id)
    if not att or att.deleted_at is not None:
        abort(404)
    report = att.message
    if not report:
        abort(404)
    allowed = (
        current_user.is_admin
        or report.author_id == current_user.id
        or (current_user.is_teacher and visible_reports(current_user).filter(Report.id == report.id).first() is not None)
    )
    if not allowed:
        abort(403)

    is_thumb = request.args.get("size") == "thumb"
    obj_name = att.thumb_object_name() if is_thumb else att.full_object_name()
    data = storage.read_bytes(obj_name)
    if data is None and is_thumb:
        data = storage.read_bytes(att.full_object_name())
    if data is None:
        abort(404)

    resp = Response(data, status=200, mimetype="image/webp")
    resp.headers["Content-Type"] = "image/webp"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


@bp.route("/admin/support/attachments/<int:attachment_id>/delete", methods=["POST"])
@admin_required
def attachment_delete(attachment_id):
    """Admin-only single-attachment deletion with storage cleanup and AuditLog entry."""
    att = db.session.get(SupportAttachment, attachment_id)
    if not att:
        abort(404)
    from .support_images import soft_delete_support_attachment

    changed = soft_delete_support_attachment(att, actor_id=current_user.id)
    if changed:
        db.session.commit()
    flash(_("Изображение удалено."), "success")
    return redirect(
        url_for(
            "reports.inbox",
            tab=request.form.get("tab") or "open",
            role=(request.form.get("role") or "").strip() or None,
        )
    )

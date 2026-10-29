"""Assistants (they load questions into the bank) and the review queue for admins and methodists.

/assistant/            Загрузка: paste a test (text or JSON) → preview → send (teachers can use it too)
/assistant/mine        Мои вопросы: черновики, на проверке, вернули с комментарием, опубликованы
/assistant/gaps        Где мало вопросов: skills that need content, with a «add a question here» link
/assistant/fixes       Исправления: students' error reports — the assistant proposes a corrected copy, a reviewer
                       approves it and the original question takes the fix (same id, so results stay linked)
/review/questions      queue for admins and methodists: approve, edit, send back with a note
"""
import os
import uuid
from collections import Counter
from datetime import timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user
from werkzeug.utils import secure_filename

from .access import reviewer_required, staff_required
from .constants import EXAMS
from .extensions import db
from .importer import find_duplicates, guess_skill, parse, problems
from .constants import REPORT_KINDS
from .models import INPUT_FORMATS, ContentNode, Question, Report, User, utcnow
from .services import content_gaps, content_tree, valid_number_answer

bp = Blueprint("assistant", __name__, url_prefix="/assistant")
review_bp = Blueprint("review", __name__, url_prefix="/review")

MAX_IMPORT = 80
THIN = 3  # same threshold as the admin overview: a skill with fewer published questions needs content
CYR = "АБВГДЕЖЗ"


def _leaves():
    out = []
    for t in content_tree(current_user):
        for s in t["subtopics"]:
            for n in s["nodes"]:
                out.append((n, f"{t['node'].name} → {s['node'].name} → {n.name}"))
    return out


def _status_for_new():
    return "pending" if current_user.is_assistant else "published"


# --------------------------------------------------------------------------- upload


@bp.route("/", methods=["GET"])
@staff_required
def home():
    mine = Question.query.filter_by(author_id=current_user.id)
    week = utcnow() - timedelta(days=7)
    stats = {
        "week": mine.filter(Question.created_at >= week).count(),
        "pending": mine.filter_by(status="pending").count(),
        "returned": mine.filter(Question.status == "draft", Question.review_note.isnot(None)).count(),
        "published": mine.filter_by(status="published").count(),
    }
    # how reviews went: share approved, and the latest comments on returned questions
    reviewed = mine.filter(Question.reviewed_at.isnot(None))
    approved = reviewed.filter(Question.status == "published").count()
    stats["approved_pct"] = round(100 * approved / reviewed.count()) if reviewed.count() else None
    notes = (mine.filter(Question.review_note.isnot(None)).order_by(Question.reviewed_at.desc()).limit(5).all())
    stats["fixes"] = Report.query.filter(Report.status == "open", Report.question_id.isnot(None)).count()
    stats["gaps"] = len(content_gaps(THIN))
    return render_template("assistant/home.html", stats=stats, notes=notes)


@bp.route("/import", methods=["POST"])
@staff_required
def import_preview():
    raw = request.form.get("raw", "")
    exams = [e for e in request.form.getlist("exams") if e in EXAMS]
    items = parse(raw)[:MAX_IMPORT]
    if not items:
        flash(_("Не нашли ни одного вопроса. Вопросы должны начинаться с номера: «1.» или «1)»."), "error")
        return redirect(url_for("assistant.home"))
    leaves = _leaves()
    for q in items:
        q["skill_id"] = guess_skill(q, leaves)
        q["exams"] = [q["exam"]] if q.get("exam") else exams
        q["problems"] = problems(q)
    dups = find_duplicates(items)
    return render_template("assistant/preview.html", items=items, leaves=leaves, dups=dups, exams=exams,
                           too_many=len(parse(raw)) > MAX_IMPORT)


def _save_image(file):
    if not file or not file.filename:
        return None
    ext = os.path.splitext(secure_filename(file.filename))[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        return None
    from .images import store_image
    return store_image(file, uuid.uuid4().hex, kind="figure")


@bp.route("/import/save", methods=["POST"])
@staff_required
def import_save():
    f = request.form
    n = min(MAX_IMPORT, f.get("count", 0, type=int))
    leaves = {node.id for node, _p in _leaves()}
    created, skipped, errors = [], 0, []
    status = "draft" if f.get("action") == "draft" else _status_for_new()
    for i in range(n):
        p = f"q{i}-"
        if not f.get(p + "include"):
            skipped += 1
            continue
        text = f.get(p + "text", "").strip()
        atype = "number" if f.get(p + "type") == "number" else "choice"
        options = [o.strip() for o in f.getlist(p + "opt") if o.strip()]
        correct = f.get(p + "correct", "").strip()
        skill = f.get(p + "skill", type=int)
        exams = [e for e in f.getlist(p + "exams") if e in EXAMS] or [e for e in f.getlist("exams") if e in EXAMS]
        label = f.get(p + "number") or str(i + 1)
        problems_ = []
        if not text:
            problems_.append(_("нет текста"))
        if skill not in leaves:
            problems_.append(_("не выбран навык"))
        if not exams:
            problems_.append(_("не выбран экзамен"))
        if atype == "choice" and (len(options) < 2 or not correct.isdigit() or int(correct) >= len(options)):
            problems_.append(_("нужно ≥ 2 вариантов и отмеченный верный"))
        if atype == "number" and not valid_number_answer(correct):
            problems_.append(_("ответ должен быть числом"))
        if problems_:
            errors.append(f"№{label}: " + ", ".join(problems_))
            continue
        q = Question(author_id=current_user.id, skill_id=skill, exams=exams,
                     difficulty=max(1, min(3, f.get(p + "difficulty", 2, type=int))), language="ru", material=[],
                     text=text, answer_type=atype, options=options if atype == "choice" else [], correct=correct,
                     input_formats=list(INPUT_FORMATS), explanation=f.get(p + "explanation", "").strip(),
                     status=status, image_path=_save_image(request.files.get(p + "image")))
        db.session.add(q)
        created.append(q)
    if created:
        from .taxonomy import auto_tags
        db.session.flush()
        for q in created:
            q.tags = auto_tags(q)
    if errors and not f.get("partial"):
        db.session.rollback()
        flash(_("Ничего не сохранено — исправьте отмеченные вопросы или снимите с них галочку."), "error")
        items = _items_from_form(f, n)
        return render_template("assistant/preview.html", items=items, leaves=_leaves(), dups=find_duplicates(items),
                               exams=[e for e in f.getlist("exams") if e in EXAMS], errors=errors), 400
    db.session.commit()
    if status == "pending":
        flash(_("Отправлено на проверку: %(n)s. Пропущено: %(s)s.", n=len(created), s=skipped), "success")
    elif status == "draft":
        flash(_("Сохранено в черновики: %(n)s.", n=len(created)), "success")
    else:
        flash(_("Опубликовано в банке: %(n)s. Пропущено: %(s)s.", n=len(created), s=skipped), "success")
    if errors:
        flash(_("Не сохранены (ошибки): %(e)s", e="; ".join(errors[:5])), "info")
    return redirect(url_for("assistant.mine") if current_user.is_assistant else url_for("teacher.bank"))


def _items_from_form(f, n):
    """Rebuild the preview from what was sent, so nothing typed is lost."""
    items = []
    for i in range(n):
        p = f"q{i}-"
        atype = "number" if f.get(p + "type") == "number" else "choice"
        q = {"number": f.get(p + "number") or str(i + 1), "text": f.get(p + "text", ""), "answer_type": atype,
             "options": [o for o in f.getlist(p + "opt")], "correct": f.get(p + "correct", ""),
             "explanation": f.get(p + "explanation", ""), "difficulty": f.get(p + "difficulty", 2, type=int),
             "skill_id": f.get(p + "skill", type=int), "exams": f.getlist(p + "exams"),
             "include": bool(f.get(p + "include"))}
        q["problems"] = problems(q)
        items.append(q)
    return items


# --------------------------------------------------------------------------- my questions


MINE_TABS = ("pending", "returned", "draft", "published")


@bp.route("/mine")
@staff_required
def mine():
    tab = request.args.get("tab", "pending")
    if tab not in MINE_TABS:
        tab = "pending"
    base = Question.query.filter_by(author_id=current_user.id)
    queries = {
        "pending": base.filter_by(status="pending"),
        "returned": base.filter(Question.status == "draft", Question.review_note.isnot(None)),
        "draft": base.filter(Question.status == "draft", Question.review_note.is_(None)),
        "published": base.filter_by(status="published"),
    }
    counts = {k: v.count() for k, v in queries.items()}
    page = max(1, request.args.get("page", 1, type=int))
    rows = queries[tab].order_by(Question.updated_at.desc()).offset((page - 1) * 30).limit(30).all()
    pages = max(1, (counts[tab] + 29) // 30)
    return render_template("assistant/mine.html", tab=tab, counts=counts, rows=rows, page=page, pages=pages)


# --------------------------------------------------------------------------- what to add, what to fix


@bp.route("/gaps")
@staff_required
def gaps():
    exam = request.args.get("exam") if request.args.get("exam") in EXAMS else None
    rows = [r for r in content_gaps(THIN) if not exam or any(e == exam for e, _c in r["gaps"])]
    return render_template("assistant/gaps.html", rows=rows[:200], total=len(rows), exam=exam, thin=THIN)


@bp.route("/fixes")
@staff_required
def fixes():
    """Open error reports on questions. A correction goes through the same review as a new question."""
    reports = (Report.query.filter(Report.status == "open", Report.question_id.isnot(None))
               .order_by(Report.created_at.desc()).limit(100).all())
    proposed = {q.replaces_id: q for q in Question.query.filter(Question.replaces_id.isnot(None),
                                                                 Question.status.in_(("pending", "draft"))).all()}
    return render_template("assistant/fixes.html", reports=reports, proposed=proposed, kinds=REPORT_KINDS)


@bp.route("/branch-request", methods=["POST"])
@staff_required
def branch_request():
    """«Нужной ветки нет»: the request reaches the admins' «Исправления» as a note on the parent subtopic."""
    parent = db.session.get(ContentNode, request.form.get("parent_id", type=int) or 0)
    name = (request.form.get("name") or "").strip()[:120]
    if not parent or not name:
        flash(_("Выберите подтему и напишите название навыка."), "error")
    else:
        db.session.add(Report(author_id=current_user.id, node_id=parent.id, kind="node",
                              message=_("Нужна новая ветка: %(n)s", n=name)))
        db.session.commit()
        flash(_("Запрос отправлен администратору."), "success")
    return redirect(request.referrer or url_for("assistant.home"))


def publish_reviewed(q):
    """Approve a question. A correction is copied onto the question it fixes (same id) and its reports are closed."""
    q.status, q.review_note, q.reviewed_by_id, q.reviewed_at = "published", None, current_user.id, utcnow()
    orig = q.replaces
    if not orig:
        return q
    for field in ("text", "options", "correct", "explanation", "material", "image_path", "answer_type", "input_formats",
                  "precision", "difficulty", "skill_id", "exams", "weight", "tags"):
        setattr(orig, field, getattr(q, field))
    orig.reviewed_by_id, orig.reviewed_at = current_user.id, utcnow()
    for r in Report.query.filter_by(question_id=orig.id, status="open").all():
        r.status, r.handled_by_id, r.handled_at, r.seen = "fixed", current_user.id, utcnow(), False
        r.reply = _("Спасибо! Вопрос исправлен.")
    db.session.delete(q)
    return orig


# --------------------------------------------------------------------------- review queue


@review_bp.route("/questions")
@reviewer_required
def queue():
    author = request.args.get("author", type=int)
    q = Question.query.filter_by(status="pending")
    authors = Counter(x.author_id for x in q.all())
    if author:
        q = q.filter_by(author_id=author)
    rows = q.order_by(Question.created_at).limit(40).all()
    dups = find_duplicates([{"text": r.text} for r in rows],
                           Question.query.filter(Question.status == "published").all())
    people = {u.id: u for u in User.query.filter(User.id.in_(list(authors) or [0])).all()}
    return render_template("assistant/review.html", rows=rows, authors=authors, people=people, author=author,
                           dups=dups, total=sum(authors.values()))


@review_bp.route("/questions/<int:qid>", methods=["POST"])
@reviewer_required
def decide(qid):
    q = db.session.get(Question, qid) or abort(404)
    if q.status != "pending":
        abort(400)
    decision = request.form.get("decision")
    q.reviewed_by_id, q.reviewed_at = current_user.id, utcnow()
    if decision == "approve":
        publish_reviewed(q)
    else:
        note = request.form.get("note", "").strip()
        if not note:
            flash(_("Напишите, что исправить — ассистент увидит комментарий."), "error")
            return redirect(url_for("review.queue", author=request.args.get("author")) + f"#q{qid}")
        q.status, q.review_note = "draft", note
    status = q.status  # read before commit: an approved correction is merged into its original and removed
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return {"status": status}
    return redirect(url_for("review.queue", author=request.args.get("author")))


@review_bp.route("/questions/approve-all", methods=["POST"])
@reviewer_required
def approve_all():
    ids = [int(x) for x in request.form.getlist("qid") if x.isdigit()]
    n = 0
    for q in Question.query.filter(Question.id.in_(ids or [0]), Question.status == "pending").all():
        publish_reviewed(q)
        n += 1
    db.session.commit()
    flash(_("Одобрено: %(n)s.", n=n), "success")
    return redirect(url_for("review.queue"))

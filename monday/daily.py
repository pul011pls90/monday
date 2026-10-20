"""Questions of the day.

Teachers choose up to three questions a day for their students (from the question bank).
A student sees the picks of all their teachers for their exam; if no teacher chose anything,
Monday picks one question for the exam so the home page is never empty.
Each question can be answered once; the answer also counts for skills and the journal.
"""
import random
from datetime import date, timedelta

from flask import Blueprint, abort, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from .models import local_date, local_midnight_utc, today as local_today  # noqa: F401
from .access import student_required
from .extensions import db
from .models import (DAILY_MAX, Attempt, AttemptAnswer, DailyAnswer, DailyPick, Question, StudentRecord, utcnow)
from .content_i18n import localize
from .services import display_answer, is_correct, teacher_ids_for

bp = Blueprint("daily", __name__, url_prefix="/daily")
LATIN = "ABCDEFGH"
CYR = "АБВГДЕЖЗ"


def _auto_pick(exam, day):
    """Monday's own question of the day for an exam (same for everyone, stable for the day)."""
    pick = DailyPick.query.filter_by(teacher_id=None, exam=exam, day=day).first()
    if pick:
        return pick
    pool = [q for q in Question.query.filter_by(status="published").all() if exam in (q.exams or [])]
    if not pool:
        return None
    rng = random.Random(f"{exam}-{day.isoformat()}")
    medium = [q for q in pool if (q.difficulty or 2) >= 2] or pool
    pick = DailyPick(teacher_id=None, exam=exam, day=day, question_id=rng.choice(sorted(medium, key=lambda q: q.id)).id)
    db.session.add(pick)
    db.session.commit()
    return pick


def picks_for_student(user, day=None):
    """Today's questions for a student: their teachers' picks, else Monday's one."""
    day = day or local_today()
    exam = user.profile.exam if user.profile else None
    teachers = teacher_ids_for(user)
    picks = []
    if teachers:
        picks = (DailyPick.query.filter(DailyPick.day == day, DailyPick.teacher_id.in_(teachers))
                 .order_by(DailyPick.teacher_id, DailyPick.position, DailyPick.id).all())
        picks = [p for p in picks if not p.exam or p.exam == exam]
    if not picks and exam:
        auto = _auto_pick(exam, day)
        picks = [auto] if auto else []
    return picks


def student_daily(user):
    """Everything the home page needs: picks with the student's answers, class rate, streak."""
    picks = picks_for_student(user)
    mine = {a.pick_id: a for a in DailyAnswer.query.filter(
        DailyAnswer.user_id == user.id, DailyAnswer.pick_id.in_([p.id for p in picks] or [0])).all()}
    exam = user.profile.exam if user.profile else None
    letters = LATIN if exam in ("SAT", "CSCA") else CYR
    items = []
    for p in picks:
        a = mine.get(p.id)
        items.append({"pick": p, "item": localize(p.question.snapshot()), "answer": a,
                      "rate": _rate(p) if a else None})
    authors = sorted({p.teacher.name for p in picks if p.teacher})
    return {"items": items, "authors": authors, "auto": bool(picks) and all(p.teacher_id is None for p in picks),
            "done": sum(1 for i in items if i["answer"]), "streak": streak(user.id), "letters": letters}


def _rate(pick):
    total = len(pick.answers)
    ok = sum(1 for a in pick.answers if a.is_correct)
    return {"ok": ok, "total": total, "pct": round(100 * ok / total) if total else 0}


def streak(user_id):
    """Days in a row (ending today, or yesterday if today isn't answered yet) with at least one answer."""
    days = {local_date(a.answered_at) for a in DailyAnswer.query.filter_by(user_id=user_id).all() if a.answered_at}
    d = local_today()
    if d not in days:
        d -= timedelta(days=1)
    n = 0
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n


def _allowed(user, pick):
    if pick.day != local_today():
        return False
    return pick in picks_for_student(user)


@bp.route("/")
@student_required
def play():
    """The questions of the day on their own screen (the home page shows a slim card that leads here)."""
    from flask import redirect, render_template, url_for
    data = student_daily(current_user)
    if not data["items"]:
        return redirect(url_for("student.home"))
    return render_template("student/daily.html", daily=data)


@bp.route("/<int:pick_id>/answer", methods=["POST"])
@student_required
def answer(pick_id):
    pick = db.session.get(DailyPick, pick_id) or abort(404)
    if not _allowed(current_user, pick):
        abort(404)
    q = pick.question
    given = (request.form.get("given") or "").strip()
    if not given:
        return jsonify(error=_("Выберите или введите ответ.")), 400
    existing = DailyAnswer.query.filter_by(user_id=current_user.id, pick_id=pick.id).first()
    if existing:
        ok = existing.is_correct
    else:
        ok = is_correct(q, given)
        db.session.add(DailyAnswer(user_id=current_user.id, pick_id=pick.id, given=given[:255], is_correct=ok))
        # also count for skills and the journal: one "daily" attempt per student per day
        today = local_today()
        att = (Attempt.query.filter(Attempt.user_id == current_user.id, Attempt.mode == "daily",
                                    Attempt.started_at >= local_midnight_utc())
               .first())
        if att is None:
            att = Attempt(user=current_user, mode="daily", plan=[], total=0, score=0)
            db.session.add(att)
        att.plan = list(att.plan or []) + [q.id]
        att.total = (att.total or 0) + 1
        att.score = (att.score or 0) + (1 if ok else 0)
        att.finished_at = utcnow()
        db.session.add(AttemptAnswer(attempt=att, index=len(att.plan) - 1, question=q, skill_id=q.skill_id,
                                     given=given[:255], is_correct=ok))
        db.session.commit()
    exam = current_user.profile.exam if current_user.profile else None
    L = LATIN if exam in ("SAT", "CSCA") else CYR
    item = localize(q.snapshot())
    correct_text = display_answer(q.correct) if q.answer_type == "number" else f"{L[int(q.correct)]}) {(item.get('options') or [''])[int(q.correct)]}"
    return jsonify(ok=ok, correct=q.correct, correct_text=correct_text,
                   explanation=item.get("explanation") or _("Учитель не добавил объяснение."), rate=_rate(pick),
                   streak=streak(current_user.id))


# --------------------------------------------------------------------------- teacher side


def teacher_daily(teacher, records):
    """Today's and tomorrow's picks with how the class did."""
    today = local_today()
    linked = {r.student_user_id for r in records if r.student_user_id}
    out = {}
    for key, day in (("today", today), ("tomorrow", today + timedelta(days=1))):
        picks = (DailyPick.query.filter_by(teacher_id=teacher.id, day=day)
                 .order_by(DailyPick.position, DailyPick.id).all())
        rows = []
        for p in picks:
            ans = [a for a in p.answers if a.user_id in linked]
            rows.append({"pick": p, "answered": len(ans), "ok": sum(1 for a in ans if a.is_correct)})
        out[key] = {"day": day, "rows": rows, "free": DAILY_MAX - len(picks)}
    out["students"] = len(linked)
    return out


def add_picks(teacher, question_ids, day, exam):
    """Add up to the daily limit; returns (added, skipped)."""
    have = DailyPick.query.filter_by(teacher_id=teacher.id, day=day).all()
    taken = {p.question_id for p in have}
    added = 0
    for qid in question_ids:
        if len(have) + added >= DAILY_MAX:
            break
        if qid in taken:
            continue
        db.session.add(DailyPick(teacher_id=teacher.id, question_id=qid, day=day, exam=exam,
                                 position=len(have) + added))
        taken.add(qid)
        added += 1
    db.session.commit()
    return added, len(question_ids) - added

"""Question bank: every published question of the student's exam, with filters and SAT-style practice.

/bank                      filters (difficulty, status, marked, answer type) + topics with checkboxes
/bank/start                builds a session from the chosen skills and filters
/bank/s/<id>/sheet?p=k     booklet: several questions per page with an answer sheet (default view)
/bank/s/<id>?i=k           one question, Bluebook-like: mark, eliminate, attempts, check, explanation
/bank/s/<id>/check|reveal  answers without reloading; /bank/mark and /bank/time keep the student's state
"""
import re
from collections import Counter, defaultdict

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user

from .access import student_required
from .constants import EXAMS, FORMAT_FOR_EXAM, TEST_FORMATS
from .extensions import db
from .models import Attempt, AttemptAnswer, BankState, Question, ReferenceSheet
from .services import content_tree, display_answer, is_correct, student_pool
from .content_i18n import localize
from .taxonomy import exam_view, keyset

bp = Blueprint("bank", __name__, url_prefix="/bank")

FILTERS = {
    "d": ("1", "2", "3"),                       # difficulty
    "st": ("correct", "incorrect", "none"),     # answered status
    "mk": ("yes", "no"),                        # marked for review
    "t": ("choice", "number"),                  # answer type
    "src": ("pack", "teacher"),                 # from compilations / made by teachers
}
LATIN = "ABCDEFGH"


# --------------------------------------------------------------------------- data


def _exam_arg():
    exam = request.values.get("exam")
    if exam in EXAMS:
        return exam
    return current_user.profile.exam if current_user.profile else None


def _filters(source):
    return {k: [v for v in source.getlist(k) if v in allowed] for k, allowed in FILTERS.items()}


def _states(user_id, qids=None):
    q = BankState.query.filter_by(user_id=user_id)
    if qids is not None:
        q = q.filter(BankState.question_id.in_(qids))
    return {s.question_id: s for s in q.all()}


def _last_answers(user_id):
    """Latest answer per question from any session or test (so the bank knows what was solved elsewhere)."""
    rows = (db.session.query(AttemptAnswer.question_id, AttemptAnswer.is_correct)
            .join(Attempt, Attempt.id == AttemptAnswer.attempt_id)
            .filter(Attempt.user_id == user_id, AttemptAnswer.question_id.isnot(None))
            .order_by(AttemptAnswer.answered_at).all())
    return {qid: ok for qid, ok in rows}


def _status(q, states, last):
    st = states.get(q.id)
    if st and st.attempts:
        return "correct" if st.last_correct else "incorrect"
    if q.id in last:
        return "correct" if last[q.id] else "incorrect"
    return "none"


def _pool(user, exam):
    """Published questions of the exam, in tree order. The tree is the exam's route plus any other node
    that has questions for this exam, so the bank holds the same questions as «Сессии» and the skill map."""
    pool = student_pool(exam)
    have = {q.skill_id for q in pool}
    tree = []
    for t in content_tree(user):
        subs = [{"node": s["node"], "nodes": [n for n in s["nodes"] if not exam or n.in_exam(exam) or n.id in have]}
                for s in t["subtopics"]]
        subs = [s for s in subs if s["nodes"]]
        if subs:
            tree.append({"node": t["node"], "subtopics": subs})
    order = {}
    for t in tree:
        for s in t["subtopics"]:
            for n in s["nodes"]:
                order[n.id] = len(order)
    qs = [q for q in pool if q.skill_id in order]
    qs.sort(key=lambda q: (order[q.skill_id], q.difficulty or 2, q.id))
    return tree, qs


def _match(q, f, status, states):
    if f["d"] and str(q.difficulty or 2) not in f["d"]:
        return False
    if f["st"] and status not in f["st"]:
        return False
    if f["mk"]:
        marked = bool(states.get(q.id) and states[q.id].marked)
        if ("yes" if marked else "no") not in f["mk"]:
            return False
    if f["t"] and (q.answer_type or "choice") not in f["t"]:
        return False
    if f["src"] and ("pack" if q.source else "teacher") not in f["src"]:
        return False
    return True


def _matching(user, exam, f):
    tree, pool = _pool(user, exam)
    states = _states(user.id)
    last = _last_answers(user.id)
    rows, every = [], []
    for q in pool:
        status = _status(q, states, last)
        every.append((q, status))
        if _match(q, f, status, states):
            rows.append((q, status))
    return tree, pool, rows, states, every  # every: all of the exam's questions with their status


def clock(seconds):
    seconds = int(seconds or 0)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# --------------------------------------------------------------------------- pages


@bp.route("/")
@student_required
def index():
    exam = _exam_arg()
    f = _filters(request.args)
    tree, pool, rows, states, every = _matching(current_user, exam, f)

    # the exam's own view of the map (SAT: official domains; others: the master map)
    view = exam_view(current_user, exam)
    ks = keyset(view)
    per_node, total_node = Counter(q.skill_id for q, _st in rows), Counter(q.skill_id for q in pool)
    count = {k: sum(per_node[n] for n in ids) for k, ids in ks.items()}
    total = {k: sum(total_node[n] for n in ids) for k, ids in ks.items()}
    topics = [sec for sec in view if total.get(sec["key"])]

    # per topic: how the matching questions split by difficulty, and how many are already answered
    by_diff, by_done = defaultdict(Counter), Counter()
    for q, st in rows:
        by_diff[q.skill_id][q.difficulty or 2] += 1
        if st != "none":
            by_done[q.skill_id] += 1
    diff = {k: [sum(by_diff[n][d] for n in ids) for d in (1, 2, 3)] for k, ids in ks.items()}
    done = {k: sum(by_done[n] for n in ids) for k, ids in ks.items()}

    # the progress card always shows the whole exam, whatever filters are on
    answered = sum(1 for _q, st in every if st != "none")
    correct = sum(1 for _q, st in every if st == "correct")
    seconds = sum(states[q.id].seconds for q, _st in every if q.id in states)
    marked = sum(1 for q, _st in every if q.id in states and states[q.id].marked)
    n = len(every)
    stats = {
        "total": n, "answered": answered, "marked": marked,
        "correct": correct, "wrong": answered - correct,
        "percent": round(100 * answered / n) if n else 0,
        "ok_w": round(100 * correct / n, 1) if n else 0,
        "bad_w": round(100 * (answered - correct) / n, 1) if n else 0,
        "time": clock(seconds) if seconds else "—",
    }
    active = any(f.values())
    return render_template("student/bank.html", exam=exam, f=f, active=active, topics=topics, stats=stats, matching=len(rows),
                           pool_size=len(pool), count=count, total=total, diff=diff, done=done)


@bp.route("/start", methods=["POST"])
@student_required
def start():
    exam = _exam_arg()
    f = _filters(request.form)
    tree, _pool_all, rows, _states_, _every = _matching(current_user, exam, f)

    # the chosen entries (any level of the exam view) → master skills
    ks = keyset(exam_view(current_user, exam))
    chosen = [k for k in request.form.getlist("k") if k in ks]
    only = request.form.get("only")
    if only in ks:
        chosen = [only]
    leaves = set().union(*(ks[k] for k in chosen)) if chosen else set()
    picked = [q for q, _st in rows if not chosen or q.skill_id in leaves]
    if exam == "ORT":  # like the paper test: comparisons (part 1) before the other questions (part 2)
        picked.sort(key=lambda q: 0 if _is_compare(q.material) else 1)
    plan = [q.id for q in picked]
    if not plan:
        from flask import flash
        flash(_("По этим фильтрам вопросов нет. Сними часть фильтров."), "error")
        return redirect(url_for("bank.index", exam=exam, **f))
    att = Attempt(user=current_user, mode="bank", plan=plan, position=0, total=len(plan), draft={"exam": exam})
    db.session.add(att)
    db.session.commit()
    if request.form.get("view") == "one":
        return redirect(url_for("bank.play", attempt_id=att.id))
    return redirect(url_for("bank.sheet", attempt_id=att.id))


def _own_bank_attempt(attempt_id):
    att = db.session.get(Attempt, attempt_id)
    if not att or att.user_id != current_user.id or att.mode != "bank":
        abort(404)
    return att


def _letters(exam):
    return LATIN if exam in ("SAT", "CSCA") else None


@bp.route("/s/<int:attempt_id>")
@student_required
def play(attempt_id):
    att = _own_bank_attempt(attempt_id)
    plan = att.plan or []
    i = request.args.get("i", type=int)
    i = att.position if i is None else i
    i = max(0, min(len(plan) - 1, i))
    if att.position != i:
        att.position = i
        db.session.commit()
    question = db.session.get(Question, plan[i])
    if question is None:
        abort(404)
    exam = (att.draft or {}).get("exam")
    states = _states(current_user.id, plan)
    last = _last_answers(current_user.id)
    checked_ids = {a.question_id for a in att.answers}
    diff = dict(db.session.query(Question.id, Question.difficulty).filter(Question.id.in_(plan)).all())
    grid = []
    for k, qid in enumerate(plan):
        st = states.get(qid)
        state = ""
        if st and st.attempts:
            state = "is-ok" if st.last_correct else "is-bad"
        grid.append({"n": k + 1, "state": state, "marked": bool(st and st.marked), "d": diff.get(qid) or 2})
    fmt = TEST_FORMATS.get(FORMAT_FOR_EXAM.get(exam, ""), TEST_FORMATS["plain"])
    sheets = (ReferenceSheet.query.filter_by(user_id=current_user.id, enabled=True)
              .order_by(ReferenceSheet.position, ReferenceSheet.id).all())
    state = states.get(question.id)
    return render_template("student/bank_play.html", att=att, i=i, n=len(plan), question=question,
                           item=localize(question.snapshot()), state=state, grid=grid, checked=len(checked_ids),
                           letters=_letters(exam), exam=exam, calculator=fmt["calculator"] or exam is None,
                           sheets=sheets, seen_before=question.id in last)


# --------------------------------------------------------------------------- booklet view

# A page shows 4 short questions (2 rows of 2), or 2 long ones (one per row), or 1 question with a picture.


def _is_compare(material):
    return any((b or {}).get("type") == "columns" for b in (material or []))


def _plain_len(text):
    """Rough printed length: LaTeX commands and braces don't take space on the page."""
    t = re.sub(r"\\[a-zA-Z]+", "", text or "")
    return len(re.sub(r"[{}$^_\\]", "", t))


def _is_wide(item):
    """Long questions get a full row; short ones share a row with a neighbour."""
    if _is_compare(item.get("material")):
        return False
    if any((b or {}).get("type") == "passage" for b in (item.get("material") or [])):
        return True
    opts = item.get("options") or []
    return (_plain_len(item.get("text")) > 170 or any(_plain_len(o) > 42 for o in opts)
            or sum(_plain_len(o) for o in opts) > 150)


def booklet_pages(items):
    """items: [(index, item)] → pages: [{"rows": [[(i, item), …], …], "compare": bool}].
    Short questions go two to a row, long ones one to a row, at most 2 rows a page; a question with a picture
    has a page of its own. Comparisons and other questions never share a page (ORT parts); order is kept."""
    pages, state = [], {"rows": [], "kind": None}

    def close():
        if state["rows"]:
            pages.append({"rows": state["rows"], "compare": state["kind"]})
        state["rows"] = []

    def add(row):
        if len(state["rows"]) >= 2:
            close()
        state["rows"].append(row)

    pending = None  # a short question waiting for a neighbour
    for i, item in items:
        cmp = _is_compare(item.get("material"))
        if state["kind"] is not None and cmp != state["kind"]:
            if pending:
                add([pending])
                pending = None
            close()
        state["kind"] = cmp
        if item.get("image_path"):
            if pending:
                add([pending])
                pending = None
            close()
            state["rows"].append([(i, item)])
            close()
        elif _is_wide(item):
            if pending:
                add([pending])
                pending = None
            add([(i, item)])
        elif pending:
            add([pending, (i, item)])
            pending = None
        else:
            pending = (i, item)
    if pending:
        add([pending])
    close()
    return pages


@bp.route("/s/<int:attempt_id>/sheet")
@student_required
def sheet(attempt_id):
    att = _own_bank_attempt(attempt_id)
    plan = att.plan or []
    exam = (att.draft or {}).get("exam")
    qs = {q.id: q for q in Question.query.filter(Question.id.in_(plan)).all()}
    items = [(k, localize(qs[qid].snapshot())) for k, qid in enumerate(plan) if qid in qs]
    pages = booklet_pages(items)
    p = max(0, min(len(pages) - 1, request.args.get("p", type=int) or 0))
    q = request.args.get("q", type=int)  # coming from the one-question view: open the page with that question
    if q is not None:
        p = next((k for k, pg in enumerate(pages) if any(i == q for row in pg["rows"] for i, _it in row)), p)
    done = {}
    for a in sorted(att.answers, key=lambda a: a.id):  # the latest check of each question in this session
        done[a.index] = {"given": a.given, "ok": a.is_correct}
    st = _states(current_user.id, plan)
    for k, qid in enumerate(plan):  # later re-checks live in the bank state
        s_ = st.get(qid)
        if k in done and s_ and s_.attempts:
            done[k] = {"given": s_.last_given, "ok": bool(s_.last_correct), "revealed": bool(s_.revealed)}
    page_state = []
    for pg in pages:
        idx = [i for row in pg["rows"] for i, _it in row]
        page_state.append("is-ok" if idx and all(done.get(i, {}).get("ok") for i in idx)
                          else ("is-part" if any(i in done for i in idx) else ""))
    fmt = TEST_FORMATS.get(FORMAT_FOR_EXAM.get(exam, ""), TEST_FORMATS["plain"])
    ranges = []
    for pg in pages:
        idx = [i for row in pg["rows"] for i, _it in row]
        ranges.append(f"{idx[0] + 1}" if len(idx) == 1 else f"{idx[0] + 1}–{idx[-1] + 1}")
    return render_template("student/bank_sheet.html", att=att, exam=exam, pages=pages, p=p, page_state=page_state, ranges=ranges,
                           page=pages[p] if pages else {"rows": [], "compare": False}, done=done, n=len(plan),
                           letters=_letters(exam), calculator=fmt["calculator"] or exam is None,
                           checked=len({a.question_id for a in att.answers}),
                           has_number=any(it.get("answer_type") == "number" for row in (pages[p]["rows"] if pages else [])
                                          for _i, it in row))


def _state_for(qid):
    st = BankState.query.filter_by(user_id=current_user.id, question_id=qid).first()
    if st is None:
        st = BankState(user_id=current_user.id, question_id=qid)
        db.session.add(st)
    return st


def _answer_payload(question, letters):
    L = letters or "АБВГДЕЖЗ"
    item = localize(question.snapshot())
    if question.answer_type == "number":
        correct_text = display_answer(question.correct)
    else:
        k = int(question.correct)
        correct_text = f"{L[k]}) {(item.get('options') or [''])[k]}"
    return {"correct": question.correct, "correct_text": correct_text,
            "explanation": item.get("explanation") or _("Учитель не добавил объяснение."),
            "video_url": question.video_url or ""}


def _seconds_arg():
    s = request.form.get("seconds", type=int) or 0
    return max(0, min(s, 3600))


@bp.route("/s/<int:attempt_id>/check", methods=["POST"])
@student_required
def check(attempt_id):
    att = _own_bank_attempt(attempt_id)
    i = request.form.get("i", type=int)
    if i is None or not 0 <= i < len(att.plan or []):
        abort(400)
    question = db.session.get(Question, att.plan[i])
    given = (request.form.get("given") or "").strip()
    if not given:
        return jsonify(error=_("Выберите или введите ответ.")), 400
    ok = is_correct(question, given)
    st = _state_for(question.id)
    st.attempts = (st.attempts or 0) + 1
    st.last_correct = ok
    st.last_given = given[:255]
    st.seconds = (st.seconds or 0) + _seconds_arg()
    # the first try in this session counts for skills and the journal
    if not any(a.index == i for a in att.answers):
        db.session.add(AttemptAnswer(attempt=att, index=i, question=question, skill_id=question.skill_id,
                                     given=given[:255], is_correct=ok))
        att.score = (att.score or 0) + (1 if ok else 0)
    db.session.commit()
    out = {"ok": ok, "attempts": st.attempts, "checked": len({a.question_id for a in att.answers})}
    if ok or st.revealed:
        out.update(_answer_payload(question, _letters((att.draft or {}).get("exam"))))
    return jsonify(out)


@bp.route("/s/<int:attempt_id>/reveal", methods=["POST"])
@student_required
def reveal(attempt_id):
    att = _own_bank_attempt(attempt_id)
    i = request.form.get("i", type=int)
    if i is None or not 0 <= i < len(att.plan or []):
        abort(400)
    question = db.session.get(Question, att.plan[i])
    st = _state_for(question.id)
    if not st.attempts:
        return jsonify(error=_("Сначала ответь — потом объяснение.")), 409
    st.revealed = True
    db.session.commit()
    return jsonify(_answer_payload(question, _letters((att.draft or {}).get("exam"))))


@bp.route("/mark", methods=["POST"])
@student_required
def mark():
    qid = request.form.get("question_id", type=int)
    if not qid or not db.session.get(Question, qid):
        abort(400)
    st = _state_for(qid)
    st.marked = request.form.get("on") == "1"
    db.session.commit()
    return jsonify(marked=st.marked)


@bp.route("/time", methods=["POST"])
@student_required
def time_spent():
    qid = request.form.get("question_id", type=int)
    if not qid or not db.session.get(Question, qid):
        abort(400)
    st = _state_for(qid)
    st.seconds = (st.seconds or 0) + _seconds_arg()
    db.session.commit()
    return ("", 204)

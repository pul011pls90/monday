"""Question picker shared by the test editor and the teacher's question bank.

Left: the topic tree with counts.  Middle: filtered, sorted, paged questions with a preview.
The page keeps the chosen questions (order list in the editor, a basket in the bank).
Also: "5 random from this skill" and "fill by plan" (n per topic, easy/medium/hard mix).
"""
import random
from collections import Counter, defaultdict

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user
from sqlalchemy import func

from .access import teacher_required
from .constants import EXAMS
from .extensions import db
from .models import AttemptAnswer, Question, User, Work
from .taxonomy import TAGS, exam_view, keyset

bp = Blueprint("picker", __name__, url_prefix="/teacher/picker")

FILTERS = {"d": ("1", "2", "3"), "t": ("choice", "number"), "m": ("with", "without"),
           "src": ("mine", "others", "monday"), "used": ("yes", "no"), "tag": ("word", "graph", "nocalc", "compare")}
SORTS = ("tree", "new", "hard", "used")
PER_PAGE = 20
MINUTES = {1: 1.5, 2: 2.0, 3: 3.0}  # rough time per question by difficulty


def _exam():
    e = request.values.get("exam")
    return e if e in EXAMS else "ORT"


def _filters():
    return {k: [v for v in request.values.getlist(k) if v in allowed] for k, allowed in FILTERS.items()}


def success_rates(qids):
    """Share of correct answers per question across all students: {qid: (rate, n)}."""
    if not qids:
        return {}
    rows = (db.session.query(AttemptAnswer.question_id, func.count(), func.sum(AttemptAnswer.is_correct.cast(db.Integer)))
            .filter(AttemptAnswer.question_id.in_(qids)).group_by(AttemptAnswer.question_id).all())
    return {qid: ((ok or 0) / n, n) for qid, n, ok in rows if n}


def usage(user_id):
    """How many works use each question (everyone's), and which ones are in my works."""
    total, mine = Counter(), set()
    for w in Work.query.all():
        ids = set(w.draft_question_ids or [])
        total.update(ids)
        if w.author_id == user_id:
            mine |= ids
    return total, mine


def _staff_ids():
    return {u.id for u in User.query.filter(User.role.in_(("admin", "assistant"))).all()}


def build(user, exam, f, keys=(), q="", sort="tree"):
    """Questions of an exam filtered by chips, search and the chosen tree keys (any level, several at once)."""
    view = exam_view(user, exam)
    ks = keyset(view)
    order = {}
    for sec in view:
        for g in sec["groups"]:
            for sk in g["skills"]:
                for nid in sorted(sk["nodes"]):
                    order.setdefault(nid, len(order))
    used_total, used_mine = usage(user.id)
    staff = _staff_ids()
    pool = [x for x in Question.query.filter((Question.status == "published") | (Question.author_id == user.id)).all()
            if x.skill_id in order and exam in (x.exams or [])]
    q = (q or "").strip().lower()

    def keep(x):
        if f["d"] and str(x.difficulty or 2) not in f["d"]:
            return False
        if f["t"] and (x.answer_type or "choice") not in f["t"]:
            return False
        if f["m"] and ("with" if (x.image_path or x.material) else "without") not in f["m"]:
            return False
        if f["src"]:
            src = "mine" if x.author_id == user.id else ("monday" if x.author_id in staff else "others")
            if src not in f["src"]:
                return False
        if f["used"] and ("yes" if x.id in used_mine else "no") not in f["used"]:
            return False
        if f["tag"] and not set(f["tag"]) & set(x.tags or []):
            return False
        if q and q not in (x.text or "").lower() and not any(q in (b.get("text") or "").lower() for b in (x.material or [])):
            return False
        return True

    matched = [x for x in pool if keep(x)]
    per_node = Counter(x.skill_id for x in matched)
    tree_counts = {k: sum(per_node[n] for n in ids) for k, ids in ks.items()}
    keys = [k for k in keys if k in ks]
    if keys:
        chosen = set().union(*(ks[k] for k in keys))
        matched = [x for x in matched if x.skill_id in chosen]
    rates = success_rates([x.id for x in matched])
    if sort == "new":
        matched.sort(key=lambda x: -x.id)
    elif sort == "hard":
        matched.sort(key=lambda x: (rates[x.id][0] if x.id in rates else 2, -(x.difficulty or 2)))
    elif sort == "used":
        matched.sort(key=lambda x: (-used_total.get(x.id, 0), x.id))
    else:
        matched.sort(key=lambda x: (order[x.skill_id], x.difficulty or 2, x.id))
    return {"view": view, "tree_counts": tree_counts, "matched": matched, "rates": rates, "keys": keys,
            "used_total": used_total, "used_mine": used_mine, "total_pool": len(pool), "keyset": ks}


def row_data(x):
    """What the order list / basket needs to show totals."""
    topic = x.skill.topic if x.skill else ""
    return {"id": x.id, "label": (x.text or "")[:90] or "…", "topic": topic, "d": x.difficulty or 2,
            "min": MINUTES.get(x.difficulty or 2, 2.0)}


@bp.route("/")
@teacher_required
def results():
    exam = _exam()
    f = _filters()
    keys = request.args.getlist("k")
    sort = request.args.get("sort") if request.args.get("sort") in SORTS else "tree"
    data = build(current_user, exam, f, keys, request.args.get("q", ""), sort)
    page = max(1, request.args.get("page", 1, type=int))
    total = len(data["matched"])
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(page, pages)
    shown = data["matched"][(page - 1) * PER_PAGE: page * PER_PAGE]
    ctx = dict(data, items=shown, total=total, page=page, pages=pages, exam=exam, TAGS=TAGS,
               rows={x.id: row_data(x) for x in shown})
    return jsonify(tree=render_template("teacher/_picker_tree.html", **ctx),
                   list=render_template("teacher/_picker_list.html", **ctx), total=total)


@bp.route("/q/<int:qid>")
@teacher_required
def preview(qid):
    x = db.session.get(Question, qid)
    if not x or (x.status != "published" and x.author_id != current_user.id):
        return ("", 404)
    return render_template("teacher/_picker_preview.html", qn=x, it=x.snapshot())


@bp.route("/random")
@teacher_required
def pick_random():
    """n random questions from the chosen branch and filters, skipping ones already chosen or in my works."""
    exam = _exam()
    n = max(1, min(20, request.args.get("n", 5, type=int)))
    exclude = {int(x) for x in request.args.get("exclude", "").split(",") if x.isdigit()}
    data = build(current_user, exam, _filters(), request.args.getlist("k"), request.args.get("q", ""))
    fresh = [x for x in data["matched"] if x.id not in exclude and x.id not in data["used_mine"]]
    pool = fresh or [x for x in data["matched"] if x.id not in exclude]
    picked = random.sample(pool, min(n, len(pool)))
    return jsonify(items=[row_data(x) for x in picked])


@bp.route("/plan")
@teacher_required
def plan():
    """Fill by plan: `per` questions from every topic, split easy/medium/hard by the given shares."""
    exam = _exam()
    per = max(1, min(10, request.args.get("per", 2, type=int)))
    mix = [max(0, request.args.get(k, d, type=int)) for k, d in (("e", 1), ("m", 2), ("h", 1))]
    exclude = {int(x) for x in request.args.get("exclude", "").split(",") if x.isdigit()}
    data = build(current_user, exam, _filters())
    rng = random.Random()
    out = []
    total_mix = sum(mix) or 1
    taken = set(exclude)
    for sec in data["view"]:
        ids = data["keyset"][sec["key"]]
        groups = defaultdict(list)
        for x in data["matched"]:
            if x.skill_id in ids and x.id not in taken:
                groups[x.difficulty or 2].append(x)
        if not groups:
            continue
        want = {d: round(per * mix[d - 1] / total_mix) for d in (1, 2, 3)}
        while sum(want.values()) < per:
            want[2] += 1
        chosen = []
        for d in (1, 2, 3):
            fresh = [x for x in groups[d] if x.id not in data["used_mine"]] or groups[d]
            chosen += rng.sample(fresh, min(want[d], len(fresh)))
        rest = [x for d in (1, 2, 3) for x in groups[d] if x not in chosen]
        while len(chosen) < per and rest:
            chosen.append(rest.pop(rng.randrange(len(rest))))
        for x in chosen[:per]:
            taken.add(x.id)
            out.append(x)
    return jsonify(items=[row_data(x) for x in out])

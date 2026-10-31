"""Business logic shared by the student and teacher sides.

Everything that computes progress, mastery, rankings or picks questions lives
here so pages stay thin and the rules are in one place.
"""
import json
import random
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from fractions import Fraction

from sqlalchemy import func

from .models import local_date, local_midnight_utc, local_now, today as local_today  # noqa: F401
from .constants import EXAMS, MODES
from .extensions import db
from .models import utcnow
from .models import (INPUT_FORMATS, Assignment, Attempt, AttemptAnswer, ContentNode, Question, Skill, StudentRecord,
                     Work, WorkVersion)

MASTERY_WINDOW = 8  # last N answers per skill
MASTERED_ACCURACY = 0.8
MASTERED_MIN_ANSWERS = 5


# --------------------------------------------------------------------------- dates


def week_start(d=None):
    d = d or local_today()
    return d - timedelta(days=d.weekday())


def next_monday_test_start(now=None):
    """Monday tests open every Monday at 19:00 local time."""
    now = now or local_now()
    monday = week_start(now.date())
    start = datetime.combine(monday, datetime.min.time()).replace(hour=19)
    if now >= start + timedelta(hours=5):  # window: Monday 19:00–24:00
        start += timedelta(days=7)
    return start


def mondays_left(exam_date, today=None):
    """Number of Mondays from today (inclusive) up to the exam date."""
    if not exam_date:
        return None
    today = today or local_today()
    if exam_date < today:
        return 0
    first = today + timedelta(days=(7 - today.weekday()) % 7)
    if first > exam_date:
        return 0
    return (exam_date - first).days // 7 + 1


def countdown_label(delta):
    total = int(delta.total_seconds())
    if total <= 0:
        return None
    days, rem = divmod(total, 86400)
    hours = rem // 3600
    return days, hours


# --------------------------------------------------------------------------- grading


_MIXED = re.compile(r"^(-?)(\d+)\s+(\d+)/(\d+)$")
_FRACTION = re.compile(r"^(-?\d+)/(-?\d+)$")
_WHOLE = re.compile(r"^-?\d+$")


def parse_number(value):
    """Read a student's answer. Returns (Fraction value, format) or (None, None).

    Accepted: whole numbers (12, -3), fractions (3/4, -7/2, 1 1/2) and decimals
    (0.75 or 0,75). Spaces around the answer and thousand spaces are ignored.
    """
    if value is None:
        return None, None
    text = str(value).strip().replace("−", "-").replace("–", "-")
    m = _MIXED.match(text)
    if m:
        sign, whole, num, den = m.groups()
        if int(den) == 0:
            return None, None
        v = int(whole) + Fraction(int(num), int(den))
        return (-v if sign else v), "fraction"
    text = text.replace(" ", "").replace(",", ".")
    m = _FRACTION.match(text)
    if m:
        num, den = int(m.group(1)), int(m.group(2))
        if den == 0:
            return None, None
        return Fraction(num, den), "fraction"
    if _WHOLE.match(text):
        return Fraction(int(text)), "whole"
    try:
        return Fraction(Decimal(text)), "decimal"
    except (InvalidOperation, ValueError):
        return None, None


def accepted_answers(correct):
    """A free-input answer may list several accepted values: "7|-7" or "-5/9|-0.555|-0.556"."""
    return [a.strip() for a in str(correct or "").split("|") if a.strip()]


def display_answer(correct, joiner=None):
    """Accepted answers for people to read: "7|-7" -> "7 или -7"; decimal roundings of a value already shown are hidden."""
    shown, values = [], []
    for a in accepted_answers(correct):
        v, _ = parse_number(a)
        if v is not None and any(abs(v - w) < Fraction(1, 1000) for w in values):
            continue
        shown.append(a)
        if v is not None:
            values.append(v)
    if joiner is None:
        from flask_babel import gettext
        joiner = " " + gettext("или") + " "
    return joiner.join(shown) if shown else str(correct or "")


def valid_number_answer(correct):
    answers = accepted_answers(correct)
    return bool(answers) and all(parse_number(a)[0] is not None for a in answers)


def normalize_number(value):
    v, _ = parse_number(value)
    return None if v is None else float(v)


def _get(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


SAT_ENTRY = re.compile(r"^-?(\d+(\.\d*)?|\.\d+|\d+/\d+)$")


def sat_entry_ok(given, values):
    """Digital SAT rules for a student-produced response.

    Up to 5 characters for a positive answer, 6 for a negative one; only digits, one "." or "/", and "-".
    Any exact equivalent counts (1/2 = 2/4 = 0.5 = .5). A decimal that doesn't fit must use every available
    character and be the value truncated or rounded at that length: 2/3 -> .6666 .6667 0.666 0.667
    (but not .66, .67, 0.66, 0.67). Mixed numbers ("3 1/2"), commas, %, $ are not accepted.
    """
    g = str(given or "").strip().replace("−", "-").replace("–", "-")
    if not SAT_ENTRY.match(g) or len(g) > (6 if g.startswith("-") else 5):
        return False
    v, fmt = parse_number(g)
    if v is None:
        return False
    for b in values:
        if v == b:
            return True
        if fmt == "decimal" and len(g) == (6 if g.startswith("-") else 5):
            places = len(g.split(".")[1]) if "." in g else 0
            exact = Decimal(b.numerator) / Decimal(b.denominator)
            q = Decimal(1).scaleb(-places)
            for mode in (ROUND_DOWN, ROUND_HALF_UP):
                if Fraction(exact.quantize(q, rounding=mode)) == v:
                    return True
    return False


def is_correct(item, given, sat=False):
    """item: question snapshot dict or Question; given: raw form value.
    sat=True: a test in the Digital SAT format — free input is checked by the SAT entry rules (sat_entry_ok).

    Free input: the value must match exactly, or — if the question allows rounding —
    match the correct value rounded to that many decimal places (tenths, hundredths).
    A format the teacher did not allow (e.g. a decimal where only fractions count) is wrong.
    """
    answer_type = _get(item, "answer_type")
    correct = _get(item, "correct")
    if given in (None, "") or answer_type == "written":
        return False
    if answer_type == "number" and sat:
        values = [v for v in (parse_number(x)[0] for x in accepted_answers(correct)) if v is not None]
        return sat_entry_ok(given, values)
    if answer_type == "number":
        a, fmt = parse_number(given)
        if a is None:
            return False
        allowed = _get(item, "input_formats") or list(INPUT_FORMATS)
        if fmt not in allowed and not (fmt == "whole" and ("fraction" in allowed or "decimal" in allowed)):
            return False
        precision = _get(item, "precision")
        for value in accepted_answers(correct):
            b, _ = parse_number(value)
            if b is None:
                continue
            if a == b:
                return True
            if precision:
                step = Fraction(1, 10 ** int(precision))
                if abs(a - b) <= step / 2 + Fraction(1, 10 ** 9):
                    return True
        return False
    return str(given).strip() == str(correct).strip()


def written_pending(attempt):
    """Written answers of a finished attempt that nobody has marked yet."""
    items = attempt.work_version.items if attempt.work_version else []
    return [a for a in attempt.answers
            if a.index < len(items) and items[a.index].get("answer_type") == "written" and a.points is None]


def rescore(attempt):
    """Score = automatic answers + marks for written answers (self or teacher)."""
    items = attempt.work_version.items if attempt.work_version else []
    score = 0
    for a in attempt.answers:
        item = items[a.index] if a.index < len(items) else {}
        if item.get("answer_type") == "written":
            score += a.points or 0
            a.is_correct = (a.points or 0) >= item_weight(item)
        elif a.is_correct:
            score += item_weight(item)
    attempt.score = score
    return attempt


def item_weight(item):
    return max(1, int(_get(item, "weight", 1) or 1))


def grade_version_attempt(attempt, version, form):
    """Grade a whole test (collection/homework/Monday). form maps q<index> -> value.

    score = marks earned, total = marks available (each question counts its weight).
    """
    score = total = 0
    # SAT entry rules in SAT-format collections (the test page shows them in "Как вводить ответ")
    sat = version_layout(version).get("format") == "sat" and attempt.mode == "collection"
    for idx, item in enumerate(version.items):
        given = (form.get(f"q{idx}") or "").strip()
        ok = is_correct(item, given, sat=sat)
        written = item.get("answer_type") == "written"
        w = item_weight(item)
        total += w
        score += w if ok else 0
        db.session.add(AttemptAnswer(
            attempt=attempt, index=idx, question_id=item.get("question_id"), skill_id=item.get("skill_id"),
            given=given or None, is_correct=ok, photo_path=(form.get(f"p{idx}") or None) if written else None,
            points=0 if written and not given and not form.get(f"p{idx}") else None,
            mistake_reason=None if ok else ("time" if not given else None),
        ))
    attempt.score = score
    attempt.total = total
    attempt.draft = {}
    attempt.finished_at = utcnow()
    attempt.duration_sec = int((attempt.finished_at - attempt.started_at).total_seconds())
    limit = attempt.work_version.time_limit_min if attempt.work_version else None
    if limit:  # a tab left open past the limit does not count as time spent (rankings sort by it)
        attempt.duration_sec = min(attempt.duration_sec, limit * 60)
    return attempt


# --------------------------------------------------------------------------- content tree


def teacher_ids_for(user):
    """Teachers whose own branches this user may see."""
    if user is None:
        return set()
    if user.is_teacher:
        return {user.id}
    rows = StudentRecord.query.filter_by(student_user_id=user.id).all()
    return {r.teacher_id for r in rows}


def visible_nodes(user=None, include_archived=False):
    """All tree entries the user can see: the shared tree plus their teachers' branches."""
    q = ContentNode.query
    if not include_archived:
        q = q.filter(ContentNode.archived.is_(False))
    nodes = q.order_by(ContentNode.position, ContentNode.id).all()
    if user is not None and user.is_admin:
        return nodes
    owners = teacher_ids_for(user)
    return [n for n in nodes if n.owner_id is None or n.owner_id in owners]


def content_tree(user=None, exam=None, include_archived=False):
    """[{node: topic, subtopics: [{node: subtopic, nodes: [node, ...]}]}] in display order.

    exam filters leaf nodes to that exam's route; empty branches are kept only when
    exam is None (so teachers see the whole structure while editing).
    """
    nodes = visible_nodes(user, include_archived)
    by_parent = defaultdict(list)
    for n in nodes:
        by_parent[n.parent_id].append(n)
    tree = []
    for t in by_parent[None]:
        if t.level != "topic":
            continue
        subs = []
        for s in by_parent[t.id]:
            leaves = [n for n in by_parent[s.id] if not exam or n.in_exam(exam)]
            if leaves or exam is None:
                subs.append({"node": s, "nodes": leaves})
        if subs or exam is None:
            tree.append({"node": t, "subtopics": subs})
    return tree


def content_gaps(thin=3):
    """Skills of the shared map with fewer than `thin` published questions for one of their exams, emptiest first:
    [{"node", "gaps": [(exam, count), ...], "least"}]. Shown to admins (overview) and assistants (what to add)."""
    published = Counter()
    for skill_id, exams in db.session.query(Question.skill_id, Question.exams).filter(Question.status == "published"):
        for ex in (exams or []):
            published[(skill_id, ex)] += 1
    rows = []
    for n in ContentNode.query.filter_by(level="node", archived=False, owner_id=None).all():
        gaps = [(ex, published.get((n.id, ex), 0)) for ex in (n.exams or []) if published.get((n.id, ex), 0) < thin]
        if gaps:
            rows.append({"node": n, "gaps": gaps, "least": min(c for _e, c in gaps)})
    rows.sort(key=lambda x: (x["least"], -len(x["gaps"]), x["node"].name))
    return rows


def leaf_nodes(user=None, exam=None):
    return [n for t in content_tree(user, exam) for s in t["subtopics"] for n in s["nodes"]]


# --------------------------------------------------------------------------- mastery & progress


def skill_stats(user_id):
    """Per-skill stats from the last MASTERY_WINDOW answers: {skill_id: {...}}."""
    rows = (db.session.query(AttemptAnswer.skill_id, AttemptAnswer.is_correct, AttemptAnswer.answered_at)
            .join(Attempt).filter(Attempt.user_id == user_id, AttemptAnswer.skill_id.isnot(None))
            .order_by(AttemptAnswer.answered_at.desc()).all())
    buckets = defaultdict(list)
    for skill_id, ok, _ in rows:
        if len(buckets[skill_id]) < MASTERY_WINDOW:
            buckets[skill_id].append(bool(ok))
    stats = {}
    for skill_id, results in buckets.items():
        acc = sum(results) / len(results)
        if len(results) >= MASTERED_MIN_ANSWERS and acc >= MASTERED_ACCURACY:
            state = "mastered"
        else:
            state = "progress"
        stats[skill_id] = {"accuracy": acc, "answers": len(results), "state": state}
    return stats


def _user(user_id):
    from .models import User
    return db.session.get(User, user_id) if user_id else None


def skills_for_exam(exam, user=None):
    return leaf_nodes(user, exam)


def skill_map(user_id, exam):
    """The tree with a state on every node: mastered | progress | new | outside.

    Returns [{node, subtopics: [{node, items: [{skill, state, accuracy}]}], items: [...all leaves]}].
    """
    stats = skill_stats(user_id)
    out = []
    for t in content_tree(_user(user_id)):
        topic = {"node": t["node"], "name": t["node"].name, "subtopics": [], "items": []}
        for s in t["subtopics"]:
            items = []
            for n in s["nodes"]:
                st = stats.get(n.id)
                if exam and not n.in_exam(exam):
                    state = "outside"
                elif st:
                    state = st["state"]
                else:
                    state = "new"
                items.append({"skill": n, "state": state, "accuracy": st["accuracy"] if st else None})
            if items:
                topic["subtopics"].append({"node": s["node"], "items": items})
                topic["items"] += items
        if topic["items"]:
            out.append(topic)
    return out


def progress_summary(user_id, exam):
    """Overall numbers for a student: mastery %, accuracy, predicted score, weak skills."""
    skills = skills_for_exam(exam, _user(user_id))
    stats = skill_stats(user_id)
    total = len(skills) or 1
    mastered = sum(1 for s in skills if stats.get(s.id, {}).get("state") == "mastered")
    touched = [stats[s.id]["accuracy"] for s in skills if s.id in stats]
    # Untouched skills count as 0.35 so the forecast is cautious early on.
    coverage = (sum(touched) + 0.35 * (len(skills) - len(touched))) / total
    scale = EXAMS.get(exam or "ORT", EXAMS["ORT"])
    predicted = round(scale["min"] + coverage * (scale["max"] - scale["min"]))
    weak = sorted(
        [{"skill": s, "accuracy": stats[s.id]["accuracy"]} for s in skills
         if s.id in stats and stats[s.id]["state"] != "mastered"],
        key=lambda x: x["accuracy"],
    )
    return {
        "mastered": mastered,
        "total": len(skills),
        "mastery_pct": round(100 * mastered / total),
        "predicted": predicted,
        "weak": weak,
    }


def record_progress(record):
    """Progress % shown in the teacher's table."""
    if record.student_user_id:
        exam = record.exam or (record.student.profile.exam if record.student and record.student.profile else None)
        return progress_summary(record.student_user_id, exam)["mastery_pct"]
    return record.manual_progress or 0


# --------------------------------------------------------------------------- practice sessions


def answer_item(answer):
    """The question as the student saw it: version snapshot if available, else the live question."""
    att = answer.attempt
    if att.work_version and att.work_version.items and answer.index < len(att.work_version.items):
        return att.work_version.items[answer.index]
    if answer.question:
        return answer.question.snapshot()
    return None


TOP_UP = 5  # a skill with fewer of the exam's own questions borrows from compilations of other exams
TOP_UP_MAX = 10


def exam_language(exam):
    return "en" if exam in ("SAT", "CSCA") else "ru"


def question_signature(q):
    """What a student sees and answers: text, the set of options, the right answer, reading material and picture.
    Two questions with the same signature are the same question (e.g. one problem in two official tests)."""
    norm = lambda v: re.sub(r"\s+", " ", str(v or "")).strip()
    opts = q.options or []
    right = q.correct
    if q.answer_type == "choice" and str(q.correct).isdigit() and int(q.correct) < len(opts):
        right = opts[int(q.correct)]
    return (norm(q.text), tuple(sorted(norm(o) for o in opts)), norm(right),
            json.dumps(q.material or [], sort_keys=True, ensure_ascii=False), q.image_path or "")


def _unique(rows):
    """Drop repeats of the same question, keeping the first (oldest) copy."""
    seen, out = set(), []
    for r in rows:
        key = question_signature(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _fits(exam):
    """Whether a question (row or object with language and skill_id) belongs in the exam's practice pool:
    SAT and CSCA are taken in English, and CSCA only covers senior-school skills (see CSCA_BELOW_LEVEL)."""
    lang = exam_language(exam)
    if exam not in ("SAT", "CSCA"):
        return lambda r: True
    below = set()
    if exam == "CSCA":
        from .taxonomy import CSCA_BELOW_LEVEL
        below = {n.id for n in ContentNode.query.filter(ContentNode.code.in_(CSCA_BELOW_LEVEL)).all()}
    return lambda r: (r.language or "ru") == lang and r.skill_id not in below


_POOL_CACHE = {}  # exam → (stamp, [(id, skill_id, difficulty), ...]); one per worker process


def _question_stamp():
    """Changes whenever any question is added, edited or deleted (cheap: one aggregate query)."""
    return tuple(db.session.query(func.count(Question.id), func.max(Question.updated_at)).one())


def pool_index(exam):
    """(id, skill_id, difficulty) of every practice question of an exam — see student_pool. Cached per process
    until a question changes, so pages that only count questions don't load ~1000 rows each time."""
    stamp = _question_stamp()
    hit = _POOL_CACHE.get(exam)
    if hit and hit[0] == stamp:
        return hit[1]
    rows = _unique(db.session.query(Question.id, Question.skill_id, Question.exams, Question.language, Question.source,
                                    Question.difficulty, Question.text, Question.options, Question.correct,
                                    Question.material, Question.image_path, Question.answer_type)
                   .filter(Question.status == "published", Question.answer_type != "written").order_by(Question.id).all())
    if not exam:
        out = [(r.id, r.skill_id, r.difficulty or 2) for r in rows]
    else:
        lang = exam_language(exam)
        fits = _fits(exam)
        own = [r for r in rows if exam in (r.exams or []) and fits(r)]
        have = Counter(r.skill_id for r in own)
        thin = {r.skill_id for r in rows if have[r.skill_id] < TOP_UP}
        extra = []
        for r in sorted(rows, key=lambda r: (r.difficulty or 2, r.id)):
            if (r.skill_id in thin and r.source and exam not in (r.exams or []) and fits(r)
                    and (r.language or "ru") == lang and have[r.skill_id] < TOP_UP_MAX):
                extra.append(r)
                have[r.skill_id] += 1
        out = [(r.id, r.skill_id, r.difficulty or 2) for r in own + extra]
    _POOL_CACHE[exam] = (stamp, out)
    return out


def student_pool(exam, questions=None):
    """Practice questions of an exam, never written ones.

    A skill with fewer than TOP_UP of the exam's own questions is topped up (to TOP_UP_MAX) with
    compilation questions of the same skill from other exams, in the exam's language.
    """
    if questions is not None:  # an explicit list (tests): filter it the same way
        base = _unique([q for q in questions if q.answer_type != "written"])
        if not exam:
            return base
        fits = _fits(exam)
        own = [q for q in base if exam in (q.exams or []) and fits(q)]
        have = Counter(q.skill_id for q in own)
        lang = exam_language(exam)
        thin = {q.skill_id for q in base if have[q.skill_id] < TOP_UP}
        extra = []
        for q in sorted(base, key=lambda q: (q.difficulty or 2, q.id)):
            if (q.skill_id in thin and q.source and exam not in (q.exams or []) and fits(q)
                    and (q.language or "ru") == lang and have[q.skill_id] < TOP_UP_MAX):
                extra.append(q)
                have[q.skill_id] += 1
        return own + extra
    ids = [i for i, _s, _d in pool_index(exam)]
    if not ids:
        return []
    by_id = {q.id: q for q in Question.query.filter(Question.id.in_(ids)).all()}
    return [by_id[i] for i in ids if i in by_id]


def build_custom_plan(user, cfg):
    """Questions for «Своя сессия».

    cfg: {exam, count (1–30), minutes (0 = no limit), level: ladder|easy|medium|hard|mix,
          topics: "weak" | "all" | "mistakes" | [topic node ids], explain: now|end, ids: [...] (repeat a set)}
    Ladder: the plan starts with one easy question; the next ones are chosen as the student goes
    (two right in a row → one level up, a mistake → one level down). The level pools are kept in cfg.
    Returns (questions, cfg).
    """
    exam = cfg.get("exam") or (user.profile.exam if user.profile else None)
    pool = student_pool(exam) or student_pool(None)
    if cfg.get("ids"):
        by_id = {q.id: q for q in Question.query.filter(Question.id.in_(cfg["ids"])).all()}
        qs = [by_id[i] for i in cfg["ids"] if i in by_id]
        cfg["count"] = len(qs)
        cfg["level"] = "mix"
        return qs, cfg
    topics = cfg.get("topics") or "weak"
    stats = skill_stats(user.id)
    if topics == "weak":
        weak = {sid for sid, st in stats.items() if st["state"] != "mastered"}
        focused = [q for q in pool if q.skill_id in weak]
        pool = focused if len(focused) >= cfg["count"] else focused + [q for q in pool if q.skill_id not in weak]
    elif topics == "mistakes":
        open_ids = {a.skill_id for a in open_mistakes(user.id)}
        pool = [q for q in pool if q.skill_id in open_ids] or pool
    elif isinstance(topics, list) and topics:
        wanted = set(topics)
        pool = [q for q in pool if q.skill and q.skill.topic_node and q.skill.topic_node.id in wanted]
    # the same question may exist twice (e.g. a compilation and a teacher's copy): keep one
    uniq, texts = [], set()
    for q in pool:
        key = (q.text or "").strip(), str(q.correct)
        if key not in texts:
            texts.add(key)
            uniq.append(q)
    pool = uniq
    # questions the student has not answered yet come first
    seen = {qid for (qid,) in db.session.query(AttemptAnswer.question_id).join(Attempt).filter(Attempt.user_id == user.id).all()}
    rng = random.Random()
    rng.shuffle(pool)
    pool.sort(key=lambda q: q.id in seen)
    level = cfg.get("level", "ladder")
    want = {"easy": {1}, "medium": {2}, "hard": {3}}.get(level)
    if want:
        exact = [q for q in pool if (q.difficulty or 2) in want]
        near = [q for q in pool if (q.difficulty or 2) not in want and abs((q.difficulty or 2) - min(want)) == 1]
        pool = exact + near
    n = cfg["count"]
    if level == "ladder":
        levels = {d: [q.id for q in pool if (q.difficulty or 2) == d] for d in (1, 2, 3)}
        start = next((d for d in (1, 2, 3) if levels[d]), None)
        if start is None:
            return [], cfg
        first = levels[start].pop(0)
        cfg["pools"] = {str(d): ids for d, ids in levels.items()}
        cfg["cur"] = start
        cfg["top"] = start
        return [db.session.get(Question, first)], cfg
    picked, skills = [], Counter()
    for q in pool:  # spread across skills: at most a third of the session from one skill
        if len(picked) >= n:
            break
        if skills[q.skill_id] < max(1, n // 3):
            picked.append(q)
            skills[q.skill_id] += 1
    for q in pool:
        if len(picked) >= n:
            break
        if q not in picked:
            picked.append(q)
    if level == "mix":
        picked.sort(key=lambda q: q.difficulty or 2)
    return picked, cfg


def ladder_next(att, cfg):
    """Ladder sessions: the id of the next question (or None when the session is over)."""
    if len(att.plan) >= cfg.get("count", 0):
        return None
    answers = sorted(att.answers, key=lambda a: a.index)
    cur = int(cfg.get("cur", 1))
    if answers and not answers[-1].is_correct:
        cur, cfg["run"] = max(1, cur - 1), 0
    elif answers:
        cfg["run"] = int(cfg.get("run", 0)) + 1
        if cfg["run"] >= 2:  # two right in a row → one level up
            cur, cfg["run"] = min(3, cur + 1), 0
    pools = cfg.get("pools", {})
    for d in sorted((1, 2, 3), key=lambda d: (abs(d - cur), -d)):
        ids = pools.get(str(d)) or []
        if ids:
            cfg["cur"] = d
            cfg["top"] = max(int(cfg.get("top", d)), d)
            return ids.pop(0)
    return None


def pick_practice_questions(user, mode, skill_id=None, exam=None, count=None):
    """exam: the map the student trains from ("all" = any exam); default is the student's own exam.
    count: how many questions (default: the mode's own number)."""
    if exam == "all":
        exam = None
    elif not exam:
        exam = user.profile.exam if user.profile else None
    count = count or MODES[mode]["count"]
    pool = student_pool(exam) or student_pool(None)
    if skill_id:
        focused = [q for q in pool if q.skill_id == skill_id]
        if not focused:  # nothing on the node itself: practise its subtopic instead of random questions
            node = db.session.get(ContentNode, skill_id)
            focused = [q for q in pool if node and q.skill and q.skill.parent_id == node.parent_id]
        if focused:
            rng = random.Random()
            picked = rng.sample(focused, min(count, len(focused)))
            # top up from the same subtopic if the node has few questions
            if len(picked) < count:
                parent = picked[0].skill.parent_id if picked[0].skill else None
                extra = [q for q in pool if q.skill and q.skill.parent_id == parent and q not in picked]
                picked += rng.sample(extra, min(count - len(picked), len(extra)))
            return picked

    if mode == "einstein":
        hard = [q for q in pool if q.difficulty == 3]
        pool = hard or pool
        return random.sample(pool, min(count, len(pool)))

    if mode == "darwin":
        open_skill_ids = {a.skill_id for a in open_mistakes(user.id)}
        pool_d = [q for q in pool if q.skill_id in open_skill_ids]
        picked = random.sample(pool_d, min(count, len(pool_d)))
        if len(picked) < count:  # few questions on those topics: top up from the rest of the pool
            rest = [q for q in pool if q not in picked]
            picked += random.sample(rest, min(count - len(picked), len(rest)))
        return picked

    # franklin / feynman: weakest skills first, then new ones
    stats = skill_stats(user.id)

    def weight(q):
        st = stats.get(q.skill_id)
        acc = st["accuracy"] if st else 0.5
        return acc + random.random() * 0.25

    ranked = sorted(pool, key=weight)
    picked, seen_skills = [], set()
    for q in ranked:  # spread across skills
        if q.skill_id not in seen_skills:
            picked.append(q)
            seen_skills.add(q.skill_id)
        if len(picked) == count:
            break
    for q in ranked:
        if len(picked) == count:
            break
        if q not in picked:
            picked.append(q)
    return picked


def recommended_mode(minutes):
    return {5: "franklin", 15: "feynman", 30: "darwin", 45: "einstein"}.get(minutes, "franklin")


# --------------------------------------------------------------------------- journal


def open_mistakes(user_id):
    return (AttemptAnswer.query.join(Attempt)
            .filter(Attempt.user_id == user_id, AttemptAnswer.is_correct.is_(False),
                    AttemptAnswer.resolved.is_(False), Attempt.finished_at.isnot(None))
            .order_by(AttemptAnswer.answered_at.desc()).all())


def mistake_breakdown(user_id, since=None):
    q = (db.session.query(AttemptAnswer.mistake_reason, func.count())
         .join(Attempt).filter(Attempt.user_id == user_id, AttemptAnswer.is_correct.is_(False)))
    if since:
        q = q.filter(AttemptAnswer.answered_at >= since)
    counts = dict(q.group_by(AttemptAnswer.mistake_reason).all())
    return counts


# --------------------------------------------------------------------------- homework


def homework_state(assignment, user_id):
    finished = [a for a in assignment.attempts if a.user_id == user_id and a.finished_at]
    started = [a for a in assignment.attempts if a.user_id == user_id and not a.finished_at]
    if assignment.checked_at:
        return "checked"
    if finished:
        return "submitted"
    if assignment.due_at and assignment.due_at < utcnow():
        return "overdue"
    if started:
        return "in_progress"
    return "new"


def latest_attempt(assignment, user_id):
    finished = [a for a in assignment.attempts if a.user_id == user_id and a.finished_at]
    return finished[-1] if finished else None


def student_assignments(user_id):
    return (Assignment.query.join(StudentRecord)
            .filter(StudentRecord.student_user_id == user_id)
            .order_by(Assignment.due_at.asc()).all())


# --------------------------------------------------------------------------- Monday test & ranking


def current_monday_work(exam):
    return (Work.query.filter_by(kind="monday", status="published", exam=exam)
            .order_by(Work.week_start.desc()).first())


def monday_ranking(work, scope=None, value=None, limit=50):
    """Best attempt per student on a Monday test, ranked by score then time."""
    if not work or not work.current_version:
        return []
    version_ids = [v.id for v in work.versions]
    attempts = (Attempt.query.filter(Attempt.work_version_id.in_(version_ids), Attempt.finished_at.isnot(None))
                .all())
    best = {}
    for a in attempts:
        key = a.user_id
        if key not in best or (a.score, -(a.duration_sec or 0)) > (best[key].score, -(best[key].duration_sec or 0)):
            best[key] = a
    rows = []
    for a in best.values():
        p = a.user.profile
        if scope and value and (not p or getattr(p, scope) != value):
            continue
        rows.append(a)
    rows.sort(key=lambda a: (-a.score, a.duration_sec or 0))
    return rows[:limit] if limit else rows


def user_rank(rows, user_id):
    for i, a in enumerate(rows, start=1):
        if a.user_id == user_id:
            return i, a
    return None, None


# --------------------------------------------------------------------------- publishing


def publish_work(work, note=None):
    """Freeze the editor's question list into a new WorkVersion."""
    from .constants import FORMAT_FOR_EXAM, TEST_FORMATS
    if not work.format:  # not chosen yet (e.g. demo data): follow the exam
        work.format = FORMAT_FOR_EXAM.get(work.exam, "plain")
    if work.calculator is None:
        work.calculator = TEST_FORMATS.get(work.format, {}).get("calculator", False)
    ids = list(work.draft_question_ids or [])
    questions = {q.id: q for q in Question.query.filter(Question.id.in_(ids)).all()} if ids else {}
    items = [questions[i].snapshot() for i in ids if i in questions]
    number = (work.current_version.number + 1) if work.current_version else 1
    version = WorkVersion(work=work, number=number, title=work.title, time_limit_min=work.time_limit_min,
                          items=items, note=note, layout=build_layout(work, len(items)))
    db.session.add(version)
    work.status = "published"
    return version


# --------------------------------------------------------------------------- test formats


def build_layout(work, n):
    """Freeze how a test is shown (format, navigation, calculator, modules) into its version."""
    from .constants import TEST_FORMATS
    fmt = TEST_FORMATS.get(work.format) or TEST_FORMATS["plain"]
    total = work.time_limit_min or 0
    if fmt["modules"] == 2 and n >= 2:
        split = work.module_split if work.module_split and 0 < work.module_split < n else n // 2
        first = (total + 1) // 2
        modules = [{"start": 0, "end": split, "minutes": first}, {"start": split, "end": n, "minutes": total - first}]
    else:
        modules = [{"start": 0, "end": n, "minutes": total}]
    return {"format": work.format if work.format in TEST_FORMATS else "plain", "nav": fmt["nav"],
            "calculator": bool(work.calculator), "per_page": max(1, min(10, work.per_page or 4)), "modules": modules}


def version_layout(version):
    """Layout of a published version (older versions without one behave as a plain test)."""
    if version.layout:
        return version.layout
    n = len(version.items or [])
    return {"format": "plain", "nav": "grid", "calculator": False, "per_page": 4,
            "modules": [{"start": 0, "end": n, "minutes": version.time_limit_min or 0}]}


def current_module(attempt, layout):
    mods = layout["modules"]
    k = max(1, min(len(mods), attempt.module or 1))
    return k, mods[k - 1]


def seconds_left(attempt, layout):
    """Time left in the current module (None = untimed)."""
    _k, mod = current_module(attempt, layout)
    if not mod["minutes"]:
        return None
    started = attempt.module_started_at or attempt.started_at
    return max(0, int((started + timedelta(minutes=mod["minutes"]) - utcnow()).total_seconds()))

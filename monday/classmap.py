"""Class map: the teacher's students and the content tree as one network.

Nodes
  topic     — a topic of the tree (hub)
  subtopic  — linked to its topic; coloured by the class's accuracy there, sized by how much was answered
  student   — a linked student account; joined only to the subtopics where they are weak

A student is *weak* in a subtopic when they answered at least WEAK_MIN_ANSWERS questions there in the chosen
period and got fewer than half right (the red stage of insights.gyr). Keeping only weak links keeps the
network sparse: a subtopic with many students hanging off it is one to reteach to the whole group.
"""
from collections import defaultdict
from datetime import timedelta

from .extensions import db
from .insights import gyr
from .models import Attempt, AttemptAnswer, utcnow
from .services import content_tree

WEAK_ACCURACY = 0.5
WEAK_MIN_ANSWERS = 3
GROUP_MIN = 2  # a subtopic with this many weak students is listed as "reteach together"
CHECK_MIN = 3  # a student weak in this many subtopics is listed as "check on"
PERIODS = {"7": 7, "30": 30, "90": 90, "all": None}


def _record_exam(r):
    if r.exam:
        return r.exam
    prof = r.student.profile if r.student else None
    return prof.exam if prof else None


def build(teacher, records, exam=None, period="30"):
    """The network for the teacher's linked students, filtered by exam and period.

    Returns {"nodes": [...], "links": [...], "groups": [...], "check": [...], "unlinked": n, "students": n}.
    """
    days = PERIODS.get(period, 30)
    linked = [r for r in records if r.student_user_id and (exam is None or _record_exam(r) == exam)]
    unlinked = sum(1 for r in records if not r.student_user_id and (exam is None or r.exam == exam))

    # skill → subtopic, for the subtopics in the chosen exam
    sub_of, subs, topics = {}, {}, []
    for t in content_tree(teacher):
        kept = []
        for s in t["subtopics"]:
            leaves = [n for n in s["nodes"] if exam is None or n.in_exam(exam)]
            if not leaves:
                continue
            for n in leaves:
                sub_of[n.id] = s["node"].id
            subs[s["node"].id] = {"node": s["node"], "topic": t["node"].id}
            kept.append(s["node"].id)
        if kept:
            topics.append(t["node"])

    # answers: (student, subtopic) → [right, total]
    per = defaultdict(lambda: [0, 0])
    by_user = {r.student_user_id: r for r in linked}
    if by_user and sub_of:
        q = (db.session.query(Attempt.user_id, AttemptAnswer.skill_id, AttemptAnswer.is_correct)
             .join(Attempt, AttemptAnswer.attempt_id == Attempt.id)
             .filter(Attempt.user_id.in_(by_user.keys()), AttemptAnswer.skill_id.in_(sub_of.keys())))
        if days:
            q = q.filter(AttemptAnswer.answered_at >= utcnow() - timedelta(days=days))
        for uid, skill_id, ok in q:
            cell = per[(uid, sub_of[skill_id])]
            cell[0] += 1 if ok else 0
            cell[1] += 1

    sub_tot = defaultdict(lambda: [0, 0])
    user_tot = defaultdict(lambda: [0, 0])
    weak = defaultdict(list)  # subtopic id → [record id]
    weak_of = defaultdict(list)  # record id → [subtopic id]
    links = []
    for (uid, sid), (right, total) in per.items():
        sub_tot[sid][0] += right
        sub_tot[sid][1] += total
        user_tot[uid][0] += right
        user_tot[uid][1] += total
        acc = right / total
        if total >= WEAK_MIN_ANSWERS and acc < WEAK_ACCURACY:
            rid = by_user[uid].id
            weak[sid].append(rid)
            weak_of[rid].append(sid)
            links.append({"source": f"r{rid}", "target": f"s{sid}", "kind": "weak", "acc": round(acc, 2),
                          "answers": total})

    nodes = []
    for t in topics:
        nodes.append({"id": f"t{t.id}", "kind": "topic", "name": t.name, "node_id": t.id})
    for sid, info in subs.items():
        right, total = sub_tot.get(sid, (0, 0))
        acc = right / total if total else None
        nodes.append({"id": f"s{sid}", "kind": "subtopic", "name": info["node"].name, "node_id": sid,
                      "topic": f"t{info['topic']}", "topic_id": info["topic"], "answers": total,
                      "acc": round(acc, 2) if acc is not None else None, "color": gyr(acc),
                      "weak": len(weak.get(sid, []))})
        links.append({"source": f"s{sid}", "target": f"t{info['topic']}", "kind": "tree"})
    for r in linked:
        right, total = user_tot.get(r.student_user_id, (0, 0))
        acc = right / total if total else None
        nodes.append({"id": f"r{r.id}", "kind": "student", "name": r.name, "record_id": r.id,
                      "exam": _record_exam(r), "answers": total,
                      "acc": round(acc, 2) if acc is not None else None, "color": gyr(acc),
                      "weak": len(weak_of.get(r.id, []))})

    names = {r.id: r.name for r in linked}
    groups = sorted(
        ({"subtopic": subs[sid]["node"], "topic_id": subs[sid]["topic"], "students": sorted(names[x] for x in rids)}
         for sid, rids in weak.items() if len(rids) >= GROUP_MIN),
        key=lambda g: (-len(g["students"]), g["subtopic"].name))
    check = sorted(
        ({"record": next(r for r in linked if r.id == rid), "subtopics": sorted(subs[s]["node"].name for s in sids)}
         for rid, sids in weak_of.items() if len(sids) >= CHECK_MIN),
        key=lambda c: (-len(c["subtopics"]), c["record"].name))
    return {"nodes": nodes, "links": links, "groups": groups, "check": check,
            "unlinked": unlinked, "students": len(linked)}

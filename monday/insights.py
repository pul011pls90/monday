"""Numbers for the teacher's screens: today, homework week, class dots, Monday test results, student trend."""
from collections import defaultdict
from datetime import date, datetime, timedelta

from .models import local_date, local_midnight_utc, today as local_today  # noqa: F401
from .extensions import db
from .models import Assignment, Attempt, AttemptAnswer, Attendance, StudentRecord, Work, utcnow
from .services import content_tree, homework_state, skill_stats, week_start


def gyr(acc):
    """Green ≥ 80, yellow 50–79, red < 50 (the agreed stage colours)."""
    if acc is None:
        return "none"
    return "green" if acc >= 0.8 else ("yellow" if acc >= 0.5 else "red")


def homework_week(teacher_id, start):
    """{weekday: [{assignment, record, state}]} for assignments due in the week starting `start` (a Monday)."""
    end = start + timedelta(days=7)
    rows = (Assignment.query.filter(Assignment.teacher_id == teacher_id,
                                    Assignment.due_at >= datetime.combine(start, datetime.min.time()),
                                    Assignment.due_at < datetime.combine(end, datetime.min.time()))
            .order_by(Assignment.due_at).all())
    days = defaultdict(list)
    for a in rows:
        state = homework_state(a, a.record.student_user_id) if a.record.student_user_id else "new"
        days[a.due_at.date().weekday()].append({"a": a, "record": a.record, "state": state})
    return [{"date": start + timedelta(days=i), "items": days.get(i, [])} for i in range(7)]


def fresh_mistakes(records, days=7, limit=8):
    """Latest wrong answers, grouped: one row per student × skill × reason with how many times (newest first)."""
    ids = {r.student_user_id: r for r in records if r.student_user_id}
    if not ids:
        return []
    since = utcnow() - timedelta(days=days)
    rows = (AttemptAnswer.query.join(Attempt)
            .filter(Attempt.user_id.in_(ids.keys()), AttemptAnswer.is_correct.is_(False),
                    AttemptAnswer.answered_at >= since)
            .order_by(AttemptAnswer.answered_at.desc()).limit(200).all())
    groups = {}
    for a in rows:
        key = (a.attempt.user_id, a.skill_id, a.mistake_reason)
        if key in groups:
            groups[key]["count"] += 1
        elif len(groups) < limit:
            groups[key] = {"answer": a, "record": ids[a.attempt.user_id], "count": 1}
    return list(groups.values())


def class_dots(teacher, records):
    """Students × topics. Each cell: accuracy over the topic's answered skills, coloured green/yellow/red."""
    tree = content_tree(teacher)
    topics = []
    for t in tree:
        leaves = [n.id for s in t["subtopics"] for n in s["nodes"]]
        if leaves:
            topics.append({"node": t["node"], "leaves": set(leaves)})
    rows = []
    for r in records:
        if not r.student_user_id:
            rows.append({"record": r, "cells": [None] * len(topics), "linked": False})
            continue
        stats = skill_stats(r.student_user_id)
        cells = []
        for t in topics:
            acc = [stats[i]["accuracy"] for i in t["leaves"] if i in stats]
            a = sum(acc) / len(acc) if acc else None
            cells.append({"acc": a, "color": gyr(a), "skills": len(acc), "of": len(t["leaves"])})
        rows.append({"record": r, "cells": cells, "linked": True})
    # weakest topics for the class (most red cells first)
    weak = []
    for k, t in enumerate(topics):
        vals = [row["cells"][k]["acc"] for row in rows if row["linked"] and row["cells"][k]["acc"] is not None]
        if vals:
            weak.append({"node": t["node"], "avg": sum(vals) / len(vals), "n": len(vals)})
    weak.sort(key=lambda x: x["avg"])
    return {"topics": [t["node"] for t in topics], "rows": rows, "weak": weak[:3]}


def _best_by_user(work):
    if not work:
        return {}
    vids = [v.id for v in work.versions]
    best = {}
    for a in Attempt.query.filter(Attempt.work_version_id.in_(vids), Attempt.finished_at.isnot(None)).all():
        if a.user_id not in best or a.score > best[a.user_id].score:
            best[a.user_id] = a
    return best


def monday_results(records):
    """Latest finished Monday test for the teacher's students: average, hardest questions, change vs the week before."""
    ids = {r.student_user_id: r for r in records if r.student_user_id}
    if not ids:
        return None
    exams = {r.exam or (r.student.profile.exam if r.student and r.student.profile else None) for r in records if r.student_user_id}
    this_monday = week_start(local_today())
    works = (Work.query.filter(Work.kind == "monday", Work.exam.in_([e for e in exams if e]),
                               Work.week_start <= this_monday)
             .order_by(Work.week_start.desc()).all())
    by_week = defaultdict(list)
    for w in works:
        by_week[w.week_start].append(w)
    weeks = sorted(by_week, reverse=True)
    # most recent week where somebody from the class took part
    for i, wk in enumerate(weeks):
        best = {}
        for w in by_week[wk]:
            best.update({u: a for u, a in _best_by_user(w).items() if u in ids})
        if not best:
            continue
        prev = {}
        if i + 1 < len(weeks):
            for w in by_week[weeks[i + 1]]:
                prev.update({u: a for u, a in _best_by_user(w).items() if u in ids})
        rows = []
        for u, a in best.items():
            p = prev.get(u)
            rows.append({"record": ids[u], "percent": a.percent, "delta": (a.percent - p.percent) if p else None})
        rows.sort(key=lambda x: -x["percent"])
        # per-question success rate
        per_q = defaultdict(lambda: [0, 0])
        items = {}
        for a in best.values():
            for ans in a.answers:
                per_q[ans.index][0] += 1 if ans.is_correct else 0
                per_q[ans.index][1] += 1
            if a.work_version:
                for k, it in enumerate(a.work_version.items or []):
                    items.setdefault(k, it)
        hardest = sorted(({"n": k + 1, "rate": ok / tot, "item": items.get(k)} for k, (ok, tot) in per_q.items() if tot),
                         key=lambda x: x["rate"])[:3]
        avg = round(sum(r["percent"] for r in rows) / len(rows))
        missing = [r for u, r in ids.items() if u not in best]
        return {"week": wk, "rows": rows, "avg": avg, "hardest": hardest, "missing": missing,
                "up": sum(1 for r in rows if r["delta"] and r["delta"] > 0),
                "down": sum(1 for r in rows if r["delta"] and r["delta"] < 0)}
    return None


def score_trend(user_id, limit=12):
    """Finished tests (not practice) in time order: [{date, percent, title}]."""
    rows = (Attempt.query.filter(Attempt.user_id == user_id, Attempt.finished_at.isnot(None),
                                 Attempt.work_version_id.isnot(None))
            .order_by(Attempt.finished_at.desc()).limit(limit).all())
    return [{"date": a.finished_at, "percent": a.percent, "title": a.work_version.title if a.work_version else ""}
            for a in reversed(rows)]


def attendance_summary(record, last=12):
    marks = list(record.attendance)[-last:]
    total = len(record.attendance)
    present = sum(1 for m in record.attendance if m.status == "present")
    late = sum(1 for m in record.attendance if m.status == "late")
    rate = round(100 * (present + 0.5 * late) / total) if total else None
    return {"marks": marks, "rate": rate, "total": total, "absent": sum(1 for m in record.attendance if m.status == "absent"),
            "late": late}

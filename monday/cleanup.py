"""One-time data fixes that must also reach databases already running (e.g. on Render).

Each fix runs once per database; AppMeta remembers it.
"""
from flask import current_app

from .extensions import db
from .models import AppMeta, Assignment, Attempt, StudentRecord, User, Work, WorkVersion

# Placeholder collections created by the demo seed (random questions, no real source).
DEMO_COLLECTIONS = [
    "ОРТ Май 2026", "Логарифмы и степени", "Геометрия: площади", "ОРТ Январь 2026", "SAT April 2024",
    "ЕНТ Июнь 2025", "ЕГЭ Профиль 2025", "ОГЭ Математика 2025", "CSCA Math Sample", "SAT March 2025",
    "ОРТ Апрель 2025", "Текстовые задачи", "ОРТ Пробник 2024", "Функции и графики",
]
DEMO_STUDENT = ("student@monday.kg", "Тима Манашов", "Student")


def _once(key, fn):
    key = f"fix:{key}"[:40]
    if db.session.get(AppMeta, key):
        return
    fn()
    db.session.add(AppMeta(key=key, value="done"))
    db.session.commit()


def remove_demo_collections():
    """Delete the seed's placeholder collections together with the attempts made on them."""
    works = (Work.query.join(User, Work.author_id == User.id)
             .filter(Work.kind == "collection", Work.title.in_(DEMO_COLLECTIONS), User.role != "admin").all())
    for w in works:
        version_ids = [v.id for v in WorkVersion.query.filter_by(work_id=w.id).all()]
        if version_ids:
            for att in Attempt.query.filter(Attempt.work_version_id.in_(version_ids)).all():
                db.session.delete(att)  # answers go with it
        for a in Assignment.query.filter_by(work_id=w.id).all():
            db.session.delete(a)
        db.session.delete(w)  # versions go with it


def rename_demo_student():
    email, old, new = DEMO_STUDENT
    user = User.query.filter_by(email=email).first()
    if not user:
        return
    if user.name == old:
        user.name = new
    for r in StudentRecord.query.filter_by(student_user_id=user.id, name=old).all():
        r.name = new


def mark_pack_sources():
    """Questions imported from content packs before Question.source existed get their pack id."""
    import json
    import os
    from .models import Question
    from .packs import PACK_DIR, available
    for pack_id in available():
        with open(os.path.join(PACK_DIR, pack_id + ".json"), encoding="utf-8") as f:
            texts = {q["text"] for q in json.load(f)["questions"]}
        for q in Question.query.filter(Question.source.is_(None), Question.text.in_(texts)).all():
            q.source = pack_id


def fix_goals_and_times():
    """Goals outside the exam's scale are cleared; test times are capped at the test's limit."""
    from .constants import EXAMS
    from .models import StudentProfile
    for p in StudentProfile.query.filter(StudentProfile.goal_score.isnot(None)).all():
        e = EXAMS.get(p.exam)
        if e and not e["min"] <= p.goal_score <= e["max"]:
            p.goal_score = None
    for a in Attempt.query.filter(Attempt.duration_sec.isnot(None), Attempt.work_version_id.isnot(None)).all():
        limit = a.work_version.time_limit_min if a.work_version else None
        if limit and a.duration_sec > limit * 60:
            a.duration_sec = limit * 60


def run_fixes():
    if not current_app.config.get("DATA_FIXES", True):
        return
    _once("demo-collections-removed", remove_demo_collections)
    _once("demo-student-renamed", rename_demo_student)
    _once("question-source", mark_pack_sources)
    _once("goals-times-capped", fix_goals_and_times)

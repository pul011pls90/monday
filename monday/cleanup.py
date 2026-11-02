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
DEMO_ADMIN = ("admin@monday.kg", "Темирлан Манашов", "Admin Monday")


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


def rename_demo_admin():
    """The admin account had a personal name; it signs ready-made content, so it is now «Admin Monday»."""
    email, old, new = DEMO_ADMIN
    user = User.query.filter_by(email=email, name=old).first()
    if user:
        user.name = new


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


def _delete_works(works):
    """Delete collections together with their assignments and the attempts made on them."""
    for w in works:
        version_ids = [v.id for v in WorkVersion.query.filter_by(work_id=w.id).all()]
        if version_ids:
            for att in Attempt.query.filter(Attempt.work_version_id.in_(version_ids)).all():
                db.session.delete(att)  # answers go with it
        for a in Assignment.query.filter_by(work_id=w.id).all():
            db.session.delete(a)
        db.session.delete(w)  # versions go with it


def remove_princeton_topic_sets():
    """The 10 short Princeton topic sets (5–22 questions) were replaced by full 44-question Chapter Tests.
    Their questions stay in the bank; only the collections go."""
    works = Work.query.filter(Work.kind == "collection", db.or_(
        Work.title.like("SAT Math Drill · % · Princeton Review 2025"),
        Work.title.like("SAT Math Practice · % · Princeton Review 2025"))).all()
    _delete_works(works)


OLD_ORT_PACKS = ("ort_monday_book_2026", "ort_monday_book_2026_b")


def replace_ort_monday_variants():
    """ORT variants 1–4 were rebuilt as one pack (ort_monday_mix_2026): topics mixed like the real ORT, 8 picture
    questions each. The old collections go (nobody had taken them); their questions leave the bank (kept as drafts,
    so nothing that may point at them breaks)."""
    from .models import Question
    old = Question.query.filter(Question.source.in_(OLD_ORT_PACKS)).all()
    old_ids = {q.id for q in old}
    works = [w for w in Work.query.filter_by(kind="collection").all()
             if old_ids & set(w.draft_question_ids or [])]
    _delete_works(works)
    for q in old:
        q.status = "draft"


def order_ort_monday_variants():
    """ORT variants 1–4: questions now go from easy to hard; a book item with non-real roots was swapped out."""
    from .packs import sync_pack
    sync_pack("ort_monday_mix_2026")


def csca_only_fitting_questions():
    """CSCA is taken in English and covers senior-school maths: Russian questions and middle-school skills
    (fractions, percents, basic geometry…) lose the CSCA tag. They stay in the bank for their other exams."""
    from .models import Question
    from .taxonomy import CSCA_BELOW_LEVEL
    for q in Question.query.all():
        if "CSCA" not in (q.exams or []):
            continue
        code = q.skill.code if q.skill else None
        if (q.language or "ru") != "en" or code is None or code in CSCA_BELOW_LEVEL:
            q.exams = [e for e in q.exams if e != "CSCA"]


def retag_ort_monday_word_mix():
    """ORT variants 1–4: most questions filed under «Смеси, сплавы, концентрации» weren't about mixtures
    (factorials, progressions, defined operations, word problems…); each now has the skill it actually trains."""
    from .models import AttemptAnswer, Question
    from .packs import sync_pack
    sync_pack("ort_monday_mix_2026")
    # past answers keep their own copy of the skill (journal, results): move them to the new one too
    for q in Question.query.filter_by(source="ort_monday_mix_2026").all():
        AttemptAnswer.query.filter(AttemptAnswer.question_id == q.id).update({"skill_id": q.skill_id})


def run_fixes():
    if not current_app.config.get("DATA_FIXES", True):
        return
    _once("demo-collections-removed", remove_demo_collections)
    _once("demo-student-renamed", rename_demo_student)
    _once("question-source", mark_pack_sources)
    _once("goals-times-capped", fix_goals_and_times)
    _once("princeton-topic-sets-removed", remove_princeton_topic_sets)
    _once("demo-admin-renamed", rename_demo_admin)
    _once("ort-monday-mixed-variants", replace_ort_monday_variants)
    _once("ort-monday-easy-to-hard", order_ort_monday_variants)
    _once("csca-fitting-questions", csca_only_fitting_questions)
    _once("ort-monday-word-mix-retagged-2", retag_ort_monday_word_mix)

#!/usr/bin/env python3
"""Idempotent seeder for the 14-unit Khan-style SAT Math Course & Practice Player."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from monday import create_app, formulas  # noqa: E402
from monday.models import ContentNode, CourseLesson, CourseMastery, CourseUnit, db, utcnow  # noqa: E402
from monday.services import pool_index  # noqa: E402
from scripts.course_articles import (  # noqa: E402
    CSCA_SIM_ARTICLES,
    CSCA_TOPIC_ARTICLES,
    SAT_CHALLENGE_ARTICLES,
    SAT_TOPIC_ARTICLES,
    SAT_UNIT1_ARTICLES,
)
from scripts.csca_course_data import CSCA_UNIT1_LESSONS, CSCA_UNIT_DEFS, CSCA_UNIT_TOPICS  # noqa: E402

UNIT_DEFS = [
    (1, "about-sat", "intro", "about", "О SAT", "Знакомство с Digital SAT, Bluebook, Desmos и структурой 44 вопросов."),
    # Foundations (d=1)
    (2, "foundations-algebra", "foundation", "algebra", "База · Алгебра", "Линейные уравнения, прямые, системы и неравенства."),
    (3, "foundations-psda", "foundation", "psda", "База · Анализ данных", "Проценты, отношения, таблицы, статистика и вероятность."),
    (4, "foundations-advanced", "foundation", "advanced", "База · Продвинутая математика", "Степени, корни, многочлены, квадратные и показательные функции."),
    (5, "foundations-geometry", "foundation", "geometry", "База · Геометрия и тригонометрия", "Углы, треугольники, окружности, объёмы и базовая тригонометрия."),
    # Medium (d=2)
    (6, "medium-algebra", "medium", "algebra", "Средний · Алгебра", "Комбинированные системы, текстовые задачи и параметры прямых."),
    (7, "medium-psda", "medium", "psda", "Средний · Анализ данных", "Последовательные проценты, линии тренда, выборки и условная вероятность."),
    (8, "medium-advanced", "medium", "advanced", "Средний · Продвинутая математика", "Дискриминант, парабола, преобразования графиков и нелинейные системы."),
    (9, "medium-geometry", "medium", "geometry", "Средний · Геометрия и тригонометрия", "Подобие, дуги и секторы, уравнение окружности и тригонометрия."),
    # Advanced (d=3)
    (10, "advanced-algebra", "advanced", "algebra", "Продвинутый · Алгебра", "Сложные системы с параметрами, модули и нестандартные текстовые задачи."),
    (11, "advanced-psda", "advanced", "psda", "Продвинутый · Анализ данных", "Стандартное отклонение, погрешность выборки и оценка выводов."),
    (12, "advanced-advanced", "advanced", "advanced", "Продвинутый · Продвинутая математика", "Рациональные и иррациональные уравнения, комплексные корни и композиция функций."),
    (13, "advanced-geometry", "advanced", "geometry", "Продвинутый · Геометрия и тригонометрия", "Радианы, кофункции $\\sin(x)=\\cos(90^\\circ-x)$, стереометрия и окружности."),
    # Challenge
    (14, "challenge-700", "challenge", "challenge", "Челлендж 700+", "Задачи повышенной сложности из второго адаптивного модуля SAT."),
]

DOMAIN_TOPICS = {
    "algebra": [
        ("linear-eq", "Линейные уравнения", "sat_algebra", "lines", [51, 66]),
        ("linear-func", "Линейные функции", "sat_algebra", "lines", [72, 97, 96]),
        ("systems", "Системы уравнений", "sat_algebra", "systems", [57]),
        ("inequalities", "Неравенства и модуль", "sat_algebra", "absolute", [59, 56, 62]),
        ("word-problems", "Текстовые задачи", "sat_algebra", "distance", [63, 65]),
    ],
    "psda": [
        ("ratios-units", "Отношения и пропорции", "sat_data", "ratios", [37, 66]),
        ("percents", "Проценты и изменения", "sat_data", "percents", [36]),
        ("stats", "Среднее и медиана", "sat_data", "statistics", [115, 116]),
        ("tables-scatter", "Таблицы и графики", "sat_data", "statistics", [117, 118]),
        ("prob-sampling", "Вероятность и выборки", "sat_data", "probability", [113, 114, 119, 120]),
    ],
    "advanced": [
        ("factoring-poly", "Многочлены", "sat_advanced", "factoring", [48, 49, 50]),
        ("powers-roots", "Степени и корни", "sat_advanced", "exponents", [42, 43, 44]),
        ("quadratics", "Квадратные уравнения", "sat_advanced", "quadratics", [52, 73]),
        ("exponential", "Показательные функции", "sat_advanced", "exponential", [75, 70, 67]),
        ("nonlinear-rat", "Нелинейные системы", "sat_advanced", "polynomials", [54, 55, 58]),
    ],
    "geometry": [
        ("angles-tri", "Углы и треугольники", "sat_geometry", "triangles", [82, 83, 84, 85, 86]),
        ("polygons-area", "Площади и объёмы", "sat_geometry", "volumes", [88, 89, 93, 94]),
        ("circles", "Окружности и дуги", "sat_geometry", "circles", [90, 91, 98]),
        ("trig-rad", "Тригонометрия", "sat_geometry", "trig", [100, 101, 102]),
    ],
}

CHALLENGE_TITLES = {
    "algebra": "Челлендж: Алгебра 700+",
    "psda": "Челлендж: Анализ данных 700+",
    "advanced": "Челлендж: Продвинутая математика 700+",
    "geometry": "Челлендж: Геометрия и тригонометрия 700+",
}

UNIT1_LESSONS = [
    {
        "slug": "welcome-sat",
        "title_ru": "Привет! Что такое Digital SAT и зачем он нужен",
        "kind": "article",
        "article_md": SAT_UNIT1_ARTICLES["welcome-sat"],
        "hints": ["Не пропускайте базовые разделы, даже если целитесь на 750+ — они дают половину баллов экзамена."],
    },
    {
        "slug": "digital-sat-bluebook",
        "title_ru": "Как устроен тест, адаптивность и правила ввода",
        "kind": "article",
        "article_md": SAT_UNIT1_ARTICLES["digital-sat-bluebook"],
        "desmos_preset": {"expr": "y = 2x + 1"},
        "hints": ["В Модуле 1 решайте сначала быстрые задачи, а сложные отмечайте флагом и возвращайтесь позже."],
    },
    {
        "slug": "math-44-breakdown",
        "title_ru": "44 вопроса математики: что именно проверяют",
        "kind": "article",
        "article_md": SAT_UNIT1_ARTICLES["math-44-breakdown"],
        "hints": ["В свободном вводе никогда не пишите смешанные дроби через пробел: вместо `2 1/2` пишите `5/2` или `2.5`."],
    },
    {
        "slug": "unit-1-check",
        "title_ru": "Проверка: формат Digital SAT",
        "kind": "quiz",
        "article_md": SAT_UNIT1_ARTICLES["unit-1-check"],
        "inline_quiz": [
            {
                "id": "u1_q1",
                "prompt": "Сколько всего вопросов и времени в секции математики Digital SAT?",
                "type": "choice",
                "options": ["44 вопроса — 2 модуля по 35 мин", "58 вопросов — 80 мин", "30 вопросов — 45 мин", "50 вопросов — 2 модуля по 30 мин"],
                "answer": "44 вопроса — 2 модуля по 35 мин",
                "hints": ["В каждом из двух модулей по 22 вопроса.", "На каждый модуль даётся по 35 минут."],
                "explain": "Digital SAT Math состоит из 2 адаптивных модулей по 22 вопроса — по 35 минут на каждый, итого 44 вопроса.",
            },
            {
                "id": "u1_q2",
                "prompt": "Какая доля вопросов приходится суммарно на Алгебру и Продвинутую математику?",
                "type": "choice",
                "options": ["Около 30%", "Около 50%", "Около 70% — 26–30 вопросов", "100%"],
                "answer": "Около 70% — 26–30 вопросов",
                "hints": ["На каждый из двух главных разделов приходится по 13–15 вопросов."],
                "explain": "13–15 вопросов по Алгебре и 13–15 по Продвинутой математике дают 26–30 из 44 вопросов, то есть около 70%.",
            },
            {
                "id": "u1_q3",
                "prompt": "Как правильно записать ответ $2\\frac{1}{2}$ в поле свободного ввода (Grid-In / SPR)? Запишите десятичной дробью.",
                "type": "number",
                "answer": "2.5",
                "hints": ["Смешанные дроби вводить нельзя — переведите в десятичную дробь или неправильную (`5/2`)."],
                "explain": "В Bluebook $2\\frac{1}{2}$ записывается как `2.5` или `5/2`.",
            },
        ],
    },
]


def _pick_questions(pool_by_sd: dict[tuple[int, int], list[int]], skill_ids: list[int], diff: int, want: int = 5) -> list[int]:
    picked: list[int] = []
    # 1. Exact difficulty first
    for sid in skill_ids:
        for qid in pool_by_sd.get((sid, diff), []):
            if qid not in picked:
                picked.append(qid)
                if len(picked) >= want:
                    return picked
    # 2. Fallback to adjacent difficulties so every lesson has real questions
    fallback_order = [2, 1, 3] if diff == 1 else ([1, 3] if diff == 2 else [2, 1])
    for d in fallback_order:
        for sid in skill_ids:
            for qid in pool_by_sd.get((sid, d), []):
                if qid not in picked:
                    picked.append(qid)
                    if len(picked) >= want:
                        return picked
    return picked


def _build_pool(exam: str, valid_qids: set[int]) -> tuple[dict[tuple[int, int], list[int]], list[int], list[int]]:
    pool_by_sd: dict[tuple[int, int], list[int]] = {}
    all_d3: list[int] = []
    all_valid: list[int] = []
    for qid, sid, diff in pool_index(exam):
        if qid not in valid_qids:
            continue
        d = diff or 2
        pool_by_sd.setdefault((sid, d), []).append(qid)
        if qid not in all_valid:
            all_valid.append(qid)
        if d == 3:
            all_d3.append(qid)
    return pool_by_sd, all_d3, all_valid


def _upsert_unit(exam: str, num: int, slug: str, tier: str, domain: str, title_ru: str, desc_ru: str,
                 lessons_spec: list[dict], stats: dict, dry_run: bool, force: bool) -> None:
    u_row = CourseUnit.query.filter_by(exam=exam, slug=slug).first()
    if u_row is None:
        stats["units_created"] += 1
        if not dry_run:
            u_row = CourseUnit(exam=exam, number=num, slug=slug, title_ru=title_ru, tier=tier, domain=domain, description_ru=desc_ru, updated_at=utcnow())
            db.session.add(u_row)
            db.session.flush()
    else:
        if u_row.number != num or u_row.title_ru != title_ru or u_row.tier != tier or (force and u_row.description_ru != desc_ru):
            stats["units_updated"] += 1
            if not dry_run:
                u_row.number = num
                u_row.title_ru = title_ru
                u_row.tier = tier
                u_row.domain = domain
                if force or not u_row.description_ru:
                    u_row.description_ru = desc_ru
                u_row.updated_at = utcnow()
        else:
            stats["unchanged"] += 1

    for lspec in lessons_spec:
        l_row = CourseLesson.query.filter_by(unit_id=u_row.id, slug=lspec["slug"]).first() if u_row else None
        qids_str = json.dumps(lspec["question_ids"])
        sids_str = json.dumps(lspec["skill_ids"])
        hints_str = json.dumps(lspec["hints"], ensure_ascii=False)
        iq_str = json.dumps(lspec["inline_quiz"], ensure_ascii=False)
        desmos_str = json.dumps(lspec["desmos_preset"], ensure_ascii=False) if lspec["desmos_preset"] else ""
        if l_row is None:
            stats["lessons_created"] += 1
            if not dry_run and u_row is not None:
                db.session.add(CourseLesson(
                    unit_id=u_row.id,
                    slug=lspec["slug"],
                    position=lspec["position"],
                    title_ru=lspec["title_ru"],
                    kind=lspec["kind"],
                    article_md=lspec["article_md"],
                    hints_json=hints_str,
                    desmos_preset_json=desmos_str,
                    formula_tpl=lspec["formula_tpl"],
                    formula_topic_id=lspec["formula_topic_id"],
                    question_ids_json=qids_str,
                    inline_quiz_json=iq_str,
                    skill_ids_json=sids_str,
                    difficulty=lspec["difficulty"],
                    updated_at=utcnow(),
                ))
        else:
            changed = False
            for attr, val in (
                ("position", lspec["position"]),
                ("kind", lspec["kind"]),
                ("formula_tpl", lspec["formula_tpl"]),
                ("formula_topic_id", lspec["formula_topic_id"]),
                ("skill_ids_json", sids_str),
                ("difficulty", lspec["difficulty"]),
            ):
                if getattr(l_row, attr) != val:
                    changed = True
                    if not dry_run:
                        setattr(l_row, attr, val)
            force_pairs = (
                ("title_ru", lspec["title_ru"]),
                ("article_md", lspec["article_md"]),
                ("question_ids_json", qids_str),
                ("inline_quiz_json", iq_str),
            ) if force else ()
            for attr, val in force_pairs:
                if getattr(l_row, attr) != val:
                    changed = True
                    if not dry_run:
                        setattr(l_row, attr, val)
            if not l_row.article_md and lspec["article_md"]:
                changed = True
                if not dry_run:
                    l_row.article_md = lspec["article_md"]
            if (not l_row.question_ids_json or l_row.question_ids_json == "[]") and lspec["question_ids"]:
                changed = True
                if not dry_run:
                    l_row.question_ids_json = qids_str
            if (not l_row.inline_quiz_json or l_row.inline_quiz_json == "[]") and lspec["inline_quiz"]:
                changed = True
                if not dry_run:
                    l_row.inline_quiz_json = iq_str
            if changed:
                stats["lessons_updated"] += 1
                if not dry_run:
                    l_row.updated_at = utcnow()
            else:
                stats["unchanged"] += 1


def _seed_csca(valid_qids: set[int], stats: dict, dry_run: bool, force: bool) -> None:
    pool_by_sd, _d3, all_valid = _build_pool("CSCA", valid_qids)
    for num, slug, tier, domain, title_ru, desc_ru in CSCA_UNIT_DEFS:
        lessons_spec: list[dict] = []
        if slug == "csca-about":
            for pos, ldef in enumerate(CSCA_UNIT1_LESSONS, start=1):
                lessons_spec.append({
                    "slug": ldef["slug"],
                    "position": pos,
                    "title_ru": ldef["title_ru"],
                    "kind": ldef["kind"],
                    "article_md": ldef["article_md"],
                    "hints": ldef.get("hints", []),
                    "desmos_preset": None,
                    "inline_quiz": ldef.get("inline_quiz", []),
                    "formula_tpl": "",
                    "formula_topic_id": "",
                    "question_ids": [],
                    "skill_ids": [],
                    "difficulty": 1,
                })
        elif slug == "csca-simulation":
            sim_qids = all_valid[:48]
            lessons_spec.append({
                "slug": "csca-sim-48",
                "position": 1,
                "title_ru": "Симуляция CSCA: 48 вопросов / 60 минут",
                "kind": "quiz",
                "article_md": CSCA_SIM_ARTICLES["csca-sim-48"],
                "hints": ["Если задача занимает больше 90 секунд, отметьте лучший вариант и двигайтесь дальше."],
                "desmos_preset": None,
                "inline_quiz": [],
                "formula_tpl": "",
                "formula_topic_id": "",
                "question_ids": sim_qids,
                "skill_ids": [],
                "difficulty": 3,
            })
            lessons_spec.append({
                "slug": "csca-sim-review",
                "position": 2,
                "title_ru": "Разбор ошибок и стратегия CSCA",
                "kind": "article",
                "article_md": CSCA_SIM_ARTICLES["csca-sim-review"],
                "hints": ["Откройте вкладку «Журнал», чтобы отработать все сохранённые ошибки из симуляции."],
                "desmos_preset": None,
                "inline_quiz": [],
                "formula_tpl": "",
                "formula_topic_id": "",
                "question_ids": [],
                "skill_ids": [],
                "difficulty": 2,
            })
        else:
            unit_topics = CSCA_UNIT_TOPICS[slug]
            unit_sids: list[int] = []
            for pos, (lslug, ltitle, ftpl, ftopic, sids, diff) in enumerate(unit_topics, start=1):
                unit_sids.extend(sids)
                qids = _pick_questions(pool_by_sd, sids, diff, want=5)
                article = CSCA_TOPIC_ARTICLES[lslug]
                lessons_spec.append({
                    "slug": lslug,
                    "position": pos,
                    "title_ru": ltitle,
                    "kind": "practice",
                    "article_md": article,
                    "hints": ["На CSCA калькулятор запрещён — упрощайте дроби и корни вручную.", "Откройте панель «Формулы темы», если забыли тождество."],
                    "desmos_preset": None,
                    "inline_quiz": [],
                    "formula_tpl": ftpl,
                    "formula_topic_id": ftopic,
                    "question_ids": qids,
                    "skill_ids": sids,
                    "difficulty": diff,
                })
            quiz_qids = _pick_questions(pool_by_sd, unit_sids, 2 if tier == "foundation" else 3, want=6)
            lessons_spec.append({
                "slug": f"{slug}-quiz",
                "position": len(lessons_spec) + 1,
                "title_ru": "Тест раздела — 6 задач",
                "kind": "quiz",
                "article_md": f"Итоговый тест раздела **«{title_ru}»**. Наберите **80%+**, чтобы закрепить статус `Освоено`.",
                "hints": ["Решайте в темпе экзамена — около 75 секунд на задачу."],
                "desmos_preset": None,
                "inline_quiz": [],
                "formula_tpl": unit_topics[0][2],
                "formula_topic_id": unit_topics[0][3],
                "question_ids": quiz_qids,
                "skill_ids": unit_sids[:4],
                "difficulty": 2 if tier == "foundation" else 3,
            })
        _upsert_unit("CSCA", num, slug, tier, domain, title_ru, desc_ru, lessons_spec, stats, dry_run, force)


def seed_course(dry_run: bool = False, force: bool = False) -> dict:
    for model in (CourseUnit, CourseLesson, CourseMastery):
        model.__table__.create(bind=db.engine, checkfirst=True)

    from monday.models import Question
    valid_qids = {
        r[0]
        for r in db.session.query(Question.id).filter(
            Question.text.isnot(None), db.func.length(db.func.trim(Question.text)) > 0
        ).all()
    }
    pool_by_sd, all_d3, _all_valid = _build_pool("SAT", valid_qids)
    stats = {"units_created": 0, "units_updated": 0, "lessons_created": 0, "lessons_updated": 0, "unchanged": 0}

    for num, slug, tier, domain, title_ru, desc_ru in UNIT_DEFS:
        u_row = CourseUnit.query.filter_by(exam="SAT", slug=slug).first()
        if u_row is None:
            stats["units_created"] += 1
            if not dry_run:
                u_row = CourseUnit(exam="SAT", number=num, slug=slug, title_ru=title_ru, tier=tier, domain=domain, description_ru=desc_ru, updated_at=utcnow())
                db.session.add(u_row)
                db.session.flush()
        else:
            if u_row.number != num or u_row.title_ru != title_ru or u_row.tier != tier or (force and u_row.description_ru != desc_ru):
                stats["units_updated"] += 1
                if not dry_run:
                    u_row.number = num
                    u_row.title_ru = title_ru
                    u_row.tier = tier
                    u_row.domain = domain
                    if force or not u_row.description_ru:
                        u_row.description_ru = desc_ru
                    u_row.updated_at = utcnow()
            else:
                stats["unchanged"] += 1

        # Build lessons list for this unit
        lessons_spec: list[dict] = []
        if slug == "about-sat":
            for pos, ldef in enumerate(UNIT1_LESSONS, start=1):
                lessons_spec.append({
                    "slug": ldef["slug"],
                    "position": pos,
                    "title_ru": ldef["title_ru"],
                    "kind": ldef["kind"],
                    "article_md": ldef["article_md"],
                    "hints": ldef.get("hints", []),
                    "desmos_preset": ldef.get("desmos_preset"),
                    "inline_quiz": ldef.get("inline_quiz", []),
                    "formula_tpl": "",
                    "formula_topic_id": "",
                    "question_ids": [],
                    "skill_ids": [],
                    "difficulty": 1,
                })
        elif slug == "challenge-700":
            for pos, dom_key in enumerate(("algebra", "psda", "advanced", "geometry"), start=1):
                dom_topics = DOMAIN_TOPICS[dom_key]
                sids = [sid for _ls, _lt, _ft, _fid, s_list in dom_topics for sid in s_list]
                qids = _pick_questions(pool_by_sd, sids, 3, want=5)
                lessons_spec.append({
                    "slug": f"challenge-{dom_key}",
                    "position": pos,
                    "title_ru": CHALLENGE_TITLES[dom_key],
                    "kind": "practice",
                    "article_md": SAT_CHALLENGE_ARTICLES[dom_key],
                    "hints": ["Если выражение сложное, попробуйте подставить $x = 2$ или построить график в Desmos."],
                    "desmos_preset": {"expr": "y = x^2 - 4x + 3"},
                    "inline_quiz": [],
                    "formula_tpl": dom_topics[0][2],
                    "formula_topic_id": dom_topics[0][3],
                    "question_ids": qids,
                    "skill_ids": sids[:4],
                    "difficulty": 3,
                })
            # Final challenge quiz
            lessons_spec.append({
                "slug": "unit-quiz",
                "position": len(lessons_spec) + 1,
                "title_ru": "Финальный тест раздела — 8 задач",
                "kind": "quiz",
                "article_md": "8 смешанных задач уровня 700+. Зачёт «Освоено» — от **80%**.",
                "hints": ["Следите за временем и перепроверяйте знак в свободных ответах."],
                "desmos_preset": None,
                "inline_quiz": [],
                "formula_tpl": "",
                "formula_topic_id": "",
                "question_ids": all_d3[:8],
                "skill_ids": [],
                "difficulty": 3,
            })
        else:
            diff = 1 if tier == "foundation" else (2 if tier == "medium" else 3)
            dom_topics = DOMAIN_TOPICS[domain]
            unit_sids: list[int] = []
            for pos, (lslug, ltitle, ftpl, ftopic, sids) in enumerate(dom_topics, start=1):
                unit_sids.extend(sids)
                qids = _pick_questions(pool_by_sd, sids, diff, want=5)
                article = SAT_TOPIC_ARTICLES[(tier, lslug)]
                lessons_spec.append({
                    "slug": lslug,
                    "position": pos,
                    "title_ru": ltitle,
                    "kind": "practice",
                    "article_md": article,
                    "hints": ["Откройте панель «Формулы темы», если забыли коэффициент.", "При наличии параметров проверьте график в Desmos."],
                    "desmos_preset": {"expr": "y = mx + b"} if domain == "algebra" else None,
                    "inline_quiz": [],
                    "formula_tpl": ftpl,
                    "formula_topic_id": ftopic,
                    "question_ids": qids,
                    "skill_ids": sids,
                    "difficulty": diff,
                })
            # Unit quiz (6 mixed questions from the unit's skills)
            quiz_qids = _pick_questions(pool_by_sd, unit_sids, diff, want=6)
            lessons_spec.append({
                "slug": "unit-quiz",
                "position": len(lessons_spec) + 1,
                "title_ru": "Тест раздела — 6 задач",
                "kind": "quiz",
                "article_md": "6 смешанных задач по всем темам раздела. Порог для статуса «Освоено» — **80%**.",
                "hints": ["Не спешите: в тесте раздела смешаны все темы этого юнита."],
                "desmos_preset": None,
                "inline_quiz": [],
                "formula_tpl": dom_topics[0][2],
                "formula_topic_id": dom_topics[0][3],
                "question_ids": quiz_qids,
                "skill_ids": unit_sids[:4],
                "difficulty": diff,
            })

        for lspec in lessons_spec:
            l_row = CourseLesson.query.filter_by(unit_id=u_row.id, slug=lspec["slug"]).first() if u_row else None
            qids_str = json.dumps(lspec["question_ids"])
            sids_str = json.dumps(lspec["skill_ids"])
            hints_str = json.dumps(lspec["hints"], ensure_ascii=False)
            iq_str = json.dumps(lspec["inline_quiz"], ensure_ascii=False)
            desmos_str = json.dumps(lspec["desmos_preset"], ensure_ascii=False) if lspec["desmos_preset"] else ""
            if l_row is None:
                stats["lessons_created"] += 1
                if not dry_run and u_row is not None:
                    db.session.add(CourseLesson(
                        unit_id=u_row.id,
                        slug=lspec["slug"],
                        position=lspec["position"],
                        title_ru=lspec["title_ru"],
                        kind=lspec["kind"],
                        article_md=lspec["article_md"],
                        hints_json=hints_str,
                        desmos_preset_json=desmos_str,
                        formula_tpl=lspec["formula_tpl"],
                        formula_topic_id=lspec["formula_topic_id"],
                        question_ids_json=qids_str,
                        inline_quiz_json=iq_str,
                        skill_ids_json=sids_str,
                        difficulty=lspec["difficulty"],
                        updated_at=utcnow(),
                    ))
            else:
                changed = False
                for attr, val in (
                    ("position", lspec["position"]),
                    ("kind", lspec["kind"]),
                    ("formula_tpl", lspec["formula_tpl"]),
                    ("formula_topic_id", lspec["formula_topic_id"]),
                    ("skill_ids_json", sids_str),
                    ("difficulty", lspec["difficulty"]),
                ):
                    if getattr(l_row, attr) != val:
                        changed = True
                        if not dry_run:
                            setattr(l_row, attr, val)
                # Preserve admin edits unless --force is passed
                force_pairs = (
                    ("title_ru", lspec["title_ru"]),
                    ("article_md", lspec["article_md"]),
                    ("question_ids_json", qids_str),
                    ("inline_quiz_json", iq_str),
                ) if force else ()
                for attr, val in force_pairs:
                    if getattr(l_row, attr) != val:
                        changed = True
                        if not dry_run:
                            setattr(l_row, attr, val)
                if not l_row.article_md and lspec["article_md"]:
                    changed = True
                    if not dry_run:
                        l_row.article_md = lspec["article_md"]
                if (not l_row.question_ids_json or l_row.question_ids_json == "[]") and lspec["question_ids"]:
                    changed = True
                    if not dry_run:
                        l_row.question_ids_json = qids_str
                if (not l_row.inline_quiz_json or l_row.inline_quiz_json == "[]") and lspec["inline_quiz"]:
                    changed = True
                    if not dry_run:
                        l_row.inline_quiz_json = iq_str
                if changed:
                    stats["lessons_updated"] += 1
                    if not dry_run:
                        l_row.updated_at = utcnow()
                else:
                    stats["unchanged"] += 1

    _seed_csca(valid_qids, stats, dry_run, force)

    if not dry_run:
        db.session.commit()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Idempotently seed 14-unit SAT Math course.")
    parser.add_argument("--dry-run", action="store_true", help="Report planned changes without writing to DB.")
    parser.add_argument("--force", action="store_true", help="Overwrite lesson titles, articles, and question lists from seeder.")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        stats = seed_course(dry_run=args.dry_run, force=args.force)
        print(json.dumps({"dry_run": args.dry_run, **stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

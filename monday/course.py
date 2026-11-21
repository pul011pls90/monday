"""Khan Academy-style SAT Math Course Overview, Interactive Player, Mastery Sync & Admin Lesson Builder."""
from __future__ import annotations

import json
import re
from fractions import Fraction

from flask import Blueprint, abort, jsonify, render_template, request, session, url_for
from flask_login import current_user
from markupsafe import Markup, escape

from . import formulas
from .access import admin_required, student_required
from .models import (
    Attempt,
    AttemptAnswer,
    CourseLesson,
    CourseMastery,
    CourseUnit,
    Question,
    db,
    utcnow,
)

bp = Blueprint("course", __name__)

MASTERY_ORDER = {"not_started": 0, "familiar": 1, "proficient": 2, "mastered": 3}
MASTERY_LABELS = {
    "not_started": "Не начато",
    "familiar": "Знаком",
    "proficient": "Уверенно",
    "mastered": "Освоено",
}

_MATH_SPAN_RE = re.compile(r"(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$)")


def _render_inline_md(line: str) -> str:
    """Escape HTML and convert **bold**, *italic*, `code` while preserving $...$ math."""
    parts = _MATH_SPAN_RE.split(line or "")
    out: list[str] = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            out.append(str(escape(part)))
        else:
            s = str(escape(part))
            s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
            s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
            s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
            out.append(s)
    return "".join(out)


def render_course_html(raw: str) -> Markup:
    """Convert course Markdown (headings, bullet lists, bold/code) to semantic HTML without breaking KaTeX."""
    lines = (raw or "").replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    para_buf: list[str] = []
    list_buf: list[str] = []
    table_buf: list[list[str]] = []

    def flush_para() -> None:
        if para_buf:
            blocks.append("<p>" + "<br>".join(_render_inline_md(x) for x in para_buf) + "</p>")
            para_buf.clear()

    def flush_list() -> None:
        if list_buf:
            items = "".join(f"<li>{_render_inline_md(x)}</li>" for x in list_buf)
            blocks.append(f"<ul>{items}</ul>")
            list_buf.clear()

    def flush_table() -> None:
        if not table_buf:
            return
        rows = [r for r in table_buf if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
        table_buf.clear()
        if not rows:
            return
        head = "".join(f"<th>{_render_inline_md(c)}</th>" for c in rows[0])
        body = "".join(
            "<tr>" + "".join(f"<td>{_render_inline_md(c)}</td>" for c in r) + "</tr>"
            for r in rows[1:]
        )
        blocks.append(f'<div class="cp-table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_para()
            flush_list()
            flush_table()
            continue
        if stripped.startswith("|") and stripped.endswith("|") and "|" in stripped[1:-1]:
            flush_para()
            flush_list()
            cells = [c.strip() for c in stripped[1:-1].split("|")]
            table_buf.append(cells)
            continue
        flush_table()
        if stripped.startswith("### ") or stripped.startswith("## "):
            flush_para()
            flush_list()
            heading_txt = stripped.lstrip("#").strip()
            blocks.append(f"<h3>{_render_inline_md(heading_txt)}</h3>")
            continue
        if stripped.startswith("• ") or stripped.startswith("- ") or stripped.startswith("* "):
            flush_para()
            list_buf.append(stripped[2:].strip())
            continue
        flush_list()
        para_buf.append(stripped)

    flush_para()
    flush_list()
    flush_table()
    return Markup("\n".join(blocks))


def _load_topic_formulas(tpl_key: str, topic_id: str) -> list[dict]:
    if not tpl_key:
        return []
    tpl = formulas.find_template(tpl_key)
    if not tpl:
        return []
    topic = next((t for t in tpl.get("topics", []) if t.get("id") == topic_id), None)
    if not topic and tpl.get("topics"):
        topic = tpl["topics"][0]
    return (topic or {}).get("formulas") or []


def _youtube_embed(raw_url: str) -> str:
    s = (raw_url or "").strip()
    if not s:
        return ""
    m = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{6,20})", s)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    return ""


def _parse_num(raw: str) -> float | None:
    s = (raw or "").strip().replace(",", ".")
    if not s:
        return None
    try:
        if "/" in s:
            return float(Fraction(s))
        return float(s)
    except Exception:
        return None


def _answers_match(given: str, expected: str, q_type: str) -> bool:
    g = (given or "").strip()
    if not g:
        return False
    exp_list = [e.strip() for e in (expected or "").split("|") if e.strip()]
    if q_type == "choice":
        return any(g.casefold() == e.casefold() for e in exp_list)
    gn = _parse_num(g)
    for e in exp_list:
        if g.casefold() == e.casefold():
            return True
        en = _parse_num(e)
        if gn is not None and en is not None and abs(gn - en) < 1e-4:
            return True
    return False


def build_course(user_id: int, exam: str = "SAT", q: str = "") -> dict:
    """Return Khan-style course overview + Continue card + 4-tier mastery for SAT or CSCA."""
    exam_code = (exam or "SAT").upper()
    units_db = CourseUnit.query.filter_by(exam=exam_code).order_by(CourseUnit.number.asc()).all()
    if not units_db:
        from scripts.seed_course import seed_course
        seed_course(dry_run=False)
        units_db = CourseUnit.query.filter_by(exam=exam_code).order_by(CourseUnit.number.asc()).all()

    mastery_all = CourseMastery.query.filter_by(user_id=user_id).all()
    mastery_by_id = {r.lesson_id: r for r in mastery_all if r.lesson_id is not None}
    mastery_by_key = {r.lesson_key: r for r in mastery_all if r.lesson_key}
    q_norm = (q or "").strip().lower()

    units_out = []
    continue_card = None
    total_lessons = 0
    mastered_lessons = 0

    for u in units_db:
        lessons_db = u.lessons.order_by(CourseLesson.position.asc()).all()
        lessons_out = []
        u_mastered = 0
        u_proficient = 0
        u_familiar = 0
        for l in lessons_db:
            lkey = f"{u.slug}:{l.slug}"
            if q_norm and q_norm not in (l.title_ru + " " + u.title_ru).lower():
                continue
            m_row = mastery_by_id.get(l.id) or mastery_by_key.get(lkey)
            level = m_row.level if m_row else "not_started"
            total_lessons += 1
            if level == "mastered":
                u_mastered += 1
                mastered_lessons += 1
            elif level == "proficient":
                u_proficient += 1
            elif level == "familiar":
                u_familiar += 1

            item = {
                "slug": l.slug,
                "key": lkey,
                "title": l.title_ru,
                "kind": l.kind,
                "level": level,
                "level_label": MASTERY_LABELS.get(level, "Не начато"),
                "best_score": m_row.best_score if m_row else 0,
                "total_q": m_row.total_q if m_row else 0,
                "url": url_for("course.player", exam=exam_code, unit_slug=u.slug, lesson_slug=l.slug),
            }
            lessons_out.append(item)
            if continue_card is None and level != "mastered":
                continue_card = {
                    "unit_number": u.number,
                    "unit_title": u.title_ru,
                    "lesson_title": l.title_ru,
                    "level_label": item["level_label"],
                    "url": item["url"],
                }

        if not lessons_out:
            continue
        units_out.append({
            "number": u.number,
            "slug": u.slug,
            "title": u.title_ru,
            "tier": u.tier,
            "domain": u.domain,
            "description": u.description_ru,
            "lessons": lessons_out,
            "mastered_count": u_mastered,
            "proficient_count": u_proficient,
            "familiar_count": u_familiar,
            "total_count": len(lessons_out),
        })

    if continue_card is None and units_out and units_out[0]["lessons"]:
        first_l = units_out[0]["lessons"][0]
        continue_card = {
            "unit_number": units_out[0]["number"],
            "unit_title": units_out[0]["title"],
            "lesson_title": first_l["title"],
            "level_label": first_l["level_label"],
            "url": first_l["url"],
        }

    return {
        "units": units_out,
        "continue_card": continue_card,
        "total_lessons": total_lessons,
        "mastered_lessons": mastered_lessons,
    }


def build_sat_course(user_id: int, q: str = "") -> dict:
    """Backward-compatible alias for SAT course overview."""
    return build_course(user_id, exam="SAT", q=q)


@bp.get("/roadmap/<exam>/<unit_slug>/<lesson_slug>")
@student_required
def player(exam: str, unit_slug: str, lesson_slug: str):
    unit = CourseUnit.query.filter_by(exam=exam.upper(), slug=unit_slug).first_or_404()
    lessons = unit.lessons.order_by(CourseLesson.position.asc()).all()
    lesson = next((x for x in lessons if x.slug == lesson_slug), None)
    if lesson is None:
        abort(404)
    session["course_run"] = {"key": f"{exam.upper()}:{unit.slug}:{lesson.slug}", "results": {}}

    mastery_all = CourseMastery.query.filter_by(user_id=current_user.id).all()
    mastery_by_id = {r.lesson_id: r.level for r in mastery_all if r.lesson_id is not None}
    mastery_by_key = {r.lesson_key: r.level for r in mastery_all if r.lesson_key}
    sidebar_lessons = []
    next_url = None
    found_cur = False
    for l in lessons:
        lkey = f"{unit.slug}:{l.slug}"
        lvl = mastery_by_id.get(l.id) or mastery_by_key.get(lkey, "not_started")
        url = url_for("course.player", exam=exam.upper(), unit_slug=unit.slug, lesson_slug=l.slug)
        if found_cur and next_url is None:
            next_url = url
        if l.id == lesson.id:
            found_cur = True
        sidebar_lessons.append({
            "slug": l.slug,
            "title": l.title_ru,
            "kind": l.kind,
            "level": lvl,
            "level_label": MASTERY_LABELS.get(lvl, "Не начато"),
            "is_current": l.id == lesson.id,
            "url": url,
        })

    if next_url is None:
        next_unit = CourseUnit.query.filter(CourseUnit.exam == exam.upper(), CourseUnit.number > unit.number).order_by(CourseUnit.number.asc()).first()
        if next_unit:
            first_next = next_unit.lessons.order_by(CourseLesson.position.asc()).first()
            if first_next:
                next_url = url_for("course.player", exam=exam.upper(), unit_slug=next_unit.slug, lesson_slug=first_next.slug)

    # Load inline or DB questions
    questions_out = []
    try:
        inline_q = json.loads(lesson.inline_quiz_json or "[]")
    except Exception:
        inline_q = []
    if inline_q:
        for idx, iq in enumerate(inline_q):
            questions_out.append({
                "id": iq.get("id") or f"iq_{idx}",
                "is_db": False,
                "prompt": iq.get("prompt", ""),
                "type": iq.get("type", "choice"),
                "options": iq.get("options", []),
                "hints": iq.get("hints", []),
                "explain": iq.get("explain", ""),
            })
    else:
        try:
            qids = [int(x) for x in json.loads(lesson.question_ids_json or "[]")]
        except Exception:
            qids = []
        if qids:
            q_rows = {q.id: q for q in Question.query.filter(Question.id.in_(qids)).all()}
            try:
                lesson_hints = json.loads(lesson.hints_json or "[]")
            except Exception:
                lesson_hints = []
            for qid in qids:
                qobj = q_rows.get(qid)
                if not qobj:
                    continue
                snap = qobj.snapshot()
                stem = (snap.get("text") or "").strip()
                if not stem:
                    continue
                opts = snap.get("options") or []
                img_path = snap.get("image_path") or ""
                questions_out.append({
                    "id": qobj.id,
                    "is_db": True,
                    "prompt": stem,
                    "image_url": url_for("uploaded_file", filename=img_path) if img_path else "",
                    "material": snap.get("material") or [],
                    "type": "choice" if (snap.get("answer_type") == "choice" and opts) else "number",
                    "options": opts,
                    "hints": lesson_hints or ["Проверьте условие и выпишите известные величины.", "При наличии графика или уравнения используйте встроенный Desmos."],
                    "explain": snap.get("explanation") or "",
                })

    formulas_list = [] if lesson.kind == "quiz" else _load_topic_formulas(lesson.formula_tpl, lesson.formula_topic_id)
    try:
        desmos_preset = json.loads(lesson.desmos_preset_json) if lesson.desmos_preset_json else None
    except Exception:
        desmos_preset = None

    cur_level = mastery_by_id.get(lesson.id) or mastery_by_key.get(f"{unit.slug}:{lesson.slug}", "not_started")

    return render_template(
        "student/course_player.html",
        exam=exam.upper(),
        unit=unit,
        lesson=lesson,
        article_html=render_course_html(lesson.article_md or ""),
        sidebar_lessons=sidebar_lessons,
        questions=questions_out,
        formulas_list=formulas_list,
        youtube_embed=_youtube_embed(lesson.youtube_url),
        desmos_preset=desmos_preset,
        next_url=next_url,
        cur_level=cur_level,
        cur_level_label=MASTERY_LABELS.get(cur_level, "Не начато"),
    )


def _lesson_question_ids(les) -> list[str]:
    try:
        iq = json.loads(les.inline_quiz_json or "[]")
    except Exception:
        iq = []
    if iq:
        return [str(x.get("id") or f"iq_{i}") for i, x in enumerate(iq)]
    try:
        return [str(int(x)) for x in json.loads(les.question_ids_json or "[]")]
    except Exception:
        return []


def _record_course_check(run_key: str, qid_str: str, is_correct: bool) -> None:
    """Persist server-graded answer result in the signed session (first answer per question in a run wins)."""
    run = session.get("course_run")
    if not isinstance(run, dict) or run.get("key") != run_key:
        run = {"key": run_key, "results": {}}
    results = dict(run.get("results") or {})
    results.setdefault(qid_str, bool(is_correct))
    session["course_run"] = {"key": run_key, "results": results}


@bp.post("/api/course/check")
@student_required
def api_check_question():
    data = request.get_json(silent=True) or {}
    exam = str(data.get("exam") or "SAT").upper()
    unit_slug = str(data.get("unit_slug") or "")
    lesson_slug = str(data.get("lesson_slug") or "")
    qid = data.get("question_id")
    given = str(data.get("given") or "").strip()

    unit = CourseUnit.query.filter_by(exam=exam, slug=unit_slug).first()
    lesson = CourseLesson.query.filter_by(unit_id=unit.id, slug=lesson_slug).first() if unit else None
    if not lesson:
        return jsonify({"ok": False, "error": "not_found"}), 404

    is_correct = False
    explain = ""
    correct_display = ""
    qid_str = ""

    # Check inline quiz first
    try:
        inline_q = json.loads(lesson.inline_quiz_json or "[]")
    except Exception:
        inline_q = []

    if inline_q:
        item = next(
            (x for idx, x in enumerate(inline_q) if str(x.get("id") or f"iq_{idx}") == str(qid)),
            None,
        )
        if not item:
            return jsonify({"ok": False, "error": "question_not_found"}), 404
        qid_str = str(qid)
        is_correct = _answers_match(given, str(item.get("answer") or ""), item.get("type", "choice"))
        explain = item.get("explain", "")
        correct_display = str(item.get("answer") or "")
    else:
        allowed_qids = set(_lesson_question_ids(lesson))
        if not str(qid).isdigit() or str(int(qid)) not in allowed_qids:
            return jsonify({"ok": False, "error": "question_not_found"}), 404
        qobj = db.session.get(Question, int(qid))
        if not qobj:
            return jsonify({"ok": False, "error": "question_not_found"}), 404
        qid_str = str(qobj.id)
        snap = qobj.snapshot()
        opts = snap.get("options") or []
        qtype = "choice" if (snap.get("answer_type") == "choice" and opts) else "number"
        expected = snap.get("correct") or ""
        if qtype == "choice" and str(expected).isdigit():
            idx = int(expected)
            if 0 <= idx < len(opts):
                expected_val = opts[idx]
                is_correct = _answers_match(given, expected_val, "choice") or _answers_match(given, str(expected), "choice")
                correct_display = expected_val
            else:
                is_correct = _answers_match(given, str(expected), qtype)
                correct_display = str(expected)
        else:
            is_correct = _answers_match(given, expected, qtype)
            correct_display = str(expected).split("|")[0]
        explain = snap.get("explanation") or ""

        # Auto-sync mistakes into Journal (Attempt + AttemptAnswer with finished_at set)
        if not is_correct:
            now = utcnow()
            att = Attempt(
                user_id=current_user.id,
                mode="roadmap",
                plan=[qobj.id],
                position=0,
                total=1,
                score=0,
                started_at=now,
                finished_at=now,
                draft={"exam": exam, "unit": unit_slug, "lesson": lesson_slug},
            )
            db.session.add(att)
            db.session.flush()
            db.session.add(AttemptAnswer(
                attempt_id=att.id,
                index=0,
                question_id=qobj.id,
                skill_id=qobj.skill_id,
                given=given[:200],
                is_correct=False,
                resolved=False,
                answered_at=now,
            ))
            db.session.commit()

    _record_course_check(f"{exam}:{unit.slug}:{lesson.slug}", qid_str, is_correct)

    return jsonify({
        "ok": True,
        "is_correct": is_correct,
        "correct_answer": correct_display,
        "explain": explain,
    })


@bp.post("/api/course/complete")
@student_required
def api_complete_lesson():
    data = request.get_json(silent=True) or {}
    exam = str(data.get("exam") or "SAT").upper()
    unit_slug = str(data.get("unit_slug") or "")
    lesson_slug = str(data.get("lesson_slug") or "")

    unit = CourseUnit.query.filter_by(exam=exam, slug=unit_slug).first()
    lesson = CourseLesson.query.filter_by(unit_id=unit.id, slug=lesson_slug).first() if unit else None
    if not lesson:
        return jsonify({"ok": False, "error": "not_found"}), 404

    if lesson.kind == "article":
        score, total = 1, 1
        new_lvl = "familiar"
    else:
        # Derive score and total strictly from server-graded answers recorded by /api/course/check
        expected_qids = _lesson_question_ids(lesson)
        total = len(expected_qids)
        run_key = f"{exam}:{unit.slug}:{lesson.slug}"
        run = session.pop("course_run", None)
        results = (run.get("results") or {}) if isinstance(run, dict) and run.get("key") == run_key else {}
        if total > 0 and not results:
            return jsonify({"ok": False, "error": "no_graded_answers"}), 400
        score = sum(1 for qid in expected_qids if results.get(str(qid)) is True)
        if lesson.kind == "quiz":
            pct = (score / total) if total > 0 else 0
            new_lvl = "mastered" if pct >= 0.80 else ("proficient" if pct >= 0.50 else "familiar")
        else:
            if total > 0 and (score / total) >= 0.60:
                new_lvl = "proficient"
            else:
                new_lvl = "familiar"

    lkey = f"{unit.slug}:{lesson.slug}"
    row = (
        CourseMastery.query.filter_by(user_id=current_user.id, lesson_id=lesson.id).first()
        or CourseMastery.query.filter_by(user_id=current_user.id, lesson_key=lkey).first()
    )
    if row is None:
        row = CourseMastery(
            user_id=current_user.id,
            lesson_id=lesson.id,
            lesson_key=lkey,
            level=new_lvl,
            best_score=score,
            total_q=total,
            updated_at=utcnow(),
        )
        db.session.add(row)
    else:
        row.lesson_id = lesson.id
        row.lesson_key = lkey
        if MASTERY_ORDER.get(new_lvl, 0) > MASTERY_ORDER.get(row.level, 0):
            row.level = new_lvl
        row.best_score = max(row.best_score or 0, score)
        row.total_q = max(row.total_q or 0, total)
        row.updated_at = utcnow()

    # Passing a Unit Quiz (>= 80%) upgrades proficient lessons in that unit to mastered
    if lesson.kind == "quiz" and new_lvl == "mastered":
        for sibling in unit.lessons.all():
            skey = f"{unit.slug}:{sibling.slug}"
            srow = (
                CourseMastery.query.filter_by(user_id=current_user.id, lesson_id=sibling.id).first()
                or CourseMastery.query.filter_by(user_id=current_user.id, lesson_key=skey).first()
            )
            if srow and srow.level == "proficient":
                srow.lesson_id = sibling.id
                srow.lesson_key = skey
                srow.level = "mastered"
                srow.updated_at = utcnow()

    db.session.commit()
    return jsonify({
        "ok": True,
        "score": score,
        "total": total,
        "level": row.level,
        "level_label": MASTERY_LABELS.get(row.level, "Знаком"),
    })


@bp.route("/admin/course", methods=["GET", "POST"])
@admin_required
def admin_course():
    units = CourseUnit.query.filter_by(exam="SAT").order_by(CourseUnit.number.asc()).all()
    saved = False
    if request.method == "POST":
        lid = int(request.form.get("lesson_id") or 0)
        lesson = db.session.get(CourseLesson, lid)
        if lesson:
            lesson.title_ru = (request.form.get("title_ru") or lesson.title_ru).strip()[:200]
            lesson.article_md = request.form.get("article_md") or ""
            lesson.youtube_url = (request.form.get("youtube_url") or "").strip()[:400]
            lesson.desmos_preset_json = (request.form.get("desmos_preset_json") or "").strip()
            raw_qids = [int(x) for x in re.findall(r"\d+", request.form.get("question_ids") or "")]
            lesson.question_ids_json = json.dumps(raw_qids)
            lesson.updated_at = utcnow()
            db.session.commit()
            saved = True

    all_lessons = (
        CourseLesson.query.join(CourseUnit)
        .filter(CourseUnit.exam == "SAT")
        .order_by(CourseUnit.number.asc(), CourseLesson.position.asc())
        .all()
    )
    sel_id = int(request.args.get("lesson_id") or (all_lessons[0].id if all_lessons else 0))
    cur = next((l for l in all_lessons if l.id == sel_id), all_lessons[0] if all_lessons else None)
    cur_qids = ", ".join(str(x) for x in json.loads(cur.question_ids_json or "[]")) if cur else ""
    return render_template("admin/course_builder.html", units=units, lessons=all_lessons, cur=cur, cur_qids=cur_qids, saved=saved)

"""Student side: home, skills, sessions, collections, tests, homework, journal, Monday test, profile."""
import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required
from sqlalchemy import or_

from .models import local_date, local_midnight_utc, local_now, today as local_today  # noqa: F401
from .access import student_required
from .auth import link_invite_code
from .constants import EXAMS, MISTAKE_REASONS, MODES
from .extensions import db
from .models import utcnow
from .models import Assignment, Attempt, AttemptAnswer, Question, Skill, StudentProfile, StudentRecord, Work
from .services import (answer_item, countdown_label, current_module, current_monday_work, grade_version_attempt,
                       homework_state, is_correct, seconds_left, version_layout, latest_attempt, mistake_breakdown, monday_ranking, mondays_left,
                       next_monday_test_start, open_mistakes, pick_practice_questions, progress_summary,
                       recommended_mode, skill_map, student_assignments, user_rank, week_start)

bp = Blueprint("student", __name__)

LETTERS = "АБВГДЕЖЗ"


@bp.app_context_processor
def letters():
    return {"LETTERS": LETTERS}


def _exam():
    return current_user.profile.exam if current_user.profile else None


# --------------------------------------------------------------------------- onboarding


@bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    if current_user.role != "student":
        return redirect(url_for("auth.index"))
    profile = current_user.profile or StudentProfile(user=current_user)
    if request.method == "POST":
        exam = request.form.get("exam")
        if exam not in EXAMS:
            flash(_("Выберите экзамен."), "error")
            return render_template("student/onboarding.html", profile=profile), 400
        profile.exam = exam
        profile.exam_date = _parse_date(request.form.get("exam_date"))
        profile.goal_score = _parse_int(request.form.get("goal_score"))
        profile.region = request.form.get("region", "").strip() or None
        profile.school = request.form.get("school", "").strip() or None
        profile.country = EXAMS[exam]["country"] and str(EXAMS[exam]["country"])
        lang = request.form.get("language")
        if lang in current_app.config["LANGUAGES"]:
            current_user.language = lang
        profile.onboarded = True
        db.session.add(profile)
        db.session.commit()
        code = request.form.get("invite_code", "").strip()
        if code:
            ok, msg = link_invite_code(current_user, code)
            flash(msg, "success" if ok else "error")
        return redirect(url_for("student.home"))
    return render_template("student/onboarding.html", profile=profile)


def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() if value else None
    except ValueError:
        return None


def _parse_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


# --------------------------------------------------------------------------- home


@bp.route("/home")
@student_required
def home():
    p = current_user.profile
    summary = progress_summary(current_user.id, p.exam)
    minutes = request.args.get("t", type=int) or 5
    start = next_monday_test_start()
    since = utcnow() - timedelta(days=7)
    breakdown = mistake_breakdown(current_user.id, since)
    week_mistakes = sum(breakdown.values())
    assignments = [a for a in student_assignments(current_user.id)
                   if homework_state(a, current_user.id) in ("new", "in_progress", "overdue")]
    last_monday = _previous_monday_work(p.exam)
    rows = monday_ranking(last_monday, limit=None)
    my_place, _a = user_rank(rows, current_user.id)
    left = mondays_left(p.exam_date)
    return render_template(
        "student/home.html", p=p, summary=summary, mondays=left, minutes=minutes,
        recommended=recommended_mode(minutes), monday_countdown=countdown_label(start - local_now()),
        monday_start=start, breakdown=breakdown, week_mistakes=week_mistakes, assignments=assignments[:3],
        my_place=my_place, strip=_monday_strip(left), task=_todays_task(p.exam, summary),
        portrait=skill_map(current_user.id, p.exam), facts=_daily_facts(len(MODES)), daily=_daily_block(),
    )


def _daily_block():
    from .daily import student_daily
    return student_daily(current_user)


def _monday_strip(left, past_weeks=6):
    """Dots for the hero: the last few Mondays (with your Monday-test %) and every Monday left."""
    this_week = week_start()
    scores = {}
    for a in (Attempt.query.filter(Attempt.user_id == current_user.id, Attempt.mode == "monday",
                                   Attempt.finished_at.isnot(None)).all()):
        scores[week_start(a.finished_at.date())] = a.percent
    dots = []
    for k in range(past_weeks, 0, -1):
        d = this_week - timedelta(days=7 * k)
        dots.append({"date": d, "state": "past", "score": scores.get(d)})
    dots.append({"date": this_week, "state": "now", "score": scores.get(this_week)})
    for k in range(1, (left or 0)):
        dots.append({"date": this_week + timedelta(days=7 * k), "state": "next", "score": None})
    return dots


def _todays_task(exam, summary):
    """One clear thing to do now: the weakest started skill, else the first new skill on the route."""
    if summary["weak"]:
        w = summary["weak"][0]
        return {"skill": w["skill"], "accuracy": round(w["accuracy"] * 100), "why": "weak"}
    stats_ids = {i["skill"].id for t in skill_map(current_user.id, exam) for i in t["items"] if i["state"] != "new"}
    for t in skill_map(current_user.id, exam):
        for i in t["items"]:
            if i["state"] == "new" and i["skill"].id not in stats_ids:
                return {"skill": i["skill"], "accuracy": None, "why": "new"}
    return None


def _daily_facts(n):
    from .constants import FACTS
    day = local_today().toordinal()
    return [str(FACTS[(day * 3 + i * 3) % len(FACTS)]) for i in range(n)]


# --------------------------------------------------------------------------- skills


@bp.route("/skills")
@student_required
def skills():
    exam = _exam()
    scope = request.args.get("scope", "exam")
    q = request.args.get("q", "").strip().lower()
    topics = skill_map(current_user.id, exam if scope == "exam" else None)

    def keep(topic, sub, item):
        if scope == "exam" and item["state"] == "outside":
            return False
        if q:
            return q in item["skill"].name.lower() or q in sub["node"].name.lower() or q in topic["name"].lower()
        return True

    filtered = []
    for t in topics:
        subs = []
        for s in t["subtopics"]:
            items = [i for i in s["items"] if keep(t, s, i)]
            if items:
                subs.append({"node": s["node"], "items": items})
        if subs:
            filtered.append({**t, "subtopics": subs, "items": [i for s in subs for i in s["items"]]})
    topics = filtered
    summary = progress_summary(current_user.id, exam)
    highlight = summary["weak"][0]["skill"].topic_node.id if summary["weak"] and summary["weak"][0]["skill"].topic_node else None
    return render_template("student/skills.html", topics=topics, summary=summary, scope=scope, q=q, exam=exam,
                           highlight=highlight)


# --------------------------------------------------------------------------- practice sessions


@bp.route("/sessions")
@student_required
def sessions():
    recent = (Attempt.query.filter(Attempt.user_id == current_user.id, Attempt.mode.in_(list(MODES.keys())))
              .order_by(Attempt.started_at.desc()).limit(8).all())
    return render_template("student/sessions.html", recent=recent, facts=_daily_facts(len(MODES)))


@bp.route("/sessions/start/<mode>", methods=["POST"])
@student_required
def start_session(mode):
    if mode not in MODES or not MODES[mode]["ready"]:
        flash(_("Этот режим скоро появится."), "info")
        return redirect(url_for("student.sessions"))
    skill_id = request.form.get("skill_id", type=int)
    questions = pick_practice_questions(current_user, mode, skill_id=skill_id)
    if not questions:
        flash(_("Пока нет вопросов для этого режима."), "error")
        return redirect(url_for("student.sessions"))
    att = Attempt(user=current_user, mode=mode, plan=[q.id for q in questions], position=0, total=len(questions))
    db.session.add(att)
    db.session.commit()
    return redirect(url_for("student.session_play", attempt_id=att.id))


def _own_attempt(attempt_id):
    att = db.session.get(Attempt, attempt_id)
    if not att or att.user_id != current_user.id:
        abort(404)
    return att


@bp.route("/sessions/<int:attempt_id>", methods=["GET", "POST"])
@student_required
def session_play(attempt_id):
    att = _own_attempt(attempt_id)
    if att.mode not in MODES:
        return redirect(url_for("student.attempt_run", attempt_id=att.id))
    if att.finished_at:
        return redirect(url_for("student.session_done", attempt_id=att.id))
    idx = att.position
    question = db.session.get(Question, att.plan[idx])
    answer = next((a for a in att.answers if a.index == idx), None)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "answer" and answer is None:
            given = request.form.get("given", "").strip()
            if not given:
                flash(_("Выберите или введите ответ."), "error")
                return redirect(url_for("student.session_play", attempt_id=att.id))
            ok = is_correct(question, given)
            answer = AttemptAnswer(attempt=att, index=idx, question=question, skill_id=question.skill_id, given=given,
                                   is_correct=ok, explanation_text=request.form.get("explanation_text") or None)
            att.score += ok
            db.session.add(answer)
            db.session.commit()
        elif action == "next" and answer is not None:
            if idx + 1 >= len(att.plan):
                att.finished_at = utcnow()
                att.duration_sec = int((att.finished_at - att.started_at).total_seconds())
                db.session.commit()
                return redirect(url_for("student.session_done", attempt_id=att.id))
            att.position = idx + 1
            db.session.commit()
        elif action == "reason" and answer is not None and not answer.is_correct:
            reason = request.form.get("reason")
            answer.mistake_reason = reason if reason in MISTAKE_REASONS else None
            db.session.commit()
        return redirect(url_for("student.session_play", attempt_id=att.id))

    return render_template("student/session.html", att=att, idx=idx, question=question, answer=answer,
                           mode=MODES[att.mode], mode_key=att.mode)


@bp.route("/sessions/<int:attempt_id>/done")
@student_required
def session_done(attempt_id):
    att = _own_attempt(attempt_id)
    return render_template("student/session_done.html", att=att, mode=MODES.get(att.mode), mode_key=att.mode)


# --------------------------------------------------------------------------- collections & tests


def _visible_collections():
    return Work.query.filter_by(kind="collection", status="published")


@bp.route("/collections")
@student_required
def collections():
    exam_filter = request.args.get("exam", "")
    cat = request.args.get("cat", "")
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "new")
    query = _visible_collections()
    if exam_filter in EXAMS:
        query = query.filter(Work.exam == exam_filter)
    if cat in ("full", "thematic"):
        query = query.filter(Work.category == cat)
    works = query.all()
    if q:
        ql = q.lower()
        works = [w for w in works if ql in w.title.lower() or ql in (w.description or "").lower()
                 or ql in w.author.name.lower() or ql in EXAMS.get(w.exam, {}).get("label", "").lower()]
    if sort == "short":
        works.sort(key=lambda w: w.time_limit_min or 0)
    elif sort == "popular":
        counts = defaultdict(int)
        for a in Attempt.query.filter(Attempt.mode == "collection").all():
            if a.work_version:
                counts[a.work_version.work_id] += 1
        works.sort(key=lambda w: -counts[w.id])
    else:
        works.sort(key=lambda w: w.current_version.published_at if w.current_version else w.created_at, reverse=True)

    # Recommendations: same exam; thematic sets that cover weak skills first.
    exam = _exam()
    weak_ids = {w["skill"].id for w in progress_summary(current_user.id, exam)["weak"][:5]}
    recommended = []
    if not (q or exam_filter or cat):
        candidates = [w for w in _visible_collections().all() if w.exam == exam]
        def covers_weak(w):
            return len({i.get("skill_id") for i in w.current_version.items} & weak_ids)
        candidates.sort(key=lambda w: (-(w.category == "thematic" and covers_weak(w) > 0), -covers_weak(w)))
        recommended = candidates[:4]
        for w in recommended:
            w.weak_match = w.category == "thematic" and covers_weak(w) > 0
    return render_template("student/collections.html", works=works, recommended=recommended, exam_filter=exam_filter,
                           cat=cat, q=q, sort=sort)


@bp.route("/works/<int:work_id>")
@student_required
def work_detail(work_id):
    work = db.session.get(Work, work_id)
    if not work or work.status != "published" or work.kind not in ("collection",):
        abort(404)
    attempts = (Attempt.query.filter(Attempt.user_id == current_user.id,
                                     Attempt.work_version_id.in_([v.id for v in work.versions]))
                .order_by(Attempt.started_at.desc()).all())
    return render_template("student/work_detail.html", work=work, attempts=attempts)


@bp.route("/works/<int:work_id>/start", methods=["POST"])
@student_required
def start_work(work_id):
    work = db.session.get(Work, work_id)
    if not work or work.status != "published" or work.kind != "collection":
        abort(404)
    att = Attempt(user=current_user, mode="collection", work_version=work.current_version,
                  total=work.current_version.question_count)
    db.session.add(att)
    db.session.commit()
    return redirect(url_for("student.attempt_run", attempt_id=att.id))


@bp.route("/attempts/<int:attempt_id>", methods=["GET", "POST"])
@student_required
def attempt_run(attempt_id):
    """A timed test in its format: grid navigation (SAT, CSCA, …) or pages + answer sheet (ORT).

    SAT-style tests run in modules: when a module ends (button or timer), its answers are
    locked and the next module starts with its own timer. If the time runs out while the page
    is closed, the server moves on by itself the next time the test is opened.
    """
    att = _own_attempt(attempt_id)
    if att.mode in MODES:
        return redirect(url_for("student.session_play", attempt_id=att.id))
    if att.finished_at:
        return redirect(url_for("student.attempt_result", attempt_id=att.id))
    version = att.work_version
    layout = version_layout(version)
    k, mod = current_module(att, layout)
    if request.method == "POST":
        _merge_module_answers(att, mod, request.form)
        blocked = _empty_homework(att, request.form)
        if blocked:
            return blocked
        return _finish_attempt(att, version)
    # time ran out while away: move to the next module, or hand the test in
    left = seconds_left(att, layout)
    while left == 0 and k < len(layout["modules"]):
        att.module = k + 1
        att.module_started_at = (att.module_started_at or att.started_at) + timedelta(minutes=mod["minutes"])
        db.session.commit()
        k, mod = current_module(att, layout)
        left = seconds_left(att, layout)
    if left == 0:
        return _finish_attempt(att, version)
    earlier = sum(1 for key, v in (att.draft or {}).items()
                  if key.startswith("q") and str(v).strip() and int(key[1:]) < mod["start"])
    return render_template("student/attempt.html", att=att, version=version, layout=layout, module=k, mod=mod,
                           seconds_left=left, draft=att.draft or {}, sheets=_enabled_sheets(), earlier_answered=earlier)


def ort_once(layout, version, draft, idx, value):
    """ORT answer sheet: the first mark is a circle; it may be corrected once (the new mark becomes a square),
    after that the answer is final. Returns False if this change isn't allowed. Updates draft["c<i>"]."""
    if layout.get("format") != "ort" or (version.items[idx] or {}).get("answer_type") != "choice":
        return True
    old = draft.get(f"q{idx}")
    if not old or old == value:
        return True
    if draft.get(f"c{idx}"):
        return False
    draft[f"c{idx}"] = "1"
    return True


def _merge_module_answers(att, mod, form):
    """Answers of the current module from a submitted form go into the draft (earlier modules stay locked)."""
    draft = dict(att.draft or {})
    layout = version_layout(att.work_version)
    for idx in range(mod["start"], mod["end"]):
        value = (form.get(f"q{idx}") or "").strip()[:64]
        if (value or f"q{idx}" in form) and not ort_once(layout, att.work_version, draft, idx, value):
            continue
        if value:
            draft[f"q{idx}"] = value
        elif f"q{idx}" in form:
            draft.pop(f"q{idx}", None)
        if draft.get(f"p{idx}"):  # a photo of a written solution counts as an answer
            draft[f"q{idx}"] = "photo"
    att.draft = draft


def answered_count(att):
    return sum(1 for k, v in (att.draft or {}).items() if k.startswith("q") and str(v).strip())


def _empty_homework(att, form):
    """Homework can't be handed in by hand with no answers. When the timer runs out it is handed in as it is
    (the teacher then sees "time ran out, no answers")."""
    if att.mode != "homework" or form.get("timeout") == "1" or answered_count(att):
        return None
    db.session.commit()
    flash(_("Ответьте хотя бы на один вопрос, чтобы сдать работу."), "error")
    return redirect(url_for("student.attempt_run", attempt_id=att.id))


def _finish_attempt(att, version):
    answers = {k: v for k, v in (att.draft or {}).items() if k[:1] in ("q", "p")}
    grade_version_attempt(att, version, answers)
    db.session.commit()
    if att.mode == "homework":
        flash(_("Домашнее задание сдано. Учитель увидит результат."), "success")
    return redirect(url_for("student.attempt_result", attempt_id=att.id))


@bp.route("/attempts/<int:attempt_id>/next-module", methods=["POST"])
@student_required
def attempt_next_module(attempt_id):
    att = _own_attempt(attempt_id)
    if att.finished_at:
        return redirect(url_for("student.attempt_result", attempt_id=att.id))
    layout = version_layout(att.work_version)
    k, mod = current_module(att, layout)
    _merge_module_answers(att, mod, request.form)
    if k < len(layout["modules"]):
        att.module = k + 1
        att.module_started_at = utcnow()
        db.session.commit()
        flash(_("Модуль %(n)s завершён. Ответы в нём больше не меняются.", n=k), "info")
        return redirect(url_for("student.attempt_run", attempt_id=att.id))
    blocked = _empty_homework(att, request.form)
    if blocked:
        return blocked
    return _finish_attempt(att, att.work_version)


@bp.route("/attempts/<int:attempt_id>/save", methods=["POST"])
@student_required
def attempt_save(attempt_id):
    """Autosave one answer (q<i>) or review mark (r<i>) while the student works.

    Answers live in Attempt.draft until the test is handed in, so a reload or a lost
    connection brings the student back to the same answers with the same time left.
    """
    att = _own_attempt(attempt_id)
    if att.finished_at or att.mode in MODES:
        return jsonify(ok=False, reason="closed"), 409
    version = att.work_version
    layout = version_layout(version)
    _k, mod = current_module(att, layout)
    left = seconds_left(att, layout)
    started = att.module_started_at or att.started_at
    if left == 0 and utcnow() > started + timedelta(minutes=mod["minutes"], seconds=30):
        return jsonify(ok=False, reason="time"), 409
    name = request.form.get("name", "")
    if not re.fullmatch(r"[qr]\d{1,3}", name) or int(name[1:]) >= len(version.items):
        return jsonify(ok=False, reason="field"), 400
    if not (mod["start"] <= int(name[1:]) < mod["end"]):
        return jsonify(ok=False, reason="locked"), 409
    draft = dict(att.draft or {})
    value = request.form.get("value", "").strip()[:64]
    if name.startswith("q") and not ort_once(layout, version, draft, int(name[1:]), value):
        return jsonify(ok=False, reason="once", value=draft.get(name)), 409
    if value:
        draft[name] = value
    else:
        draft.pop(name, None)
    att.draft = draft
    db.session.commit()
    return jsonify(ok=True, answered=sum(1 for k in draft if k.startswith("q")))


ALLOWED_PHOTO = {"png", "jpg", "jpeg", "webp", "heic"}


@bp.route("/attempts/<int:attempt_id>/photo", methods=["POST"])
@student_required
def attempt_photo(attempt_id):
    """Photo of a written solution (part 2 of ЕГЭ etc.), attached while the test is running."""
    import os
    import secrets as _secrets
    att = _own_attempt(attempt_id)
    if att.finished_at or att.mode in MODES:
        return jsonify(ok=False, reason="closed"), 409
    version = att.work_version
    _k, mod = current_module(att, version_layout(version))
    idx = request.form.get("idx", type=int)
    if idx is None or not (mod["start"] <= idx < mod["end"]) or version.items[idx].get("answer_type") != "written":
        return jsonify(ok=False, reason="field"), 400
    f = request.files.get("photo")
    ext = (f.filename.rsplit(".", 1)[-1].lower() if f and "." in f.filename else "")
    if not f or ext not in ALLOWED_PHOTO:
        return jsonify(ok=False, reason="type", message=_("Нужна фотография: JPG, PNG, WEBP или HEIC.")), 400
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "solutions")
    os.makedirs(folder, exist_ok=True)
    name = f"solutions/a{att.id}_{idx}_{_secrets.token_hex(6)}.{ext}"
    f.save(os.path.join(current_app.config["UPLOAD_FOLDER"], name))
    draft = dict(att.draft or {})
    draft[f"p{idx}"] = name
    draft[f"q{idx}"] = "photo"
    att.draft = draft
    db.session.commit()
    return jsonify(ok=True, url=url_for("uploaded_file", filename=name))


@bp.route("/attempts/<int:attempt_id>/assess/<int:idx>", methods=["POST"])
@student_required
def attempt_assess(attempt_id, idx):
    """Self-assessment of a written answer by the criteria (a teacher's mark is final)."""
    from .services import rescore
    att = _own_attempt(attempt_id)
    if not att.finished_at:
        abort(404)
    ans = next((a for a in att.answers if a.index == idx), None)
    items = att.work_version.items
    if not ans or idx >= len(items) or items[idx].get("answer_type") != "written":
        abort(404)
    if ans.points_by == "teacher":
        flash(_("Это задание уже оценил учитель."), "info")
    else:
        pts = request.form.get("points", type=int)
        if pts is not None and 0 <= pts <= int(items[idx].get("weight") or 1):
            ans.points, ans.points_by = pts, "self"
            rescore(att)
            db.session.commit()
    return redirect(url_for("student.attempt_result", attempt_id=att.id) + f"#q{idx + 1}")


def _enabled_sheets():
    from .models import ReferenceSheet
    return (ReferenceSheet.query.filter_by(user_id=current_user.id, enabled=True)
            .order_by(ReferenceSheet.position, ReferenceSheet.id).all())


@bp.route("/attempts/<int:attempt_id>/result")
@student_required
def attempt_result(attempt_id):
    att = _own_attempt(attempt_id)
    if not att.finished_at:
        return redirect(url_for("student.attempt_run", attempt_id=att.id))
    items = att.work_version.items if att.work_version else []
    rows = [{"item": items[a.index] if a.index < len(items) else None, "answer": a} for a in att.answers]
    layout = version_layout(att.work_version) if att.work_version else None
    return render_template("student/result.html", att=att, rows=rows, layout=layout)


# --------------------------------------------------------------------------- homework


@bp.route("/homework")
@student_required
def homework():
    groups = defaultdict(list)
    for a in student_assignments(current_user.id):
        if a.work.status == "archived" and not a.attempts:
            continue
        state = homework_state(a, current_user.id)
        groups["todo" if state in ("new", "in_progress", "overdue") else "done"].append((a, state))
    groups["todo"].sort(key=lambda x: (x[0].due_at or datetime.max))
    groups["done"].sort(key=lambda x: x[0].due_at or datetime.min, reverse=True)
    teachers = StudentRecord.query.filter_by(student_user_id=current_user.id).all()
    return render_template("student/homework.html", todo=groups["todo"], done=groups["done"], teachers=teachers)


def _own_assignment(assignment_id):
    a = db.session.get(Assignment, assignment_id)
    if not a or a.record.student_user_id != current_user.id:
        abort(404)
    return a


@bp.route("/homework/<int:assignment_id>")
@student_required
def homework_detail(assignment_id):
    a = _own_assignment(assignment_id)
    state = homework_state(a, current_user.id)
    last = latest_attempt(a, current_user.id)
    open_attempt = next((x for x in a.attempts if x.user_id == current_user.id and not x.finished_at), None)
    return render_template("student/homework_detail.html", a=a, state=state, last=last, open_attempt=open_attempt)


@bp.route("/homework/<int:assignment_id>/start", methods=["POST"])
@student_required
def homework_start(assignment_id):
    a = _own_assignment(assignment_id)
    open_attempt = next((x for x in a.attempts if x.user_id == current_user.id and not x.finished_at), None)
    if open_attempt:
        return redirect(url_for("student.attempt_run", attempt_id=open_attempt.id))
    if a.checked_at:
        flash(_("Это задание уже проверено."), "info")
        return redirect(url_for("student.homework_detail", assignment_id=a.id))
    version = a.work.current_version
    att = Attempt(user=current_user, mode="homework", work_version=version, assignment=a, total=version.question_count)
    db.session.add(att)
    db.session.commit()
    return redirect(url_for("student.attempt_run", attempt_id=att.id))


# --------------------------------------------------------------------------- journal


@bp.route("/journal")
@student_required
def journal():
    show = request.args.get("show", "open")
    base = (AttemptAnswer.query.join(Attempt).outerjoin(Question, AttemptAnswer.question_id == Question.id)
            .filter(Attempt.user_id == current_user.id, AttemptAnswer.is_correct.is_(False),
                    Attempt.finished_at.isnot(None),
                    or_(Question.answer_type.is_(None), Question.answer_type != "written",
                        AttemptAnswer.points.isnot(None))))
    days_shown = max(7, min(365, request.args.get("days", 14, type=int)))
    entries = base.filter(AttemptAnswer.resolved.is_(show == "resolved")).order_by(
        AttemptAnswer.answered_at.desc()).limit(1500).all()
    open_count = base.filter(AttemptAnswer.resolved.is_(False)).count()
    resolved_count = base.filter(AttemptAnswer.resolved.is_(True)).count()
    since = utcnow() - timedelta(days=7)
    breakdown = mistake_breakdown(current_user.id, since)
    days, more = journal_days(entries, days_shown)
    return render_template("student/journal.html", days=days, more=more, days_shown=days_shown, show=show, today_d=local_today(),
                           open_count=open_count, resolved_count=resolved_count, breakdown=breakdown,
                           week_total=sum(breakdown.values()))


def journal_days(entries, limit_days):
    """Mistakes grouped like a diary: day → practice/test → entries, with the day's topics on top."""
    from .models import local_date as to_local
    days, order = {}, []
    for e in entries:
        d = to_local(e.answered_at)
        if d not in days:
            if len(order) == limit_days:
                return [days[k] for k in order], True
            days[d] = {"date": d, "groups": {}, "group_order": [], "topics": defaultdict(int), "total": 0}
            order.append(d)
        day = days[d]
        day["total"] += 1
        day["topics"][e.skill.name if e.skill else _("Задача")] += 1
        g = day["groups"].get(e.attempt_id)
        if g is None:
            att = e.attempt
            if att.mode in MODES:
                title, kind = MODES[att.mode]["name"], _("Сессия")
            else:
                from .constants import WORK_KINDS
                title = att.work_version.title if att.work_version else _("Работа")
                kind = WORK_KINDS.get(att.mode) or _("Сборник")
            layout = version_layout(att.work_version) if att.work_version else None
            g = {"attempt": att, "title": title, "kind": kind, "rows": [], "topics": defaultdict(int),
                 "modules": (layout or {}).get("modules") or [],
                 "letters": "ABCDEFGH" if (layout or {}).get("format") in ("sat", "csca") else None}
            day["groups"][e.attempt_id] = g
            day["group_order"].append(e.attempt_id)
        mods = g["modules"]
        label = _("Вопрос %(n)s", n=e.index + 1)
        if len(mods) > 1:
            for k, m in enumerate(mods, 1):
                if m["start"] <= e.index < m["end"]:
                    label = _("Модуль %(k)s", k=k) + " · " + _("Вопрос %(n)s", n=e.index - m["start"] + 1)
        g["rows"].append({"answer": e, "item": answer_item(e), "label": label})
        g["topics"][e.skill.name if e.skill else _("Задача")] += 1
    out = []
    for k in order:
        day = days[k]
        day["topics"] = sorted(day["topics"].items(), key=lambda t: -t[1])
        day["groups"] = [days[k]["groups"][g] for g in day["group_order"]]
        for g in day["groups"]:
            g["topics"] = sorted(g["topics"].items(), key=lambda t: -t[1])
            g["rows"].sort(key=lambda r: r["answer"].index)   # in question order
        out.append(day)
    return out, False


@bp.route("/journal/<int:answer_id>", methods=["POST"])
@student_required
def journal_update(answer_id):
    ans = db.session.get(AttemptAnswer, answer_id)
    if not ans or ans.attempt.user_id != current_user.id or ans.is_correct:
        abort(404)
    if "reason" in request.form:
        reason = request.form.get("reason")
        ans.mistake_reason = reason if reason in MISTAKE_REASONS else None
    if request.form.get("resolve") == "1":
        ans.resolved = True
    if request.form.get("resolve") == "0":
        ans.resolved = False
    db.session.commit()
    return redirect(url_for("student.journal", show=request.form.get("show", "open")) + f"#e{ans.id}")


# --------------------------------------------------------------------------- Monday test & ranking


def _previous_monday_work(exam):
    upcoming_start = week_start(next_monday_test_start().date())
    return (Work.query.filter(Work.kind == "monday", Work.status == "published", Work.exam == exam,
                              Work.week_start < upcoming_start)
            .order_by(Work.week_start.desc()).first())


def _upcoming_monday_work(exam):
    upcoming_start = week_start(next_monday_test_start().date())
    return Work.query.filter_by(kind="monday", status="published", exam=exam, week_start=upcoming_start).first()


def monday_window_open():
    if current_app.config.get("MONDAY_TEST_ALWAYS_OPEN"):
        return True
    now = local_now()
    start = next_monday_test_start(now)
    return start <= now < start + timedelta(hours=5)


@bp.route("/monday")
@student_required
def monday():
    p = current_user.profile
    scope = request.args.get("scope", "country")
    scope_value = {"region": p.region, "school": p.school}.get(scope)
    previous = _previous_monday_work(p.exam)
    upcoming = _upcoming_monday_work(p.exam)
    all_rows = monday_ranking(previous, limit=None)
    rows = monday_ranking(previous, scope if scope in ("region", "school") else None, scope_value, limit=None)
    my_place, my_attempt = user_rank(rows, current_user.id)
    start = next_monday_test_start()
    # school duel: my school vs the strongest other school by average score
    schools = defaultdict(list)
    for a in all_rows:
        if a.user.profile and a.user.profile.school:
            schools[a.user.profile.school].append(a.score)
    averages = {s: sum(v) / len(v) for s, v in schools.items()}
    mine = averages.get(p.school)
    rival = max(((s, v) for s, v in averages.items() if s != p.school), key=lambda x: x[1], default=None)
    prev_two = (Work.query.filter(Work.kind == "monday", Work.exam == p.exam, Work.status == "published")
                .order_by(Work.week_start.desc()).all())
    already_taken = upcoming and Attempt.query.filter(
        Attempt.user_id == current_user.id,
        Attempt.work_version_id.in_([v.id for v in upcoming.versions])).filter(Attempt.finished_at.isnot(None)).first()
    return render_template(
        "student/monday.html", previous=previous, upcoming=upcoming, rows=rows[:10], total=len(rows),
        my_place=my_place, my_attempt=my_attempt, scope=scope, countdown=countdown_label(start - local_now()),
        start=start, window_open=monday_window_open(), already_taken=already_taken,
        duel={"mine": (p.school, mine), "rival": rival} if mine is not None and rival else None,
        week_number=len(prev_two),
    )


@bp.route("/monday/start", methods=["POST"])
@student_required
def monday_start():
    p = current_user.profile
    work = _upcoming_monday_work(p.exam)
    if not work or not monday_window_open():
        flash(_("Тест понедельника откроется в понедельник в 19:00."), "info")
        return redirect(url_for("student.monday"))
    existing = Attempt.query.filter(Attempt.user_id == current_user.id,
                                    Attempt.work_version_id.in_([v.id for v in work.versions])).first()
    if existing:
        return redirect(url_for("student.attempt_run", attempt_id=existing.id))
    att = Attempt(user=current_user, mode="monday", work_version=work.current_version,
                  total=work.current_version.question_count)
    db.session.add(att)
    db.session.commit()
    return redirect(url_for("student.attempt_run", attempt_id=att.id))


# --------------------------------------------------------------------------- profile


@bp.route("/profile", methods=["GET", "POST"])
@student_required
def profile():
    p = current_user.profile
    if request.method == "POST":
        action = request.form.get("action")
        if action == "profile":
            name = request.form.get("name", "").strip()
            if len(name) >= 2:
                current_user.name = name
            exam = request.form.get("exam")
            if exam in EXAMS:
                p.exam = exam
            p.exam_date = _parse_date(request.form.get("exam_date")) or p.exam_date
            p.goal_score = _parse_int(request.form.get("goal_score"))
            p.grade = request.form.get("grade", "").strip() or None
            p.region = request.form.get("region", "").strip() or None
            p.school = request.form.get("school", "").strip() or None
            lang = request.form.get("language")
            if lang in current_app.config["LANGUAGES"]:
                current_user.language = lang
            db.session.commit()
            flash(_("Профиль сохранён."), "success")
        elif action == "join":
            ok, msg = link_invite_code(current_user, request.form.get("invite_code"))
            flash(msg, "success" if ok else "error")
        elif action == "password":
            if not current_user.check_password(request.form.get("current", "")):
                flash(_("Текущий пароль неверный."), "error")
            elif len(request.form.get("new", "")) < 8:
                flash(_("Новый пароль должен быть не короче 8 символов."), "error")
            else:
                current_user.set_password(request.form["new"])
                db.session.commit()
                flash(_("Пароль изменён."), "success")
        return redirect(url_for("student.profile"))
    teachers = StudentRecord.query.filter_by(student_user_id=current_user.id).all()
    return render_template("student/profile.html", p=p, teachers=teachers)


# --------------------------------------------------------------------------- formula sheets


@bp.route("/formulas", methods=["GET", "POST"])
@student_required
def formulas():
    """The student's own reference sheets: branch → name → picture → formula.

    Enabled sheets open from the «Формулы» button inside every test.
    """
    import os
    import uuid
    from werkzeug.utils import secure_filename
    from .models import ReferenceSheet, SheetEntry

    def own_sheet(sheet_id):
        sh = db.session.get(ReferenceSheet, sheet_id or 0)
        if not sh or sh.user_id != current_user.id:
            abort(404)
        return sh

    if request.method == "POST":
        f = request.form
        action = f.get("action")
        if action == "create":
            title = f.get("title", "").strip()[:120]
            if len(title) < 2:
                flash(_("Назови лист, например «CSCA формулы»."), "error")
            else:
                count = ReferenceSheet.query.filter_by(user_id=current_user.id).count()
                sh = ReferenceSheet(user_id=current_user.id, title=title, exam=f.get("exam") if f.get("exam") in EXAMS else None,
                                    position=count)
                db.session.add(sh)
                db.session.commit()
                flash(_("Лист создан. Добавь первую формулу."), "success")
                return redirect(url_for("student.formulas", _anchor=f"sheet-{sh.id}"))
        elif action == "toggle":
            sh = own_sheet(f.get("sheet_id", type=int))
            sh.enabled = not sh.enabled
            db.session.commit()
        elif action == "rename":
            sh = own_sheet(f.get("sheet_id", type=int))
            if len(f.get("title", "").strip()) >= 2:
                sh.title = f.get("title").strip()[:120]
                db.session.commit()
        elif action == "delete_sheet":
            db.session.delete(own_sheet(f.get("sheet_id", type=int)))
            db.session.commit()
            flash(_("Лист удалён."), "success")
        elif action == "add_entry":
            sh = own_sheet(f.get("sheet_id", type=int))
            branch = " ".join(f.get("branch", "").split())[:80]
            for e in sh.entries:  # same section typed in another case → one section
                if e.branch and e.branch.casefold() == branch.casefold():
                    branch = e.branch
                    break
            topics, formulas_, images = f.getlist("topic"), f.getlist("formula"), request.files.getlist("image")
            added = 0
            for i, topic in enumerate(topics):
                topic = topic.strip()[:120]
                formula = (formulas_[i] if i < len(formulas_) else "").strip()[:2000]
                upload = images[i] if i < len(images) else None
                if not topic and not formula and not (upload and upload.filename):
                    continue
                if not topic or not (formula or (upload and upload.filename)):
                    flash(_("Укажи название и формулу или картинку."), "error")
                    continue
                if formula and "$" not in formula:
                    formula = f"${formula}$"
                entry = SheetEntry(sheet=sh, branch=branch, topic=topic, formula=formula, position=len(sh.entries) + added)
                added += 1
                if upload and upload.filename:
                    ext = secure_filename(upload.filename).rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
                    if ext in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
                        name = f"sheet-{current_user.id}-{uuid.uuid4().hex[:10]}.{ext}"
                        upload.save(os.path.join(current_app.config["UPLOAD_FOLDER"], name))
                        entry.image_path = name
                    else:
                        flash(_("Картинка: только PNG, JPG или WEBP."), "error")
                db.session.add(entry)
            if added:
                db.session.commit()
            elif not any(t.strip() for t in topics):
                flash(_("Укажи название и формулу или картинку."), "error")
            return redirect(url_for("student.formulas", _anchor=f"sheet-{sh.id}"))
        elif action == "delete_entry":
            entry = db.session.get(SheetEntry, f.get("entry_id", type=int) or 0)
            if not entry or entry.sheet.user_id != current_user.id:
                abort(404)
            sid = entry.sheet_id
            db.session.delete(entry)
            db.session.commit()
            return redirect(url_for("student.formulas", _anchor=f"sheet-{sid}"))
        return redirect(url_for("student.formulas"))
    sheets = (ReferenceSheet.query.filter_by(user_id=current_user.id)
              .order_by(ReferenceSheet.position, ReferenceSheet.id).all())
    return render_template("student/formulas.html", sheets=sheets)

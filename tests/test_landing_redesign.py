"""Tests for Stages 2–5 of the Monday Academy public landing redesign:
- Stage 2: Living dot engine, interactive curve, and opaque-token live hero question (/api/public/hero-question)
- Stage 3: Live counters strip (/api/public/stats), threshold hiding, and Asia/Bishkek (UTC+6) day/week boundaries
- Stage 4: Reusable exam page (/exams/<slug>, /ort), versioned verified content, preflight guard, sitemap, lead form
- Stage 5: Playwright multi-viewport (390, 820, 1440; light & dark), frame-time telemetry, keyboard/reduced-motion, CSP
"""
from __future__ import annotations

import json
import pathlib
import re
import threading
import time
from datetime import timedelta

from werkzeug.serving import make_server

from config import Config
from monday import create_app, storage
from monday.constants import EXAMS
from monday.extensions import db
from monday.models import (
    Attempt,
    AttemptAnswer,
    ContentNode,
    Lead,
    Question,
    StudentProfile,
    User,
     local_midnight_utc,
)
from monday.public_samples import (
    issue_public_sample_token,
    set_question_public_sample,
    verify_public_sample_token,
)
from monday.public_site import clear_public_stats_cache, collect_site_preflight_blockers

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_app(tmp_path, *, public_enabled: bool = True, csrf_enabled: bool = False, **overrides):
    class LandingCfg(Config):
        TESTING = True
        WTF_CSRF_ENABLED = csrf_enabled
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        PUBLIC_SITE_ENABLED = public_enabled
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'landing.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        PUBLIC_SAMPLE_MEDIA_FOLDER = str(tmp_path / "public_sample_media")

    for k, v in overrides.items():
        setattr(LandingCfg, k, v)
    clear_public_stats_cache()
    return create_app(LandingCfg, seed_if_empty=False)


def test_landing_csp_static_audit_and_auth_redirects(tmp_path):
    inline_handler_re = re.compile(r"\bon(?:click|change|input|submit|load|keydown|keyup|focus|blur)=", re.I)
    for rel in (
        "monday/templates/public/landing.html",
        "monday/templates/public/_base.html",
        "monday/templates/public/_stats_strip.html",
        "monday/templates/public/exam_page.html",
        "monday/templates/public/question_bank.html",
        "monday/templates/public/offline_courses.html",
        "monday/templates/public/online_courses.html",
        "monday/templates/public/pricing.html",
        "monday/templates/public/faq.html",
        "monday/templates/public/contact.html",
        "monday/templates/public/about.html",
        "monday/templates/info/_legal_header.html",
        "monday/templates/info/terms.html",
        "monday/templates/info/privacy.html",
        "monday/templates/info/refund.html",
    ):
        raw = (ROOT_DIR / rel).read_text(encoding="utf-8")
        assert "javascript:" not in raw.lower(), f"javascript: URL in {rel}"
        assert not inline_handler_re.search(raw), f"inline event handler in {rel}"
        for tag in re.findall(r"<script\b[^>]*>", raw, re.I):
            assert "src=" in tag.lower() or "application/ld+json" in tag.lower(), f"inline executable script in {rel}: {tag}"

    # Verify STATE TO PRESERVE defaults in config.py and render.production.yaml
    assert Config.PUBLIC_SITE_ENABLED is False
    assert Config.SELF_STUDY_SIGNUP_ENABLED is False
    prod_yaml = (ROOT_DIR / "render.production.yaml").read_text(encoding="utf-8")
    assert "key: PUBLIC_SITE_ENABLED\n        value: \"0\"" in prod_yaml
    assert "key: SELF_STUDY_SIGNUP_ENABLED\n        value: \"0\"" in prod_yaml

    app = _make_app(tmp_path, public_enabled=True)
    with app.app_context():
        stu = User(email="s_land@monday.kg", name="Student L", role="student", is_approved=True)
        stu.set_password("Pass12345!")
        adm = User(email="a_land@monday.kg", name="Admin L", role="admin", is_approved=True)
        adm.set_password("StrongAdmin123!")
        db.session.add_all([stu, adm])
        db.session.flush()
        db.session.add(StudentProfile(user_id=stu.id, exam="SAT", onboarded=True))
        db.session.commit()

    anon = app.test_client()
    for pub_url in (
        "/",
        "/exams/ort",
        "/ort",
        "/question-bank",
        "/offline-courses",
        "/online",
        "/pricing",
        "/faq",
        "/contact",
        "/about",
        "/terms",
        "/privacy",
        "/refund",
        "/login",
        "/register",
    ):
        resp = anon.get(pub_url)
        assert resp.status_code == 200, f"{pub_url} returned {resp.status_code}"
        body_txt = resp.data.decode("utf-8")
        if pub_url not in ("/login", "/register"):
            assert "mp-footer" in body_txt, f"Missing unified black footer on {pub_url}"
            # When SELF_STUDY_SIGNUP_ENABLED is False (default), public pages must not link to /register
            assert 'href="/register"' not in body_txt, f"Unexpected /register link on {pub_url} when signup flag is off"

    # Landing & base templates must contain zero inline style="" attributes (strict CSP)
    for tpl_rel in ("monday/templates/public/landing.html", "monday/templates/public/_base.html"):
        tpl_raw = (ROOT_DIR / tpl_rel).read_text(encoding="utf-8")
        assert "style=" not in tpl_raw.lower(), f"Inline style= attribute found in {tpl_rel}"

    r = anon.get("/")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    for expected in (
        "ОРТ · SAT · ЕГЭ · ЕНТ · ОГЭ · Школьная математика",
        "Персональный тренажёр по",
        "математике и экзаменам",
        "Готовься к ОРТ, SAT, ЕГЭ, ЕНТ и школьной математике в одном месте.",
        "Я ученик",
        "Я преподаватель или родитель",
        "mp-fan",
        "Закрасьте 1/2 фигуры",
        "(x + 2)(x + 1) = x² + [ ] + 2",
        "f(x) = x² − 4x + 5",
        "6–8–10 → S = ?",
        "sin(x) = cos(x)",
        "ОРТ / SAT прогноз баллов",
        'data-exam="ort"',
        'data-exam="ent"',
        'data-exam="ege"',
        'data-exam="oge"',
        'data-exam="sat"',
        'data-exam="csca"',
        'data-exam="olymp"',
        'data-exam="calc1"',
        "Интерактивный тренажёр, а не просто ответы",
        "Как устроена подготовка в Monday",
        "Банк вопросов с фильтрами",
        "Тренировочные сессии",
        "Сборники и пробные тесты",
        "Справочник и шпаргалки формул",
        'data-demo-tab="bank"',
        'data-demo-tab="session"',
        'data-demo-tab="tests"',
        'data-demo-tab="formulas"',
        "Показать задачу",
        "Запустить мини-сессию",
        "Интерактивные значения углов",
        "ОРТ · Математика",
        "Бланк ответов",
        "Колонка А",
        "Колонка Б",
        "Пройти полный вариант ОРТ →",
        "mp-sky__wave-top",
        "mp-sky__stars",
        "Desmos Graphing Calculator",
        "Digital SAT · Module 1",
        "Учись в любое время, с любого устройства",
        "mp-aud-bg",
        "mp-aud-3d--pi",
        "mp-aud-3d--x2",
        "mp-aud-3d--prism",
        "mp-aud-3d--sum",
        "mp-aud-3d--torus",
        "Для учеников",
        "Для преподавателей и родителей",
        "1. Диагностика уровня",
        "2. Интерактивная практика",
        "3. Контроль прогресса с преподавателем",
        "data-cta-reveal",
        "mp-cta-sky",
        "Начни подготовку с Monday сегодня",
        "mp-btn--soft mp-btn--wide",
        "Начать бесплатно",
        "mp-wave__layers",
        "mp-wave-geom",
        "https://instagram.com/monday_edc",
        "mailto:temirlanmanasev@gmail.com",
        "© 2026 Monday Academy",
        "static/js/landing.js",
    ):
        assert expected in html, f"Missing expected copy on /: {expected}"

    # Verify removed clutter: no center header nav links, no hero account/status lines, no 4-box metrics, no secondary tabs, no rectangular wave cards
    assert 'class="mp-nav"' not in html
    assert "У меня уже есть аккаунт" not in html
    assert "Открытый доступ без подписки" not in html
    assert 'class="mp-metrics"' not in html
    assert 'data-mode-panel="exam"' not in html
    assert 'class="mp-wave-card' not in html
    assert "data-math-bg" not in html
    assert "data-route-gutter" not in html
    assert "static/js/dot-engine.js" not in html
    assert "data-strip-scroll" not in html
    assert "зад.</span>" not in html
    assert anon.get("/api/public/hero-question").status_code == 404

    # Existing auth routing rules stay intact for logged-in users
    c_stu = app.test_client()
    assert c_stu.post("/login", data={"email": "s_land@monday.kg", "password": "Pass12345!"}).status_code == 302
    assert "/home" in c_stu.get("/", follow_redirects=False).headers["Location"]

    c_adm = app.test_client()
    assert c_adm.post("/login", data={"email": "a_land@monday.kg", "password": "StrongAdmin123!"}).status_code == 302
    assert "/teacher" in c_adm.get("/", follow_redirects=False).headers["Location"]


def test_stage2_exam_page_sample_check_opaque_tokens_and_removed_hero_endpoint(tmp_path):
    """GET /api/public/hero-question is removed (404); POST /api/public/hero-question/check remains strictly for /exams/<slug> opaque sample tokens."""
    app = _make_app(tmp_path, public_enabled=True, HERO_QUESTION_TOKEN_TTL_SECONDS=60)
    with app.app_context():
        top = ContentNode.query.filter_by(code="b-alg").first() or ContentNode(code="s2_top", name="Алгебра", level="topic", exams=["ORT"])
        if top.id is None:
            db.session.add(top)
            db.session.flush()
        skill = ContentNode(code="s2_sk", name="Линейные уравнения", level="node", parent_id=top.id, exams=["ORT"])
        db.session.add(skill)
        db.session.flush()

        img_name = storage.save("q-hero-sample.png", PNG_1PX, "image/png")
        q_pub = Question(
            skill=skill,
            exams=["ORT"],
            difficulty=1,
            text="Решите уравнение $2x + 5 = 13$.",
            image_path=img_name,
            answer_type="choice",
            options=["3", "4", "5", "6"],
            correct="1",
            explanation="SECRET_EXPLANATION_TEXT",
            status="published",
        )
        q_priv = Question(
            skill=skill,
            exams=["ORT"],
            difficulty=2,
            text="PRIVATE_UNFLAGGED_QUESTION_TEXT",
            answer_type="choice",
            options=["10", "20", "30", "40"],
            correct="0",
            status="published",
            is_public_sample=False,
        )
        db.session.add_all([q_pub, q_priv])
        db.session.flush()
        set_question_public_sample(q_pub, True)
        db.session.commit()
        pub_qid = q_pub.id
        priv_qid = q_priv.id
        token = issue_public_sample_token(pub_qid, "ORT")

    c = app.test_client()
    # Removed hero-question GET endpoint returns 404
    assert c.get("/api/public/hero-question").status_code == 404

    # /exams/ort renders the sample with opaque token and loads dot-engine.js
    ort_html = c.get("/exams/ort").data.decode("utf-8")
    assert "static/js/dot-engine.js" in ort_html
    assert "SECRET_EXPLANATION_TEXT" not in ort_html
    assert "PRIVATE_UNFLAGGED_QUESTION_TEXT" not in ort_html

    # Wrong answer returns hint without revealing the correct option index
    r_wrong = c.post("/api/public/hero-question/check", json={"token": token, "choice": 0})
    assert r_wrong.status_code == 200
    w_data = r_wrong.get_json()
    assert w_data["ok"] is True and w_data["correct"] is False
    assert "Подсказка" in w_data["hint"]
    assert "correct_choice" not in w_data

    # Correct answer returns badge and /exams/ort link
    r_right = c.post("/api/public/hero-question/check", json={"token": token, "choice": 1})
    assert r_right.status_code == 200
    r_data = r_right.get_json()
    assert r_data["ok"] is True and r_data["correct"] is True
    assert "Это вопрос ОРТ" in r_data["badge"]
    assert r_data["exam_url"] == "/exams/ort"

    # Tampered token, expired token, and token for unflagged question are rejected
    assert c.post("/api/public/hero-question/check", json={"token": token + "tamper", "choice": 1}).status_code == 400
    with app.app_context():
        assert verify_public_sample_token(token, max_age=-1) is None
        priv_token = issue_public_sample_token(priv_qid, "ORT")
    assert c.post("/api/public/hero-question/check", json={"token": priv_token, "choice": 0}).status_code == 404

    # Unflagging the sample invalidates existing tokens immediately
    with app.app_context():
        set_question_public_sample(db.session.get(Question, pub_qid), False)
        db.session.commit()
    assert c.post("/api/public/hero-question/check", json={"token": token, "choice": 1}).status_code == 404


def test_stage3_public_stats_api_thresholds_and_bishkek_timezone(tmp_path):
    app = _make_app(
        tmp_path,
        public_enabled=True,
        PUBLIC_STATS_MIN_QUESTIONS=2,
        PUBLIC_STATS_MIN_TOPICS=1,
        PUBLIC_STATS_MIN_TOPIC_QUESTIONS=2,  # Algebra has 2 -> shown; Geometry has 0 -> None/hidden!
        PUBLIC_STATS_MIN_COLLECTIONS=5,  # intentionally above seeded count (0) -> must be hidden!
        PUBLIC_STATS_MIN_SOLVED_TODAY=2,
        PUBLIC_STATS_MIN_SOLVED_WEEK=3,
        PUBLIC_STATS_MIN_MONDAY_PARTICIPANTS=10,  # above 0 -> hidden!
        MONDAY_TEST_SCHEDULE_PUBLIC=False,
    )
    with app.app_context():
        stu = User(email="stats_stu@monday.kg", name="Secret Student Name", role="student", is_approved=True)
        stu.set_password("Pass12345!")
        alg_topic = ContentNode.query.filter_by(code="b-alg").first()
        assert alg_topic is not None
        db.session.add(stu)
        db.session.flush()
        node = ContentNode(code="s3_n", name="Linear", level="node", parent_id=alg_topic.id, exams=["ORT"])
        db.session.add(node)
        db.session.flush()

        q1 = Question(skill=node, exams=["ORT"], difficulty=1, text="Q1", options=["1", "2"], correct="0", status="published")
        q2 = Question(skill=node, exams=["ORT"], difficulty=1, text="Q2", options=["1", "2"], correct="0", status="published")
        db.session.add_all([q1, q2])
        db.session.flush()

        att = Attempt(user_id=stu.id, mode="franklin", plan=[q1.id, q2.id], total=2)
        db.session.add(att)
        db.session.flush()

        # Bishkek midnight in naive UTC
        bishkek_midnight = local_midnight_utc()
        # 2 answers today (after Bishkek midnight), 1 answer 5 minutes before Bishkek midnight (yesterday)
        db.session.add_all([
            AttemptAnswer(attempt_id=att.id, index=0, question_id=q1.id, is_correct=True, answered_at=bishkek_midnight + timedelta(minutes=10)),
            AttemptAnswer(attempt_id=att.id, index=1, question_id=q2.id, is_correct=True, answered_at=bishkek_midnight + timedelta(minutes=20)),
            AttemptAnswer(attempt_id=att.id, index=2, question_id=q1.id, is_correct=False, answered_at=bishkek_midnight - timedelta(minutes=5)),
        ])
        db.session.commit()

    clear_public_stats_cache()
    c = app.test_client()
    r = c.get("/api/public/stats")
    assert r.status_code == 200
    assert "max-age=60" in (r.headers.get("Cache-Control") or "")
    data = r.get_json()
    raw_json = json.dumps(data, ensure_ascii=False)
    # Zero personal data or user IDs
    assert "stats_stu@monday.kg" not in raw_json
    assert "Secret Student Name" not in raw_json
    assert "user_id" not in raw_json
    assert data["timezone"] == "Asia/Bishkek"

    counters = data["counters"]
    assert counters["published_questions"] == 2
    assert counters["topics_count"] >= 1
    assert counters["solved_today"] == 2
    # Below threshold counters are None (hidden)
    assert counters["collections_count"] is None
    assert counters["last_monday_participants"] is None
    assert counters["next_monday_test"] is None

    # Real DB per-topic counts in /api/public/stats (threshold-gated)
    topics_by_code = {t["code"]: t for t in data["topics"]}
    assert set(topics_by_code.keys()) == {"b-alg", "b-geo", "b-trig", "b-fn", "b-stat", "b-logic"}
    assert topics_by_code["b-alg"]["count"] == 2
    assert topics_by_code["b-geo"]["count"] is None  # 0 < PUBLIC_STATS_MIN_TOPIC_QUESTIONS=2

    # HTML stats strip on /exams/ort hides below-threshold cards completely
    ort_html = c.get("/exams/ort").data.decode("utf-8")
    assert 'data-stat-card="published_questions"' in ort_html
    assert 'data-stat-card="solved_today"' in ort_html
    assert 'data-stat-card="collections_count"' not in ort_html
    assert 'data-stat-card="last_monday_participants"' not in ort_html
    assert 'data-stat-card="next_monday_test"' not in ort_html

    # When MONDAY_TEST_SCHEDULE_PUBLIC=True, /exams/ort stats strip renders the countdown
    app.config["MONDAY_TEST_SCHEDULE_PUBLIC"] = True
    clear_public_stats_cache()
    ort_sched = c.get("/exams/ort").data.decode("utf-8")
    assert "data-monday-countdown=" in ort_sched


def test_stage4_exam_page_ort_preflight_guard_sitemap_and_lead_form(tmp_path):
    app = _make_app(tmp_path, public_enabled=True, csrf_enabled=False)
    with app.app_context():
        node = ContentNode(code="s4_ort", name="Алгебра ОРТ", level="node", exams=list(EXAMS.keys()))
        db.session.add(node)
        db.session.flush()
        q_ort = Question(
            skill=node,
            exams=list(EXAMS.keys()),
            difficulty=1,
            text="Сравните $3x + 4$ и $2x + 4$ при $x > 1$.",
            options=["Колонка А", "Колонка Б", "Равны", "Мало данных"],
            correct="0",
            status="published",
        )
        q_non_sample = Question(
            skill=node,
            exams=["ORT"],
            difficulty=2,
            text="NON_SAMPLE_SECRET_ORT_QUESTION",
            options=["1", "2"],
            correct="0",
            status="published",
            is_public_sample=False,
        )
        db.session.add_all([q_ort, q_non_sample])
        db.session.flush()
        set_question_public_sample(q_ort, True)
        db.session.commit()

    c = app.test_client()
    # 1. /exams/ort and /ort render 200 OK with verified structure, scoring, timeline, sample, formulas, FAQ, lead form
    for url in ("/exams/ort", "/ort"):
        r = c.get(url)
        assert r.status_code == 200
        html = r.data.decode("utf-8")
        assert "Подготовка к ОРТ по математике" in html
        assert "Математика · Часть 1 — Сравнение величин" in html
        assert "Математика · Часть 2 — Задачи с выбором из 5 ответов" in html
        assert "Сравните $3x + 4$ и $2x + 4$" in html
        assert "Разность квадратов" in html
        assert "FAQPage" in html
        assert "NON_SAMPLE_SECRET_ORT_QUESTION" not in html
        assert "[требует подтверждения" not in html

    # 2. Unknown exam slug returns 404
    assert c.get("/exams/nonexistent").status_code == 404

    # 3. Sitemap includes /exams/ort when verified
    sm_xml = c.get("/sitemap.xml").data.decode("utf-8")
    assert "/exams/ort" in sm_xml

    # 4. Lead form submission on /exams/ort creates one Lead with interest='ОРТ' and source='site'
    r_apply = c.post(
        "/apply",
        data={
            "full_name": "Айдана ОРТ",
            "phone": "+996700555666",
            "interest": "ОРТ",
            "mode_preference": "offline",
            "consent": "1",
            "consent_required": "1",
            "next": "/exams/ort",
        },
        follow_redirects=True,
    )
    assert r_apply.status_code == 200
    with app.app_context():
        lead = Lead.query.filter_by(full_name="Айдана ОРТ").one()
        assert lead.source == "site"
        assert lead.interest == "ОРТ"

    # 5. Unverified fact in exam content file fails preflight guard
    unverified_dir = tmp_path / "unverified_exams"
    unverified_dir.mkdir()
    bad_ort = json.loads((ROOT_DIR / "monday" / "data" / "exams" / "ort.json").read_text(encoding="utf-8"))
    bad_ort["facts"]["organizer"]["verified"] = False
    (unverified_dir / "ort.json").write_text(json.dumps(bad_ort, ensure_ascii=False), encoding="utf-8")

    with app.app_context():
        blockers = collect_site_preflight_blockers(exam_data_dir=unverified_dir)
        assert any("unverified fact" in b for b in blockers), blockers


def test_playwright_landing_interactive_challenge_and_csp(tmp_path):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return

    app = _make_app(tmp_path, public_enabled=True, csrf_enabled=True)
    with app.app_context():
        alg_topic = ContentNode.query.filter_by(code="b-alg").first()
        node = ContentNode(code="pw_ort", name="Алгебра", level="node", parent_id=(alg_topic.id if alg_topic else None), exams=["ORT"])
        db.session.add(node)
        db.session.flush()
        q = Question(
            skill=node,
            exams=["ORT"],
            difficulty=1,
            text="Найдите $x$, если $2x + 4 = 10$.",
            options=["2", "3", "4", "5"],
            correct="1",
            status="published",
        )
        adm = User(email="adm_pw@monday.kg", name="Admin PW", role="admin", is_approved=True)
        adm.set_password("StrongAdmin123!")
        db.session.add_all([q, adm])
        db.session.flush()
        set_question_public_sample(q, True)
        db.session.commit()

    app.config["SERVER_NAME"] = None
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.add_init_script(
                'window.__csp = []; window.__errs = [];'
                'document.addEventListener("securitypolicyviolation", e => window.__csp.push(e.violatedDirective));'
                'window.addEventListener("pageerror", e => window.__errs.push(String(e)));'
            )

            page.goto(f"{base_url}/", wait_until="networkidle")
            assert page.locator(".mp-hero h1").is_visible()
            assert page.locator(".mp-fan").is_visible()
            assert page.locator("[data-math-bg]").count() == 0
            assert page.locator("[data-route-gutter]").count() == 0
            assert page.locator("[data-dot-canvas]").count() == 0

            # Verify White (#FFFFFF) canvas, Soft Light Blue hero pill, and strictly black (#000000) footer
            body_bg = page.locator("body.pub-body").evaluate("el => getComputedStyle(el).backgroundColor")
            assert body_bg == "rgb(255, 255, 255)"
            pill_bg = page.locator(".mp-hero__pill").first.evaluate("el => getComputedStyle(el).backgroundColor")
            assert pill_bg == "rgb(238, 244, 255)"
            footer_bg = page.locator(".mp-footer").evaluate("el => getComputedStyle(el).backgroundColor")
            assert footer_bg == "rgb(0, 0, 0)"

            # Verify each exam badge in the infinite marquee has its own distinct assigned color
            expected_badge_colors = {
                "ort": "rgb(31, 79, 224)",     # #1F4FE0 Monday Blue
                "ent": "rgb(13, 148, 136)",    # #0D9488 Emerald Teal
                "ege": "rgb(220, 38, 38)",     # #DC2626 Coral Crimson
                "oge": "rgb(217, 119, 6)",     # #D97706 Warm Amber
                "sat": "rgb(79, 70, 229)",     # #4F46E5 Deep Indigo
                "csca": "rgb(2, 132, 199)",    # #0284C7 Vivid Sky
                "olymp": "rgb(124, 58, 237)",  # #7C3AED Royal Violet
                "calc1": "rgb(219, 39, 119)",  # #DB2777 Berry Rose
            }
            actual_colors = page.evaluate("""() => {
                const res = {};
                document.querySelectorAll('.mp-marquee__group:first-child .mp-strip__item[data-exam]').forEach(el => {
                    const key = el.getAttribute('data-exam');
                    const badge = el.querySelector('.mp-strip__badge');
                    res[key] = badge ? getComputedStyle(badge).backgroundColor : '';
                });
                return res;
            }""")
            assert actual_colors == expected_badge_colors, f"Marquee badge colors mismatch: {actual_colors}"
            assert len(set(actual_colors.values())) == 8

            # Verify zero horizontal overflow, borderless transparent sticky header, centered hero H1, and non-clipped sky-band cards at 1440px, 1280px, 1024px, and 390px viewports
            assert page.locator(".mp-header__pill").count() == 0
            hdr_top = page.evaluate("""() => {
                const h = document.querySelector('[data-site-header]');
                const inner = document.querySelector('.mp-header__inner');
                const hs = getComputedStyle(h);
                const is = getComputedStyle(inner);
                return {
                    pos: hs.position,
                    bg: hs.backgroundColor,
                    hasScrolled: h.classList.contains('is-scrolled'),
                    innerRadius: is.borderRadius,
                    innerBorder: is.borderTopWidth,
                    innerShadow: is.boxShadow,
                };
            }""")
            assert hdr_top["pos"] == "sticky", hdr_top
            assert hdr_top["bg"] == "rgba(0, 0, 0, 0)" and not hdr_top["hasScrolled"], hdr_top
            assert hdr_top["innerRadius"] == "0px" and hdr_top["innerBorder"] == "0px" and hdr_top["innerShadow"] == "none", hdr_top

            for vw, vh in ((1440, 900), (1280, 840), (1024, 900), (390, 844)):
                page.set_viewport_size({"width": vw, "height": vh})
                page.wait_for_timeout(100)
                metrics = page.evaluate(
                    "() => {"
                    "  const r = document.querySelector('.mp-hero h1').getBoundingClientRect();"
                    "  const satFoot = document.querySelector('.mp-sat-card__foot').getBoundingClientRect();"
                    "  const navInner = document.querySelector('.mp-header__inner').getBoundingClientRect();"
                    "  const audBg = document.querySelector('.mp-aud-bg');"
                    "  return {"
                    "    scrollW: document.documentElement.scrollWidth,"
                    "    innerW: window.innerWidth,"
                    "    h1Left: r.left,"
                    "    h1Right: r.right,"
                    "    h1Center: r.left + r.width / 2,"
                    "    satLeft: satFoot.left,"
                    "    satRight: satFoot.right,"
                    "    navH: Math.round(navInner.height),"
                    "    audBgDisplay: audBg ? getComputedStyle(audBg).display : ''"
                    "  };"
                    "}"
                )
                assert metrics["scrollW"] <= metrics["innerW"] + 1, f"Horizontal overflow at {vw}px: {metrics}"
                assert metrics["h1Left"] >= 0 and metrics["h1Right"] <= metrics["innerW"] + 1, f"H1 clipped at {vw}px: {metrics}"
                assert abs(metrics["h1Center"] - metrics["innerW"] / 2) <= 24, f"H1 not centered at {vw}px: {metrics}"
                assert metrics["satLeft"] >= 0 and metrics["satRight"] <= metrics["innerW"] + 1, f"Mastery badge clipped at {vw}px: {metrics}"
                assert metrics["navH"] <= 72, f"Borderless navbar wrapped at {vw}px: {metrics}"
                if vw <= 1200:
                    assert metrics["audBgDisplay"] == "none", f"3D margin shapes must hide at {vw}px"
                else:
                    assert metrics["audBgDisplay"] != "none", f"3D margin shapes should show at {vw}px"

            # Mobile 390px: verify burger toggle opens and closes cleanly
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator("[data-nav-toggle]").click()
            page.locator("[data-nav-panel]").wait_for(state="visible", timeout=3000)
            page.keyboard.press("Escape")
            page.locator("[data-nav-panel]").wait_for(state="hidden", timeout=3000)

            # Verify scroll activates progressive frosted-blur glass header (.is-scrolled)
            page.set_viewport_size({"width": 1440, "height": 900})
            page.evaluate("window.scrollTo(0, 120)")
            page.wait_for_function(
                "() => {"
                "  const h = document.querySelector('[data-site-header]');"
                "  return h && h.classList.contains('is-scrolled') && getComputedStyle(h).backgroundColor === 'rgba(255, 255, 255, 0.8)';"
                "}"
            )
            page.evaluate("window.scrollTo(0, 0)")

            # Verify Jet-Black Starry Night .mp-sky band (shallow wave, 15 stars, crisp white Desmos/SAT cards) and 3D margin shapes at 1440px
            page.set_viewport_size({"width": 1440, "height": 900})
            sky_checks = page.evaluate("""() => {
                const sky = document.querySelector('.mp-sky');
                const skyH = document.querySelector('.mp-sky__h');
                const wave = document.querySelector('.mp-sky__wave-top');
                const desmos = document.querySelector('.mp-desmos-card');
                const sat = document.querySelector('.mp-sat-card');
                const stars = document.querySelectorAll('.mp-sky__stars .mp-star').length;
                const shapes3d = document.querySelectorAll('.mp-aud-bg .mp-aud-3d').length;
                const sparkles = document.querySelectorAll('.mp-aud-bg .mp-aud-spark').length;
                const audCards = Array.from(document.querySelectorAll('.mp-aud__card, .mp-loop__step')).map(el => el.getBoundingClientRect());
                const shapeRects = Array.from(document.querySelectorAll('.mp-aud-bg .mp-aud-3d')).map(el => el.getBoundingClientRect());
                let overlaps = 0;
                for (const sr of shapeRects) {
                    for (const cr of audCards) {
                        const horiz = sr.right > cr.left + 2 && sr.left < cr.right - 2;
                        const vert = sr.bottom > cr.top + 2 && sr.top < cr.bottom - 2;
                        if (horiz && vert) overlaps++;
                    }
                }
                return {
                    skyBgImg: getComputedStyle(sky).backgroundImage,
                    skyHColor: getComputedStyle(skyH).color,
                    waveH: Math.round(wave.getBoundingClientRect().height),
                    desmosBg: getComputedStyle(desmos).backgroundColor,
                    satBg: getComputedStyle(sat).backgroundColor,
                    stars,
                    shapes3d,
                    sparkles,
                    overlaps,
                };
            }""")
            assert "rgb(7, 10, 18)" in sky_checks["skyBgImg"] and "rgb(0, 0, 0)" in sky_checks["skyBgImg"], sky_checks
            assert sky_checks["skyHColor"] == "rgb(255, 255, 255)", sky_checks
            assert sky_checks["waveH"] <= 46, sky_checks
            assert sky_checks["desmosBg"] == "rgb(255, 255, 255)" and sky_checks["satBg"] == "rgb(255, 255, 255)", sky_checks
            assert sky_checks["stars"] >= 15, sky_checks
            assert sky_checks["shapes3d"] == 5 and sky_checks["sparkles"] == 4, sky_checks
            assert sky_checks["overlaps"] == 0, f"3D margin shapes overlapped audience cards: {sky_checks}"

            page.set_viewport_size({"width": 1280, "height": 840})

            # Interactive 4-Tab Sandbox: Tab 3 (ORT Mini-Test) is default active
            ort = page.locator("[data-ort-minitest]")
            assert ort.is_visible()
            assert page.locator('button[role="tab"].mp-page-card').count() == 4
            assert page.locator('[data-demo-tab="tests"]').get_attribute("aria-selected") == "true"

            q0 = ort.locator('[data-ort-q="0"]')
            q0.locator('[data-ort-bubble][aria-label="А"]').click()
            q0.locator("[data-ort-explain]").wait_for(state="visible", timeout=5000)
            assert "is-right" in (q0.locator('[data-ort-bubble][aria-label="А"]').get_attribute("class") or "")
            q0.locator('[data-ort-next="1"]').click()

            q1 = ort.locator('[data-ort-q="1"]')
            q1.wait_for(state="visible", timeout=5000)
            q1.locator('[data-ort-bubble][aria-label="В"]').click()
            q1.locator("[data-ort-explain]").wait_for(state="visible", timeout=5000)
            q1.locator('[data-ort-next="2"]').click()

            q2 = ort.locator('[data-ort-q="2"]')
            q2.wait_for(state="visible", timeout=5000)
            q2.locator('[data-ort-bubble][aria-label="Б"]').click()
            q2.locator("[data-ort-explain]").wait_for(state="visible", timeout=5000)
            assert q2.locator('a:has-text("Пройти полный вариант ОРТ")').is_visible()

            # Switch to Tab 1 (Question Bank with Filters): choose SAT + Геометрия + Средняя -> click Показать задачу -> answer -> see 2-step explanation
            page.locator('[data-demo-tab="bank"]').click()
            bank = page.locator("[data-bank-demo]")
            bank.wait_for(state="visible", timeout=5000)
            assert page.locator('[data-demo-tab="bank"]').get_attribute("aria-selected") == "true"
            bank.locator('[data-bank-filter="exam"][data-value="SAT"]').click()
            bank.locator('[data-bank-filter="topic"][data-value="geo"]').click()
            bank.locator('[data-bank-filter="diff"][data-value="medium"]').click()
            bank.locator("[data-bank-show]").click()
            assert "SAT · Геометрия · Средняя" in (bank.locator("[data-bank-meta]").text_content() or "")
            bank.locator('[data-bank-opt="1"]').click()
            bank.locator("[data-bank-explain]").wait_for(state="visible", timeout=5000)
            assert bank.locator("[data-bank-steps] li").count() == 2
            assert bank.locator('a[href="/question-bank"]').is_visible()

            # Switch to Tab 2 (Training Sessions): pick mode -> start 3-question drill -> finish -> see "Результат: 3 / 3"
            page.locator('[data-demo-tab="session"]').click()
            sess = page.locator("[data-session-demo]")
            sess.wait_for(state="visible", timeout=5000)
            sess.locator('[data-session-mode="mistakes"]').click()
            sess.locator("[data-session-start]").click()
            sess.locator("[data-session-drill]").wait_for(state="visible", timeout=5000)
            for correct_idx in ("1", "0", "2"):
                sess.locator(f'[data-drill-opt="{correct_idx}"]').click()
                sess.locator("[data-drill-explain]").wait_for(state="visible", timeout=5000)
                sess.locator("[data-drill-next]").click()
            sess.locator("[data-session-summary]").wait_for(state="visible", timeout=5000)
            assert "Результат: 3 / 3" in (sess.locator("[data-drill-score]").text_content() or "")

            # Switch to Tab 4 (Formula Reference + Interactive Trig Angle Switcher)
            page.locator('[data-demo-tab="formulas"]').click()
            f_pane = page.locator("[data-formulas-demo]")
            f_pane.wait_for(state="visible", timeout=5000)
            f_pane.locator('[data-formula-cat="trig"]').click()
            assert f_pane.locator('[data-formula-panel="trig"]').is_visible()
            f_pane.locator('[data-trig-angle="90"]').click()
            assert "не опр." in (f_pane.locator("[data-trig-tan]").text_content() or "")

            # Pre-footer sun (~1.3x) & continuous rightward-drifting cloud bank reveal on scroll + soft light-blue CTA button color
            cta_sec = page.locator("[data-cta-reveal]")
            cta_sec.scroll_into_view_if_needed()
            page.wait_for_function("() => document.querySelector('[data-cta-reveal]').classList.contains('is-revealed')")
            cta_sky = page.evaluate("""() => {
                const sun = document.querySelector('.mp-cta-sun-svg');
                const sky = document.querySelector('.mp-cta-sky');
                const backTrack = document.querySelector('.mp-cta-clouds__track--back');
                const frontTrack = document.querySelector('.mp-cta-clouds__track--front');
                return {
                    sunW: sun ? Math.round(sun.getBoundingClientRect().width) : 0,
                    skyOverflow: sky ? getComputedStyle(sky).overflow : '',
                    backAnim: backTrack ? getComputedStyle(backTrack).animationName : '',
                    frontAnim: frontTrack ? getComputedStyle(frontTrack).animationName : '',
                    backSvgCount: backTrack ? backTrack.querySelectorAll('svg').length : 0,
                    frontSvgCount: frontTrack ? frontTrack.querySelectorAll('svg').length : 0,
                };
            }""")
            assert 88 <= cta_sky["sunW"] <= 116, cta_sky
            assert cta_sky["skyOverflow"] == "hidden", cta_sky
            assert cta_sky["backAnim"] == "mpCloudDriftRight" and cta_sky["frontAnim"] == "mpCloudDriftRight", cta_sky
            assert cta_sky["backSvgCount"] == 2 and cta_sky["frontSvgCount"] == 2, cta_sky
            cta_btn_bg = cta_sec.locator(".mp-btn--soft").evaluate("el => getComputedStyle(el).backgroundColor")
            assert cta_btn_bg == "rgb(238, 244, 255)", f"Expected soft light-blue CTA button, got {cta_btn_bg}"

            # Check /exams/ort, /question-bank, /login, /register in browser for zero CSP violations & zero horizontal overflow
            for route in ("/exams/ort", "/question-bank", "/login", "/register"):
                resp_r = page.goto(f"{base_url}{route}", wait_until="networkidle")
                assert resp_r.status == 200, f"{route} returned {resp_r.status}"
                for vw, vh in ((1440, 900), (1024, 900), (390, 844)):
                    page.set_viewport_size({"width": vw, "height": vh})
                    page.wait_for_timeout(60)
                    ov = page.evaluate("() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth })")
                    assert ov["sw"] <= ov["iw"] + 1, f"Overflow on {route} at {vw}px: {ov}"
            page.goto(f"{base_url}/exams/ort", wait_until="networkidle")
            assert page.locator("#mp-exam-h").is_visible()
            assert page.locator("[data-dot-canvas]").is_visible()

            # Verify /admin/preview returns 200 OK and pins the borderless sticky header directly beneath .pub-preview-bar
            page.goto(f"{base_url}/login", wait_until="networkidle")
            page.fill('input[name="email"]', "adm_pw@monday.kg")
            page.fill('input[name="password"]', "StrongAdmin123!")
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle")
            page.set_viewport_size({"width": 1440, "height": 900})
            resp_prev = page.goto(f"{base_url}/admin/preview?page=landing", wait_until="networkidle")
            assert resp_prev.status == 200
            assert page.locator(".pub-preview-bar").is_visible()
            page.evaluate("window.scrollTo(0, 260)")
            page.wait_for_timeout(100)
            prev_pos = page.evaluate("""() => {
                const bar = document.querySelector('.pub-preview-bar').getBoundingClientRect();
                const hdr = document.querySelector('[data-site-header]').getBoundingClientRect();
                return { barBottom: Math.round(bar.bottom), hdrTop: Math.round(hdr.top) };
            }""")
            assert abs(prev_pos["hdrTop"] - prev_pos["barBottom"]) <= 2, f"Navbar overlapped admin preview bar: {prev_pos}"
            assert page.locator(".mp-fan").is_visible()
            assert page.locator('.mp-strip__item[data-exam="ent"]').first.is_visible()

            assert page.evaluate("window.__csp") == []
            assert page.evaluate("window.__errs") == []
            browser.close()
    finally:
        server.shutdown()

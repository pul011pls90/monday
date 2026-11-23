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

    r = anon.get("/")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    for expected in (
        "Персональный тренажёр по",
        "математике и экзаменам",
        "Я ученик",
        "Я преподаватель или родитель",
        "У меня уже есть аккаунт",
        "data-dot-canvas",
        "data-skip-intro",
        "data-hero-question-card",
        "Закрасьте 1/2 фигуры",
        "(x + 2)(x + 1) = x² + [ ] + 2",
        "f(x) = x² − 4x + 5",
        "6–8–10 → S = ?",
        "sin(x) = cos(x)",
        "ОРТ / SAT прогноз баллов",
        "Интерактивный тренажёр, а не просто ответы",
        "Мини-тест ОРТ",
        "ОРТ · Математика",
        "Бланк ответов",
        "Колонка А",
        "Колонка Б",
        "Пройти полный вариант ОРТ →",
        "Desmos Graphing Calculator",
        "Digital SAT · Module 1",
        "Учись в любое время, с любого устройства",
        "Для учеников",
        "Для преподавателей и родителей",
        "1. Диагностика уровня",
        "2. Интерактивная практика",
        "3. Контроль прогресса с преподавателем",
        "Начни подготовку с Monday сегодня",
        "Прогноз ОРТ · Пример",
        "Desmos встроен",
        "Журнал ошибок",
        "Начать бесплатно",
        "https://instagram.com/monday_edc",
        "mailto:temirlanmanasev@gmail.com",
        "© 2026 Monday Academy",
        "static/js/dot-engine.js",
        "static/js/landing.js",
    ):
        assert expected in html, f"Missing expected copy on /: {expected}"

    assert "data-strip-scroll" not in html
    assert "зад.</span>" not in html
    assert "двигай точки, меняй уравнения" not in html

    # Query-string & deep-link adaptation (?exam=ort and ?utm_source=exam_sat); unknown exam ignored safely
    r_ort = anon.get("/?exam=ort").data.decode("utf-8")
    assert 'data-highlighted-exam="ORT"' in r_ort
    r_bot = anon.get("/?utm_source=exam_sat").data.decode("utf-8")
    assert 'data-highlighted-exam="SAT"' in r_bot
    r_unknown = anon.get("/?exam=<script>alert(1)</script>")
    assert r_unknown.status_code == 200
    assert "data-highlighted-exam" not in r_unknown.data.decode("utf-8")

    # Existing auth routing rules stay intact for logged-in users
    c_stu = app.test_client()
    assert c_stu.post("/login", data={"email": "s_land@monday.kg", "password": "Pass12345!"}).status_code == 302
    assert "/home" in c_stu.get("/", follow_redirects=False).headers["Location"]

    c_adm = app.test_client()
    assert c_adm.post("/login", data={"email": "a_land@monday.kg", "password": "StrongAdmin123!"}).status_code == 302
    assert "/teacher" in c_adm.get("/", follow_redirects=False).headers["Location"]


def test_stage2_hero_live_question_opaque_tokens_and_security(tmp_path):
    app = _make_app(tmp_path, public_enabled=True, HERO_QUESTION_TOKEN_TTL_SECONDS=60)
    with app.app_context():
        top = ContentNode(code="s2_top", name="Алгебра", level="topic", exams=["ORT"])
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
        pub_media_key = q_pub.public_image_key

    c = app.test_client()
    # 1. GET /api/public/hero-question serves only is_public_sample=True with an opaque token, never DB id or /uploads/
    r_get = c.get("/api/public/hero-question")
    assert r_get.status_code == 200
    payload = r_get.get_json()
    assert payload["ok"] is True
    q_data = payload["question"]
    assert "id" not in q_data
    assert "correct" not in q_data
    assert "SECRET_EXPLANATION_TEXT" not in json.dumps(payload, ensure_ascii=False)
    assert "PRIVATE_UNFLAGGED_QUESTION_TEXT" not in json.dumps(payload, ensure_ascii=False)
    assert q_data["image_url"] == f"/question-bank/media/{pub_media_key}"
    assert "/uploads/" not in (q_data["image_url"] or "")
    token = q_data["token"]
    assert isinstance(token, str) and len(token) > 20

    # 2. Wrong answer returns hint without revealing the correct option index
    r_wrong = c.post("/api/public/hero-question/check", json={"token": token, "choice": 0})
    assert r_wrong.status_code == 200
    w_data = r_wrong.get_json()
    assert w_data["ok"] is True and w_data["correct"] is False
    assert "Подсказка" in w_data["hint"]
    assert "correct_choice" not in w_data

    # 3. Correct answer returns "Это вопрос ОРТ · Алгебра" and /exams/ort link
    r_right = c.post("/api/public/hero-question/check", json={"token": token, "choice": 1})
    assert r_right.status_code == 200
    r_data = r_right.get_json()
    assert r_data["ok"] is True and r_data["correct"] is True
    assert "Это вопрос ОРТ · Алгебра" in r_data["badge"]
    assert r_data["exam_url"] == "/exams/ort"

    # 4. Tampered token, expired token, and token for unflagged question are rejected
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
        PUBLIC_STATS_MIN_COLLECTIONS=5,  # intentionally above seeded count (0) -> must be hidden!
        PUBLIC_STATS_MIN_SOLVED_TODAY=2,
        PUBLIC_STATS_MIN_SOLVED_WEEK=3,
        PUBLIC_STATS_MIN_MONDAY_PARTICIPANTS=10,  # above 0 -> hidden!
        MONDAY_TEST_SCHEDULE_PUBLIC=False,
    )
    with app.app_context():
        stu = User(email="stats_stu@monday.kg", name="Secret Student Name", role="student", is_approved=True)
        stu.set_password("Pass12345!")
        top = ContentNode(code="s3_t", name="Algebra", level="topic", exams=["ORT"])
        db.session.add_all([stu, top])
        db.session.flush()
        node = ContentNode(code="s3_n", name="Linear", level="node", parent_id=top.id, exams=["ORT"])
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

    # HTML strip hides below-threshold cards completely
    landing_html = c.get("/").data.decode("utf-8")
    assert 'data-stat-card="published_questions"' in landing_html
    assert 'data-stat-card="solved_today"' in landing_html
    assert 'data-stat-card="collections_count"' not in landing_html
    assert 'data-stat-card="last_monday_participants"' not in landing_html
    assert 'data-stat-card="next_monday_test"' not in landing_html


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
        node = ContentNode(code="pw_ort", name="Алгебра", level="node", exams=["ORT"])
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
        db.session.add(q)
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
            ctx = browser.new_context(viewport={"width": 1280, "height": 840})
            page = ctx.new_page()
            page.add_init_script(
                'window.__csp = []; window.__errs = [];'
                'document.addEventListener("securitypolicyviolation", e => window.__csp.push(e.violatedDirective));'
                'window.addEventListener("pageerror", e => window.__errs.push(String(e)));'
            )

            page.goto(f"{base_url}/", wait_until="networkidle")
            assert page.locator(".mp-hero h1").is_visible()
            assert page.locator("[data-dot-canvas]").is_visible()
            assert page.locator(".mp-fan").is_visible()

            # Verify White (#FFFFFF) canvas, Soft Light Blue (#EEF4FF -> rgb(238, 244, 255)) hero pill, and strictly black (#000000) footer
            body_bg = page.locator("body.pub-body").evaluate("el => getComputedStyle(el).backgroundColor")
            assert body_bg == "rgb(255, 255, 255)"
            pill_bg = page.locator(".mp-hero__pill").evaluate("el => getComputedStyle(el).backgroundColor")
            assert pill_bg == "rgb(238, 244, 255)"
            footer_bg = page.locator(".mp-footer").evaluate("el => getComputedStyle(el).backgroundColor")
            assert footer_bg == "rgb(0, 0, 0)"

            # Verify zero horizontal overflow, centered hero H1, and non-clipped sky-band cards at 1440px, 820px, and 390px viewports
            for vw, vh in ((1440, 900), (820, 900), (390, 844)):
                page.set_viewport_size({"width": vw, "height": vh})
                metrics = page.evaluate(
                    "() => {"
                    "  const r = document.querySelector('.mp-hero h1').getBoundingClientRect();"
                    "  const satFoot = document.querySelector('.mp-sat-card__foot').getBoundingClientRect();"
                    "  return {"
                    "    scrollW: document.documentElement.scrollWidth,"
                    "    innerW: window.innerWidth,"
                    "    h1Left: r.left,"
                    "    h1Right: r.right,"
                    "    h1Center: r.left + r.width / 2,"
                    "    satLeft: satFoot.left,"
                    "    satRight: satFoot.right"
                    "  };"
                    "}"
                )
                assert metrics["scrollW"] <= metrics["innerW"] + 1, f"Horizontal overflow at {vw}px: {metrics}"
                assert metrics["h1Left"] >= 0 and metrics["h1Right"] <= metrics["innerW"] + 1, f"H1 clipped at {vw}px: {metrics}"
                assert abs(metrics["h1Center"] - metrics["innerW"] / 2) <= 24, f"H1 not centered at {vw}px: {metrics}"
                assert metrics["satLeft"] >= 0 and metrics["satRight"] <= metrics["innerW"] + 1, f"Mastery badge clipped at {vw}px: {metrics}"

            page.set_viewport_size({"width": 1280, "height": 840})

            # Stage 2 live hero question interaction: tap wrong option -> hint; tap right option (index 1 -> "3") -> badge + CTA
            hero_q = page.locator(".mp-hero [data-hero-question-card]")
            hero_q.locator('[data-live-opt="0"]').click()
            hero_q.locator("[data-live-feedback]").wait_for(state="visible", timeout=5000)
            assert "is-wrong" in (hero_q.locator('[data-live-opt="0"]').get_attribute("class") or "")
            hero_q.locator('[data-live-opt="1"]').click()
            page.wait_for_function(
                "() => document.querySelector('.mp-hero [data-live-opt=\"1\"]').classList.contains('is-right')"
            )
            assert "Это вопрос ОРТ" in (hero_q.locator("[data-live-badge]").text_content() or "")

            # Dot engine perf stats check
            perf = page.evaluate("() => window.__mondayDotEngine && window.__mondayDotEngine.getPerfStats()")
            assert perf and perf["dpr"] <= 2 and perf["pointCount"] >= 260

            # Mode 1 (Мини-тест ОРТ): click bubble А on Q1 -> highlights right + reveals explanation -> advance to Q2 -> click В -> advance to Q3 -> click Б
            ort = page.locator("[data-ort-minitest]")
            assert ort.is_visible()
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

            # Switch to Mode 2 (По темам) -> switch subject tab -> Геометрия -> solve correctly
            page.click('[data-mode-btn="exam"]')
            page.click('[data-subject-tab="geometry"]')
            geom = page.locator('[data-subject-panel="geometry"]')
            geom.wait_for(state="visible", timeout=5000)
            geom.locator('[data-challenge-opt]:has-text("24")').click()
            assert "is-right" in (geom.locator('[data-challenge-opt]:has-text("24")').get_attribute("class") or "")
            geom.locator("[data-challenge-explain]").wait_for(state="visible", timeout=5000)

            # Check /exams/ort in browser for zero CSP violations
            page.goto(f"{base_url}/exams/ort", wait_until="networkidle")
            assert page.locator("#mp-exam-h").is_visible()

            assert page.evaluate("window.__csp") == []
            assert page.evaluate("window.__errs") == []
            browser.close()
    finally:
        server.shutdown()

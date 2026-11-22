"""Tests for Admin Course Lesson Builder (/admin/course): Stage 1 preview parity, XSS sanitization & labels."""
import secrets

from monday.course import render_course_html
from monday.extensions import db
from monday.models import CourseLesson, CourseUnit, StudentProfile, User
from scripts.seed_course import seed_course
from test_app import APP, client, login


def _mk_user(email: str, name: str, role: str, pw: str) -> int:
    with APP.app_context():
        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(email=email, name=name, role=role, is_approved=True, auth_provider="password")
            db.session.add(u)
        else:
            u.name = name
            u.role = role
            u.is_approved = True
            u.is_blocked = False
            u.auth_provider = "password"
        u.set_password(pw)
        db.session.flush()
        if role == "student":
            from datetime import timedelta
            from monday.models import utcnow
            u.legacy_access_until = utcnow() + timedelta(days=7)
            if not StudentProfile.query.filter_by(user_id=u.id).first():
                db.session.add(StudentProfile(user_id=u.id, exam="SAT", onboarded=True))
        db.session.commit()
        return u.id


def test_stage1_preview_parity_xss_sanitization_labels_and_rbac():
    pw_adm = secrets.token_urlsafe(12)
    pw_stu = secrets.token_urlsafe(12)
    pw_tch = secrets.token_urlsafe(12)
    _mk_user("cb.adm@example.com", "CB Admin", "admin", pw_adm)
    _mk_user("cb.stu@example.com", "CB Student", "student", pw_stu)
    _mk_user("cb.tch@example.com", "CB Teacher", "teacher", pw_tch)

    with APP.app_context():
        seed_course(dry_run=False)
        unit = CourseUnit.query.filter_by(exam="SAT").order_by(CourseUnit.number.asc()).first()
        lesson = unit.lessons.order_by(CourseLesson.position.asc()).first()
        unit_slug = unit.slug
        lesson_slug = lesson.slug
        lesson_id = lesson.id
        orig_md = lesson.article_md

    c_adm = login(client(), "cb.adm@example.com", pw_adm)
    c_stu = login(client(), "cb.stu@example.com", pw_stu)
    c_tch = login(client(), "cb.tch@example.com", pw_tch)

    # 1. RBAC: non-admin receives 403 on course builder & preview
    for non_adm in (c_stu, c_tch):
        assert non_adm.get("/admin/course").status_code == 403
        assert non_adm.post("/admin/course", data={"lesson_id": str(lesson_id), "article_md": "x"}).status_code == 403
        assert non_adm.post("/admin/course/preview", json={"article_md": "x"}).status_code == 403

    # 2. Label fix: delimiters protected with .no-math and KaTeX trust: false
    builder_html = c_adm.get(f"/admin/course?lesson_id={lesson_id}").data.decode()
    assert 'class="no-math">$...$</span>' in builder_html
    assert 'class="no-math">KaTeX $...$, \\(...\\)</span>' in builder_html
    assert "trust: false" in builder_html

    # 3. Preview vs Student parity + XSS stripping
    sample_md = (
        "# Главная тема\n\n"
        "### Подзаголовок\n"
        "Первая строка с **жирным**, *курсивом*, `кодом` и переносом.\n"
        "Вторая строка абзаца.\n\n"
        "- Пункт один\n"
        "- Пункт два с [ссылкой](https://monday.kg/docs)\n\n"
        "1. Шаг раз\n"
        "2. Шаг два\n\n"
        "Формулы: $a^2+b^2=c^2$ и \\(x + 1\\), а также:\n"
        "\\[y = mx + b\\]\n"
        "$$E = mc^2$$\n\n"
        '<script>alert("xss")</script> '
        '<img src="x" onerror="alert(1)"> '
        '<iframe src="https://evil.example"></iframe> '
        "[bad1](javascript:alert(1)) "
        "[bad2](data:text/html,<script>alert(1)</script>)"
    )

    try:
        r_pv = c_adm.post("/admin/course/preview", json={"article_md": sample_md})
        assert r_pv.status_code == 200
        pv_data = r_pv.get_json()
        assert pv_data["ok"] is True
        pv_html = pv_data["html"]

        # Exact match with shared renderer
        assert pv_html == str(render_course_html(sample_md))

        # Expected Markdown structures & KaTeX spans preserved verbatim
        assert "<h2>Главная тема</h2>" in pv_html
        assert "<h3>Подзаголовок</h3>" in pv_html
        assert "<strong>жирным</strong>" in pv_html
        assert "<em>курсивом</em>" in pv_html
        assert "<code>кодом</code>" in pv_html
        assert "<br>" in pv_html
        assert "<ul><li>Пункт один</li>" in pv_html
        assert '<a href="https://monday.kg/docs" target="_blank" rel="noopener noreferrer">ссылкой</a>' in pv_html
        assert "<ol><li>Шаг раз</li><li>Шаг два</li></ol>" in pv_html
        assert r"\(x + 1\)" in pv_html
        assert r"\[y = mx + b\]" in pv_html
        assert "$$E = mc^2$$" in pv_html

        # XSS payloads neutered
        for bad_needle in ("<script>", "<img ", "<iframe ", "javascript:alert", "data:text/html"):
            assert bad_needle not in pv_html
        assert "&lt;script&gt;" in pv_html
        assert "bad1" in pv_html
        assert "href=\"javascript:" not in pv_html

        # Save into lesson and verify student course player renders identical article HTML & trust: false
        r_save = c_adm.post(
            f"/admin/course?lesson_id={lesson_id}",
            data={"lesson_id": str(lesson_id), "article_md": sample_md},
        )
        assert r_save.status_code == 200

        stu_page = c_stu.get(f"/roadmap/SAT/{unit_slug}/{lesson_slug}").data.decode()
        assert pv_html in stu_page
        assert "trust: false" in stu_page
    finally:
        with APP.app_context():
            les = db.session.get(CourseLesson, lesson_id)
            if les:
                les.article_md = orig_md
                db.session.commit()

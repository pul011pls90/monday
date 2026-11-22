"""Stage 3 tests: Sender role badges, server-only snapshot, role filtering, profile links, and student-side 'Поддержка' reply label."""
from __future__ import annotations

from datetime import timedelta

from config import Config
from monday import create_app
from monday.extensions import db
from monday.models import Report, StudentProfile, User, utcnow


def _make_stage3_app(tmp_path):
    class Cfg(Config):
        TESTING = True
        SECRET_KEY = "sup-stage3-secret"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'stage3.db'}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SQLALCHEMY_ENGINE_OPTIONS = {}
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        SEED_DEMO = False
        IMPORT_PACKS = False

    app = create_app(Cfg, seed_if_empty=False)
    with app.app_context():
        db.create_all()
        users = [
            ("stu@s3.kg", "Айдана Ученик", "student"),
            ("tch@s3.kg", "Бакыт Учитель", "teacher"),
            ("ast@s3.kg", "Данияр Ассистент", "assistant"),
            ("mgr@s3.kg", "Камила Менеджер", "sales_manager"),
            ("sup@s3.kg", "Руслан Супервайзер", "supervisor"),
            ("adm@s3.kg", "Тимур СекретныйАдмин", "admin"),
        ]
        for email, name, role in users:
            u = User(email=email, name=name, role=role, is_approved=True)
            u.set_password("StrongPass123!")
            if role == "student":
                u.profile = StudentProfile(exam="SAT", grade="11", onboarded=True)
            db.session.add(u)
        db.session.commit()
    return app


def test_role_badges_filter_sort_forged_ignore_snapshot_and_student_support_label(tmp_path):
    app = _make_stage3_app(tmp_path)

    role_expectations = [
        ("stu@s3.kg", "student", "Ученик", "Сообщение от ученика"),
        ("tch@s3.kg", "teacher", "Учитель", "Сообщение от учителя"),
        ("ast@s3.kg", "assistant", "Ассистент", "Сообщение от ассистента"),
        ("mgr@s3.kg", "sales_manager", "Менеджер", "Сообщение от менеджера"),
        ("sup@s3.kg", "supervisor", "Супервайзер", "Сообщение от супервайзера"),
        ("adm@s3.kg", "admin", "Админ", "Сообщение от админа"),
    ]

    # Submit via /support with forged sender_role="admin" -> server ignores forged value and uses session role
    for idx, (email, expected_role, _label, body) in enumerate(role_expectations):
        c_user = app.test_client()
        assert c_user.post("/login", data={"email": email, "password": "StrongPass123!"}).status_code == 302
        r_post = c_user.post(
            "/support",
            data={
                "subject": "Техническая проблема",
                "message": body,
                "sender_role": "admin" if expected_role != "admin" else "student",
                "role": "supervisor",
            },
            follow_redirects=False,
        )
        assert r_post.status_code == 302

    # Adjust timestamps deterministically to verify newest-first sorting
    with app.app_context():
        base_t = utcnow()
        reps = Report.query.order_by(Report.id.asc()).all()
        assert len(reps) == len(role_expectations)
        for i, (rep, (_e, exp_role, _lbl, _b)) in enumerate(zip(reps, role_expectations)):
            assert rep.sender_role == exp_role
            rep.created_at = base_t + timedelta(minutes=i)
        db.session.commit()
        stu_report_id = reps[0].id
        stu_user_id = reps[0].author_id
        tch_user_id = reps[1].author_id

    c_adm = app.test_client()
    assert c_adm.post("/login", data={"email": "adm@s3.kg", "password": "StrongPass123!"}).status_code == 302

    # Admin inbox renders all role badges, sender names, profile links, newest-first order
    r_inbox = c_adm.get("/teacher/reports")
    assert r_inbox.status_code == 200
    html = r_inbox.data.decode("utf-8")
    for _email, _exp_role, label, body in role_expectations:
        assert label in html
        assert body in html
    assert f"/manager/students/{stu_user_id}" in html
    assert f"/manager/teachers/{tch_user_id}" in html
    assert html.index("Сообщение от админа") < html.index("Сообщение от ученика")

    # Role filter works cleanly
    r_mgr_filter = c_adm.get("/teacher/reports?role=sales_manager")
    mgr_html = r_mgr_filter.data.decode("utf-8")
    assert "Сообщение от менеджера" in mgr_html
    assert "Сообщение от ученика" not in mgr_html
    assert "Сообщение от учителя" not in mgr_html

    # Promote student user's role to 'teacher' later -> historical report keeps snapshot 'Ученик' badge
    with app.app_context():
        stu_u = db.session.get(User, stu_user_id)
        stu_u.role = "teacher"
        db.session.commit()

    r_after_promote = c_adm.get("/teacher/reports?role=student")
    prom_html = r_after_promote.data.decode("utf-8")
    assert "Сообщение от ученика" in prom_html
    assert 'data-sender-role="student"' in prom_html

    # Revert role back to student for student UI reply check; admin replies -> student sees "Поддержка" (no admin name)
    with app.app_context():
        stu_u = db.session.get(User, stu_user_id)
        stu_u.role = "student"
        db.session.commit()

    r_reply = c_adm.post(
        f"/teacher/reports/{stu_report_id}",
        data={"action": "fixed", "reply": "Мы всё починили"},
        follow_redirects=False,
    )
    assert r_reply.status_code == 302

    c_stu = app.test_client()
    assert c_stu.post("/login", data={"email": "stu@s3.kg", "password": "StrongPass123!"}).status_code == 302
    sup_html = c_stu.get("/support").data.decode("utf-8")
    assert "Поддержка" in sup_html
    assert "Мы всё починили" in sup_html
    assert "Тимур СекретныйАдмин" not in sup_html

    home_html = c_stu.get("/home").data.decode("utf-8")
    assert "Поддержка" in home_html
    assert "Мы всё починили" in home_html
    assert "Тимур СекретныйАдмин" not in home_html

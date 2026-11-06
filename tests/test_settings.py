"""Student settings: email, password help, hiding from rankings, practice defaults, a second subject."""
import re
from datetime import date

from monday.extensions import db
from monday.models import Attempt, AttemptAnswer, Question, StudentRecord, User, Work
from monday.services import monday_ranking
from test_app import APP, client, login, ok

PW = "settings123"


def new_student(tag, exam="ORT"):
    """Each test gets its own account, so nothing leaks into the seed student other tests rely on."""
    c = client()
    email = f"{tag}@settings.test"
    r = c.post("/register", data={"name": "Тест Настроек", "email": email, "password": PW, "password2": PW, "role": "student",
                                  "exam": exam, "consent": "1", "agree": "1"})
    assert r.status_code == 302, r.data[:400]
    with APP.app_context():
        u = User.query.filter_by(email=email).first()
        u.profile.exam, u.profile.onboarded = exam, True
        db.session.commit()
    return c, email


def user(email):
    return User.query.filter_by(email=email).first()


def post(c, **data):
    return c.post("/profile", data=data)


def test_email_needs_the_password_and_a_free_address():
    c, email = new_student("mail")
    post(c, action="email", email="next@settings.test", password="wrong")
    post(c, action="email", email="student@monday.kg", password=PW)
    post(c, action="email", email="not-an-email", password=PW)
    with APP.app_context():
        assert user(email) is not None
    post(c, action="email", email="  Next@Settings.TEST ", password=PW)
    with APP.app_context():
        assert user(email) is None and user("next@settings.test") is not None
    login(client(), "next@settings.test", PW)


def test_teacher_resets_only_a_linked_student():
    c, email = new_student("reset")
    t = login(client(), "aibek@monday.kg", "teacher123")
    with APP.app_context():
        teacher = user("aibek@monday.kg")
        rec = StudentRecord(teacher_id=teacher.id, name="Тест", student_user_id=user(email).id, invite_code="MND-TST1")
        empty = StudentRecord(teacher_id=teacher.id, name="Пусто", invite_code="MND-TST2")
        foreign = StudentRecord(teacher_id=user("admin@monday.kg").id, name="Чужой", student_user_id=user(email).id, invite_code="MND-TST3")
        db.session.add_all([rec, empty, foreign])
        db.session.commit()
        rec_id, empty_id, foreign_id = rec.id, empty.id, foreign.id
    assert t.post(f"/teacher/students/{empty_id}/reset-password").status_code == 404
    assert t.post(f"/teacher/students/{foreign_id}/reset-password").status_code == 404
    body = t.post(f"/teacher/students/{rec_id}/reset-password", follow_redirects=True).data.decode()
    raw = re.search(r"Временный пароль для [^:]+: (\w+)\.", body).group(1)
    assert client().post("/login", data={"email": email, "password": PW}).status_code == 401  # the old one is gone
    login(client(), email, raw)
    with APP.app_context():
        for r in StudentRecord.query.filter(StudentRecord.id.in_([rec_id, empty_id, foreign_id])):
            db.session.delete(r)
        db.session.commit()


def test_admin_resets_others_but_not_an_admin():
    _c, email = new_student("adminreset")
    a = login(client(), "admin@monday.kg", "monday2026")
    with APP.app_context():
        target, boss = user(email).id, user("admin@monday.kg").id
    body = a.post(f"/admin/users/{target}/reset-password", follow_redirects=True).data.decode()
    assert "Временный пароль" in body
    a.post(f"/admin/users/{boss}/reset-password", follow_redirects=True)
    login(client(), "admin@monday.kg", "monday2026")
    assert login(client(), "student@monday.kg", "student123").post(f"/admin/users/{target}/reset-password").status_code in (302, 403)


def test_hidden_student_leaves_the_ranking_but_keeps_their_own_place():
    c, email = new_student("hide")
    with APP.app_context():
        work = Work.query.filter_by(kind="monday", status="published").first()
        u = user(email)
        att = Attempt(user=u, work_version=work.current_version, mode="monday", total=1, score=1, finished_at=date(2026, 1, 5))
        db.session.add(att)
        db.session.commit()
        uid, att_id = u.id, att.id
        assert uid in [a.user_id for a in monday_ranking(work, limit=None)]
    post(c, action="privacy", hide_rank="1")
    with APP.app_context():
        work = Work.query.filter_by(kind="monday", status="published").first()
        assert uid not in [a.user_id for a in monday_ranking(work, limit=None)]
        assert uid in [a.user_id for a in monday_ranking(work, limit=None, viewer_id=uid)]
        db.session.delete(db.session.get(Attempt, att_id))
        db.session.commit()


def test_practice_defaults_reach_the_session_form_and_the_bank():
    c, _email = new_student("prefs")
    post(c, action="practice", session_explain="end", bank_view="one")
    body = ok(c, "/sessions").data.decode()
    assert re.search(r'name="explain" value="end" checked', body) and not re.search(r'name="explain" value="now" checked', body)
    r = c.post("/bank/start", data={"exam": "ORT"})
    assert r.status_code == 302 and "/sheet" not in r.location
    post(c, action="practice")
    assert "/sheet" in c.post("/bank/start", data={"exam": "ORT"}).location


def test_second_subject_swaps_and_each_keeps_its_goal_and_date():
    c, email = new_student("second")
    post(c, action="field", field="goal_score", value="200", tab="exam")
    post(c, action="field", field="exam_date", value="2027-05-20", tab="exam")
    post(c, action="field", field="second_exam", value="ORT", tab="exam")     # same as the main exam: refused
    with APP.app_context():
        assert user(email).pref("second_exam") is None
    post(c, action="field", field="second_exam", value="SAT", tab="exam")
    assert "topbar__switch" in ok(c, "/home").data.decode()
    c.post("/exam/switch")
    with APP.app_context():
        u = user(email)
        assert (u.profile.exam, u.profile.goal_score, u.profile.exam_date) == ("SAT", None, None)
    ok(c, "/home")
    post(c, action="field", field="goal_score", value="700", tab="exam")
    c.post("/exam/switch")
    with APP.app_context():
        u = user(email)
        assert (u.profile.exam, u.profile.goal_score, u.profile.exam_date) == ("ORT", 200, date(2027, 5, 20))
        assert u.pref("second_exam") == "SAT" and u.pref("exam_plans")["SAT"]["goal"] == 700


def test_a_course_as_second_subject_opens_without_swapping():
    c, email = new_student("course")
    post(c, action="field", field="second_exam", value="CALC1", tab="exam")
    assert "/bank/?exam=CALC1" in ok(c, "/home").data.decode()
    c.post("/exam/switch")
    with APP.app_context():
        assert user(email).profile.exam == "ORT"


def test_region_and_school_moved_to_the_profile_tab():
    c, _email = new_student("rows")
    body = ok(c, "/profile").data.decode()
    assert body.index('data-set-pane="profile"') < body.index("Город или область") < body.index('data-set-pane="exam"')


def test_session_results_use_the_shared_review():
    c, email = new_student("review")
    with APP.app_context():
        q = Question.query.filter_by(status="published", answer_type="choice").first()
        u = user(email)
        att = Attempt(user=u, mode="weak", plan=[q.id], position=1, total=1, score=1)
        db.session.add(att)
        db.session.flush()
        db.session.add(AttemptAnswer(attempt=att, index=0, question=q, skill_id=q.skill_id, given=str(q.snapshot()["correct"]), is_correct=True, hint_used=True))
        db.session.commit()
        att_id = att.id
    body = ok(c, f"/sessions/{att_id}/done").data.decode()
    assert 'class="rv-explain"' in body and 'class="rv-question"' in body and "sd-row" not in body
    assert body.index('class="rv-explain"') < body.index('class="rv-question"')
    assert "С подсказкой" in body and "sd-level--" in body and "sd-act is-main" not in body

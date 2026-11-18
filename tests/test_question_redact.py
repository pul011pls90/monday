"""Test Student-view Question Redactor modal and admin-moderated correction approval."""
import os
import tempfile

from config import Config


def test_teacher_redacts_question_and_admin_approves():
    tmp = tempfile.mkdtemp()

    class RedactTestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "redact_test.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")
        SERVER_NAME = "localhost"

    from monday import create_app
    from monday.models import ContentNode, Question, User, db

    app = create_app(RedactTestConfig)
    with app.app_context():
        admin = User(email="adm@monday.kg", name="Admin", role="admin", is_approved=True)
        admin.set_password("pw")
        teacher = User(email="tch@monday.kg", name="Teacher", role="teacher", is_approved=True)
        teacher.set_password("pw")
        db.session.add_all([admin, teacher])
        db.session.flush()
        skill = ContentNode.query.filter_by(level="node").first()

        orig = Question(
            author_id=admin.id,
            skill_id=skill.id,
            exams=["ORT"],
            difficulty=2,
            answer_type="choice",
            options=["$1$", "$2$", "$3$", "$4$"],
            correct="1",
            text="Решите: $x + 1 = 3$",
            explanation="Ответ: $2$.",
            status="published",
        )
        db.session.add(orig)
        db.session.commit()
        qid = orig.id
        tid = teacher.id
        aid = admin.id

    t = app.test_client()
    with t.session_transaction() as sess:
        sess["_user_id"] = str(tid)

    # 1. Teacher opens the student-view redactor modal
    r_get = t.get(f"/teacher/questions/{qid}/redact?modal=1")
    assert r_get.status_code == 200
    html = r_get.data.decode("utf-8")
    assert "Вид ученика" in html and "Отправить админу" in html

    # 2. Teacher submits correction -> goes to pending moderation, original untouched
    r_post = t.post(
        f"/teacher/questions/{qid}/redact",
        headers={"X-Requested-With": "fetch"},
        data={
            "text": "Решите уравнение: $x + 1 = 4$",
            "opt_0": "$1$",
            "opt_1": "$2$",
            "opt_2": "$3$",
            "opt_3": "$4$",
            "correct": "2",
            "explanation": "$x = 4 - 1 = 3$.",
            "difficulty": "2",
            "review_note": "Исправил условие",
        },
    )
    assert r_post.status_code == 200
    data = r_post.get_json()
    assert data["ok"] is True
    pending_id = data["pending_id"]

    with app.app_context():
        live_q = db.session.get(Question, qid)
        pend_q = db.session.get(Question, pending_id)
        assert live_q.text == "Решите: $x + 1 = 3$"  # students still see original!
        assert pend_q.status == "pending"
        assert pend_q.replaces_id == qid

    # 3. Admin sees it in /review/questions and approves
    adm = app.test_client()
    with adm.session_transaction() as sess:
        sess["_user_id"] = str(aid)
    r_queue = adm.get("/review/questions")
    assert r_queue.status_code == 200
    assert "Решите уравнение: $x + 1 = 4$" in r_queue.data.decode("utf-8")

    r_dec = adm.post(f"/review/questions/{pending_id}", data={"decision": "approve"})
    assert r_dec.status_code in (200, 302)

    with app.app_context():
        live_q = db.session.get(Question, qid)
        assert live_q.text == "Решите уравнение: $x + 1 = 4$"
        assert live_q.correct == "2"


def test_simple_math_notation_and_symbol_keyboard():
    from monday.math_plain import latex_to_plain, plain_to_latex

    assert latex_to_plain(r"Вычислите: $\frac{1}{2} + \frac{1}{3}$") == "Вычислите: 1/2 + 1/3"
    assert latex_to_plain(r"$\frac{5}{3}$") == "5/3"
    assert latex_to_plain(r"$\sqrt{3} \le \pi$") == "√3 ≤ π"

    assert plain_to_latex("5/3", is_option=True) == r"$\frac{5}{3}$"
    assert plain_to_latex("√3", is_option=True) == r"$\sqrt{3}$"
    assert plain_to_latex("Вычислите: 1/2 + 1/3", is_option=False) == r"Вычислите: $\frac{1}{2} + \frac{1}{3}$"

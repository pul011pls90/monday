"""End-to-end checks for every page and the main flows.

Run:  python3 -m pytest -q        (or)        python3 tests/test_app.py
Uses a temporary SQLite database with the demo data.
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config  # noqa: E402


def make_app():
    tmp = tempfile.mkdtemp()
    # TEST_DATABASE_URL=postgresql+psycopg://… runs the whole suite on PostgreSQL (the database is wiped first)
    pg = os.environ.get("TEST_DATABASE_URL")
    if pg:
        import sqlalchemy
        eng = sqlalchemy.create_engine(pg)
        with eng.begin() as conn:
            conn.execute(sqlalchemy.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        eng.dispose()

    class TestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SQLALCHEMY_DATABASE_URI = pg or "sqlite:///" + os.path.join(tmp, "test.db")
        SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True} if pg else {}
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")
        SERVER_NAME = "localhost"
        DATA_FIXES = False  # the flows below use the demo collections; test_data_fixes runs the fixes itself

    from monday import create_app
    return create_app(TestConfig)


APP = make_app()


def client():
    return APP.test_client()


def login(c, email, password):
    r = c.post("/login", data={"email": email, "password": password})
    assert r.status_code == 302, r.data[:300]
    return c


def ok(c, url, status=200, contains=None):
    r = c.get(url)
    assert r.status_code == status, f"{url} -> {r.status_code}\n{r.data.decode()[:1500]}"
    if contains:
        body = r.data.decode()
        for needle in ([contains] if isinstance(contains, str) else contains):
            assert needle in body, f"{url}: '{needle}' not found"
    return r


def ids(pattern, html):
    return [int(x) for x in re.findall(pattern, html)]


# --------------------------------------------------------------------------- data


def test_demo_questions_are_well_formed():
    from monday.models import Question
    with APP.app_context():
        for q in Question.query.all():
            if q.answer_type == "choice":
                assert len(q.options) == len(set(q.options)) >= 2, (q.id, q.options)
                assert q.correct.isdigit() and int(q.correct) < len(q.options), (q.id, q.correct)
            elif q.answer_type == "written":
                assert q.correct and q.rubric and q.rubric[0]["points"] == q.weight, (q.id, q.weight)
            else:
                from monday.services import valid_number_answer
                assert valid_number_answer(q.correct), (q.id, q.correct)


def test_sat_pack_is_imported_with_two_35_minute_modules():
    from monday.models import Question, Work
    with APP.app_context():
        works = Work.query.filter(Work.title.like("SAT Math · Princeton Review 2025%")).all()
        assert len(works) == 6  # Practice Tests 1–2 (Module 2 easier/harder) + Chapter Tests 1–2
        for w in works:
            v = w.current_version
            assert w.status == "published" and w.exam == "SAT" and v.question_count == 44
            assert v.layout["format"] == "sat"
            assert v.layout["modules"] == [{"start": 0, "end": 22, "minutes": 35}, {"start": 22, "end": 44, "minutes": 35}]
            assert all(item["skill_id"] for item in v.items)
        pack_q = Question.query.filter(Question.image_path.like("packs/%")).all()
        assert pack_q and all(os.path.exists(os.path.join(APP.config["UPLOAD_FOLDER"], q.image_path)) for q in pack_q)


def test_sat_entry_rules_and_sheet_in_sat_collections():
    from monday.models import Attempt, Work
    from monday.services import is_correct
    item = {"answer_type": "number", "correct": "2/3"}
    for g in ("2/3", "4/6", ".6666", ".6667", "0.666", "0.667"):
        assert is_correct(item, g, sat=True), g
    for g in ("0.66", ".67", "0.6667", "0,666", "2 / 3"):
        assert not is_correct(item, g, sat=True), g
    assert is_correct({"answer_type": "number", "correct": "7/2"}, "3.50", sat=True)
    assert not is_correct({"answer_type": "number", "correct": "7/2"}, "3 1/2", sat=True)
    assert is_correct({"answer_type": "number", "correct": "1/2"}, "0,5")          # other tests stay lenient
    s = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        w = Work.query.filter(Work.title.like("SAT Math · Princeton Review 2025 · Practice Test 1 (Module 2 Easier)")).first()
        wid, items = w.id, w.current_version.items
    r = s.post(f"/works/{wid}/start")
    run = r.headers["Location"]
    ok(s, run, contains=["Правильная запись ответа", ".6667", "data-sat-entry"])
    # Module 1, question 5: 200 — "200.0" is 5 characters and equal, so it counts
    idx = next(i for i, it in enumerate(items[:22]) if it["answer_type"] == "number")
    r = s.post(run.rstrip("/") + "/next-module", data={f"q{idx}": items[idx]["correct"].split("|")[0]})
    r = s.post(run, data={})
    with APP.app_context():
        from monday.extensions import db
        att = db.session.get(Attempt, int(run.rstrip("/").split("/")[-1]))
        assert att.finished_at and att.score >= 1


def test_several_accepted_numeric_answers():
    from monday.services import display_answer, is_correct
    item = {"answer_type": "number", "correct": "-5/9|-0.5555|-0.5556|-0.555|-0.556"}
    for given in ("-5/9", "-0.5556", "-.555", "-10/18"):
        assert is_correct(item, given), given
    assert not is_correct(item, "-0.55")
    assert is_correct({"answer_type": "number", "correct": "7|-7"}, "-7")
    assert display_answer("-5/9|-0.5555|-0.5556", joiner=" or ") == "-5/9"
    assert display_answer("7|-7", joiner=" or ") == "7 or -7"


# --------------------------------------------------------------------------- auth


def test_login_page_and_redirects():
    c = client()
    ok(c, "/login", contains="С возвращением")
    ok(c, "/register", contains="Создай аккаунт")
    assert c.get("/home").status_code == 302
    assert c.get("/teacher/").status_code == 302
    r = c.post("/login", data={"email": "student@monday.kg", "password": "wrong"})
    assert r.status_code == 401


def test_register_student_with_invite_code_and_onboarding():
    from monday.models import StudentRecord
    with APP.app_context():
        code = StudentRecord.query.filter(StudentRecord.student_user_id.is_(None)).first().invite_code
    c = client()
    r = c.get(f"/join/{code}")
    assert r.status_code == 302
    r = c.post("/register", data={"name": "Новый Ученик", "email": "new.student@mail.com", "password": "password1",
                                  "role": "student", "invite_code": ""})
    assert r.status_code == 302 and "/onboarding" in r.headers["Location"]
    with APP.app_context():
        rec = StudentRecord.query.filter_by(invite_code=code).first()
        assert rec.student is not None and rec.student.email == "new.student@mail.com"
    ok(c, "/onboarding", contains="Какой экзамен сдаёшь?")
    r = c.post("/onboarding", data={"exam": "ENT", "exam_date": "2027-06-01", "goal_score": "120", "language": "ru"})
    assert r.status_code == 302
    ok(c, "/home", contains="понедельник")


def test_register_teacher_needs_approval():
    c = client()
    r = c.post("/register", data={"name": "Учитель Тест", "email": "t.test@mail.com", "password": "password1",
                                  "role": "teacher"})
    assert "/pending" in r.headers["Location"]
    ok(c, "/pending", contains="Заявка учителя")
    assert c.get("/teacher/").status_code == 302


# --------------------------------------------------------------------------- student pages


def test_student_pages_render():
    c = login(client(), "student@monday.kg", "student123")
    ok(c, "/home", contains=["Привет, Тима", "data-countdown", "Сегодня", "Целевой балл", "Ты в точках", "мин сегодня", "К сессиям"])
    ok(c, "/home?t=30")
    ok(c, "/skills?show=list", contains=["Карта навыков", "Свойства логарифмов"])
    body = ok(c, "/skills").data.decode()  # the list choice is remembered
    assert "sp-level" in body and "metro-data" not in body
    body = ok(c, "/skills?show=map", contains=["data-metro", "metro-data", "mt-start", "Продолжить"]).data.decode()
    assert "sp-level" not in body
    ok(c, "/skills?scope=all&q=лог")
    ok(c, "/sessions", contains="Недавние сессии")
    ok(c, "/collections", contains=["Сборники", "Рекомендуем тебе", "ОРТ Май 2026"])
    ok(c, "/collections?exam=SAT&cat=full&sort=short", contains="SAT April 2024")
    ok(c, "/collections?q=Геометрия", contains="Геометрия: площади")
    ok(c, "/homework", contains=["Нужно сделать", "Свойства логарифмов", "hwcal__day", "Проверено"])
    ok(c, "/journal", contains=["Журнал ошибок", "Где теряешь баллы", "Записи", "Начать работу над ошибками"])
    ok(c, "/journal?show=resolved")
    body = ok(c, "/monday", contains="Тест").data.decode()
    assert "Рейтинг прошлой недели" not in body and "Дуэль школ" not in body and "Твой прошлый тест" not in body   # off by default
    APP.config["MONDAY_RANKINGS"] = True
    ok(c, "/monday", contains=["Тест", "Рейтинг прошлой недели", "Дуэль школ"])
    ok(c, "/monday?scope=region")
    ok(c, "/monday?scope=school")
    APP.config["MONDAY_RANKINGS"] = False
    ok(c, "/profile", contains=["Мои учителя", "Айбек Токтогулов"])
    # students cannot open teacher pages
    assert c.get("/teacher/").status_code == 403
    assert c.get("/admin/").status_code == 403


def test_practice_session_flow():
    c = login(client(), "student@monday.kg", "student123")
    r = c.post("/sessions/start/franklin")
    assert r.status_code == 302
    url = r.headers["Location"]
    for _ in range(10):
        page = c.get(url)
        if page.status_code == 302:
            break
        html = page.data.decode()
        assert page.status_code == 200
        if 'value="answer"' in html:
            if 'name="given" value="0"' in html:
                c.post(url, data={"action": "answer", "given": "0"})
            else:
                c.post(url, data={"action": "answer", "given": "1"})
            html = c.get(url).data.decode()
            assert "Объяснение" in html
            if "Почему ошибка" in html:
                c.post(url, data={"action": "reason", "reason": "careless"})
        r = c.post(url, data={"action": "next"})
        if "/done" in r.headers.get("Location", ""):
            ok(c, r.headers["Location"], contains="сессия завершена")
            break
    else:
        raise AssertionError("session never finished")
    # other modes start
    for mode in ("feynman", "darwin", "einstein"):
        r = c.post(f"/sessions/start/{mode}")
        assert r.status_code == 302 and "/sessions/" in r.headers["Location"]
        ok(c, r.headers["Location"])
    r = c.post("/sessions/start/tesla")
    assert r.headers["Location"].endswith("/sessions")


def test_collection_test_flow():
    from monday.models import Work
    c = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        w = Work.query.filter_by(title="Геометрия: площади").first()
        wid, n = w.id, w.current_version.question_count
        first = w.current_version.items[0]
    ok(c, f"/works/{wid}", contains="Начать тест")
    r = c.post(f"/works/{wid}/start")
    run = r.headers["Location"]
    ok(c, run, contains=["Сдать работу", "data-timer"])
    data = {"q0": first["correct"]}
    r = c.post(run, data=data)
    assert "/result" in r.headers["Location"]
    ok(c, r.headers["Location"], contains=["Разбор", f"1 / {n}"])


def db_get(model, pk):
    from monday.extensions import db
    return db.session.get(model, pk)


def test_empty_homework_goes_in_only_when_time_runs_out():
    from monday.models import Assignment, Attempt, Work
    s = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        from monday.extensions import db
        from monday.models import StudentRecord, User
        student = User.query.filter_by(email="student@monday.kg").first()
        rec = StudentRecord.query.filter_by(student_user_id=student.id).first()
        work = Work.query.filter_by(kind="homework", status="published").first()
        a = Assignment(work=work, teacher_id=rec.teacher_id, record=rec)
        db.session.add(a)
        db.session.commit()
        aid, teacher_email = a.id, rec.teacher.email
    r = s.post(f"/homework/{aid}/start")
    run = r.headers["Location"]
    r = s.post(run, data={"timeout": "1"})
    assert "/result" in r.headers["Location"]
    with APP.app_context():
        att = db_get(Attempt, int(run.rstrip("/").split("/")[-1]))
        assert att.finished_at is not None and att.score == 0
    t = login(client(), teacher_email, "teacher123")
    ok(t, f"/teacher/review/{aid}", contains="ни на один вопрос")


def test_homework_flow_student_then_teacher():
    from monday.models import Assignment, Work
    s = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        a = Assignment.query.join(Work).filter(Work.title == "ДЗ: свойства логарифмов",
                                               Assignment.checked_at.is_(None)).first()
        aid = a.id
        items = a.work.current_version.items
    ok(s, f"/homework/{aid}", contains="Начать")
    r = s.post(f"/homework/{aid}/start")
    run = r.headers["Location"]
    # handing in with no answers is refused (the test stays open) ...
    r = s.post(run, data={})
    assert r.headers["Location"].endswith(run)
    ok(s, run, contains="Ответьте хотя бы на один вопрос")
    # ... unless the timer ran out
    with APP.app_context():
        from monday.models import Attempt
        assert db_get(Attempt, int(run.rstrip("/").split("/")[-1])).finished_at is None
    form = {f"q{i}": it["correct"] for i, it in enumerate(items)}
    r = s.post(run, data=form)
    ok(s, r.headers["Location"], contains="К заданию")
    ok(s, f"/homework/{aid}", contains="Учитель ещё не проверил")

    t = login(client(), "aibek@monday.kg", "teacher123")
    ok(t, "/teacher/review", contains="ДЗ: свойства логарифмов")
    ok(t, f"/teacher/review/{aid}", contains="Отметить как проверенное")
    r = t.post(f"/teacher/review/{aid}", data={"action": "check", "teacher_comment": "Отлично, всё верно!"})
    assert r.status_code == 302
    ok(s, f"/homework/{aid}", contains="Отлично, всё верно!")


def test_journal_update_and_monday_test():
    from monday.models import Attempt, AttemptAnswer, User
    c = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        u = User.query.filter_by(email="student@monday.kg").first()
        ans = (AttemptAnswer.query.join(Attempt).filter(Attempt.user_id == u.id, AttemptAnswer.is_correct.is_(False),
                                                        AttemptAnswer.resolved.is_(False)).first())
        aid = ans.id
    c.post(f"/journal/{aid}", data={"reason": "gap"})
    c.post(f"/journal/{aid}", data={"resolve": "1"})
    with APP.app_context():
        from monday.extensions import db
        a = db.session.get(AttemptAnswer, aid)
        assert a.mistake_reason == "gap" and a.resolved
    r = c.post("/monday/start")
    assert r.status_code == 302 and "/attempts/" in r.headers["Location"]
    r = c.post(r.headers["Location"], data={})
    ok(c, r.headers["Location"], contains="К тесту понедельника")
    ok(c, "/monday", contains="Мой результат")


def test_profile_updates_and_invalid_code():
    c = login(client(), "student@monday.kg", "student123")
    r = c.post("/profile", data={"action": "join", "invite_code": "MND-ZZZZ"}, follow_redirects=True)
    assert "Код не найден" in r.data.decode()
    r = c.post("/profile", data={"action": "profile", "name": "Тима Манашов", "exam": "ORT", "exam_date": "",
                                 "goal_score": "200", "grade": "11", "region": "Чуйская область",
                                 "school": "Гимназия №1, Токмок", "language": "ky"}, follow_redirects=True)
    assert r.status_code == 200 and "Профиль сакталды" in r.data.decode()   # Kyrgyz from now on
    c.post("/profile", data={"action": "profile", "name": "Тима Манашов", "exam": "ORT", "exam_date": "",
                             "goal_score": "200", "grade": "11", "region": "Чуйская область",
                             "school": "Гимназия №1, Токмок", "language": "ru"})
    r = c.post("/prefs/theme", data={"theme": "dark"}, headers={"X-Requested-With": "fetch"})
    assert r.json["theme"] == "dark"
    assert 'data-theme="dark"' in c.get("/home").data.decode()


def test_profile_settings_export_and_delete():
    from monday.extensions import db
    from monday.models import StudentProfile, User
    c = login(client(), "student@monday.kg", "student123")
    html = c.get("/profile").data.decode()
    for part in ("Оформление", "Учёба", "Безопасность", "Калькулятор сразу", "Удалить аккаунт", "data-set-tab"):
        assert part in html
    # one row saved on its own
    r = c.post("/profile", data={"action": "field", "field": "school", "value": "Лицей 61", "tab": "exam"})
    assert r.headers["Location"].endswith("/profile#exam")
    assert "Лицей 61" in c.get("/profile").data.decode()
    c.post("/profile", data={"action": "field", "field": "school", "value": "Гимназия №1, Токмок", "tab": "exam"})
    r = c.post("/profile", data={"action": "field", "field": "name", "value": "x"}, follow_redirects=True)
    assert "Не получилось сохранить" in r.data.decode()
    c.post("/profile", data={"action": "appearance", "theme": "system", "text": "large", "motion": "reduce"})
    html = c.get("/home").data.decode()
    assert "data-theme-auto" in html and 'data-text="large"' in html and 'data-motion="reduce"' in html
    c.post("/profile", data={"action": "appearance", "theme": "light", "text": "normal"})
    c.post("/profile", data={"action": "study", "daily_goal": "30", "study_days": ["0", "2", "4"]})
    c.post("/profile", data={"action": "practice", "calc_open": "1"})
    with APP.app_context():
        u = User.query.filter_by(email="student@monday.kg").first()
        assert u.pref("study_days") == [0, 2, 4] and u.pref("bank_timer") is False and u.pref("calc_open") is True
        assert u.profile.daily_goal == 30
        u.set_prefs(bank_timer=True, calc_open=False, study_days=list(range(7)))
        u.profile.daily_goal = 15
        db.session.commit()
    r = c.get("/profile/export.csv")
    assert r.status_code == 200 and "text/csv" in r.headers["Content-Type"] and "Баллы" in r.data.decode("utf-8-sig")
    # deleting an account wipes who the student was and blocks sign-in
    with APP.app_context():
        v = User(email="leaving@monday.kg", name="Уходящий Ученик", role="student")
        v.set_password("leaving123")
        v.profile = StudentProfile(exam="ORT", onboarded=True, school="Школа 5")
        db.session.add(v)
        db.session.commit()
        vid = v.id
    d = login(client(), "leaving@monday.kg", "leaving123")
    r = d.post("/profile", data={"action": "delete", "password": "wrong"}, follow_redirects=True)
    assert "аккаунт не удалён" in r.data.decode()
    d.post("/profile", data={"action": "delete", "password": "leaving123"})
    with APP.app_context():
        v = db.session.get(User, vid)
        assert v.is_blocked and "leaving" not in v.email and v.name != "Уходящий Ученик" and v.profile.school is None
    r = client().post("/login", data={"email": "leaving@monday.kg", "password": "leaving123"})
    assert r.status_code != 302


def test_info_pages_for_everyone():
    for url, text in (("/about", "instagram.com/monday_edc"), ("/terms", "Условия использования"), ("/privacy", "Cookies")):
        ok(client(), url, contains=text)
    ok(login(client(), "student@monday.kg", "student123"), "/about", contains=["rail", "Записаться на пробный урок"])


# --------------------------------------------------------------------------- teacher pages


def test_teacher_pages_render():
    t = login(client(), "aibek@monday.kg", "teacher123")
    ok(t, "/teacher/", contains=["Уроки сегодня", "Ждут проверки"])
    ok(t, "/teacher/students", contains=["Ученики", "Тима Манашов", "MND-"])
    ok(t, "/teacher/students?sort=progress")
    ok(t, "/teacher/works", contains=["ОРТ Май 2026", "v2"])
    ok(t, "/teacher/works?status=draft", contains="Функции и графики")
    ok(t, "/teacher/works?status=archived", contains="ОРТ Пробник 2024")
    ok(t, "/teacher/works/new?kind=homework", contains="Банк вопросов")
    ok(t, "/teacher/assign", contains="Выдать задание")
    ok(t, "/teacher/review?show=open")
    ok(t, "/teacher/review?show=checked")
    ok(t, "/teacher/questions", contains="Банк вопросов")
    ok(t, "/teacher/questions?mine=0&exam=ORT")
    ok(t, "/teacher/questions/new", contains="Так увидит ученик")
    ok(t, "/teacher/account", contains="Настройки")


def test_teacher_students_crud():
    from monday.models import StudentRecord
    t = login(client(), "aibek@monday.kg", "teacher123")
    r = t.post("/teacher/students/new", data={"name": "Айдай Тестова", "grade": "11", "lesson_time": "17:00",
                                              "lesson_days": ["1", "3"], "exam": "ORT", "goal_score": "200",
                                              "manual_progress": "15"})
    assert r.status_code == 302
    rid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    ok(t, f"/teacher/students/{rid}", contains=["Айдай Тестова", "Подключите аккаунт", "/join/MND-"])
    r = t.post("/teacher/students/new", data={"name": "X", "lesson_time": "25:99"}, follow_redirects=True)
    assert "Укажите имя" in r.data.decode() or "ЧЧ:ММ" in r.data.decode()
    t.post(f"/teacher/students/{rid}/edit", data={"name": "Айдай Тестова", "lesson_time": "18:30", "grade": "10"})
    with APP.app_context():
        from monday.extensions import db
        rec = db.session.get(StudentRecord, rid)
        old = rec.invite_code
        assert rec.lesson_time == "18:30"
    t.post(f"/teacher/students/{rid}/code")
    with APP.app_context():
        from monday.extensions import db
        assert db.session.get(StudentRecord, rid).invite_code != old
    t.post(f"/teacher/students/{rid}/delete")
    with APP.app_context():
        from monday.extensions import db
        assert db.session.get(StudentRecord, rid) is None
    # another teacher cannot see Aibek's students
    other = login(client(), "nurai@monday.kg", "teacher123")
    with APP.app_context():
        rid2 = StudentRecord.query.first().id
    assert other.get(f"/teacher/students/{rid2}").status_code == 404


def test_teacher_question_and_work_versioning():
    from monday.models import Question, Work
    t = login(client(), "aibek@monday.kg", "teacher123")
    with APP.app_context():
        from monday.models import Skill
        sid = Skill.query.filter_by(code="log_props").first().id
    r = t.post("/teacher/questions/new", data={
        "exams": ["ORT", "ENT"], "skill_id": str(sid), "difficulty": "2", "language": "ru",
        "text": "Вычислите $\\log_3 27$", "answer_type": "choice",
        "option0": "3", "option1": "9", "option2": "27", "option3": "", "correct_option": "0",
        "explanation": "$3^3 = 27$", "video_url": "", "action": "submit"})
    assert r.status_code == 302
    with APP.app_context():
        q = Question.query.filter_by(text="Вычислите $\\log_3 27$").first()
        assert q.status == "published" and q.options == ["3", "9", "27"]
        qid = q.id
    # validation
    r = t.post("/teacher/questions/new", data={"exams": [], "skill_id": "", "text": "", "answer_type": "number",
                                               "correct_number": "abc"})
    assert r.status_code == 400
    ok(t, f"/teacher/questions/{qid}/edit", contains="Вычислите")

    # create a homework, publish v1, change, publish v2
    with APP.app_context():
        bank = [q.id for q in Question.query.filter_by(status="published").limit(3).all()]
    r = t.post("/teacher/works/new?kind=homework", data={
        "kind": "homework", "title": "ДЗ тест", "description": "", "exam": "ORT", "category": "thematic",
        "time_limit_min": "15", "question_order": ",".join(map(str, bank[:2])), "action": "publish"})
    assert r.status_code == 302
    with APP.app_context():
        w = Work.query.filter_by(title="ДЗ тест").first()
        wid = w.id
        assert w.status == "published" and w.current_version.number == 1 and w.current_version.question_count == 2
    ok(t, f"/teacher/works/{wid}/edit", contains="Опубликовать новую версию")
    t.post(f"/teacher/works/{wid}/edit", data={"title": "ДЗ тест", "exam": "ORT", "category": "thematic",
                                               "time_limit_min": "15", "question_order": ",".join(map(str, bank)),
                                               "version_note": "добавлена задача", "action": "publish"})
    with APP.app_context():
        from monday.extensions import db
        w = db.session.get(Work, wid)
        assert w.current_version.number == 2 and w.versions[0].question_count == 2 and w.current_version.question_count == 3
    # assign it
    with APP.app_context():
        from monday.models import StudentRecord
        rec = StudentRecord.query.filter(StudentRecord.student_user_id.isnot(None)).first()
    r = t.post("/teacher/assign", data={"work_id": str(wid), "record_ids": [str(rec.id)], "due_date": "2030-01-01",
                                        "due_time": "20:00", "message": "Удачи"})
    assert r.status_code == 302
    # archive / duplicate
    t.post(f"/teacher/works/{wid}/status", data={"status": "archived"})
    r = t.post(f"/teacher/works/{wid}/duplicate")
    assert "/edit" in r.headers["Location"]
    # cannot delete a published (archived) work
    r = t.post(f"/teacher/works/{wid}/delete", follow_redirects=True)
    assert "нельзя удалить" in r.data.decode()


def test_admin_pages_and_moderation():
    from monday.models import Question, User
    a = login(client(), "admin@monday.kg", "monday2026")
    ok(a, "/admin/", contains=["Регистрации по дням", "Где мало вопросов", "заявок ждут"])
    ok(a, "/admin/?tab=apps", contains=["Бакыт Осмонов", "Принять"])
    ok(a, "/admin/?tab=moderation", contains="Очередь пуста")
    ok(a, "/admin/?tab=students&exam=ORT&q=student@monday", contains="student@monday.kg")
    ok(a, "/admin/?tab=teachers", contains="aibek@monday.kg")
    with APP.app_context():
        tima = User.query.filter_by(email="student@monday.kg").first().id
    r = ok(a, f"/admin/?tab=students&user={tima}&fragment=1", contains=["Последние результаты", "Заблокировать аккаунт"])
    assert "<html" not in r.data.decode()
    # block: can't sign in, unblock: can again
    a.post(f"/admin/users/{tima}/block", data={"on": "1"})
    assert client().post("/login", data={"email": "student@monday.kg", "password": "student123"}).status_code == 403
    a.post(f"/admin/users/{tima}/block", data={"on": ""})
    login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        pending = User.query.filter_by(email="new.teacher@monday.kg").first().id
    a.post(f"/admin/users/{pending}/approve", data={"decision": "approve"})
    with APP.app_context():
        from monday.extensions import db
        assert db.session.get(User, pending).is_approved
    ok(a, "/teacher/", contains="Уроки сегодня")
    ok(a, "/teacher/works?kind=monday", contains="Тест понедельника")


def test_errors_and_language():
    c = client()
    assert c.get("/does-not-exist").status_code == 404
    r = c.post("/prefs/lang", data={"lang": "ky", "next": "/login"})
    assert r.status_code == 302
    assert 'lang="ky"' in c.get("/login").data.decode()


if __name__ == "__main__":
    import inspect
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                failures += 1
                print("FAIL", name, "\n", e)
    sys.exit(1 if failures else 0)


# --------------------------------------------------------------------------- step 1: tree, question template, layout, autosave


def test_number_answers_fractions_and_rounding():
    from monday.services import is_correct, parse_number
    assert parse_number("1 1/2")[0] == parse_number("3/2")[0] == parse_number("1,5")[0]
    item = {"answer_type": "number", "correct": "25/6", "precision": 1, "input_formats": ["decimal", "fraction"]}
    assert is_correct(item, "4,2") and is_correct(item, "25/6") and not is_correct(item, "4,3")
    item = {"answer_type": "number", "correct": "0.75", "input_formats": ["fraction"]}
    assert is_correct(item, "3/4") and not is_correct(item, "0.75")
    assert not is_correct({"answer_type": "number", "correct": "5"}, "5/0")


def test_content_tree_and_teacher_branches():
    from monday.models import ContentNode
    from monday.services import content_tree
    with APP.app_context():
        tree = content_tree(None)
        assert all(t["node"].level == "topic" for t in tree)
        assert all(s["node"].level == "subtopic" for t in tree for s in t["subtopics"])
        own = ContentNode.query.filter_by(code="abs_eq_aibek").first()
        assert own.owner_id and own.topic == "Алгебра" and own.subtopic == "Уравнения"
    # Aibek's student sees his branch, another teacher does not
    s = login(client(), "student@monday.kg", "student123")
    ok(s, "/skills?show=list", contains=["Уравнения с параметром", "Геометрия"])
    other = login(client(), "nurai@monday.kg", "teacher123")
    body = ok(other, "/teacher/tree", contains="Карта способностей").data.decode()
    assert "Уравнения с параметром" not in body
    # teacher adds a node to the shared tree as their own branch, then archives it
    t = login(client(), "aibek@monday.kg", "teacher123")
    ok(t, "/teacher/tree", contains=["Уравнения с параметром", "Новая подтема"])
    with APP.app_context():
        sub_id = ContentNode.query.filter_by(level="subtopic", name="Логарифмы, показательные уравнения").first().id
    r = t.post("/teacher/tree/add", data={"level": "node", "parent_id": str(sub_id), "name": "Логарифмические неравенства"})
    assert r.status_code == 302
    with APP.app_context():
        n = ContentNode.query.filter_by(name="Логарифмические неравенства").first()
        assert n.owner_id is not None and n.parent_id == sub_id and n.level == "node"
        nid = n.id
        shared_id = ContentNode.query.filter_by(code="log_def").first().id
    assert t.post(f"/teacher/tree/{shared_id}/edit", data={"name": "x"}).status_code == 403
    t.post(f"/teacher/tree/{nid}/edit", data={"action": "archive"})
    with APP.app_context():
        from monday.extensions import db
        assert db.session.get(ContentNode, nid).archived
    assert t.post("/teacher/tree/add", data={"level": "node", "parent_id": str(nid), "name": "Bad"}).status_code == 302


def test_question_template_material_new_branch_and_free_input():
    from monday.models import ContentNode, Question
    t = login(client(), "aibek@monday.kg", "teacher123")
    ok(t, "/teacher/questions/new", contains=["Место в карте", "Текст для чтения", "Свободный ввод", "tree-data"])
    with APP.app_context():
        topic_id = ContentNode.query.filter_by(level="topic", name="Геометрия").first().id
    r = t.post("/teacher/questions/new", data={
        "exams": ["ORT"], "topic_id": str(topic_id), "new_subtopic": "Векторы", "new_node": "Длина вектора",
        "difficulty": "2", "weight": "3", "language": "ru",
        "m1_type": "passage", "m1_title": "Условие", "m1_text": "Даны точки A(1; 2) и B(4; 6).",
        "m2_type": "columns", "m2_left_title": "А", "m2_left": "$|AB|$", "m2_right_title": "Б", "m2_right": "$5$",
        "text": "Найдите длину отрезка AB.", "answer_type": "number", "correct_number": "5",
        "input_formats": ["whole", "decimal"], "precision": "", "action": "submit"})
    assert r.status_code == 302, r.data.decode()[:800]
    with APP.app_context():
        q = Question.query.filter_by(text="Найдите длину отрезка AB.").first()
        assert q.weight == 3 and [b["type"] for b in q.material] == ["passage", "columns"]
        assert q.skill.name == "Длина вектора" and q.skill.subtopic == "Векторы" and q.skill.topic == "Геометрия"
        assert q.input_formats == ["whole", "decimal"] and q.skill.owner_id is not None
        qid = q.id
    ok(t, f"/teacher/questions/{qid}/edit", contains=["Даны точки A(1; 2)", "Длина вектора"])
    # word limit and missing tree place are rejected
    long_text = " ".join(["слово"] * 151)
    r = t.post("/teacher/questions/new", data={"exams": ["ORT"], "skill_id": "", "text": long_text,
                                               "answer_type": "number", "correct_number": "1"})
    assert r.status_code == 400 and "150" in r.data.decode()


def test_test_formats_ort_pages_and_sat_grid():
    from monday.models import Work
    c = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        ort = Work.query.filter_by(title="ОРТ Май 2026").first().id
        sat = Work.query.filter_by(title="SAT April 2024").first()
        sat_id, sat_n = sat.id, sat.current_version.question_count
        assert sat.current_version.layout["format"] == "sat" and sat.current_version.layout["calculator"]
        assert len(sat.current_version.layout["modules"]) == 2
    # ORT: pages + bubble answer sheet, material still rendered
    body = ok(c, c.post(f"/works/{ort}/start").headers["Location"]).data.decode()
    assert 'data-nav="pages"' in body and "Бланк ответов" in body and "Дорога в Чолпон-Ату" in body
    assert "Можно ввести:" in body and 'class="bubble"' in body
    # SAT: one question per screen, review marks, cross-out, calculator, module 1 of 2
    run = c.post(f"/works/{sat_id}/start").headers["Location"]
    aid = int(run.rstrip("/").split("/")[-1])
    body = ok(c, run, contains=["Модуль 1 из 2", "Отметить для проверки", "Калькулятор", "data-grid"]).data.decode()
    assert 'data-nav="grid"' in body and "Завершить модуль 1" in body
    assert c.post(f"/attempts/{aid}/save", data={"name": "r0", "value": "1"}).get_json()["ok"]
    c.post(f"/attempts/{aid}/save", data={"name": "q0", "value": "0"})
    # finish module 1: its answers are locked, module 2 starts
    r = c.post(f"/attempts/{aid}/next-module", data={"q1": "1"})
    assert r.status_code == 302
    body = ok(c, run, contains="Модуль 2 из 2").data.decode()
    assert c.post(f"/attempts/{aid}/save", data={"name": "q0", "value": "2"}).status_code == 409
    from monday.extensions import db
    from monday.models import Attempt
    with APP.app_context():
        att = db.session.get(Attempt, aid)
        assert att.module == 2 and att.draft["q0"] == "0" and att.draft["q1"] == "1"
    r = c.post(run, data={f"q{sat_n - 1}": "0"})
    assert "/result" in r.headers["Location"]
    with APP.app_context():
        att = db.session.get(Attempt, aid)
        assert att.finished_at and len(att.answers) == sat_n


def test_ort_math_in_two_parts():
    from monday.models import Attempt, Work
    c = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        w = Work.query.filter_by(title="ОРТ Математика · Вариант 1 (Monday)").first()
        wid, items = w.id, w.current_version.items
    run = c.post(f"/works/{wid}/start").headers["Location"]
    body = ok(c, run).data.decode()
    # part 1 (1–30): one answer key, compact cards without the four option lines, sheet with А–Г
    assert body.count('class="ort-part"') == 2 and body.count("data-sheet-part=") == 2
    assert "ort-grid--cmp" in body and "больше величина А" in body and "Перейти к части 2" in body
    part1, part2 = body.split('data-part="1"')[0], body.split('data-part="1"')[1].split('class="ort-sheet"')[0]
    assert "Величина А больше" not in part1 and part1.count("Сравните величины в колонках") == 1  # only in the key
    assert 'id="question-30"' in part1 and 'id="question-31"' in part2 and "ort-grid--cmp" not in part2
    sheet1, sheet2 = body.split('data-sheet-part="0"')[1].split('data-sheet-part="1"')
    assert 'name="q29"' in sheet1 and 'name="q30"' not in sheet1 and 'name="q30"' in sheet2 and 'name="q59"' in sheet2
    assert '<span>Д</span>' not in sheet1 and '<span>Д</span>' in sheet2
    # one timer and one hand-in for both parts
    r = c.post(run, data={"q0": items[0]["correct"], "q59": items[59]["correct"]})
    assert "/result" in r.headers["Location"]
    with APP.app_context():
        att = db_get(Attempt, int(run.rstrip("/").split("/")[-1]))
        assert att.finished_at and att.score == 2 and len(att.answers) == 60


def test_ort_monday_variants_mixed_with_pictures():
    import os
    from monday.models import Question, Work
    c = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        works = Work.query.filter(Work.title.like("ОРТ Математика · Вариант % (Monday)")).all()
        assert sorted(w.title[-10] for w in works) == ["1", "2", "3", "4"]
        seen = set()
        for w in works:
            items = w.current_version.items
            assert len(items) == 60 and w.format == "ort" and w.time_limit_min == 90
            assert all(len(it["options"]) == 4 for it in items[:30]) and all(len(it["options"]) == 5 for it in items[30:])
            assert 6 <= sum(1 for it in items if it.get("image_path")) <= 10
            skills = [db_get(Question, i).skill_id for i in w.draft_question_ids]
            assert len(set(skills[:30])) >= 8 and len(set(skills[30:])) >= 8  # topics are mixed
            assert not seen & set(w.draft_question_ids)  # no question in two variants
            seen |= set(w.draft_question_ids)
        pic = next(it["image_path"] for it in works[0].current_version.items if it.get("image_path"))
    assert c.get(f"/uploads/{pic}").status_code == 200


def test_ort_monday_sync_restores_order_easy_to_hard():
    import json, os
    from monday.extensions import db
    from monday.models import Question, Work
    from monday.packs import PACK_DIR, sync_pack
    with open(os.path.join(PACK_DIR, "ort_monday_mix_2026.json"), encoding="utf-8") as f:
        pack = json.load(f)
    with APP.app_context():
        w = Work.query.filter_by(kind="collection", title="ОРТ Математика · Вариант 1 (Monday)").first()
        want = list(w.draft_question_ids)
        w.draft_question_ids = list(reversed(want))
        db.session.commit()
        sync_pack("ort_monday_mix_2026")
        w = db.session.get(Work, w.id)
        assert w.draft_question_ids == want and len(w.current_version.items) == 60
        diffs = [db.session.get(Question, i).difficulty for i in want]
        assert diffs[:10] == [1] * 10 and diffs[30:40] == [1] * 10 and diffs[29] == diffs[59] == 3
        assert len(pack["collections"]) == 4


def test_csca_pool_is_english_and_senior_school():
    from monday.cleanup import csca_only_fitting_questions
    from monday.extensions import db
    from monday.models import ContentNode, Question
    from monday.services import student_pool
    from monday.taxonomy import CSCA_BELOW_LEVEL
    with APP.app_context():
        fr = ContentNode.query.filter_by(code="fractions").first()
        assert "CSCA" not in fr.exams
        q = Question.query.filter_by(language="ru").first()
        q.exams = list(q.exams or []) + ["CSCA"]
        db.session.commit()
        pool = student_pool("CSCA")
        assert pool and all(p.language == "en" for p in pool)
        assert not any(p.skill and p.skill.code in CSCA_BELOW_LEVEL for p in pool)
        csca_only_fitting_questions()
        db.session.commit()
        assert "CSCA" not in db.session.get(Question, q.id).exams
        bad = [x for x in Question.query.all() if "CSCA" in (x.exams or [])
               and (x.language != "en" or not x.skill or x.skill.code in CSCA_BELOW_LEVEL)]
        assert not bad


def test_practice_pool_has_no_repeated_questions():
    from monday.extensions import db
    from monday.models import Question
    from monday.services import question_signature, student_pool
    with APP.app_context():
        q = next(x for x in Question.query.filter_by(status="published", answer_type="choice").all() if "CSCA" in (x.exams or []))
        opts = list(q.options)
        twin = Question(author=q.author, skill=q.skill, text=q.text, answer_type="choice", options=list(reversed(opts)),
                        correct=str(len(opts) - 1 - int(q.correct)), status="published", exams=["CSCA"], language=q.language,
                        material=q.material or [], image_path=q.image_path, source=q.source)
        db.session.add(twin)
        db.session.commit()
        for exam in ("CSCA", "SAT", "ORT", "ENT", "EGE", "OGE"):
            sigs = [question_signature(x) for x in student_pool(exam)]
            assert len(sigs) == len(set(sigs)), exam
        assert twin.id not in {x.id for x in student_pool("CSCA")}


def test_bank_booklet_pages_and_check():
    from monday.bank import booklet_pages
    from monday.models import Question
    c = login(client(), "student@monday.kg", "student123")
    r = c.post("/bank/start", data={"exam": "ORT"})
    assert "/sheet" in r.headers["Location"]
    body = ok(c, r.headers["Location"]).data.decode()
    assert 'class="ort-sheet bb-sheet"' in body and "Проверить страницу" in body
    att_id = int(r.headers["Location"].split("/s/")[1].split("/")[0])
    with APP.app_context():
        from monday.models import Attempt
        att = db_get(Attempt, att_id)
        qs = [db_get(Question, i) for i in att.plan]
        kinds = [any((b or {}).get("type") == "columns" for b in (q.material or [])) for q in qs]
        assert kinds == sorted(kinds, reverse=True)  # ORT: comparisons first
        first = qs[0]
        items = [(k, q.snapshot()) for k, q in enumerate(qs)]
        pages = booklet_pages(items)
        assert [i for pg in pages for row in pg["rows"] for i, _ in row] == list(range(len(qs)))
        assert all(len(pg["rows"]) <= 2 for pg in pages)
        for pg in pages:
            its = [it for row in pg["rows"] for _i, it in row]
            assert len(its) <= 4
            assert not any(it.get("image_path") for it in its) or len(its) == 1
        assert all(len({pg["compare"]}) == 1 for pg in pages)
    r = c.post(f"/bank/s/{att_id}/check", data={"i": "0", "given": first.correct})
    assert r.get_json()["ok"] is True
    body = ok(c, f"/bank/s/{att_id}/sheet").data.decode()
    assert 'data-sheet-row="0"' in body and "is-ok" in body
    r = c.post("/bank/start", data={"exam": "ORT", "view": "one"})
    assert "/sheet" not in r.headers["Location"]
    one = ok(c, r.headers["Location"] + "?i=5").data.decode()
    assert "/sheet?q=5" in one and "view-switch" in one  # and back to pages
    assert 'id="question-6"' in ok(c, r.headers["Location"] + "/sheet?q=5").data.decode()


def test_sat_bank_shows_entry_rules_for_typed_answers():
    from monday.models import Attempt, Question
    c = login(client(), "student@monday.kg", "student123")
    r = c.post("/bank/start", data={"exam": "SAT", "t": "number", "view": "one"})
    loc = r.headers["Location"]
    body = ok(c, loc).data.decode()
    assert "Без запятых, % и $" in body and 'data-drawer-open="entry"' in body and "Правильная запись ответа" in body
    sheet = ok(c, loc + "/sheet").data.decode()
    assert "Без запятых, % и $" in sheet


def test_old_ort_monday_collections_are_replaced():
    from monday.cleanup import replace_ort_monday_variants
    from monday.extensions import db
    from monday.models import Question, Work
    from monday.services import publish_work
    with APP.app_context():
        q = Question.query.filter_by(source="ort_monday_mix_2026").first()
        old = Question(author=q.author, text="старый вопрос", answer_type="choice", options=["1", "2"], correct="0",
                       status="published", source="ort_monday_book_2026", exams=["ORT"], material=[])
        db.session.add(old)
        db.session.flush()
        w = Work(author=q.author, kind="collection", category="full", exam="ORT", format="ort", title="ОРТ Математика · Вариант 1 (Monday)",
                 time_limit_min=90, status="draft", draft_question_ids=[old.id])
        db.session.add(w)
        db.session.flush()
        publish_work(w)
        wid, qid = w.id, old.id
        replace_ort_monday_variants()
        db.session.commit()
        assert db.session.get(Work, wid) is None and db.session.get(Question, qid).status == "draft"
        assert Work.query.filter(Work.title.like("ОРТ Математика · Вариант % (Monday)")).count() == 4


def test_clear_recent_sessions_keeps_stats():
    from monday.models import Attempt, User
    c = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        uid = User.query.filter_by(email="student@monday.kg").first().id
        n = Attempt.query.filter_by(user_id=uid).count()
    body = ok(c, "/sessions").data.decode()
    assert "Очистить всё" in body and 'class="sc-card"' in body
    r = c.post("/sessions/clear")
    assert r.status_code == 302
    body = ok(c, "/sessions", contains="Список недавних сессий очищен").data.decode()
    assert 'class="sc-card"' not in body and "Очистить всё" not in body
    with APP.app_context():
        assert Attempt.query.filter_by(user_id=uid).count() == n  # only the list is emptied


def test_journal_with_more_days_than_shown():
    """Mistakes on more days than the journal shows at once used to crash the page (unfinished day cards)."""
    from datetime import timedelta
    from monday.extensions import db
    from monday.models import Attempt, AttemptAnswer, User, utcnow
    with APP.app_context():
        uid = User.query.filter_by(email="student@monday.kg").first().id
        rows = (AttemptAnswer.query.join(Attempt).filter(Attempt.user_id == uid, Attempt.finished_at.isnot(None),
                                                         AttemptAnswer.is_correct.is_(False)).limit(12).all())
        saved = [(r.id, r.answered_at) for r in rows]
        for k, r in enumerate(rows):
            r.answered_at = utcnow() - timedelta(days=k)
        db.session.commit()
    try:
        c = login(client(), "student@monday.kg", "student123")
        assert len(saved) > 7
        ok(c, "/journal?days=7")
    finally:
        with APP.app_context():
            for rid, t in saved:
                db.session.get(AttemptAnswer, rid).answered_at = t
            db.session.commit()


def test_journal_mistakes_session_has_one_question_per_open_record():
    from monday.models import Attempt
    c = login(client(), "student@monday.kg", "student123")
    body = ok(c, "/journal").data.decode()
    n = int(re.search(r'name="count" value="(\d+)"', body).group(1))
    assert 1 <= n <= 30 and "ИИ" not in body
    r = c.post("/sessions/start/darwin", data={"count": str(n)})
    with APP.app_context():
        att = db_get(Attempt, int(r.headers["Location"].rstrip("/").split("/")[-1]))
        assert len(att.plan) == n


def test_ort_trig_comparisons_pack():
    from monday.models import Question
    with APP.app_context():
        qs = Question.query.filter_by(source="ort_trig_compare_2026").all()
        assert len(qs) == 15 and all(q.exams == ["ORT"] and q.skill.code == "right_trig" for q in qs)
        assert all(q.material[0]["type"] == "columns" and len(q.options) == 4 for q in qs)
    c = login(client(), "student@monday.kg", "student123")
    ok(c, "/skills?exam=ORT&show=list", contains=["Таблица", "Карта"])


def test_admin_name_platform_author_and_moderation_count():
    from monday.models import User
    with APP.app_context():
        admin = User.query.filter_by(email="admin@monday.kg").first()
        assert admin.name == "Admin Monday" and admin.public_name == "Monday Academy"
    s = login(client(), "student@monday.kg", "student123")
    ok(s, "/collections", contains="Monday Academy")
    a = login(client(), "admin@monday.kg", "monday2026")
    body = ok(a, "/admin/").data.decode()
    assert "на модерации" in body and "тестов на проверке" not in body


def test_assistant_fixes_reported_question_and_gaps():
    from monday.extensions import db
    from monday.models import Question, Report
    with APP.app_context():
        q = Question.query.filter_by(status="published", answer_type="choice", source=None).first()
        qid, skill, opts = q.id, q.skill_id, list(q.options)
    st = login(client(), "student@monday.kg", "student123")
    st.post("/report", data={"question_id": str(qid), "kind": "typo", "message": "опечатка в условии"})
    with APP.app_context():
        rid = Report.query.filter_by(question_id=qid, status="open").first().id
    a = login(client(), "assistant@monday.kg", "assistant123")
    ok(a, "/assistant/", contains=["Исправления", "Где мало вопросов"])
    ok(a, "/assistant/fixes", contains=["опечатка в условии", f"/teacher/questions/new?fix={rid}"])
    ok(a, "/assistant/gaps", contains="Где мало вопросов")
    ok(a, f"/teacher/questions/new?fix={rid}", contains=f"Исправление к вопросу #{qid}")
    data = {"exams": ["ORT"], "skill_id": str(skill), "text": "Исправленное условие задачи", "difficulty": "2",
            "weight": "1", "language": "ru", "answer_type": "choice", "correct_option": "0"}
    data.update({f"option{i}": o for i, o in enumerate(opts)})
    r = a.post(f"/teacher/questions/new?fix={rid}", data=data)
    assert r.status_code == 302
    with APP.app_context():
        fix = Question.query.filter_by(replaces_id=qid).first()
        assert fix.status == "pending"
        fix_id = fix.id
    adm = login(client(), "admin@monday.kg", "monday2026")
    ok(adm, "/review/questions", contains=f"исправление к #{qid}")
    adm.post(f"/review/questions/{fix_id}", data={"decision": "approve"})
    with APP.app_context():
        assert db.session.get(Question, qid).text == "Исправленное условие задачи"
        assert db.session.get(Question, fix_id) is None
        assert db.session.get(Report, rid).status == "fixed"
    # «нужной ветки нет»: the request reaches the admin's error reports
    a.post("/assistant/branch-request", data={"parent_id": str(db_get_skill_parent(skill)), "name": "Новый навык X"})
    ok(adm, "/teacher/reports", contains="Нужна новая ветка: Новый навык X")


def db_get_skill_parent(skill_id):
    from monday.models import ContentNode
    with APP.app_context():
        return db_get(ContentNode, skill_id).parent_id


def test_teacher_pages_compact_and_labels():
    t = login(client(), "aibek@monday.kg", "teacher123")
    body = ok(t, "/teacher/").data.decode()
    assert 't-today' in body and "hero--home" not in body and "навыков или есть просроченная" in body
    ok(t, "/teacher/review?show=written", contains="Письменные ответы")
    body = ok(t, "/teacher/assign").data.decode()  # «Выдать задание» lights up «Работы», not «Проверка»
    assert re.search(r'class="rail__item is-active[^"]*" href="/teacher/works"', body)
    assert "Одобрено вопросов" not in ok(t, "/teacher/account").data.decode()
    assert 'class="pk-drop' in ok(t, "/teacher/bank").data.decode()
    assert 'data-we-steps' in ok(t, "/teacher/works/new?kind=homework").data.decode()


def test_formula_sheets():
    import io
    from monday.models import ReferenceSheet
    c = login(client(), "student@monday.kg", "student123")
    ok(c, "/formulas", contains=["Формулы", "Новый лист"])
    c.post("/formulas", data={"action": "create", "title": "SAT формулы", "exam": "SAT"})
    with APP.app_context():
        sid = ReferenceSheet.query.filter_by(title="SAT формулы").first().id
    c.post("/formulas", data={"action": "add_entry", "sheet_id": str(sid), "branch": "Геометрия",
                              "topic": "Площадь круга", "formula": "$S = \\pi r^2$"})
    ok(c, "/formulas", contains=["Площадь круга", "Геометрия", "data-mathkb"])
    # several formulas at once, the section typed in another case joins the same section, $…$ added
    c.post("/formulas", data={"action": "add_entry", "sheet_id": str(sid), "branch": " геометрия ",
                              "topic": ["Площадь квадрата", "Теорема Пифагора", ""], "formula": ["S = a^2", "$c^2 = a^2 + b^2$", ""]})
    with APP.app_context():
        from monday.models import SheetEntry
        entries = SheetEntry.query.filter_by(sheet_id=sid).all()
        assert len(entries) == 3 and {e.branch for e in entries} == {"Геометрия"}
        assert any(e.formula == "$S = a^2$" for e in entries)
    assert c.get("/formulas").data.decode().count('class="sheet-view__branch') == 1
    # the sheet opens inside tests
    from monday.models import Work
    with APP.app_context():
        wid = Work.query.filter_by(title="SAT March 2025").first().id
    run = c.post(f"/works/{wid}/start").headers["Location"]
    ok(c, run, contains=["Мои формулы", "Площадь круга"])
    c.post("/formulas", data={"action": "toggle", "sheet_id": str(sid)})
    assert "Площадь круга" not in c.get(run).data.decode()
    other = login(client(), "student2@monday.kg", "student123")
    assert other.post("/formulas", data={"action": "delete_sheet", "sheet_id": str(sid)}).status_code == 404


def test_test_autosave_and_resume():
    from monday.models import Attempt, Work
    c = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        w = Work.query.filter_by(title="SAT March 2025").first()
        wid = w.id
        first = w.current_version.items[0]
    run = c.post(f"/works/{wid}/start").headers["Location"]
    aid = int(run.rstrip("/").split("/")[-1])
    r = c.post(f"/attempts/{aid}/save", data={"name": "q0", "value": first["correct"]})
    assert r.status_code == 200 and r.get_json()["ok"]
    assert c.post(f"/attempts/{aid}/save", data={"name": "q999", "value": "1"}).status_code == 400
    assert c.post(f"/attempts/{aid}/save", data={"name": "evil", "value": "1"}).status_code == 400
    with APP.app_context():
        from monday.extensions import db
        assert db.session.get(Attempt, aid).draft == {"q0": first["correct"]}
    # reload keeps the answer selected
    body = ok(c, run).data.decode()
    if first["answer_type"] == "choice":
        assert re.search(r'name="q0" value="%s"\s+checked' % first["correct"], body)
    # another student cannot save into this attempt
    other = login(client(), "student2@monday.kg", "student123")
    assert other.post(f"/attempts/{aid}/save", data={"name": "q0", "value": "1"}).status_code == 404
    # submitting grades with weights and clears the draft
    r = c.post(run, data={"q0": first["correct"]})
    with APP.app_context():
        att = db.session.get(Attempt, aid)
        assert att.finished_at and att.draft == {} and att.score >= 1
    assert c.post(f"/attempts/{aid}/save", data={"name": "q0", "value": "1"}).status_code == 409


def test_publish_page_grouped_by_tree():
    t = login(client(), "aibek@monday.kg", "teacher123")
    ok(t, "/teacher/works", contains=["Полные варианты экзаменов", "Логарифмы", "ДЗ: свойства логарифмов", "По темам"])
    ok(t, "/teacher/works?view=list", contains=["ОРТ Май 2026"])
    ok(t, "/teacher/works?status=draft", contains="Функции и графики")
    ok(t, "/teacher/questions?node=1")


def test_profile_photo_and_name():
    import io
    from monday.models import User
    for email, pw, page in [("student@monday.kg", "student123", "/profile"), ("aibek@monday.kg", "teacher123", "/teacher/account")]:
        c = login(client(), email, pw)
        ok(c, page, contains=["Изменить" if page == "/profile" else "Изменить имя", "data-avatar-input"])
        png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
               b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\x8d\xf1\x00\x00\x00\x00IEND\xaeB`\x82")
        r = c.post("/prefs/avatar", data={"next": page, "avatar": (io.BytesIO(png), "me.png")},
                   content_type="multipart/form-data")
        assert r.status_code == 302 and r.headers["Location"].endswith(page)
        with APP.app_context():
            path = User.query.filter_by(email=email).first().avatar_path
            assert path and path.endswith(".png")
        body = ok(c, page).data.decode()
        assert f"/uploads/{path}" in body and "Удалить фото" in body
        assert c.post("/prefs/avatar", data={"avatar": (io.BytesIO(b"x"), "evil.exe")},
                      content_type="multipart/form-data").status_code == 302
        c.post("/prefs/avatar", data={"remove": "1", "next": page})
        with APP.app_context():
            assert User.query.filter_by(email=email).first().avatar_path is None
    c = login(client(), "student@monday.kg", "student123")
    c.post("/profile", data={"action": "profile", "name": "Темирлан Манашов", "exam": "ORT"})
    ok(c, "/profile", contains="Темирлан Манашов")
    c.post("/profile", data={"action": "profile", "name": "Тима Манашов", "exam": "ORT"})


def test_old_database_gets_new_columns():
    import pytest
    if os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("edits the SQLite file directly")
    import sqlite3
    from sqlalchemy import inspect
    from monday.extensions import db
    with APP.app_context():
        path = db.engine.url.database
    con = sqlite3.connect(path)
    con.execute('ALTER TABLE "user" DROP COLUMN avatar_path')
    con.commit(); con.close()
    with APP.app_context():
        db.engine.dispose()
        from monday import _check_schema
        _check_schema()
        assert "avatar_path" in {c["name"] for c in inspect(db.engine).get_columns("user")}


def test_question_bank_filters_and_play():
    c = login(client(), "student@monday.kg", "student123")
    app = APP
    r = c.get("/bank/?exam=SAT")
    assert r.status_code == 200 and "Банк вопросов" in r.data.decode() and "Сложность" in r.data.decode()
    r = c.get("/bank/?exam=SAT&d=3&t=number")
    assert r.status_code == 200
    token = ""
    r = c.post("/bank/start", data={"csrf_token": token, "exam": "SAT", "d": "2", "view": "one"})
    assert r.status_code == 302 and "/bank/s/" in r.headers["Location"]
    play = r.headers["Location"]
    att_id = int(play.rstrip("/").split("/")[-1])
    r = c.get(play)
    assert r.status_code == 200 and "Отметить для проверки" in r.data.decode() and "Попытки" in r.data.decode()
    from monday.models import Attempt, BankState, Question
    with app.app_context():
        from monday.extensions import db
        att = db.session.get(Attempt, att_id)
        q = db.session.get(Question, att.plan[0])
        assert q.difficulty == 2
        wrong = "x" if q.answer_type == "number" else str((int(q.correct) + 1) % len(q.options))
        right = q.correct
        qid = q.id
    # explanation is closed before the first try
    r = c.post(f"/bank/s/{att_id}/reveal", data={"csrf_token": token, "i": 0})
    assert r.status_code == 409
    r = c.post(f"/bank/s/{att_id}/check", data={"csrf_token": token, "i": 0, "given": wrong, "seconds": 12})
    assert r.json["ok"] is False and "correct" not in r.json and r.json["attempts"] == 1
    r = c.post(f"/bank/s/{att_id}/check", data={"csrf_token": token, "i": 0, "given": right, "seconds": 5})
    assert r.json["ok"] is True and r.json["correct"] == right and r.json["attempts"] == 2
    c.post("/bank/mark", data={"csrf_token": token, "question_id": qid, "on": "1"})
    with app.app_context():
        st = BankState.query.filter_by(question_id=qid).first()
        assert st.marked and st.seconds == 17 and st.last_correct
    r = c.get("/bank/?exam=SAT&mk=yes")
    body = r.data.decode()
    assert "сессия по всем фильтрам: 1<" in body  # the filter keeps the one marked question
    assert re.search(r'bk-pchip--mark is-on.*?<b class="num">1</b>', body, re.S)  # the card counts the whole exam
    assert re.search(r'<b class="num">\d+</b> из <span class="num">\d+</span> решено', body)


def test_teacher_today_bank_and_attendance():
    from datetime import date as _date
    from monday.models import Attendance, StudentRecord, Work, Assignment
    t = login(client(), "aibek@monday.kg", "teacher123")
    ok(t, "/teacher/", contains=["Домашка на неделю", "Класс в точках", "Тест понедельника", "Свежие ошибки"])
    ok(t, "/teacher/?week=-1", contains="Домашка на неделю")
    with APP.app_context():
        rec = StudentRecord.query.filter_by(name="Тима Манашов").first()
        rec_id = rec.id
        a = Assignment.query.filter_by(record_id=rec_id).first()
        a_id = a.id
    r = t.post("/teacher/attendance", data={"record_id": rec_id, "status": "late"}, headers={"X-Requested-With": "fetch"})
    assert r.json["status"] == "late"
    r = t.post(f"/teacher/assignments/{a_id}/due", data={"day": "2030-01-07"}, headers={"X-Requested-With": "fetch"})
    assert r.json["due"].startswith("2030-01-07")
    with APP.app_context():
        assert Attendance.query.filter_by(record_id=rec_id, day=__import__("monday.models", fromlist=["today"]).today()).first().status == "late"
    ok(t, f"/teacher/students/{rec_id}", contains=["Посещаемость", "Итог", "Журнал ошибок"])
    # bank: filter, then add two questions into a new homework
    ok(t, "/teacher/bank?exam=ORT", contains=["Банк вопросов", "Корзина"])
    r = t.get("/teacher/picker/?exam=ORT&d=2&sort=hard")
    qids = [int(x) for x in re.findall(r'class="pk-check" value="(\d+)"', r.json["list"])][:2]
    assert r.json["total"] > 0 and "Все темы" in r.json["tree"]
    rnd = t.get("/teacher/picker/random?exam=ORT&n=5").json["items"]
    assert len(rnd) == 5 and len({i["id"] for i in rnd}) == 5
    plan = t.get("/teacher/picker/plan?exam=ORT&per=2&e=1&m=1&h=0").json["items"]
    assert len(plan) >= 4
    assert len(qids) == 2
    r = t.post("/teacher/bank/add", data={"qid": qids, "work": "new", "exam": "ORT", "kind": "homework"})
    assert r.status_code == 302 and "/works/" in r.headers["Location"]
    with APP.app_context():
        w = Work.query.order_by(Work.id.desc()).first()
        assert w.draft_question_ids == qids and w.kind == "homework"


def test_big_collection_waits_for_admin():
    from monday.models import Question, Work
    t = login(client(), "aibek@monday.kg", "teacher123")
    with APP.app_context():
        ids = [q.id for q in Question.query.filter_by(status="published").limit(20).all()]
    r = t.post("/teacher/works/new", data={"title": "Большой сборник", "kind": "collection", "exam": "ORT",
                                          "category": "full", "time_limit_min": "60", "format": "ort",
                                          "question_order": ",".join(map(str, ids)), "action": "publish"})
    assert r.status_code == 302 and "status=pending" in r.headers["Location"]
    with APP.app_context():
        w = Work.query.filter_by(title="Большой сборник").first()
        assert w.status == "pending" and w.current_version.question_count == 20
        wid = w.id
    s = login(client(), "student@monday.kg", "student123")
    assert "Большой сборник" not in s.get("/collections").data.decode()
    a = login(client(), "admin@monday.kg", "monday2026")
    ok(a, "/admin/?tab=moderation", contains=["Большой сборник", "Опубликовать"])
    a.post(f"/admin/works/{wid}/review", data={"decision": "approve"})
    with APP.app_context():
        from monday.extensions import db
        assert db.session.get(Work, wid).status == "published"
    # small homework is published straight away
    r = t.post("/teacher/works/new", data={"title": "Мини ДЗ", "kind": "homework", "exam": "ORT", "category": "thematic",
                                          "time_limit_min": "10", "format": "ort", "question_order": ",".join(map(str, ids[:3])),
                                          "action": "publish"})
    with APP.app_context():
        assert Work.query.filter_by(title="Мини ДЗ").first().status == "published"


def test_questions_of_the_day():
    from datetime import date as _date
    from monday.models import DailyPick, DailyAnswer, Question
    s = login(client(), "student@monday.kg", "student123")
    ok(s, "/home", contains=["Вопросы дня", "выбрал"])
    ok(s, "/daily/", contains=["Вопросы дня", "Ответить", "Вопросы дня — готово"])
    with APP.app_context():
        pick = DailyPick.query.filter(DailyPick.teacher_id.isnot(None), DailyPick.day == __import__("monday.models", fromlist=["today"]).today()).first()
        pid, correct = pick.id, pick.question.correct
    r = s.post(f"/daily/{pid}/answer", data={"given": correct})
    assert r.json["ok"] is True and r.json["rate"]["total"] == 1 and r.json["streak"] == 1
    # only one try: a second answer keeps the first result
    r = s.post(f"/daily/{pid}/answer", data={"given": "zzz"})
    assert r.json["ok"] is True
    with APP.app_context():
        assert DailyAnswer.query.filter_by(pick_id=pid).count() == 1
    # teacher sees it and can add tomorrow's question from the bank
    t = login(client(), "aibek@monday.kg", "teacher123")
    ok(t, "/teacher/", contains=["Вопросы дня", "1/"])
    with APP.app_context():
        qid = Question.query.filter_by(status="published").first().id
    r = t.post("/teacher/bank/add", data={"qid": [qid], "work": "daily-tomorrow", "exam": "ORT"})
    assert r.status_code == 302
    with APP.app_context():
        assert DailyPick.query.filter_by(day=__import__("monday.models", fromlist=["today"]).today() + __import__("datetime").timedelta(days=1)).count() == 1
    # a student without a teacher gets Monday's question
    other = login(client(), "student27@monday.kg", "student123")
    ok(other, "/home", contains="Monday подобрал")


SAMPLE_TEST = """1. Найдите значение выражения $2^3 + 4$.
А) 10  Б) 12  В) 14  Г) 16
2) Решите уравнение $3x = 12$. Ответ: 4
3. Найдите $25\\%$ от числа 360.
(A) 80
(B) 90
(C) 95
(D) 100
Ответы: 1-Б 3-Б"""


def test_importer_parses_text_and_json():
    from monday.importer import parse
    with APP.app_context():
        qs = parse(SAMPLE_TEST)
        assert [q["answer_type"] for q in qs] == ["choice", "number", "choice"]
        assert qs[0]["options"] == ["10", "12", "14", "16"] and qs[0]["correct"] == "1"
        assert qs[1]["correct"] == "4" and qs[1]["text"].endswith("$3x = 12$.")
        assert qs[2]["correct"] == "1"
        js = parse('[{"test_type": "SAT", "question_text": "What is $2+2$?", "options": ["A) 3", "B) 4"], '
                   '"correct_answer": "B", "topic": "Проценты", "difficulty": "Hard"}]')
        assert js[0]["options"] == ["3", "4"] and js[0]["correct"] == "1" and js[0]["exam"] == "SAT" and js[0]["difficulty"] == 3


def test_assistant_uploads_and_methodist_reviews():
    from monday.models import Question, User
    a = login(client(), "assistant@monday.kg", "assistant123")
    r = a.get("/home")
    assert r.status_code == 302 and "/assistant" in r.headers["Location"]
    assert a.get("/teacher/").status_code == 403          # no access to students and grades
    ok(a, "/assistant/", contains=["Загрузка вопросов", "Разобрать"])
    r = ok(a, "/assistant/import", status=405)            # GET not allowed
    r = a.post("/assistant/import", data={"raw": SAMPLE_TEST, "exams": ["ORT"]})
    html = r.data.decode()
    assert r.status_code == 200 and "Нашли вопросов: 3" in html
    with APP.app_context():
        from monday.models import Skill
        sid = Skill.query.filter_by(code="percents").first().id
    form = {"count": "3", "exams": ["ORT"], "action": "send"}
    for i, (text, typ, opts, correct) in enumerate([
            ("Найдите $2^3 + 4$ (импорт).", "choice", ["10", "12", "14", "16"], "1"),
            ("Решите уравнение $3x = 12$ (импорт).", "number", [], "4"),
            ("Найдите 25% от 360 (импорт).", "choice", ["80", "90"], "1")]):
        p = f"q{i}-"
        form.update({p + "include": "1", p + "text": text, p + "type": typ, p + "correct": correct,
                     p + "skill": str(sid), p + "difficulty": "2"})
        form[p + "opt"] = opts
    r = a.post("/assistant/import/save", data=form)
    assert r.status_code == 302 and "/assistant/mine" in r.headers["Location"]
    with APP.app_context():
        mine = Question.query.filter(Question.text.like("%(импорт)%")).all()
        assert len(mine) == 3 and all(q.status == "pending" for q in mine)
        qid = mine[0].id
        qid2 = mine[1].id
    ok(a, "/assistant/mine?tab=pending", contains="(импорт)")
    # a broken question is reported, nothing saved
    bad = {"count": "1", "exams": ["ORT"], "q0-include": "1", "q0-text": "", "q0-type": "choice", "q0-skill": ""}
    assert a.post("/assistant/import/save", data=bad).status_code == 400
    # the methodist (Aibek) reviews
    t = login(client(), "aibek@monday.kg", "teacher123")
    ok(t, "/review/questions", contains=["Проверка вопросов", "(импорт)"])
    t.post(f"/review/questions/{qid}", data={"decision": "approve"})
    assert t.post(f"/review/questions/{qid2}", data={"decision": "return", "note": ""}).status_code == 302
    t.post(f"/review/questions/{qid2}", data={"decision": "return", "note": "Добавьте объяснение"})
    with APP.app_context():
        from monday.extensions import db
        assert db.session.get(Question, qid).status == "published"
        q2 = db.session.get(Question, qid2)
        assert q2.status == "draft" and q2.review_note == "Добавьте объяснение"
    ok(a, "/assistant/mine?tab=returned", contains="Добавьте объяснение")
    # a regular teacher can't review; a teacher's own import is published at once
    n = login(client(), "nurai@monday.kg", "teacher123")
    assert n.get("/review/questions").status_code == 403
    adm = login(client(), "admin@monday.kg", "monday2026")
    ok(adm, "/admin/?tab=assistants", contains="assistant@monday.kg")


def test_master_map_and_exam_views():
    from monday.models import ContentNode, Question, User
    from monday.taxonomy import MASTER, exam_view, keyset
    with APP.app_context():
        codes = [k for _b, _n, subs in MASTER for _s, _sn, skills in subs for k, *_ in skills]
        assert len(codes) >= 60 and len(codes) == len(set(codes))
        assert ContentNode.query.filter(ContentNode.code.in_(codes), ContentNode.archived.is_(False)).count() == len(codes)
        teacher = User.query.filter_by(email="aibek@monday.kg").first()
        sat = exam_view(teacher, "SAT")
        assert [s["en"] for s in sat][:4] == ["Algebra", "Advanced Math", "Problem-Solving and Data Analysis", "Geometry and Trigonometry"]
        ks = keyset(sat)
        assert "x:psda:pct" in ks and ks["x:psda:pct"]
        ort = exam_view(teacher, "ORT")
        assert any(sk["name"].startswith("Сравнение величин") for sec in ort for g in sec["groups"] for sk in g["skills"])
        assert all(q.tags is not None for q in Question.query.limit(50).all())
    t = login(client(), "aibek@monday.kg", "teacher123")
    r = t.get("/teacher/picker/?exam=SAT&k=x:psda:pct")
    assert r.json["total"] > 0 and "Problem-Solving" in r.json["tree"]
    assert t.get("/teacher/picker/?exam=ORT&tag=compare").json["total"] > 0
    s = login(client(), "student@monday.kg", "student123")
    ok(s, "/bank/?exam=SAT", contains=["Problem-Solving and Data Analysis", "Percentages"])
    r = s.post("/bank/start", data={"exam": "SAT", "only": "x:psda:pct"})
    assert r.status_code == 302 and "/bank/s/" in r.headers["Location"]


def test_questions_translated_for_student():
    """Known question patterns are shown in the student's language; the original is one click away."""
    from monday.content_i18n import translate_string
    assert translate_string("Найдите 15% от числа 240.", "ru", "en") == "Find 15% of 240."
    assert translate_string("Решите уравнение: $3x + 7 = 22$", "ru", "ky") == "Теңдемени чыгарыңыз: $3x + 7 = 22$"
    assert translate_string("$x^2$", "ru", "kk") == "$x^2$"            # formulas only: nothing to translate
    assert translate_string("Совсем новая фраза", "ru", "en") is None   # unknown: left for the online translator
    c = login(client(), "student@monday.kg", "student123")
    c.post("/prefs/lang", data={"lang": "en", "next": "/home"})
    from monday.extensions import db
    from monday.models import Attempt, Question, User
    with APP.app_context():  # a session on a seed question with a known pattern (compilation questions may have none)
        q = Question.query.filter(Question.source.is_(None), Question.text.like("Найдите%")).order_by(Question.id).first()
        u = User.query.filter_by(email="student@monday.kg").first()
        att = Attempt(user=u, mode="franklin", plan=[q.id], position=0, total=1)
        db.session.add(att)
        db.session.commit()
        att_id = att.id
    body = c.get(f"/sessions/{att_id}", follow_redirects=True).data.decode()
    assert "Show original" in body and "/prefs/original" in body
    c.get("/prefs/original?next=/home")
    body = c.get("/sessions").data.decode()
    c.get("/prefs/original?next=/home")
    c.post("/prefs/lang", data={"lang": "ru", "next": "/home"})


def test_ege_full_variant_combines_both_parts():
    from monday.models import Work
    with APP.app_context():
        w = Work.query.filter(Work.title.like("%Вариант 1 (полный%")).first()
        items = w.current_version.items if w.current_version else None
        assert w.time_limit_min == 235
        assert items and len(items) == 19
        assert [i["answer_type"] for i in items[12:]] == ["written"] * 7
        assert [i["weight"] for i in items[12:]] == [2, 3, 2, 2, 3, 4, 4]
        assert items[0]["answer_type"] == "number"


def test_written_answer_photo_self_assessment_and_teacher_mark():
    import io
    from monday.models import Attempt, AttemptAnswer, StudentRecord, User, Work
    s = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        w = Work.query.filter(Work.title.like("%Вариант 1 (полный%")).first()
        wid, first = w.id, w.current_version.items[0]
        student = User.query.filter_by(email="student@monday.kg").first()
        teacher_email = StudentRecord.query.filter_by(student_user_id=student.id).first().teacher.email
    run = s.post(f"/works/{wid}/start").headers["Location"]
    ok(s, run, contains=["data-photo-input", "Решение записано на бумаге"])
    att_id = int(run.rstrip("/").split("/")[-1])
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    r = s.post(f"/attempts/{att_id}/photo", data={"idx": "12", "photo": (io.BytesIO(png), "sol.png")},
               content_type="multipart/form-data")
    assert r.get_json()["ok"]
    assert s.post(f"/attempts/{att_id}/photo", data={"idx": "0", "photo": (io.BytesIO(png), "x.png")},
                  content_type="multipart/form-data").status_code == 400
    r = s.post(run, data={"q0": first["correct"], "q13": "done"})
    result = r.headers["Location"]
    ok(s, result, contains=["ждёт оценки"])
    with APP.app_context():
        att = db_get(Attempt, att_id)
        assert att.score == 1 and att.total == 12 + 20
        by_idx = {a.index: a for a in att.answers}
        assert by_idx[12].photo_path and by_idx[12].points is None
        assert by_idx[13].points is None and by_idx[14].points == 0  # paper-only answer waits, empty one is 0
    s.post(f"/attempts/{att_id}/assess/12", data={"points": "1"})
    with APP.app_context():
        assert db_get(Attempt, att_id).score == 2
    t = login(client(), teacher_email, "teacher123")
    ok(t, "/teacher/review?show=written", contains=[f"/teacher/attempts/{att_id}/written", "Оценить"])
    ok(t, f"/teacher/attempts/{att_id}/written", contains=["Проверка части 2", "самопроверка ученика"])
    t.post(f"/teacher/attempts/{att_id}/written", data={"idx": "12", "points": "2"})
    s.post(f"/attempts/{att_id}/assess/12", data={"points": "0"})  # teacher's mark stays
    with APP.app_context():
        att = db_get(Attempt, att_id)
        a = AttemptAnswer.query.filter_by(attempt_id=att_id, index=12).first()
        assert (a.points, a.points_by) == (2, "teacher") and att.score == 3
    other = login(client(), "nurai@monday.kg", "teacher123")
    assert other.get(f"/teacher/attempts/{att_id}/written").status_code == 404
    t.post(f"/teacher/attempts/{att_id}/written", data={"idx": "13", "points": "0"})
    ok(t, "/teacher/review?show=written", contains="Все решения оценены")
    ok(s, result, contains="ЕГЭ · ")


def test_data_fixes_remove_demo_collections_and_rename_student():
    from monday.cleanup import DEMO_COLLECTIONS, run_fixes
    from monday.extensions import db
    from monday.models import Attempt, StudentRecord, User, Work
    app = make_app()
    app.config["DATA_FIXES"] = True
    with app.app_context():
        assert Work.query.filter(Work.title.in_(DEMO_COLLECTIONS)).count() >= 12
        packs_before = Work.query.filter(Work.title.like("ЕГЭ профиль 2026%")).count()
        run_fixes()
        run_fixes()  # second run does nothing
        assert Work.query.filter(Work.title.in_(DEMO_COLLECTIONS)).count() == 0
        assert Work.query.filter(Work.title.like("ЕГЭ профиль 2026%")).count() == packs_before > 0
        assert all(a.work_version is not None for a in Attempt.query.filter(Attempt.work_version_id.isnot(None)))
        u = User.query.filter_by(email="student@monday.kg").first()
        assert u.name == "Student"
        assert StudentRecord.query.filter_by(student_user_id=u.id).first().name == "Student"
        db.session.remove()
    c = app.test_client()
    login(c, "student@monday.kg", "student123")
    assert "ОРТ Май 2026" not in c.get("/collections").data.decode()
    for path in ("/home", "/skills", "/sessions", "/collections?exam=SAT", "/homework", "/journal", "/monday", "/profile", "/bank/"):
        assert c.get(path).status_code in (200, 302), path


def test_ort_sheet_allows_one_correction():
    from monday.models import Assignment, Attempt, StudentRecord, User, Work
    s = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        from monday.extensions import db
        student = User.query.filter_by(email="student@monday.kg").first()
        rec = StudentRecord.query.filter_by(student_user_id=student.id).first()
        work = Work.query.filter_by(kind="homework", status="published", format="ort").first()
        a = Assignment(work=work, teacher_id=rec.teacher_id, record=rec)
        db.session.add(a)
        db.session.commit()
        aid = a.id
        idx = next(i for i, it in enumerate(work.current_version.items) if it["answer_type"] == "choice")
    run = s.post(f"/homework/{aid}/start").headers["Location"]
    att_id = int(run.rstrip("/").split("/")[-1])
    ok(s, run, contains="только один раз")
    save = lambda v: s.post(f"/attempts/{att_id}/save", data={"name": f"q{idx}", "value": v})
    assert save("0").status_code == 200      # first mark: circle
    assert save("0").status_code == 200      # same mark again is fine
    assert save("1").status_code == 200      # one correction: square
    assert save("2").status_code == 409      # no second correction
    ok(s, run, contains="bubble--square")
    r = s.post(run, data={f"q{idx}": "3"})   # hand-in can't sneak a change in either
    with APP.app_context():
        att = db_get(Attempt, att_id)
        assert att.finished_at and next(x for x in att.answers if x.index == idx).given == "1"


def test_bank_source_filter_and_format_info():
    from monday.models import Question
    c = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        assert Question.query.filter(Question.source.isnot(None)).count() > 0
    r = c.get("/bank/?exam=SAT&src=pack").data.decode()
    assert "Из сборников" in r and "От учителей" in r
    t = login(client(), "aibek@monday.kg", "teacher123")
    ok(t, "/teacher/works/new?kind=homework", contains=["data-format-info=\"ort\"", "исправить только один раз"])


def test_mistakes_review_page():
    from monday.models import Attempt, AttemptAnswer, User
    c = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        u = User.query.filter_by(email="student@monday.kg").first()
        att = (Attempt.query.join(AttemptAnswer).filter(Attempt.user_id == u.id, Attempt.finished_at.isnot(None),
                                                        Attempt.work_version_id.isnot(None),
                                                        AttemptAnswer.is_correct.is_(False)).first())
        att_id = att.id
        wrong = [a.id for a in att.answers if a.is_correct is False]
    ok(c, "/journal", contains=f"/journal/attempt/{att_id}")
    page = f"/journal/attempt/{att_id}"
    ok(c, page, contains=["Разбор ошибок", "Понял, дальше", "Потренировать эти темы"])
    for tab in ("wrong", "blank", "all"):
        assert c.get(page + f"?tab={tab}").status_code == 200
    # «Понял, дальше» closes the mistake and goes to the next one on the same page
    r = c.post(f"/journal/{wrong[0]}", data={"reason": "careless", "resolve": "1", "next": page + "?tab=all&i=1"})
    assert page + "?tab=all&i=1" in r.headers["Location"]
    r = c.post(f"/journal/{wrong[0]}", data={"resolve": "1", "next": "https://evil.example/"})
    assert "/journal" in r.headers["Location"] and "evil" not in r.headers["Location"]
    c.post(page + "/blank-reason", data={"tab": "blank"})
    r = c.post(page + "/practice")
    assert "/bank/" in r.headers["Location"]
    other = login(client(), "student2@monday.kg", "student123")
    assert other.get(page).status_code == 404


def test_scan_fixes_goal_time_skills():
    """Goal follows the exam scale, test time never exceeds the limit, thin skills borrow compilation questions."""
    from monday.models import Attempt, WorkVersion
    from monday.services import student_pool
    c = login(client(), "student11@monday.kg", "student123")
    r = c.post("/profile", data={"action": "profile", "name": "Тест Студент", "exam": "ORT", "goal_score": "900"},
               follow_redirects=True)
    assert "от 0 до 245" in r.data.decode()
    with APP.app_context():
        from monday.models import User
        assert User.query.filter_by(email="student11@monday.kg").first().profile.goal_score != 900
        v = WorkVersion.query.filter(WorkVersion.time_limit_min.isnot(None)).first()
        a = Attempt(user_id=1, mode="collection", work_version=v, duration_sec=v.time_limit_min * 60 + 9999)
        assert a.time_used == v.time_limit_min * 60
        own = [q for q in student_pool("ORT") if "ORT" in (q.exams or [])]
        assert len(student_pool("ORT")) > len(own)
        assert all(q.answer_type != "written" for q in student_pool("ORT"))
    ok(c, "/skills?show=list", contains=["sp-level", "sp-dot", "Глава 1"])


def test_practice_pack_answers_are_consistent():
    """The generated practice pack: every choice key points at an option, every number answer parses, every skill exists."""
    import json
    from monday.models import ContentNode
    from monday.packs import PACK_DIR
    from monday.services import parse_number
    with open(os.path.join(PACK_DIR, "monday_practice_2026.json"), encoding="utf-8") as f:
        qs = json.load(f)["questions"]
    with APP.app_context():
        codes = {n.code for n in ContentNode.query.filter(ContentNode.code.isnot(None))}
    assert len(qs) > 400
    for q in qs:
        assert q["skill"] in codes and q["exams"]
        if q["answer_type"] == "choice":
            assert 0 <= int(q["correct"]) < len(q["options"]) and len(set(q["options"])) == len(q["options"])
        else:
            assert parse_number(q["correct"])[0] is not None, q["id"]


def test_error_report_flow_and_teacher_map():
    """A student flags a question, staff fix it and reply, the student sees the reply once; the map shows gaps."""
    from monday.models import Question, Report
    s = login(client(), "student11@monday.kg", "student123")
    with APP.app_context():
        qid = Question.query.filter_by(status="published").first().id
    r = s.post("/report", data={"question_id": qid, "kind": "typo", "message": "опечатка в условии"},
               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and r.json["ok"]
    assert s.post("/report", data={"question_id": qid, "kind": "other"}, headers={"X-Requested-With": "fetch"}).status_code == 400
    a = login(client(), "admin@monday.kg", "monday2026")
    ok(a, "/teacher/reports", contains=["опечатка в условии", "Исправлено"])
    with APP.app_context():
        rid = Report.query.filter_by(question_id=qid, status="open").first().id
    a.post(f"/teacher/reports/{rid}", data={"action": "fixed", "reply": "Поправили условие"})
    ok(s, "/home", contains=["Поправили условие"])
    s.post(f"/report/{rid}/seen", headers={"X-Requested-With": "fetch"})
    assert "Поправили условие" not in s.get("/home").data.decode()
    t = login(client(), "aibek@monday.kg", "teacher123")
    ok(t, "/teacher/tree?exam=ORT", contains=["Только пробелы", "tm-count"])
    ok(t, "/teacher/tree?exam=SAT&gaps=1")
    ok(t, "/teacher/reports")


def test_custom_session_builder_ladder_hint_retry():
    """«Своя сессия»: ladder picks the next question as you go, hints count as half, retry repeats the mistakes."""
    from monday.models import Attempt, User
    s = login(client(), "student11@monday.kg", "student123")
    ok(s, "/sessions", contains=["Своя сессия", "Лестница", "Сохранить как мой режим"])
    r = s.post("/sessions/custom", data={"minutes": "10", "count": "4", "level": "ladder", "topics": "all", "explain": "now"})
    assert r.status_code == 302 and "/sessions/" in r.headers["Location"]
    url = r.headers["Location"]
    with APP.app_context():
        uid = User.query.filter_by(email="student11@monday.kg").first().id
        att = Attempt.query.filter_by(user_id=uid, mode="custom").order_by(Attempt.id.desc()).first()
        assert len(att.plan) == 1 and att.draft["cfg"]["count"] == 4
    ok(s, url, contains=["Ступень", "Подсказка", "Закончить сессию сейчас"])
    s.post(url, data={"action": "hint"})
    assert "hint-box" in s.get(url).data.decode()
    for _i in range(4):
        s.post(url, data={"action": "answer", "given": "999999"})
        r = s.post(url, data={"action": "next"})
    assert "/done" in r.headers["Location"]
    with APP.app_context():
        att = Attempt.query.filter_by(user_id=uid, mode="custom").order_by(Attempt.id.desc()).first()
        assert att.finished_at and len(att.plan) == 4 and att.answers[0].hint_used
        assert len(set(att.plan)) == 4  # the ladder never repeats a question
        att_id = att.id
    ok(s, f"/sessions/{att_id}/done", contains=["Повторить ошибки", "Лёгкие", "дошёл до ступени"])
    r = s.post(f"/sessions/{att_id}/retry")
    assert r.status_code == 302 and "/sessions/" in r.headers["Location"]
    # explanations at the end: answering moves straight to the next question
    r = s.post("/sessions/custom", data={"minutes": "0", "count": "2", "level": "hard", "topics": "weak", "explain": "end"})
    url = r.headers["Location"]
    s.post(url, data={"action": "answer", "given": "1"})
    r = s.post(url, data={"action": "answer", "given": "1"})
    assert "/done" in r.headers["Location"]
    # presets and the daily goal
    s.post("/sessions/presets", data={"name": "Утро", "minutes": "5", "count": "3", "level": "easy", "topics": "all"})
    ok(s, "/sessions", contains=["Утро"])
    s.post("/sessions/presets", data={"action": "delete", "index": "0"})
    s.post("/goal", data={"minutes": "30", "next": "/home"})
    ok(s, "/home", contains=["из 30 мин сегодня"])

"""Monday formula templates: well-formed content, the two tabs, adding to My formulas and practice links."""
import os

from monday import formulas as fx
from monday.extensions import db
from monday.models import ReferenceSheet, User
from monday.taxonomy import exam_view, keyset
from test_app import APP, client, login, ok
from test_settings import new_student

IMAGES = os.path.join(os.path.dirname(fx.__file__), "static", "img", "formulas")


def sat():
    return [t for t in fx.all_templates() if t["exam"] == "SAT"]


def ort():
    return [t for t in fx.all_templates() if t["exam"] == "ORT"]


def test_sat_templates_are_complete_and_ids_unique():
    blocks = sat()
    assert len(blocks) == 4 and sum(len(t["topics"]) for t in blocks) == 28
    every = [f for t in blocks for f in fx.formulas_of(t)]
    assert len({f["id"] for f in every}) == len(every) and len({f["tex"] for f in every}) == len(every)
    for f in every:
        assert len(f["examples"]) >= 2 and all(e["q"] and e["use"] and e["answer"] for e in f["examples"])
        assert all(e["goal"].startswith("The question asks for ") and e["plan"] and e["steps"] for e in f["examples"])  # explained step by step
        assert all(e[k].replace("\\$", "").count("$") % 2 == 0 for e in f["examples"] for k in ("q", "use", "answer", "goal", "plan", "check") if k in e)  # no half-open maths
        assert not f.get("image") or os.path.exists(os.path.join(IMAGES, f["image"] + ".svg"))


def test_every_topic_practises_a_real_part_of_the_bank():
    with APP.app_context():
        keys = keyset(exam_view(User.query.filter_by(email="student@monday.kg").first(), "SAT"))
    assert all(topic["bank"] in keys for t in sat() for topic in t["topics"])


def test_tabs_and_template_page():
    c, _email = new_student("fxtabs")
    body = ok(c, "/formulas").data.decode()
    assert "От Monday" in body and "SAT · Алгебра" in body and "Новый лист" not in body
    assert "Новый лист" in ok(c, "/formulas?tab=mine").data.decode()
    body = ok(c, "/formulas/t/sat_geometry?topic=volumes").data.decode()
    assert "Цилиндр" in body and "img/formulas/cylinder.svg" in body and "Добавить всю тему" in body
    assert "The question asks for the volume of a cone." in body and "fx-example__steps" in body
    ok(c, "/formulas/t/nothing", status=404)


def test_adding_a_formula_then_a_topic_never_doubles():
    c, email = new_student("fxadd")
    c.post("/formulas/t/sat_algebra/add", data={"topic": "lines", "formula": "slope"})
    c.post("/formulas/t/sat_algebra/add", data={"topic": "lines", "formula": "slope"})
    c.post("/formulas/t/sat_algebra/add", data={"topic": "lines"})
    assert c.post("/formulas/t/sat_algebra/add", data={"topic": "nope"}).status_code == 404
    with APP.app_context():
        sheet = ReferenceSheet.query.filter_by(user_id=User.query.filter_by(email=email).first().id).one()
        assert sheet.title == "Мои формулы SAT" and sheet.exam == "SAT" and len(sheet.entries) == 4
        assert {e.branch for e in sheet.entries} == {"Уравнение прямой"}
    assert "Добавлено 4 из" in ok(c, "/formulas?tab=monday").data.decode()


def test_a_drawing_follows_the_formula_into_my_sheet():
    c, _email = new_student("fximg")
    c.post("/formulas/t/sat_geometry/add", data={"topic": "volumes", "formula": "cone"})
    assert "/static/img/formulas/cone.svg" in ok(c, "/formulas?tab=mine").data.decode()


def test_practice_button_opens_questions():
    c, _email = new_student("fxgo")
    r = c.post("/bank/start", data={"exam": "SAT", "only": "x:geo:area"})
    assert r.status_code == 302 and "/bank/s/" in r.location


def test_my_formulas_open_in_the_bank_pages_view():
    c, _email = new_student("fxpanel")
    c.post("/formulas/t/sat_algebra/add", data={"topic": "distance", "formula": "distance"})
    r = c.post("/bank/start", data={"exam": "SAT", "only": "x:alg:lin2"})
    assert "Мои формулы SAT" in ok(c, r.location).data.decode()



def _sheet(email, **kw):
    u = User.query.filter_by(email=email).first()
    s = ReferenceSheet(user_id=u.id, title=kw.pop("title", "Лист"), **kw)
    db.session.add(s)
    db.session.commit()
    return s.id


def test_a_sheet_shows_only_for_its_exam():
    c, email = new_student("fxexam")
    with APP.app_context():
        _sheet(email, title="Для SAT", exam="SAT")
        _sheet(email, title="Для ОРТ", exam="ORT")
        _sheet(email, title="Общий")
    body = ok(c, c.post("/bank/start", data={"exam": "SAT", "only": "x:alg:lin2"}).location).data.decode()
    assert "Для SAT" in body and "Общий" in body and "Для ОРТ" not in body


def test_section_switches_save_and_stay_the_students_own():
    c, email = new_student("fxplace")
    with APP.app_context():
        sid = _sheet(email, exam="SAT")
    assert c.post(f"/formulas/sheet/{sid}/place", data={"place": "bank"}).status_code == 204
    with APP.app_context():
        s = db.session.get(ReferenceSheet, sid)
        assert not s.is_on("bank") and s.is_on("sessions") and s.is_on("tests")
    body = ok(c, c.post("/bank/start", data={"exam": "SAT", "only": "x:alg:lin2"}).location).data.decode()
    assert 'class="sheet-view is-off"' in body        # still listed, so it can be switched back on from the test
    c.post(f"/formulas/sheet/{sid}/place", data={"place": "sessions"})
    c.post(f"/formulas/sheet/{sid}/place", data={"place": "tests"})
    with APP.app_context():
        assert db.session.get(ReferenceSheet, sid).enabled is False
    c.post(f"/formulas/sheet/{sid}/place", data={"place": "tests", "on": "1"})
    with APP.app_context():
        s = db.session.get(ReferenceSheet, sid)
        assert s.enabled and s.is_on("tests") and not s.is_on("bank")
    assert c.post(f"/formulas/sheet/{sid}/place", data={"place": "nowhere", "on": "1"}).status_code == 404
    other, _e = new_student("fxother")
    assert other.post(f"/formulas/sheet/{sid}/place", data={"place": "bank", "on": "1"}).status_code == 404


def test_monday_tests_never_show_own_formulas():
    from monday.models import Attempt, Work
    c, email = new_student("fxmonday")
    with APP.app_context():
        _sheet(email, title="Шпаргалка")
        work = Work.query.filter_by(kind="monday", status="published").first()
        collection = Work.query.filter_by(kind="collection", status="published", exam="ORT").first()
        u = User.query.filter_by(email=email).first()
        monday = Attempt(user=u, work_version=work.current_version, mode="monday", total=1)
        normal = Attempt(user=u, work_version=collection.current_version, mode="collection", total=1)
        db.session.add_all([monday, normal])
        db.session.commit()
        ids = monday.id, normal.id
    body = ok(c, f"/attempts/{ids[0]}").data.decode()
    assert "Шпаргалка" not in body and "свои формулы выключены" in body
    assert "Шпаргалка" in ok(c, f"/attempts/{ids[1]}").data.decode()


def test_ort_templates_are_complete_and_explained():
    blocks = ort()
    assert len(blocks) == 6 and sum(len(t["topics"]) for t in blocks) >= 30
    every = [f for t in blocks for f in fx.formulas_of(t)]
    assert len(every) >= 80 and len({f["id"] for f in every}) == len(every)
    examples = [e for f in every for e in f["examples"]]
    assert all(len(f["examples"]) >= 2 for f in every) and sum("Колонка А" in e["q"] for e in examples) >= 10
    assert all(e["goal"].startswith("Нужно ") and e["plan"] and e["steps"] and e["use"] and e["answer"] for e in examples)
    assert all(e[k].count("$") % 2 == 0 for e in examples for k in ("q", "plan", "use", "answer"))
    assert all(not f.get("image") or os.path.exists(os.path.join(IMAGES, f["image"] + ".svg")) for f in every)


def test_ort_practice_links_reach_real_bank_topics():
    with APP.app_context():
        keys = keyset(exam_view(User.query.filter_by(email="student@monday.kg").first(), "ORT"))
        assert all(fx.bank_key(topic) in keys for t in ort() for topic in t["topics"])


def test_own_exam_templates_come_first_and_sheets_stay_apart():
    c, email = new_student("fxort")
    body = ok(c, "/formulas?tab=monday").data.decode()
    assert body.index("ОРТ · Алгебра") < body.index("SAT · Алгебра")
    c.post("/formulas/t/sat_geometry/add", data={"topic": "triangles", "formula": "pythagoras"})
    assert "Добавлено" not in ok(c, "/formulas/t/ort_geometry?topic=triangles").data.decode().split('id="f-pythagoras"')[1].split("</article>")[0]
    c.post("/formulas/t/ort_geometry/add", data={"topic": "triangles", "formula": "pythagoras"})
    with APP.app_context():
        titles = {s.title for s in ReferenceSheet.query.filter_by(user_id=User.query.filter_by(email=email).first().id)}
    assert titles == {"Мои формулы SAT", "Мои формулы ОРТ"}


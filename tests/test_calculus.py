"""Calculus I: its topic map, tests and bank option stay apart from the school exams."""
import json
import os

from monday.extensions import db
from monday.models import Attempt, ContentNode, Question, Work
from monday.search import search
from monday.services import parse_number, version_layout
from monday.taxonomy import MASTER
from test_app import APP, client, login, ok

PACK = os.path.join(os.path.dirname(__file__), "..", "monday", "data", "packs", "calculus1_mixed.json")


def pack():
    with open(PACK, encoding="utf-8") as f:
        return json.load(f)


def test_every_question_has_a_valid_skill_and_answer():
    codes = {c for b, _n, subs in MASTER if b == "b-calc1" for _s, _m, skills in subs for c, *_r in skills}
    questions = pack()["questions"]
    assert len(questions) == 46 and {q["skill"] for q in questions} == codes
    assert sum(q["difficulty"] >= 2 for q in questions) == 46  # these are multi-step problems, not drills
    pictures = {q["image"] for q in questions if q.get("image")}
    assert len(pictures) == 5 and all(os.path.exists(os.path.join(PACK[:-5], "figures", p)) for p in pictures)
    for q in questions:
        if q["answer_type"] == "choice":
            assert 0 <= int(q["correct"]) < len(q["options"]) and len(set(q["options"])) == len(q["options"])
        else:
            assert all(parse_number(v)[0] is not None for v in q["correct"].split("|"))


def test_tests_are_published_and_topic_sets_are_thematic():
    with APP.app_context():
        works = Work.query.filter_by(exam="CALC1").all()
        assert len(works) == 12 and all(w.status == "published" for w in works)
        assert sum(w.category == "thematic" for w in works) == 10
        assert all(w.description.startswith("Topics: ") for w in works)
        assert all(version_layout(w.current_version)["format"] == "uni" for w in works)
    c = login(client(), "student@monday.kg", "student123")
    assert "Calculus I · Limits" in ok(c, "/collections?cat=thematic").get_data(as_text=True)
    page = ok(c, "/collections?cat=university").get_data(as_text=True)
    assert "Practice Quiz 1" in page and "Calculus I · Limits" not in page


def test_bank_option_shows_only_calculus_topics():
    c = login(client(), "student@monday.kg", "student123")
    page = ok(c, "/bank/?exam=CALC1").get_data(as_text=True)
    assert 'value="CALC1" checked' in page
    names = [t.split('class="bk-tile__name">')[1].split("<")[0] for t in page.split('class="bank-topic bk-tile')[1:]]
    assert names == ["Calculus I"]
    assert "Теорема о промежуточном значении" in page
    r = c.post("/bank/start", data={"exam": "CALC1"})
    att_id = int(r.location.split("/bank/s/")[1].split("/")[0])
    with APP.app_context():
        assert len(db.session.get(Attempt, att_id).plan) == 67
    sheet = ok(c, r.location).get_data(as_text=True)
    assert "· Calculus I" in sheet


def test_calculus_stays_out_of_school_exams():
    with APP.app_context():
        assert ContentNode.query.filter_by(code="c1_chain").one().exams == ["CALC1"]
        assert all(q.status == "draft" for q in Question.query.filter_by(source="calculus1_mixed").all())
    c = login(client(), "student@monday.kg", "student123")
    assert "Calculus I" not in ok(c, "/bank/?exam=ORT").get_data(as_text=True).split("cb__chips")[-1]


def test_search_finds_it_by_common_names():
    docs = [("c", "Calculus I · Limits (weeks 2–3)", ""), ("o", "ОРТ Математика · Вариант 1", "")]
    for q in ("calculus", "калькулус", "матан", "матанализ"):
        assert search(q, docs)[:1] == ["c"], q


def test_every_test_page_lists_its_topics():
    with APP.app_context():
        ivt = Work.query.filter_by(title="Calculus I · Intermediate Value Theorem").one().id
        ort = Work.query.filter_by(exam="ORT", kind="collection", status="published").first().id
    c = login(client(), "student@monday.kg", "student123")
    assert "Теорема о промежуточном значении" in ok(c, f"/works/{ivt}").get_data(as_text=True)
    assert "<b>Темы:</b>" in ok(c, f"/works/{ort}").get_data(as_text=True)
    cards = ok(c, "/collections?cat=thematic").get_data(as_text=True)
    assert 'class="work-card__topics"' in cards and "bisection steps, fixed points and helper functions</p>" in cards


def test_collections_page_is_ready_for_live_search():
    c = login(client(), "student@monday.kg", "student123")
    page = ok(c, "/collections").get_data(as_text=True)
    assert 'data-live="filters"' in page and 'data-live="results"' in page and "js/collections.js" in page
    found = ok(c, "/collections?q=производная").get_data(as_text=True)
    assert "Calculus I · Derivatives" in found  # a subtopic's name finds the tests inside it
    assert "AMO 2023" not in ok(c, "/collections?q=calculus").get_data(as_text=True)  # "без калькулятора" is not calculus

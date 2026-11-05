"""Olympiad section of the collections and the forgiving search."""
import json
import os

import pytest

from test_app import APP, client, login, ok
from monday.extensions import db
from monday.models import Attempt, Question, Work
from monday.packs import PACK_DIR
from monday.search import search
from monday.services import parse_number, pool_index
from monday.taxonomy import MASTER

TITLES = ["AMO 2025 · 10 класс", "AMO 2024 · 11 класс", "ОРТ Математика · Вариант 1 (Monday)", "ЕГЭ профиль · Вариант 3",
          "Digital SAT Practice Test 2", "CSCA Mathematics Sample", "Логарифмы: тематический тест", "ОГЭ по математике"]
OTHER = {"AMO 2025 · 10 класс": "OLYMP Олимпиада Американская математическая олимпиада 2025",
         "AMO 2024 · 11 класс": "OLYMP Олимпиада Американская математическая олимпиада 2024",
         "ОРТ Математика · Вариант 1 (Monday)": "ORT ОРТ Полный вариант Monday Academy",
         "ЕГЭ профиль · Вариант 3": "EGE ЕГЭ Полный вариант", "Digital SAT Practice Test 2": "SAT Полный вариант",
         "CSCA Mathematics Sample": "CSCA Полный вариант", "Логарифмы: тематический тест": "ORT ОРТ Тематический",
         "ОГЭ по математике": "OGE ОГЭ Тематический"}
DOCS = [(t, t, OTHER[t]) for t in TITLES]


@pytest.mark.parametrize("query,expected", [
    ("олимпиада", "AMO 2025 · 10 класс"),
    ("ОЛИМПИАДА", "AMO 2025 · 10 класс"),
    ("olimpiada", "AMO 2025 · 10 класс"),  # transliteration
    ("olympiad", "AMO 2025 · 10 класс"),
    ("jkbvgbflf", "AMO 2025 · 10 класс"),  # wrong keyboard layout
    ("олимпада", "AMO 2025 · 10 класс"),  # typos
    ("алимпиада", "AMO 2025 · 10 класс"),
    ("олимпиадаа", "AMO 2025 · 10 класс"),
    ("олимпиады", "AMO 2025 · 10 класс"),
    ("олимп", "AMO 2025 · 10 класс"),  # beginning of a word
    ("лимпиа", "AMO 2025 · 10 класс"),  # middle of a word
    ("млмпд", "AMO 2025 · 10 класс"),  # no vowels
    ("амо", "AMO 2025 · 10 класс"),  # Cyrillic for Latin
    ("фьщ", "AMO 2025 · 10 класс"),
    ("10 класс амо", "AMO 2025 · 10 класс"),  # word order
    ("класс 11 amo", "AMO 2024 · 11 класс"),
    ("11кл", "AMO 2024 · 11 класс"),  # glued, short
    ("амо 25", "AMO 2025 · 10 класс"),
    ("одиннадцатый класс олимпиада", "AMO 2024 · 11 класс"),
    ("ort", "ОРТ Математика · Вариант 1 (Monday)"),
    ("орт", "ОРТ Математика · Вариант 1 (Monday)"),
    ("щке", "ОРТ Математика · Вариант 1 (Monday)"),
    ("отр", "ОРТ Математика · Вариант 1 (Monday)"),
    ("ege", "ЕГЭ профиль · Вариант 3"),
    ("егэ вариант 3", "ЕГЭ профиль · Вариант 3"),
    ("егэвариант", "ЕГЭ профиль · Вариант 3"),  # no space
    ("ТЫЕ", None),
    ("сат", "Digital SAT Practice Test 2"),
    ("ыфе", "Digital SAT Practice Test 2"),
    ("цска", "CSCA Mathematics Sample"),
    ("логорифмы", "Логарифмы: тематический тест"),
    ("logarifmy", "Логарифмы: тематический тест"),
    ("kjufhbavs", "Логарифмы: тематический тест"),
    ("матем орт", "ОРТ Математика · Вариант 1 (Monday)"),
    ("орт мatematika", "ОРТ Математика · Вариант 1 (Monday)"),  # Cyrillic and Latin in one word
    ("тест по ogе", "ОГЭ по математике"),
])
def test_strange_queries_find_the_title(query, expected):
    found = search(query, DOCS)
    if expected is None:
        assert "ЕГЭ профиль · Вариант 3" not in found[:1]
    else:
        assert expected in found[:2], found


@pytest.mark.parametrize("query", ["zzzzqq", "холодильник", "12345"])
def test_nonsense_finds_nothing(query):
    assert search(query, DOCS) == []


def test_empty_query_keeps_everything():
    assert search("   ", DOCS) == TITLES


def test_numbers_are_exact():
    assert "AMO 2024 · 11 класс" not in search("amo 10", DOCS)


def test_a_grade_is_not_another_grade():
    assert search("олимпиада 11", DOCS) == ["AMO 2024 · 11 класс"]
    assert search("амо 25", DOCS) == ["AMO 2025 · 10 класс"]


PACKS = {"amo_olympiad_10_11": 149, "amo_olympiad_7_9": 125, "amo_olympiad_6_8": 125}


@pytest.mark.parametrize("pack_id,total", PACKS.items())
def test_amo_pack_is_valid(pack_id, total):
    with open(os.path.join(PACK_DIR, pack_id + ".json"), encoding="utf-8") as f:
        pack = json.load(f)
    codes = {c for _b, _n, subs in MASTER for _s, _m, skills in subs for c, *_r in skills}
    assert pack["bank"] is False
    ids = {q["id"] for q in pack["questions"]}
    assert len(ids) == len(pack["questions"]) == total
    for q in pack["questions"]:
        assert q["skill"] in codes
        if q["answer_type"] == "choice":
            assert 0 <= int(q["correct"]) < len(q["options"]) and len(set(q["options"])) == len(q["options"])
        else:
            assert parse_number(q["correct"].split("|")[0]) is not None
        if q.get("image"):
            assert os.path.exists(os.path.join(PACK_DIR, pack["id"], "figures", q["image"]))
    assert all(set(c["questions"]) <= ids and c["category"] == "olympiad" for c in pack["collections"])
    # a paper keeps all 25 questions; 2024 grade 10 №14 is left out: its formula is lost in the source
    assert all(len(c["questions"]) == (24 if c["id"] == "amo24_g10" else 25) for c in pack["collections"])


def test_olympiads_stay_out_of_practice():
    with APP.app_context():
        qs = Question.query.filter(Question.source.in_(PACKS)).all()
        assert len(qs) == sum(PACKS.values()) and {q.status for q in qs} == {"draft"}
        amo = {q.id for q in qs}
        for exam in ("ORT", "EGE", "ENT", "OGE"):
            assert not amo & {i for i, _s, _d in pool_index(exam)}
        works = Work.query.filter_by(category="olympiad", status="published").all()
        assert len(works) == 16 and {w.exam for w in works} == {"OLYMP"}


def test_collections_page_has_the_olympiad_section():
    c = login(client(), "student@monday.kg", "student123")

    def page(url):
        return ok(c, url).get_data(as_text=True)

    home = page("/collections")
    assert "Олимпиада" in home and "AMO 2025 · 10 класс" in home and "Все олимпиады" in home
    only = page("/collections?cat=olympiad&grade=11")
    assert "AMO 2023 · 11 класс" in only and "AMO 2023 · 10 класс" not in only
    assert "AMO 2025" not in page("/collections?exam=ORT")
    assert "AMO 2024 · 11 класс" in page("/collections?q=jkbvgbflf+11")
    assert "Ничего не нашлось" in page("/collections?q=zzzzqq")


def test_an_olympiad_can_be_taken():
    c = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        work = Work.query.filter_by(title="AMO 2025 · 11 класс").first()
        wid, n = work.id, work.current_version.question_count
    assert n == 25
    ok(c, f"/works/{wid}")
    assert c.post(f"/works/{wid}/start", follow_redirects=True).status_code == 200


def test_olympiad_questions_are_in_the_bank():
    c = login(client(), "student@monday.kg", "student123")
    assert "Олимпиада" in ok(c, "/bank/").get_data(as_text=True)
    page = ok(c, "/bank/?exam=OLYMP&t=number&d=3").get_data(as_text=True)
    assert 'value="OLYMP" checked' in page
    r = c.post("/bank/start", data={"exam": "OLYMP", "t": "number", "d": "3"})
    assert r.status_code == 302 and "/bank/s/" in r.location
    att_id = int(r.location.split("/bank/s/")[1].split("/")[0])
    with APP.app_context():
        att = db.session.get(Attempt, att_id)
        first = db.session.get(Question, att.plan[0])
        assert att.total > 0 and first.source.startswith("amo_olympiad") and first.answer_type == "number" and first.difficulty == 3
        given = first.correct.split("|")[0]
    sheet = ok(c, f"/bank/s/{att_id}/sheet").get_data(as_text=True)
    assert "· Олимпиада" in sheet and "· OLYMP" not in sheet and 'data-split="bank"' in sheet
    assert c.post(f"/bank/s/{att_id}/check", data={"i": "0", "given": given}).get_json()["ok"] is True


def test_the_exam_bank_has_no_olympiad_questions():
    c = login(client(), "student@monday.kg", "student123")
    r = c.post("/bank/start", data={"exam": "ORT"})
    att_id = int(r.location.split("/bank/s/")[1].split("/")[0])
    with APP.app_context():
        plan = db.session.get(Attempt, att_id).plan
        sources = {q.source for q in Question.query.filter(Question.id.in_(plan)).all()}
    assert not any((s or "").startswith("amo_olympiad") for s in sources)


def test_logarithms_have_a_shortcut_in_the_bank():
    c = login(client(), "student@monday.kg", "student123")
    page = ok(c, "/bank/?exam=ORT").get_data(as_text=True)
    assert 'class="bk-featured"' in page and "Логарифмы, показательные уравнения" in page
    key = page.split('class="bk-featured"')[1].split('name="only" value="')[1].split('"')[0]
    r = c.post("/bank/start", data={"exam": "ORT", "only": key})
    att_id = int(r.location.split("/bank/s/")[1].split("/")[0])
    with APP.app_context():
        plan = db.session.get(Attempt, att_id).plan
        codes = {q.skill.code for q in Question.query.filter(Question.id.in_(plan)).all()}
    assert "log_def" in codes and codes <= {"log_def", "log_props", "log_eq", "exp_eq", "log_ineq"}
    assert 'class="bk-featured"' not in ok(c, "/bank/?exam=OGE").get_data(as_text=True)

"""Formula templates prepared by Monday: exam → block → topic → formula with worked examples.

They live in data/formulas/*.json and are read-only, so a fix reaches everyone on the next deploy. Adding a formula
copies it into the student's own sheet, which they can then change without touching the template.
"""
import json
from functools import lru_cache
from pathlib import Path

from flask_babel import lazy_gettext as _l

from .constants import EXAMS
from .extensions import db
from .models import ContentNode, ReferenceSheet, SheetEntry

FOLDER = Path(__file__).parent / "data" / "formulas"
IMAGE_PREFIX = "img:"   # an entry's picture from static/img/formulas rather than from uploads

FORMULA_CATEGORIES = {
    "numbers": _l("Числа и вычисления"),
    "algebra": _l("Алгебра"),
    "functions": _l("Функции"),
    "geometry": _l("Геометрия"),
    "trig": _l("Тригонометрия"),
    "probability": _l("Вероятность и статистика"),
}

TEMPLATE_CATEGORIES = {
    "ort_numbers": ("numbers",),
    "ort_algebra": ("algebra",),
    "ort_functions": ("functions",),
    "ort_geometry": ("geometry",),
    "ort_trig": ("trig",),
    "ort_probability": ("probability",),
    "sat_algebra": ("algebra", "functions"),
    "sat_advanced": ("algebra", "functions", "numbers"),
    "sat_data": ("probability", "numbers"),
    "sat_geometry": ("geometry", "trig"),
    "csca_sets": ("algebra", "numbers"),
    "csca_functions": ("functions", "trig"),
    "csca_geometry": ("geometry", "algebra"),
    "csca_probability": ("probability",),
    "oge_algebra": ("algebra", "numbers", "functions"),
    "oge_real_math": ("numbers",),
    "oge_geometry": ("geometry",),
    "oge_probability": ("probability",),
    "ege_algebra": ("algebra", "numbers", "trig"),
    "ege_equations": ("algebra",),
    "ege_functions": ("functions",),
    "ege_planimetry": ("geometry",),
    "ege_stereometry": ("geometry",),
    "ege_probability": ("probability",),
    "ege_word_finance": ("numbers", "algebra"),
    "ent_numbers": ("numbers", "algebra"),
    "ent_equations": ("algebra",),
    "ent_inequalities": ("algebra",),
    "ent_analysis": ("functions", "algebra"),
    "ent_planimetry": ("geometry", "trig"),
    "ent_stereometry": ("geometry",),
    "ent_literacy": ("numbers", "probability"),
    "trig_formulas": ("trig",),
}


@lru_cache(maxsize=4)
def _load_templates(mtime_ns):
    out = []
    for path in sorted(FOLDER.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out += [{**t, "exam": data["exam"]} for t in data["templates"]]
    return out


def all_templates():
    mtime_ns = max((p.stat().st_mtime_ns for p in FOLDER.glob("*.json")), default=0)
    return _load_templates(mtime_ns)


def templates_for(exam):
    """Every template, the student's own exam first."""
    return sorted(all_templates(), key=lambda t: t["exam"] != exam)


def find_template(template_id):
    return next((t for t in all_templates() if t["id"] == template_id), None)


def formulas_of(template):
    return [f for topic in template["topics"] for f in topic["formulas"]]


def stored(formula):
    return f"${formula['tex']}$"


def added_ids(user, template):
    """Ids of this template's formulas already in the student's sheets for that exam. The same formula can sit on two exams' sheets."""
    have = {e.formula for sheet in ReferenceSheet.query.filter_by(user_id=user.id, exam=template["exam"]) for e in sheet.entries}
    return {f["id"] for f in formulas_of(template) if stored(f) in have}


def sheets_for(user, exam):
    """The sheets that belong with this exam: its own, and those made for no exam in particular."""
    sheets = ReferenceSheet.query.filter_by(user_id=user.id).order_by(ReferenceSheet.position, ReferenceSheet.id).all()
    return [s for s in sheets if not exam or s.exam in (None, "", exam)]


def _own_sheet(user, exam, title):
    sheet = ReferenceSheet.query.filter_by(user_id=user.id, exam=exam, title=title).first()
    if not sheet:
        sheet = ReferenceSheet(user_id=user.id, exam=exam, title=title, position=ReferenceSheet.query.filter_by(user_id=user.id).count())
        db.session.add(sheet)
    return sheet


def add_formulas(user, template, topic, title, formula_id=None):
    """Copies one formula, or the whole topic, into the student's sheet for that exam. Returns how many were new."""
    have = added_ids(user, template)
    fresh = [f for f in topic["formulas"] if f["id"] not in have and formula_id in (None, f["id"])]
    if fresh:
        sheet = _own_sheet(user, template["exam"], title)
        start = len(sheet.entries)
        for n, f in enumerate(fresh):
            db.session.add(SheetEntry(sheet=sheet, branch=topic["name"], topic=f["name"], formula=stored(f), position=start + n,
                                      image_path=IMAGE_PREFIX + f["image"] + ".svg" if f.get("image") else None))
        db.session.commit()
    return len(fresh)


def bank_key(topic):
    """What the bank calls this topic: SAT domains have their own keys, other exams use a skill of the master map."""
    if not topic.get("bank"):
        return ""
    if topic["bank"].startswith("x:"):
        return topic["bank"]
    node = ContentNode.query.filter_by(code=topic["bank"]).first()
    return f"n{node.id}" if node else ""


def exam_name(code):
    return EXAMS[code]["label"] if code in EXAMS else code

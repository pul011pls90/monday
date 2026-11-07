"""Formula templates prepared by Monday: exam → block → topic → formula with worked examples.

They live in data/formulas/*.json and are read-only, so a fix reaches everyone on the next deploy. Adding a formula
copies it into the student's own sheet, which they can then change without touching the template.
"""
import json
from functools import lru_cache
from pathlib import Path

from .constants import EXAMS
from .extensions import db
from .models import ContentNode, ReferenceSheet, SheetEntry

FOLDER = Path(__file__).parent / "data" / "formulas"
IMAGE_PREFIX = "img:"   # an entry's picture from static/img/formulas rather than from uploads


@lru_cache(maxsize=1)
def all_templates():
    out = []
    for path in sorted(FOLDER.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out += [{**t, "exam": data["exam"]} for t in data["templates"]]
    return out


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
    if topic["bank"].startswith("x:"):
        return topic["bank"]
    node = ContentNode.query.filter_by(code=topic["bank"]).first()
    return f"n{node.id}" if node else ""


def exam_name(code):
    return EXAMS[code]["label"] if code in EXAMS else code

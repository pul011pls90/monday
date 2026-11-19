"""Standalone "All Trigonometry" block & pages for Monday formulas.

Independent from the test/compilation formula cards: own data file, own
templates, nothing here reads or writes the SAT / CSCA / test formula data.
"""
import json
import re
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, render_template, request, url_for
from flask_login import login_required

_BASE = Path(__file__).resolve().parent
_DATA_FILE = _BASE / "data" / "trigonometry_formulas.json"
_PHOTO_SUBDIR = "img/trig"

_raw_cache = None

trig_bp = Blueprint("trig_block", __name__)


def _load_raw():
    global _raw_cache
    if _raw_cache is None:
        _raw_cache = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    return _raw_cache


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _photo_url(app_static_folder, card_id):
    for ext in ("svg", "png"):
        path = Path(app_static_folder) / _PHOTO_SUBDIR / f"{card_id}.{ext}"
        if path.exists():
            return url_for("static", filename=f"{_PHOTO_SUBDIR}/{card_id}.{ext}")
    return None


def _math_tex(s):
    """Convert Unicode trig notation to clean KaTeX LaTeX."""
    t = str(s or "")
    for a, b in (
        ("½", r"\frac{1}{2}"),
        ("²", "^2"),
        ("³", "^3"),
        ("ⁿ", "^n"),
        ("′", "'"),
        ("−", "-"),
        ("·", r"\cdot "),
        ("×", r"\times "),
        ("±", r"\pm "),
        ("∓", r"\mp "),
        ("≤", r"\le "),
        ("≥", r"\ge "),
        ("≠", r"\neq "),
        ("⇒", r"\Rightarrow "),
        ("→", r"\to "),
        ("ℝ", r"\mathbb{R}"),
        ("∞", r"\infty "),
        ("π", r"\pi "),
        ("θ", r"\theta "),
        ("φ", r"\varphi "),
        ("°", r"^\circ "),
        ("∫", r"\int "),
        ("lim(x->0)", r"\lim_{x\to 0}"),
    ):
        t = t.replace(a, b)
    t = t.replace("lim(x\\to 0)", r"\lim_{x\to 0}")
    t = re.sub(r"√\(([^()]+)\)", r"\\sqrt{\1}", t)
    t = re.sub(r"√([A-Za-z0-9]+)", r"\\sqrt{\1}", t)
    return t.strip()


def build_trig_block(static_folder):
    """Return {'levels': [...], 'groups': [{'level': {...}, 'branches': [{'id', 'name', 'cards'}]}]}."""
    raw = _load_raw()
    branch_order = raw["branches"]
    groups = []
    for level in raw["levels"]:
        level_cards = [c for c in raw["cards"] if c["level"] == level["id"]]
        branches = []
        for name in branch_order:
            cards = []
            for c in level_cards:
                if c["branch"] == name:
                    card = dict(c)
                    card["photo_url"] = _photo_url(static_folder, c["id"])
                    card["tex_lines"] = [_math_tex(f) for f in c["formulas"]]
                    sol = c["example"]["solution"]
                    steps = [s.strip() for s in re.split(r"(?<=\.)\s+", sol) if s.strip()]
                    card["ex_view"] = {
                        "q": c["example"]["problem"],
                        "goal": c["description"],
                        "use": f"${card['tex_lines'][0]}$" if card["tex_lines"] else "",
                        "steps": steps[:-1] if len(steps) > 1 else steps,
                        "answer": steps[-1] if steps else sol,
                    }
                    cards.append(card)
            if cards:
                branches.append({"id": _slug(name), "name": name, "cards": cards})
        groups.append({
            "level": level,
            "branches": branches,
            "cards_count": sum(len(b["cards"]) for b in branches),
        })
    return {
        "levels": raw["levels"],
        "groups": groups,
        "levels_count": len(raw["levels"]),
        "branches_count": len(raw["branches"]),
        "cards_count": len(raw["cards"]),
    }


@trig_bp.route("/formulas/trigonometry")
@login_required
def trig_sections():
    """Subtopic cards for All Trigonometry (Basic, Intermediate, Calculus 1)."""
    tb = build_trig_block(current_app.static_folder)
    return render_template("student/trig_sections.html", tb=tb)


@trig_bp.route("/formulas/trigonometry/<level_id>")
@login_required
def trig_level(level_id):
    """Topic formulas, diagram, and examples for one trigonometry section."""
    tb = build_trig_block(current_app.static_folder)
    group = next((g for g in tb["groups"] if g["level"]["id"] == level_id), None) or abort(404)
    topic_id = request.args.get("topic")
    branch = next((b for b in group["branches"] if b["id"] == topic_id), group["branches"][0])
    return render_template("student/trig_topic.html", group=group, branch=branch)


@trig_bp.route("/api/trigonometry-formulas")
def trig_api():
    """JSON endpoint."""
    return jsonify(_load_raw())


def init_trig_block(app):
    """Register the blueprint and the `trig_block()` template helper."""
    app.register_blueprint(trig_bp)

    @app.context_processor
    def _inject():
        return {"trig_block": lambda: build_trig_block(app.static_folder)}

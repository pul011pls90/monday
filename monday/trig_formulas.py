"""Standalone "Trigonometry formulas" block for the Monday formulas page.

Independent from the test/compilation formula cards: own data file, own
template partial, own CSS prefix (trig-). Nothing here reads or writes the
SAT / CSCA / test formula data.

Usage:
    from .trig_formulas import init_trig_block
    init_trig_block(app)

In the formulas page template, at the position of the block:
    {% include "_trigonometry_block.html" %}
"""
import json
from pathlib import Path

from flask import Blueprint, jsonify, url_for

_BASE = Path(__file__).resolve().parent
_DATA_FILE = _BASE / "data" / "trigonometry_formulas.json"
_PHOTO_SUBDIR = "img/trig"  # static/img/trig/<card id>.png (optional)

_raw_cache = None

trig_bp = Blueprint("trig_block", __name__)


def _load_raw():
    global _raw_cache
    if _raw_cache is None:
        _raw_cache = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    return _raw_cache


def _photo_url(app_static_folder, card_id):
    path = Path(app_static_folder) / _PHOTO_SUBDIR / f"{card_id}.png"
    if path.exists():
        return url_for("static", filename=f"{_PHOTO_SUBDIR}/{card_id}.png")
    return None


def build_trig_block(static_folder):
    """Return {'levels': [...], 'groups': [{'level': {...}, 'branches': [{'name', 'cards'}]}]}."""
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
                    cards.append(card)
            if cards:
                branches.append({"name": name, "cards": cards})
        groups.append({"level": level, "branches": branches})
    return {"levels": raw["levels"], "groups": groups}


@trig_bp.route("/api/trigonometry-formulas")
def trig_api():
    """JSON endpoint (roadmap / future mobile app can consume it)."""
    return jsonify(_load_raw())


def init_trig_block(app):
    """Register the blueprint and the `trig_block()` template helper."""
    app.register_blueprint(trig_bp)

    @app.context_processor
    def _inject():
        return {"trig_block": lambda: build_trig_block(app.static_folder)}

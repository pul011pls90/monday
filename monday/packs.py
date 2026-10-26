"""Content packs: ready-made questions and collections shipped with the code (monday/data/packs/).

A pack is one JSON file plus a folder of figures with the same name:

    monday/data/packs/<pack>.json
    monday/data/packs/<pack>/figures/*.png

Each question carries its master skill code, text with $…$ LaTeX, options or a numeric answer
(several accepted values are separated by "|"), an explanation and an optional figure.
Each collection lists question ids in order plus its test format (SAT: two 22-question modules, 32 min each).

A pack is imported once (AppMeta remembers it). Figures are copied into the uploads folder, so they come back
whenever the database is rebuilt (e.g. on a fresh Render instance).
"""
import json
import os
import shutil

from flask import current_app

from .extensions import db
from .models import AppMeta, ContentNode, Question, User, Work

PACK_DIR = os.path.join(os.path.dirname(__file__), "data", "packs")


def available():
    if not os.path.isdir(PACK_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(PACK_DIR) if f.endswith(".json"))


def _meta_key(pack_id):
    return f"pack:{pack_id}"[:40]


def is_imported(pack_id):
    return db.session.get(AppMeta, _meta_key(pack_id)) is not None


def _copy_figures(pack_id):
    src = os.path.join(PACK_DIR, pack_id, "figures")
    if not os.path.isdir(src):
        return
    dst = os.path.join(current_app.config["UPLOAD_FOLDER"], "packs", pack_id)
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        target = os.path.join(dst, name)
        if not os.path.exists(target):
            shutil.copyfile(os.path.join(src, name), target)


def _foreign_questions(ids, own_pack, publish, author):
    """Questions a collection borrows from other packs (e.g. a full EGE variant = part 1 pack + part 2 pack).
    The other pack is imported first if needed; its question is matched by text and answer."""
    found = {}
    for other in available():
        if other == own_pack:
            continue
        with open(os.path.join(PACK_DIR, other + ".json"), encoding="utf-8") as f:
            items = {q["id"]: q for q in json.load(f)["questions"]}
        wanted = [k for k in ids if k in items and k not in found]
        if not wanted:
            continue
        import_pack(other, publish=publish, author=author)
        for k in wanted:
            q = Question.query.filter_by(text=items[k]["text"], correct=items[k]["correct"]).order_by(Question.id).first()
            if q:
                found[k] = q
    lost = [k for k in ids if k not in found]
    if lost:
        raise KeyError(f"pack {own_pack}: unknown question ids {lost[:5]}")
    return found


def import_pack(pack_id, publish=True, author=None):
    """Create the pack's questions and collections. Returns (questions, works) created; (0, 0) if already there."""
    _copy_figures(pack_id)
    if is_imported(pack_id):
        return 0, 0
    with open(os.path.join(PACK_DIR, pack_id + ".json"), encoding="utf-8") as f:
        pack = json.load(f)
    if author is None:
        author = User.query.filter_by(role="admin").order_by(User.id).first()
    nodes = {n.code: n for n in ContentNode.query.filter(ContentNode.code.isnot(None)).all()}
    exam = pack.get("exam", "SAT")
    status = "published" if publish else "draft"
    by_key = {}
    for item in pack["questions"]:
        node = nodes.get(item["skill"])
        q = Question(author=author, skill=node, exams=item.get("exams") or [exam], difficulty=item.get("difficulty", 2),
                     language=item.get("language") or pack.get("language", "en"), material=[], text=item["text"],
                     image_path=f"packs/{pack_id}/{item['image']}" if item.get("image") else None,
                     weight=int(item.get("weight") or 1), rubric=item.get("rubric") or None,
                     answer_type=item["answer_type"], options=item.get("options") or [],
                     correct=item["correct"], explanation=item.get("explanation", ""),
                     tags=item.get("tags") or [], status=status, source=pack_id)
        db.session.add(q)
        by_key[item["id"]] = q
    db.session.flush()
    from .services import publish_work
    works = 0
    for c in pack.get("collections", []):
        missing = [k for k in c["questions"] if k not in by_key]
        if missing:
            by_key.update(_foreign_questions(missing, pack_id, publish, author))
        minutes = c.get("minutes_per_module", 32) * (2 if c.get("module_split") else 1)
        category = c.get("category") if c.get("category") in ("full", "thematic") else "full"
        w = Work(author=author, kind="collection", category=category, exam=exam, title=c["title"][:160],
                 description=c.get("description", ""), time_limit_min=minutes, status="draft",
                 draft_question_ids=[by_key[k].id for k in c["questions"]], format=c.get("format", "sat"),
                 calculator=bool(c.get("calculator", True)), module_split=c.get("module_split"))
        db.session.add(w)
        db.session.flush()
        if publish:
            publish_work(w, note=pack.get("title"))
        works += 1
    db.session.add(AppMeta(key=_meta_key(pack_id), value=status))
    db.session.commit()
    return len(by_key), works


def ensure_packs():
    """Import every shipped pack that this database doesn't have yet (runs at start-up)."""
    if not current_app.config.get("IMPORT_PACKS", True):
        return
    if not User.query.filter_by(role="admin").first():
        return  # empty database (reset-db --no-seed): nothing to attach the content to yet
    for pack_id in available():
        import_pack(pack_id, publish=current_app.config.get("PUBLISH_PACKS", True))

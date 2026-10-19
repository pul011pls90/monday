"""Questions in the student's language.

Questions are written in one language (usually Russian). For a student whose interface is in another
language, each question is shown translated — the original is one click away («Показать оригинал»).

Where translations come from, in order:
1. Patterns (monday/data/content_patterns.json): known sentences with numbers and formulas cut out,
   e.g. "Решите уравнение: {0}". A new question in a known shape is translated instantly and exactly.
2. A translation service (MyMemory, free, no key) for anything new. It runs in the background after the
   first view, so the page never waits; the next view shows the translation.
3. Later: a person can correct a translation (source="human"); it is never overwritten.

Formulas ($…$) and numbers never pass through translation: they are cut out first and put back after,
and a translation that lost any of them is thrown away.
"""
import hashlib
import json
import os
import re
import threading
import urllib.parse
import urllib.request

from flask import Blueprint, current_app, g, redirect, request, url_for

bp = Blueprint("content_i18n", __name__)

CONTENT_LANGS = ("ky", "kk", "en")  # languages questions are translated into
ORIG_COOKIE = "orig"

MATH = re.compile(r"\$[^$]*\$")
NUM = re.compile(r"(?<![\w{])-?\d+(?:[.,]\d+)?")
SLOT = re.compile(r"\{(\d+)\}")
LETTERS = re.compile(r"[^\W\d_]")  # any letter of any alphabet
FIELDS_MATERIAL = ("text", "title", "left_title", "right_title", "left", "right")

_patterns = None
_running = set()
_lock = threading.Lock()


# --------------------------------------------------------------------------- pieces


def skeleton(s):
    """'Найдите 15% от числа 240.' → ('Найдите {0}% от числа {1}.', ['15', '240'])."""
    vals = []

    def sub(m):
        vals.append(m.group(0))
        return "{%d}" % (len(vals) - 1)
    return NUM.sub(sub, MATH.sub(sub, s)), vals


def _fill(tpl, vals):
    return SLOT.sub(lambda m: vals[int(m.group(1))] if int(m.group(1)) < len(vals) else m.group(0), tpl)


def _has_words(s):
    return bool(s) and bool(LETTERS.search(MATH.sub("", s)))


def patterns():
    global _patterns
    if _patterns is None:
        path = os.path.join(os.path.dirname(__file__), "data", "content_patterns.json")
        try:
            with open(path, encoding="utf-8") as fh:
                _patterns = json.load(fh)
        except OSError:
            _patterns = {}
    return _patterns


def src_hash(item):
    raw = json.dumps([item.get("text") or "", list(item.get("options") or []), item.get("explanation") or "",
                      list(item.get("material") or [])], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- translating one string


def _from_pattern(s, lang):
    tpl, vals = skeleton(s)
    t = patterns().get(tpl, {}).get(lang)
    return _fill(t, vals) if t else None


def _mymemory(text, src, dst):
    """One call to MyMemory (free, no key; ~500 bytes per call). Returns None on any problem."""
    params = {"q": text, "langpair": f"{src}|{dst}"}
    email = current_app.config.get("TRANSLATE_EMAIL")
    if email:
        params["de"] = email  # raises the free daily limit
    url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 — offline, limit reached, bad answer: keep the original
        return None
    if int(data.get("responseStatus") or 0) != 200:
        return None
    out = (data.get("responseData") or {}).get("translatedText") or ""
    if not out or "MYMEMORY WARNING" in out.upper():
        return None
    return out


def _chunks(text, limit=450):
    """Split by sentences so each piece stays under the service's size limit (bytes)."""
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if cur and len((cur + " " + sent).encode("utf-8")) > limit:
            parts.append(cur)
            cur = sent
        else:
            cur = (cur + " " + sent).strip()
    if cur:
        parts.append(cur)
    return parts


def _machine(s, src, lang):
    tpl, vals = skeleton(s)
    pieces = []
    for part in _chunks(tpl):
        t = _mymemory(part, src, lang)
        if t is None:
            return None
        pieces.append(t)
    out = " ".join(pieces)
    # every formula and number must come back exactly once
    if sorted(SLOT.findall(out)) != sorted(SLOT.findall(tpl)):
        return None
    return _fill(out, vals)


def translate_string(s, src, lang, machine=False):
    """Text in `lang`, or None if it can't be done (yet)."""
    if not _has_words(s):
        return s  # numbers and formulas only
    return _from_pattern(s, lang) or (_machine(s, src, lang) if machine else None)


# --------------------------------------------------------------------------- translating a question


def translate_item(item, src, lang, machine=False):
    """All texts of a question snapshot in `lang`; None if any piece is missing."""
    def tr(s):
        return translate_string(s, src, lang, machine) if s else s
    out = {"text": tr(item.get("text") or ""), "explanation": tr(item.get("explanation") or "")}
    out["options"] = [tr(o) for o in (item.get("options") or [])]
    mats = []
    for b in item.get("material") or []:
        nb = dict(b)
        for f in FIELDS_MATERIAL:
            if b.get(f):
                nb[f] = tr(b[f])
        mats.append(nb)
    out["material"] = mats
    pieces = [out["text"], out["explanation"], *out["options"]] + [b.get(f) for b in mats for f in FIELDS_MATERIAL if f in b]
    if any(p is None for p in pieces):
        return None
    return out


def _save(question_id, lang, h, data, source):
    from .extensions import db
    from .models import ContentTranslation
    row = ContentTranslation.query.filter_by(question_id=question_id, lang=lang).first()
    if row and row.source == "human" and row.src_hash == h:
        return row
    if row is None:
        row = ContentTranslation(question_id=question_id, lang=lang)
        db.session.add(row)
    row.src_hash, row.data, row.source = h, data, source
    db.session.commit()
    return row


def _background(app, question_id, src, lang):
    key = (question_id, lang)
    with _lock:
        if key in _running:
            return
        _running.add(key)

    def work():
        try:
            with app.app_context():
                from .extensions import db
                from .models import Question
                q = db.session.get(Question, question_id)
                if q is None:
                    return
                item = q.snapshot()
                data = translate_item(item, src, lang, machine=True)
                if data is not None:
                    _save(q.id, lang, src_hash(item), data, "machine")
        finally:
            with _lock:
                _running.discard(key)
    threading.Thread(target=work, daemon=True).start()


def _lookup(question_id, lang):
    cache = g.setdefault("_translations", {})
    key = (question_id, lang)
    if key not in cache:
        from .models import ContentTranslation
        cache[key] = ContentTranslation.query.filter_by(question_id=question_id, lang=lang).first()
    return cache[key]


def content_lang():
    from flask_babel import get_locale
    return str(get_locale() or "ru")


def localize(item, lang=None):
    """The snapshot as the current student should see it (a copy; the original is never changed)."""
    if not item or not item.get("question_id"):
        return item
    lang = lang or content_lang()
    src = item.get("language") or "ru"
    if lang == src or lang not in CONTENT_LANGS:
        return item
    h = src_hash(item)
    row = _lookup(item["question_id"], lang)
    data = row.data if row is not None and row.src_hash == h else None
    source = row.source if data else None
    if data is None:
        data = translate_item(item, src, lang)  # instant, from patterns only
        if data is not None:
            _save(item["question_id"], lang, h, data, "pattern")
            source = "pattern"
        elif current_app.config.get("TRANSLATE_ONLINE", True) and not current_app.testing:
            _background(current_app._get_current_object(), item["question_id"], src, lang)
    if data is None:
        return item
    out = dict(item)
    out["_translated"] = source
    if request.cookies.get(ORIG_COOKIE) == "1":
        out["_original_shown"] = True
        return out
    for k in ("text", "explanation", "options", "material"):
        if k in data and data[k] is not None:
            out[k] = data[k]
    if len(out.get("options") or []) != len(item.get("options") or []):
        out["options"] = item.get("options")  # never risk shifting the answer letters
    return out


@bp.route("/prefs/original")
def toggle_original():
    """Switch between the translated and the original question text (remembered in a cookie)."""
    nxt = request.args.get("next") or ""
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = url_for("auth.index")
    resp = redirect(nxt)
    if request.cookies.get(ORIG_COOKIE) == "1":
        resp.delete_cookie(ORIG_COOKIE)
    else:
        resp.set_cookie(ORIG_COOKIE, "1", max_age=60 * 60 * 24 * 365, samesite="Lax")
    return resp

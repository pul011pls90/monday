"""Paste a whole test → questions.

Accepts either
  * JSON (one object or an array) in the parser schema: test_type, question_text, options ["A) …"],
    correct_answer, explanation, topic, difficulty;
  * plain text: numbered questions "1." / "1)", options "А) … Б) …" or "(A) …" on separate lines or in one line,
    an inline "Ответ: Б", and/or an answer key block at the end ("Ответы: 1-Б 2-А 3-12").
Each parsed question gets a guessed skill, a duplicate check against the bank, and a list of problems
so the preview can show what needs fixing.
"""
import difflib
import json
import re

from .models import Question
from .services import parse_number

CYR = "АБВГДЕЖЗ"
LAT = "ABCDEFGH"
EXAM_ALIASES = {"SAT": "SAT", "CSCA": "CSCA", "ORT": "ORT", "ОРТ": "ORT", "EGE": "EGE", "ЕГЭ": "EGE",
                "OGE": "OGE", "ОГЭ": "OGE", "ENT": "ENT", "ЕНТ": "ENT"}
DIFF = {"easy": 1, "лёгкий": 1, "легкий": 1, "1": 1, "medium": 2, "средний": 2, "2": 2,
        "hard": 3, "сложный": 3, "3": 3}
DIAGRAM = re.compile(r"\[requires diagram\]|на рисунке|по рисунку|изображ[её]н|на графике|см\. рис", re.I)

OPT_MARK = re.compile(r"(?:(?<=\s)|^)\(?([A-HА-З])\s?[).]\s+", re.M)
Q_START = re.compile(r"^\s*(?:№\s*)?(\d{1,3})\s*[.)]\s+", re.M)
INLINE_ANS = re.compile(r"(?:^|\s)(?:правильный ответ|ответ|answer)\s*[:\-–]\s*([^\n]+?)\s*$", re.I | re.M)
KEY_HEAD = re.compile(r"^\s*(?:ответы|ключ(?:\s+ответов)?|answer\s*key|answers)\s*[:\-–]?\s*", re.I | re.M)
KEY_ITEM = re.compile(r"(\d{1,3})\s*[-–—.):]?\s*([A-HА-З](?![а-яa-z])|-?\d+(?:[.,/]\d+)?)", re.I)


def _letter_index(s):
    s = (s or "").strip().strip("()").strip().upper()[:1]
    if s in CYR:
        return CYR.index(s)
    if s in LAT:
        return LAT.index(s)
    return None


def _strip_marker(opt):
    return re.sub(r"^\s*\(?[A-HА-З]\s?[).]\s*", "", str(opt)).strip()


def normalize(text):
    """For duplicate checks: lower case, no spaces, no $ and punctuation."""
    return re.sub(r"[\s$.,:;!?«»\"'()\\{}]+", "", (text or "").lower())


# --------------------------------------------------------------------------- parsing


def parse(raw):
    raw = (raw or "").strip()
    if not raw:
        return []
    if raw[0] in "[{":
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        if data is not None:
            return [_from_json(x, i) for i, x in enumerate(data if isinstance(data, list) else [data])]
    return _from_text(raw)


def _from_json(x, i):
    opts = [_strip_marker(o) for o in (x.get("options") or []) if str(o).strip()]
    ans = str(x.get("correct_answer") or "").strip()
    q = {"number": str(x.get("question_number") or i + 1), "text": str(x.get("question_text") or "").strip(),
         "options": opts, "explanation": str(x.get("explanation") or "").strip(),
         "topic": str(x.get("topic") or "").strip(), "difficulty": DIFF.get(str(x.get("difficulty") or "").lower(), 2),
         "exam": EXAM_ALIASES.get(str(x.get("test_type") or "").upper())}
    _set_answer(q, ans)
    return q


def _set_answer(q, ans):
    ans = (ans or "").strip()
    if q["options"]:
        q["answer_type"] = "choice"
        k = _letter_index(ans) if ans and (len(ans) == 1 or re.match(r"^\(?[A-HА-З]\s?[).]", ans)) else None
        if k is None and ans:  # the answer may be written as the option itself
            plain = _strip_marker(ans)
            k = next((i for i, o in enumerate(q["options"]) if normalize(o) == normalize(plain)), None)
        q["correct"] = str(k) if k is not None and k < len(q["options"]) else ""
    else:
        q["answer_type"] = "number"
        q["correct"] = ans


def _answer_key(raw):
    """Answer key block at the end → ({number: answer}, text without the block)."""
    m = KEY_HEAD.search(raw)
    if not m:
        return {}, raw
    block = raw[m.end():]
    key = {int(n): a.strip() for n, a in KEY_ITEM.findall(block)}
    return key, raw[:m.start()]


def _from_text(raw):
    key, body = _answer_key(raw)
    starts = list(Q_START.finditer(body))
    out = []
    for i, m in enumerate(starts):
        chunk = body[m.end(): starts[i + 1].start() if i + 1 < len(starts) else len(body)]
        inline = INLINE_ANS.search(chunk)
        ans = inline.group(1) if inline else ""
        if inline:
            chunk = chunk[:inline.start()] + chunk[inline.end():]
        marks = list(OPT_MARK.finditer(chunk))
        # options must run in order А, Б, В… (otherwise "в)" inside a sentence would split it)
        good, expect = [], 0
        for mk in marks:
            if _letter_index(mk.group(1)) == expect:
                good.append(mk)
                expect += 1
        if len(good) >= 2:
            text = chunk[:good[0].start()].strip()
            options = [chunk[mk.end(): good[j + 1].start() if j + 1 < len(good) else len(chunk)].strip()
                       for j, mk in enumerate(good)]
        else:
            text, options = chunk.strip(), []
        number = int(m.group(1))
        q = {"number": str(number), "text": re.sub(r"\s*\n\s*", " ", text).strip(),
             "options": [re.sub(r"\s*\n\s*", " ", o).strip() for o in options], "explanation": "",
             "topic": "", "difficulty": 2, "exam": None}
        _set_answer(q, ans or key.get(number, ""))
        out.append(q)
    return out


# --------------------------------------------------------------------------- checks


# Words that point to a skill (by its code in the shared map). First match wins, so specific rules go first.
KEYWORDS = [
    (r"(\\log|логарифм).*(уравнен|x\s*\)?\s*=|=.*x)", "log_eq"), (r"\\log|логарифм", "log_props"),
    (r"\\sin|\\cos|\\tg|\\ctg|синус|косинус|тангенс", "trig_values"),
    (r"производн|f'\(", "derivative"), (r"вероятност", "probability"),
    (r"прогресси", "sequences"), (r"колонк[аеи] [аaб]|сравните величин", "compare"),
    (r"среднее арифметическ|медиан", "statistics"), (r"%|процент", "percents"),
    (r"пропорци", "proportions"), (r"площад.*треугольник|треугольник.*площад", "triangle_area"),
    (r"гипотенуз|катет|пифагор", "pythagoras"), (r"окружност|радиус|круг", "circle"),
    (r"объ[её]м", "volumes"), (r"параллелограм|трапеци|ромб|прямоугольник|квадрат[а-я]* со сторон", "quadrilaterals"),
    (r"угл[а-я]* треугольник|градус", "angles"), (r"парабол|вершин[а-я]* парабол", "parabola"),
    (r"област[ья] определения", "domain"), (r"x\^2|x\^\{2\}|квадратн[а-я]* уравнен", "quadratic"),
    (r"систем[а-я]* уравнен", "systems"), (r"неравенств|[<>]|\\le|\\ge", "inequalities"),
    (r"\^\{?x|показательн", "exp_eq"), (r"нок|нод|делит", "divisibility"),
    (r"\\frac|дроб", "fractions"), (r"уравнени", "linear_eq"), (r"\^", "powers_int"),
]


def guess_skill(q, leaves):
    """leaves: [(node, 'Тема → Подтема → Навык')]. Returns node id or None."""
    names = {n.name.lower(): n.id for n, _p in leaves}
    topic = (q.get("topic") or "").lower()
    if topic:
        if topic in names:
            return names[topic]
        close = difflib.get_close_matches(topic, list(names), n=1, cutoff=0.6)
        if close:
            return names[close[0]]
        for name, nid in names.items():
            if name in topic or topic in name:
                return nid
    # no topic: keyword rules over the question text (and options)
    text = " ".join([q.get("text") or ""] + list(q.get("options") or [])).lower()
    codes = {n.code: n.id for n, _p in leaves if n.code}
    for pattern, code in KEYWORDS:
        if code in codes and re.search(pattern, text):
            return codes[code]
    return None


def find_duplicates(questions, bank=None):
    """{index: existing Question} for parsed questions that look almost the same as one in the bank."""
    bank = bank if bank is not None else Question.query.all()
    keyed = [(normalize(b.text), b) for b in bank if b.text]
    dup = {}
    for i, q in enumerate(questions):
        n = normalize(q.get("text"))
        if len(n) < 12:
            continue
        for kn, b in keyed:
            if abs(len(kn) - len(n)) > max(8, len(n) // 5):
                continue
            if kn == n or difflib.SequenceMatcher(None, kn, n).ratio() >= 0.9:
                dup[i] = b
                break
    return dup


def problems(q):
    out = []
    if not q.get("text"):
        out.append("text")
    if q.get("answer_type") == "choice":
        if len(q.get("options") or []) < 2:
            out.append("options")
        if q.get("correct", "") == "":
            out.append("answer")
    else:
        val, _fmt = parse_number(q.get("correct") or "")
        if val is None:
            out.append("answer")
    if DIAGRAM.search(q.get("text") or ""):
        out.append("diagram")
    if not q.get("skill_id"):
        out.append("skill")
    return out

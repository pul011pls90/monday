"""Forgiving search over collection titles, in plain Python so it behaves the same on SQLite and PostgreSQL.

Every word is folded to a rough Latin sound-alike ("олимпиада", "olympiad" and "olimpiada" meet in one form), then
compared by whole word, start of word, part of word, typo distance and consonants only. A query word is also tried in
the other keyboard layout ("jkbvgbflf" is "олимпиада"). A word glued to another ("егэматематика") is split.
The catalogue is a few hundred titles, so scanning it per request costs nothing.
"""
import re
import unicodedata
from functools import lru_cache

_EN = "`qwertyuiop[]asdfghjkl;'zxcvbnm,."
_RU = "ёйцукенгшщзхъфывапролджэячсмитьбю"
_TO_RU = str.maketrans(_EN, _RU)
_TO_EN = str.maketrans(_RU, _EN)

_CYR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "z", "з": "z", "и": "i", "й": "i",
        "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
        "х": "h", "ц": "k", "ч": "c", "ш": "s", "щ": "s", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "iu", "я": "ia",
        "ө": "o", "ү": "u", "ң": "n"}
_LATIN = (("sch", "s"), ("shch", "s"), ("zh", "z"), ("kh", "h"), ("ch", "c"), ("sh", "s"), ("ph", "f"), ("ts", "k"),
          ("yu", "iu"), ("ya", "ia"), ("ju", "iu"), ("ja", "ia"), ("c", "k"), ("q", "k"), ("w", "v"), ("x", "ks"),
          ("y", "i"), ("j", "i"))

# Short or spoken forms. Keys and values are folded on first use, so spelling here doesn't matter.
_ALIASES = {
    "мат": "математика", "матем": "математика", "матеша": "математика", "математика": "математика", "math": "математика",
    "maths": "математика", "матан": "calculus", "матанализ": "calculus", "анализ": "calculus", "вышка": "calculus", "кл": "класс", "grade": "класс", "вар": "вариант", "пробник": "вариант", "пробный": "вариант",
    "variant": "вариант", "олимпка": "олимпиада", "олимпиадный": "олимпиада", "olympiad": "олимпиада", "olymp": "олимпиада",
    "десятый": "10", "десятого": "10", "десятиклассник": "10", "одиннадцатый": "11", "одиннадцатого": "11",
    "одиннадцатиклассник": "11", "x": "10", "xi": "11", "тематика": "тематический", "тема": "тематический",
}
_STOP = {"и", "в", "на", "по", "для", "с", "к", "the", "of", "for", "за", "год", "года", "г", "й", "ый", "ой", "тест", "тесты"}
_PLURALS = ("ами", "ях", "ах", "ов", "ев", "ы", "и", "а", "я", "у", "е", "ом")


def clean(text):
    text = unicodedata.normalize("NFKC", str(text or "")).lower().replace("ё", "е")
    return text


def tokens(text):
    """Words and numbers; letters and digits stuck together come apart ('11кл' → '11', 'кл')."""
    return re.findall(r"\d+|[^\W\d_]+", clean(text))


@lru_cache(maxsize=20000)
def fold(word):
    """A rough Latin spelling shared by Russian, transliterated and English forms; repeated letters collapse."""
    out = "".join(_CYR.get(ch, ch) for ch in word)
    for a, b in _LATIN:
        out = out.replace(a, b)
    return re.sub(r"([^\d])\1+", r"\1", out)


def _bones(folded):
    return re.sub(r"[aeiou]", "", folded)


_ALIAS_FOLDED = {fold(k): tokens(v)[0] for k, v in _ALIASES.items()}


def _distance(a, b, limit):
    """Damerau–Levenshtein distance, stopping early once it passes limit."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            cost = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (ca != cb))
            if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cost = min(cost, prev2[j - 2] + 1)
            row.append(cost)
        if min(row) > limit:
            return limit + 1
        prev2, prev = prev, row
    return prev[-1]


def _allowed(length):
    return 0 if length < 4 else 1 if length < 6 else 2 if length < 10 else 3


def _word_score(q, d):
    """How well a folded query word q fits a folded document word d, 0 to 1."""
    if q == d:
        return 1.0
    if q.isdigit() or d.isdigit():
        # numbers are exact, except a two-digit year: "25" finds 2025
        return 0.8 if len(q) == 2 and len(d) == 4 and d.startswith("20") and d.endswith(q) else 0
    if len(q) >= 2 and d.startswith(q):
        return 0.9
    if len(q) >= 3 and q in d:
        return 0.72
    if len(q) == 3 and len(d) == 3 and sorted(q) == sorted(d):
        return 0.6  # swapped letters in a short name: "отр" for "орт"
    limit = min(_allowed(len(q)), _allowed(len(d)))
    if limit:
        gap = _distance(q, d, limit)
        if gap <= limit:
            return 0.85 - 0.12 * gap
        # the query is the start of a longer word, with a typo: "олимпада" for "олимпиадный"
        if len(d) > len(q) and _distance(q, d[:len(q)], limit) <= limit:
            return 0.55
    qb, db = _bones(q), _bones(d)
    if len(qb) >= 3 and (qb == db or (len(qb) >= 4 and db.startswith(qb))):
        return 0.55  # vowels lost or changed: "млмпд"
    if len(qb) >= 5 and _distance(qb, db, 1) <= 1:
        return 0.52
    return 0


def _best(q, words):
    return max((_word_score(q, d) for d in words), default=0)


def _piece_score(token, words):
    """One typed word against the document, with its alias."""
    f = fold(token)
    alias = _ALIAS_FOLDED.get(f)
    best = _best(f, words)
    if alias:
        best = max(best, _best(fold(alias), words))
    for ending in _PLURALS:  # "олимпиады", "варианты"
        if token.endswith(ending) and len(token) - len(ending) >= 4:
            best = max(best, _best(fold(token[:-len(ending)]), words) * 0.95)
    return best


def _glued(token, words):
    """A word without its space ('егэматематика'): the best split where both halves are found."""
    best = 0
    if len(token) >= 6:
        for cut in range(2, len(token) - 1):
            left, right = _piece_score(token[:cut], words), _piece_score(token[cut:], words)
            if left >= 0.7 and right >= 0.7:
                best = max(best, min(left, right) * 0.9)
    return best


def _spellings(raw):
    """A typed chunk as it stands and in the other keyboard layout, each split into words."""
    low = clean(raw)
    seen, out = set(), []
    for text in (low, low.translate(_TO_RU), low.translate(_TO_EN)):
        parts = tuple(t for t in tokens(text))
        if parts and parts not in seen:
            seen.add(parts)
            out.append(parts)
    return out


def _chunk_score(spellings, words):
    best = 0
    for i, parts in enumerate(spellings):
        scores = [max(_piece_score(p, words), _glued(p, words)) for p in parts]
        useful = [s for p, s in zip(parts, scores) if p not in _STOP or s]
        if useful:
            value = sum(useful) / len(useful) if min(useful) >= 0.5 else 0
            best = max(best, value * (1 if i == 0 else 0.97))
    return best


def _query(q):
    chunks = [c for c in re.split(r"\s+", clean(q).strip()) if c]
    prepared = [(c, _spellings(c)) for c in chunks]
    prepared = [(c, s) for c, s in prepared if s]
    meaningful = [(c, s) for c, s in prepared if not all(p in _STOP for p in s[0])]
    return meaningful or prepared


def search(q, documents):
    """documents: [(item, title, other_text)]. Items best first; every query word must be found.
    If nothing has them all, items with at least half of the words are returned instead."""
    chunks = _query(q)
    if not chunks:
        return [item for item, _t, _o in documents]
    full, partial = [], []
    for n, (item, title, other) in enumerate(documents):
        title_words = {fold(t) for t in tokens(title)}
        all_words = title_words | {fold(t) for t in tokens(other) if not t.isdigit()}  # "25 заданий" is not a year
        scores = []
        for _chunk, spellings in chunks:
            in_title = _chunk_score(spellings, title_words)
            scores.append(max(in_title * 1.15, _chunk_score(spellings, all_words)))
        found = sum(1 for s in scores if s >= 0.5)
        total = sum(scores) / len(scores)
        if found == len(scores):
            full.append((-total, n, item))
        elif found * 2 >= len(scores) and len(scores) > 1:
            partial.append((-total, n, item))
    return [row[2] for row in sorted(full or partial, key=lambda r: r[:2])]

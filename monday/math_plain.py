"""Convert between LaTeX math ($...$) and simple human-friendly notation for teachers."""
from __future__ import annotations

import re

_SYMBOLS_TO_PLAIN = (
    (r"\\leq\b|\\le\b", "≤"),
    (r"\\geq\b|\\ge\b", "≥"),
    (r"\\neq\b|\\ne\b", "≠"),
    (r"\\approx\b", "≈"),
    (r"\\pm\b", "±"),
    (r"\\cdot\b", "·"),
    (r"\\times\b", "×"),
    (r"\\div\b", "÷"),
    (r"\\infty\b", "∞"),
    (r"\\pi\b", "π"),
    (r"\\alpha\b", "α"),
    (r"\\beta\b", "β"),
    (r"\\gamma\b", "γ"),
    (r"\\theta\b", "θ"),
    (r"\^\{\\circ\}|\^\\circ|\\circ\b", "°"),
    (r"\\left\s*\(", "("),
    (r"\\right\s*\)", ")"),
    (r"\\left\s*\[", "["),
    (r"\\right\s*\]", "]"),
    (r"\\(sin|cos|tan|cot|log|ln)\b", r"\1"),
)

_PLAIN_TO_LATEX_MAP = {
    "≤": r"\le ",
    "≥": r"\ge ",
    "≠": r"\neq ",
    "≈": r"\approx ",
    "±": r"\pm ",
    "·": r"\cdot ",
    "×": r"\times ",
    "÷": r"\div ",
    "∞": r"\infty ",
    "π": r"\pi ",
    "α": r"\alpha ",
    "β": r"\beta ",
    "γ": r"\gamma ",
    "θ": r"\theta ",
    "°": r"^{\circ}",
}


def _read_braced(s: str, pos: int) -> tuple[str, int] | None:
    if pos >= len(s) or s[pos] != "{":
        return None
    depth = 0
    start = pos + 1
    i = pos
    while i < len(s):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start:i], i + 1
        i += 1
    return None


def _read_arg(s: str, pos: int) -> tuple[str, int] | None:
    braced = _read_braced(s, pos)
    if braced:
        return braced
    if pos < len(s) and s[pos] not in ("\\", "}", " "):
        return s[pos], pos + 1
    return None


def _replace_fracs_and_roots(expr: str) -> str:
    expr = expr.replace(r"\dfrac", r"\frac").replace(r"\tfrac", r"\frac")
    out = []
    i = 0
    while i < len(expr):
        if expr.startswith(r"\frac", i):
            j = i + 5
            while j < len(expr) and expr[j] == " ":
                j += 1
            num = _read_arg(expr, j)
            if num:
                num_txt, j2 = num
                while j2 < len(expr) and expr[j2] == " ":
                    j2 += 1
                den = _read_arg(expr, j2)
                if den:
                    den_txt, j3 = den
                    num_txt = _replace_fracs_and_roots(num_txt).strip()
                    den_txt = _replace_fracs_and_roots(den_txt).strip()
                    n_wrap = f"({num_txt})" if any(c in num_txt for c in "+- ") else num_txt
                    d_wrap = f"({den_txt})" if any(c in den_txt for c in "+- ") else den_txt
                    out.append(f"{n_wrap}/{d_wrap}")
                    i = j3
                    continue
        if expr.startswith(r"\sqrt", i):
            j = i + 5
            while j < len(expr) and expr[j] == " ":
                j += 1
            arg = _read_arg(expr, j)
            if arg:
                inner, j2 = arg
                inner = _replace_fracs_and_roots(inner).strip()
                if re.fullmatch(r"[A-Za-z0-9]+", inner):
                    out.append(f"√{inner}")
                else:
                    out.append(f"√({inner})")
                i = j2
                continue
        out.append(expr[i])
        i += 1
    return "".join(out)


def _convert_math_chunk_to_plain(chunk: str) -> str:
    s = _replace_fracs_and_roots(chunk)
    for pat, repl in _SYMBOLS_TO_PLAIN:
        s = re.sub(pat, repl, s)
    s = re.sub(r"\^\{([A-Za-z0-9])\}", r"^\1", s)
    s = re.sub(r"\^\{([^}]+)\}", r"^(\1)", s)
    s = re.sub(r"_\{([A-Za-z0-9])\}", r"_\1", s)
    s = re.sub(r"_\{([^}]+)\}", r"_(\1)", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def latex_to_plain(text: str | None) -> str:
    """Convert a LaTeX-mixed string into simple readable notation without $ or \\frac."""
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"\$\$(.+?)\$\$", lambda m: _convert_math_chunk_to_plain(m.group(1)), s, flags=re.S)
    s = re.sub(r"\$(.+?)\$", lambda m: _convert_math_chunk_to_plain(m.group(1)), s, flags=re.S)
    return s


def _convert_plain_math_to_latex(expr: str) -> str:
    s = expr.strip()
    # Parenthesized or simple fractions: (a+b)/(c+d) or 1/2
    s = re.sub(
        r"\(([^()]+)\)\s*/\s*\(([^()]+)\)",
        lambda m: f"\\frac{{{m.group(1).strip()}}}{{{m.group(2).strip()}}}",
        s,
    )
    s = re.sub(
        r"\(([^()]+)\)\s*/\s*([A-Za-z0-9]+)",
        lambda m: f"\\frac{{{m.group(1).strip()}}}{{{m.group(2).strip()}}}",
        s,
    )
    s = re.sub(
        r"([A-Za-z0-9]+)\s*/\s*\(([^()]+)\)",
        lambda m: f"\\frac{{{m.group(1).strip()}}}{{{m.group(2).strip()}}}",
        s,
    )
    s = re.sub(
        r"(?<![A-Za-z0-9_\\])([A-Za-z0-9]+)\s*/\s*([A-Za-z0-9]+)",
        lambda m: f"\\frac{{{m.group(1)}}}{{{m.group(2)}}}",
        s,
    )
    # Roots: √(x+1) or √3
    s = re.sub(r"√\s*\(([^()]+)\)", lambda m: f"\\sqrt{{{m.group(1).strip()}}}", s)
    s = re.sub(r"√\s*([A-Za-z0-9]+)", lambda m: f"\\sqrt{{{m.group(1)}}}", s)
    # Powers and subscripts: ^(2n) or ^2
    s = re.sub(r"\^\(([^()]+)\)", lambda m: f"^{{{m.group(1).strip()}}}", s)
    s = re.sub(r"\^([A-Za-z0-9]+)", lambda m: f"^{{{m.group(1)}}}", s)
    s = re.sub(r"_\(([^()]+)\)", lambda m: f"_{{{m.group(1).strip()}}}", s)
    s = re.sub(r"_([A-Za-z0-9]+)", lambda m: f"_{{{m.group(1)}}}", s)
    for sym, tex in _PLAIN_TO_LATEX_MAP.items():
        s = s.replace(sym, tex)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_MATH_HINT_RE = re.compile(r"(\d+\s*/\s*\d+|[A-Za-z0-9]\s*/\s*[A-Za-z0-9]|√|\^|_|[≤≥≠≈±·×÷∞παβγθ°])")
_PROSE_MATH_SPAN_RE = re.compile(
    r"(?:(?<![А-Яа-яЁёA-Za-z0-9_])(?:\(?[A-Za-z0-9√][A-Za-z0-9√\^_°παβγθ]*\)?(?:\s*(?:[+\-*/=<>≤≥≠≈±·×÷])\s*\(?[A-Za-z0-9√][A-Za-z0-9√\^_°παβγθ]*\)?)+|[A-Za-z0-9]+/[A-Za-z0-9]+|√\([^()]+\)|√[A-Za-z0-9]+|[A-Za-z0-9]+\^\([^()]+\)|[A-Za-z0-9]+\^[A-Za-z0-9]+|[≤≥≠≈±∞παβγθ°]+))"
)


def plain_to_latex(text: str | None, *, is_option: bool = False) -> str:
    """Convert teacher's simple math notation back to $...$ LaTeX for KaTeX rendering."""
    if not text:
        return ""
    s = str(text).strip()
    if "$" in s:
        return s

    if is_option:
        if _MATH_HINT_RE.search(s):
            return f"${_convert_plain_math_to_latex(s)}$"
        return s

    def _repl(match):
        span = match.group(0).strip()
        if not _MATH_HINT_RE.search(span) and "=" not in span and not re.search(r"[+\-*/]", span):
            return span
        # Don't wrap plain hyphenated words or standalone punctuation
        if re.fullmatch(r"\d+", span):
            return span
        return f"${_convert_plain_math_to_latex(span)}$"

    return _PROSE_MATH_SPAN_RE.sub(_repl, s)

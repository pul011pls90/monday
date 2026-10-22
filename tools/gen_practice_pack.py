"""Generate the Monday practice pack: harder questions for skills that have few of them.

Every answer is computed here (never typed by hand), so the key and the explanation always agree.
Run:  python tools/gen_practice_pack.py   → monday/data/packs/monday_practice_2026.json
"""
import json
import math
import os
import random
from fractions import Fraction as F

OUT = os.path.join(os.path.dirname(__file__), "..", "monday", "data", "packs", "monday_practice_2026.json")
LANG = "ru"


def L(ru, en):
    return ru if LANG == "ru" else en


def fr(x):
    """LaTeX for a Fraction / int."""
    x = F(x)
    if x.denominator == 1:
        return str(x.numerator)
    s = "-" if x < 0 else ""
    return f"{s}\\frac{{{abs(x.numerator)}}}{{{x.denominator}}}"


def num(x):
    """Plain answer string for a number (exact)."""
    x = F(x)
    if x.denominator == 1:
        return str(x.numerator)
    d = x.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d == 1:
        return str(float(x)).rstrip("0").rstrip(".")
    return f"{x.numerator}/{x.denominator}"


def dec(x):
    s = num(x)
    return s.replace(".", ",") if LANG == "ru" else s


def choice(r, right, wrong, explanation, text, difficulty=3, math_opts=True):
    opts = [right]
    for w in wrong:
        if w not in opts:
            opts.append(w)
    opts = opts[:4]
    r.shuffle(opts)
    return {"text": text, "answer_type": "choice", "options": [f"${o}$" if math_opts else o for o in opts],
            "correct": str(opts.index(right)), "explanation": explanation, "difficulty": difficulty}


def number(answer, explanation, text, difficulty=3):
    return {"text": text, "answer_type": "number", "correct": answer, "explanation": explanation, "difficulty": difficulty}


_ALL = []  # (skill code, (template, languages)); several templates per skill are allowed


def tpl(code, langs=("ru", "en")):
    def wrap(fn):
        _ALL.append((code, (fn, langs)))
        return fn
    return wrap


# ------------------------------------------------------------------ arithmetic

@tpl("fractions")
def _(r):
    a, b, c, d = r.choice([(2, 3), (3, 4), (5, 6), (4, 9)]), r.choice([(1, 6), (5, 12), (7, 18)]), r.choice([(3, 5), (2, 7)]), r.choice([(1, 4), (3, 8)])
    x = (F(*a) - F(*b)) / F(*c) + F(*d)
    return number(num(x), L(
        f"Сначала вычитание: ${fr(F(*a))} - {fr(F(*b))} = {fr(F(*a) - F(*b))}$. Деление на ${fr(F(*c))}$ — умножение на ${fr(1 / F(*c))}$: ${fr((F(*a) - F(*b)) / F(*c))}$. Прибавляем ${fr(F(*d))}$ и получаем ${fr(x)}$.",
        f"Subtract first: ${fr(F(*a))} - {fr(F(*b))} = {fr(F(*a) - F(*b))}$. Dividing by ${fr(F(*c))}$ means multiplying by ${fr(1 / F(*c))}$: ${fr((F(*a) - F(*b)) / F(*c))}$. Add ${fr(F(*d))}$ to get ${fr(x)}$."),
        L(f"Вычислите: $\\left({fr(F(*a))} - {fr(F(*b))}\\right) : {fr(F(*c))} + {fr(F(*d))}$. Ответ запишите обыкновенной или десятичной дробью.",
          f"Evaluate $\\left({fr(F(*a))} - {fr(F(*b))}\\right) \\div {fr(F(*c))} + {fr(F(*d))}$. Give the answer as a fraction or a decimal."))


@tpl("percents", ("ru",))
def _(r):
    p, q = r.choice([10, 20, 25, 30, 40]), r.choice([10, 20, 25, 50])
    up = r.random() < .5
    k = (1 + F(p, 100)) * (1 - F(q, 100)) if up else (1 - F(p, 100)) * (1 + F(q, 100))
    ch = (k - 1) * 100
    return number(num(ch), L(
        f"Пусть цена 1. После изменений: ${dec(1 + F(p, 100) if up else 1 - F(p, 100))} \\cdot {dec(1 - F(q, 100) if up else 1 + F(q, 100))} = {dec(k)}$. Изменение: $({dec(k)} - 1) \\cdot 100\\% = {dec(ch)}\\%$.", ""),
        L(f"Цену товара сначала {'повысили' if up else 'снизили'} на ${p}\\%$, затем {'снизили' if up else 'повысили'} на ${q}\\%$. На сколько процентов изменилась цена по сравнению с первоначальной? (Повышение — положительное число, снижение — отрицательное.)", ""))


@tpl("proportions")
def _(r):
    a, b, c = r.choice([(2, 3, 5), (3, 4, 5), (1, 2, 4), (3, 5, 7)])
    k = r.choice([4, 6, 8, 12])
    total = (a + b + c) * k
    diff = (c - a) * k
    return number(str(total), L(
        f"Части $ {a}x, {b}x, {c}x$. Разность наибольшей и наименьшей: ${c - a}x = {diff}$, $x = {k}$. Сумма: ${a + b + c} \\cdot {k} = {total}$.",
        f"Let the parts be ${a}x, {b}x, {c}x$. The difference of the largest and smallest is ${c - a}x = {diff}$, so $x = {k}$. The total is ${a + b + c} \\cdot {k} = {total}$."),
        L(f"Число разделили на три части в отношении ${a} : {b} : {c}$. Наибольшая часть больше наименьшей на ${diff}$. Найдите исходное число.",
          f"A number is split into three parts in the ratio ${a} : {b} : {c}$. The largest part exceeds the smallest by ${diff}$. Find the number."))


@tpl("abs_value")
def _(r):
    a, b = r.choice([(2, 5), (3, 7), (1, 4), (4, 9)])
    x = r.choice([-3, -2, 0, 1, 6])
    v = abs(x - a) + abs(x - b) - abs(x)
    return number(str(v), L(
        f"Подставляем $x = {x}$: $|{x} - {a}| + |{x} - {b}| - |{x}| = {abs(x - a)} + {abs(x - b)} - {abs(x)} = {v}$.",
        f"Substitute $x = {x}$: $|{x} - {a}| + |{x} - {b}| - |{x}| = {abs(x - a)} + {abs(x - b)} - {abs(x)} = {v}$."),
        L(f"Найдите значение выражения $|x - {a}| + |x - {b}| - |x|$ при $x = {x}$.", f"Find $|x - {a}| + |x - {b}| - |x|$ for $x = {x}$."))


@tpl("abs_value", ("ru",))
def _abs2(r):
    a = r.choice([2, 3, 4, 5])
    b = r.choice([7, 8, 9])
    # minimum of |x-a|+|x-b| is b-a on [a,b]
    return number(str(b - a), L(
        f"$|x-{a}|+|x-{b}|$ — сумма расстояний от $x$ до точек ${a}$ и ${b}$ на числовой прямой. Она наименьшая для $x$ между ними и равна ${b} - {a} = {b - a}$.", ""),
        L(f"Найдите наименьшее значение выражения $|x - {a}| + |x - {b}|$.", ""))


@tpl("rounding", ("ru",))
def _(r):
    a, b, c = r.choice([(48, 12, 3), (36, 8, 2), (64, 16, 4)])
    d = r.choice([2, 3, 5])
    v = F(a, b // c) + d ** 2 - F(a - b, c)
    return number(num(v), f"Сначала скобки: ${b} : {c} = {b // c}$ и ${a} - {b} = {a - b}$. Затем: ${a} : {b // c} = {fr(F(a, b // c))}$, ${d}^2 = {d * d}$, ${a - b} : {c} = {fr(F(a - b, c))}$. Итог: ${fr(v)}$.",
                  f"Вычислите: ${a} : ({b} : {c}) + {d}^2 - ({a} - {b}) : {c}$.")


@tpl("divisibility", ("ru",))
def _(r):
    a, b = r.choice([(84, 126), (90, 150), (72, 120), (168, 252), (96, 144)])
    g, l = math.gcd(a, b), a * b // math.gcd(a, b)
    return number(str(l // g), L(
        f"${a}$ и ${b}$: НОД $= {g}$, НОК $= \\frac{{{a} \\cdot {b}}}{{{g}}} = {l}$. Отношение: ${l} : {g} = {l // g}$.", ""),
        L(f"Найдите, во сколько раз НОК чисел ${a}$ и ${b}$ больше их НОД.", ""))


@tpl("primes", ("ru",))
def _(r):
    n = r.choice([360, 504, 720, 1260, 600])
    f, m, p = {}, n, 2
    while m > 1:
        while m % p == 0:
            f[p] = f.get(p, 0) + 1
            m //= p
        p += 1
    cnt = 1
    for e in f.values():
        cnt *= e + 1
    fac = " \\cdot ".join(f"{p}^{{{e}}}" if e > 1 else str(p) for p, e in f.items())
    prod = " \\cdot ".join(f"({e}+1)" for e in f.values())
    return number(str(cnt), L(
        f"${n} = {fac}$. Число делителей: ${prod} = {cnt}$.", ""),
        L(f"Сколько натуральных делителей у числа ${n}$ (включая $1$ и само число)?", ""))


@tpl("powers_int", ("en",))
def _(r):
    a, m, n = r.choice([(2, 5, 3), (3, 4, 2), (5, 3, 2)])
    k = r.choice([2, 3])
    e = m * k - n
    return choice(r, f"{a}^{{{e}}}", [f"{a}^{{{m + k - n}}}", f"{a}^{{{m * k + n}}}", f"{a}^{{{m - n}}}"],
                  f"$(a^m)^k = a^{{mk}}$, so the numerator is ${a}^{{{m * k}}}$. Dividing subtracts exponents: ${a}^{{{m * k} - {n}}} = {a}^{{{e}}}$.",
                  f"Which expression is equivalent to $\\dfrac{{({a}^{{{m}}})^{{{k}}}}}{{{a}^{{{n}}}}}$?")


@tpl("powers_frac", ("en",))
def _(r):
    b, p, q = r.choice([(8, 2, 3), (27, 2, 3), (16, 3, 4), (32, 3, 5)])
    root = round(b ** (1 / q))
    v = root ** p
    return number(str(v), f"${b}^{{{p}/{q}}} = (\\sqrt[{q}]{{{b}}})^{p} = {root}^{p} = {v}$.",
                  f"What is the value of ${b}^{{\\frac{{{p}}}{{{q}}}}}$?")


@tpl("radicals", ("en",))
def _(r):
    a, b = r.choice([(2, 3), (3, 2), (5, 2)])
    s = a * a * b
    k = r.choice([2, 3])
    return choice(r, f"{a * (k + 1)}\\sqrt{{{b}}}", [f"{a + k}\\sqrt{{{b}}}", f"\\sqrt{{{s + k * k * b}}}", f"{a * k}\\sqrt{{{b}}}"],
                  f"$\\sqrt{{{s}}} = \\sqrt{{{a * a} \\cdot {b}}} = {a}\\sqrt{{{b}}}$ and $\\sqrt{{{k * k * a * a * b}}} = {k * a}\\sqrt{{{b}}}$. Sum: ${a * (k + 1)}\\sqrt{{{b}}}$.",
                  f"Which is equivalent to $\\sqrt{{{s}}} + \\sqrt{{{k * k * a * a * b}}}$?")


@tpl("sci_notation")
def _(r):
    (m1, e1), (m2, e2) = r.choice([((4.8, 7), (1.2, 3)), ((6.3, 9), (2.1, 4)), ((7.2, 8), (3.6, 2)), ((2.4, 6), (4.8, 2)), ((1.5, 5), (6, 9))])
    q = F(str(m1)) / F(str(m2))
    e = e1 - e2
    while q < 1:
        q *= 10
        e -= 1
    return choice(r, f"{dec(q)} \\cdot 10^{{{e}}}", [f"{dec(q)} \\cdot 10^{{{e + 1}}}", f"{dec(q)} \\cdot 10^{{{e - 1}}}", f"{dec(q)} \\cdot 10^{{{e1 + e2}}}"],
                  L(f"Делим мантиссы: ${dec(F(str(m1)))} : {dec(F(str(m2)))} = {dec(F(str(m1)) / F(str(m2)))}$, порядки вычитаются: $10^{{{e1} - {e2}}}$. В стандартном виде: ${dec(q)} \\cdot 10^{{{e}}}$.",
                    f"Divide the leading parts: ${m1} / {m2} = {dec(F(str(m1)) / F(str(m2)))}$ and subtract the exponents: $10^{{{e1} - {e2}}}$. In scientific notation: ${dec(q)} \\cdot 10^{{{e}}}$."),
                  L(f"Запишите в стандартном виде частное $\\dfrac{{{dec(F(str(m1)))} \\cdot 10^{{{e1}}}}}{{{dec(F(str(m2)))} \\cdot 10^{{{e2}}}}}$.",
                    f"Write $\\dfrac{{{m1} \\times 10^{{{e1}}}}}{{{m2} \\times 10^{{{e2}}}}}$ in scientific notation."))


# ------------------------------------------------------------------ sequences

@tpl("sequences")
def _(r):
    a1, d = r.choice([3, 5, 7, -4]), r.choice([4, 6, -3])
    m, n = r.choice([(4, 11), (5, 13), (3, 10)])
    am, an = a1 + (m - 1) * d, a1 + (n - 1) * d
    k = r.choice([20, 25, 30])
    ak = a1 + (k - 1) * d
    return number(str(ak), L(
        f"$a_{{{n}}} - a_{{{m}}} = {n - m}d = {an - am}$, значит $d = {d}$. $a_1 = a_{{{m}}} - {m - 1}d = {a1}$. $a_{{{k}}} = a_1 + {k - 1}d = {ak}$.",
        f"$a_{{{n}}} - a_{{{m}}} = {n - m}d = {an - am}$, so $d = {d}$. Then $a_1 = a_{{{m}}} - {m - 1}d = {a1}$ and $a_{{{k}}} = a_1 + {k - 1}d = {ak}$."),
        L(f"В арифметической прогрессии $a_{{{m}}} = {am}$, $a_{{{n}}} = {an}$. Найдите $a_{{{k}}}$.",
          f"In an arithmetic sequence, $a_{{{m}}} = {am}$ and $a_{{{n}}} = {an}$. What is $a_{{{k}}}$?"))


@tpl("sequences", ("ru",))
def _seq2(r):
    b1, q = r.choice([2, 3, 5]), r.choice([2, 3, -2])
    b3, b6 = b1 * q ** 2, b1 * q ** 5
    return number(str(b1 * q ** 4), L(
        f"$\\frac{{b_6}}{{b_3}} = q^3 = {fr(F(b6, b3))}$, значит $q = {q}$. $b_5 = b_3 \\cdot q^2 = {b3} \\cdot {q * q} = {b1 * q ** 4}$.", ""),
        L(f"В геометрической прогрессии $b_3 = {b3}$, $b_6 = {b6}$. Найдите $b_5$.", ""))


@tpl("series_sum", ("ru",))
def _(r):
    a1, d, n = r.choice([(2, 3, 20), (5, 4, 15), (-7, 3, 18)])
    s = n * (2 * a1 + (n - 1) * d) // 2
    return number(str(s), L(
        f"$S_n = \\frac{{2a_1 + (n-1)d}}{{2}} \\cdot n = \\frac{{2 \\cdot {a1} + {n - 1} \\cdot {d}}}{{2}} \\cdot {n} = {s}$.", ""),
        L(f"Найдите сумму первых ${n}$ членов арифметической прогрессии, если $a_1 = {a1}$, $d = {d}$.", ""))


@tpl("series_sum", ("ru",))
def _ser2(r):
    b1, q = r.choice([(24, F(1, 2)), (54, F(1, 3)), (36, F(-1, 2))])
    s = F(b1) / (1 - q)
    return number(num(s), L(
        f"$|q| < 1$, поэтому $S = \\frac{{b_1}}{{1 - q}} = \\frac{{{b1}}}{{1 - ({fr(q)})}} = {fr(s)}$.", ""),
        L(f"Найдите сумму бесконечно убывающей геометрической прогрессии с $b_1 = {b1}$ и $q = {fr(q)}$.", ""))


# ------------------------------------------------------------------ algebra

@tpl("identities")
def _(r):
    a, b = r.choice([(7, 3), (9, 4), (11, 5)])
    s, p = a + b, a * b
    return number(str(s * s - 2 * p), L(
        f"$x^2 + y^2 = (x + y)^2 - 2xy = {s}^2 - 2 \\cdot {p} = {s * s - 2 * p}$.",
        f"$x^2 + y^2 = (x + y)^2 - 2xy = {s}^2 - 2 \\cdot {p} = {s * s - 2 * p}$."),
        L(f"Известно, что $x + y = {s}$ и $xy = {p}$. Найдите $x^2 + y^2$.", f"If $x + y = {s}$ and $xy = {p}$, what is $x^2 + y^2$?"))


@tpl("identities", ("ru",))
def _id2(r):
    a = r.choice([97, 103, 998, 1002])
    b = a - (100 if a < 500 else 1000)
    return number(str(a * a), L(
        f"${a}^2 = ({a - b} {'+' if b > 0 else '-'} {abs(b)})^2 = {(a - b) ** 2} {'+' if b > 0 else '-'} {2 * (a - b) * abs(b)} + {b * b} = {a * a}$.", ""),
        L(f"Вычислите ${a}^2$, используя формулу квадрата суммы или разности.", ""))


@tpl("poly_ops", ("ru",))
def _(r):
    p, q = r.choice([(2, 3), (1, 5), (3, 4), (2, 7)])
    # x^3 - (p+q)x^2 + pq x ... factor x(x-p)(x-q); ask sum of roots
    return number(str(p + q), L(
        f"$x^3 - {p + q}x^2 + {p * q}x = x(x^2 - {p + q}x + {p * q}) = x(x - {p})(x - {q})$. Корни: $0, {p}, {q}$; сумма ${p + q}$.", ""),
        L(f"Разложите на множители и найдите сумму корней уравнения $x^3 - {p + q}x^2 + {p * q}x = 0$.", ""))


@tpl("poly_ops", ("ru",))
def _poly2(r):
    a = r.choice([2, 3, -1, -2])
    c = r.choice([5, -4, 7])
    # remainder of x^3 + c x - 3 divided by (x - a)
    rem = a ** 3 + c * a - 3
    return number(str(rem), L(
        f"По теореме Безу остаток от деления на $x {'-' if a > 0 else '+'} {abs(a)}$ равен $P({a}) = ({a})^3 + ({c}) \\cdot ({a}) - 3 = {rem}$.", ""),
        L(f"Найдите остаток от деления многочлена $P(x) = x^3 {'+' if c > 0 else '-'} {abs(c)}x - 3$ на $x {'-' if a > 0 else '+'} {abs(a)}$.", ""))


@tpl("rational_expr")
def _(r):
    a = r.choice([2, 3, 4, 5])
    x = r.choice([7, 9, 11])
    # (x^2 - a^2)/(x^2 + a x) = (x-a)/x
    v = F(x - a, x)
    return number(num(v), L(
        f"$\\frac{{x^2 - {a * a}}}{{x^2 + {a}x}} = \\frac{{(x - {a})(x + {a})}}{{x(x + {a})}} = \\frac{{x - {a}}}{{x}}$. При $x = {x}$: ${fr(v)}$.",
        f"$\\frac{{x^2 - {a * a}}}{{x^2 + {a}x}} = \\frac{{(x - {a})(x + {a})}}{{x(x + {a})}} = \\frac{{x - {a}}}{{x}}$. For $x = {x}$: ${fr(v)}$."),
        L(f"Упростите и найдите значение выражения $\\dfrac{{x^2 - {a * a}}}{{x^2 + {a}x}}$ при $x = {x}$.",
          f"Simplify $\\dfrac{{x^2 - {a * a}}}{{x^2 + {a}x}}$ and evaluate it at $x = {x}$."))


@tpl("linear_eq", ("ru",))
def _(r):
    a, b, c, d = r.choice([(3, 2, 4, 5), (5, 3, 2, 7), (2, 5, 3, 4)])
    x = r.choice([-2, 3, 6])
    # (x + a)/b - (x - c)/d = k
    k = F(x + a, b) - F(x - c, d)
    return number(str(x), L(
        f"Умножаем на ${b * d}$: ${d}(x + {a}) - {b}(x - {c}) = {fr(k * b * d)}$, ${d - b}x + {d * a + b * c} = {fr(k * b * d)}$, $x = {x}$.", ""),
        L(f"Решите уравнение $\\dfrac{{x + {a}}}{{{b}}} - \\dfrac{{x - {c}}}{{{d}}} = {fr(k)}$.", ""))


@tpl("quadratic", ("en",))
def _(r):
    p, q = r.choice([(-3, 5), (2, 7), (-4, -1), (1, 6)])
    a = r.choice([1, 2])
    b, c = -a * (p + q), a * p * q
    return number(str(max(p, q) - min(p, q)), f"${a if a > 1 else ""}x^2 {'+' if b >= 0 else '-'} {abs(b)}x {'+' if c >= 0 else '-'} {abs(c)} = {a}(x - ({p}))(x - ({q}))$, so the solutions are ${p}$ and ${q}$. Their positive difference is ${abs(p - q)}$.",
                  f"What is the positive difference between the solutions of ${a if a > 1 else ''}x^2 {'+' if b >= 0 else '-'} {abs(b)}x {'+' if c >= 0 else '-'} {abs(c)} = 0$?")


@tpl("vieta", ("ru",))
def _(r):
    p, q = r.choice([(2, 5), (-3, 4), (1, 6), (-2, -7)])
    s, m = p + q, p * q
    v = F(1, p) + F(1, q)
    return number(num(v), L(
        f"По теореме Виета $x_1 + x_2 = {s}$, $x_1 x_2 = {m}$. $\\frac{{1}}{{x_1}} + \\frac{{1}}{{x_2}} = \\frac{{x_1 + x_2}}{{x_1 x_2}} = {fr(v)}$.", ""),
        L(f"Не решая уравнение $x^2 {'-' if s >= 0 else '+'} {abs(s)}x {'+' if m >= 0 else '-'} {abs(m)} = 0$, найдите $\\dfrac{{1}}{{x_1}} + \\dfrac{{1}}{{x_2}}$.", ""))


@tpl("vieta", ("ru",))
def _vieta2(r):
    p, q = r.choice([(2, 5), (-3, 4), (1, 6), (3, 7)])
    s, m = p + q, p * q
    return number(str(p * p + q * q), L(
        f"$x_1^2 + x_2^2 = (x_1 + x_2)^2 - 2x_1x_2 = {s}^2 - 2 \\cdot ({m}) = {p * p + q * q}$.", ""),
        L(f"$x_1$ и $x_2$ — корни уравнения $x^2 {'-' if s >= 0 else '+'} {abs(s)}x {'+' if m >= 0 else '-'} {abs(m)} = 0$. Найдите $x_1^2 + x_2^2$.", ""))


@tpl("rational_eq")
def _(r):
    a = r.choice([2, 3, 4])
    b = r.choice([1, 5, 6])
    # x/(x-a) + a/(x+a) ... use: (x+b)/(x-a) = (2x - ... ) simpler: 1/(x-a) + 1/(x+a) = 2a/((x-a)(x+a))*... choose root
    x = r.choice([a + 3, a + 5, -a - 2])
    k = F(x + b, x - a)
    # equation (x + b)/(x - a) = k  -> unique root unless k == 1
    return number(str(x), L(
        f"ОДЗ: $x \\ne {a}$. $x + {b} = {fr(k)}(x - {a})$, отсюда $x = {x}$ (подходит).",
        f"Note $x \\ne {a}$. Then $x + {b} = {fr(k)}(x - {a})$, which gives $x = {x}$."),
        L(f"Решите уравнение $\\dfrac{{x + {b}}}{{x - {a}}} = {fr(k)}$.", f"Solve $\\dfrac{{x + {b}}}{{x - {a}}} = {fr(k)}$."))


@tpl("rational_eq", ("ru",))
def _req2(r):
    a = r.choice([2, 3, 5])
    # x^2/(x-a) = a^2/(x-a)  -> x = -a  (x = a excluded)
    return number(str(-a), L(
        f"ОДЗ: $x \\ne {a}$. Тогда $x^2 = {a * a}$, $x = \\pm {a}$. Корень $x = {a}$ не входит в ОДЗ, остаётся $x = {-a}$.", ""),
        L(f"Решите уравнение $\\dfrac{{x^2}}{{x - {a}}} = \\dfrac{{{a * a}}}{{x - {a}}}$.", ""))


@tpl("radical_eq", ("en",))
def _(r):
    # sqrt(2x + b) = x - c  <=>  x^2 - (2c + 2)x + c^2 - b = 0 with x >= c; keep only cases with exactly one valid root
    cases = []
    for x in range(2, 12):
        for c in range(0, 5):
            if x - c <= 0:
                continue
            b = (x - c) ** 2 - 2 * x
            other = 2 * c + 2 - x
            if other == x or (other - c >= 0 and 2 * other + b >= 0):
                continue
            cases.append((x, c, b, other))
    x, c, b, other = r.choice(cases)
    return number(str(x), f"Square both sides: $2x {'+' if b >= 0 else '-'} {abs(b)} = (x - {c})^2$, so $x^2 - {2 * c + 2}x + {c * c - b} = 0$ and $x = {x}$ or $x = {other}$. "
                          f"The right side $x - {c}$ must be non-negative, so $x = {other}$ is extraneous. The solution is $x = {x}$.",
                  f"What is the solution to $\\sqrt{{2x {'+' if b >= 0 else '-'} {abs(b)}}} = x - {c}$?")


@tpl("abs_eq")
def _(r):
    a, b = r.choice([(3, 7), (2, 5), (4, 9), (-1, 6)])
    # |x - a| = b -> roots a±b ; product
    p = (a + b) * (a - b)
    return number(str(p), L(
        f"$x - {a} = {b}$ или $x - {a} = -{b}$, то есть $x = {a + b}$ или $x = {a - b}$. Произведение корней: ${p}$.".replace("- -", "+ "),
        f"$x - {a} = {b}$ or $x - {a} = -{b}$, so $x = {a + b}$ or $x = {a - b}$. The product of the solutions is ${p}$.".replace("- -", "+ ")),
        L(f"Найдите произведение корней уравнения $|x {'-' if a > 0 else '+'} {abs(a)}| = {b}$.",
          f"What is the product of the solutions of $|x {'-' if a > 0 else '+'} {abs(a)}| = {b}$?"))


@tpl("abs_eq", ("ru",))
def _abs_eq2(r):
    a = r.choice([1, 2, 3])
    # |2x - a| = x + 3  -> 2x - a = x + 3 -> x = a+3 ; 2x - a = -x - 3 -> x = (a-3)/3 need x+3>=0
    x1, x2 = F(a + 3), F(a - 3, 3)
    s = x1 + x2
    return number(num(s), L(
        f"Нужно $x + 3 \\ge 0$. Случай 1: $2x - {a} = x + 3$, $x = {fr(x1)}$. Случай 2: $2x - {a} = -x - 3$, $x = {fr(x2)}$. Оба корня удовлетворяют условию, сумма ${fr(s)}$.", ""),
        L(f"Найдите сумму корней уравнения $|2x - {a}| = x + 3$.", ""))


@tpl("systems", ("ru",))
def _(r):
    x, y = r.choice([(3, -2), (5, 1), (-4, 3), (2, 7)])
    a, b, c, d = r.choice([(3, 2, 5, -3), (4, -3, 2, 5), (2, 5, 3, -2)])
    return number(str(x * y), L(
        f"Решаем систему сложением (уравниваем коэффициенты при одной переменной): $x = {x}$, $y = {y}$. Тогда $xy = {x * y}$.", ""),
        L(f"Решите систему $\\begin{{cases}} {a}x {'+' if b > 0 else '-'} {abs(b)}y = {a * x + b * y} \\\\ {c}x {'+' if d > 0 else '-'} {abs(d)}y = {c * x + d * y} \\end{{cases}}$ и найдите $xy$.", ""))


@tpl("systems_nl")
def _(r):
    x, y = r.choice([(2, 3), (1, 4), (3, 5)])
    s, p = x + y, x * y
    return number(str(abs(x - y) * s), L(
        f"$x$ и $y$ — корни $t^2 - {s}t + {p} = 0$, то есть ${x}$ и ${y}$. $x^2 - y^2 = (x - y)(x + y)$; при $x > y$ это ${abs(x - y)} \\cdot {s} = {abs(x - y) * s}$.",
        f"$x$ and $y$ are the roots of $t^2 - {s}t + {p} = 0$, i.e. ${x}$ and ${y}$. With $x > y$, $x^2 - y^2 = (x - y)(x + y) = {abs(x - y)} \\cdot {s} = {abs(x - y) * s}$."),
        L(f"Известно, что $x + y = {s}$, $xy = {p}$ и $x > y$. Найдите $x^2 - y^2$.",
          f"If $x + y = {s}$, $xy = {p}$, and $x > y$, what is $x^2 - y^2$?"))


@tpl("inequalities", ("ru",))
def _(r):
    a, b, c = r.choice([(3, 7, 2), (5, 4, 3), (7, 9, 4)])
    # (a x - b)/c > x - 1  -> a x - b > c x - c -> (a-c) x > b - c
    lo = F(b - c, a - c)
    k = math.floor(lo) + 1
    return number(str(k), L(
        f"Умножаем на ${c}$: ${a}x - {b} > {c}x - {c}$, ${a - c}x > {b - c}$, $x > {fr(lo)}$. Наименьшее целое: ${k}$.", ""),
        L(f"Найдите наименьшее целое решение неравенства $\\dfrac{{{a}x - {b}}}{{{c}}} > x - 1$.", ""))


@tpl("ineq_quad", ("ru",))
def _(r):
    p, q = r.choice([(-3, 4), (-2, 5), (1, 6), (-5, 2)])
    cnt = q - p - 1
    return number(str(cnt), L(
        f"Корни $x^2 - ({p + q})x + ({p * q}) = 0$: ${p}$ и ${q}$. Парабола ветвями вверх, поэтому неравенство $< 0$ выполняется между корнями: ${p} < x < {q}$. Целых чисел: ${cnt}$.", ""),
        L(f"Сколько целых решений имеет неравенство $x^2 {'-' if p + q > 0 else '+'} {abs(p + q) if abs(p + q) != 1 else ''}x {'-' if p * q < 0 else '+'} {abs(p * q)} < 0$?", ""))


@tpl("ineq_rational", ("ru",))
def _(r):
    a, b = r.choice([(-2, 5), (-4, 3), (1, 7)])
    cnt = b - a  # (x - a)/(x - b) <= 0 : a <= x < b
    return number(str(cnt), L(
        f"Метод интервалов: нули числителя $x = {a}$ (входит), знаменателя $x = {b}$ (не входит). Дробь $\\le 0$ при ${a} \\le x < {b}$. Целых: ${cnt}$.", ""),
        L(f"Сколько целых решений имеет неравенство $\\dfrac{{x {'-' if a > 0 else '+'} {abs(a)}}}{{x - {b}}} \\le 0$?", ""))


@tpl("ineq_abs")
def _(r):
    a, b = r.choice([(3, 5), (1, 4), (-2, 6), (4, 3)])
    lo, hi = a - b, a + b
    return number(str(hi - lo + 1), L(
        f"$|x - {a}| \\le {b} \\iff {a} - {b} \\le x \\le {a} + {b}$, то есть ${lo} \\le x \\le {hi}$. Целых: ${hi - lo + 1}$.".replace("- -", "+ "),
        f"$|x - {a}| \\le {b}$ means ${lo} \\le x \\le {hi}$, which contains ${hi - lo + 1}$ integers.".replace("- -", "+ ")),
        L(f"Сколько целых решений имеет неравенство $|x {'-' if a > 0 else '+'} {abs(a)}| \\le {b}$?",
          f"How many integers $x$ satisfy $|x {'-' if a > 0 else '+'} {abs(a)}| \\le {b}$?"))


@tpl("word_money")
def _(r):
    s, p, n = r.choice([(100000, 10, 2), (200000, 5, 2), (50000, 20, 2), (80000, 10, 3)])
    v = F(s) * (1 + F(p, 100)) ** n
    return number(num(v), L(
        f"Каждый год сумма умножается на ${dec(1 + F(p, 100))}$: ${s} \\cdot {dec(1 + F(p, 100))}^{n} = {num(v)}$.",
        f"Each year the amount is multiplied by ${dec(1 + F(p, 100))}$: ${s} \\cdot {dec(1 + F(p, 100))}^{n} = {num(v)}$."),
        L(f"Вклад {s:,} сомов положили в банк под ${p}\\%$ годовых с ежегодной капитализацией. Сколько сомов будет на счёте через {n} года?".replace(",", "\u00a0"),
          f"A deposit of $\\${f"{s:,}".replace(",", "{,}")}$ earns ${p}\\%$ interest per year, compounded annually. How many dollars will be in the account after {n} years?"))


@tpl("word_money", ("ru",))
def _money2(r):
    cost, m = r.choice([(800, 25), (1200, 20), (600, 50)])
    d = r.choice([10, 20])
    price = F(cost) * (1 + F(m, 100))
    sale = price * (1 - F(d, 100))
    profit = sale - cost
    return number(num(profit), L(
        f"Цена: ${cost} \\cdot {dec(1 + F(m, 100))} = {num(price)}$. Со скидкой: ${num(price)} \\cdot {dec(1 - F(d, 100))} = {num(sale)}$. Прибыль: ${num(sale)} - {cost} = {num(profit)}$.", ""),
        L(f"Магазин закупил товар за {cost} сомов и установил наценку ${m}\\%$. Затем товар продали со скидкой ${d}\\%$. Какую прибыль (в сомах) получил магазин?", ""))


@tpl("units")
def _(r):
    v = r.choice([54, 72, 90, 108])
    t = r.choice([15, 20, 25])
    ms = F(v * 1000, 3600)
    return number(num(ms * t), L(
        f"${v}$ км/ч $= \\frac{{{v} \\cdot 1000}}{{3600}} = {num(ms)}$ м/с. За ${t}$ с: ${num(ms)} \\cdot {t} = {num(ms * t)}$ м.",
        f"${v}$ km/h $= \\frac{{{v} \\cdot 1000}}{{3600}} = {num(ms)}$ m/s. In ${t}$ s: ${num(ms)} \\cdot {t} = {num(ms * t)}$ m."),
        L(f"Автомобиль едет со скоростью ${v}$ км/ч. Сколько метров он проедет за ${t}$ секунд?",
          f"A car travels at ${v}$ kilometers per hour. How many meters does it travel in ${t}$ seconds?"))


@tpl("units", ("ru",))
def _units2(r):
    v1, v2, d = r.choice([(60, 40, 300), (75, 45, 360), (80, 70, 450)])
    t = F(d, v1 + v2)
    return number(num(t * 60), L(
        f"Скорость сближения ${v1} + {v2} = {v1 + v2}$ км/ч. Время: ${d} : {v1 + v2} = {fr(t)}$ ч $= {num(t * 60)}$ мин.", ""),
        L(f"Из двух городов, расстояние между которыми ${d}$ км, одновременно навстречу друг другу выехали машины со скоростями ${v1}$ и ${v2}$ км/ч. Через сколько минут они встретятся?", ""))


# ------------------------------------------------------------------ functions

@tpl("graphs", ("en",))
def _(r):
    a, b = r.choice([(2, -3), (3, 1), (-1, 4)])
    c = r.choice([1, 2, 3])
    v = a * (c + 1) + b
    return number(str(v), f"First find $f({c}) = {a}\\cdot{c} {'+' if b >= 0 else '-'} {abs(b)} = {a * c + b}$. Then $f(x + 1)$ at $x = {c}$ is $f({c + 1}) = {v}$.",
                  f"The function $f$ is defined by $f(x) = {a}x {'+' if b >= 0 else '-'} {abs(b)}$. What is the value of $f(x + 1)$ when $x = {c}$?")


@tpl("domain", ("ru",))
def _(r):
    a, b = r.choice([(-3, 5), (-2, 6), (1, 7)])
    # sqrt((x - a)(b - x)) / (x - m)
    m = r.choice([x for x in range(a + 1, b) if x != 0][:3])
    cnt = (b - a + 1) - 1
    return number(str(cnt), L(
        f"Нужно $(x {'-' if a > 0 else '+'} {abs(a)})({b} - x) \\ge 0$, то есть ${a} \\le x \\le {b}$, и $x \\ne {m}$. Целых точек: ${b - a + 1} - 1 = {cnt}$.", ""),
        L(f"Сколько целых чисел входит в область определения функции $y = \\dfrac{{\\sqrt{{(x {'-' if a > 0 else '+'} {abs(a)})({b} - x)}}}}{{x - {m}}}$?", ""))


@tpl("domain", ("ru",))
def _dom2(r):
    a = r.choice([1, 2, 3])
    # range of y = a - |x|... use y = 3 - 2 sin x -> [1,5]; ask sum of integers in range
    k = r.choice([2, 3])
    lo, hi = a + 2 - k, a + 2 + k
    return number(str(sum(range(lo, hi + 1))), L(
        f"$-1 \\le \\cos x \\le 1$, поэтому $y = {a + 2} - {k}\\cos x$ принимает значения от ${lo}$ до ${hi}$. Сумма целых: ${sum(range(lo, hi + 1))}$.", ""),
        L(f"Найдите сумму всех целых чисел, входящих в множество значений функции $y = {a + 2} - {k}\\cos x$.", ""))


@tpl("fn_props", ("ru",))
def _(r):
    opts = ["$y = x^3 - x$", "$y = x^4 + x^2$", "$y = x^2 + x$", "$y = |x| + 1$"]
    right = r.choice([0])
    return {"text": "Какая из функций является нечётной?", "answer_type": "choice", "options": opts, "correct": "0", "difficulty": 2,
            "explanation": "Нечётная: $f(-x) = -f(x)$. Для $y = x^3 - x$: $(-x)^3 - (-x) = -(x^3 - x)$. Функции $x^4 + x^2$ и $|x| + 1$ чётные, $x^2 + x$ — ни чётная, ни нечётная."}


@tpl("fn_props", ("ru",))
def _fp2(r):
    k = r.choice([2, 3, 4, 6])
    t = F(2, k)
    return number(num(t), L(
        f"Период $\\sin x$ равен $2\\pi$; у $\\sin {k}x$ он в ${k}$ раз меньше: $\\frac{{2\\pi}}{{{k}}} = {fr(t)}\\pi$. Ответ: ${fr(t)}$.", ""),
        L(f"Наименьший положительный период функции $y = \\sin {k}x$ равен $T = a\\pi$. Найдите $a$.", ""))


@tpl("fn_props", ("ru",))
def _fp3(r):
    a = r.choice([2, 4, 6])
    return number(str(a // 2), L(
        f"$y = x^2 - {a}x$ — парабола ветвями вверх с вершиной в $x_0 = {a // 2}$. Слева от вершины функция убывает, справа возрастает, поэтому наименьшее $b$, при котором функция возрастает на $[b; +\\infty)$, равно ${a // 2}$.", ""),
        L(f"Найдите наименьшее $b$, при котором функция $y = x^2 - {a}x$ возрастает на промежутке $[b; +\\infty)$.", ""))


@tpl("fn_transform")
def _(r):
    h, k = r.choice([(2, -3), (-1, 4), (3, 1)])
    sh = lambda v: f"{'-' if v > 0 else '+'} {abs(v)}"
    up = lambda v: f"{'+' if v > 0 else '-'} {abs(v)}"
    right = f"y = (x {sh(h)})^2 {up(k)}"
    wrong = [f"y = (x {sh(-h)})^2 {up(k)}", f"y = (x {sh(h)})^2 {up(-k)}", f"y = (x {sh(-k)})^2 {up(h)}"]
    return choice(r, right, wrong,
                  L(f"Сдвиг вправо на $a$ — замена $x$ на $x - a$, сдвиг вверх на $b$ — прибавление $b$. Вершина новой параболы: $({h}; {k})$.",
                    f"Shifting right by $a$ replaces $x$ with $x - a$; shifting up by $b$ adds $b$. The new vertex is $({h}, {k})$."),
                  L(f"График $y = x^2$ сдвинули на ${abs(h)}$ {'вправо' if h > 0 else 'влево'} и на ${abs(k)}$ {'вверх' if k > 0 else 'вниз'}. Какой формулой задаётся новый график?",
                    f"The graph of $y = x^2$ is shifted {abs(h)} unit{'s' if abs(h) != 1 else ''} {'right' if h > 0 else 'left'} and {abs(k)} unit{'s' if abs(k) != 1 else ''} {'up' if k > 0 else 'down'}. Which equation defines the new graph?"),
                  difficulty=2)


@tpl("fn_transform", ("ru",))
def _ft2(r):
    a, c = r.choice([(2, 3), (3, -1), (-2, 5)])
    x0 = r.choice([1, 2, 4])
    v = abs(x0 - a) + c
    return number(str(c), L(
        f"$y = |x - {a}| + {c}$ — это график $y = |x|$, сдвинутый на ${a}$ по оси $x$ и на ${c}$ по оси $y$. Наименьшее значение — в вершине: ${c}$.".replace("- -", "+ ").replace("+ -", "- "), ""),
        L(f"Найдите наименьшее значение функции $y = |x {'-' if a > 0 else '+'} {abs(a)}| {'+' if c > 0 else '-'} {abs(c)}$.", ""))


@tpl("fn_inverse", ("ru",))
def _(r):
    a, b = r.choice([(2, 3), (3, -4), (5, 1)])
    y = r.choice([7, 11, 13])
    x = F(y - b, a)
    return number(num(x), L(
        f"$g({y})$ — такое $x$, что $f(x) = {y}$: ${a}x {'+' if b > 0 else '-'} {abs(b)} = {y}$, $x = {fr(x)}$.", ""),
        L(f"Функция $g$ обратна к $f(x) = {a}x {'+' if b > 0 else '-'} {abs(b)}$. Найдите $g({y})$.", ""))


@tpl("power_fn", ("en",))
def _(r):
    a, b = r.choice([(6, 2), (12, 3), (8, -2)])
    return number(str(a), f"The graph of $y = \\frac{{k}}{{x}}$ passes through $({b}, {a // b})$, so $k = {b} \\cdot {a // b} = {a}$. Then at $x = 1$, $y = {a}$.",
                  f"The graph of $y = \\dfrac{{k}}{{x}}$ passes through the point $({b}, {a // b})$. What is the value of $y$ when $x = 1$?")


@tpl("log_fn", ("ru",))
def _(r):
    a = r.choice([2, 3, 5])
    b = r.choice([1, 2, 4])
    # domain of log_a(x^2 - b^2... ) choose log(x - b) + log(c - x): integers in (b, c)
    c = b + r.choice([5, 6, 7])
    cnt = c - b - 1
    return number(str(cnt), L(
        f"Нужно $x - {b} > 0$ и ${c} - x > 0$, то есть ${b} < x < {c}$. Целых: ${cnt}$.", ""),
        L(f"Сколько целых чисел входит в область определения функции $y = \\log_{{{a}}}(x - {b}) + \\log_{{{a}}}({c} - x)$?", ""))


@tpl("log_fn", ("ru",))
def _logfn2(r):
    a = r.choice([2, 3])
    lo, hi = a, a ** 3
    return number(str(3 - 1), L(
        f"$\\log_{{{a}}} x$ возрастает, поэтому на $[{lo}; {hi}]$ наибольшее значение $\\log_{{{a}}} {hi} = 3$, наименьшее $\\log_{{{a}}} {lo} = 1$. Разность: $2$.", ""),
        L(f"Найдите разность наибольшего и наименьшего значений функции $y = \\log_{{{a}}} x$ на отрезке $[{lo}; {hi}]$.", ""))


@tpl("log_def", ("ru",))
def _(r):
    a, k = r.choice([(2, 5), (3, 4), (5, 3)])
    m = r.choice([2, 3])
    v = F(k, m)
    return number(num(v), L(
        f"$\\sqrt[{m}]{{{a ** k}}} = {a}^{{{fr(v)}}}$, поэтому $\\log_{{{a}}} \\sqrt[{m}]{{{a ** k}}} = {fr(v)}$.", ""),
        L(f"Вычислите $\\log_{{{a}}} \\sqrt[{m}]{{{a ** k}}}$.", ""))


@tpl("log_def", ("ru",))
def _logdef2(r):
    a, b = r.choice([(2, 7), (3, 5), (5, 4)])
    k = r.choice([2, 3])
    return number(str(b ** k), L(
        f"$a^{{\\log_a b}} = b$: $({a}^{{\\log_{{{a}}} {b}}})^{k} = {b}^{k} = {b ** k}$.", ""),
        L(f"Вычислите ${a}^{{{k}\\log_{{{a}}} {b}}}$.", ""))


@tpl("log_ineq", ("ru",))
def _(r):
    a, c = r.choice([(2, 3), (3, 2), (2, 4)])
    hi = a ** c
    cnt = hi - 1  # 0 < x - 1? use log_a(x) < c with x>0 -> 0 < x < a^c ; integers 1..hi-1
    return number(str(cnt), L(
        f"Основание ${a} > 1$, функция возрастает: $0 < x < {a}^{c} = {hi}$. Натуральных решений: ${cnt}$.", ""),
        L(f"Сколько натуральных чисел являются решениями неравенства $\\log_{{{a}}} x < {c}$?", ""))


@tpl("log_ineq", ("ru",))
def _logineq2(r):
    a, k = r.choice([(2, 5), (3, 3), (2, 3)])
    return number(str(k + 1), f"$\\frac{{1}}{{{a ** k}}} = \\left(\\frac{{1}}{{{a}}}\\right)^{k}$. Основание меньше 1, функция убывает, знак меняется: $x > {k}$. Наименьшее целое решение: ${k + 1}$.",
                  f"Найдите наименьшее целое решение неравенства $\\left(\\dfrac{{1}}{{{a}}}\\right)^x < \\dfrac{{1}}{{{a ** k}}}$.")


@tpl("exp_fn", ("ru",))
def _(r):
    a = r.choice([2, 3])
    k = r.choice([3, 4, 5])
    return number(str(k + 1), L(
        f"${a}^{{x - 1}} = {a ** k}= {a}^{{{k}}}$, значит $x - 1 = {k}$, $x = {k + 1}$.", ""),
        L(f"Найдите абсциссу точки пересечения графика $y = {a}^{{x - 1}}$ с прямой $y = {a ** k}$.", ""))


# ------------------------------------------------------------------ geometry

@tpl("angles", ("ru",))
def _(r):
    n = r.choice([2, 3, 4])
    a = r.choice([20, 30, 36])
    # two parallel lines, angles a and n*a? interior same-side sum 180
    x = F(180, n + 1)
    return number(num(x * n), L(
        f"Односторонние углы при параллельных прямых в сумме дают $180^\\circ$: $x + {n}x = 180^\\circ$, $x = {num(x)}^\\circ$. Больший угол: ${num(x * n)}^\\circ$.", ""),
        L(f"При пересечении двух параллельных прямых секущей один из односторонних углов в ${n}$ раза больше другого. Найдите больший угол (в градусах).", ""))


@tpl("triangle_types")
def _(r):
    a = r.choice([40, 50, 70, 30])
    base = (180 - a) // 2
    ext = 180 - base
    return number(str(ext), L(
        f"Углы при основании равны $\\frac{{180^\\circ - {a}^\\circ}}{{2}} = {base}^\\circ$. Внешний угол при основании: $180^\\circ - {base}^\\circ = {ext}^\\circ$.",
        f"Each base angle is $\\frac{{180^\\circ - {a}^\\circ}}{{2}} = {base}^\\circ$, so an exterior angle at the base is $180^\\circ - {base}^\\circ = {ext}^\\circ$."),
        L(f"В равнобедренном треугольнике угол при вершине равен ${a}^\\circ$. Найдите внешний угол при основании (в градусах).",
          f"In an isosceles triangle, the vertex angle measures ${a}^\\circ$. What is the measure, in degrees, of an exterior angle at the base?"))


@tpl("triangle_types", ("ru",))
def _tt2(r):
    a = r.choice([6, 8, 12])
    h2 = F(3 * a * a, 4)
    s2 = F(3, 16) * a ** 4
    # area = a^2 sqrt3 /4 ; ask S^2
    return number(num(s2), L(
        f"Площадь равностороннего треугольника $S = \\frac{{a^2\\sqrt3}}{{4}}$, $S^2 = \\frac{{3a^4}}{{16}} = {num(s2)}$.", ""),
        L(f"Сторона равностороннего треугольника равна ${a}$. Найдите $S^2$, где $S$ — его площадь.", ""))


@tpl("pythagoras")
def _(r):
    a, b, c = r.choice([(5, 12, 13), (8, 15, 17), (7, 24, 25), (9, 40, 41)])
    h = F(a * b, c)
    return number(num(h), L(
        f"Гипотенуза $\\sqrt{{{a}^2 + {b}^2}} = {c}$. Высота к гипотенузе $h = \\frac{{ab}}{{c}} = \\frac{{{a} \\cdot {b}}}{{{c}}} = {fr(h)}$.",
        f"The hypotenuse is $\\sqrt{{{a}^2 + {b}^2}} = {c}$. The altitude to the hypotenuse is $h = \\frac{{ab}}{{c}} = \\frac{{{a} \\cdot {b}}}{{{c}}} = {fr(h)}$."),
        L(f"Катеты прямоугольного треугольника равны ${a}$ и ${b}$. Найдите высоту, проведённую к гипотенузе.",
          f"A right triangle has legs of length ${a}$ and ${b}$. What is the length of the altitude to the hypotenuse?"))


@tpl("similarity", ("ru",))
def _(r):
    k = r.choice([2, 3, F(3, 2), F(5, 2)])
    s = r.choice([12, 18, 20])
    big = F(s) * F(k) ** 2
    return number(num(big), L(
        f"Отношение площадей подобных фигур равно квадрату коэффициента подобия: $S_2 = {s} \\cdot ({fr(k)})^2 = {num(big)}$.", ""),
        L(f"Треугольники подобны с коэффициентом ${fr(k)}$. Площадь меньшего равна ${s}$. Найдите площадь большего.", ""))


@tpl("similarity", ("ru",))
def _sim2(r):
    a, b = r.choice([(4, 6), (3, 9), (5, 10)])
    # trapezoid bases a, b; diagonals intersect; ratio of segments; height ... midsegment through intersection parallel to bases: 2ab/(a+b)
    v = F(2 * a * b, a + b)
    return number(num(v), L(
        f"Отрезок, параллельный основаниям трапеции и проходящий через точку пересечения диагоналей, равен $\\frac{{2ab}}{{a + b}} = \\frac{{2 \\cdot {a} \\cdot {b}}}{{{a + b}}} = {fr(v)}$ (это следует из подобия треугольников).", ""),
        L(f"Основания трапеции равны ${a}$ и ${b}$. Через точку пересечения диагоналей проведён отрезок, параллельный основаниям, с концами на боковых сторонах. Найдите его длину.", ""))


@tpl("triangle_area", ("ru",))
def _(r):
    a, b, c = r.choice([(13, 14, 15), (5, 5, 6), (10, 13, 13), (7, 15, 20)])
    p = F(a + b + c, 2)
    s = math.isqrt(int(p * (p - a) * (p - b) * (p - c)))
    return number(str(s), L(
        f"Формула Герона: $p = {num(p)}$, $S = \\sqrt{{{num(p)} \\cdot {num(p - a)} \\cdot {num(p - b)} \\cdot {num(p - c)}}} = {s}$.", ""),
        L(f"Найдите площадь треугольника со сторонами ${a}$, ${b}$ и ${c}$.", ""))


@tpl("sin_cos_law", ("ru",))
def _(r):
    a, b = r.choice([(5, 8), (3, 8), (7, 8)])
    c2 = a * a + b * b - a * b  # angle 60
    c = math.isqrt(c2)
    return number(str(c) if c * c == c2 else num(F(c2)), L(
        f"Теорема косинусов: $c^2 = {a}^2 + {b}^2 - 2 \\cdot {a} \\cdot {b} \\cdot \\cos 60^\\circ = {c2}$, $c = {c}$." if c * c == c2 else
        f"Теорема косинусов: $c^2 = {a}^2 + {b}^2 - 2 \\cdot {a} \\cdot {b} \\cdot \\cos 60^\\circ = {c2}$.", ""),
        L(f"Две стороны треугольника равны ${a}$ и ${b}$, угол между ними $60^\\circ$. Найдите третью сторону." if c * c == c2 else
          f"Две стороны треугольника равны ${a}$ и ${b}$, угол между ними $60^\\circ$. Найдите квадрат третьей стороны.", ""))


@tpl("sin_cos_law", ("ru",))
def _scl2(r):
    a = r.choice([6, 10, 14])
    ang = r.choice([30, 150])
    R = a  # a / sin30 = 2R -> R = a
    return number(str(R), L(
        f"Теорема синусов: $\\frac{{a}}{{\\sin A}} = 2R$, $\\sin {ang}^\\circ = \\frac{{1}}{{2}}$, поэтому $R = \\frac{{{a}}}{{2 \\cdot \\frac12}} = {R}$.", ""),
        L(f"В треугольнике сторона, противолежащая углу ${ang}^\\circ$, равна ${a}$. Найдите радиус описанной окружности.", ""))


@tpl("polygons")
def _(r):
    n = r.choice([8, 9, 10, 12, 15])
    ang = F(180 * (n - 2), n)
    return number(num(ang), L(
        f"Сумма углов ${n}$-угольника $180^\\circ \\cdot ({n} - 2) = {180 * (n - 2)}^\\circ$. Один угол: ${180 * (n - 2)} : {n} = {num(ang)}^\\circ$.",
        f"The interior angles of a {n}-sided polygon sum to $180^\\circ({n} - 2) = {180 * (n - 2)}^\\circ$, so each angle is ${num(ang)}^\\circ$."),
        L(f"Найдите внутренний угол правильного ${n}$-угольника (в градусах).", f"What is the measure, in degrees, of each interior angle of a regular {n}-sided polygon?"))


@tpl("polygons", ("ru",))
def _poly_n(r):
    ext = r.choice([20, 24, 30, 36, 40])
    n = 360 // ext
    d = n * (n - 3) // 2
    return number(str(d), L(
        f"Сумма внешних углов $360^\\circ$, поэтому $n = 360 : {ext} = {n}$. Диагоналей: $\\frac{{n(n-3)}}{{2}} = {d}$.", ""),
        L(f"Внешний угол правильного многоугольника равен ${ext}^\\circ$. Сколько у него диагоналей?", ""))


@tpl("circle")
def _(r):
    a, b = r.choice([(6, 8), (5, 12), (9, 12)])
    d = math.isqrt(a * a + b * b)
    return number(num(F(d, 2)), L(
        f"Вписанный прямой угол опирается на диаметр. Гипотенуза $= \\sqrt{{{a}^2 + {b}^2}} = {d}$ — диаметр, радиус ${dec(F(d, 2))}$.",
        f"A right angle inscribed in a circle subtends a diameter. The hypotenuse is $\\sqrt{{{a}^2 + {b}^2}} = {d}$, so the radius is ${dec(F(d, 2))}$."),
        L(f"Прямоугольный треугольник с катетами ${a}$ и ${b}$ вписан в окружность. Найдите её радиус.",
          f"A right triangle with legs ${a}$ and ${b}$ is inscribed in a circle. What is the radius of the circle?"))


@tpl("arcs")
def _(r):
    R = r.choice([6, 9, 12])
    ang = r.choice([60, 120, 150, 240])
    area = F(ang, 360) * R * R
    return number(num(area), L(
        f"Площадь сектора $\\frac{{{ang}}}{{360}} \\pi R^2 = {fr(area)}\\pi$. Ответ: ${fr(area)}$.",
        f"Sector area $= \\frac{{{ang}}}{{360}} \\pi r^2 = {fr(area)}\\pi$, so $k = {fr(area)}$."),
        L(f"Радиус круга ${R}$, центральный угол сектора ${ang}^\\circ$. Площадь сектора равна $k\\pi$. Найдите $k$.",
          f"A circle has radius ${R}$. A sector has a central angle of ${ang}^\\circ$, and its area is $k\\pi$. What is $k$?"))


@tpl("arcs", ("ru",))
def _arcs2(r):
    R, d = r.choice([(13, 5), (10, 6), (17, 8), (25, 7)])
    half = math.isqrt(R * R - d * d)
    return number(str(2 * half), L(
        f"Перпендикуляр из центра делит хорду пополам: половина хорды $\\sqrt{{{R}^2 - {d}^2}} = {half}$, хорда ${2 * half}$.", ""),
        L(f"Радиус окружности ${R}$, расстояние от центра до хорды ${d}$. Найдите длину хорды.", ""))


@tpl("arcs", ("ru",))
def _arcs3(r):
    d, R = r.choice([(10, 6), (13, 5), (17, 8)])
    t = math.isqrt(d * d - R * R)
    return number(str(t), L(
        f"Касательная перпендикулярна радиусу в точке касания: $t = \\sqrt{{{d}^2 - {R}^2}} = {t}$.", ""),
        L(f"Из точки, удалённой от центра окружности радиуса ${R}$ на ${d}$, проведена касательная. Найдите длину отрезка касательной.", ""))


@tpl("space_coords", ("ru",))
def _(r):
    a = r.choice([(1, 2, 2), (2, 3, 6), (4, 4, 7)])
    b = r.choice([(0, 0, 0)])
    l = math.isqrt(sum(x * x for x in a))
    return number(str(l), L(
        f"$|\\vec a| = \\sqrt{{{a[0]}^2 + {a[1]}^2 + {a[2]}^2}} = \\sqrt{{{sum(x * x for x in a)}}} = {l}$.", ""),
        L(f"Найдите длину вектора $\\vec a({a[0]}; {a[1]}; {a[2]})$.", ""))


@tpl("space_coords", ("ru",))
def _sc2(r):
    a = r.choice([(1, 2, -1), (3, 0, 2), (2, -1, 4)])
    b = r.choice([(2, -1, 3), (1, 4, -2), (-1, 2, 1)])
    d = sum(x * y for x, y in zip(a, b))
    return number(str(d), L(
        f"$\\vec a \\cdot \\vec b = {a[0]} \\cdot {b[0]} + {a[1]} \\cdot {b[1]} + {a[2]} \\cdot {b[2]} = {d}$.".replace("+ -", "- "), ""),
        L(f"Найдите скалярное произведение векторов $\\vec a({a[0]}; {a[1]}; {a[2]})$ и $\\vec b({b[0]}; {b[1]}; {b[2]})$.", ""))


@tpl("coord_basics")
def _(r):
    (x1, y1), (x2, y2) = r.choice([((1, 2), (7, 10)), ((-2, 3), (4, -5)), ((3, -1), (-3, 7))])
    d = math.isqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    mx, my = F(x1 + x2, 2), F(y1 + y2, 2)
    return number(str(d), L(
        f"$AB = \\sqrt{{({x2} - {x1})^2 + ({y2} - {y1})^2}} = \\sqrt{{{(x2 - x1) ** 2} + {(y2 - y1) ** 2}}} = {d}$.".replace("- -", "+ "),
        f"$AB = \\sqrt{{({x2} - {x1})^2 + ({y2} - {y1})^2}} = \\sqrt{{{(x2 - x1) ** 2} + {(y2 - y1) ** 2}}} = {d}$.".replace("- -", "+ ")),
        L(f"Найдите длину отрезка с концами $A({x1}; {y1})$ и $B({x2}; {y2})$.", f"What is the distance between $A({x1}, {y1})$ and $B({x2}, {y2})$?"))


@tpl("coord_basics", ("ru",))
def _cb2(r):
    (x1, y1), (x2, y2) = r.choice([((1, 2), (5, 10)), ((-2, 3), (4, -9)), ((0, -1), (3, 8))])
    k = F(y2 - y1, x2 - x1)
    return number(num(k), L(
        f"$k = \\frac{{y_2 - y_1}}{{x_2 - x_1}} = \\frac{{{y2 - y1}}}{{{x2 - x1}}} = {fr(k)}$.", ""),
        L(f"Найдите угловой коэффициент прямой, проходящей через точки $({x1}; {y1})$ и $({x2}; {y2})$.", ""))


@tpl("line_eq", ("ru",))
def _(r):
    k, b = r.choice([(2, -3), (-1, 4), (3, 1)])
    x0, y0 = r.choice([(1, 5), (2, -1), (-1, 2)])
    # perpendicular through (x0,y0): slope -1/k ; find y-intercept
    m = F(-1, k)
    c = y0 - m * x0
    return number(num(c), L(
        f"Перпендикулярная прямая имеет угловой коэффициент $-\\frac{{1}}{{{k}}} = {fr(m)}$. $y = {fr(m)}x + c$ через $({x0}; {y0})$: $c = {y0} - ({fr(m)}) \\cdot {x0} = {fr(c)}$.", ""),
        L(f"Прямая перпендикулярна прямой $y = {k}x {'+' if b > 0 else '-'} {abs(b)}$ и проходит через точку $({x0}; {y0})$. В какой точке она пересекает ось $Oy$? Укажите ординату.", ""))


@tpl("circle_eq")
def _(r):
    a, b, R = r.choice([(2, -3, 5), (-1, 4, 3), (3, 1, 4)])
    D = -2 * a
    E = -2 * b
    C = a * a + b * b - R * R
    return number(str(R), L(
        f"Выделяем полные квадраты: $(x {'-' if a > 0 else '+'} {abs(a)})^2 + (y {'-' if b > 0 else '+'} {abs(b)})^2 = {R * R}$. Радиус ${R}$.",
        f"Complete the square: $(x {'-' if a > 0 else '+'} {abs(a)})^2 + (y {'-' if b > 0 else '+'} {abs(b)})^2 = {R * R}$, so the radius is ${R}$."),
        L(f"Найдите радиус окружности $x^2 + y^2 {'+' if D > 0 else '-'} {abs(D)}x {'+' if E > 0 else '-'} {abs(E)}y {'+' if C > 0 else '-'} {abs(C)} = 0$.",
          f"What is the radius of the circle $x^2 + y^2 {'+' if D > 0 else '-'} {abs(D)}x {'+' if E > 0 else '-'} {abs(E)}y {'+' if C > 0 else '-'} {abs(C)} = 0$?"))


@tpl("conics", ("ru",))
def _(r):
    a, b = r.choice([(5, 3), (13, 5), (10, 6)])
    c = math.isqrt(a * a - b * b)
    return number(str(2 * c), L(
        f"Для эллипса $c^2 = a^2 - b^2 = {a * a} - {b * b} = {c * c}$, $c = {c}$. Расстояние между фокусами $2c = {2 * c}$.", ""),
        L(f"Найдите расстояние между фокусами эллипса $\\dfrac{{x^2}}{{{a * a}}} + \\dfrac{{y^2}}{{{b * b}}} = 1$.", ""))


@tpl("conics", ("ru",))
def _con2(r):
    p = r.choice([2, 4, 6, 8])
    return number(num(F(p, 4)), L(
        f"Парабола $y^2 = 4ax$ имеет фокус $(a; 0)$. Здесь $4a = {p}$, $a = {fr(F(p, 4))}$.", ""),
        L(f"Найдите абсциссу фокуса параболы $y^2 = {p}x$.", ""))


@tpl("quadrilaterals", ("en",))
def _(r):
    a, b = r.choice([(6, 8), (5, 12), (9, 12)])
    d = math.isqrt(a * a + b * b)
    return number(str(2 * (a + b)), f"By the Pythagorean theorem the other side is $\\sqrt{{{d}^2 - {a}^2}} = {b}$. Perimeter $= 2({a} + {b}) = {2 * (a + b)}$.",
                  f"A rectangle has a diagonal of length ${d}$ and one side of length ${a}$. What is the perimeter of the rectangle?")


@tpl("volumes", ("en",))
def _(r):
    R, h = r.choice([(3, 4), (6, 8), (5, 12)])
    return number(str(R * R * h // 3), f"$V = \\frac13 \\pi r^2 h = \\frac13 \\pi \\cdot {R}^2 \\cdot {h} = {R * R * h // 3}\\pi$.",
                  f"A right circular cone has radius ${R}$ and height ${h}$. Its volume is $k\\pi$. What is $k$?")


@tpl("surface", ("en",))
def _(r):
    a = r.choice([3, 5, 7])
    return number(str(6 * a * a * 4), f"Doubling the edge multiplies the surface area by 4: $6 \\cdot ({2 * a})^2 = {24 * a * a}$.",
                  f"A cube has edge length ${a}$. If each edge is doubled, what is the surface area of the new cube?")


# ------------------------------------------------------------------ trigonometry

@tpl("right_trig", ("ru",))
def _(r):
    a, b, c = r.choice([(3, 4, 5), (5, 12, 13), (8, 15, 17)])
    return number(num(F(a, c) + F(b, c)), L(
        f"Гипотенуза ${c}$. $\\sin A = \\frac{{{a}}}{{{c}}}$, $\\cos A = \\frac{{{b}}}{{{c}}}$, сумма ${fr(F(a + b, c))}$.", ""),
        L(f"В прямоугольном треугольнике катет, противолежащий углу $A$, равен ${a}$, прилежащий — ${b}$. Найдите $\\sin A + \\cos A$.", ""))


@tpl("trig_values", ("en",))
def _(r):
    opts = [("\\sin 30^\\circ + \\cos 60^\\circ", 1), ("\\tan 45^\\circ \\cdot \\cos 0^\\circ", 1), ("\\sin^2 60^\\circ + \\cos^2 60^\\circ + \\tan 45^\\circ", 2)]
    e, v = r.choice(opts)
    return number(str(v), f"Use exact values: $\\sin 30^\\circ = \\cos 60^\\circ = \\frac12$, $\\tan 45^\\circ = 1$, $\\cos 0^\\circ = 1$, and $\\sin^2 x + \\cos^2 x = 1$. The value is ${v}$.",
                  f"What is the value of ${e}$?")


@tpl("radians")
def _(r):
    deg = r.choice([135, 210, 300, 330, 225])
    rad = F(deg, 180)
    return choice(r, f"{fr(rad)}\\pi", [f"{fr(F(deg, 360))}\\pi", f"{fr(rad * 2)}\\pi", f"{fr(F(180, deg))}\\pi"],
                  L(f"$\\pi$ рад $= 180^\\circ$, поэтому ${deg}^\\circ = \\frac{{{deg}}}{{180}}\\pi = {fr(rad)}\\pi$.",
                    f"Since $\\pi$ radians $= 180^\\circ$, ${deg}^\\circ = \\frac{{{deg}}}{{180}}\\pi = {fr(rad)}\\pi$ radians."),
                  L(f"Переведите ${deg}^\\circ$ в радианы.", f"What is ${deg}^\\circ$ in radians?"), difficulty=2)


@tpl("radians", ("ru",))
def _rad2(r):
    expr, val, why = r.choice([
        ("\\sin\\dfrac{7\\pi}{6}", F(-1, 2), "$\\frac{7\\pi}{6} = \\pi + \\frac{\\pi}{6}$ — III четверть, синус отрицателен: $-\\sin\\frac{\\pi}{6} = -\\frac12$."),
        ("\\cos\\dfrac{5\\pi}{3}", F(1, 2), "$\\frac{5\\pi}{3} = 2\\pi - \\frac{\\pi}{3}$ — IV четверть, косинус положителен: $\\cos\\frac{\\pi}{3} = \\frac12$."),
        ("\\operatorname{tg}\\dfrac{3\\pi}{4}", F(-1), "$\\frac{3\\pi}{4} = \\pi - \\frac{\\pi}{4}$ — II четверть, тангенс отрицателен: $-1$."),
        ("\\cos\\dfrac{2\\pi}{3} + \\sin\\dfrac{11\\pi}{6}", F(-1), "$\\cos\\frac{2\\pi}{3} = -\\frac12$, $\\sin\\frac{11\\pi}{6} = -\\frac12$, сумма $-1$.")])
    return number(num(val), why, f"Вычислите ${expr}$.")


@tpl("trig_eq", ("ru",))
def _(r):
    n = r.choice([2, 3])
    # number of roots of sin x = 1/2 on [0, 2pi n]
    return number(str(2 * n), L(
        f"На каждом отрезке длины $2\\pi$ уравнение $\\sin x = \\frac12$ имеет два корня ($\\frac{{\\pi}}{{6}}$ и $\\frac{{5\\pi}}{{6}}$ плюс период). На $[0; {2 * n}\\pi]$ — ${2 * n}$ корня.", ""),
        L(f"Сколько корней уравнения $\\sin x = \\dfrac12$ принадлежит отрезку $[0; {2 * n}\\pi]$?", ""))


@tpl("trig_eq", ("ru",))
def _te2(r):
    return number("90", "$2\\sin^2 x - \\sin x - 1 = 0$: $\\sin x = 1$ или $\\sin x = -\\frac12$. На $[0^\\circ; 180^\\circ]$ подходит только $\\sin x = 1$, $x = 90^\\circ$.",
                  "Решите уравнение $2\\sin^2 x - \\sin x - 1 = 0$ на отрезке $[0^\\circ; 180^\\circ]$. Ответ дайте в градусах.")


@tpl("arc_fn", ("ru",))
def _(r):
    e, v, why = r.choice([("\\arcsin\\frac12 + \\arccos\\frac12", "90", "$\\frac{\\pi}{6} + \\frac{\\pi}{3} = \\frac{\\pi}{2}$, то есть $90^\\circ$."),
                          ("\\arccos\\left(-\\frac12\\right)", "120", "$\\arccos(-a) = \\pi - \\arccos a = \\pi - \\frac{\\pi}{3} = \\frac{2\\pi}{3}$, то есть $120^\\circ$."),
                          ("\\operatorname{arctg} 1 + \\arcsin\\left(-\\frac{\\sqrt2}{2}\\right)", "0", "$\\frac{\\pi}{4} - \\frac{\\pi}{4} = 0$."),
                          ("2\\arcsin\\frac{\\sqrt3}{2}", "120", "$2 \\cdot \\frac{\\pi}{3} = \\frac{2\\pi}{3}$, то есть $120^\\circ$.")])
    return number(v, why, f"Вычислите ${e}$. Ответ дайте в градусах.")


@tpl("arc_fn", ("ru",))
def _af2(r):
    x = r.choice([F(3, 5), F(5, 13), F(8, 17)])
    c = {F(3, 5): F(4, 5), F(5, 13): F(12, 13), F(8, 17): F(15, 17)}[x]
    return number(num(c), f"Пусть $\\alpha = \\arcsin {fr(x)}$, $\\alpha \\in [-\\frac{{\\pi}}{{2}}; \\frac{{\\pi}}{{2}}]$, поэтому $\\cos\\alpha \\ge 0$: $\\cos\\alpha = \\sqrt{{1 - ({fr(x)})^2}} = {fr(c)}$.",
                  f"Вычислите $\\cos\\left(\\arcsin {fr(x)}\\right)$.")


# ------------------------------------------------------------------ analysis

@tpl("limits", ("ru",))
def _(r):
    a = r.choice([2, 3, 4, 5])
    return number(str(2 * a), f"$\\frac{{x^2 - {a * a}}}{{x - {a}}} = x + {a}$ при $x \\ne {a}$, поэтому предел равен ${a} + {a} = {2 * a}$.",
                  f"Найдите $\\lim\\limits_{{x \\to {a}}} \\dfrac{{x^2 - {a * a}}}{{x - {a}}}$.")


@tpl("limits", ("ru",))
def _lim2(r):
    a, b, c, d = r.choice([(3, 2, 6, 5), (4, 1, 2, 7), (5, 3, 10, 1)])
    return number(num(F(a, c)), f"Делим числитель и знаменатель на $x^2$: при $x \\to \\infty$ остаётся $\\frac{{{a}}}{{{c}}} = {fr(F(a, c))}$.",
                  f"Найдите $\\lim\\limits_{{x \\to \\infty}} \\dfrac{{{a}x^2 + {b}x}}{{{c}x^2 - {d}}}$.")


@tpl("complex")
def _(r):
    a, b = r.choice([(3, 4), (5, 12), (1, 2), (2, -3)])
    c, d = r.choice([(1, 1), (2, -1), (1, -2)])
    re, im = a * c - b * d, a * d + b * c
    return number(str(re + im), L(
        f"$({a} {'+' if b > 0 else '-'} {abs(b)}i)({c} {'+' if d > 0 else '-'} {abs(d)}i) = {re} {'+' if im >= 0 else '-'} {abs(im)}i$ (так как $i^2 = -1$). $a + b = {re + im}$.",
        f"$({a} {'+' if b > 0 else '-'} {abs(b)}i)({c} {'+' if d > 0 else '-'} {abs(d)}i) = {re} {'+' if im >= 0 else '-'} {abs(im)}i$ since $i^2 = -1$. So $a + b = {re + im}$."),
        L(f"Произведение $({a} {'+' if b > 0 else '-'} {abs(b)}i)({c} {'+' if d > 0 else '-'} {abs(d)}i)$ записано в виде $a + bi$. Найдите $a + b$.",
          f"The product $({a} {'+' if b > 0 else '-'} {abs(b)}i)({c} {'+' if d > 0 else '-'} {abs(d)}i)$ is written as $a + bi$, where $i = \\sqrt{{-1}}$. What is $a + b$?"))


# ------------------------------------------------------------------ probability & statistics

@tpl("combinatorics", ("ru",))
def _(r):
    n, k = r.choice([(8, 3), (10, 2), (7, 4), (9, 3)])
    c = math.comb(n, k)
    return number(str(c), f"Порядок не важен — сочетания: $C_{{{n}}}^{{{k}}} = \\frac{{{n}!}}{{{k}!\\,{n - k}!}} = {c}$.",
                  f"Сколькими способами можно выбрать ${k}$ человек из ${n}$ для дежурства?")


@tpl("combinatorics", ("ru",))
def _comb2(r):
    n = r.choice([5, 6, 7])
    v = math.factorial(n - 1) * 2
    return number(str(v), f"Склеиваем двух человек в один «блок»: ${n - 1}$ объектов, ${n - 1}! = {math.factorial(n - 1)}$ перестановок, внутри блока $2$ порядка: ${v}$.",
                  f"Сколькими способами ${n}$ человек могут встать в очередь так, чтобы Айбек и Нурай стояли рядом?")


@tpl("combinatorics", ("ru",))
def _comb3(r):
    d = r.choice([3, 4])
    # number of d-digit numbers with distinct digits
    v = 9 * math.perm(9, d - 1)
    return number(str(v), f"Первая цифра — любая кроме нуля: $9$ вариантов; затем $9, 8, \\dots$: $9 \\cdot {' \\cdot '.join(str(9 - i) for i in range(d - 1))} = {v}$.",
                  f"Сколько существует {d}-значных чисел, у которых все цифры различны?")


@tpl("cond_prob")
def _(r):
    n, w = r.choice([(10, 4), (12, 5), (8, 3)])
    p = F(w, n) * F(w - 1, n - 1)
    return number(num(p) if p.denominator in (2, 4, 5, 8, 10, 20, 25, 40, 50) else num(p), L(
        f"$P = \\frac{{{w}}}{{{n}}} \\cdot \\frac{{{w - 1}}}{{{n - 1}}} = {fr(p)}$.",
        f"$P = \\frac{{{w}}}{{{n}}} \\cdot \\frac{{{w - 1}}}{{{n - 1}}} = {fr(p)}$."),
        L(f"В коробке ${n}$ шаров, из них ${w}$ белых. Наугад достают два шара без возвращения. Какова вероятность, что оба белые? Ответ — обыкновенной дробью.",
          f"A box has ${n}$ marbles, ${w}$ of which are white. Two marbles are drawn at random without replacement. What is the probability that both are white?"))


@tpl("statistics", ("ru",))
def _(r):
    xs = r.choice([[3, 7, 7, 10, 13], [2, 4, 9, 9, 11, 13], [5, 6, 6, 8, 15]])
    n = len(xs)
    m = F(sum(xs), n)
    new = r.choice([20, 1])
    m2 = F(sum(xs) + new, n + 1)
    return number(num(m2 - m), f"Среднее было ${fr(m)}$. После добавления ${new}$: $\\frac{{{sum(xs)} + {new}}}{{{n + 1}}} = {fr(m2)}$. Изменение: ${fr(m2 - m)}$.",
                  f"Набор чисел: ${', '.join(map(str, xs))}$. На сколько изменится среднее арифметическое, если добавить число ${new}$? (Рост — положительное число, уменьшение — отрицательное.)")


@tpl("spread", ("ru",))
def _(r):
    xs = r.choice([[2, 4, 6, 8, 10], [1, 3, 5, 7, 9], [4, 6, 8, 10, 12]])
    m = F(sum(xs), len(xs))
    v = sum((x - m) ** 2 for x in xs) / len(xs)
    return number(num(v), f"Среднее ${fr(m)}$. Отклонения: ${', '.join(fr(x - m) for x in xs)}$. Дисперсия — среднее квадратов отклонений: ${fr(v)}$.",
                  f"Найдите дисперсию набора ${', '.join(map(str, xs))}$.")


@tpl("data_read", ("ru",))
def _(r):
    rows = r.choice([[("Пн", 12), ("Вт", 18), ("Ср", 15), ("Чт", 8), ("Пт", 20)], [("Янв", 40), ("Фев", 25), ("Мар", 50), ("Апр", 45)]])
    tab = "\\begin{array}{|" + "c|" * len(rows) + "}\\hline " + " & ".join(f"\\text{{{a}}}" for a, _ in rows) + " \\\\ \\hline " + " & ".join(str(b) for _, b in rows) + " \\\\ \\hline\\end{array}"
    vals = [b for _, b in rows]
    best, worst = max(vals), min(vals)
    p = F(best - worst, worst) * 100
    return number(num(p), f"Наибольшее значение ${best}$, наименьшее ${worst}$. $\\frac{{{best} - {worst}}}{{{worst}}} \\cdot 100\\% = {dec(p)}\\%$.",
                  f"$$ {tab} $$ На сколько процентов наибольшее значение в таблице больше наименьшего?")


@tpl("patterns", ("ru",))
def _(r):
    seq, nxt, why = r.choice([([2, 6, 12, 20, 30], 42, "разности $4, 6, 8, 10$ растут на $2$, следующая разность $12$: $30 + 12 = 42$"),
                              ([1, 2, 6, 24, 120], 720, "каждый член умножается на $2, 3, 4, 5$, дальше на $6$: $120 \\cdot 6 = 720$"),
                              ([3, 5, 9, 17, 33], 65, "$a_{n+1} = 2a_n - 1$: $2 \\cdot 33 - 1 = 65$"),
                              ([1, 4, 9, 16, 25], 36, "квадраты натуральных чисел: $6^2 = 36$"),
                              ([2, 3, 5, 8, 13], 21, "каждое число — сумма двух предыдущих: $8 + 13 = 21$")])
    return number(str(nxt), f"Закономерность: {why}.", f"Найдите следующее число последовательности: ${', '.join(map(str, seq))}, \\dots$")


@tpl("compare", ("ru",))
def _(r):
    a, b, sol, why = r.choice([("2^{30}", "3^{20}", 1, "$2^{30} = 8^{10}$, $3^{20} = 9^{10}$; $8^{10} < 9^{10}$, больше величина Б"),
                               ("\\sqrt{5} + \\sqrt{7}", "\\sqrt{3} + 3", 0, "Возведём в квадрат: $12 + 2\\sqrt{35}$ и $12 + 6\\sqrt3 = 12 + 2\\sqrt{27}$; $\\sqrt{35} > \\sqrt{27}$, больше А"),
                               ("\\log_2 3", "\\log_3 2", 0, "$\\log_2 3 > 1$, а $\\log_3 2 < 1$, больше А"),
                               ("0{,}3^{-2}", "\\left(\\frac{10}{3}\\right)^2", 2, "$0{,}3^{-2} = \\left(\\frac{10}{3}\\right)^2$ — величины равны")])
    opts = ["Величина А больше", "Величина Б больше", "Величины равны", "Недостаточно данных"]
    return {"text": f"Сравните величины. А: ${a}$. Б: ${b}$.", "answer_type": "choice", "options": opts, "correct": str(sol),
            "explanation": why + ".", "difficulty": 3}


@tpl("abs_eq_aibek", ("ru",))
def _(r):
    a = r.choice([4, 9, 16, 25])
    s_ = math.isqrt(a)
    return number(str(2 * s_), f"Квадратное уравнение имеет ровно один корень, когда $D = 0$: $b^2 - 4 \\cdot {a} = 0$, $b = \\pm {2 * s_}$. Наибольшее $b = {2 * s_}$.",
                  f"При каком наибольшем значении параметра $b$ уравнение $x^2 - bx + {a} = 0$ имеет ровно один корень?")


# ---- SAT-only statistics skills (English)

@tpl("scatter", ("en",))
def _(r):
    m, b = r.choice([(F(3, 2), 12), (F(5, 2), 40), (F(4, 5), 7)])
    x = r.choice([10, 20, 30])
    return number(num(m * x + b), f"Substitute $x = {x}$ into the line of best fit: $y = {fr(m)}({x}) + {b} = {num(m * x + b)}$.",
                  f"The line of best fit for a scatterplot is $y = {fr(m)}x + {b}$. According to the line, what is the predicted value of $y$ when $x = {x}$?")


@tpl("inference", ("en",))
def _(r):
    n, k, N = r.choice([(200, 46, 5000), (150, 27, 3000), (400, 92, 12000)])
    return number(str(k * N // n), f"The sample proportion is $\\frac{{{k}}}{{{n}}}$. Estimated count: $\\frac{{{k}}}{{{n}}} \\cdot {N} = {k * N // n}$.",
                  f"In a random sample of {n} students from a school of {N} students, {k} said they bike to school. Based on the sample, what is the best estimate of the number of students at the school who bike to school?")


@tpl("stat_claims", ("en",))
def _(r):
    opts = ["The results can be generalized to all students at the school.",
            "The results can be generalized only to students who volunteered.",
            "Studying causes higher test scores for all students in the city.",
            "No conclusion can be drawn about any group."]
    return {"text": "A researcher selected 300 students at random from one school and found that students who studied at least 5 hours a week had higher average scores. Which conclusion is best supported?",
            "answer_type": "choice", "options": opts, "correct": "0", "difficulty": 3,
            "explanation": "The sample was chosen at random from this school, so the results generalize to the school's students. It was an observational study (no random assignment), so it cannot show causation, and it says nothing about students outside the school."}


@tpl("spread", ("en",))
def _sp_en(r):
    return choice(r, "Data set A", ["Data set B", "They have the same standard deviation", "It cannot be determined"],
                  "Data set A's values are farther from its mean (10 to 50) than data set B's values (28 to 32), so its standard deviation is greater.",
                  "Data set A: 10, 20, 30, 40, 50. Data set B: 28, 29, 30, 31, 32. Which data set has the greater standard deviation?", difficulty=2, math_opts=False)


@tpl("data_read", ("en",))
def _dr_en(r):
    a, b, c = r.choice([(120, 80, 200), (45, 75, 30)])
    tot = a + b + c
    return number(num(F(b, tot) * 100), f"Total $= {a} + {b} + {c} = {tot}$. Percent $= \\frac{{{b}}}{{{tot}}} \\cdot 100 = {num(F(b, tot) * 100)}$.",
                  f"A survey recorded {a} responses for Option X, {b} for Option Y, and {c} for Option Z. What percent of all responses were for Option Y?")


@tpl("cond_prob", ("en",))
def _cp_en(r):
    a, b, c, d = r.choice([(30, 20, 10, 40), (25, 15, 35, 25)])
    return number(num(F(a, a + c)), f"Restrict to the first column: {a + c} people, of whom {a} are in group 1. $P = \\frac{{{a}}}{{{a + c}}} = {fr(F(a, a + c))}$.",
                  f"In a two-way table, group 1 has {a} people who like tea and {b} who do not; group 2 has {c} who like tea and {d} who do not. If a person who likes tea is chosen at random, what is the probability the person is in group 1?")


@tpl("percents", ("en",))
def _pc_en(r):
    p, x = r.choice([(25, 60), (40, 84), (20, 96)])
    orig = F(x * 100, 100 + p)
    return number(num(orig), f"After a {p}% increase the value is ${dec(1 + F(p, 100))}$ times the original: original $= \\frac{{{x}}}{{{dec(1 + F(p, 100))}}} = {num(orig)}$.",
                  f"After a {p}% increase, a price is $\\${x}$. What was the price before the increase?")


@tpl("fractions", ("en",))
def _fr_en(r):
    a, b = r.choice([(F(3, 4), F(2, 3)), (F(5, 6), F(3, 8))])
    return number(num(a / b), f"Divide: ${fr(a)} \\div {fr(b)} = {fr(a)} \\cdot {fr(1 / b)} = {fr(a / b)}$.", f"What is ${fr(a)} \\div {fr(b)}$?")


@tpl("proportions", ("en",))
def _pr_en(r):
    a, b, x = r.choice([(3, 5, 24), (2, 7, 18), (4, 9, 28)])
    return number(num(F(b * x, a)), f"$\\frac{{{a}}}{{{b}}} = \\frac{{{x}}}{{y}}$ gives $y = \\frac{{{b} \\cdot {x}}}{{{a}}} = {num(F(b * x, a))}$.",
                  f"The ratio of boys to girls in a club is ${a} : {b}$. If there are {x} boys, how many girls are there?")


@tpl("abs_value", ("en",))
def _av_en(r):
    a, b = r.choice([(3, 8), (-2, 5)])
    return number(str(abs(a - b)), f"$|{a} - {b}| = |{a - b}| = {abs(a - b)}$.", f"What is the value of $|{a} - {b}|$?")


@tpl("sequences", ("en",))
def _sq_en(r):
    a, q = r.choice([(3, 2), (5, 3)])
    return number(str(a * q ** 5), f"Each term is multiplied by ${q}$: the 6th term is ${a} \\cdot {q}^5 = {a * q ** 5}$.",
                  f"The first term of a sequence is ${a}$, and each term after the first is ${q}$ times the previous term. What is the 6th term?")


@tpl("identities", ("en",))
def _id_en(r):
    a = r.choice([3, 5, 7])
    return choice(r, f"x^2 - {a * a}", [f"x^2 + {a * a}", f"x^2 - {2 * a}x + {a * a}", f"x^2 - {a}"],
                  f"$(x - {a})(x + {a})$ is a difference of squares: $x^2 - {a * a}$.", f"Which expression is equivalent to $(x - {a})(x + {a})$?", difficulty=2)


@tpl("rational_expr", ("en",))
def _re_en(r):
    a = r.choice([2, 3, 4])
    return choice(r, f"\\frac{{1}}{{x + {a}}}", [f"\\frac{{1}}{{x - {a}}}", f"x + {a}", f"\\frac{{x}}{{x + {a}}}"],
                  f"$\\frac{{x - {a}}}{{x^2 - {a * a}}} = \\frac{{x - {a}}}{{(x - {a})(x + {a})}} = \\frac{{1}}{{x + {a}}}$ for $x \\ne {a}$.",
                  f"For $x > {a}$, which expression is equivalent to $\\dfrac{{x - {a}}}{{x^2 - {a * a}}}$?", difficulty=2)


@tpl("inequalities", ("en",))
def _ie_en(r):
    a, b = r.choice([(3, 14), (5, 27), (4, 30)])
    k = (b - 1) // a
    return number(str(k), f"${a}x + 1 \\le {b}$ gives $x \\le {fr(F(b - 1, a))}$, so the greatest integer is ${k}$.",
                  f"What is the greatest integer $x$ that satisfies ${a}x + 1 \\le {b}$?")


@tpl("systems_nl", ("ru",))
def _snl_ru(r):
    k = r.choice([1, 2, 3])
    # y = x^2, y = 2x + k  -> x^2 - 2x - k = 0, number of intersection points
    D = 4 + 4 * k
    return number("2", f"Подставляем: $x^2 = 2x + {k}$, $x^2 - 2x - {k} = 0$, $D = 4 + {4 * k} = {D} > 0$ — два корня, значит две точки пересечения.",
                  f"Сколько общих точек имеют парабола $y = x^2$ и прямая $y = 2x + {k}$?")


@tpl("triangle_area", ("en",))
def _ta_en(r):
    a, b = r.choice([(8, 10), (6, 14)])
    return number(str(a * b // 4), f"Area $= \\frac12 ab \\sin 30^\\circ = \\frac12 \\cdot {a} \\cdot {b} \\cdot \\frac12 = {a * b // 4}$.",
                  f"Two sides of a triangle have lengths ${a}$ and ${b}$, and the angle between them is $30^\\circ$. What is the area of the triangle?")


@tpl("similarity", ("en",))
def _sim_en(r):
    a, b, c = r.choice([(4, 6, 10), (3, 9, 7)])
    return number(num(F(b * c, a)), f"Corresponding sides are proportional: $\\frac{{{b}}}{{{a}}} = \\frac{{x}}{{{c}}}$, so $x = {num(F(b * c, a))}$.",
                  f"Triangle $ABC$ is similar to triangle $DEF$. $AB = {a}$, $DE = {b}$, and $BC = {c}$. What is $EF$?")


@tpl("circle_eq", ("ru",))
def _ce2(r):
    a, b, R = r.choice([(3, 4, 5), (6, 8, 10)])
    return number(str(R * R), "Окружность с центром в начале координат, проходящая через $(%d; %d)$, имеет $R^2 = %d^2 + %d^2 = %d$." % (a, b, a, b, R * R),
                  f"Окружность с центром в начале координат проходит через точку $({a}; {b})$. Её уравнение $x^2 + y^2 = c$. Найдите $c$.")


@tpl("line_eq", ("en",))
def _le_en(r):
    (x1, y1), (x2, y2) = r.choice([((1, 3), (3, 7)), ((-2, 5), (2, -3))])
    m = F(y2 - y1, x2 - x1)
    c = y1 - m * x1
    return number(num(c), f"Slope $= \\frac{{{y2} - {y1}}}{{{x2} - {x1}}} = {fr(m)}$. Then $b = {y1} - ({fr(m)})({x1}) = {fr(c)}$.".replace("- -", "+ "),
                  f"A line passes through $({x1}, {y1})$ and $({x2}, {y2})$. What is the $y$-intercept of the line?")


@tpl("graphs", ("ru",))
def _gr_ru(r):
    a, b = r.choice([(2, -3), (-1, 5)])
    c, d = r.choice([(1, 1), (3, -2)])
    x = F(d - b, a - c)
    return number(num(a * x + b), f"Точка пересечения: ${a}x {'+' if b > 0 else '-'} {abs(b)} = {c}x {'+' if d > 0 else '-'} {abs(d)}$, $x = {fr(x)}$, $y = {fr(a * x + b)}$.",
                  f"Найдите ординату точки пересечения графиков $y = {a}x {'+' if b > 0 else '-'} {abs(b)}$ и $y = {c if c != 1 else ''}x {'+' if d > 0 else '-'} {abs(d)}$.")


@tpl("trig_values", ("ru",))
def _tv_ru(r):
    return number("2", "$\\sin^2 30^\\circ + \\cos^2 30^\\circ = 1$ и $\\operatorname{tg}^2 45^\\circ = 1$, сумма $2$.",
                  "Вычислите $\\sin^2 30^\\circ + \\cos^2 30^\\circ + \\operatorname{tg}^2 45^\\circ$.", difficulty=2)


@tpl("divisibility", ("ru",))
def _dv2(r):
    a = r.choice([12, 18, 20])
    b = r.choice([30, 45])
    l = a * b // math.gcd(a, b)
    return number(str(l), f"Ищем НОК$({a}; {b}) = {l}$: через это время события совпадут впервые.",
                  f"Один автобус отходит каждые ${a}$ минут, другой — каждые ${b}$ минут. Они отошли одновременно. Через сколько минут они снова отойдут одновременно?", difficulty=2)



# ------------------------------------------------------------------ more skills

@tpl("powers_frac", ("ru",))
def _pf_ru(r):
    a, p, q = r.choice([(8, 2, 3), (27, 4, 3), (16, 3, 4), (32, 2, 5), (125, 2, 3)])
    root = round(a ** (1 / q))
    b = r.choice([4, 9, 25])
    v = root ** p * F(1, math.isqrt(b))
    return number(num(v), f"${a}^{{\\frac{{{p}}}{{{q}}}}} = (\\sqrt[{q}]{{{a}}})^{p} = {root ** p}$, ${b}^{{-\\frac12}} = \\frac{{1}}{{{math.isqrt(b)}}}$. Произведение: ${fr(v)}$.",
                  f"Вычислите ${a}^{{\\frac{{{p}}}{{{q}}}}} \\cdot {b}^{{-\\frac{{1}}{{2}}}}$.")


@tpl("word_mix", ("ru",))
def _wm(r):
    m1, p1, m2, p2 = r.choice([(4, 15, 6, 40), (3, 10, 7, 30), (5, 20, 5, 60), (2, 30, 8, 5)])
    c = F(m1 * p1 + m2 * p2, m1 + m2)
    return number(num(c), f"Масса вещества: ${m1} \\cdot {dec(F(p1, 100))} + {m2} \\cdot {dec(F(p2, 100))} = {dec(F(m1 * p1 + m2 * p2, 100))}$ кг из ${m1 + m2}$ кг. Концентрация: ${dec(c)}\\%$.",
                  f"Смешали ${m1}$ кг ${p1}\\%$-го раствора соли и ${m2}$ кг ${p2}\\%$-го раствора. Какова концентрация (в процентах) полученного раствора?")


@tpl("word_mix", ("ru",))
def _wm2(r):
    m, p, q = r.choice([(10, 30, 20), (12, 25, 15), (8, 40, 25)])
    w = F(m * p, q) - m
    return number(num(w), f"Соли ${m} \\cdot {dec(F(p, 100))} = {dec(F(m * p, 100))}$ кг, её количество не меняется. Новая масса $\\frac{{{dec(F(m * p, 100))}}}{{{dec(F(q, 100))}}} = {dec(F(m * p, q))}$ кг, воды добавили ${dec(w)}$ кг.",
                  f"Сколько килограммов воды нужно добавить к ${m}$ кг ${p}\\%$-го раствора соли, чтобы получить ${q}\\%$-й раствор?")


@tpl("linear_fn", ("ru",))
def _lf(r):
    (x1, y1), (x2, y2) = r.choice([((1, 4), (3, 10)), ((-2, 7), (2, -1)), ((0, -3), (4, 5))])
    k = F(y2 - y1, x2 - x1)
    b = y1 - k * x1
    x0 = -b / k
    return number(num(x0), f"$k = \\frac{{{y2} - ({y1})}}{{{x2} - ({x1})}} = {fr(k)}$, $b = {y1} - ({fr(k)}) \\cdot ({x1}) = {fr(b)}$. Пересечение с $Ox$: $y = 0$, $x = -\\frac{{b}}{{k}} = {fr(x0)}$.",
                  f"График линейной функции проходит через точки $({x1}; {y1})$ и $({x2}; {y2})$. Найдите абсциссу точки его пересечения с осью $Ox$.")


@tpl("parabola", ("ru",))
def _pb(r):
    a, b, c = r.choice([(1, -6, 5), (2, 8, 3), (-1, 4, 1), (3, -12, 7)])
    x0 = F(-b, 2 * a)
    y0 = a * x0 * x0 + b * x0 + c
    return number(num(x0 + y0), f"Вершина: $x_0 = -\\frac{{b}}{{2a}} = {fr(x0)}$, $y_0 = {fr(y0)}$. Сумма координат: ${fr(x0 + y0)}$.",
                  f"Найдите сумму координат вершины параболы $y = {a if a not in (1, -1) else ('-' if a == -1 else '')}x^2 {'+' if b > 0 else '-'} {abs(b)}x {'+' if c > 0 else '-'} {abs(c)}$.")


@tpl("power_fn", ("ru",))
def _pw(r):
    k, b = r.choice([(6, 1), (12, -2), (8, 2)])
    # y = k/x + b passes through (2, ...) ; value at x = 4
    return number(num(F(k, 4) + b), f"$y = \\frac{{{k}}}{{x}} {'+' if b > 0 else '-'} {abs(b)}$; при $x = 4$: $\\frac{{{k}}}{{4}} {'+' if b > 0 else '-'} {abs(b)} = {fr(F(k, 4) + b)}$.",
                  f"График функции $y = \\dfrac{{k}}{{x}} {'+' if b > 0 else '-'} {abs(b)}$ проходит через точку $(2; {fr(F(k, 2) + b)})$. Найдите значение функции при $x = 4$.")


@tpl("trig_identities", ("ru",))
def _ti(r):
    s_, c_ = r.choice([(F(3, 5), F(-4, 5)), (F(5, 13), F(-12, 13)), (F(8, 17), F(-15, 17))])
    v = 2 * s_ * c_
    return number(num(v), f"Угол во II четверти, косинус отрицателен: $\\cos\\alpha = -\\sqrt{{1 - ({fr(s_)})^2}} = {fr(c_)}$. $\\sin 2\\alpha = 2\\sin\\alpha\\cos\\alpha = {fr(v)}$.",
                  f"Известно, что $\\sin\\alpha = {fr(s_)}$ и $\\dfrac{{\\pi}}{{2}} < \\alpha < \\pi$. Найдите $\\sin 2\\alpha$.")


@tpl("trig_identities", ("ru",))
def _ti2(r):
    t = r.choice([2, 3, F(1, 2)])
    v = (t - 1) / (t + 1)
    return number(num(v), f"Делим числитель и знаменатель на $\\cos\\alpha$: $\\frac{{\\operatorname{{tg}}\\alpha - 1}}{{\\operatorname{{tg}}\\alpha + 1}} = \\frac{{{fr(t)} - 1}}{{{fr(t)} + 1}} = {fr(v)}$.",
                  f"Известно, что $\\operatorname{{tg}}\\alpha = {fr(t)}$. Найдите $\\dfrac{{\\sin\\alpha - \\cos\\alpha}}{{\\sin\\alpha + \\cos\\alpha}}$.")


@tpl("tangent", ("ru",))
def _tg(r):
    a, b, x0 = r.choice([(1, -3, 2), (2, 1, 1), (1, 4, -1)])
    # f = a x^2 + b x ; tangent at x0: y = f'(x0)(x - x0) + f(x0); ask y-intercept
    f0, d = a * x0 * x0 + b * x0, 2 * a * x0 + b
    c = f0 - d * x0
    return number(str(c), f"$f'(x) = {2 * a}x {'+' if b > 0 else '-'} {abs(b)}$, $f'({x0}) = {d}$, $f({x0}) = {f0}$. Касательная: $y = {d}(x - ({x0})) + ({f0})$; при $x = 0$: $y = {c}$.",
                  f"Найдите ординату точки пересечения с осью $Oy$ касательной к графику $f(x) = {a if a != 1 else ''}x^2 {'+' if b > 0 else '-'} {abs(b)}x$ в точке $x_0 = {x0}$.")


@tpl("poly_ops", ("en",))
def _po_en(r):
    a, b = r.choice([(3, 2), (2, 5), (4, 1)])
    return choice(r, f"{a}x^2 + {a * b + 1}x + {b}", [f"{a}x^2 + {a + b}x + {b}", f"{a}x^2 + {a * b}x + {b}", f"{a + 1}x^2 + {b}x + {b}"],
                  f"Expand: $({a}x + 1)(x + {b}) = {a}x^2 + {a * b}x + x + {b} = {a}x^2 + {a * b + 1}x + {b}$.",
                  f"Which expression is equivalent to $({a}x + 1)(x + {b})$?")


@tpl("systems", ("en",))
def _sy_en(r):
    x, y = r.choice([(3, 2), (5, -1), (4, 7)])
    return number(str(x + y), f"Add the equations to eliminate $y$: $2x = {2 * x}$, so $x = {x}$ and $y = {y}$. Then $x + y = {x + y}$.",
                  f"If $x + y = {x + y}$... ".replace(f"If $x + y = {x + y}$... ", "") + f"$x + y = {x + y}$ and $x - y = {x - y}$. What is the value of $xy$?") if False else \
        number(str(x * y), f"Add the equations: $2x = {2 * x}$, so $x = {x}$; then $y = {y}$ and $xy = {x * y}$.",
               f"If $x + y = {x + y}$ and $x - y = {x - y}$, what is the value of $xy$?")


@tpl("word_problems", ("en",))
def _wp_en(r):
    p, a, h = r.choice([(12, 3, 40), (15, 5, 60), (20, 4, 90)])
    return number(str(h // 1), f"Cost $= {p} + {a}h$. Setting ${p} + {a}h = {p + a * h}$ gives $h = {h}$.",
                  f"A plumber charges a $\\${p}$ fee plus $\\${a}$ per minute. A job cost $\\${p + a * h}$. How many minutes did the job take?")


@tpl("exp_fn", ("en",))
def _ex_en(r):
    a, p, t = r.choice([(500, 2, 3), (1000, F(1, 2), 4), (80, 3, 2)])
    v = a * F(p) ** t
    return number(num(v), f"$f({t}) = {a}({fr(p)})^{t} = {num(v)}$.",
                  f"The function $f(t) = {a}({fr(p)})^t$ models a quantity after $t$ years. What is $f({t})$?")


@tpl("angles", ("en",))
def _an_en(r):
    x = r.choice([25, 35, 40])
    return number(str(180 - 2 * x - x), f"The angles $x$, $2x$ and the third angle form a straight line... no — they are angles of a triangle: $x + 2x + y = 180$, so $y = 180 - {3 * x} = {180 - 3 * x}$." if False else
                  f"The three angles of a triangle sum to $180^\\circ$: $y = 180 - {x} - {2 * x} = {180 - 3 * x}$.",
                  f"In a triangle, one angle measures ${x}^\\circ$ and a second angle is twice the first. What is the measure, in degrees, of the third angle?")


@tpl("right_trig", ("en",))
def _rt_en(r):
    a, b, c = r.choice([(3, 4, 5), (5, 12, 13), (8, 15, 17)])
    return number(num(F(a, b)), f"$\\sin A = \\frac{{{a}}}{{{c}}}$ means the opposite side is ${a}$ and the hypotenuse ${c}$, so the adjacent side is ${b}$ and $\\tan A = \\frac{{{a}}}{{{b}}}$.",
                  f"In right triangle $ABC$, $\\sin A = \\dfrac{{{a}}}{{{c}}}$. What is $\\tan A$?")


@tpl("probability", ("en",))
def _pb_en(r):
    r_, b_, g_ = r.choice([(4, 6, 10), (3, 5, 12), (7, 8, 5)])
    tot = r_ + b_ + g_
    return number(num(F(r_ + b_, tot)), f"Favorable: ${r_} + {b_} = {r_ + b_}$ of ${tot}$. $P = {fr(F(r_ + b_, tot))}$.",
                  f"A bag has {r_} red, {b_} blue, and {g_} green marbles. If one marble is chosen at random, what is the probability it is not green?")


@tpl("statistics", ("en",))
def _st_en(r):
    xs = r.choice([[4, 8, 8, 10, 15], [2, 5, 9, 9, 10]])
    n, m = len(xs), F(sum(xs), len(xs))
    new = r.choice([30, 35])
    med = sorted(xs + [new])
    return number(num(F(med[2] + med[3], 2)), f"Sorted with {new}: ${', '.join(map(str, med))}$. With six values the median is the mean of the 3rd and 4th: $\\frac{{{med[2]} + {med[3]}}}{{2}} = {num(F(med[2] + med[3], 2))}$.",
                  f"The data set ${', '.join(map(str, xs))}$ has a value of ${new}$ added. What is the median of the new data set?")



@tpl("data_read", ("ru",))
def _dr2(r):
    rows = r.choice([[("Математика", 24), ("Физика", 18), ("Химия", 12), ("Биология", 6)], [("Бишкек", 45), ("Ош", 30), ("Каракол", 15), ("Нарын", 10)]])
    tab = "\\begin{array}{|l|c|}\\hline " + " \\\\ \\hline ".join(f"\\text{{{a}}} & {b}" for a, b in rows) + " \\\\ \\hline\\end{array}"
    tot = sum(b for _, b in rows)
    a, b = rows[0]
    return number(num(F(b, tot) * 100), f"Всего ${' + '.join(str(v) for _, v in rows)} = {tot}$. Доля «{a}»: $\\frac{{{b}}}{{{tot}}} \\cdot 100\\% = {dec(F(b, tot) * 100)}\\%$.",
                  f"$$ {tab} $$ Какой процент от общего числа составляет строка «{a}»?")


@tpl("data_read", ("ru",))
def _dr3(r):
    vals = r.choice([[12, 15, 9, 18, 21, 15], [30, 28, 35, 40, 32, 45]])
    m = F(sum(vals), len(vals))
    above = sum(1 for v in vals if v > m)
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]
    tab = "\\begin{array}{|" + "c|" * 6 + "}\\hline " + " & ".join(f"\\text{{{d}}}" for d in days) + " \\\\ \\hline " + " & ".join(map(str, vals)) + " \\\\ \\hline\\end{array}"
    return number(str(above), f"Среднее: $\\frac{{{sum(vals)}}}{{6}} = {dec(m)}$. Больше среднего: {above} дн.",
                  f"$$ {tab} $$ В скольких днях значение было больше среднего за неделю?")


@tpl("stat_claims", ("en",))
def _sc_en2(r):
    opts = ["Only that the new method is associated with higher scores among volunteers; it cannot be generalized or shown to be the cause.",
            "The new method causes higher scores for all students in the country.",
            "The new method causes higher scores for the volunteers only.",
            "The new method has no effect on scores."]
    return {"text": "A teacher asked for volunteers to try a new study method. Volunteers who used it scored higher on average than students who did not. Which conclusion is appropriate?",
            "answer_type": "choice", "options": opts, "correct": "0", "difficulty": 3,
            "explanation": "The students were volunteers (not a random sample), so results cannot be generalized, and they chose the method themselves (no random assignment), so causation cannot be concluded."}


@tpl("stat_claims", ("en",))
def _sc_en3(r):
    opts = ["Students were randomly assigned, so the program likely caused the improvement for students like those in the study.",
            "The results apply to every school in the world.",
            "Nothing can be concluded because the sample is too large.",
            "The improvement must be due to chance."]
    return {"text": "Researchers randomly selected 200 students from a district and randomly assigned half of them to a tutoring program. The tutored group improved more on average. Which conclusion is best supported?",
            "answer_type": "choice", "options": opts, "correct": "0", "difficulty": 3,
            "explanation": "Random assignment supports a cause-and-effect conclusion, and random selection from the district lets the result generalize to students in that district."}


# ------------------------------------------------------------------ build

RU_EXAMS = ["ORT", "ENT", "EGE", "OGE", "CSCA"]


def _tidy(t):
    """1x -> x, 1i -> i, "+ -3" -> "- 3" (coefficients written by the templates)."""
    import re
    t = re.sub(r"([ (+\-])1([xi])(?![\w^{])", r"\1\2", t)
    return t.replace("+ -", "- ").replace("- -", "+ ")


def build(skill_exams, need_ru, need_en, per_ru=5, per_en=4):
    """skill_exams: {code: [exams]}; need_*: skills to fill. Returns the pack dict."""
    global LANG
    rng = random.Random(2026)
    by_code = {}
    for fn_name, (fn, langs) in _ALL:
        by_code.setdefault(fn_name, []).append((fn, langs))
    questions, seen = [], set()
    for lang, need, per in (("ru", need_ru, per_ru), ("en", need_en, per_en)):
        LANG = lang
        for code in need:
            fns = [f for f, langs in by_code.get(code, []) if lang in langs]
            if not fns:
                continue
            made, tries = 0, 0
            while made < per and tries < per * 12:
                tries += 1
                fn = fns[made % len(fns)] if tries <= per else rng.choice(fns)
                q = fn(rng)
                if not q or not q.get("text") or q["text"] in seen:
                    continue
                seen.add(q["text"])
                exams = [e for e in skill_exams.get(code, []) if (e != "SAT" if lang == "ru" else e in ("SAT", "CSCA"))]
                if not exams:
                    continue
                made += 1
                q.update({"id": f"mp26_{lang}_{code}_{made}", "skill": code, "language": lang, "exams": exams, "tags": [],
                          "image": None, "source": {"book": "Monday", "where": "practice"}})
                q.setdefault("difficulty", 3)
                for key in ("text", "explanation"):
                    q[key] = _tidy(q[key])
                if q.get("options"):
                    q["options"] = [_tidy(o) for o in q["options"]]
                questions.append(q)
    return {"id": "monday_practice_2026", "title": "Monday — тренировочные задачи повышенной сложности", "exam": "ORT",
            "language": "ru", "collections": [], "questions": questions}




def main():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from collections import Counter
    from app import app
    from monday.models import ContentNode, Question
    with app.app_context():
        nodes = [n for n in ContentNode.query.filter_by(archived=False).all() if n.level == "node" and n.code]
        qs = [q for q in Question.query.filter_by(status="published").all() if q.answer_type != "written" and q.source != "monday_practice_2026"]
        ru = Counter(q.skill.code for q in qs if q.skill and (q.language or "ru") == "ru")
        en = Counter(q.skill.code for q in qs if q.skill and q.language == "en")
        exams = {n.code: list(n.exams or []) for n in nodes}
    need_ru = [c for c, ex in exams.items() if [e for e in ex if e != "SAT"] and ru[c] < 8]
    need_en = [c for c, ex in exams.items() if "SAT" in ex and en[c] < 8]
    pack = build(exams, need_ru, need_en)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=1)
    by = Counter((q["language"], q["skill"]) for q in pack["questions"])
    print(len(pack["questions"]), "questions;", "ru skills", len({s for l, s in by if l == "ru"}), "en skills", len({s for l, s in by if l == "en"}))
    print("ru needed but no template:", [c for c in need_ru if ("ru", c) not in by])
    print("en needed but no template:", [c for c in need_en if ("en", c) not in by])


if __name__ == "__main__":
    main()

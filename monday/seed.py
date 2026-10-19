"""Demo data so every page has something real to show.

Accounts (all created on first run):
    admin@monday.kg    / monday2026   — admin (you)
    aibek@monday.kg    / teacher123   — teacher with a full student table
    student@monday.kg  / student123   — student "Тима", ORT, lots of history
    new.teacher@monday.kg / teacher123 — teacher waiting for approval

All maths questions are generated with their answers computed, so the
answer keys are correct.
"""
import math
import os
import random
from datetime import date, datetime, timedelta
from fractions import Fraction

from flask import current_app

from .extensions import db
from .models import utcnow
from .models import (Assignment, Attempt, AttemptAnswer, Question, Skill, StudentProfile, StudentRecord, User,
                     Work, new_invite_code)
from .services import grade_version_attempt, next_monday_test_start, publish_work, week_start

ALL = ["ORT", "ENT", "EGE", "OGE", "SAT", "CSCA"]
NO_SAT = ["ORT", "ENT", "EGE", "OGE", "CSCA"]
ADV = ["ORT", "ENT", "EGE", "CSCA"]

SKILLS = [
    # topic, code, name, exams
    ("Арифметика", "fractions", "Дроби", ALL),
    ("Арифметика", "percents", "Проценты", ALL),
    ("Арифметика", "proportions", "Пропорции", ALL),
    ("Арифметика", "divisibility", "Делимость и НОК", NO_SAT),
    ("Арифметика", "powers_int", "Степени с целым показателем", ALL),
    ("Алгебра", "linear_eq", "Линейные уравнения", ALL),
    ("Алгебра", "quadratic", "Квадратные уравнения", ALL),
    ("Алгебра", "systems", "Системы уравнений", ALL),
    ("Алгебра", "identities", "Формулы сокращённого умножения", NO_SAT),
    ("Алгебра", "inequalities", "Неравенства", ALL),
    ("Алгебра", "word_problems", "Текстовые задачи", ALL),
    ("Степени и логарифмы", "log_def", "Определение логарифма", ADV),
    ("Степени и логарифмы", "log_props", "Свойства логарифмов", ADV),
    ("Степени и логарифмы", "log_eq", "Логарифмические уравнения", ["ORT", "ENT", "EGE"]),
    ("Степени и логарифмы", "exp_eq", "Показательные уравнения", ADV),
    ("Функции", "linear_fn", "Линейная функция", ALL),
    ("Функции", "parabola", "Парабола", ALL),
    ("Функции", "graphs", "Значение функции", ALL),
    ("Функции", "domain", "Область определения", ADV),
    ("Функции", "derivative", "Производная", ["ENT", "EGE", "CSCA"]),
    ("Геометрия", "angles", "Углы треугольника", ALL),
    ("Геометрия", "triangle_area", "Площадь треугольника", ALL),
    ("Геометрия", "pythagoras", "Теорема Пифагора", ALL),
    ("Геометрия", "circle", "Окружность", ALL),
    ("Геометрия", "quadrilaterals", "Четырёхугольники", ALL),
    ("Геометрия", "volumes", "Объёмы тел", ["ORT", "ENT", "EGE", "SAT"]),
    ("Логика и данные", "compare", "Сравнение величин", ["ORT"]),
    ("Логика и данные", "sequences", "Прогрессии", ALL),
    ("Логика и данные", "probability", "Вероятность", ALL),
    ("Логика и данные", "statistics", "Среднее значение", ALL),
    ("Тригонометрия", "trig_values", "Значения тригонометрических функций", ["ENT", "EGE", "SAT", "CSCA"]),
]


SUBTOPICS = {
    "fractions": "Дроби и проценты", "percents": "Дроби и проценты", "proportions": "Дроби и проценты",
    "divisibility": "Числа и степени", "powers_int": "Числа и степени",
    "linear_eq": "Уравнения", "quadratic": "Уравнения", "systems": "Уравнения",
    "identities": "Выражения и неравенства", "inequalities": "Выражения и неравенства",
    "word_problems": "Текстовые задачи",
    "log_def": "Логарифмы", "log_props": "Логарифмы", "log_eq": "Логарифмы", "exp_eq": "Показательные уравнения",
    "linear_fn": "Графики функций", "parabola": "Графики функций", "graphs": "Графики функций",
    "domain": "Исследование функций", "derivative": "Исследование функций",
    "angles": "Треугольники", "triangle_area": "Площади фигур", "pythagoras": "Треугольники",
    "circle": "Площади фигур", "quadrilaterals": "Площади фигур", "volumes": "Стереометрия",
    "compare": "Сравнение величин", "sequences": "Прогрессии",
    "probability": "Вероятность и статистика", "statistics": "Вероятность и статистика",
    "trig_values": "Тригонометрические функции",
}


def build_tree(owner=None):
    """The master skill map (taxonomy.MASTER). Returns {code: node}."""
    from .taxonomy import ensure_taxonomy
    ensure_taxonomy(force=True)
    return {n.code: n for n in Skill.query.filter(Skill.level == "node", Skill.code.isnot(None)).all()}


# --------------------------------------------------------------------------- helpers


def _xterm(k):
    """Linear term written the way a teacher would: −x, + 3x, nothing for 0 (never "1x")."""
    if k == 0:
        return ""
    sign = "+" if k > 0 else "-"
    return f"{sign} x" if abs(k) == 1 else f"{sign} {abs(k)}x"


def _fmt(v):
    if isinstance(v, Fraction):
        if v.denominator == 1:
            return str(v.numerator)
        sign = "-" if v < 0 else ""
        return f"${sign}\\frac{{{abs(v.numerator)}}}{{{v.denominator}}}$"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def _distractors(correct, extra=()):
    """Three plausible wrong answers for a numeric correct value."""
    c = correct
    pool = list(extra)
    if isinstance(c, Fraction):
        pool += [c + 1, c * 2, Fraction(c.denominator, c.numerator) if c else Fraction(1), c - Fraction(1, 2)]
    else:
        pool += [c + 1, c - 1, c * 2, c + 2, c - 2, c + 10]
    out = []
    for p in pool:
        if p != c and p not in out and (not isinstance(p, (int, float)) or p >= 0 or c < 0):
            out.append(p)
        if len(out) == 3:
            break
    return out


def _choice(text, correct, explanation, wrong=None, rng=None):
    rng = rng or random
    candidates = list(wrong or []) + _distractors(correct)
    seen = {_fmt(correct)}
    picked = []
    for w in candidates:  # unique wrong options, never equal to the right one
        if _fmt(w) not in seen:
            seen.add(_fmt(w))
            picked.append(w)
        if len(picked) == 3:
            break
    opts = [_fmt(correct)] + [_fmt(w) for w in picked]
    rng.shuffle(opts)
    return {"text": text, "answer_type": "choice", "options": opts,
            "correct": str(opts.index(_fmt(correct))), "explanation": explanation}


def _number(text, correct, explanation):
    return {"text": text, "answer_type": "number", "options": [], "correct": _fmt(correct),
            "explanation": explanation}


# --------------------------------------------------------------------------- generators


def gen_questions(rng):
    """Yields (skill_code, difficulty, question_dict, image_spec_or_None)."""
    # fractions
    for a, b, c, d in [(1, 2, 1, 3), (3, 4, 1, 6), (2, 5, 3, 10)]:
        r = Fraction(a, b) + Fraction(c, d)
        yield "fractions", 1, _choice(
            f"Вычислите: $\\frac{{{a}}}{{{b}}} + \\frac{{{c}}}{{{d}}}$", r,
            f"Приводим к общему знаменателю: $\\frac{{{a}}}{{{b}}} + \\frac{{{c}}}{{{d}}} = {_fmt(r).strip('$')}$.",
            rng=rng), None
    # percents
    for p, n in [(15, 240), (35, 80), (120, 45)]:
        r = p * n // 100 if p * n % 100 == 0 else p * n / 100
        yield "percents", 1 if p < 100 else 2, _choice(
            f"Найдите {p}% от числа {n}.", r, f"{p}% от {n} = ${n} \\cdot {p} / 100 = {_fmt(r)}$.", rng=rng), None
    yield "percents", 2, _number(
        "Цена товара была 800 сом, затем её снизили на 25%. Какой стала цена (в сомах)?", 600,
        "Снижение на 25%: $800 \\cdot 0{,}75 = 600$.") , None
    # proportions
    for k, cost, m in [(3, 45, 7), (4, 120, 9)]:
        r = cost // k * m
        yield "proportions", 1, _choice(
            f"{k} тетради стоят {cost} сом. Сколько стоят {m} таких тетрадей?", r,
            f"Одна тетрадь: ${cost} : {k} = {cost // k}$ сом, значит ${m}$ штук: ${cost // k} \\cdot {m} = {r}$.",
            rng=rng), None
    # divisibility
    for a, b in [(6, 8), (12, 18), (9, 15)]:
        r = a * b // math.gcd(a, b)
        yield "divisibility", 2, _choice(
            f"Найдите наименьшее натуральное число, которое делится и на {a}, и на {b}.", r,
            f"Это НОК({a}, {b}) $= {r}$.", wrong=[a * b, math.gcd(a, b), r + a], rng=rng), None
    # powers
    for a, b, c in [(5, 3, 4), (7, 2, 6)]:
        r = 2 ** (a + b - c)
        yield "powers_int", 1, _choice(
            f"Вычислите: $\\frac{{2^{{{a}}} \\cdot 2^{{{b}}}}}{{2^{{{c}}}}}$", r,
            f"$2^{{{a}+{b}-{c}}} = 2^{{{a + b - c}}} = {r}$.", rng=rng), None
    # linear equations
    for a, b, x in [(3, 7, 5), (4, -6, 3), (5, 12, -2)]:
        c = a * x + b
        bs = f"+ {b}" if b >= 0 else f"- {abs(b)}"
        yield "linear_eq", 1, _choice(f"Решите уравнение: ${a}x {bs} = {c}$", x,
                                      f"${a}x = {c - b}$, откуда $x = {x}$.", rng=rng), None
    # quadratic
    for r1, r2 in [(2, 5), (-3, 4), (1, 6)]:
        s, p = r1 + r2, r1 * r2
        bs = _xterm(-s)
        ps = f"+ {p}" if p >= 0 else f"- {abs(p)}"
        yield "quadratic", 2, _choice(
            f"Найдите больший корень уравнения $x^2 {bs} {ps} = 0$.", max(r1, r2),
            f"По теореме Виета корни $x_1 = {r1}$, $x_2 = {r2}$. Больший: ${max(r1, r2)}$.",
            wrong=[min(r1, r2), s, p], rng=rng), None
    yield "quadratic", 3, _number("Найдите сумму квадратов корней уравнения $x^2 - 7x + 10 = 0$.", 29,
                                  "Корни 2 и 5: $4 + 25 = 29$. Или: $(x_1+x_2)^2 - 2x_1x_2 = 49 - 20 = 29$."), None
    # systems
    for x, y in [(7, 3), (5, -2)]:
        yield "systems", 2, _choice(
            f"Решите систему: $x + y = {x + y}$, $x - y = {x - y}$. Найдите $x$.", x,
            f"Складываем уравнения: $2x = {2 * x}$, значит $x = {x}$.", rng=rng), None
    # identities
    for a, b in [(53, 47), (101, 99)]:
        r = (a + b) ** 2 - (a - b) ** 2
        yield "identities", 2, _number(f"Вычислите: $({a}+{b})^2 - ({a}-{b})^2$.", r,
                                       f"$(a+b)^2-(a-b)^2 = 4ab = 4 \\cdot {a} \\cdot {b} = {r}$."), None
    yield "identities", 1, _number("Вычислите: $57^2 - 43^2$.", 1400,
                                   "$a^2 - b^2 = (a-b)(a+b) = 14 \\cdot 100 = 1400$."), None
    # inequalities
    for a, b, c in [(3, 5, 7), (2, 9, 4)]:
        # a x - b > c  → x > (b + c)/a, smallest integer
        bound = Fraction(b + c, a)
        r = math.floor(bound) + 1
        yield "inequalities", 2, _choice(
            f"Найдите наименьшее целое решение неравенства ${a}x - {b} > {c}$.", r,
            f"${a}x > {b + c}$, $x > {_fmt(bound).strip('$')}$. Наименьшее целое: ${r}$.", rng=rng), None
    # word problems
    yield "word_problems", 2, _number(
        "Поезд прошёл 360 км за 4 часа. С какой скоростью (км/ч) он шёл?", 90, "$v = 360 : 4 = 90$ км/ч."), None
    yield "word_problems", 3, _choice(
        "Два рабочих выполняют работу за 6 часов. Первый один сделал бы её за 10 часов. За сколько часов сделает её второй?",
        15, "Производительность второго: $\\frac16 - \\frac1{10} = \\frac1{15}$, значит 15 часов.",
        wrong=[4, 16, 8], rng=rng), None
    # logarithms
    for base, val in [(2, 32), (3, 81), (5, 125)]:
        r = round(math.log(val, base))
        yield "log_def", 1, _choice(f"Вычислите: $\\log_{{{base}}} {val}$", r,
                                    f"${base}^{{{r}}} = {val}$, значит $\\log_{{{base}}} {val} = {r}$.", rng=rng), None
    for base, a, b in [(2, 48, 3), (3, 54, 2), (6, 4, 9)]:
        if base == 6:
            r = 2
            yield "log_props", 2, _choice(
                "Вычислите: $\\log_{6} 4 + \\log_{6} 9$", r,
                "Сумма логарифмов — логарифм произведения: $\\log_6 36 = 2$.", rng=rng), None
            continue
        r = round(math.log(a / b, base))
        yield "log_props", 2, _choice(
            f"Вычислите: $\\log_{{{base}}} {a} - \\log_{{{base}}} {b}$", r,
            f"Разность логарифмов — логарифм частного: $\\log_{{{base}}} ({a} : {b}) = \\log_{{{base}}} {a // b} = {r}$.",
            wrong=[r + 2, round(math.log(a, base), 1), a - b], rng=rng), None
    for base, k, shift in [(2, 3, 1), (3, 2, -2)]:
        x = base ** k - shift
        ss = f"+ {shift}" if shift >= 0 else f"- {abs(shift)}"
        yield "log_eq", 2, _number(f"Решите уравнение: $\\log_{{{base}}}(x {ss}) = {k}$", x,
                                   f"$x {ss} = {base}^{{{k}}} = {base ** k}$, откуда $x = {x}$."), None
    for base, power, sub in [(3, 3, 1), (2, 5, 2)]:
        x = power + sub
        yield "exp_eq", 2, _choice(f"Решите уравнение: ${base}^{{x-{sub}}} = {base ** power}$", x,
                                   f"${base ** power} = {base}^{{{power}}}$, значит $x - {sub} = {power}$, $x = {x}$.",
                                   rng=rng), None
    # functions
    for (x1, y1), (x2, y2) in [((1, 3), (3, 7)), ((0, -2), (4, 10))]:
        k = Fraction(y2 - y1, x2 - x1)
        yield "linear_fn", 1, _choice(
            f"Прямая проходит через точки $({x1}; {y1})$ и $({x2}; {y2})$. Найдите её угловой коэффициент.", k,
            f"$k = \\frac{{{y2} - {y1 if y1 >= 0 else '(' + str(y1) + ')'}}}{{{x2} - {x1}}} = {_fmt(k).strip('$')}$.", rng=rng), None
    for b, c in [(6, 5), (-4, 1)]:
        xv = Fraction(b, 2)
        bs = _xterm(-b)
        yield "parabola", 2, _choice(f"Найдите абсциссу вершины параболы $y = x^2 {bs} + {c}$.", xv,
                                     f"$x_0 = -\\frac{{b}}{{2a}} = {_fmt(xv).strip('$')}$.", rng=rng), None
    for a, b, x in [(2, -3, 2), (3, 1, -1)]:
        r = a * x * x + b
        bs = f"- {abs(b)}" if b < 0 else f"+ {b}"
        yield "graphs", 1, _number(f"Дана функция $f(x) = {a}x^2 {bs}$. Найдите $f({x})$.", r,
                                   f"$f({x}) = {a} \\cdot {x * x} {bs} = {r}$."), None
    yield "domain", 2, _number("Найдите наименьшее значение $x$ из области определения функции $y = \\sqrt{x - 4}$.",
                               4, "Подкоренное выражение неотрицательно: $x - 4 \\ge 0$, $x \\ge 4$."), None
    yield "derivative", 2, _number("Найдите $f'(2)$, если $f(x) = x^3 - 2x$.", 10,
                                   "$f'(x) = 3x^2 - 2$, $f'(2) = 12 - 2 = 10$."), None
    yield "derivative", 3, _choice("Найдите точку минимума функции $f(x) = x^2 - 8x + 3$.", 4,
                                   "$f'(x) = 2x - 8 = 0$ при $x = 4$; производная меняет знак с − на +.",
                                   wrong=[-4, 8, 3], rng=rng), None
    # geometry
    for a, b in [(50, 60), (35, 95)]:
        r = 180 - a - b
        yield "angles", 1, _choice(f"Два угла треугольника равны ${a}^\\circ$ и ${b}^\\circ$. Найдите третий угол.",
                                   r, f"$180^\\circ - {a}^\\circ - {b}^\\circ = {r}^\\circ$.", rng=rng), None
    yield "triangle_area", 2, _choice("По рисунку найдите площадь треугольника $ABC$.", 24,
                                      "Треугольник прямоугольный, катеты $BC = 6$ и $CA = 8$. $S = \\frac12 \\cdot 6 \\cdot 8 = 24$.",
                                      wrong=[12, 48, 30], rng=rng), ("right", 6, 8)
    yield "triangle_area", 1, _number("Основание треугольника 10, высота к нему 7. Найдите площадь.", 35,
                                      "$S = \\frac12 \\cdot 10 \\cdot 7 = 35$."), None
    yield "pythagoras", 1, _choice("По рисунку найдите гипотенузу $AB$.", 13,
                                   "$AB = \\sqrt{5^2 + 12^2} = \\sqrt{169} = 13$.", wrong=[17, 12, 15], rng=rng), ("right", 5, 12)
    yield "pythagoras", 2, _number("Диагональ прямоугольника 10, одна сторона 6. Найдите другую сторону.", 8,
                                   "$\\sqrt{10^2 - 6^2} = \\sqrt{64} = 8$."), None
    yield "circle", 1, {"text": "Найдите длину окружности радиуса 5.", "answer_type": "choice",
                        "options": ["$5\\pi$", "$10\\pi$", "$25\\pi$", "$20\\pi$"], "correct": "1",
                        "explanation": "$C = 2\\pi r = 10\\pi$."}, None
    yield "circle", 2, _number("Площадь круга равна $49\\pi$. Найдите его радиус.", 7,
                               "$\\pi r^2 = 49\\pi$, $r = 7$."), None
    yield "quadrilaterals", 1, _choice("Периметр прямоугольника 30, одна сторона 6. Найдите его площадь.", 54,
                                       "Вторая сторона $15 - 6 = 9$, площадь $6 \\cdot 9 = 54$.", wrong=[45, 90, 36], rng=rng), None
    yield "quadrilaterals", 2, _choice("По рисунку найдите площадь трапеции.", 30,
                                       "$S = \\frac{4 + 8}{2} \\cdot 5 = 30$.", wrong=[60, 40, 24], rng=rng), ("trapezoid", 4, 8, 5)
    yield "volumes", 1, _number("Ребро куба равно 4. Найдите его объём.", 64, "$V = 4^3 = 64$."), None
    yield "volumes", 3, _number("Объём куба увеличили в 8 раз. Во сколько раз увеличилось его ребро?", 2,
                                "$V$ пропорционален $a^3$, $\\sqrt[3]{8} = 2$."), None
    # ORT comparison
    cmp_opts = ["Величина А больше", "Величина Б больше", "Величины равны", "Недостаточно данных"]
    for cond, a, b, correct, expl in [
        ("", "$2^{10}$", "$10^3$", 0, "$2^{10} = 1024 > 1000 = 10^3$."),
        ("", "$\\sqrt{50}$", "$7$", 0, "$\\sqrt{50} > \\sqrt{49} = 7$."),
        ("$x > 0$. ", "$x^2$", "$x$", 3, "При $x = 0{,}5$ больше Б, при $x = 2$ больше А."),
        ("", "30% от 70", "70% от 30", 2, "Оба равны 21."),
    ]:
        yield "compare", 2, {"text": cond + "Сравните величины в колонках А и Б.", "answer_type": "choice",
                             "options": cmp_opts, "correct": str(correct), "explanation": expl,
                             "material": [{"type": "columns", "left_title": "Колонка А", "left": a,
                                           "right_title": "Колонка Б", "right": b}]}, None
    # sequences
    for a1, d, n in [(3, 4, 10), (20, -3, 8)]:
        r = a1 + (n - 1) * d
        yield "sequences", 1, _choice(
            f"В арифметической прогрессии $a_1 = {a1}$, $d = {d}$. Найдите $a_{{{n}}}$.", r,
            f"$a_n = a_1 + (n-1)d = {a1} + {n - 1} \\cdot ({d}) = {r}$.", rng=rng), None
    yield "sequences", 2, _number("Геометрическая прогрессия: $b_1 = 3$, $q = 2$. Найдите $b_5$.", 48,
                                  "$b_5 = 3 \\cdot 2^4 = 48$."), None
    yield "probability", 1, _choice("Бросают игральный кубик. Какова вероятность, что выпадет чётное число?",
                                    Fraction(1, 2), "Чётных граней 3 из 6: $\\frac36 = \\frac12$.",
                                    wrong=[Fraction(1, 3), Fraction(1, 6), Fraction(2, 3)], rng=rng), None
    yield "probability", 2, _choice("В классе 12 мальчиков и 18 девочек. Случайно выбирают одного ученика. Найдите вероятность, что это девочка.",
                                    Fraction(3, 5), "$\\frac{18}{30} = \\frac35$.",
                                    wrong=[Fraction(2, 5), Fraction(1, 2), Fraction(3, 2)], rng=rng), None
    yield "statistics", 1, _number("Найдите среднее арифметическое чисел 4, 7, 10, 15.", 9,
                                   "$(4+7+10+15) : 4 = 36 : 4 = 9$."), None
    yield "trig_values", 1, _choice("Найдите $\\sin 30^\\circ$.", Fraction(1, 2), "$\\sin 30^\\circ = \\frac12$.",
                                    wrong=[1, Fraction(3, 2), 0], rng=rng), None
    yield "trig_values", 2, {"text": "Найдите $\\cos 60^\\circ + \\sin^2 45^\\circ$.", "answer_type": "choice",
                             "options": ["$1$", "$\\frac12$", "$\\frac{\\sqrt2}{2}$", "$\\frac32$"], "correct": "0",
                             "explanation": "$\\frac12 + \\left(\\frac{\\sqrt2}{2}\\right)^2 = \\frac12 + \\frac12 = 1$."}, None


def _write_figure(spec, filename):
    """Draw a simple geometry figure as SVG into the uploads folder."""
    kind = spec[0]
    if kind == "right":
        _, a, b = spec
        body = (
            '<path d="M60 200 L60 40 L270 200 Z" fill="none" stroke="#0E0E0E" stroke-width="3" stroke-linejoin="round"/>'
            '<path d="M60 182 L78 182 L78 200" fill="none" stroke="#0E0E0E" stroke-width="2"/>'
            '<text x="44" y="36" font-size="18" font-weight="700">B</text>'
            '<text x="40" y="218" font-size="18" font-weight="700">C</text>'
            '<text x="276" y="218" font-size="18" font-weight="700">A</text>'
            f'<text x="36" y="126" font-size="18" fill="#1F4FE0">{a}</text>'
            f'<text x="160" y="226" font-size="18" fill="#1F4FE0">{b}</text>'
        )
    else:
        _, top, bottom, h = spec
        body = (
            '<path d="M100 60 L220 60 L280 200 L40 200 Z" fill="none" stroke="#0E0E0E" stroke-width="3" stroke-linejoin="round"/>'
            '<path d="M100 60 L100 200" stroke="#1F4FE0" stroke-width="2" stroke-dasharray="6 5"/>'
            f'<text x="150" y="50" font-size="18" fill="#1F4FE0">{top}</text>'
            f'<text x="150" y="226" font-size="18" fill="#1F4FE0">{bottom}</text>'
            f'<text x="108" y="136" font-size="18" fill="#1F4FE0">{h}</text>'
        )
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 240" width="960" height="720" '
           f'font-family="Arial, sans-serif"><rect width="320" height="240" fill="#FFFFFF"/>{body}</svg>')
    with open(os.path.join(current_app.config["UPLOAD_FOLDER"], filename), "w") as f:
        f.write(svg)


def _wrong_answer(item, rng):
    """A plausible wrong answer for a question snapshot (dict) or Question."""
    data = item if isinstance(item, dict) else item.snapshot()
    if data["answer_type"] == "number":
        try:
            value = float(data["correct"])
        except ValueError:
            return "0"
        delta = rng.choice([-2, -1, 1, 2, 10])
        out = value + delta
        return str(int(out)) if out.is_integer() else str(out)
    choices = [str(i) for i in range(len(data["options"])) if str(i) != data["correct"]]
    return rng.choice(choices) if choices else "0"


# --------------------------------------------------------------------------- main


def seed_demo():
    rng = random.Random(2026)
    today = date.today()

    # ---- users
    admin = User(email="admin@monday.kg", name="Темирлан Манашов", role="admin")
    admin.set_password("monday2026")
    teachers = {}
    for key, name in [("aibek", "Айбек Токтогулов"), ("nurai", "Нурай Асанова"), ("erkin", "Эркин Садыков"),
                      ("aliya", "Алия Бекова"), ("daniyar", "Данияр Ахметов"), ("marina", "Марина Ким"),
                      ("liwei", "Ли Вэй")]:
        t = User(email=f"{key}@monday.kg", name=name, role="teacher")
        t.set_password("teacher123")
        teachers[key] = t
    pending = User(email="new.teacher@monday.kg", name="Бакыт Осмонов", role="teacher", is_approved=False)
    pending.set_password("teacher123")
    teachers["aibek"].is_methodist = True  # reviews the assistant's questions
    helper = User(email="assistant@monday.kg", name="Айдана Жолдошева", role="assistant")
    helper.set_password("assistant123")
    db.session.add_all([admin, pending, helper, *teachers.values()])

    # Exam date chosen so the countdown shows 21 Mondays.
    first_monday = today + timedelta(days=(7 - today.weekday()) % 7)
    exam_date = first_monday + timedelta(weeks=20, days=4)
    tima = User(email="student@monday.kg", name="Тима Манашов", role="student")
    tima.set_password("student123")
    tima.profile = StudentProfile(exam="ORT", exam_date=exam_date, goal_score=190, grade="11", country="Кыргызстан",
                                  region="Чуйская область", school="Гимназия №1, Токмок", onboarded=True)
    db.session.add(tima)

    regions = [("Бишкек", "Школа-гимназия №5"), ("Ош", "Лицей №2"), ("Каракол", "Школа №3"),
               ("Чуйская область", "Гимназия №1, Токмок"), ("Нарын", "Школа №1"), ("Джалал-Абад", "Лицей №7"),
               ("Талас", "Школа №4")]
    first_names = ["Айгерим", "Бекзат", "Нурай", "Эмир", "Алина", "Данияр", "Сезим", "Арсен", "Айдана", "Тимур",
                   "Камила", "Адилет", "Жанара", "Нурлан", "Медина", "Руслан", "Асель", "Бакыт", "Элина", "Самат",
                   "Диана", "Азамат", "Айпери", "Мирлан", "Акылай", "Ислам", "Наргиза", "Улан"]
    last_names = ["Асанова", "Осмонов", "Жумабаева", "Токтосунов", "Абдыкадырова", "Мамытов", "Касымова",
                  "Эсенов", "Садыкова", "Бакиров"]
    others = []
    for i, fn in enumerate(first_names):
        region, school = regions[i % len(regions)]
        u = User(email=f"student{i + 1}@monday.kg", name=f"{fn} {last_names[i % len(last_names)]}", role="student")
        u.set_password("student123")
        u.profile = StudentProfile(exam="ORT", exam_date=exam_date, goal_score=rng.choice([160, 180, 200, 210]),
                                   grade="11", country="Кыргызстан", region=region, school=school, onboarded=True)
        others.append(u)
    db.session.add_all(others)
    db.session.flush()

    # ---- skills
    skills = build_tree()

    # ---- questions
    authors = list(teachers.values())
    questions = []
    for i, (code, diff, data, figure) in enumerate(gen_questions(rng)):
        q = Question(author=authors[i % len(authors)], skill=skills[code], difficulty=diff,
                     exams=list(skills[code].exams), status="published", **data)
        if figure:
            fname = f"seed-figure-{i}.svg"
            _write_figure(figure, fname)
            q.image_path = fname
        questions.append(q)
    db.session.add_all(questions)
    db.session.add(Question(author=teachers["nurai"], skill=skills["log_props"], difficulty=2, exams=ADV,
                            status="published", text="Вычислите: $\\log_{2} 12 - \\log_{2} 3$", answer_type="choice",
                            options=["$2$", "$4$", "$\\log_2 9$", "$3$"], correct="0",
                            explanation="$\\log_2 (12 : 3) = \\log_2 4 = 2$."))
    # ---- showcase questions: reading material, weights, free input with fractions and rounding
    showcase = [
        Question(author=teachers["aibek"], skill=skills["statistics"], difficulty=2, exams=ALL, status="published",
                 weight=2, answer_type="number", correct="4.2", precision=1, input_formats=["decimal", "fraction"],
                 material=[{"type": "heading", "text": "Оценки за контрольную"},
                           {"type": "passage", "title": "Журнал 11 «Б»",
                            "text": "Шесть учеников написали контрольную по алгебре и получили оценки: "
                                    "4, 5, 3, 5, 4, 4. Учитель хочет сравнить средний балл с прошлой четвертью, "
                                    "где он был равен 3,9."}],
                 text="Найдите средний балл за контрольную. Ответ округлите до десятых.",
                 explanation="$\\frac{4+5+3+5+4+4}{6} = \\frac{25}{6} \\approx 4{,}17 \\approx 4{,}2$."),
        Question(author=teachers["aibek"], skill=skills["probability"], difficulty=2, exams=ALL, status="published",
                 weight=2, answer_type="number", correct="3/8", input_formats=["fraction", "decimal"],
                 text="Монету бросают три раза. Найдите вероятность того, что орёл выпадет ровно два раза. "
                      "Ответ запишите дробью или десятичным числом.",
                 explanation="Исходов $2^3 = 8$, благоприятных $3$ (ООР, ОРО, РОО): $P = \\frac{3}{8} = 0{,}375$."),
        Question(author=teachers["aibek"], skill=skills["word_problems"], difficulty=3, exams=ALL, status="published",
                 weight=3, answer_type="choice", options=["40 км/ч", "45 км/ч", "50 км/ч", "60 км/ч"], correct="3",
                 material=[{"type": "passage", "title": "Дорога в Чолпон-Ату",
                            "text": "Автобус выехал из Бишкека в Чолпон-Ату, расстояние между городами 240 км. "
                                    "Через час следом выехал автомобиль, скорость которого на 20 км/ч больше. "
                                    "В Чолпон-Ату они приехали одновременно."}],
                 text="Найдите скорость автобуса.",
                 explanation="$\\frac{240}{v} - \\frac{240}{v+20} = 1 \\Rightarrow v^2 + 20v - 4800 = 0 "
                             "\\Rightarrow v = 60$ км/ч."),
    ]
    db.session.add_all(showcase)

    # ---- a teacher's own branch under the shared tree (Aibek): visible to him and his students
    eq_sub = skills["quadratic"].parent
    abs_node = Skill(level="node", code="abs_eq_aibek", name="Уравнения с параметром", parent=eq_sub, position=100,
                     exams=["ORT", "ENT", "EGE"], owner=teachers["aibek"])
    db.session.add(abs_node)
    db.session.add_all([
        Question(author=teachers["aibek"], skill=abs_node, difficulty=2, exams=["ORT", "ENT", "EGE"], status="published",
                 text="Найдите сумму корней уравнения $|x - 3| = 5$.", answer_type="choice",
                 options=["$6$", "$8$", "$-2$", "$10$"], correct="0",
                 explanation="$x - 3 = 5$ или $x - 3 = -5$: $x = 8$ или $x = -2$, сумма $6$."),
        Question(author=teachers["aibek"], skill=abs_node, difficulty=2, exams=["ORT", "ENT", "EGE"], status="published",
                 text="Найдите произведение корней уравнения $|2x + 1| = 7$.", answer_type="number", correct="-12",
                 input_formats=["whole"],
                 explanation="$2x + 1 = \\pm 7$: $x = 3$ или $x = -4$, произведение $-12$."),
    ])
    db.session.flush()
    skills["abs_eq_aibek"] = abs_node

    by_skill = {}
    for q in questions:
        by_skill.setdefault(q.skill.code, []).append(q)

    def pick(codes, n):
        pool = [q for c in codes for q in by_skill.get(c, [])]
        return [q.id for q in rng.sample(pool, min(n, len(pool)))]

    ort_codes = [c for _, c, _, ex in SKILLS if "ORT" in ex]

    # ---- collections (Сборники)
    collections = [
        ("aibek", "ORT", "full", "ОРТ Май 2026", "Полный пробный вариант основного тура по математике в формате 2026 года.", 40, ort_codes, 16),
        ("nurai", "ORT", "thematic", "Логарифмы и степени", "Свойства логарифмов, уравнения и сравнение степеней — от простого к сложному.", 20, ["log_def", "log_props", "log_eq", "exp_eq", "powers_int"], 10),
        ("erkin", "ORT", "thematic", "Геометрия: площади", "Треугольники, четырёхугольники и круг. Задачи с чертежами.", 20, ["triangle_area", "pythagoras", "quadrilaterals", "circle", "angles"], 9),
        ("aibek", "ORT", "full", "ОРТ Январь 2026", "Зимний пробный вариант с разбором каждой задачи после завершения.", 40, ort_codes, 16),
        ("aliya", "SAT", "full", "SAT April 2024", "Digital SAT Math: алгебра, данные, геометрия и тригонометрия.", 35, [c for _, c, _, ex in SKILLS if "SAT" in ex], 14),
        ("daniyar", "ENT", "full", "ЕНТ Июнь 2025", "Профильная математика: задания с одним верным ответом и числовые.", 40, [c for _, c, _, ex in SKILLS if "ENT" in ex], 15),
        ("marina", "EGE", "full", "ЕГЭ Профиль 2025", "Задания с кратким ответом из обеих частей.", 60, [c for _, c, _, ex in SKILLS if "EGE" in ex], 15),
        ("marina", "OGE", "full", "ОГЭ Математика 2025", "Алгебра, геометрия и практические задачи для 9 класса.", 45, [c for _, c, _, ex in SKILLS if "OGE" in ex], 14),
        ("liwei", "CSCA", "full", "CSCA Math Sample", "Математика для поступления в вузы Китая.", 30, [c for _, c, _, ex in SKILLS if "CSCA" in ex], 12),
        ("aliya", "SAT", "full", "SAT March 2025", "Весенний вариант с акцентом на алгебру и анализ данных.", 35, [c for _, c, _, ex in SKILLS if "SAT" in ex], 14),
        ("erkin", "ORT", "full", "ОРТ Апрель 2025", "Весенний вариант прошлого года для сравнения с текущим форматом.", 40, ort_codes, 16),
        ("daniyar", "ENT", "thematic", "Текстовые задачи", "Движение, работа, проценты и пропорции — типовые задачи ЕНТ.", 20, ["word_problems", "percents", "proportions"], 7),
    ]
    works = {}
    for author, exam, cat, title, desc, minutes, codes, n in collections:
        ids = pick(codes, n)
        if title == "ОРТ Май 2026":  # show reading material and weights in the flagship test
            ids = [q.id for q in showcase] + [i for i in ids if i not in {q.id for q in showcase}][:n - len(showcase)]
        w = Work(author=teachers[author], kind="collection", category=cat, exam=exam, title=title,
                 description=desc, time_limit_min=minutes, draft_question_ids=ids,
                 node=skills[codes[0]].topic_node if cat == "thematic" else None)
        db.session.add(w)
        publish_work(w)
        works[title] = w
    # A republished collection (version 2) and a draft + archived one, for the teacher's "Published works" page.
    w = works["ОРТ Май 2026"]
    db.session.flush()
    w.draft_question_ids = w.draft_question_ids[:-1] + pick(["sequences"], 1)
    publish_work(w, note="Заменена задача 16: в старой версии было два верных ответа")
    draft = Work(author=teachers["aibek"], kind="collection", category="thematic", exam="ORT",
                 title="Функции и графики", description="Черновик тематического сборника.", time_limit_min=25,
                 node=skills["linear_fn"].subtopic_node,
                 status="draft", draft_question_ids=pick(["linear_fn", "parabola", "graphs"], 6))
    archived = Work(author=teachers["aibek"], kind="collection", category="full", exam="ORT",
                    title="ОРТ Пробник 2024", description="Старый формат.", time_limit_min=40,
                    draft_question_ids=pick(ort_codes, 12))
    db.session.add_all([draft, archived])
    publish_work(archived)
    archived.status = "archived"

    # ---- homework works by Aibek
    hw_specs = [
        ("ДЗ: свойства логарифмов", "Повторить свойства и решить все задачи без калькулятора.", ["log_def", "log_props"], 6),
        ("ДЗ: площади фигур", "Задачи с чертежами. Пишите решение в тетради, ответы — сюда.", ["triangle_area", "pythagoras", "quadrilaterals"], 6),
        ("ДЗ: квадратные уравнения", "Теорема Виета и дискриминант.", ["quadratic", "identities"], 6),
        ("ДЗ: проценты и пропорции", "Текстовые задачи из прошлых вариантов ОРТ.", ["percents", "proportions", "word_problems"], 6),
    ]
    hw_works = []
    for title, desc, codes, n in hw_specs:
        w = Work(author=teachers["aibek"], kind="homework", category="thematic", exam="ORT", title=title,
                 description=desc, time_limit_min=20, draft_question_ids=pick(codes, n),
                 node=skills[codes[0]].subtopic_node)
        db.session.add(w)
        publish_work(w)
        hw_works.append(w)

    # ---- Monday tests: last week (with results) and this week (upcoming)
    upcoming = week_start(next_monday_test_start().date())
    monday_works = []
    for ws in (upcoming - timedelta(days=7), upcoming):
        w = Work(author=admin, kind="monday", category="full", exam="ORT",
                 title=f"Тест понедельника · {ws.strftime('%d.%m')}", description="10 задач, одинаковых для всех на треке ОРТ.",
                 time_limit_min=20, week_start=ws, draft_question_ids=pick(ort_codes, 10))
        db.session.add(w)
        publish_work(w)
        monday_works.append(w)
    db.session.flush()

    # ---- teacher's student table (Aibek)
    lesson_rows = [
        (tima, "11", "16:00", [0, 2, 4], "ORT", 190, None),
        (others[0], "11", "17:30", [0, 3], "ORT", 210, None),
        (others[1], "11", "15:00", [1, 4], "ORT", 180, None),
        (None, "Алина Касымова", "10", "18:00", [1, 3], "ORT", 170, 34),
        (None, "Эмир Бакиров", "11", "16:00", [1, 3], "SAT", 700, 58),
        (None, "Сезим Жумабаева", "11", "19:00", [2, 5], "ORT", 200, 71),
        (None, "Арсен Мамытов", "9", "14:00", [5], "OGE", 25, 22),
    ]
    records = []
    for row in lesson_rows:
        if row[0] is not None:
            user, grade, time_, days, exam, goal, _ = row
            r = StudentRecord(teacher=teachers["aibek"], student=user, name=user.name, grade=grade, lesson_time=time_,
                              lesson_days=days, exam=exam, goal_score=goal, linked_at=utcnow(),
                              invite_code=new_invite_code())
        else:
            _, name, grade, time_, days, exam, goal, manual = row
            r = StudentRecord(teacher=teachers["aibek"], name=name, grade=grade, lesson_time=time_, lesson_days=days,
                              exam=exam, goal_score=goal, manual_progress=manual, invite_code=new_invite_code())
        records.append(r)
    records[4].goal_text = "SAT Math 700+"
    db.session.add_all(records)
    db.session.flush()

    # ---- practice history for Tima and the others (last 3 weeks)
    weak_for_tima = {"triangle_area": 0.3, "log_props": 0.45, "word_problems": 0.5, "percents": 0.55, "log_eq": 0.4}
    reasons = ["careless", "careless", "careless", "gap", "misread", None]

    def simulate(user, days_back, n_sessions, skill_acc, base_acc):
        for s in range(n_sessions):
            started = utcnow() - timedelta(days=rng.randint(1, days_back), hours=rng.randint(0, 10))
            mode = rng.choice(["franklin", "franklin", "darwin", "einstein"])
            att = Attempt(user=user, mode=mode, started_at=started, finished_at=started + timedelta(minutes=8))
            qs = rng.sample(questions, 5)
            score = 0
            for i, q in enumerate(qs):
                acc = skill_acc.get(q.skill.code, base_acc)
                ok = rng.random() < acc
                score += ok
                att.answers.append(AttemptAnswer(
                    index=i, question=q, skill=q.skill, given=q.correct if ok else _wrong_answer(q, rng), is_correct=ok,
                    mistake_reason=None if ok else rng.choice(reasons), resolved=(not ok and rng.random() < 0.55),
                    answered_at=started + timedelta(minutes=i + 1)))
            att.score, att.total = score, len(qs)
            att.plan = [q.id for q in qs]
            att.position = len(qs)
            att.duration_sec = 480
            db.session.add(att)

    simulate(tima, 21, 22, weak_for_tima, 0.66)
    # make Tima's skill map interesting: guaranteed mastery on arithmetic basics
    for code in ["fractions", "proportions", "divisibility", "powers_int", "linear_eq", "systems",
                 "identities", "log_def", "linear_fn", "angles"]:
        started = utcnow() - timedelta(days=rng.randint(1, 15))
        att = Attempt(user=tima, mode="franklin", started_at=started, finished_at=started + timedelta(minutes=6))
        qs = by_skill.get(code, [])
        for i in range(5):
            q = qs[i % len(qs)]
            att.answers.append(AttemptAnswer(index=i, question=q, skill=q.skill, given=q.correct, is_correct=True,
                                             answered_at=started + timedelta(minutes=i)))
        att.score = att.total = 5
        db.session.add(att)
    for u in others[:12]:
        simulate(u, 21, rng.randint(4, 10), {}, rng.uniform(0.5, 0.92))

    # ---- homework assignments for Tima (one per state) and others
    rec_tima = records[0]
    now = utcnow()
    a_new = Assignment(work=hw_works[0], teacher=teachers["aibek"], record=rec_tima, due_at=now + timedelta(days=3),
                       message="Сделай до четверга, обсудим на уроке.")
    a_progress = Assignment(work=hw_works[3], teacher=teachers["aibek"], record=rec_tima, due_at=now + timedelta(days=5))
    a_sub = Assignment(work=hw_works[1], teacher=teachers["aibek"], record=rec_tima, due_at=now - timedelta(days=1))
    a_checked = Assignment(work=hw_works[2], teacher=teachers["aibek"], record=rec_tima, due_at=now - timedelta(days=6),
                           teacher_comment="Хорошо! Обрати внимание на знаки в теореме Виета — задача 4.",
                           checked_at=now - timedelta(days=4))
    a_other = Assignment(work=hw_works[0], teacher=teachers["aibek"], record=records[1], due_at=now + timedelta(days=3))
    a_other_sub = Assignment(work=hw_works[1], teacher=teachers["aibek"], record=records[2], due_at=now - timedelta(days=1))
    db.session.add_all([a_new, a_progress, a_sub, a_checked, a_other, a_other_sub])
    db.session.flush()

    def finish(assignment, user, correct_ratio, days_ago):
        v = assignment.work.current_version
        started = now - timedelta(days=days_ago, minutes=25)
        att = Attempt(user=user, mode="homework", work_version=v, assignment=assignment, started_at=started)
        form = {}
        for idx, item in enumerate(v.items):
            form[f"q{idx}"] = item["correct"] if rng.random() < correct_ratio else _wrong_answer(item, rng)
        from .services import grade_version_attempt
        db.session.add(att)
        grade_version_attempt(att, v, form)
        att.finished_at = started + timedelta(minutes=17)
        att.duration_sec = 17 * 60

    finish(a_sub, tima, 0.7, 1)
    finish(a_checked, tima, 0.85, 5)
    finish(a_other_sub, others[1], 0.6, 1)
    db.session.add(Attempt(user=tima, mode="homework", work_version=hw_works[3].current_version,
                           assignment=a_progress, started_at=now - timedelta(hours=3)))

    # ---- last week's Monday test results
    last_monday = monday_works[0]
    v = last_monday.current_version
    for u in [tima] + others:
        started = datetime.combine(last_monday.week_start, datetime.min.time()) + timedelta(hours=19, minutes=rng.randint(0, 5))
        att = Attempt(user=u, mode="monday", work_version=v, started_at=started)
        ratio = 0.7 if u is tima else rng.uniform(0.35, 1.0)
        form = {f"q{i}": (it["correct"] if rng.random() < ratio else (_wrong_answer(it, rng) if rng.random() < 0.85 else ""))
                for i, it in enumerate(v.items)}
        db.session.add(att)
        from .services import grade_version_attempt
        grade_version_attempt(att, v, form)
        att.finished_at = started + timedelta(minutes=rng.randint(9, 20))
        att.duration_sec = int((att.finished_at - started).total_seconds())

    # attendance for the last five weeks of lessons (kept apart from knowledge)
    from .models import Attendance
    today = date.today()
    for rec in StudentRecord.query.filter_by(teacher_id=teachers["aibek"].id).all():
        for back in range(1, 36):
            d = today - timedelta(days=back)
            if d.weekday() in (rec.lesson_days or []):
                roll = rng.random()
                db.session.add(Attendance(record_id=rec.id, day=d,
                                          status="present" if roll < 0.82 else ("late" if roll < 0.93 else "absent")))

    # the assistant's uploads: two wait for review, one came back with a comment
    for k, (text, opts, right, status, note) in enumerate([
        ("Найдите $25\\%$ от числа $360$.", ["$80$", "$90$", "$95$", "$100$"], "1", "pending", None),
        ("Найдите $40\\%$ от числа $150$.", ["$50$", "$55$", "$60$", "$65$"], "2", "pending", None),
        ("Сколько процентов составляет $30$ от $120$?", ["$20\\%$", "$25\\%$", "$30\\%$", "$40\\%$"], "1", "draft",
         "Добавьте пошаговое объяснение и проверьте сложность — это лёгкий вопрос."),
    ]):
        db.session.add(Question(author=helper, skill=skills["percents"], difficulty=2, exams=["ORT", "ENT"],
                                text=text, options=opts, correct=right, answer_type="choice", status=status,
                                review_note=note))

    # Aibek's questions of the day (today)
    from .models import DailyPick
    ort_qs = [q for q in questions if "ORT" in (q.exams or []) and (q.difficulty or 2) >= 2][:2]
    for k, q in enumerate(ort_qs):
        db.session.add(DailyPick(teacher_id=teachers["aibek"].id, question_id=q.id, day=today, position=k))

    # kinds of question for the filters (word problem, graph, comparison…)
    from .taxonomy import auto_tags
    db.session.flush()
    for q in Question.query.filter(Question.tags.is_(None)).all():
        q.tags = auto_tags(q)

    db.session.commit()

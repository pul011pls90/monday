"""The master skill map and the exam views.

Every question is tagged with ONE master skill (a leaf of the map below).
Exams show the map their own way:
  * SAT — the official College Board domains and skills (each points to one or more master skills);
  * ORT, ENT, OGE, EGE, CSCA — the master map, only the skills that exam tests (ORT keeps "Сравнение величин").
So a question tagged once appears under every exam where it fits.
"""
from .extensions import db

ALL = ["ORT", "ENT", "EGE", "OGE", "SAT", "CSCA"]
NO_SAT = ["ORT", "ENT", "EGE", "OGE", "CSCA"]
SCHOOL = ["ORT", "ENT", "EGE", "OGE"]
UPPER = ["ENT", "EGE", "CSCA"]  # senior school: logs, trig equations, calculus
TAXONOMY_VERSION = "3"

# branch code, branch name, [(subtopic code, subtopic name, [(skill code, skill name, exams, weight)])]
MASTER = [
    ("b-arith", "Арифметика и числа", [
        ("s-numbers", "Действия с числами", [
            ("fractions", "Дроби: обыкновенные и десятичные", ALL, 1),
            ("percents", "Проценты", ALL, 2),
            ("proportions", "Отношения и пропорции", ALL, 1),
            ("abs_value", "Модуль числа", ALL, 1),
            ("rounding", "Округление, порядок действий, оценка", ["ORT", "OGE", "ENT", "CSCA"], 1),
        ]),
        ("s-integers", "Свойства целых чисел", [
            ("divisibility", "Делимость, НОД и НОК", NO_SAT, 1),
            ("primes", "Простые числа и разложение на множители", NO_SAT, 1),
        ]),
        ("s-powers", "Степени и корни", [
            ("powers_int", "Степени с целым показателем", ALL, 1),
            ("powers_frac", "Степени с рациональным показателем", ["SAT", "EGE", "ENT", "CSCA", "ORT"], 1),
            ("radicals", "Корни и их преобразования", ALL, 1),
            ("sci_notation", "Стандартный вид числа", ["OGE", "SAT", "ORT", "CSCA"], 1),
        ]),
        ("s-seq", "Прогрессии", [
            ("sequences", "Арифметическая и геометрическая прогрессии", ALL, 1),
            ("series_sum", "Сумма членов прогрессии", NO_SAT, 1),
        ]),
    ]),
    ("b-alg", "Алгебра", [
        ("s-expr", "Выражения", [
            ("identities", "Формулы сокращённого умножения", ALL, 1),
            ("poly_ops", "Многочлены и разложение на множители", ALL, 1),
            ("rational_expr", "Алгебраические дроби", ALL, 1),
        ]),
        ("s-eq", "Уравнения", [
            ("linear_eq", "Линейные уравнения", ALL, 2),
            ("quadratic", "Квадратные уравнения", ALL, 2),
            ("vieta", "Теорема Виета", NO_SAT, 1),
            ("rational_eq", "Дробно-рациональные уравнения", ALL, 1),
            ("radical_eq", "Иррациональные уравнения", ["SAT", "EGE", "ENT", "CSCA"], 1),
            ("abs_eq", "Уравнения с модулем", ["ORT", "ENT", "EGE", "OGE", "CSCA", "SAT"], 1),
        ]),
        ("s-sys", "Системы уравнений", [
            ("systems", "Системы линейных уравнений", ALL, 1),
            ("systems_nl", "Нелинейные системы", ["SAT", "EGE", "ENT", "OGE", "CSCA"], 1),
        ]),
        ("s-ineq", "Неравенства", [
            ("inequalities", "Линейные неравенства", ALL, 1),
            ("ineq_quad", "Квадратные неравенства, метод интервалов", NO_SAT, 1),
            ("ineq_rational", "Дробно-рациональные неравенства", ["EGE", "ENT", "OGE", "CSCA"], 1),
            ("ineq_abs", "Неравенства с модулем", ["EGE", "ENT", "CSCA", "SAT"], 1),
        ]),
        ("s-word", "Текстовые задачи", [
            ("word_problems", "Движение и работа", ALL, 2),
            ("word_mix", "Смеси, сплавы, концентрации", NO_SAT, 1),
            ("word_money", "Скидки, прибыль, вклады", ALL, 1),
            ("units", "Скорости, единицы измерения", ["SAT", "ORT", "OGE", "CSCA"], 1),
        ]),
    ]),
    ("b-fn", "Функции", [
        ("s-fnprops", "Свойства функций", [
            ("graphs", "Значение функции, чтение графика", ALL, 1),
            ("domain", "Область определения и значений", ["ORT", "ENT", "EGE", "OGE", "CSCA"], 1),
            ("fn_props", "Чётность, монотонность, периодичность", UPPER, 1),
            ("fn_transform", "Преобразования графиков", ALL, 1),
            ("fn_inverse", "Обратная функция", UPPER, 1),
        ]),
        ("s-fnkinds", "Виды функций", [
            ("linear_fn", "Линейная функция", ALL, 1),
            ("parabola", "Квадратичная функция", ALL, 1),
            ("power_fn", "Степенная и дробно-линейная функция", ["OGE", "EGE", "ENT", "CSCA", "SAT"], 1),
            ("exp_fn", "Показательная функция", ["SAT", "ORT", "EGE", "ENT", "CSCA"], 1),
            ("log_fn", "Логарифмическая функция", ["ORT", "ENT", "EGE", "CSCA"], 1),
        ]),
        ("s-log", "Логарифмы, показательные уравнения", [
            ("log_def", "Определение логарифма", ["ORT", "ENT", "EGE", "CSCA"], 1),
            ("log_props", "Свойства логарифмов", ["ORT", "ENT", "EGE", "CSCA"], 1),
            ("log_eq", "Логарифмические уравнения", ["ORT", "ENT", "EGE", "CSCA"], 1),
            ("exp_eq", "Показательные уравнения", ["ORT", "ENT", "EGE", "CSCA"], 1),
            ("log_ineq", "Логарифмические и показательные неравенства", UPPER, 1),
        ]),
    ]),
    ("b-geo", "Геометрия", [
        ("s-tri", "Треугольники", [
            ("angles", "Углы и параллельные прямые", ALL, 1),
            ("triangle_types", "Равнобедренный и равносторонний треугольник", ALL, 1),
            ("pythagoras", "Прямоугольный треугольник, теорема Пифагора", ALL, 1),
            ("similarity", "Подобие и равенство треугольников", ALL, 1),
            ("triangle_area", "Площадь треугольника", ALL, 1),
            ("sin_cos_law", "Теоремы синусов и косинусов", ["EGE", "ENT", "OGE", "CSCA"], 1),
        ]),
        ("s-quad", "Четырёхугольники и многоугольники", [
            ("quadrilaterals", "Четырёхугольники", ALL, 1),
            ("polygons", "Многоугольники: углы и площади", ALL, 1),
        ]),
        ("s-circle", "Окружность", [
            ("circle", "Окружность и круг", ALL, 1),
            ("arcs", "Дуги, секторы, хорды, касательные", ALL, 1),
            ("inscribed", "Вписанные и описанные фигуры", NO_SAT, 1),
        ]),
        ("s-solid", "Стереометрия", [
            ("volumes", "Объёмы тел", ["ORT", "ENT", "EGE", "SAT", "CSCA"], 1),
            ("surface", "Площадь поверхности", ["ORT", "ENT", "EGE", "SAT", "CSCA"], 1),
            ("space_coords", "Координаты и векторы в пространстве", ["EGE", "CSCA"], 1),
        ]),
        ("s-coord", "Координатная геометрия", [
            ("coord_basics", "Расстояние, середина отрезка, угловой коэффициент", ALL, 1),
            ("line_eq", "Уравнение прямой", ALL, 1),
            ("circle_eq", "Уравнение окружности", ["SAT", "EGE", "ENT", "CSCA"], 1),
            ("conics", "Параболы, эллипсы, гиперболы", ["CSCA"], 1),
        ]),
    ]),
    ("b-trig", "Тригонометрия", [
        ("s-trig-tri", "Тригонометрия в треугольнике", [
            ("right_trig", "Синус, косинус, тангенс острого угла", ALL, 1),
            ("trig_values", "Значения для 0°, 30°, 45°, 60°, 90°", ["ENT", "EGE", "SAT", "CSCA", "OGE"], 1),
        ]),
        ("s-trig-id", "Преобразования", [
            ("radians", "Радианы и единичная окружность", ["SAT", "EGE", "ENT", "CSCA"], 1),
            ("trig_identities", "Формулы приведения, сложения, двойного угла", UPPER, 1),
        ]),
        ("s-trig-eq", "Уравнения", [
            ("trig_eq", "Тригонометрические уравнения", UPPER, 1),
            ("arc_fn", "arcsin, arccos, arctg", UPPER, 1),
        ]),
    ]),
    ("b-calc", "Начала анализа", [
        ("s-deriv", "Производная", [
            ("limits", "Пределы", ["CSCA"], 1),
            ("derivative", "Производная: правила вычисления", UPPER, 1),
            ("tangent", "Касательная к графику", UPPER, 1),
            ("extrema", "Экстремумы, наибольшее и наименьшее значение", UPPER, 1),
        ]),
        ("s-cv", "Комплексные числа и векторы", [
            ("complex", "Комплексные числа", ["SAT", "CSCA"], 1),
            ("vectors", "Векторы на плоскости", ["EGE", "ENT", "OGE", "CSCA"], 1),
        ]),
    ]),
    ("b-stat", "Вероятность и статистика", [
        ("s-prob", "Комбинаторика и вероятность", [
            ("combinatorics", "Перестановки и сочетания", ["ORT", "EGE", "ENT", "OGE", "CSCA"], 1),
            ("probability", "Классическая вероятность", ALL, 1),
            ("cond_prob", "Условная вероятность, независимые события", ["SAT", "EGE", "CSCA"], 1),
        ]),
        ("s-stats", "Статистика и данные", [
            ("statistics", "Среднее, медиана, мода, размах", ALL, 1),
            ("spread", "Дисперсия и стандартное отклонение", ["SAT", "CSCA"], 1),
            ("data_read", "Чтение таблиц и диаграмм", ALL, 1),
            ("scatter", "Диаграммы рассеяния и модели", ["SAT"], 1),
            ("inference", "Выборки и погрешность", ["SAT"], 1),
            ("stat_claims", "Оценка статистических выводов", ["SAT"], 1),
        ]),
    ]),
    ("b-logic", "Логика и сравнение", [
        ("s-compare", "Сравнение величин", [
            ("compare", "Сравнение величин (колонки А и Б)", ["ORT"], 1),
        ]),
        ("s-logic", "Закономерности", [
            ("patterns", "Числовые и логические закономерности", ["ORT", "OGE"], 1),
        ]),
    ]),
]

# CSCA is a senior-school exam (functions, trig, sequences, analytic geometry, vectors, complex numbers, probability).
# Middle-school skills are not on it: arithmetic, percents, basic algebra drills, plane-geometry basics, data reading.
CSCA_BELOW_LEVEL = {
    "fractions", "percents", "proportions", "abs_value", "rounding", "divisibility", "primes", "powers_int", "powers_frac",
    "radicals", "sci_notation", "identities", "poly_ops", "rational_expr", "linear_eq", "word_problems", "word_mix",
    "word_money", "units", "angles", "triangle_types", "pythagoras", "similarity", "quadrilaterals", "polygons", "circle",
    "arcs", "inscribed", "data_read", "spread", "scatter", "inference", "stat_claims",
}
for _b, _bn, _subs in MASTER:
    for _s, _sn, _skills in _subs:
        for _i, (_code, _name, _exams, _w) in enumerate(_skills):
            if _code in CSCA_BELOW_LEVEL and "CSCA" in _exams:
                _skills[_i] = (_code, _name, [e for e in _exams if e != "CSCA"], _w)

# SAT: the official domains → skills, each pointing to master skills.
SAT_VIEW = [
    ("alg", "Алгебра", "Algebra", [
        ("lin1", "Линейные уравнения с одной переменной", "Linear equations in one variable", ["linear_eq"]),
        ("linfn", "Линейные функции", "Linear functions", ["linear_fn"]),
        ("lin2", "Линейные уравнения с двумя переменными", "Linear equations in two variables", ["line_eq"]),
        ("sys", "Системы двух линейных уравнений", "Systems of two linear equations in two variables", ["systems"]),
        ("ineq", "Линейные неравенства", "Linear inequalities in one or two variables", ["inequalities", "ineq_abs"]),
    ]),
    ("adv", "Продвинутая математика", "Advanced Math", [
        ("equiv", "Равносильные выражения", "Equivalent expressions",
         ["identities", "poly_ops", "rational_expr", "powers_frac", "radicals", "powers_int"]),
        ("nleq", "Нелинейные уравнения и системы", "Nonlinear equations in one variable and systems of equations in two variables",
         ["quadratic", "rational_eq", "radical_eq", "systems_nl", "abs_eq"]),
        ("nlfn", "Нелинейные функции", "Nonlinear functions",
         ["parabola", "exp_fn", "power_fn", "fn_transform", "graphs"]),
    ]),
    ("psda", "Задачи и анализ данных", "Problem-Solving and Data Analysis", [
        ("ratio", "Отношения, скорости, единицы", "Ratios, rates, proportional relationships, and units",
         ["proportions", "units", "word_problems"]),
        ("pct", "Проценты", "Percentages", ["percents", "word_money"]),
        ("one", "Данные одной переменной", "One-variable data: distributions and measures of center and spread",
         ["statistics", "spread", "data_read"]),
        ("two", "Данные двух переменных", "Two-variable data: models and scatterplots", ["scatter"]),
        ("prob", "Вероятность и условная вероятность", "Probability and conditional probability", ["probability", "cond_prob"]),
        ("infer", "Выводы по выборке", "Inference from sample statistics and margin of error", ["inference"]),
        ("claims", "Оценка статистических утверждений", "Evaluating statistical claims: observational studies and experiments",
         ["stat_claims"]),
    ]),
    ("geo", "Геометрия и тригонометрия", "Geometry and Trigonometry", [
        ("area", "Площадь и объём", "Area and volume", ["triangle_area", "quadrilaterals", "polygons", "volumes", "surface"]),
        ("lines", "Прямые, углы и треугольники", "Lines, angles, and triangles", ["angles", "triangle_types", "similarity"]),
        ("rtrig", "Прямоугольные треугольники и тригонометрия", "Right triangles and trigonometry",
         ["pythagoras", "right_trig", "trig_values", "radians"]),
        ("circ", "Окружности", "Circles", ["circle", "arcs", "circle_eq"]),
    ]),
]

# Cross-cutting kinds of question (shown as filter chips).
TAGS = {
    "word": "Задача с текстом",
    "graph": "Чтение графика / таблицы",
    "nocalc": "Без калькулятора",
    "compare": "Сравнение",
}


def auto_tags(q):
    """A first guess, used when the author didn't set tags."""
    import re
    tags = set()
    text = (q.text or "").lower()
    code = (q.skill.code if q.skill else "") or ""
    if code == "compare" or any((b or {}).get("type") == "columns" for b in (q.material or [])):
        tags.add("compare")
    if q.image_path or re.search(r"график|таблиц|диаграмм|на рисунке", text):
        tags.add("graph")
    if code.startswith("word") or code in ("units",) or any((b or {}).get("type") == "passage" for b in (q.material or [])) \
            or len(re.sub(r"\$[^$]*\$", "", text)) > 140:
        tags.add("word")
    return sorted(tags)


# --------------------------------------------------------------------------- building / upgrading the map


def ensure_taxonomy(force=False):
    """Create the master map, or move an older map onto it. Results and questions keep their skill ids.

    Runs once per TAXONOMY_VERSION (kept in AppMeta), so later renames by the admin aren't overwritten.
    """
    from .models import AppMeta, ContentNode, Question, Work
    meta = db.session.get(AppMeta, "taxonomy")
    if meta and meta.value == TAXONOMY_VERSION and not force:
        return
    by_code = {n.code: n for n in ContentNode.query.filter(ContentNode.code.isnot(None)).all()}
    old_parents = {}  # old shared subtopic/topic id → new node, to carry teacher branches and works along
    for tpos, (bcode, bname, subs) in enumerate(MASTER):
        branch = by_code.get(bcode)
        if branch is None:
            branch = ContentNode(level="topic", code=bcode, name=bname, position=tpos)
            db.session.add(branch)
            by_code[bcode] = branch
        branch.parent, branch.level, branch.archived, branch.position, branch.owner_id = None, "topic", False, tpos, None
        b_exams = set()
        for spos, (scode, sname, skills) in enumerate(subs):
            sub = by_code.get(scode)
            if sub is None:
                sub = ContentNode(level="subtopic", code=scode, name=sname, position=spos)
                db.session.add(sub)
                by_code[scode] = sub
            sub.parent, sub.level, sub.archived, sub.position, sub.owner_id = branch, "subtopic", False, spos, None
            s_exams = set()
            for kpos, (code, name, exams, weight) in enumerate(skills):
                node = by_code.get(code)
                if node is None:
                    node = ContentNode(level="node", code=code, name=name)
                    db.session.add(node)
                    by_code[code] = node
                else:
                    old_sub = node.parent
                    if old_sub is not None and old_sub.id is not None and old_sub is not sub:
                        old_parents.setdefault(old_sub.id, sub)
                        if old_sub.parent is not None and old_sub.parent.id is not None:
                            old_parents.setdefault(old_sub.parent.id, branch)
                node.parent, node.level, node.name, node.exams = sub, "node", name, list(exams)
                node.position, node.weight, node.archived = kpos, weight, False
                s_exams |= set(exams)
            sub.exams = sorted(s_exams)
            b_exams |= s_exams
        branch.exams = sorted(b_exams)
    db.session.flush()
    keep = {c for c in by_code}
    master_codes = {b for b, _n, _s in MASTER} | {s for _b, _n, subs in MASTER for s, _sn, _k in subs} | \
        {k for _b, _n, subs in MASTER for _s, _sn, skills in subs for k, *_ in skills}
    # teacher branches hanging under old shared subtopics → the matching new subtopic
    for n in ContentNode.query.filter(ContentNode.owner_id.isnot(None)).all():
        if n.parent_id in old_parents:
            target = old_parents[n.parent_id]
            if n.level == "node" and target.level == "topic":
                continue
            n.parent = target
    for w in Work.query.filter(Work.node_id.isnot(None)).all():
        if w.node_id in old_parents:
            w.node = old_parents[w.node_id]
    db.session.flush()
    # old shared topics/subtopics that are now empty → archive (never delete)
    for n in ContentNode.query.filter(ContentNode.owner_id.is_(None), ContentNode.archived.is_(False)).all():
        if n.code in master_codes:
            continue
        if n.level in ("topic", "subtopic") and not any(not c.archived for c in n.children):
            n.archived = True
        elif n.level == "node" and n.parent is not None and n.parent.archived:
            n.archived = True
    db.session.flush()
    # a second pass: topics whose subtopics were all archived above
    for n in ContentNode.query.filter(ContentNode.level == "topic", ContentNode.owner_id.is_(None),
                                      ContentNode.archived.is_(False)).all():
        if n.code not in master_codes and not any(not c.archived for c in n.children):
            n.archived = True
    for q in Question.query.filter((Question.tags.is_(None)) | (Question.tags == "[]")).all():
        q.tags = auto_tags(q)
    if meta is None:
        meta = AppMeta(key="taxonomy", value=TAXONOMY_VERSION)
        db.session.add(meta)
    meta.value = TAXONOMY_VERSION
    db.session.commit()
    _ = keep


# --------------------------------------------------------------------------- exam views


def exam_view(user, exam):
    """[{key, name, en, groups: [{key, name, skills: [{key, name, en, nodes: {ids}}]}]}].

    Keys: master — "t<id>", "s<id>", "n<id>"; SAT — "x:<domain>", "x:<domain>:<skill>".
    Every key resolves to a set of master node ids with keyset().
    """
    from .services import content_tree
    tree = content_tree(user, exam)
    if exam != "SAT":
        out = []
        for t in tree:
            groups = []
            for s in t["subtopics"]:
                skills = [{"key": f"n{n.id}", "name": n.name, "en": "", "nodes": {n.id}, "own": not n.is_shared}
                          for n in s["nodes"]]
                if skills:
                    groups.append({"key": f"s{s['node'].id}", "name": s["node"].name, "skills": skills})
            if groups:
                out.append({"key": f"t{t['node'].id}", "name": t["node"].name, "en": "", "groups": groups})
        return out
    by_code, own = {}, []
    for t in tree:
        for s in t["subtopics"]:
            for n in s["nodes"]:
                if n.is_shared and n.code:
                    by_code[n.code] = n.id
                elif not n.is_shared:
                    own.append(n)
    out = []
    for dkey, dname, den, skills in SAT_VIEW:
        items = []
        for skey, sname, sen, codes in skills:
            ids = {by_code[c] for c in codes if c in by_code}
            items.append({"key": f"x:{dkey}:{skey}", "name": sname, "en": sen, "nodes": ids, "own": False})
        out.append({"key": f"x:{dkey}", "name": dname, "en": den, "groups": [{"key": None, "name": "", "skills": items}]})
    if own:
        out.append({"key": "x:own", "name": "Мои навыки", "en": "", "groups": [{"key": None, "name": "", "skills": [
            {"key": f"n{n.id}", "name": n.name, "en": "", "nodes": {n.id}, "own": True} for n in own]}]})
    return out


def keyset(view):
    """{key: set(node ids)} for every section, group and skill of a view."""
    out = {}
    for sec in view:
        sec_ids = set()
        for g in sec["groups"]:
            g_ids = set()
            for sk in g["skills"]:
                out[sk["key"]] = set(sk["nodes"])
                g_ids |= sk["nodes"]
            if g["key"]:
                out[g["key"]] = g_ids
            sec_ids |= g_ids
        out[sec["key"]] = sec_ids
    return out

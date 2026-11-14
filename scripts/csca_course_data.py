"""CSCA Mathematics 10-unit curriculum definitions for seed_course.py."""
from __future__ import annotations

from scripts.course_articles import CSCA_UNIT1_ARTICLES

CSCA_UNIT_DEFS = [
    (1, "csca-about", "intro", "about", "О CSCA", "Знакомство с экзаменом CSCA, форматом 48 вопросов за 60 минут и четырьмя модулями."),
    # База (Units 2-5)
    (2, "csca-base-sets", "foundation", "sets", "База · Множества и неравенства", "Линейные и квадратные неравенства, модуль, метод интервалов и базовые уравнения."),
    (3, "csca-base-functions", "foundation", "functions", "База · Функции и прогрессии", "Линейная и квадратичная функции, область определения, логарифмы, степени и прогрессии."),
    (4, "csca-base-geometry", "foundation", "geometry", "База · Геометрия, векторы и комплексные числа", "Прямая, окружность, векторы на плоскости, комплексные числа и стереометрия."),
    (5, "csca-base-probability", "foundation", "probability", "База · Вероятность и статистика", "Классическая и условная вероятность, среднее, медиана, размах и закономерности."),
    # Продвинутый уровень (Units 6-9)
    (6, "csca-adv-trig", "advanced", "trig", "Продвинутый · Тригонометрические тождества", "Формулы приведения, сложения, двойного угла, радианы и единичная окружность."),
    (7, "csca-adv-conics", "advanced", "conics", "Продвинутый · Эллипс, гипербола и парабола", "Канонические уравнения конических сечений, фокусы, асимптоты и пересечения с прямой."),
    (8, "csca-adv-calculus", "advanced", "calculus", "Продвинутый · Сложные функции и производные", "Чётность, периодичность, обратные функции, преобразования графиков и основы производной."),
    (9, "csca-adv-params", "advanced", "params", "Продвинутый · Параметры и неравенства", "Иррациональные уравнения, нелинейные системы, теорема Виета и сложные неравенства."),
    # Симуляция (Unit 10)
    (10, "csca-simulation", "challenge", "simulation", "Симуляция CSCA", "Полная тренировка формата 48 вопросов за 60 минут без калькулятора и стратегия разбора ошибок."),
]

CSCA_UNIT1_LESSONS = [
    {
        "slug": "welcome-csca",
        "title_ru": "Привет! Что такое CSCA и зачем он нужен",
        "kind": "article",
        "article_md": CSCA_UNIT1_ARTICLES["welcome-csca"],
        "hints": ["На CSCA калькулятор запрещён — тренируйте устный счёт и преобразования дробей."],
    },
    {
        "slug": "csca-format-rules",
        "title_ru": "Как устроен экзамен: 48 вопросов и 60 минут",
        "kind": "article",
        "article_md": CSCA_UNIT1_ARTICLES["csca-format-rules"],
        "hints": ["В плеере для CSCA калькулятор Desmos отключён, чтобы условия совпадали с экзаменом."],
    },
    {
        "slug": "csca-4-modules",
        "title_ru": "4 модуля программы CSCA Mathematics",
        "kind": "article",
        "article_md": CSCA_UNIT1_ARTICLES["csca-4-modules"],
        "hints": ["Наибольшее число баллов в CSCA приносят функции, тригонометрия и аналитическая геометрия."],
    },
    {
        "slug": "csca-unit-1-check",
        "title_ru": "Проверка: формат CSCA",
        "kind": "quiz",
        "article_md": CSCA_UNIT1_ARTICLES["csca-unit-1-check"],
        "inline_quiz": [
            {
                "id": "csca_u1_q1",
                "prompt": "Сколько вопросов и минут отводится на экзамен CSCA Mathematics?",
                "type": "choice",
                "options": [
                    "48 вопросов за 60 минут",
                    "44 вопроса за 70 минут",
                    "60 вопросов за 90 минут",
                    "30 вопросов за 45 минут",
                ],
                "answer": "48 вопросов за 60 минут",
                "hints": ["На один вопрос приходится примерно 75 секунд."],
                "explain": "CSCA Mathematics состоит из 48 тестовых заданий, на решение которых даётся ровно 60 минут.",
            },
            {
                "id": "csca_u1_q2",
                "prompt": "Можно ли пользоваться графическим калькулятором на экзамене CSCA?",
                "type": "choice",
                "options": [
                    "Нет, любые калькуляторы запрещены",
                    "Да, встроен Desmos",
                    "Разрешён только научный калькулятор",
                    "Разрешён только во второй половине теста",
                ],
                "answer": "Нет, любые калькуляторы запрещены",
                "hints": ["Вспомните таблицу из второго урока."],
                "explain": "На CSCA Mathematics калькуляторы полностью запрещены — все вычисления выполняются вручную.",
            },
            {
                "id": "csca_u1_q3",
                "prompt": "По какой шкале оценивается экзамен CSCA Mathematics?",
                "type": "choice",
                "options": [
                    "От 0 до 100 баллов",
                    "От 200 до 800 баллов",
                    "От 0 до 150 баллов",
                    "От 1 до 5 баллов",
                ],
                "answer": "От 0 до 100 баллов",
                "hints": ["Это классическая стобалльная шкала."],
                "explain": "Результат CSCA Mathematics выставляется по шкале от 0 до 100 баллов.",
            },
        ],
    },
]

# Unit 2-9 topic specs: (slug, title_ru, formula_tpl, formula_topic_id, skill_ids, diff)
CSCA_UNIT_TOPICS = {
    "csca-base-sets": [
        ("csca-linear-ineq", "Линейные и квадратные неравенства", "csca_sets", "inequalities", [59, 60], 1),
        ("csca-abs-ineq", "Уравнения и неравенства с модулем", "csca_sets", "inequalities", [56, 62], 1),
        ("csca-rat-ineq", "Дробно-рациональные неравенства", "csca_sets", "sets", [54, 61], 1),
        ("csca-linear-sys", "Уравнения и системы", "csca_sets", "sets", [52, 57], 1),
    ],
    "csca-base-functions": [
        ("csca-lin-quad-fn", "Линейная и квадратичная функции", "csca_functions", "functions", [72, 73, 67], 1),
        ("csca-domain-range", "Область определения и свойства", "csca_functions", "functions", [68, 69], 1),
        ("csca-exp-pow", "Степенная и показательная функции", "csca_functions", "exponential", [74, 75], 1),
        ("csca-logarithms", "Логарифмы и их свойства", "csca_functions", "logarithmic", [76, 78], 1),
        ("csca-progressions", "Арифметическая и геометрическая прогрессии", "csca_functions", "sequences", [46, 47], 1),
    ],
    "csca-base-geometry": [
        ("csca-lines", "Прямая и угловой коэффициент", "csca_geometry", "analytic_geometry", [96, 97], 1),
        ("csca-circles", "Окружность на плоскости", "csca_geometry", "analytic_geometry", [98], 1),
        ("csca-vectors", "Векторы на плоскости", "csca_geometry", "vectors", [111, 86], 1),
        ("csca-complex", "Комплексные числа", "csca_geometry", "complex_numbers", [110], 1),
        ("csca-solid", "Объёмы и площади поверхности", "csca_geometry", "solid_geometry", [93, 94], 1),
    ],
    "csca-base-probability": [
        ("csca-prob-classic", "Классическая вероятность", "csca_probability", "probability", [113], 1),
        ("csca-prob-cond", "Условная вероятность и события", "csca_probability", "probability", [114], 1),
        ("csca-stats", "Среднее, медиана и размах", "csca_probability", "statistics", [115], 1),
        ("csca-patterns", "Числовые закономерности", "csca_probability", "statistics", [122], 1),
    ],
    "csca-adv-trig": [
        ("csca-trig-angles", "Острые углы и табличные значения", "csca_functions", "trigonometric", [100, 101], 2),
        ("csca-trig-circle", "Радианы и единичная окружность", "csca_functions", "trigonometric", [102], 2),
        ("csca-trig-id", "Формулы приведения и двойного угла", "csca_functions", "trigonometric", [103], 3),
    ],
    "csca-adv-conics": [
        ("csca-conics-parab", "Параболы и их свойства", "csca_geometry", "conics", [99, 73], 2),
        ("csca-conics-ell", "Эллипсы и гиперболы", "csca_geometry", "conics", [99], 3),
        ("csca-conics-lines", "Касательные и пересечения с прямой", "csca_geometry", "analytic_geometry", [96, 97, 98], 3),
    ],
    "csca-adv-calculus": [
        ("csca-fn-trans", "Преобразования графиков", "csca_functions", "functions", [70, 67], 2),
        ("csca-fn-parity", "Чётность, монотонность, периодичность", "csca_functions", "calculus", [69], 3),
        ("csca-fn-inv", "Обратная функция", "csca_functions", "calculus", [71, 68], 3),
        ("csca-fn-explog", "Показательные и логарифмические задачи", "csca_functions", "logarithmic", [75, 76, 78], 3),
    ],
    "csca-adv-params": [
        ("csca-irrat", "Иррациональные уравнения", "csca_sets", "inequalities", [55], 3),
        ("csca-nonlin", "Нелинейные системы", "csca_sets", "sets", [58], 3),
        ("csca-vieta", "Теорема Виета и квадратные неравенства", "csca_sets", "inequalities", [52, 53, 60], 3),
        ("csca-mod-adv", "Сложные модули и дроби", "csca_sets", "inequalities", [54, 56, 61, 62], 3),
    ],
}

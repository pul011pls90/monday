"""Shared reference data: exams, session modes, statuses.

Labels are wrapped with lazy_gettext so they can be translated later.
"""
from flask_babel import lazy_gettext as _l

# Exam catalogue. min/max describe the score scale used for the
# predicted-score estimate on the home page.
EXAMS = {
    "ORT": {"label": "ОРТ", "country": _l("Кыргызстан"), "note": _l("математика и логика"), "min": 0, "max": 245},
    "ENT": {"label": "ЕНТ", "country": _l("Казахстан"), "note": _l("11 класс"), "min": 0, "max": 140},
    "EGE": {"label": "ЕГЭ", "country": _l("Россия"), "note": _l("база и профиль"), "min": 0, "max": 100},
    "OGE": {"label": "ОГЭ", "country": _l("Россия"), "note": _l("9 класс"), "min": 0, "max": 31},
    "SAT": {"label": "SAT", "country": _l("США"), "note": _l("на английском"), "min": 200, "max": 800},
    "CSCA": {"label": "CSCA", "country": _l("Китай"), "note": _l("английский или китайский"), "min": 0, "max": 100},
}
EXAM_CHOICES = list(EXAMS.keys())

# Session modes, ordered from shortest to longest. Colour keys map to CSS.
MODES = {
    "franklin": {"name": _l("Франклин"), "approx": 5, "time": _l("5–10 мин"), "desc": _l("короткий точный разбор слабых тем"), "color": "green", "count": 5, "ready": True},
    "feynman": {"name": _l("Фейнман"), "approx": 10, "time": _l("10–15 мин"), "desc": _l("объясни тему своими словами"), "color": "yellow", "count": 4, "ready": True},
    "tesla": {"name": _l("Тесла"), "approx": 15, "time": _l("15 мин"), "desc": _l("графики и фигуры руками"), "color": "orange", "count": 0, "ready": False},
    "darwin": {"name": _l("Дарвин"), "approx": 20, "time": _l("15–20 мин"), "desc": _l("расследуй свои ошибки"), "color": "red", "count": 6, "ready": True},
    "einstein": {"name": _l("Эйнштейн"), "approx": 30, "time": _l("20–30 мин"), "desc": _l("сложные задачи, два способа"), "color": "purple", "count": 5, "ready": True},
}

WORK_KINDS = {
    "collection": _l("Сборник"),
    "homework": _l("Домашнее задание"),
    "monday": _l("Тест понедельника"),
}
WORK_CATEGORIES = {"full": _l("Полный вариант"), "thematic": _l("Тематический")}
WORK_STATUSES = {"draft": _l("Черновик"), "pending": _l("На проверке"), "published": _l("Опубликовано"), "archived": _l("В архиве")}

# A collection (seen by every student of the exam) this big goes to the admin before students see it.
# Homework goes only to the teacher's own students and never needs approval.
BIG_TEST_QUESTIONS = 20

QUESTION_STATUSES = {"draft": _l("Черновик"), "pending": _l("На проверке"), "published": _l("Опубликован")}
DIFFICULTIES = {1: _l("Лёгкий"), 2: _l("Средний"), 3: _l("Сложный")}

MISTAKE_REASONS = {
    "careless": _l("Невнимательность"),
    "gap": _l("Пробел в теме"),
    "misread": _l("Не дочитал условие"),
    "time": _l("Не хватило времени"),
}

HOMEWORK_STATES = {
    "new": _l("Новое"),
    "in_progress": _l("В процессе"),
    "submitted": _l("Сдано"),
    "checked": _l("Проверено"),
    "overdue": _l("Просрочено"),
}

WEEKDAYS = [_l("Пн"), _l("Вт"), _l("Ср"), _l("Чт"), _l("Пт"), _l("Сб"), _l("Вс")]

# Teachers whose number of approved questions reaches this publish directly.
TRUSTED_TEACHER_THRESHOLD = 20


# Short true stories from maths, shown on the Home session cards (one per card, changes daily).
FACTS = [
    _l("Яблоко не падало Ньютону на голову. По воспоминаниям его друга Стьюкли, Ньютон просто увидел, как оно падает в саду, — и задумался, почему всегда вниз."),
    _l("Слова «алгоритм» и «алгебра» пришли от аль-Хорезми — учёного IX века родом из Хорезма, это Центральная Азия."),
    _l("Аль-Бируни, уроженец Хорезма, около 1000 лет назад измерил радиус Земли с вершины горы — и ошибся меньше чем на 1%."),
    _l("Знак «=» придумал Роберт Рекорд в 1557 году: «нет ничего более равного, чем две параллельные линии»."),
    _l("По легенде, маленький Гаусс за минуту сложил числа от 1 до 100: пары 1+100, 2+99… дают 50 раз по 101 = 5050."),
    _l("Хорошо перемешанную колоду из 52 карт почти наверняка никто никогда не раскладывал в том же порядке: вариантов 52! ≈ 8·10⁶⁷."),
    _l("В группе всего из 23 человек вероятность, что у двоих совпадёт день рождения, больше 50%."),
    _l("Великую теорему Ферма доказали только в 1994 году — через 357 лет после того, как Ферма написал, что знает доказательство."),
    _l("0,999… с бесконечными девятками — это ровно 1. Проверь: 1/3 = 0,333…, умножь на 3."),
    _l("Название Google — это искажённое «googol»: так называют число 10¹⁰⁰."),
    _l("Софи Жермен отправляла свои работы Гауссу под мужским именем «месье Леблан» — женщине тогда почти невозможно было заниматься наукой открыто."),
    _l("Пчёлы строят шестиугольные соты не случайно: в 1999 году доказали, что так тратится меньше всего воска."),
    _l("Улугбек в XV веке построил в Самарканде обсерваторию и составил каталог примерно из тысячи звёзд."),
    _l("Ноль как число со своими правилами описал индийский математик Брахмагупта в 628 году."),
    _l("π нельзя записать обычной дробью — это доказал Ламберт в 1761 году. Зато 22/7 даёт π с точностью до сотых."),
]


# How a test looks and behaves for the student. Chosen by the teacher when creating a work;
# the default follows the exam. "grid" = one question per screen with a number grid to jump
# anywhere (like the Digital SAT / CSCA); "pages" = several questions per page with a bubble
# answer sheet (like ORT on paper).
TEST_FORMATS = {
    "plain": {"label": _l("Обычный"), "nav": "grid", "calculator": False, "modules": 1},
    "sat": {"label": "SAT", "nav": "grid", "calculator": True, "modules": 2},
    "ort": {"label": "ОРТ", "nav": "pages", "calculator": False, "modules": 1},
    "ent": {"label": "ЕНТ", "nav": "grid", "calculator": False, "modules": 1},
    "ege": {"label": "ЕГЭ", "nav": "grid", "calculator": False, "modules": 1},
    "oge": {"label": "ОГЭ", "nav": "grid", "calculator": False, "modules": 1},
    "csca": {"label": "CSCA", "nav": "grid", "calculator": True, "modules": 1},
}
FORMAT_FOR_EXAM = {"SAT": "sat", "ORT": "ort", "ENT": "ent", "EGE": "ege", "OGE": "oge", "CSCA": "csca"}

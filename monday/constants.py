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
    "franklin": {"name": _l("Слабые темы"), "approx": 5, "time": _l("5–10 мин"), "desc": _l("5 задач с проверкой сразу"), "color": "green", "count": 5, "ready": True, "emoji": "🥪",
                 "points": [_l("5 задач"), _l("из твоих самых слабых тем, каждая из новой темы"), _l("ответ проверяется сразу")]},
    "feynman": {"name": _l("Объясни сам"), "approx": 10, "time": _l("10–15 мин"), "desc": _l("4 задачи, решение своими словами"), "color": "yellow", "count": 4, "ready": True, "emoji": "☕",
                "points": [_l("4 задачи из слабых тем"), _l("перед проверкой пишешь решение своими словами"), _l("учит понимать, а не угадывать")]},
    "tesla": {"name": _l("Графики"), "approx": 15, "time": _l("15 мин"), "desc": _l("двигай точки, меняй уравнения"), "color": "orange", "count": 0, "ready": False, "emoji": "⚡",
              "points": [_l("двигаешь точки и меняешь уравнения"), _l("видишь, как меняется график"), _l("режим в разработке")]},
    "darwin": {"name": _l("Работа над ошибками"), "approx": 20, "time": _l("15–20 мин"), "desc": _l("6 задач из журнала ошибок"), "color": "red", "count": 6, "ready": True, "emoji": "🚌",
               "points": [_l("6 задач"), _l("по темам из твоего журнала ошибок (похожие задачи, не те же самые)"), _l("ответ проверяется сразу")]},
    "einstein": {"name": _l("Сложные задачи"), "approx": 30, "time": _l("20–30 мин"), "desc": _l("5 трудных задач, два способа"), "color": "purple", "count": 5, "ready": True, "emoji": "📚",
                 "points": [_l("5 задач высокой сложности"), _l("темы вперемешку"), _l("попробуй решить двумя способами")]},
    # built in «Своя сессия»: time, number of questions, difficulty and topics chosen by the student
    "custom": {"name": _l("Своя сессия"), "approx": 10, "time": _l("сколько захочешь"), "desc": _l("время, число вопросов и сложность — твои"), "color": "blue", "count": 10, "ready": True, "builder": True, "emoji": "⚙️"},
}

# Comfortable time for one question, by difficulty (seconds): drives the pace hint in «Своя сессия».
PACE = {1: 40, 2: 75, 3: 150}
SESSION_MINUTES = (5, 10, 15, 20, 30, 45)
SESSION_LEVELS = ("ladder", "easy", "medium", "hard", "mix")

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

REPORT_KINDS = {
    "answer": _l("Неверный ответ"),
    "typo": _l("Опечатка или ошибка в формуле"),
    "unclear": _l("Непонятное условие"),
    "other": _l("Другое"),
    "node": _l("Правка карты"),
}

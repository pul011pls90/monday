"""«Мои результаты» as a designed PDF: a header like the home page, summary tiles, then one block per sector
(an exam's tests, Monday tests, homework, sessions) with its mean and every result under it.

Takes the rows student.py also writes to the CSV. Imported only when someone downloads
the PDF, so reportlab costs nothing on the 512 MB plan until then. The fonts are static
TTF builds of the app's own Onest and Unbounded (reportlab cannot read woff2).
"""
import io
import math
from pathlib import Path
from xml.sax.saxutils import escape

from flask_babel import format_date, get_locale
from flask_babel import gettext as _
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from .constants import EXAMS

FONT_DIR = Path(__file__).parent / "static" / "fonts" / "pdf"
REGULAR, SEMIBOLD, BOLD, WORDMARK = "Onest-Regular", "Onest-SemiBold", "Onest-Bold", "Unbounded-ExtraBold"

# the tokens of monday.css, light theme: paper stays white whatever theme the app is in
INK = HexColor("#0E0E0E")
MUTED = HexColor("#5E5E5E")
LINE = HexColor("#E4E4E1")
ACCENT = HexColor("#1F4FE0")
NAVY = HexColor("#0A1A5C")
SOFT = HexColor("#E8F1FB")
TRACK = HexColor("#DCE5F5")
LOGO = ("#7FA3F3", "#4275E9", "#2B60E5", "#2456D9", "#153893", "#020B29")   # the letters of the wordmark, as in brand.css

# the sky of hero.js at the size of the PDF header
SKY = HexColor("#2B60E5")
SKY_PX, SKY_CELL, SKY_DRIFT = 3.5, 58, 7.3
BAYER = [(v + .5) / 16 for v in (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)]

PAGE_W, PAGE_H = A4
MARGIN = 40
WIDTH = PAGE_W - 2 * MARGIN
FRAME_PAD = 6  # reportlab pads its page frame by this much on every side


EMPTY_SECONDS = 60  # no points in less time than this: opened and handed in, not really taken


def is_empty(row):
    """An attempt listed in the PDF but left out of every mean. No recorded time proves nothing, so it still counts."""
    return row["score"] == 0 and row["total"] and 0 < row["seconds"] < EMPTY_SECONDS


def percent_of(row):
    """A row's result in percent; None when it had nothing to score or was empty."""
    if not row["total"] or row["score"] is None or is_empty(row):
        return None
    return 100 * row["score"] / row["total"]


def mean_percent(rows):
    """Plain mean over the scored rows, each test counting once whatever its length; None if none."""
    scored = [p for p in map(percent_of, rows) if p is not None]
    return round(sum(scored) / len(scored)) if scored else None


def group_by_sector(rows):
    """Rows → sectors, exams first: [{"name", "rows", "mean", "best", "seconds", "empty"}]. Rows stay newest first."""
    sessions = _("Сессии")
    named = {"monday": _("Тест понедельника"), "homework": _("Домашка"), "daily": _("Вопрос дня")}
    order = [*EXAMS, "collection", "monday", "homework", "sessions", "daily"]
    groups = {}
    for r in rows:
        if r["mode"] == "collection":
            key = r["exam"] if r["exam"] in EXAMS else "collection"
        else:
            key = r["mode"] if r["mode"] in named else "sessions"
        groups.setdefault(key, []).append(r)
    sectors = []
    for key in sorted(groups, key=order.index):
        part = groups[key]
        name = _("Тесты %(exam)s", exam=EXAMS[key]["label"]) if key in EXAMS else _("Сборники") if key == "collection" else named.get(key, sessions)
        scored = [p for p in map(percent_of, part) if p is not None]
        sectors.append({"name": name, "rows": part, "mean": mean_percent(part), "best": round(max(scored)) if scored else None,
                        "seconds": sum(r["seconds"] for r in part), "empty": sum(1 for r in part if is_empty(r))})
    return sectors


def _register_fonts():
    for name in (REGULAR, SEMIBOLD, BOLD, WORDMARK):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f"{name}.ttf")))


def _clean(text):
    """Keeps what Onest can draw: an emoji in a name must not turn into a black box."""
    glyphs = pdfmetrics.getFont(REGULAR).face.charToGlyph
    return " ".join("".join(ch for ch in " ".join(str(text or "").split()) if ord(ch) in glyphs).split())


def _fit(c, text, font, size, width, smallest=9):
    """Sets the font, shrinking down to `smallest` and then cutting the text, so it fits `width`."""
    while size > smallest and pdfmetrics.stringWidth(text, font, size) > width:
        size -= .5
    if pdfmetrics.stringWidth(text, font, size) > width:
        while text and pdfmetrics.stringWidth(text + "…", font, size) > width:
            text = text[:-1]
        text = text.rstrip() + "…"
    c.setFont(font, size)
    return text


def _smooth(a, b, v):
    t = min(max((v - a) / (b - a), 0), 1)
    return t * t * (3 - 2 * t)


def _hash(x, y):
    v = math.sin(x * 127.1 + y * 311.7) * 43758.5453
    return v - math.floor(v)


def _noise(x, y):
    xi, yi = math.floor(x), math.floor(y)
    xf, yf = x - xi, y - yi
    u, v = xf * xf * (3 - 2 * xf), yf * yf * (3 - 2 * yf)
    a, b, c, d = _hash(xi, yi), _hash(xi + 1, yi), _hash(xi, yi + 1), _hash(xi + 1, yi + 1)
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v


def _clouds(x, y):
    return _noise(x, y) * .55 + _noise(x * 2.1, y * 2.1) * .3 + _noise(x * 4.3, y * 4.3) * .15


def _sky(c, w, h, clear):
    """One still frame of the home page's sky (hero.js): pixel clouds and a thin grid. The clouds start after `clear`, right of the text."""
    clouds, grain = c.beginPath(), c.beginPath()
    for ix in range(int(w / SKY_PX) + 1):
        for iy in range(int(h / SKY_PX) + 1):
            x, y = ix * SKY_PX, iy * SKY_PX
            quiet = _smooth(clear, clear + w * .16, x)
            if not quiet:
                continue
            density = _smooth(.38, .78, _clouds(x * .012 + SKY_DRIFT, y * .024 - SKY_DRIFT * .3))
            if density * quiet > BAYER[(iy & 3) * 4 + (ix & 3)]:
                clouds.rect(x, y, SKY_PX - .8, SKY_PX - .8)
            elif ix % 3 == 0 and iy % 3 == 0 and quiet > .6:
                grain.rect(x + .7, y + .7, 1.4, 1.4)
    c.setFillColor(SKY)
    c.setFillAlpha(.1)
    c.drawPath(grain, stroke=0, fill=1)
    c.setFillAlpha(.4)
    c.drawPath(clouds, stroke=0, fill=1)
    c.setFillAlpha(1)
    c.setStrokeColor(SKY)
    c.setStrokeAlpha(.14)
    c.setLineWidth(.5)
    for x in range(SKY_CELL, int(w), SKY_CELL):
        c.line(x, 0, x, h)
    for y in range(SKY_CELL, int(h), SKY_CELL):
        c.line(0, y, w, y)
    c.setStrokeAlpha(1)


def _wordmark(c, x, y, size):
    """MONDAY letter by letter in the colours of the logo at the top of the site."""
    c.setFont(WORDMARK, size)
    for letter, colour in zip("MONDAY", LOGO):
        c.setFillColor(HexColor(colour))
        c.drawString(x, y, letter)
        x += pdfmetrics.stringWidth(letter, WORDMARK, size)


class Hero(Flowable):
    """Top of the first page: wordmark, title, who and when, on the home page's sky."""

    def __init__(self, title, student, meta):
        super().__init__()
        self.title, self.student, self.meta = title, student, meta
        self.width, self.height = WIDTH, 148

    def wrap(self, *_args):
        return self.width, self.height

    def draw(self):
        c, w, h, pad = self.canv, self.width, self.height, 22
        c.saveState()
        shape = c.beginPath()
        shape.roundRect(0, 0, w, h, 16)
        c.clipPath(shape, stroke=0, fill=0)
        c.setFillColor(white)
        c.rect(0, 0, w, h, stroke=0, fill=1)
        _sky(c, w, h, max(w * .36, min(pdfmetrics.stringWidth(self.title, BOLD, 27), w * .7) + pad + 8))
        c.restoreState()
        c.setStrokeColor(LINE)
        c.setLineWidth(1)
        c.roundRect(0, 0, w, h, 16, stroke=1, fill=0)

        _wordmark(c, pad, h - pad - 11, 13)
        c.setFillColor(INK)
        c.drawString(pad, 66, _fit(c, self.title, BOLD, 27, w - 2 * pad, 16))
        c.drawString(pad, 42, _fit(c, self.student, SEMIBOLD, 13, w - 2 * pad))
        c.setFillColor(MUTED)
        c.drawString(pad, 24, _fit(c, self.meta, REGULAR, 10, w - 2 * pad))


class Tiles(Flowable):
    """The summary: a row of soft cards, the number first."""

    def __init__(self, items):
        super().__init__()
        self.items = items
        self.width, self.height = WIDTH, 62

    def wrap(self, *_args):
        return self.width, self.height

    def draw(self):
        c, gap = self.canv, 8
        tile = (self.width - gap * (len(self.items) - 1)) / len(self.items)
        for n, (value, label) in enumerate(self.items):
            x = n * (tile + gap)
            c.setFillColor(SOFT)
            c.roundRect(x, 0, tile, self.height, 10, stroke=0, fill=1)
            c.setFillColor(NAVY)
            c.drawString(x + 12, 28, _fit(c, value, BOLD, 19, tile - 24, 12))
            c.setFillColor(MUTED)
            c.drawString(x + 12, 12, _fit(c, label, REGULAR, 8.5, tile - 24, 6.5))


def _ring(c, x, y, radius, percent, width=5):
    """A sector's mean: how much of the circle is filled."""
    c.saveState()
    c.setLineWidth(width)
    c.setStrokeColor(TRACK)
    c.circle(x, y, radius, stroke=1, fill=0)
    if percent:
        c.setLineCap(1)
        c.setStrokeColor(ACCENT)
        if percent >= 100:
            c.circle(x, y, radius, stroke=1, fill=0)
        else:
            c.arc(x - radius, y - radius, x + radius, y + radius, 90, -3.6 * percent)
    c.restoreState()


def _time(seconds):
    hours, minutes = divmod(round(seconds / 60), 60)
    return _("%(hours)s ч %(minutes)s мин", hours=hours, minutes=minutes) if hours else _("%(minutes)s мин", minutes=minutes)


class Overview(Flowable):
    """Every sector's mean side by side, four to a row."""

    PER_ROW, ROW, GAP = 4, 52, 8

    def __init__(self, sectors):
        super().__init__()
        self.sectors = sectors
        rows = -(-len(sectors) // self.PER_ROW)
        self.width, self.height = WIDTH, rows * self.ROW + (rows - 1) * self.GAP

    def wrap(self, *_args):
        return self.width, self.height

    def draw(self):
        c = self.canv
        tile = (self.width - self.GAP * (self.PER_ROW - 1)) / self.PER_ROW
        for n, sector in enumerate(self.sectors):
            x = (n % self.PER_ROW) * (tile + self.GAP)
            y = self.height - (n // self.PER_ROW + 1) * self.ROW - (n // self.PER_ROW) * self.GAP
            c.setStrokeColor(LINE)
            c.setLineWidth(.8)
            c.roundRect(x, y, tile, self.ROW, 10, stroke=1, fill=0)
            _ring(c, x + 26, y + self.ROW / 2, 13, sector["mean"], 4.5)
            c.setFillColor(NAVY)
            c.setFont(BOLD, 14)
            c.drawString(x + 48, y + 27, "—" if sector["mean"] is None else f'{sector["mean"]}%')
            c.setFillColor(MUTED)
            c.drawString(x + 48, y + 14, _fit(c, _clean(sector["name"]), REGULAR, 8, tile - 56, 6))


class SectorHead(Flowable):
    """The title of a sector; repeated on top of each page the sector runs on to."""

    def __init__(self, sector):
        super().__init__()
        self.sector = sector
        self.width, self.height = WIDTH, 50

    def wrap(self, *_args):
        return self.width, self.height

    def draw(self):
        c, s, w, h = self.canv, self.sector, self.width, self.height
        c.setFillColor(SOFT)
        c.roundRect(0, 0, w, h, 10, stroke=0, fill=1)
        _ring(c, 28, h / 2, 13, s["mean"], 4.5)
        c.setFillColor(NAVY)
        c.drawString(52, 28, _fit(c, _clean(s["name"]), BOLD, 12.5, w - 150))
        facts = [_("Работ: %(count)s", count=len(s["rows"]))]
        if s["best"] is not None:
            facts.append(f'{_("Лучший результат")}: {s["best"]}%')
        facts.append(_time(s["seconds"]))
        if s["empty"]:
            facts.append(_("Пустых: %(count)s", count=s["empty"]))
        c.setFillColor(MUTED)
        c.drawString(52, 14, _fit(c, _clean(" · ".join(facts)), REGULAR, 8.5, w - 150, 7))
        c.setFillColor(NAVY)
        c.setFont(BOLD, 18)
        c.drawRightString(w - 14, 24, "—" if s["mean"] is None else f'{s["mean"]}%')
        c.setFillColor(MUTED)
        c.drawRightString(w - 14, 12, _fit(c, _clean(_("Среднее")), REGULAR, 8, 80, 6.5))


class Pie(Flowable):
    """The bullet of a result: a small pie, filled as far as the test went."""

    def __init__(self, percent):
        super().__init__()
        self.percent = percent
        self.width, self.height = 12, 12

    def wrap(self, *_args):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(TRACK)
        c.circle(6, 6, 6, stroke=0, fill=1)
        if self.percent:
            c.setFillColor(ACCENT)
            if self.percent >= 100:
                c.circle(6, 6, 6, stroke=0, fill=1)
            else:
                c.wedge(0, 0, 12, 12, 90, -3.6 * self.percent, stroke=0, fill=1)


class Empty(Flowable):
    """An account with no finished work yet."""

    def __init__(self, title, text):
        super().__init__()
        self.title, self.text = title, text
        self.width, self.height = WIDTH, 120

    def wrap(self, *_args):
        return self.width, self.height

    def draw(self):
        c, w, h = self.canv, self.width, self.height
        c.setFillColor(SOFT)
        c.roundRect(0, 0, w, h, 14, stroke=0, fill=1)
        c.setFillColor(NAVY)
        c.drawCentredString(w / 2, h / 2 + 4, _fit(c, self.title, BOLD, 15, w - 48))
        c.setFillColor(MUTED)
        c.drawCentredString(w / 2, h / 2 - 16, _fit(c, self.text, REGULAR, 10, w - 48, 7))


def _chrome(title, student):
    """A canvas that knows the page count, so the footer can say «Страница 2 из 5»."""

    class PagedCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            for number, state in enumerate(self._pages, 1):
                self.__dict__.update(state)
                self._decorate(number, len(self._pages))
                super().showPage()
            super().save()

        def _decorate(self, number, total):
            if number > 1:  # the first page has the hero instead
                self.setFillColor(ACCENT)
                self.setFont(WORDMARK, 9)
                self.drawString(MARGIN, PAGE_H - 30, "MONDAY")
                self.setFillColor(MUTED)
                self.drawRightString(PAGE_W - MARGIN, PAGE_H - 30, _fit(self, f"{title} · {student}", REGULAR, 8.5, WIDTH - 90, 7))
            self.setStrokeColor(LINE)
            self.setLineWidth(.6)
            self.line(MARGIN, 34, PAGE_W - MARGIN, 34)
            self.setFillColor(MUTED)
            self.setFont(REGULAR, 8)
            self.drawString(MARGIN, 22, "Monday")
            self.drawRightString(PAGE_W - MARGIN, 22, _("Страница %(page)s из %(pages)s", page=number, pages=total))

    return PagedCanvas


def _summary(rows):
    mean = mean_percent(rows)
    scored = [p for p in map(percent_of, rows) if p is not None]
    return [
        (str(len(rows)), _("Всего работ")),
        ("—" if mean is None else f"{mean}%", _("Средний результат")),
        (f"{round(max(scored))}%" if scored else "—", _("Лучший результат")),
        (_time(sum(r["seconds"] for r in rows)), _("Время занятий")),
    ]


def _sector(sector):
    """One sector: its head, then a bullet per result."""
    body = ParagraphStyle("body", fontName=REGULAR, fontSize=9, leading=11.5, textColor=INK)
    date = ParagraphStyle("date", parent=body, fontSize=8, textColor=MUTED)
    number = ParagraphStyle("number", parent=body, alignment=TA_RIGHT)
    strong = ParagraphStyle("strong", parent=number, fontName=SEMIBOLD)
    muted = ParagraphStyle("muted", parent=number, fontSize=8, textColor=MUTED)

    data = [[SectorHead(sector), "", "", "", "", ""]]
    for r in sector["rows"]:
        percent = percent_of(r)
        shown = None if percent is None else round(percent)
        time = "—" if not r["seconds"] else _("%(minutes)s мин", minutes="<1" if r["seconds"] < 30 else r["minutes"])
        data.append([
            Pie(shown),
            Paragraph(format_date(r["date"], "dd.MM.y"), date),
            Paragraph(escape(_clean(r["title"]) or _clean(r["kind"])), body),
            Paragraph(f'{r["score"]} / {r["total"]}' if r["total"] and r["score"] is not None else "—", number),
            Paragraph("—" if shown is None else f"{shown}%", strong),
            Paragraph(escape(_clean(time)), muted),
        ])
    widths = [24, 58, WIDTH - 24 - 58 - 54 - 42 - 56, 54, 42, 56]
    table = LongTable(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 1), (-1, -1), 4), ("RIGHTPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING", (0, 1), (0, -1), 10),
        ("TOPPADDING", (0, 1), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 1), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, 0), 0), ("RIGHTPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, 0), 0), ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("LINEBELOW", (0, 1), (-1, -2), .4, LINE),
    ]))
    return table


def build_results_pdf(rows, student, exam, exported_on):
    """`rows` are student._results_rows(); returns the PDF as bytes."""
    _register_fonts()
    title = _("Мои результаты")
    student = _clean(student)
    meta = " · ".join(x for x in (exam, _("Выгружено %(date)s", date=format_date(exported_on, "d MMMM y"))) if x)

    story = [Hero(_clean(title), student, _clean(meta)), Spacer(1, 12)]
    if rows:
        sectors = group_by_sector(rows)
        story += [Tiles(_summary(rows)), Spacer(1, 8), Overview(sectors), Spacer(1, 16)]
        if any(s["empty"] for s in sectors):
            note = ParagraphStyle("note", fontName=REGULAR, fontSize=8, leading=10.5, textColor=MUTED)
            story[-1:] = [Spacer(1, 8), Paragraph(escape(_clean(_("Пустые попытки (0 баллов меньше чем за минуту) есть в списке, но не входят в средние."))), note), Spacer(1, 14)]
        for sector in sectors:
            story += [_sector(sector), Spacer(1, 14)]
    else:
        story.append(Empty(_("Пока нет завершённых работ"), _("Пройди первый тест или сессию, и результаты появятся здесь.")))

    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=MARGIN - FRAME_PAD, rightMargin=MARGIN - FRAME_PAD, topMargin=38, bottomMargin=40,
                            title=f"Monday · {title}", author="Monday", subject=student, creator="Monday",
                            lang=str(get_locale() or "ru"))
    doc.build(story, canvasmaker=_chrome(_clean(title), student))
    return out.getvalue()

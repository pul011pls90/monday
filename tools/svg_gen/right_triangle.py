"""Renderer for registry type: right_triangle."""
from .core import arc_path, line, svg_wrap, text

ALL_KEYS = ["hyp", "sin", "cos", "tg", "complement", "result"]


def render(params: dict, aria_label: str = "") -> str:
    legs = params.get("legs") or [4, 3]
    hyp = params.get("hyp", 5)
    special = params.get("special", "none")
    x0, y0, x1, y1 = 105, 245, 365, 85
    parts = [
        f'<polygon points="{x0},{y0} {x1},{y0} {x1},{y1}" class="soft f-fill"/>',
        f'<polyline points="{x1-18},{y0} {x1-18},{y0-18} {x1},{y0-18}" class="ax"/>',
        line(x0, y0, x1, y0, "main f-cos f-tg"),
        line(x1, y0, x1, y1, "main f-sin f-tg"),
        line(x0, y0, x1, y1, "main f-hyp f-result"),
        f'<path d="{arc_path(x0, y0, 44, 0, 31.6)}" class="main f-sin f-cos f-tg"/>',
        text(x0 + 56, y0 - 12, "30°" if special == "30-60-90" else ("45°" if special == "45-45-90" else "θ"), "var"),
        text((x0 + x1) / 2, y0 + 20, str(legs[0]), "lbl f-cos f-tg"),
        text(x1 + 14, (y0 + y1) / 2 + 4, str(legs[1]), "lbl f-sin f-tg", "start"),
        text((x0 + x1) / 2 - 14, (y0 + y1) / 2 - 10, str(hyp), "lbl f-hyp f-result", "end"),
    ]
    if special == "30-60-90":
        parts.append(text(x1 - 24, y1 + 32, "60°", "lbl f-complement"))
    elif params.get("angles"):
        parts.append(text(x1 - 28, y1 + 32, f"{params['angles'][-1]}°", "lbl f-complement"))
    return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or "Прямоугольный треугольник")

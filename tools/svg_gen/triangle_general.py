"""Renderer for registry type: triangle_general."""
from .core import arc_path, line, svg_wrap, text

ALL_KEYS = ["pair", "unknown", "included_angle", "height", "area"]


def render(params: dict, aria_label: str = "") -> str:
    rule = params.get("rule", "sine")
    a, b, c = params.get("a", "a"), params.get("b", "b"), params.get("c", "c")
    A, B, C = params.get("A", "A"), params.get("B", "B"), params.get("C", "C")
    ax, ay = 95, 250
    bx, by = 385, 250
    cx_, cy_ = 285, 78
    parts = [
        f'<polygon points="{ax},{ay} {bx},{by} {cx_},{cy_}" class="soft f-fill f-area"/>',
        line(ax, ay, bx, by, "main f-pair"),
        line(bx, by, cx_, cy_, "main f-pair f-included_angle"),
        line(ax, ay, cx_, cy_, "main f-unknown"),
        line(cx_, cy_, cx_, ay, "aux f-height"),
        f'<path d="{arc_path(bx, by, 38, 120, 180)}" class="main f-included_angle"/>',
        text(ax - 12, ay + 16, f"{A}", "lbl f-pair"),
        text(bx + 12, by + 16, f"{B}", "lbl f-pair f-included_angle"),
        text(cx_, cy_ - 12, f"{C}", "lbl f-unknown"),
        text((ax + bx) / 2, ay + 20, str(b), "lbl f-pair"),
        text((bx + cx_) / 2 + 16, (by + cy_) / 2, str(a), "lbl f-pair", "start"),
        text((ax + cx_) / 2 - 16, (ay + cy_) / 2, str(c), "lbl f-unknown", "end"),
    ]
    if rule == "area":
        parts.append(text(255, 195, "S = ½ab sin C", "lbl f-area"))
    return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or "Треугольник общего вида")

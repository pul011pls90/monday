"""Renderer for registry type: vector_rotation."""
import math
from .core import arc_path, line, svg_wrap, text

ALL_KEYS = ["a", "b", "R", "phi", "max"]


def render(params: dict, aria_label: str = "") -> str:
    a = float(params.get("a", 1))
    b = float(params.get("b", 1))
    x0, y0, w, h = 135, 240, 175, 145
    r_val = math.hypot(a, b)
    r_lbl = "√2" if abs(r_val - math.sqrt(2)) < 0.01 else f"{r_val:.2g}"
    parts = [
        f'<polygon points="{x0},{y0} {x0+w},{y0} {x0+w},{y0-h}" class="soft f-fill"/>',
        line(x0, y0, x0 + w, y0, "main f-a"),
        line(x0 + w, y0, x0 + w, y0 - h, "main f-b"),
        line(x0, y0, x0 + w, y0 - h, "main f-R f-max"),
        f'<path d="{arc_path(x0, y0, 44, 0, math.degrees(math.atan2(h, w)))}" class="main f-phi"/>',
        text(x0 + w / 2, y0 + 20, f"a = {int(a) if a.is_integer() else a}", "lbl f-a"),
        text(x0 + w + 14, y0 - h / 2, f"b = {int(b) if b.is_integer() else b}", "lbl f-b", "start"),
        text(x0 + w / 2 - 14, y0 - h / 2 - 12, f"R = {r_lbl}", "lbl f-R f-max", "end"),
        text(x0 + 58, y0 - 14, "φ", "var f-phi"),
    ]
    return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or "Векторная диаграмма гармонического вида")

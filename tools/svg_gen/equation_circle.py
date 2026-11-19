"""Renderer for registry type: equation_circle."""
import math
from .core import circle, grid_and_axes, line, svg_wrap, text

ALL_KEYS = ["line", "points", "general"]


def render(params: dict, aria_label: str = "") -> str:
    fn = params.get("fn", "sin")
    a = max(-1.0, min(1.0, float(params.get("a", 0.5))))
    cx, cy, r = 240, 160, 102
    parts = [grid_and_axes(cx, cy, 185, 130, 34), circle(cx, cy, r, "main")]
    if fn == "sin":
        ly = cy - a * r
        dx = r * math.sqrt(max(0.0, 1 - a * a))
        parts += [
            line(cx - 140, ly, cx + 140, ly, "aux f-line"),
            circle(cx + dx, ly, 4.5, "pt f-points f-general"),
            circle(cx - dx, ly, 4.5, "pt f-points f-general"),
            text(cx + dx + 10, ly - 8, "x₁", "lbl f-points f-general", "start"),
            text(cx - dx - 10, ly - 8, "x₂", "lbl f-points f-general", "end"),
            text(cx + 142, ly + 18, f"y = {a}", "lbl f-line", "end"),
        ]
    else:
        lx = cx + a * r
        dy = r * math.sqrt(max(0.0, 1 - a * a))
        parts += [
            line(lx, cy - 125, lx, cy + 125, "aux f-line"),
            circle(lx, cy - dy, 4.5, "pt f-points f-general"),
            circle(lx, cy + dy, 4.5, "pt f-points f-general"),
            text(lx + 10, cy - dy - 6, "x₁", "lbl f-points f-general", "start"),
            text(lx + 10, cy + dy + 14, "x₂", "lbl f-points f-general", "start"),
        ]
    return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or f"Решение уравнения {fn} x = {a} на окружности")

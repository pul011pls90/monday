"""Renderer for registry type: special_angles_circle."""
import math
from .core import circle, grid_and_axes, line, svg_wrap, text

ALL_KEYS = ["p0", "p30", "p45", "p60", "p90", "result"]


def render(params: dict, aria_label: str = "") -> str:
    angles = params.get("angles") or [0, 30, 45, 60, 90]
    cx, cy, r = 170, 235, 145
    parts = [grid_and_axes(cx, cy, 185, 180, 36), circle(cx, cy, r, "main")]
    for deg in angles:
        rd = math.radians(deg)
        px, py = cx + r * math.cos(rd), cy - r * math.sin(rd)
        lx, ly = cx + (r + 22) * math.cos(rd), cy - (r + 22) * math.sin(rd) + 4
        key = f"p{int(deg)}"
        parts += [
            line(cx, cy, px, py, f"aux f-{key}"),
            circle(px, py, 4.5, f"pt f-{key} f-result"),
            text(lx - 18 if deg == 90 else lx, ly, f"{int(deg)}°", f"lbl f-{key} f-result", "end" if deg == 90 else ("start" if math.cos(rd) > 0.2 else "middle")),
        ]
    return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or "Табличные углы на окружности")

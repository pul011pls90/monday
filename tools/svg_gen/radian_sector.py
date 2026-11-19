"""Renderer for registry type: radian_sector."""
import math
from .core import arc_path, line, svg_wrap, text

ALL_KEYS = ["arc", "sector", "radius", "angle"]


def render(params: dict, aria_label: str = "") -> str:
    r_val = params.get("r", 6)
    theta_lbl = params.get("theta", "π/3")
    deg = 60.0
    cx, cy, r = 135, 240, 175
    rad = math.radians(deg)
    px, py = cx + r * math.cos(rad), cy - r * math.sin(rad)
    sector_d = f"M {cx} {cy} L {cx + r} {cy} A {r} {r} 0 0 0 {px:.1f} {py:.1f} Z"
    parts = [
        f'<path d="{sector_d}" class="soft f-fill f-sector"/>',
        line(cx, cy, cx + r, cy, "main f-radius"),
        line(cx, cy, px, py, "main f-radius"),
        f'<path d="{arc_path(cx, cy, r, 0, deg)}" class="main f-arc"/>',
        f'<path d="{arc_path(cx, cy, 46, 0, deg)}" class="main f-angle"/>',
        text(cx + r / 2, cy + 20, f"r = {r_val}", "lbl f-radius"),
        text(cx + 62, cy - 20, f"θ = {theta_lbl}", "lbl f-angle", "start"),
        text(cx + r * 0.88 + 14, cy - r * 0.45, "s = rθ", "lbl f-arc", "start"),
        text(cx + r * 0.45, cy - r * 0.25, "A = ½r²θ", "lbl f-sector"),
    ]
    return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or "Сектор окружности: длина дуги и площадь")

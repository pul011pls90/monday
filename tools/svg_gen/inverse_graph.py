"""Renderer for registry type: inverse_graph."""
import math
from .core import circle, grid_and_axes, line, plot_curve, svg_wrap, text

ALL_KEYS = ["arcsin_point", "arccos_point", "range"]


def render(params: dict, aria_label: str = "") -> str:
    fn_name = params.get("fn", "arcsin")
    cx, cy = 240, 170
    sx, sy = 95, 58
    parts = [grid_and_axes(cx, cy, 185, 130, 32)]
    if fn_name in ("arcsin", "both"):
        parts.append(plot_curve(math.asin, -1, 1, cx, cy, sx, sy, "main f-arcsin_point f-range"))
    if fn_name in ("arccos", "both"):
        parts.append(plot_curve(math.acos, -1, 1, cx, cy, sx, sy, "main f-arccos_point f-range"))
    if fn_name == "arctg":
        parts += [
            line(55, cy - math.pi / 2 * sy, 425, cy - math.pi / 2 * sy, "aux f-range"),
            line(55, cy + math.pi / 2 * sy, 425, cy + math.pi / 2 * sy, "aux f-range"),
            plot_curve(math.atan, -2.1, 2.1, cx, cy, sx, sy, "main f-range"),
        ]
    def _num(v, default=0.0):
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(eval(str(v).replace("pi", "math.pi"), {"__builtins__": {}, "math": math}))
        except Exception:
            return float(default)

    for idx, pt in enumerate(params.get("points") or []):
        if isinstance(pt, dict):
            x = _num(pt.get("x", -0.5), -0.5)
            y = _num(pt.get("y", math.asin(x) if idx == 0 else math.acos(x)))
            lbl = pt.get("label", "")
        else:
            x = _num(pt[0], -0.5)
            y = _num(pt[1]) if len(pt) > 1 else (math.asin(x) if idx == 0 else math.acos(x))
            lbl = str(pt[2]) if len(pt) > 2 else ""
        cls = "f-arcsin_point" if idx == 0 else "f-arccos_point"
        parts += [circle(cx + x * sx, cy - y * sy, 4.5, f"pt {cls}"), text(cx + x * sx - 10, cy - y * sy - 10, lbl, f"lbl {cls}", "end")]
    return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or f"График обратной функции {fn_name}")

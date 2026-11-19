"""Renderer for registry type: wave_graph."""
import math
from .core import circle, grid_and_axes, line, plot_curve, svg_wrap, text

ALL_KEYS = ["amplitude_period", "shift_midline", "range", "point", "midline", "intersections"]


def render(params: dict, aria_label: str = "") -> str:
    fn_name = params.get("fn", "sin")
    def _num(v, default=0.0):
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(eval(str(v).replace("pi", "math.pi"), {"__builtins__": {}, "math": math}))
        except Exception:
            return float(default)

    A = _num(params.get("A", 1), 1)
    B = _num(params.get("B", 1), 1)
    C = _num(params.get("C", 0), 0)
    D = _num(params.get("D", 0), 0)
    xr = params.get("x_range") or [-math.pi, 2 * math.pi]
    x0, x1 = _num(xr[0], -math.pi), _num(xr[1], 2 * math.pi)
    fn_map = {
        "sin": lambda x: A * math.sin(B * (x - C)) + D,
        "cos": lambda x: A * math.cos(B * (x - C)) + D,
        "tan": lambda x: A * math.tan(B * (x - C)) + D,
        "cos^2": lambda x: A * (math.cos(B * (x - C)) ** 2) + D,
        "sin^2": lambda x: A * (math.sin(B * (x - C)) ** 2) + D,
    }
    fn = fn_map.get(fn_name, fn_map["sin"])
    cx, cy = 140, 170
    sx = 340 / max(0.5, (x1 - x0))
    sy = 34 if abs(A) >= 2 else 65
    parts = [
        grid_and_axes(cx, cy, 185, 130, 32),
        plot_curve(fn, x0, x1, cx, cy, sx, sy, "main f-amplitude_period f-range"),
    ]
    mid = params.get("midline", D if D != 0 else None)
    if mid is not None:
        my = cy - float(mid) * sy
        parts += [line(45, my, 435, my, "aux f-midline f-shift_midline"), text(438, my - 6, f"y={mid}", "lbl f-midline", "end")]
    hline = params.get("horizontal_line")
    if hline is not None:
        hy = cy - float(hline) * sy
        parts += [line(45, hy, 435, hy, "aux f-intersections"), text(438, hy - 6, f"y={hline}", "lbl f-intersections", "end")]
    for pt in (params.get("points") or []):
        if isinstance(pt, dict):
            px_val = _num(pt.get("x", 0), 0)
            py_val = _num(pt.get("y", fn(px_val)), 0)
            lbl = pt.get("label", "")
        else:
            px_val = _num(pt[0], 0)
            py_val = _num(pt[1], fn(px_val)) if len(pt) > 1 else fn(px_val)
            lbl = str(pt[2]) if len(pt) > 2 else ""
        px = cx + px_val * sx
        py = cy - py_val * sy
        parts += [circle(px, py, 4.5, "pt f-point f-intersections"), text(px + 8, py - 8, lbl, "lbl f-point", "start")]
    return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or f"График функции {fn_name}")

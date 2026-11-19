"""Renderer for registry type: function_graph."""
import math
from .core import circle, grid_and_axes, line, plot_curve, svg_wrap, text

ALL_KEYS = ["hole", "same_curve", "point", "parts", "tangent", "inner", "slope", "antiderivative", "bounds", "area", "a_equals_3", "result", "upper", "lower", "cos_to_sin", "sec2_to_tan"]


def render(params: dict, aria_label: str = "") -> str:
    kind = params.get("kind", "limit")
    fn_expr = params.get("fn", "sin(5*x)/(2*x)")
    def _num(v, default=0.0):
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(eval(str(v).replace("pi", "math.pi"), {"__builtins__": {}, "math": math}))
        except Exception:
            return float(default)

    xr = params.get("x_range") or [-1.5, 1.5]
    x0, x1 = _num(xr[0], -1.5), _num(xr[1], 1.5)
    cx, cy = 240, 225 if kind in ("limit", "area") else 160
    sx = 340 / max(0.5, (x1 - x0))
    sy = 58

    def fn(x):
        import re
        safe = fn_expr.replace("^", "**")
        safe = re.sub(r"\b(atan|asin|acos|sin|cos|tan|sqrt|exp|log|pi)\b", r"math.\1", safe)
        return eval(safe, {"__builtins__": {}, "math": math, "x": x})

    parts = [grid_and_axes(cx, cy, 185, 125, 32)]
    if kind == "derivative_cycle":
        parts = [
            f'<rect x="75" y="55" width="120" height="52" rx="12" class="soft f-cos_to_sin"/>',
            f'<rect x="285" y="55" width="120" height="52" rx="12" class="soft f-cos_to_sin"/>',
            f'<rect x="285" y="210" width="120" height="52" rx="12" class="soft f-parts"/>',
            f'<rect x="75" y="210" width="120" height="52" rx="12" class="soft f-parts"/>',
            line(195, 81, 281, 81, "main f-cos_to_sin", 'marker-end="url(#ax)"'),
            line(345, 107, 345, 206, "main f-parts", 'marker-end="url(#ax)"'),
            line(285, 236, 199, 236, "main f-parts", 'marker-end="url(#ax)"'),
            line(135, 210, 135, 111, "main f-cos_to_sin", 'marker-end="url(#ax)"'),
            text(135, 86, "sin x", "var"),
            text(345, 86, "cos x", "var"),
            text(345, 241, "−sin x", "var"),
            text(135, 241, "−cos x", "var"),
            text(240, 165, "d/dx", "lbl f-sec2_to_tan"),
        ]
        return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or "Цикл производных и интегралов")

    if kind == "area" and params.get("shade"):
        s0, s1 = _num(params["shade"][0], 0), _num(params["shade"][1], 1)
        pts = []
        for i in range(41):
            xx = s0 + (s1 - s0) * i / 40
            yy = fn(xx)
            pts.append(f"{cx + xx * sx:.1f},{cy - yy * sy:.1f}")
        poly = f"{cx + s0 * sx:.1f},{cy} " + " ".join(pts) + f" {cx + s1 * sx:.1f},{cy}"
        parts.append(f'<polygon points="{poly}" class="soft f-fill f-area f-bounds f-result"/>')

    parts.append(plot_curve(fn, x0, x1, cx, cy, sx, sy, "main f-same_curve f-parts f-inner f-antiderivative f-a_equals_3"))
    hole = params.get("hole")
    if hole:
        hx_v = _num(hole["x"], 0) if isinstance(hole, dict) else _num(hole[0], 0)
        hy_v = _num(hole["y"], 0) if isinstance(hole, dict) else _num(hole[1], 0)
        hlbl = hole.get("label", "(0; 2,5)") if isinstance(hole, dict) else (str(hole[2]) if len(hole) > 2 else "")
        hx, hy = cx + hx_v * sx, cy - hy_v * sy
        parts += [
            line(55, hy, hx, hy, "aux f-hole f-point"),
            circle(hx, hy, 5, "hole f-hole f-point"),
            text(hx + 12, hy - 8, hlbl, "lbl f-hole f-point f-result", "start"),
        ]
    pt = params.get("point")
    if pt is not None:
        if isinstance(pt, dict):
            px_v = _num(pt["x"], 0)
            py_v = _num(pt["y"], fn(px_v))
            plbl = pt.get("label", "")
        elif isinstance(pt, (list, tuple)):
            px_v = _num(pt[0], 0)
            py_v = _num(pt[1], fn(px_v)) if len(pt) > 1 else fn(px_v)
            plbl = str(pt[2]) if len(pt) > 2 else ""
        else:
            px_v = _num(pt, 0)
            py_v = fn(px_v)
            plbl = ""
        px, py = cx + px_v * sx, cy - py_v * sy
        parts += [circle(px, py, 4.5, "pt f-point f-tangent f-slope f-result"), text(px + 10, py - 8, plbl, "lbl f-point f-slope", "start")]
    return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or "График функции")

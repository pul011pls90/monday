"""Renderer for registry type: angle_relation."""
import math
from .core import arc_path, circle, grid_and_axes, line, svg_wrap, text

ALL_KEYS = ["mirror", "result", "split_angle", "terms", "sin2a", "cos2a", "half", "value", "alpha", "three_alpha"]


def render(params: dict, aria_label: str = "") -> str:
    rel = params.get("relation", "pi-alpha")
    a_deg = float(params.get("alpha_deg", 30))
    b_deg = float(params.get("beta_deg", 30))
    cx, cy, r = 240, 160, 102

    def pt(d):
        rd = math.radians(d)
        return cx + r * math.cos(rd), cy - r * math.sin(rd), math.cos(rd), math.sin(rd)

    target_map = {
        "pi-alpha": 180 - a_deg,
        "pi+alpha": 180 + a_deg,
        "2pi-alpha": 360 - a_deg,
        "alpha+beta": a_deg + b_deg,
        "2alpha": 2 * a_deg,
        "alpha/2": a_deg / 2,
        "3alpha": 3 * a_deg,
    }
    t_deg = target_map.get(rel, 180 - a_deg)
    ax, ay, ac, as_ = pt(a_deg)
    tx, ty, tc, ts = pt(t_deg)

    parts = [
        grid_and_axes(cx, cy, 185, 130, 34),
        circle(cx, cy, r, "main"),
        line(cx, cy, ax, ay, "main f-alpha f-terms"),
        circle(ax, ay, 4.5, "pt f-alpha"),
        text(ax + 14 * ac, ay - 14 * as_, f"α={int(a_deg)}°", "lbl f-alpha", "start" if ac >= 0 else "end"),
        f'<path d="{arc_path(cx, cy, 34, 0, a_deg)}" class="main f-alpha"/>',
        line(cx, cy, tx, ty, "main f-result f-mirror f-sin2a f-cos2a f-half f-three_alpha f-split_angle"),
        circle(tx, ty, 4.5, "pt f-result f-value f-mirror f-half f-three_alpha"),
        line(ax, ay, tx, ty, "aux f-mirror f-split_angle"),
        f'<path d="{arc_path(cx, cy, 50, 0, t_deg)}" class="main f-result f-split_angle f-half f-three_alpha"/>',
        text(tx + 16 * tc, ty - 16 * ts, f"{int(t_deg) if t_deg.is_integer() else t_deg}°", "lbl f-result f-value f-sin2a f-cos2a f-half f-three_alpha", "start" if tc >= 0 else "end"),
    ]
    return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or f"Соотношение углов: {rel}")

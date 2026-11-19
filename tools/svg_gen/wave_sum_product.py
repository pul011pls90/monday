"""Renderer for registry type: wave_sum_product."""
import math
from .core import grid_and_axes, plot_curve, svg_wrap, text

ALL_KEYS = ["sum_diff_angles", "half_sum_half_diff", "result"]


def render(params: dict, aria_label: str = "") -> str:
    mode = params.get("mode", "sum")
    a = float(params.get("a_deg", 75))
    b = float(params.get("b_deg", 15))
    cx, cy = 65, 165
    if mode == "product":
        fn = lambda x: math.sin(2.5 * x) * math.cos(0.5 * x)
        lbl = f"sin {int(a)}°·cos {int(b)}°"
    else:
        fn = lambda x: 0.5 * (math.sin(2.5 * x) + math.sin(0.5 * x))
        lbl = f"sin {int(a)}° + sin {int(b)}°"
    parts = [
        grid_and_axes(cx, cy, 370, 120, 32),
        plot_curve(fn, 0, 2 * math.pi, cx, cy, 56, 82, "main f-result f-sum_diff_angles"),
        plot_curve(lambda x: math.sin(1.5 * x), 0, 2 * math.pi, cx, cy, 56, 70, "aux f-half_sum_half_diff"),
        text(240, 34, lbl, "lbl f-sum_diff_angles f-result"),
    ]
    return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or f"Волновая диаграмма: {lbl}")

"""Renderers for the 88 missing_formula_images types in illustration_specs.json."""
from __future__ import annotations

import math
import re
from .core import arc_path, circle, grid_and_axes, line, plot_curve, svg_wrap, text


def _nums(depict: str) -> list[str]:
    return re.findall(r"-?\d+(?:[.,/]\d+)?", depict or "")


def render_fraction_bar(item: dict) -> str:
    dep = item.get("depict", "")
    fracs = re.findall(r"(\d+)\s*/\s*(\d+)", dep)
    if not fracs:
        fracs = [("2", "3"), ("1", "4"), ("11", "12")]
    parts = [text(240, 36, item.get("name", "Дроби"), "lbl")]
    y = 75
    for idx, (a, b) in enumerate(fracs[:3]):
        n, d = max(1, int(a)), max(1, min(16, int(b)))
        bw, bh = 320, 34
        x0 = 80
        seg = bw / d
        for i in range(d):
            cls = "soft" if i < n else "grd"
            parts.append(f'<rect x="{x0 + i*seg:.1f}" y="{y}" width="{seg:.1f}" height="{bh}" class="{cls}"/>')
        parts.append(f'<rect x="{x0}" y="{y}" width="{bw}" height="{bh}" class="main"/>')
        parts.append(text(x0 + bw + 14, y + 22, f"{a}/{b}", "lbl", "start"))
        y += 66
    return svg_wrap("\n".join(parts), aria_label=dep or item.get("name", ""))


def render_percent_bar(item: dict) -> str:
    dep = item.get("depict", "")
    pcts = re.findall(r"(\d+)\s*%", dep)
    p = min(100, max(5, int(pcts[0]))) if pcts else 25
    x0, y0, bw, bh = 65, 130, 350, 44
    fill_w = bw * (p / 100.0)
    parts = [
        text(240, 56, item.get("name", "Проценты"), "lbl"),
        f'<rect x="{x0}" y="{y0}" width="{bw}" height="{bh}" rx="8" class="grd"/>',
        f'<rect x="{x0}" y="{y0}" width="{fill_w:.1f}" height="{bh}" rx="8" class="soft"/>',
        f'<rect x="{x0}" y="{y0}" width="{bw}" height="{bh}" rx="8" class="main"/>',
        text(x0 + fill_w / 2, y0 + 27, f"{p}%", "lbl"),
        text(x0, y0 + 70, "0%", "mut", "start"),
        text(x0 + bw, y0 + 70, "100%", "mut", "end"),
    ]
    return svg_wrap("\n".join(parts), aria_label=dep or item.get("name", ""))


def render_ratio_tape(item: dict) -> str:
    dep = item.get("depict", "")
    m = re.search(r"(\d+)\s*:\s*(\d+)", dep)
    a, b = (int(m.group(1)), int(m.group(2))) if m else (3, 5)
    a, b = max(1, min(8, a)), max(1, min(8, b))
    total = a + b
    x0, y0, bw, bh = 65, 132, 350, 42
    aw = bw * (a / total)
    parts = [
        text(240, 56, f"{item.get('name', 'Пропорция')} ({a}:{b})", "lbl"),
        f'<rect x="{x0}" y="{y0}" width="{aw:.1f}" height="{bh}" class="soft"/>',
        f'<rect x="{x0+aw:.1f}" y="{y0}" width="{bw-aw:.1f}" height="{bh}" class="grd"/>',
        f'<rect x="{x0}" y="{y0}" width="{bw}" height="{bh}" class="main"/>',
        line(x0 + aw, y0, x0 + aw, y0 + bh, "main"),
        text(x0 + aw / 2, y0 + 26, str(a), "lbl"),
        text(x0 + aw + (bw - aw) / 2, y0 + 26, str(b), "lbl"),
    ]
    return svg_wrap("\n".join(parts), aria_label=dep or item.get("name", ""))


def render_number_line(item: dict) -> str:
    dep = item.get("depict", "")
    cy = 165
    parts = [
        text(240, 56, item.get("name", "Числовая прямая"), "lbl"),
        line(48, cy, 432, cy, "ax", 'marker-end="url(#ax)"'),
    ]
    for i, val in enumerate(range(-3, 4)):
        px = 80 + i * 52
        parts.append(line(px, cy - 6, px, cy + 6, "ax"))
        parts.append(text(px, cy + 24, str(val), "mut"))
    if any(w in dep.lower() for w in ("отрез", "интервал", "[", "≤", "≥", "<", ">")):
        parts += [
            line(184, cy, 340, cy, "main"),
            circle(184, cy, 5, "pt"),
            circle(340, cy, 5, "hole" if "(" in dep or "<" in dep else "pt"),
        ]
    else:
        parts += [circle(288, cy, 5, "pt"), circle(184, cy, 5, "pt")]
    return svg_wrap("\n".join(parts), aria_label=dep or item.get("name", ""))


def render_power_blocks(item: dict) -> str:
    dep = item.get("depict", "")
    parts = [text(240, 48, item.get("name", "Степени"), "lbl")]
    for idx, (pw, h) in enumerate([(1, 32), (2, 64), (3, 128)]):
        x = 95 + idx * 110
        y = 240 - h
        parts.append(f'<rect x="{x}" y="{y}" width="64" height="{h}" rx="8" class="soft"/>')
        parts.append(text(x + 32, y - 10, f"a^{pw}", "var"))
    return svg_wrap("\n".join(parts), aria_label=dep or item.get("name", ""))


def render_sequence_plot(item: dict) -> str:
    dep = item.get("depict", "")
    is_geo = "геометр" in (item.get("name", "") + dep).lower()
    cx, cy = 75, 250
    parts = [
        text(240, 34, item.get("name", "Прогрессия"), "lbl"),
        grid_and_axes(cx, cy, 360, 190, 40, "n", "aₙ"),
    ]
    for n in range(1, 7):
        val = (1.5 ** (n - 1)) * 18 if is_geo else n * 24
        px = cx + n * 52
        py = cy - min(175, val)
        parts += [line(px, cy, px, py, "aux"), circle(px, py, 4.5, "pt"), text(px, cy + 16, str(n), "mut")]
    return svg_wrap("\n".join(parts), aria_label=dep or item.get("name", ""))


def render_area_model(item: dict) -> str:
    dep = item.get("depict", "")
    x0, y0, w1, w2, h1, h2 = 120, 75, 145, 95, 110, 75
    parts = [
        text(240, 38, item.get("name", "Площадь / произведение"), "lbl"),
        f'<rect x="{x0}" y="{y0}" width="{w1}" height="{h1}" class="soft"/>',
        f'<rect x="{x0+w1}" y="{y0}" width="{w2}" height="{h1}" class="grd"/>',
        f'<rect x="{x0}" y="{y0+h1}" width="{w1}" height="{h2}" class="grd"/>',
        f'<rect x="{x0+w1}" y="{y0+h1}" width="{w2}" height="{h2}" class="soft"/>',
        f'<rect x="{x0}" y="{y0}" width="{w1+w2}" height="{h1+h2}" class="main"/>',
        text(x0 + w1 / 2, y0 - 10, "a", "var"),
        text(x0 + w1 + w2 / 2, y0 - 10, "b", "var"),
        text(x0 - 16, y0 + h1 / 2 + 4, "a", "var"),
        text(x0 - 16, y0 + h1 + h2 / 2 + 4, "b", "var"),
        text(x0 + w1 / 2, y0 + h1 / 2 + 4, "a²", "var"),
        text(x0 + w1 + w2 / 2, y0 + h1 / 2 + 4, "ab", "var"),
        text(x0 + w1 / 2, y0 + h1 + h2 / 2 + 4, "ab", "var"),
        text(x0 + w1 + w2 / 2, y0 + h1 + h2 / 2 + 4, "b²", "var"),
    ]
    return svg_wrap("\n".join(parts), aria_label=dep or item.get("name", ""))


def render_parabola_graph(item: dict) -> str:
    cx, cy = 240, 210
    parts = [
        text(240, 30, item.get("name", "Парабола"), "lbl"),
        grid_and_axes(cx, cy, 185, 130, 32),
        plot_curve(lambda x: 0.45 * (x * x) - 1.2, -3.0, 3.0, cx, cy, 46, 52, "main"),
        circle(cx, cy + 1.2 * 52, 4.5, "pt"),
        circle(cx - math.sqrt(1.2 / 0.45) * 46, cy, 4.5, "pt"),
        circle(cx + math.sqrt(1.2 / 0.45) * 46, cy, 4.5, "pt"),
    ]
    return svg_wrap("\n".join(parts), aria_label=item.get("depict") or item.get("name", ""))


def render_line_graph(item: dict) -> str:
    cx, cy = 240, 170
    parts = [
        text(240, 30, item.get("name", "Прямая"), "lbl"),
        grid_and_axes(cx, cy, 185, 125, 32),
        plot_curve(lambda x: 0.65 * x + 0.5, -3.5, 3.5, cx, cy, 44, 44, "main"),
        circle(cx, cy - 0.5 * 44, 4.5, "pt"),
        text(cx + 10, cy - 26, "(0; b)", "lbl", "start"),
    ]
    return svg_wrap("\n".join(parts), aria_label=item.get("depict") or item.get("name", ""))


def render_log_exp(item: dict) -> str:
    is_log = "лог" in (item.get("name", "") + item.get("depict", "")).lower() or "log" in item.get("key", "").lower()
    cx, cy = 240, 175
    fn = (lambda x: math.log(x) if x > 0.05 else None) if is_log else (lambda x: math.exp(0.7 * x))
    parts = [
        text(240, 30, item.get("name", "Функция"), "lbl"),
        grid_and_axes(cx, cy, 185, 125, 32),
        plot_curve(fn, 0.1 if is_log else -2.5, 4.0 if is_log else 2.2, cx, cy, 44, 44, "main"),
        circle(cx + (44 if is_log else 0), cy - (0 if is_log else 44), 4.5, "pt"),
    ]
    return svg_wrap("\n".join(parts), aria_label=item.get("depict") or item.get("name", ""))


def render_triangle_shape(item: dict) -> str:
    ax, ay, bx, by, cx_, cy_ = 115, 245, 365, 245, 255, 85
    parts = [
        text(240, 42, item.get("name", "Треугольник"), "lbl"),
        f'<polygon points="{ax},{ay} {bx},{by} {cx_},{cy_}" class="soft"/>',
        line(cx_, cy_, cx_, ay, "aux"),
        text(cx_ + 10, (cy_ + ay) / 2, "h", "var", "start"),
        text((ax + bx) / 2, ay + 20, "a", "var"),
    ]
    return svg_wrap("\n".join(parts), aria_label=item.get("depict") or item.get("name", ""))


def render_count_tree(item: dict) -> str:
    parts = [
        text(240, 36, item.get("name", "Комбинаторика / вероятность"), "lbl"),
        line(95, 165, 225, 95, "main"),
        line(95, 165, 225, 235, "main"),
        line(225, 95, 365, 68, "main"),
        line(225, 95, 365, 122, "main"),
        line(225, 235, 365, 208, "main"),
        line(225, 235, 365, 262, "main"),
        circle(95, 165, 5, "pt"),
        circle(225, 95, 4.5, "pt"),
        circle(225, 235, 4.5, "pt"),
    ]
    for y in (68, 122, 208, 262):
        parts.append(circle(365, y, 4.5, "pt"))
    return svg_wrap("\n".join(parts), aria_label=item.get("depict") or item.get("name", ""))


def render_stat_chart(item: dict) -> str:
    parts = [text(240, 38, item.get("name", "Статистика"), "lbl"), line(75, 250, 405, 250, "ax"), line(75, 250, 75, 70, "ax")]
    for idx, h in enumerate([65, 125, 155, 95, 50]):
        x = 105 + idx * 58
        parts.append(f'<rect x="{x}" y="{250-h}" width="38" height="{h}" rx="4" class="soft"/>')
    return svg_wrap("\n".join(parts), aria_label=item.get("depict") or item.get("name", ""))


def render_angle_diag(item: dict) -> str:
    cx, cy = 240, 200
    parts = [
        text(240, 42, item.get("name", "Углы"), "lbl"),
        line(95, cy, 385, cy, "main"),
        line(cx - 75, cy + 75, cx + 110, cy - 110, "main"),
        f'<path d="{arc_path(cx, cy, 46, 0, 45)}" class="main"/>',
        text(cx + 62, cy - 14, "α", "var"),
    ]
    return svg_wrap("\n".join(parts), aria_label=item.get("depict") or item.get("name", ""))


def render_generic_card(item: dict) -> str:
    dep = item.get("depict") or item.get("name", "")
    words = dep.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 44:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    parts = [
        f'<rect x="44" y="54" width="392" height="212" rx="16" class="soft"/>',
        text(240, 96, item.get("name", ""), "lbl"),
    ]
    for i, ln in enumerate(lines[:4]):
        parts.append(text(240, 134 + i * 24, ln, "mut"))
    return svg_wrap("\n".join(parts), aria_label=dep)


FORMULA_TYPE_MAP = {
    "fraction_bar": render_fraction_bar,
    "percent_bar": render_percent_bar,
    "ratio_tape": render_ratio_tape,
    "word_problem_tape": render_ratio_tape,
    "number_line": render_number_line,
    "power_blocks": render_power_blocks,
    "exponent_ladder": render_power_blocks,
    "sequence_plot": render_sequence_plot,
    "area_model": render_area_model,
    "parabola_graph": render_parabola_graph,
    "graph_shift": render_parabola_graph,
    "line_graph": render_line_graph,
    "coordinate_plane": render_line_graph,
    "log_exp_graph": render_log_exp,
    "triangle_diagram": render_triangle_shape,
    "shape_diagram": render_triangle_shape,
    "count_tree": render_count_tree,
    "probability_diagram": render_count_tree,
    "stat_chart": render_stat_chart,
    "angle_diagram": render_angle_diag,
    "factor_view": render_generic_card,
    "root_square": render_power_blocks,
    "place_value": render_generic_card,
    "cancel_diagram": render_fraction_bar,
    "division_layout": render_generic_card,
    "unit_conversion": render_number_line,
}


def render_missing_formula(item: dict) -> str:
    vtype = item.get("type", "")
    fn = FORMULA_TYPE_MAP.get(vtype, render_generic_card)
    return fn(item)

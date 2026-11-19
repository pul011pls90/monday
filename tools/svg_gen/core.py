"""Core SVG primitives, CSS theme variables, and data-focus rules for tools/svg_gen."""
from __future__ import annotations

import html
import math

W = 480
H = 320
PAD = 24


def svg_wrap(body: str, focus_keys: list[str] | None = None, aria_label: str = "", view_box: str = f"0 0 {W} {H}") -> str:
    keys = sorted(set(focus_keys or []))
    focus_rules = "\n".join(
        f'  svg[data-focus~="{k}"] .f-{k} {{ opacity: 1; stroke: var(--answer); }}\n'
        f'  svg[data-focus~="{k}"] text.f-{k}, svg[data-focus~="{k}"] .f-{k} text {{ stroke: none; fill: var(--answer); font-weight: 700; }}\n'
        f'  svg[data-focus~="{k}"] .f-{k}.f-fill {{ fill: var(--answer-soft); stroke: var(--answer); }}'
        for k in keys
    )
    dim_rule = "  svg[data-focus] [class*='f-'] { opacity: .30; transition: opacity .15s, stroke .15s; }" if keys else ""
    aria = f' role="img" aria-label="{html.escape(aria_label)}"' if aria_label else ""
    safe_lbl = html.escape(aria_label or "Математическая иллюстрация")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}"{aria}>\n'
        f"<title>{safe_lbl}</title>\n"
        f"<desc>{safe_lbl}</desc>\n"
        f"<style>\n"
        f"  svg {{ --ink: #0B0B0C; --axis: #8A93B2; --muted-txt: #4E5775; --grid: #E3E8FA; --primary: #2F4FE0; --primary-soft: #E3E8FA; --answer: #E5484D; --answer-soft: rgba(229,72,77,.14); --muted: #B8C0DA; --bg: #FFFFFF; font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; }}\n"
        f"  @media (prefers-color-scheme: dark) {{ :root:not([data-theme='light']) svg {{ --ink: #F4F5F8; --axis: #7F8AA8; --muted-txt: #CBD5E1; --grid: #252B3D; --primary: #6B93FF; --primary-soft: #1B2542; --answer: #FF6B6B; --answer-soft: rgba(255,107,107,.18); --muted: #56607A; --bg: #0F131D; }} }}\n"
        f"  :root[data-theme='dark'] svg {{ --ink: #F4F5F8; --axis: #7F8AA8; --muted-txt: #CBD5E1; --grid: #252B3D; --primary: #6B93FF; --primary-soft: #1B2542; --answer: #FF6B6B; --answer-soft: rgba(255,107,107,.18); --muted: #56607A; --bg: #0F131D; }}\n"
        f"  @media (prefers-reduced-motion: reduce) {{ svg * {{ transition: none !important; }} }}\n"
        f"  .lbl {{ font-size: 18px; font-weight: 600; fill: var(--ink); paint-order: stroke; stroke: var(--bg); stroke-width: 4px; stroke-linejoin: round; }}\n"
        f"  .var {{ font-family: 'KaTeX_Math', Georgia, serif; font-style: italic; font-size: 19px; fill: var(--ink); paint-order: stroke; stroke: var(--bg); stroke-width: 4px; stroke-linejoin: round; }}\n"
        f"  .mut {{ font-size: 18px; fill: var(--muted-txt); paint-order: stroke; stroke: var(--bg); stroke-width: 4px; stroke-linejoin: round; }}\n"
        f"  .ax {{ stroke: var(--axis); stroke-width: 1.25; fill: none; }}\n"
        f"  .grd {{ stroke: var(--grid); stroke-width: 1; fill: none; }}\n"
        f"  .main {{ stroke: var(--primary); stroke-width: 2; fill: none; stroke-linecap: round; stroke-linejoin: round; }}\n"
        f"  .aux {{ stroke: var(--axis); stroke-width: 1.25; stroke-dasharray: 4 3; fill: none; }}\n"
        f"  .soft {{ fill: var(--primary-soft); stroke: var(--primary); stroke-width: 1.5; stroke-linejoin: round; }}\n"
        f"  .pt {{ fill: var(--primary); stroke: var(--bg); stroke-width: 1.5; }}\n"
        f"  .hole {{ fill: var(--bg); stroke: var(--primary); stroke-width: 2; }}\n"
        f"{dim_rule}\n"
        f"{focus_rules}\n"
        f"</style>\n"
        f"<defs><marker id='ax' viewBox='0 0 10 10' refX='8' refY='5' markerWidth='6' markerHeight='6' orient='auto'><path d='M1 1.5L9 5L1 8.5z' fill='var(--axis)'/></marker></defs>\n"
        f"{body}\n"
        f"</svg>\n"
    )


def line(x1: float, y1: float, x2: float, y2: float, cls: str = "main", extra: str = "") -> str:
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="{cls}" {extra}/>'


def circle(cx: float, cy: float, r: float, cls: str = "main", extra: str = "") -> str:
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" class="{cls}" {extra}/>'


def text(x: float, y: float, s: str, cls: str = "lbl", anchor: str = "middle") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" class="{cls}">{html.escape(str(s))}</text>'


def grid_and_axes(cx: float = 240, cy: float = 160, rx: float = 195, ry: float = 128, step: float = 32, xl: str = "x", yl: str = "y") -> str:
    parts = []
    for dx in range(-int(rx // step), int(rx // step) + 1):
        px = cx + dx * step
        parts.append(line(px, cy - ry, px, cy + ry, "grd"))
    for dy in range(-int(ry // step), int(ry // step) + 1):
        py = cy + dy * step
        parts.append(line(cx - rx, py, cx + rx, py, "grd"))
    parts.append(line(cx - rx, cy, cx + rx, cy, "ax", 'marker-end="url(#ax)"'))
    parts.append(line(cx, cy + ry, cx, cy - ry, "ax", 'marker-end="url(#ax)"'))
    parts.append(text(cx + rx + 8, cy + 4, xl, "var", "start"))
    parts.append(text(cx + 10, cy - ry + 6, yl, "var", "start"))
    return "\n".join(parts)


def plot_curve(fn, x0: float, x1: float, cx: float, cy: float, sx: float, sy: float, cls: str = "main", steps: int = 160, max_y: float = 3.2) -> str:
    segs, pts = [], []
    for i in range(steps + 1):
        x = x0 + (x1 - x0) * (i / steps)
        try:
            y = fn(x)
        except Exception:
            y = None
        if y is None or math.isnan(y) or math.isinf(y) or abs(y) > max_y:
            if len(pts) > 1:
                segs.append(pts)
            pts = []
            continue
        pts.append((cx + x * sx, cy - y * sy))
    if len(pts) > 1:
        segs.append(pts)
    return "\n".join(
        f'<path d="M {" L ".join(f"{px:.1f} {py:.1f}" for px, py in s)}" class="{cls}"/>'
        for s in segs
    )


def arc_path(cx: float, cy: float, r: float, a0_deg: float, a1_deg: float) -> str:
    a0, a1 = math.radians(a0_deg), math.radians(a1_deg)
    x0, y0 = cx + r * math.cos(a0), cy - r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy - r * math.sin(a1)
    large = 1 if abs(a1_deg - a0_deg) > 180 else 0
    sweep = 0 if a1_deg >= a0_deg else 1
    return f"M {x0:.1f} {y0:.1f} A {r:.1f} {r:.1f} 0 {large} {sweep} {x1:.1f} {y1:.1f}"

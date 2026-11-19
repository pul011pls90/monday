"""Renderer for registry type: angle_circle."""
import math
from .core import arc_path, circle, grid_and_axes, line, svg_wrap, text

ALL_KEYS = ["quadrant", "reference", "coords", "full_turn", "angle45", "x_coord", "y_coord", "mirror", "sin_leg", "cos_leg", "sign", "angle", "arc", "radian_label", "degree_label"]


def render(params: dict, aria_label: str = "") -> str:
    deg = float(params.get("angle_deg", 45))
    show = set(params.get("show") or ["arc", "degree_label"])
    mirror_deg = params.get("mirror_deg")
    cx, cy, r = 240, 160, 102
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    px, py = cx + r * c, cy - r * s
    anch = "start" if c > 0.2 else ("end" if c < -0.2 else "middle")

    parts = [grid_and_axes(cx, cy, 185, 130, 34), circle(cx, cy, r, "main")]
    if "quadrant_signs" in show:
        parts += [
            text(cx + 85, cy - 82, "I (+)", "lbl f-quadrant"),
            text(cx - 85, cy - 82, "II (sin+)", "lbl f-quadrant"),
            text(cx - 85, cy + 92, "III (tg+)", "lbl f-quadrant"),
            text(cx + 85, cy + 92, "IV (cos+)", "lbl f-quadrant"),
        ]
    if "arc" in show or "full_turn" in show:
        a1 = deg % 360 or 45
        parts.append(f'<path d="{arc_path(cx, cy, 34, 0, a1)}" class="main f-arc f-angle f-full_turn"/>')
    if "right_triangle_inside" in show:
        parts += [
            f'<polygon points="{cx},{cy} {px:.1f},{cy} {px:.1f},{py:.1f}" class="soft f-fill f-triangle"/>',
            line(cx, cy, px, cy, "main f-cos_leg f-x_coord"),
            line(px, cy, px, py, "main f-sin_leg f-y_coord"),
            text((cx + px) / 2, cy + 16, "cos", "var f-cos_leg f-x_coord"),
            text(px + (10 if c >= 0 else -10), (cy + py) / 2, "sin", "var f-sin_leg f-y_coord", "start" if c >= 0 else "end"),
        ]
    parts += [
        line(cx, cy, px, py, "main f-angle f-angle45"),
        circle(px, py, 4.5, "pt f-coords f-sign"),
    ]
    if "degree_label" in show:
        parts.append(text(px + (14 * c), py - (14 * s), f"{int(deg) if deg.is_integer() else deg}°", "lbl f-degree_label f-angle45", anch))
    if "radian_label" in show:
        from fractions import Fraction
        fr = Fraction(round(deg), 180)
        rad_lbl = "π" if fr == 1 else (f"{fr.numerator}π/{fr.denominator}" if fr.numerator != 1 else f"π/{fr.denominator}")
        parts.append(text(px + (14 * c), py - (14 * s) + 18, rad_lbl, "lbl f-radian_label", anch))
    if "coords" in show:
        parts.append(text(px + (14 * c), py - (14 * s) - 6, f"({c:.2f}; {s:.2f})".replace(".", ","), "lbl f-coords f-x_coord f-y_coord", anch))
    if "reference_angle" in show:
        ref = abs(180 - (deg % 360)) if 90 < (deg % 360) < 270 else (360 - (deg % 360) if (deg % 360) >= 270 else deg % 360)
        parts.append(text(cx - 48 if c < 0 else cx + 48, cy - 12 if s >= 0 else cy + 20, f"α₀={int(ref)}°", "lbl f-reference"))
    if mirror_deg is not None or "mirror" in show:
        mdeg = float(mirror_deg if mirror_deg is not None else -deg)
        mrad = math.radians(mdeg)
        mx, my = cx + r * math.cos(mrad), cy - r * math.sin(mrad)
        parts += [
            line(px, py, mx, my, "aux f-mirror"),
            line(cx, cy, mx, my, "main f-mirror"),
            circle(mx, my, 4.5, "pt f-mirror"),
            text(mx + 12, my + 12, f"{int(mdeg)}°", "lbl f-mirror", "start"),
        ]
    return svg_wrap("\n".join(parts), ALL_KEYS, aria_label or f"Окружность с углом {deg}°")

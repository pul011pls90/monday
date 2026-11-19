"""Phase 3 Pass 1: Truth-spec SVG generator for P0 math accuracy, radical notation, and text overlaps."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORMULAS_DIR = ROOT / "monday" / "static" / "img" / "formulas"

STYLE_BLOCK = """<style>
  svg {
    --bg: #FFFFFF;
    --soft: #EEF2FF;
    --soft-red: #FEE2E2;
    --ink: #0B0B0C;
    --muted: #4E5775;
    --axis: #8A93B2;
    --grid: #E3E8FA;
    --primary: #2F4FE0;
    --accent: #E5484D;
    --halo: #FFFFFF;
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) svg {
      --bg: #0F172A;
      --soft: #1E293B;
      --soft-red: #3B1A24;
      --ink: #F1F5F9;
      --muted: #CBD5E1;
      --axis: #64748B;
      --grid: #1E293B;
      --primary: #7AA2FF;
      --accent: #FB7185;
      --halo: #0F172A;
    }
  }
  :root[data-theme="dark"] svg {
    --bg: #0F172A;
    --soft: #1E293B;
    --soft-red: #3B1A24;
    --ink: #F1F5F9;
    --muted: #CBD5E1;
    --axis: #64748B;
    --grid: #1E293B;
    --primary: #7AA2FF;
    --accent: #FB7185;
    --halo: #0F172A;
  }
  .bg { fill: var(--bg); }
  .halo { paint-order: stroke; stroke: var(--halo); stroke-width: 4px; stroke-linejoin: round; }
  .lbl { fill: var(--ink); font-size: 18px; font-weight: 700; }
  .tick { fill: var(--muted); font-size: 18px; font-weight: 600; }
  .ax { stroke: var(--axis); stroke-width: 1.8; }
  .grid { stroke: var(--grid); stroke-width: 1; }
  .prim { stroke: var(--primary); fill: none; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }
  .acc { stroke: var(--accent); fill: none; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }
</style>"""


def radical_svg(x: float, y: float, w: float, h: float, index: str = "", body: str = "", color: str = "var(--ink)", fs: int = 20) -> str:
    """Render a proper vector radical sign with overbar and optional root index."""
    # Radical hook from (x, y + h*0.55) -> (x+4, y+h*0.55) -> (x+9, y+h) -> (x+15, y) -> (x+15+w, y)
    d = f"M {x:.1f} {y + h*0.58:.1f} L {x+4:.1f} {y + h*0.58:.1f} L {x+9:.1f} {y + h:.1f} L {x+16:.1f} {y:.1f} L {x+18+w:.1f} {y:.1f}"
    parts = [f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>']
    if index:
        parts.append(f'<text class="halo" x="{x + 7:.1f}" y="{y + h*0.42:.1f}" text-anchor="end" font-size="{max(18, fs-2)}" font-weight="700" fill="{color}">{index}</text>')
    if body:
        parts.append(f'<text class="halo" x="{x + 21:.1f}" y="{y + h*0.82:.1f}" font-size="{fs}" font-weight="700" fill="{color}">{body}</text>')
    return "\n  ".join(parts)


def gen_ru_ege_powers_roots_04() -> str:
    """Seed image: exact 1:1 coordinate graph of y = x vs y = |x| with numeric points (-3;-3) and (-3;3)."""
    W, H = 560, 380
    ox, oy = 230, 195  # origin
    scale = 38.0       # 1 unit = 38 px on both axes (exact 1:1 scale -> slope 1!)

    def mx(x: float) -> float:
        return ox + x * scale

    def my(y: float) -> float:
        return oy - y * scale

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img">',
        "<title>Сравнение корней чётной и нечётной степени: y = x и y = |x|</title>",
        "<desc>Координатная плоскость с графиками y = x (сплошная синяя прямая через (0; 0) с наклоном 1) и y = |x| (пунктирный красный график, совпадающий с y = x при x ≥ 0), с точками (−3; −3) и (−3; 3).</desc>",
        STYLE_BLOCK,
        "<defs>",
        '  <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M1 1.5L9 5L1 8.5z" fill="var(--axis)"/></marker>',
        "</defs>",
        f'<rect class="bg" width="{W}" height="{H}"/>',
    ]

    # Grid & ticks (-3..3)
    for v in range(-3, 4):
        px = mx(v)
        py = my(v)
        parts.append(f'<line class="grid" x1="{px:.1f}" y1="30" x2="{px:.1f}" y2="350"/>')
        parts.append(f'<line class="grid" x1="40" y1="{py:.1f}" x2="380" y2="{py:.1f}"/>')
        if v != 0:
            parts.append(f'<line class="ax" x1="{px:.1f}" y1="{oy-4}" x2="{px:.1f}" y2="{oy+4}"/>')
            parts.append(f'<text class="tick halo" x="{px:.1f}" y="{oy+22}" text-anchor="middle">{v}</text>')
            parts.append(f'<line class="ax" x1="{ox-4}" y1="{py:.1f}" x2="{ox+4}" y2="{py:.1f}"/>')
            parts.append(f'<text class="tick halo" x="{ox-10}" y="{py+6:.1f}" text-anchor="end">{v}</text>')

    # Axes
    parts.append(f'<line class="ax" x1="40" y1="{oy}" x2="382" y2="{oy}" marker-end="url(#arr)"/>')
    parts.append(f'<line class="ax" x1="{ox}" y1="350" x2="{ox}" y2="28" marker-end="url(#arr)"/>')
    parts.append(f'<text class="lbl halo" x="390" y="{oy+6}">x</text>')
    parts.append(f'<text class="lbl halo" x="{ox+12}" y="38">y</text>')
    parts.append(f'<text class="tick halo" x="{ox-10}" y="{oy+22}" text-anchor="end">0</text>')

    # Solid primary: y = x from (-3.4, -3.4) to (3.4, 3.4) — passes through (0, 0) with exact slope 1
    parts.append(f'<line class="prim" x1="{mx(-3.4):.1f}" y1="{my(-3.4):.1f}" x2="{mx(3.4):.1f}" y2="{my(3.4):.1f}"/>')

    # Dashed accent on top: y = |x| from (-3.4, 3.4) -> (0, 0) -> (3.4, 3.4)
    parts.append(
        f'<polyline class="acc" stroke-dasharray="8 6" points="{mx(-3.4):.1f},{my(3.4):.1f} {mx(0):.1f},{my(0):.1f} {mx(3.4):.1f},{my(3.4):.1f}"/>'
    )

    # Guide lines & concrete points at x = -3: (-3; 3) and (-3; -3)
    px3 = mx(-3)
    py_pos = my(3)
    py_neg = my(-3)
    parts.append(f'<line x1="{px3:.1f}" y1="{py_pos:.1f}" x2="{px3:.1f}" y2="{py_neg:.1f}" stroke="var(--axis)" stroke-width="1.5" stroke-dasharray="4 4"/>')
    parts.append(f'<circle cx="{px3:.1f}" cy="{py_pos:.1f}" r="5.5" fill="var(--accent)"/>')
    parts.append(f'<circle cx="{px3:.1f}" cy="{py_neg:.1f}" r="5.5" fill="var(--primary)"/>')
    parts.append(f'<circle cx="{mx(0):.1f}" cy="{my(0):.1f}" r="4.5" fill="var(--ink)"/>')
    parts.append(f'<text class="lbl halo" x="{px3-10:.1f}" y="{py_pos-10:.1f}" text-anchor="end" fill="var(--accent)">(−3; 3)</text>')
    parts.append(f'<text class="lbl halo" x="{px3-10:.1f}" y="{py_neg+22:.1f}" text-anchor="end" fill="var(--primary)">(−3; −3)</text>')

    # Legend box on right (x=396..548)
    parts.append('<rect x="396" y="135" width="154" height="190" rx="14" fill="var(--soft)" stroke="var(--grid)" stroke-width="1.5"/>')
    # Odd root item
    parts.append('<line class="prim" x1="408" y1="168" x2="432" y2="168"/>')
    parts.append(radical_svg(444, 152, 34, 24, index="n", body="xⁿ = x", color="var(--primary)", fs=19))
    parts.append('<text x="410" y="198" font-size="18" font-weight="600" fill="var(--muted)">n — нечётное</text>')
    # Even root item
    parts.append('<line class="acc" stroke-dasharray="6 5" x1="408" y1="238" x2="432" y2="238"/>')
    parts.append(radical_svg(448, 222, 38, 24, index="2k", body="x²ᵏ = |x|", color="var(--accent)", fs=19))
    parts.append('<text x="410" y="268" font-size="18" font-weight="600" fill="var(--muted)">2k — чётное</text>')
    # Coincidence note
    parts.append('<text x="410" y="302" font-size="18" font-weight="700" fill="var(--ink)">при x ≥ 0</text>')
    parts.append('<text x="410" y="322" font-size="18" font-weight="600" fill="var(--muted)">совпадают</text>')

    parts.append("</svg>")
    return "\n".join(parts)


def gen_ru_ege_powers_roots_02() -> str:
    W, H = 520, 320
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img">',
        "<title>Свойства корней n-й степени: нечётный и чётный показатели</title>",
        "<desc>Сравнение корня нечётной степени (результат x) и чётной степени (результат |x|) с числовыми примерами при x = −3.</desc>",
        STYLE_BLOCK,
        f'<rect class="bg" width="{W}" height="{H}"/>',
        '<rect x="20" y="24" width="480" height="122" rx="16" fill="var(--soft)" stroke="var(--grid)" stroke-width="1.5"/>',
        radical_svg(48, 48, 36, 28, index="n", body="aⁿ = a", color="var(--primary)", fs=24),
        '<text x="200" y="72" font-size="20" font-weight="700" fill="var(--muted)">(n — нечётное)</text>',
        radical_svg(48, 98, 62, 26, index="3", body="(−3)³ = −3", color="var(--ink)", fs=20),
        '<rect x="20" y="168" width="480" height="128" rx="16" fill="var(--soft-red)" stroke="var(--grid)" stroke-width="1.5"/>',
        radical_svg(56, 192, 46, 28, index="2k", body="a²ᵏ = |a|", color="var(--accent)", fs=24),
        '<text x="230" y="216" font-size="20" font-weight="700" fill="var(--muted)">(2k — чётное)</text>',
        radical_svg(56, 242, 62, 26, index="2", body="(−3)² = |−3| = 3", color="var(--ink)", fs=20),
        "</svg>",
    ])


def gen_ru_oge_powers_roots_02() -> str:
    W, H = 500, 320
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img">',
        "<title>Квадратный корень из квадрата числа: √(a²) = |a|</title>",
        "<desc>Тождество квадратного корня из квадрата с примерами для положительного и отрицательного числа.</desc>",
        STYLE_BLOCK,
        f'<rect class="bg" width="{W}" height="{H}"/>',
        '<rect x="24" y="24" width="452" height="106" rx="16" fill="var(--soft)" stroke="var(--grid)" stroke-width="1.5"/>',
        radical_svg(120, 54, 34, 30, body="a² = |a|", color="var(--primary)", fs=28),
        '<rect x="24" y="152" width="216" height="140" rx="14" fill="var(--soft)" stroke="var(--grid)" stroke-width="1.5"/>',
        '<text x="132" y="188" text-anchor="middle" font-size="19" font-weight="700" fill="var(--primary)">a = 3 ≥ 0</text>',
        radical_svg(56, 218, 34, 28, body="3² = 3", color="var(--ink)", fs=22),
        '<rect x="260" y="152" width="216" height="140" rx="14" fill="var(--soft-red)" stroke="var(--grid)" stroke-width="1.5"/>',
        '<text x="368" y="188" text-anchor="middle" font-size="19" font-weight="700" fill="var(--accent)">a = −3 &lt; 0</text>',
        radical_svg(274, 218, 66, 28, body="(−3)² = |−3| = 3", color="var(--ink)", fs=20),
        "</svg>",
    ])


def gen_root_sq() -> str:
    W, H = 480, 320
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img">',
        "<title>Квадрат со стороной |a| и корень из квадрата</title>",
        "<desc>Геометрический квадрат со стороной |a| и площадью a², иллюстрирующий равенство √(a²) = |a|.</desc>",
        STYLE_BLOCK,
        f'<rect class="bg" width="{W}" height="{H}"/>',
        '<rect x="64" y="54" width="170" height="170" rx="8" fill="var(--soft)" stroke="var(--primary)" stroke-width="3"/>',
        '<text x="149" y="148" text-anchor="middle" font-size="26" font-weight="700" fill="var(--primary)">S = a²</text>',
        '<text x="149" y="254" text-anchor="middle" font-size="22" font-weight="700" fill="var(--ink)">|a|</text>',
        '<text x="42" y="146" text-anchor="middle" font-size="22" font-weight="700" fill="var(--ink)">|a|</text>',
        radical_svg(266, 118, 32, 28, body="a² = |a|", color="var(--ink)", fs=24),
        "</svg>",
    ])


def gen_root_mul() -> str:
    W, H = 480, 320
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img">',
        "<title>Произведение квадратных корней</title>",
        "<desc>Корень произведения равен произведению корней: √(a · b) = √a · √b при a, b ≥ 0.</desc>",
        STYLE_BLOCK,
        f'<rect class="bg" width="{W}" height="{H}"/>',
        '<rect x="24" y="34" width="432" height="118" rx="16" fill="var(--soft)" stroke="var(--grid)" stroke-width="1.5"/>',
        radical_svg(60, 74, 52, 28, body="a · b", color="var(--primary)", fs=24),
        '<text x="150" y="98" font-size="24" font-weight="700" fill="var(--ink)">=</text>',
        radical_svg(176, 74, 24, 28, body="a", color="var(--ink)", fs=24),
        '<text x="228" y="98" font-size="24" font-weight="700" fill="var(--ink)">·</text>',
        radical_svg(246, 74, 24, 28, body="b", color="var(--ink)", fs=24),
        '<text x="240" y="198" text-anchor="middle" font-size="20" font-weight="700" fill="var(--muted)">Пример: a = 4, b = 9</text>',
        radical_svg(72, 224, 52, 28, body="4 · 9", color="var(--primary)", fs=22),
        '<text x="160" y="248" font-size="22" font-weight="700" fill="var(--ink)">= 2 · 3 = 6</text>',
        "</svg>",
    ])


def gen_csca_09_am_gm() -> str:
    W, H = 500, 320
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img">',
        "<title>Неравенство о среднем арифметическом и геометрическом</title>",
        "<desc>Полуокружность с диаметром a + b: радиус (a + b)/2 больше или равен высоте √(ab).</desc>",
        STYLE_BLOCK,
        f'<rect class="bg" width="{W}" height="{H}"/>',
        # Semicircle center (250, 220), radius R = 140 (a=200, b=80 -> h=sqrt(200*80)=126.5)
        '<path d="M 110 220 A 140 140 0 0 1 390 220 Z" fill="var(--soft)" stroke="var(--primary)" stroke-width="3"/>',
        '<line x1="250" y1="220" x2="250" y2="80" stroke="var(--axis)" stroke-width="2" stroke-dasharray="5 4"/>',
        '<line x1="310" y1="220" x2="310" y2="93.5" stroke="var(--accent)" stroke-width="3.5"/>',
        '<circle cx="250" cy="220" r="4.5" fill="var(--primary)"/>',
        '<circle cx="310" cy="220" r="4.5" fill="var(--accent)"/>',
        '<text class="lbl halo" x="210" y="246" text-anchor="middle" fill="var(--ink)">a</text>',
        '<text class="lbl halo" x="350" y="246" text-anchor="middle" fill="var(--ink)">b</text>',
        '<text class="lbl halo" x="240" y="150" text-anchor="end" fill="var(--primary)">(a+b)/2</text>',
        radical_svg(322, 138, 36, 26, body="ab", color="var(--accent)", fs=20),
        '<text x="250" y="290" text-anchor="middle" font-size="20" font-weight="700" fill="var(--ink)">(a + b) / 2 ≥</text>',
        radical_svg(330, 268, 36, 26, body="ab", color="var(--accent)", fs=20),
        "</svg>",
    ])


def main():
    targets = {
        "ru_ege_powers_roots_04.svg": gen_ru_ege_powers_roots_04(),
        "ru_ege_powers_roots_02.svg": gen_ru_ege_powers_roots_02(),
        "ru_oge_powers_roots_02.svg": gen_ru_oge_powers_roots_02(),
        "root_sq.svg": gen_root_sq(),
        "root_mul.svg": gen_root_mul(),
        "csca_09_am_gm.svg": gen_csca_09_am_gm(),
    }
    for fname, svg in targets.items():
        (FORMULAS_DIR / fname).write_text(svg, encoding="utf-8")
        print(f"Regenerated {fname}")


if __name__ == "__main__":
    main()

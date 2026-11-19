"""Fix text_overlap and text_clip in trig/*.svg cards caused by 28px font-bump in 720x450 viewBox."""
from __future__ import annotations

from pathlib import Path
from tools.image_audit.truth_specs import STYLE_BLOCK, radical_svg

ROOT = Path(__file__).resolve().parents[2]
TRIG_DIR = ROOT / "monday" / "static" / "img" / "trig"


def wrap(w: int, h: int, title: str, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img">\n'
        f"<title>{title}</title>\n<desc>{title}</desc>\n"
        f"{STYLE_BLOCK}\n"
        f'<rect class="bg" width="{w}" height="{h}"/>\n'
        f"{body}\n</svg>\n"
    )


def fix_reciprocal_quotient() -> str:
    body = """
  <rect x="18" y="18" width="484" height="304" rx="18" fill="var(--soft)" stroke="var(--primary)" stroke-width="2"/>
  <line x1="18" y1="158" x2="502" y2="158" stroke="var(--axis)" stroke-width="1.5"/>
  <text x="260" y="64" text-anchor="middle" font-size="21" font-weight="700" fill="var(--ink)">sin θ ↔ csc θ = 1 / sin θ</text>
  <text x="260" y="114" text-anchor="middle" font-size="21" font-weight="700" fill="var(--ink)">cos θ ↔ sec θ = 1 / cos θ</text>
  <text x="260" y="204" text-anchor="middle" font-size="21" font-weight="700" fill="var(--primary)">tan θ = sin θ / cos θ</text>
  <text x="260" y="250" text-anchor="middle" font-size="21" font-weight="700" fill="var(--primary)">cot θ = cos θ / sin θ</text>
  <text x="260" y="296" text-anchor="middle" font-size="21" font-weight="700" fill="var(--ink)">tan θ · cot θ = 1</text>
"""
    return wrap(520, 340, "Reciprocal and quotient identities", body)


def fix_inverse_trig() -> str:
    body = """
  <rect x="18" y="20" width="524" height="280" rx="18" fill="var(--soft)" stroke="var(--primary)" stroke-width="2"/>
  <text x="42" y="84" font-size="22" font-weight="700" fill="var(--primary)">arcsin x :  [−1; 1] → [−π/2; π/2]</text>
  <text x="42" y="160" font-size="22" font-weight="700" fill="var(--ink)">arccos x :  [−1; 1] → [0; π]</text>
  <text x="42" y="236" font-size="22" font-weight="700" fill="var(--accent)">arctan x :  ℝ → (−π/2; π/2)</text>
"""
    return wrap(560, 320, "Inverse trigonometric functions", body)


def fix_inverse_trig_integrals() -> str:
    body = f"""
  <rect x="18" y="24" width="524" height="122" rx="16" fill="var(--soft)" stroke="var(--primary)" stroke-width="2"/>
  <text x="42" y="96" font-size="22" font-weight="700" fill="var(--ink)">∫ dx /</text>
  {radical_svg(108, 72, 68, 28, body="a² − x²", color="var(--ink)", fs=22)}
  <text x="210" y="96" font-size="22" font-weight="700" fill="var(--primary)">= arcsin(x/a) + C</text>
  <rect x="18" y="174" width="524" height="122" rx="16" fill="var(--soft)" stroke="var(--primary)" stroke-width="2"/>
  <text x="42" y="244" font-size="22" font-weight="700" fill="var(--ink)">∫ dx / (a² + x²) =</text>
  <text x="224" y="244" font-size="22" font-weight="700" fill="var(--primary)">(1/a) arctan(x/a) + C</text>
"""
    return wrap(560, 320, "Integrals giving inverse trigonometric functions", body)


def fix_trig_integrals_log() -> str:
    body = """
  <rect x="18" y="24" width="524" height="122" rx="16" fill="var(--soft)" stroke="var(--primary)" stroke-width="2"/>
  <text x="42" y="94" font-size="22" font-weight="700" fill="var(--primary)">∫ tan x dx = −ln|cos x| + C</text>
  <rect x="18" y="174" width="524" height="122" rx="16" fill="var(--soft)" stroke="var(--primary)" stroke-width="2"/>
  <text x="42" y="244" font-size="22" font-weight="700" fill="var(--ink)">∫ sec x dx = ln|sec x + tan x| + C</text>
"""
    return wrap(560, 320, "Integrals of tan, cot, sec, csc", body)


def fix_trig_limits() -> str:
    body = """
  <rect x="18" y="24" width="524" height="122" rx="16" fill="var(--soft)" stroke="var(--primary)" stroke-width="2"/>
  <text x="280" y="94" text-anchor="middle" font-size="23" font-weight="700" fill="var(--primary)">lim (x → 0)  sin x / x = 1</text>
  <rect x="18" y="174" width="524" height="122" rx="16" fill="var(--soft)" stroke="var(--primary)" stroke-width="2"/>
  <text x="280" y="244" text-anchor="middle" font-size="23" font-weight="700" fill="var(--ink)">lim (x → 0)  (1 − cos x) / x² = 1/2</text>
"""
    return wrap(560, 320, "Fundamental trigonometric limits", body)


def fix_right_triangle() -> str:
    body = """
  <polygon points="80,260 360,260 360,70" fill="var(--soft)" stroke="var(--primary)" stroke-width="3" stroke-linejoin="round"/>
  <polyline points="338,260 338,238 360,238" fill="none" stroke="var(--primary)" stroke-width="2"/>
  <path d="M 135 260 A 55 55 0 0 0 125.5 229" fill="none" stroke="var(--accent)" stroke-width="2.5"/>
  <text class="halo" x="148" y="246" font-size="20" font-weight="700" fill="var(--accent)">θ</text>
  <text class="halo" x="220" y="292" text-anchor="middle" font-size="20" font-weight="700" fill="var(--ink)">Adjacent (cos θ)</text>
  <text class="halo" x="374" y="172" font-size="20" font-weight="700" fill="var(--ink)">Opposite</text>
  <text class="halo" x="374" y="198" font-size="20" font-weight="700" fill="var(--primary)">(sin θ)</text>
  <text class="halo" x="195" y="148" text-anchor="end" font-size="20" font-weight="700" fill="var(--primary)">Hypotenuse = 1</text>
"""
    return wrap(520, 320, "Right-triangle definitions", body)


def main():
    fixes = {
        "reciprocal-quotient.svg": fix_reciprocal_quotient(),
        "inverse-trig.svg": fix_inverse_trig(),
        "inverse-trig-integrals.svg": fix_inverse_trig_integrals(),
        "trig-integrals-log.svg": fix_trig_integrals_log(),
        "trig-limits.svg": fix_trig_limits(),
        "right-triangle.svg": fix_right_triangle(),
    }
    for fname, svg in fixes.items():
        (TRIG_DIR / fname).write_text(svg, encoding="utf-8")
        print(f"Fixed trig/{fname}")


if __name__ == "__main__":
    main()

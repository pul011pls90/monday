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


def fix_special_values() -> str:
    body = f"""
  <!-- 30-60-90 triangle (exact 1 : sqrt(3) : 2 proportions, base=115, height=199) -->
  <polygon points="44,268 159,268 159,69" fill="var(--soft)" stroke="var(--primary)" stroke-width="2.5" stroke-linejoin="round"/>
  <polyline points="141,268 141,250 159,250" fill="none" stroke="var(--primary)" stroke-width="2"/>
  <text class="halo" x="76" y="256" text-anchor="start" font-size="20" font-weight="700" fill="var(--primary)">60°</text>
  <text class="halo" x="155" y="156" text-anchor="end" font-size="20" font-weight="700" fill="var(--primary)">30°</text>
  <text class="halo" x="101" y="294" text-anchor="middle" font-size="20" font-weight="700" fill="var(--ink)">1</text>
  {radical_svg(170, 154, 16, 24, body="3", color="var(--ink)", fs=20)}
  <text class="halo" x="88" y="158" text-anchor="end" font-size="20" font-weight="700" fill="var(--primary)">2</text>

  <!-- 45-45-90 triangle (exact 1 : 1 : sqrt(2) proportions, base=165, height=165) -->
  <polygon points="285,268 450,268 450,103" fill="var(--soft)" stroke="var(--primary)" stroke-width="2.5" stroke-linejoin="round"/>
  <polyline points="432,268 432,250 450,250" fill="none" stroke="var(--primary)" stroke-width="2"/>
  <text class="halo" x="326" y="256" text-anchor="start" font-size="20" font-weight="700" fill="var(--primary)">45°</text>
  <text class="halo" x="445" y="166" text-anchor="end" font-size="20" font-weight="700" fill="var(--primary)">45°</text>
  <text class="halo" x="367" y="294" text-anchor="middle" font-size="20" font-weight="700" fill="var(--ink)">1</text>
  <text class="halo" x="466" y="190" text-anchor="start" font-size="20" font-weight="700" fill="var(--ink)">1</text>
  {radical_svg(326, 162, 16, 24, body="2", color="var(--primary)", fs=20)}
"""
    return wrap(520, 320, "Special angle values", body)


def fix_cofunction() -> str:
    body = """
  <polygon points="105,250 415,250 415,58" fill="var(--soft)" stroke="var(--primary)" stroke-width="2.5" stroke-linejoin="round"/>
  <polyline points="395,250 395,230 415,230" fill="none" stroke="var(--primary)" stroke-width="2"/>
  <path d="M 162 250 A 57 57 0 0 0 153 220" fill="none" stroke="var(--accent)" stroke-width="2.2"/>
  <text class="halo" x="174" y="236" text-anchor="start" font-size="20" font-weight="700" fill="var(--primary)">θ</text>
  <text class="halo" x="405" y="132" text-anchor="end" font-size="20" font-weight="700" fill="var(--primary)">90° − θ</text>
  <text class="halo" x="260" y="290" text-anchor="middle" font-size="21" font-weight="700" fill="var(--ink)">cos θ = sin(90° − θ)</text>
"""
    return wrap(520, 320, "Cofunction identities", body)


def fix_auxiliary_angle() -> str:
    body = f"""
  <polygon points="110,255 410,255 410,65" fill="var(--soft)" stroke="var(--primary)" stroke-width="2.5" stroke-linejoin="round"/>
  <polyline points="390,255 390,235 410,235" fill="none" stroke="var(--primary)" stroke-width="2"/>
  <path d="M 165 255 A 55 55 0 0 0 156 226" fill="none" stroke="var(--accent)" stroke-width="2.2"/>
  <text class="halo" x="178" y="242" text-anchor="start" font-size="20" font-weight="700" fill="var(--primary)">φ</text>
  <text class="halo" x="260" y="286" text-anchor="middle" font-size="21" font-weight="700" fill="var(--ink)">a</text>
  <text class="halo" x="428" y="165" text-anchor="start" font-size="21" font-weight="700" fill="var(--ink)">b</text>
  <text class="halo" x="155" y="140" text-anchor="end" font-size="21" font-weight="700" fill="var(--primary)">R =</text>
  {radical_svg(160, 118, 72, 26, body="a² + b²", color="var(--primary)", fs=21)}
"""
    return wrap(520, 320, "Auxiliary angle (harmonic) form", body)


def main():
    fixes = {
        "reciprocal-quotient.svg": fix_reciprocal_quotient(),
        "inverse-trig.svg": fix_inverse_trig(),
        "inverse-trig-integrals.svg": fix_inverse_trig_integrals(),
        "trig-integrals-log.svg": fix_trig_integrals_log(),
        "trig-limits.svg": fix_trig_limits(),
        "right-triangle.svg": fix_right_triangle(),
        "special-values.svg": fix_special_values(),
        "cofunction.svg": fix_cofunction(),
        "auxiliary-angle.svg": fix_auxiliary_angle(),
    }
    for fname, svg in fixes.items():
        (TRIG_DIR / fname).write_text(svg, encoding="utf-8")
        print(f"Fixed trig/{fname}")


if __name__ == "__main__":
    main()

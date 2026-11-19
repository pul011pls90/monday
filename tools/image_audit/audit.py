"""Phase 2: Automated Playwright + SVG structural/style/geometry/math audit."""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = Path(__file__).resolve().parent
INVENTORY_CSV = AUDIT_DIR / "inventory.csv"
REPORT_CSV = AUDIT_DIR / "audit_report.csv"

PALETTE_LIGHT = {
    "#0B0B0C", "#8A93B2", "#E3E8FA", "#2F4FE0", "#E5484D",
    "#FFFFFF", "#F8FAFF", "#EEF2FF", "#4E5775", "#1F359E",
    "#15803D", "#DCFCE7", "#FEE2E2", "#D97706", "#FEF3C7",
    "#5E5E5E", "#101218", "#5A6278", "#E6ECF7", "#D4DDF2",
}


def parse_hex(c: str) -> tuple[int, int, int] | None:
    if not c:
        return None
    c = c.strip()
    m = re.match(r"^#([0-9a-fA-F]{6})$", c)
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    m = re.match(r"^rgb\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)$", c)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def rel_lum(rgb: tuple[int, int, int]) -> float:
    def ch(v):
        s = v / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    l1, l2 = rel_lum(c1), rel_lum(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def static_checks(row: dict, svg_text: str) -> list[tuple[str, str, str]]:
    """Return list of (defect_class, severity, detail)."""
    defects: list[tuple[str, str, str]] = []
    size_kb = float(row["size_kb"])
    if size_kb >= 30.0:
        defects.append(("structure", "P1", f"SVG size {size_kb} KB >= 30 KB"))

    # viewBox & fixed width/height
    svg_open = re.search(r"<svg\b[^>]*>", svg_text, re.I | re.S)
    tag = svg_open.group(0) if svg_open else ""
    if "viewBox" not in tag:
        defects.append(("structure", "P1", "Missing viewBox on <svg>"))
    if re.search(r'\bwidth\s*=\s*["\']\d', tag) or re.search(r'\bheight\s*=\s*["\']\d', tag):
        defects.append(("structure", "P2", "Fixed width/height attribute on <svg>"))

    if "<image" in svg_text.lower():
        defects.append(("structure", "P1", "Embedded raster <image> found"))
    if re.search(r"@import|fonts\.googleapis|<link\b|https?://(?!www\.w3\.org/2000/svg)", svg_text, re.I):
        defects.append(("structure", "P1", "External font or link reference found"))
    if "<title" not in svg_text.lower():
        defects.append(("structure", "P2", "Missing <title> element"))
    if "<desc" not in svg_text.lower():
        defects.append(("structure", "P2", "Missing <desc> element"))

    # Dark mode support
    has_dark = ("prefers-color-scheme: dark" in svg_text) or ('data-theme="dark"' in svg_text) or ("data-theme='dark'" in svg_text)
    if not has_dark:
        defects.append(("style_dark_mode", "P2", "No dark mode CSS variables / selectors inside SVG"))

    # Off-palette hex colors
    hexes = set(h.upper() for h in re.findall(r"#[0-9a-fA-F]{6}\b", svg_text))
    off = sorted(h for h in hexes if h not in PALETTE_LIGHT and not has_dark)
    if off:
        defects.append(("style_palette", "P2", f"Off-palette colors without theme vars: {', '.join(off[:6])}"))

    # Math notation plain-text approximations (only check visible <text> elements, not <title>/<desc>)
    visible_texts = " ".join(re.findall(r"<text\b[^>]*>(.*?)</text>", svg_text, re.I | re.S))
    if re.search(r"[ⁿ²ᵏ³⁴]√|√\([^)]+\)", visible_texts):
        defects.append(("math_notation", "P1", "Plain-text radical approximation (e.g. ⁿ√ / ²ᵏ√ / √(...)) without radical bar"))
    if re.search(r"неч\.|чет\.", visible_texts):
        defects.append(("math_notation", "P1", "Abbreviated parity label (неч./чет.) in diagram"))

    # Ambiguous symbolic point labels on function graphs like (-a, |a|) or (-a, -a)
    if row["type"] == "function graph" and re.search(r"\([−-]?[a-zA-Z],\s*[|−-]?[a-zA-Z|]+\)", svg_text):
        defects.append(("geometry_ambiguous_var", "P1", "Symbolic point label like (-a, |a|) instead of concrete numeric coordinates"))

    # Function graph missing numeric axis ticks
    if row["type"] == "function graph":
        nums = re.findall(r">\s*[−-]?\d+(?:[.,]\d+)?\s*<", svg_text)
        # Filter out single '0' origin only
        non_zero_nums = [n for n in nums if re.sub(r"[>\s<]", "", n) != "0"]
        if len(non_zero_nums) < 2:
            defects.append(("geometry_ticks", "P1", "Function graph lacks numeric axis ticks/labels"))

    return defects


JS_INSPECT = r"""
({ width, isDark }) => {
  const svg = document.querySelector("svg");
  if (!svg) return { error: "no svg" };
  const vb = svg.viewBox && svg.viewBox.baseVal ? svg.viewBox.baseVal : { x: 0, y: 0, width: 480, height: 320 };
  const vbW = vb.width || 480;
  const vbH = vb.height || 320;
  const vbX = vb.x || 0;
  const vbY = vb.y || 0;
  const rect = svg.getBoundingClientRect();
  const scale = rect.width ? rect.width / vbW : 1;

  const texts = [...svg.querySelectorAll("text")];
  const minFontPx = texts.length ? Math.min(...texts.map(t => parseFloat(getComputedStyle(t).fontSize || "14") * scale)) : 99;
  const tinyTexts = [];
  const clipped = [];
  const textBoxes = [];
  const lowContrast = [];

  const parseRgb = (s) => {
    const m = (s || "").match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    return m ? [+m[1], +m[2], +m[3]] : null;
  };
  const lum = ([r, g, b]) => {
    const ch = (v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4); };
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
  };
  const contrast = (a, b) => {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };

  // Determine effective SVG canvas background color
  const bgRect = svg.querySelector("rect[width='100%'], rect[width='" + vbW + "'], rect:first-of-type");
  let canvasBg = isDark ? [15, 23, 42] : [255, 255, 255];
  if (bgRect) {
    const r = parseRgb(getComputedStyle(bgRect).fill);
    if (r) canvasBg = r;
  }

  for (const t of texts) {
    const content = (t.textContent || "").trim();
    if (!content) continue;
    const cs = getComputedStyle(t);
    const fs = parseFloat(cs.fontSize || "14") * scale;
    if (fs < 11.9) {
      tinyTexts.push(`${content} (${fs.toFixed(1)}px)`);
    }
    let bb;
    try { bb = t.getBBox(); } catch (_) { continue; }
    if (bb.width === 0 || bb.height === 0) continue;
    if (bb.x < vbX - 1 || bb.y < vbY - 1 || bb.x + bb.width > vbX + vbW + 1 || bb.y + bb.height > vbY + vbH + 1) {
      clipped.push(content);
    }
    const r = t.getBoundingClientRect();
    textBoxes.push({ text: content, bb, rect: r, hasHalo: cs.paintOrder && cs.paintOrder.includes("stroke") && cs.stroke !== "none" });

    // Contrast check
    const fg = parseRgb(cs.fill);
    let bg = canvasBg;
    // Check if text sits inside a smaller non-canvas rect pill
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const stack = document.elementsFromPoint(cx, cy);
    for (const el of stack) {
      if (el !== t && el.tagName && el.tagName.toLowerCase() === "rect" && el !== bgRect) {
        const rf = parseRgb(getComputedStyle(el).fill);
        if (rf) { bg = rf; break; }
      }
    }
    if (fg && bg) {
      const cr = contrast(fg, bg);
      if (cr < 4.5) {
        lowContrast.push(`${content} (${cr.toFixed(2)}:1)`);
      }
    }
  }

  // Text-text overlaps (using rendered boundingClientRect so <g transform> is respected)
  const textOverlaps = [];
  for (let i = 0; i < textBoxes.length; i++) {
    for (let j = i + 1; j < textBoxes.length; j++) {
      const a = textBoxes[i].rect, b = textBoxes[j].rect;
      const ix = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
      const iy = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
      if (ix > 2 && iy > 2) {
        textOverlaps.push(`${textBoxes[i].text} <-> ${textBoxes[j].text}`);
      }
    }
  }

  // Text vs stroke/line overlap (only when text has no halo)
  const strokeOverlaps = [];
  for (const tb of textBoxes) {
    if (tb.hasHalo) continue;
    const r = tb.rect;
    if (r.width < 2 || r.height < 2) continue;
    const pts = [
      [r.left + r.width * 0.25, r.top + r.height * 0.5],
      [r.left + r.width * 0.5, r.top + r.height * 0.5],
      [r.left + r.width * 0.75, r.top + r.height * 0.5],
    ];
    let hit = false;
    for (const [px, py] of pts) {
      const stack = document.elementsFromPoint(px, py);
      for (const el of stack) {
        const tag = el.tagName ? el.tagName.toLowerCase() : "";
        if (tag === "line" || tag === "path" || tag === "polyline" || tag === "circle") {
          const elCs = getComputedStyle(el);
          if (elCs.stroke !== "none" && parseFloat(elCs.strokeWidth || "0") > 0) {
            hit = true;
            break;
          }
        }
      }
      if (hit) break;
    }
    if (hit) strokeOverlaps.push(tb.text);
  }

  return {
    minFontPx: Number(minFontPx.toFixed(1)),
    tinyTexts,
    clipped,
    textOverlaps,
    strokeOverlaps,
    lowContrast,
  };
}
"""


def run_audit():
    rows = list(csv.DictReader(INVENTORY_CSV.open(encoding="utf-8")))
    report_rows: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 600, "height": 500})

        for idx, row in enumerate(rows, 1):
            fp = ROOT / row["file"]
            if not fp.exists() or fp.suffix != ".svg":
                continue
            svg_text = fp.read_text(encoding="utf-8", errors="replace")

            # Static checks
            for d_class, sev, detail in static_checks(row, svg_text):
                report_rows.append({
                    "image_id": row["image_id"],
                    "defect_class": d_class,
                    "severity": sev,
                    "detail": detail,
                })

            # Render in Chromium at 320px (light) & 480px (dark)
            for width, is_dark in [(320, False), (480, True)]:
                theme_attr = ' data-theme="dark"' if is_dark else ""
                bg = "#0F172A" if is_dark else "#FFFFFF"
                html = f"""<!doctype html><html{theme_attr}><body style="margin:0;background:{bg}"><div style="width:{width}px">{svg_text}</div></body></html>"""
                page.set_content(html, wait_until="domcontentloaded")
                res = page.evaluate(JS_INSPECT, {"width": width, "isDark": is_dark})
                mode_lbl = f"{width}px {'dark' if is_dark else 'light'}"
                if res.get("tinyTexts") and width == 320 and not is_dark:
                    report_rows.append({
                        "image_id": row["image_id"],
                        "defect_class": "text_size",
                        "severity": "P1",
                        "detail": f"[{mode_lbl}] Font <12px: {', '.join(res['tinyTexts'][:4])}",
                    })
                if res.get("clipped") and width == 320 and not is_dark:
                    report_rows.append({
                        "image_id": row["image_id"],
                        "defect_class": "text_clip",
                        "severity": "P1",
                        "detail": f"[{mode_lbl}] Clipped text: {', '.join(res['clipped'][:4])}",
                    })
                if res.get("textOverlaps") and width == 320 and not is_dark:
                    report_rows.append({
                        "image_id": row["image_id"],
                        "defect_class": "text_overlap",
                        "severity": "P1",
                        "detail": f"[{mode_lbl}] Text overlap: {', '.join(res['textOverlaps'][:3])}",
                    })
                if res.get("strokeOverlaps") and width == 320 and not is_dark:
                    report_rows.append({
                        "image_id": row["image_id"],
                        "defect_class": "label_stroke_collision",
                        "severity": "P1",
                        "detail": f"[{mode_lbl}] Label collides with stroke (no halo): {', '.join(res['strokeOverlaps'][:4])}",
                    })
                if res.get("lowContrast"):
                    report_rows.append({
                        "image_id": row["image_id"],
                        "defect_class": "contrast",
                        "severity": "P1" if not is_dark else "P2",
                        "detail": f"[{mode_lbl}] Contrast <4.5:1: {', '.join(res['lowContrast'][:3])}",
                    })

        browser.close()

    with REPORT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["image_id", "defect_class", "severity", "detail"])
        w.writeheader()
        w.writerows(report_rows)

    from collections import Counter
    by_class = Counter(r["defect_class"] for r in report_rows)
    by_sev = Counter(r["severity"] for r in report_rows)
    affected = len({r["image_id"] for r in report_rows})
    print(f"Audited {len(rows)} images -> {len(report_rows)} defects across {affected} images")
    print("By severity:", dict(by_sev))
    print("By class:", dict(by_class))


if __name__ == "__main__":
    run_audit()

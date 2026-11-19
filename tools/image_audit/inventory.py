"""Phase 1: Inventory of all images referenced on /formulas and /formulas/t/*."""
from __future__ import annotations

import csv
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "monday" / "data" / "formulas"
TRIG_FILE = ROOT / "monday" / "data" / "trigonometry_formulas.json"
FORMULAS_IMG_DIR = ROOT / "monday" / "static" / "img" / "formulas"
EXAMPLES_IMG_DIR = ROOT / "monday" / "static" / "img" / "examples"
TRIG_IMG_DIR = ROOT / "monday" / "static" / "img" / "trig"
OUT_CSV = Path(__file__).resolve().parent / "inventory.csv"


def classify_svg(svg_text: str) -> str:
    low = svg_text.lower()
    if "<table" in low or ("grid" in low and low.count("<rect") >= 8 and low.count("<text") >= 6):
        return "table"
    has_axes = ("marker-end" in low or "fx-svg-axes" in low or "axis" in low) and (
        re.search(r">\s*y\s*<", low) or re.search(r">\s*x\s*<", low) or "y =" in low
    )
    has_curve = ("<path" in low and ("c" in low or "q" in low or "l" in low)) or "<polyline" in low
    if has_axes and has_curve and ("fx-svg-curve" in low or "y" in low):
        return "function graph"
    if ("number line" in low or "числовая" in low or "fx-svg-ticks" in low) or (
        low.count("<line") <= 14 and "marker-end" in low and not re.search(r">\s*y\s*<", low)
    ):
        if any(k in low for k in ("circle", "triangle", "угол", "треуг", "окруж", "radius", "гипотен", "sin", "cos")):
            return "geometric figure"
        return "number line"
    if any(k in low for k in ("polygon", "треуг", "окруж", "triangle", "circle", "параллел", "ромб", "трапец", "квадрат", "prism", "cylinder", "cone", "sphere")):
        return "geometric figure"
    if any(k in low for k in ("<rect", "<line", "<path", "<circle")):
        return "diagram"
    return "other"


def collect_inventory():
    usage = defaultdict(list)  # (image_id, rel_file) -> list of (exam, formula_id, name, desc)

    for json_path in sorted(DATA_DIR.glob("*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        exam = data.get("exam", json_path.stem.upper())
        for tmpl in data.get("templates", []):
            formulas_list = list(tmpl.get("formulas", []))
            for topic in tmpl.get("topics", []):
                formulas_list.extend(topic.get("formulas", []))
            for f in formulas_list:
                img_id = f.get("image") or ""
                img_path = f.get("image_path") or ""
                if not img_id and not img_path:
                    continue
                if img_path:
                    rel = f"monday/static/{img_path.lstrip('/')}"
                    if not img_id:
                        img_id = Path(img_path).stem
                else:
                    rel = f"monday/static/img/formulas/{img_id}.svg"
                usage[(img_id, rel)].append({
                    "exam": exam,
                    "formula_id": f.get("id", ""),
                    "name": f.get("name", ""),
                    "tex": f.get("tex", ""),
                })

    if TRIG_FILE.exists():
        trig = json.loads(TRIG_FILE.read_text(encoding="utf-8"))
        for c in trig.get("cards", []):
            cid = c["id"]
            # Check trig photo
            for ext in ("svg", "png", "webp"):
                p = TRIG_IMG_DIR / f"{cid}.{ext}"
                if p.exists():
                    rel = str(p.relative_to(ROOT))
                    usage[(f"trig/{cid}", rel)].append({
                        "exam": "TRIG",
                        "formula_id": cid,
                        "name": c.get("name", ""),
                        "tex": "; ".join(c.get("formulas", [])),
                    })
                    break
            # Check inline example visual
            ex_svg = EXAMPLES_IMG_DIR / f"{cid.replace('-', '_')}_0.svg"
            if ex_svg.exists():
                rel = str(ex_svg.relative_to(ROOT))
                usage[(f"examples/{ex_svg.stem}", rel)].append({
                    "exam": "TRIG_EX",
                    "formula_id": cid,
                    "name": c.get("name", ""),
                    "tex": "; ".join(c.get("formulas", [])),
                })

    rows = []
    shared_issues = []
    for (img_id, rel), refs in sorted(usage.items()):
        fp = ROOT / rel
        exists = fp.exists()
        size_kb = round(fp.stat().st_size / 1024, 2) if exists else 0.0
        svg_text = fp.read_text(encoding="utf-8", errors="replace") if exists and fp.suffix == ".svg" else ""
        img_type = classify_svg(svg_text) if svg_text else "other"
        formulas_str = " | ".join(f"{r['exam']}:{r['formula_id']} ({r['name']})" for r in refs)
        shared = len(refs) > 1
        rows.append({
            "image_id": img_id,
            "file": rel,
            "exists": "yes" if exists else "NO",
            "size_kb": f"{size_kb:.2f}",
            "usage_count": len(refs),
            "shared": "yes" if shared else "no",
            "formulas": formulas_str,
            "type": img_type,
        })
        if shared:
            names = [r["name"] for r in refs]
            shared_issues.append((img_id, len(refs), names))

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["image_id", "file", "exists", "size_kb", "usage_count", "shared", "formulas", "type"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUT_CSV}")
    missing = [r for r in rows if r["exists"] == "NO"]
    print(f"Missing files: {len(missing)}")
    print(f"Shared images: {len(shared_issues)}")
    for img_id, cnt, names in shared_issues[:20]:
        print(f"  shared {img_id} ({cnt}x): {names}")


if __name__ == "__main__":
    collect_inventory()

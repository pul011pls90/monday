"""Generate all 32 trigonometry example visuals and 88 missing formula images from illustration_specs.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.svg_gen import REGISTRY, render_missing_formula, render_visual  # noqa: E402

SPEC_PATH = Path("/Users/apple/Downloads/illustration_specs.json")
EXAMPLES_DIR = ROOT / "monday" / "static" / "img" / "examples"
FORMULAS_IMG_DIR = ROOT / "monday" / "static" / "img" / "formulas"
FORMULAS_DATA_DIR = ROOT / "monday" / "data" / "formulas"

PRIORITY_ORDER = [
    "fraction_bar", "percent_bar", "ratio_tape", "number_line",
    "power_blocks", "sequence_plot", "area_model", "parabola_graph", "line_graph",
]


def main():
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    FORMULAS_IMG_DIR.mkdir(parents=True, exist_ok=True)

    # Part 3: 32 trigonometry example visuals
    trig_generated = []
    for item in spec["trigonometry"]:
        fid = item["formula_id"]
        idx = item.get("example_index", 0)
        vis = item["visual"]
        svg = render_visual(vis["type"], vis.get("params", {}), aria_label=item.get("alt", item.get("title", "")))
        out = EXAMPLES_DIR / f"{fid}_{idx}.svg"
        out.write_text(svg, encoding="utf-8")
        trig_generated.append(out.name)
    print(f"Part 3: generated {len(trig_generated)} example SVGs in {EXAMPLES_DIR}")

    # Part 5: 88 missing formula images in priority order
    missing = list(spec["missing_formula_images"])
    order_idx = {t: i for i, t in enumerate(PRIORITY_ORDER)}
    missing.sort(key=lambda x: (order_idx.get(x.get("type", ""), 999), x["key"]))

    by_exam: dict[str, dict[str, str]] = {}
    for item in missing:
        exam, fid = item["key"].split("/", 1)
        vtype = item["type"]
        if vtype in REGISTRY:
            params = {}
            if vtype == "special_angles_circle":
                params = {"angles": [0, 30, 45, 60, 90]}
            elif vtype == "angle_circle":
                params = {"angle_deg": 45, "show": ["arc", "quadrant_signs", "degree_label"]}
            elif vtype == "right_triangle":
                params = {"legs": [4, 3], "hyp": 5}
            svg = render_visual(vtype, params, aria_label=item.get("depict") or item.get("name", ""))
        else:
            svg = render_missing_formula(item)

        stem = f"{exam.lower()}_{fid}" if (FORMULAS_IMG_DIR / f"{fid}.svg").exists() else fid
        out = FORMULAS_IMG_DIR / f"{stem}.svg"
        out.write_text(svg, encoding="utf-8")
        by_exam.setdefault(exam.upper(), {})[fid] = stem

    # Update image field in monday/data/formulas/*.json for those 88 formulas without changing any text
    updated_count = 0
    for json_path in sorted(FORMULAS_DATA_DIR.glob("*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        exam_code = data["exam"].upper()
        mapping = by_exam.get(exam_code)
        if not mapping:
            continue
        changed = False
        for tpl in data["templates"]:
            for top in tpl["topics"]:
                for f in top["formulas"]:
                    if f["id"] in mapping and not f.get("image"):
                        f["image"] = mapping[f["id"]]
                        updated_count += 1
                        changed = True
        if changed:
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Part 5: generated {len(missing)} formula SVGs, updated {updated_count} formula image fields")


if __name__ == "__main__":
    main()

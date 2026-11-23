"""Versioned exam content loader, fact verifier, and production preflight guard (Stage 4)."""
from __future__ import annotations

import json
import pathlib
from typing import Any

from .constants import EXAMS
from .models import Question

_EXAMS_DATA_DIR = pathlib.Path(__file__).resolve().parent / "data" / "exams"
UNVERIFIED_MARKER_PREFIX = "[требует подтверждения"


def _resolve_fact(node: Any, path_label: str, unverified_paths: list[str]) -> str:
    """Resolve a fact dict `{"value", "verified", "source"}` into string or blocking marker."""
    if not isinstance(node, dict):
        unverified_paths.append(f"{path_label} (missing fact object)")
        return f"{UNVERIFIED_MARKER_PREFIX}: {path_label}]"
    val = str(node.get("value") or "").strip()
    verified = bool(node.get("verified") is True)
    source = str(node.get("source") or "").strip()
    label = str(node.get("label") or path_label).strip()
    if not verified or not val or not source or UNVERIFIED_MARKER_PREFIX.lower() in val.lower():
        unverified_paths.append(f"{path_label} (verified={verified}, source={bool(source)})")
        return f"{UNVERIFIED_MARKER_PREFIX}: {label}]"
    return val


def list_exam_content_slugs(data_dir: pathlib.Path | None = None) -> list[str]:
    folder = data_dir or _EXAMS_DATA_DIR
    if not folder.is_dir():
        return []
    return sorted(p.stem.lower() for p in folder.glob("*.json") if p.is_file())


def load_exam_page_content(slug: str, *, data_dir: pathlib.Path | None = None) -> dict[str, Any] | None:
    """Load and validate a versioned exam content JSON file by slug (e.g., 'ort')."""
    clean_slug = (slug or "").strip().lower()
    if not clean_slug or not clean_slug.isalnum():
        return None
    folder = data_dir or _EXAMS_DATA_DIR
    path = folder / f"{clean_slug}.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None

    exam_code = str(raw.get("exam_code") or clean_slug.upper()).strip().upper()
    exam_meta = EXAMS.get(exam_code, {"label": exam_code, "country": "", "note": "", "min": 0, "max": 100})
    unverified: list[str] = []

    seo_raw = raw.get("seo") or {}
    seo_title = _resolve_fact(seo_raw.get("title"), f"{clean_slug}.seo.title", unverified)
    seo_desc = _resolve_fact(seo_raw.get("description"), f"{clean_slug}.seo.description", unverified)

    hero_raw = raw.get("hero") or {}
    hero = {
        "pill": _resolve_fact(hero_raw.get("pill"), f"{clean_slug}.hero.pill", unverified),
        "headline": _resolve_fact(hero_raw.get("headline"), f"{clean_slug}.hero.headline", unverified),
        "subheadline": _resolve_fact(hero_raw.get("subheadline"), f"{clean_slug}.hero.subheadline", unverified),
    }

    facts_list: list[dict[str, str]] = []
    facts_raw = raw.get("facts") or {}
    if isinstance(facts_raw, dict):
        for fkey, fnode in facts_raw.items():
            lbl = str((fnode or {}).get("label") or fkey)
            val = _resolve_fact(fnode, f"{clean_slug}.facts.{fkey}", unverified)
            src = str((fnode or {}).get("source") or "").strip()
            facts_list.append({"key": fkey, "label": lbl, "value": val, "source": src})
    if not facts_list:
        unverified.append(f"{clean_slug}.facts (empty)")

    sections: list[dict[str, str]] = []
    for idx, sec in enumerate(raw.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        sections.append(
            {
                "code": str(sec.get("code") or f"sec-{idx + 1}"),
                "title": _resolve_fact(sec.get("title"), f"{clean_slug}.sections[{idx}].title", unverified),
                "duration": _resolve_fact(sec.get("duration"), f"{clean_slug}.sections[{idx}].duration", unverified),
                "questions_count": _resolve_fact(
                    sec.get("questions_count"), f"{clean_slug}.sections[{idx}].questions_count", unverified
                ),
                "summary": _resolve_fact(sec.get("summary"), f"{clean_slug}.sections[{idx}].summary", unverified),
                "source": str((sec.get("title") or {}).get("source") or ""),
            }
        )
    if not sections:
        unverified.append(f"{clean_slug}.sections (empty)")

    scoring_raw = raw.get("scoring") or {}
    scoring_rules = [
        _resolve_fact(rnode, f"{clean_slug}.scoring.rules[{idx}]", unverified)
        for idx, rnode in enumerate(scoring_raw.get("rules") or [])
    ]
    if not scoring_rules:
        unverified.append(f"{clean_slug}.scoring.rules (empty)")
    scoring = {
        "headline": _resolve_fact(scoring_raw.get("headline"), f"{clean_slug}.scoring.headline", unverified),
        "rules": scoring_rules,
        "min_score": int(exam_meta.get("min", 0)),
        "max_score": int(exam_meta.get("max", 245)),
    }

    timeline: list[dict[str, str]] = []
    for idx, step in enumerate(raw.get("timeline") or []):
        if not isinstance(step, dict):
            continue
        timeline.append(
            {
                "step": str(step.get("step") or (idx + 1)),
                "title": _resolve_fact(step.get("title"), f"{clean_slug}.timeline[{idx}].title", unverified),
                "detail": _resolve_fact(step.get("detail"), f"{clean_slug}.timeline[{idx}].detail", unverified),
            }
        )
    if not timeline:
        unverified.append(f"{clean_slug}.timeline (empty)")

    faqs: list[dict[str, str]] = []
    for idx, item in enumerate(raw.get("faqs") or []):
        if not isinstance(item, dict):
            continue
        faqs.append(
            {
                "q": _resolve_fact(item.get("q"), f"{clean_slug}.faqs[{idx}].q", unverified),
                "a": _resolve_fact(item.get("a"), f"{clean_slug}.faqs[{idx}].a", unverified),
            }
        )
    if not faqs:
        unverified.append(f"{clean_slug}.faqs (empty)")

    public_formulas = [
        {
            "topic": str(f.get("topic") or ""),
            "title": str(f.get("title") or ""),
            "latex": str(f.get("latex") or ""),
            "note": str(f.get("note") or ""),
        }
        for f in (raw.get("public_formulas") or [])
        if isinstance(f, dict) and f.get("title") and f.get("latex")
    ]

    return {
        "schema_version": int(raw.get("schema_version") or 1),
        "slug": clean_slug,
        "code": exam_code,
        "label": str(exam_meta.get("label") or exam_code),
        "country": str(exam_meta.get("country") or ""),
        "note": str(exam_meta.get("note") or ""),
        "theme_accent": str(raw.get("theme_accent") or "#1F4FE0"),
        "seo_title": seo_title,
        "seo_description": seo_desc,
        "hero": hero,
        "facts": facts_list,
        "sections": sections,
        "scoring": scoring,
        "timeline": timeline,
        "public_formulas": public_formulas,
        "faqs": faqs,
        "unverified_paths": unverified,
        "all_verified": len(unverified) == 0,
    }


def collect_exam_content_preflight_blockers(
    *,
    data_dir: pathlib.Path | None = None,
    min_samples_per_page: int = 1,
) -> list[str]:
    """Check all exam content files for unverified facts and minimum public samples."""
    blockers: list[str] = []
    slugs = list_exam_content_slugs(data_dir)
    if "ort" not in slugs:
        blockers.append("Missing required exam content file for '/exams/ort' (ort.json).")
    if not slugs:
        return blockers

    sample_rows = Question.query.filter_by(status="published", is_public_sample=True).all()
    for slug in slugs:
        doc = load_exam_page_content(slug, data_dir=data_dir)
        if doc is None:
            blockers.append(f"Exam content file '{slug}.json' could not be parsed.")
            continue
        if not doc["all_verified"]:
            preview = ", ".join(doc["unverified_paths"][:4])
            blockers.append(
                f"Exam page '/exams/{slug}' has {len(doc['unverified_paths'])} unverified fact(s): {preview}."
            )
        exam_code = doc["code"]
        matching_samples = [
            q for q in sample_rows if exam_code in (q.exams or []) and (q.answer_type or "choice") != "written"
        ]
        if len(matching_samples) < max(1, int(min_samples_per_page)):
            blockers.append(
                f"Exam page '/exams/{slug}' ({exam_code}) has {len(matching_samples)} public sample(s); at least {min_samples_per_page} required."
            )
    return blockers

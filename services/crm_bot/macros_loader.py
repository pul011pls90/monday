"""Loader and idempotent seeder for Optima-style reply macros in docs/crm_bot/reply_macros.md."""
from __future__ import annotations

import pathlib
import re
from typing import Any

from monday.extensions import db
from monday.models import ReplyTemplate

DOCS_DIR = pathlib.Path(__file__).resolve().parents[2] / "docs" / "crm_bot"
MACROS_PATH = DOCS_DIR / "reply_macros.md"

_MACRO_HEADER_RE = re.compile(r"^##\s+Macro:\s*([a-zA-Z0-9_]+)\s*$", re.MULTILINE)


def parse_reply_macros_markdown(md_text: str) -> list[dict[str, Any]]:
    """Parse structured `## Macro: <slug>` sections into ReplyTemplate payloads."""
    matches = list(_MACRO_HEADER_RE.finditer(md_text))
    items: list[dict[str, Any]] = []
    for idx, m in enumerate(matches):
        slug = m.group(1).strip()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(md_text)
        block = md_text[start:end]

        cat_m = re.search(r"^- category:\s*(.+)$", block, re.MULTILINE)
        title_m = re.search(r"^- title:\s*(.+)$", block, re.MULTILINE)
        vars_m = re.search(r"^- variables:\s*(.*)$", block, re.MULTILINE)
        ru_m = re.search(r"```ru\s*\n([\s\S]*?)\n```", block)
        ky_m = re.search(r"```ky\s*\n([\s\S]*?)\n```", block)

        variables = [
            v.strip()
            for v in (vars_m.group(1) if vars_m else "").split(",")
            if v.strip()
        ]
        items.append(
            {
                "slug": slug,
                "category": (cat_m.group(1).strip() if cat_m else "general"),
                "title": (title_m.group(1).strip() if title_m else slug),
                "variables_json": variables,
                "body_ru": ru_m.group(1).strip() if ru_m else "",
                "body_ky": ky_m.group(1).strip() if ky_m else "",
            }
        )
    return items


def load_macros_from_docs(path: pathlib.Path | None = None) -> list[dict[str, Any]]:
    target = path or MACROS_PATH
    if not target.is_file():
        return []
    return parse_reply_macros_markdown(target.read_text(encoding="utf-8"))


def seed_reply_templates(path: pathlib.Path | None = None, *, commit: bool = True) -> int:
    """Idempotently upsert ReplyTemplate rows from docs/crm_bot/reply_macros.md. Returns created count."""
    from sqlalchemy import inspect as sa_inspect

    if not sa_inspect(db.engine).has_table("reply_templates"):
        return 0
    macros = load_macros_from_docs(path)
    created = 0
    for item in macros:
        existing = ReplyTemplate.query.filter_by(slug=item["slug"]).first()
        if existing is None:
            db.session.add(
                ReplyTemplate(
                    slug=item["slug"],
                    category=item["category"],
                    title=item["title"],
                    body_ru=item["body_ru"],
                    body_ky=item["body_ky"],
                    variables_json=item["variables_json"],
                    is_active=True,
                )
            )
            created += 1
        else:
            existing.category = item["category"]
            existing.title = item["title"]
            existing.body_ru = item["body_ru"]
            existing.body_ky = item["body_ky"]
            existing.variables_json = item["variables_json"]
    if commit:
        db.session.commit()
    return created


def render_macro_text(template: ReplyTemplate | dict[str, Any], language: str, variables: dict[str, Any] | None = None) -> str:
    """Fill `{variable}` placeholders safely without raising on missing keys."""
    lang = (language or "ru").lower()
    if isinstance(template, dict):
        raw = template.get("body_ky") if lang == "ky" else template.get("body_ru")
        if not raw:
            raw = template.get("body_ru") or template.get("body_ky") or ""
    else:
        raw = template.body_ky if lang == "ky" else template.body_ru
        if not raw:
            raw = template.body_ru or template.body_ky or ""

    defaults = {
        "name": "друг" if lang != "ky" else "досум",
        "subject": "подготовка" if lang != "ky" else "даярдык",
        "schedule": "уточняется у менеджера" if lang != "ky" else "менеджерден такталат",
        "branch": "онлайн / офлайн" if lang != "ky" else "онлайн / офлайн",
        "trial_time": "ближайшее свободное окно" if lang != "ky" else "жакынкы бош убакыт",
        "manager_name": "менеджер Monday" if lang != "ky" else "Monday менеджери",
        "price_placeholder": "Точную стоимость подберёт менеджер" if lang != "ky" else "Так баасын менеджер тандап берет",
    }
    ctx = {**defaults}
    for k, v in (variables or {}).items():
        if v is not None and str(v).strip():
            ctx[k] = str(v).strip()

    class _SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    return raw.format_map(_SafeDict(ctx))

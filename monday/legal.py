"""Legal scaffolding helpers and preflight checks (Stage 7)."""
from __future__ import annotations

import re

from flask import current_app

from .constants import CONTACTS

_MARKER_RE = re.compile(r"(\[требует подтверждения|TODO|Lorem\s+ipsum)", re.IGNORECASE)


def _confirm_marker(label: str) -> str:
    return f"[требует подтверждения: {label}]"


def get_legal_context() -> dict[str, object]:
    """Build legal operator and policy metadata from app config without hardcoding entity details."""
    cfg = current_app.config
    reviewed = bool(cfg.get("PUBLIC_LEGAL_REVIEWED", False))

    entity_name = (cfg.get("LEGAL_ENTITY_NAME") or "").strip()
    entity_id = (cfg.get("LEGAL_ENTITY_ID") or "").strip()
    entity_address = (cfg.get("LEGAL_ENTITY_ADDRESS") or "").strip() or (CONTACTS.get("address") or "").strip()
    contact_email = (cfg.get("LEGAL_CONTACT_EMAIL") or "").strip()
    jurisdiction = (cfg.get("LEGAL_JURISDICTION") or "").strip()
    effective_date = (cfg.get("LEGAL_EFFECTIVE_DATE") or "").strip()
    refund_days = int(cfg.get("LEGAL_REFUND_WINDOW_DAYS", 0) or 0)

    return {
        "reviewed": reviewed,
        "entity_name": entity_name or _confirm_marker("наименование юридического лица / ИП"),
        "entity_id": entity_id or _confirm_marker("ИНН / регистрационный номер"),
        "entity_address": entity_address or _confirm_marker("юридический адрес"),
        "contact_email": contact_email or _confirm_marker("email для юридических обращений и возвратов"),
        "jurisdiction": jurisdiction or _confirm_marker("применимое право / юрисдикция"),
        "effective_date": effective_date or _confirm_marker("дата вступления в силу"),
        "refund_window_days": refund_days,
        "refund_terms_text": (
            f"{refund_days}" if refund_days > 0 else _confirm_marker("срок и условия возврата по выбранному платёжному провайдеру")
        ),
        "raw_entity_name": entity_name,
        "raw_contact_email": contact_email,
    }


def collect_legal_config_blockers() -> list[str]:
    """Return missing legal configuration/review items for `site-preflight`."""
    blockers: list[str] = []
    cfg = current_app.config
    required_fields = (
        ("LEGAL_ENTITY_NAME", "legal entity name / operator"),
        ("LEGAL_ENTITY_ID", "taxpayer / registration ID"),
        ("LEGAL_ENTITY_ADDRESS", "registered legal address"),
        ("LEGAL_CONTACT_EMAIL", "legal & refund contact email"),
        ("LEGAL_JURISDICTION", "governing law / jurisdiction"),
        ("LEGAL_EFFECTIVE_DATE", "legal policy effective date"),
    )
    for key, desc in required_fields:
        val = (cfg.get(key) or "").strip()
        if not val:
            blockers.append(f"Missing {key} ({desc}) in legal configuration.")
        elif _MARKER_RE.search(val):
            blockers.append(f"{key} contains unfinished marker text.")
    if int(cfg.get("LEGAL_REFUND_WINDOW_DAYS", 0) or 0) <= 0:
        blockers.append("Missing positive LEGAL_REFUND_WINDOW_DAYS for refund policy.")
    return blockers

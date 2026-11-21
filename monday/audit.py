"""Central helper for recording immutable AuditLog entries."""
from __future__ import annotations

from .extensions import db
from .models import AuditLog, utcnow


def write_audit_log(
    *,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    old_value=None,
    new_value=None,
    reason: str = "",
) -> AuditLog:
    """Append an AuditLog entry to the current DB session (caller commits)."""
    entry = AuditLog(
        actor_id=actor_id,
        action=(action or "")[:64],
        entity_type=(entity_type or "")[:40],
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        reason=(reason or "").strip()[:300],
        timestamp=utcnow(),
    )
    db.session.add(entry)
    return entry

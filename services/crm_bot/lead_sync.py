"""Lead deduplication, timeline updates, stage moves, and spam soft-archiving for Telegram CRM Bot."""
from __future__ import annotations

from monday.audit import write_audit_log
from monday.crm_intake import pick_next_manager_round_robin
from monday.extensions import db
from monday.models import AuditLog, Lead, LeadActivity, LeadTask, utcnow
from monday.phone_utils import normalize_messenger, normalize_phone
from .classifier import LeadClassificationResult


def _find_telegram_lead(
    *,
    chat_id_str: str,
    phone_e164: str | None,
    messenger_norm: str | None,
) -> tuple[Lead | None, Lead | None]:
    """Locate active non-archived open lead (first) or closed non-archived lead (second)."""
    active = Lead.is_archived.is_(False)

    # 1. Exact telegram_chat_id match
    open_lead = (
        Lead.query.filter(active, Lead.telegram_chat_id == chat_id_str, Lead.status.notin_(("won", "lost")))
        .order_by(Lead.id.desc())
        .first()
    )
    if open_lead is not None:
        return open_lead, None
    closed_lead = (
        Lead.query.filter(active, Lead.telegram_chat_id == chat_id_str, Lead.status.in_(("won", "lost")))
        .order_by(Lead.id.desc())
        .first()
    )

    # 2. Dedupe by normalized E.164 phone
    if phone_e164:
        open_by_phone = (
            Lead.query.filter(active, Lead.phone_e164 == phone_e164, Lead.status.notin_(("won", "lost")))
            .order_by(Lead.id.desc())
            .first()
        )
        if open_by_phone is not None:
            return open_by_phone, None
        if closed_lead is None:
            closed_lead = (
                Lead.query.filter(active, Lead.phone_e164 == phone_e164, Lead.status.in_(("won", "lost")))
                .order_by(Lead.id.desc())
                .first()
            )

    # 3. Dedupe by normalized telegram username
    if messenger_norm:
        open_by_msg = (
            Lead.query.filter(active, Lead.messenger_norm == messenger_norm, Lead.status.notin_(("won", "lost")))
            .order_by(Lead.id.desc())
            .first()
        )
        if open_by_msg is not None:
            return open_by_msg, None
        if closed_lead is None:
            closed_lead = (
                Lead.query.filter(active, Lead.messenger_norm == messenger_norm, Lead.status.in_(("won", "lost")))
                .order_by(Lead.id.desc())
                .first()
            )

    return None, closed_lead


def sync_telegram_lead(
    *,
    telegram_chat_id: int | str,
    telegram_username: str | None,
    sender_name: str,
    message_text: str,
    classification: LeadClassificationResult,
    shared_phone: str | None = None,
    sla_minutes: int = 15,
) -> tuple[Lead, str, AuditLog]:
    """Create, update, or soft-archive a Lead from a Telegram event (never hard-deletes)."""
    now = utcnow()
    chat_id_str = str(telegram_chat_id).strip()[:64]
    raw_username = (telegram_username or "").strip().lstrip("@")[:120] or None
    messenger_handle = f"@{raw_username}" if raw_username else None
    messenger_norm = normalize_messenger(messenger_handle)
    raw_phone = (shared_phone or classification.phone or "").strip()[:40] or None
    phone_e164 = normalize_phone(raw_phone)
    full_name = (classification.full_name or sender_name or raw_username or f"Telegram #{chat_id_str}").strip()[:160]
    subject = (classification.subject or "").strip()[:160]
    prio = max(1, min(100, int(classification.priority_score or 50)))
    temp = "hot" if prio >= 80 else ("warm" if prio >= 50 else "cold")

    # Check existing archived spam for this chat_id so repeat spam does not spawn duplicates
    archived_lead = (
        Lead.query.filter(Lead.telegram_chat_id == chat_id_str, Lead.is_archived.is_(True))
        .order_by(Lead.id.desc())
        .first()
    )
    if classification.intent == "spam":
        open_lead, _closed = _find_telegram_lead(
            chat_id_str=chat_id_str,
            phone_e164=phone_e164,
            messenger_norm=messenger_norm,
        )
        target = open_lead or archived_lead
        if target is not None:
            old_state = {
                "status": target.status,
                "is_archived": bool(target.is_archived),
                "archive_reason": target.archive_reason,
                "priority_score": int(target.priority_score or 0),
            }
            target.is_archived = True
            target.archive_reason = "spam"
            target.priority_score = min(prio, 10)
            target.last_contact_at = now
            db.session.add(
                LeadActivity(
                    lead_id=target.id,
                    actor_id=None,
                    type="note",
                    body=f"[Telegram Bot · SPAM archived] {message_text[:500]}",
                    created_at=now,
                )
            )
            audit = write_audit_log(
                actor_id=None,
                action="bot_lead_archive",
                entity_type="lead",
                entity_id=target.id,
                old_value=old_state,
                new_value={"is_archived": True, "archive_reason": "spam", "priority_score": target.priority_score},
                reason="telegram_bot_spam",
            )
            db.session.commit()
            return target, "archived_spam", audit

        spam_lead = Lead(
            full_name=full_name,
            phone=raw_phone,
            phone_e164=phone_e164,
            messenger_handle=messenger_handle,
            messenger_norm=messenger_norm,
            telegram_chat_id=chat_id_str,
            telegram_username=raw_username,
            source="telegram",
            interest=subject,
            temperature="cold",
            priority_score=min(prio, 10),
            status="new",
            is_archived=True,
            archive_reason="spam",
            created_at=now,
            last_contact_at=now,
        )
        db.session.add(spam_lead)
        db.session.flush()
        db.session.add(
            LeadActivity(
                lead_id=spam_lead.id,
                actor_id=None,
                type="note",
                body=f"[Telegram Bot · SPAM archived] {message_text[:500]}",
                created_at=now,
            )
        )
        audit = write_audit_log(
            actor_id=None,
            action="bot_lead_archive",
            entity_type="lead",
            entity_id=spam_lead.id,
            old_value=None,
            new_value={"is_archived": True, "archive_reason": "spam", "telegram_chat_id": chat_id_str},
            reason="telegram_bot_spam",
        )
        db.session.commit()
        return spam_lead, "archived_spam", audit

    open_lead, closed_lead = _find_telegram_lead(
        chat_id_str=chat_id_str,
        phone_e164=phone_e164,
        messenger_norm=messenger_norm,
    )

    if open_lead is not None:
        old_val = {
            "status": open_lead.status,
            "priority_score": int(open_lead.priority_score or 50),
            "phone_e164": open_lead.phone_e164,
            "interest": open_lead.interest,
        }
        if not open_lead.telegram_chat_id:
            open_lead.telegram_chat_id = chat_id_str
        if raw_username and not open_lead.telegram_username:
            open_lead.telegram_username = raw_username
        if messenger_handle and not open_lead.messenger_handle:
            open_lead.messenger_handle = messenger_handle
        if messenger_norm and not open_lead.messenger_norm:
            open_lead.messenger_norm = messenger_norm
        if raw_phone and not open_lead.phone:
            open_lead.phone = raw_phone
        if phone_e164 and not open_lead.phone_e164:
            open_lead.phone_e164 = phone_e164
        if subject and not open_lead.interest:
            open_lead.interest = subject
        open_lead.priority_score = max(int(open_lead.priority_score or 50), prio)
        if temp == "hot" or (temp == "warm" and open_lead.temperature == "cold"):
            open_lead.temperature = temp
        open_lead.last_contact_at = now
        if open_lead.first_contact_at is None:
            open_lead.first_contact_at = now

        moved_stage = False
        if open_lead.status == "new" and (
            classification.intent in ("hot_lead", "trial_booking", "reschedule") or phone_e164
        ):
            open_lead.status = "contacted"
            moved_stage = True

        db.session.add(
            LeadActivity(
                lead_id=open_lead.id,
                actor_id=None,
                type="message",
                body=f"[Telegram · {classification.intent}] {message_text}",
                created_at=now,
            )
        )
        if moved_stage:
            db.session.add(
                LeadActivity(
                    lead_id=open_lead.id,
                    actor_id=None,
                    type="status_change",
                    body="Новый → В работе (Telegram-бот: подтверждён контакт/интерес)",
                    created_at=now,
                )
            )
        audit = write_audit_log(
            actor_id=None,
            action="bot_lead_update",
            entity_type="lead",
            entity_id=open_lead.id,
            old_value=old_val,
            new_value={
                "status": open_lead.status,
                "priority_score": open_lead.priority_score,
                "phone_e164": open_lead.phone_e164,
                "interest": open_lead.interest,
            },
            reason=f"telegram_bot:{classification.intent}",
        )
        db.session.commit()
        return open_lead, "updated", audit

    manager = pick_next_manager_round_robin()
    assigned_id = manager.id if manager else None
    initial_status = "contacted" if (classification.intent in ("hot_lead", "trial_booking") and phone_e164) else "new"

    new_lead = Lead(
        full_name=full_name,
        phone=raw_phone,
        phone_e164=phone_e164,
        messenger_handle=messenger_handle,
        messenger_norm=messenger_norm,
        telegram_chat_id=chat_id_str,
        telegram_username=raw_username,
        source="telegram",
        interest=subject,
        temperature=temp,
        priority_score=prio,
        ai_summary=f"Telegram ({classification.language}): intent={classification.intent}, score={prio}",
        previous_lead_id=closed_lead.id if closed_lead else None,
        status=initial_status,
        is_archived=False,
        archive_reason="",
        assigned_manager_id=assigned_id,
        created_at=now,
        last_contact_at=now,
        first_contact_at=now if initial_status == "contacted" else None,
    )
    db.session.add(new_lead)
    db.session.flush()

    db.session.add(
        LeadActivity(
            lead_id=new_lead.id,
            actor_id=None,
            type="message",
            body=f"[Telegram · {classification.intent}] {message_text}",
            created_at=now,
        )
    )
    if assigned_id is not None:
        db.session.add(
            LeadTask(
                lead_id=new_lead.id,
                assignee_id=assigned_id,
                due_at=now,
                note=f"Telegram лид ({classification.intent}, приоритет {prio}) — проверить и ответить",
                created_at=now,
            )
        )
    audit = write_audit_log(
        actor_id=None,
        action="bot_lead_create",
        entity_type="lead",
        entity_id=new_lead.id,
        old_value=None,
        new_value={
            "telegram_chat_id": chat_id_str,
            "phone_e164": phone_e164,
            "intent": classification.intent,
            "priority_score": prio,
            "status": initial_status,
        },
        reason=f"telegram_bot:{classification.intent}",
    )
    db.session.commit()
    return new_lead, "created", audit

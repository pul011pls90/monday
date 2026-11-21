"""Stage 4: Public site lead intake form, authenticated webhook endpoint, and round-robin assignment."""
from __future__ import annotations

import hmac
import threading
from datetime import timedelta

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .extensions import csrf, db, limiter
from .manager import MODE_PREF_LABELS, SOURCE_LABELS
from .models import (
    AppMeta,
    LEAD_MODE_PREFERENCES,
    LEAD_SOURCES,
    LEAD_TEMPERATURES,
    Lead,
    LeadActivity,
    LeadTask,
    User,
    utcnow,
)
from .phone_utils import normalize_messenger, normalize_phone

bp = Blueprint("crm_intake", __name__)

RR_META_KEY = "crm:rr_last_mgr"
_RR_THREAD_LOCK = threading.Lock()


def _ensure_rr_meta_row() -> AppMeta | None:
    meta = db.session.get(AppMeta, RR_META_KEY)
    if meta is not None:
        return meta
    try:
        with db.session.begin_nested():
            meta = AppMeta(key=RR_META_KEY, value="")
            db.session.add(meta)
            db.session.flush()
            return meta
    except IntegrityError:
        return db.session.get(AppMeta, RR_META_KEY)


def _pick_manager_unlocked() -> User | None:
    """Internal round-robin + least-load picker; caller holds _RR_THREAD_LOCK across DB commit."""
    pool = (
        User.query.filter_by(role="sales_manager", is_blocked=False, is_on_shift=True)
        .order_by(User.id.asc())
        .all()
    )
    if not pool:
        pool = (
            User.query.filter(
                User.role.in_(("supervisor", "admin")),
                User.is_blocked.is_(False),
                User.is_on_shift.is_(True),
            )
            .order_by(User.role != "supervisor", User.id.asc())
            .all()
        )
    if not pool:
        pool = (
            User.query.filter(User.role.in_(("supervisor", "admin")), User.is_blocked.is_(False))
            .order_by(User.role != "supervisor", User.id.asc())
            .all()
        )
    if not pool:
        return None

    _ensure_rr_meta_row()
    is_pg = bool(db.session.bind and db.session.bind.dialect.name == "postgresql")
    q_meta = AppMeta.query.filter_by(key=RR_META_KEY)
    if is_pg:
        q_meta = q_meta.with_for_update()
    meta = q_meta.first()
    last_id = int(meta.value) if (meta and str(meta.value or "").isdigit()) else None

    pool_ids = [u.id for u in pool]
    counts_rows = (
        db.session.query(Lead.assigned_manager_id, func.count(Lead.id))
        .filter(Lead.assigned_manager_id.in_(pool_ids), Lead.status.notin_(("won", "lost")))
        .group_by(Lead.assigned_manager_id)
        .all()
    )
    open_counts = {mid: cnt for mid, cnt in counts_rows}
    min_load = min(open_counts.get(u.id, 0) for u in pool)
    least_loaded = [u for u in pool if open_counts.get(u.id, 0) == min_load]

    chosen = least_loaded[0]
    if last_id is not None:
        for candidate in least_loaded:
            if candidate.id > last_id:
                chosen = candidate
                break

    if meta is None:
        db.session.add(AppMeta(key=RR_META_KEY, value=str(chosen.id)))
    else:
        meta.value = str(chosen.id)
    return chosen


def pick_next_manager_round_robin() -> User | None:
    """Atomically select the next on-shift Sales Manager with fewest open leads (round-robin tie-break).

    Falls back to supervisors / admins when no sales manager is on shift.
    """
    with _RR_THREAD_LOCK:
        return _pick_manager_unlocked()


def find_existing_lead_for_intake(phone_e164: str | None, messenger_norm: str | None) -> tuple[Lead | None, Lead | None]:
    """Return (open_duplicate_lead, latest_closed_lead) matching normalized phone_e164 or messenger_norm."""
    open_match = None
    closed_match = None
    if phone_e164:
        open_match = (
            Lead.query.filter(Lead.phone_e164 == phone_e164, Lead.status.notin_(("won", "lost")))
            .order_by(Lead.id.desc())
            .first()
        )
        if not open_match:
            closed_match = (
                Lead.query.filter(Lead.phone_e164 == phone_e164, Lead.status.in_(("won", "lost")))
                .order_by(Lead.id.desc())
                .first()
            )
    if not open_match and messenger_norm:
        open_match = (
            Lead.query.filter(Lead.messenger_norm == messenger_norm, Lead.status.notin_(("won", "lost")))
            .order_by(Lead.id.desc())
            .first()
        )
        if not open_match and not closed_match:
            closed_match = (
                Lead.query.filter(Lead.messenger_norm == messenger_norm, Lead.status.in_(("won", "lost")))
                .order_by(Lead.id.desc())
                .first()
            )
    return open_match, closed_match


def ingest_or_dedupe_lead(
    *,
    full_name: str,
    phone: str | None = None,
    messenger_handle: str | None = None,
    source: str = "site",
    interest: str = "",
    mode_preference: str = "",
    note: str = "",
    temperature: str = "cold",
    ai_summary: str | None = None,
    explicit_manager_id: int | None = None,
    actor_id: int | None = None,
) -> tuple[Lead, bool]:
    """Create a lead or merge repeat contact into an open lead (returning (lead, deduplicated))."""
    if source not in LEAD_SOURCES:
        source = "other"
    if mode_preference not in LEAD_MODE_PREFERENCES:
        mode_preference = ""
    if temperature not in LEAD_TEMPERATURES:
        temperature = "cold"

    raw_phone = (phone or "").strip()[:40] or None
    raw_msg = (messenger_handle or "").strip()[:120] or None
    phone_e164 = normalize_phone(raw_phone)
    messenger_norm = normalize_messenger(raw_msg)
    now = utcnow()

    with _RR_THREAD_LOCK:
        open_dup, closed_prev = find_existing_lead_for_intake(phone_e164, messenger_norm)
        if open_dup is not None:
            if raw_phone and not open_dup.phone:
                open_dup.phone = raw_phone
            if phone_e164 and not open_dup.phone_e164:
                open_dup.phone_e164 = phone_e164
            if raw_msg and not open_dup.messenger_handle:
                open_dup.messenger_handle = raw_msg
            if messenger_norm and not open_dup.messenger_norm:
                open_dup.messenger_norm = messenger_norm
            if interest.strip() and not open_dup.interest:
                open_dup.interest = interest.strip()[:160]
            if ai_summary and not open_dup.ai_summary:
                open_dup.ai_summary = ai_summary
            open_dup.last_contact_at = now

            src_label = SOURCE_LABELS.get(source, source)
            parts = [f"Повторное обращение ({src_label})"]
            if interest.strip():
                parts.append(f"Интерес: {interest.strip()[:160]}")
            if note.strip():
                parts.append(note.strip())
            db.session.add(
                LeadActivity(
                    lead_id=open_dup.id,
                    actor_id=actor_id,
                    type="message" if source in ("whatsapp", "telegram", "instagram") else "note",
                    body="\n".join(parts),
                    created_at=now,
                )
            )
            db.session.commit()
            current_app.logger.info("CRM intake deduped into open lead #%s (%s)", open_dup.id, source)
            return open_dup, True

        assigned_id = explicit_manager_id
        if assigned_id is None:
            manager = _pick_manager_unlocked()
            assigned_id = manager.id if manager else None

        sla_min = max(1, int(current_app.config.get("CRM_SLA_MINUTES", 15) or 15))
        lead = Lead(
            full_name=full_name.strip()[:160],
            phone=raw_phone,
            phone_e164=phone_e164,
            messenger_handle=raw_msg,
            messenger_norm=messenger_norm,
            source=source,
            interest=(interest or "").strip()[:160],
            mode_preference=mode_preference,
            temperature=temperature,
            ai_summary=ai_summary,
            previous_lead_id=closed_prev.id if closed_prev else None,
            status="new",
            assigned_manager_id=assigned_id,
            created_at=now,
        )
        db.session.add(lead)
        db.session.flush()

        if note.strip():
            db.session.add(
                LeadActivity(lead_id=lead.id, actor_id=actor_id, type="note", body=note.strip(), created_at=now)
            )
        if closed_prev is not None:
            db.session.add(
                LeadActivity(
                    lead_id=lead.id,
                    actor_id=actor_id,
                    type="note",
                    body=f"Повторная заявка (предыдущий лид #{closed_prev.id} в статусе {closed_prev.status})",
                    created_at=now,
                )
            )
        if assigned_id is not None:
            db.session.add(
                LeadTask(
                    lead_id=lead.id,
                    assignee_id=assigned_id,
                    due_at=now + timedelta(minutes=sla_min),
                    note=f"Новый входящий лид ({SOURCE_LABELS.get(source, source)}) — связаться за {sla_min} мин",
                    created_at=now,
                )
            )
        db.session.commit()
        current_app.logger.info("CRM intake: lead #%s (%s) assigned to manager #%s", lead.id, source, lead.assigned_manager_id)
        return lead, False


def create_incoming_lead(
    *,
    full_name: str,
    phone: str | None = None,
    messenger_handle: str | None = None,
    source: str = "site",
    interest: str = "",
    mode_preference: str = "",
    note: str = "",
) -> Lead:
    """Backwards-compatible wrapper creating or deduplicating an incoming lead."""
    lead, _deduped = ingest_or_dedupe_lead(
        full_name=full_name,
        phone=phone,
        messenger_handle=messenger_handle,
        source=source,
        interest=interest,
        mode_preference=mode_preference,
        note=note,
    )
    return lead


@bp.route("/apply", methods=["GET", "POST"])
@limiter.limit("5 per minute; 30 per hour", methods=["POST"])
def public_apply():
    """Public site lead inquiry form (CSRF-protected & rate-limited)."""
    if request.method == "POST":
        # Simple anti-spam honeypot: bots filling hidden `website` get silent 200
        if (request.form.get("website") or "").strip():
            return render_template("manager/apply.html", submitted=True, MODE_PREF_LABELS=MODE_PREF_LABELS)

        full_name = (request.form.get("full_name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        messenger_handle = (request.form.get("messenger_handle") or "").strip()
        interest = (request.form.get("interest") or "").strip()
        mode_pref = (request.form.get("mode_preference") or "").strip()
        note = (request.form.get("note") or "").strip()

        errors = []
        if len(full_name) < 2:
            errors.append(_("Укажите ваше имя (минимум 2 символа)."))
        if not phone and not messenger_handle:
            errors.append(_("Укажите номер телефона или Telegram / WhatsApp."))
        if errors:
            for e in errors:
                flash(e, "error")
            return (
                render_template(
                    "manager/apply.html",
                    submitted=False,
                    form=request.form,
                    MODE_PREF_LABELS=MODE_PREF_LABELS,
                ),
                400,
            )

        create_incoming_lead(
            full_name=full_name,
            phone=phone or None,
            messenger_handle=messenger_handle or None,
            source="site",
            interest=interest,
            mode_preference=mode_pref,
            note=note,
        )
        return redirect(url_for("crm_intake.public_apply", sent="1"))

    return render_template(
        "manager/apply.html",
        submitted=(request.args.get("sent") == "1"),
        form={},
        MODE_PREF_LABELS=MODE_PREF_LABELS,
    )


def _verify_webhook_secret() -> tuple[bool, int, str]:
    expected = (current_app.config.get("CRM_WEBHOOK_SECRET") or "").strip()
    if not expected:
        return False, 503, "webhook_not_configured"
    provided = (request.headers.get("X-Webhook-Secret") or "").strip()
    if not provided:
        auth = (request.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()
    if not provided or not hmac.compare_digest(provided, expected):
        return False, 401, "unauthorized"
    return True, 200, ""


@bp.post("/api/leads/webhook")
@csrf.exempt
@limiter.limit("60 per minute")
def webhook_lead():
    """Shared-secret authenticated webhook for Telegram/WhatsApp/Instagram bots."""
    ok, status_code, err = _verify_webhook_secret()
    if not ok:
        return jsonify({"ok": False, "error": err}), status_code

    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "invalid_json"}), 400
    full_name = str(data.get("full_name") or "").strip()
    phone = str(data.get("phone") or "").strip()
    messenger_handle = str(data.get("messenger_handle") or "").strip()
    source = str(data.get("source") or "other").strip().lower()
    interest = str(data.get("interest") or "").strip()
    mode_pref = str(data.get("mode_preference") or "").strip().lower()
    note = str(data.get("note") or "").strip()

    if len(full_name) < 2:
        return jsonify({"ok": False, "error": "full_name_required"}), 400
    if not phone and not messenger_handle:
        return jsonify({"ok": False, "error": "contact_required"}), 400

    lead, deduped = ingest_or_dedupe_lead(
        full_name=full_name,
        phone=phone or None,
        messenger_handle=messenger_handle or None,
        source=source,
        interest=interest,
        mode_preference=mode_pref,
        note=note,
        temperature=str(data.get("temperature") or "cold").strip().lower(),
        ai_summary=(str(data.get("ai_summary") or "").strip() or None),
    )
    return (
        jsonify(
            {
                "ok": True,
                "lead_id": lead.id,
                "status": lead.status,
                "assigned_manager_id": lead.assigned_manager_id,
                "deduplicated": deduped,
            }
        ),
        200 if deduped else 201,
    )

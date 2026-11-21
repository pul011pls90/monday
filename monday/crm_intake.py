"""Stage 4: Public site lead intake form, authenticated webhook endpoint, and round-robin assignment."""
from __future__ import annotations

import hmac
from datetime import timedelta

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _

from .extensions import csrf, db, limiter
from .manager import MODE_PREF_LABELS, SOURCE_LABELS
from .models import (
    AppMeta,
    LEAD_MODE_PREFERENCES,
    LEAD_SOURCES,
    Lead,
    LeadActivity,
    LeadTask,
    User,
    utcnow,
)

bp = Blueprint("crm_intake", __name__)

RR_META_KEY = "crm:rr_last_mgr"


def pick_next_manager_round_robin() -> User | None:
    """Select the next active Sales Manager in deterministic ID order (falls back to supervisor/admin)."""
    pool = (
        User.query.filter_by(role="sales_manager", is_blocked=False)
        .order_by(User.id.asc())
        .all()
    )
    if not pool:
        pool = (
            User.query.filter(User.role.in_(("supervisor", "admin")), User.is_blocked.is_(False))
            .order_by(User.id.asc())
            .all()
        )
    if not pool:
        return None

    meta = db.session.get(AppMeta, RR_META_KEY)
    last_id = int(meta.value) if (meta and str(meta.value or "").isdigit()) else None

    chosen = pool[0]
    if last_id is not None:
        for candidate in pool:
            if candidate.id > last_id:
                chosen = candidate
                break

    if meta is None:
        db.session.add(AppMeta(key=RR_META_KEY, value=str(chosen.id)))
    else:
        meta.value = str(chosen.id)
    return chosen


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
    """Create a lead, auto-assign via round-robin, and create an SLA notification task for the manager."""
    if source not in LEAD_SOURCES:
        source = "other"
    if mode_preference not in LEAD_MODE_PREFERENCES:
        mode_preference = ""

    manager = pick_next_manager_round_robin()
    sla_min = max(1, int(current_app.config.get("CRM_SLA_MINUTES", 15) or 15))
    now = utcnow()

    lead = Lead(
        full_name=full_name.strip()[:160],
        phone=(phone or "").strip()[:40] or None,
        messenger_handle=(messenger_handle or "").strip()[:120] or None,
        source=source,
        interest=(interest or "").strip()[:160],
        mode_preference=mode_preference,
        status="new",
        assigned_manager_id=manager.id if manager else None,
        created_at=now,
    )
    db.session.add(lead)
    db.session.flush()

    if note.strip():
        db.session.add(
            LeadActivity(lead_id=lead.id, actor_id=None, type="note", body=note.strip(), created_at=now)
        )
    if manager is not None:
        db.session.add(
            LeadTask(
                lead_id=lead.id,
                assignee_id=manager.id,
                due_at=now + timedelta(minutes=sla_min),
                note=f"Новый входящий лид ({SOURCE_LABELS.get(source, source)}) — связаться за {sla_min} мин",
                created_at=now,
            )
        )
    db.session.commit()
    current_app.logger.info(
        "CRM intake: lead #%s (%s) assigned to manager #%s",
        lead.id,
        source,
        lead.assigned_manager_id,
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

    lead = create_incoming_lead(
        full_name=full_name,
        phone=phone or None,
        messenger_handle=messenger_handle or None,
        source=source,
        interest=interest,
        mode_preference=mode_pref,
        note=note,
    )
    return (
        jsonify(
            {
                "ok": True,
                "lead_id": lead.id,
                "status": lead.status,
                "assigned_manager_id": lead.assigned_manager_id,
            }
        ),
        201,
    )

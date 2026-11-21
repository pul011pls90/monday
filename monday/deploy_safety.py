"""Deploy safety: maintenance state, build version, and idempotent activity autosave/resume."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, make_response, render_template, request
from flask_babel import gettext as _
from flask_login import current_user, login_required
from flask_wtf.csrf import validate_csrf

from .access import admin_required
from .models import ActivityDraft, ClientOp, MaintenanceLog, MaintenanceState, db, utcnow

bp = Blueprint("deploy_safety", __name__)

VALID_ACTIVITY_TYPES = {"test", "bank", "session", "homework", "practice"}
VALID_MAINT_STATES = {"off", "scheduled", "active"}


def ensure_deploy_safety_tables() -> None:
    """Create only the new deploy-safety tables if missing (never alters or deletes existing data)."""
    for model in (ActivityDraft, ClientOp, MaintenanceState, MaintenanceLog):
        model.__table__.create(bind=db.engine, checkfirst=True)


def get_maintenance_state() -> MaintenanceState:
    row = MaintenanceState.query.order_by(MaintenanceState.id.asc()).first()
    if row is None:
        row = MaintenanceState(state="off", message="", expected_minutes=15)
        db.session.add(row)
        db.session.commit()
    return row


def _parse_iso_dt(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1]
        return datetime.fromisoformat(s.replace("T", " ")[:19])
    except Exception:
        return None


def _update_maintenance(
    *,
    state: str,
    message: str,
    expected_minutes: int,
    starts_at: datetime | None,
    actor_id: int | None,
    actor_name: str,
    source: str,
) -> MaintenanceState:
    if state not in VALID_MAINT_STATES:
        raise ValueError("Invalid maintenance state")
    expected_minutes = max(1, min(720, int(expected_minutes or 15)))
    row = get_maintenance_state()
    row.state = state
    row.message = (message or "").strip()[:500]
    row.expected_minutes = expected_minutes
    row.starts_at = starts_at
    row.updated_by_id = actor_id
    row.updated_by_name = (actor_name or "")[:120]
    row.updated_at = utcnow()
    db.session.add(
        MaintenanceLog(
            state=state,
            message=row.message,
            expected_minutes=expected_minutes,
            starts_at=starts_at,
            actor_id=actor_id,
            actor=row.updated_by_name,
            source=source,
        )
    )
    db.session.commit()
    return row


@bp.get("/api/version")
def api_version():
    resp = jsonify({"version": current_app.config.get("APP_VERSION", "dev")})
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


@bp.get("/api/site-status")
def api_site_status():
    row = get_maintenance_state()
    payload = row.to_dict()
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    etag = '"' + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16] + '"'
    if request.headers.get("If-None-Match") == etag:
        resp = make_response("", 304)
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "public, max-age=5, must-revalidate"
        return resp
    resp = jsonify(payload)
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "public, max-age=5, must-revalidate"
    return resp


def _check_idempotency(user_id: int, op_id: str | None):
    if not op_id:
        return None
    existing = ClientOp.query.filter_by(user_id=user_id, op_id=op_id[:80]).first()
    if existing:
        try:
            return json.loads(existing.response_json or "{}")
        except Exception:
            return {"ok": True, "deduped": True}
    return None


def _record_idempotency(user_id: int, op_id: str | None, activity_type: str, body: dict) -> None:
    if not op_id:
        return
    db.session.add(
        ClientOp(
            user_id=user_id,
            op_id=op_id[:80],
            activity_type=activity_type[:24],
            response_json=json.dumps(body, ensure_ascii=False),
        )
    )
    # Keep idempotency table bounded per user (prune ops older than 7 days opportunistically)
    cutoff = utcnow() - timedelta(days=7)
    ClientOp.query.filter(ClientOp.created_at < cutoff).delete(synchronize_session=False)


@bp.post("/api/activity/save")
@login_required
def api_activity_save():
    data = request.get_json(silent=True) or {}
    op_id = (data.get("client_op_id") or "").strip() or None
    cached = _check_idempotency(current_user.id, op_id)
    if cached is not None:
        return jsonify({**cached, "deduped": True})

    activity_type = (data.get("type") or "").strip().lower()
    if activity_type not in VALID_ACTIVITY_TYPES:
        return jsonify({"ok": False, "error": "invalid_type"}), 400

    activity_id = str(data.get("activity_id") or "").strip()[:120]
    title = str(data.get("title") or "").strip()[:200]
    subtitle = str(data.get("subtitle") or "").strip()[:200]
    resume_url = str(data.get("resume_url") or "").strip()[:500]
    answered = max(0, int(data.get("answered") or 0))
    total = max(0, int(data.get("total") or 0))
    state_obj = data.get("state")
    if not isinstance(state_obj, dict):
        state_obj = {}
    if_version = data.get("if_version")
    force_replace = bool(data.get("force_replace"))
    client_updated_at = _parse_iso_dt(data.get("client_updated_at"))
    now = utcnow()

    draft = ActivityDraft.query.filter_by(user_id=current_user.id, activity_type=activity_type).first()

    if draft is None:
        draft = ActivityDraft(
            user_id=current_user.id,
            activity_type=activity_type,
            activity_id=activity_id,
            title=title,
            subtitle=subtitle,
            resume_url=resume_url,
            answered=answered,
            total=total,
            state_json=json.dumps(state_obj, ensure_ascii=False),
            status="in_progress",
            version=1,
            updated_at=now,
            created_at=now,
        )
        db.session.add(draft)
        db.session.flush()
        resp_body = {"ok": True, "record": draft.to_dict(), "conflict": False}
        _record_idempotency(current_user.id, op_id, activity_type, resp_body)
        db.session.commit()
        return jsonify(resp_body)

    # At most one in_progress record per user & type: starting a different activity requires previous completion/discard
    if (
        draft.status == "in_progress"
        and draft.activity_id
        and activity_id
        and draft.activity_id != activity_id
        and not force_replace
    ):
        # Allow replacement only if caller explicitly passes force_replace=True
        return jsonify({
            "ok": False,
            "error": "active_draft_exists",
            "conflict": True,
            "record": draft.to_dict(),
        }), 409

    # Optimistic versioning check
    if if_version is not None and draft.status == "in_progress":
        try:
            expected_v = int(if_version)
        except (TypeError, ValueError):
            expected_v = None
        if expected_v is not None and expected_v != draft.version:
            # Keep the newer updated_at; tell the client about the conflict
            server_newer = not (client_updated_at and draft.updated_at and client_updated_at > draft.updated_at)
            if server_newer:
                return jsonify({
                    "ok": False,
                    "error": "version_conflict",
                    "conflict": True,
                    "record": draft.to_dict(),
                }), 409

    draft.activity_id = activity_id or draft.activity_id
    if title:
        draft.title = title
    if subtitle:
        draft.subtitle = subtitle
    if resume_url:
        draft.resume_url = resume_url
    draft.answered = answered
    draft.total = total
    draft.state_json = json.dumps(state_obj, ensure_ascii=False)
    draft.status = "in_progress"
    draft.version = int(draft.version or 0) + 1
    draft.updated_at = now

    resp_body = {"ok": True, "record": draft.to_dict(), "conflict": False}
    _record_idempotency(current_user.id, op_id, activity_type, resp_body)
    db.session.commit()
    return jsonify(resp_body)


@bp.get("/api/activity/latest")
@login_required
def api_activity_latest():
    max_days = int(current_app.config.get("RESUME_MAX_DAYS", 30) or 30)
    cutoff = utcnow() - timedelta(days=max_days)
    rows = (
        ActivityDraft.query.filter(
            ActivityDraft.user_id == current_user.id,
            ActivityDraft.status == "in_progress",
            ActivityDraft.updated_at >= cutoff,
        )
        .order_by(ActivityDraft.updated_at.desc())
        .all()
    )
    resp = jsonify({"records": [r.to_dict() for r in rows]})
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


@bp.post("/api/activity/complete")
@login_required
def api_activity_complete():
    data = request.get_json(silent=True) or {}
    op_id = (data.get("client_op_id") or "").strip() or None
    cached = _check_idempotency(current_user.id, op_id)
    if cached is not None:
        return jsonify({**cached, "deduped": True})

    activity_type = (data.get("type") or "").strip().lower()
    if activity_type not in VALID_ACTIVITY_TYPES:
        return jsonify({"ok": False, "error": "invalid_type"}), 400

    status = (data.get("status") or "completed").strip().lower()
    if status not in ("completed", "abandoned"):
        return jsonify({"ok": False, "error": "invalid_status"}), 400

    draft = ActivityDraft.query.filter_by(user_id=current_user.id, activity_type=activity_type).first()
    if draft is None:
        resp_body = {"ok": True, "record": None}
        _record_idempotency(current_user.id, op_id, activity_type, resp_body)
        db.session.commit()
        return jsonify(resp_body)

    activity_id = str(data.get("activity_id") or "").strip()
    if activity_id and draft.activity_id and draft.activity_id != activity_id:
        resp_body = {"ok": True, "record": draft.to_dict(), "unchanged": True}
        _record_idempotency(current_user.id, op_id, activity_type, resp_body)
        db.session.commit()
        return jsonify(resp_body)

    draft.status = status
    draft.version = int(draft.version or 0) + 1
    draft.updated_at = utcnow()
    resp_body = {"ok": True, "record": draft.to_dict()}
    _record_idempotency(current_user.id, op_id, activity_type, resp_body)
    db.session.commit()
    return jsonify(resp_body)


@bp.route("/admin/maintenance", methods=["GET", "POST"])
@admin_required
def admin_maintenance():
    row = get_maintenance_state()
    saved = False
    error = ""
    if request.method == "POST":
        action = (request.form.get("action") or "save").strip()
        if action == "clear":
            _update_maintenance(
                state="off",
                message="",
                expected_minutes=15,
                starts_at=None,
                actor_id=current_user.id,
                actor_name=current_user.name or current_user.email,
                source="admin",
            )
            saved = True
        else:
            state = (request.form.get("state") or "off").strip().lower()
            message = request.form.get("message") or ""
            try:
                expected_minutes = int(request.form.get("expected_minutes") or 15)
            except ValueError:
                expected_minutes = 15
            starts_at = _parse_iso_dt(request.form.get("starts_at"))
            if state not in VALID_MAINT_STATES:
                error = _("Неверное состояние обслуживания.")
            else:
                _update_maintenance(
                    state=state,
                    message=message,
                    expected_minutes=expected_minutes,
                    starts_at=starts_at,
                    actor_id=current_user.id,
                    actor_name=current_user.name or current_user.email,
                    source="admin",
                )
                saved = True
        row = get_maintenance_state()

    logs = MaintenanceLog.query.order_by(MaintenanceLog.created_at.desc()).limit(30).all()
    return render_template("admin/maintenance.html", maint=row, logs=logs, saved=saved, error=error)


# Exempt from automatic form CSRF so the CLI script can authenticate with Bearer ADMIN_API_TOKEN;
# browser requests using session auth still validate X-CSRFToken explicitly below.
from . import csrf  # noqa: E402
from .extensions import limiter  # noqa: E402


@csrf.exempt
@limiter.limit("20 per minute")
@bp.post("/api/admin/maintenance")
def api_admin_maintenance():
    auth_header = request.headers.get("Authorization", "")
    token = current_app.config.get("ADMIN_API_TOKEN", "")
    is_token_auth = bool(token and hmac.compare_digest(auth_header, f"Bearer {token}"))

    if is_token_auth:
        actor_id = None
        actor_name = "cli-token"
        source = "cli"
    else:
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({"ok": False, "error": "forbidden"}), 403
        csrf_token = request.headers.get("X-CSRFToken") or (request.get_json(silent=True) or {}).get("csrf_token")
        try:
            validate_csrf(csrf_token)
        except Exception:
            return jsonify({"ok": False, "error": "invalid_csrf"}), 400
        actor_id = current_user.id
        actor_name = current_user.name or current_user.email
        source = "admin"

    data = request.get_json(silent=True) or {}
    state = (data.get("state") or "off").strip().lower()
    if state not in VALID_MAINT_STATES:
        return jsonify({"ok": False, "error": "invalid_state"}), 400
    message = str(data.get("message") or "")
    try:
        expected_minutes = int(data.get("expected_minutes") or 15)
    except (TypeError, ValueError):
        expected_minutes = 15
    starts_at = _parse_iso_dt(data.get("starts_at"))

    row = _update_maintenance(
        state=state,
        message=message,
        expected_minutes=expected_minutes,
        starts_at=starts_at,
        actor_id=actor_id,
        actor_name=actor_name,
        source=source,
    )
    return jsonify({"ok": True, "maintenance": row.to_dict()})

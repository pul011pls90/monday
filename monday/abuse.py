"""Abuse, brute-force enumeration, and scraping-velocity protection helpers (Stage 6)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from flask import abort, current_app, has_request_context, request
from flask_limiter.util import get_remote_address
from flask_login import current_user

from .audit import write_audit_log
from .extensions import db

_AUDIT_COOLDOWN_SECONDS = 300


def abuse_rate_key() -> str:
    """Rate-limit bucket keyed by authenticated user ID (or client IP when anonymous)."""
    if current_user and getattr(current_user, "is_authenticated", False):
        return f"user:{current_user.id}"
    return f"ip:{get_remote_address()}"


def rate_limit_value(config_key: str, default: str) -> str:
    try:
        return str(current_app.config.get(config_key) or default)
    except RuntimeError:
        return default


def _state() -> dict:
    store = current_app.extensions.get("monday_abuse")
    if store is None:
        store = {
            "lock": threading.Lock(),
            "q_fetches": defaultdict(deque),   # user_id -> deque[(ts, qid)]
            "probes": defaultdict(deque),      # scope_key -> deque[ts]
            "audit_ts": {},                    # (action, scope_key) -> last logged monotonic ts
        }
        current_app.extensions["monday_abuse"] = store
    return store


def _audit_once(action: str, entity_type: str, entity_id: int | None, scope_key: str, new_value: dict) -> None:
    st = _state()
    now_m = time.monotonic()
    key = (action, scope_key)
    with st["lock"]:
        last = st["audit_ts"].get(key, 0.0)
        if now_m - last < _AUDIT_COOLDOWN_SECONDS:
            return
        st["audit_ts"][key] = now_m
    try:
        actor_id = current_user.id if (has_request_context() and current_user and current_user.is_authenticated) else None
        write_audit_log(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            new_value=new_value,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()


def _abuse_enabled() -> bool:
    if not current_app.config.get("ABUSE_PROTECTION_ENABLED", True):
        return False
    if current_app.config.get("TESTING") and not current_app.config.get("ABUSE_PROTECTION_IN_TESTING", False):
        return False
    return True


def enforce_question_scrape_guard(user, question_ids: list[int | str] | tuple[int | str, ...], *, source: str = "") -> None:
    """Detect and block rapid harvesting of distinct questions within rolling minute/hour windows."""
    if not _abuse_enabled():
        return
    if not user or not getattr(user, "is_authenticated", False):
        return
    if getattr(user, "role", None) != "student":
        return

    cleaned: list[str] = []
    for q in question_ids or ():
        if q is not None and str(q).strip():
            cleaned.append(str(q).strip())
    if not cleaned:
        return

    window_sec = max(5, int(current_app.config.get("QBANK_SCRAPE_WINDOW_SECONDS", 60) or 60))
    max_window = max(1, int(current_app.config.get("QBANK_SCRAPE_MAX_PER_WINDOW", 60) or 60))
    max_hour = max(max_window, int(current_app.config.get("QBANK_SCRAPE_MAX_PER_HOUR", 350) or 350))
    now_m = time.monotonic()

    st = _state()
    blocked_reason: str | None = None
    distinct_window = 0
    distinct_hour = 0

    with st["lock"]:
        dq: deque = st["q_fetches"][user.id]
        cutoff_hour = now_m - 3600.0
        while dq and dq[0][0] < cutoff_hour:
            dq.popleft()

        recent_hour_ids = {qid for _ts, qid in dq}
        cutoff_win = now_m - float(window_sec)
        recent_win_ids = {qid for ts, qid in dq if ts >= cutoff_win}

        new_for_win = [qid for qid in dict.fromkeys(cleaned) if qid not in recent_win_ids]
        new_for_hour = [qid for qid in dict.fromkeys(cleaned) if qid not in recent_hour_ids]

        distinct_window = len(recent_win_ids) + len(new_for_win)
        distinct_hour = len(recent_hour_ids) + len(new_for_hour)

        if distinct_window > max_window:
            blocked_reason = "window_velocity"
        elif distinct_hour > max_hour:
            blocked_reason = "hourly_velocity"
        else:
            for qid in dict.fromkeys(cleaned):
                dq.append((now_m, qid))

    if blocked_reason:
        _audit_once(
            "abuse_scrape_velocity_blocked",
            "user",
            user.id,
            f"user:{user.id}",
            {
                "reason": blocked_reason,
                "source": source or (request.endpoint if has_request_context() else ""),
                "distinct_window": distinct_window,
                "distinct_hour": distinct_hour,
            },
        )
        abort(429)


def _probe_scope_key(scope_key: str | None = None) -> str:
    if scope_key:
        return scope_key
    return abuse_rate_key() if has_request_context() else "global"


def check_404_probe_guard(scope_key: str | None = None) -> None:
    """Reject clients currently throttled for excessive 404 enumeration probes."""
    if not _abuse_enabled():
        return
    window_sec = max(5, int(current_app.config.get("ABUSE_404_WINDOW_SECONDS", 60) or 60))
    max_probes = max(1, int(current_app.config.get("ABUSE_404_MAX_PER_WINDOW", 30) or 30))
    key = _probe_scope_key(scope_key)
    now_m = time.monotonic()

    st = _state()
    with st["lock"]:
        dq: deque = st["probes"][key]
        cutoff = now_m - float(window_sec)
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= max_probes:
            abort(429)


def record_404_probe(endpoint: str = "", scope_key: str | None = None) -> None:
    """Record a 404 probe against enumeration targets; writes a cooldown audit log when threshold is reached."""
    if not _abuse_enabled():
        return
    window_sec = max(5, int(current_app.config.get("ABUSE_404_WINDOW_SECONDS", 60) or 60))
    max_probes = max(1, int(current_app.config.get("ABUSE_404_MAX_PER_WINDOW", 30) or 30))
    key = _probe_scope_key(scope_key)
    now_m = time.monotonic()

    st = _state()
    tripped = False
    count = 0
    with st["lock"]:
        dq: deque = st["probes"][key]
        cutoff = now_m - float(window_sec)
        while dq and dq[0] < cutoff:
            dq.popleft()
        dq.append(now_m)
        count = len(dq)
        if count >= max_probes:
            tripped = True

    if tripped:
        _audit_once(
            "abuse_enumeration_blocked",
            "abuse",
            None,
            key,
            {"scope": key, "endpoint": endpoint or (request.endpoint if has_request_context() else ""), "probes": count},
        )

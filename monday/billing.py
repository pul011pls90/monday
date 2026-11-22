"""Stripe Hosted Checkout, Customer Billing Portal & Idempotent Webhook Processing (Stage 5)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, request, url_for
from flask_babel import gettext as _
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from .access import role_required, student_required
from .abuse import abuse_rate_key, rate_limit_value
from .audit import write_audit_log
from .extensions import csrf, db, limiter
from .models import (
    PaymentWebhookEvent,
    Subscription,
    SubscriptionEvent,
    SubscriptionPlan,
    User,
    utcnow,
)
from .subscriptions import (
    active_subscription_for_user,
    get_or_create_default_plan,
    is_content_staff,
    is_enrolled_monday_student,
)

bp = Blueprint("billing", __name__)

_STRIPE_STATUS_MAP = {
    "active": "active",
    "trialing": "trialing",
    "past_due": "past_due",
    "canceled": "cancelled",
    "unpaid": "expired",
    "incomplete_expired": "expired",
    "paused": "past_due",
}


class StripeBillingError(RuntimeError):
    """Safe error raised on Stripe API failure without exposing secret credentials."""


class StripeSignatureError(ValueError):
    """Raised when a Stripe webhook signature header is missing, expired, or invalid."""


def is_stripe_checkout_ready() -> bool:
    """True when hosted Stripe checkout is enabled and a secret API key is configured."""
    cfg = current_app.config
    return bool(cfg.get("STRIPE_ENABLED", False) and (cfg.get("STRIPE_SECRET_KEY") or "").strip())


def _stripe_request(
    method: str,
    path: str,
    params: list[tuple[str, str]] | dict[str, str] | None = None,
    *,
    idempotency_key: str | None = None,
) -> dict:
    """Execute an HTTPS request to Stripe REST API v1 (separated for test mocking)."""
    secret_key = (current_app.config.get("STRIPE_SECRET_KEY") or "").strip()
    if not secret_key:
        raise StripeBillingError("Stripe secret key is not configured.")

    api_version = (current_app.config.get("STRIPE_API_VERSION") or "2024-06-20").strip()
    clean_path = path.lstrip("/")
    url = f"https://api.stripe.com/v1/{clean_path}"
    data = urllib.parse.urlencode(params or {}).encode("utf-8") if method.upper() == "POST" else None
    if method.upper() == "GET" and params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Stripe-Version": api_version,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw or "{}")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
            err_msg = (json.loads(body).get("error") or {}).get("message") or f"HTTP {exc.code}"
        except Exception:
            err_msg = f"HTTP {exc.code}"
        raise StripeBillingError(f"Stripe API error: {err_msg}") from exc
    except Exception as exc:
        raise StripeBillingError(f"Stripe network error: {type(exc).__name__}") from exc


def ensure_stripe_customer(user: User) -> str:
    """Return existing `user.stripe_customer_id` or create a new Stripe Customer."""
    if (user.stripe_customer_id or "").strip():
        return user.stripe_customer_id.strip()
    payload = [
        ("email", user.email),
        ("name", (user.name or user.email)[:120]),
        ("metadata[user_id]", str(user.id)),
    ]
    res = _stripe_request("POST", "customers", payload, idempotency_key=f"customer-{user.id}")
    cus_id = str(res.get("id") or "").strip()
    if not cus_id:
        raise StripeBillingError("Stripe customer creation did not return an id.")
    user.stripe_customer_id = cus_id
    db.session.commit()
    return cus_id


def _recurring_interval(plan: SubscriptionPlan) -> tuple[str, int]:
    bp_kind = (plan.billing_period or "monthly").strip().lower()
    if bp_kind in ("year", "yearly", "annual"):
        return "year", 1
    days = int(plan.duration_days or 30)
    if days >= 360:
        return "year", max(1, round(days / 365))
    return "month", max(1, round(days / 30))


def create_checkout_session(user: User, plan: SubscriptionPlan, *, success_url: str, cancel_url: str) -> str:
    """Create a Stripe Hosted Checkout Session for `plan` and return its redirect URL."""
    customer_id = ensure_stripe_customer(user)
    params: list[tuple[str, str]] = [
        ("mode", "subscription"),
        ("customer", customer_id),
        ("client_reference_id", str(user.id)),
        ("success_url", success_url),
        ("cancel_url", cancel_url),
        ("metadata[user_id]", str(user.id)),
        ("metadata[plan_id]", str(plan.id)),
        ("metadata[plan_code]", plan.code),
        ("subscription_data[metadata][user_id]", str(user.id)),
        ("subscription_data[metadata][plan_id]", str(plan.id)),
        ("subscription_data[metadata][plan_code]", plan.code),
    ]
    if (plan.stripe_price_id or "").strip():
        params.append(("line_items[0][price]", plan.stripe_price_id.strip()))
        params.append(("line_items[0][quantity]", "1"))
    else:
        interval, interval_count = _recurring_interval(plan)
        params.extend([
            ("line_items[0][price_data][currency]", (plan.currency or "USD").strip().lower()),
            ("line_items[0][price_data][unit_amount]", str(max(1, int(plan.price_amount or 0)))),
            ("line_items[0][price_data][product_data][name]", plan.name[:120]),
            ("line_items[0][price_data][recurring][interval]", interval),
            ("line_items[0][price_data][recurring][interval_count]", str(interval_count)),
            ("line_items[0][quantity]", "1"),
        ])

    trial_days = int(current_app.config.get("STRIPE_TRIAL_DAYS", 0) or 0)
    if trial_days > 0:
        params.append(("subscription_data[trial_period_days]", str(trial_days)))

    res = _stripe_request("POST", "checkout/sessions", params)
    checkout_url = str(res.get("url") or "").strip()
    if not checkout_url:
        raise StripeBillingError("Stripe checkout session missing hosted URL.")
    return checkout_url


def create_billing_portal_session(user: User, *, return_url: str) -> str:
    """Create a Stripe Hosted Billing Portal Session for managing/cancelling subscriptions."""
    customer_id = (user.stripe_customer_id or "").strip()
    if not customer_id:
        sub = active_subscription_for_user(user)
        if sub and (sub.provider_customer_id or "").strip():
            customer_id = sub.provider_customer_id.strip()
    if not customer_id:
        raise StripeBillingError("Stripe customer profile not found for this user.")

    res = _stripe_request(
        "POST",
        "billing_portal/sessions",
        [("customer", customer_id), ("return_url", return_url)],
    )
    portal_url = str(res.get("url") or "").strip()
    if not portal_url:
        raise StripeBillingError("Stripe billing portal session missing URL.")
    return portal_url


def verify_stripe_webhook_signature(
    payload_bytes: bytes,
    sig_header: str | None,
    webhook_secret: str | None,
    *,
    tolerance_sec: int = 300,
    now_ts: int | None = None,
) -> None:
    """Verify Stripe's `Stripe-Signature: t=...,v1=...` HMAC-SHA256 header with replay protection."""
    secret = (webhook_secret or "").strip()
    if not secret:
        raise StripeSignatureError("Stripe webhook secret is not configured.")
    if not sig_header:
        raise StripeSignatureError("Missing Stripe-Signature header.")

    timestamp: int | None = None
    signatures: list[str] = []
    for part in sig_header.split(","):
        k, sep, v = part.strip().partition("=")
        if not sep:
            continue
        if k == "t":
            try:
                timestamp = int(v)
            except ValueError as exc:
                raise StripeSignatureError("Invalid Stripe signature timestamp.") from exc
        elif k == "v1":
            signatures.append(v.strip().lower())

    if timestamp is None or not signatures:
        raise StripeSignatureError("Malformed Stripe-Signature header.")

    ref_now = int(now_ts if now_ts is not None else time.time())
    if tolerance_sec > 0 and abs(ref_now - timestamp) > tolerance_sec:
        raise StripeSignatureError("Expired Stripe webhook timestamp.")

    signed_payload = f"{timestamp}.".encode("utf-8") + payload_bytes
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest().lower()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise StripeSignatureError("Invalid Stripe webhook signature.")


def _ts_to_dt(value) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _resolve_plan(metadata: dict | None, stripe_sub_obj: dict | None = None) -> SubscriptionPlan:
    meta = metadata or {}
    plan_id = meta.get("plan_id")
    if plan_id and str(plan_id).isdigit():
        p = db.session.get(SubscriptionPlan, int(plan_id))
        if p:
            return p
    if stripe_sub_obj:
        items_data = ((stripe_sub_obj.get("items") or {}).get("data") or [])
        for it in items_data:
            price_id = ((it.get("price") or {}).get("id") or "").strip()
            if price_id:
                p = SubscriptionPlan.query.filter_by(stripe_price_id=price_id).first()
                if p:
                    return p
    plan_code = (meta.get("plan_code") or "").strip()
    if plan_code:
        p = SubscriptionPlan.query.filter_by(code=plan_code).first()
        if p:
            return p
    return get_or_create_default_plan()


def _resolve_user(customer_id: str | None, metadata: dict | None, client_ref_id: str | None = None) -> User | None:
    meta = metadata or {}
    for raw_uid in (meta.get("user_id"), client_ref_id):
        if raw_uid and str(raw_uid).isdigit():
            u = db.session.get(User, int(raw_uid))
            if u:
                return u
    if customer_id:
        u = User.query.filter_by(stripe_customer_id=customer_id).first()
        if u:
            return u
        sub = Subscription.query.filter_by(provider_customer_id=customer_id).order_by(Subscription.id.desc()).first()
        if sub:
            return db.session.get(User, sub.user_id)
    return None


def _sync_stripe_subscription_object(
    stripe_sub: dict,
    *,
    fallback_user: User | None = None,
    fallback_meta: dict | None = None,
    event_type: str = "stripe_sync",
) -> Subscription | None:
    stripe_sub_id = str(stripe_sub.get("id") or "").strip()
    customer_id = str(stripe_sub.get("customer") or "").strip() or None
    meta = {**(fallback_meta or {}), **(stripe_sub.get("metadata") or {})}

    sub = Subscription.query.filter_by(provider_subscription_id=stripe_sub_id).first() if stripe_sub_id else None
    user = db.session.get(User, sub.user_id) if sub else (fallback_user or _resolve_user(customer_id, meta))
    if not user:
        return None
    if customer_id and user.stripe_customer_id != customer_id:
        user.stripe_customer_id = customer_id

    plan = _resolve_plan(meta, stripe_sub)
    raw_status = str(stripe_sub.get("status") or "active").strip().lower()
    mapped_status = _STRIPE_STATUS_MAP.get(raw_status, "active")

    now = utcnow()
    period_end = _ts_to_dt(stripe_sub.get("current_period_end"))
    trial_end = _ts_to_dt(stripe_sub.get("trial_end"))
    canceled_at = _ts_to_dt(stripe_sub.get("canceled_at"))
    cancel_at_period_end = bool(stripe_sub.get("cancel_at_period_end", False))

    if period_end is None and mapped_status == "active":
        period_end = now + timedelta(days=int(plan.duration_days or 30))

    if sub is None:
        # Supersede prior open subscriptions so only one active/trialing subscription holds at a time
        prior_open = Subscription.query.filter(
            Subscription.user_id == user.id,
            Subscription.status.in_(("active", "trialing")),
        ).all()
        for prev in prior_open:
            old_st = prev.status
            prev.status = "expired"
            db.session.add(
                SubscriptionEvent(
                    subscription=prev,
                    user_id=user.id,
                    actor_id=None,
                    event_type="expire",
                    old_status=old_st,
                    new_status="expired",
                    payload={"reason": "superseded_by_stripe_subscription", "stripe_subscription_id": stripe_sub_id},
                )
            )

        sub = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=mapped_status,
            provider="stripe",
            provider_subscription_id=stripe_sub_id or None,
            provider_customer_id=customer_id,
            cancel_at_period_end=cancel_at_period_end,
            starts_at=now,
            current_period_end=period_end,
            trial_ends_at=trial_end,
            cancelled_at=canceled_at,
            note="Stripe Hosted Checkout",
        )
        db.session.add(sub)
        db.session.flush()
        old_status = None
    else:
        old_status = sub.status
        sub.plan_id = plan.id
        sub.status = mapped_status
        sub.provider = "stripe"
        if customer_id:
            sub.provider_customer_id = customer_id
        sub.cancel_at_period_end = cancel_at_period_end
        if period_end is not None:
            sub.current_period_end = period_end
        if trial_end is not None:
            sub.trial_ends_at = trial_end
        if canceled_at is not None:
            sub.cancelled_at = canceled_at
        elif mapped_status == "cancelled" and sub.cancelled_at is None:
            sub.cancelled_at = now

    db.session.add(
        SubscriptionEvent(
            subscription_id=sub.id,
            user_id=user.id,
            actor_id=None,
            event_type=event_type[:32],
            old_status=old_status,
            new_status=sub.status,
            payload={
                "stripe_subscription_id": stripe_sub_id,
                "stripe_customer_id": customer_id,
                "plan_id": plan.id,
                "cancel_at_period_end": cancel_at_period_end,
                "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            },
        )
    )
    write_audit_log(
        actor_id=None,
        action="subscription_stripe_sync",
        entity_type="bank_subscription",
        entity_id=sub.id,
        old_value={"status": old_status} if old_status else None,
        new_value={
            "event_type": event_type,
            "user_id": user.id,
            "plan_id": plan.id,
            "status": sub.status,
            "cancel_at_period_end": cancel_at_period_end,
            "stripe_subscription_id": stripe_sub_id,
        },
    )
    return sub


def process_stripe_webhook_event(event: dict) -> dict[str, object]:
    """Process a verified Stripe webhook event idempotently via `payment_webhook_events`."""
    event_id = str(event.get("id") or "").strip()
    event_type = str(event.get("type") or "").strip()
    if not event_id or not event_type:
        raise ValueError("Webhook payload missing id or type.")

    if PaymentWebhookEvent.query.filter_by(event_id=event_id).first() is not None:
        return {"status": "duplicate", "event_id": event_id, "handled": False}

    obj = ((event.get("data") or {}).get("object") or {})
    handled_status = "processed"
    summary: dict[str, object] = {"type": event_type}

    if event_type == "checkout.session.completed":
        mode = str(obj.get("mode") or "")
        customer_id = str(obj.get("customer") or "").strip() or None
        sub_id = str(obj.get("subscription") or "").strip()
        meta = obj.get("metadata") or {}
        user = _resolve_user(customer_id, meta, obj.get("client_reference_id"))
        if user and customer_id:
            user.stripe_customer_id = customer_id
        if mode == "subscription" and user:
            sub = Subscription.query.filter_by(provider_subscription_id=sub_id).first() if sub_id else None
            if sub is None:
                plan = _resolve_plan(meta)
                now = utcnow()
                # Create immediate active subscription (subscription.created/updated will refine exact Stripe period dates)
                sub = _sync_stripe_subscription_object(
                    {
                        "id": sub_id,
                        "customer": customer_id,
                        "status": "active",
                        "metadata": meta,
                        "current_period_end": int((now + timedelta(days=int(plan.duration_days or 30))).replace(tzinfo=timezone.utc).timestamp()),
                    },
                    fallback_user=user,
                    fallback_meta=meta,
                    event_type="checkout_completed",
                )
            summary.update({"user_id": user.id, "subscription_id": sub.id if sub else None})
        else:
            handled_status = "ignored"

    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        ev_label = "stripe_deleted" if event_type.endswith("deleted") else "stripe_update"
        if event_type.endswith("deleted"):
            obj = {**obj, "status": "canceled"}
        sub = _sync_stripe_subscription_object(obj, event_type=ev_label)
        if sub:
            summary.update({"user_id": sub.user_id, "subscription_id": sub.id, "status": sub.status})
        else:
            handled_status = "ignored"

    elif event_type in ("invoice.paid", "invoice.payment_failed"):
        stripe_sub_id = str(obj.get("subscription") or "").strip()
        sub = Subscription.query.filter_by(provider_subscription_id=stripe_sub_id).first() if stripe_sub_id else None
        if sub:
            old_st = sub.status
            if event_type == "invoice.payment_failed":
                sub.status = "past_due"
            elif sub.status in ("past_due", "active"):
                sub.status = "active"
                lines = ((obj.get("lines") or {}).get("data") or [])
                if lines:
                    p_end = _ts_to_dt(((lines[0].get("period") or {}).get("end")))
                    if p_end is not None:
                        sub.current_period_end = p_end
            db.session.add(
                SubscriptionEvent(
                    subscription_id=sub.id,
                    user_id=sub.user_id,
                    actor_id=None,
                    event_type="invoice_paid" if event_type == "invoice.paid" else "payment_failed",
                    old_status=old_st,
                    new_status=sub.status,
                    payload={"stripe_invoice_id": obj.get("id"), "stripe_subscription_id": stripe_sub_id},
                )
            )
            write_audit_log(
                actor_id=None,
                action="subscription_stripe_invoice",
                entity_type="bank_subscription",
                entity_id=sub.id,
                old_value={"status": old_st},
                new_value={"event_type": event_type, "status": sub.status, "stripe_invoice_id": obj.get("id")},
            )
            summary.update({"user_id": sub.user_id, "subscription_id": sub.id, "status": sub.status})
        else:
            handled_status = "ignored"
    else:
        handled_status = "ignored"

    db.session.add(
        PaymentWebhookEvent(
            provider="stripe",
            event_id=event_id,
            event_type=event_type[:64],
            status=handled_status,
            payload_summary=summary,
        )
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"status": "duplicate", "event_id": event_id, "handled": False}

    return {"status": handled_status, "event_id": event_id, "handled": handled_status == "processed", **summary}


# --------------------------------------------------------------------------- HTTP routes


@bp.route("/subscription/checkout", methods=["POST"])
@role_required("student")
@student_required
@limiter.limit(lambda: rate_limit_value("QBANK_RATE_LIMIT_ACTION", "90 per minute; 600 per hour"), key_func=abuse_rate_key)
def checkout():
    """Start a Stripe Hosted Checkout Session for the selected SubscriptionPlan."""
    if not is_stripe_checkout_ready():
        flash(_("Онлайн-оплата временно отключена."), "info")
        return redirect(url_for("student.subscription"))
    if is_content_staff(current_user) or is_enrolled_monday_student(current_user):
        flash(_("Полный доступ к банку вопросов уже включён в ваше обучение в Monday Academy."), "info")
        return redirect(url_for("student.subscription"))

    existing = active_subscription_for_user(current_user)
    if existing and existing.provider == "stripe":
        flash(_("У вас уже есть активная подписка. Управляйте ею через биллинг-портал."), "info")
        return redirect(url_for("student.subscription"))

    plan_id = request.form.get("plan_id", type=int)
    plan = (
        SubscriptionPlan.query.filter_by(id=plan_id, is_active=True).first()
        if plan_id
        else SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.price_amount.asc()).first()
    )
    if not plan:
        abort(404)

    success_url = url_for("student.subscription", checkout="success", _external=True) + "&session_id={CHECKOUT_SESSION_ID}"
    cancel_url = url_for("student.subscription", checkout="cancelled", _external=True)
    try:
        hosted_url = create_checkout_session(current_user._get_current_object(), plan, success_url=success_url, cancel_url=cancel_url)
    except StripeBillingError as exc:
        current_app.logger.error("Stripe checkout session creation failed (%s)", exc)
        flash(_("Не удалось создать платёжную сессию. Попробуйте позже."), "error")
        return redirect(url_for("student.subscription"))

    return redirect(hosted_url, code=303)


@bp.route("/subscription/portal", methods=["POST"])
@role_required("student")
@student_required
@limiter.limit(lambda: rate_limit_value("QBANK_RATE_LIMIT_ACTION", "90 per minute; 600 per hour"), key_func=abuse_rate_key)
def portal():
    """Redirect student to Stripe Hosted Billing Portal (manage payment method / cancel)."""
    if not is_stripe_checkout_ready():
        flash(_("Управление онлайн-оплатой временно отключено."), "info")
        return redirect(url_for("student.subscription"))

    return_url = url_for("student.subscription", _external=True)
    try:
        portal_url = create_billing_portal_session(current_user._get_current_object(), return_url=return_url)
    except StripeBillingError as exc:
        current_app.logger.warning("Stripe portal creation failed (%s)", exc)
        flash(_("Платёжный профиль ещё не создан или недоступен."), "error")
        return redirect(url_for("student.subscription"))

    return redirect(portal_url, code=303)


@bp.route("/webhooks/stripe", methods=["POST"])
@csrf.exempt
@limiter.limit("300 per minute")
def stripe_webhook():
    """Receive, cryptographically verify, and idempotently process Stripe webhooks."""
    payload = request.get_data(cache=False) or b""
    sig_header = request.headers.get("Stripe-Signature")
    secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
    tolerance = int(current_app.config.get("STRIPE_WEBHOOK_TOLERANCE_SECONDS", 300) or 300)

    try:
        verify_stripe_webhook_signature(payload, sig_header, secret, tolerance_sec=tolerance)
        event = json.loads(payload.decode("utf-8"))
    except StripeSignatureError:
        return jsonify(ok=False, error="invalid_signature"), 400
    except Exception:
        return jsonify(ok=False, error="invalid_payload"), 400

    try:
        res = process_stripe_webhook_event(event)
    except ValueError:
        return jsonify(ok=False, error="invalid_event"), 400
    return jsonify(ok=True, **res), 200

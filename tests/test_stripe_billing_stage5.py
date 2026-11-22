"""Stage 5 tests: Stripe Hosted Checkout, Billing Portal, cryptographic webhooks, idempotency & entitlement revocation."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import timedelta

from config import Config
from monday import create_app
from monday.billing import _stripe_request, verify_stripe_webhook_signature
from monday.extensions import db
from monday.models import (
    AuditLog,
    ContentNode,
    PaymentWebhookEvent,
    Question,
    StudentProfile,
    StudentRecord,
    Subscription,
    SubscriptionEvent,
    SubscriptionPlan,
    User,
    utcnow,
)
from monday.subscriptions import has_question_bank_access


def _make_app(tmp_path, **overrides):
    class Cfg(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        PUBLIC_SITE_ENABLED = True
        PUBLIC_LEGAL_REVIEWED = True
        STRIPE_ENABLED = True
        STRIPE_SECRET_KEY = "sk_test_mock_key"
        STRIPE_WEBHOOK_SECRET = "whsec_test_mock_secret"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'stage5_stripe.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        PUBLIC_SAMPLE_MEDIA_FOLDER = str(tmp_path / "public_sample_media")

    for k, v in overrides.items():
        setattr(Cfg, k, v)
    return create_app(Cfg, seed_if_empty=False)


def _login(client, email: str, password: str = "Pass123456!"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=False)


def _sign_stripe_payload(payload_bytes: bytes, secret: str, ts: int | None = None) -> str:
    t = int(ts if ts is not None else time.time())
    signed = f"{t}.".encode("utf-8") + payload_bytes
    sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def test_stripe_hosted_checkout_and_portal_flows(tmp_path, monkeypatch):
    from monday import billing

    app = _make_app(tmp_path)
    calls: list[tuple[str, str, dict]] = []

    def fake_stripe_req(method, path, params=None, *, idempotency_key=None):
        pdict = dict(params or [])
        calls.append((method, path, pdict))
        if path == "customers":
            return {"id": "cus_test_123"}
        if path == "checkout/sessions":
            return {"id": "cs_test_abc", "url": "https://checkout.stripe.com/c/pay/cs_test_abc"}
        if path == "billing_portal/sessions":
            return {"id": "bps_test_xyz", "url": "https://billing.stripe.com/p/session/bps_test_xyz"}
        raise AssertionError(f"Unexpected Stripe path {path}")

    monkeypatch.setattr(billing, "_stripe_request", fake_stripe_req)

    with app.app_context():
        student = User(email="self@s5.test", name="Self Learner", role="student", is_approved=True)
        student.set_password("Pass123456!")
        teacher = User(email="teach@s5.test", name="Teacher", role="teacher", is_approved=True)
        teacher.set_password("StrongTeacher123!")
        enrolled = User(email="enr@s5.test", name="Enrolled", role="student", is_approved=True)
        enrolled.set_password("Pass123456!")
        db.session.add_all([student, teacher, enrolled])
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, exam="SAT", onboarded=True))
        db.session.add(StudentProfile(user_id=enrolled.id, exam="SAT", onboarded=True))
        db.session.add(StudentRecord(teacher_id=teacher.id, student_user_id=enrolled.id, name="Enrolled", exam="SAT"))
        plan = SubscriptionPlan(
            code="qbank_pro",
            name="Подписка Pro",
            price_amount=1200,
            currency="USD",
            duration_days=30,
            stripe_price_id="price_test_1200",
            is_active=True,
        )
        db.session.add(plan)
        db.session.commit()
        plan_id = plan.id
        student_id = student.id

    c = app.test_client()
    # Unauthenticated POST redirects to login
    assert c.post("/subscription/checkout", data={"plan_id": plan_id}).status_code == 302

    # Teacher blocked by RBAC (403)
    assert _login(c, "teach@s5.test", "StrongTeacher123!").status_code == 302
    assert c.post("/subscription/checkout", data={"plan_id": plan_id}).status_code == 403

    # Self-study learner sees hosted checkout CTA (no inline card fields!) and redirects to Stripe URL
    c_stu = app.test_client()
    assert _login(c_stu, "self@s5.test").status_code == 302
    sub_html = c_stu.get("/subscription").get_data(as_text=True)
    assert "Оформить подписку через Stripe" in sub_html
    assert "card_number" not in sub_html and "cvc" not in sub_html

    r_chk = c_stu.post("/subscription/checkout", data={"plan_id": plan_id}, follow_redirects=False)
    assert r_chk.status_code == 303
    assert r_chk.headers["Location"] == "https://checkout.stripe.com/c/pay/cs_test_abc"

    # Verify customer & price_id + metadata sent cleanly
    assert calls[0][1] == "customers"
    assert calls[1][1] == "checkout/sessions"
    assert calls[1][2]["customer"] == "cus_test_123"
    assert calls[1][2]["line_items[0][price]"] == "price_test_1200"
    assert calls[1][2]["metadata[user_id]"] == str(student_id)
    assert calls[1][2]["metadata[plan_id]"] == str(plan_id)

    # Customer ID persisted and opens Billing Portal cleanly
    r_port = c_stu.post("/subscription/portal", follow_redirects=False)
    assert r_port.status_code == 303
    assert r_port.headers["Location"] == "https://billing.stripe.com/p/session/bps_test_xyz"


def test_stripe_webhook_signature_lifecycle_and_idempotency(tmp_path):
    app = _make_app(tmp_path)

    with app.app_context():
        node = ContentNode(code="s5_n", name="S5 Node", level="node", exams=["SAT"])
        db.session.add(node)
        db.session.flush()
        db.session.add(
            Question(
                skill=node,
                exams=["SAT"],
                difficulty=1,
                text="S5 Q1",
                options=["A", "B"],
                correct="0",
                status="published",
            )
        )
        student = User(email="buyer@s5.test", name="Buyer", role="student", is_approved=True)
        student.set_password("Pass123456!")
        db.session.add(student)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, exam="SAT", onboarded=True))
        plan = SubscriptionPlan(
            code="qbank_m_s5",
            name="Месячная подписка",
            price_amount=800,
            currency="USD",
            duration_days=30,
            stripe_price_id="price_s5_800",
            is_active=True,
        )
        db.session.add(plan)
        db.session.commit()
        uid, pid = student.id, plan.id
        assert has_question_bank_access(student) is False

    client = app.test_client()

    # 1. Invalid / missing / expired signature rejected with 400
    bad_payload = json.dumps({"id": "evt_bad", "type": "checkout.session.completed"}).encode("utf-8")
    assert client.post("/webhooks/stripe", data=bad_payload, content_type="application/json").status_code == 400
    assert client.post(
        "/webhooks/stripe",
        data=bad_payload,
        headers={"Stripe-Signature": "t=100,v1=deadbeef"},
        content_type="application/json",
    ).status_code == 400
    stale_sig = _sign_stripe_payload(bad_payload, "whsec_test_mock_secret", ts=int(time.time()) - 900)
    assert client.post(
        "/webhooks/stripe",
        data=bad_payload,
        headers={"Stripe-Signature": stale_sig},
        content_type="application/json",
    ).status_code == 400

    # 2. Valid checkout.session.completed provisions active subscription + idempotent replay ignores duplicate
    future_end = int((utcnow() + timedelta(days=30)).timestamp())
    evt_checkout = json.dumps({
        "id": "evt_chk_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_1",
                "mode": "subscription",
                "customer": "cus_buyer_1",
                "subscription": "sub_buyer_1",
                "client_reference_id": str(uid),
                "metadata": {"user_id": str(uid), "plan_id": str(pid)},
            }
        },
    }).encode("utf-8")
    sig_chk = _sign_stripe_payload(evt_checkout, "whsec_test_mock_secret")
    r_w1 = client.post("/webhooks/stripe", data=evt_checkout, headers={"Stripe-Signature": sig_chk}, content_type="application/json")
    assert r_w1.status_code == 200
    assert r_w1.get_json()["status"] == "processed"

    # Exact replay of evt_chk_1 is deduplicated cleanly
    r_w1_dup = client.post("/webhooks/stripe", data=evt_checkout, headers={"Stripe-Signature": sig_chk}, content_type="application/json")
    assert r_w1_dup.status_code == 200
    assert r_w1_dup.get_json()["status"] == "duplicate"

    with app.app_context():
        u = db.session.get(User, uid)
        assert u.stripe_customer_id == "cus_buyer_1"
        assert has_question_bank_access(u) is True
        subs = Subscription.query.filter_by(user_id=uid).all()
        assert len(subs) == 1
        assert subs[0].provider == "stripe"
        assert subs[0].provider_subscription_id == "sub_buyer_1"
        assert PaymentWebhookEvent.query.filter_by(event_id="evt_chk_1").count() == 1

    # 3. customer.subscription.updated sets cancel_at_period_end while remaining active through period end
    evt_upd = json.dumps({
        "id": "evt_upd_1",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_buyer_1",
                "customer": "cus_buyer_1",
                "status": "active",
                "cancel_at_period_end": True,
                "current_period_end": future_end,
                "items": {"data": [{"price": {"id": "price_s5_800"}}]},
            }
        },
    }).encode("utf-8")
    sig_upd = _sign_stripe_payload(evt_upd, "whsec_test_mock_secret")
    assert client.post("/webhooks/stripe", data=evt_upd, headers={"Stripe-Signature": sig_upd}, content_type="application/json").status_code == 200

    assert _login(client, "buyer@s5.test").status_code == 302
    sub_page = client.get("/subscription").get_data(as_text=True)
    assert "Управлять подпиской / отменить в Stripe" in sub_page
    assert "Продление отменено" in sub_page

    # 4. invoice.payment_failed moves status -> past_due (revokes active subscription bank access)
    evt_fail = json.dumps({
        "id": "evt_inv_fail_1",
        "type": "invoice.payment_failed",
        "data": {"object": {"id": "in_fail_1", "subscription": "sub_buyer_1"}},
    }).encode("utf-8")
    sig_fail = _sign_stripe_payload(evt_fail, "whsec_test_mock_secret")
    assert client.post("/webhooks/stripe", data=evt_fail, headers={"Stripe-Signature": sig_fail}, content_type="application/json").status_code == 200
    with app.app_context():
        assert has_question_bank_access(db.session.get(User, uid)) is False

    # 5. invoice.paid restores active access, then customer.subscription.deleted cancels cleanly
    evt_paid = json.dumps({
        "id": "evt_inv_paid_1",
        "type": "invoice.paid",
        "data": {
            "object": {
                "id": "in_paid_1",
                "subscription": "sub_buyer_1",
                "lines": {"data": [{"period": {"end": future_end}}]},
            }
        },
    }).encode("utf-8")
    sig_paid = _sign_stripe_payload(evt_paid, "whsec_test_mock_secret")
    assert client.post("/webhooks/stripe", data=evt_paid, headers={"Stripe-Signature": sig_paid}, content_type="application/json").status_code == 200
    with app.app_context():
        assert has_question_bank_access(db.session.get(User, uid)) is True

    evt_del = json.dumps({
        "id": "evt_del_1",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_buyer_1",
                "customer": "cus_buyer_1",
                "canceled_at": int(time.time()),
                "current_period_end": future_end,
            }
        },
    }).encode("utf-8")
    sig_del = _sign_stripe_payload(evt_del, "whsec_test_mock_secret")
    assert client.post("/webhooks/stripe", data=evt_del, headers={"Stripe-Signature": sig_del}, content_type="application/json").status_code == 200
    with app.app_context():
        u = db.session.get(User, uid)
        assert has_question_bank_access(u) is False
        sub = Subscription.query.filter_by(user_id=uid).one()
        assert sub.status == "cancelled"
        assert SubscriptionEvent.query.filter_by(subscription_id=sub.id).count() >= 5
        assert AuditLog.query.filter(AuditLog.entity_type == "bank_subscription").count() >= 5


def test_stripe_disabled_default_and_preflight_guard(tmp_path):
    assert Config.STRIPE_ENABLED is False
    app = _make_app(tmp_path, STRIPE_ENABLED=True, STRIPE_SECRET_KEY="", STRIPE_WEBHOOK_SECRET="")
    from monday.public_site import collect_site_preflight_blockers

    with app.app_context():
        blockers = collect_site_preflight_blockers()
        joined = "\n".join(blockers)
        assert "STRIPE_SECRET_KEY" in joined
        assert "STRIPE_WEBHOOK_SECRET" in joined

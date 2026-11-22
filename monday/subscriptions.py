"""Self-study subscription lifecycle, enrollment checks, legacy grandfathering & atomic free-tier quota."""
from __future__ import annotations

import threading
from datetime import date, datetime, timedelta

from flask import current_app
from sqlalchemy import exists, or_, text
from sqlalchemy.exc import IntegrityError

from .audit import write_audit_log
from .extensions import db
from .models import (
    Assignment,
    DailyQuestionAccess,
    GroupEnrollment,
    Question,
    StudentRecord,
    Subscription,
    SubscriptionEvent,
    SubscriptionPlan,
    TeacherAssignment,
    User,
    today as local_today,
    utcnow,
)
from .student_links import student_current_teachers

_CONTENT_STAFF_ROLES = frozenset({"teacher", "assistant", "admin"})
_USER_QUOTA_LOCKS: dict[int, threading.RLock] = {}
_QUOTA_REGISTRY_LOCK = threading.Lock()


def _lock_for_user(user_id: int) -> threading.RLock:
    with _QUOTA_REGISTRY_LOCK:
        lock = _USER_QUOTA_LOCKS.get(user_id)
        if lock is None:
            lock = threading.RLock()
            _USER_QUOTA_LOCKS[user_id] = lock
        return lock


def free_daily_question_limit() -> int:
    try:
        return max(0, int(current_app.config.get("FREE_DAILY_QUESTION_LIMIT", 10) or 0))
    except RuntimeError:
        return 10


def subscriptions_enforced() -> bool:
    """Return True when subscription / daily-quota gating is active; False grants open access to all students."""
    try:
        return bool(current_app.config.get("SUBSCRIPTION_REQUIRED", False))
    except RuntimeError:
        return False


def course_included_in_subscription() -> bool:
    try:
        return bool(current_app.config.get("COURSE_INCLUDED_IN_SUBSCRIPTION", True))
    except RuntimeError:
        return True


def is_content_staff(user: User | None) -> bool:
    if not user or not getattr(user, "is_authenticated", False) or getattr(user, "is_blocked", False):
        return False
    role = getattr(user, "role", None)
    if role == "teacher" and not getattr(user, "is_approved", False):
        return False
    return role in _CONTENT_STAFF_ROLES


def has_teacher_link(user: User | None) -> bool:
    """True only when a student has an active teacher-student assignment/link (invite-code or open assignment)."""
    if not user or not getattr(user, "is_authenticated", False) or getattr(user, "role", None) != "student":
        return False
    return bool(student_current_teachers(user.id))


def is_enrolled_monday_student(user: User | None) -> bool:
    """True for Monday Academy enrolled students (active GroupEnrollment, open TeacherAssignment, invite link, or assignment)."""
    if not user or not getattr(user, "is_authenticated", False) or getattr(user, "is_blocked", False):
        return False
    if getattr(user, "role", None) != "student":
        return False

    if has_teacher_link(user):
        return True

    active_group = (
        GroupEnrollment.query.filter(
            GroupEnrollment.student_user_id == user.id,
            GroupEnrollment.left_at.is_(None),
            GroupEnrollment.status == "active",
        ).first()
        is not None
    )
    if active_group:
        return True

    has_assignment = (
        Assignment.query.join(StudentRecord, StudentRecord.id == Assignment.record_id)
        .filter(StudentRecord.student_user_id == user.id)
        .first()
        is not None
    )
    return has_assignment


def active_subscription_for_user(user: User | None, *, at: datetime | None = None) -> Subscription | None:
    """Return active or trialing Subscription if still within period/trial window."""
    if not user or not getattr(user, "is_authenticated", False) or getattr(user, "is_blocked", False):
        return None
    now = at or utcnow()
    subs = (
        Subscription.query.filter(
            Subscription.user_id == user.id,
            Subscription.status.in_(("active", "trialing")),
        )
        .order_by(Subscription.id.desc())
        .all()
    )
    for sub in subs:
        if sub.status == "active":
            if sub.current_period_end is None or sub.current_period_end > now:
                return sub
        elif sub.status == "trialing":
            if sub.trial_ends_at is None or sub.trial_ends_at > now:
                return sub
    return None


def has_valid_legacy_access(user: User | None, *, at: datetime | None = None) -> bool:
    if not user or not getattr(user, "is_authenticated", False) or getattr(user, "is_blocked", False):
        return False
    until = getattr(user, "legacy_access_until", None)
    if until is None:
        return False
    return until > (at or utcnow())


def has_question_bank_access(user: User | None) -> bool:
    """Central access helper (Stage 4): open to all active students unless SUBSCRIPTION_REQUIRED=1."""
    if not user or not getattr(user, "is_authenticated", False) or getattr(user, "is_blocked", False):
        return False
    if is_content_staff(user):
        return True
    if getattr(user, "role", None) != "student":
        return False
    if not subscriptions_enforced():
        return True
    if is_enrolled_monday_student(user):
        return True
    if active_subscription_for_user(user) is not None:
        return True
    if has_valid_legacy_access(user):
        return True
    return False


def has_course_access(user: User | None) -> bool:
    """SAT theory course access: open to all active students unless SUBSCRIPTION_REQUIRED=1."""
    if not user or not getattr(user, "is_authenticated", False) or getattr(user, "is_blocked", False):
        return False
    if is_content_staff(user):
        return True
    if getattr(user, "role", None) != "student":
        return False
    if not subscriptions_enforced():
        return True
    if is_enrolled_monday_student(user):
        return True
    if not course_included_in_subscription():
        return False
    return active_subscription_for_user(user) is not None or has_valid_legacy_access(user)


def free_daily_usage_counts(user_id: int, *, day: date | None = None) -> tuple[int, int, int]:
    """Return (used_today, daily_limit, remaining) for a user's local day."""
    today = day or local_today()
    limit = free_daily_question_limit()
    used = DailyQuestionAccess.query.filter_by(user_id=user_id, access_date=today).count()
    return used, limit, max(0, limit - used)


def is_question_unlocked_today(user_id: int, question_id: int, *, day: date | None = None) -> bool:
    today = day or local_today()
    return (
        DailyQuestionAccess.query.filter_by(
            user_id=user_id,
            access_date=today,
            question_id=question_id,
        ).first()
        is not None
    )


def has_unlocked_image_today(user_id: int, image_path: str, *, day: date | None = None) -> bool:
    today = day or local_today()
    return (
        DailyQuestionAccess.query.join(Question, Question.id == DailyQuestionAccess.question_id)
        .filter(
            DailyQuestionAccess.user_id == user_id,
            DailyQuestionAccess.access_date == today,
            Question.image_path == image_path,
        )
        .first()
        is not None
    )


def claim_free_question_access(
    user_id: int,
    question_ids: list[int],
    *,
    day: date | None = None,
    partial: bool = False,
) -> tuple[bool, int, int, list[int]]:
    """Atomically verify & record free-tier daily access for distinct non-sample questions.

    Returns (allowed, used_today, remaining_today, allowed_question_ids).
    Concurrent requests for the same user serialize strictly so races can never exceed `FREE_DAILY_QUESTION_LIMIT`.
    """
    ordered_qids: list[int] = []
    seen_q: set[int] = set()
    for raw in question_ids or []:
        if raw is None:
            continue
        qid = int(raw)
        if qid not in seen_q:
            seen_q.add(qid)
            ordered_qids.append(qid)

    if not ordered_qids:
        used, limit, remaining = free_daily_usage_counts(user_id, day=day)
        return True, used, remaining, []

    public_sample_ids = {
        row[0]
        for row in db.session.query(Question.id)
        .filter(
            Question.id.in_(ordered_qids),
            Question.is_public_sample.is_(True),
            Question.status == "published",
        )
        .all()
    }
    non_sample_qids = [qid for qid in ordered_qids if qid not in public_sample_ids]
    if not non_sample_qids:
        used, limit, remaining = free_daily_usage_counts(user_id, day=day)
        return True, used, remaining, ordered_qids

    today = day or local_today()
    limit = free_daily_question_limit()
    user_lock = _lock_for_user(user_id)
    with user_lock:
        bind = db.session.get_bind()
        if bind is not None and bind.dialect.name != "sqlite":
            # Serialize cross-worker Postgres allocations per user row
            db.session.execute(text('SELECT id FROM "user" WHERE id = :uid FOR UPDATE'), {"uid": user_id})

        already_today = {
            row[0]
            for row in db.session.query(DailyQuestionAccess.question_id)
            .filter_by(user_id=user_id, access_date=today)
            .all()
        }
        used_count = len(already_today)
        missing_qids = [qid for qid in non_sample_qids if qid not in already_today]
        remaining = max(0, limit - used_count)

        if partial:
            take_new = missing_qids[:remaining]
            allowed_set = public_sample_ids | already_today | set(take_new)
            allowed_qids = [qid for qid in ordered_qids if qid in allowed_set]
            if not allowed_qids:
                return False, used_count, 0, []
            to_insert = take_new
        else:
            if used_count + len(missing_qids) > limit:
                return False, used_count, remaining, []
            allowed_qids = ordered_qids
            to_insert = missing_qids

        if to_insert:
            for qid in to_insert:
                db.session.add(DailyQuestionAccess(user_id=user_id, access_date=today, question_id=qid))
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                # Recompute cleanly if a concurrent external transaction raced on unique key
                already_after = {
                    row[0]
                    for row in db.session.query(DailyQuestionAccess.question_id)
                    .filter_by(user_id=user_id, access_date=today)
                    .all()
                }
                used_after = len(already_after)
                if used_after > limit and not all(qid in already_after for qid in to_insert):
                    return False, used_after, max(0, limit - used_after), []
                return True, used_after, max(0, limit - used_after), allowed_qids

        new_used = used_count + len(to_insert)
        return True, new_used, max(0, limit - new_used), allowed_qids


def subscription_status_summary(user: User | None) -> dict:
    """Summarize active entitlement tier for templates, banners, and /subscription page."""
    if not user or not getattr(user, "is_authenticated", False):
        return {
            "tier": "anonymous",
            "has_full_access": False,
            "has_teacher_link": False,
            "active_subscription": None,
            "legacy_access_until": None,
            "daily_used": 0,
            "daily_limit": free_daily_question_limit(),
            "daily_remaining": free_daily_question_limit(),
        }
    if is_content_staff(user):
        return {
            "tier": "staff",
            "has_full_access": True,
            "has_teacher_link": False,
            "active_subscription": None,
            "legacy_access_until": None,
            "daily_used": 0,
            "daily_limit": free_daily_question_limit(),
            "daily_remaining": free_daily_question_limit(),
        }
    teacher_linked = has_teacher_link(user)
    enrolled = is_enrolled_monday_student(user)
    active_sub = active_subscription_for_user(user)
    legacy_ok = has_valid_legacy_access(user)
    used, limit, remaining = free_daily_usage_counts(user.id)

    if enrolled:
        tier = "enrolled"
    elif active_sub is not None:
        tier = "subscription"
    elif legacy_ok:
        tier = "legacy"
    elif not subscriptions_enforced():
        tier = "open"
    else:
        tier = "free"

    return {
        "tier": tier,
        "has_full_access": enrolled or (active_sub is not None) or legacy_ok or (not subscriptions_enforced()),
        "has_teacher_link": teacher_linked,
        "active_subscription": active_sub,
        "legacy_access_until": user.legacy_access_until if (legacy_ok and not enrolled and active_sub is None and subscriptions_enforced()) else None,
        "daily_used": used,
        "daily_limit": limit,
        "daily_remaining": remaining,
    }


def get_or_create_default_plan() -> SubscriptionPlan:
    """Fetch default active SubscriptionPlan or create one from current Config (never hardcoding prices)."""
    plan = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.id.asc()).first()
    if plan is not None:
        return plan
    price_amount = int(current_app.config.get("PUBLIC_QBANK_PRICE_AMOUNT", 800) or 800)
    currency = (current_app.config.get("PUBLIC_QBANK_PRICE_CURRENCY") or "USD").strip().upper()
    plan = SubscriptionPlan(
        code="qbank_monthly",
        name="Подписка на банк вопросов",
        description="Полный самостоятельный доступ к банку вопросов, тренировочным сессиям и сборникам.",
        price_amount=price_amount,
        currency=currency,
        billing_period="monthly",
        duration_days=30,
        is_active=True,
    )
    db.session.add(plan)
    db.session.flush()
    return plan


def count_legacy_backfill_candidates() -> dict[str, int | bool]:
    """Strictly read-only diagnostic count of students eligible for legacy_access_until grandfathering.

    Safe to execute BEFORE migration `h4c5d6e7f8a9` runs: inspects actual DB columns/tables and never
    references `user.legacy_access_until` if that column does not yet exist.
    """
    from sqlalchemy import inspect as sa_inspect

    insp = sa_inspect(db.engine)
    if not insp.has_table("user"):
        return {
            "schema_has_legacy_column": False,
            "total_students": 0,
            "enrolled_students": 0,
            "would_backfill_if_null": 0,
            "already_grandfathered": 0,
        }

    user_cols = {c["name"] for c in insp.get_columns("user")}
    has_legacy_col = "legacy_access_until" in user_cols
    has_sr = insp.has_table("student_record")
    has_ta = insp.has_table("teacher_assignments")
    has_ge = insp.has_table("group_enrollments")

    enrolled_clauses: list[str] = []
    if has_sr and has_ta:
        enrolled_clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM student_record sr
                LEFT JOIN teacher_assignments ta ON ta.student_record_id = sr.id
                WHERE sr.student_user_id = "user".id
                  AND (
                      (ta.id IS NOT NULL AND ta.ended_at IS NULL)
                      OR (ta.id IS NULL AND sr.teacher_id IS NOT NULL)
                  )
            )
            """
        )
    elif has_sr:
        enrolled_clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM student_record sr
                WHERE sr.student_user_id = "user".id
                  AND sr.teacher_id IS NOT NULL
            )
            """
        )
    if has_ge:
        enrolled_clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM group_enrollments ge
                WHERE ge.student_user_id = "user".id
                  AND ge.left_at IS NULL
                  AND ge.status = 'active'
            )
            """
        )

    enrolled_sql = " OR ".join(f"({c})" for c in enrolled_clauses) if enrolled_clauses else "1 = 0"
    params = {"not_blocked": False}

    total_students = int(
        db.session.execute(
            text('SELECT COUNT(*) FROM "user" WHERE role = \'student\' AND is_blocked = :not_blocked'),
            params,
        ).scalar_one()
    )
    enrolled_students = int(
        db.session.execute(
            text(f'SELECT COUNT(*) FROM "user" WHERE role = \'student\' AND is_blocked = :not_blocked AND ({enrolled_sql})'),
            params,
        ).scalar_one()
    )
    if not has_legacy_col:
        would_backfill = int(
            db.session.execute(
                text(f'SELECT COUNT(*) FROM "user" WHERE role = \'student\' AND is_blocked = :not_blocked AND NOT ({enrolled_sql})'),
                params,
            ).scalar_one()
        )
        already_backfilled = 0
    else:
        would_backfill = int(
            db.session.execute(
                text(
                    f'SELECT COUNT(*) FROM "user" '
                    f'WHERE role = \'student\' AND is_blocked = :not_blocked '
                    f'AND legacy_access_until IS NULL AND NOT ({enrolled_sql})'
                ),
                params,
            ).scalar_one()
        )
        already_backfilled = int(
            db.session.execute(
                text(
                    f'SELECT COUNT(*) FROM "user" '
                    f'WHERE role = \'student\' AND is_blocked = :not_blocked '
                    f'AND legacy_access_until IS NOT NULL AND NOT ({enrolled_sql})'
                ),
                params,
            ).scalar_one()
        )
    return {
        "schema_has_legacy_column": has_legacy_col,
        "total_students": total_students,
        "enrolled_students": enrolled_students,
        "would_backfill_if_null": would_backfill,
        "already_grandfathered": already_backfilled,
    }


def grant_manual_subscription(
    actor: User,
    target_user: User,
    plan: SubscriptionPlan,
    *,
    status: str = "active",
    duration_days: int | None = None,
    note: str = "",
) -> Subscription:
    """Manually grant or renew a Subscription with SubscriptionEvent + AuditLog."""
    if status not in ("active", "trialing"):
        raise ValueError("Manual grant status must be 'active' or 'trialing'.")
    now = utcnow()
    days = max(1, int(duration_days if duration_days is not None else (plan.duration_days or 30)))
    end_at = now + timedelta(days=days)

    # Close any existing open active/trialing grant cleanly before issuing the replacement period
    existing_open = Subscription.query.filter(
        Subscription.user_id == target_user.id,
        Subscription.status.in_(("active", "trialing")),
    ).all()
    for prev in existing_open:
        old_st = prev.status
        prev.status = "expired"
        db.session.add(
            SubscriptionEvent(
                subscription=prev,
                user_id=target_user.id,
                actor_id=actor.id,
                event_type="expire",
                old_status=old_st,
                new_status="expired",
                payload={"reason": "superseded_by_manual_grant"},
            )
        )

    sub = Subscription(
        user_id=target_user.id,
        plan_id=plan.id,
        status=status,
        starts_at=now,
        current_period_end=end_at if status == "active" else None,
        trial_ends_at=end_at if status == "trialing" else None,
        granted_by_id=actor.id,
        note=(note or "").strip()[:255],
    )
    db.session.add(sub)
    db.session.flush()

    ev = SubscriptionEvent(
        subscription_id=sub.id,
        user_id=target_user.id,
        actor_id=actor.id,
        event_type="manual_grant",
        old_status=None,
        new_status=status,
        payload={
            "plan_id": plan.id,
            "plan_code": plan.code,
            "duration_days": days,
            "ends_at": end_at.isoformat(),
            "note": sub.note,
        },
    )
    db.session.add(ev)
    write_audit_log(
        actor_id=actor.id,
        action="subscription_manual_grant",
        entity_type="bank_subscription",
        entity_id=sub.id,
        new_value={
            "user_id": target_user.id,
            "plan_id": plan.id,
            "plan_code": plan.code,
            "status": status,
            "duration_days": days,
            "ends_at": end_at.isoformat(),
            "note": sub.note,
        },
    )
    return sub


def change_subscription_plan(
    actor: User,
    subscription: Subscription,
    new_plan: SubscriptionPlan,
    *,
    note: str = "",
) -> Subscription:
    """Change the SubscriptionPlan of an existing Subscription and write SubscriptionEvent + AuditLog."""
    old_plan_id = subscription.plan_id
    subscription.plan_id = new_plan.id
    if note:
        subscription.note = note.strip()[:255]
    ev = SubscriptionEvent(
        subscription_id=subscription.id,
        user_id=subscription.user_id,
        actor_id=actor.id,
        event_type="plan_change",
        old_status=subscription.status,
        new_status=subscription.status,
        payload={
            "old_plan_id": old_plan_id,
            "new_plan_id": new_plan.id,
            "new_plan_code": new_plan.code,
            "note": (note or "").strip()[:255],
        },
    )
    db.session.add(ev)
    write_audit_log(
        actor_id=actor.id,
        action="subscription_plan_change",
        entity_type="bank_subscription",
        entity_id=subscription.id,
        old_value={"plan_id": old_plan_id},
        new_value={"plan_id": new_plan.id, "plan_code": new_plan.code, "note": (note or "").strip()[:255]},
    )
    return subscription


def cancel_subscription(
    actor: User,
    subscription: Subscription,
    *,
    note: str = "",
) -> Subscription:
    """Immediately cancel a Subscription and write SubscriptionEvent + AuditLog."""
    now = utcnow()
    old_status = subscription.status
    subscription.status = "cancelled"
    subscription.cancelled_at = now
    if subscription.current_period_end is None or subscription.current_period_end > now:
        subscription.current_period_end = now
    if subscription.trial_ends_at is not None and subscription.trial_ends_at > now:
        subscription.trial_ends_at = now
    if note:
        subscription.note = note.strip()[:255]

    ev = SubscriptionEvent(
        subscription_id=subscription.id,
        user_id=subscription.user_id,
        actor_id=actor.id,
        event_type="cancel",
        old_status=old_status,
        new_status="cancelled",
        payload={"cancelled_at": now.isoformat(), "note": (note or "").strip()[:255]},
    )
    db.session.add(ev)
    write_audit_log(
        actor_id=actor.id,
        action="subscription_cancel",
        entity_type="bank_subscription",
        entity_id=subscription.id,
        old_value={"status": old_status},
        new_value={"status": "cancelled", "cancelled_at": now.isoformat(), "note": (note or "").strip()[:255]},
    )
    return subscription

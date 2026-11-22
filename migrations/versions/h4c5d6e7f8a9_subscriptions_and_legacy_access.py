"""subscriptions, daily free-tier tracking, and legacy_access_until backfill

Revision ID: h4c5d6e7f8a9
Revises: g3b4c5d6e7f8
Create Date: 2026-11-23 04:10:00.000000

"""
import os
from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa


revision = "h4c5d6e7f8a9"
down_revision = "g3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("legacy_access_until", sa.DateTime(), nullable=True))

    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("price_amount", sa.Integer(), nullable=False, server_default="800"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("billing_period", sa.String(length=16), nullable=False, server_default="monthly"),
        sa.Column("duration_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_subscription_plans_code"),
    )
    with op.batch_alter_table("subscription_plans", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_subscription_plans_is_active"), ["is_active"], unique=False)

    op.create_table(
        "bank_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(), nullable=True),
        sa.Column("granted_by_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["granted_by_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("bank_subscriptions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_bank_subscriptions_current_period_end"), ["current_period_end"], unique=False)
        batch_op.create_index(batch_op.f("ix_bank_subscriptions_plan_id"), ["plan_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_bank_subscriptions_status"), ["status"], unique=False)
        batch_op.create_index("ix_bank_subscriptions_user_status", ["user_id", "status"], unique=False)

    op.create_table(
        "subscription_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("old_status", sa.String(length=20), nullable=True),
        sa.Column("new_status", sa.String(length=20), nullable=True),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["bank_subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("subscription_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_subscription_events_subscription_id"), ["subscription_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_subscription_events_user_id"), ["user_id"], unique=False)

    op.create_table(
        "daily_question_access",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("access_date", sa.Date(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["question.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "access_date", "question_id", name="uq_daily_q_access_user_date_q"),
    )
    with op.batch_alter_table("daily_question_access", schema=None) as batch_op:
        batch_op.create_index("ix_daily_q_access_user_date", ["user_id", "access_date"], unique=False)

    # Backfill grandfathered access ONLY for existing active student accounts with NO enrollment or teacher link.
    legacy_days = max(1, int(os.environ.get("LEGACY_ACCESS_DAYS", "30") or "30"))
    until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=legacy_days)
    op.execute(
        sa.text(
            """
            UPDATE "user"
            SET legacy_access_until = :until
            WHERE role = 'student'
              AND is_blocked = :not_blocked
              AND legacy_access_until IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM student_record sr
                  LEFT JOIN teacher_assignments ta ON ta.student_record_id = sr.id
                  WHERE sr.student_user_id = "user".id
                    AND (
                        (ta.id IS NOT NULL AND ta.ended_at IS NULL)
                        OR (ta.id IS NULL AND sr.teacher_id IS NOT NULL)
                    )
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM group_enrollments ge
                  WHERE ge.student_user_id = "user".id
                    AND ge.left_at IS NULL
                    AND ge.status = 'active'
              )
            """
        ).bindparams(until=until, not_blocked=False)
    )


def downgrade():
    with op.batch_alter_table("daily_question_access", schema=None) as batch_op:
        batch_op.drop_index("ix_daily_q_access_user_date")
    op.drop_table("daily_question_access")

    with op.batch_alter_table("subscription_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_subscription_events_user_id"))
        batch_op.drop_index(batch_op.f("ix_subscription_events_subscription_id"))
    op.drop_table("subscription_events")

    with op.batch_alter_table("bank_subscriptions", schema=None) as batch_op:
        batch_op.drop_index("ix_bank_subscriptions_user_status")
        batch_op.drop_index(batch_op.f("ix_bank_subscriptions_status"))
        batch_op.drop_index(batch_op.f("ix_bank_subscriptions_plan_id"))
        batch_op.drop_index(batch_op.f("ix_bank_subscriptions_current_period_end"))
    op.drop_table("bank_subscriptions")

    with op.batch_alter_table("subscription_plans", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_subscription_plans_is_active"))
    op.drop_table("subscription_plans")

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("legacy_access_until")

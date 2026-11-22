"""stripe billing fields and idempotent webhook event ledger

Revision ID: i5d6e7f8a9b0
Revises: h4c5d6e7f8a9
Create Date: 2026-11-23 05:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "i5d6e7f8a9b0"
down_revision = "h4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("stripe_customer_id", sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f("ix_user_stripe_customer_id"), ["stripe_customer_id"], unique=False)

    with op.batch_alter_table("subscription_plans", schema=None) as batch_op:
        batch_op.add_column(sa.Column("stripe_price_id", sa.String(length=64), nullable=True))

    with op.batch_alter_table("bank_subscriptions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("provider", sa.String(length=24), nullable=False, server_default="manual"))
        batch_op.add_column(sa.Column("provider_subscription_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("provider_customer_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index(batch_op.f("ix_bank_subscriptions_provider_customer_id"), ["provider_customer_id"], unique=False)
        batch_op.create_unique_constraint("uq_bank_subscriptions_provider_sub_id", ["provider_subscription_id"])

    op.execute(sa.text("UPDATE bank_subscriptions SET provider = 'manual' WHERE provider IS NULL"))

    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False, server_default="stripe"),
        sa.Column("event_id", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="processed"),
        sa.Column("payload_summary", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_payment_webhook_events_event_id"),
    )
    with op.batch_alter_table("payment_webhook_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_payment_webhook_events_event_type"), ["event_type"], unique=False)


def downgrade():
    with op.batch_alter_table("payment_webhook_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_payment_webhook_events_event_type"))
    op.drop_table("payment_webhook_events")

    with op.batch_alter_table("bank_subscriptions", schema=None) as batch_op:
        batch_op.drop_constraint("uq_bank_subscriptions_provider_sub_id", type_="unique")
        batch_op.drop_index(batch_op.f("ix_bank_subscriptions_provider_customer_id"))
        batch_op.drop_column("cancel_at_period_end")
        batch_op.drop_column("provider_customer_id")
        batch_op.drop_column("provider_subscription_id")
        batch_op.drop_column("provider")

    with op.batch_alter_table("subscription_plans", schema=None) as batch_op:
        batch_op.drop_column("stripe_price_id")

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_stripe_customer_id"))
        batch_op.drop_column("stripe_customer_id")

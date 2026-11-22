"""crm bot models and lead telegram fields

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-11-23 02:18:00.000000

"""
from datetime import datetime, timezone
import json

from alembic import op
import sqlalchemy as sa

from services.crm_bot.macros_loader import load_macros_from_docs


revision = "e1f2a3b4c5d6"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("leads", schema=None) as batch_op:
        batch_op.add_column(sa.Column("telegram_chat_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("telegram_username", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("priority_score", sa.Integer(), nullable=False, server_default="50"))
        batch_op.add_column(sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("archive_reason", sa.String(length=120), nullable=False, server_default=""))
        batch_op.create_index(batch_op.f("ix_leads_telegram_chat_id"), ["telegram_chat_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_leads_telegram_username"), ["telegram_username"], unique=False)
        batch_op.create_index(batch_op.f("ix_leads_is_archived"), ["is_archived"], unique=False)

    op.create_table(
        "reply_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body_ru", sa.Text(), nullable=False),
        sa.Column("body_ky", sa.Text(), nullable=False),
        sa.Column("variables_json", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_reply_templates_category"), "reply_templates", ["category"], unique=False)
    op.create_index(op.f("ix_reply_templates_is_active"), "reply_templates", ["is_active"], unique=False)

    op.create_table(
        "bot_reply_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=True),
        sa.Column("template_slug", sa.String(length=80), nullable=True),
        sa.Column("intent", sa.String(length=48), nullable=False),
        sa.Column("subject", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=12), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=False),
        sa.Column("final_sent_text", sa.Text(), nullable=False),
        sa.Column("was_accepted", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bot_reply_feedback_lookup",
        "bot_reply_feedback",
        ["intent", "subject", "language", "was_accepted"],
        unique=False,
    )
    op.create_index(op.f("ix_bot_reply_feedback_created_at"), "bot_reply_feedback", ["created_at"], unique=False)
    op.create_index(op.f("ix_bot_reply_feedback_created_by_id"), "bot_reply_feedback", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_bot_reply_feedback_intent"), "bot_reply_feedback", ["intent"], unique=False)
    op.create_index(op.f("ix_bot_reply_feedback_language"), "bot_reply_feedback", ["language"], unique=False)
    op.create_index(op.f("ix_bot_reply_feedback_lead_id"), "bot_reply_feedback", ["lead_id"], unique=False)
    op.create_index(op.f("ix_bot_reply_feedback_subject"), "bot_reply_feedback", ["subject"], unique=False)
    op.create_index(op.f("ix_bot_reply_feedback_template_slug"), "bot_reply_feedback", ["template_slug"], unique=False)
    op.create_index(op.f("ix_bot_reply_feedback_was_accepted"), "bot_reply_feedback", ["was_accepted"], unique=False)

    # Seed initial Optima-style macros from docs/crm_bot/reply_macros.md idempotently
    conn = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for item in load_macros_from_docs():
        exists = conn.execute(
            sa.text("SELECT 1 FROM reply_templates WHERE slug = :slug"),
            {"slug": item["slug"]},
        ).first()
        if not exists:
            conn.execute(
                sa.text(
                    "INSERT INTO reply_templates "
                    "(slug, category, title, body_ru, body_ky, variables_json, is_active, created_at, updated_at) "
                    "VALUES (:slug, :category, :title, :body_ru, :body_ky, :variables_json, :is_active, :created_at, :updated_at)"
                ),
                {
                    "slug": item["slug"],
                    "category": item["category"],
                    "title": item["title"],
                    "body_ru": item["body_ru"],
                    "body_ky": item["body_ky"],
                    "variables_json": json.dumps(item["variables_json"], ensure_ascii=False),
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                },
            )


def downgrade():
    op.drop_index(op.f("ix_bot_reply_feedback_was_accepted"), table_name="bot_reply_feedback")
    op.drop_index(op.f("ix_bot_reply_feedback_template_slug"), table_name="bot_reply_feedback")
    op.drop_index(op.f("ix_bot_reply_feedback_subject"), table_name="bot_reply_feedback")
    op.drop_index(op.f("ix_bot_reply_feedback_lead_id"), table_name="bot_reply_feedback")
    op.drop_index(op.f("ix_bot_reply_feedback_language"), table_name="bot_reply_feedback")
    op.drop_index(op.f("ix_bot_reply_feedback_intent"), table_name="bot_reply_feedback")
    op.drop_index(op.f("ix_bot_reply_feedback_created_by_id"), table_name="bot_reply_feedback")
    op.drop_index(op.f("ix_bot_reply_feedback_created_at"), table_name="bot_reply_feedback")
    op.drop_index("ix_bot_reply_feedback_lookup", table_name="bot_reply_feedback")
    op.drop_table("bot_reply_feedback")

    op.drop_index(op.f("ix_reply_templates_is_active"), table_name="reply_templates")
    op.drop_index(op.f("ix_reply_templates_category"), table_name="reply_templates")
    op.drop_table("reply_templates")

    with op.batch_alter_table("leads", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_leads_is_archived"))
        batch_op.drop_index(batch_op.f("ix_leads_telegram_username"))
        batch_op.drop_index(batch_op.f("ix_leads_telegram_chat_id"))
        batch_op.drop_column("archive_reason")
        batch_op.drop_column("is_archived")
        batch_op.drop_column("priority_score")
        batch_op.drop_column("telegram_username")
        batch_op.drop_column("telegram_chat_id")

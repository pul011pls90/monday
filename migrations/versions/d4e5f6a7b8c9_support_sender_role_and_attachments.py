"""support sender role and attachments

Revision ID: d4e5f6a7b8c9
Revises: c8d9e0f1a2b3
Create Date: 2026-11-22 23:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("report", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sender_role", sa.String(length=32), nullable=True))

    # NOTE: Historical Report rows did not record sender_role at send time;
    # backfill from the sender's current User.role as an approximate snapshot.
    op.execute(
        sa.text(
            "UPDATE report SET sender_role = COALESCE("
            "(SELECT u.role FROM \"user\" u WHERE u.id = report.author_id), "
            "'student')"
        )
    )

    with op.batch_alter_table("report", schema=None) as batch_op:
        batch_op.alter_column("sender_role", existing_type=sa.String(length=32), nullable=False)
        batch_op.create_index(batch_op.f("ix_report_sender_role"), ["sender_role"], unique=False)

    op.create_table(
        "support_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=120), nullable=False),
        sa.Column("mime", sa.String(length=32), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("bytes_original", sa.Integer(), nullable=False),
        sa.Column("bytes_stored", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["report.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        op.f("ix_support_attachments_message_id"),
        "support_attachments",
        ["message_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_support_attachments_message_id"), table_name="support_attachments")
    op.drop_table("support_attachments")

    with op.batch_alter_table("report", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_report_sender_role"))
        batch_op.drop_column("sender_role")

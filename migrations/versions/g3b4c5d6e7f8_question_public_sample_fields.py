"""question public sample fields

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-11-23 03:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "g3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("question", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_public_sample", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("public_image_key", sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f("ix_question_is_public_sample"), ["is_public_sample"], unique=False)
        batch_op.create_index(batch_op.f("ix_question_public_image_key"), ["public_image_key"], unique=True)

    # Backfill guard for any rows missing defaults before constraint enforcement
    op.execute(sa.text("UPDATE question SET is_public_sample = :val WHERE is_public_sample IS NULL").bindparams(val=False))


def downgrade():
    with op.batch_alter_table("question", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_question_public_image_key"))
        batch_op.drop_index(batch_op.f("ix_question_is_public_sample"))
        batch_op.drop_column("public_image_key")
        batch_op.drop_column("is_public_sample")

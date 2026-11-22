"""public site location and course fields

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-23 03:32:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("locations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("public_name", sa.String(length=160), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("map_url", sa.String(length=400), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("working_hours", sa.String(length=160), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("phone", sa.String(length=40), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("photo", sa.String(length=255), nullable=False, server_default=""))
        batch_op.create_index(batch_op.f("ix_locations_is_public"), ["is_public"], unique=False)

    with op.batch_alter_table("academic_courses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("public_summary", sa.Text(), nullable=False, server_default=""))
        batch_op.create_index(batch_op.f("ix_academic_courses_is_public"), ["is_public"], unique=False)


def downgrade():
    with op.batch_alter_table("academic_courses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_academic_courses_is_public"))
        batch_op.drop_column("public_summary")
        batch_op.drop_column("is_public")

    with op.batch_alter_table("locations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_locations_is_public"))
        batch_op.drop_column("photo")
        batch_op.drop_column("phone")
        batch_op.drop_column("working_hours")
        batch_op.drop_column("map_url")
        batch_op.drop_column("public_name")
        batch_op.drop_column("is_public")

"""student links and teacher assignments

Revision ID: c8d9e0f1a2b3
Revises: b7e2f4a9c102
Create Date: 2026-11-22 22:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c8d9e0f1a2b3"
down_revision = "b7e2f4a9c102"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("student_record", schema=None) as batch_op:
        batch_op.alter_column("teacher_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("source_lead_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("course_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("claimed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("claimed_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("phone", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("email", sa.String(length=255), nullable=True))
        batch_op.create_index(batch_op.f("ix_student_record_created_by_user_id"), ["created_by_user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_student_record_source_lead_id"), ["source_lead_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_student_record_course_id"), ["course_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_student_record_claimed_by_user_id"), ["claimed_by_user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_student_record_phone"), ["phone"], unique=False)
        batch_op.create_index(batch_op.f("ix_student_record_email"), ["email"], unique=False)
        batch_op.create_foreign_key(
            "fk_student_record_created_by_user_id",
            "user",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_student_record_source_lead_id",
            "leads",
            ["source_lead_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_student_record_course_id",
            "academic_courses",
            ["course_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_student_record_claimed_by_user_id",
            "user",
            ["claimed_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "teacher_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_record_id", sa.Integer(), nullable=False),
        sa.Column("teacher_user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("assigned_by_id", sa.Integer(), nullable=False),
        sa.Column("ended_by_id", sa.Integer(), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["assigned_by_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["course_id"], ["academic_courses.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ended_by_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_record_id"], ["student_record.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher_user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_teacher_assignments_teacher_ended",
        "teacher_assignments",
        ["teacher_user_id", "ended_at"],
        unique=False,
    )
    op.create_index(
        "ix_teacher_assignments_student_record_id",
        "teacher_assignments",
        ["student_record_id"],
        unique=False,
    )
    op.create_index(
        "uq_teacher_assignments_open_record_course",
        "teacher_assignments",
        ["student_record_id", "course_id"],
        unique=True,
        sqlite_where=sa.text("ended_at IS NULL AND course_id IS NOT NULL"),
        postgresql_where=sa.text("ended_at IS NULL AND course_id IS NOT NULL"),
    )
    op.create_index(
        "uq_teacher_assignments_open_record_nocourse",
        "teacher_assignments",
        ["student_record_id"],
        unique=True,
        sqlite_where=sa.text("ended_at IS NULL AND course_id IS NULL"),
        postgresql_where=sa.text("ended_at IS NULL AND course_id IS NULL"),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE student_record
            SET claimed_at = COALESCE(linked_at, created_at, CURRENT_TIMESTAMP),
                claimed_by_user_id = student_user_id
            WHERE student_user_id IS NOT NULL AND claimed_at IS NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO teacher_assignments (
                student_record_id,
                teacher_user_id,
                course_id,
                started_at,
                ended_at,
                assigned_by_id,
                ended_by_id,
                change_reason
            )
            SELECT
                id,
                teacher_id,
                course_id,
                COALESCE(linked_at, created_at, CURRENT_TIMESTAMP),
                NULL,
                COALESCE(created_by_user_id, teacher_id),
                NULL,
                NULL
            FROM student_record
            WHERE teacher_id IS NOT NULL
            """
        )
    )


def downgrade():
    op.drop_index("uq_teacher_assignments_open_record_nocourse", table_name="teacher_assignments")
    op.drop_index("uq_teacher_assignments_open_record_course", table_name="teacher_assignments")
    op.drop_index("ix_teacher_assignments_student_record_id", table_name="teacher_assignments")
    op.drop_index("ix_teacher_assignments_teacher_ended", table_name="teacher_assignments")
    op.drop_table("teacher_assignments")

    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM student_record WHERE teacher_id IS NULL"))

    with op.batch_alter_table("student_record", schema=None) as batch_op:
        batch_op.drop_constraint("fk_student_record_claimed_by_user_id", type_="foreignkey")
        batch_op.drop_constraint("fk_student_record_course_id", type_="foreignkey")
        batch_op.drop_constraint("fk_student_record_source_lead_id", type_="foreignkey")
        batch_op.drop_constraint("fk_student_record_created_by_user_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_student_record_email"))
        batch_op.drop_index(batch_op.f("ix_student_record_phone"))
        batch_op.drop_index(batch_op.f("ix_student_record_claimed_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_student_record_course_id"))
        batch_op.drop_index(batch_op.f("ix_student_record_source_lead_id"))
        batch_op.drop_index(batch_op.f("ix_student_record_created_by_user_id"))
        batch_op.drop_column("email")
        batch_op.drop_column("phone")
        batch_op.drop_column("claimed_by_user_id")
        batch_op.drop_column("claimed_at")
        batch_op.drop_column("course_id")
        batch_op.drop_column("source_lead_id")
        batch_op.drop_column("created_by_user_id")
        batch_op.alter_column("teacher_id", existing_type=sa.Integer(), nullable=False)

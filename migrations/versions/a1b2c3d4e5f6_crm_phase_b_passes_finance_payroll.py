"""crm phase b passes finance payroll

Revision ID: a1b2c3d4e5f6
Revises: 61002b45aac5
Create Date: 2026-11-22 05:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '61002b45aac5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'membership_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=True),
        sa.Column('total_lessons', sa.Integer(), nullable=True),
        sa.Column('duration_days', sa.Integer(), nullable=False),
        sa.Column('price_amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['academic_courses.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_membership_plans_course_id'), 'membership_plans', ['course_id'], unique=False)

    op.create_table(
        'student_passes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_user_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('enrollment_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('lessons_total', sa.Integer(), nullable=True),
        sa.Column('lessons_remaining', sa.Integer(), nullable=True),
        sa.Column('starts_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('agreed_price', sa.Integer(), nullable=False),
        sa.Column('paid_amount', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['enrollment_id'], ['group_enrollments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['plan_id'], ['membership_plans.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['student_user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_student_passes_enrollment_id'), 'student_passes', ['enrollment_id'], unique=False)
    op.create_index(op.f('ix_student_passes_expires_at'), 'student_passes', ['expires_at'], unique=False)
    op.create_index(op.f('ix_student_passes_plan_id'), 'student_passes', ['plan_id'], unique=False)
    op.create_index(op.f('ix_student_passes_status'), 'student_passes', ['status'], unique=False)
    op.create_index('ix_student_passes_student_status', 'student_passes', ['student_user_id', 'status'], unique=False)
    op.create_index(op.f('ix_student_passes_student_user_id'), 'student_passes', ['student_user_id'], unique=False)

    op.create_table(
        'payment_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_user_id', sa.Integer(), nullable=False),
        sa.Column('pass_id', sa.Integer(), nullable=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('method', sa.String(length=24), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=False),
        sa.Column('recorded_by_id', sa.Integer(), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pass_id'], ['student_passes.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['recorded_by_id'], ['user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['student_user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_payment_transactions_paid_at'), 'payment_transactions', ['paid_at'], unique=False)
    op.create_index(op.f('ix_payment_transactions_pass_id'), 'payment_transactions', ['pass_id'], unique=False)
    op.create_index(op.f('ix_payment_transactions_recorded_by_id'), 'payment_transactions', ['recorded_by_id'], unique=False)
    op.create_index(op.f('ix_payment_transactions_student_user_id'), 'payment_transactions', ['student_user_id'], unique=False)

    op.create_table(
        'lesson_pass_usages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lesson_id', sa.Integer(), nullable=False),
        sa.Column('student_user_id', sa.Integer(), nullable=False),
        sa.Column('pass_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pass_id'], ['student_passes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lesson_id', 'student_user_id', name='uq_lesson_pass_usage_lesson_student'),
    )
    op.create_index(op.f('ix_lesson_pass_usages_lesson_id'), 'lesson_pass_usages', ['lesson_id'], unique=False)
    op.create_index(op.f('ix_lesson_pass_usages_pass_id'), 'lesson_pass_usages', ['pass_id'], unique=False)
    op.create_index(op.f('ix_lesson_pass_usages_student_user_id'), 'lesson_pass_usages', ['student_user_id'], unique=False)

    op.create_table(
        'teacher_pay_rates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=True),
        sa.Column('rate_type', sa.String(length=24), nullable=False),
        sa.Column('rate_amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['academic_courses.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['teacher_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_teacher_pay_rates_course_id'), 'teacher_pay_rates', ['course_id'], unique=False)
    op.create_index(op.f('ix_teacher_pay_rates_teacher_id'), 'teacher_pay_rates', ['teacher_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_teacher_pay_rates_teacher_id'), table_name='teacher_pay_rates')
    op.drop_index(op.f('ix_teacher_pay_rates_course_id'), table_name='teacher_pay_rates')
    op.drop_table('teacher_pay_rates')

    op.drop_index(op.f('ix_lesson_pass_usages_student_user_id'), table_name='lesson_pass_usages')
    op.drop_index(op.f('ix_lesson_pass_usages_pass_id'), table_name='lesson_pass_usages')
    op.drop_index(op.f('ix_lesson_pass_usages_lesson_id'), table_name='lesson_pass_usages')
    op.drop_table('lesson_pass_usages')

    op.drop_index(op.f('ix_payment_transactions_student_user_id'), table_name='payment_transactions')
    op.drop_index(op.f('ix_payment_transactions_recorded_by_id'), table_name='payment_transactions')
    op.drop_index(op.f('ix_payment_transactions_pass_id'), table_name='payment_transactions')
    op.drop_index(op.f('ix_payment_transactions_paid_at'), table_name='payment_transactions')
    op.drop_table('payment_transactions')

    op.drop_index(op.f('ix_student_passes_student_user_id'), table_name='student_passes')
    op.drop_index('ix_student_passes_student_status', table_name='student_passes')
    op.drop_index(op.f('ix_student_passes_status'), table_name='student_passes')
    op.drop_index(op.f('ix_student_passes_plan_id'), table_name='student_passes')
    op.drop_index(op.f('ix_student_passes_expires_at'), table_name='student_passes')
    op.drop_index(op.f('ix_student_passes_enrollment_id'), table_name='student_passes')
    op.drop_table('student_passes')

    op.drop_index(op.f('ix_membership_plans_course_id'), table_name='membership_plans')
    op.drop_table('membership_plans')

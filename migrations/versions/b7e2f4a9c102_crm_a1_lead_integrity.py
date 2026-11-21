"""crm a1 lead integrity

Revision ID: b7e2f4a9c102
Revises: a1b2c3d4e5f6
Create Date: 2026-11-22 05:55:00.000000

"""
from alembic import op
import sqlalchemy as sa

from monday.phone_utils import normalize_messenger, normalize_phone


revision = 'b7e2f4a9c102'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_on_shift', sa.Boolean(), nullable=False, server_default=sa.true()))

    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('phone_e164', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('messenger_norm', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('temperature', sa.String(length=16), nullable=False, server_default='cold'))
        batch_op.add_column(sa.Column('ai_summary', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('previous_lead_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_leads_phone_e164'), ['phone_e164'], unique=False)
        batch_op.create_index(batch_op.f('ix_leads_messenger_norm'), ['messenger_norm'], unique=False)
        batch_op.create_index(batch_op.f('ix_leads_previous_lead_id'), ['previous_lead_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_leads_previous_lead_id',
            'leads',
            ['previous_lead_id'],
            ['id'],
            ondelete='SET NULL',
        )

    # Backfill normalized phone_e164 and messenger_norm for all existing leads
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, phone, messenger_handle FROM leads")).fetchall()
    for row in rows:
        p_norm = normalize_phone(row[1])
        m_norm = normalize_messenger(row[2])
        if p_norm is not None or m_norm is not None:
            conn.execute(
                sa.text("UPDATE leads SET phone_e164 = :p, messenger_norm = :m WHERE id = :id"),
                {"p": p_norm, "m": m_norm, "id": row[0]},
            )


def downgrade():
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_constraint('fk_leads_previous_lead_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_leads_previous_lead_id'))
        batch_op.drop_index(batch_op.f('ix_leads_messenger_norm'))
        batch_op.drop_index(batch_op.f('ix_leads_phone_e164'))
        batch_op.drop_column('previous_lead_id')
        batch_op.drop_column('ai_summary')
        batch_op.drop_column('temperature')
        batch_op.drop_column('messenger_norm')
        batch_op.drop_column('phone_e164')

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('is_on_shift')

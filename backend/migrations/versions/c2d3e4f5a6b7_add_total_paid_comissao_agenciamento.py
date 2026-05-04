"""add total_paid_comissao and total_paid_agenciamento to policies

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa


revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('total_paid_comissao', sa.Numeric(12, 2), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('total_paid_agenciamento', sa.Numeric(12, 2), nullable=True, server_default='0'))


def downgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.drop_column('total_paid_agenciamento')
        batch_op.drop_column('total_paid_comissao')

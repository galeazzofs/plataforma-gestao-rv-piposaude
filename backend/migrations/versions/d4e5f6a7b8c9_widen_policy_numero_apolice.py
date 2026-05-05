"""widen policy numero_apolice

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-05-05
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.drop_index('ix_policies_numero_apolice')
        batch_op.alter_column(
            'numero_apolice',
            existing_type=sa.String(length=100),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.alter_column(
            'numero_apolice',
            existing_type=sa.Text(),
            type_=sa.String(length=100),
            existing_nullable=True,
        )
        batch_op.create_index('ix_policies_numero_apolice', ['numero_apolice'], unique=False)

"""create cn_quarter_bonuses table

Issue #33: CN trimestral bonus storage.

Revision ID: c5bcdcdb5a76
Revises: 7aadd02f43f7
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa
from app.models.compat import GUID


revision = 'c5bcdcdb5a76'
down_revision = '7aadd02f43f7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cn_quarter_bonuses',
        sa.Column('id', GUID(length=36), nullable=False),
        sa.Column('cn_id', GUID(length=36), nullable=False),
        sa.Column('quarter', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('sao_trim_realizado', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('sao_trim_meta', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('pct_sao_trim', sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column('multiplicador', sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column('bonus_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('salario_base_snapshot', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('is_final', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['cn_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cn_id', 'quarter', 'year', name='uq_cn_quarter_bonus'),
    )


def downgrade():
    op.drop_table('cn_quarter_bonuses')

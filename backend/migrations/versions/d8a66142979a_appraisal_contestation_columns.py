"""add contestation columns to appraisal tables

Issue #36: contestation flag + notes used to route a component from
VALIDATING straight to REVOPS_REVIEW and back. Applied to
appraisals, cn_monthly_appraisals, and lider_vendas_quarter_appraisals.

Revision ID: d8a66142979a
Revises: 1da88efb63ba
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa


revision = 'd8a66142979a'
down_revision = '1da88efb63ba'
branch_labels = None
depends_on = None


_TABLES = (
    'appraisals',
    'cn_monthly_appraisals',
    'lider_vendas_quarter_appraisals',
)


def upgrade():
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column(
                'has_contestation', sa.Boolean(), nullable=False,
                server_default=sa.false(),
            ))
            batch_op.add_column(sa.Column(
                'contestation_note', sa.Text(), nullable=True,
            ))
            batch_op.add_column(sa.Column(
                'resolution_note', sa.Text(), nullable=True,
            ))


def downgrade():
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('resolution_note')
            batch_op.drop_column('contestation_note')
            batch_op.drop_column('has_contestation')

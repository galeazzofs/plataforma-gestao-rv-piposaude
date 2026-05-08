"""add last_action_at + reminder_sent_at to appraisal tables

Issue #39: power the 2-day reminders + 7-day escalations.

Revision ID: 4e48a4363926
Revises: d8a66142979a
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa


revision = '4e48a4363926'
down_revision = 'd8a66142979a'
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
                'last_action_at', sa.DateTime(timezone=True), nullable=True,
            ))
            batch_op.add_column(sa.Column(
                'reminder_sent_at', sa.Date(), nullable=True,
            ))


def downgrade():
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('reminder_sent_at')
            batch_op.drop_column('last_action_at')

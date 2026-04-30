"""widen audit_logs.action column to fit BATCH_CALCULATE/PARTIAL_MATCH

Revision ID: f3a9c5d8e2b7
Revises: 86eb3ff84c01
Create Date: 2026-04-30 18:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f3a9c5d8e2b7'
down_revision = '86eb3ff84c01'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('audit_logs') as batch_op:
        batch_op.alter_column(
            'action',
            existing_type=sa.String(length=10),
            type_=sa.String(length=32),
            existing_nullable=False,
        )


def downgrade():
    with op.batch_alter_table('audit_logs') as batch_op:
        batch_op.alter_column(
            'action',
            existing_type=sa.String(length=32),
            type_=sa.String(length=10),
            existing_nullable=False,
        )

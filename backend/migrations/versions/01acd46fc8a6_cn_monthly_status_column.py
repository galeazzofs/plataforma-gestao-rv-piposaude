"""add status enum to cn_monthly_appraisals; drop is_final

Issue #34: replace boolean is_final with full state machine status.
Existing is_final=True rows map to LOCKED; is_final=False rows map to DRAFT.

Revision ID: 01acd46fc8a6
Revises: c5bcdcdb5a76
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa


revision = '01acd46fc8a6'
down_revision = 'c5bcdcdb5a76'
branch_labels = None
depends_on = None


_STATUS_VALUES = (
    'DRAFT', 'CALCULATING', 'VALIDATING',
    'LIDER_REVIEW', 'REVOPS_REVIEW', 'LOCKED',
)


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'postgresql':
        op.execute(
            "CREATE TYPE cn_monthly_appraisal_status AS ENUM "
            f"({', '.join(repr(v) for v in _STATUS_VALUES)})"
        )
        op.execute(
            "ALTER TABLE cn_monthly_appraisals "
            "ADD COLUMN status cn_monthly_appraisal_status "
            "NOT NULL DEFAULT 'DRAFT'::cn_monthly_appraisal_status"
        )
        op.execute(
            "UPDATE cn_monthly_appraisals SET status = 'LOCKED' WHERE is_final = TRUE"
        )
        op.execute(
            "ALTER TABLE cn_monthly_appraisals DROP COLUMN is_final"
        )
    else:
        # SQLite path: do everything via batch_alter_table.
        with op.batch_alter_table('cn_monthly_appraisals', schema=None) as batch_op:
            batch_op.add_column(sa.Column(
                'status',
                sa.Enum(*_STATUS_VALUES, name='cn_monthly_appraisal_status'),
                nullable=False,
                server_default='DRAFT',
            ))
        op.execute(
            "UPDATE cn_monthly_appraisals SET status = 'LOCKED' WHERE is_final = 1"
        )
        with op.batch_alter_table('cn_monthly_appraisals', schema=None) as batch_op:
            batch_op.drop_column('is_final')


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'postgresql':
        op.execute(
            "ALTER TABLE cn_monthly_appraisals "
            "ADD COLUMN is_final BOOLEAN NOT NULL DEFAULT FALSE"
        )
        op.execute(
            "UPDATE cn_monthly_appraisals SET is_final = TRUE WHERE status = 'LOCKED'"
        )
        op.execute("ALTER TABLE cn_monthly_appraisals DROP COLUMN status")
        op.execute("DROP TYPE cn_monthly_appraisal_status")
    else:
        with op.batch_alter_table('cn_monthly_appraisals', schema=None) as batch_op:
            batch_op.add_column(sa.Column(
                'is_final', sa.Boolean(), nullable=False, server_default=sa.false(),
            ))
        op.execute(
            "UPDATE cn_monthly_appraisals SET is_final = 1 WHERE status = 'LOCKED'"
        )
        with op.batch_alter_table('cn_monthly_appraisals', schema=None) as batch_op:
            batch_op.drop_column('status')

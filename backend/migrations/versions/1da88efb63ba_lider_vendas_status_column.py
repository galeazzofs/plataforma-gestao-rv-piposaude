"""add status enum to lider_vendas_quarter_appraisals; drop is_final

Issue #35: full state machine for the leadership commission. Existing
is_final=True maps to LOCKED; is_final=False maps to DRAFT.

Revision ID: 1da88efb63ba
Revises: 01acd46fc8a6
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa


revision = '1da88efb63ba'
down_revision = '01acd46fc8a6'
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
            "CREATE TYPE lider_vendas_quarter_appraisal_status AS ENUM "
            f"({', '.join(repr(v) for v in _STATUS_VALUES)})"
        )
        op.execute(
            "ALTER TABLE lider_vendas_quarter_appraisals "
            "ADD COLUMN status lider_vendas_quarter_appraisal_status "
            "NOT NULL DEFAULT 'DRAFT'::lider_vendas_quarter_appraisal_status"
        )
        op.execute(
            "UPDATE lider_vendas_quarter_appraisals SET status = 'LOCKED' "
            "WHERE is_final = TRUE"
        )
        op.execute(
            "ALTER TABLE lider_vendas_quarter_appraisals DROP COLUMN is_final"
        )
    else:
        with op.batch_alter_table('lider_vendas_quarter_appraisals', schema=None) as batch_op:
            batch_op.add_column(sa.Column(
                'status',
                sa.Enum(*_STATUS_VALUES, name='lider_vendas_quarter_appraisal_status'),
                nullable=False, server_default='DRAFT',
            ))
        op.execute(
            "UPDATE lider_vendas_quarter_appraisals SET status = 'LOCKED' "
            "WHERE is_final = 1"
        )
        with op.batch_alter_table('lider_vendas_quarter_appraisals', schema=None) as batch_op:
            batch_op.drop_column('is_final')


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'postgresql':
        op.execute(
            "ALTER TABLE lider_vendas_quarter_appraisals "
            "ADD COLUMN is_final BOOLEAN NOT NULL DEFAULT FALSE"
        )
        op.execute(
            "UPDATE lider_vendas_quarter_appraisals SET is_final = TRUE "
            "WHERE status = 'LOCKED'"
        )
        op.execute("ALTER TABLE lider_vendas_quarter_appraisals DROP COLUMN status")
        op.execute("DROP TYPE lider_vendas_quarter_appraisal_status")
    else:
        with op.batch_alter_table('lider_vendas_quarter_appraisals', schema=None) as batch_op:
            batch_op.add_column(sa.Column(
                'is_final', sa.Boolean(), nullable=False, server_default=sa.false(),
            ))
        op.execute(
            "UPDATE lider_vendas_quarter_appraisals SET is_final = 1 "
            "WHERE status = 'LOCKED'"
        )
        with op.batch_alter_table('lider_vendas_quarter_appraisals', schema=None) as batch_op:
            batch_op.drop_column('status')

"""create quarterly_cycles + appraisals.cycle_id

Issue #32. Foundational table for the quarterly orchestration:
  - quarterly_cycles(id, quarter, year, status, created_by, created_at, locked_at)
  - appraisals.cycle_id (FK quarterly_cycles.id, nullable, additive only)

Revision ID: 7aadd02f43f7
Revises: 9f203e93a235
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa
from app.models.compat import GUID


revision = '7aadd02f43f7'
down_revision = '9f203e93a235'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'quarterly_cycles',
        sa.Column('id', GUID(length=36), nullable=False),
        sa.Column('quarter', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('OPEN', 'LOCKED', name='quarterly_cycle_status'),
            nullable=False,
        ),
        sa.Column('created_by', GUID(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'quarter', 'year', name='uq_quarterly_cycle_quarter_year',
        ),
    )

    with op.batch_alter_table('appraisals', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('cycle_id', GUID(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_appraisals_cycle_id_quarterly_cycles',
            'quarterly_cycles', ['cycle_id'], ['id'],
        )
        batch_op.create_index(
            'ix_appraisals_cycle_id', ['cycle_id'], unique=False,
        )


def downgrade():
    with op.batch_alter_table('appraisals', schema=None) as batch_op:
        batch_op.drop_index('ix_appraisals_cycle_id')
        batch_op.drop_constraint(
            'fk_appraisals_cycle_id_quarterly_cycles', type_='foreignkey',
        )
        batch_op.drop_column('cycle_id')

    op.drop_table('quarterly_cycles')

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("DROP TYPE quarterly_cycle_status")

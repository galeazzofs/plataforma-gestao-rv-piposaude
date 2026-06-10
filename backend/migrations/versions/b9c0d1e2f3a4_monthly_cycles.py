"""quarterly_cycles -> monthly_cycles

The apuração now runs as one monthly cycle holding the full sequence
(Apuração EV, Apuração CN, and — on quarter-end months — Bônus CN,
Bônus EV and Bônus Liderança):
  - create monthly_cycles(id, month, year, status, created_by,
    created_at, locked_at)
  - carry each quarterly cycle over as its three monthly cycles
  - drop appraisals.cycle_id (never populated; cycles attach by period)
  - drop quarterly_cycles

Revision ID: b9c0d1e2f3a4
Revises: f1e2d3c4b5a6
Create Date: 2026-06-10
"""
import uuid

from alembic import op
import sqlalchemy as sa
from app.models.compat import GUID


revision = 'b9c0d1e2f3a4'
down_revision = 'f1e2d3c4b5a6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'monthly_cycles',
        sa.Column('id', GUID(length=36), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('OPEN', 'LOCKED', name='monthly_cycle_status'),
            nullable=False,
        ),
        sa.Column('created_by', GUID(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'month', 'year', name='uq_monthly_cycle_month_year',
        ),
    )

    # Carry existing quarterly cycles over: Q n/year becomes the three
    # monthly cycles of its calendar months, same status / timestamps.
    bind = op.get_bind()
    monthly = sa.table(
        'monthly_cycles',
        sa.column('id', GUID(length=36)),
        sa.column('month', sa.Integer),
        sa.column('year', sa.Integer),
        sa.column('status', sa.String),
        sa.column('created_by', GUID(length=36)),
        sa.column('created_at', sa.DateTime(timezone=True)),
        sa.column('locked_at', sa.DateTime(timezone=True)),
    )
    rows = bind.execute(sa.text(
        "SELECT quarter, year, status, created_by, created_at, locked_at "
        "FROM quarterly_cycles"
    )).fetchall()
    for quarter, year, status, created_by, created_at, locked_at in rows:
        for month in range((quarter - 1) * 3 + 1, quarter * 3 + 1):
            bind.execute(monthly.insert().values(
                id=str(uuid.uuid4()),
                month=month, year=year, status=status,
                created_by=created_by, created_at=created_at,
                locked_at=locked_at,
            ))

    with op.batch_alter_table('appraisals', schema=None) as batch_op:
        batch_op.drop_index('ix_appraisals_cycle_id')
        batch_op.drop_constraint(
            'fk_appraisals_cycle_id_quarterly_cycles', type_='foreignkey',
        )
        batch_op.drop_column('cycle_id')

    op.drop_table('quarterly_cycles')
    if bind.dialect.name == 'postgresql':
        op.execute("DROP TYPE quarterly_cycle_status")


def downgrade():
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

    # Monthly cycle rows are not folded back into quarters.
    op.drop_table('monthly_cycles')

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("DROP TYPE monthly_cycle_status")

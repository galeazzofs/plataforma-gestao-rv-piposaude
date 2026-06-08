"""EV commission apuração: quarter → month (rekey + reset)

Revision ID: f1e2d3c4b5a6
Revises: 6b7c8d9e0f12
Create Date: 2026-06-05

The Comissão EV is now apurada monthly instead of quarterly. The four
apuração tables (appraisals, commissions, financial_imports, perks) are
rekeyed from `quarter` to `month` and reset — the monthly flow repopulates
them from scratch.

Policy state is preserved: the 12-month clock (installments_paid) is baked
into the legacy baseline (initial_installments_paid) so the monthly
calculator — which rebuilds installments_paid = initial_installments_paid +
positive Comissão months of LOCKED apurações — keeps the count even with no
LOCKED apuração right after the reset. total_paid_comissao /
total_paid_agenciamento / first_payment_real / commission_paid_legacy are
left untouched.

The quarterly components stay quarterly (no schema change):
ev_quarter_achievements, goals, lider_vendas_quarter_appraisals,
cn_quarter_bonuses, quarterly_cycles.
"""
from alembic import op
import sqlalchemy as sa


revision = 'f1e2d3c4b5a6'
down_revision = '6b7c8d9e0f12'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Reset the apuração tables — they are rekeyed and repopulated monthly.
    #    ev_validations reference appraisals, so clear them before appraisals.
    op.execute("DELETE FROM commissions")
    op.execute("DELETE FROM ev_validations")
    op.execute("DELETE FROM perks")
    op.execute("DELETE FROM financial_imports")
    op.execute("DELETE FROM appraisals")

    # 2. Preserve the 12-month clock across the reset. Bake the current
    #    effective clock into the legacy baseline so the monthly calculator
    #    keeps it even with no LOCKED apuração yet. Paid totals, legacy paid
    #    and first_payment_real are intentionally left as-is.
    op.execute(
        "UPDATE policies SET initial_installments_paid = installments_paid "
        "WHERE installments_paid > initial_installments_paid"
    )

    # 3. Rekey quarter → month on the four apuração tables.
    with op.batch_alter_table('appraisals', schema=None) as batch_op:
        batch_op.drop_constraint('uq_appraisal_quarter_year', type_='unique')
        batch_op.alter_column(
            'quarter', new_column_name='month',
            existing_type=sa.Integer(), existing_nullable=False,
        )
        batch_op.create_unique_constraint(
            'uq_appraisal_month_year', ['month', 'year'],
        )

    with op.batch_alter_table('commissions', schema=None) as batch_op:
        batch_op.drop_constraint('uq_commission_policy_quarter_year', type_='unique')
        batch_op.alter_column(
            'quarter', new_column_name='month',
            existing_type=sa.Integer(), existing_nullable=False,
        )
        batch_op.create_unique_constraint(
            'uq_commission_policy_month_year', ['policy_id', 'month', 'year'],
        )

    with op.batch_alter_table('financial_imports', schema=None) as batch_op:
        batch_op.alter_column(
            'quarter', new_column_name='month',
            existing_type=sa.Integer(), existing_nullable=False,
        )

    with op.batch_alter_table('perks', schema=None) as batch_op:
        batch_op.alter_column(
            'quarter', new_column_name='month',
            existing_type=sa.Integer(), existing_nullable=False,
        )


def downgrade():
    # Rename month → quarter back and restore the old unique constraints.
    # The data wipe and clock-baseline bump are destructive by design and
    # are not reversed.
    with op.batch_alter_table('perks', schema=None) as batch_op:
        batch_op.alter_column(
            'month', new_column_name='quarter',
            existing_type=sa.Integer(), existing_nullable=False,
        )

    with op.batch_alter_table('financial_imports', schema=None) as batch_op:
        batch_op.alter_column(
            'month', new_column_name='quarter',
            existing_type=sa.Integer(), existing_nullable=False,
        )

    with op.batch_alter_table('commissions', schema=None) as batch_op:
        batch_op.drop_constraint('uq_commission_policy_month_year', type_='unique')
        batch_op.alter_column(
            'month', new_column_name='quarter',
            existing_type=sa.Integer(), existing_nullable=False,
        )
        batch_op.create_unique_constraint(
            'uq_commission_policy_quarter_year', ['policy_id', 'quarter', 'year'],
        )

    with op.batch_alter_table('appraisals', schema=None) as batch_op:
        batch_op.drop_constraint('uq_appraisal_month_year', type_='unique')
        batch_op.alter_column(
            'month', new_column_name='quarter',
            existing_type=sa.Integer(), existing_nullable=False,
        )
        batch_op.create_unique_constraint(
            'uq_appraisal_quarter_year', ['quarter', 'year'],
        )

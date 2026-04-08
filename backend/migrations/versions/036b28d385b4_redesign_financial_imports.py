"""redesign financial_imports

Revision ID: 036b28d385b4
Revises: 080bc8ca92f5
Create Date: 2026-04-07 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '036b28d385b4'
down_revision = '080bc8ca92f5'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Table is empty in production (verified). Safe to wipe.
    if dialect == 'postgresql':
        op.execute("TRUNCATE TABLE financial_imports")
    else:
        op.execute("DELETE FROM financial_imports")

    # Drop legacy unique constraint (Postgres only — SQLite handles via batch_alter_table below)
    if dialect == 'postgresql':
        op.execute("ALTER TABLE financial_imports DROP CONSTRAINT IF EXISTS uq_financial_policy_month")

    with op.batch_alter_table('financial_imports', schema=None) as batch_op:
        if dialect == 'postgresql':
            batch_op.alter_column('policy_id', existing_type=postgresql.UUID(), nullable=True)
        else:
            batch_op.alter_column('policy_id', existing_type=sa.String(length=36), nullable=True)
        batch_op.add_column(sa.Column('cliente_mae', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('operadora', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('produto', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('tipo_receita', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('status_recebimento', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('data_recebimento', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('match_status', sa.String(length=30), nullable=False, server_default='UNMATCHED'))
        batch_op.add_column(sa.Column('matched_at', sa.DateTime(timezone=True), nullable=True))

    op.create_index('ix_financial_imports_quarter_year', 'financial_imports', ['quarter', 'year'])
    op.create_index('ix_financial_imports_match_status', 'financial_imports', ['match_status'])
    op.create_index('ix_financial_imports_policy_id', 'financial_imports', ['policy_id'])


def downgrade():
    op.drop_index('ix_financial_imports_policy_id', table_name='financial_imports')
    op.drop_index('ix_financial_imports_match_status', table_name='financial_imports')
    op.drop_index('ix_financial_imports_quarter_year', table_name='financial_imports')

    with op.batch_alter_table('financial_imports', schema=None) as batch_op:
        batch_op.drop_column('matched_at')
        batch_op.drop_column('match_status')
        batch_op.drop_column('data_recebimento')
        batch_op.drop_column('status_recebimento')
        batch_op.drop_column('tipo_receita')
        batch_op.drop_column('produto')
        batch_op.drop_column('operadora')
        batch_op.drop_column('cliente_mae')
        batch_op.alter_column('policy_id', existing_type=postgresql.UUID(), nullable=False)

    op.create_unique_constraint('uq_financial_policy_month', 'financial_imports', ['policy_id', 'nf_mes_recebimento'])

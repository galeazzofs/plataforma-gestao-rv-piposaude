"""apolice anchored sync wipe and schema

Revision ID: 86eb3ff84c01
Revises: 5fd44aa9a820
Create Date: 2026-04-30 11:14:26.694560

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '86eb3ff84c01'
down_revision = '5fd44aa9a820'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1. Wipe existing data — clear all child tables that FK to policies
    # before deleting policies themselves (no ondelete cascade configured).
    op.execute("DELETE FROM commissions")
    op.execute("DELETE FROM ev_validations")
    op.execute("UPDATE financial_imports SET policy_id = NULL WHERE policy_id IS NOT NULL")
    op.execute("DELETE FROM policies")

    # 2. Add SAUDE_ODONTO to benefit_type enum (Postgres only — SQLite uses VARCHAR check)
    if dialect == "postgresql":
        # ALTER TYPE ADD VALUE cannot run inside a transaction block
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE benefit_type ADD VALUE IF NOT EXISTS 'SAUDE_ODONTO'")

    # 3. Add new columns and adjust unique constraints on policies
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hubspot_apolice_id', sa.String(length=100), nullable=False))
        batch_op.add_column(sa.Column('numero_apolice', sa.String(length=100), nullable=True))
        batch_op.create_index('ix_policies_hubspot_apolice_id', ['hubspot_apolice_id'], unique=True)
        batch_op.create_index('ix_policies_numero_apolice', ['numero_apolice'])
        # Drop old unique on hubspot_ticket_id but keep a regular index
        batch_op.drop_index('ix_policies_hubspot_ticket_id')
        batch_op.create_index('ix_policies_hubspot_ticket_id', ['hubspot_ticket_id'], unique=False)


def downgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.drop_index('ix_policies_hubspot_ticket_id')
        batch_op.create_index('ix_policies_hubspot_ticket_id', ['hubspot_ticket_id'], unique=True)
        batch_op.drop_index('ix_policies_numero_apolice')
        batch_op.drop_index('ix_policies_hubspot_apolice_id')
        batch_op.drop_column('numero_apolice')
        batch_op.drop_column('hubspot_apolice_id')

    # NOTE: Postgres has no clean way to remove an enum value. SAUDE_ODONTO
    # remains in the type definition after downgrade. Acceptable trade-off.

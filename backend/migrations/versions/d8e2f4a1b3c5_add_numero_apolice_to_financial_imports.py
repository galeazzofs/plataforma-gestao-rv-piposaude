"""add numero_apolice to financial_imports

Revision ID: d8e2f4a1b3c5
Revises: c4f1a2b3d5e6
Create Date: 2026-04-30 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8e2f4a1b3c5'
down_revision = 'c4f1a2b3d5e6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('financial_imports', schema=None) as batch_op:
        batch_op.add_column(sa.Column('numero_apolice', sa.String(length=100), nullable=True))
        batch_op.create_index('ix_financial_imports_numero_apolice', ['numero_apolice'])


def downgrade():
    with op.batch_alter_table('financial_imports', schema=None) as batch_op:
        batch_op.drop_index('ix_financial_imports_numero_apolice')
        batch_op.drop_column('numero_apolice')

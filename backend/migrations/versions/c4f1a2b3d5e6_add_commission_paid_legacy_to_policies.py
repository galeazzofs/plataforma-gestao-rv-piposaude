"""add commission_paid_legacy to policies (merge two heads)

Revision ID: c4f1a2b3d5e6
Revises: 86eb3ff84c01, 9d8a108b4890
Create Date: 2026-04-30 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4f1a2b3d5e6'
down_revision = ('86eb3ff84c01', '9d8a108b4890')
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('commission_paid_legacy', sa.Numeric(precision=12, scale=2), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.drop_column('commission_paid_legacy')

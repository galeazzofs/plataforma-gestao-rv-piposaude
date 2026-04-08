"""add is_locked to policies

Revision ID: 080bc8ca92f5
Revises: bed5f7ad4ac0
Create Date: 2026-04-07 20:55:57.901406

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '080bc8ca92f5'
down_revision = 'bed5f7ad4ac0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_locked', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.drop_column('is_locked')

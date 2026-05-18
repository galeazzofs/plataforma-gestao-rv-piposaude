"""add departed EV flag and rename default sales teams

Revision ID: 6b7c8d9e0f12
Revises: 4e48a4363926
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa


revision = "6b7c8d9e0f12"
down_revision = "4e48a4363926"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "left_company",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ))

    op.execute("UPDATE teams SET name = 'Time P/M' WHERE name = 'Vendas 1'")
    op.execute("UPDATE teams SET name = 'Time G+' WHERE name = 'Vendas 2'")


def downgrade():
    op.execute("UPDATE teams SET name = 'Vendas 1' WHERE name = 'Time P/M'")
    op.execute("UPDATE teams SET name = 'Vendas 2' WHERE name = 'Time G+'")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("left_company")

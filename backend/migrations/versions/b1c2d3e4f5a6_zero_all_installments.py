"""zero all installments_paid and initial_installments_paid

Revision ID: b1c2d3e4f5a6
Revises: a3f7b9c4d2e1
Create Date: 2026-05-04

Admin requested a manual reset of all month counters so they can fix
values by hand.
"""
from alembic import op


revision = 'b1c2d3e4f5a6'
down_revision = 'a3f7b9c4d2e1'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE policies SET installments_paid = 0, initial_installments_paid = 0")


def downgrade():
    # Cannot restore previous values — data-only migration.
    pass

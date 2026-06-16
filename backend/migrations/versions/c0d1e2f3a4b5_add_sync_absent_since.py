"""Add policies.sync_absent_since

The HubSpot sync no longer hard-deletes policies that carry paid (LOCKED)
history when their ticket vanishes from the fetch; it preserves + cancels
them and stamps when the absence was first noticed.

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-06-11

(Originally authored as d4e5f6a7b8c9, which collided with the earlier
"widen policy numero_apolice" migration; renamed to a unique id.)
"""
from alembic import op
import sqlalchemy as sa

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "policies",
        sa.Column("sync_absent_since", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("policies", "sync_absent_since")

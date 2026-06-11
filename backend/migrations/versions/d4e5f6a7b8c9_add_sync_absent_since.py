"""Add policies.sync_absent_since

The HubSpot sync no longer hard-deletes policies that carry paid (LOCKED)
history when their ticket vanishes from the fetch; it preserves + cancels
them and stamps when the absence was first noticed.

Revision ID: d4e5f6a7b8c9
Revises: b9c0d1e2f3a4
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
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

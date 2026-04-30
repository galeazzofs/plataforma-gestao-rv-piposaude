"""ticket anchored sync wipe and schema

Revision ID: a3f7b9c4d2e1
Revises: d8e2f4a1b3c5, f3a9c5d8e2b7
Create Date: 2026-04-30

Swap UNIQUE constraint between hubspot_apolice_id and hubspot_ticket_id —
the sync now creates 1 Policy per ticket instead of per apolice. Also makes
hubspot_apolice_id nullable since the apolice is now secondary metadata
rather than the row's identity (ticket is). Wipes data so the new sync
repopulates from scratch under the new shape.

Also acts as the merge point for the two extant heads on master
(`d8e2f4a1b3c5` numero_apolice on financial_imports, `f3a9c5d8e2b7` widen
audit_logs.action) so Alembic has a single head again.
"""
from alembic import op
import sqlalchemy as sa


revision = 'a3f7b9c4d2e1'
down_revision = ('d8e2f4a1b3c5', 'f3a9c5d8e2b7')
branch_labels = None
depends_on = None


def upgrade():
    # 1. Wipe — clear children before policies (no ON DELETE CASCADE configured).
    op.execute("DELETE FROM commissions")
    op.execute("DELETE FROM ev_validations")
    op.execute("UPDATE financial_imports SET policy_id = NULL WHERE policy_id IS NOT NULL")
    op.execute("DELETE FROM policies")

    # 2. Cleanup orphan cursor PlatformSetting from the briefly-incremental design.
    op.execute("DELETE FROM platform_settings WHERE key = 'hubspot_sync_last_success_at'")

    # 3. Swap UNIQUE + nullability:
    #    - hubspot_apolice_id: was UNIQUE NOT NULL → now non-unique nullable
    #    - hubspot_ticket_id:  was non-unique NOT NULL → now UNIQUE NOT NULL
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.alter_column('hubspot_apolice_id', existing_type=sa.String(length=100), nullable=True)
        batch_op.drop_index('ix_policies_hubspot_apolice_id')
        batch_op.create_index('ix_policies_hubspot_apolice_id', ['hubspot_apolice_id'], unique=False)
        batch_op.drop_index('ix_policies_hubspot_ticket_id')
        batch_op.create_index('ix_policies_hubspot_ticket_id', ['hubspot_ticket_id'], unique=True)


def downgrade():
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.drop_index('ix_policies_hubspot_ticket_id')
        batch_op.create_index('ix_policies_hubspot_ticket_id', ['hubspot_ticket_id'], unique=False)
        batch_op.drop_index('ix_policies_hubspot_apolice_id')
        batch_op.create_index('ix_policies_hubspot_apolice_id', ['hubspot_apolice_id'], unique=True)
        batch_op.alter_column('hubspot_apolice_id', existing_type=sa.String(length=100), nullable=False)
    # Wipe and orphan cleanup are not reversed (destructive by design).

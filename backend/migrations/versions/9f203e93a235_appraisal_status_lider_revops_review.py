"""extend appraisal_status with LIDER_REVIEW and REVOPS_REVIEW

State machine extension (issue #31):
  - rename REVIEWING -> REVOPS_REVIEW
  - add LIDER_REVIEW
  - remove APPROVED (existing rows promoted to LOCKED)

Revision ID: 9f203e93a235
Revises: 4ac16b631856
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa


revision = '9f203e93a235'
down_revision = '4ac16b631856'
branch_labels = None
depends_on = None


_NEW_VALUES = ('DRAFT', 'CALCULATING', 'VALIDATING',
               'LIDER_REVIEW', 'REVOPS_REVIEW', 'LOCKED')
_OLD_VALUES = ('DRAFT', 'CALCULATING', 'VALIDATING',
               'REVIEWING', 'APPROVED', 'LOCKED')


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'postgresql':
        # Recreate the enum type swapping the value set, mapping rows on the fly.
        op.execute(
            "CREATE TYPE appraisal_status_new AS ENUM "
            f"({', '.join(repr(v) for v in _NEW_VALUES)})"
        )
        op.execute(
            "ALTER TABLE appraisals "
            "ALTER COLUMN status DROP DEFAULT, "
            "ALTER COLUMN status TYPE appraisal_status_new USING ("
            "  CASE status::text "
            "    WHEN 'REVIEWING' THEN 'REVOPS_REVIEW' "
            "    WHEN 'APPROVED'  THEN 'LOCKED' "
            "    ELSE status::text "
            "  END"
            ")::appraisal_status_new, "
            "ALTER COLUMN status SET DEFAULT 'DRAFT'::appraisal_status_new"
        )
        op.execute("DROP TYPE appraisal_status")
        op.execute("ALTER TYPE appraisal_status_new RENAME TO appraisal_status")
    else:
        # SQLite stores enums as VARCHAR — only the row values need updating.
        op.execute(
            "UPDATE appraisals SET status = 'REVOPS_REVIEW' WHERE status = 'REVIEWING'"
        )
        op.execute(
            "UPDATE appraisals SET status = 'LOCKED' WHERE status = 'APPROVED'"
        )


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'postgresql':
        op.execute(
            "CREATE TYPE appraisal_status_new AS ENUM "
            f"({', '.join(repr(v) for v in _OLD_VALUES)})"
        )
        # We cannot recover APPROVED rows that were promoted to LOCKED;
        # LIDER_REVIEW collapses back into REVIEWING (best-effort downgrade).
        op.execute(
            "ALTER TABLE appraisals "
            "ALTER COLUMN status DROP DEFAULT, "
            "ALTER COLUMN status TYPE appraisal_status_new USING ("
            "  CASE status::text "
            "    WHEN 'REVOPS_REVIEW' THEN 'REVIEWING' "
            "    WHEN 'LIDER_REVIEW'  THEN 'REVIEWING' "
            "    ELSE status::text "
            "  END"
            ")::appraisal_status_new, "
            "ALTER COLUMN status SET DEFAULT 'DRAFT'::appraisal_status_new"
        )
        op.execute("DROP TYPE appraisal_status")
        op.execute("ALTER TYPE appraisal_status_new RENAME TO appraisal_status")
    else:
        op.execute(
            "UPDATE appraisals SET status = 'REVIEWING' "
            "WHERE status IN ('REVOPS_REVIEW', 'LIDER_REVIEW')"
        )

"""seed commission_pct_table v2

Revision ID: 5fd44aa9a820
Revises: 036b28d385b4
Create Date: 2026-04-07 21:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import date
import uuid


# revision identifiers, used by Alembic.
revision = '5fd44aa9a820'
down_revision = '036b28d385b4'
branch_labels = None
depends_on = None


MATRIX = [
    # (segment, achievement_min, achievement_max, commission_pct)
    ('PP', '0.0000', '0.4999', '0.07'),
    ('PP', '0.5000', '0.9999', '0.08'),
    ('PP', '1.0000', '99.9999', '0.10'),
    ('P',  '0.0000', '0.4999', '0.07'),
    ('P',  '0.5000', '0.9999', '0.08'),
    ('P',  '1.0000', '99.9999', '0.10'),
    ('M',  '0.0000', '0.4999', '0.05'),
    ('M',  '0.5000', '0.9999', '0.06'),
    ('M',  '1.0000', '99.9999', '0.08'),
    ('G',  '0.0000', '0.4999', '0.03'),
    ('G',  '0.5000', '0.9999', '0.04'),
    ('G',  '1.0000', '99.9999', '0.06'),
]


def upgrade():
    conn = op.get_bind()

    # Determine next version
    result = conn.execute(sa.text(
        "SELECT COALESCE(MAX(version), 0) FROM commission_pct_table"
    )).scalar()
    next_version = (result or 0) + 1

    today = date.today().isoformat()

    for segment, ach_min, ach_max, pct in MATRIX:
        conn.execute(sa.text("""
            INSERT INTO commission_pct_table
                (id, version, segment, achievement_min, achievement_max,
                 commission_pct, valid_from, valid_until, created_by)
            VALUES
                (:id, :version, :segment, :ach_min, :ach_max, :pct, :valid_from, NULL, NULL)
        """), {
            "id": str(uuid.uuid4()),
            "version": next_version,
            "segment": segment,
            "ach_min": ach_min,
            "ach_max": ach_max,
            "pct": pct,
            "valid_from": today,
        })


def downgrade():
    # Best-effort: remove the version we added (only if it's the latest)
    conn = op.get_bind()
    max_version = conn.execute(sa.text(
        "SELECT MAX(version) FROM commission_pct_table"
    )).scalar()
    if max_version:
        conn.execute(sa.text(
            "DELETE FROM commission_pct_table WHERE version = :v"
        ), {"v": max_version})

"""Create ev_signoffs

Conferência do RevOps por EV na apuração mensal: status + fingerprint,
para o recálculo invalidar só os EVs cujos valores realmente mudaram.

Revision ID: a7c3e5f1b2d4
Revises: e1f2a3b4c5d6
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa
from app.models.compat import GUID


revision = "a7c3e5f1b2d4"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ev_signoffs",
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("appraisal_id", GUID(length=36), nullable=False),
        sa.Column("ev_id", GUID(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "DONE", name="signoff_status"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.Column(
            "values_changed", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("signed_off_by", GUID(length=36), nullable=True),
        sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["appraisal_id"], ["appraisals.id"]),
        sa.ForeignKeyConstraint(["ev_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["signed_off_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "appraisal_id", "ev_id", name="uq_ev_signoff_appraisal_ev",
        ),
    )


def downgrade():
    op.drop_table("ev_signoffs")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE signoff_status")

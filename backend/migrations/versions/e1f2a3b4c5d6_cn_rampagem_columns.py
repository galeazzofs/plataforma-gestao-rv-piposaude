"""CN rampagem columns

Adds the em_rampagem flag (users), cadence metas (cn_monthly_goals) and
cadence realizados + calc_mode + sao bonus (cn_monthly_appraisals) needed
for the rampagem commission mode.

Revision ID: e1f2a3b4c5d6
Revises: c0d1e2f3a4b5
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column(
        "em_rampagem", sa.Boolean(), nullable=False, server_default=sa.false()))

    for col in ("negocios_cadencia_meta", "emails_meta", "qualis_agendadas_meta"):
        op.add_column("cn_monthly_goals", sa.Column(
            col, sa.Numeric(12, 2), nullable=False, server_default="0"))

    op.add_column("cn_monthly_appraisals", sa.Column(
        "calc_mode", sa.String(32), nullable=False, server_default="NORMAL"))
    for col in ("negocios_cadencia_realizado", "emails_realizado",
                "qualis_agendadas_realizado", "bonus_sao_amount"):
        op.add_column("cn_monthly_appraisals", sa.Column(
            col, sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("cn_monthly_appraisals", sa.Column(
        "sao_fora_da_meta", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    for col in ("negocios_cadencia_realizado", "emails_realizado",
                "qualis_agendadas_realizado", "bonus_sao_amount",
                "sao_fora_da_meta", "calc_mode"):
        op.drop_column("cn_monthly_appraisals", col)
    for col in ("negocios_cadencia_meta", "emails_meta", "qualis_agendadas_meta"):
        op.drop_column("cn_monthly_goals", col)
    op.drop_column("users", "em_rampagem")

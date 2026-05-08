"""rename GERENTE role to LIDER_VENDAS

Renomeação pura de nomenclatura (issue #29):
  - users.role: 'GERENTE' -> 'LIDER_VENDAS'
  - gerente_quarter_appraisals -> lider_vendas_quarter_appraisals
  - column gerente_id -> lider_vendas_id
  - constraint uq_gerente_quarter_appraisal -> uq_lider_vendas_quarter_appraisal
  - PK/FK constraint names mirror the new table/column on Postgres

Revision ID: 4ac16b631856
Revises: d4e5f6a7b8c9
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa


revision = '4ac16b631856'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1. Rename the role value. On Postgres the ENUM rename also updates all
    #    existing rows in place; on SQLite roles are plain VARCHARs.
    if dialect == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE user_role RENAME VALUE 'GERENTE' TO 'LIDER_VENDAS'")
    else:
        op.execute("UPDATE users SET role = 'LIDER_VENDAS' WHERE role = 'GERENTE'")

    # 2. Rename column + unique constraint inside the appraisals table
    with op.batch_alter_table('gerente_quarter_appraisals', schema=None) as batch_op:
        batch_op.alter_column('gerente_id', new_column_name='lider_vendas_id')
        batch_op.drop_constraint('uq_gerente_quarter_appraisal', type_='unique')
        batch_op.create_unique_constraint(
            'uq_lider_vendas_quarter_appraisal',
            ['lider_vendas_id', 'quarter', 'year'],
        )

    # 3. Rename the table itself
    op.rename_table('gerente_quarter_appraisals', 'lider_vendas_quarter_appraisals')

    # 4. Rename PK and FK constraints on Postgres so their names match the
    #    new table/column. SQLite auto-generates these on create_all so it
    #    doesn't carry the old names forward.
    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE lider_vendas_quarter_appraisals "
            "RENAME CONSTRAINT gerente_quarter_appraisals_pkey "
            "TO lider_vendas_quarter_appraisals_pkey"
        )
        op.execute(
            "ALTER TABLE lider_vendas_quarter_appraisals "
            "RENAME CONSTRAINT gerente_quarter_appraisals_gerente_id_fkey "
            "TO lider_vendas_quarter_appraisals_lider_vendas_id_fkey"
        )


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE lider_vendas_quarter_appraisals "
            "RENAME CONSTRAINT lider_vendas_quarter_appraisals_lider_vendas_id_fkey "
            "TO gerente_quarter_appraisals_gerente_id_fkey"
        )
        op.execute(
            "ALTER TABLE lider_vendas_quarter_appraisals "
            "RENAME CONSTRAINT lider_vendas_quarter_appraisals_pkey "
            "TO gerente_quarter_appraisals_pkey"
        )

    op.rename_table('lider_vendas_quarter_appraisals', 'gerente_quarter_appraisals')

    with op.batch_alter_table('gerente_quarter_appraisals', schema=None) as batch_op:
        batch_op.drop_constraint('uq_lider_vendas_quarter_appraisal', type_='unique')
        batch_op.alter_column('lider_vendas_id', new_column_name='gerente_id')
        batch_op.create_unique_constraint(
            'uq_gerente_quarter_appraisal',
            ['gerente_id', 'quarter', 'year'],
        )

    if dialect == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE user_role RENAME VALUE 'LIDER_VENDAS' TO 'GERENTE'")
    else:
        op.execute("UPDATE users SET role = 'GERENTE' WHERE role = 'LIDER_VENDAS'")

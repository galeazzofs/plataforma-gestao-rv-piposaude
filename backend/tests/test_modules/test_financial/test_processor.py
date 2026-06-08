"""Tests for persist_financial_rows (per-competência month ingestion)."""
import uuid
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    FinancialImport, ImportBatch, Appraisal, AppraisalStatus,
    User, UserRole,
)
from app.modules.financial.processor import persist_financial_rows


@pytest.fixture
def admin_user():
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"proc-admin-{suffix}@x", name="Admin",
        role=UserRole.ADMIN, active=True,
    )
    db.session.add(u)
    db.session.flush()
    db.session.commit()
    yield u
    # Teardown
    FinancialImport.query.delete()
    ImportBatch.query.delete()
    Appraisal.query.delete()
    db.session.delete(u)
    db.session.commit()


def _row(**kw):
    base = {
        'cliente_mae': 'Zup', 'operadora': 'SulAmerica', 'produto': 'Saúde',
        'nf_valor_liquido': 1000.00, 'mes_recebimento': '2026-02',
        'data_recebimento': date(2026, 2, 15), 'tipo_receita': 'Comissão',
        'status_recebimento': 'RECEBIDO',
    }
    base.update(kw)
    return base


def test_persist_tags_month_per_row(admin_user):
    """Each NF is tagged by its own competência month (from mes_recebimento),
    so one upload of a multi-month file populates every month."""
    result = persist_financial_rows(
        [_row(),  # 2026-02
         _row(cliente_mae='Acme', mes_recebimento='2026-05',
              data_recebimento=date(2026, 5, 10))],
        year=2026, filename="t.xlsx", uploaded_by=admin_user.id,
    )
    db.session.commit()

    assert result['persisted'] == 2
    assert FinancialImport.query.filter_by(month=2, year=2026).count() == 1
    assert FinancialImport.query.filter_by(month=5, year=2026).count() == 1
    batch = db.session.get(ImportBatch, result['batch_id'])
    assert batch.nf_count == 2
    assert batch.status == "CONFIRMED"


def test_persist_replaces_only_months_present(admin_user):
    """Re-upload replaces only the months the file carries — others stay."""
    persist_financial_rows([_row()], 2026, "first.xlsx", admin_user.id)  # Feb
    db.session.commit()
    persist_financial_rows(
        [_row(data_recebimento=date(2026, 5, 1), mes_recebimento='2026-05')],
        2026, "second.xlsx", admin_user.id,  # May only
    )
    db.session.commit()

    # May upload did NOT wipe Feb — both coexist.
    assert FinancialImport.query.filter_by(month=2, year=2026).count() == 1
    assert FinancialImport.query.filter_by(month=5, year=2026).count() == 1

    # Re-uploading Feb replaces only Feb (May untouched); old Feb batch SUPERSEDED.
    persist_financial_rows(
        [_row(cliente_mae='A'), _row(cliente_mae='B')],
        2026, "third.xlsx", admin_user.id,
    )
    db.session.commit()
    assert FinancialImport.query.filter_by(month=2, year=2026).count() == 2
    assert FinancialImport.query.filter_by(month=5, year=2026).count() == 1
    assert ImportBatch.query.filter_by(status='SUPERSEDED').count() == 1


def test_persist_skips_and_preserves_locked_months(admin_user):
    """A LOCKED month's NFs are preserved; the file's rows for it are skipped."""
    persist_financial_rows([_row()], 2026, "first.xlsx", admin_user.id)  # Feb, open
    db.session.commit()
    db.session.add(Appraisal(
        month=2, year=2026, status=AppraisalStatus.LOCKED,
        created_by=admin_user.id,
    ))
    db.session.commit()

    result = persist_financial_rows(
        [_row(cliente_mae='New')], 2026, "second.xlsx", admin_user.id,
    )
    db.session.commit()

    assert result['skipped_locked'] == 1
    assert result['persisted'] == 0
    rows = FinancialImport.query.filter_by(month=2, year=2026).all()
    assert len(rows) == 1
    assert rows[0].cliente_mae == 'Zup'  # original preserved, not overwritten

"""Tests for persist_financial_rows."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    FinancialImport, ImportBatch, Appraisal, AppraisalStatus,
    User, UserRole,
)
from app.modules.financial.processor import (
    persist_financial_rows, UploadBlockedError,
)


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


def test_persist_creates_rows(admin_user):
    batch_id = persist_financial_rows(
        [_row(), _row(cliente_mae='Acme')],
        quarter=1, year=2026, filename="t.xlsx", uploaded_by=admin_user.id,
    )
    db.session.commit()

    assert FinancialImport.query.filter_by(quarter=1, year=2026).count() == 2
    batch = db.session.get(ImportBatch, batch_id)
    assert batch.nf_count == 2
    assert batch.status == "CONFIRMED"


def test_persist_replaces_existing_for_same_period(admin_user):
    persist_financial_rows([_row()], 1, 2026, "first.xlsx", admin_user.id)
    db.session.commit()
    persist_financial_rows(
        [_row(), _row(cliente_mae='X')], 1, 2026, "second.xlsx", admin_user.id,
    )
    db.session.commit()

    # Only the second batch's rows remain
    assert FinancialImport.query.filter_by(quarter=1, year=2026).count() == 2
    # Old batch is marked SUPERSEDED
    superseded = ImportBatch.query.filter_by(status='SUPERSEDED').count()
    assert superseded == 1


def test_persist_blocks_when_appraisal_locked(admin_user):
    appraisal = Appraisal(
        quarter=1, year=2026, status=AppraisalStatus.LOCKED,
        created_by=admin_user.id,
    )
    db.session.add(appraisal)
    db.session.commit()

    with pytest.raises(UploadBlockedError):
        persist_financial_rows([_row()], 1, 2026, "t.xlsx", admin_user.id)

    assert FinancialImport.query.count() == 0


def test_persist_does_not_touch_other_periods(admin_user):
    persist_financial_rows([_row()], 1, 2026, "q1.xlsx", admin_user.id)
    db.session.commit()
    persist_financial_rows(
        [_row(data_recebimento=date(2026, 5, 1), mes_recebimento='2026-05')],
        2, 2026, "q2.xlsx", admin_user.id,
    )
    db.session.commit()

    assert FinancialImport.query.filter_by(quarter=1, year=2026).count() == 1
    assert FinancialImport.query.filter_by(quarter=2, year=2026).count() == 1

"""Tests for shared policy clock helpers."""
from datetime import date
from decimal import Decimal
import uuid

from app.extensions import db
from app.models import (
    Appraisal,
    AppraisalStatus,
    BenefitType,
    Client,
    FinancialImport,
    ImportBatch,
    Policy,
    Segment,
    User,
    UserRole,
)
from app.modules.financial.policy_clock import positive_locked_comissao_month_counts


def test_counts_only_positive_locked_comissao_months(db_session):
    suffix = uuid.uuid4().hex[:8]
    year = 2300 + int(suffix[:2], 16)
    admin = User(
        email=f"clock-admin-{suffix}@x",
        name="Clock Admin",
        role=UserRole.ADMIN,
        active=True,
    )
    ev = User(
        email=f"clock-ev-{suffix}@x",
        name="Clock EV",
        role=UserRole.EV,
        active=True,
    )
    db.session.add_all([admin, ev])
    db.session.flush()

    client = Client(
        name=f"Clock Client {suffix}",
        name_normalized=f"clock-client-{suffix}",
    )
    policy = Policy(
        hubspot_ticket_id=f"CLOCK-{suffix}",
        numero_apolice=f"AP-CLOCK-{suffix}",
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
    )
    batch = ImportBatch(
        filename=f"clock-{suffix}.xlsx",
        uploaded_by=admin.id,
        status="CONFIRMED",
    )
    db.session.add_all([client, policy, batch])
    db.session.flush()

    for month in (1, 2, 3, 4):
        db.session.add(Appraisal(
            month=month,
            year=year,
            status=AppraisalStatus.LOCKED,
            created_by=admin.id,
        ))

    def add_nf(month, amount, revenue_type):
        db.session.add(FinancialImport(
            import_batch_id=batch.id,
            policy_id=policy.id,
            month=month,
            year=year,
            nf_mes_recebimento=f"{year}-{month:02d}",
            nf_valor_liquido=Decimal(str(amount)),
            tipo_receita=revenue_type,
            status_recebimento="RECEBIDO",
            data_recebimento=date(year, month, 15),
            match_status="MATCHED",
        ))

    add_nf(1, "100.00", "Comissao")
    add_nf(1, "-40.00", "Comissao")
    add_nf(2, "100.00", "Comissao")
    add_nf(2, "-150.00", "Comissao")
    add_nf(3, "200.00", "Agenciamento")
    add_nf(4, "80.00", "Comissao")
    db.session.flush()

    assert positive_locked_comissao_month_counts({policy.id})[policy.id] == 2
    assert (
        positive_locked_comissao_month_counts({policy.id}, before=(3, year))[policy.id]
        == 1
    )

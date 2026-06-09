"""Finance dashboard API contract tests."""
from datetime import date
from decimal import Decimal
import uuid

import pytest

from app.auth.jwt_manager import create_access_token
from app.extensions import db
from app.models import (
    Appraisal,
    AppraisalStatus,
    BenefitType,
    Client,
    Commission,
    CommissionPctTable,
    CommissionStatus,
    EvQuarterAchievement,
    FinancialImport,
    ImportBatch,
    Policy,
    Segment,
    User,
    UserRole,
)


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _admin():
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"finance-dashboard-admin-{suffix}@x",
        name="Finance Admin",
        role=UserRole.ADMIN,
        active=True,
    )
    db.session.add(u)
    db.session.flush()
    return u


def _batch(admin):
    b = ImportBatch(filename="finance-dashboard.xlsx", uploaded_by=admin.id)
    db.session.add(b)
    db.session.flush()
    return b


def _financial_row(
    batch, amount, mes_recebimento, year, tipo="Comissao", policy_id=None
):
    # FinancialImport is keyed by financial month now; derive it from the
    # YYYY-MM receipt month so the dashboard's quarter selector (which maps a
    # quarter to its three months) scopes rows correctly.
    month = int(mes_recebimento.split("-")[1])
    row = FinancialImport(
        import_batch_id=batch.id,
        policy_id=policy_id,
        nf_valor_liquido=Decimal(str(amount)),
        nf_mes_recebimento=mes_recebimento,
        month=month,
        year=year,
        tipo_receita=tipo,
        match_status="MATCHED",
    )
    db.session.add(row)
    db.session.flush()
    return row


def _seed_m_pct_table():
    for mn, mx, pct in [
        ("0.0000", "0.4999", "0.05"),
        ("0.5000", "0.9999", "0.06"),
        ("1.0000", "99.9999", "0.08"),
    ]:
        db.session.add(CommissionPctTable(
            version=1,
            segment="M",
            achievement_min=Decimal(mn),
            achievement_max=Decimal(mx),
            commission_pct=Decimal(pct),
            valid_from=date.today(),
        ))
    db.session.flush()


class FrozenDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 1, 1)


@pytest.fixture
def frozen_finance_today(monkeypatch):
    from app.api.v1 import finance_dashboard

    monkeypatch.setattr(finance_dashboard, "date", FrozenDate)


def _projected_policy(ev, client_obj, closed, first_payment, ticket=None):
    db.session.add(EvQuarterAchievement(
        ev_id=ev.id,
        quarter=((closed.month - 1) // 3) + 1,
        year=closed.year,
        achievement_pct=Decimal("0.75"),
    ))
    policy = Policy(
        hubspot_ticket_id=ticket or f"FD-{uuid.uuid4().hex[:8]}",
        ev_id=ev.id,
        client_id=client_obj.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("1000.00"),
        closed_date=closed,
        first_payment_real=first_payment,
        installments_paid=0,
        initial_installments_paid=0,
    )
    db.session.add(policy)
    db.session.flush()
    return policy


def _ev_and_client():
    ev = User(
        email=f"finance-dashboard-ev-{uuid.uuid4().hex[:8]}@x",
        name="EV",
        role=UserRole.EV,
        active=True,
    )
    client_name = f"Client {uuid.uuid4().hex[:8]}"
    client_obj = Client(name=client_name, name_normalized=client_name.lower())
    db.session.add_all([ev, client_obj])
    db.session.flush()
    return ev, client_obj


def test_dashboard_period_filter_scopes_paid_totals_and_monthly_series(client, db_session):
    admin = _admin()
    batch = _batch(admin)
    _financial_row(batch, "100.00", "2026-01", 2026, "Comissao")
    _financial_row(batch, "250.00", "2026-04", 2026, "Comissao")

    resp = client.get(
        "/api/v1/finance/dashboard?year=2026&quarter=1",
        headers=_auth_header(admin),
    )

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["comissao_paga"] == "100.00"
    assert data["comissao_agenciamento"]["comissao"] == "100.00"
    assert data["comissao_agenciamento"]["agenciamento"] == "0"
    assert data["comissao_agenciamento"]["series"] == [
        {"label": "jan/26", "comissao": "100.00", "agenciamento": "0"}
    ]


def test_finance_approval_returns_appraisal_id_and_commission_summary(
    client, db_session
):
    period_year = 2080 + int(uuid.uuid4().hex[:2], 16)
    admin = _admin()
    ev, client_obj = _ev_and_client()
    policy = Policy(
        hubspot_ticket_id=f"FIN-APPROVAL-{uuid.uuid4().hex[:8]}",
        ev_id=ev.id,
        client_id=client_obj.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("1000.00"),
        closed_date=date(2026, 1, 1),
    )
    db.session.add(policy)
    db.session.flush()

    appraisal = Appraisal(
        month=8,
        year=period_year,
        status=AppraisalStatus.REVOPS_REVIEW,
        created_by=admin.id,
    )
    commission = Commission(
        policy_id=policy.id,
        ev_id=ev.id,
        month=8,
        year=period_year,
        segment="M",
        achievement_pct=Decimal("0.75"),
        commission_pct=Decimal("0.06"),
        total_actual=Decimal("60.00"),
    )
    db.session.add_all([appraisal, commission])
    db.session.flush()

    resp = client.get("/api/v1/finance/approval", headers=_auth_header(admin))

    assert resp.status_code == 200
    items = resp.get_json()["data"]["items"]
    item = next(i for i in items if i["appraisal_id"] == str(appraisal.id))
    assert item["appraisal_id"] == str(appraisal.id)
    assert item["commission_total"] == "60.00"
    assert item["policies_count"] == 1
    assert item["ev_name"] == ev.name
    assert item["achievement_pct"] == "75.00"


def test_dashboard_year_filter_uses_payment_calendar_not_gongo_year(
    client, db_session, frozen_finance_today
):
    _seed_m_pct_table()
    admin = _admin()
    ev, client_obj = _ev_and_client()
    _projected_policy(
        ev,
        client_obj,
        closed=date(2025, 11, 15),
        first_payment=date(2026, 1, 1),
    )

    resp = client.get(
        "/api/v1/finance/dashboard?year=2026",
        headers=_auth_header(admin),
    )

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["comissao_potencial"] == "720.00"
    assert data["saldo_devedor_total"] == "720.00"
    assert data["fluxo_caixa"]["period_summary"]["projetado"] == "720.00"
    assert data["fluxo_caixa"]["period_summary"]["apolices"] == 1


def test_dashboard_projection_splits_policy_potential_across_future_years(
    client, db_session, frozen_finance_today
):
    _seed_m_pct_table()
    admin = _admin()
    ev, client_obj = _ev_and_client()
    _projected_policy(
        ev,
        client_obj,
        closed=date(2026, 9, 15),
        first_payment=date(2026, 10, 1),
    )

    resp_2026 = client.get(
        "/api/v1/finance/dashboard?year=2026",
        headers=_auth_header(admin),
    )
    resp_2027 = client.get(
        "/api/v1/finance/dashboard?year=2027",
        headers=_auth_header(admin),
    )

    assert resp_2026.status_code == 200
    assert resp_2027.status_code == 200
    assert resp_2026.get_json()["data"]["comissao_potencial"] == "180.00"
    assert resp_2027.get_json()["data"]["comissao_potencial"] == "540.00"


def test_dashboard_pending_import_replaces_projected_policy_month(
    client, db_session, frozen_finance_today
):
    _seed_m_pct_table()
    admin = _admin()
    batch = _batch(admin)
    ev, client_obj = _ev_and_client()
    policy = _projected_policy(
        ev,
        client_obj,
        closed=date(2025, 11, 15),
        first_payment=date(2026, 1, 1),
    )
    _financial_row(
        batch,
        "80.00",
        "2026-01",
        2026,
        "Comissao",
        policy_id=policy.id,
    )

    resp = client.get(
        "/api/v1/finance/dashboard?year=2026&quarter=1",
        headers=_auth_header(admin),
    )

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    jan = next(p for p in data["fluxo_caixa"]["series"] if p["ym"] == "2026-01")
    assert jan["a_apurar"] == "80.00"
    assert jan["projetado"] is None
    assert jan["estado"] == "A_APURAR"
    assert data["fluxo_caixa"]["period_summary"]["a_apurar"] == "80.00"
    assert data["fluxo_caixa"]["period_summary"]["projetado"] == "120.00"
    assert data["fluxo_caixa"]["period_summary"]["potencial_a_pagar"] == "200.00"
    assert data["potencial_a_pagar"] == "200.00"
    assert data["comissao_potencial"] == "200.00"
    assert data["saldo_devedor_total"] == "200.00"


def test_dashboard_locked_apuracao_shows_realizado_and_recalibrates_projection(
    client, db_session, frozen_finance_today
):
    _seed_m_pct_table()
    admin = _admin()
    batch = _batch(admin)
    ev, client_obj = _ev_and_client()
    policy = _projected_policy(
        ev,
        client_obj,
        closed=date(2025, 11, 15),
        first_payment=date(2026, 1, 1),
    )
    # The NF is received in 2026-01, so its financial month is 1; lock the
    # month-1 apuração so this row counts as Realizado.
    db.session.add(Appraisal(
        month=1,
        year=2026,
        status=AppraisalStatus.LOCKED,
        created_by=admin.id,
    ))
    _financial_row(
        batch,
        "80.00",
        "2026-01",
        2026,
        "Comissao",
        policy_id=policy.id,
    )
    db.session.flush()

    resp = client.get(
        "/api/v1/finance/dashboard?year=2026&quarter=1",
        headers=_auth_header(admin),
    )

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    jan = next(p for p in data["fluxo_caixa"]["series"] if p["ym"] == "2026-01")
    assert jan["realizado"] == "80.00"
    assert jan["a_apurar"] is None
    assert jan["projetado"] is None
    assert jan["estado"] == "REALIZADO"
    assert data["fluxo_caixa"]["period_summary"]["realizado"] == "80.00"
    assert data["fluxo_caixa"]["period_summary"]["a_apurar"] == "0"
    assert data["fluxo_caixa"]["period_summary"]["projetado"] == "160.00"
    assert data["potencial_a_pagar"] == "160.00"


def test_dashboard_excludes_settled_policy_from_payable_potential(
    client, db_session, frozen_finance_today
):
    _seed_m_pct_table()
    admin = _admin()
    ev, client_obj = _ev_and_client()
    _projected_policy(
        ev,
        client_obj,
        closed=date(2025, 11, 15),
        first_payment=date(2026, 1, 1),
    )
    settled = Policy(
        hubspot_ticket_id=f"SETTLED-{uuid.uuid4().hex[:8]}",
        ev_id=ev.id,
        client_id=client_obj.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("1000.00"),
        closed_date=date(2025, 11, 15),
        first_payment_real=date(2026, 1, 1),
        installments_paid=12,
        initial_installments_paid=12,
        commission_status=CommissionStatus.SETTLED,
    )
    db.session.add(settled)
    db.session.flush()

    resp = client.get(
        "/api/v1/finance/dashboard?year=2026",
        headers=_auth_header(admin),
    )

    assert resp.status_code == 200
    assert resp.get_json()["data"]["potencial_a_pagar"] == "720.00"


def test_dashboard_available_years_include_policy_closed_years(client, db_session):
    admin = _admin()
    ev = User(
        email=f"finance-dashboard-ev-{uuid.uuid4().hex[:8]}@x",
        name="EV",
        role=UserRole.EV,
        active=True,
    )
    client_name = f"Client {uuid.uuid4().hex[:8]}"
    client_obj = Client(name=client_name, name_normalized=client_name.lower())
    db.session.add_all([ev, client_obj])
    db.session.flush()
    policy = Policy(
        hubspot_ticket_id=f"FD-{uuid.uuid4().hex[:8]}",
        ev_id=ev.id,
        client_id=client_obj.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("1000.00"),
        closed_date=date(2028, 2, 15),
    )
    db.session.add(policy)

    resp = client.get("/api/v1/finance/dashboard", headers=_auth_header(admin))

    assert resp.status_code == 200
    assert 2028 in resp.get_json()["data"]["available_years"]


def test_dashboard_rejects_invalid_quarter_filter(client, db_session):
    admin = _admin()

    resp = client.get(
        "/api/v1/finance/dashboard?year=2026&quarter=5",
        headers=_auth_header(admin),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"

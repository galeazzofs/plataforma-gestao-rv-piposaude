from datetime import date
from decimal import Decimal

from app.models import (
    User, UserRole, Client, Policy, Segment, BenefitType,
    CommissionStatus, CommissionPctTable, EvQuarterAchievement,
)
from app.modules.commissions.projection import (
    compute_ev_balance,
    compute_ev_projection,
)
from app.extensions import db


def _seed_pct_table(session):
    """Seed P segment with 3 tiers. Middle tier (50-99.9%) = 8%."""
    rows = [
        ("P", "0.0000", "0.4999", "0.07"),
        ("P", "0.5000", "0.9999", "0.08"),
        ("P", "1.0000", "9.9999", "0.10"),
    ]
    for seg, amin, amax, pct in rows:
        session.add(CommissionPctTable(
            version=1, segment=seg,
            achievement_min=Decimal(amin),
            achievement_max=Decimal(amax),
            commission_pct=Decimal(pct),
        ))
    session.flush()


def _setup(session):
    ev = User(email="ev@piposaude.com", name="EV Test", role=UserRole.EV, active=True)
    session.add(ev)
    session.flush()

    client = Client(name="TestCo", name_normalized="testco", ev_id=ev.id)
    session.add(client)
    session.flush()

    _seed_pct_table(session)
    return ev, client


class TestComputeEvBalance:
    """Projecao: comissao usa atingimento real do trimestre do gongo;
    cai para o piso (0% = 7%) quando nao ha atingimento cadastrado."""

    def test_balance_uses_real_achievement_when_available(self, db_session):
        ev, client = _setup(db_session)

        # 100%+ achievement -> 10% tier
        db_session.add(EvQuarterAchievement(
            ev_id=ev.id, quarter=1, year=2026,
            total_mrr=Decimal("60000"), mrr_target=Decimal("50000"),
            achievement_pct=Decimal("1.2000"),
        ))
        db_session.add(Policy(
            hubspot_apolice_id="A-1", hubspot_ticket_id="T-1", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("10000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.PROJECTED,
            installments_paid=0,
        ))
        db_session.flush()

        balance = compute_ev_balance(ev.id)

        # 10000 x 0.10 (top tier) x 12 remaining = 12000
        assert balance == Decimal("12000.00")

    def test_balance_fallback_lowest_tier_when_no_achievement(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_apolice_id="A-1b", hubspot_ticket_id="T-1b", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("10000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.PROJECTED,
            installments_paid=0,
        ))
        db_session.flush()

        balance = compute_ev_balance(ev.id)

        # no achievement on file -> fallback 0% -> 7% tier
        # 10000 x 0.07 x 12 = 8400
        assert balance == Decimal("8400.00")

    def test_balance_reduces_with_installments_paid(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_apolice_id="A-2", hubspot_ticket_id="T-2", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("10000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.IN_PAYMENT,
            installments_paid=4,
            first_payment_real=date(2026, 1, 1),
        ))
        db_session.flush()

        balance = compute_ev_balance(ev.id)

        # 10000 x 0.07 x (12-4) = 700 x 8 = 5600
        assert balance == Decimal("5600.00")

    def test_settled_policy_excluded(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_apolice_id="A-3", hubspot_ticket_id="T-3", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("10000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.SETTLED,
            installments_paid=12,
        ))
        db_session.flush()

        balance = compute_ev_balance(ev.id)
        assert balance == Decimal("0")

    def test_uses_mrr_for_commission_cascade(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_apolice_id="A-4", hubspot_ticket_id="T-4", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("10000"),
            mrr_post_deploy=Decimal("8000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.PROJECTED,
            installments_paid=0,
        ))
        db_session.flush()

        balance = compute_ev_balance(ev.id)

        # mrr_for_commission = mrr_post_deploy = 8000
        # 8000 x 0.07 x 12 = 6720
        assert balance == Decimal("6720.00")


class TestComputeEvProjection:
    """Spec S7 -- Projecao mensal, 12 meses."""

    def test_projection_distributes_across_months(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_apolice_id="A-5", hubspot_ticket_id="T-5", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("10000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.IN_PAYMENT,
            installments_paid=6,
            first_payment_real=date(2026, 1, 1),
        ))
        db_session.flush()

        months = compute_ev_projection(
            ev.id,
            ref_date=date(2026, 4, 1),
            period_start=date(2026, 4, 1),
            period_months=9,
        )

        assert len(months) == 9
        # no achievement on file -> fallback 0% -> 7%
        # 6 remaining installments of R$ 700 (10000 x 0.07), starting
        # after the 6 already-paid months.
        non_zero = [m for m in months if m["projected"] > Decimal("0")]
        assert len(non_zero) == 6
        assert non_zero[0]["month"] == "2026-07"
        assert non_zero[-1]["month"] == "2026-12"
        assert all(m["projected"] == Decimal("700.00") for m in non_zero)

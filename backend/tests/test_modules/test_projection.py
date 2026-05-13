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
    cai para faixa media (50-99.9% = 8%) quando nao ha atingimento cadastrado."""

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

    def test_balance_fallback_middle_tier_when_no_achievement(self, db_session):
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

        # no achievement on file -> fallback 50% floor -> 8% tier
        # 10000 x 0.08 x 12 = 9600
        assert balance == Decimal("9600.00")

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

        # 10000 x 0.08 x (12-4) = 800 x 8 = 6400
        assert balance == Decimal("6400.00")

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
        # 8000 x 0.08 x 12 = 7680
        assert balance == Decimal("7680.00")


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

        months = compute_ev_projection(ev.id, ref_date=date(2026, 4, 1))

        assert len(months) == 12
        # no achievement on file -> fallback 50% floor -> 8%
        # 6 remaining installments of R$ 800 (10000 x 0.08)
        non_zero = [m for m in months if m["projected"] > Decimal("0")]
        assert len(non_zero) == 6
        assert all(m["projected"] == Decimal("800.00") for m in non_zero)

    def test_projection_schedules_remaining_months_after_paid_installments(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_apolice_id="A-6", hubspot_ticket_id="T-6", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("1000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.IN_PAYMENT,
            installments_paid=10,
            first_payment_real=date(2026, 1, 1),
        ))
        db_session.flush()

        q3 = compute_ev_projection(
            ev.id,
            period_start=date(2026, 7, 1),
            period_months=3,
        )
        q4 = compute_ev_projection(
            ev.id,
            period_start=date(2026, 10, 1),
            period_months=3,
        )

        assert [m["projected"] for m in q3] == [
            Decimal("0.00"), Decimal("0.00"), Decimal("0.00"),
        ]
        assert q4 == [
            {"month": "2026-10", "projected": Decimal("0.00")},
            {"month": "2026-11", "projected": Decimal("80.00")},
            {"month": "2026-12", "projected": Decimal("80.00")},
        ]

    def test_projection_uses_paid_commission_when_installment_count_is_missing(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_apolice_id="A-7", hubspot_ticket_id="T-7", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("1000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.IN_PAYMENT,
            installments_paid=0,
            first_payment_real=date(2026, 1, 1),
            total_paid_comissao=Decimal("240.00"),
        ))
        db_session.flush()

        months = compute_ev_projection(
            ev.id,
            period_start=date(2026, 1, 1),
            period_months=6,
        )

        assert months == [
            {"month": "2026-01", "projected": Decimal("0.00")},
            {"month": "2026-02", "projected": Decimal("0.00")},
            {"month": "2026-03", "projected": Decimal("0.00")},
            {"month": "2026-04", "projected": Decimal("80.00")},
            {"month": "2026-05", "projected": Decimal("80.00")},
            {"month": "2026-06", "projected": Decimal("80.00")},
        ]

    def test_projection_uses_paid_agenciamento_to_reduce_ev_open_balance(self, db_session):
        ev, client = _setup(db_session)

        db_session.add(Policy(
            hubspot_apolice_id="A-8", hubspot_ticket_id="T-8", ev_id=ev.id, client_id=client.id,
            segment=Segment.P, benefit_type=BenefitType.SAUDE,
            mrr_projected=Decimal("1000"),
            closed_date=date(2026, 1, 15),
            commission_status=CommissionStatus.IN_PAYMENT,
            installments_paid=0,
            first_payment_real=date(2026, 1, 1),
            total_paid_agenciamento=Decimal("240.00"),
        ))
        db_session.flush()

        months = compute_ev_projection(
            ev.id,
            period_start=date(2026, 1, 1),
            period_months=3,
        )

        assert [m["projected"] for m in months] == [
            Decimal("0.00"), Decimal("0.00"), Decimal("0.00"),
        ]

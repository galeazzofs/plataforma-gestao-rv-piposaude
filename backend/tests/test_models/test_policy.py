from decimal import Decimal
from datetime import date
from app.extensions import db
from app.models import (
    Policy, CommissionStatus, User, UserRole, Segment,
    EvQuarterAchievement, CommissionPctTable,
)


def test_mrr_for_commission_prefers_actual(db_session):
    """MRR cascade: actual > post_deploy > projected."""
    policy = Policy(
        hubspot_apolice_id="A-TEST-1",
        hubspot_ticket_id="TEST-1",
        ev_id=None,
        client_id=None,
        mrr_projected=Decimal("1000"),
        mrr_post_deploy=Decimal("1200"),
        mrr_actual=Decimal("1100"),
    )
    assert policy.mrr_for_commission == Decimal("1100")


def test_mrr_for_commission_falls_back_to_post_deploy(db_session):
    policy = Policy(
        hubspot_apolice_id="A-TEST-2",
        hubspot_ticket_id="TEST-2",
        ev_id=None,
        client_id=None,
        mrr_projected=Decimal("1000"),
        mrr_post_deploy=Decimal("1200"),
        mrr_actual=None,
    )
    assert policy.mrr_for_commission == Decimal("1200")


def test_mrr_for_commission_falls_back_to_projected(db_session):
    policy = Policy(
        hubspot_apolice_id="A-TEST-3",
        hubspot_ticket_id="TEST-3",
        ev_id=None,
        client_id=None,
        mrr_projected=Decimal("1000"),
        mrr_post_deploy=None,
        mrr_actual=None,
    )
    assert policy.mrr_for_commission == Decimal("1000")


def test_commission_paid_total_prefers_explicit_policy_paid_totals(db_session):
    policy = Policy(
        hubspot_apolice_id="A-PAID-1",
        hubspot_ticket_id="PAID-1",
        total_paid_comissao=Decimal("100.00"),
        total_paid_agenciamento=Decimal("25.00"),
        commission_paid_legacy=Decimal("10.00"),
    )

    assert policy.commission_paid_total == Decimal("135.00")


def test_quarter_closed_from_date(db_session):
    policy = Policy(
        hubspot_apolice_id="A-TEST-4",
        hubspot_ticket_id="TEST-4",
        ev_id=None,
        client_id=None,
        closed_date=date(2026, 2, 15),
    )
    q, y = policy.quarter_closed
    assert q == 1
    assert y == 2026


# ── commission_potential ─────────────────────────────────────


def _seed_pct_table_full():
    """Seed M-segment tiers used across potential tests."""
    for seg, mn, mx, pct in [
        ('M', '0.0000', '0.4999', '0.05'),
        ('M', '0.5000', '0.9999', '0.06'),
        ('M', '1.0000', '99.9999', '0.08'),
    ]:
        db.session.add(CommissionPctTable(
            version=1, segment=seg,
            achievement_min=Decimal(mn), achievement_max=Decimal(mx),
            commission_pct=Decimal(pct), valid_from=date.today(),
        ))
    db.session.flush()


def test_commission_potential_uses_ev_achievement_in_gongo_quarter(db_session):
    """commission_pct comes from CommissionPctTable.lookup(segment, achievement),
    where achievement is the EV's EvQuarterAchievement for the policy's gongo
    (closed_date) quarter. Final value is MRR × 12 × pct."""
    _seed_pct_table_full()
    ev = User(email="pot@x", name="Pot EV", role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()

    # 75% achievement → M tier 50-99.9% → 0.06 (6%)
    db.session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=4, year=2025, achievement_pct=Decimal("0.75"),
    ))
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="A-POT-1",
        hubspot_ticket_id="POT-1",
        ev_id=ev.id,
        segment=Segment.M,
        mrr_projected=Decimal("1000"),
        closed_date=date(2025, 11, 15),  # Q4/2025
    )
    db.session.add(policy)
    db.session.flush()

    # MRR 1000 × 12 × 0.06 = 720.00
    assert policy.commission_potential == Decimal("720.00")


def test_commission_potential_uses_lowest_tier_when_no_achievement(db_session):
    """No EvQuarterAchievement on file → mirror calculator behaviour and
    treat achievement as 0 (lowest tier)."""
    _seed_pct_table_full()
    ev = User(email="pot2@x", name="Pot EV2", role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="A-POT-2",
        hubspot_ticket_id="POT-2",
        ev_id=ev.id,
        segment=Segment.M,
        mrr_projected=Decimal("1000"),
        closed_date=date(2025, 11, 15),
    )
    db.session.add(policy)
    db.session.flush()

    # Achievement absent → 0 → M tier <50% → 0.05 (5%)
    # MRR 1000 × 12 × 0.05 = 600.00
    assert policy.commission_potential == Decimal("600.00")


def test_commission_potential_returns_none_when_segment_missing(db_session):
    _seed_pct_table_full()
    ev = User(email="pot3@x", name="Pot EV3", role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="A-POT-3",
        hubspot_ticket_id="POT-3",
        ev_id=ev.id,
        segment=None,
        mrr_projected=Decimal("1000"),
        closed_date=date(2025, 11, 15),
    )
    db.session.add(policy)
    db.session.flush()

    assert policy.commission_potential is None


def test_commission_potential_returns_none_when_mrr_missing(db_session):
    _seed_pct_table_full()
    ev = User(email="pot4@x", name="Pot EV4", role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="A-POT-4",
        hubspot_ticket_id="POT-4",
        ev_id=ev.id,
        segment=Segment.M,
        mrr_projected=None,
        mrr_post_deploy=None,
        mrr_actual=None,
        closed_date=date(2025, 11, 15),
    )
    db.session.add(policy)
    db.session.flush()

    assert policy.commission_potential is None


def test_commission_potential_returns_none_when_ev_missing(db_session):
    """Policies without an EV (orphans, pre-sync) can't resolve achievement."""
    _seed_pct_table_full()
    policy = Policy(
        hubspot_apolice_id="A-POT-5",
        hubspot_ticket_id="POT-5",
        ev_id=None,
        segment=Segment.M,
        mrr_projected=Decimal("1000"),
        closed_date=date(2025, 11, 15),
    )
    db.session.add(policy)
    db.session.flush()

    assert policy.commission_potential is None


def test_commission_potential_uses_actual_mrr_when_available(db_session):
    """commission_potential follows the same MRR cascade as
    mrr_for_commission: actual > post_deploy > projected."""
    _seed_pct_table_full()
    ev = User(email="pot6@x", name="Pot EV6", role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()

    db.session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=4, year=2025, achievement_pct=Decimal("0.75"),
    ))
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="A-POT-6",
        hubspot_ticket_id="POT-6",
        ev_id=ev.id,
        segment=Segment.M,
        mrr_projected=Decimal("1000"),
        mrr_post_deploy=Decimal("1500"),
        mrr_actual=Decimal("2000"),
        closed_date=date(2025, 11, 15),
    )
    db.session.add(policy)
    db.session.flush()

    # mrr_actual wins: 2000 × 12 × 0.06 = 1440.00
    assert policy.commission_potential == Decimal("1440.00")

from decimal import Decimal
from datetime import date
from app.models import Policy, CommissionStatus


def test_mrr_for_commission_prefers_actual(db_session):
    """MRR cascade: actual > post_deploy > projected."""
    policy = Policy(
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
        hubspot_ticket_id="TEST-3",
        ev_id=None,
        client_id=None,
        mrr_projected=Decimal("1000"),
        mrr_post_deploy=None,
        mrr_actual=None,
    )
    assert policy.mrr_for_commission == Decimal("1000")


def test_quarter_closed_from_date(db_session):
    policy = Policy(
        hubspot_ticket_id="TEST-4",
        ev_id=None,
        client_id=None,
        closed_date=date(2026, 2, 15),
    )
    q, y = policy.quarter_closed
    assert q == 1
    assert y == 2026

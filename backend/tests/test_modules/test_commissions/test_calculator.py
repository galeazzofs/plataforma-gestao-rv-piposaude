from decimal import Decimal
from datetime import date
from app.modules.commissions.calculator import (
    calculate_projection_for_policy,
    run_quarterly_appraisal,
)
from app.models import (
    User, UserRole, Client, Policy, Goal, Commission,
    CommissionPctTable, Segment, CommissionStatus,
)
from app.extensions import db


def _setup_ev_and_policy(session):
    """Create an EV, client, goal, pct table, and a policy."""
    ev = User(email="ev1@piposaude.com", name="EV 1", role=UserRole.EV)
    session.add(ev)
    session.flush()

    client = Client(name="Acme Corp", name_normalized="acme corp", ev_id=ev.id)
    session.add(client)
    session.flush()

    goal = Goal(ev_id=ev.id, quarter=1, year=2026, mrr_target=Decimal("50000"))
    session.add(goal)

    # Pct table version 1 for P segment
    for amin, amax, pct in [
        ("0.0000", "0.4999", "0.06"),
        ("0.5000", "0.9999", "0.10"),
        ("1.0000", "9.9999", "0.15"),
    ]:
        session.add(CommissionPctTable(
            version=1, segment="P",
            achievement_min=Decimal(amin),
            achievement_max=Decimal(amax),
            commission_pct=Decimal(pct),
        ))

    policy = Policy(
        hubspot_ticket_id="T-100",
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.P,
        mrr_projected=Decimal("10000"),
        closed_date=date(2026, 1, 15),
        commission_status=CommissionStatus.PROJECTED,
    )
    session.add(policy)
    session.flush()

    return ev, client, goal, policy


def test_calculate_projection_uses_medium_faixa(db_session):
    ev, client, goal, policy = _setup_ev_and_policy(db_session)

    commission = calculate_projection_for_policy(policy, quarter=1, year=2026)

    # Projection uses medium faixa (50-99.9%) = 10%
    assert commission.commission_pct == Decimal("0.10")
    # monthly = 10000 * 0.10 = 1000
    assert commission.monthly_estimated == Decimal("1000.00")
    # total = 1000 * 12 = 12000
    assert commission.total_estimated == Decimal("12000.00")
    assert commission.is_final is False


def test_run_quarterly_appraisal_applies_retroactive_pct(db_session):
    ev, client, goal, policy = _setup_ev_and_policy(db_session)

    # Add a second policy for the same EV to total 20k MRR (40% of 50k target)
    policy2 = Policy(
        hubspot_ticket_id="T-101",
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.P,
        mrr_projected=Decimal("10000"),
        closed_date=date(2026, 2, 10),
        commission_status=CommissionStatus.PROJECTED,
    )
    db_session.add(policy2)
    db_session.flush()

    results = run_quarterly_appraisal(quarter=1, year=2026)

    ev_result = results[str(ev.id)]
    # 20k / 50k = 0.4 → faixa baixa (0-49.9%) = 6%
    assert ev_result["achievement_pct"] == Decimal("0.4000")

    # Both policies should have 6% (retroactive)
    c1 = Commission.query.filter_by(policy_id=policy.id, quarter=1, year=2026).first()
    c2 = Commission.query.filter_by(policy_id=policy2.id, quarter=1, year=2026).first()
    assert c1.commission_pct == Decimal("0.06")
    assert c2.commission_pct == Decimal("0.06")
    assert c1.is_final is True
    assert c2.is_final is True

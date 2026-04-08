"""Tests for validate_achievements_for_appraisal.

The validator checks that every (ev_id, gongo_quarter, gongo_year) combination
required by the active-EV policies has a stored achievement record.
"""
import pytest
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, EvQuarterAchievement,
    Segment, BenefitType,
)


def _ev(email):
    u = User(email=email, name=email, role=UserRole.EV, active=True)
    db.session.add(u)
    db.session.flush()
    return u


def _policy(ev, ticket, closed_date, client_name="X"):
    c = Client.find_or_create(client_name)
    db.session.flush()
    p = Policy(
        hubspot_ticket_id=ticket,
        ev_id=ev.id,
        client_id=c.id,
        closed_date=closed_date,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        partner_operator="Op",
    )
    db.session.add(p)
    db.session.flush()
    return p


def _ach(ev, q, y, pct):
    a = EvQuarterAchievement(
        ev_id=ev.id,
        quarter=q,
        year=y,
        achievement_pct=Decimal(str(pct)),
    )
    db.session.add(a)
    db.session.flush()
    return a


def test_validator_passes_when_all_gongo_quarters_have_achievement(db_session):
    from app.modules.commissions.calculator import validate_achievements_for_appraisal

    ev = _ev("e1@x")
    _policy(ev, "T1", date(2026, 1, 15), client_name="C1")
    _policy(ev, "T2", date(2025, 11, 1), client_name="C2")
    _ach(ev, 1, 2026, Decimal("0.75"))
    _ach(ev, 4, 2025, Decimal("0.50"))

    missing = validate_achievements_for_appraisal(1, 2026)
    assert missing == []


def test_validator_returns_missing_for_uncovered_gongo_quarter(db_session):
    from app.modules.commissions.calculator import validate_achievements_for_appraisal

    ev = _ev("e2@x")
    _policy(ev, "T1", date(2026, 1, 15), client_name="C1")
    _policy(ev, "T2", date(2025, 11, 1), client_name="C2")
    _ach(ev, 1, 2026, Decimal("0.75"))
    # Missing achievement for Q4/2025

    missing = validate_achievements_for_appraisal(1, 2026)
    assert len(missing) == 1
    assert "Q4/2025" in missing[0]


def test_validator_ignores_inactive_evs(db_session):
    from app.modules.commissions.calculator import validate_achievements_for_appraisal

    inactive = _ev("inact@x")
    inactive.active = False
    db.session.flush()
    _policy(inactive, "T1", date(2026, 1, 15), client_name="C1")

    # Even without achievement, inactive EV's policies are excluded
    missing = validate_achievements_for_appraisal(1, 2026)
    assert missing == []

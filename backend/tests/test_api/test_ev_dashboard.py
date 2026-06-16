"""EV dashboard period filter API contract tests."""
from datetime import date
from decimal import Decimal
import uuid

from app.auth.jwt_manager import create_access_token
from app.extensions import db
from app.models import (
    BenefitType,
    Client,
    CommissionPctTable,
    Goal,
    Policy,
    Segment,
    User,
    UserRole,
)


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _seed_p_pct_table():
    rows = [
        ("0.0000", "0.4999", "0.07"),
        ("0.5000", "0.9999", "0.08"),
        ("1.0000", "9.9999", "0.10"),
    ]
    for mn, mx, pct in rows:
        db.session.add(CommissionPctTable(
            version=1,
            segment="P",
            achievement_min=Decimal(mn),
            achievement_max=Decimal(mx),
            commission_pct=Decimal(pct),
            valid_from=date.today(),
        ))
    db.session.flush()


def _ev_and_client():
    suffix = uuid.uuid4().hex[:8]
    ev = User(
        email=f"ev-dashboard-{suffix}@piposaude.com",
        name="EV Dashboard",
        role=UserRole.EV,
        active=True,
    )
    client = Client(name=f"Cliente {suffix}", name_normalized=f"cliente {suffix}")
    db.session.add_all([ev, client])
    db.session.flush()
    return ev, client


def _policy(ev, client, mrr, closed, first_payment):
    policy = Policy(
        hubspot_ticket_id=f"EV-DASH-{uuid.uuid4().hex[:8]}",
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.P,
        benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal(str(mrr)),
        closed_date=closed,
        first_payment_real=first_payment,
        installments_paid=0,
        initial_installments_paid=0,
    )
    db.session.add(policy)
    db.session.flush()
    return policy


def test_summary_period_filter_scopes_balance_mrr_and_goal(client, db_session):
    _seed_p_pct_table()
    ev, client_obj = _ev_and_client()
    db.session.add_all([
        Goal(ev_id=ev.id, quarter=1, year=2026, mrr_target=Decimal("10000.00")),
        Goal(ev_id=ev.id, quarter=2, year=2026, mrr_target=Decimal("20000.00")),
    ])
    _policy(ev, client_obj, "1000.00", date(2026, 1, 15), date(2026, 1, 1))
    _policy(ev, client_obj, "2000.00", date(2026, 4, 15), date(2026, 4, 1))

    resp = client.get(
        "/api/v1/commissions/summary?year=2026&quarter=1",
        headers=_auth_header(ev),
    )

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["current_quarter"] == 1
    assert data["current_year"] == 2026
    assert data["balance_estimated"] == "840.00"
    assert data["mrr_sold"] == "1000.00"
    assert data["mrr_target"] == "10000.00"
    assert data["achievement_pct"] == "10.00"
    assert data["available_years"] == [2026]


def test_projection_period_filter_returns_selected_quarter_months(client, db_session):
    _seed_p_pct_table()
    ev, client_obj = _ev_and_client()
    _policy(ev, client_obj, "1000.00", date(2026, 1, 15), date(2026, 1, 1))
    _policy(ev, client_obj, "2000.00", date(2026, 4, 15), date(2026, 4, 1))

    resp = client.get(
        "/api/v1/commissions/projection?year=2026&quarter=1",
        headers=_auth_header(ev),
    )

    assert resp.status_code == 200
    assert resp.get_json()["data"] == [
        {"month": "2026-01", "projected": "70.00"},
        {"month": "2026-02", "projected": "70.00"},
        {"month": "2026-03", "projected": "70.00"},
    ]


def test_summary_rejects_invalid_quarter(client, db_session):
    ev, _ = _ev_and_client()

    resp = client.get(
        "/api/v1/commissions/summary?year=2026&quarter=5",
        headers=_auth_header(ev),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"

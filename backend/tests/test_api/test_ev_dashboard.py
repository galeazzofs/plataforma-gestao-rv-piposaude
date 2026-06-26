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


def test_summary_period_scopes_mrr_and_goal_but_balance_is_whole_book(client, db_session):
    """The quarter selector scopes MRR vendido / goal / achievement only. The
    Saldo a receber covers the EV's whole book regardless of selected quarter
    (CONTEXT.md 'Saldo a receber do EV')."""
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
    # Whole book: 1000*12*0.07 + 2000*12*0.07 = 840 + 1680 = 2520
    assert data["balance_estimated"] == "2520.00"
    # MRR vendido / goal / achievement stay scoped to the selected quarter (Q1).
    assert data["mrr_sold"] == "1000.00"
    assert data["mrr_target"] == "10000.00"
    assert data["achievement_pct"] == "10.00"
    assert data["available_years"] == [2026]


def test_summary_year_only_aggregates_the_whole_year(client, db_session):
    """Year selected, no quarter: MRR vendido / meta / atingimento aggregate
    the whole year; saldo stays the whole-book total."""
    _seed_p_pct_table()
    ev, client_obj = _ev_and_client()
    db.session.add_all([
        Goal(ev_id=ev.id, quarter=1, year=2026, mrr_target=Decimal("10000.00")),
        Goal(ev_id=ev.id, quarter=2, year=2026, mrr_target=Decimal("20000.00")),
    ])
    _policy(ev, client_obj, "1000.00", date(2026, 1, 15), date(2026, 1, 1))
    _policy(ev, client_obj, "2000.00", date(2026, 4, 15), date(2026, 4, 1))

    resp = client.get("/api/v1/commissions/summary?year=2026", headers=_auth_header(ev))

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["current_year"] == 2026
    assert data["current_quarter"] is None
    assert data["mrr_sold"] == "3000.00"        # both policies, whole year
    assert data["mrr_target"] == "30000.00"     # sum of the year's goals
    assert data["achievement_pct"] == "10.00"   # 3000 / 30000
    assert data["balance_estimated"] == "2520.00"   # whole book


def test_summary_no_filter_is_all_time_total(client, db_session):
    """No year at all: MRR vendido is all-time, achievement hidden (no all-time
    goal), saldo is the whole-book total."""
    _seed_p_pct_table()
    ev, client_obj = _ev_and_client()
    db.session.add(Goal(ev_id=ev.id, quarter=1, year=2026, mrr_target=Decimal("10000.00")))
    _policy(ev, client_obj, "1000.00", date(2026, 1, 15), date(2026, 1, 1))
    _policy(ev, client_obj, "2000.00", date(2027, 4, 15), date(2027, 4, 1))

    resp = client.get("/api/v1/commissions/summary", headers=_auth_header(ev))

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["current_year"] is None
    assert data["current_quarter"] is None
    assert data["mrr_sold"] == "3000.00"          # all-time, across years
    assert data["achievement_pct"] is None         # hidden
    assert data["balance_estimated"] == "2520.00"   # whole book


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

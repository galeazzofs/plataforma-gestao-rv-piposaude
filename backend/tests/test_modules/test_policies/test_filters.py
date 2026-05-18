from app.extensions import db
from app.models import User, UserRole, Policy, Client


def _make_user(email, role=UserRole.EV, active=True):
    u = User(email=email, name=email, role=role, active=active)
    db.session.add(u)
    db.session.flush()
    return u


def _make_policy(ev, ticket_id, apolice_id=None):
    p = Policy(
        hubspot_apolice_id=apolice_id or f"A-{ticket_id}",
        hubspot_ticket_id=ticket_id,
        ev_id=ev.id,
    )
    db.session.add(p)
    db.session.flush()
    return p


def test_returns_policies_of_commissionable_evs(db_session):
    from app.modules.policies.filters import active_ev_policies_query

    active_ev = _make_user("active@x", role=UserRole.EV, active=True)
    inactive_ev = _make_user("inactive@x", role=UserRole.EV, active=False)
    departed_ev = _make_user("departed@x", role=UserRole.EV, active=False)
    departed_ev.left_company = True
    admin = _make_user("admin@x", role=UserRole.ADMIN, active=True)

    p_active = _make_policy(active_ev, "T1")
    p_departed = _make_policy(departed_ev, "T0")
    _make_policy(inactive_ev, "T2")
    _make_policy(admin, "T3")  # admin is not EV; excluded

    result = active_ev_policies_query().all()
    result_ids = {p.id for p in result}
    assert result_ids == {p_active.id, p_departed.id}


def test_excludes_policies_with_null_ev(db_session):
    from app.modules.policies.filters import active_ev_policies_query

    p = Policy(hubspot_apolice_id="A-NULL", hubspot_ticket_id="T_NULL", ev_id=None)
    db.session.add(p)
    db.session.flush()

    assert active_ev_policies_query().count() == 0

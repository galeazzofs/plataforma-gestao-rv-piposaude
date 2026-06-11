"""Authorization tests for the appraisal detail payload (GET /appraisals/<id>).

The detail serialization (detail=True) carries the full ev_summary — commission
totals, achievement and per-policy subtotals of every EV in the month. That is
RV (salary-equivalent) data: EV/CN must not read it at all, a líder must only
see their own team, and ADMIN/FINANCE keep the full view.
"""
import uuid
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    User, UserRole, Team, Client, Policy, Segment, BenefitType,
    Commission, Appraisal, AppraisalStatus,
)
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def detail_setup():
    """Two EVs with commissions in the 09/2026 apuração: ev_a belongs to
    team A (led by lider_a), ev_b has no team — it doubles as the
    "other team" case for lider_a and as the IS-NULL-bucket regression for
    the teamless líder."""
    suffix = uuid.uuid4().hex[:8]

    team_a = Team(name=f"Time A {suffix}")
    db.session.add(team_a)
    db.session.flush()

    admin = User(email=f"adm-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    finance = User(email=f"fin-{suffix}@x", name="Finance",
                   role=UserRole.FINANCE, active=True)
    lider_a = User(email=f"lid-a-{suffix}@x", name="Lider A",
                   role=UserRole.LIDER_VENDAS, active=True, team_id=team_a.id)
    lider_sem_time = User(email=f"lid-0-{suffix}@x", name="Lider Sem Time",
                          role=UserRole.LIDER_VENDAS, active=True, team_id=None)
    ev_a = User(email=f"ev-a-{suffix}@x", name="EV Alice",
                role=UserRole.EV, active=True, team_id=team_a.id)
    ev_b = User(email=f"ev-b-{suffix}@x", name="EV Bruno",
                role=UserRole.EV, active=True, team_id=None)
    cn = User(email=f"cn-{suffix}@x", name="CN Carla",
              role=UserRole.CN, active=True)
    db.session.add_all([admin, finance, lider_a, lider_sem_time, ev_a, ev_b, cn])
    db.session.flush()

    client_row = Client.find_or_create(f"DetailClient-{suffix}")
    db.session.flush()

    policies = {}
    for key, ev in (("a", ev_a), ("b", ev_b)):
        p = Policy(
            hubspot_apolice_id=f"A-DET-{key}-{suffix}",
            hubspot_ticket_id=f"DET-{key}-{suffix}",
            numero_apolice=f"AP-DET-{key}-{suffix}",
            ev_id=ev.id, client_id=client_row.id,
            segment=Segment.M, benefit_type=BenefitType.SAUDE,
            partner_operator="SulAmerica",
        )
        db.session.add(p)
        policies[key] = p
    db.session.flush()

    appraisal = Appraisal(
        month=9, year=2026, status=AppraisalStatus.REVOPS_REVIEW,
        created_by=admin.id,
    )
    db.session.add(appraisal)
    db.session.add_all([
        Commission(policy_id=policies["a"].id, ev_id=ev_a.id,
                   month=9, year=2026, total_actual=Decimal("100.00")),
        Commission(policy_id=policies["b"].id, ev_id=ev_b.id,
                   month=9, year=2026, total_actual=Decimal("200.00")),
    ])
    db.session.commit()

    return {
        "appraisal": appraisal,
        "admin": admin, "finance": finance,
        "lider_a": lider_a, "lider_sem_time": lider_sem_time,
        "ev_a": ev_a, "ev_b": ev_b, "cn": cn,
    }


def _get_detail(client, setup, user):
    return client.get(
        f"/api/v1/appraisals/{setup['appraisal'].id}",
        headers=_auth_header(setup[user]),
    )


def _summary_ev_ids(payload):
    return {s["ev_id"] for s in payload["data"]["ev_summary"]}


def test_ev_cannot_read_appraisal_detail(client, db_session, detail_setup):
    resp = _get_detail(client, detail_setup, "ev_a")
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "FORBIDDEN"


def test_cn_cannot_read_appraisal_detail(client, db_session, detail_setup):
    resp = _get_detail(client, detail_setup, "cn")
    assert resp.status_code == 403


def test_lider_sees_only_own_team_in_detail(client, db_session, detail_setup):
    resp = _get_detail(client, detail_setup, "lider_a")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert _summary_ev_ids(payload) == {str(detail_setup["ev_a"].id)}
    totals = payload["data"]["totals"]
    assert totals["ev_count"] == 1
    assert totals["total_commission"] == 100.0
    # Company-wide review tabs are not part of a team-scoped view.
    assert payload["data"]["unmatched"] == []
    assert payload["data"]["nao_suportado"] == []
    assert payload["data"]["apolices_finalizadas"] == []
    assert payload["data"]["missing_achievements"] == []


def test_lider_without_team_sees_empty_summary(client, db_session, detail_setup):
    """team_id NULL must scope to nothing — not to the bucket of
    team-less EVs (ev_b would leak through an IS NULL filter)."""
    resp = _get_detail(client, detail_setup, "lider_sem_time")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["data"]["ev_summary"] == []
    assert payload["data"]["totals"]["total_commission"] == 0


def test_admin_and_finance_see_full_detail(client, db_session, detail_setup):
    expected = {str(detail_setup["ev_a"].id), str(detail_setup["ev_b"].id)}
    for user in ("admin", "finance"):
        resp = _get_detail(client, detail_setup, user)
        assert resp.status_code == 200
        assert _summary_ev_ids(resp.get_json()) == expected


def test_list_endpoint_carries_no_detail_payload(client, db_session, detail_setup):
    """The list stays metadata-only for any authenticated role."""
    resp = client.get(
        "/api/v1/appraisals",
        headers=_auth_header(detail_setup["ev_a"]),
    )
    assert resp.status_code == 200
    for item in resp.get_json()["data"]:
        assert "ev_summary" not in item
        assert "totals" not in item


def test_lider_transition_response_is_team_scoped(client, db_session, detail_setup):
    """The transition endpoint returns the same detail payload — a líder
    driving their legitimate edge must not receive other teams' values."""
    appraisal = detail_setup["appraisal"]
    appraisal.status = AppraisalStatus.VALIDATING
    db.session.commit()

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/transition",
        json={"to": "LIDER_REVIEW"},
        headers=_auth_header(detail_setup["lider_a"]),
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert _summary_ev_ids(payload) == {str(detail_setup["ev_a"].id)}

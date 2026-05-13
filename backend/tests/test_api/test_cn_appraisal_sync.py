"""Tests for GET /api/v1/commissions/cn/appraisal/sync — the read-only
HubSpot preview that powers the Sincronizar button on the CN apuração
admin page."""
from decimal import Decimal
from unittest.mock import patch
import uuid

import pytest

from app.extensions import db
from app.auth.jwt_manager import create_access_token
from app.models import User, UserRole, CnNivel, CnPorte


def _auth(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_and_cns():
    suffix = uuid.uuid4().hex[:8]
    admin = User(email=f"sync-admin-{suffix}@x", name="Sync Admin",
                 role=UserRole.ADMIN, active=True)
    ana = User(email=f"ana-{suffix}@piposaude.com", name="Ana CN",
               role=UserRole.CN, active=True,
               nivel=CnNivel.CN1, porte=CnPorte.M,
               salario_base=Decimal("3000"))
    bob = User(email=f"bob-{suffix}@piposaude.com", name="Bob CN",
               role=UserRole.CN, active=True,
               nivel=CnNivel.CN1, porte=CnPorte.M,
               salario_base=Decimal("3000"))
    db.session.add_all([admin, ana, bob])
    db.session.commit()
    yield {"admin": admin, "ana": ana, "bob": bob}
    # Cascade: tests may commit goals/appraisals for these CNs (the API
    # endpoint commits its own transaction), so wipe dependents before the
    # users to avoid FK violations.
    from app.models import CnMonthlyGoal, CnMonthlyAppraisal
    cn_ids = [ana.id, bob.id]
    CnMonthlyAppraisal.query.filter(
        CnMonthlyAppraisal.cn_id.in_(cn_ids)).delete(synchronize_session=False)
    CnMonthlyGoal.query.filter(
        CnMonthlyGoal.cn_id.in_(cn_ids)).delete(synchronize_session=False)
    db.session.delete(admin)
    db.session.delete(ana)
    db.session.delete(bob)
    db.session.commit()


def test_sync_endpoint_returns_all_active_cns(client, admin_and_cns):
    """Every active CN appears in the response, including those with zero
    deals — so admin can spot gaps."""
    with patch(
        "app.api.v1.cn_commissions.fetch_cn_realized_with_meta",
        return_value=(
            {admin_and_cns["ana"].id: {
                "sao_realizado": Decimal("3"),
                "vidas_realizado": Decimal("21"),
            }},
            {"deals_scanned": 3, "unresolved": 0},
        ),
    ):
        resp = client.get(
            "/api/v1/commissions/cn/appraisal/sync?month=4&year=2026",
            headers=_auth(admin_and_cns["admin"]),
        )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["month"] == 4 and data["year"] == 2026

    by_name = {it["cn_name"]: it for it in data["items"]}
    assert by_name["Ana CN"]["sao_realizado"] == "3"
    assert by_name["Ana CN"]["vidas_realizado"] == "21"
    assert by_name["Bob CN"]["sao_realizado"] == "0"
    assert by_name["Bob CN"]["vidas_realizado"] == "0"

    assert data["summary"]["cns_hit"] == 1
    assert data["summary"]["total_sao"] == 3


def test_sync_endpoint_forbidden_for_cn(client, admin_and_cns):
    resp = client.get(
        "/api/v1/commissions/cn/appraisal/sync?month=4&year=2026",
        headers=_auth(admin_and_cns["ana"]),
    )
    assert resp.status_code == 403


def test_sync_endpoint_validates_query_params(client, admin_and_cns):
    resp = client.get(
        "/api/v1/commissions/cn/appraisal/sync",
        headers=_auth(admin_and_cns["admin"]),
    )
    assert resp.status_code == 400


def test_sync_endpoint_handles_hubspot_failure(client, admin_and_cns):
    with patch(
        "app.api.v1.cn_commissions.fetch_cn_realized_with_meta",
        side_effect=RuntimeError("HubSpot down"),
    ):
        resp = client.get(
            "/api/v1/commissions/cn/appraisal/sync?month=4&year=2026",
            headers=_auth(admin_and_cns["admin"]),
        )
    assert resp.status_code == 502
    assert resp.get_json()["error"]["code"] == "HUBSPOT_SYNC_FAILED"


def test_post_appraisal_uses_supplied_inputs_no_implicit_sync(
    client, admin_and_cns
):
    """After splitting sync from run, POST /appraisal should NOT call
    HubSpot — the frontend passes inputs from its sync preview."""
    from app.models import CnMonthlyGoal
    db.session.add(CnMonthlyGoal(
        cn_id=admin_and_cns["ana"].id, month=4, year=2026,
        sao_target=Decimal("10"), vidas_target=Decimal("50"),
    ))
    db.session.add(CnMonthlyGoal(
        cn_id=admin_and_cns["bob"].id, month=4, year=2026,
        sao_target=Decimal("10"), vidas_target=Decimal("50"),
    ))
    db.session.commit()

    with patch("app.api.v1.cn_commissions.fetch_cn_realized_with_meta") as m:
        resp = client.post(
            "/api/v1/commissions/cn/appraisal",
            json={
                "month": 4, "year": 2026,
                "inputs": [
                    {"cn_id": str(admin_and_cns["ana"].id),
                     "sao_realizado": "5",
                     "vidas_realizado": "30"},
                ],
            },
            headers=_auth(admin_and_cns["admin"]),
        )
    assert resp.status_code == 200
    m.assert_not_called()

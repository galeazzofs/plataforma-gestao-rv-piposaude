import uuid

from app.auth.jwt_manager import create_access_token
from app.models import User, UserRole


def _auth(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


def test_cn_simulator_uses_current_cn_profile_and_auto_vidas_meta(client, db_session):
    suffix = uuid.uuid4().hex[:8]
    cn = User(
        email=f"sim-cn-{suffix}@piposaude.com",
        name="Sim CN",
        role=UserRole.CN,
        nivel="CN3",
        porte="G+",
        active=True,
    )
    db_session.add(cn)
    db_session.flush()

    response = client.post(
        "/api/v1/commissions/cn/simulate",
        headers=_auth(cn),
        json={
            "nivel": "CN1",
            "porte": "M",
            "sao_meta": "100",
            "sao_realizado": "100",
            "vidas_realizado": "200000",
        },
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["nivel"] == "CN3"
    assert data["porte"] == "G+"
    assert data["vidas_meta"] == "200000.00"
    assert data["pct_vidas"] == "1.0000"
    assert data["commission_amount"] == "3600.00"


def test_admin_simulator_can_auto_vidas_meta_from_payload_porte(client, db_session):
    suffix = uuid.uuid4().hex[:8]
    admin = User(
        email=f"sim-admin-{suffix}@piposaude.com",
        name="Sim Admin",
        role=UserRole.ADMIN,
        active=True,
    )
    db_session.add(admin)
    db_session.flush()

    response = client.post(
        "/api/v1/commissions/cn/simulate",
        headers=_auth(admin),
        json={
            "nivel": "CN2",
            "porte": "M",
            "sao_meta": "80",
            "sao_realizado": "80",
            "vidas_realizado": "30000",
        },
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["nivel"] == "CN2"
    assert data["porte"] == "M"
    assert data["vidas_meta"] == "30000.00"
    assert data["commission_amount"] == "3000.00"

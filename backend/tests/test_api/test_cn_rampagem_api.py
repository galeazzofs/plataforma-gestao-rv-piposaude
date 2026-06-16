import uuid
from app.auth.jwt_manager import create_access_token
from app.models import User, UserRole


def _auth(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _make_admin(db_session):
    u = User(email=f"admin-{uuid.uuid4().hex[:8]}@piposaude.com",
             name="Admin", role=UserRole.ADMIN, active=True)
    db_session.add(u); db_session.flush()
    return u


def _make_cn(db_session, nivel="CN3", porte="M"):
    u = User(email=f"cn-{uuid.uuid4().hex[:8]}@piposaude.com",
             name="CN", role=UserRole.CN, nivel=nivel, porte=porte, active=True)
    db_session.add(u); db_session.flush()
    return u


def test_upsert_goals_accepts_cadence_metas(client, db_session):
    admin = _make_admin(db_session)
    cn = _make_cn(db_session)
    resp = client.put("/api/v1/commissions/cn/goals", headers=_auth(admin), json={
        "month": 4, "year": 2026,
        "items": [{"cn_id": str(cn.id), "sao_target": "0",
                   "negocios_cadencia_meta": "60", "emails_meta": "400",
                   "qualis_agendadas_meta": "0"}],
    })
    assert resp.status_code == 200
    listing = client.get("/api/v1/commissions/cn/goals?month=4&year=2026",
                         headers=_auth(admin)).get_json()
    row = next(r for r in listing["data"] if r["cn_id"] == str(cn.id))
    assert row["negocios_cadencia_meta"] == "60.00"
    assert row["emails_meta"] == "400.00"
    assert row["em_rampagem"] is False


def test_admin_can_set_em_rampagem(client, db_session):
    admin = _make_admin(db_session)
    cn = _make_cn(db_session, nivel="CN1")
    resp = client.patch(f"/api/v1/admin/users/{cn.id}", headers=_auth(admin),
                        json={"em_rampagem": True})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["em_rampagem"] is True


def test_simulate_rampagem_sem_sao(client, db_session):
    admin = _make_admin(db_session)
    resp = client.post("/api/v1/commissions/cn/simulate", headers=_auth(admin), json={
        "nivel": "CN3", "em_rampagem": True, "sao_meta": "0",
        "negocios_cadencia_meta": "60", "negocios_cadencia_realizado": "103",
        "emails_meta": "400", "emails_realizado": "1133",
        "sao_fora_da_meta": "1",
    })
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["calc_mode"] == "RAMPAGEM_SEM_SAO"
    assert data["commission_amount"] == "3300.00"

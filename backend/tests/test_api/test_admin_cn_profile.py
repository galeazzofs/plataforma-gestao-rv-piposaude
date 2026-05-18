from decimal import Decimal
import uuid

from app.auth.jwt_manager import create_access_token
from app.models import User, UserRole, Team


def _auth(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


def test_admin_user_crud_persists_cn_profile(client, db_session):
    suffix = uuid.uuid4().hex[:8]
    admin = User(
        email=f"admin-cn-profile-{suffix}@piposaude.com",
        name="Admin CN Profile",
        role=UserRole.ADMIN,
        active=True,
    )
    db_session.add(admin)
    db_session.flush()

    response = client.post(
        "/api/v1/admin/users",
        headers=_auth(admin),
        json={
            "email": f"cn-profile-{suffix}@piposaude.com",
            "name": "CN Profile",
            "role": "CN",
            "nivel": "CN2",
            "porte": "G+",
            "salario_base": "8100.50",
        },
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["nivel"] == "CN2"
    assert data["porte"] == "G+"
    assert data["salario_base"] == "8100.50"

    update = client.patch(
        f"/api/v1/admin/users/{data['id']}",
        headers=_auth(admin),
        json={"nivel": "CN3", "porte": "M"},
    )

    assert update.status_code == 200
    updated = update.get_json()["data"]
    assert updated["nivel"] == "CN3"
    assert updated["porte"] == "M"

    created = db_session.get(User, data["id"])
    created.active = False
    admin.active = False
    db_session.commit()


def test_admin_user_crud_persists_left_company_flag(client, db_session):
    suffix = uuid.uuid4().hex[:8]
    admin = User(
        email=f"admin-left-company-{suffix}@piposaude.com",
        name="Admin Left Company",
        role=UserRole.ADMIN,
        active=True,
    )
    db_session.add(admin)
    db_session.flush()

    response = client.post(
        "/api/v1/admin/users",
        headers=_auth(admin),
        json={
            "email": f"departed-ev-{suffix}@piposaude.com",
            "name": "Departed EV",
            "role": "EV",
            "left_company": True,
        },
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["left_company"] is True

    update = client.patch(
        f"/api/v1/admin/users/{data['id']}",
        headers=_auth(admin),
        json={"left_company": False},
    )

    assert update.status_code == 200
    assert update.get_json()["data"]["left_company"] is False

    created = db_session.get(User, data["id"])
    created.active = False
    admin.active = False
    db_session.commit()


def test_delete_user_hides_user_from_default_admin_list(client, db_session):
    suffix = uuid.uuid4().hex[:8]
    admin = User(
        email=f"admin-delete-user-{suffix}@piposaude.com",
        name="Admin Delete User",
        role=UserRole.ADMIN,
        active=True,
    )
    user = User(
        email=f"delete-user-{suffix}@piposaude.com",
        name="Delete User",
        role=UserRole.EV,
        active=True,
    )
    db_session.add_all([admin, user])
    db_session.flush()

    delete_response = client.delete(
        f"/api/v1/admin/users/{user.id}",
        headers=_auth(admin),
    )

    assert delete_response.status_code == 200
    assert delete_response.get_json()["data"]["active"] is False

    list_response = client.get("/api/v1/admin/users", headers=_auth(admin))

    assert list_response.status_code == 200
    ids = {row["id"] for row in list_response.get_json()["data"]}
    assert str(user.id) not in ids

    all_response = client.get("/api/v1/admin/users?active=all", headers=_auth(admin))

    assert all_response.status_code == 200
    all_rows = {row["id"]: row for row in all_response.get_json()["data"]}
    assert all_rows[str(user.id)]["active"] is False

    admin.active = False
    db_session.commit()


def test_team_members_include_cn_profile(client, db_session):
    suffix = uuid.uuid4().hex[:8]
    admin = User(
        email=f"admin-team-cn-{suffix}@piposaude.com",
        name="Admin Team CN",
        role=UserRole.ADMIN,
        active=True,
    )
    team = Team(name=f"Time CN {suffix}")
    db_session.add_all([admin, team])
    db_session.flush()
    cn = User(
        email=f"team-cn-{suffix}@piposaude.com",
        name="Team CN",
        role=UserRole.CN,
        team_id=team.id,
        nivel="CN1",
        porte="M",
        salario_base=Decimal("7000"),
        active=True,
    )
    db_session.add(cn)
    db_session.flush()

    response = client.get("/api/v1/admin/teams", headers=_auth(admin))

    assert response.status_code == 200
    teams = response.get_json()["data"]
    row = next(t for t in teams if t["id"] == str(team.id))
    member = next(m for m in row["members"] if m["id"] == str(cn.id))
    assert member["nivel"] == "CN1"
    assert member["porte"] == "M"
    assert member["salario_base"] in ("7000", "7000.00")

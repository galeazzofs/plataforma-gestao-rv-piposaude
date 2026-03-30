from app.models import User, UserRole
from app.auth.jwt_manager import create_access_token


def test_require_auth_blocks_unauthenticated(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_require_auth_allows_valid_token(client, app, db_session):
    user = User(
        email="test@piposaude.com",
        name="Test User",
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    db_session.flush()

    with app.app_context():
        token = create_access_token(str(user.id), user.role.value)

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json["data"]["email"] == "test@piposaude.com"


def test_require_role_blocks_wrong_role(client, app, db_session):
    user = User(
        email="ev@piposaude.com",
        name="EV User",
        role=UserRole.EV,
    )
    db_session.add(user)
    db_session.flush()

    with app.app_context():
        token = create_access_token(str(user.id), user.role.value)

    response = client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403

import uuid
from app.auth.jwt_manager import create_access_token, create_refresh_token, decode_token


def test_create_and_decode_access_token(app):
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id, "ADMIN")
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["role"] == "ADMIN"
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token(app):
    user_id = str(uuid.uuid4())
    token = create_refresh_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"


def test_expired_token_raises(app):
    import jwt as pyjwt
    from datetime import datetime, timedelta, timezone
    from app.auth.jwt_manager import InvalidTokenError

    user_id = str(uuid.uuid4())
    # Create a token that is already expired (exp in the past)
    payload = {
        "sub": str(user_id),
        "role": "EV",
        "type": "access",
        "iat": datetime(2020, 1, 1, tzinfo=timezone.utc),
        "exp": datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=1),
    }
    token = pyjwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")

    try:
        decode_token(token)
        assert False, "Should have raised InvalidTokenError"
    except InvalidTokenError:
        pass

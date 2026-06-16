from flask import Blueprint, jsonify, g, request
from app.auth.decorators import require_auth
from app.auth.jwt_manager import create_access_token, create_refresh_token, decode_token, InvalidTokenError
from app.models import User
from app.extensions import db

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def _serialize_auth_user(user):
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role.value if user.role else None,
        "team_id": str(user.team_id) if user.team_id else None,
        "active": user.active,
        "nivel": user.nivel.value if hasattr(user.nivel, "value") else user.nivel,
        "porte": user.porte.value if hasattr(user.porte, "value") else user.porte,
        "salario_base": str(user.salario_base) if user.salario_base is not None else None,
    }


@auth_bp.route("/me")
@require_auth
def me():
    user = g.current_user
    return jsonify({"data": _serialize_auth_user(user)})


@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    refresh_token = request.json.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Refresh token required"}}), 400
    try:
        payload = decode_token(refresh_token)
    except InvalidTokenError as e:
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": str(e)}}), 401
    if payload.get("type") != "refresh":
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Invalid token type"}}), 401
    user = db.session.get(User, payload["sub"])
    if user is None or not user.active:
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": "User not found"}}), 401
    if user.refresh_token != refresh_token:
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Token revoked"}}), 401
    access_token = create_access_token(str(user.id), user.role.value if user.role else None)
    return jsonify({"data": {"access_token": access_token}})


def _dev_login_enabled():
    """Dev-only endpoints (dev-login, dev-users) require BOTH the dev-only
    DEV_LOGIN_ALLOWED config flag (True only in DevConfig) AND an explicit
    DEV_LOGIN_ENABLED=true env var.

    We gate on DEV_LOGIN_ALLOWED rather than DEBUG: `flask run` sets
    app.config["DEBUG"] from its own --debug/FLASK_DEBUG flag (default off),
    overriding DevConfig — so a normal `flask run` in dev has DEBUG=False and
    would wrongly 403 the dev-login picker. The two-signal model still protects
    stag/prod, where DEV_LOGIN_ALLOWED is False and the env var is never set.
    """
    import os
    from flask import current_app
    return (
        current_app.config.get("DEV_LOGIN_ALLOWED")
        and os.environ.get("DEV_LOGIN_ENABLED", "").lower() in ("1", "true", "yes")
    )


@auth_bp.route("/dev-login", methods=["POST"])
def dev_login():
    """Dev-only login by email. Bypasses Google OAuth for local testing.
    Gated behind both DEBUG and DEV_LOGIN_ENABLED env var.
    """
    if not _dev_login_enabled():
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Dev login disabled"}}), 403

    email = request.json.get("email")
    if not email:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Email required"}}), 400

    user = User.query.filter_by(email=email).first()
    if user is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": f"User {email} not found. Run seed.py first."}}), 404

    if not user.active:
        return jsonify({"error": {"code": "FORBIDDEN", "message": "User is inactive"}}), 403

    access_token = create_access_token(
        str(user.id), user.role.value if user.role else None
    )
    refresh_token = create_refresh_token(str(user.id))
    user.refresh_token = refresh_token
    db.session.commit()

    return jsonify({
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": _serialize_auth_user(user),
        }
    })


@auth_bp.route("/dev-users")
def dev_users():
    """Dev-only: list available users for dev-login picker.
    Gated behind both DEBUG and DEV_LOGIN_ENABLED env var.
    """
    if not _dev_login_enabled():
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Dev only"}}), 403

    users = User.query.filter_by(active=True).all()
    return jsonify({
        "data": [
            {
                "email": u.email,
                "name": u.name,
                "role": u.role.value if u.role else None,
            }
            for u in users
        ]
    })


@auth_bp.route("/google", methods=["POST"])
def google_login():
    from app.auth.google_sso import exchange_code_for_tokens, get_user_info, validate_email_domain, GoogleSSOError

    code = request.json.get("code")
    if not code:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Authorization code required"}}), 400

    try:
        tokens = exchange_code_for_tokens(code)
        user_info = get_user_info(tokens["access_token"])
        validate_email_domain(user_info["email"])
    except GoogleSSOError as e:
        return jsonify({"error": {"code": "AUTH_ERROR", "message": str(e)}}), 401

    user = User.query.filter_by(email=user_info["email"]).first()
    if user is None:
        user = User(
            email=user_info["email"],
            name=user_info.get("name", user_info["email"]),
            google_id=user_info.get("id"),
            role=None,
        )
        db.session.add(user)

    access_token = create_access_token(
        str(user.id), user.role.value if user.role else None
    )
    refresh_token = create_refresh_token(str(user.id))
    user.refresh_token = refresh_token
    db.session.commit()

    return jsonify({
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": _serialize_auth_user(user),
        }
    })

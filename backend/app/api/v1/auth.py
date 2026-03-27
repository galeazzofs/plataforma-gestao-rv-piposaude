from flask import Blueprint, jsonify, g, request
from app.auth.decorators import require_auth
from app.auth.jwt_manager import create_access_token, create_refresh_token, decode_token, InvalidTokenError
from app.models import User
from app.extensions import db

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@auth_bp.route("/me")
@require_auth
def me():
    user = g.current_user
    return jsonify({
        "data": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role.value if user.role else None,
            "team_id": str(user.team_id) if user.team_id else None,
            "active": user.active,
        }
    })


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
    user = User.query.get(payload["sub"])
    if user is None or not user.active:
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": "User not found"}}), 401
    if user.refresh_token != refresh_token:
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Token revoked"}}), 401
    access_token = create_access_token(str(user.id), user.role.value if user.role else None)
    return jsonify({"data": {"access_token": access_token}})

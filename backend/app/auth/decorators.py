from functools import wraps
from flask import request, jsonify, g
from app.auth.jwt_manager import decode_token, InvalidTokenError
from app.extensions import db
from app.models.user import User, UserRole


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Missing or invalid Authorization header"}}), 401
        token = auth_header.split(" ", 1)[1]
        try:
            payload = decode_token(token)
        except InvalidTokenError as e:
            return jsonify({"error": {"code": "UNAUTHORIZED", "message": str(e)}}), 401
        if payload.get("type") != "access":
            return jsonify({"error": {"code": "UNAUTHORIZED", "message": "Invalid token type"}}), 401
        user = db.session.get(User, payload["sub"])
        if user is None or not user.active:
            return jsonify({"error": {"code": "UNAUTHORIZED", "message": "User not found or inactive"}}), 401
        if user.role is None:
            return jsonify({"error": {"code": "FORBIDDEN", "message": "User has no role assigned"}}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def require_role(*allowed_roles):
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated(*args, **kwargs):
            user = g.current_user
            if user.role == UserRole.ADMIN:
                return f(*args, **kwargs)
            if user.role not in allowed_roles:
                return jsonify({"error": {"code": "FORBIDDEN", "message": "Insufficient permissions"}}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

from flask import Blueprint, jsonify
from app.auth.decorators import require_role
from app.models.user import UserRole

admin_bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")


@admin_bp.route("/users")
@require_role(UserRole.ADMIN)
def list_users():
    from app.models import User
    users = User.query.filter_by(active=True).all()
    return jsonify({
        "data": [
            {
                "id": str(u.id),
                "email": u.email,
                "name": u.name,
                "role": u.role.value if u.role else None,
                "team_id": str(u.team_id) if u.team_id else None,
            }
            for u in users
        ]
    })

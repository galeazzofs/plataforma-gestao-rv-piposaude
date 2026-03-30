from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_role, require_auth
from app.models.user import UserRole
from app.api.middlewares import paginate_query, log_audit
from app.extensions import db

admin_bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")


# ── Users ──────────────────────────────────────────────────────────────────────

@admin_bp.route("/users")
@require_role(UserRole.ADMIN)
def list_users():
    from app.models import User
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    query = User.query.order_by(User.name)
    active = request.args.get("active")
    if active is not None:
        query = query.filter(User.active == (active.lower() == "true"))

    items, meta = paginate_query(query, page, per_page)

    return jsonify({
        "data": [_serialize_user(u) for u in items],
        "meta": meta,
    })


@admin_bp.route("/users/<user_id>")
@require_role(UserRole.ADMIN)
def get_user(user_id):
    from app.models import User
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "User not found"}}), 404
    return jsonify({"data": _serialize_user(user)})


@admin_bp.route("/users", methods=["POST"])
@require_role(UserRole.ADMIN)
def create_user():
    from app.models import User
    data = request.get_json()
    if not data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400

    email = data.get("email")
    name = data.get("name")
    role = data.get("role")
    if not email or not name or not role:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "email, name, role required"}}), 400

    try:
        role_enum = UserRole(role)
    except ValueError:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": f"Invalid role: {role}"}}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": {"code": "CONFLICT", "message": "Email already in use"}}), 409

    user = User(
        email=email,
        name=name,
        role=role_enum,
        team_id=data.get("team_id"),
        active=True,
    )
    db.session.add(user)
    db.session.flush()
    log_audit("users", user.id, "CREATE", new_values={"email": email, "role": role})
    db.session.commit()

    return jsonify({"data": _serialize_user(user)}), 201


@admin_bp.route("/users/<user_id>", methods=["PATCH"])
@require_role(UserRole.ADMIN)
def update_user(user_id):
    from app.models import User
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "User not found"}}), 404

    data = request.get_json() or {}
    old_values = _serialize_user(user)

    if "name" in data:
        user.name = data["name"]
    if "role" in data:
        try:
            user.role = UserRole(data["role"])
        except ValueError:
            return jsonify({"error": {"code": "VALIDATION_ERROR", "message": f"Invalid role: {data['role']}"}}), 400
    if "team_id" in data:
        user.team_id = data["team_id"]
    if "active" in data:
        user.active = bool(data["active"])

    log_audit("users", user.id, "UPDATE", old_values=old_values, new_values=_serialize_user(user))
    db.session.commit()

    return jsonify({"data": _serialize_user(user)})


@admin_bp.route("/users/<user_id>", methods=["DELETE"])
@require_role(UserRole.ADMIN)
def deactivate_user(user_id):
    from app.models import User
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "User not found"}}), 404

    user.active = False
    log_audit("users", user.id, "UPDATE", old_values={"active": True}, new_values={"active": False})
    db.session.commit()

    return jsonify({"data": {"id": str(user.id), "active": False}})


# ── Teams ─────────────────────────────────────────────────────────────────────

@admin_bp.route("/teams")
@require_role(UserRole.ADMIN)
def list_teams():
    from app.models import Team
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    query = Team.query.order_by(Team.name)
    items, meta = paginate_query(query, page, per_page)
    return jsonify({"data": [_serialize_team(t) for t in items], "meta": meta})


@admin_bp.route("/teams/<team_id>")
@require_role(UserRole.ADMIN)
def get_team(team_id):
    from app.models import Team
    team = db.session.get(Team, team_id)
    if team is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Team not found"}}), 404
    return jsonify({"data": _serialize_team(team)})


@admin_bp.route("/teams", methods=["POST"])
@require_role(UserRole.ADMIN)
def create_team():
    from app.models import Team
    data = request.get_json()
    if not data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400

    name = data.get("name")
    if not name:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "name required"}}), 400

    team = Team(name=name, leader_id=data.get("leader_id"))
    db.session.add(team)
    db.session.flush()
    log_audit("teams", team.id, "CREATE", new_values={"name": name})
    db.session.commit()

    return jsonify({"data": _serialize_team(team)}), 201


@admin_bp.route("/teams/<team_id>", methods=["DELETE"])
@require_role(UserRole.ADMIN)
def delete_team(team_id):
    from app.models import Team
    team = db.session.get(Team, team_id)
    if team is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Team not found"}}), 404

    log_audit("teams", team.id, "DELETE", old_values={"name": team.name})
    db.session.delete(team)
    db.session.commit()

    return jsonify({"data": {"id": team_id, "deleted": True}})


@admin_bp.route("/teams/<team_id>", methods=["PATCH"])
@require_role(UserRole.ADMIN)
def update_team(team_id):
    from app.models import Team
    team = db.session.get(Team, team_id)
    if team is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Team not found"}}), 404

    data = request.get_json() or {}
    if "name" in data:
        team.name = data["name"]
    if "leader_id" in data:
        team.leader_id = data["leader_id"]

    log_audit("teams", team.id, "UPDATE", new_values=data)
    db.session.commit()

    return jsonify({"data": _serialize_team(team)})


# ── Commission Pct Table ───────────────────────────────────────────────────────

@admin_bp.route("/commission-table")
@require_role(UserRole.ADMIN)
def list_commission_table():
    from app.models import CommissionPctTable
    version = request.args.get("version", type=int)
    if version is None:
        version = CommissionPctTable.current_version()

    rows = CommissionPctTable.query.filter_by(version=version).order_by(
        CommissionPctTable.segment, CommissionPctTable.achievement_min
    ).all()

    return jsonify({
        "data": [_serialize_pct_row(r) for r in rows],
        "meta": {"version": version},
    })


@admin_bp.route("/commission-table", methods=["POST"])
@require_role(UserRole.ADMIN)
def create_commission_table_row():
    from app.models import CommissionPctTable
    data = request.get_json()
    if not data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400

    required = ["version", "segment", "achievement_min", "achievement_max", "commission_pct"]
    if not all(k in data for k in required):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": f"Required: {required}"}}), 400

    user = g.current_user
    row = CommissionPctTable(
        version=data["version"],
        segment=data["segment"],
        achievement_min=data["achievement_min"],
        achievement_max=data["achievement_max"],
        commission_pct=data["commission_pct"],
        valid_from=data.get("valid_from"),
        valid_until=data.get("valid_until"),
        created_by=user.id,
    )
    db.session.add(row)
    db.session.flush()
    log_audit("commission_pct_table", row.id, "CREATE", new_values=data)
    db.session.commit()

    return jsonify({"data": _serialize_pct_row(row)}), 201


# ── Settings ──────────────────────────────────────────────────────────────────

@admin_bp.route("/settings")
@require_role(UserRole.ADMIN)
def list_settings():
    from app.models import PlatformSetting
    settings = PlatformSetting.query.all()
    return jsonify({
        "data": {s.key: s.value for s in settings}
    })


@admin_bp.route("/settings", methods=["PUT"])
@require_role(UserRole.ADMIN)
def bulk_update_settings():
    from app.models import PlatformSetting
    data = request.get_json()
    if data is None or "settings" not in data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "settings object required"}}), 400

    user = g.current_user
    result = {}
    for key, value in data["settings"].items():
        setting = PlatformSetting.set(key, value, user_id=user.id)
        log_audit("platform_settings", setting.id, "UPDATE", new_values={"key": key, "value": value})
        result[key] = value

    db.session.commit()
    return jsonify({"data": result})


@admin_bp.route("/settings/<key>", methods=["PUT"])
@require_role(UserRole.ADMIN)
def update_setting(key):
    from app.models import PlatformSetting
    data = request.get_json()
    if data is None or "value" not in data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "value required"}}), 400

    user = g.current_user
    setting = PlatformSetting.set(key, data["value"], user_id=user.id)
    log_audit("platform_settings", setting.id, "UPDATE", new_values={"key": key, "value": data["value"]})
    db.session.commit()

    return jsonify({"data": {"key": key, "value": data["value"]}})


# ── Sync Status ────────────────────────────────────────────────────────────────

@admin_bp.route("/sync-trigger", methods=["POST"])
@require_role(UserRole.ADMIN)
def sync_trigger():
    """Manually trigger a HubSpot sync."""
    try:
        from app.modules.hubspot_sync.sync import run_sync
        result = run_sync()
        return jsonify({"data": {"status": "triggered", "result": result}})
    except Exception as e:
        return jsonify({"error": {"code": "SYNC_ERROR", "message": str(e)}}), 500


@admin_bp.route("/sync-status")
@require_role(UserRole.ADMIN)
def sync_status():
    """Return HubSpot sync status from platform settings."""
    from app.models import PlatformSetting
    last_sync = PlatformSetting.get("hubspot_last_sync")
    sync_errors = PlatformSetting.get("hubspot_last_sync_errors", 0)
    sync_created = PlatformSetting.get("hubspot_last_sync_created", 0)
    sync_updated = PlatformSetting.get("hubspot_last_sync_updated", 0)

    return jsonify({
        "data": {
            "last_sync": last_sync,
            "errors": sync_errors,
            "created": sync_created,
            "updated": sync_updated,
        }
    })


# ── Audit Log ─────────────────────────────────────────────────────────────────

@admin_bp.route("/audit-log")
@require_role(UserRole.ADMIN)
def audit_log():
    from app.models import AuditLog
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    query = AuditLog.query.order_by(AuditLog.created_at.desc())

    table_name = request.args.get("table_name")
    if table_name:
        query = query.filter(AuditLog.table_name == table_name)

    action = request.args.get("action")
    if action:
        query = query.filter(AuditLog.action == action)

    items, meta = paginate_query(query, page, per_page)

    return jsonify({
        "data": [
            {
                "id": str(e.id),
                "table_name": e.table_name,
                "record_id": str(e.record_id) if e.record_id else None,
                "action": e.action,
                "user_id": str(e.user_id) if e.user_id else None,
                "old_values": e.old_values,
                "new_values": e.new_values,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in items
        ],
        "meta": meta,
    })


# ── Serializers ────────────────────────────────────────────────────────────────

def _serialize_user(u):
    return {
        "id": str(u.id),
        "email": u.email,
        "name": u.name,
        "role": u.role.value if u.role else None,
        "team_id": str(u.team_id) if u.team_id else None,
        "active": u.active,
    }


def _serialize_team(t):
    return {
        "id": str(t.id),
        "name": t.name,
        "leader_id": str(t.leader_id) if t.leader_id else None,
    }


def _serialize_pct_row(r):
    return {
        "id": str(r.id),
        "version": r.version,
        "segment": r.segment,
        "achievement_min": str(r.achievement_min),
        "achievement_max": str(r.achievement_max),
        "commission_pct": str(r.commission_pct),
        "valid_from": r.valid_from.isoformat() if r.valid_from else None,
        "valid_until": r.valid_until.isoformat() if r.valid_until else None,
    }

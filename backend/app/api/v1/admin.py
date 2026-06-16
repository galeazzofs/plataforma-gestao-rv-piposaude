from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, g
from sqlalchemy import or_
from app.auth.decorators import require_role, require_auth
from app.models.user import User, UserRole
from app.models import PlatformSetting
from app.api.middlewares import paginate_query, log_audit
from app.extensions import db

admin_bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")

# Allowlist of platform_settings keys writable via the admin API.
# Anything not in this set is rejected with 400. Adding a new key here is
# an explicit decision because settings can change runtime behavior
# (HubSpot owner mapping, sync intervals, default targets, etc.).
WRITABLE_SETTINGS = {
    "hubspot_owner_map",
    "hubspot_sync_interval_minutes",
    "default_quarterly_target",
    "default_commission_table_version",
    "financial_client_aliases",
    "perk_match_strict",
}

CN_NIVEIS = {"CN1", "CN2", "CN3"}
CN_PORTES = {"M", "G+"}


# ── Users ──────────────────────────────────────────────────────────────────────

@admin_bp.route("/users")
@require_role(UserRole.FINANCE)
def list_users():
    from app.models import User
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    query = User.query.order_by(User.name)
    active = request.args.get("active")
    # Default to active-only so soft-deleted users disappear from the admin list.
    # Pass ?active=false to see deactivated users, or ?active=all for everyone.
    if active is None:
        query = query.filter(User.active.is_(True))
    elif active.lower() != "all":
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
        team_id=data.get("team_id") or None,
        active=True,
        left_company=bool(data.get("left_company", False)),
    )
    error = _apply_profile_fields(user, data)
    if error:
        return error
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
        user.team_id = data["team_id"] or None
    if "active" in data:
        user.active = bool(data["active"])
    if "left_company" in data:
        user.left_company = bool(data["left_company"])
    error = _apply_profile_fields(user, data)
    if error:
        return error

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
        team.leader_id = data["leader_id"] or None

    log_audit("teams", team.id, "UPDATE", new_values=data)
    db.session.commit()

    return jsonify({"data": _serialize_team(team)})


@admin_bp.route("/teams/<team_id>/members", methods=["POST"])
@require_role(UserRole.ADMIN)
def add_team_member(team_id):
    """Assign a user to a team. Body: {user_id}."""
    from app.models import Team, User
    team = db.session.get(Team, team_id)
    if team is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Team not found"}}), 404

    data = request.get_json() or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "user_id required"}}), 400

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "User not found"}}), 404

    old_team_id = str(user.team_id) if user.team_id else None
    user.team_id = team.id
    log_audit(
        "users", user.id, "UPDATE",
        old_values={"team_id": old_team_id},
        new_values={"team_id": str(team.id)},
    )
    db.session.commit()

    return jsonify({"data": _serialize_team(team)})


@admin_bp.route("/teams/<team_id>/members/<user_id>", methods=["DELETE"])
@require_role(UserRole.ADMIN)
def remove_team_member(team_id, user_id):
    """Remove a user from a team (sets user.team_id = NULL)."""
    from app.models import Team, User
    team = db.session.get(Team, team_id)
    if team is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Team not found"}}), 404

    user = db.session.get(User, user_id)
    if user is None or str(user.team_id) != str(team.id):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "User is not a member of this team"}}), 404

    user.team_id = None
    log_audit(
        "users", user.id, "UPDATE",
        old_values={"team_id": str(team.id)},
        new_values={"team_id": None},
    )
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

    from decimal import Decimal
    user = g.current_user
    try:
        version = int(data["version"])
        achievement_min = Decimal(str(data["achievement_min"]))
        achievement_max = Decimal(str(data["achievement_max"]))
        commission_pct = Decimal(str(data["commission_pct"]))
    except (ValueError, TypeError, Exception):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "version must be int; min/max/pct must be numeric"}}), 400

    row = CommissionPctTable(
        version=version,
        segment=data["segment"],
        achievement_min=achievement_min,
        achievement_max=achievement_max,
        commission_pct=commission_pct,
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
        db.session.flush()  # ensure setting.id is populated before log_audit
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
    db.session.flush()  # ensure setting.id is populated before log_audit
    log_audit("platform_settings", setting.id, "UPDATE", new_values={"key": key, "value": data["value"]})
    db.session.commit()

    return jsonify({"data": {"key": key, "value": data["value"]}})


# ── Sync Status ────────────────────────────────────────────────────────────────

@admin_bp.route("/sync-trigger", methods=["POST"])
@require_role(UserRole.ADMIN)
def sync_trigger():
    """Manually trigger a HubSpot sync (runs in background thread).

    Uses an atomic UPDATE + rowcount check to avoid the TOCTOU race that
    a separate read-then-write would have (two simultaneous POSTs could
    both observe `running=False` and spawn parallel sync threads).

    The flag is the fast 409 + UI status ("RUNNING") only. The authoritative
    mutual exclusion is the Postgres advisory lock inside run_sync itself,
    which also covers the per-worker schedulers — if a scheduled sync is
    mid-run, the thread spawned here no-ops cleanly.
    """
    import threading
    from flask import current_app

    # Atomic "claim the lock" — set running=True only if currently false-or-missing.
    # PlatformSetting stores values as JSON, so "false"/"true" are the JSON forms.
    from sqlalchemy import text
    result = db.session.execute(
        text("""
            UPDATE platform_settings
               SET value = 'true'
             WHERE key = 'hubspot_sync_running'
               AND value IN ('false', 'null')
        """)
    )
    if result.rowcount == 0:
        # No row updated — either lock is already held, OR the row doesn't exist.
        # Check current state to distinguish.
        current = PlatformSetting.get("hubspot_sync_running", False)
        if current:
            db.session.rollback()
            return jsonify({"data": {"status": "already_running"}}), 409
        # Row missing — create it atomically.
        PlatformSetting.set("hubspot_sync_running", True, user_id=None)
    db.session.commit()

    app = current_app._get_current_object()

    def _bg_sync():
        with app.app_context():
            try:
                from app.modules.hubspot_sync.sync import run_sync
                run_sync()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Background sync failed: {e}")
                PlatformSetting.set("hubspot_last_sync", datetime.now(timezone.utc).isoformat(), user_id=None)
                PlatformSetting.set("hubspot_last_sync_errors", [str(e)], user_id=None)
                PlatformSetting.set("hubspot_last_sync_created", 0, user_id=None)
                PlatformSetting.set("hubspot_last_sync_updated", 0, user_id=None)
                db.session.commit()
            finally:
                PlatformSetting.set("hubspot_sync_running", False, user_id=None)
                db.session.commit()

    threading.Thread(target=_bg_sync, daemon=True).start()
    return jsonify({"data": {"status": "triggered"}})


@admin_bp.route("/sync-status")
@require_role(UserRole.ADMIN)
def sync_status():
    """Return HubSpot sync status from platform settings."""
    last_sync = PlatformSetting.get("hubspot_last_sync")
    sync_errors = PlatformSetting.get("hubspot_last_sync_errors", [])
    sync_created = PlatformSetting.get("hubspot_last_sync_created", 0)
    sync_updated = PlatformSetting.get("hubspot_last_sync_updated", 0)
    sync_skipped = PlatformSetting.get("hubspot_last_sync_skipped", 0)
    sync_skipped_breakdown = PlatformSetting.get("hubspot_last_sync_skipped_breakdown", {})
    running = PlatformSetting.get("hubspot_sync_running", False)

    created = sync_created if isinstance(sync_created, int) else 0
    updated = sync_updated if isinstance(sync_updated, int) else 0
    skipped = sync_skipped if isinstance(sync_skipped, int) else 0
    skipped_breakdown = sync_skipped_breakdown if isinstance(sync_skipped_breakdown, dict) else {}
    error_list = sync_errors if isinstance(sync_errors, list) else []

    if running:
        display_status = "RUNNING"
    elif error_list:
        display_status = "ERRORS"
    else:
        display_status = "OK"

    return jsonify({
        "data": {
            "last_sync": last_sync,
            "records_synced": created + updated,
            "running": bool(running),
            "status": display_status,
            "counts": {
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "skipped_breakdown": skipped_breakdown,
            },
            "errors": error_list,
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


# ── EV Quarter Achievement ────────────────────────────────────────────────

@admin_bp.route("/ev-achievements")
@require_role(UserRole.ADMIN)
def list_ev_achievements():
    """List all active EVs with their quarterly achievements (if any)."""
    from app.models import EvQuarterAchievement, User, Goal
    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)

    # Former EVs can keep receiving policy commissions after leaving, so
    # achievement maintenance must include active EVs plus flagged leavers.
    evs = User.query.filter(
        User.role == UserRole.EV,
        or_(User.active.is_(True), User.left_company.is_(True)),
    ).order_by(User.name).all()

    # Build achievement lookup keyed by ev_id
    ach_map = {}
    if quarter and year:
        rows = EvQuarterAchievement.query.filter_by(quarter=quarter, year=year).all()
        ach_map = {a.ev_id: a for a in rows}

    # Build goal lookup for MRR targets
    goal_map = {}
    if quarter and year:
        goals = Goal.query.filter_by(quarter=quarter, year=year).all()
        goal_map = {gl.ev_id: gl for gl in goals}

    data = []
    for ev in evs:
        ach = ach_map.get(ev.id)
        goal = goal_map.get(ev.id)
        data.append({
            "id": str(ach.id) if ach else None,
            "ev_id": str(ev.id),
            "ev_name": ev.name,
            "quarter": quarter,
            "year": year,
            "total_mrr": str(ach.total_mrr) if ach and ach.total_mrr else None,
            "mrr_target": str(goal.mrr_target) if goal and goal.mrr_target else (
                str(ach.mrr_target) if ach and ach.mrr_target else None
            ),
            "achievement_pct": str(ach.achievement_pct) if ach and ach.achievement_pct else None,
            "is_final": ach.is_final if ach else False,
        })

    return jsonify({"data": data})


@admin_bp.route("/ev-achievements", methods=["POST"])
@require_role(UserRole.ADMIN)
def upsert_ev_achievement():
    """Create or update an EV quarterly achievement manually."""
    from decimal import Decimal
    from app.models import EvQuarterAchievement

    data = request.get_json()
    if not data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400

    required = ["ev_id", "quarter", "year"]
    if not all(k in data for k in required):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": f"Required: {required}"}}), 400

    ev_id = data["ev_id"]
    quarter = int(data["quarter"])
    year = int(data["year"])

    ach = EvQuarterAchievement.query.filter_by(
        ev_id=ev_id, quarter=quarter, year=year
    ).first()

    if ach and ach.is_final:
        return jsonify({"error": {"code": "LOCKED", "message": "Achievement is final and cannot be changed"}}), 409

    if ach is None:
        ach = EvQuarterAchievement(ev_id=ev_id, quarter=quarter, year=year)
        db.session.add(ach)

    if "total_mrr" in data:
        ach.total_mrr = Decimal(str(data["total_mrr"]))
    if "mrr_target" in data:
        ach.mrr_target = Decimal(str(data["mrr_target"]))
    if "achievement_pct" in data:
        ach.achievement_pct = Decimal(str(data["achievement_pct"]))
    if "is_final" in data:
        ach.is_final = bool(data["is_final"])

    # Auto-calculate achievement if both MRR values present and no explicit pct
    if "achievement_pct" not in data and ach.total_mrr is not None and ach.mrr_target:
        ach.achievement_pct = (ach.total_mrr / ach.mrr_target).quantize(Decimal("0.0001"))

    db.session.flush()
    log_audit("ev_quarter_achievements", ach.id, "UPSERT", new_values=data)
    db.session.commit()

    return jsonify({"data": _serialize_achievement(ach)}), 201


@admin_bp.route("/ev-achievements/calculate", methods=["POST"])
@require_role(UserRole.ADMIN)
def calculate_ev_achievements():
    """Auto-calculate achievements for all EVs in a quarter from their gongos."""
    from decimal import Decimal
    from app.models import EvQuarterAchievement, Goal, Policy, User, UserRole as UR
    from app.modules.commissions.achievement import get_quarter_date_range

    data = request.get_json()
    if not data or "quarter" not in data or "year" not in data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "quarter and year required"}}), 400

    quarter = int(data["quarter"])
    year = int(data["year"])
    start, end = get_quarter_date_range(quarter, year)

    # Get all EVs with goals for this quarter
    goals = Goal.query.filter_by(quarter=quarter, year=year).all()
    results = []

    for goal in goals:
        # Check if already final
        existing = EvQuarterAchievement.query.filter_by(
            ev_id=goal.ev_id, quarter=quarter, year=year
        ).first()
        if existing and existing.is_final:
            results.append(_serialize_achievement(existing))
            continue

        # Sum MRR from gongos
        total_mrr = db.session.query(
            db.func.coalesce(db.func.sum(Policy.mrr_projected), Decimal("0"))
        ).filter(
            Policy.ev_id == goal.ev_id,
            Policy.closed_date >= start,
            Policy.closed_date < end,
            Policy.commission_status != "CANCELLED",
        ).scalar()

        achievement = (Decimal(str(total_mrr)) / goal.mrr_target).quantize(
            Decimal("0.0001")
        ) if goal.mrr_target > 0 else Decimal("0")

        if existing is None:
            existing = EvQuarterAchievement(
                ev_id=goal.ev_id, quarter=quarter, year=year
            )
            db.session.add(existing)

        existing.total_mrr = total_mrr
        existing.mrr_target = goal.mrr_target
        existing.achievement_pct = achievement

        results.append(_serialize_achievement(existing))

    log_audit("ev_quarter_achievements", None, "BATCH_CALCULATE",
              new_values={"quarter": quarter, "year": year, "count": len(results)})
    db.session.commit()

    return jsonify({"data": results})


def _serialize_achievement(a):
    ev = db.session.get(User, a.ev_id) if a.ev_id else None
    return {
        "id": str(a.id),
        "ev_id": str(a.ev_id),
        "ev_name": ev.name if ev else None,
        "quarter": a.quarter,
        "year": a.year,
        "total_mrr": str(a.total_mrr) if a.total_mrr else None,
        "mrr_target": str(a.mrr_target) if a.mrr_target else None,
        "achievement_pct": str(a.achievement_pct) if a.achievement_pct else None,
        "is_final": a.is_final,
    }


# ── Serializers ────────────────────────────────────────────────────────────────

def _serialize_user(u):
    from app.models import Team
    team_name = None
    if u.team_id:
        team = db.session.get(Team, u.team_id)
        team_name = team.name if team else None
    return {
        "id": str(u.id),
        "email": u.email,
        "name": u.name,
        "role": u.role.value if u.role else None,
        "team_id": str(u.team_id) if u.team_id else None,
        "team_name": team_name,
        "active": u.active,
        "left_company": bool(getattr(u, "left_company", False)),
        "nivel": u.nivel.value if hasattr(u.nivel, "value") else u.nivel,
        "porte": u.porte.value if hasattr(u.porte, "value") else u.porte,
        "salario_base": str(u.salario_base) if u.salario_base is not None else None,
        "em_rampagem": bool(getattr(u, "em_rampagem", False)),
    }


def _serialize_team(t):
    from app.models import User
    leader_name = None
    if t.leader_id:
        leader = db.session.get(User, t.leader_id)
        leader_name = leader.name if leader else None
    members = User.query.filter_by(team_id=t.id, active=True).order_by(User.name).all()
    return {
        "id": str(t.id),
        "name": t.name,
        "leader_id": str(t.leader_id) if t.leader_id else None,
        "leader_name": leader_name,
        "members": [
            {
                "id": str(m.id),
                "name": m.name,
                "email": m.email,
                "role": m.role.value if m.role else None,
                "active": m.active,
                "left_company": bool(getattr(m, "left_company", False)),
                "nivel": m.nivel.value if hasattr(m.nivel, "value") else m.nivel,
                "porte": m.porte.value if hasattr(m.porte, "value") else m.porte,
                "salario_base": str(m.salario_base) if m.salario_base is not None else None,
                "em_rampagem": bool(getattr(m, "em_rampagem", False)),
            }
            for m in members
        ],
    }


def _apply_profile_fields(user, data):
    """Persist role-specific compensation profile fields from admin forms."""
    from decimal import Decimal, InvalidOperation

    if "nivel" in data:
        nivel = data.get("nivel") or None
        if nivel is not None and nivel not in CN_NIVEIS:
            return jsonify({"error": {"code": "VALIDATION_ERROR", "message": f"Invalid nivel: {nivel}"}}), 400
        user.nivel = nivel

    if "porte" in data:
        porte = data.get("porte") or None
        if porte is not None and porte not in CN_PORTES:
            return jsonify({"error": {"code": "VALIDATION_ERROR", "message": f"Invalid porte: {porte}"}}), 400
        user.porte = porte

    if "salario_base" in data:
        salario = data.get("salario_base")
        if salario in (None, ""):
            user.salario_base = None
        else:
            try:
                user.salario_base = Decimal(str(salario))
            except (InvalidOperation, ValueError):
                return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Invalid salario_base"}}), 400

    if "em_rampagem" in data:
        user.em_rampagem = bool(data.get("em_rampagem"))

    if "role" in data and user.role != UserRole.CN:
        user.nivel = None
        user.porte = None
        user.em_rampagem = False
    if "role" in data and user.role != UserRole.EV:
        user.left_company = False

    return None


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

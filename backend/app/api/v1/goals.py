from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth, require_role
from app.models import Goal, UserRole, User
from app.api.middlewares import paginate_query, log_audit
from app.extensions import db

goals_bp = Blueprint("goals", __name__, url_prefix="/api/v1/goals")


@goals_bp.route("")
@require_auth
def list_goals():
    """List goals with role-based filtering."""
    user = g.current_user
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = Goal.query

    if user.role in (UserRole.EV, UserRole.CN):
        query = query.filter(Goal.ev_id == user.id)
    elif user.role == UserRole.GERENTE:
        team_member_ids = [
            u.id for u in User.query.filter_by(team_id=user.team_id, active=True).all()
        ]
        query = query.filter(Goal.ev_id.in_(team_member_ids))

    ev_id = request.args.get("ev_id")
    if ev_id:
        query = query.filter(Goal.ev_id == ev_id)

    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)
    if quarter:
        query = query.filter(Goal.quarter == quarter)
    if year:
        query = query.filter(Goal.year == year)

    items, meta = paginate_query(query, page, per_page)

    return jsonify({
        "data": [_serialize_goal(g_) for g_ in items],
        "meta": meta,
    })


@goals_bp.route("", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.GERENTE)
def create_goal():
    """Create or update a goal for an EV."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400

    ev_id = data.get("ev_id")
    try:
        quarter = int(data.get("quarter", 0))
        year = int(data.get("year", 0))
        mrr_target = Decimal(str(data.get("mrr_target", "")))
    except (ValueError, TypeError, InvalidOperation):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "quarter, year must be integers; mrr_target must be numeric"}}), 400

    if not all([ev_id, quarter, year, mrr_target is not None]):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "ev_id, quarter, year, mrr_target required"}}), 400

    existing = Goal.query.filter_by(ev_id=ev_id, quarter=quarter, year=year).first()
    if existing:
        old_values = {"mrr_target": str(existing.mrr_target)}
        existing.mrr_target = mrr_target
        db.session.flush()
        log_audit("goals", existing.id, "UPDATE", old_values=old_values, new_values={"mrr_target": str(mrr_target)})
        db.session.commit()
        return jsonify({"data": _serialize_goal(existing)}), 200

    goal = Goal(ev_id=ev_id, quarter=quarter, year=year, mrr_target=mrr_target)
    db.session.add(goal)
    db.session.flush()
    log_audit("goals", goal.id, "CREATE", new_values={"ev_id": str(ev_id), "quarter": quarter, "year": year, "mrr_target": str(mrr_target)})
    db.session.commit()
    return jsonify({"data": _serialize_goal(goal)}), 201


@goals_bp.route("/<goal_id>", methods=["PUT"])
@require_role(UserRole.ADMIN, UserRole.GERENTE)
def update_goal(goal_id):
    """Update a single goal's mrr_target."""
    goal = db.session.get(Goal, goal_id)
    if goal is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Goal not found"}}), 404

    data = request.get_json() or {}
    if "mrr_target" not in data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "mrr_target required"}}), 400

    old_values = {"mrr_target": str(goal.mrr_target)}
    try:
        goal.mrr_target = Decimal(str(data["mrr_target"]))
    except (InvalidOperation, ValueError):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "mrr_target must be numeric"}}), 400
    log_audit("goals", goal.id, "UPDATE", old_values=old_values, new_values={"mrr_target": str(data["mrr_target"])})
    db.session.commit()

    return jsonify({"data": _serialize_goal(goal)})


@goals_bp.route("/import", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.GERENTE)
def import_goals():
    """Bulk import goals from JSON array."""
    data = request.get_json()
    if not data or not isinstance(data, list):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON array required"}}), 400

    created = 0
    updated = 0
    errors = []

    for i, row in enumerate(data):
        ev_id = row.get("ev_id")
        try:
            quarter = int(row.get("quarter", 0))
            year = int(row.get("year", 0))
            mrr_target = Decimal(str(row.get("mrr_target", "")))
        except (ValueError, TypeError, InvalidOperation):
            errors.append({"index": i, "message": "quarter/year must be integers; mrr_target must be numeric"})
            continue

        if not all([ev_id, quarter, year, mrr_target is not None]):
            errors.append({"index": i, "message": "ev_id, quarter, year, mrr_target required"})
            continue

        existing = Goal.query.filter_by(ev_id=ev_id, quarter=quarter, year=year).first()
        if existing:
            existing.mrr_target = mrr_target
            updated += 1
        else:
            goal = Goal(ev_id=ev_id, quarter=quarter, year=year, mrr_target=mrr_target)
            db.session.add(goal)
            created += 1

    db.session.commit()

    return jsonify({
        "data": {"created": created, "updated": updated, "errors": errors}
    }), 207 if errors else 200


def _serialize_goal(goal):
    return {
        "id": str(goal.id),
        "ev_id": str(goal.ev_id),
        "quarter": goal.quarter,
        "year": goal.year,
        "mrr_target": str(goal.mrr_target),
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
        "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
    }

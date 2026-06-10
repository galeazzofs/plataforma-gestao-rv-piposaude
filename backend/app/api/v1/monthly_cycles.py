from flask import Blueprint, jsonify, request, g

from app.auth.decorators import require_auth, require_role
from app.models import MonthlyCycle, MonthlyCycleStatus, UserRole
from app.api.middlewares import log_audit
from app.extensions import db
from app.modules.workflow.cycle_aggregator import build_cycle_payload


monthly_cycles_bp = Blueprint(
    "monthly_cycles", __name__, url_prefix="/api/v1/monthly-cycles"
)


def _serialize(cycle: MonthlyCycle) -> dict:
    return {
        "id": str(cycle.id),
        "month": cycle.month,
        "year": cycle.year,
        "quarter": cycle.quarter,
        "is_quarter_end": cycle.is_quarter_end,
        "status": cycle.status.value,
        "created_by": str(cycle.created_by),
        "created_at": cycle.created_at.isoformat() if cycle.created_at else None,
        "locked_at": cycle.locked_at.isoformat() if cycle.locked_at else None,
    }




@monthly_cycles_bp.route("", methods=["POST"])
@require_role(UserRole.ADMIN)
def create_cycle():
    """Open a monthly cycle. Blocks duplicates of the same (month, year)."""
    data = request.get_json() or {}
    month = data.get("month")
    year = data.get("year")

    try:
        month = int(month)
        year = int(year)
    except (TypeError, ValueError):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "month and year required (integers)"},
        }), 400

    if month not in range(1, 13):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "month must be 1..12"},
        }), 400

    existing = MonthlyCycle.query.filter_by(month=month, year=year).first()
    if existing is not None:
        return jsonify({
            "error": {
                "code": "CONFLICT",
                "message": (
                    f"MonthlyCycle for {month:02d}/{year} already exists "
                    f"(status: {existing.status.value})"
                ),
            },
        }), 409

    cycle = MonthlyCycle(
        month=month, year=year,
        status=MonthlyCycleStatus.OPEN,
        created_by=g.current_user.id,
    )
    db.session.add(cycle)
    db.session.flush()
    log_audit(
        "monthly_cycles", cycle.id, "CREATE",
        new_values={"month": month, "year": year, "status": "OPEN"},
    )
    db.session.commit()
    return jsonify({"data": _serialize(cycle)}), 201


@monthly_cycles_bp.route("")
@require_auth
def list_cycles():
    """List monthly cycles, newest first."""
    cycles = (
        MonthlyCycle.query
        .order_by(MonthlyCycle.year.desc(), MonthlyCycle.month.desc())
        .all()
    )
    return jsonify({"data": [_serialize(c) for c in cycles]})


@monthly_cycles_bp.route("/<cycle_id>")
@require_auth
def get_cycle(cycle_id):
    """Return a cycle with the global status of each sequence component."""
    cycle = db.session.get(MonthlyCycle, cycle_id)
    if cycle is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404

    return jsonify({"data": build_cycle_payload(cycle)})


@monthly_cycles_bp.route("/<cycle_id>", methods=["DELETE"])
@require_role(UserRole.ADMIN)
def delete_cycle(cycle_id):
    """Delete a monthly cycle. LOCKED cycles are frozen and cannot be removed."""
    cycle = db.session.get(MonthlyCycle, cycle_id)
    if cycle is None:
        return jsonify({"error": {"code": "NOT_FOUND",
                                  "message": "MonthlyCycle not found"}}), 404

    if cycle.status == MonthlyCycleStatus.LOCKED:
        return jsonify({
            "error": {
                "code": "CONFLICT",
                "message": (
                    f"MonthlyCycle {cycle.month:02d}/{cycle.year} is LOCKED "
                    "and cannot be deleted."
                ),
            },
        }), 409

    month, year = cycle.month, cycle.year
    log_audit(
        "monthly_cycles", cycle.id, "DELETE",
        old_values={"month": month, "year": year,
                    "status": cycle.status.value},
    )
    db.session.delete(cycle)
    db.session.commit()
    return jsonify({"data": {"id": cycle_id, "deleted": True}})

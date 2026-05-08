from flask import Blueprint, jsonify, request, g

from app.auth.decorators import require_auth, require_role
from app.models import QuarterlyCycle, QuarterlyCycleStatus, UserRole
from app.api.middlewares import log_audit
from app.extensions import db


quarterly_cycles_bp = Blueprint(
    "quarterly_cycles", __name__, url_prefix="/api/v1/quarterly-cycles"
)


# Placeholder component layout returned by GET /:id until issue #37 wires
# the real orchestration. Each entry mirrors what the orchestrator will
# eventually populate so the frontend can already render the cycle page.
_PLACEHOLDER_COMPONENTS = (
    "ev_quarter",
    "cn_monthly",
    "cn_quarterly_bonus",
    "ev_quarterly_bonus",
    "leadership",
)


def _serialize(cycle: QuarterlyCycle) -> dict:
    return {
        "id": str(cycle.id),
        "quarter": cycle.quarter,
        "year": cycle.year,
        "status": cycle.status.value,
        "created_by": str(cycle.created_by),
        "created_at": cycle.created_at.isoformat() if cycle.created_at else None,
        "locked_at": cycle.locked_at.isoformat() if cycle.locked_at else None,
    }


def _placeholder_components() -> list:
    return [{"key": k, "status": "PENDING"} for k in _PLACEHOLDER_COMPONENTS]


@quarterly_cycles_bp.route("", methods=["POST"])
@require_role(UserRole.ADMIN)
def create_cycle():
    """Open a quarterly cycle. Blocks duplicates of the same (quarter, year)."""
    data = request.get_json() or {}
    quarter = data.get("quarter")
    year = data.get("year")

    try:
        quarter = int(quarter)
        year = int(year)
    except (TypeError, ValueError):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "quarter and year required (integers)"},
        }), 400

    if quarter not in (1, 2, 3, 4):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "quarter must be 1..4"},
        }), 400

    existing = QuarterlyCycle.query.filter_by(quarter=quarter, year=year).first()
    if existing is not None:
        return jsonify({
            "error": {
                "code": "CONFLICT",
                "message": (
                    f"QuarterlyCycle for Q{quarter}/{year} already exists "
                    f"(status: {existing.status.value})"
                ),
            },
        }), 409

    cycle = QuarterlyCycle(
        quarter=quarter, year=year,
        status=QuarterlyCycleStatus.OPEN,
        created_by=g.current_user.id,
    )
    db.session.add(cycle)
    db.session.flush()
    log_audit(
        "quarterly_cycles", cycle.id, "CREATE",
        new_values={"quarter": quarter, "year": year, "status": "OPEN"},
    )
    db.session.commit()
    return jsonify({"data": _serialize(cycle)}), 201


@quarterly_cycles_bp.route("")
@require_auth
def list_cycles():
    """List quarterly cycles, newest first."""
    cycles = (
        QuarterlyCycle.query
        .order_by(QuarterlyCycle.year.desc(), QuarterlyCycle.quarter.desc())
        .all()
    )
    return jsonify({"data": [_serialize(c) for c in cycles]})


@quarterly_cycles_bp.route("/<cycle_id>")
@require_auth
def get_cycle(cycle_id):
    """Return a cycle and its 5 component slots.

    Components are placeholders (status PENDING) until issue #37 wires the
    real orchestration that reads each component's actual state.
    """
    cycle = db.session.get(QuarterlyCycle, cycle_id)
    if cycle is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404

    payload = _serialize(cycle)
    payload["components"] = _placeholder_components()
    return jsonify({"data": payload})

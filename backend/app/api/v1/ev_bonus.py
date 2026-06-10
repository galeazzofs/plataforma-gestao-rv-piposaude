import logging

from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth
from app.models import UserRole, EvQuarterAchievement
from app.extensions import db
from app.modules.commissions.ev_bonus import run_ev_quarterly_bonus
from app.modules.workflow.state_machine import _maybe_lock_attached_cycle

_log = logging.getLogger(__name__)

ev_bonus_bp = Blueprint("ev_bonus", __name__, url_prefix="/api/v1/commissions/ev")


@ev_bonus_bp.route("/bonus", methods=["POST"])
@require_auth
def run_bonus():
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json()
    if not body:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400
    try:
        quarter = int(body["quarter"])
        year = int(body["year"])
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": str(e)}}), 400

    try:
        result = run_ev_quarterly_bonus(quarter, year)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": str(e)}}), 500
    return jsonify({"data": result})


@ev_bonus_bp.route("/bonus")
@require_auth
def list_bonuses():
    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.EV):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)
    query = EvQuarterAchievement.query
    if quarter:
        query = query.filter_by(quarter=quarter)
    if year:
        query = query.filter_by(year=year)
    if user.role == UserRole.EV:
        query = query.filter_by(ev_id=user.id)

    items = query.all()
    return jsonify({"data": [_serialize(a) for a in items]})


def _serialize(a):
    return {
        "id": str(a.id),
        "ev_id": str(a.ev_id),
        "quarter": a.quarter,
        "year": a.year,
        "achievement_pct": str(a.achievement_pct) if a.achievement_pct is not None else None,
        "bonus_amount": str(a.bonus_amount) if a.bonus_amount is not None else None,
        "salario_base_snapshot": str(a.salario_base_snapshot) if a.salario_base_snapshot is not None else None,
        "is_final": a.is_final,
    }


@ev_bonus_bp.route("/bonus/finalize", methods=["POST"])
@require_auth
def finalize_bonus():
    """Lock all non-final EV quarter achievements for (quarter, year).
    Mirrors the CN quarterly-bonus finalize; the last final row may
    complete the quarter-end month's cycle. ADMIN only."""
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json() or {}
    try:
        quarter = int(body.get("quarter"))
        year = int(body.get("year"))
    except (TypeError, ValueError):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "quarter and year required (integers)"},
        }), 400

    if quarter not in range(1, 5):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "quarter must be 1..4"},
        }), 400

    # Compute-then-lock: run the bonus calculator before flipping flags so
    # no NULL bonus_amount is ever irreversibly locked.
    try:
        run_ev_quarterly_bonus(quarter, year)
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "error": {"code": "BONUS_RUN_FAILED", "message": str(e)},
        }), 422

    rows = EvQuarterAchievement.query.filter_by(
        quarter=quarter, year=year, is_final=False,
    ).all()
    for row in rows:
        row.is_final = True
    db.session.commit()

    # Locking the last bonus row may complete the quarter-end cycle.
    try:
        _maybe_lock_attached_cycle(quarter * 3, year)
        db.session.commit()
    except Exception:
        db.session.rollback()
        _log.exception("cycle re-evaluation after EV bonus finalize failed")

    return jsonify({"data": {"finalized": len(rows)}})

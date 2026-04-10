from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth
from app.models import UserRole, EvQuarterAchievement
from app.extensions import db
from app.modules.commissions.ev_bonus import run_ev_quarterly_bonus

ev_bonus_bp = Blueprint("ev_bonus", __name__, url_prefix="/api/v1/commissions/ev")


@ev_bonus_bp.route("/bonus", methods=["POST"])
@require_auth
def run_bonus():
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json()
    quarter = int(body["quarter"])
    year = int(body["year"])
    result = run_ev_quarterly_bonus(quarter, year)
    db.session.commit()
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
        "achievement_pct": str(a.achievement_pct) if a.achievement_pct else None,
        "bonus_amount": str(a.bonus_amount) if a.bonus_amount is not None else None,
        "salario_base_snapshot": str(a.salario_base_snapshot) if a.salario_base_snapshot else None,
        "is_final": a.is_final,
    }

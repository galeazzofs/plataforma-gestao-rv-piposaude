from decimal import Decimal
from datetime import date
from flask import Blueprint, jsonify, request, g
from sqlalchemy import func
from app.auth.decorators import require_auth
from app.models import Commission, Policy, Goal, UserRole
from app.api.middlewares import paginate_query
from app.extensions import db

commissions_bp = Blueprint("commissions", __name__, url_prefix="/api/v1/commissions")


@commissions_bp.route("")
@require_auth
def list_commissions():
    user = g.current_user
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = Commission.query

    if user.role in (UserRole.EV, UserRole.CN):
        query = query.filter(Commission.ev_id == user.id)

    ev_id = request.args.get("ev_id")
    if ev_id:
        query = query.filter(Commission.ev_id == ev_id)

    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)
    if quarter:
        query = query.filter(Commission.quarter == quarter)
    if year:
        query = query.filter(Commission.year == year)

    is_final = request.args.get("is_final")
    if is_final is not None:
        query = query.filter(Commission.is_final == (is_final.lower() == "true"))

    items, meta = paginate_query(query, page, per_page)

    return jsonify({
        "data": [_serialize_commission(c) for c in items],
        "meta": meta,
    })


@commissions_bp.route("/summary")
@require_auth
def commission_summary():
    """Summary: saldo a receber, atingimento, projeção."""
    user = g.current_user
    ev_id = request.args.get("ev_id", str(user.id) if user.role in (UserRole.EV, UserRole.CN) else None)

    if not ev_id:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "ev_id required"}}), 400

    # Total estimated balance (non-settled)
    balance = db.session.query(
        func.coalesce(func.sum(Commission.total_estimated), 0)
    ).filter(
        Commission.ev_id == ev_id,
        Commission.is_final == False,  # noqa: E712
    ).scalar()

    # Current quarter achievement
    today = date.today()
    current_quarter = (today.month - 1) // 3 + 1
    current_year = today.year

    goal = Goal.query.filter_by(
        ev_id=ev_id, quarter=current_quarter, year=current_year
    ).first()

    # TODO: Use db.extract for PostgreSQL — for SQLite compatibility use date range
    quarter_start_month = (current_quarter - 1) * 3 + 1
    quarter_end_month = current_quarter * 3
    start_date = date(current_year, quarter_start_month, 1)
    if quarter_end_month == 12:
        end_date = date(current_year + 1, 1, 1)
    else:
        end_date = date(current_year, quarter_end_month + 1, 1)

    quarter_mrr = db.session.query(
        func.coalesce(func.sum(Policy.mrr_projected), 0)
    ).filter(
        Policy.ev_id == ev_id,
        Policy.closed_date >= start_date,
        Policy.closed_date < end_date,
    ).scalar()

    target = goal.mrr_target if goal else Decimal("0")
    achievement = (Decimal(str(quarter_mrr)) / target * 100) if target > 0 else Decimal("0")

    return jsonify({
        "data": {
            "balance_estimated": str(balance),
            "current_quarter": current_quarter,
            "current_year": current_year,
            "mrr_sold": str(quarter_mrr),
            "mrr_target": str(target),
            "achievement_pct": str(achievement.quantize(Decimal("0.01"))),
        }
    })


@commissions_bp.route("/projection")
@require_auth
def commission_projection():
    """12-month projection of estimated receivables."""
    user = g.current_user
    ev_id = request.args.get("ev_id", str(user.id) if user.role in (UserRole.EV, UserRole.CN) else None)

    if not ev_id:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "ev_id required"}}), 400

    commissions = Commission.query.filter(
        Commission.ev_id == ev_id,
        Commission.is_final == False,  # noqa: E712
    ).all()

    # Build monthly projection (simplified: spread evenly over remaining months)
    today = date.today()
    months = []
    for i in range(12):
        month = today.month + i
        year = today.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        total = sum(
            c.monthly_estimated or Decimal("0")
            for c in commissions
        )
        months.append({
            "month": f"{year}-{month:02d}",
            "projected": str(total),
        })

    return jsonify({"data": months})


def _serialize_commission(c):
    return {
        "id": str(c.id),
        "policy_id": str(c.policy_id),
        "ev_id": str(c.ev_id),
        "quarter": c.quarter,
        "year": c.year,
        "segment": c.segment,
        "achievement_pct": str(c.achievement_pct) if c.achievement_pct else None,
        "commission_pct": str(c.commission_pct) if c.commission_pct else None,
        "monthly_estimated": str(c.monthly_estimated) if c.monthly_estimated else None,
        "monthly_actual": str(c.monthly_actual) if c.monthly_actual else None,
        "total_estimated": str(c.total_estimated) if c.total_estimated else None,
        "total_actual": str(c.total_actual) if c.total_actual else None,
        "is_final": c.is_final,
    }

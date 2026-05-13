from decimal import Decimal
from datetime import date
from flask import Blueprint, jsonify, request, g
from sqlalchemy import func
from app.auth.decorators import require_auth
from app.models import Commission, Policy, Goal, UserRole
from app.api.middlewares import paginate_query
from app.extensions import db

commissions_bp = Blueprint("commissions", __name__, url_prefix="/api/v1/commissions")


def _parse_quarter():
    quarter = request.args.get("quarter", type=int)
    if quarter is not None and quarter not in (1, 2, 3, 4):
        return None, (
            jsonify({
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "quarter must be between 1 and 4",
                }
            }),
            400,
        )
    return quarter, None


def _period_bounds(year, quarter):
    if year is None:
        return None, None
    q_start = quarter or 1
    q_end = quarter or 4
    start_month = (q_start - 1) * 3 + 1
    end_month = q_end * 3
    start = date(year, start_month, 1)
    end = date(year + 1, 1, 1) if end_month == 12 else date(year, end_month + 1, 1)
    return start, end


def _projection_window(year, quarter):
    if year is None:
        return date.today(), 12
    start, _ = _period_bounds(year, quarter)
    return start, 3 if quarter else 12


def _available_years(ev_id):
    rows = (
        db.session.query(func.extract("year", Policy.closed_date))
        .filter(Policy.ev_id == ev_id, Policy.closed_date.isnot(None))
        .distinct()
        .all()
    )
    years = {int(y) for (y,) in rows if y}
    years.add(date.today().year)
    return sorted(years)


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
    """Summary: saldo a receber, atingimento, projecao (spec S7 + S9)."""
    from app.modules.commissions.projection import compute_ev_projection

    user = g.current_user
    ev_id = request.args.get("ev_id", str(user.id) if user.role in (UserRole.EV, UserRole.CN) else None)
    quarter, error = _parse_quarter()
    if error:
        return error
    year = request.args.get("year", type=int)

    if not ev_id:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "ev_id required"}}), 400

    # Live estimated balance from Policy data (spec S9 projection layer)
    today = date.today()
    selected_quarter = quarter or (today.month - 1) // 3 + 1
    selected_year = year or today.year
    start_date, end_date = _period_bounds(selected_year, selected_quarter)
    period_start, period_months = _projection_window(selected_year, selected_quarter)
    period_projection = compute_ev_projection(
        ev_id,
        period_start=period_start,
        period_months=period_months,
    )
    balance = sum((m["projected"] for m in period_projection), Decimal("0"))
    balance = balance.quantize(Decimal("0.01"))

    goal = Goal.query.filter_by(
        ev_id=ev_id, quarter=selected_quarter, year=selected_year
    ).first()

    quarter_mrr = db.session.query(
        func.coalesce(func.sum(Policy.mrr_projected), 0)
    ).filter(
        Policy.ev_id == ev_id,
        Policy.closed_date >= start_date,
        Policy.closed_date < end_date,
    ).scalar()
    quarter_mrr = Decimal(str(quarter_mrr or "0")).quantize(Decimal("0.01"))

    target = goal.mrr_target if goal else Decimal("0")
    achievement = (quarter_mrr / target * 100) if target > 0 else Decimal("0")

    return jsonify({
        "data": {
            "balance_estimated": str(balance),
            "current_quarter": selected_quarter,
            "current_year": selected_year,
            "mrr_sold": str(quarter_mrr),
            "mrr_target": str(target),
            "achievement_pct": str(achievement.quantize(Decimal("0.01"))),
            "available_years": _available_years(ev_id),
        }
    })


@commissions_bp.route("/projection")
@require_auth
def commission_projection():
    """12-month projection of estimated receivables (spec S7)."""
    from app.modules.commissions.projection import compute_ev_projection

    user = g.current_user
    ev_id = request.args.get("ev_id", str(user.id) if user.role in (UserRole.EV, UserRole.CN) else None)
    quarter, error = _parse_quarter()
    if error:
        return error
    year = request.args.get("year", type=int)

    if not ev_id:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "ev_id required"}}), 400

    period_start, period_months = _projection_window(year, quarter)
    months = compute_ev_projection(
        ev_id,
        period_start=period_start,
        period_months=period_months,
    )

    return jsonify({
        "data": [
            {"month": m["month"], "projected": str(m["projected"])}
            for m in months
        ]
    })


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

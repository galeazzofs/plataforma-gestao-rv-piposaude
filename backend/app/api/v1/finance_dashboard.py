import csv
import io
from datetime import date
from flask import Blueprint, jsonify, request, g, Response
from sqlalchemy import func
from app.auth.decorators import require_role
from app.models import Commission, Policy, UserRole, User, ImportBatch, EvValidation, ValidationStatus
from app.extensions import db

finance_dashboard_bp = Blueprint("finance_dashboard", __name__, url_prefix="/api/v1/finance")


@finance_dashboard_bp.route("/dashboard")
@require_role(UserRole.ADMIN, UserRole.FINANCE)
def dashboard():
    """Finance dashboard overview: totals, pending validations, recent batches."""
    today = date.today()
    current_quarter = (today.month - 1) // 3 + 1
    current_year = today.year

    # Total commissions estimated this quarter
    total_estimated = db.session.query(
        func.coalesce(func.sum(Commission.total_estimated), 0)
    ).filter(
        Commission.quarter == current_quarter,
        Commission.year == current_year,
        Commission.is_final == False,  # noqa: E712
    ).scalar()

    # Total commissions final (settled) this quarter
    total_final = db.session.query(
        func.coalesce(func.sum(Commission.total_actual), 0)
    ).filter(
        Commission.quarter == current_quarter,
        Commission.year == current_year,
        Commission.is_final == True,  # noqa: E712
    ).scalar()

    # Pending validations count
    pending_validations = EvValidation.query.filter_by(
        status=ValidationStatus.PENDING
    ).count()

    # Contested validations count
    contested_validations = EvValidation.query.filter_by(
        status=ValidationStatus.CONTESTED
    ).count()

    # Recent import batches
    recent_batches = ImportBatch.query.order_by(ImportBatch.created_at.desc()).limit(5).all()

    # EV count with commissions this quarter
    ev_count = db.session.query(
        func.count(func.distinct(Commission.ev_id))
    ).filter(
        Commission.quarter == current_quarter,
        Commission.year == current_year,
    ).scalar()

    return jsonify({
        "data": {
            "current_quarter": current_quarter,
            "current_year": current_year,
            "total_estimated": str(total_estimated),
            "total_final": str(total_final),
            "ev_count": ev_count,
            "pending_validations": pending_validations,
            "contested_validations": contested_validations,
            "recent_batches": [
                {
                    "id": str(b.id),
                    "filename": b.filename,
                    "status": b.status,
                    "nf_count": b.nf_count,
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                }
                for b in recent_batches
            ],
        }
    })


@finance_dashboard_bp.route("/export")
@require_role(UserRole.ADMIN, UserRole.FINANCE)
def export_commissions():
    """Export commissions to CSV for a given quarter/year."""
    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)

    if not quarter or not year:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "quarter and year required"}}), 400

    commissions = Commission.query.filter_by(quarter=quarter, year=year).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "commission_id", "ev_id", "ev_name", "policy_id", "quarter", "year",
        "segment", "achievement_pct", "commission_pct",
        "monthly_estimated", "total_estimated",
        "monthly_actual", "total_actual", "is_final",
    ])

    for c in commissions:
        ev_name = c.ev.name if c.ev else ""
        writer.writerow([
            str(c.id), str(c.ev_id), ev_name, str(c.policy_id),
            c.quarter, c.year, c.segment,
            str(c.achievement_pct) if c.achievement_pct else "",
            str(c.commission_pct) if c.commission_pct else "",
            str(c.monthly_estimated) if c.monthly_estimated else "",
            str(c.total_estimated) if c.total_estimated else "",
            str(c.monthly_actual) if c.monthly_actual else "",
            str(c.total_actual) if c.total_actual else "",
            str(c.is_final),
        ])

    csv_data = output.getvalue()
    filename = f"commissions_Q{quarter}_{year}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth
from app.models import UserRole, GerenteQuarterAppraisal
from app.extensions import db
from app.modules.commissions.leadership_calculator import (
    run_leadership_appraisal,
    get_leadership_preview,
)

leadership_bp = Blueprint("leadership", __name__, url_prefix="/api/v1/commissions/leadership")


@leadership_bp.route("/preview")
@require_auth
def preview():
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)
    if not quarter or not year:
        return jsonify({"error": {"code": "VALIDATION_ERROR",
                                  "message": "quarter and year required"}}), 400
    data = get_leadership_preview(quarter, year)
    return jsonify({"data": data})


@leadership_bp.route("/appraisal", methods=["POST"])
@require_auth
def run_appraisal():
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    body = request.get_json()
    quarter = int(body["quarter"])
    year = int(body["year"])
    inputs = body["inputs"]  # [{gerente_id, meta_sql, realizado_mrr, realizado_sql}]
    result = run_leadership_appraisal(quarter, year, inputs)
    db.session.commit()
    return jsonify({"data": result})


@leadership_bp.route("/appraisal")
@require_auth
def list_appraisals():
    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.GERENTE):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)
    query = GerenteQuarterAppraisal.query
    if quarter:
        query = query.filter_by(quarter=quarter)
    if year:
        query = query.filter_by(year=year)
    if user.role == UserRole.GERENTE:
        query = query.filter_by(gerente_id=user.id)

    items = query.all()
    return jsonify({"data": [_serialize(a) for a in items]})


@leadership_bp.route("/appraisal/<appraisal_id>/finalize", methods=["POST"])
@require_auth
def finalize(appraisal_id):
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    appraisal = db.session.get(GerenteQuarterAppraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404
    if appraisal.is_final:
        return jsonify({"error": {"code": "ALREADY_FINAL"}}), 409

    appraisal.is_final = True
    db.session.commit()
    return jsonify({"data": _serialize(appraisal)})


def _serialize(a):
    return {
        "id": str(a.id),
        "gerente_id": str(a.gerente_id),
        "quarter": a.quarter,
        "year": a.year,
        "meta_mrr": str(a.meta_mrr),
        "meta_sql": a.meta_sql,
        "realizado_mrr": str(a.realizado_mrr),
        "realizado_sql": a.realizado_sql,
        "pct_mrr": str(a.pct_mrr),
        "pct_sql": str(a.pct_sql),
        "multiplicador": str(a.multiplicador),
        "bonus_amount": str(a.bonus_amount),
        "is_final": a.is_final,
    }

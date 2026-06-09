from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth
from app.models import (
    Appraisal, AppraisalStatus, UserRole, LiderVendasQuarterAppraisal,
)
from app.extensions import db
from app.modules.commissions.leadership_calculator import (
    run_leadership_appraisal,
    get_leadership_preview,
)
from app.modules.workflow.state_machine import (
    transition_lider_vendas_appraisal,
    maybe_auto_advance_appraisal_after_validation,
    InvalidTransitionError,
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
    if not body:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400
    try:
        quarter = int(body["quarter"])
        year = int(body["year"])
        inputs = body["inputs"]
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": str(e)}}), 400

    try:
        result = run_leadership_appraisal(quarter, year, inputs)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": str(e)}}), 500
    return jsonify({"data": result})


@leadership_bp.route("/appraisal")
@require_auth
def list_appraisals():
    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.LIDER_VENDAS):
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)
    query = LiderVendasQuarterAppraisal.query
    if quarter:
        query = query.filter_by(quarter=quarter)
    if year:
        query = query.filter_by(year=year)
    if user.role == UserRole.LIDER_VENDAS:
        query = query.filter_by(lider_vendas_id=user.id)

    items = query.all()
    return jsonify({"data": [_serialize(a) for a in items]})


@leadership_bp.route("/appraisal/<appraisal_id>/finalize", methods=["POST"])
@require_auth
def finalize(appraisal_id):
    """Drive a leadership appraisal straight to LOCKED via the state machine."""
    user = g.current_user
    if user.role != UserRole.ADMIN:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    appraisal = db.session.get(LiderVendasQuarterAppraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404
    if appraisal.status == AppraisalStatus.LOCKED:
        return jsonify({"error": {"code": "ALREADY_FINAL"}}), 409

    chain = [
        AppraisalStatus.VALIDATING,
        AppraisalStatus.LIDER_REVIEW,
        AppraisalStatus.REVOPS_REVIEW,
        AppraisalStatus.LOCKED,
    ]
    try:
        for s in chain:
            if appraisal.status == s:
                continue
            transition_lider_vendas_appraisal(appraisal, s)
    except InvalidTransitionError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "INVALID_TRANSITION", "message": str(e)}}), 422

    db.session.commit()
    return jsonify({"data": _serialize(appraisal)})


@leadership_bp.route("/appraisal/<appraisal_id>/transition", methods=["POST"])
@require_auth
def transition_endpoint(appraisal_id):
    """Move a leadership appraisal to a new status.

    Body: {"to": "VALIDATING" | "LIDER_REVIEW" | ...}
    Coarse role check: ADMIN drives anything; the LIDER_VENDAS who owns
    the row can move VALIDATING → LIDER_REVIEW (auto-validates own row).
    """
    user = g.current_user
    appraisal = db.session.get(LiderVendasQuarterAppraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404

    body = request.get_json() or {}
    to_status_str = body.get("to")
    if not to_status_str:
        return jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "'to' field required"},
        }), 400

    try:
        new_status = AppraisalStatus(to_status_str)
    except ValueError:
        valid = [s.value for s in AppraisalStatus]
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": f"Invalid status. Valid: {valid}"},
        }), 400

    if user.role == UserRole.ADMIN:
        pass
    elif user.role == UserRole.LIDER_VENDAS:
        if str(appraisal.lider_vendas_id) != str(user.id):
            return jsonify({"error": {"code": "FORBIDDEN"}}), 403
        if not (appraisal.status == AppraisalStatus.VALIDATING
                and new_status == AppraisalStatus.LIDER_REVIEW):
            return jsonify({"error": {"code": "FORBIDDEN"}}), 403
    else:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    try:
        transition_lider_vendas_appraisal(appraisal, new_status)
        db.session.commit()
    except InvalidTransitionError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "INVALID_TRANSITION", "message": str(e)}}), 422

    # Issue #37a: a Líder validating own row may have been the last gate
    # holding the global Appraisal in VALIDATING. Re-evaluate.
    start_month = (appraisal.quarter - 1) * 3 + 1
    global_appraisals = Appraisal.query.filter(
        Appraisal.year == appraisal.year,
        Appraisal.month.in_([start_month, start_month + 1, start_month + 2]),
        Appraisal.status == AppraisalStatus.VALIDATING,
    ).all()
    if global_appraisals:
        try:
            advanced = False
            for global_appraisal in global_appraisals:
                advanced = (
                    maybe_auto_advance_appraisal_after_validation(global_appraisal)
                    or advanced
                )
            if advanced:
                db.session.commit()
        except Exception:
            db.session.rollback()

    return jsonify({"data": _serialize(appraisal)})


def _serialize(a):
    return {
        "id": str(a.id),
        "lider_vendas_id": str(a.lider_vendas_id),
        "lider_vendas_name": a.lider_vendas.name if a.lider_vendas else None,
        "quarter": a.quarter,
        "year": a.year,
        "meta_mrr": str(a.meta_mrr) if a.meta_mrr is not None else None,
        "meta_sql": a.meta_sql,
        "realizado_mrr": str(a.realizado_mrr) if a.realizado_mrr is not None else None,
        "realizado_sql": a.realizado_sql,
        "pct_mrr": str(a.pct_mrr) if a.pct_mrr is not None else None,
        "pct_sql": str(a.pct_sql) if a.pct_sql is not None else None,
        "multiplicador": str(a.multiplicador) if a.multiplicador is not None else None,
        "bonus_amount": str(a.bonus_amount) if a.bonus_amount is not None else None,
        "status": a.status.value if a.status else None,
        "is_final": a.is_final,
        "has_contestation": bool(a.has_contestation),
        "contestation_note": a.contestation_note,
        "resolution_note": a.resolution_note,
    }

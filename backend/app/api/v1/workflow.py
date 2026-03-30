from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth, require_role
from app.models import Appraisal, AppraisalStatus, UserRole
from app.api.middlewares import paginate_query, log_audit
from app.extensions import db
from app.modules.workflow.state_machine import (
    start_appraisal,
    transition_appraisal,
    InvalidTransitionError,
)

workflow_bp = Blueprint("workflow", __name__, url_prefix="/api/v1/appraisals")


@workflow_bp.route("")
@require_auth
def list_appraisals():
    """List appraisals."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = Appraisal.query.order_by(Appraisal.year.desc(), Appraisal.quarter.desc())

    status = request.args.get("status")
    if status:
        query = query.filter(Appraisal.status == status)

    items, meta = paginate_query(query, page, per_page)

    return jsonify({
        "data": [_serialize_appraisal(a) for a in items],
        "meta": meta,
    })


@workflow_bp.route("/<appraisal_id>")
@require_auth
def get_appraisal(appraisal_id):
    """Get a single appraisal."""
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Appraisal not found"}}), 404

    return jsonify({"data": _serialize_appraisal(appraisal, detail=True)})


@workflow_bp.route("", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.GERENTE)
def create_appraisal():
    """Create a new appraisal in DRAFT status."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400

    quarter = data.get("quarter")
    year = data.get("year")

    if not quarter or not year:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "quarter and year required"}}), 400

    user = g.current_user

    try:
        appraisal = start_appraisal(quarter=quarter, year=year, created_by=user.id)
        log_audit("appraisals", appraisal.id, "CREATE", new_values={"quarter": quarter, "year": year})
        db.session.commit()
    except InvalidTransitionError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "CONFLICT", "message": str(e)}}), 409

    return jsonify({"data": _serialize_appraisal(appraisal)}), 201


@workflow_bp.route("/<appraisal_id>/transition", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.GERENTE, UserRole.FINANCE)
def transition(appraisal_id):
    """Transition an appraisal to a new status.

    Body: { "to": "CALCULATING" | "VALIDATING" | "REVIEWING" | "APPROVED" | "LOCKED", ... }
    """
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Appraisal not found"}}), 404

    data = request.get_json() or {}
    to_status_str = data.get("to")
    if not to_status_str:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "'to' field required"}}), 400

    try:
        new_status = AppraisalStatus(to_status_str)
    except ValueError:
        valid = [s.value for s in AppraisalStatus]
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": f"Invalid status. Valid: {valid}"}}), 400

    user = g.current_user
    old_status = appraisal.status.value

    kwargs = {}
    if new_status == AppraisalStatus.VALIDATING:
        kwargs["validation_deadline"] = data.get("validation_deadline")
    if new_status == AppraisalStatus.LOCKED:
        kwargs["approved_by"] = user.id

    try:
        transition_appraisal(appraisal, new_status, **kwargs)
        log_audit(
            "appraisals", appraisal.id, "UPDATE",
            old_values={"status": old_status},
            new_values={"status": new_status.value},
        )
        db.session.commit()
    except InvalidTransitionError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "INVALID_TRANSITION", "message": str(e)}}), 422

    return jsonify({"data": _serialize_appraisal(appraisal)})


def _serialize_appraisal(appraisal, detail=False):
    data = {
        "id": str(appraisal.id),
        "quarter": appraisal.quarter,
        "year": appraisal.year,
        "status": appraisal.status.value,
        "validation_deadline": appraisal.validation_deadline.isoformat() if appraisal.validation_deadline else None,
        "created_by": str(appraisal.created_by),
        "created_at": appraisal.created_at.isoformat() if appraisal.created_at else None,
        "locked_at": appraisal.locked_at.isoformat() if appraisal.locked_at else None,
    }
    if detail:
        data["approved_by_finance"] = str(appraisal.approved_by_finance) if appraisal.approved_by_finance else None
        data["validation_count"] = len(appraisal.validations)
    return data

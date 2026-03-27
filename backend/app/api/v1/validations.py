from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth, require_role
from app.models import EvValidation, ValidationStatus, UserRole
from app.api.middlewares import paginate_query, log_audit
from app.extensions import db

validations_bp = Blueprint("validations", __name__, url_prefix="/api/v1/validations")


@validations_bp.route("")
@require_auth
def list_validations():
    """List validations with role-based filtering."""
    user = g.current_user
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = EvValidation.query

    # EVs/CNs only see their own
    if user.role in (UserRole.EV, UserRole.CN):
        query = query.filter(EvValidation.ev_id == user.id)

    appraisal_id = request.args.get("appraisal_id")
    if appraisal_id:
        query = query.filter(EvValidation.appraisal_id == appraisal_id)

    ev_id = request.args.get("ev_id")
    if ev_id:
        query = query.filter(EvValidation.ev_id == ev_id)

    status = request.args.get("status")
    if status:
        query = query.filter(EvValidation.status == status)

    query = query.order_by(EvValidation.created_at.desc())
    items, meta = paginate_query(query, page, per_page)

    return jsonify({
        "data": [_serialize_validation(v) for v in items],
        "meta": meta,
    })


@validations_bp.route("/<validation_id>/approve", methods=["POST"])
@require_auth
def approve_validation(validation_id):
    """EV approves their own validation."""
    user = g.current_user
    validation = db.session.get(EvValidation, validation_id)
    if validation is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Validation not found"}}), 404

    if user.role in (UserRole.EV, UserRole.CN) and validation.ev_id != user.id:
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Access denied"}}), 403

    if validation.status not in (ValidationStatus.PENDING,):
        return jsonify({
            "error": {"code": "CONFLICT", "message": f"Cannot approve: status is {validation.status.value}"}
        }), 409

    old_status = validation.status.value
    validation.status = ValidationStatus.APPROVED
    log_audit("ev_validations", validation.id, "UPDATE",
              old_values={"status": old_status},
              new_values={"status": ValidationStatus.APPROVED.value})
    db.session.commit()

    return jsonify({"data": _serialize_validation(validation)})


@validations_bp.route("/<validation_id>/contest", methods=["POST"])
@require_auth
def contest_validation(validation_id):
    """EV contests their own validation."""
    user = g.current_user
    validation = db.session.get(EvValidation, validation_id)
    if validation is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Validation not found"}}), 404

    if user.role in (UserRole.EV, UserRole.CN) and validation.ev_id != user.id:
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Access denied"}}), 403

    if validation.status not in (ValidationStatus.PENDING,):
        return jsonify({
            "error": {"code": "CONFLICT", "message": f"Cannot contest: status is {validation.status.value}"}
        }), 409

    data = request.get_json() or {}
    comment = data.get("comment", "")

    old_status = validation.status.value
    validation.status = ValidationStatus.CONTESTED
    validation.comment = comment
    validation.contested_at = datetime.now(timezone.utc)
    log_audit("ev_validations", validation.id, "UPDATE",
              old_values={"status": old_status},
              new_values={"status": ValidationStatus.CONTESTED.value, "comment": comment})
    db.session.commit()

    return jsonify({"data": _serialize_validation(validation)})


@validations_bp.route("/<validation_id>/resolve", methods=["POST"])
@require_role(UserRole.ADMIN, UserRole.GERENTE)
def resolve_validation(validation_id):
    """RevOps/Manager resolves a contested validation."""
    validation = db.session.get(EvValidation, validation_id)
    if validation is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Validation not found"}}), 404

    if validation.status != ValidationStatus.CONTESTED:
        return jsonify({
            "error": {"code": "CONFLICT", "message": "Validation is not in CONTESTED status"}
        }), 409

    data = request.get_json() or {}
    resolution_comment = data.get("resolution_comment", "")
    user = g.current_user

    old_status = validation.status.value
    validation.status = ValidationStatus.RESOLVED
    validation.resolution_comment = resolution_comment
    validation.resolved_at = datetime.now(timezone.utc)
    validation.resolved_by = user.id
    log_audit("ev_validations", validation.id, "UPDATE",
              old_values={"status": old_status},
              new_values={"status": ValidationStatus.RESOLVED.value})
    db.session.commit()

    return jsonify({"data": _serialize_validation(validation)})


def _serialize_validation(v):
    return {
        "id": str(v.id),
        "appraisal_id": str(v.appraisal_id),
        "policy_id": str(v.policy_id),
        "ev_id": str(v.ev_id),
        "status": v.status.value,
        "comment": v.comment,
        "resolution_comment": v.resolution_comment,
        "contested_at": v.contested_at.isoformat() if v.contested_at else None,
        "resolved_at": v.resolved_at.isoformat() if v.resolved_at else None,
        "resolved_by": str(v.resolved_by) if v.resolved_by else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }

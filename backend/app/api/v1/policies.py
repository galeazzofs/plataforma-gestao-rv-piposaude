from datetime import date
from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth
from app.models import Policy, UserRole
from app.api.middlewares import paginate_query
from app.extensions import db

policies_bp = Blueprint("policies", __name__, url_prefix="/api/v1/policies")


@policies_bp.route("")
@require_auth
def list_policies():
    """List policies with role-based filtering."""
    user = g.current_user
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = Policy.query

    # Role-based filtering
    if user.role in (UserRole.EV, UserRole.CN):
        query = query.filter(Policy.ev_id == user.id)
    elif user.role == UserRole.GERENTE:
        from app.models import User
        team_member_ids = [
            u.id for u in User.query.filter_by(team_id=user.team_id, active=True).all()
        ]
        query = query.filter(Policy.ev_id.in_(team_member_ids))
    # ADMIN and FINANCE see all

    # Optional filters
    ev_id = request.args.get("ev_id")
    if ev_id:
        query = query.filter(Policy.ev_id == ev_id)

    client_id = request.args.get("client_id")
    if client_id:
        query = query.filter(Policy.client_id == client_id)

    # TODO: quarter/year filtering requires PostgreSQL extract — use date range instead
    quarter = request.args.get("quarter", type=int)
    year = request.args.get("year", type=int)
    if quarter and year:
        # Build date range for the quarter
        quarter_start_month = (quarter - 1) * 3 + 1
        quarter_end_month = quarter * 3
        start_date = date(year, quarter_start_month, 1)
        if quarter_end_month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, quarter_end_month + 1, 1)
        query = query.filter(
            Policy.closed_date >= start_date,
            Policy.closed_date < end_date,
        )

    status = request.args.get("status")
    if status:
        query = query.filter(Policy.commission_status == status)

    query = query.order_by(Policy.closed_date.desc())
    items, meta = paginate_query(query, page, per_page)

    return jsonify({
        "data": [_serialize_policy(p) for p in items],
        "meta": meta,
    })


@policies_bp.route("/<policy_id>")
@require_auth
def get_policy(policy_id):
    """Get a single policy detail."""
    user = g.current_user
    policy = db.session.get(Policy, policy_id)
    if policy is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Policy not found"}}), 404

    # Access control
    if user.role in (UserRole.EV, UserRole.CN) and policy.ev_id != user.id:
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Access denied"}}), 403

    return jsonify({"data": _serialize_policy(policy, detail=True)})


@policies_bp.route("/<policy_id>/installments", methods=["PATCH"])
@require_auth
def update_installments(policy_id):
    """Manually update installments_paid and first_payment_real for a policy.

    Used by RevOps to set the correct state for policies that were already
    in payment before the platform existed.
    Body: {installments_paid: 8, first_payment_real: "2025-09-01", commission_status: "IN_PAYMENT"}
    """
    from app.models import CommissionStatus
    from app.api.middlewares import log_audit

    user = g.current_user
    if user.role not in (UserRole.ADMIN, UserRole.GERENTE):
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Admin or Gerente required"}}), 403

    policy = db.session.get(Policy, policy_id)
    if policy is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Policy not found"}}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400

    old_values = {
        "installments_paid": policy.installments_paid,
        "initial_installments_paid": policy.initial_installments_paid,
        "first_payment_real": policy.first_payment_real.isoformat() if policy.first_payment_real else None,
        "commission_status": policy.commission_status.value,
    }

    if "initial_installments_paid" in data:
        val = int(data["initial_installments_paid"])
        if val < 0 or val > 12:
            return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "initial_installments_paid must be 0-12"}}), 400
        policy.initial_installments_paid = val
        # Se installments_paid for menor que o valor inicial, ajusta automaticamente
        if policy.installments_paid < val:
            policy.installments_paid = val

    if "installments_paid" in data:
        val = int(data["installments_paid"])
        if val < 0 or val > 12:
            return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "installments_paid must be 0-12"}}), 400
        if val < policy.initial_installments_paid:
            return jsonify({"error": {"code": "VALIDATION_ERROR", "message": f"installments_paid cannot be less than initial_installments_paid ({policy.initial_installments_paid})"}}), 400
        policy.installments_paid = val

    if "first_payment_real" in data:
        if data["first_payment_real"]:
            policy.first_payment_real = date.fromisoformat(data["first_payment_real"])
        else:
            policy.first_payment_real = None

    if "commission_status" in data:
        try:
            policy.commission_status = CommissionStatus(data["commission_status"])
        except ValueError:
            valid = [s.value for s in CommissionStatus]
            return jsonify({"error": {"code": "VALIDATION_ERROR", "message": f"Invalid status. Valid: {valid}"}}), 400

    # Auto-derive status from installments if not explicitly set
    if "commission_status" not in data:
        if policy.installments_paid >= 12:
            policy.commission_status = CommissionStatus.SETTLED
        elif policy.installments_paid > 0 and policy.commission_status == CommissionStatus.PROJECTED:
            policy.commission_status = CommissionStatus.IN_PAYMENT

    log_audit(
        "policies", policy.id, "UPDATE",
        old_values=old_values,
        new_values={
            "installments_paid": policy.installments_paid,
            "initial_installments_paid": policy.initial_installments_paid,
            "first_payment_real": policy.first_payment_real.isoformat() if policy.first_payment_real else None,
            "commission_status": policy.commission_status.value,
        },
    )
    db.session.commit()

    return jsonify({"data": _serialize_policy(policy, detail=True)})


def _serialize_policy(policy, detail=False):
    data = {
        "id": str(policy.id),
        "hubspot_ticket_id": policy.hubspot_ticket_id,
        "ev_id": str(policy.ev_id) if policy.ev_id else None,
        "client_id": str(policy.client_id) if policy.client_id else None,
        "client_name": policy.client.name if policy.client else None,
        "benefit_type": policy.benefit_type.value if policy.benefit_type else None,
        "segment": policy.segment.value if policy.segment else None,
        "mrr_projected": str(policy.mrr_projected) if policy.mrr_projected else None,
        "mrr_for_commission": str(policy.mrr_for_commission) if policy.mrr_for_commission else None,
        "closed_date": policy.closed_date.isoformat() if policy.closed_date else None,
        "installments_paid": policy.installments_paid,
        "initial_installments_paid": policy.initial_installments_paid,
        "commission_status": policy.commission_status.value,
    }
    if detail:
        data.update({
            "deal_id": policy.deal_id,
            "headcount": policy.headcount,
            "mrr_post_deploy": str(policy.mrr_post_deploy) if policy.mrr_post_deploy else None,
            "mrr_actual": str(policy.mrr_actual) if policy.mrr_actual else None,
            "deploy_date": policy.deploy_date.isoformat() if policy.deploy_date else None,
            "first_payment_prev": policy.first_payment_prev.isoformat() if policy.first_payment_prev else None,
            "first_payment_real": policy.first_payment_real.isoformat() if policy.first_payment_real else None,
            "partner_operator": policy.partner_operator,
            "deal_stage": policy.deal_stage,
        })
    return data

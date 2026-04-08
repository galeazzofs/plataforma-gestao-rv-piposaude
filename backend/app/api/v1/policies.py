from datetime import date, datetime
from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth, require_role
from app.models import Policy, UserRole
from app.models.policy import Segment
from app.api.middlewares import paginate_query, log_audit
from app.modules.policies.filters import active_ev_policies_query
from app.extensions import db

policies_bp = Blueprint("policies", __name__, url_prefix="/api/v1/policies")


EDITABLE_FIELDS = {
    "ev_id",
    "first_payment_real",
    "closed_date",
    "initial_installments_paid",
    "segment",
    "partner_operator",
    "client_id",
}


def _coerce_field(field, value):
    """Coerce a JSON value into the right Python type for the Policy column."""
    if value is None:
        return None
    if field in ("first_payment_real", "closed_date"):
        if isinstance(value, str):
            return datetime.fromisoformat(value).date()
        return value
    if field == "segment":
        return Segment(value)
    if field == "initial_installments_paid":
        return int(value)
    return value


@policies_bp.route("")
@require_auth
def list_policies():
    """List policies with role-based filtering."""
    user = g.current_user
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    # Base query: only policies of active EVs (global filter)
    query = active_ev_policies_query()

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


@policies_bp.route("/<policy_id>", methods=["PUT"])
@require_role(UserRole.ADMIN)
def update_policy(policy_id):
    """Manual override of Policy fields. Sets is_locked=True so the HubSpot
    sync will not clobber these fields on next run. Writes audit log entry."""
    policy = db.session.get(Policy, policy_id)
    if policy is None:
        return jsonify({
            "error": {"code": "NOT_FOUND", "message": "Policy not found"}
        }), 404

    data = request.get_json() or {}
    old_values = {}
    new_values = {}

    for field in EDITABLE_FIELDS:
        if field not in data:
            continue
        try:
            new_value = _coerce_field(field, data[field])
        except (ValueError, TypeError) as e:
            return jsonify({
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": f"Invalid value for {field}: {e}",
                }
            }), 400
        old_value = getattr(policy, field, None)
        if old_value != new_value:
            old_values[field] = (
                old_value.isoformat() if hasattr(old_value, "isoformat")
                else (old_value.value if hasattr(old_value, "value")
                      else str(old_value) if old_value is not None else None)
            )
            new_values[field] = (
                new_value.isoformat() if hasattr(new_value, "isoformat")
                else (new_value.value if hasattr(new_value, "value")
                      else str(new_value) if new_value is not None else None)
            )
            setattr(policy, field, new_value)

    if new_values:
        policy.is_locked = True
        log_audit(
            "policies", policy.id, "UPDATE",
            old_values=old_values, new_values=new_values,
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

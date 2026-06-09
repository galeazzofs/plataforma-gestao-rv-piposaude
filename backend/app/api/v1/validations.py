from collections import defaultdict
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, g
from sqlalchemy.orm import joinedload
from app.auth.decorators import require_auth, require_role
from app.models import (
    Appraisal, Commission, EvValidation, FinancialImport, Policy, User,
    ValidationStatus, UserRole,
)
from app.api.middlewares import paginate_query, log_audit
from app.extensions import db
from app.modules.workflow.state_machine import (
    maybe_auto_advance_appraisal_after_validation,
    maybe_dm_lider_team_validated,
)

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
    elif user.role == UserRole.LIDER_VENDAS:
        team_member_ids = [
            u.id for u in User.query.filter_by(
                team_id=user.team_id, active=True, left_company=False,
            ).all()
        ]
        query = query.filter(EvValidation.ev_id.in_(team_member_ids))

    appraisal_id = request.args.get("appraisal_id")
    if appraisal_id:
        query = query.filter(EvValidation.appraisal_id == appraisal_id)

    ev_id = request.args.get("ev_id")
    if ev_id:
        query = query.filter(EvValidation.ev_id == ev_id)

    status = request.args.get("status")
    if status:
        query = query.filter(EvValidation.status == status)

    # Eager-load the to-one relationships the serializer reads so the page
    # doesn't lazy-load appraisal / policy / client / ev once per row.
    query = query.options(
        joinedload(EvValidation.appraisal),
        joinedload(EvValidation.policy).joinedload(Policy.client),
        joinedload(EvValidation.ev),
    )
    query = query.order_by(EvValidation.created_at.desc())
    items, meta = paginate_query(query, page, per_page)

    # Batch-load commissions + matched NFs for the whole page in two queries,
    # keyed on (policy_id, month, year), instead of two queries per row.
    policy_ids = {v.policy_id for v in items if v.policy_id}
    comm_by_key = {}
    nfs_by_key = defaultdict(list)
    if policy_ids:
        for c in Commission.query.filter(
            Commission.policy_id.in_(policy_ids)
        ).all():
            comm_by_key[(c.policy_id, c.month, c.year)] = c
        for n in FinancialImport.query.filter(
            FinancialImport.policy_id.in_(policy_ids),
            FinancialImport.match_status == "MATCHED",
        ).all():
            nfs_by_key[(n.policy_id, n.month, n.year)].append(n)

    def _serialize(v):
        appraisal = v.appraisal
        key = (v.policy_id, appraisal.month, appraisal.year) if appraisal else None
        nfs = sorted(nfs_by_key.get(key, []), key=_nf_sort_key) if key else []
        return _serialize_validation(
            v, commission=comm_by_key.get(key) if key else None, nfs=nfs,
        )

    return jsonify({
        "data": [_serialize(v) for v in items],
        "meta": meta,
    })


@validations_bp.route("/<validation_id>/approve", methods=["POST"])
@require_auth
def approve_validation(validation_id):
    """EV approves their own validation.

    Idempotent: re-approving a validation that is already APPROVED or
    AUTO_APPROVED is a no-op that returns 200, so a double-click or an
    "Aprovar todos" that overlaps a single "Aprovar" can never 409. Only
    CONTESTED / RESOLVED are genuine conflicts — silently flipping a
    contestation to approved would lose the EV's objection.
    """
    user = g.current_user
    validation = db.session.get(EvValidation, validation_id)
    if validation is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Validation not found"}}), 404

    if user.role in (UserRole.EV, UserRole.CN) and validation.ev_id != user.id:
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Access denied"}}), 403

    if validation.status in (ValidationStatus.APPROVED, ValidationStatus.AUTO_APPROVED):
        # Desired state already reached — no status transition. We still
        # re-run the (idempotent, VALIDATING-guarded) post hooks: if the first
        # approve committed the row but its advance hook failed/rolled back,
        # this lets a re-approve re-drive the stalled Appraisal advance.
        _post_validation_hooks(validation)
        return jsonify({"data": _serialize_validation(validation)})

    if validation.status != ValidationStatus.PENDING:
        return jsonify({
            "error": {"code": "CONFLICT", "message": f"Cannot approve: status is {validation.status.value}"}
        }), 409

    old_status = validation.status.value
    validation.status = ValidationStatus.APPROVED
    log_audit("ev_validations", validation.id, "UPDATE",
              old_values={"status": old_status},
              new_values={"status": ValidationStatus.APPROVED.value})
    db.session.commit()

    _post_validation_hooks(validation)

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
@require_role(UserRole.ADMIN, UserRole.LIDER_VENDAS)
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
    if user.role == UserRole.LIDER_VENDAS:
        ev = db.session.get(User, validation.ev_id)
        if (
            ev is None
            or ev.left_company
            or str(ev.team_id) != str(user.team_id)
        ):
            return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    old_status = validation.status.value
    validation.status = ValidationStatus.RESOLVED
    validation.resolution_comment = resolution_comment
    validation.resolved_at = datetime.now(timezone.utc)
    validation.resolved_by = user.id
    log_audit("ev_validations", validation.id, "UPDATE",
              old_values={"status": old_status},
              new_values={"status": ValidationStatus.RESOLVED.value})
    db.session.commit()

    _post_validation_hooks(validation)

    return jsonify({"data": _serialize_validation(validation)})


def _post_validation_hooks(validation: EvValidation):
    """Run post-approval/post-resolve checks: DM the team Líder when their
    team finished, and auto-advance the global Appraisal if every team
    has finished and every Líder validated own. Issues #37a + #38.

    All work runs in a fresh transaction so a hook failure never poisons
    the parent commit. The validation row is already persisted by the
    time we get here.
    """
    appraisal = db.session.get(Appraisal, validation.appraisal_id)
    if appraisal is None:
        return

    ev = db.session.get(User, validation.ev_id)
    team_id = ev.team_id if ev is not None else None

    try:
        maybe_dm_lider_team_validated(appraisal, team_id)
        if maybe_auto_advance_appraisal_after_validation(appraisal):
            db.session.commit()
    except Exception:
        db.session.rollback()


# Sentinel so callers can pass a pre-loaded (possibly None) commission / nfs.
_UNSET = object()


def _nf_sort_key(nf):
    # Deterministic, DB-portable "oldest first": NULL data_recebimento last,
    # then by date. Avoids relying on backend-specific NULLS ordering.
    return (nf.data_recebimento is None, nf.data_recebimento)


def _matched_period_nfs(policy_id, month, year):
    """Matched NFs for a policy in a competência, oldest first. This is the
    per-apólice breakdown the EV drills into from the validation row."""
    if policy_id is None or month is None or year is None:
        return []
    nfs = FinancialImport.query.filter_by(
        policy_id=policy_id, month=month, year=year, match_status="MATCHED",
    ).all()
    return sorted(nfs, key=_nf_sort_key)


def _serialize_validation(v, commission=_UNSET, nfs=_UNSET):
    """Serialize one validation. ``commission`` and ``nfs`` may be supplied by
    the list endpoint (batch-loaded once for the whole page) to avoid an N+1;
    when omitted they are loaded lazily for the single-row callers."""
    appraisal = v.appraisal or db.session.get(Appraisal, v.appraisal_id)
    policy = v.policy or db.session.get(Policy, v.policy_id)
    if commission is _UNSET:
        commission = None
        if appraisal is not None:
            commission = Commission.query.filter_by(
                policy_id=v.policy_id,
                month=appraisal.month,
                year=appraisal.year,
            ).first()

    mrr = policy.mrr_for_commission if policy is not None else None
    commission_amount = None
    if commission is not None:
        commission_amount = commission.monthly_actual or commission.total_actual

    if nfs is _UNSET:
        nfs = _matched_period_nfs(
            v.policy_id,
            appraisal.month if appraisal else None,
            appraisal.year if appraisal else None,
        )
    nf_liquido_total = float(sum(n.nf_valor_liquido for n in nfs)) if nfs else 0.0

    return {
        "id": str(v.id),
        "appraisal_id": str(v.appraisal_id),
        "policy_id": str(v.policy_id),
        "ev_id": str(v.ev_id),
        "ev_name": v.ev.name if v.ev else None,
        "month": appraisal.month if appraisal else None,
        "year": appraisal.year if appraisal else None,
        "appraisal_status": (
            appraisal.status.value if appraisal and appraisal.status else None
        ),
        "client_name": (
            policy.client.name if policy is not None and policy.client else None
        ),
        "benefit_type": (
            policy.benefit_type.value
            if policy is not None and policy.benefit_type else None
        ),
        "numero_apolice": (
            policy.numero_apolice or policy.hubspot_apolice_id
            if policy is not None else None
        ),
        "operadora": policy.partner_operator if policy is not None else None,
        "segment": (
            policy.segment.value
            if policy is not None and policy.segment else None
        ),
        "mrr": str(mrr) if mrr is not None else None,
        "commission_monthly": (
            str(commission_amount) if commission_amount is not None else None
        ),
        "commission_pct": (
            str(commission.commission_pct)
            if commission is not None and commission.commission_pct is not None
            else None
        ),
        # Achievement comes back already as a percentage number (0.75 → 75.0),
        # matching the appraisal-review payload the deep view renders.
        "achievement_pct": (
            float(commission.achievement_pct * 100)
            if commission is not None and commission.achievement_pct is not None
            else None
        ),
        # 12-month clock is count-based; first_payment_real is advisory only.
        "installments_paid": (
            policy.installments_paid or 0 if policy is not None else None
        ),
        "closed_date": (
            policy.closed_date.isoformat()
            if policy is not None and policy.closed_date else None
        ),
        "nf_liquido_total": nf_liquido_total,
        "nfs": [
            {
                "data_recebimento": (
                    n.data_recebimento.isoformat() if n.data_recebimento else None
                ),
                "tipo_receita": n.tipo_receita,
                "nf_liquido": float(n.nf_valor_liquido),
            }
            for n in nfs
        ],
        "status": v.status.value,
        "comment": v.comment,
        "resolution_comment": v.resolution_comment,
        "contested_at": v.contested_at.isoformat() if v.contested_at else None,
        "resolved_at": v.resolved_at.isoformat() if v.resolved_at else None,
        "resolved_by": str(v.resolved_by) if v.resolved_by else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }

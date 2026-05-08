from collections import defaultdict
from decimal import Decimal

from flask import Blueprint, jsonify, request, g

from app.auth.decorators import require_auth, require_role
from app.models import (
    Appraisal, AppraisalStatus, UserRole,
    Commission, EvQuarterAchievement, FinancialImport, Policy, User,
)
from app.api.middlewares import paginate_query, log_audit
from app.extensions import db
from app.modules.workflow.state_machine import (
    start_appraisal,
    transition_appraisal,
    InvalidTransitionError,
)
from app.modules.commissions.calculator import MissingAchievementsError
from app.modules.financial.monthly_engine import COMISSAO, classify_revenue_type

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
@require_role(UserRole.ADMIN, UserRole.LIDER_VENDAS)
def create_appraisal():
    """Create a new appraisal in DRAFT status."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "JSON body required"}}), 400

    quarter = data.get("quarter")
    year = data.get("year")

    if not quarter or not year:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "quarter and year required"}}), 400

    try:
        quarter = int(quarter)
        year = int(year)
    except (ValueError, TypeError):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "quarter and year must be integers"}}), 400

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
@require_role(UserRole.ADMIN, UserRole.LIDER_VENDAS, UserRole.FINANCE)
def transition(appraisal_id):
    """Transition an appraisal to a new status.

    Body: { "to": "CALCULATING" | "VALIDATING" | "LIDER_REVIEW" | "REVOPS_REVIEW" | "LOCKED", ... }
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
    except MissingAchievementsError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "MISSING_ACHIEVEMENTS", "message": str(e), "missing": e.missing}}), 422

    return jsonify({"data": _serialize_appraisal(appraisal, detail=True)})


@workflow_bp.route("/<appraisal_id>", methods=["DELETE"])
@require_role(UserRole.ADMIN)
def delete_appraisal(appraisal_id):
    """Delete an appraisal and its associated commissions / NF matches."""
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Appraisal not found"}}), 404

    quarter, year = appraisal.quarter, appraisal.year

    # Delete ALL commissions for this quarter (including is_final when LOCKED)
    Commission.query.filter_by(quarter=quarter, year=year).delete()

    # Reset NF match status back to UNMATCHED
    FinancialImport.query.filter(
        FinancialImport.quarter == quarter,
        FinancialImport.year == year,
    ).update({
        FinancialImport.match_status: 'UNMATCHED',
        FinancialImport.policy_id: None,
        FinancialImport.matched_at: None,
    })

    log_audit("appraisals", appraisal.id, "DELETE",
              old_values={"quarter": quarter, "year": year, "status": appraisal.status.value})

    db.session.delete(appraisal)
    db.session.commit()

    return jsonify({"data": {"deleted": True}}), 200


@workflow_bp.route("/<appraisal_id>/recalculate", methods=["POST"])
@require_role(UserRole.ADMIN)
def recalculate(appraisal_id):
    """Re-run the calculator for this appraisal's (quarter, year).

    Allowed when appraisal is in CALCULATING / VALIDATING / LIDER_REVIEW / REVOPS_REVIEW.
    Blocked when LOCKED. Returns the enriched detail payload.
    """
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({
            "error": {"code": "NOT_FOUND", "message": "Appraisal not found"},
        }), 404

    if appraisal.status == AppraisalStatus.LOCKED:
        return jsonify({
            "error": {
                "code": "CONFLICT",
                "message": "Apuração está LOCKED — recalculate não permitido",
            },
        }), 409

    from app.modules.commissions.calculator import (
        run_quarterly_appraisal, MissingAchievementsError,
    )
    try:
        run_quarterly_appraisal(appraisal.quarter, appraisal.year)
        db.session.commit()
    except MissingAchievementsError as e:
        db.session.rollback()
        return jsonify({
            "error": {
                "code": "MISSING_ACHIEVEMENTS",
                "message": str(e),
                "missing": e.missing,
            },
        }), 422

    return jsonify({"data": _serialize_appraisal(appraisal, detail=True)})


# ── Serializer ───────────────────────────────────────────────────────


def _serialize_appraisal(appraisal, detail=False):
    data = {
        "id": str(appraisal.id),
        "quarter": appraisal.quarter,
        "year": appraisal.year,
        "status": appraisal.status.value,
        "validation_deadline": (
            appraisal.validation_deadline.isoformat()
            if appraisal.validation_deadline else None
        ),
        "created_by": str(appraisal.created_by),
        "created_at": (
            appraisal.created_at.isoformat() if appraisal.created_at else None
        ),
        "locked_at": (
            appraisal.locked_at.isoformat() if appraisal.locked_at else None
        ),
    }
    if detail:
        data["approved_by_finance"] = (
            str(appraisal.approved_by_finance)
            if appraisal.approved_by_finance else None
        )
        data["validation_count"] = len(appraisal.validations)
        data.update(_build_appraisal_detail(appraisal))
    return data


def _build_appraisal_detail(appraisal):
    """Build the rich review payload: ev_summary with nested policies and NFs,
    plus unmatched / expired / nao_suportado tabs and totals."""
    quarter, year = appraisal.quarter, appraisal.year

    commissions = Commission.query.filter_by(quarter=quarter, year=year).all()
    nfs_matched = FinancialImport.query.filter_by(
        quarter=quarter, year=year, match_status='MATCHED',
    ).all()
    nfs_finalized = FinancialImport.query.filter_by(
        quarter=quarter, year=year, match_status='APOLICE_FINALIZADA',
    ).all()

    nfs_by_policy = defaultdict(list)
    for nf in nfs_matched:
        if nf.policy_id:
            nfs_by_policy[nf.policy_id].append(nf)

    finalized_policy_ids = {nf.policy_id for nf in nfs_finalized if nf.policy_id}
    policy_ids = (
        {c.policy_id for c in commissions}
        | set(nfs_by_policy.keys())
        | finalized_policy_ids
    )
    policies = (
        {p.id: p for p in Policy.query.filter(Policy.id.in_(policy_ids)).all()}
        if policy_ids else {}
    )

    by_ev = defaultdict(list)
    for c in commissions:
        by_ev[c.ev_id].append(c)

    ev_summary = []
    for ev_id, ev_commissions in by_ev.items():
        ev = db.session.get(User, ev_id)
        ach_curr = EvQuarterAchievement.query.filter_by(
            ev_id=ev_id, quarter=quarter, year=year,
        ).first()

        policy_blocks = []
        for c in ev_commissions:
            p = policies.get(c.policy_id)
            if p is None:
                continue
            nfs = nfs_by_policy.get(p.id, [])
            policy_blocks.append({
                "policy_id": str(p.id),
                "client_name": p.client.name if p.client else None,
                "operadora": p.partner_operator,
                "produto": p.benefit_type.value if p.benefit_type else None,
                "segment": p.segment.value if p.segment else None,
                "first_payment_real": (
                    p.first_payment_real.isoformat() if p.first_payment_real else None
                ),
                "closed_date": (
                    p.closed_date.isoformat() if p.closed_date else None
                ),
                "achievement_used_pct": (
                    float(c.achievement_pct * 100) if c.achievement_pct else 0.0
                ),
                "commission_pct": (
                    float(c.commission_pct) if c.commission_pct else 0.0
                ),
                "subtotal": float(c.total_actual or 0),
                "nfs": [
                    {
                        "data_recebimento": (
                            nf.data_recebimento.isoformat()
                            if nf.data_recebimento else None
                        ),
                        "tipo_receita": nf.tipo_receita,
                        "nf_liquido": float(nf.nf_valor_liquido),
                    }
                    for nf in nfs
                ],
            })

        ev_summary.append({
            "ev_id": str(ev_id),
            "ev_name": ev.name if ev else "—",
            "achievement_pct": (
                float(ach_curr.achievement_pct * 100)
                if ach_curr and ach_curr.achievement_pct is not None else None
            ),
            "policies_count": len(policy_blocks),
            "nf_count": sum(len(b["nfs"]) for b in policy_blocks),
            "total_commission": float(
                sum(c.total_actual or Decimal("0") for c in ev_commissions)
            ),
            "policies": sorted(policy_blocks, key=lambda b: b["client_name"] or ""),
        })
    ev_summary.sort(key=lambda s: s["ev_name"])

    finalized_completion_months = _finalized_completion_months(
        quarter, year, finalized_policy_ids, policies
    )

    def _serialize_nf(nf):
        return {
            "id": str(nf.id),
            "cliente_mae": nf.cliente_mae,
            "operadora": nf.operadora,
            "produto": nf.produto,
            "data_recebimento": (
                nf.data_recebimento.isoformat() if nf.data_recebimento else None
            ),
            "nf_liquido": float(nf.nf_valor_liquido),
            "tipo_receita": nf.tipo_receita,
            "match_status": nf.match_status,
            "policy_id": str(nf.policy_id) if nf.policy_id else None,
            "apolice_finalizada_mes": (
                finalized_completion_months.get(nf.policy_id)
                if nf.match_status == 'APOLICE_FINALIZADA' and nf.policy_id
                else None
            ),
        }

    unmatched = [
        _serialize_nf(n) for n in FinancialImport.query.filter_by(
            quarter=quarter, year=year, match_status='UNMATCHED',
        ).all()
    ]
    expired = [
        _serialize_nf(n) for n in FinancialImport.query.filter(
            FinancialImport.quarter == quarter,
            FinancialImport.year == year,
            FinancialImport.match_status.in_(['EXPIRED', 'PRE_VIGENCIA']),
        ).all()
    ]
    nao_suportado = [
        _serialize_nf(n) for n in FinancialImport.query.filter_by(
            quarter=quarter, year=year, match_status='PRODUTO_NAO_SUPORTADO',
        ).all()
    ]
    apolices_finalizadas = [
        _serialize_nf(n) for n in nfs_finalized
    ]

    totals = {
        "total_commission": sum(s["total_commission"] for s in ev_summary),
        "ev_count": len(ev_summary),
        "policy_count": sum(s["policies_count"] for s in ev_summary),
        "matched_nf_count": sum(s["nf_count"] for s in ev_summary),
        "unmatched_count": len(unmatched),
        "expired_count": len(expired),
        "nao_suportado_count": len(nao_suportado),
        "apolices_finalizadas_count": len(apolices_finalizadas),
    }

    return {
        "totals": totals,
        "ev_summary": ev_summary,
        "unmatched": unmatched,
        "expired": expired,
        "nao_suportado": nao_suportado,
        "apolices_finalizadas": apolices_finalizadas,
    }


def _period_before(left: tuple[int, int], right: tuple[int, int]) -> bool:
    left_q, left_y = left
    right_q, right_y = right
    return (left_y, left_q) < (right_y, right_q)


def _locked_period_pairs_before(quarter: int, year: int) -> set[tuple[int, int]]:
    current = (quarter, year)
    appraisal_pairs = {
        (q, y) for q, y in db.session.query(Appraisal.quarter, Appraisal.year)
        .filter(Appraisal.status == AppraisalStatus.LOCKED)
        .all()
    }
    commission_pairs = {
        (q, y) for q, y in db.session.query(Commission.quarter, Commission.year)
        .filter(Commission.is_final.is_(True))
        .all()
    }
    return {
        pair for pair in (appraisal_pairs | commission_pairs)
        if _period_before(pair, current)
    }


def _positive_locked_comissao_month_counts(
    policy_ids: set,
    quarter: int,
    year: int,
) -> dict:
    pairs = _locked_period_pairs_before(quarter, year)
    if not policy_ids or not pairs:
        return {}

    rows = FinancialImport.query.filter(
        FinancialImport.match_status == 'MATCHED',
        FinancialImport.policy_id.in_(policy_ids),
    ).all()

    monthly = defaultdict(lambda: defaultdict(Decimal))
    for row in rows:
        if (row.quarter, row.year) not in pairs:
            continue
        if classify_revenue_type(row.tipo_receita) != COMISSAO:
            continue
        monthly[row.policy_id][row.nf_mes_recebimento] += (
            row.nf_valor_liquido or Decimal("0")
        )

    return {
        policy_id: sum(1 for total in months.values() if total > 0)
        for policy_id, months in monthly.items()
    }


def _finalized_completion_months(
    quarter: int,
    year: int,
    policy_ids: set,
    policies: dict,
) -> dict:
    if not policy_ids:
        return {}

    prior_counts = _positive_locked_comissao_month_counts(policy_ids, quarter, year)
    rows = FinancialImport.query.filter_by(
        quarter=quarter,
        year=year,
        match_status='MATCHED',
    ).filter(FinancialImport.policy_id.in_(policy_ids)).all()

    current_monthly = defaultdict(lambda: defaultdict(Decimal))
    for row in rows:
        if classify_revenue_type(row.tipo_receita) != COMISSAO:
            continue
        current_monthly[row.policy_id][row.nf_mes_recebimento] += (
            row.nf_valor_liquido or Decimal("0")
        )

    completion_months = {}
    for policy_id in policy_ids:
        policy = policies.get(policy_id)
        if policy is None:
            continue
        clock = min(
            12,
            (policy.initial_installments_paid or 0)
            + prior_counts.get(policy_id, 0),
        )
        if clock >= 12:
            continue
        for month in sorted(current_monthly.get(policy_id, {})):
            if current_monthly[policy_id][month] <= 0:
                continue
            clock += 1
            if clock >= 12:
                completion_months[policy_id] = month
                break

    return completion_months

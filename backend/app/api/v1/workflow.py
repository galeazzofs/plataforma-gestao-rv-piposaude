from collections import defaultdict
from decimal import Decimal

from flask import Blueprint, jsonify, request, g

from app.auth.decorators import require_auth, require_role
from app.models import (
    Appraisal, AppraisalStatus, UserRole, CommissionStatus,
    Commission, EvQuarterAchievement, FinancialImport, Policy, User,
)
from app.api.middlewares import paginate_query, log_audit
from app.extensions import db
from app.modules.policies.filters import ev_policies_query
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

    query = Appraisal.query.order_by(Appraisal.year.desc(), Appraisal.month.desc())

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

    month = data.get("month")
    year = data.get("year")

    if not month or not year:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "month and year required"}}), 400

    try:
        month = int(month)
        year = int(year)
    except (ValueError, TypeError):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "month and year must be integers"}}), 400

    if month < 1 or month > 12:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "month must be 1..12"}}), 400

    user = g.current_user

    try:
        appraisal = start_appraisal(month=month, year=year, created_by=user.id)
        log_audit("appraisals", appraisal.id, "CREATE", new_values={"month": month, "year": year})
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

    if (
        appraisal.status == AppraisalStatus.VALIDATING
        and new_status == AppraisalStatus.REVOPS_REVIEW
        and user.role != UserRole.ADMIN
    ):
        return jsonify({
            "error": {
                "code": "FORBIDDEN",
                "message": "Only RevOps can approve departed-EV appraisals.",
            },
        }), 403

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

    month, year = appraisal.month, appraisal.year

    # Delete ALL commissions for this month (including is_final when LOCKED)
    Commission.query.filter_by(month=month, year=year).delete()

    # Reset NF match status back to UNMATCHED
    FinancialImport.query.filter(
        FinancialImport.month == month,
        FinancialImport.year == year,
    ).update({
        FinancialImport.match_status: 'UNMATCHED',
        FinancialImport.policy_id: None,
        FinancialImport.matched_at: None,
    })

    log_audit("appraisals", appraisal.id, "DELETE",
              old_values={"month": month, "year": year, "status": appraisal.status.value})

    db.session.delete(appraisal)
    db.session.commit()

    return jsonify({"data": {"deleted": True}}), 200


@workflow_bp.route("/<appraisal_id>/contest", methods=["POST"])
@require_auth
def contest_appraisal(appraisal_id):
    """Open a contestation on an appraisal in VALIDATING.

    Requires a non-empty note. Sets has_contestation=True and routes the
    appraisal straight to REVOPS_REVIEW so the contestation skips the
    LIDER_REVIEW step.
    """
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404

    if appraisal.status != AppraisalStatus.VALIDATING:
        return jsonify({
            "error": {
                "code": "INVALID_STATE",
                "message": (
                    f"Contestation only allowed in VALIDATING "
                    f"(current: {appraisal.status.value})"
                ),
            },
        }), 409

    body = request.get_json() or {}
    note = (body.get("note") or "").strip()
    if not note:
        return jsonify({
            "error": {"code": "VALIDATION_ERROR", "message": "note is required"},
        }), 400

    appraisal.has_contestation = True
    appraisal.contestation_note = note
    appraisal.resolution_note = None

    # Walk to REVOPS_REVIEW: VALIDATING → LIDER_REVIEW is normally blocked
    # by has_contestation, so route via that step explicitly with the
    # contestation-skip path. We bypass transition_appraisal's block by
    # going through LIDER_REVIEW first (with a contested flag) is not
    # desired; instead, set status directly. The state graph allows
    # LIDER_REVIEW → REVOPS_REVIEW, so we set LIDER_REVIEW → REVOPS_REVIEW
    # via the state machine after a forced jump from VALIDATING.
    # Simpler: set appraisal.status = REVOPS_REVIEW directly here, which
    # is the documented contestation route per issue #36.
    appraisal.status = AppraisalStatus.REVOPS_REVIEW

    log_audit(
        "appraisals", appraisal.id, "CONTEST",
        new_values={"has_contestation": True, "note": note},
    )
    db.session.commit()

    try:
        from app.modules.notifications.slack import notify_contestation_opened
        notify_contestation_opened(
            appraisal.month, appraisal.year, g.current_user.name,
        )
    except Exception as e:  # pragma: no cover — graceful failure
        import logging
        logging.getLogger(__name__).warning(
            f"Slack notify_contestation_opened failed: {e}"
        )

    return jsonify({"data": _serialize_appraisal(appraisal, detail=True)})


@workflow_bp.route("/<appraisal_id>/resolve-contestation", methods=["POST"])
@require_role(UserRole.ADMIN)
def resolve_contestation(appraisal_id):
    """RevOps resolves a contestation. Requires a resolution note.

    Clears has_contestation and routes the appraisal back to VALIDATING
    so the contesting party can re-validate with the resolution context.
    """
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND"}}), 404

    if not appraisal.has_contestation:
        return jsonify({
            "error": {"code": "INVALID_STATE",
                      "message": "no open contestation on this appraisal"},
        }), 409

    body = request.get_json() or {}
    resolution = (body.get("resolution_note") or "").strip()
    if not resolution:
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "resolution_note is required"},
        }), 400

    appraisal.has_contestation = False
    appraisal.resolution_note = resolution
    # Route back to VALIDATING so the contesting party can re-validate.
    appraisal.status = AppraisalStatus.VALIDATING

    log_audit(
        "appraisals", appraisal.id, "RESOLVE_CONTESTATION",
        new_values={"has_contestation": False, "resolution_note": resolution},
    )
    db.session.commit()

    # Best-effort: DM the contestant if we can identify them via the
    # latest CONTEST audit log entry.
    try:
        from app.modules.notifications.slack import notify_contestation_resolved
        from app.models import AuditLog
        contest_log = (
            AuditLog.query
            .filter_by(table_name="appraisals", row_id=appraisal.id, action="CONTEST")
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        if contest_log and contest_log.user_id:
            contestant = db.session.get(User, contest_log.user_id)
            if contestant is not None:
                notify_contestation_resolved(
                    contestant, appraisal.month, appraisal.year,
                )
    except Exception as e:  # pragma: no cover — graceful failure
        import logging
        logging.getLogger(__name__).warning(
            f"Slack notify_contestation_resolved failed: {e}"
        )

    return jsonify({"data": _serialize_appraisal(appraisal, detail=True)})


@workflow_bp.route("/<appraisal_id>/recalculate", methods=["POST"])
@require_role(UserRole.ADMIN)
def recalculate(appraisal_id):
    """Re-run the calculator for this appraisal's (month, year).

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
        run_monthly_appraisal, MissingAchievementsError,
    )
    try:
        # Missing achievements don't block — they fall back to 0% and surface
        # as a warning in the detail payload (same as the preview).
        run_monthly_appraisal(
            appraisal.month, appraisal.year, validate_achievements=False
        )
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


@workflow_bp.route("/preview", methods=["POST"])
@require_role(UserRole.ADMIN)
def preview_appraisal():
    """Read-only monthly draft of the EV commission apuração.

    Runs the real monthly calculator against whatever financial data is
    currently uploaded for (month, year), builds the same review payload
    the CALCULATING screen renders, then rolls the whole transaction back.

    Nothing is persisted: no Commission rows, no Policy mutations
    (installments_paid / first_payment_real / commission_status), no NF
    match_status changes, and no Slack notifications fire. This lets RevOps
    sanity-check the apuração mid-month — e.g. as NFs land —
    without opening an appraisal or touching any state.

    Missing achievements do NOT block a draft (unlike the real apuração): the
    affected policies fall back to 0% achievement and the gaps come back in
    `missing_achievements` as a warning.

    Body: { "month": 1..12, "year": int }
    """
    data = request.get_json() or {}
    try:
        month = int(data.get("month"))
        year = int(data.get("year"))
    except (TypeError, ValueError):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "month and year required (integers)"},
        }), 400

    if month not in range(1, 13):
        return jsonify({
            "error": {"code": "VALIDATION_ERROR",
                      "message": "month must be 1..12"},
        }), 400

    from app.modules.commissions.calculator import (
        run_monthly_appraisal, validate_achievements_for_appraisal,
    )
    try:
        # Report (don't enforce) the achievement gaps, then run the real
        # calculator with the gate disabled so a draft is always produced.
        missing_achievements = validate_achievements_for_appraisal(month, year)
        run_monthly_appraisal(month, year, validate_achievements=False)
        detail = _build_period_detail(month, year)
    finally:
        # A preview must never persist. Nothing here was committed, so a full
        # rollback discards everything the calculator flushed — commissions,
        # policy clock mutations and NF match statuses all evaporate. The
        # detail payload is already materialised into plain values above, so
        # it survives the rollback.
        db.session.rollback()

    return jsonify({"data": {
        "month": month, "year": year, "preview": True,
        "missing_achievements": missing_achievements, **detail,
    }})


# ── Serializer ───────────────────────────────────────────────────────


def _serialize_appraisal(appraisal, detail=False):
    data = {
        "id": str(appraisal.id),
        "month": appraisal.month,
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
        "has_contestation": bool(appraisal.has_contestation),
        "contestation_note": appraisal.contestation_note,
        "resolution_note": appraisal.resolution_note,
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
    """Build the rich review payload for an appraisal, keyed on its period."""
    return _build_period_detail(appraisal.month, appraisal.year)


def _build_period_detail(month, year):
    """Build the rich review payload: ev_summary with nested policies and NFs,
    plus unmatched / expired / nao_suportado tabs and totals. Keyed purely on
    (month, year) so it serves both a persisted appraisal and a throwaway
    preview run."""
    # Achievement stays quarterly: the per-EV achievement shown for a monthly
    # appraisal is the achievement of the quarter that contains this month.
    quarter = (month - 1) // 3 + 1
    # Surface (don't enforce) the gongo-quarter achievements still missing, so
    # the review can flag the EVs that were apurados at 0%.
    from app.modules.commissions.calculator import validate_achievements_for_appraisal
    missing_achievements = validate_achievements_for_appraisal(month, year)
    commissions = Commission.query.filter_by(month=month, year=year).all()
    nfs_matched = FinancialImport.query.filter_by(
        month=month, year=year, match_status='MATCHED',
    ).all()
    nfs_finalized = FinancialImport.query.filter_by(
        month=month, year=year, match_status='APOLICE_FINALIZADA',
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

    # The Por EV view also lets the user filter to the EV's policies that did
    # NOT generate commission this month ("não apuradas"). To explain *why*
    # each one fell out we need, per policy, which match statuses landed in
    # the competência (e.g. an EXPIRED NF vs no NF at all).
    month_nf_status = defaultdict(set)
    for ms, pid in db.session.query(
        FinancialImport.match_status, FinancialImport.policy_id,
    ).filter(
        FinancialImport.month == month,
        FinancialImport.year == year,
        FinancialImport.policy_id.isnot(None),
    ).all():
        month_nf_status[pid].add(ms)

    # Pull the full book (excluding cancelled) for every EV that has at least
    # one apurada policy this month — that's the set of cards the user can
    # expand and filter inside.
    ev_ids = list(by_ev.keys())
    ev_book = defaultdict(list)
    if ev_ids:
        for p in (
            ev_policies_query()
            .filter(Policy.ev_id.in_(ev_ids))
            .filter(Policy.commission_status != CommissionStatus.CANCELLED)
            .all()
        ):
            ev_book[p.ev_id].append(p)

    def _nao_apurada_reason(p):
        if p.commission_status == CommissionStatus.SETTLED or (p.installments_paid or 0) >= 12:
            return "Ciclo 12/12 completo"
        statuses = month_nf_status.get(p.id, set())
        if 'APOLICE_FINALIZADA' in statuses:
            return "Ciclo 12/12 completo"
        if 'EXPIRED' in statuses or 'PRE_VIGENCIA' in statuses:
            return "NF fora de vigência no mês"
        if 'PRODUTO_NAO_SUPORTADO' in statuses:
            return "Produto não suportado"
        if statuses:
            return "NF não comissionável no mês"
        return "Sem NF no mês"

    def _policy_base(p):
        return {
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
        }

    ev_summary = []
    for ev_id, ev_commissions in by_ev.items():
        ev = db.session.get(User, ev_id)
        ach_curr = EvQuarterAchievement.query.filter_by(
            ev_id=ev_id, quarter=quarter, year=year,
        ).first()

        apurada_ids = {c.policy_id for c in ev_commissions}

        policy_blocks = []
        for c in ev_commissions:
            p = policies.get(c.policy_id)
            if p is None:
                continue
            nfs = nfs_by_policy.get(p.id, [])
            block = _policy_base(p)
            block.update({
                "apurada": True,
                "reason": None,
                "achievement_used_pct": (
                    float(c.achievement_pct * 100) if c.achievement_pct else 0.0
                ),
                "commission_pct": (
                    float(c.commission_pct) if c.commission_pct else 0.0
                ),
                "subtotal": float(c.total_actual or 0),
                "nf_liquido_total": float(
                    sum(nf.nf_valor_liquido for nf in nfs)
                ) if nfs else 0.0,
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
            policy_blocks.append(block)

        nao_apurada_blocks = []
        for p in ev_book.get(ev_id, []):
            if p.id in apurada_ids:
                continue
            block = _policy_base(p)
            block.update({
                "apurada": False,
                "reason": _nao_apurada_reason(p),
                "achievement_used_pct": None,
                "commission_pct": None,
                "subtotal": 0.0,
                "nf_liquido_total": 0.0,
                "nfs": [],
            })
            nao_apurada_blocks.append(block)

        ev_summary.append({
            "ev_id": str(ev_id),
            "ev_name": ev.name if ev else "—",
            "ev_left_company": bool(getattr(ev, "left_company", False)) if ev else False,
            "achievement_pct": (
                float(ach_curr.achievement_pct * 100)
                if ach_curr and ach_curr.achievement_pct is not None else None
            ),
            "policies_count": len(policy_blocks),
            "nao_apuradas_count": len(nao_apurada_blocks),
            "nf_count": sum(len(b["nfs"]) for b in policy_blocks),
            "nf_liquido_total": float(
                sum(b["nf_liquido_total"] for b in policy_blocks)
            ),
            "total_commission": float(
                sum(c.total_actual or Decimal("0") for c in ev_commissions)
            ),
            "policies": sorted(
                policy_blocks + nao_apurada_blocks,
                key=lambda b: b["client_name"] or "",
            ),
        })
    ev_summary.sort(key=lambda s: s["ev_name"])

    finalized_completion_months = _finalized_completion_months(
        month, year, finalized_policy_ids, policies
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
            month=month, year=year, match_status='UNMATCHED',
        ).all()
    ]
    expired = [
        _serialize_nf(n) for n in FinancialImport.query.filter(
            FinancialImport.month == month,
            FinancialImport.year == year,
            FinancialImport.match_status.in_(['EXPIRED', 'PRE_VIGENCIA']),
        ).all()
    ]
    nao_suportado = [
        _serialize_nf(n) for n in FinancialImport.query.filter_by(
            month=month, year=year, match_status='PRODUTO_NAO_SUPORTADO',
        ).all()
    ]
    apolices_finalizadas = [
        _serialize_nf(n) for n in nfs_finalized
    ]

    totals = {
        "total_commission": sum(s["total_commission"] for s in ev_summary),
        "nf_liquido_total": float(sum(s["nf_liquido_total"] for s in ev_summary)),
        "ev_count": len(ev_summary),
        "left_company_ev_count": sum(
            1 for s in ev_summary if s.get("ev_left_company")
        ),
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
        "missing_achievements": missing_achievements,
        "financial_data_periods": _financial_data_periods(),
    }


def _financial_data_periods():
    """Every (year, month) that currently has RECEBIDO financial imports, with
    NF counts. The apuração is keyed strictly on its own month, so when the
    selected month comes back empty this tells the UI where the imported NFs
    actually landed — e.g. all of a year's commission receipts often pile into
    January (renewal season)."""
    rows = (
        db.session.query(
            FinancialImport.year,
            FinancialImport.month,
            db.func.count(FinancialImport.id),
        )
        .filter(FinancialImport.status_recebimento == 'RECEBIDO')
        .group_by(FinancialImport.year, FinancialImport.month)
        .order_by(FinancialImport.year, FinancialImport.month)
        .all()
    )
    return [
        {"year": y, "month": m, "nf_count": c}
        for (y, m, c) in rows
    ]


def _period_before(left: tuple[int, int], right: tuple[int, int]) -> bool:
    left_q, left_y = left
    right_q, right_y = right
    return (left_y, left_q) < (right_y, right_q)


def _locked_period_pairs_before(month: int, year: int) -> set[tuple[int, int]]:
    current = (month, year)
    appraisal_pairs = {
        (m, y) for m, y in db.session.query(Appraisal.month, Appraisal.year)
        .filter(Appraisal.status == AppraisalStatus.LOCKED)
        .all()
    }
    commission_pairs = {
        (m, y) for m, y in db.session.query(Commission.month, Commission.year)
        .filter(Commission.is_final.is_(True))
        .all()
    }
    return {
        pair for pair in (appraisal_pairs | commission_pairs)
        if _period_before(pair, current)
    }


def _positive_locked_comissao_month_counts(
    policy_ids: set,
    month: int,
    year: int,
) -> dict:
    pairs = _locked_period_pairs_before(month, year)
    if not policy_ids or not pairs:
        return {}

    rows = FinancialImport.query.filter(
        FinancialImport.match_status == 'MATCHED',
        FinancialImport.policy_id.in_(policy_ids),
    ).all()

    monthly = defaultdict(lambda: defaultdict(Decimal))
    for row in rows:
        if (row.month, row.year) not in pairs:
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
    month: int,
    year: int,
    policy_ids: set,
    policies: dict,
) -> dict:
    if not policy_ids:
        return {}

    prior_counts = _positive_locked_comissao_month_counts(policy_ids, month, year)
    rows = FinancialImport.query.filter_by(
        month=month,
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

"""Read model for Apuracao review and preview payloads."""
from collections import defaultdict
from decimal import Decimal

from app.extensions import db
from app.models import (
    Commission,
    CommissionStatus,
    EvQuarterAchievement,
    FinancialImport,
    Policy,
    User,
)
from app.modules.financial.monthly_engine import COMISSAO, classify_revenue_type
from app.modules.financial.policy_clock import positive_locked_comissao_month_counts
from app.modules.policies.filters import ev_policies_query


def build_period_detail(month, year):
    """Build the rich review payload for an Apuracao period."""
    quarter = (month - 1) // 3 + 1
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
    for commission in commissions:
        by_ev[commission.ev_id].append(commission)

    month_nf_status = defaultdict(set)
    for match_status, policy_id in db.session.query(
        FinancialImport.match_status, FinancialImport.policy_id,
    ).filter(
        FinancialImport.month == month,
        FinancialImport.year == year,
        FinancialImport.policy_id.isnot(None),
    ).all():
        month_nf_status[policy_id].add(match_status)

    ev_ids = list(by_ev.keys())
    ev_book = defaultdict(list)
    if ev_ids:
        for policy in (
            ev_policies_query()
            .filter(Policy.ev_id.in_(ev_ids))
            .filter(Policy.commission_status != CommissionStatus.CANCELLED)
            .all()
        ):
            ev_book[policy.ev_id].append(policy)

    def _nao_apurada_reason(policy):
        if (
            policy.commission_status == CommissionStatus.SETTLED
            or (policy.installments_paid or 0) >= 12
        ):
            return "Ciclo 12/12 completo"
        statuses = month_nf_status.get(policy.id, set())
        if 'APOLICE_FINALIZADA' in statuses:
            return "Ciclo 12/12 completo"
        if 'PRODUTO_NAO_SUPORTADO' in statuses:
            return "Produto não suportado"
        if statuses:
            return "NF não comissionável no mês"
        return "Sem NF no mês"

    def _policy_base(policy):
        return {
            "policy_id": str(policy.id),
            "client_name": policy.client.name if policy.client else None,
            "operadora": policy.partner_operator,
            "produto": policy.benefit_type.value if policy.benefit_type else None,
            "segment": policy.segment.value if policy.segment else None,
            "installments_paid": policy.installments_paid or 0,
            "first_payment_real": (
                policy.first_payment_real.isoformat()
                if policy.first_payment_real else None
            ),
            "closed_date": (
                policy.closed_date.isoformat() if policy.closed_date else None
            ),
        }

    ev_summary = []
    for ev_id, ev_commissions in by_ev.items():
        ev = db.session.get(User, ev_id)
        ach_curr = EvQuarterAchievement.query.filter_by(
            ev_id=ev_id, quarter=quarter, year=year,
        ).first()

        apurada_ids = {commission.policy_id for commission in ev_commissions}

        policy_blocks = []
        for commission in ev_commissions:
            policy = policies.get(commission.policy_id)
            if policy is None:
                continue
            nfs = nfs_by_policy.get(policy.id, [])
            block = _policy_base(policy)
            block.update({
                "apurada": True,
                "reason": None,
                "achievement_used_pct": (
                    float(commission.achievement_pct * 100)
                    if commission.achievement_pct else 0.0
                ),
                "commission_pct": (
                    float(commission.commission_pct)
                    if commission.commission_pct else 0.0
                ),
                "subtotal": float(commission.total_actual or 0),
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
        for policy in ev_book.get(ev_id, []):
            if policy.id in apurada_ids:
                continue
            block = _policy_base(policy)
            block.update({
                "apurada": False,
                "reason": _nao_apurada_reason(policy),
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
            "nf_count": sum(len(block["nfs"]) for block in policy_blocks),
            "nf_liquido_total": float(
                sum(block["nf_liquido_total"] for block in policy_blocks)
            ),
            "total_commission": float(
                sum(commission.total_actual or Decimal("0") for commission in ev_commissions)
            ),
            "policies": sorted(
                policy_blocks + nao_apurada_blocks,
                key=lambda block: block["client_name"] or "",
            ),
        })
    ev_summary.sort(key=lambda summary: summary["ev_name"])

    finalized_completion_months = _finalized_completion_months(
        month, year, finalized_policy_ids, policies
    )

    unmatched = [
        _serialize_nf(row, finalized_completion_months)
        for row in FinancialImport.query.filter_by(
            month=month, year=year, match_status='UNMATCHED',
        ).all()
    ]
    nao_suportado = [
        _serialize_nf(row, finalized_completion_months)
        for row in FinancialImport.query.filter_by(
            month=month, year=year, match_status='PRODUTO_NAO_SUPORTADO',
        ).all()
    ]
    apolices_finalizadas = [
        _serialize_nf(row, finalized_completion_months)
        for row in nfs_finalized
    ]

    totals = {
        "total_commission": sum(summary["total_commission"] for summary in ev_summary),
        "nf_liquido_total": float(
            sum(summary["nf_liquido_total"] for summary in ev_summary)
        ),
        "ev_count": len(ev_summary),
        "left_company_ev_count": sum(
            1 for summary in ev_summary if summary.get("ev_left_company")
        ),
        "policy_count": sum(summary["policies_count"] for summary in ev_summary),
        "matched_nf_count": sum(summary["nf_count"] for summary in ev_summary),
        "unmatched_count": len(unmatched),
        "nao_suportado_count": len(nao_suportado),
        "apolices_finalizadas_count": len(apolices_finalizadas),
    }

    return {
        "totals": totals,
        "ev_summary": ev_summary,
        "unmatched": unmatched,
        "nao_suportado": nao_suportado,
        "apolices_finalizadas": apolices_finalizadas,
        "missing_achievements": missing_achievements,
        "financial_data_periods": _financial_data_periods(),
    }


def _serialize_nf(nf, finalized_completion_months):
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


def _financial_data_periods():
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
        {"year": year, "month": month, "nf_count": count}
        for (year, month, count) in rows
    ]


def _finalized_completion_months(
    month: int,
    year: int,
    policy_ids: set,
    policies: dict,
) -> dict:
    if not policy_ids:
        return {}

    prior_counts = positive_locked_comissao_month_counts(
        policy_ids,
        before=(month, year),
    )
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
        for financial_month in sorted(current_monthly.get(policy_id, {})):
            if current_monthly[policy_id][financial_month] <= 0:
                continue
            clock += 1
            if clock >= 12:
                completion_months[policy_id] = financial_month
                break

    return completion_months

"""Quarterly commission calculator (v4 --- per-empresa formula with perks).

Spec 4.3:
  Comissao real = (Total liquido empresa - Perks empresa) x % comissao

Algorithm:
1. Match NF rows -> policies by (cliente_mae, operadora, produto) normalised
2. Aggregate matched NFs by client (empresa level)
3. Subtract perks at the client level
4. Distribute net amount proportionally across policies
5. Apply commission % per policy (from gongo quarter achievement snapshot)
6. Update commission_status via status helper
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from app.extensions import db
from app.models import (
    Policy,
    Commission,
    EvQuarterAchievement,
    FinancialImport,
    Perk,
    User,
)
from app.modules.policies.filters import active_ev_policies_query
from app.modules.financial.matcher import build_policy_index, normalize
from app.modules.commissions.pct_lookup import lookup_commission_pct
from app.modules.commissions.status import update_policy_statuses


# -- Errors -------------------------------------------------------------------


class MissingAchievementsError(Exception):
    def __init__(self, missing):
        self.missing = missing
        super().__init__(f"Missing achievements: {missing}")


# -- Pre-check ----------------------------------------------------------------


def validate_achievements_for_appraisal(quarter, year):
    """Verify every (ev_id, gongo_q, gongo_y) needed by this apuracao
    has a stored achievement.

    Returns list of human-readable strings for missing combinations.
    Empty list = ok to proceed.
    """
    policies = active_ev_policies_query().all()

    needed = set()
    for p in policies:
        if not p.closed_date or not p.ev_id:
            continue
        gq = (p.closed_date.month - 1) // 3 + 1
        needed.add((p.ev_id, gq, p.closed_date.year))

    missing = []
    for ev_id, gq, gy in sorted(needed, key=lambda t: (str(t[0]), t[2], t[1])):
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=ev_id, quarter=gq, year=gy
        ).first()
        if ach is None or ach.achievement_pct is None:
            user = db.session.get(User, ev_id)
            label = user.name if user else str(ev_id)
            missing.append(f"{label} \u2192 Q{gq}/{gy}")
    return missing


# -- Benefit normalisation ----------------------------------------------------

BENEFIT_MAP = {'saude': 'SAUDE', 'odonto': 'ODONTO', 'vida': 'VIDA'}


# -- Main entry ---------------------------------------------------------------


def run_quarterly_appraisal(quarter, year):
    """Process all financial_imports for (quarter, year) and produce commissions.

    Implements spec 4.3:
      Comissao real = (Total liquido empresa - Perks empresa) x % comissao
    """
    # -- Pre-check ----------------------------------------------------
    missing = validate_achievements_for_appraisal(quarter, year)
    if missing:
        raise MissingAchievementsError(missing)

    # -- 1. Wipe non-final commissions --------------------------------
    Commission.query.filter_by(
        quarter=quarter, year=year, is_final=False
    ).delete()
    db.session.flush()

    # -- 2. Reset installments_paid to baseline -----------------------
    locked_policy_ids = {
        pid for (pid,) in db.session.query(Commission.policy_id)
        .filter(
            Commission.quarter == quarter,
            Commission.year == year,
            Commission.is_final.is_(True),
        )
        .all()
    }
    policies = [
        p for p in active_ev_policies_query().all()
        if p.id not in locked_policy_ids
    ]

    locked_nf_count_rows = (
        db.session.query(
            FinancialImport.policy_id,
            db.func.count(FinancialImport.id),
        )
        .join(Commission, Commission.policy_id == FinancialImport.policy_id)
        .filter(
            Commission.is_final.is_(True),
            FinancialImport.match_status == 'MATCHED',
        )
        .group_by(FinancialImport.policy_id)
        .all()
    )
    locked_nf_count = {pid: int(cnt) for pid, cnt in locked_nf_count_rows}

    for p in policies:
        p.installments_paid = (
            (p.initial_installments_paid or 0) + locked_nf_count.get(p.id, 0)
        )

    # -- 3. Build matcher index ---------------------------------------
    policy_index = build_policy_index(policies)

    # -- 4. Pass 1 --- Match NFs to policies --------------------------
    nfs = FinancialImport.query.filter_by(
        quarter=quarter, year=year, status_recebimento='RECEBIDO'
    ).all()

    # Accumulators
    policy_nf_subtotals = defaultdict(Decimal)    # policy_id -> sum NF values
    client_nf_totals = defaultdict(Decimal)        # client_id -> sum NF values
    matched_policies = {}                           # policy_id -> Policy
    earliest_nf_dates = {}                          # policy_id -> earliest date

    for nf in nfs:
        produto_n = normalize(nf.produto or '')
        benefit = BENEFIT_MAP.get(produto_n)
        if benefit is None:
            nf.match_status = 'PRODUTO_NAO_SUPORTADO'
            nf.policy_id = None
            nf.matched_at = None
            continue

        key = (
            normalize(nf.cliente_mae or ''),
            normalize(nf.operadora or ''),
            benefit,
        )
        candidates = policy_index.get(key, [])
        if not candidates:
            nf.match_status = 'UNMATCHED'
            nf.policy_id = None
            nf.matched_at = None
            continue

        matched = None
        for policy in candidates:
            if not policy.first_payment_real:
                continue
            window_end = policy.first_payment_real + relativedelta(
                months=12 - (policy.initial_installments_paid or 0)
            )
            if nf.data_recebimento is None:
                continue
            if nf.data_recebimento < policy.first_payment_real:
                continue
            if nf.data_recebimento > window_end:
                continue
            matched = policy
            break

        if matched is None:
            best = candidates[0]
            if (not best.first_payment_real
                    or (nf.data_recebimento
                        and nf.data_recebimento < best.first_payment_real)):
                nf.match_status = 'PRE_VIGENCIA'
            else:
                nf.match_status = 'EXPIRED'
            nf.policy_id = best.id
            nf.matched_at = None
            continue

        # Record the match
        amount = Decimal(str(nf.nf_valor_liquido))
        nf.policy_id = matched.id
        nf.match_status = 'MATCHED'
        nf.matched_at = datetime.now(timezone.utc)

        policy_nf_subtotals[matched.id] += amount
        client_nf_totals[matched.client_id] += amount
        matched_policies[matched.id] = matched
        matched.installments_paid = (matched.installments_paid or 0) + 1

        # Track earliest NF date per policy (for first_payment_real inference)
        if nf.data_recebimento:
            prev = earliest_nf_dates.get(matched.id)
            if prev is None or nf.data_recebimento < prev:
                earliest_nf_dates[matched.id] = nf.data_recebimento

    # -- 5. Load perks per client -------------------------------------
    perks_by_client = defaultdict(Decimal)
    perk_rows = Perk.query.filter_by(quarter=quarter, year=year).all()
    for perk in perk_rows:
        perks_by_client[perk.client_id] += perk.amount

    # -- 6. Pass 2 --- Compute commissions per policy -----------------
    for policy_id, nf_subtotal in policy_nf_subtotals.items():
        policy = matched_policies[policy_id]
        client_id = policy.client_id

        # Empresa-level aggregation (spec 4.3)
        client_total = client_nf_totals[client_id]
        client_perks = perks_by_client.get(client_id, Decimal('0'))
        net_client = max(Decimal('0'), client_total - client_perks)

        # Proportional share for this policy
        if client_total > 0:
            share = nf_subtotal / client_total
        else:
            share = Decimal('0')
        net_policy = (net_client * share).quantize(Decimal('0.01'))

        # Achievement snapshot from gongo quarter
        gongo_q = (policy.closed_date.month - 1) // 3 + 1
        gongo_y = policy.closed_date.year
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=policy.ev_id, quarter=gongo_q, year=gongo_y
        ).first()
        achievement = ach.achievement_pct if ach else Decimal('0')

        segment_value = policy.segment.value if policy.segment else 'P'
        commission_pct, version = lookup_commission_pct(segment_value, achievement)
        if commission_pct is None:
            commission_pct = Decimal('0')

        commission_amount = (net_policy * commission_pct).quantize(Decimal('0.01'))

        comm = Commission(
            policy_id=policy_id,
            ev_id=policy.ev_id,
            quarter=quarter,
            year=year,
            segment=segment_value,
            achievement_pct=achievement,
            commission_pct=commission_pct,
            commission_pct_version=version,
            monthly_actual=commission_amount,
            total_actual=commission_amount,
            is_final=False,
        )
        db.session.add(comm)

    # -- 7. Update commission_status ----------------------------------
    update_policy_statuses(matched_policies.values(), earliest_nf_dates)

    db.session.flush()
    return _build_summary(quarter, year)


# -- Summary ------------------------------------------------------------------


def _build_summary(quarter, year):
    return {
        "totals": {
            "matched_count": FinancialImport.query.filter_by(
                quarter=quarter, year=year, match_status='MATCHED'
            ).count(),
            "unmatched_count": FinancialImport.query.filter_by(
                quarter=quarter, year=year, match_status='UNMATCHED'
            ).count(),
            "expired_count": FinancialImport.query.filter_by(
                quarter=quarter, year=year, match_status='EXPIRED'
            ).count(),
            "pre_vigencia_count": FinancialImport.query.filter_by(
                quarter=quarter, year=year, match_status='PRE_VIGENCIA'
            ).count(),
            "produto_nao_suportado_count": FinancialImport.query.filter_by(
                quarter=quarter, year=year, match_status='PRODUTO_NAO_SUPORTADO'
            ).count(),
        }
    }

"""Quarterly commission calculator (v4 --- per-empresa formula with perks).

Spec 4.3:
  Comissao real = (Total liquido empresa - Perks empresa) x % comissao

Algorithm:
1. Match NF rows -> policies by `numero_apolice` (after normalising whitespace
   and case). Product is still validated against the saude/odonto/vida
   benefit map so non-policy revenue is rejected explicitly. NFs without
   `numero_apolice` populated are dropped as UNMATCHED — the spreadsheet
   must carry the apolice number for the row to match.
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
from sqlalchemy import tuple_

from app.extensions import db
from app.models import (
    Appraisal,
    AppraisalStatus,
    Policy,
    Commission,
    CommissionStatus,
    EvQuarterAchievement,
    FinancialImport,
    Perk,
    User,
)
from app.modules.policies.filters import active_ev_policies_query
from app.modules.financial.matcher import build_policy_index, normalize_apolice_number
from app.modules.commissions.pct_lookup import lookup_commission_pct
from app.modules.financial.monthly_engine import (
    COMISSAO,
    classify_revenue_type,
)


# -- Errors -------------------------------------------------------------------


class MissingAchievementsError(Exception):
    def __init__(self, missing):
        self.missing = missing
        super().__init__(f"Missing achievements: {missing}")


# -- Pre-check ----------------------------------------------------------------


def validate_achievements_for_appraisal(quarter, year):
    """Verify every (ev_id, gongo_quarter, gongo_year) tuple needed by this
    apuracao has a stored achievement.

    Each policy uses the achievement_pct from the EV's GONGO quarter (when
    the sale closed) as a snapshot — not the appraisal quarter. So we need
    one achievement per (ev_id, gongo_q, gongo_y) combination across all
    active policies.

    Returns list of human-readable strings for missing combinations.
    Empty list = ok to proceed.
    """
    policies = active_ev_policies_query().filter(
        Policy.commission_status.notin_([
            CommissionStatus.CANCELLED,
            CommissionStatus.SETTLED,
        ])
    ).all()

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


APOLICE_FINALIZADA = "APOLICE_FINALIZADA"
RECEITA_NAO_COMISSIONAVEL = "RECEITA_NAO_COMISSIONAVEL"


def _locked_period_pairs():
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
    return appraisal_pairs | commission_pairs


def _locked_positive_comissao_month_counts():
    pairs = _locked_period_pairs()
    if not pairs:
        return {}

    rows = (
        db.session.query(
            FinancialImport.policy_id,
            FinancialImport.nf_mes_recebimento,
            FinancialImport.tipo_receita,
            db.func.coalesce(db.func.sum(FinancialImport.nf_valor_liquido), 0),
        )
        .filter(
            FinancialImport.match_status == "MATCHED",
            FinancialImport.policy_id.isnot(None),
            tuple_(FinancialImport.quarter, FinancialImport.year).in_(pairs),
        )
        .group_by(
            FinancialImport.policy_id,
            FinancialImport.nf_mes_recebimento,
            FinancialImport.tipo_receita,
        )
        .all()
    )

    monthly = defaultdict(lambda: defaultdict(Decimal))
    for policy_id, month, tipo, total in rows:
        if classify_revenue_type(tipo) == COMISSAO:
            monthly[policy_id][month] += total or Decimal("0")

    return {
        policy_id: sum(1 for total in months.values() if total > 0)
        for policy_id, months in monthly.items()
    }


def _set_nf_status(nf, status, policy_id=None, matched=False):
    nf.match_status = status
    nf.policy_id = policy_id
    nf.matched_at = datetime.now(timezone.utc) if matched else None


def _window_end(policy):
    if policy.first_payment_real is None:
        return None
    remaining_from_legacy = max(0, 12 - (policy.initial_installments_paid or 0))
    return policy.first_payment_real + relativedelta(months=remaining_from_legacy)


def _is_after_window(policy, nf):
    end = _window_end(policy)
    return bool(end and nf.data_recebimento and nf.data_recebimento > end)


def _sync_policy_status(policy):
    if policy.commission_status == CommissionStatus.CANCELLED:
        return
    if policy.installments_paid >= 12 and policy.first_payment_real is not None:
        policy.commission_status = CommissionStatus.SETTLED
    elif policy.first_payment_real is not None and policy.installments_paid > 0:
        policy.commission_status = CommissionStatus.IN_PAYMENT


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
    policies_for_index = active_ev_policies_query().filter(
        Policy.commission_status != CommissionStatus.CANCELLED
    ).all()
    policies = [p for p in policies_for_index if p.id not in locked_policy_ids]

    locked_comissao_count = _locked_positive_comissao_month_counts()
    for p in policies_for_index:
        if p.commission_status == CommissionStatus.CANCELLED:
            continue
        p.installments_paid = min(
            12,
            (p.initial_installments_paid or 0) + locked_comissao_count.get(p.id, 0),
        )

    # -- 3. Build matcher index ---------------------------------------
    policy_index = build_policy_index(policies_for_index)

    # -- 4. Pass 1 --- Find candidate policies ------------------------
    nfs = FinancialImport.query.filter_by(
        quarter=quarter, year=year, status_recebimento='RECEBIDO'
    ).all()

    # Accumulators
    policy_nf_subtotals = defaultdict(Decimal)    # policy_id -> sum NF values
    client_nf_totals = defaultdict(Decimal)        # client_id -> sum NF values
    matched_policies = {}                           # policy_id -> Policy
    candidate_rows = defaultdict(list)              # policy_id -> [FinancialImport]

    for nf in nfs:
        revenue_type = classify_revenue_type(nf.tipo_receita)
        if revenue_type is None:
            _set_nf_status(nf, RECEITA_NAO_COMISSIONAVEL)
            continue

        # Apolice-number-anchored matching: every match is keyed on the
        # apolice number stamped on the NF row + on the policy. Product
        # is still validated so non-saude/odonto/vida revenue is rejected
        # explicitly rather than appearing as "no policy found".
        from app.modules.financial.matcher import normalize as _normalize_text
        produto_n = _normalize_text(nf.produto or '')
        benefit = BENEFIT_MAP.get(produto_n)
        if benefit is None:
            _set_nf_status(nf, 'PRODUTO_NAO_SUPORTADO')
            continue

        apolice_key = normalize_apolice_number(nf.numero_apolice)
        if not apolice_key:
            _set_nf_status(nf, 'UNMATCHED')
            continue

        candidates = policy_index.get(apolice_key, [])
        if not candidates:
            _set_nf_status(nf, 'UNMATCHED')
            continue

        matched = None
        for policy in candidates:
            if policy.id in locked_policy_ids:
                continue
            if (
                policy.first_payment_real
                and nf.data_recebimento
                and nf.data_recebimento < policy.first_payment_real
            ):
                continue
            matched = policy
            break

        if matched is None:
            best = candidates[0]
            if (not best.first_payment_real
                    or (nf.data_recebimento
                        and nf.data_recebimento < best.first_payment_real)):
                _set_nf_status(nf, 'PRE_VIGENCIA', best.id)
            else:
                _set_nf_status(nf, 'EXPIRED', best.id)
            continue

        matched_policies[matched.id] = matched
        candidate_rows[matched.id].append(nf)

    # -- 4b. Pass 2 --- Process each policy chronologically by financial month
    for policy_id, rows in candidate_rows.items():
        policy = matched_policies[policy_id]
        by_month = defaultdict(list)
        for nf in rows:
            by_month[nf.nf_mes_recebimento].append(nf)

        for month in sorted(by_month):
            month_rows = by_month[month]
            if (
                policy.commission_status == CommissionStatus.SETTLED
                or (policy.installments_paid or 0) >= 12
            ):
                for nf in month_rows:
                    _set_nf_status(nf, APOLICE_FINALIZADA, policy.id)
                policy.commission_status = CommissionStatus.SETTLED
                continue

            eligible_rows = []
            for nf in month_rows:
                if _is_after_window(policy, nf):
                    _set_nf_status(nf, 'EXPIRED', policy.id)
                else:
                    eligible_rows.append(nf)

            if not eligible_rows:
                continue

            comissao_net = Decimal("0")
            first_comissao_date = None
            for nf in eligible_rows:
                revenue_type = classify_revenue_type(nf.tipo_receita)
                amount = Decimal(str(nf.nf_valor_liquido))
                _set_nf_status(nf, 'MATCHED', policy.id, matched=True)

                policy_nf_subtotals[policy.id] += amount
                client_nf_totals[policy.client_id] += amount
                if revenue_type == COMISSAO:
                    comissao_net += amount
                    if nf.data_recebimento is not None:
                        if first_comissao_date is None or nf.data_recebimento < first_comissao_date:
                            first_comissao_date = nf.data_recebimento

            if policy.first_payment_real is None and comissao_net > 0:
                policy.first_payment_real = first_comissao_date

            if comissao_net > 0:
                policy.installments_paid = min(12, (policy.installments_paid or 0) + 1)

            _sync_policy_status(policy)

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
    for policy in matched_policies.values():
        _sync_policy_status(policy)

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
            "receita_nao_comissionavel_count": FinancialImport.query.filter_by(
                quarter=quarter, year=year, match_status=RECEITA_NAO_COMISSIONAVEL
            ).count(),
            "apolice_finalizada_count": FinancialImport.query.filter_by(
                quarter=quarter, year=year, match_status=APOLICE_FINALIZADA
            ).count(),
        }
    }

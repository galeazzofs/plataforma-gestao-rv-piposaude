"""Quarterly commission calculator (v3 — replaces old run_quarterly_appraisal_v2).

Match logic ported from the old React app's processCommissions:
- Match NF row → Policy by (cliente_mae, operadora, produto) normalized
- Vigência window = [first_payment_real, first_payment_real + (12 - initial_installments_paid) months]
- Achievement % is taken from EvQuarterAchievement of the policy's GONGO quarter
  (NOT the apuração quarter — snapshot per the old app)
- Commission = nf_valor_liquido × matrix[segment][achievement_faixa]

is_final is NEVER set here; only by transition_appraisal(LOCKED).
"""
from datetime import datetime, timezone
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from app.extensions import db
from app.models import (
    Policy,
    Commission,
    EvQuarterAchievement,
    FinancialImport,
    User,
)
from app.modules.policies.filters import active_ev_policies_query
from app.modules.financial.matcher import build_policy_index, normalize
from app.modules.commissions.pct_lookup import lookup_commission_pct


# ── Errors ───────────────────────────────────────────────────────────


class MissingAchievementsError(Exception):
    def __init__(self, missing):
        self.missing = missing
        super().__init__(f"Missing achievements: {missing}")


# ── Pre-check ────────────────────────────────────────────────────────


def validate_achievements_for_appraisal(quarter, year):
    """Verify every (ev_id, gongo_q, gongo_y) needed by this apuração
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
            missing.append(f"{label} → Q{gq}/{gy}")
    return missing


# ── Main entry ───────────────────────────────────────────────────────


BENEFIT_MAP = {'saude': 'SAUDE', 'odonto': 'ODONTO', 'vida': 'VIDA'}


def run_quarterly_appraisal(quarter, year):
    """Process all financial_imports for (quarter, year) and produce commissions.

    Pre-conditions:
    - validate_achievements_for_appraisal(quarter, year) returns []
    - financial_imports populated for this quarter

    Side effects:
    - Wipes Commissions for (quarter, year) where is_final=False
    - Resets policy.installments_paid to baseline (initial + LOCKED count)
    - Updates each NF's match_status and policy_id
    - Creates/updates Commission rows (is_final=False)
    - Increments policy.installments_paid as MATCHED NFs are processed

    Raises:
        MissingAchievementsError if pre-check fails (no writes happen).
    """
    # ── Pre-check ────────────────────────────────────────────
    missing = validate_achievements_for_appraisal(quarter, year)
    if missing:
        raise MissingAchievementsError(missing)

    # ── 1. Wipe non-final commissions ────────────────────────
    Commission.query.filter_by(
        quarter=quarter, year=year, is_final=False
    ).delete()
    db.session.flush()

    # ── 2. Reset installments_paid to baseline ───────────────
    # baseline = initial_installments_paid + count(NFs from LOCKED periods)
    # Exclude policies that already have a LOCKED commission for (quarter, year)
    # from the matching set — they are already finalized.
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

    # ── 3. Build matcher index ───────────────────────────────
    policy_index = build_policy_index(policies)

    # ── 4. Iterate financial_imports for this quarter ────────
    nfs = FinancialImport.query.filter_by(
        quarter=quarter, year=year, status_recebimento='RECEBIDO'
    ).all()

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

        # Pick most recent policy whose vigência window covers data_recebimento
        matched = None
        for policy in candidates:  # already sorted desc by closed_date
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
            # Has candidates but none in vigência — record reason
            best = candidates[0]  # most recent
            if (not best.first_payment_real
                    or (nf.data_recebimento
                        and nf.data_recebimento < best.first_payment_real)):
                nf.match_status = 'PRE_VIGENCIA'
            else:
                nf.match_status = 'EXPIRED'
            nf.policy_id = best.id
            nf.matched_at = None
            continue

        # Lookup achievement from the gongo quarter (snapshot)
        gongo_q = (matched.closed_date.month - 1) // 3 + 1
        gongo_y = matched.closed_date.year
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=matched.ev_id, quarter=gongo_q, year=gongo_y
        ).first()
        achievement = ach.achievement_pct if ach else Decimal('0')

        segment_value = matched.segment.value if matched.segment else 'P'
        commission_pct, version = lookup_commission_pct(segment_value, achievement)
        if commission_pct is None:
            commission_pct = Decimal('0')

        commission_amount = (
            Decimal(str(nf.nf_valor_liquido)) * commission_pct
        ).quantize(Decimal('0.01'))

        # Upsert commission (non-final, accumulating)
        comm = Commission.query.filter_by(
            policy_id=matched.id, quarter=quarter, year=year, is_final=False
        ).first()
        if comm is None:
            comm = Commission(
                policy_id=matched.id,
                ev_id=matched.ev_id,
                quarter=quarter,
                year=year,
                segment=segment_value,
                achievement_pct=achievement,
                commission_pct=commission_pct,
                commission_pct_version=version,
                monthly_actual=Decimal('0'),
                total_actual=Decimal('0'),
                is_final=False,
            )
            db.session.add(comm)
        comm.monthly_actual = (comm.monthly_actual or Decimal('0')) + commission_amount
        comm.total_actual = (comm.total_actual or Decimal('0')) + commission_amount

        nf.policy_id = matched.id
        nf.match_status = 'MATCHED'
        nf.matched_at = datetime.now(timezone.utc)

        # Increment counter (baseline was reset at the start of this fn)
        matched.installments_paid = (matched.installments_paid or 0) + 1

    db.session.flush()
    return _build_summary(quarter, year)


# ── Summary ──────────────────────────────────────────────────────────


def _build_summary(quarter, year):
    """Lightweight summary for the caller.
    The rich ev_summary / drill-down lives in workflow.py serializer."""
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

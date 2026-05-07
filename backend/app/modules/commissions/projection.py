"""Live projection helpers -- compute estimated balance and monthly projection
from Policy data.

Commission % is resolved from the real EvQuarterAchievement for the policy's
gongo quarter (same snapshot the appraisal engine uses).  When no achievement
is on file yet, falls back to the 50 % floor (_MIDDLE_TIER_ACH) so projections
remain conservative but non-zero.

These never touch Commission records.  They read Policy / EvQuarterAchievement
fields directly and compute on-the-fly so projections stay current after each
sync.
"""
from datetime import date
from decimal import Decimal

from app.models import Policy, CommissionStatus, EvQuarterAchievement
from app.modules.commissions.pct_lookup import lookup_commission_pct

# Fallback when no EvQuarterAchievement is registered for the gongo quarter.
# 0.50 is the floor of the medium-performance tier (50-99.9 %).
_MIDDLE_TIER_ACH = Decimal("0.5000")


def _resolve_achievement(policy) -> Decimal:
    """Return the achievement pct to use for commission-rate lookup.

    Priority:
    1. Real EvQuarterAchievement for the policy's gongo quarter.
    2. _MIDDLE_TIER_ACH (50 % floor) when no achievement is on file or the
       policy has not been gongoed yet.
    """
    if policy.closed_date and policy.ev_id:
        gongo_q = (policy.closed_date.month - 1) // 3 + 1
        gongo_y = policy.closed_date.year
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=policy.ev_id, quarter=gongo_q, year=gongo_y,
        ).first()
        if ach is not None:
            return ach.achievement_pct
    return _MIDDLE_TIER_ACH


def _estimated_monthly(policy):
    """Estimated monthly commission for a single policy."""
    mrr = policy.mrr_for_commission or Decimal("0")
    if mrr <= 0:
        return Decimal("0")
    segment = policy.segment.value if policy.segment else "P"
    achievement = _resolve_achievement(policy)
    pct, _ = lookup_commission_pct(segment, achievement)
    if pct is None:
        return Decimal("0")
    return (mrr * pct).quantize(Decimal("0.01"))


def _active_policies(ev_id, closed_start=None, closed_end=None):
    """Non-settled, non-cancelled policies for an EV."""
    query = Policy.query.filter(
        Policy.ev_id == ev_id,
        Policy.commission_status.notin_([
            CommissionStatus.SETTLED,
            CommissionStatus.CANCELLED,
        ]),
    )
    if closed_start is not None:
        query = query.filter(Policy.closed_date >= closed_start)
    if closed_end is not None:
        query = query.filter(Policy.closed_date < closed_end)
    return query.all()


def compute_ev_balance(ev_id, closed_start=None, closed_end=None):
    """Total estimated saldo a receber for an EV (spec S3.7 saldo_devedor_estimado).

    balance = SUM( monthly_est x remaining_months ) across active policies.
    """
    policies = _active_policies(ev_id, closed_start, closed_end)
    balance = Decimal("0")
    for p in policies:
        monthly = _estimated_monthly(p)
        remaining = max(0, 12 - (p.installments_paid or 0))
        balance += monthly * remaining
    return balance.quantize(Decimal("0.01"))


def compute_ev_projection(ev_id, ref_date=None, period_start=None, period_months=12):
    """12-month projection of estimated receivables (spec S7).

    Returns list of 12 dicts: [{"month": "YYYY-MM", "projected": Decimal}, ...]
    """
    ref_date = ref_date or date.today()
    period_start = period_start or ref_date
    period_months = max(1, int(period_months or 12))
    policies = _active_policies(ev_id)

    # Build the requested monthly bucket list.
    buckets = []
    for i in range(period_months):
        m = period_start.month + i
        y = period_start.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        buckets.append({"month": f"{y}-{m:02d}", "projected": Decimal("0")})

    for p in policies:
        monthly = _estimated_monthly(p)
        if monthly <= 0:
            continue

        remaining = max(0, 12 - (p.installments_paid or 0))
        if remaining == 0:
            continue

        # Determine payment start: real > prev > ref_date
        start = p.first_payment_real or p.first_payment_prev or ref_date

        distributed = 0
        for bucket in buckets:
            if distributed >= remaining:
                break
            bucket_y, bucket_m = map(int, bucket["month"].split("-"))
            if (bucket_y, bucket_m) >= (start.year, start.month):
                bucket["projected"] += monthly
                distributed += 1

    # Quantize all values
    for b in buckets:
        b["projected"] = b["projected"].quantize(Decimal("0.01"))

    return buckets

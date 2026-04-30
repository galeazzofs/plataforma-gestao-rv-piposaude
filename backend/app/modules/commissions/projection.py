"""Live projection helpers -- compute estimated balance and monthly projection
from Policy data using the middle-tier commission % (spec S9).

These never touch Commission records. They read Policy fields directly
and compute on-the-fly so projections stay current after each sync.
"""
from datetime import date
from decimal import Decimal

from app.models import Policy, CommissionStatus
from app.modules.commissions.pct_lookup import lookup_commission_pct

# Middle-tier achievement value -- any value in [0.50, 0.999) works.
# We use 0.50 (the floor) to hit the 50-99.9% tier in the pct table.
_MIDDLE_TIER_ACH = Decimal("0.5000")


def _estimated_monthly(policy):
    """Estimated monthly commission for a single policy using middle tier %."""
    mrr = policy.mrr_for_commission or Decimal("0")
    if mrr <= 0:
        return Decimal("0")
    segment = policy.segment.value if policy.segment else "P"
    pct, _ = lookup_commission_pct(segment, _MIDDLE_TIER_ACH)
    if pct is None:
        return Decimal("0")
    return (mrr * pct).quantize(Decimal("0.01"))


def _active_policies(ev_id):
    """Non-settled, non-cancelled policies for an EV."""
    return Policy.query.filter(
        Policy.ev_id == ev_id,
        Policy.commission_status.notin_([
            CommissionStatus.SETTLED,
            CommissionStatus.CANCELLED,
        ]),
    ).all()


def compute_ev_balance(ev_id):
    """Total estimated saldo a receber for an EV (spec S3.7 saldo_devedor_estimado).

    balance = SUM( monthly_est x remaining_months ) across active policies.
    """
    policies = _active_policies(ev_id)
    balance = Decimal("0")
    for p in policies:
        monthly = _estimated_monthly(p)
        remaining = max(0, 12 - (p.installments_paid or 0))
        balance += monthly * remaining
    return balance.quantize(Decimal("0.01"))


def compute_ev_projection(ev_id, ref_date=None):
    """12-month projection of estimated receivables (spec S7).

    Returns list of 12 dicts: [{"month": "YYYY-MM", "projected": Decimal}, ...]
    """
    ref_date = ref_date or date.today()
    policies = _active_policies(ev_id)

    # Build 12-month bucket list
    buckets = []
    for i in range(12):
        m = ref_date.month + i
        y = ref_date.year + (m - 1) // 12
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

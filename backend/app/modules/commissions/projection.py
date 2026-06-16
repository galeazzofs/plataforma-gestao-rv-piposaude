"""Live projection helpers -- compute estimated balance and monthly projection
from Policy data.

Projected monthly commission is the policy's contractual commission potential
divided by 12. That keeps the EV dashboard on the same payable scale as Finance
and the Policies page.
"""
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from app.models import Policy, CommissionStatus


def _projected_monthly(policy):
    """Estimated monthly commission for a single policy."""
    potential = policy.commission_potential
    if potential is None:
        return Decimal("0")
    return (Decimal(str(potential)) / Decimal("12")).quantize(Decimal("0.01"))


def _projection_start(policy, fallback):
    """First unpaid monthly competency for this policy."""
    start = policy.first_payment_real or policy.first_payment_prev or fallback
    months_paid = max(0, min(policy.installments_paid or 0, 12))
    return start + relativedelta(months=months_paid)


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
        monthly = _projected_monthly(p)
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
        monthly = _projected_monthly(p)
        if monthly <= 0:
            continue

        remaining = max(0, 12 - (p.installments_paid or 0))
        if remaining == 0:
            continue

        start = _projection_start(p, ref_date)

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

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


def _policy_saldo(policy):
    """Per-policy Saldo a receber (CONTEXT.md 'Saldo a receber do EV').

        0                                                  if the clock is 12/12
        (monthly * 12) - min(comissao_paga, monthly * meses)   otherwise

    where monthly = comissao potencial / 12 and meses = months on the clock.
    Underpayment (pago below contract-to-date) raises the saldo; overpayment is
    capped, so a hot-running policy still projects its remaining months instead
    of zeroing. Only Comissao counts -- Agenciamento never does.
    """
    meses = max(0, min(policy.installments_paid or 0, 12))
    if meses >= 12:
        return Decimal("0")
    monthly = _projected_monthly(policy)
    if monthly <= 0:
        return Decimal("0")
    credited = min(policy.comissao_paga, monthly * meses)
    return monthly * 12 - credited


def compute_ev_balance(ev_id, closed_start=None, closed_end=None):
    """Saldo a receber do EV: sum of each active policy's saldo a receber
    (see _policy_saldo). Whole-book -- the dashboard quarter only scopes MRR /
    goal / achievement, never the saldo.
    """
    policies = _active_policies(ev_id, closed_start, closed_end)
    balance = sum((_policy_saldo(p) for p in policies), Decimal("0"))
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
        meses = max(0, min(p.installments_paid or 0, 12))
        remaining = 12 - meses
        if remaining <= 0:
            continue
        saldo = _policy_saldo(p)
        if saldo <= 0:
            continue

        start = _projection_start(p, ref_date)
        targets = []
        for bucket in buckets:
            by, bm = map(int, bucket["month"].split("-"))
            if (by, bm) >= (start.year, start.month):
                targets.append(bucket)
                if len(targets) >= remaining:
                    break
        if not targets:
            continue

        # Spread the policy's saldo evenly over its remaining clock months; the
        # last visible bucket absorbs the rounding remainder when the whole
        # remaining clock fits the window, so the chart total equals the saldo.
        per_month = (saldo / remaining).quantize(Decimal("0.01"))
        for i, bucket in enumerate(targets):
            if i == len(targets) - 1 and len(targets) == remaining:
                bucket["projected"] += saldo - per_month * (remaining - 1)
            else:
                bucket["projected"] += per_month

    # Quantize all values
    for b in buckets:
        b["projected"] = b["projected"].quantize(Decimal("0.01"))

    return buckets

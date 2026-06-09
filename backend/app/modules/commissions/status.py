"""commission_status auto-transitions per spec §3.3.

PROJECTED  → first payment received → IN_PAYMENT
IN_PAYMENT → 12 installments paid   → SETTLED
CANCELLED  → never touched
"""
from app.models import CommissionStatus


def update_policy_statuses(policies, earliest_nf_dates=None):
    """Update commission_status for each policy based on payment state.

    Args:
        policies: iterable of Policy objects (will be mutated in-place).
        earliest_nf_dates: optional dict {policy_id: date} — earliest
            data_recebimento among matched NFs. Used to infer
            first_payment_real when it is None.
    """
    earliest_nf_dates = earliest_nf_dates or {}

    for policy in policies:
        if policy.commission_status == CommissionStatus.CANCELLED:
            continue

        # Infer first_payment_real from matched NF dates if missing
        if policy.first_payment_real is None and policy.id in earliest_nf_dates:
            policy.first_payment_real = earliest_nf_dates[policy.id]

        # Transition logic — count-based only. first_payment_real (Início
        # vigência) is unreliable and must NOT gate the transition; the
        # paid-month count alone decides the status.
        if policy.installments_paid >= 12:
            policy.commission_status = CommissionStatus.SETTLED
        elif policy.installments_paid > 0:
            policy.commission_status = CommissionStatus.IN_PAYMENT
        # else: stays PROJECTED

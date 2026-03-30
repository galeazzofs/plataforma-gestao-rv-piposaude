from decimal import Decimal
from app.extensions import db
from app.models import (
    Policy, Commission, Goal, CommissionPctTable,
    Appraisal, FinancialImport, Perk, Client,
)
from app.modules.commissions.achievement import calculate_achievement, get_quarter_date_range
from app.modules.commissions.pct_lookup import lookup_commission_pct


def get_ev_total_mrr_in_quarter(ev_id, quarter, year):
    """Sum MRR of all gongos for an EV in a quarter."""
    start, end = get_quarter_date_range(quarter, year)
    policies = Policy.query.filter(
        Policy.ev_id == ev_id,
        Policy.closed_date >= start,
        Policy.closed_date < end,
    ).all()
    return sum(p.mrr_for_commission or Decimal("0") for p in policies)


def get_ev_goal(ev_id, quarter, year):
    """Get EV's MRR target for a quarter."""
    goal = Goal.query.filter_by(ev_id=ev_id, quarter=quarter, year=year).first()
    return goal.mrr_target if goal else Decimal("0")


def calculate_projection_for_policy(policy, quarter, year):
    """Calculate projected commission for a single policy.

    Uses the MEDIUM faixa (50-99.9%) as estimate for projection.
    """
    mrr = policy.mrr_for_commission or Decimal("0")

    # For projection, use medium faixa estimate
    commission_pct, version = lookup_commission_pct(
        policy.segment.value if policy.segment else "P",
        Decimal("0.75"),  # Middle of medium faixa
    )
    if commission_pct is None:
        commission_pct = Decimal("0")

    monthly_estimated = (mrr * commission_pct).quantize(Decimal("0.01"))
    total_estimated = (monthly_estimated * 12).quantize(Decimal("0.01"))

    # Upsert commission record
    commission = Commission.query.filter_by(
        policy_id=policy.id, quarter=quarter, year=year
    ).first()

    if commission is None:
        commission = Commission(
            policy_id=policy.id,
            ev_id=policy.ev_id,
            quarter=quarter,
            year=year,
        )
        db.session.add(commission)

    if not commission.is_final:
        commission.segment = policy.segment.value if policy.segment else None
        commission.commission_pct = commission_pct
        commission.commission_pct_version = version
        commission.monthly_estimated = monthly_estimated
        commission.total_estimated = total_estimated

    db.session.flush()
    return commission


def run_quarterly_appraisal(quarter, year):
    """Run final commission calculation for a quarter.

    1. Calculate final achievement for each EV
    2. Lookup final % from table
    3. For each policy in the quarter:
       - Calculate using FINAL %
       - Apply retroactively to ALL deals in the quarter
    4. Mark commissions as is_final=True

    Returns dict of {ev_id: {achievement, commission_pct, policies: [...]}}
    """
    results = {}

    # Get all policies gongoed in this quarter (SQLite compat: use date range)
    start, end = get_quarter_date_range(quarter, year)
    policies = Policy.query.filter(
        Policy.closed_date >= start,
        Policy.closed_date < end,
        Policy.commission_status != "CANCELLED",
    ).all()

    # Group by EV
    ev_policies = {}
    for p in policies:
        ev_policies.setdefault(p.ev_id, []).append(p)

    for ev_id, ev_policy_list in ev_policies.items():
        # 1. Calculate achievement
        total_mrr = sum(p.mrr_for_commission or Decimal("0") for p in ev_policy_list)
        target = get_ev_goal(ev_id, quarter, year)
        achievement = calculate_achievement(total_mrr, target)

        # 2. For each policy, calculate with FINAL %
        policy_results = []
        for policy in ev_policy_list:
            segment = policy.segment.value if policy.segment else "P"
            commission_pct, version = lookup_commission_pct(segment, achievement)
            if commission_pct is None:
                commission_pct = Decimal("0")

            mrr = policy.mrr_for_commission or Decimal("0")

            # Calculate based on real NFs if available
            monthly_actual = _calculate_actual_monthly(
                policy, commission_pct, quarter, year
            )
            monthly_estimated = (mrr * commission_pct).quantize(Decimal("0.01"))
            total_estimated = (monthly_estimated * 12).quantize(Decimal("0.01"))

            # Upsert commission
            commission = Commission.query.filter_by(
                policy_id=policy.id, quarter=quarter, year=year
            ).first()
            if commission is None:
                commission = Commission(
                    policy_id=policy.id, ev_id=ev_id,
                    quarter=quarter, year=year,
                )
                db.session.add(commission)

            commission.segment = segment
            commission.achievement_pct = achievement
            commission.commission_pct = commission_pct
            commission.commission_pct_version = version
            commission.monthly_estimated = monthly_estimated
            commission.monthly_actual = monthly_actual
            commission.total_estimated = total_estimated
            commission.total_actual = (
                (monthly_actual * 12).quantize(Decimal("0.01"))
                if monthly_actual else None
            )
            commission.is_final = True

            policy_results.append({
                "policy_id": str(policy.id),
                "mrr": mrr,
                "commission_pct": commission_pct,
                "monthly_estimated": monthly_estimated,
                "monthly_actual": monthly_actual,
            })

        db.session.flush()

        results[str(ev_id)] = {
            "achievement_pct": achievement,
            "total_mrr": total_mrr,
            "target": target,
            "policies": policy_results,
        }

    return results


def _calculate_actual_monthly(policy, commission_pct, quarter, year):
    """Calculate actual monthly commission based on real NFs.

    base = SUM(NFs da empresa no tri) - perks da empresa no tri
    comissao = base * commission_pct / num_policies_empresa_no_tri
    """
    if policy.client_id is None:
        return None

    # Sum NFs for this client in the quarter
    nf_total = db.session.query(
        db.func.coalesce(db.func.sum(FinancialImport.nf_valor_liquido), Decimal("0"))
    ).join(
        Policy, FinancialImport.policy_id == Policy.id
    ).filter(
        Policy.client_id == policy.client_id,
        FinancialImport.quarter == quarter,
        FinancialImport.year == year,
    ).scalar()

    if nf_total == 0:
        return None

    # Subtract perks for this client
    perk_total = db.session.query(
        db.func.coalesce(db.func.sum(Perk.amount), Decimal("0"))
    ).filter(
        Perk.client_id == policy.client_id,
        Perk.quarter == quarter,
        Perk.year == year,
    ).scalar()

    base = nf_total - perk_total
    if base <= 0:
        return Decimal("0")

    # Divide by number of policies for this client in the quarter (SQLite compat)
    start, end = get_quarter_date_range(quarter, year)
    policy_count = Policy.query.filter(
        Policy.client_id == policy.client_id,
        Policy.closed_date >= start,
        Policy.closed_date < end,
    ).count()
    if policy_count == 0:
        policy_count = 1

    return ((base / policy_count) * commission_pct).quantize(Decimal("0.01"))

from decimal import Decimal
from collections import defaultdict
from app.extensions import db
from app.models import (
    Policy, Commission, Goal, CommissionPctTable,
    Appraisal, FinancialImport, Perk, Client,
    EvQuarterAchievement, CommissionStatus,
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


def get_ev_achievement(ev_id, quarter, year):
    """Get the stored achievement for an EV in a specific quarter.

    Returns (achievement_pct, is_final) or (None, False) if not found.
    """
    ach = EvQuarterAchievement.query.filter_by(
        ev_id=ev_id, quarter=quarter, year=year
    ).first()
    if ach and ach.achievement_pct is not None:
        return ach.achievement_pct, ach.is_final
    return None, False


def calculate_and_save_quarter_achievements(quarter, year):
    """Calculate and persist achievements for all EVs with gongos in a quarter.

    Only updates non-final records.
    Returns dict of {ev_id: EvQuarterAchievement}.
    """
    start, end = get_quarter_date_range(quarter, year)

    # Get all policies gongoed in this quarter
    policies = Policy.query.filter(
        Policy.closed_date >= start,
        Policy.closed_date < end,
        Policy.commission_status != CommissionStatus.CANCELLED.value,
    ).all()

    # Group by EV
    ev_policies = defaultdict(list)
    for p in policies:
        if p.ev_id:
            ev_policies[p.ev_id].append(p)

    results = {}
    for ev_id, policy_list in ev_policies.items():
        total_mrr = sum(p.mrr_for_commission or Decimal("0") for p in policy_list)
        target = get_ev_goal(ev_id, quarter, year)
        achievement = calculate_achievement(total_mrr, target)

        # Upsert (skip if already final)
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=ev_id, quarter=quarter, year=year
        ).first()

        if ach and ach.is_final:
            results[ev_id] = ach
            continue

        if ach is None:
            ach = EvQuarterAchievement(ev_id=ev_id, quarter=quarter, year=year)
            db.session.add(ach)

        ach.total_mrr = total_mrr
        ach.mrr_target = target
        ach.achievement_pct = achievement

        results[ev_id] = ach

    db.session.flush()
    return results


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
    """Legacy version — kept for backwards compatibility.

    Use run_quarterly_appraisal_v2() for the correct logic.
    """
    return run_quarterly_appraisal_v2(quarter, year)


def run_quarterly_appraisal_v2(quarter, year):
    """Run final commission calculation for a quarter (v2).

    Two-phase process:
    Phase 1: Calculate and save achievement for EVs with gongos in this quarter
    Phase 2: Calculate commission on all policies that received NFs in this quarter,
             using the achievement % from the quarter each policy was gongoed in.

    Only considers policies with installments_paid < 12 (not yet settled).

    Returns dict of {ev_id: {achievement_pct, total_mrr, target, nf_policies: [...]}}
    """
    results = {}

    # ── Phase 1: Save achievements for this quarter's gongos ──────────
    calculate_and_save_quarter_achievements(quarter, year)

    # ── Phase 2: Calculate commission on NFs received in this quarter ─
    # Get all NFs received in this quarter
    nfs = FinancialImport.query.filter_by(quarter=quarter, year=year).all()

    if not nfs:
        return results

    # Group NFs by policy
    nf_by_policy = defaultdict(lambda: Decimal("0"))
    for nf in nfs:
        nf_by_policy[nf.policy_id] += (nf.nf_valor_liquido or Decimal("0"))

    # Load all relevant policies
    policy_ids = list(nf_by_policy.keys())
    policies = Policy.query.filter(Policy.id.in_(policy_ids)).all()
    policy_map = {p.id: p for p in policies}

    # Group by EV for results
    ev_policy_results = defaultdict(list)

    for policy_id, nf_total in nf_by_policy.items():
        policy = policy_map.get(policy_id)
        if policy is None:
            continue

        # Skip settled or cancelled policies
        if policy.commission_status in (CommissionStatus.SETTLED, CommissionStatus.CANCELLED):
            continue

        # Skip policies that have completed 12 installments
        if (policy.installments_paid or 0) >= 12:
            continue

        # Get achievement from the quarter this policy was gongoed
        gongo_q, gongo_y = policy.quarter_closed
        if gongo_q is None:
            continue

        achievement, _ = get_ev_achievement(policy.ev_id, gongo_q, gongo_y)
        if achievement is None:
            # No achievement stored for that quarter — use 0 (lowest faixa)
            achievement = Decimal("0")

        # Lookup commission %
        segment = policy.segment.value if policy.segment else "P"
        commission_pct, version = lookup_commission_pct(segment, achievement)
        if commission_pct is None:
            commission_pct = Decimal("0")

        # Subtract perks for this client in the appraisal quarter
        perk_total = Decimal("0")
        if policy.client_id:
            perk_total = db.session.query(
                db.func.coalesce(db.func.sum(Perk.amount), Decimal("0"))
            ).filter(
                Perk.client_id == policy.client_id,
                Perk.quarter == quarter,
                Perk.year == year,
            ).scalar()

        # Commission = (NF liquido - perks share) * commission_pct
        # Perks are per-client, so distribute across policies of same client in this quarter
        client_policy_count = 1
        if policy.client_id and perk_total > 0:
            client_policy_count = len([
                pid for pid, p in policy_map.items()
                if p.client_id == policy.client_id and pid in nf_by_policy
            ])
            if client_policy_count == 0:
                client_policy_count = 1

        perk_share = (perk_total / client_policy_count).quantize(Decimal("0.01"))
        base = nf_total - perk_share
        if base < 0:
            base = Decimal("0")

        commission_amount = (base * commission_pct).quantize(Decimal("0.01"))

        # Upsert commission record
        commission = Commission.query.filter_by(
            policy_id=policy.id, quarter=quarter, year=year
        ).first()
        if commission is None:
            commission = Commission(
                policy_id=policy.id, ev_id=policy.ev_id,
                quarter=quarter, year=year,
            )
            db.session.add(commission)

        commission.segment = segment
        commission.achievement_pct = achievement
        commission.commission_pct = commission_pct
        commission.commission_pct_version = version
        commission.monthly_actual = commission_amount
        commission.monthly_estimated = (
            (policy.mrr_for_commission or Decimal("0")) * commission_pct
        ).quantize(Decimal("0.01"))
        commission.total_estimated = (commission.monthly_estimated * 12).quantize(Decimal("0.01"))
        commission.total_actual = (commission_amount * 12).quantize(Decimal("0.01"))
        commission.is_final = True

        ev_policy_results[policy.ev_id].append({
            "policy_id": str(policy.id),
            "hubspot_ticket_id": policy.hubspot_ticket_id,
            "client_name": policy.client.name if policy.client else None,
            "segment": segment,
            "gongo_quarter": f"Q{gongo_q}/{gongo_y}",
            "achievement_pct": achievement,
            "nf_total": nf_total,
            "perk_share": perk_share,
            "commission_pct": commission_pct,
            "commission_amount": commission_amount,
            "installments_paid": policy.installments_paid,
        })

    db.session.flush()

    # Build results summary
    for ev_id, policy_list in ev_policy_results.items():
        # Get this quarter's achievement for summary (may not exist if EV had no gongos)
        ach_record = EvQuarterAchievement.query.filter_by(
            ev_id=ev_id, quarter=quarter, year=year
        ).first()

        results[str(ev_id)] = {
            "achievement_pct_q": ach_record.achievement_pct if ach_record else None,
            "total_mrr_q": ach_record.total_mrr if ach_record else None,
            "target_q": ach_record.mrr_target if ach_record else None,
            "total_nf": sum(p["nf_total"] for p in policy_list),
            "total_commission": sum(p["commission_amount"] for p in policy_list),
            "nf_policies": policy_list,
        }

    return results

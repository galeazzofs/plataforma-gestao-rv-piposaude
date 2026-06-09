from decimal import Decimal

from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_role
from app.models.user import UserRole
from app.api.middlewares import log_audit
from app.extensions import db

lider_vendas_bp = Blueprint("lider_vendas", __name__, url_prefix="/api/v1/lider-vendas")


@lider_vendas_bp.route("/team")
@require_role(UserRole.LIDER_VENDAS)
def get_team():
    """Return team members for the logged-in lider de vendas."""
    from app.models import Appraisal, Commission, User
    user = g.current_user
    if not user.team_id:
        return jsonify({"data": []})

    members = User.query.filter_by(
        team_id=user.team_id,
        role=UserRole.EV,
        active=True,
        left_company=False,
    ).all()
    appraisal = _latest_appraisal()
    period = (appraisal.month, appraisal.year) if appraisal else None

    return jsonify({
        "data": [_serialize_team_member(m, appraisal, period) for m in members]
    })


@lider_vendas_bp.route("/ev/<ev_id>")
@require_role(UserRole.LIDER_VENDAS)
def get_ev_detail(ev_id):
    """Return EV detail (policies, commissions) for a team member."""
    from app.models import Commission, User
    user = g.current_user

    # Verify that the requested EV belongs to the lider de vendas's team
    ev = db.session.get(User, ev_id)
    if ev is None or ev.left_company or str(ev.team_id) != str(user.team_id):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "EV not found or not in your team"}}), 404

    appraisal = _latest_appraisal()
    commission_query = Commission.query.filter_by(ev_id=ev_id)
    if appraisal is not None:
        commission_query = commission_query.filter_by(
            month=appraisal.month,
            year=appraisal.year,
        )
    commissions = commission_query.all()
    policies = [c.policy for c in commissions if c.policy is not None]
    achievement_pct = _ev_quarter_achievement_pct(
        ev_id,
        _quarter_of(appraisal.month) if appraisal else None,
        appraisal.year if appraisal else None,
    )
    commission_total = _sum_commissions(commissions)

    return jsonify({
        "data": {
            "id": str(ev.id),
            "name": ev.name,
            "email": ev.email,
            "role": ev.role.value if ev.role else None,
            "left_company": bool(ev.left_company),
            "month": appraisal.month if appraisal else None,
            "year": appraisal.year if appraisal else None,
            "quarter": ((appraisal.month - 1) // 3 + 1) if appraisal else None,
            "appraisal_status": (
                appraisal.status.value if appraisal and appraisal.status else None
            ),
            "achievement_pct": achievement_pct,
            "commission_total": str(commission_total),
            "deals_count": len({c.policy_id for c in commissions}),
            "ev": {
                "id": str(ev.id),
                "name": ev.name,
                "email": ev.email,
                "role": ev.role.value if ev.role else None,
                "left_company": bool(ev.left_company),
            },
            "policies": [
                {
                    "id": str(p.id),
                    "hubspot_ticket_id": p.hubspot_ticket_id,
                    "numero_apolice": p.numero_apolice or p.hubspot_apolice_id,
                    "client_name": p.client.name if p.client else None,
                    "benefit_type": p.benefit_type.value if p.benefit_type else None,
                    "segment": p.segment.value if p.segment else None,
                    "mrr_projected": str(p.mrr_projected) if p.mrr_projected else None,
                    "mrr_for_commission": (
                        str(p.mrr_for_commission)
                        if p.mrr_for_commission is not None else None
                    ),
                    "closed_date": p.closed_date.isoformat() if p.closed_date else None,
                    "commission_status": (
                        p.commission_status.value if p.commission_status else None
                    ),
                    "commission_pct": _policy_commission_pct(commissions, p.id),
                    "commission_amount": _policy_commission_amount(commissions, p.id),
                    # Per-policy achievement = the GONGO-quarter achievement that
                    # actually drove this commission (varies policy to policy).
                    "achievement_pct": _policy_achievement_pct(commissions, p.id),
                    "multiplier": "1,00",
                }
                for p in policies
            ],
            "commissions": [
                {
                    "id": str(c.id),
                    "month": c.month,
                    "year": c.year,
                    "segment": c.segment,
                    "achievement_pct": _pct_to_percent(c.achievement_pct),
                    "commission_pct": _pct_to_percent(c.commission_pct),
                    "total_estimated": str(c.total_estimated) if c.total_estimated else None,
                    "total_actual": str(c.total_actual) if c.total_actual else None,
                    "is_final": c.is_final,
                }
                for c in commissions
            ],
        }
    })


_VALIDATION_DONE = ("APPROVED", "AUTO_APPROVED", "RESOLVED")


def _team_ev_ids(team_id):
    """Current (active, not-departed) EVs of a team — the ones whose approval
    the líder is responsible for."""
    from app.models import User
    return [
        u.id for u in User.query.filter_by(
            team_id=team_id, role=UserRole.EV, active=True, left_company=False,
        ).all()
    ]


def _team_validation_progress(appraisal, team_id):
    """How many of the team's EV validations are done for this appraisal."""
    from app.models import EvValidation
    ev_ids = _team_ev_ids(team_id)
    vals = (
        EvValidation.query.filter(
            EvValidation.appraisal_id == appraisal.id,
            EvValidation.ev_id.in_(ev_ids),
        ).all()
        if ev_ids else []
    )
    total = len(vals)
    approved = sum(1 for v in vals if v.status.value in _VALIDATION_DONE)
    return total, approved


@lider_vendas_bp.route("/appraisal")
@require_role(UserRole.LIDER_VENDAS)
def get_team_appraisal():
    """The current apuração for the líder's team, with approval progress and
    whether the líder can approve it now. Powers the 'Aprovar apuração' card."""
    user = g.current_user
    appraisal = _latest_appraisal()
    if appraisal is None or not user.team_id:
        return jsonify({"data": None})

    total, approved = _team_validation_progress(appraisal, user.team_id)
    status = appraisal.status.value if appraisal.status else None
    all_done = total > 0 and approved == total
    can_approve = (
        status in ("VALIDATING", "LIDER_REVIEW")
        and all_done
        and not appraisal.has_contestation
    )
    return jsonify({"data": {
        "id": str(appraisal.id),
        "month": appraisal.month,
        "year": appraisal.year,
        "status": status,
        "team_total": total,
        "team_approved": approved,
        "team_pending": total - approved,
        "all_team_approved": all_done,
        "has_contestation": bool(appraisal.has_contestation),
        "can_approve": can_approve,
    }})


@lider_vendas_bp.route("/appraisal/<appraisal_id>/approve", methods=["POST"])
@require_role(UserRole.LIDER_VENDAS)
def approve_team_appraisal(appraisal_id):
    """Líder approves their team's EV apuração and sends it to RevOps.

    Guarded: every current EV of the team must have approved first. Advances
    VALIDATING → LIDER_REVIEW → REVOPS_REVIEW. (The apuração is monthly/global;
    in a multi-team month the líder who approves moves it forward — the per-EV
    approvals are still individually required upstream.)
    """
    from app.models import Appraisal, AppraisalStatus
    from app.modules.workflow.state_machine import (
        transition_appraisal, InvalidTransitionError,
    )
    user = g.current_user
    appraisal = db.session.get(Appraisal, appraisal_id)
    if appraisal is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Apuração not found"}}), 404
    if not user.team_id:
        return jsonify({"error": {"code": "FORBIDDEN"}}), 403

    total, approved = _team_validation_progress(appraisal, user.team_id)
    if total == 0 or approved != total:
        return jsonify({"error": {
            "code": "CONFLICT",
            "message": f"Ainda há EVs do time sem aprovar ({approved}/{total}).",
        }}), 409

    old_status = appraisal.status.value
    try:
        if appraisal.status == AppraisalStatus.VALIDATING:
            transition_appraisal(appraisal, AppraisalStatus.LIDER_REVIEW)
        if appraisal.status == AppraisalStatus.LIDER_REVIEW:
            transition_appraisal(appraisal, AppraisalStatus.REVOPS_REVIEW)
        log_audit("appraisals", appraisal.id, "UPDATE",
                  old_values={"status": old_status},
                  new_values={"status": appraisal.status.value})
        db.session.commit()
    except InvalidTransitionError as e:
        db.session.rollback()
        return jsonify({"error": {"code": "INVALID_TRANSITION", "message": str(e)}}), 422

    return jsonify({"data": {"id": str(appraisal.id), "status": appraisal.status.value}})


def _latest_appraisal():
    from app.models import Appraisal
    return Appraisal.query.order_by(
        Appraisal.year.desc(),
        Appraisal.month.desc(),
    ).first()


def _commission_value(c):
    return Decimal(str(c.total_actual or c.monthly_actual or 0))


def _sum_commissions(commissions):
    return sum((_commission_value(c) for c in commissions), Decimal("0"))


def _pct_to_percent(value):
    if value is None:
        return None
    return str((Decimal(str(value)) * Decimal("100")).quantize(Decimal("0.01")))


def _quarter_of(month):
    return (month - 1) // 3 + 1


def _ev_quarter_achievement_pct(ev_id, quarter, year):
    """The EV's achievement for a quarter, as a percent string (0.75 → '75.00').

    This is THE atingimento of the EV in the period — the same value the
    apuração shows. (Per-policy commissions use each policy's *gongo*-quarter
    achievement, which varies; averaging those across an EV's book produced a
    meaningless headline number, so we read the quarter achievement directly.)
    """
    from app.models import EvQuarterAchievement
    if quarter is None or year is None:
        return None
    row = EvQuarterAchievement.query.filter_by(
        ev_id=ev_id, quarter=quarter, year=year,
    ).first()
    if row is None or row.achievement_pct is None:
        return None
    return str((Decimal(str(row.achievement_pct)) * Decimal("100"))
               .quantize(Decimal("0.01")))


def _serialize_team_member(member, appraisal, period):
    from app.models import Commission

    commissions = []
    if period is not None:
        month, year = period
        commissions = Commission.query.filter_by(
            ev_id=member.id,
            month=month,
            year=year,
        ).all()
    mrr = sum(
        (
            Decimal(str(c.policy.mrr_for_commission or 0))
            for c in commissions
            if c.policy is not None
        ),
        Decimal("0"),
    )
    return {
        "id": str(member.id),
        "name": member.name,
        "email": member.email,
        "role": member.role.value if member.role else None,
        "team_id": str(member.team_id) if member.team_id else None,
        "active": member.active,
        "left_company": bool(member.left_company),
        "month": appraisal.month if appraisal else None,
        "year": appraisal.year if appraisal else None,
        "achievement_pct": _ev_quarter_achievement_pct(
            member.id,
            _quarter_of(appraisal.month) if appraisal else None,
            appraisal.year if appraisal else None,
        ),
        "mrr": str(mrr),
        "commission": str(_sum_commissions(commissions)),
        "appraisal_status": (
            appraisal.status.value if appraisal and appraisal.status else None
        ),
        "deals_count": len({c.policy_id for c in commissions}),
    }


def _policy_commission(commissions, policy_id):
    return next((c for c in commissions if str(c.policy_id) == str(policy_id)), None)


def _policy_commission_pct(commissions, policy_id):
    commission = _policy_commission(commissions, policy_id)
    return _pct_to_percent(commission.commission_pct) if commission else None


def _policy_achievement_pct(commissions, policy_id):
    commission = _policy_commission(commissions, policy_id)
    return _pct_to_percent(commission.achievement_pct) if commission else None


def _policy_commission_amount(commissions, policy_id):
    commission = _policy_commission(commissions, policy_id)
    if commission is None:
        return None
    return str(_commission_value(commission))

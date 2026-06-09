from decimal import Decimal

from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_role
from app.models.user import UserRole
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
    achievement_pct = _average_achievement_pct(commissions)
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


def _average_achievement_pct(commissions):
    values = [
        Decimal(str(c.achievement_pct)) * Decimal("100")
        for c in commissions
        if c.achievement_pct is not None
    ]
    if not values:
        return None
    return str((sum(values, Decimal("0")) / len(values)).quantize(Decimal("0.01")))


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
        "achievement_pct": _average_achievement_pct(commissions),
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


def _policy_commission_amount(commissions, policy_id):
    commission = _policy_commission(commissions, policy_id)
    if commission is None:
        return None
    return str(_commission_value(commission))

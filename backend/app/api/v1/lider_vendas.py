from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_role
from app.models.user import UserRole
from app.extensions import db

lider_vendas_bp = Blueprint("lider_vendas", __name__, url_prefix="/api/v1/lider-vendas")


@lider_vendas_bp.route("/team")
@require_role(UserRole.LIDER_VENDAS)
def get_team():
    """Return team members for the logged-in lider de vendas."""
    from app.models import User
    user = g.current_user
    if not user.team_id:
        return jsonify({"data": []})

    members = User.query.filter_by(team_id=user.team_id, active=True).all()
    return jsonify({
        "data": [
            {
                "id": str(m.id),
                "name": m.name,
                "email": m.email,
                "role": m.role.value if m.role else None,
                "team_id": str(m.team_id) if m.team_id else None,
                "active": m.active,
            }
            for m in members
        ]
    })


@lider_vendas_bp.route("/ev/<ev_id>")
@require_role(UserRole.LIDER_VENDAS)
def get_ev_detail(ev_id):
    """Return EV detail (policies, commissions) for a team member."""
    from app.models import User, Policy, Commission
    user = g.current_user

    # Verify that the requested EV belongs to the lider de vendas's team
    ev = db.session.get(User, ev_id)
    if ev is None or str(ev.team_id) != str(user.team_id):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "EV not found or not in your team"}}), 404

    policies = Policy.query.filter_by(ev_id=ev_id).all()
    commissions = Commission.query.filter_by(ev_id=ev_id).all()

    return jsonify({
        "data": {
            "ev": {
                "id": str(ev.id),
                "name": ev.name,
                "email": ev.email,
                "role": ev.role.value if ev.role else None,
            },
            "policies": [
                {
                    "id": str(p.id),
                    "hubspot_ticket_id": p.hubspot_ticket_id,
                    "client_name": p.client.name if p.client else None,
                    "benefit_type": p.benefit_type,
                    "segment": p.segment,
                    "mrr_projected": str(p.mrr_projected) if p.mrr_projected else None,
                    "mrr_for_commission": str(p.mrr_for_commission) if p.mrr_for_commission else None,
                    "closed_date": p.closed_date.isoformat() if p.closed_date else None,
                    "commission_status": p.commission_status,
                }
                for p in policies
            ],
            "commissions": [
                {
                    "id": str(c.id),
                    "quarter": c.quarter,
                    "year": c.year,
                    "segment": c.segment,
                    "achievement_pct": str(c.achievement_pct) if c.achievement_pct else None,
                    "commission_pct": str(c.commission_pct) if c.commission_pct else None,
                    "total_estimated": str(c.total_estimated) if c.total_estimated else None,
                    "total_actual": str(c.total_actual) if c.total_actual else None,
                    "is_final": c.is_final,
                }
                for c in commissions
            ],
        }
    })

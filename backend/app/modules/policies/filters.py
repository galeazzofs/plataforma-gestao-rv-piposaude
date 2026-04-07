"""Centralized policy filters.

Use these query builders for any feature that should only see policies
tied to active EV users (Apólices page, dashboards, calculator, etc).
"""
from app.models import Policy, User, UserRole
from app.extensions import db


def active_ev_policies_query():
    """Base query returning only policies whose ev_id resolves to an
    active user with role=EV.

    Use as starting point for further filters:
        active_ev_policies_query().filter(Policy.year == 2026).all()
    """
    return (
        db.session.query(Policy)
        .join(User, Policy.ev_id == User.id)
        .filter(User.role == UserRole.EV, User.active.is_(True))
    )

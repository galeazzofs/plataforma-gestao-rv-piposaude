"""Centralized policy filters.

Use these query builders for any feature that should only see policies
tied to commissionable EV users (active EVs plus EVs flagged as having
left the company but still eligible for policy commission).
"""
from sqlalchemy import or_

from app.models import Policy, User, UserRole
from app.extensions import db


def active_ev_policies_query():
    """Base query returning policies whose ev_id resolves to a
    commissionable user with role=EV.

    Use as starting point for further filters:
        active_ev_policies_query().filter(Policy.year == 2026).all()
    """
    return (
        db.session.query(Policy)
        .join(User, Policy.ev_id == User.id)
        .filter(
            User.role == UserRole.EV,
            or_(User.active.is_(True), User.left_company.is_(True)),
        )
    )


def all_ev_policies_query():
    """Base query returning policies for ALL EVs (active and inactive).

    Used by ADMIN/FINANCE views that need the complete picture.
    """
    return (
        db.session.query(Policy)
        .join(User, Policy.ev_id == User.id)
        .filter(User.role.in_([UserRole.EV, UserRole.CN]))
    )

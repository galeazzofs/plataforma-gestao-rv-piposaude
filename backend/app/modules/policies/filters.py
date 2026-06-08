"""Centralized policy filters.

Use these query builders for any feature that should only see policies
tied to EV users (role=EV), regardless of the EV's account state.
"""
from app.models import Policy, User, UserRole
from app.extensions import db


def ev_policies_query():
    """Base query returning policies whose ev_id resolves to a user with
    role=EV — regardless of whether that EV's account is active or whether
    the EV has left the company.

    Commissionability of an already-sold policy must never depend on the
    EV's account flags: deactivating or soft-deleting a user (which only
    flips ``active``) must not silently drop their apuração. Exclusion of
    non-paying policies is driven solely by ``Policy.commission_status``
    (CANCELLED / SETTLED) at each call site, never by the EV's user row.

    Use as starting point for further filters:
        ev_policies_query().filter(Policy.year == 2026).all()
    """
    return (
        db.session.query(Policy)
        .join(User, Policy.ev_id == User.id)
        .filter(User.role == UserRole.EV)
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

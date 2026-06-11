"""Role-based scoping for endpoints that read one EV's data."""
import uuid

from app.extensions import db
from app.models import User, UserRole


class EvScopeError(Exception):
    """The requested ev_id is outside what the user's role allows."""


def resolve_ev_scope(user, requested_ev_id):
    """Return the effective ev_id for a per-EV read.

    Returns None when the role requires an explicit target and none was
    given (callers answer 400). Raises EvScopeError when the request is
    outside the user's scope — an explicit 403 over silently swapping the
    target, so abuse is visible.

    EV/CN are always themselves. LIDER_VENDAS may target only members of
    the own team; a líder without a team has no scope at all (never the
    bucket of team-less users a team_id IS NULL filter would match).
    ADMIN/FINANCE are unrestricted.
    """
    if user.role in (UserRole.EV, UserRole.CN):
        own = str(user.id)
        if requested_ev_id and requested_ev_id != own:
            raise EvScopeError(requested_ev_id)
        return own

    if user.role == UserRole.LIDER_VENDAS:
        if not requested_ev_id:
            return None
        if user.team_id is None:
            raise EvScopeError(requested_ev_id)
        try:
            target_id = uuid.UUID(str(requested_ev_id))
        except (ValueError, TypeError):
            raise EvScopeError(requested_ev_id)
        target = db.session.get(User, target_id)
        if target is None or target.team_id != user.team_id:
            raise EvScopeError(requested_ev_id)
        return str(target_id)

    return requested_ev_id or None

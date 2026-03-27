from app.extensions import db
from app.models import Notification, User


def create_notification(user_id, type_, title, message, metadata=None):
    """Create an in-app notification."""
    notification = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        message=message,
        metadata_=metadata or {},
    )
    db.session.add(notification)
    db.session.flush()
    return notification


def notify_users_by_role(role, type_, title, message, metadata=None):
    """Send notification to all users with a specific role."""
    users = User.query.filter_by(role=role, active=True).all()
    for user in users:
        create_notification(user.id, type_, title, message, metadata)
    return len(users)


def notify_ev_team(ev_ids, type_, title, message, metadata=None):
    """Send notification to a list of EV user IDs."""
    for ev_id in ev_ids:
        create_notification(ev_id, type_, title, message, metadata)
    return len(ev_ids)

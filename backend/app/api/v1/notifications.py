from flask import Blueprint, jsonify, request, g
from app.auth.decorators import require_auth
from app.models import Notification
from app.api.middlewares import paginate_query
from app.extensions import db

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")


@notifications_bp.route("")
@require_auth
def list_notifications():
    """List notifications for the current user."""
    user = g.current_user
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    unread_only = request.args.get("unread_only", "false").lower() == "true"

    query = Notification.query.filter_by(user_id=user.id)

    if unread_only:
        query = query.filter_by(read=False)

    query = query.order_by(Notification.created_at.desc())
    items, meta = paginate_query(query, page, per_page)

    # Count unread
    unread_count = Notification.query.filter_by(user_id=user.id, read=False).count()

    return jsonify({
        "data": [_serialize_notification(n) for n in items],
        "meta": {**meta, "unread_count": unread_count},
    })


@notifications_bp.route("/<notification_id>/read", methods=["POST"])
@require_auth
def mark_read(notification_id):
    """Mark a single notification as read."""
    user = g.current_user
    notification = db.session.get(Notification, notification_id)
    if notification is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Notification not found"}}), 404

    if notification.user_id != user.id:
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Access denied"}}), 403

    notification.read = True
    db.session.commit()

    return jsonify({"data": _serialize_notification(notification)})


@notifications_bp.route("/read-all", methods=["POST"])
@require_auth
def mark_all_read():
    """Mark all notifications as read for the current user."""
    user = g.current_user
    updated = Notification.query.filter_by(user_id=user.id, read=False).update({"read": True})
    db.session.commit()

    return jsonify({"data": {"updated": updated}})


def _serialize_notification(n):
    return {
        "id": str(n.id),
        "user_id": str(n.user_id),
        "type": n.type,
        "title": n.title,
        "message": n.message,
        "read": n.read,
        "metadata": n.metadata_,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }

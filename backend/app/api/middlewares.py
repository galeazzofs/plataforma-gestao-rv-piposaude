from flask import g
from app.extensions import db
from app.models import AuditLog


def log_audit(table_name, record_id, action, old_values=None, new_values=None):
    """Log an audit entry for data changes."""
    user_id = getattr(g, "current_user", None)
    if user_id and hasattr(user_id, "id"):
        user_id = user_id.id

    entry = AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        old_values=old_values,
        new_values=new_values,
        user_id=user_id,
    )
    db.session.add(entry)


def paginate_query(query, page, per_page, max_per_page=100):
    """Apply pagination to a SQLAlchemy query.

    Returns (items, meta_dict).
    """
    per_page = min(per_page, max_per_page)
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": (total + per_page - 1) // per_page,
    }

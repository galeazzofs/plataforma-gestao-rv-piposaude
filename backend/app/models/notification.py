import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID, JSONType


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    user_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=True)
    read = db.Column(db.Boolean, default=False, nullable=False)
    metadata_ = db.Column("metadata", JSONType, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = db.relationship("User", foreign_keys=[user_id])

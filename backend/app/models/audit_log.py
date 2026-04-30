import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID, JSONType


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    table_name = db.Column(db.String(100), nullable=False, index=True)
    record_id = db.Column(GUID, nullable=False, index=True)
    action = db.Column(db.String(32), nullable=False)  # CREATE, UPDATE, DELETE, UPSERT, PARTIAL_MATCH, BATCH_CALCULATE
    old_values = db.Column(JSONType, nullable=True)
    new_values = db.Column(JSONType, nullable=True)
    user_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<AuditLog {self.action} {self.table_name} {self.record_id}>"

import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class ValidationStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    CONTESTED = "CONTESTED"
    RESOLVED = "RESOLVED"
    AUTO_APPROVED = "AUTO_APPROVED"


class EvValidation(db.Model):
    __tablename__ = "ev_validations"

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    appraisal_id = db.Column(
        GUID, db.ForeignKey("appraisals.id"), nullable=False
    )
    policy_id = db.Column(GUID, db.ForeignKey("policies.id"), nullable=False)
    ev_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(
        db.Enum(ValidationStatus, name="validation_status"),
        default=ValidationStatus.PENDING,
        nullable=False,
    )
    comment = db.Column(db.Text, nullable=True)
    resolution_comment = db.Column(db.Text, nullable=True)
    contested_at = db.Column(db.DateTime(timezone=True), nullable=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    resolved_by = db.Column(GUID, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    appraisal = db.relationship("Appraisal", back_populates="validations")
    policy = db.relationship("Policy", foreign_keys=[policy_id])
    ev = db.relationship("User", foreign_keys=[ev_id])
    resolver = db.relationship("User", foreign_keys=[resolved_by])

import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class AppraisalStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CALCULATING = "CALCULATING"
    VALIDATING = "VALIDATING"
    LIDER_REVIEW = "LIDER_REVIEW"
    REVOPS_REVIEW = "REVOPS_REVIEW"
    LOCKED = "LOCKED"


class Appraisal(db.Model):
    __tablename__ = "appraisals"
    __table_args__ = (
        db.UniqueConstraint("quarter", "year", name="uq_appraisal_quarter_year"),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    cycle_id = db.Column(
        GUID, db.ForeignKey("quarterly_cycles.id"), nullable=True, index=True,
    )
    status = db.Column(
        db.Enum(AppraisalStatus, name="appraisal_status"),
        default=AppraisalStatus.DRAFT,
        nullable=False,
    )
    validation_deadline = db.Column(db.Date, nullable=True)
    created_by = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    approved_by_finance = db.Column(
        GUID, db.ForeignKey("users.id"), nullable=True
    )
    locked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    has_contestation = db.Column(db.Boolean, default=False, nullable=False)
    contestation_note = db.Column(db.Text, nullable=True)
    resolution_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    creator = db.relationship("User", foreign_keys=[created_by])
    approver = db.relationship("User", foreign_keys=[approved_by_finance])
    validations = db.relationship("EvValidation", back_populates="appraisal")

    def __repr__(self):
        return f"<Appraisal Q{self.quarter}/{self.year} ({self.status})>"

    @property
    def is_locked(self):
        return self.status == AppraisalStatus.LOCKED

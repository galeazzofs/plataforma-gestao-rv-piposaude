import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class QuarterlyCycleStatus(str, enum.Enum):
    OPEN = "OPEN"
    LOCKED = "LOCKED"


class QuarterlyCycle(db.Model):
    __tablename__ = "quarterly_cycles"
    __table_args__ = (
        db.UniqueConstraint("quarter", "year", name="uq_quarterly_cycle_quarter_year"),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.Enum(QuarterlyCycleStatus, name="quarterly_cycle_status"),
        default=QuarterlyCycleStatus.OPEN,
        nullable=False,
    )
    created_by = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    locked_at = db.Column(db.DateTime(timezone=True), nullable=True)

    creator = db.relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<QuarterlyCycle Q{self.quarter}/{self.year} ({self.status.value})>"

import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class MonthlyCycleStatus(str, enum.Enum):
    OPEN = "OPEN"
    LOCKED = "LOCKED"


class MonthlyCycle(db.Model):
    __tablename__ = "monthly_cycles"
    __table_args__ = (
        db.UniqueConstraint("month", "year", name="uq_monthly_cycle_month_year"),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    month = db.Column(db.Integer, nullable=False)  # 1–12
    year = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.Enum(MonthlyCycleStatus, name="monthly_cycle_status"),
        default=MonthlyCycleStatus.OPEN,
        nullable=False,
    )
    created_by = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    locked_at = db.Column(db.DateTime(timezone=True), nullable=True)

    creator = db.relationship("User", foreign_keys=[created_by])

    @property
    def quarter(self) -> int:
        return (self.month - 1) // 3 + 1

    @property
    def is_quarter_end(self) -> bool:
        """Quarter-end months (3, 6, 9, 12) also carry the quarterly
        bonus components (Bônus CN, Bônus EV, Bônus Liderança)."""
        return self.month % 3 == 0

    def __repr__(self):
        return f"<MonthlyCycle {self.month:02d}/{self.year} ({self.status.value})>"

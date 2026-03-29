import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class Goal(db.Model):
    __tablename__ = "goals"
    __table_args__ = (
        db.UniqueConstraint("ev_id", "quarter", "year", name="uq_goal_ev_quarter_year"),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    ev_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    mrr_target = db.Column(db.Numeric(12, 2), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    ev = db.relationship("User", foreign_keys=[ev_id])

    def __repr__(self):
        return f"<Goal EV={self.ev_id} Q{self.quarter}/{self.year} target={self.mrr_target}>"

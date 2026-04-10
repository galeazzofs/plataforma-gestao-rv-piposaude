import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class EvQuarterAchievement(db.Model):
    """Stores the final achievement % for each EV in each quarter.

    The achievement is based on MRR gongoed in that quarter vs the EV's target.
    Once is_final=True (after Finance approval), it cannot be changed.
    This is used to determine the commission % for all policies gongoed in that quarter,
    even when those policies are paid out in future quarters.
    """
    __tablename__ = "ev_quarter_achievements"
    __table_args__ = (
        db.UniqueConstraint("ev_id", "quarter", "year", name="uq_ev_quarter_achievement"),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    ev_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    total_mrr = db.Column(db.Numeric(12, 2), nullable=True)
    mrr_target = db.Column(db.Numeric(12, 2), nullable=True)
    achievement_pct = db.Column(db.Numeric(8, 4), nullable=True)
    is_final = db.Column(db.Boolean, default=False, nullable=False)
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
        return f"<EvQuarterAchievement ev={self.ev_id} Q{self.quarter}/{self.year} ach={self.achievement_pct}>"

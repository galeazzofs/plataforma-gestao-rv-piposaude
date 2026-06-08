import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class Commission(db.Model):
    __tablename__ = "commissions"
    __table_args__ = (
        db.UniqueConstraint(
            "policy_id", "month", "year", name="uq_commission_policy_month_year"
        ),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    policy_id = db.Column(GUID, db.ForeignKey("policies.id"), nullable=False)
    ev_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1–12
    year = db.Column(db.Integer, nullable=False)
    segment = db.Column(db.String(10), nullable=True)
    achievement_pct = db.Column(db.Numeric(8, 4), nullable=True)
    commission_pct = db.Column(db.Numeric(8, 4), nullable=True)
    commission_pct_version = db.Column(db.Integer, nullable=True)
    monthly_estimated = db.Column(db.Numeric(12, 2), nullable=True)
    monthly_actual = db.Column(db.Numeric(12, 2), nullable=True)
    total_estimated = db.Column(db.Numeric(12, 2), nullable=True)
    total_actual = db.Column(db.Numeric(12, 2), nullable=True)
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
    policy = db.relationship("Policy", back_populates="commissions")
    ev = db.relationship("User", foreign_keys=[ev_id])

    def __repr__(self):
        return f"<Commission policy={self.policy_id} {self.month:02d}/{self.year}>"

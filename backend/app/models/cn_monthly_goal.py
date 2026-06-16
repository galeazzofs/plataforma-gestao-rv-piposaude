import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class CnMonthlyGoal(db.Model):
    __tablename__ = "cn_monthly_goals"
    __table_args__ = (
        db.UniqueConstraint("cn_id", "month", "year", name="uq_cn_monthly_goal"),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    cn_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    month = db.Column(db.Integer, nullable=False)   # 1–12
    year = db.Column(db.Integer, nullable=False)
    sao_target = db.Column(db.Numeric(12, 2), nullable=False)
    vidas_target = db.Column(db.Numeric(12, 2), nullable=False)
    negocios_cadencia_meta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    emails_meta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    qualis_agendadas_meta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    cn = db.relationship("User", foreign_keys=[cn_id])

    def __repr__(self):
        return f"<CnMonthlyGoal cn={self.cn_id} {self.month}/{self.year}>"

import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class CnMonthlyAppraisal(db.Model):
    __tablename__ = "cn_monthly_appraisals"
    __table_args__ = (
        db.UniqueConstraint("cn_id", "month", "year", name="uq_cn_monthly_appraisal"),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    cn_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    sao_realizado = db.Column(db.Numeric(12, 2), nullable=False)
    vidas_realizado = db.Column(db.Numeric(12, 2), nullable=False)
    pct_sao = db.Column(db.Numeric(8, 4), nullable=False)
    pct_vidas = db.Column(db.Numeric(8, 4), nullable=False)
    score_final = db.Column(db.Numeric(8, 4), nullable=False)
    multiplicador = db.Column(db.Numeric(8, 4), nullable=False)
    commission_amount = db.Column(db.Numeric(12, 2), nullable=False)
    is_final = db.Column(db.Boolean, default=False, nullable=False)
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
        return f"<CnMonthlyAppraisal cn={self.cn_id} {self.month}/{self.year} final={self.is_final}>"

import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class CnQuarterBonus(db.Model):
    __tablename__ = "cn_quarter_bonuses"
    __table_args__ = (
        db.UniqueConstraint(
            "cn_id", "quarter", "year",
            name="uq_cn_quarter_bonus",
        ),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    cn_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    sao_trim_realizado = db.Column(db.Numeric(12, 2), nullable=False)
    sao_trim_meta = db.Column(db.Numeric(12, 2), nullable=False)
    pct_sao_trim = db.Column(db.Numeric(8, 4), nullable=False)
    multiplicador = db.Column(db.Numeric(8, 4), nullable=False)
    bonus_amount = db.Column(db.Numeric(12, 2), nullable=False)
    salario_base_snapshot = db.Column(db.Numeric(12, 2), nullable=True)
    is_final = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    cn = db.relationship("User", foreign_keys=[cn_id])

    def __repr__(self):
        return (
            f"<CnQuarterBonus cn={self.cn_id} Q{self.quarter}/{self.year} "
            f"final={self.is_final}>"
        )

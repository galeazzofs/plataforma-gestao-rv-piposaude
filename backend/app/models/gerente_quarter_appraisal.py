import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class GerenteQuarterAppraisal(db.Model):
    __tablename__ = "gerente_quarter_appraisals"
    __table_args__ = (
        db.UniqueConstraint(
            "gerente_id", "quarter", "year",
            name="uq_gerente_quarter_appraisal"
        ),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    gerente_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    meta_mrr = db.Column(db.Numeric(12, 2), nullable=False)
    meta_sql = db.Column(db.Integer, nullable=False)
    realizado_mrr = db.Column(db.Numeric(12, 2), nullable=False)
    realizado_sql = db.Column(db.Integer, nullable=False)
    pct_mrr = db.Column(db.Numeric(8, 4), nullable=False)
    pct_sql = db.Column(db.Numeric(8, 4), nullable=False)
    multiplicador = db.Column(db.Numeric(8, 4), nullable=False)
    bonus_amount = db.Column(db.Numeric(12, 2), nullable=False)
    is_final = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    gerente = db.relationship("User", foreign_keys=[gerente_id])

    def __repr__(self):
        return f"<GerenteQuarterAppraisal gerente={self.gerente_id} Q{self.quarter}/{self.year}>"

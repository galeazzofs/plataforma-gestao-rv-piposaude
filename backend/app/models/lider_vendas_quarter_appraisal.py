import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.hybrid import hybrid_property

from app.extensions import db
from app.models.compat import GUID
from app.models.appraisal import AppraisalStatus


class LiderVendasQuarterAppraisal(db.Model):
    __tablename__ = "lider_vendas_quarter_appraisals"
    __table_args__ = (
        db.UniqueConstraint(
            "lider_vendas_id", "quarter", "year",
            name="uq_lider_vendas_quarter_appraisal"
        ),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    lider_vendas_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
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
    status = db.Column(
        db.Enum(AppraisalStatus, name="lider_vendas_quarter_appraisal_status"),
        default=AppraisalStatus.DRAFT,
        nullable=False,
    )
    has_contestation = db.Column(db.Boolean, default=False, nullable=False)
    contestation_note = db.Column(db.Text, nullable=True)
    resolution_note = db.Column(db.Text, nullable=True)
    last_action_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reminder_sent_at = db.Column(db.Date, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    lider_vendas = db.relationship("User", foreign_keys=[lider_vendas_id])

    @hybrid_property
    def is_final(self):
        return self.status == AppraisalStatus.LOCKED

    @is_final.expression
    def is_final(cls):  # noqa: N805 — hybrid_property convention
        return cls.status == AppraisalStatus.LOCKED

    def __repr__(self):
        return (
            f"<LiderVendasQuarterAppraisal lider_vendas={self.lider_vendas_id} "
            f"Q{self.quarter}/{self.year} status="
            f"{self.status.value if self.status else None}>"
        )

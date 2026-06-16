import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.hybrid import hybrid_property

from app.extensions import db
from app.models.compat import GUID
from app.models.appraisal import AppraisalStatus


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
    calc_mode = db.Column(db.String(32), nullable=False, default="NORMAL")
    negocios_cadencia_realizado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    emails_realizado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    qualis_agendadas_realizado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    sao_fora_da_meta = db.Column(db.Integer, nullable=False, default=0)
    bonus_sao_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    status = db.Column(
        db.Enum(AppraisalStatus, name="cn_monthly_appraisal_status"),
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

    cn = db.relationship("User", foreign_keys=[cn_id])

    @hybrid_property
    def is_final(self):
        return self.status == AppraisalStatus.LOCKED

    @is_final.expression
    def is_final(cls):  # noqa: N805 — hybrid_property convention
        return cls.status == AppraisalStatus.LOCKED

    def __repr__(self):
        return (
            f"<CnMonthlyAppraisal cn={self.cn_id} {self.month}/{self.year} "
            f"status={self.status.value if self.status else None}>"
        )

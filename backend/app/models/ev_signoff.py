import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class SignoffStatus(str, enum.Enum):
    PENDING = "PENDING"
    DONE = "DONE"


class EvSignoff(db.Model):
    """Conferência do RevOps por EV numa Apuração mensal.

    Uma linha por (apuração, EV do escopo). Uma linha DONE carrega o
    fingerprint dos valores do EV no momento da conferência; um recálculo
    que muda os valores volta a linha para PENDING com values_changed=True
    (spec docs/superpowers/specs/2026-07-07-conferencia-ev-por-ev-design.md).
    """
    __tablename__ = "ev_signoffs"
    __table_args__ = (
        db.UniqueConstraint(
            "appraisal_id", "ev_id", name="uq_ev_signoff_appraisal_ev",
        ),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    appraisal_id = db.Column(
        GUID, db.ForeignKey("appraisals.id"), nullable=False,
    )
    ev_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(
        db.Enum(SignoffStatus, name="signoff_status"),
        default=SignoffStatus.PENDING,
        nullable=False,
    )
    fingerprint = db.Column(db.String(64), nullable=True)
    values_changed = db.Column(db.Boolean, default=False, nullable=False)
    signed_off_by = db.Column(GUID, db.ForeignKey("users.id"), nullable=True)
    signed_off_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    appraisal = db.relationship("Appraisal", foreign_keys=[appraisal_id])
    ev = db.relationship("User", foreign_keys=[ev_id])
    signer = db.relationship("User", foreign_keys=[signed_off_by])

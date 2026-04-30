import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class BenefitType(str, enum.Enum):
    SAUDE = "SAUDE"
    ODONTO = "ODONTO"
    VIDA = "VIDA"
    SAUDE_ODONTO = "SAUDE_ODONTO"


class Segment(str, enum.Enum):
    PP = "PP"
    P = "P"
    M = "M"
    G = "G"


class CommissionStatus(str, enum.Enum):
    PROJECTED = "PROJECTED"
    IN_PAYMENT = "IN_PAYMENT"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


class Policy(db.Model):
    __tablename__ = "policies"

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    hubspot_apolice_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    hubspot_ticket_id = db.Column(db.String(100), nullable=False, index=True)
    numero_apolice = db.Column(db.String(100), nullable=True, index=True)
    ev_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=True)
    client_id = db.Column(GUID, db.ForeignKey("clients.id"), nullable=True)
    deal_id = db.Column(db.String(100), nullable=True)
    benefit_type = db.Column(db.Enum(BenefitType, name="benefit_type"), nullable=True)
    segment = db.Column(db.Enum(Segment, name="segment"), nullable=True)
    headcount = db.Column(db.Integer, nullable=True)
    mrr_projected = db.Column(db.Numeric(12, 2), nullable=True)
    mrr_post_deploy = db.Column(db.Numeric(12, 2), nullable=True)
    mrr_actual = db.Column(db.Numeric(12, 2), nullable=True)
    closed_date = db.Column(db.Date, nullable=True)
    deploy_date = db.Column(db.Date, nullable=True)
    first_payment_prev = db.Column(db.Date, nullable=True)
    first_payment_real = db.Column(db.Date, nullable=True)
    installments_paid = db.Column(db.Integer, default=0, nullable=False)
    initial_installments_paid = db.Column(db.Integer, default=0, nullable=False, server_default="0")
    is_locked = db.Column(db.Boolean, nullable=False, default=False, server_default='false')
    commission_status = db.Column(
        db.Enum(CommissionStatus, name="commission_status"),
        default=CommissionStatus.PROJECTED,
        nullable=False,
    )
    partner_operator = db.Column(db.String(255), nullable=True)
    deal_stage = db.Column(db.String(100), nullable=True)
    commission_paid_legacy = db.Column(db.Numeric(12, 2), nullable=True)
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
    client = db.relationship("Client", back_populates="policies")
    commissions = db.relationship("Commission", back_populates="policy")

    def __repr__(self):
        return f"<Policy apolice={self.hubspot_apolice_id} ticket={self.hubspot_ticket_id} ({self.commission_status})>"

    @property
    def mrr_for_commission(self):
        """MRR cascade: actual > post_deploy > projected."""
        if self.mrr_actual is not None:
            return self.mrr_actual
        if self.mrr_post_deploy is not None:
            return self.mrr_post_deploy
        return self.mrr_projected

    @property
    def quarter_closed(self):
        """Quarter when deal was closed (gongo)."""
        if self.closed_date is None:
            return None, None
        q = (self.closed_date.month - 1) // 3 + 1
        return q, self.closed_date.year

    @property
    def commission_paid_total(self):
        """Sum of total_actual across this policy's commissions, plus the
        legacy manual amount for policies that pre-date the platform."""
        from decimal import Decimal
        total = Decimal("0")
        for c in self.commissions or []:
            if c.total_actual is not None:
                total += c.total_actual
        if self.commission_paid_legacy is not None:
            total += self.commission_paid_legacy
        return total

    @property
    def commission_potential(self):
        """MRR x 12 x commission_pct.

        % cascade: if any apuração already produced a commission_pct for
        this policy, use the most recent one. Otherwise look up the base
        rate for this segment at 100% achievement (the floor a fully
        on-target EV would receive)."""
        from decimal import Decimal
        from app.models import CommissionPctTable

        mrr = self.mrr_for_commission
        if mrr is None:
            return None

        pct = None
        if self.commissions:
            latest = max(
                (c for c in self.commissions if c.commission_pct is not None),
                key=lambda c: (c.year, c.quarter),
                default=None,
            )
            if latest is not None:
                pct = latest.commission_pct

        if pct is None and self.segment is not None:
            row = CommissionPctTable.lookup(self.segment.value, Decimal("1.0"))
            if row is not None:
                pct = row.commission_pct

        if pct is None:
            return None

        return (Decimal(str(mrr)) * Decimal("12") * Decimal(str(pct))).quantize(Decimal("0.01"))

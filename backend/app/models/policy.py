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
    hubspot_apolice_id = db.Column(db.String(100), nullable=True, index=True)
    hubspot_ticket_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    numero_apolice = db.Column(db.Text, nullable=True)
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
    # Stamped by the HubSpot sync when the ticket vanished from the fetch but
    # the policy carries paid (LOCKED) history and was preserved + cancelled
    # instead of hard-deleted. Cleared only by human review.
    sync_absent_since = db.Column(db.DateTime(timezone=True), nullable=True)
    commission_status = db.Column(
        db.Enum(CommissionStatus, name="commission_status"),
        default=CommissionStatus.PROJECTED,
        nullable=False,
    )
    partner_operator = db.Column(db.String(255), nullable=True)
    deal_stage = db.Column(db.String(100), nullable=True)
    commission_paid_legacy = db.Column(db.Numeric(12, 2), nullable=True)
    total_paid_comissao = db.Column(db.Numeric(12, 2), nullable=True, server_default="0")
    total_paid_agenciamento = db.Column(db.Numeric(12, 2), nullable=True, server_default="0")
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
    def comissao_paga(self):
        """EV-payable Comissao paid for this policy (Escala pagavel ao EV).

        The frozen manual pre-platform baseline plus the Comissao cut of every
        finalized apuracao (see CONTEXT.md 'Comissao paga da apolice')."""
        from decimal import Decimal
        from app.modules.financial.paid_split import policy_apuracao_paid
        comissao, _agenciamento = policy_apuracao_paid(self)
        return Decimal(str(self.total_paid_comissao or "0")) + comissao

    @property
    def agenciamento_pago(self):
        """EV-payable Agenciamento paid for this policy (Escala pagavel ao EV).

        Frozen manual pre-platform baseline plus the Agenciamento cut of every
        finalized apuracao (see CONTEXT.md 'Agenciamento pago da apolice')."""
        from decimal import Decimal
        from app.modules.financial.paid_split import policy_apuracao_paid
        _comissao, agenciamento = policy_apuracao_paid(self)
        return Decimal(str(self.total_paid_agenciamento or "0")) + agenciamento

    @property
    def total_pago(self):
        """Total paid to the EV: Comissao paga + Agenciamento pago
        (see CONTEXT.md 'Total pago da apolice')."""
        return self.comissao_paga + self.agenciamento_pago

    @property
    def commission_potential(self):
        """MRR × 12 × commission_pct.

        commission_pct is looked up from the EV's achievement in the
        apolice's gongo quarter (same snapshot the calculator uses when
        stamping a Commission row), so 'potential' tracks what the EV
        will actually earn for the full 12-month vigência.

        Returns None if any of segment / closed_date / ev_id / mrr is
        missing — those cases can't produce a meaningful potential."""
        from decimal import Decimal
        from app.models import CommissionPctTable, EvQuarterAchievement

        mrr = self.mrr_for_commission
        if mrr is None or self.segment is None:
            return None
        if self.closed_date is None or self.ev_id is None:
            return None

        gongo_q = (self.closed_date.month - 1) // 3 + 1
        gongo_y = self.closed_date.year
        ach = EvQuarterAchievement.query.filter_by(
            ev_id=self.ev_id, quarter=gongo_q, year=gongo_y,
        ).first()
        # When the EV has no achievement on file for this quarter we
        # mirror the calculator's behaviour and treat it as 0 — i.e. the
        # lowest tier of CommissionPctTable, not "unknown / null".
        achievement = ach.achievement_pct if ach else Decimal("0")

        row = CommissionPctTable.lookup(self.segment.value, achievement)
        if row is None:
            return None

        return (
            Decimal(str(mrr)) * Decimal("12") * Decimal(str(row.commission_pct))
        ).quantize(Decimal("0.01"))

import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class ImportBatch(db.Model):
    __tablename__ = "import_batches"

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    filename = db.Column(db.String(500), nullable=False)
    uploaded_by = db.Column(GUID, db.ForeignKey("users.id"), nullable=False)
    nf_count = db.Column(db.Integer, default=0)
    perk_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="PENDING")  # PENDING, CONFIRMED, CANCELLED
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    uploader = db.relationship("User", foreign_keys=[uploaded_by])


class FinancialImport(db.Model):
    __tablename__ = "financial_imports"

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    policy_id = db.Column(GUID, db.ForeignKey("policies.id"), nullable=True)
    nf_valor_liquido = db.Column(db.Numeric(12, 2), nullable=False)
    nf_mes_recebimento = db.Column(db.String(7), nullable=False)  # YYYY-MM
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    import_batch_id = db.Column(GUID, db.ForeignKey("import_batches.id"), nullable=False)

    cliente_mae = db.Column(db.String(500), nullable=True)
    operadora = db.Column(db.String(255), nullable=True)
    produto = db.Column(db.String(50), nullable=True)
    tipo_receita = db.Column(db.String(100), nullable=True)
    status_recebimento = db.Column(db.String(50), nullable=True)
    data_recebimento = db.Column(db.Date, nullable=True)
    match_status = db.Column(db.String(30), nullable=False, default='UNMATCHED', server_default='UNMATCHED')
    matched_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    policy = db.relationship("Policy", foreign_keys=[policy_id])
    batch = db.relationship("ImportBatch", foreign_keys=[import_batch_id])

import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class Perk(db.Model):
    __tablename__ = "perks"

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    client_id = db.Column(GUID, db.ForeignKey("clients.id"), nullable=False)
    quarter = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    import_batch_id = db.Column(
        GUID, db.ForeignKey("import_batches.id"), nullable=False
    )
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    client = db.relationship("Client", foreign_keys=[client_id])
    batch = db.relationship("ImportBatch", foreign_keys=[import_batch_id])

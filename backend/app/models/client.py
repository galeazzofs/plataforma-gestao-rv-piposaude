import uuid
import unicodedata
import re
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


def normalize_client_name(name):
    """Normalize company name: lowercase, strip accents, trim whitespace."""
    name = name.strip().lower()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"\s+", " ", name)
    return name


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(500), nullable=False, index=True)
    name_normalized = db.Column(db.String(500), unique=True, nullable=False, index=True)
    hubspot_company_id = db.Column(db.String(100), nullable=True)
    ev_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=True)
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
    policies = db.relationship("Policy", back_populates="client")

    def __repr__(self):
        return f"<Client {self.name}>"

    @classmethod
    def find_or_create(cls, name, ev_id=None):
        """Find by normalized name or create new client."""
        normalized = normalize_client_name(name)
        client = cls.query.filter_by(name_normalized=normalized).first()
        if client is None:
            client = cls(name=name, name_normalized=normalized, ev_id=ev_id)
            db.session.add(client)
        return client

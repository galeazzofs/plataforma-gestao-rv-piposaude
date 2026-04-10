import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    FINANCE = "FINANCE"
    GERENTE = "GERENTE"
    EV = "EV"
    CN = "CN"


class CnNivel(str, enum.Enum):
    CN1 = "CN1"
    CN2 = "CN2"
    CN3 = "CN3"


class CnPorte(str, enum.Enum):
    M = "M"
    G_PLUS = "G+"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(UserRole, name="user_role"), nullable=True)
    google_id = db.Column(db.String(255), nullable=True)
    team_id = db.Column(GUID, db.ForeignKey("teams.id"), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    refresh_token = db.Column(db.String(500), nullable=True)
    slack_user_id = db.Column(db.String(50), nullable=True)
    # CN-specific profile fields
    nivel = db.Column(db.Enum("CN1", "CN2", "CN3", name="cn_nivel"), nullable=True)
    porte = db.Column(db.Enum("M", "G+", name="cn_porte"), nullable=True)
    salario_base = db.Column(db.Numeric(12, 2), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    team = db.relationship("Team", back_populates="members", foreign_keys=[team_id])

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"

    def has_role(self, *roles):
        return self.role in roles

    def is_admin(self):
        return self.role == UserRole.ADMIN

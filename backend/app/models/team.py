import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    leader_id = db.Column(GUID, db.ForeignKey("users.id"), nullable=True)
    slack_channel_id = db.Column(db.String(50), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    leader = db.relationship("User", foreign_keys=[leader_id])
    members = db.relationship(
        "User", back_populates="team", foreign_keys="User.team_id"
    )

    def __repr__(self):
        return f"<Team {self.name}>"

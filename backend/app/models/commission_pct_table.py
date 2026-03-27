import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID


class CommissionPctTable(db.Model):
    __tablename__ = "commission_pct_table"
    __table_args__ = (
        db.UniqueConstraint(
            "version", "segment", "achievement_min",
            name="uq_pct_version_segment_min",
        ),
    )

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    version = db.Column(db.Integer, nullable=False, index=True)
    segment = db.Column(db.String(10), nullable=False)
    achievement_min = db.Column(db.Numeric(8, 4), nullable=False)
    achievement_max = db.Column(db.Numeric(8, 4), nullable=False)
    commission_pct = db.Column(db.Numeric(8, 4), nullable=False)
    valid_from = db.Column(db.Date, nullable=True)
    valid_until = db.Column(db.Date, nullable=True)
    created_by = db.Column(GUID, db.ForeignKey("users.id"), nullable=True)

    @classmethod
    def current_version(cls):
        """Get the latest version number."""
        result = db.session.query(db.func.max(cls.version)).scalar()
        return result or 0

    @classmethod
    def lookup(cls, segment, achievement_pct, version=None):
        """Find commission % for given segment and achievement."""
        if version is None:
            version = cls.current_version()
        return cls.query.filter(
            cls.version == version,
            cls.segment == segment,
            cls.achievement_min <= achievement_pct,
            cls.achievement_max >= achievement_pct,
        ).first()

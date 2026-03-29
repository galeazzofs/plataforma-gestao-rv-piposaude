import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.compat import GUID, JSONType


class PlatformSetting(db.Model):
    __tablename__ = "platform_settings"

    id = db.Column(GUID, primary_key=True, default=uuid.uuid4)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(JSONType, nullable=True)
    updated_by = db.Column(GUID, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @classmethod
    def get(cls, key, default=None):
        setting = cls.query.filter_by(key=key).first()
        if setting is None:
            return default
        return setting.value

    @classmethod
    def set(cls, key, value, user_id=None):
        setting = cls.query.filter_by(key=key).first()
        if setting is None:
            setting = cls(key=key, value=value, updated_by=user_id)
            db.session.add(setting)
        else:
            setting.value = value
            setting.updated_by = user_id
        return setting

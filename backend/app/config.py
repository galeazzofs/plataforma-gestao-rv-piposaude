import os


def _split_csv(value):
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class Config:
    """Base configuration."""
    # SECRET_KEY has no fallback in non-test envs — see DevConfig/TestConfig
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://localhost:5432/comissoes_dev"
    )
    JWT_ACCESS_TOKEN_EXPIRES = 8 * 60 * 60
    JWT_REFRESH_TOKEN_EXPIRES = 7 * 24 * 60 * 60
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")
    ALLOWED_EMAIL_DOMAIN = "piposaude.com"
    HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN", "")
    HUBSPOT_SYNC_INTERVAL_MINUTES = int(
        os.environ.get("HUBSPOT_SYNC_INTERVAL_MINUTES", "30")
    )
    SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
    SLACK_OPS_CHANNEL = os.environ.get("SLACK_OPS_CHANNEL", "")
    SLACK_FINANCE_CHANNEL = os.environ.get("SLACK_FINANCE_CHANNEL", "")
    PLATFORM_PUBLIC_URL = os.environ.get("PLATFORM_PUBLIC_URL", "")
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100
    # Reject uploads larger than 100 MB — financial XLSX files are routinely large.
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    # CORS origins — must be explicit per env. No wildcard fallback.
    CORS_ORIGINS = _split_csv(os.environ.get("CORS_ORIGINS"))


class DevConfig(Config):
    DEBUG = True
    # Allow a fallback ONLY in dev so a fresh clone runs out of the box.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    CORS_ORIGINS = _split_csv(os.environ.get("CORS_ORIGINS")) or [
        "http://localhost:3000",
        "http://localhost:8080",
    ]


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "sqlite:///test.db"
    )


class StagConfig(Config):
    DEBUG = False


class ProdConfig(Config):
    DEBUG = False


config_map = {
    "dev": DevConfig,
    "test": TestConfig,
    "stag": StagConfig,
    "prod": ProdConfig,
}
import os


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://localhost:5432/comissoes_dev"
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
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100


class DevConfig(Config):
    DEBUG = True


class TestConfig(Config):
    TESTING = True
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

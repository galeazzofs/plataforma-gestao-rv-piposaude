import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask  # noqa: E402
from app.config import config_map  # noqa: E402
from app.extensions import db, migrate, cors  # noqa: E402


def create_app(config_name=None):
    """Flask application factory."""
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "dev")

    app = Flask(__name__)
    app.config.from_object(config_map[config_name])

    # Hard fail if no SECRET_KEY in non-dev/test envs
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY environment variable must be set in stag/prod. "
            "Set it via .env, container env, or your secrets manager."
        )

    cors_origins = app.config.get("CORS_ORIGINS") or []
    if not cors_origins and config_name in ("stag", "prod"):
        raise RuntimeError(
            "CORS_ORIGINS environment variable must be set in stag/prod. "
            "Comma-separated list of allowed frontend origins."
        )

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": cors_origins or "http://localhost:3000"}},
        supports_credentials=True,
    )

    # Import models so Alembic sees them
    from app import models as _models  # noqa: F401

    # Register blueprints
    from app.api import register_blueprints
    register_blueprints(app)

    # Start HubSpot sync scheduler (skip in testing)
    if not app.config.get("TESTING") and app.config.get("HUBSPOT_TOKEN"):
        from app.modules.hubspot_sync.scheduler import init_scheduler
        init_scheduler(app)

    # Start the daily reminder/escalation cron (skip in testing)
    if not app.config.get("TESTING"):
        from app.modules.workflow.reminders_scheduler import init_reminders_scheduler
        init_reminders_scheduler(app)

    return app
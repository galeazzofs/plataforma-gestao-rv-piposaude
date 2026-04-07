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

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}})

    # Import models so Alembic sees them
    from app import models as _models  # noqa: F401

    # Register blueprints
    from app.api import register_blueprints
    register_blueprints(app)

    # Start HubSpot sync scheduler (skip in testing)
    if not app.config.get("TESTING") and app.config.get("HUBSPOT_TOKEN"):
        from app.modules.hubspot_sync.scheduler import init_scheduler
        init_scheduler(app)

    return app

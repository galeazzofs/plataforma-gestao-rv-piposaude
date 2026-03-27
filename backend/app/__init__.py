import os
from flask import Flask
from app.config import config_map
from app.extensions import db, migrate, cors


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

    # Register blueprints
    from app.api import register_blueprints
    register_blueprints(app)

    return app

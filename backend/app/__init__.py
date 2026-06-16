import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask  # noqa: E402
from app.config import config_map  # noqa: E402
from app.extensions import db, migrate, cors  # noqa: E402


def create_app(config_name=None, *, start_schedulers=True):
    """Flask application factory.

    config_name must be explicit (argument or FLASK_ENV). Defaulting to dev
    here would be fail-open: DevConfig carries a repo-public SECRET_KEY
    fallback, so a deploy that forgot FLASK_ENV would silently boot with
    forgeable JWTs instead of refusing to start.
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV")
    if not config_name:
        raise RuntimeError(
            "FLASK_ENV must be set explicitly (one of: "
            + ", ".join(sorted(config_map)) + "). Refusing to guess an "
            "environment — a wrong default would boot with dev secrets."
        )
    if config_name not in config_map:
        raise RuntimeError(
            f"Unknown FLASK_ENV {config_name!r}. Must be one of: "
            + ", ".join(sorted(config_map))
        )

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

    # Schedulers are skipped in testing and for short-lived processes
    # (bootstrap/seed pass start_schedulers=False so a migration or seed run
    # doesn't fire cron jobs mid-flight).
    if start_schedulers and not app.config.get("TESTING") and app.config.get("HUBSPOT_TOKEN"):
        from app.modules.hubspot_sync.scheduler import init_scheduler
        init_scheduler(app)

    if start_schedulers and not app.config.get("TESTING"):
        from app.modules.workflow.reminders_scheduler import init_reminders_scheduler
        init_reminders_scheduler(app)

    return app
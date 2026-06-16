from flask import Blueprint, jsonify
from app.extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    """Liveness check — app is running."""
    return jsonify({"status": "ok"})


@health_bp.route("/ready")
def ready():
    """Readiness check — DB connected."""
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"status": "ready"})
    except Exception:
        # Unauthenticated endpoint: log the cause server-side, but never echo
        # driver errors (which can carry connection-string fragments).
        import logging
        logging.getLogger(__name__).exception("Readiness check failed")
        return jsonify({"status": "not_ready", "error": "database unavailable"}), 503

def register_blueprints(app):
    """Register all API blueprints."""
    from app.api.v1.health import health_bp
    app.register_blueprint(health_bp)

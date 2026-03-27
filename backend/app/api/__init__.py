def register_blueprints(app):
    from app.api.v1.health import health_bp
    from app.api.v1.auth import auth_bp
    from app.api.v1.admin import admin_bp
    from app.api.v1.policies import policies_bp
    from app.api.v1.commissions import commissions_bp
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(policies_bp)
    app.register_blueprint(commissions_bp)

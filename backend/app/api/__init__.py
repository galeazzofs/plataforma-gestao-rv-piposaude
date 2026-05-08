def register_blueprints(app):
    from app.api.v1.health import health_bp
    from app.api.v1.auth import auth_bp
    from app.api.v1.admin import admin_bp
    from app.api.v1.policies import policies_bp
    from app.api.v1.commissions import commissions_bp
    from app.api.v1.goals import goals_bp
    from app.api.v1.financial import financial_bp
    from app.api.v1.workflow import workflow_bp
    from app.api.v1.validations import validations_bp
    from app.api.v1.finance_dashboard import finance_dashboard_bp
    from app.api.v1.notifications import notifications_bp
    from app.api.v1.lider_vendas import lider_vendas_bp
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(policies_bp)
    app.register_blueprint(commissions_bp)
    app.register_blueprint(goals_bp)
    app.register_blueprint(financial_bp)
    app.register_blueprint(workflow_bp)
    app.register_blueprint(validations_bp)
    app.register_blueprint(finance_dashboard_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(lider_vendas_bp)
    from app.api.v1.cn_commissions import cn_commissions_bp
    from app.api.v1.ev_bonus import ev_bonus_bp
    from app.api.v1.leadership import leadership_bp
    from app.api.v1.quarterly_cycles import quarterly_cycles_bp
    app.register_blueprint(cn_commissions_bp)
    app.register_blueprint(ev_bonus_bp)
    app.register_blueprint(leadership_bp)
    app.register_blueprint(quarterly_cycles_bp)

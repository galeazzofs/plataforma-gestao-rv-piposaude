"""seed.py must be inert outside dev.

entrypoint.sh runs seed.py on every container boot. In stag/prod that used
to upsert the dev E2E scenario (hardcoded ADMIN users, fake goals and
achievements, a CONFIRMED fake financial batch) on top of real data. The
seed must no-op unless the config explicitly allows dev seeding.
"""
import seed as seed_module

from app.models import User


def test_seed_is_noop_when_dev_seed_not_allowed(app, db_session):
    # TestConfig inherits DEV_SEED_ALLOWED=False from the base Config,
    # same as StagConfig/ProdConfig.
    assert app.config.get("DEV_SEED_ALLOWED") is False

    seed_module.seed(app=app)

    assert User.query.count() == 0


def test_seed_runs_when_dev_seed_allowed(app, db_session, monkeypatch):
    monkeypatch.setitem(app.config, "DEV_SEED_ALLOWED", True)

    seed_module.seed(app=app)

    admin = User.query.filter_by(email=seed_module.USER_EMAILS["admin"]).first()
    assert admin is not None


def test_dev_seed_allowed_only_in_dev_config():
    from app.config import Config, DevConfig, StagConfig, ProdConfig

    assert Config.DEV_SEED_ALLOWED is False
    assert DevConfig.DEV_SEED_ALLOWED is True
    assert StagConfig.DEV_SEED_ALLOWED is False
    assert ProdConfig.DEV_SEED_ALLOWED is False

import pytest
from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    """Create application for testing."""
    app = create_app("test")
    with app.app_context():
        yield app


@pytest.fixture(scope="session")
def _setup_db(app):
    """Create all tables once per test session."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture(autouse=True)
def db_session(app, _setup_db):
    """Provide clean DB session for each test."""
    with app.app_context():
        yield _db.session
        _db.session.rollback()


@pytest.fixture
def client(app):
    """Test client for HTTP requests."""
    return app.test_client()

import pytest
from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    """Create application for testing."""
    app = create_app("test")
    # Test sessions bind to a Connection carrying the per-test outer
    # transaction (see db_session). SQLAlchemy's default join mode,
    # "conditional_savepoint", degrades to "rollback_only" when that
    # connection holds no savepoint yet — a session.rollback() anywhere
    # in production code (preview, sync error handling) would then roll
    # back the whole outer transaction, wiping the test's fixtures.
    # "create_savepoint" gives every session true savepoint semantics.
    _db.session.session_factory.configure(
        join_transaction_mode="create_savepoint"
    )
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
    """Run each test inside one outer transaction that is rolled back.

    Every engine in db.engines is swapped for a single Connection holding
    an open transaction. All sessions Flask-SQLAlchemy hands out during
    the test — the test body's and one per request context — bind to that
    connection and join its transaction through a SAVEPOINT (SQLAlchemy's
    default "conditional_savepoint" mode), so even db.session.commit()
    inside an endpoint cannot escape the outer transaction. The final
    rollback discards everything: no state leaks between tests, and an
    interrupted run leaves no rows behind.
    """
    with app.app_context():
        replaced = []
        for key, engine in list(_db.engines.items()):
            connection = engine.connect()
            transaction = connection.begin()
            _db.engines[key] = connection
            replaced.append((key, engine, connection, transaction))

        yield _db.session

        _db.session.remove()
        for key, engine, connection, transaction in replaced:
            if transaction.is_active:
                transaction.rollback()
            connection.close()
            _db.engines[key] = engine


@pytest.fixture
def client(app):
    """Test client for HTTP requests."""
    return app.test_client()

import pytest
from sqlalchemy import text

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
    """Provide a clean DB session for each test.

    Many API tests exercise code paths that commit. A plain rollback after the
    test only clears the current transaction, so committed rows can leak into
    later tests. Clean table data explicitly at the test boundary.
    """
    with app.app_context():
        yield _db.session
        _db.session.rollback()
        _clean_tables(_db)


def _clean_tables(db):
    bind = db.session.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        preparer = bind.dialect.identifier_preparer
        tables = ", ".join(
            preparer.format_table(table)
            for table in db.metadata.sorted_tables
        )
        if tables:
            db.session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
            db.session.commit()
        return

    if dialect == "sqlite":
        db.session.execute(text("PRAGMA foreign_keys=OFF"))

    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())

    if dialect == "sqlite":
        db.session.execute(text("PRAGMA foreign_keys=ON"))

    db.session.commit()


@pytest.fixture
def client(app):
    """Test client for HTTP requests."""
    return app.test_client()

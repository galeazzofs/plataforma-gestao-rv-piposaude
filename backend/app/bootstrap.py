"""Database bootstrap — the only place allowed to choose between
create_all and the Alembic chain.

Rule: db.create_all() may run ONLY against a database Alembic has never
stamped. On an existing, partially-migrated database create_all would build
new tables in their final model shape and the pending migration's
create_table would then fail with DuplicateTable, crash-looping the deploy
(entrypoint.sh runs under set -e). A stamped database only ever moves
forward via `upgrade()`.
"""
from app.extensions import db


def _current_revision():
    from alembic.runtime.migration import MigrationContext

    with db.engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def init_database(app, *, current_revision=None, create_all=None, stamp=None, upgrade=None):
    """Bring the schema up to date. Returns "stamped" or "upgraded".

    The callables are injectable for tests; defaults are the real
    Alembic/SQLAlchemy operations.
    """
    if current_revision is None:
        current_revision = _current_revision
    if create_all is None:
        create_all = db.create_all
    if stamp is None or upgrade is None:
        from flask_migrate import stamp as _stamp, upgrade as _upgrade

        stamp = stamp or _stamp
        upgrade = upgrade or _upgrade

    with app.app_context():
        if current_revision() is None:
            # Never-stamped database (fresh, or legacy pre-Alembic): build
            # missing tables from the models, then mark the chain as applied.
            create_all()
            stamp(revision="head")
            return "stamped"
        upgrade()
        return "upgraded"


def main():
    from app import create_app

    app = create_app(start_schedulers=False)
    result = init_database(app)
    print(f"Database ready ({result}).")


if __name__ == "__main__":
    main()

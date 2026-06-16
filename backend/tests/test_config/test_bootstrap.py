"""Database bootstrap branch logic (used by entrypoint.sh).

The dangerous shape this guards against: running db.create_all() against an
EXISTING, partially-migrated database. create_all would build new tables in
their final model shape, and the pending migration's create_table then fails
with DuplicateTable, crash-looping the deploy. create_all is only legitimate
on a database that has never been stamped by Alembic.
"""
from app.bootstrap import init_database


def test_fresh_db_runs_create_all_then_stamps_head(app):
    calls = []
    result = init_database(
        app,
        current_revision=lambda: None,
        create_all=lambda: calls.append("create_all"),
        stamp=lambda revision: calls.append(f"stamp:{revision}"),
        upgrade=lambda: calls.append("upgrade"),
    )
    assert calls == ["create_all", "stamp:head"]
    assert result == "stamped"


def test_migrated_db_upgrades_without_create_all(app):
    calls = []
    result = init_database(
        app,
        current_revision=lambda: "b9c0d1e2f3a4",
        create_all=lambda: calls.append("create_all"),
        stamp=lambda revision: calls.append(f"stamp:{revision}"),
        upgrade=lambda: calls.append("upgrade"),
    )
    assert calls == ["upgrade"]
    assert result == "upgraded"

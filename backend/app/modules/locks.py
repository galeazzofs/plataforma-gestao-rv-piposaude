"""Cross-process mutual exclusion via Postgres advisory locks.

The deploy runs gunicorn with multiple workers and no preload, so
create_app starts one APScheduler PER WORKER — every scheduled job fires
N times in parallel. A session-level advisory lock picks one winner per
deploy (and per cluster, since the lock lives in Postgres).

The lock is taken on a DEDICATED connection, not the request/job ORM
session: jobs commit and roll back freely while running, and a pooled
session connection would carry the lock to unrelated checkouts. The
dedicated connection holds the lock for exactly the job's lifetime and
the server releases it if the process dies mid-job.
"""
from contextlib import contextmanager

from flask import current_app
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

# Fixed int64 keys in the pg_advisory_lock keyspace — one per scheduled job.
HUBSPOT_SYNC_LOCK = 0x5049504F53594E43  # "PIPOSYNC"
REMINDERS_LOCK = 0x5049504F524D4452     # "PIPORMDR"


@contextmanager
def try_advisory_lock(key):
    """Yield True and hold the advisory lock for the block, or yield False
    immediately (without blocking) when another session holds it."""
    engine = create_engine(
        current_app.config["SQLALCHEMY_DATABASE_URI"], poolclass=NullPool,
    )
    conn = engine.connect()
    got = False
    try:
        got = bool(conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": key},
        ).scalar())
        yield got
    finally:
        try:
            if got:
                conn.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": key},
                )
        finally:
            conn.close()
            engine.dispose()

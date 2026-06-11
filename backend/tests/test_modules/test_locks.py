"""Cross-process advisory locks for scheduled jobs.

Every gunicorn worker runs its own APScheduler, so every scheduled job
fires once per worker. The Postgres advisory lock must let exactly one
execution through, without blocking the others, and must be released even
when the job blows up (the lock dies with its dedicated connection).
"""
import pytest

from app.modules.locks import (
    try_advisory_lock,
    HUBSPOT_SYNC_LOCK,
    REMINDERS_LOCK,
)


def test_lock_is_exclusive_across_sessions(db_session):
    """Each try_advisory_lock call opens its own connection/session, so a
    nested attempt models a second worker — it must lose without blocking."""
    with try_advisory_lock(HUBSPOT_SYNC_LOCK) as got_first:
        assert got_first is True
        with try_advisory_lock(HUBSPOT_SYNC_LOCK) as got_second:
            assert got_second is False
    # Released after the block: a fresh attempt wins again.
    with try_advisory_lock(HUBSPOT_SYNC_LOCK) as got_again:
        assert got_again is True


def test_distinct_keys_do_not_contend(db_session):
    with try_advisory_lock(HUBSPOT_SYNC_LOCK) as got_sync:
        assert got_sync is True
        with try_advisory_lock(REMINDERS_LOCK) as got_rem:
            assert got_rem is True


def test_lock_released_on_exception(db_session):
    with pytest.raises(RuntimeError):
        with try_advisory_lock(REMINDERS_LOCK) as got:
            assert got is True
            raise RuntimeError("job blew up")
    with try_advisory_lock(REMINDERS_LOCK) as got:
        assert got is True


def test_run_sync_skips_when_lock_held(db_session):
    """A second concurrent sync (another worker's scheduler, or a manual
    trigger racing the cron) must be a clean no-op — it must not fetch from
    HubSpot nor touch the summary settings."""
    from app.modules.hubspot_sync.sync import run_sync

    with try_advisory_lock(HUBSPOT_SYNC_LOCK):
        summary = run_sync()

    assert summary == {"skipped": "already_running"}


def test_reminders_job_skips_when_lock_held(db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.modules.workflow.reminders.check_pending_validations",
        lambda: calls.append(1),
    )
    from app.modules.workflow.reminders_scheduler import run_reminders_job

    with try_advisory_lock(REMINDERS_LOCK):
        assert run_reminders_job() is False
    assert calls == []

    # Lock free again: the job runs for real (and commits).
    assert run_reminders_job() is True
    assert calls == [1]

"""APScheduler wiring for the daily reminder/escalation job (issue #39)."""
import logging

logger = logging.getLogger(__name__)


def run_reminders_job():
    """Advisory-locked job body: check pending validations and commit.

    Every gunicorn worker schedules this at 09:00, so without the lock the
    same appraisal got N concurrent evaluations racing on reminder_sent_at —
    duplicate Slack DMs. The lock covers the COMMIT too: releasing it before
    the commit would let a second worker re-read stale reminder_sent_at.

    Returns True when the job ran, False when another worker held the lock.
    """
    from app.extensions import db
    from app.modules.workflow.reminders import check_pending_validations
    from app.modules.locks import try_advisory_lock, REMINDERS_LOCK

    with try_advisory_lock(REMINDERS_LOCK) as got:
        if not got:
            logger.info("Reminders job skipped: another worker is running it")
            return False
        try:
            check_pending_validations()
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    return True


def init_reminders_scheduler(app):
    """Run check_pending_validations once a day at 09:00 UTC."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("APScheduler not installed; skipping reminders scheduler")
        return None

    scheduler = BackgroundScheduler()

    def job():
        with app.app_context():
            try:
                run_reminders_job()
            except Exception as e:
                logger.error(f"check_pending_validations failed: {e}")

    scheduler.add_job(
        job,
        trigger=CronTrigger(hour=9, minute=0),
        id="appraisal_reminders",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Appraisal reminders scheduler started (daily 09:00 UTC)")
    return scheduler

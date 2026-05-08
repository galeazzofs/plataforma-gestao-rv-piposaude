"""APScheduler wiring for the daily reminder/escalation job (issue #39)."""
import logging

logger = logging.getLogger(__name__)


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
            from app.extensions import db
            from app.modules.workflow.reminders import check_pending_validations
            try:
                check_pending_validations()
                db.session.commit()
            except Exception as e:
                db.session.rollback()
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

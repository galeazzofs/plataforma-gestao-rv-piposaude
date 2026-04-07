import logging
from flask import current_app

logger = logging.getLogger(__name__)


def init_scheduler(app):
    """Initialize APScheduler with HubSpot sync job.

    Requires APScheduler to be installed and configured.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("APScheduler not installed, skipping scheduler init")
        return None

    scheduler = BackgroundScheduler()

    interval_minutes = app.config.get("HUBSPOT_SYNC_INTERVAL_MINUTES", 30)

    def sync_job():
        with app.app_context():
            from app.modules.hubspot_sync.sync import run_sync
            try:
                summary = run_sync()
                logger.info(f"Scheduled HubSpot sync completed: {summary}")
            except Exception as e:
                logger.error(f"Scheduled HubSpot sync failed: {e}")

    scheduler.add_job(
        sync_job,
        trigger=CronTrigger(minute=f"*/{interval_minutes}"),
        id="hubspot_sync",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(f"HubSpot sync scheduler started (every {interval_minutes}min)")
    return scheduler

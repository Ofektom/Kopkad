from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from database.postgres_optimized import get_db
from service.proactive_advisor import (
    check_overspending_alerts,
    check_goal_progress,
    check_spending_anomalies,
    check_savings_opportunities,
    generate_periodic_reports,
    update_financial_health_scores
)
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def init_scheduler():
    """Initialize and configure the scheduler with financial advisor jobs."""
    
    # Daily check for overspending (every day at 9 AM)
    scheduler.add_job(
        run_overspending_check,
        CronTrigger(hour=9, minute=0),
        id="overspending_check",
        name="Check for overspending alerts",
        replace_existing=True
    )
    
    # Daily check for spending anomalies (every day at 10 AM)
    scheduler.add_job(
        run_anomaly_check,
        CronTrigger(hour=10, minute=0),
        id="anomaly_check",
        name="Check for spending anomalies",
        replace_existing=True
    )
    
    # Daily goal progress check (every day at 8 AM)
    scheduler.add_job(
        run_goal_progress_check,
        CronTrigger(hour=8, minute=0),
        id="goal_progress_check",
        name="Check savings goal progress",
        replace_existing=True
    )
    
    # Weekly savings opportunities check (every Monday at 9 AM)
    scheduler.add_job(
        run_savings_opportunities_check,
        CronTrigger(day_of_week='mon', hour=9, minute=0),
        id="savings_opportunities_check",
        name="Check for savings opportunities",
        replace_existing=True
    )
    
    # Weekly financial summary (every Monday at 7 AM)
    scheduler.add_job(
        run_weekly_summary,
        CronTrigger(day_of_week='mon', hour=7, minute=0),
        id="weekly_summary",
        name="Generate weekly financial summaries",
        replace_existing=True
    )
    
    # Monthly financial summary (1st of every month at 7 AM)
    scheduler.add_job(
        run_monthly_summary,
        CronTrigger(day=1, hour=7, minute=0),
        id="monthly_summary",
        name="Generate monthly financial summaries",
        replace_existing=True
    )
    
    # Update financial health scores (every 3 days at 6 AM)
    scheduler.add_job(
        run_health_score_update,
        CronTrigger(day='*/3', hour=6, minute=0),
        id="health_score_update",
        name="Update financial health scores",
        replace_existing=True
    )
    
    logger.info("Scheduler initialized with all financial advisor jobs")


async def run_overspending_check():
    """Wrapper to run overspending check with database session."""
    try:
        logger.info("Running scheduled overspending check")
        db = next(get_db())
        await check_overspending_alerts(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in scheduled overspending check: {str(e)}")


async def run_anomaly_check():
    """Wrapper to run anomaly check with database session."""
    try:
        logger.info("Running scheduled anomaly check")
        db = next(get_db())
        await check_spending_anomalies(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in scheduled anomaly check: {str(e)}")


async def run_goal_progress_check():
    """Wrapper to run goal progress check with database session."""
    try:
        logger.info("Running scheduled goal progress check")
        db = next(get_db())
        await check_goal_progress(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in scheduled goal progress check: {str(e)}")


async def run_savings_opportunities_check():
    """Wrapper to run savings opportunities check with database session."""
    try:
        logger.info("Running scheduled savings opportunities check")
        db = next(get_db())
        await check_savings_opportunities(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in scheduled savings opportunities check: {str(e)}")


async def run_weekly_summary():
    """Wrapper to generate weekly summaries with database session."""
    try:
        logger.info("Running scheduled weekly summary generation")
        db = next(get_db())
        await generate_periodic_reports(db, period="weekly")
        db.close()
    except Exception as e:
        logger.error(f"Error in scheduled weekly summary: {str(e)}")


async def run_monthly_summary():
    """Wrapper to generate monthly summaries with database session."""
    try:
        logger.info("Running scheduled monthly summary generation")
        db = next(get_db())
        await generate_periodic_reports(db, period="monthly")
        db.close()
    except Exception as e:
        logger.error(f"Error in scheduled monthly summary: {str(e)}")


async def run_health_score_update():
    """Wrapper to update health scores with database session."""
    try:
        logger.info("Running scheduled health score update")
        db = next(get_db())
        await update_financial_health_scores(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in scheduled health score update: {str(e)}")


def start_scheduler():
    """Start the scheduler."""
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started successfully")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shutdown successfully")


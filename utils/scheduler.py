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
    update_financial_health_scores,
    check_overdue_savings_payments,
)
from service.cron_notifications import (
    send_business_without_admin_alerts,
    send_daily_system_summary,
    send_inactive_user_reminders,
    send_low_balance_alerts,
    send_payment_request_reminders,
    send_savings_completion_reminders,
    send_savings_nearing_completion_notifications,
    send_savings_payment_overdue_notifications,
    send_weekly_analytics_report,
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

    # Savings nearing completion reminders (daily 6:00 AM)
    scheduler.add_job(
        run_savings_nearing_completion_notifications,
        CronTrigger(hour=6, minute=0),
        id="savings_nearing_completion",
        name="Savings nearing completion reminders",
        replace_existing=True,
    )

    # Savings completion reminders (daily 6:30 AM)
    scheduler.add_job(
        run_savings_completion_reminders,
        CronTrigger(hour=6, minute=30),
        id="savings_completion_reminders",
        name="Savings completion reminders",
        replace_existing=True,
    )

    # Overdue savings payments (every 5 minutes) - using proactive_advisor version with deduplication
    scheduler.add_job(
        run_overdue_savings_payments_check,
        IntervalTrigger(minutes=5),
        id="overdue_savings_payments",
        name="Overdue savings payments",
        replace_existing=True,
    )

    # System summary for super admins (daily 8:00 AM)
    scheduler.add_job(
        run_system_summary,
        CronTrigger(hour=8, minute=0),
        id="system_summary",
        name="Daily system summary",
        replace_existing=True,
    )

    # Payment request reminders (daily 11:00 AM)
    scheduler.add_job(
        run_payment_request_reminders,
        CronTrigger(hour=11, minute=0),
        id="payment_request_reminders",
        name="Payment request reminders",
        replace_existing=True,
    )

    # Business without admin alerts (daily 12:00 PM)
    scheduler.add_job(
        run_business_without_admin_alerts,
        CronTrigger(hour=12, minute=0),
        id="business_without_admin_alerts",
        name="Business without admin alerts",
        replace_existing=True,
    )

    # Low balance alerts (daily 1:00 PM)
    scheduler.add_job(
        run_low_balance_alerts,
        CronTrigger(hour=13, minute=0),
        id="low_balance_alerts",
        name="Low balance alerts",
        replace_existing=True,
    )

    # Inactive user reminders (weekly on Monday at 9 AM)
    scheduler.add_job(
        run_inactive_user_reminders,
        CronTrigger(day_of_week='mon', hour=9, minute=0),
        id="inactive_user_reminders",
        name="Inactive user reminders",
        replace_existing=True,
    )

    # Weekly analytics report (weekly on Monday at 7:45 AM)
    scheduler.add_job(
        run_weekly_analytics_report,
        CronTrigger(day_of_week='mon', hour=7, minute=45),
        id="weekly_analytics_report",
        name="Weekly analytics report",
        replace_existing=True,
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


async def run_savings_nearing_completion_notifications():
    """Wrapper to send savings nearing completion reminders."""
    try:
        logger.info("Running scheduled savings nearing completion reminders")
        db = next(get_db())
        await send_savings_nearing_completion_notifications(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in savings nearing completion reminders: {str(e)}")


async def run_savings_completion_reminders():
    """Wrapper to send savings completion reminders."""
    try:
        logger.info("Running scheduled savings completion reminders")
        db = next(get_db())
        await send_savings_completion_reminders(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in savings completion reminders: {str(e)}")


async def run_overdue_savings_payments():
    """Wrapper to check overdue savings payments (legacy - kept for compatibility)."""
    try:
        logger.info("Running scheduled overdue savings payment check")
        db = next(get_db())
        await send_savings_payment_overdue_notifications(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in overdue savings payment check: {str(e)}")


async def run_overdue_savings_payments_check():
    """Wrapper to check overdue savings payments using proactive_advisor with deduplication."""
    try:
        logger.info("Running scheduled overdue savings payment check (with deduplication)")
        db = next(get_db())
        await check_overdue_savings_payments(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in overdue savings payment check: {str(e)}")


async def run_payment_request_reminders():
    """Wrapper to send payment request reminders."""
    try:
        logger.info("Running scheduled payment request reminders")
        db = next(get_db())
        await send_payment_request_reminders(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in payment request reminders: {str(e)}")


async def run_inactive_user_reminders():
    """Wrapper to send inactive user reminders."""
    try:
        logger.info("Running scheduled inactive user reminders")
        db = next(get_db())
        await send_inactive_user_reminders(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in inactive user reminders: {str(e)}")


async def run_business_without_admin_alerts():
    """Wrapper to alert about businesses without admins."""
    try:
        logger.info("Running scheduled business-without-admin alerts")
        db = next(get_db())
        await send_business_without_admin_alerts(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in business-without-admin alerts: {str(e)}")


async def run_low_balance_alerts():
    """Wrapper to send low balance alerts."""
    try:
        logger.info("Running scheduled low balance alerts")
        db = next(get_db())
        await send_low_balance_alerts(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in low balance alerts: {str(e)}")


async def run_system_summary():
    """Wrapper to send system summary to super admins."""
    try:
        logger.info("Running scheduled system summary")
        db = next(get_db())
        await send_daily_system_summary(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in system summary: {str(e)}")


async def run_weekly_analytics_report():
    """Wrapper to send weekly analytics report."""
    try:
        logger.info("Running scheduled weekly analytics report")
        db = next(get_db())
        await send_weekly_analytics_report(db)
        db.close()
    except Exception as e:
        logger.error(f"Error in weekly analytics report: {str(e)}")


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


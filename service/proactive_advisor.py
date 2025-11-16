from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from models.financial_advisor import (
    GoalStatus,
    NotificationPriority,
    NotificationType,
    PatternType,
)
from models.savings import SavingsAccount, SavingsMarking, MarkingStatus, SavingsStatus
from models.payments import PaymentRequest, PaymentRequestStatus, Commission
from models.expenses import ExpenseCard, CardStatus
from models.user import User
from models.business import Business
from service.financial_advisor import (
    analyze_savings_capacity,
    calculate_financial_health_score,
    detect_spending_patterns,
)
from store.repositories import (
    ExpenseRepository,
    BusinessRepository,
    ExpenseCardRepository,
    FinancialHealthScoreRepository,
    PaymentsRepository,
    SavingsRepository,
    SavingsGoalRepository,
    SpendingPatternRepository,
    UserNotificationRepository,
    UserRepository,
)
from store.enums import Role

logging.basicConfig(
    filename="proactive_advisor.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _resolve_repo(repo, repo_cls, db: Session):
    return repo if repo is not None else repo_cls(db)


async def check_overspending_alerts(
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    expense_repo: ExpenseRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Detect when users are nearing/exceeding category limits."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    expense_repo = _resolve_repo(expense_repo, ExpenseRepository, db)
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = user_repo.db

    try:
        logger.info("Running overspending alerts check")
        customers = user_repo.get_active_customers()

        for customer in customers:
            try:
                month_start = date.today().replace(day=1)
                total_this_month = expense_repo.sum_by_user(
                    user_id=customer.id,
                    from_date=month_start,
                )

                last_month_start = (month_start - timedelta(days=1)).replace(day=1)
                last_month_end = month_start - timedelta(days=1)
                last_month_expenses = expense_repo.sum_by_user(
                    user_id=customer.id,
                    from_date=last_month_start,
                    to_date=last_month_end,
                )

                if last_month_expenses > 0:
                    increase_percentage = (
                        (total_this_month - last_month_expenses)
                        / last_month_expenses
                        * 100
                    )
                    if increase_percentage > 20:
                        existing_alert = notification_repo.find_recent(
                            user_id=customer.id,
                            notification_type=NotificationType.OVERSPENDING,
                            since=datetime.combine(
                                month_start, datetime.min.time()
                            ).replace(tzinfo=timezone.utc),
                        )
                        if not existing_alert:
                            notification_repo.create(
                                {
                                    "user_id": customer.id,
                                    "notification_type": NotificationType.OVERSPENDING,
                                    "title": "Overspending Alert",
                                    "message": (
                                        f"Your spending this month ({total_this_month:.2f}) "
                                        f"is {increase_percentage:.1f}% higher than last month. "
                                        "Consider reviewing your expenses."
                                    ),
                                    "priority": NotificationPriority.HIGH,
                                    "created_by": customer.id,
                                    "created_at": datetime.now(timezone.utc),
                                }
                            )
                            logger.info(
                                "Created overspending alert for user %s", customer.id
                            )
            except Exception as exc:
                logger.error(
                    "Error checking overspending for customer %s: %s",
                    customer.id,
                    exc,
                )

        session.commit()
        logger.info("Completed overspending alerts check")
    except Exception as exc:
        session.rollback()
        logger.error("Error in check_overspending_alerts: %s", exc)


async def check_goal_progress(
    db: Session,
    *,
    savings_goal_repo: SavingsGoalRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Alert on goals falling behind schedule."""
    savings_goal_repo = _resolve_repo(savings_goal_repo, SavingsGoalRepository, db)
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = savings_goal_repo.db

    try:
        logger.info("Running goal progress check")
        active_goals = savings_goal_repo.get_active_with_deadlines()

        for goal in active_goals:
            try:
                days_remaining = (goal.deadline - date.today()).days
                if days_remaining <= 0:
                    continue

                if goal.created_at:
                    total_days = (goal.deadline - goal.created_at.date()).days
                    days_elapsed = total_days - days_remaining
                    expected_progress = (
                        (days_elapsed / total_days) * 100 if total_days > 0 else 0
                    )
                else:
                    expected_progress = 50

                actual_progress = (
                    float(goal.current_amount / goal.target_amount * 100)
                    if goal.target_amount > 0
                    else 0
                )

                if expected_progress - actual_progress > 20:
                    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
                    existing_alert = notification_repo.find_recent(
                        user_id=goal.customer_id,
                        notification_type=NotificationType.GOAL_PROGRESS,
                        since=week_ago,
                        related_entity_id=goal.id,
                    )
                    if not existing_alert:
                        remaining_amount = goal.target_amount - goal.current_amount
                        daily_required = (
                            remaining_amount / days_remaining
                            if days_remaining > 0
                            else remaining_amount
                        )
                        notification_repo.create(
                            {
                                "user_id": goal.customer_id,
                                "notification_type": NotificationType.GOAL_PROGRESS,
                                "title": f"Goal Alert: {goal.name}",
                                "message": (
                                    f"You're behind schedule on your goal '{goal.name}'. "
                                    f"You need to save {daily_required:.2f} per day to reach your target "
                                    f"by {goal.deadline}."
                                ),
                                "priority": NotificationPriority.MEDIUM,
                                "related_entity_id": goal.id,
                                "related_entity_type": "savings_goal",
                                "created_by": goal.customer_id,
                                "created_at": datetime.now(timezone.utc),
                            }
                        )
                        logger.info(
                            "Created goal progress alert for goal %s", goal.id
                        )
                elif 50 <= actual_progress < 55:
                    existing_milestone = (
                        notification_repo.db.query(notification_repo.model)
                        .filter(
                            notification_repo.model.user_id == goal.customer_id,
                            notification_repo.model.related_entity_id == goal.id,
                            notification_repo.model.message.like("%50%"),
                        )
                        .first()
                    )
                    if not existing_milestone:
                        notification_repo.create(
                            {
                                "user_id": goal.customer_id,
                                "notification_type": NotificationType.GOAL_PROGRESS,
                                "title": f"Milestone Reached: {goal.name}",
                                "message": (
                                    "Congratulations! You're halfway to your goal "
                                    f"'{goal.name}'. Keep up the great work!"
                                ),
                                "priority": NotificationPriority.LOW,
                                "related_entity_id": goal.id,
                                "related_entity_type": "savings_goal",
                                "created_by": goal.customer_id,
                                "created_at": datetime.now(timezone.utc),
                            }
                        )
                        logger.info("Created milestone alert for goal %s", goal.id)
            except Exception as exc:
                logger.error(
                    "Error checking progress for goal %s: %s", goal.id, exc
                )

        session.commit()
        logger.info("Completed goal progress check")
    except Exception as exc:
        session.rollback()
        logger.error("Error in check_goal_progress: %s", exc)


async def check_spending_anomalies(
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    expense_repo: ExpenseRepository | None = None,
    spending_pattern_repo: SpendingPatternRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Flag unusual transactions."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    expense_repo = _resolve_repo(expense_repo, ExpenseRepository, db)
    spending_pattern_repo = _resolve_repo(
        spending_pattern_repo, SpendingPatternRepository, db
    )
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = user_repo.db

    try:
        logger.info("Running spending anomalies check")
        customers = user_repo.get_active_customers()

        for customer in customers:
            try:
                await detect_spending_patterns(
                    customer.id,
                    db,
                    expense_repo=expense_repo,
                    spending_pattern_repo=spending_pattern_repo,
                )

                today_start = datetime.combine(
                    datetime.now(timezone.utc).date(), datetime.min.time()
                ).replace(tzinfo=timezone.utc)
                anomaly_patterns = spending_pattern_repo.get_recent_by_type(
                    customer.id,
                    PatternType.ANOMALY,
                    since=today_start,
                )

                for pattern in anomaly_patterns:
                    existing_notif = notification_repo.find_recent(
                        user_id=customer.id,
                        notification_type=NotificationType.SPENDING_ANOMALY,
                        since=today_start,
                        related_entity_id=pattern.id,
                    )
                    if not existing_notif:
                        metadata = pattern.pattern_metadata or {}
                        severity = metadata.get("severity", "medium")
                        priority_map = {
                            "high": NotificationPriority.HIGH,
                            "medium": NotificationPriority.MEDIUM,
                            "low": NotificationPriority.LOW,
                        }
                        notification_repo.create(
                            {
                                "user_id": customer.id,
                                "notification_type": NotificationType.SPENDING_ANOMALY,
                                "title": "Unusual Spending Detected",
                                "message": (
                                    f"{pattern.description}. Amount: {pattern.amount:.2f}. "
                                    "This is significantly different from your usual spending pattern."
                                ),
                                "priority": priority_map.get(
                                    severity, NotificationPriority.MEDIUM
                                ),
                                "related_entity_id": pattern.id,
                                "related_entity_type": "spending_pattern",
                                "created_by": customer.id,
                                "created_at": datetime.now(timezone.utc),
                            }
                        )
                        logger.info(
                            "Created anomaly alert for user %s", customer.id
                        )
            except Exception as exc:
                logger.error(
                    "Error checking anomalies for customer %s: %s", customer.id, exc
                )

        session.commit()
        logger.info("Completed spending anomalies check")
    except Exception as exc:
        session.rollback()
        logger.error("Error in check_spending_anomalies: %s", exc)


async def check_savings_opportunities(
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    expense_repo: ExpenseRepository | None = None,
    savings_goal_repo: SavingsGoalRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Identify good times to increase savings."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    expense_repo = _resolve_repo(expense_repo, ExpenseRepository, db)
    savings_goal_repo = _resolve_repo(savings_goal_repo, SavingsGoalRepository, db)
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = user_repo.db

    try:
        logger.info("Running savings opportunities check")
        customers = user_repo.get_active_customers()

        for customer in customers:
            try:
                capacity = await analyze_savings_capacity(
                    customer.id,
                    db,
                    expense_repo=expense_repo,
                    savings_repo=savings_goal_repo,
                )

                if capacity and capacity.get("capacity_level") in {"moderate", "high"}:
                    current_savings_rate = capacity.get("savings_rate", 0)
                    if current_savings_rate < 15:
                        two_weeks_ago = datetime.now(timezone.utc) - timedelta(days=14)
                        existing_alert = notification_repo.find_recent(
                            user_id=customer.id,
                            notification_type=NotificationType.SAVINGS_OPPORTUNITY,
                            since=two_weeks_ago,
                        )
                        if not existing_alert:
                            potential_increase = (
                                capacity["recommended_optimal_savings"]
                                - capacity["current_savings"]
                            )
                            notification_repo.create(
                                {
                                    "user_id": customer.id,
                                    "notification_type": NotificationType.SAVINGS_OPPORTUNITY,
                                    "title": "Savings Opportunity",
                                    "message": (
                                        f"You have capacity to save an additional {potential_increase:.2f} per month. "
                                        f"Your current savings rate is {current_savings_rate:.1f}%, aim for 15-20%."
                                    ),
                                    "priority": NotificationPriority.MEDIUM,
                                    "created_by": customer.id,
                                    "created_at": datetime.now(timezone.utc),
                                }
                            )
                            logger.info(
                                "Created savings opportunity alert for user %s",
                                customer.id,
                            )
            except Exception as exc:
                logger.error(
                    "Error checking savings opportunities for customer %s: %s",
                    customer.id,
                    exc,
                )

        session.commit()
        logger.info("Completed savings opportunities check")
    except Exception as exc:
        session.rollback()
        logger.error("Error in check_savings_opportunities: %s", exc)


async def generate_periodic_reports(
    db: Session,
    period: str = "weekly",
    *,
    user_repo: UserRepository | None = None,
    expense_repo: ExpenseRepository | None = None,
    financial_health_repo: FinancialHealthScoreRepository | None = None,
    savings_goal_repo: SavingsGoalRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Generate weekly/monthly financial summaries."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    expense_repo = _resolve_repo(expense_repo, ExpenseRepository, db)
    financial_health_repo = _resolve_repo(
        financial_health_repo, FinancialHealthScoreRepository, db
    )
    savings_goal_repo = _resolve_repo(savings_goal_repo, SavingsGoalRepository, db)
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = user_repo.db

    try:
        logger.info("Running %s periodic reports generation", period)
        customers = user_repo.get_active_customers()

        for customer in customers:
            try:
                if period == "weekly":
                    period_start = date.today() - timedelta(days=7)
                    title = "Weekly Financial Summary"
                    score_days = 7
                else:
                    period_start = date.today().replace(day=1)
                    title = "Monthly Financial Summary"
                    score_days = 30

                period_since = datetime.combine(
                    period_start, datetime.min.time()
                ).replace(tzinfo=timezone.utc)
                existing_report = notification_repo.find_recent(
                    user_id=customer.id,
                    notification_type=NotificationType.MONTHLY_SUMMARY,
                    since=period_since,
                )

                if existing_report:
                    continue

                total_expenses = expense_repo.sum_by_user(
                    user_id=customer.id,
                    from_date=period_start,
                )
                expense_count = expense_repo.count_by_user(
                    user_id=customer.id,
                    from_date=period_start,
                )
                latest_score = financial_health_repo.get_recent_score(
                    customer.id, days=score_days
                )
                score_text = (
                    f"Your financial health score is {latest_score.score}/100."
                    if latest_score
                    else "Track your finances to get a health score."
                )
                active_goals = savings_goal_repo.count_active_for_customer(customer.id)

                message_lines = [
                    f"{title}:",
                    f"- Total expenses: {total_expenses:.2f} ({expense_count} transactions)",
                    f"- {score_text}",
                    f"- Active savings goals: {active_goals}",
                    "",
                    "Keep tracking your expenses and working towards your goals!",
                ]
                notification_repo.create(
                    {
                        "user_id": customer.id,
                        "notification_type": NotificationType.MONTHLY_SUMMARY,
                        "title": title,
                        "message": "\n".join(message_lines),
                        "priority": NotificationPriority.LOW,
                        "created_by": customer.id,
                        "created_at": datetime.now(timezone.utc),
                    }
                )
                logger.info("Created %s summary for user %s", period, customer.id)
            except Exception as exc:
                logger.error(
                    "Error generating report for customer %s: %s", customer.id, exc
                )

        session.commit()
        logger.info("Completed %s periodic reports generation", period)
    except Exception as exc:
        session.rollback()
        logger.error("Error in generate_periodic_reports: %s", exc)


async def update_financial_health_scores(
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    financial_health_repo: FinancialHealthScoreRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Update financial health scores for all customers."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    financial_health_repo = _resolve_repo(
        financial_health_repo, FinancialHealthScoreRepository, db
    )
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = user_repo.db

    try:
        logger.info("Running financial health scores update")
        customers = user_repo.get_active_customers()

        for customer in customers:
            try:
                week_ago = datetime.now(timezone.utc) - timedelta(days=7)
                recent_score = financial_health_repo.get_recent_since(
                    customer.id, since=week_ago
                )
                if recent_score:
                    continue

                new_score = await calculate_financial_health_score(
                    customer.id,
                    db,
                    financial_health_repo=financial_health_repo,
                    savings_goal_repo=None,
                    expense_repo=None,
                    expense_card_repo=None,
                    savings_repo=None,
                )
                logger.info(
                    "Updated health score for user %s: %s",
                    customer.id,
                    new_score.score,
                )

                previous_score = financial_health_repo.get_previous_score(customer.id)
                if (
                    previous_score
                    and abs(new_score.score - previous_score.score) >= 10
                ):
                    direction = (
                        "improved"
                        if new_score.score > previous_score.score
                        else "declined"
                    )
                    change = abs(new_score.score - previous_score.score)
                    notification_repo.create(
                        {
                            "user_id": customer.id,
                            "notification_type": NotificationType.HEALTH_SCORE,
                            "title": "Financial Health Score Update",
                            "message": (
                                f"Your financial health score has {direction} by {change} points "
                                f"to {new_score.score}/100. Keep tracking your progress!"
                            ),
                            "priority": NotificationPriority.MEDIUM,
                            "related_entity_id": new_score.id,
                            "related_entity_type": "health_score",
                            "created_by": customer.id,
                            "created_at": datetime.now(timezone.utc),
                        }
                    )
                    logger.info(
                        "Created health score notification for user %s", customer.id
                    )
            except Exception as exc:
                logger.error(
                    "Error updating health score for customer %s: %s",
                    customer.id,
                    exc,
                )

        session.commit()
        logger.info("Completed financial health scores update")
    except Exception as exc:
        session.rollback()
        logger.error("Error in update_financial_health_scores: %s", exc)


async def check_savings_completion_reminders(
    db: Session,
    *,
    savings_repo: SavingsRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Send reminders for savings accounts approaching completion."""
    savings_repo = _resolve_repo(savings_repo, SavingsRepository, db)
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = savings_repo.db

    try:
        logger.info("Running savings completion reminders check")
        today = date.today()
        reminder_windows = [
            (7, NotificationType.SAVINGS_NEARING_COMPLETION, NotificationPriority.MEDIUM),
            (3, NotificationType.SAVINGS_COMPLETION_REMINDER, NotificationPriority.MEDIUM),
        ]

        for days_out, notif_type, priority in reminder_windows:
            target_date = today + timedelta(days=days_out)
            accounts = (
                session.query(SavingsAccount)
                .filter(
                    SavingsAccount.end_date.isnot(None),
                    SavingsAccount.end_date == target_date,
                    SavingsAccount.marking_status != MarkingStatus.COMPLETED,
                )
                .all()
            )

            for account in accounts:
                since = datetime.now(timezone.utc) - timedelta(days=1)
                existing = notification_repo.find_recent(
                    user_id=account.customer_id,
                    notification_type=notif_type,
                    since=since,
                    related_entity_id=account.id,
                )
                if existing:
                    continue

                days_text = "in 7 days" if days_out == 7 else "in 3 days"
                notification_repo.create(
                    {
                        "user_id": account.customer_id,
                        "notification_type": notif_type,
                        "title": "Savings Account Reminder",
                        "message": (
                            f"Your savings account {account.tracking_number} will complete {days_text}. "
                            "Please ensure all payments are up to date."
                        ),
                        "priority": priority,
                        "related_entity_id": account.id,
                        "related_entity_type": "savings_account",
                        "created_by": account.customer_id,
                        "created_at": datetime.now(timezone.utc),
                    }
                )

        session.commit()
        logger.info("Completed savings completion reminders check")
    except Exception as exc:
        session.rollback()
        logger.error("Error in check_savings_completion_reminders: %s", exc)


async def check_overdue_savings_payments(
    db: Session,
    *,
    savings_repo: SavingsRepository | None = None,
    business_repo: BusinessRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Notify customers and agents about overdue savings markings."""
    savings_repo = _resolve_repo(savings_repo, SavingsRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = savings_repo.db

    try:
        logger.info("Running overdue savings payments check")
        overdue_cutoff = date.today() - timedelta(days=1)
        rows = (
            session.query(
                SavingsAccount.id.label("account_id"),
                SavingsAccount.tracking_number,
                SavingsAccount.customer_id,
                SavingsAccount.business_id,
                func.min(SavingsMarking.marked_date).label("oldest_mark"),
            )
            .join(SavingsMarking, SavingsMarking.savings_account_id == SavingsAccount.id)
            .filter(
                SavingsMarking.status == SavingsStatus.PENDING.value,
                SavingsMarking.marked_date < overdue_cutoff,
            )
            .group_by(
                SavingsAccount.id,
                SavingsAccount.tracking_number,
                SavingsAccount.customer_id,
                SavingsAccount.business_id,
            )
            .all()
        )

        for row in rows:
            # Check if notification exists after the payment became overdue
            # This ensures we create notifications for existing overdue payments
            # Convert date to datetime at start of day in UTC
            if isinstance(row.oldest_mark, date):
                overdue_date = datetime.combine(row.oldest_mark, datetime.min.time()).replace(tzinfo=timezone.utc)
            else:
                # If it's already a datetime, ensure it has timezone
                overdue_date = row.oldest_mark if row.oldest_mark.tzinfo else row.oldest_mark.replace(tzinfo=timezone.utc)
            since = overdue_date
            existing = notification_repo.find_recent(
                user_id=row.customer_id,
                notification_type=NotificationType.SAVINGS_PAYMENT_OVERDUE,
                since=since,
                related_entity_id=row.account_id,
            )
            if not existing:
                notification_repo.create(
                    {
                        "user_id": row.customer_id,
                        "notification_type": NotificationType.SAVINGS_PAYMENT_OVERDUE,
                        "title": "Savings Payment Overdue",
                        "message": (
                            f"You have overdue payments for savings account {row.tracking_number}. "
                            "Please mark the pending payments to stay on track."
                        ),
                        "priority": NotificationPriority.HIGH,
                        "related_entity_id": row.account_id,
                        "related_entity_type": "savings_account",
                        "created_by": row.customer_id,
                        "created_at": datetime.now(timezone.utc),
                    }
                )

            if row.business_id:
                business = business_repo.get_by_id(row.business_id)
                if business and business.agent_id:
                    # Use the same overdue_date for agent notifications
                    existing_agent = notification_repo.find_recent(
                        user_id=business.agent_id,
                        notification_type=NotificationType.SAVINGS_PAYMENT_OVERDUE,
                        since=overdue_date,
                        related_entity_id=row.account_id,
                    )
                    if not existing_agent:
                        notification_repo.create(
                            {
                                "user_id": business.agent_id,
                                "notification_type": NotificationType.SAVINGS_PAYMENT_OVERDUE,
                                "title": "Customer Savings Payment Overdue",
                                "message": (
                                    f"Savings account {row.tracking_number} has overdue payments. "
                                    "Kindly follow up with the customer."
                                ),
                                "priority": NotificationPriority.HIGH,
                                "related_entity_id": row.account_id,
                                "related_entity_type": "savings_account",
                                "created_by": business.agent_id,
                                "created_at": datetime.now(timezone.utc),
                            }
                        )

        session.commit()
        logger.info("Completed overdue savings payments check")
    except Exception as exc:
        session.rollback()
        logger.error("Error in check_overdue_savings_payments: %s", exc)


async def send_payment_request_reminders(
    db: Session,
    *,
    payments_repo: PaymentsRepository | None = None,
    business_repo: BusinessRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Remind business admins about pending payment requests older than 24 hours."""
    payments_repo = _resolve_repo(payments_repo, PaymentsRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = payments_repo.db

    try:
        logger.info("Running payment request reminder job")
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        pending_requests = (
            session.query(PaymentRequest)
            .options(joinedload(PaymentRequest.savings_account))
            .filter(
                PaymentRequest.status == PaymentRequestStatus.PENDING.value,
                PaymentRequest.request_date <= cutoff,
            )
            .all()
        )

        for request in pending_requests:
            savings_account = request.savings_account
            if not savings_account or not savings_account.business_id:
                continue

            business = business_repo.get_by_id(savings_account.business_id)
            admin_id = business.admin_id if business else None
            if not admin_id:
                continue

            since = datetime.now(timezone.utc) - timedelta(hours=12)
            existing = notification_repo.find_recent(
                user_id=admin_id,
                notification_type=NotificationType.PAYMENT_REQUEST_REMINDER,
                since=since,
                related_entity_id=request.id,
            )
            if existing:
                continue

            notification_repo.create(
                {
                    "user_id": admin_id,
                    "notification_type": NotificationType.PAYMENT_REQUEST_REMINDER,
                    "title": "Pending Payment Request",
                    "message": (
                        f"A payment request of {request.amount:.2f} for savings account "
                        f"{savings_account.tracking_number} has been pending for over 24 hours."
                    ),
                    "priority": NotificationPriority.MEDIUM,
                    "related_entity_id": request.id,
                    "related_entity_type": "payment_request",
                    "created_by": admin_id,
                    "created_at": datetime.now(timezone.utc),
                }
            )

        session.commit()
        logger.info("Completed payment request reminder job")
    except Exception as exc:
        session.rollback()
        logger.error("Error in send_payment_request_reminders: %s", exc)


async def send_inactive_user_reminders(
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Remind customers who have been inactive for 30 days."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = user_repo.db

    try:
        logger.info("Running inactive user reminder job")
        threshold = datetime.now(timezone.utc) - timedelta(days=30)
        users = (
            session.query(User)
            .filter(
                User.role == Role.CUSTOMER,
                User.is_active.is_(True),
                or_(
                    User.updated_at.is_(None),
                    User.updated_at < threshold,
                ),
            )
            .all()
        )

        for user in users:
            since = datetime.now(timezone.utc) - timedelta(days=25)
            existing = notification_repo.find_recent(
                user_id=user.id,
                notification_type=NotificationType.INACTIVE_USER_REMINDER,
                since=since,
            )
            if existing:
                continue

            notification_repo.create(
                {
                    "user_id": user.id,
                    "notification_type": NotificationType.INACTIVE_USER_REMINDER,
                    "title": "We Miss You at Kopkad",
                    "message": (
                        "We haven't seen you in a while. Come back, review your finances, "
                        "and continue your savings journey!"
                    ),
                    "priority": NotificationPriority.LOW,
                    "created_by": user.id,
                    "created_at": datetime.now(timezone.utc),
                }
            )

        session.commit()
        logger.info("Completed inactive user reminder job")
    except Exception as exc:
        session.rollback()
        logger.error("Error in send_inactive_user_reminders: %s", exc)


async def check_business_without_admin(
    db: Session,
    *,
    business_repo: BusinessRepository | None = None,
    user_repo: UserRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Alert super admins and agents when a business lacks an assigned admin."""
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = business_repo.db

    try:
        logger.info("Running business-without-admin check")
        threshold = datetime.now(timezone.utc) - timedelta(days=7)
        businesses = business_repo.get_unassigned_businesses()
        super_admins = user_repo.get_by_role(Role.SUPER_ADMIN)

        for business in businesses:
            if not business.created_at or business.created_at > threshold:
                continue

            since = datetime.now(timezone.utc) - timedelta(days=2)
            for admin in super_admins:
                existing = notification_repo.find_recent(
                    user_id=admin.id,
                    notification_type=NotificationType.BUSINESS_WITHOUT_ADMIN,
                    since=since,
                    related_entity_id=business.id,
                )
                if not existing:
                    notification_repo.create(
                        {
                            "user_id": admin.id,
                            "notification_type": NotificationType.BUSINESS_WITHOUT_ADMIN,
                            "title": "Business Without Admin",
                            "message": (
                                f"Business '{business.name}' ({business.unique_code}) still has no assigned admin."
                            ),
                            "priority": NotificationPriority.HIGH,
                            "related_entity_id": business.id,
                            "related_entity_type": "business",
                            "created_by": admin.id,
                            "created_at": datetime.now(timezone.utc),
                        }
                    )

            if business.agent_id:
                existing_agent = notification_repo.find_recent(
                    user_id=business.agent_id,
                    notification_type=NotificationType.BUSINESS_WITHOUT_ADMIN,
                    since=since,
                    related_entity_id=business.id,
                )
                if not existing_agent:
                    notification_repo.create(
                        {
                            "user_id": business.agent_id,
                            "notification_type": NotificationType.BUSINESS_WITHOUT_ADMIN,
                            "title": "Assign a Business Admin",
                            "message": (
                                f"Business '{business.name}' has been without an admin for over 7 days. "
                                "Please complete the assignment."
                            ),
                            "priority": NotificationPriority.HIGH,
                            "related_entity_id": business.id,
                            "related_entity_type": "business",
                            "created_by": business.agent_id,
                            "created_at": datetime.now(timezone.utc),
                        }
                    )

        session.commit()
        logger.info("Completed business-without-admin check")
    except Exception as exc:
        session.rollback()
        logger.error("Error in check_business_without_admin: %s", exc)


async def check_low_balance_alerts(
    db: Session,
    *,
    expense_card_repo: ExpenseCardRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Notify users when their expense card balances fall below 20%."""
    expense_card_repo = _resolve_repo(expense_card_repo, ExpenseCardRepository, db)
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = expense_card_repo.db

    try:
        logger.info("Running low balance alert check")
        cards = (
            session.query(ExpenseCard)
            .filter(
                ExpenseCard.status == CardStatus.ACTIVE,
                ExpenseCard.is_plan.is_(False),
                ExpenseCard.income_amount > 0,
            )
            .all()
        )

        for card in cards:
            ratio = Decimal(card.balance or 0) / Decimal(card.income_amount or 1)
            if ratio > Decimal("0.20"):
                continue

            since = datetime.now(timezone.utc) - timedelta(days=1)
            existing = notification_repo.find_recent(
                user_id=card.customer_id,
                notification_type=NotificationType.LOW_BALANCE_ALERT,
                since=since,
                related_entity_id=card.id,
            )
            if existing:
                continue

            notification_repo.create(
                {
                    "user_id": card.customer_id,
                    "notification_type": NotificationType.LOW_BALANCE_ALERT,
                    "title": "Low Balance Alert",
                    "message": (
                        f"Your expense card '{card.name}' balance is low ({card.balance:.2f}). "
                        "Consider topping up to keep your planned expenses on track."
                    ),
                    "priority": NotificationPriority.HIGH,
                    "related_entity_id": card.id,
                    "related_entity_type": "expense_card",
                    "created_by": card.customer_id,
                    "created_at": datetime.now(timezone.utc),
                }
            )

        session.commit()
        logger.info("Completed low balance alert check")
    except Exception as exc:
        session.rollback()
        logger.error("Error in check_low_balance_alerts: %s", exc)


async def send_system_summary(
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    business_repo: BusinessRepository | None = None,
    savings_repo: SavingsRepository | None = None,
    payments_repo: PaymentsRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Send a daily system summary to super admins."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    savings_repo = _resolve_repo(savings_repo, SavingsRepository, db)
    payments_repo = _resolve_repo(payments_repo, PaymentsRepository, db)
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = user_repo.db

    try:
        logger.info("Running system summary job")
        total_users = user_repo.count_all_users()
        active_users = user_repo.count_active_users()
        business_count = business_repo.db.query(func.count(Business.id)).scalar() or 0
        savings_metrics = savings_repo.get_system_savings_metrics()
        payment_summary = payments_repo.get_status_summary()

        status_breakdown = ", ".join(
            f"{item['status']}: {item['count']}" for item in payment_summary
        )
        message_lines = [
            "Daily System Summary:",
            f"- Total users: {total_users} ({active_users} active)",
            f"- Total businesses: {business_count}",
            f"- Savings accounts: {savings_metrics['total_accounts']}",
            f"- Savings volume (paid): {savings_metrics['volume_by_status'].get('paid', 0):.2f}",
            f"- Pending payment requests: {status_breakdown or 'None'}",
        ]

        since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        super_admins = user_repo.get_by_role(Role.SUPER_ADMIN)

        for admin in super_admins:
            existing = notification_repo.find_recent(
                user_id=admin.id,
                notification_type=NotificationType.SYSTEM_SUMMARY,
                since=since,
            )
            if existing:
                continue

            notification_repo.create(
                {
                    "user_id": admin.id,
                    "notification_type": NotificationType.SYSTEM_SUMMARY,
                    "title": "Daily System Summary",
                    "message": "\n".join(message_lines),
                    "priority": NotificationPriority.LOW,
                    "created_by": admin.id,
                    "created_at": datetime.now(timezone.utc),
                }
            )

        session.commit()
        logger.info("Completed system summary job")
    except Exception as exc:
        session.rollback()
        logger.error("Error in send_system_summary: %s", exc)


async def send_weekly_analytics_report(
    db: Session,
    *,
    business_repo: BusinessRepository | None = None,
    user_repo: UserRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Send weekly analytics highlights to super admins."""
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    notification_repo = _resolve_repo(notification_repo, UserNotificationRepository, db)
    session = business_repo.db

    try:
        logger.info("Running weekly analytics report job")
        metrics = business_repo.get_business_performance_metrics()
        top_businesses = sorted(
            metrics, key=lambda item: item["total_volume"], reverse=True
        )[:3]

        lines = ["Weekly Analytics Report:"]
        for idx, business in enumerate(top_businesses, start=1):
            lines.append(
                f"{idx}. {business['name']} - Volume: {business['total_volume']:.2f}, "
                f"Paid: {business['paid_volume']:.2f}, Pending: {business['pending_volume']:.2f}"
            )
        if len(lines) == 1:
            lines.append("No business activity recorded this week.")

        since = datetime.now(timezone.utc) - timedelta(days=6)
        super_admins = user_repo.get_by_role(Role.SUPER_ADMIN)

        for admin in super_admins:
            existing = notification_repo.find_recent(
                user_id=admin.id,
                notification_type=NotificationType.WEEKLY_ANALYTICS,
                since=since,
            )
            if existing:
                continue

            notification_repo.create(
                {
                    "user_id": admin.id,
                    "notification_type": NotificationType.WEEKLY_ANALYTICS,
                    "title": "Weekly Analytics Report",
                    "message": "\n".join(lines),
                    "priority": NotificationPriority.LOW,
                    "created_by": admin.id,
                    "created_at": datetime.now(timezone.utc),
                }
            )

        session.commit()
        logger.info("Completed weekly analytics report job")
    except Exception as exc:
        session.rollback()
        logger.error("Error in send_weekly_analytics_report: %s", exc)


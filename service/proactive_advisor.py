from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging

from sqlalchemy.orm import Session

from models.financial_advisor import (
    GoalStatus,
    NotificationPriority,
    NotificationType,
    PatternType,
)
from service.financial_advisor import (
    analyze_savings_capacity,
    calculate_financial_health_score,
    detect_spending_patterns,
)
from store.repositories import (
    ExpenseRepository,
    FinancialHealthScoreRepository,
    SavingsGoalRepository,
    SpendingPatternRepository,
    UserNotificationRepository,
    UserRepository,
)

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


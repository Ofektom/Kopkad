from sqlalchemy.orm import Session
from sqlalchemy import func
from models.financial_advisor import (
    SavingsGoal, FinancialHealthScore, SpendingPattern, UserNotification,
    GoalStatus, PatternType, NotificationType, NotificationPriority
)
from models.expenses import ExpenseCard, Expense
from models.user import User
from service.financial_advisor import (
    calculate_financial_health_score,
    detect_spending_patterns,
    analyze_savings_capacity
)
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
import logging

logging.basicConfig(
    filename="proactive_advisor.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def check_overspending_alerts(db: Session):
    """Detect when users are nearing/exceeding category limits."""
    try:
        logger.info("Running overspending alerts check")
        
        # Get all active customers
        customers = db.query(User).filter(User.role == "customer", User.is_active == True).all()
        
        for customer in customers:
            try:
                # Get this month's expenses
                month_start = date.today().replace(day=1)
                expenses_query = db.query(Expense).join(ExpenseCard).filter(
                    ExpenseCard.customer_id == customer.id,
                    Expense.date >= month_start
                )
                
                total_this_month = expenses_query.with_entities(func.sum(Expense.amount)).scalar() or Decimal(0)
                
                # Get last month's expenses for comparison
                last_month_start = (month_start - timedelta(days=1)).replace(day=1)
                last_month_end = month_start - timedelta(days=1)
                
                last_month_expenses = db.query(Expense).join(ExpenseCard).filter(
                    ExpenseCard.customer_id == customer.id,
                    Expense.date >= last_month_start,
                    Expense.date <= last_month_end
                ).with_entities(func.sum(Expense.amount)).scalar() or Decimal(0)
                
                # Alert if spending is 20% higher than last month
                if last_month_expenses > 0:
                    increase_percentage = (total_this_month - last_month_expenses) / last_month_expenses * 100
                    
                    if increase_percentage > 20:
                        # Check if alert already sent this month
                        existing_alert = db.query(UserNotification).filter(
                            UserNotification.user_id == customer.id,
                            UserNotification.notification_type == NotificationType.OVERSPENDING,
                            UserNotification.created_at >= month_start
                        ).first()
                        
                        if not existing_alert:
                            notification = UserNotification(
                                user_id=customer.id,
                                notification_type=NotificationType.OVERSPENDING,
                                title="Overspending Alert",
                                message=f"Your spending this month ({total_this_month:.2f}) is {increase_percentage:.1f}% higher than last month. Consider reviewing your expenses.",
                                priority=NotificationPriority.HIGH,
                                created_by=customer.id,
                                created_at=datetime.now(timezone.utc)
                            )
                            db.add(notification)
                            logger.info(f"Created overspending alert for user {customer.id}")
            
            except Exception as e:
                logger.error(f"Error checking overspending for customer {customer.id}: {str(e)}")
                continue
        
        db.commit()
        logger.info("Completed overspending alerts check")
    
    except Exception as e:
        logger.error(f"Error in check_overspending_alerts: {str(e)}")
        db.rollback()


async def check_goal_progress(db: Session):
    """Alert on goals falling behind schedule."""
    try:
        logger.info("Running goal progress check")
        
        # Get all active goals
        active_goals = db.query(SavingsGoal).filter(
            SavingsGoal.status == GoalStatus.ACTIVE,
            SavingsGoal.deadline.isnot(None)
        ).all()
        
        for goal in active_goals:
            try:
                days_remaining = (goal.deadline - date.today()).days
                
                if days_remaining > 0:
                    # Calculate expected progress
                    if goal.created_at:
                        total_days = (goal.deadline - goal.created_at.date()).days
                        days_elapsed = total_days - days_remaining
                        expected_progress = (days_elapsed / total_days) * 100 if total_days > 0 else 0
                    else:
                        expected_progress = 50  # Default if no creation date
                    
                    # Calculate actual progress
                    actual_progress = float(goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0
                    
                    # Alert if more than 20% behind schedule
                    if expected_progress - actual_progress > 20:
                        # Check if alert sent in last 7 days
                        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
                        existing_alert = db.query(UserNotification).filter(
                            UserNotification.user_id == goal.customer_id,
                            UserNotification.notification_type == NotificationType.GOAL_PROGRESS,
                            UserNotification.related_entity_id == goal.id,
                            UserNotification.created_at >= week_ago
                        ).first()
                        
                        if not existing_alert:
                            remaining_amount = goal.target_amount - goal.current_amount
                            daily_required = remaining_amount / days_remaining if days_remaining > 0 else remaining_amount
                            
                            notification = UserNotification(
                                user_id=goal.customer_id,
                                notification_type=NotificationType.GOAL_PROGRESS,
                                title=f"Goal Alert: {goal.name}",
                                message=f"You're behind schedule on your goal '{goal.name}'. You need to save {daily_required:.2f} per day to reach your target by {goal.deadline}.",
                                priority=NotificationPriority.MEDIUM,
                                related_entity_id=goal.id,
                                related_entity_type="savings_goal",
                                created_by=goal.customer_id,
                                created_at=datetime.now(timezone.utc)
                            )
                            db.add(notification)
                            logger.info(f"Created goal progress alert for goal {goal.id}")
                    
                    # Celebrate milestones
                    elif actual_progress >= 50 and actual_progress < 55:
                        # Check if milestone alert already sent
                        existing_milestone = db.query(UserNotification).filter(
                            UserNotification.user_id == goal.customer_id,
                            UserNotification.related_entity_id == goal.id,
                            UserNotification.message.like("%50%milestone%")
                        ).first()
                        
                        if not existing_milestone:
                            notification = UserNotification(
                                user_id=goal.customer_id,
                                notification_type=NotificationType.GOAL_PROGRESS,
                                title=f"Milestone Reached: {goal.name}",
                                message=f"Congratulations! You're halfway to your goal '{goal.name}'. Keep up the great work!",
                                priority=NotificationPriority.LOW,
                                related_entity_id=goal.id,
                                related_entity_type="savings_goal",
                                created_by=goal.customer_id,
                                created_at=datetime.now(timezone.utc)
                            )
                            db.add(notification)
                            logger.info(f"Created milestone alert for goal {goal.id}")
            
            except Exception as e:
                logger.error(f"Error checking progress for goal {goal.id}: {str(e)}")
                continue
        
        db.commit()
        logger.info("Completed goal progress check")
    
    except Exception as e:
        logger.error(f"Error in check_goal_progress: {str(e)}")
        db.rollback()


async def check_spending_anomalies(db: Session):
    """Flag unusual transactions."""
    try:
        logger.info("Running spending anomalies check")
        
        # Get all active customers
        customers = db.query(User).filter(User.role == "customer", User.is_active == True).all()
        
        for customer in customers:
            try:
                # Detect patterns (which includes anomalies)
                patterns = await detect_spending_patterns(customer.id, db)
                
                # Find anomaly patterns that were just detected
                today = datetime.now(timezone.utc).date()
                anomaly_patterns = db.query(SpendingPattern).filter(
                    SpendingPattern.customer_id == customer.id,
                    SpendingPattern.pattern_type == PatternType.ANOMALY,
                    SpendingPattern.detected_at >= datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
                ).all()
                
                for pattern in anomaly_patterns:
                    # Check if notification already exists for this pattern
                    existing_notif = db.query(UserNotification).filter(
                        UserNotification.user_id == customer.id,
                        UserNotification.notification_type == NotificationType.SPENDING_ANOMALY,
                        UserNotification.related_entity_id == pattern.id
                    ).first()
                    
                    if not existing_notif:
                        severity = pattern.metadata.get('severity', 'medium') if pattern.metadata else 'medium'
                        priority_map = {'high': NotificationPriority.HIGH, 'medium': NotificationPriority.MEDIUM, 'low': NotificationPriority.LOW}
                        
                        notification = UserNotification(
                            user_id=customer.id,
                            notification_type=NotificationType.SPENDING_ANOMALY,
                            title="Unusual Spending Detected",
                            message=f"{pattern.description}. Amount: {pattern.amount:.2f}. This is significantly different from your usual spending pattern.",
                            priority=priority_map.get(severity, NotificationPriority.MEDIUM),
                            related_entity_id=pattern.id,
                            related_entity_type="spending_pattern",
                            created_by=customer.id,
                            created_at=datetime.now(timezone.utc)
                        )
                        db.add(notification)
                        logger.info(f"Created anomaly alert for user {customer.id}")
            
            except Exception as e:
                logger.error(f"Error checking anomalies for customer {customer.id}: {str(e)}")
                continue
        
        db.commit()
        logger.info("Completed spending anomalies check")
    
    except Exception as e:
        logger.error(f"Error in check_spending_anomalies: {str(e)}")
        db.rollback()


async def check_savings_opportunities(db: Session):
    """Identify good times to increase savings."""
    try:
        logger.info("Running savings opportunities check")
        
        # Get all active customers
        customers = db.query(User).filter(User.role == "customer", User.is_active == True).all()
        
        for customer in customers:
            try:
                # Analyze savings capacity
                capacity = await analyze_savings_capacity(customer.id, db)
                
                if capacity and capacity.get('capacity_level') in ['moderate', 'high']:
                    # Check if below optimal savings
                    current_savings_rate = capacity.get('savings_rate', 0)
                    
                    if current_savings_rate < 15:  # Below optimal 15-20% range
                        # Check if opportunity alert sent in last 14 days
                        two_weeks_ago = datetime.now(timezone.utc) - timedelta(days=14)
                        existing_alert = db.query(UserNotification).filter(
                            UserNotification.user_id == customer.id,
                            UserNotification.notification_type == NotificationType.SAVINGS_OPPORTUNITY,
                            UserNotification.created_at >= two_weeks_ago
                        ).first()
                        
                        if not existing_alert:
                            potential_increase = capacity['recommended_optimal_savings'] - capacity['current_savings']
                            
                            notification = UserNotification(
                                user_id=customer.id,
                                notification_type=NotificationType.SAVINGS_OPPORTUNITY,
                                title="Savings Opportunity",
                                message=f"You have capacity to save an additional {potential_increase:.2f} per month. Your current savings rate is {current_savings_rate:.1f}%, aim for 15-20%.",
                                priority=NotificationPriority.MEDIUM,
                                created_by=customer.id,
                                created_at=datetime.now(timezone.utc)
                            )
                            db.add(notification)
                            logger.info(f"Created savings opportunity alert for user {customer.id}")
            
            except Exception as e:
                logger.error(f"Error checking savings opportunities for customer {customer.id}: {str(e)}")
                continue
        
        db.commit()
        logger.info("Completed savings opportunities check")
    
    except Exception as e:
        logger.error(f"Error in check_savings_opportunities: {str(e)}")
        db.rollback()


async def generate_periodic_reports(db: Session, period: str = "weekly"):
    """Generate weekly/monthly financial summaries."""
    try:
        logger.info(f"Running {period} periodic reports generation")
        
        # Get all active customers
        customers = db.query(User).filter(User.role == "customer", User.is_active == True).all()
        
        for customer in customers:
            try:
                # Check if report already sent this period
                if period == "weekly":
                    period_start = date.today() - timedelta(days=7)
                    title = "Weekly Financial Summary"
                else:  # monthly
                    period_start = date.today().replace(day=1)
                    title = "Monthly Financial Summary"
                
                existing_report = db.query(UserNotification).filter(
                    UserNotification.user_id == customer.id,
                    UserNotification.notification_type == NotificationType.MONTHLY_SUMMARY,
                    UserNotification.created_at >= datetime.combine(period_start, datetime.min.time()).replace(tzinfo=timezone.utc)
                ).first()
                
                if not existing_report:
                    # Calculate period statistics
                    expenses = db.query(Expense).join(ExpenseCard).filter(
                        ExpenseCard.customer_id == customer.id,
                        Expense.date >= period_start
                    )
                    
                    total_expenses = expenses.with_entities(func.sum(Expense.amount)).scalar() or Decimal(0)
                    expense_count = expenses.count()
                    
                    # Get health score
                    latest_score = db.query(FinancialHealthScore).filter(
                        FinancialHealthScore.customer_id == customer.id
                    ).order_by(FinancialHealthScore.score_date.desc()).first()
                    
                    score_text = f"Your financial health score is {latest_score.score}/100." if latest_score else "Track your finances to get a health score."
                    
                    # Get active goals count
                    active_goals = db.query(SavingsGoal).filter(
                        SavingsGoal.customer_id == customer.id,
                        SavingsGoal.status == GoalStatus.ACTIVE
                    ).count()
                    
                    message = f"{title}:\n"
                    message += f"- Total expenses: {total_expenses:.2f} ({expense_count} transactions)\n"
                    message += f"- {score_text}\n"
                    message += f"- Active savings goals: {active_goals}\n"
                    message += "\nKeep tracking your expenses and working towards your goals!"
                    
                    notification = UserNotification(
                        user_id=customer.id,
                        notification_type=NotificationType.MONTHLY_SUMMARY,
                        title=title,
                        message=message,
                        priority=NotificationPriority.LOW,
                        created_by=customer.id,
                        created_at=datetime.now(timezone.utc)
                    )
                    db.add(notification)
                    logger.info(f"Created {period} summary for user {customer.id}")
            
            except Exception as e:
                logger.error(f"Error generating report for customer {customer.id}: {str(e)}")
                continue
        
        db.commit()
        logger.info(f"Completed {period} periodic reports generation")
    
    except Exception as e:
        logger.error(f"Error in generate_periodic_reports: {str(e)}")
        db.rollback()


async def update_financial_health_scores(db: Session):
    """Update financial health scores for all customers."""
    try:
        logger.info("Running financial health scores update")
        
        # Get all active customers
        customers = db.query(User).filter(User.role == "customer", User.is_active == True).all()
        
        for customer in customers:
            try:
                # Check if score updated in last 7 days
                week_ago = datetime.now(timezone.utc) - timedelta(days=7)
                recent_score = db.query(FinancialHealthScore).filter(
                    FinancialHealthScore.customer_id == customer.id,
                    FinancialHealthScore.score_date >= week_ago
                ).first()
                
                if not recent_score:
                    # Calculate new score
                    new_score = await calculate_financial_health_score(customer.id, db)
                    logger.info(f"Updated health score for user {customer.id}: {new_score.score}")
                    
                    # Get previous score for comparison
                    previous_score = db.query(FinancialHealthScore).filter(
                        FinancialHealthScore.customer_id == customer.id
                    ).order_by(FinancialHealthScore.score_date.desc()).offset(1).first()
                    
                    if previous_score and abs(new_score.score - previous_score.score) >= 10:
                        # Significant change, notify user
                        direction = "improved" if new_score.score > previous_score.score else "declined"
                        change = abs(new_score.score - previous_score.score)
                        
                        notification = UserNotification(
                            user_id=customer.id,
                            notification_type=NotificationType.HEALTH_SCORE,
                            title="Financial Health Score Update",
                            message=f"Your financial health score has {direction} by {change} points to {new_score.score}/100. Keep tracking your progress!",
                            priority=NotificationPriority.MEDIUM,
                            related_entity_id=new_score.id,
                            related_entity_type="health_score",
                            created_by=customer.id,
                            created_at=datetime.now(timezone.utc)
                        )
                        db.add(notification)
                        logger.info(f"Created health score notification for user {customer.id}")
            
            except Exception as e:
                logger.error(f"Error updating health score for customer {customer.id}: {str(e)}")
                continue
        
        db.commit()
        logger.info("Completed financial health scores update")
    
    except Exception as e:
        logger.error(f"Error in update_financial_health_scores: {str(e)}")
        db.rollback()


"""
Financial advisor controller with repository-injected endpoints.
"""
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.postgres_optimized import get_db
from models.financial_advisor import GoalStatus, NotificationType, PatternType
from schemas.financial_advisor import (
    AnomalyResponse,
    FinancialHealthScoreResponse,
    HealthScoreHistory,
    ImprovementRoadmapResponse,
    NotificationMarkReadRequest,
    NotificationResponse,
    PersonalizedAdviceResponse,
    RecommendationResponse,
    RecurringExpenseResponse,
    RoadmapStepResponse,
    GoalAllocationRequest,
    SavingsGoalCreate,
    SavingsGoalResponse,
    SavingsGoalUpdate,
    SavingsOpportunitiesResponse,
    SavingsOpportunityResponse,
    SpendingPatternResponse,
)
from service.financial_advisor import (
    analyze_savings_capacity,
    calculate_financial_health_score,
    detect_spending_patterns,
    generate_improvement_roadmap,
    generate_personalized_advice,
    identify_wasteful_spending,
    recommend_savings_goals,
    recommend_savings_opportunities,
    suggest_category_optimizations,
    track_goal_progress,
)
from store.repositories import (
    ExpenseRepository,
    FinancialHealthScoreRepository,
    SavingsGoalRepository,
    SavingsRepository,
    SpendingPatternRepository,
    UserNotificationRepository,
)
from utils.auth import get_current_user
from utils.dependencies import get_repository
from utils.response import success_response
import logging

logger = logging.getLogger(__name__)


async def create_savings_goal_controller(
    request: SavingsGoalCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    savings_goal_repo: SavingsGoalRepository = Depends(get_repository(SavingsGoalRepository)),
):
    session = savings_goal_repo.db
    try:
        goal = savings_goal_repo.create(
            {
                "customer_id": current_user["user_id"],
                "name": request.name,
                "target_amount": request.target_amount,
                "current_amount": Decimal(0),
                "deadline": request.deadline,
                "priority": request.priority,
                "category": request.category,
                "status": GoalStatus.ACTIVE,
                "description": request.description,
                "is_ai_recommended": False,
                "created_by": current_user["user_id"],
                "created_at": datetime.now(timezone.utc),
            }
        )
        session.commit()
        session.refresh(goal)

        # Notify customer about savings goal creation
        from service.notifications import notify_user
        from models.financial_advisor import NotificationType, NotificationPriority
        from store.repositories import UserNotificationRepository
        await notify_user(
            user_id=current_user["user_id"],
            notification_type=NotificationType.SAVINGS_GOAL_CREATED,
            title="Savings Goal Created",
            message=f"New savings goal '{goal.name}' has been created. Target: {goal.target_amount:.2f}",
            priority=NotificationPriority.LOW,
            db=session,
            notification_repo=UserNotificationRepository(session),
            related_entity_id=goal.id,
            related_entity_type="savings_goal",
        )

        goal_response = SavingsGoalResponse.model_validate(goal)
        if goal.target_amount > 0:
            goal_response.progress_percentage = float(
                goal.current_amount / goal.target_amount * 100
            )
        if goal.deadline:
            goal_response.days_remaining = (goal.deadline - date.today()).days

        logger.info("Created savings goal %s for user %s", goal.id, current_user["user_id"])
        return goal_response
    except Exception as exc:
        session.rollback()
        logger.error("Error creating savings goal: %s", exc)
        raise HTTPException(status_code=500, detail="Error creating savings goal") from exc


async def list_savings_goals_controller(
    status: Optional[str] = Query(None, description="Filter by status (active, achieved, abandoned)"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    savings_goal_repo: SavingsGoalRepository = Depends(get_repository(SavingsGoalRepository)),
):
    try:
        goal_status = None
        if status:
            try:
                goal_status = GoalStatus(status.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid status value")

        goals, total_count = savings_goal_repo.get_goals_with_filters(
            customer_id=current_user["user_id"],
            status=goal_status,
            limit=limit,
            offset=offset,
        )

        goal_responses: List[SavingsGoalResponse] = []
        for goal in goals:
            goal_response = SavingsGoalResponse.model_validate(goal)
            if goal.target_amount > 0:
                goal_response.progress_percentage = float(goal.current_amount / goal.target_amount * 100)
            if goal.deadline:
                goal_response.days_remaining = (goal.deadline - date.today()).days
            goal_responses.append(goal_response)

        return success_response(
            status_code=200,
            message="Goals retrieved successfully",
            data={
                "goals": goal_responses,
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error listing savings goals: %s", exc)
        raise HTTPException(status_code=500, detail="Error retrieving goals") from exc


async def get_savings_goal_controller(
    goal_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    savings_goal_repo: SavingsGoalRepository = Depends(get_repository(SavingsGoalRepository)),
):
    try:
        progress_data = await track_goal_progress(
            goal_id,
            current_user["user_id"],
            db,
            savings_goal_repo=savings_goal_repo,
        )
        if isinstance(progress_data, dict) and progress_data.get("status_code") == 404:
            raise HTTPException(status_code=404, detail="Goal not found")
        return success_response(status_code=200, message="Goal details retrieved", data=progress_data)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error getting goal details: %s", exc)
        raise HTTPException(status_code=500, detail="Error retrieving goal details") from exc


async def update_savings_goal_controller(
    goal_id: int,
    request: SavingsGoalUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    savings_goal_repo: SavingsGoalRepository = Depends(get_repository(SavingsGoalRepository)),
):
    session = savings_goal_repo.db
    try:
        goal = savings_goal_repo.get_by_id_for_customer(goal_id, current_user["user_id"])
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        old_status = goal.status
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(goal, field, value)

        was_achieved = False
        was_abandoned = False
        if goal.current_amount >= goal.target_amount and goal.status != GoalStatus.ACHIEVED:
            goal.status = GoalStatus.ACHIEVED
            was_achieved = True
        
        if goal.status == GoalStatus.ABANDONED and old_status != GoalStatus.ABANDONED:
            was_abandoned = True

        goal.updated_by = current_user["user_id"]
        goal.updated_at = datetime.now(timezone.utc)

        session.commit()
        session.refresh(goal)

        # Notify customer about status changes
        from service.notifications import notify_user
        from models.financial_advisor import NotificationType, NotificationPriority
        from store.repositories import UserNotificationRepository
        if was_achieved:
            await notify_user(
                user_id=current_user["user_id"],
                notification_type=NotificationType.SAVINGS_GOAL_ACHIEVED,
                title="Savings Goal Achieved!",
                message=f"Congratulations! You've achieved your goal '{goal.name}'",
                priority=NotificationPriority.HIGH,
                db=session,
                notification_repo=UserNotificationRepository(session),
                related_entity_id=goal.id,
                related_entity_type="savings_goal",
            )
        elif was_abandoned:
            await notify_user(
                user_id=current_user["user_id"],
                notification_type=NotificationType.SAVINGS_GOAL_ABANDONED,
                title="Savings Goal Abandoned",
                message=f"Your savings goal '{goal.name}' has been marked as abandoned",
                priority=NotificationPriority.MEDIUM,
                db=session,
                notification_repo=UserNotificationRepository(session),
                related_entity_id=goal.id,
                related_entity_type="savings_goal",
            )

        goal_response = SavingsGoalResponse.model_validate(goal)
        if goal.target_amount > 0:
            goal_response.progress_percentage = float(goal.current_amount / goal.target_amount * 100)
        if goal.deadline:
            goal_response.days_remaining = (goal.deadline - date.today()).days

        logger.info("Updated savings goal %s", goal_id)
        return goal_response
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        logger.error("Error updating goal: %s", exc)
        raise HTTPException(status_code=500, detail="Error updating goal") from exc


async def delete_savings_goal_controller(
    goal_id: int,
    current_user: dict = Depends(get_current_user),
    savings_goal_repo: SavingsGoalRepository = Depends(get_repository(SavingsGoalRepository)),
):
    session = savings_goal_repo.db
    try:
        goal = savings_goal_repo.get_by_id_for_customer(goal_id, current_user["user_id"])
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        session.delete(goal)
        session.commit()

        logger.info("Deleted savings goal %s", goal_id)
        return success_response(
            status_code=200,
            message="Goal deleted successfully",
            data={"goal_id": goal_id},
        )
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        logger.error("Error deleting goal: %s", exc)
        raise HTTPException(status_code=500, detail="Error deleting goal") from exc


async def get_ai_recommended_goals_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        recommendations = await recommend_savings_goals(
            current_user["user_id"],
            db,
        )
        return recommendations
    except Exception as exc:
        logger.error("Error generating goal recommendations: %s", exc)
        raise HTTPException(status_code=500, detail="Error generating recommendations") from exc


async def allocate_to_goal_controller(
    goal_id: int,
    request: GoalAllocationRequest,
    current_user: dict = Depends(get_current_user),
    savings_goal_repo: SavingsGoalRepository = Depends(get_repository(SavingsGoalRepository)),
):
    session = savings_goal_repo.db
    try:
        goal = savings_goal_repo.get_by_id_for_customer(goal_id, current_user["user_id"])
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        if request.amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")

        was_achieved = False
        goal.current_amount += request.amount
        if goal.current_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE:
            goal.status = GoalStatus.ACHIEVED
            was_achieved = True

        goal.updated_by = current_user["user_id"]
        goal.updated_at = datetime.now(timezone.utc)

        session.commit()
        session.refresh(goal)

        # Notify customer if goal was achieved
        if was_achieved:
            from service.notifications import notify_user
            from models.financial_advisor import NotificationType, NotificationPriority
            from store.repositories import UserNotificationRepository
            await notify_user(
                user_id=current_user["user_id"],
                notification_type=NotificationType.SAVINGS_GOAL_ACHIEVED,
                title="Savings Goal Achieved!",
                message=f"Congratulations! You've achieved your goal '{goal.name}'",
                priority=NotificationPriority.HIGH,
                db=session,
                notification_repo=UserNotificationRepository(session),
                related_entity_id=goal.id,
                related_entity_type="savings_goal",
            )

        goal_response = SavingsGoalResponse.model_validate(goal)
        if goal.target_amount > 0:
            goal_response.progress_percentage = float(goal.current_amount / goal.target_amount * 100)
        if goal.deadline:
            goal_response.days_remaining = (goal.deadline - date.today()).days

        logger.info("Allocated %s to goal %s", request.amount, goal_id)
        return goal_response
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        logger.error("Error allocating to goal: %s", exc)
        raise HTTPException(status_code=500, detail="Error allocating funds") from exc


async def get_current_health_score_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    financial_health_repo: FinancialHealthScoreRepository = Depends(get_repository(FinancialHealthScoreRepository)),
    savings_goal_repo: SavingsGoalRepository = Depends(get_repository(SavingsGoalRepository)),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
):
    try:
        recent_score = financial_health_repo.get_recent_score(current_user["user_id"])
        if recent_score:
            return FinancialHealthScoreResponse.model_validate(recent_score)

        score = await calculate_financial_health_score(
            current_user["user_id"],
            db,
            financial_health_repo=financial_health_repo,
            savings_goal_repo=savings_goal_repo,
            expense_repo=expense_repo,
            expense_card_repo=None,
            savings_repo=savings_repo,
        )
        return score
    except Exception as exc:
        logger.error("Error getting health score: %s", exc)
        raise HTTPException(status_code=500, detail="Error calculating health score") from exc


async def get_health_score_history_controller(
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    financial_health_repo: FinancialHealthScoreRepository = Depends(get_repository(FinancialHealthScoreRepository)),
):
    try:
        scores = financial_health_repo.get_history(current_user["user_id"], limit=limit)
        if not scores:
            raise HTTPException(status_code=404, detail="No health scores found")

        score_responses = [FinancialHealthScoreResponse.model_validate(s) for s in scores]
        average_score = sum(s.score for s in scores) / len(scores)

        if len(scores) >= 2:
            midpoint = len(scores) // 2
            recent_avg = sum(s.score for s in scores[:midpoint]) / max(midpoint, 1)
            older_avg = sum(s.score for s in scores[midpoint:]) / max(len(scores) - midpoint, 1)

            if recent_avg > older_avg + 5:
                trend = "improving"
            elif recent_avg < older_avg - 5:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return HealthScoreHistory(scores=score_responses, average_score=average_score, trend=trend)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error getting health score history: %s", exc)
        raise HTTPException(status_code=500, detail="Error retrieving history") from exc


async def get_improvement_roadmap_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    financial_health_repo: FinancialHealthScoreRepository = Depends(get_repository(FinancialHealthScoreRepository)),
    savings_goal_repo: SavingsGoalRepository = Depends(get_repository(SavingsGoalRepository)),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
):
    try:
        roadmap = await generate_improvement_roadmap(
            current_user["user_id"],
            db,
            financial_health_repo=financial_health_repo,
            savings_goal_repo=savings_goal_repo,
            expense_repo=expense_repo,
            expense_card_repo=None,
            savings_repo=savings_repo,
        )
        return roadmap
    except Exception as exc:
        logger.error("Error generating roadmap: %s", exc)
        raise HTTPException(status_code=500, detail="Error generating roadmap") from exc


async def get_spending_patterns_controller(
    pattern_type: Optional[str] = Query(None, description="Filter by type (recurring, seasonal, anomaly)"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
    spending_pattern_repo: SpendingPatternRepository = Depends(get_repository(SpendingPatternRepository)),
):
    try:
        patterns = await detect_spending_patterns(
            current_user["user_id"],
            db,
            expense_repo=expense_repo,
            spending_pattern_repo=spending_pattern_repo,
        )

        if pattern_type:
            try:
                requested_type = PatternType(pattern_type.lower())
                patterns = [p for p in patterns if p.pattern_type == requested_type]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid pattern type")

        return patterns
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error getting spending patterns: %s", exc)
        raise HTTPException(status_code=500, detail="Error retrieving patterns") from exc


async def get_recurring_expenses_controller(
    current_user: dict = Depends(get_current_user),
    spending_pattern_repo: SpendingPatternRepository = Depends(get_repository(SpendingPatternRepository)),
):
    try:
        patterns = spending_pattern_repo.get_by_type(current_user["user_id"], PatternType.RECURRING)

        recurring_expenses: List[RecurringExpenseResponse] = []
        for pattern in patterns:
            if pattern.amount and pattern.frequency:
                freq_multipliers = {"weekly": 52, "monthly": 12, "quarterly": 4}
                multiplier = freq_multipliers.get(pattern.frequency, 12)
                yearly_cost = pattern.amount * multiplier

                recurring_expenses.append(
                    RecurringExpenseResponse(
                        description=pattern.description,
                        amount=pattern.amount,
                        frequency=pattern.frequency,
                        last_occurrence=pattern.last_occurrence,
                        next_expected=None,
                        total_yearly_cost=yearly_cost,
                    )
                )

        return recurring_expenses
    except Exception as exc:
        logger.error("Error getting recurring expenses: %s", exc)
        raise HTTPException(status_code=500, detail="Error retrieving recurring expenses") from exc


async def get_spending_anomalies_controller(
    current_user: dict = Depends(get_current_user),
    spending_pattern_repo: SpendingPatternRepository = Depends(get_repository(SpendingPatternRepository)),
):
    try:
        patterns = (
            spending_pattern_repo.db.query(spending_pattern_repo.model)
            .filter(
                spending_pattern_repo.model.customer_id == current_user["user_id"],
                spending_pattern_repo.model.pattern_type == PatternType.ANOMALY,
            )
            .order_by(spending_pattern_repo.model.detected_at.desc())
            .limit(20)
            .all()
        )

        anomalies: List[AnomalyResponse] = []
        for pattern in patterns:
            pattern_meta = pattern.pattern_metadata or {}
            anomalies.append(
                AnomalyResponse(
                    description=pattern.description,
                    amount=pattern.amount or Decimal(0),
                    date=pattern.last_occurrence,
                    deviation_percentage=pattern_meta.get("deviation_percentage", 0),
                    severity=pattern_meta.get("severity", "medium"),
                )
            )

        return anomalies
    except Exception as exc:
        logger.error("Error getting anomalies: %s", exc)
        raise HTTPException(status_code=500, detail="Error retrieving anomalies") from exc


async def get_personalized_advice_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    financial_health_repo: FinancialHealthScoreRepository = Depends(get_repository(FinancialHealthScoreRepository)),
    savings_goal_repo: SavingsGoalRepository = Depends(get_repository(SavingsGoalRepository)),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
    spending_pattern_repo: SpendingPatternRepository = Depends(get_repository(SpendingPatternRepository)),
) -> PersonalizedAdviceResponse:
    try:
        advice = await generate_personalized_advice(
            current_user["user_id"],
            db,
            financial_health_repo=financial_health_repo,
            savings_goal_repo=savings_goal_repo,
            expense_repo=expense_repo,
            expense_card_repo=None,
            savings_repo=savings_repo,
            spending_pattern_repo=spending_pattern_repo,
        )
        return advice
    except Exception as exc:
        logger.error("Error generating advice: %s", exc)
        raise HTTPException(status_code=500, detail="Error generating advice") from exc


async def get_category_recommendations_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
) -> List[RecommendationResponse]:
    try:
        recommendations_data = await suggest_category_optimizations(
            current_user["user_id"],
            db,
            expense_repo=expense_repo,
        )
        recommendations: List[RecommendationResponse] = []
        for item in recommendations_data:
            recommendations.append(
                RecommendationResponse(
                    title=f"Optimize {item['category']} Spending",
                    description=item["description"],
                    category=item["category"],
                    potential_savings=item.get("potential_savings"),
                    priority="medium",
                    action_items=item.get("action_items", []),
                )
            )
        return recommendations
    except Exception as exc:
        logger.error("Error getting recommendations: %s", exc)
        raise HTTPException(status_code=500, detail="Error generating recommendations") from exc


async def get_savings_opportunities_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
    spending_pattern_repo: SpendingPatternRepository = Depends(get_repository(SpendingPatternRepository)),
) -> SavingsOpportunitiesResponse:
    try:
        opportunities = await recommend_savings_opportunities(
            current_user["user_id"],
            db,
            expense_repo=expense_repo,
            spending_pattern_repo=spending_pattern_repo,
        )
        return opportunities
    except Exception as exc:
        logger.error("Error getting savings opportunities: %s", exc)
        raise HTTPException(status_code=500, detail="Error retrieving opportunities") from exc


async def get_notifications_controller(
    unread_only: bool = Query(False, description="Show only unread notifications"),
    notification_type: Optional[str] = Query(None, description="Filter by type"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    notification_repo: UserNotificationRepository = Depends(get_repository(UserNotificationRepository)),
):
    try:
        resolved_type: Optional[NotificationType] = None
        if notification_type:
            try:
                resolved_type = NotificationType(notification_type.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid notification type")

        notifications, total_count = notification_repo.get_notifications_with_filters(
            user_id=current_user["user_id"],
            unread_only=unread_only,
            notification_type=resolved_type,
            limit=limit,
            offset=offset,
        )

        notification_responses = [NotificationResponse.model_validate(n) for n in notifications]
        unread_count = notification_repo.get_unread_count(current_user["user_id"])

        return success_response(
            status_code=200,
            message="Notifications retrieved successfully",
            data={
                "notifications": notification_responses,
                "total_count": total_count,
                "unread_count": unread_count,
                "limit": limit,
                "offset": offset,
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error getting notifications: %s", exc)
        raise HTTPException(status_code=500, detail="Error retrieving notifications") from exc


async def mark_notification_as_read_controller(
    notification_id: int,
    request: NotificationMarkReadRequest,
    current_user: dict = Depends(get_current_user),
    notification_repo: UserNotificationRepository = Depends(get_repository(UserNotificationRepository)),
):
    session = notification_repo.db
    try:
        notification = notification_repo.get_by_id_for_user(notification_id, current_user["user_id"])
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        notification.is_read = request.is_read
        notification.updated_at = datetime.now(timezone.utc)

        session.commit()
        session.refresh(notification)

        return NotificationResponse.model_validate(notification)
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        logger.error("Error marking notification: %s", exc)
        raise HTTPException(status_code=500, detail="Error updating notification") from exc


async def get_unread_notification_count_controller(
    current_user: dict = Depends(get_current_user),
    notification_repo: UserNotificationRepository = Depends(get_repository(UserNotificationRepository)),
):
    try:
        count = notification_repo.get_unread_count(current_user["user_id"])
        return success_response(
            status_code=200,
            message="Unread count retrieved",
            data={"unread_count": count},
        )
    except Exception as exc:
        logger.error("Error getting unread count: %s", exc)
        raise HTTPException(status_code=500, detail="Error retrieving count") from exc


async def get_savings_capacity_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
):
    try:
        capacity = await analyze_savings_capacity(
            current_user["user_id"],
            db,
            expense_repo=expense_repo,
            expense_card_repo=None,
            savings_repo=savings_repo,
        )
        return success_response(
            status_code=200,
            message="Savings capacity analyzed",
            data=capacity,
        )
    except Exception as exc:
        logger.error("Error analyzing capacity: %s", exc)
        raise HTTPException(status_code=500, detail="Error analyzing capacity") from exc


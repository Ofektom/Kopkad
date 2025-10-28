from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

from schemas.financial_advisor import (
    SavingsGoalCreate, SavingsGoalUpdate, SavingsGoalResponse, GoalAllocationRequest,
    FinancialHealthScoreResponse, HealthScoreHistory,
    SpendingPatternResponse, RecurringExpenseResponse, AnomalyResponse,
    PersonalizedAdviceResponse, RecommendationResponse,
    ImprovementRoadmapResponse, SavingsOpportunitiesResponse,
    NotificationResponse, NotificationMarkReadRequest
)
from models.financial_advisor import (
    SavingsGoal, FinancialHealthScore, SpendingPattern, UserNotification,
    GoalStatus, PatternType, NotificationType
)
from service.financial_advisor import (
    analyze_savings_capacity, recommend_savings_goals, track_goal_progress,
    detect_spending_patterns, identify_wasteful_spending,
    calculate_financial_health_score, generate_improvement_roadmap,
    generate_personalized_advice, suggest_category_optimizations,
    recommend_savings_opportunities
)
from database.postgres_optimized import get_db
from utils.auth import get_current_user
from utils.response import success_response, error_response
import logging

logger = logging.getLogger(__name__)

financial_advisor_router = APIRouter(tags=["Financial Advisor"], prefix="/advisor")


# ========================
# SAVINGS GOALS ENDPOINTS
# ========================

@financial_advisor_router.post("/goals", response_model=SavingsGoalResponse)
async def create_savings_goal(
    request: SavingsGoalCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new savings goal."""
    try:
        goal = SavingsGoal(
            customer_id=current_user["user_id"],
            name=request.name,
            target_amount=request.target_amount,
            current_amount=Decimal(0),
            deadline=request.deadline,
            priority=request.priority,
            category=request.category,
            status=GoalStatus.ACTIVE,
            is_ai_recommended=False,
            description=request.description,
            created_by=current_user["user_id"],
            created_at=datetime.now(timezone.utc)
        )
        db.add(goal)
        db.commit()
        db.refresh(goal)
        
        logger.info(f"Created savings goal {goal.id} for user {current_user['user_id']}")
        
        # Add calculated fields
        goal_response = SavingsGoalResponse.model_validate(goal)
        if goal.target_amount > 0:
            goal_response.progress_percentage = float(goal.current_amount / goal.target_amount * 100)
        if goal.deadline:
            goal_response.days_remaining = (goal.deadline - date.today()).days
        
        return goal_response
    except Exception as e:
        logger.error(f"Error creating savings goal: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error creating savings goal")


@financial_advisor_router.get("/goals", response_model=dict)
async def list_savings_goals(
    status: Optional[str] = Query(None, description="Filter by status (active, achieved, abandoned)"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List user's savings goals with progress."""
    try:
        query = db.query(SavingsGoal).filter(SavingsGoal.customer_id == current_user["user_id"])
        
        if status:
            try:
                goal_status = GoalStatus(status.lower())
                query = query.filter(SavingsGoal.status == goal_status)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid status value")
        
        total_count = query.count()
        goals = query.order_by(SavingsGoal.created_at.desc()).offset(offset).limit(limit).all()
        
        # Add calculated fields
        goal_responses = []
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
            data={"goals": goal_responses, "total_count": total_count, "limit": limit, "offset": offset}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing savings goals: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving goals")


@financial_advisor_router.get("/goals/{goal_id}", response_model=dict)
async def get_savings_goal(
    goal_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get detailed goal progress and suggestions."""
    try:
        progress_data = await track_goal_progress(goal_id, current_user["user_id"], db)
        return success_response(status_code=200, message="Goal details retrieved", data=progress_data)
    except Exception as e:
        logger.error(f"Error getting goal details: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving goal details")


@financial_advisor_router.put("/goals/{goal_id}", response_model=SavingsGoalResponse)
async def update_savings_goal(
    goal_id: int,
    request: SavingsGoalUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a savings goal."""
    try:
        goal = db.query(SavingsGoal).filter(
            SavingsGoal.id == goal_id,
            SavingsGoal.customer_id == current_user["user_id"]
        ).first()
        
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")
        
        # Update fields
        if request.name is not None:
            goal.name = request.name
        if request.target_amount is not None:
            goal.target_amount = request.target_amount
        if request.current_amount is not None:
            goal.current_amount = request.current_amount
            # Check if goal achieved
            if goal.current_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE:
                goal.status = GoalStatus.ACHIEVED
        if request.deadline is not None:
            goal.deadline = request.deadline
        if request.priority is not None:
            goal.priority = request.priority
        if request.category is not None:
            goal.category = request.category
        if request.status is not None:
            goal.status = request.status
        if request.description is not None:
            goal.description = request.description
        
        goal.updated_by = current_user["user_id"]
        goal.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(goal)
        
        logger.info(f"Updated savings goal {goal_id}")
        
        goal_response = SavingsGoalResponse.model_validate(goal)
        if goal.target_amount > 0:
            goal_response.progress_percentage = float(goal.current_amount / goal.target_amount * 100)
        if goal.deadline:
            goal_response.days_remaining = (goal.deadline - date.today()).days
        
        return goal_response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating goal: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error updating goal")


@financial_advisor_router.delete("/goals/{goal_id}", response_model=dict)
async def delete_savings_goal(
    goal_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a savings goal."""
    try:
        goal = db.query(SavingsGoal).filter(
            SavingsGoal.id == goal_id,
            SavingsGoal.customer_id == current_user["user_id"]
        ).first()
        
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")
        
        db.delete(goal)
        db.commit()
        
        logger.info(f"Deleted savings goal {goal_id}")
        return success_response(status_code=200, message="Goal deleted successfully", data={"goal_id": goal_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting goal: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error deleting goal")


@financial_advisor_router.get("/goals/recommendations/ai", response_model=List[SavingsGoalResponse])
async def get_ai_recommended_goals(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get AI-recommended savings goals based on financial situation."""
    try:
        recommendations = await recommend_savings_goals(current_user["user_id"], db)
        return recommendations
    except Exception as e:
        logger.error(f"Error generating goal recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail="Error generating recommendations")


@financial_advisor_router.post("/goals/{goal_id}/allocate", response_model=SavingsGoalResponse)
async def allocate_to_goal(
    goal_id: int,
    request: GoalAllocationRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Allocate funds to a savings goal."""
    try:
        goal = db.query(SavingsGoal).filter(
            SavingsGoal.id == goal_id,
            SavingsGoal.customer_id == current_user["user_id"]
        ).first()
        
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")
        
        if request.amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        
        goal.current_amount += request.amount
        
        # Check if goal achieved
        if goal.current_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE:
            goal.status = GoalStatus.ACHIEVED
        
        goal.updated_by = current_user["user_id"]
        goal.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(goal)
        
        logger.info(f"Allocated {request.amount} to goal {goal_id}")
        
        goal_response = SavingsGoalResponse.model_validate(goal)
        if goal.target_amount > 0:
            goal_response.progress_percentage = float(goal.current_amount / goal.target_amount * 100)
        if goal.deadline:
            goal_response.days_remaining = (goal.deadline - date.today()).days
        
        return goal_response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error allocating to goal: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error allocating funds")


# ========================
# FINANCIAL HEALTH ENDPOINTS
# ========================

@financial_advisor_router.get("/health-score", response_model=FinancialHealthScoreResponse)
async def get_current_health_score(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current financial health score."""
    try:
        # Check if recent score exists (within last 7 days)
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_score = db.query(FinancialHealthScore).filter(
            FinancialHealthScore.customer_id == current_user["user_id"],
            FinancialHealthScore.score_date >= week_ago
        ).order_by(FinancialHealthScore.score_date.desc()).first()
        
        if recent_score:
            return FinancialHealthScoreResponse.model_validate(recent_score)
        
        # Calculate new score
        score = await calculate_financial_health_score(current_user["user_id"], db)
        return score
    except Exception as e:
        logger.error(f"Error getting health score: {str(e)}")
        raise HTTPException(status_code=500, detail="Error calculating health score")


@financial_advisor_router.get("/health-score/history", response_model=HealthScoreHistory)
async def get_health_score_history(
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get historical financial health scores."""
    try:
        scores = db.query(FinancialHealthScore).filter(
            FinancialHealthScore.customer_id == current_user["user_id"]
        ).order_by(FinancialHealthScore.score_date.desc()).limit(limit).all()
        
        if not scores:
            raise HTTPException(status_code=404, detail="No health scores found")
        
        score_responses = [FinancialHealthScoreResponse.model_validate(s) for s in scores]
        average_score = sum(s.score for s in scores) / len(scores)
        
        # Determine trend
        if len(scores) >= 2:
            recent_avg = sum(s.score for s in scores[:len(scores)//2]) / (len(scores)//2)
            older_avg = sum(s.score for s in scores[len(scores)//2:]) / (len(scores) - len(scores)//2)
            
            if recent_avg > older_avg + 5:
                trend = "improving"
            elif recent_avg < older_avg - 5:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"
        
        return HealthScoreHistory(
            scores=score_responses,
            average_score=average_score,
            trend=trend
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting health score history: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving history")


@financial_advisor_router.get("/roadmap", response_model=ImprovementRoadmapResponse)
async def get_improvement_roadmap(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get personalized improvement roadmap."""
    try:
        roadmap = await generate_improvement_roadmap(current_user["user_id"], db)
        return roadmap
    except Exception as e:
        logger.error(f"Error generating roadmap: {str(e)}")
        raise HTTPException(status_code=500, detail="Error generating roadmap")


# ========================
# SPENDING PATTERNS ENDPOINTS
# ========================

@financial_advisor_router.get("/patterns", response_model=List[SpendingPatternResponse])
async def get_spending_patterns(
    pattern_type: Optional[str] = Query(None, description="Filter by type (recurring, seasonal, anomaly)"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get detected spending patterns."""
    try:
        query = db.query(SpendingPattern).filter(SpendingPattern.customer_id == current_user["user_id"])
        
        if pattern_type:
            try:
                ptype = PatternType(pattern_type.lower())
                query = query.filter(SpendingPattern.pattern_type == ptype)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid pattern type")
        
        patterns = query.order_by(SpendingPattern.detected_at.desc()).all()
        return [SpendingPatternResponse.model_validate(p) for p in patterns]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting spending patterns: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving patterns")


@financial_advisor_router.get("/patterns/recurring", response_model=List[dict])
async def get_recurring_expenses(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get analysis of recurring expenses."""
    try:
        patterns = db.query(SpendingPattern).filter(
            SpendingPattern.customer_id == current_user["user_id"],
            SpendingPattern.pattern_type == PatternType.RECURRING
        ).all()
        
        recurring_expenses = []
        for pattern in patterns:
            if pattern.amount and pattern.frequency:
                # Calculate yearly cost
                freq_multipliers = {"weekly": 52, "monthly": 12, "quarterly": 4}
                multiplier = freq_multipliers.get(pattern.frequency, 12)
                yearly_cost = pattern.amount * multiplier
                
                recurring_expenses.append({
                    "description": pattern.description,
                    "amount": pattern.amount,
                    "frequency": pattern.frequency,
                    "last_occurrence": pattern.last_occurrence,
                    "total_yearly_cost": yearly_cost
                })
        
        return recurring_expenses
    except Exception as e:
        logger.error(f"Error getting recurring expenses: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving recurring expenses")


@financial_advisor_router.get("/patterns/anomalies", response_model=List[dict])
async def get_spending_anomalies(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get unusual spending alerts."""
    try:
        patterns = db.query(SpendingPattern).filter(
            SpendingPattern.customer_id == current_user["user_id"],
            SpendingPattern.pattern_type == PatternType.ANOMALY
        ).order_by(SpendingPattern.detected_at.desc()).limit(20).all()
        
        anomalies = []
        for pattern in patterns:
            pattern_meta = pattern.pattern_metadata or {}
            anomalies.append({
                "description": pattern.description,
                "amount": pattern.amount,
                "date": pattern.last_occurrence,
                "deviation_percentage": pattern_meta.get("deviation_percentage", 0),
                "severity": pattern_meta.get("severity", "medium")
            })
        
        return anomalies
    except Exception as e:
        logger.error(f"Error getting anomalies: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving anomalies")


# ========================
# ADVICE & RECOMMENDATIONS ENDPOINTS
# ========================

@financial_advisor_router.get("/advice", response_model=PersonalizedAdviceResponse)
async def get_personalized_advice(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get comprehensive personalized financial advice."""
    try:
        advice = await generate_personalized_advice(current_user["user_id"], db)
        return advice
    except Exception as e:
        logger.error(f"Error generating advice: {str(e)}")
        raise HTTPException(status_code=500, detail="Error generating advice")


@financial_advisor_router.get("/recommendations", response_model=List[dict])
async def get_category_recommendations(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get category-specific optimization recommendations."""
    try:
        recommendations = await suggest_category_optimizations(current_user["user_id"], db)
        return recommendations
    except Exception as e:
        logger.error(f"Error getting recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail="Error generating recommendations")


@financial_advisor_router.get("/opportunities", response_model=SavingsOpportunitiesResponse)
async def get_savings_opportunities(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get identified savings opportunities."""
    try:
        opportunities = await recommend_savings_opportunities(current_user["user_id"], db)
        return opportunities
    except Exception as e:
        logger.error(f"Error getting savings opportunities: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving opportunities")


# ========================
# NOTIFICATIONS ENDPOINTS
# ========================

@financial_advisor_router.get("/notifications", response_model=dict)
async def get_notifications(
    unread_only: bool = Query(False, description="Show only unread notifications"),
    notification_type: Optional[str] = Query(None, description="Filter by type"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get user notifications."""
    try:
        query = db.query(UserNotification).filter(UserNotification.user_id == current_user["user_id"])
        
        if unread_only:
            query = query.filter(UserNotification.is_read == False)
        
        if notification_type:
            try:
                ntype = NotificationType(notification_type.lower())
                query = query.filter(UserNotification.notification_type == ntype)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid notification type")
        
        total_count = query.count()
        notifications = query.order_by(UserNotification.created_at.desc()).offset(offset).limit(limit).all()
        
        notification_responses = [NotificationResponse.model_validate(n) for n in notifications]
        
        return success_response(
            status_code=200,
            message="Notifications retrieved successfully",
            data={
                "notifications": notification_responses,
                "total_count": total_count,
                "unread_count": db.query(UserNotification).filter(
                    UserNotification.user_id == current_user["user_id"],
                    UserNotification.is_read == False
                ).count(),
                "limit": limit,
                "offset": offset
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting notifications: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving notifications")


@financial_advisor_router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_as_read(
    notification_id: int,
    request: NotificationMarkReadRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark notification as read/unread."""
    try:
        notification = db.query(UserNotification).filter(
            UserNotification.id == notification_id,
            UserNotification.user_id == current_user["user_id"]
        ).first()
        
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        notification.is_read = request.is_read
        notification.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(notification)
        
        return NotificationResponse.model_validate(notification)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error updating notification")


@financial_advisor_router.get("/notifications/unread-count", response_model=dict)
async def get_unread_notification_count(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get count of unread notifications."""
    try:
        count = db.query(UserNotification).filter(
            UserNotification.user_id == current_user["user_id"],
            UserNotification.is_read == False
        ).count()
        
        return success_response(
            status_code=200,
            message="Unread count retrieved",
            data={"unread_count": count}
        )
    except Exception as e:
        logger.error(f"Error getting unread count: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving count")


# ========================
# CAPACITY ANALYSIS ENDPOINT
# ========================

@financial_advisor_router.get("/capacity", response_model=dict)
async def get_savings_capacity(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Analyze savings capacity based on income and expenses."""
    try:
        capacity = await analyze_savings_capacity(current_user["user_id"], db)
        return success_response(
            status_code=200,
            message="Savings capacity analyzed",
            data=capacity
        )
    except Exception as e:
        logger.error(f"Error analyzing capacity: {str(e)}")
        raise HTTPException(status_code=500, detail="Error analyzing capacity")


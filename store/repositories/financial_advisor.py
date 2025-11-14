"""
Repositories for financial advisor models.
"""
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from .base import BaseRepository
from models.financial_advisor import (
    SavingsGoal,
    FinancialHealthScore,
    SpendingPattern,
    UserNotification,
    GoalStatus,
    PatternType,
    NotificationType,
)


class SavingsGoalRepository(BaseRepository[SavingsGoal]):
    """Repository for managing savings goals."""

    def __init__(self, db: Session):
        super().__init__(SavingsGoal, db)

    def get_goals_with_filters(
        self,
        *,
        customer_id: int,
        status: Optional[GoalStatus] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Tuple[List[SavingsGoal], int]:
        """Retrieve savings goals for a customer with optional filtering."""
        query = self.db.query(SavingsGoal).filter(
            SavingsGoal.customer_id == customer_id
        )

        if status:
            query = query.filter(SavingsGoal.status == status)

        total_count = query.count()
        goals = (
            query.order_by(SavingsGoal.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return goals, total_count

    def get_by_id_for_customer(
        self, goal_id: int, customer_id: int
    ) -> Optional[SavingsGoal]:
        """Get a goal by ID for a specific customer."""
        return (
            self.db.query(SavingsGoal)
            .filter(
                SavingsGoal.id == goal_id,
                SavingsGoal.customer_id == customer_id,
            )
            .first()
        )

    def get_all_for_customer(self, customer_id: int) -> List[SavingsGoal]:
        """Get all goals for a customer."""
        return (
            self.db.query(SavingsGoal)
            .filter(SavingsGoal.customer_id == customer_id)
            .all()
        )

    def get_active_with_deadlines(self) -> List[SavingsGoal]:
        """Get active goals that have deadlines."""
        return (
            self.db.query(SavingsGoal)
            .filter(
                SavingsGoal.status == GoalStatus.ACTIVE,
                SavingsGoal.deadline.isnot(None),
            )
            .all()
        )

    def count_active_for_customer(self, customer_id: int) -> int:
        """Count active goals for a customer."""
        return (
            self.db.query(func.count(SavingsGoal.id))
            .filter(
                SavingsGoal.customer_id == customer_id,
                SavingsGoal.status == GoalStatus.ACTIVE,
            )
            .scalar()
            or 0
        )


class FinancialHealthScoreRepository(BaseRepository[FinancialHealthScore]):
    """Repository for managing financial health scores."""

    def __init__(self, db: Session):
        super().__init__(FinancialHealthScore, db)

    def get_recent_score(
        self, customer_id: int, days: int = 7
    ) -> Optional[FinancialHealthScore]:
        """Get the most recent score within the specified days."""
        from datetime import datetime, timezone, timedelta

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        return (
            self.db.query(FinancialHealthScore)
            .filter(
                FinancialHealthScore.customer_id == customer_id,
                FinancialHealthScore.score_date >= cutoff_date,
            )
            .order_by(FinancialHealthScore.score_date.desc())
            .first()
        )

    def get_history(
        self, customer_id: int, limit: int = 10
    ) -> List[FinancialHealthScore]:
        """Get historical scores for a customer."""
        return (
            self.db.query(FinancialHealthScore)
            .filter(FinancialHealthScore.customer_id == customer_id)
            .order_by(FinancialHealthScore.score_date.desc())
            .limit(limit)
            .all()
        )

    def get_recent_since(
        self, customer_id: int, since
    ) -> Optional[FinancialHealthScore]:
        """Get the most recent score since a specific datetime."""
        return (
            self.db.query(FinancialHealthScore)
            .filter(
                FinancialHealthScore.customer_id == customer_id,
                FinancialHealthScore.score_date >= since,
            )
            .order_by(FinancialHealthScore.score_date.desc())
            .first()
        )

    def get_previous_score(self, customer_id: int) -> Optional[FinancialHealthScore]:
        """Get the score immediately preceding the most recent one."""
        return (
            self.db.query(FinancialHealthScore)
            .filter(FinancialHealthScore.customer_id == customer_id)
            .order_by(FinancialHealthScore.score_date.desc())
            .offset(1)
            .first()
        )


class SpendingPatternRepository(BaseRepository[SpendingPattern]):
    """Repository for managing spending patterns."""

    def __init__(self, db: Session):
        super().__init__(SpendingPattern, db)

    def get_patterns_with_filters(
        self,
        *,
        customer_id: int,
        pattern_type: Optional[PatternType] = None,
        limit: int = 20,
    ) -> List[SpendingPattern]:
        """Retrieve spending patterns for a customer with optional filtering."""
        query = self.db.query(SpendingPattern).filter(
            SpendingPattern.customer_id == customer_id
        )

        if pattern_type:
            query = query.filter(SpendingPattern.pattern_type == pattern_type)

        return (
            query.order_by(SpendingPattern.detected_at.desc()).limit(limit).all()
        )

    def get_by_type(
        self, customer_id: int, pattern_type: PatternType
    ) -> List[SpendingPattern]:
        """Get patterns of a specific type for a customer."""
        return (
            self.db.query(SpendingPattern)
            .filter(
                SpendingPattern.customer_id == customer_id,
                SpendingPattern.pattern_type == pattern_type,
            )
            .order_by(SpendingPattern.detected_at.desc())
            .all()
        )

    def get_recent_by_type(
        self, customer_id: int, pattern_type: PatternType, since
    ) -> List[SpendingPattern]:
        """Get recent patterns of a type since a given datetime."""
        return (
            self.db.query(SpendingPattern)
            .filter(
                SpendingPattern.customer_id == customer_id,
                SpendingPattern.pattern_type == pattern_type,
                SpendingPattern.detected_at >= since,
            )
            .order_by(SpendingPattern.detected_at.desc())
            .all()
        )


class UserNotificationRepository(BaseRepository[UserNotification]):
    """Repository for managing user notifications."""

    def __init__(self, db: Session):
        super().__init__(UserNotification, db)

    def get_notifications_with_filters(
        self,
        *,
        user_id: int,
        unread_only: bool = False,
        notification_type: Optional[NotificationType] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[UserNotification], int]:
        """Retrieve notifications for a user with optional filtering."""
        query = self.db.query(UserNotification).filter(
            UserNotification.user_id == user_id
        )

        if unread_only:
            query = query.filter(UserNotification.is_read == False)

        if notification_type:
            query = query.filter(
                UserNotification.notification_type == notification_type
            )

        total_count = query.count()
        notifications = (
            query.order_by(UserNotification.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return notifications, total_count

    def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications for a user."""
        return (
            self.db.query(UserNotification)
            .filter(
                UserNotification.user_id == user_id,
                UserNotification.is_read == False,
            )
            .count()
        )

    def get_by_id_for_user(
        self, notification_id: int, user_id: int
    ) -> Optional[UserNotification]:
        """Get a notification by ID for a specific user."""
        return (
            self.db.query(UserNotification)
            .filter(
                UserNotification.id == notification_id,
                UserNotification.user_id == user_id,
            )
            .first()
        )

    def find_recent(
        self,
        *,
        user_id: int,
        notification_type: NotificationType,
        since,
        related_entity_id: Optional[int] = None,
    ) -> Optional[UserNotification]:
        """Find a recent notification of a given type (and optional related entity)."""
        query = self.db.query(UserNotification).filter(
            UserNotification.user_id == user_id,
            UserNotification.notification_type == notification_type,
            UserNotification.created_at >= since,
        )
        if related_entity_id is not None:
            query = query.filter(
                UserNotification.related_entity_id == related_entity_id
            )
        return query.first()


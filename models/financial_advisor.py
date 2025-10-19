from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Enum, DateTime, Date, Boolean, JSON, Text
from sqlalchemy.orm import relationship
from database.postgres import Base
from models.audit import AuditMixin
from enum import Enum as PyEnum
from datetime import datetime, timezone

class GoalPriority(PyEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class GoalStatus(PyEnum):
    ACTIVE = "active"
    ACHIEVED = "achieved"
    ABANDONED = "abandoned"

class PatternType(PyEnum):
    RECURRING = "recurring"
    SEASONAL = "seasonal"
    ANOMALY = "anomaly"

class NotificationType(PyEnum):
    OVERSPENDING = "overspending"
    GOAL_PROGRESS = "goal_progress"
    SPENDING_ANOMALY = "spending_anomaly"
    SAVINGS_OPPORTUNITY = "savings_opportunity"
    MONTHLY_SUMMARY = "monthly_summary"
    HEALTH_SCORE = "health_score"

class NotificationPriority(PyEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class SavingsGoal(AuditMixin, Base):
    __tablename__ = "savings_goals"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    target_amount = Column(Numeric(10, 2), nullable=False)
    current_amount = Column(Numeric(10, 2), nullable=False, default=0.00)
    deadline = Column(Date, nullable=True)
    priority = Column(
        Enum(GoalPriority, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=GoalPriority.MEDIUM,
    )
    category = Column(String(50), nullable=True)  # e.g., "emergency_fund", "vacation", "education"
    status = Column(
        Enum(GoalStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=GoalStatus.ACTIVE,
    )
    is_ai_recommended = Column(Boolean, default=False, nullable=False)
    description = Column(Text, nullable=True)
    
    customer = relationship("User", foreign_keys=[customer_id])

class FinancialHealthScore(AuditMixin, Base):
    __tablename__ = "financial_health_scores"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    score = Column(Integer, nullable=False)  # 0-100
    score_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    factors_breakdown = Column(JSON, nullable=False)  # {"expense_ratio": 75, "savings_rate": 80, ...}
    recommendations = Column(JSON, nullable=True)  # List of recommendation objects
    
    customer = relationship("User", foreign_keys=[customer_id])

class SpendingPattern(AuditMixin, Base):
    __tablename__ = "spending_patterns"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    pattern_type = Column(
        Enum(PatternType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    description = Column(Text, nullable=False)
    amount = Column(Numeric(10, 2), nullable=True)
    frequency = Column(String(50), nullable=True)  # e.g., "weekly", "monthly", "quarterly"
    detected_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_occurrence = Column(Date, nullable=True)
    pattern_metadata = Column(JSON, nullable=True)  # Additional pattern-specific data (renamed from metadata)
    
    customer = relationship("User", foreign_keys=[customer_id])

class UserNotification(AuditMixin, Base):
    __tablename__ = "user_notifications"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    notification_type = Column(
        Enum(NotificationType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    priority = Column(
        Enum(NotificationPriority, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=NotificationPriority.MEDIUM,
    )
    is_read = Column(Boolean, default=False, nullable=False)
    related_entity_id = Column(Integer, nullable=True)  # ID of related goal, pattern, etc.
    related_entity_type = Column(String(50), nullable=True)  # e.g., "savings_goal", "spending_pattern"
    
    user = relationship("User", foreign_keys=[user_id])


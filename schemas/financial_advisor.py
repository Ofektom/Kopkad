from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, List, Any
from decimal import Decimal
from datetime import date, datetime
from models.financial_advisor import GoalPriority, GoalStatus, PatternType, NotificationType, NotificationPriority

# Savings Goal Schemas
class SavingsGoalCreate(BaseModel):
    name: str = Field(..., max_length=100)
    target_amount: Decimal = Field(..., gt=0)
    deadline: Optional[date] = None
    priority: GoalPriority = GoalPriority.MEDIUM
    category: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None

class SavingsGoalUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    target_amount: Optional[Decimal] = Field(None, gt=0)
    current_amount: Optional[Decimal] = Field(None, ge=0)
    deadline: Optional[date] = None
    priority: Optional[GoalPriority] = None
    category: Optional[str] = Field(None, max_length=50)
    status: Optional[GoalStatus] = None
    description: Optional[str] = None

class SavingsGoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    customer_id: int
    name: str
    target_amount: Decimal
    current_amount: Decimal
    deadline: Optional[date]
    priority: GoalPriority
    category: Optional[str]
    status: GoalStatus
    is_ai_recommended: bool
    description: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    progress_percentage: Optional[float] = None
    days_remaining: Optional[int] = None

class GoalAllocationRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)

# Financial Health Score Schemas
class FinancialHealthScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    customer_id: int
    score: int
    score_date: datetime
    factors_breakdown: Dict[str, Any]
    recommendations: Optional[List[Dict[str, Any]]]
    created_at: Optional[datetime]

class HealthScoreHistory(BaseModel):
    scores: List[FinancialHealthScoreResponse]
    average_score: float
    trend: str  # "improving", "declining", "stable"

# Spending Pattern Schemas
class SpendingPatternResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    customer_id: int
    pattern_type: PatternType
    description: str
    amount: Optional[Decimal]
    frequency: Optional[str]
    detected_at: datetime
    last_occurrence: Optional[date]
    pattern_metadata: Optional[Dict[str, Any]]

class RecurringExpenseResponse(BaseModel):
    description: str
    amount: Decimal
    frequency: str
    last_occurrence: date
    next_expected: Optional[date]
    total_yearly_cost: Decimal

class AnomalyResponse(BaseModel):
    description: str
    amount: Decimal
    date: date
    deviation_percentage: float
    severity: str  # "low", "medium", "high"

# Recommendation Schemas
class RecommendationResponse(BaseModel):
    title: str
    description: str
    category: str
    potential_savings: Optional[Decimal]
    priority: str
    action_items: List[str]

class PersonalizedAdviceResponse(BaseModel):
    total_income: Decimal
    total_expenses: Decimal
    net_balance: Decimal
    savings_contribution: Decimal
    financial_health_score: int
    advice_summary: str
    recommendations: List[RecommendationResponse]
    spending_insights: List[str]

# Improvement Roadmap Schemas
class RoadmapStepResponse(BaseModel):
    step_number: int
    title: str
    description: str
    estimated_impact: str  # e.g., "+5 points", "+10% savings"
    timeframe: str  # e.g., "1 week", "1 month"
    difficulty: str  # "easy", "medium", "hard"

class ImprovementRoadmapResponse(BaseModel):
    current_score: int
    target_score: int
    estimated_weeks: int
    steps: List[RoadmapStepResponse]
    key_focus_areas: List[str]

# Notification Schemas
class NotificationCreate(BaseModel):
    notification_type: NotificationType
    title: str = Field(..., max_length=200)
    message: str
    priority: NotificationPriority = NotificationPriority.MEDIUM
    related_entity_id: Optional[int] = None
    related_entity_type: Optional[str] = Field(None, max_length=50)

class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    notification_type: NotificationType
    title: str
    message: str
    priority: NotificationPriority
    is_read: bool
    related_entity_id: Optional[int]
    related_entity_type: Optional[str]
    created_at: Optional[datetime]

class NotificationMarkReadRequest(BaseModel):
    is_read: bool = True

# Savings Opportunity Schemas
class SavingsOpportunityResponse(BaseModel):
    category: str
    current_spending: Decimal
    recommended_spending: Decimal
    potential_savings: Decimal
    confidence: float  # 0.0 to 1.0
    reasoning: str

class SavingsOpportunitiesResponse(BaseModel):
    total_potential_savings: Decimal
    opportunities: List[SavingsOpportunityResponse]
    monthly_savings_goal_suggestion: Decimal


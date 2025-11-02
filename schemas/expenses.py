from pydantic import BaseModel, validator
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict
from models.expenses import IncomeType, ExpenseCategory, CardStatus

class ExpenseCardCreate(BaseModel):
    name: str
    income_type: IncomeType
    business_id: Optional[int] = None  # Optional - backend will use active_business_id if not provided
    savings_id: Optional[int] = None
    initial_income: Optional[Decimal] = None
    income_details: Optional[str] = None

    @validator("income_details")
    def validate_income_details(cls, v, values):
        income_type = values.get("income_type")
        if income_type == IncomeType.OTHER and not v:
            raise ValueError("income_details is required when income_type is OTHER")
        if income_type != IncomeType.OTHER and v:
            raise ValueError("income_details should only be provided when income_type is OTHER")
        return v

    class Config:
        arbitrary_types_allowed = True

class ExpenseCardResponse(BaseModel):
    id: int
    customer_id: int
    business_id: int
    name: str
    income_type: IncomeType
    income_amount: Decimal
    balance: Decimal
    savings_id: Optional[int]
    income_details: Optional[str]
    status: CardStatus
    is_plan: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        arbitrary_types_allowed = True

class ExpenseCreate(BaseModel):
    category: ExpenseCategory
    description: Optional[str] = None
    amount: Decimal
    date: date

    class Config:
        arbitrary_types_allowed = True

class ExpenseResponse(BaseModel):
    id: int
    expense_card_id: int
    category: ExpenseCategory
    description: Optional[str]
    amount: Decimal
    date: date
    is_planned: bool
    is_completed: bool
    planned_amount: Optional[Decimal]
    purpose: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        arbitrary_types_allowed = True

class TopUpRequest(BaseModel):
    amount: Decimal

    class Config:
        arbitrary_types_allowed = True

class ExpenseStatsResponse(BaseModel):
    total_income: Decimal
    total_expenses: Decimal
    net_balance: Decimal
    expenses_by_category: Dict[str, Decimal]
    savings_contribution: Decimal
    savings_payout: Decimal

    class Config:
        arbitrary_types_allowed = True

class FinancialAdviceResponse(BaseModel):
    total_income: Decimal
    total_expenses: Decimal
    net_balance: Decimal
    expenses_by_category: Dict[str, Decimal]
    savings_contribution: Decimal
    savings_payout: Decimal
    projected_expenses: Decimal
    spending_trend_slope: float
    savings_ratio: float
    advice: str

    class Config:
        arbitrary_types_allowed = True

class FinancialAnalyticsResponse(BaseModel):
    total_income: Decimal
    total_expenses: Decimal
    net_balance: Decimal
    savings_contribution: Decimal
    savings_payout: Decimal
    savings_ratio: float
    expense_distribution: Dict[str, float]
    transaction_counts: Dict[str, int]
    avg_income: Decimal
    avg_expense: Decimal
    spending_trend_slope: float
    expense_volatility: float
    top_expense_category: Optional[str]
    top_expense_percentage: float

    class Config:
        arbitrary_types_allowed = True

# New schemas for expense planner
class PlannedExpense(BaseModel):
    category: ExpenseCategory
    amount: Decimal
    purpose: str

    class Config:
        arbitrary_types_allowed = True

class ExpensePlannerRequest(BaseModel):
    capital: Decimal
    planned_expenses: List[PlannedExpense]

    class Config:
        arbitrary_types_allowed = True

class ExpensePlannerResponse(BaseModel):
    total_planned: Decimal
    capital: Decimal
    remaining_balance: Decimal
    is_sufficient: bool
    ai_advice: str
    category_breakdown: Dict[str, Decimal]
    recommendations: List[str]

    class Config:
        arbitrary_types_allowed = True

class EligibleSavingsResponse(BaseModel):
    id: int
    tracking_number: str
    savings_type: str
    total_amount: Decimal
    commission: Decimal
    net_payout: Decimal
    start_date: date
    completion_date: Optional[date]
    already_linked: bool

    class Config:
        arbitrary_types_allowed = True

class ExpenseUpdate(BaseModel):
    category: Optional[ExpenseCategory] = None
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    date: Optional[date] = None

    class Config:
        arbitrary_types_allowed = True

# New schemas for enhanced planner workflow

class CreatePlannerCardRequest(BaseModel):
    """Create a planner/draft expense card with planned expenses"""
    name: str
    capital: Decimal
    planned_expenses: List[PlannedExpense]

    class Config:
        arbitrary_types_allowed = True

class PlannerCardResponse(BaseModel):
    """Response after creating planner card with AI analysis"""
    card: ExpenseCardResponse
    total_planned: Decimal
    remaining_balance: Decimal
    is_sufficient: bool
    ai_advice: str
    category_breakdown: Dict[str, Decimal]
    recommendations: List[str]

    class Config:
        arbitrary_types_allowed = True

class ActivatePlannerRequest(BaseModel):
    """Request to activate a draft planner card"""
    confirm: bool = True  # Safety check

    class Config:
        arbitrary_types_allowed = True

class CompletePlannedItemRequest(BaseModel):
    """Mark a planned expense as completed (checklist)"""
    actual_amount: Optional[Decimal] = None  # If different from planned

    class Config:
        arbitrary_types_allowed = True

class PlannerProgressResponse(BaseModel):
    """Progress tracking for a planner card"""
    card_id: int
    card_name: str
    status: CardStatus
    planned_total: Decimal
    actual_total: Decimal
    remaining_balance: Decimal
    completed_items: int
    total_items: int
    completion_percentage: float
    variance_by_category: Dict[str, Dict[str, Decimal]]  # {category: {planned, actual, variance}}
    items: List[Dict]  # List of planned items with status

    class Config:
        arbitrary_types_allowed = True
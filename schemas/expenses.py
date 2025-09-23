from pydantic import BaseModel, validator
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict
from models.expenses import IncomeType, ExpenseCategory

class ExpenseCardCreate(BaseModel):
    name: str
    income_type: IncomeType
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
    name: str
    income_type: IncomeType
    income_amount: Decimal
    balance: Decimal
    savings_id: Optional[int]
    income_details: Optional[str]
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
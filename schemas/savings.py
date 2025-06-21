from pydantic import BaseModel
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict


class SavingsCreateDaily(BaseModel):
    business_id: int
    daily_amount: Decimal
    duration_months: int
    start_date: date
    commission_days: int = 30
    customer_id: Optional[int] = None


class SavingsCreateTarget(BaseModel):
    business_id: Optional[int] = None
    target_amount: Decimal
    start_date: date
    end_date: date
    commission_days: Optional[int] = 30
    customer_id: Optional[int] = None


class SavingsReinitiateDaily(BaseModel):
    tracking_number: str
    daily_amount: Decimal
    duration_months: int
    start_date: date
    commission_days: int = 30


class SavingsReinitiateTarget(BaseModel):
    tracking_number: str
    target_amount: Decimal
    start_date: date
    end_date: date
    commission_days: int = 30


class SavingsUpdate(BaseModel):
    daily_amount: Optional[Decimal] = None
    target_amount: Optional[Decimal] = None
    duration_months: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    commission_days: Optional[int] = None


class SavingsResponse(BaseModel):
    id: int
    customer_id: int
    business_id: int
    tracking_number: str
    savings_type: str
    daily_amount: Decimal
    duration_months: int  # Updated to months
    start_date: date
    target_amount: Optional[Decimal]
    end_date: Optional[date]
    commission_days: int
    created_at: datetime
    updated_at: Optional[datetime]


class SavingsMarkingRequest(BaseModel):
    marked_date: date
    payment_method: str


class SavingsTargetCalculationResponse(BaseModel):  # NEW
    daily_amount: Decimal
    duration_months: int


class SavingsMarkingResponse(BaseModel):
    tracking_number: str
    savings_schedule: Dict[date, str]
    total_amount: Decimal
    authorization_url: Optional[str] = None
    payment_reference: Optional[str] = None
    virtual_account: Optional[dict] = None


class BulkMarkSavingsRequest(BaseModel):
    markings: List[SavingsMarkingRequest]  # Updated to use SavingsMarkingRequest
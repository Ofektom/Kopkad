from pydantic import BaseModel, Field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict
from models.savings import SavingsType, PaymentMethod, MarkingStatus

class SavingsCreateDaily(BaseModel):
    customer_id: Optional[int] = None
    business_id: int
    unit_id: int
    daily_amount: Decimal
    duration_months: int
    start_date: date
    commission_days: int = 30
    commission_amount: Optional[Decimal] = None

    class Config:
        arbitrary_types_allowed = True

class SavingsCreateTarget(BaseModel):
    customer_id: Optional[int] = None
    business_id: int
    unit_id: int
    target_amount: Decimal
    start_date: date
    end_date: date
    commission_days: int = 30
    commission_amount: Optional[Decimal] = None

    class Config:
        arbitrary_types_allowed = True

class SavingsExtend(BaseModel):
    tracking_number: str
    additional_months: int

    class Config:
        arbitrary_types_allowed = True

class SavingsUpdate(BaseModel):
    business_id: Optional[int] = None
    unit_id: Optional[int] = None
    daily_amount: Optional[Decimal] = None
    duration_months: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    target_amount: Optional[Decimal] = None
    commission_days: Optional[int] = None
    commission_amount: Optional[Decimal] = None

    class Config:
        arbitrary_types_allowed = True

class SavingsResponse(BaseModel):
    id: int
    customer_id: int
    business_id: int
    unit_id: Optional[int]
    tracking_number: str
    savings_type: SavingsType
    daily_amount: Decimal
    duration_months: int
    start_date: date
    target_amount: Optional[Decimal]
    end_date: Optional[date]
    commission_days: int
    commission_amount: Decimal
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        arbitrary_types_allowed = True

class SavingsMarkingRequest(BaseModel):
    marked_date: date
    payment_method: PaymentMethod
    unit_id: Optional[int] = None
    idempotency_key: Optional[str] = Field(None, description="Unique key to prevent duplicate payments")

    class Config:
        arbitrary_types_allowed = True

class BulkSavingsMarkingRequest(BaseModel):
    tracking_number: str
    marked_date: date
    unit_id: Optional[int] = None

    class Config:
        arbitrary_types_allowed = True

class BulkMarkSavingsRequest(BaseModel):
    payment_method: PaymentMethod
    markings: List[BulkSavingsMarkingRequest]
    idempotency_key: Optional[str] = Field(None, description="Unique key to prevent duplicate payments")

    class Config:
        arbitrary_types_allowed = True

class SavingsTargetCalculationResponse(BaseModel):
    daily_amount: Decimal
    duration_months: int

    class Config:
        arbitrary_types_allowed = True

class SavingsMarkingResponse(BaseModel):
    tracking_number: str
    unit_id: Optional[int]
    savings_schedule: Dict[str, str]
    total_amount: Decimal
    authorization_url: Optional[str] = None
    payment_reference: Optional[str] = None
    virtual_account: Optional[dict] = None

    class Config:
        arbitrary_types_allowed = True

class SavingsMetricsResponse(BaseModel):
    tracking_number: str
    savings_account_id: int
    total_amount: Decimal
    amount_marked: Decimal
    days_remaining: int
    can_extend: bool
    total_commission: Decimal
    marking_status: MarkingStatus
    payment_request_status: Optional[str]  # pending, approved, rejected, cancelled, or None

    class Config:
        arbitrary_types_allowed = True
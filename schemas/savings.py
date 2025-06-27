from pydantic import BaseModel
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict
from models.savings import SavingsType, SavingsStatus, PaymentMethod

class SavingsCreateDaily(BaseModel):
    customer_id: Optional[int] = None
    business_id: int
    unit_id: int  # Added unit_id
    daily_amount: Decimal
    duration_months: int
    start_date: date
    commission_days: int = 30

    class Config:
        arbitrary_types_allowed = True

class SavingsCreateTarget(BaseModel):
    customer_id: Optional[int] = None
    business_id: int  # Made business_id required
    unit_id: int  # Added unit_id
    target_amount: Decimal
    start_date: date
    end_date: date
    commission_days: int = 30

    class Config:
        arbitrary_types_allowed = True

class SavingsReinitiateDaily(BaseModel):
    tracking_number: str
    business_id: int  # Added business_id
    unit_id: int  # Added unit_id
    daily_amount: Decimal
    duration_months: int
    start_date: date
    commission_days: int = 30

    class Config:
        arbitrary_types_allowed = True

class SavingsReinitiateTarget(BaseModel):
    tracking_number: str
    business_id: int  # Added business_id
    unit_id: int  # Added unit_id
    target_amount: Decimal
    start_date: date
    end_date: date
    commission_days: int = 30

    class Config:
        arbitrary_types_allowed = True

class SavingsUpdate(BaseModel):
    business_id: Optional[int] = None  # Added business_id
    unit_id: Optional[int] = None  # Added unit_id
    daily_amount: Optional[Decimal] = None
    duration_months: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    target_amount: Optional[Decimal] = None
    commission_days: Optional[int] = None

    class Config:
        arbitrary_types_allowed = True

class SavingsResponse(BaseModel):
    id: int
    customer_id: int
    business_id: int
    unit_id: Optional[int]  # Added unit_id
    tracking_number: str
    savings_type: SavingsType
    daily_amount: Decimal
    duration_months: int
    start_date: date
    target_amount: Optional[Decimal]
    end_date: Optional[date]
    commission_days: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        arbitrary_types_allowed = True

class SavingsMarkingRequest(BaseModel):
    marked_date: date
    payment_method: PaymentMethod
    unit_id: Optional[int] = None  # Added unit_id

    class Config:
        arbitrary_types_allowed = True

# New schema for bulk marking entries
class BulkSavingsMarkingRequest(BaseModel):
    tracking_number: str
    marked_date: date
    unit_id: Optional[int] = None

    class Config:
        arbitrary_types_allowed = True

class BulkMarkSavingsRequest(BaseModel):
    payment_method: PaymentMethod
    markings: List[BulkSavingsMarkingRequest]

    class Config:
        arbitrary_types_allowed = True

class SavingsTargetCalculationResponse(BaseModel):
    daily_amount: Decimal
    duration_months: int

    class Config:
        arbitrary_types_allowed = True

class SavingsMarkingResponse(BaseModel):
    tracking_number: str
    savings_schedule: Dict[str, str]
    total_amount: Decimal
    authorization_url: Optional[str] = None
    payment_reference: Optional[str] = None
    virtual_account: Optional[dict] = None

    class Config:
        arbitrary_types_allowed = True
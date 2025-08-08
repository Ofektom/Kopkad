from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from models.payments import PaymentStatus

class AccountDetailsCreate(BaseModel):
    payment_account_id: int
    account_name: str
    account_number: str
    bank_name: str
    bank_code: Optional[str] = None
    account_type: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

class AccountDetailsResponse(BaseModel):
    id: int
    payment_account_id: int
    account_name: str
    account_number: str
    bank_name: str
    bank_code: Optional[str]
    account_type: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        arbitrary_types_allowed = True

class PaymentAccountCreate(BaseModel):
    savings_account_id: int
    account_details: List[AccountDetailsCreate]

    class Config:
        arbitrary_types_allowed = True

class PaymentAccountUpdate(BaseModel):
    savings_account_id: Optional[int] = None
    account_details: Optional[List[AccountDetailsCreate]] = None

    class Config:
        arbitrary_types_allowed = True

class PaymentAccountResponse(BaseModel):
    id: int
    customer_id: int
    savings_account_id: int
    amount: Decimal
    status: PaymentStatus
    payment_reference: Optional[str]
    account_details: List[AccountDetailsResponse]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        arbitrary_types_allowed = True

class PaymentInitiateResponse(BaseModel):
    payment_account_id: int
    amount: Decimal
    payment_reference: str
    status: PaymentStatus
    bank_details: dict

    class Config:
        arbitrary_types_allowed = True
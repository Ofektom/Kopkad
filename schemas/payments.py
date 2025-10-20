from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

class AccountDetailsCreate(BaseModel):
    account_name: str
    account_number: str
    bank_name: str
    bank_code: Optional[str] = None
    account_type: Optional[str] = None

class AccountDetailsUpdate(BaseModel):
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    bank_name: Optional[str] = None
    bank_code: Optional[str] = None
    account_type: Optional[str] = None

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
        from_attributes = True

class PaymentAccountCreate(BaseModel):
    account_details: List[AccountDetailsCreate]

class PaymentAccountResponse(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    account_details: List[AccountDetailsResponse]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

class PaymentAccountUpdate(BaseModel):
    account_details: List[AccountDetailsCreate]

class PaymentRequestCreate(BaseModel):
    account_details_id: int
    savings_account_id: int

class PaymentRequestResponse(BaseModel):
    id: int
    payment_account_id: int
    account_details_id: int
    savings_account_id: int
    amount: Decimal
    status: str
    request_date: datetime
    approval_date: Optional[datetime]
    rejection_reason: Optional[str]
    customer_name: str
    tracking_number: str

    class Config:
        from_attributes = True

class PaymentRequestReject(BaseModel):
    rejection_reason: str

class CommissionResponse(BaseModel):
    id: int
    savings_account_id: int
    agent_id: int
    amount: Decimal
    commission_date: datetime
    customer_id: int
    customer_name: str
    savings_type: str
    tracking_number: str

    class Config:
        from_attributes = True

class CustomerPaymentResponse(BaseModel):
    payment_request_id: int
    savings_account_id: int
    customer_id: int
    customer_name: str
    savings_type: str
    tracking_number: str
    total_amount: Decimal
    total_commission: Decimal
    payout_amount: Decimal
    status: str
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
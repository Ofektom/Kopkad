from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class UnitResponse(BaseModel):
    id: int
    business_id: int
    name: str
    location: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

class BusinessCreate(BaseModel):
    name: str
    address: Optional[str] = None
    business_type: str = "standard"  # Default to standard

class BusinessResponse(BaseModel):
    id: int
    name: str
    unique_code: str
    agent_id: int
    address: Optional[str] = None
    is_default: bool = False
    business_type: str = "standard"
    created_by: Optional[int] = None
    created_at: datetime
    units: List[UnitResponse] = []

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None

class UnitCreate(BaseModel):
    name: str
    location: Optional[str] = None

class UnitUpdate(BaseModel):
    name: str
    location: Optional[str] = None

class CustomerInvite(BaseModel):
    customer_phone: str = Field(..., pattern=r"^(0\d{9,10}|\+234\d{10})$")
    email: Optional[str] = None
    business_unique_code: str = Field(..., min_length=6, max_length=10)
    unit_id: Optional[int] = None

class CompleteRegistration(BaseModel):
    token: str

    pin: str = Field(..., min_length=5, max_length=5) # Assuming 5 digit pin
    full_name: str
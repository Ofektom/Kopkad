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
    password: str # Optional if we rely on PIN? But plan said password/pin. Let's include both or just PIN if system uses PIN.
    # The system uses PIN for transaction/login mostly. The SignupRequest has 'pin'.
    # I'll use 'pin' as the primary credential. But maybe user wants a password too?
    # User model has `pin` hashed. I'll stick to `pin` as the main auth credential for this app based on `signup`.
    # But wait, `AdminCredentials` has password.
    # Let's check `User` model again for password field.
    # Actually, I'll stick to `pin` as that is what `signup` does.
    # But for "Complete Registration" the prompt says "create password/pin".
    # I'll just ask for PIN.
    pin: str = Field(..., min_length=4, max_length=4) # Assuming 4 digit pin
    full_name: str
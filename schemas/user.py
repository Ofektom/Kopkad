from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict
from datetime import datetime
from schemas.business import BusinessResponse

class SignupRequest(BaseModel):
    phone_number: str
    pin: str = Field(..., pattern=r"^\d{5}$")
    role: str
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    identifier: Optional[str] = None
    business_code: Optional[str] = None
    address: Optional[str] = None

class UserResponse(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    phone_number: str
    email: Optional[EmailStr] = None
    role: str
    is_active: bool
    businesses: List[BusinessResponse] = []
    created_at: datetime
    access_token: Optional[str] = None
    next_action: Optional[str] = None
    address: Optional[str] = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

class LoginRequest(BaseModel):
    username: str
    pin: str = Field(..., pattern=r"^\d{5}$")

class ChangePasswordRequest(BaseModel):
    old_pin: str
    new_pin: str

class Response(BaseModel):
    status_code: int
    success: bool
    message: str
    data: Optional[Dict] = None
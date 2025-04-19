from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict
from datetime import datetime
from schemas.business import BusinessResponse


class SignupRequest(BaseModel):
    phone_number: str
    pin: str = Field(..., pattern=r"^\d{5}$")  # 5-digit numeric pin constraint
    role: str
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    identifier: Optional[str] = None
    business_code: Optional[str] = None
    location: Optional[str] = None

class UserResponse(BaseModel):
    full_name: str
    phone_number: str
    email: Optional[str]
    role: str
    businesses: List[BusinessResponse]
    created_at: datetime
    access_token: str
    next_action: str
    location: Optional[str]

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    pin: str = Field(..., pattern=r"^\d{5}$")


class Response(BaseModel):
    status_code: int
    success: bool
    message: str
    data: Optional[Dict] = None

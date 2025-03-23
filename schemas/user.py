from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict
from datetime import datetime

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
    email: Optional[EmailStr] = None
    role: str
    business_ids: List[int]
    created_at: datetime
    access_token: str
    next_action: str
    location: Optional[str] = None  # Added location to response

    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    username: str
    pin: str = Field(..., pattern=r"^\d{5}$")  # 5-digit numeric pin constraint

class Response(BaseModel):
    status_code: int
    success: bool
    message: str
    data: Optional[Dict] = None
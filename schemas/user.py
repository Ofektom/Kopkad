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
    active_business_id: Optional[int] = None
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

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_pin: str = Field(..., pattern=r"^\d{5}$")

class Response(BaseModel):
    status_code: int
    success: bool
    message: str
    data: Optional[Dict] = None


class AdminUpdateRequest(BaseModel):
    """Payload for updating admin profile details."""
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None


class UserUpdateRequest(BaseModel):
    """
    Schema for partial self-update of the current user's profile (PATCH /auth/me).
    Only fields that exist on the User model are allowed.
    """
    full_name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=100,
        description="User's full name"
    )
    email: Optional[EmailStr] = Field(
        None,
        description="Email address (must be unique)"
    )
    phone_number: Optional[str] = Field(
        None,
        pattern=r"^\+?\d{10,14}$",
        description="Phone number (will be normalized to Nigerian format)"
    )

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "full_name": "John Doe Updated",
                "email": "john.doe.updated@example.com",
                "phone_number": "08012345678"
            }
        }
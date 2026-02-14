from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal
from models.savings_group import GroupFrequency
from models.savings import PaymentMethod


class SavingsGroupBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    contribution_amount: Decimal = Field(..., gt=0)
    frequency: GroupFrequency = GroupFrequency.MONTHLY
    start_date: date
    end_date: Optional[date] = None


class SavingsGroupCreate(SavingsGroupBase):
    member_ids: Optional[List[int]] = Field(default_factory=list)
    duration_months: Optional[int] = Field(None, ge=1)


class SavingsGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    contribution_amount: Optional[Decimal] = Field(None, gt=0)
    frequency: Optional[GroupFrequency] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None


class SavingsGroupResponse(SavingsGroupBase):
    id: int
    business_id: int
    created_by_id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    user_relationship: Optional[dict] = Field(None, description="Current user's relationship with the group (if member)")

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: str,
            date: lambda v: v.isoformat() if v else None,
            datetime: lambda v: v.isoformat() if v else None,
        }


class CreateSavingsGroupResponse(BaseModel):
    """Response model specifically for group creation"""
    message: str
    group: SavingsGroupResponse
    created_members_count: int


class PaginatedSavingsGroupsResponse(BaseModel):
    groups: List[SavingsGroupResponse]
    total_count: int
    limit: int
    offset: int
    message: Optional[str] = None


class AddGroupMemberRequest(BaseModel):
    user_id: int
    start_date: Optional[date] = None


class GroupMemberResponse(BaseModel):
    user_id: int
    savings_account_id: int
    tracking_number: str
    joined_at: datetime
    status: str = "active"

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

class GroupMarkingItem(BaseModel):
    savings_account_id: int
    date: date               # renamed from 'marked_date' to match your toggle style

class SavingsGroupMarkingPaystackInit(BaseModel):
    payment_method: PaymentMethod
    markings: List[GroupMarkingItem]

    class Config:
        arbitrary_types_allowed = True   # usually needed when using enums from SQLAlchemy

class SavingsGroupMarkingVerifyResponse(BaseModel):
    status: str                  # "success" / "pending" / etc.
    message: str
    reference: str
    paid_amount: Optional[float] = None

    class Config:
        arbitrary_types_allowed = True
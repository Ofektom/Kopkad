from pydantic import BaseModel, Field, validator
from datetime import date, datetime
from typing import Optional, List
from models.savings_group import GroupFrequency
from enum import Enum

class SavingsGroupBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    contribution_amount: float = Field(..., gt=0)
    frequency: GroupFrequency = GroupFrequency.MONTHLY
    start_date: date
    end_date: Optional[date] = None

class SavingsGroupCreate(SavingsGroupBase):
    member_ids: Optional[List[int]] = []
    duration_months: Optional[int] = None

class SavingsGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    contribution_amount: Optional[float] = Field(None, gt=0)
    frequency: Optional[GroupFrequency] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None

class SavingsGroupResponse(SavingsGroupBase):
    id: int
    business_id: int
    created_by_id: int
    is_active: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class AddGroupMemberRequest(BaseModel):
    user_id: int # The member user ID
    start_date: Optional[date] = None # Optional override, defaults to Group start date or today?

class GroupMemberResponse(BaseModel):
    user_id: int
    savings_account_id: int
    joined_at: datetime
    status: str 

    class Config:
        from_attributes = True

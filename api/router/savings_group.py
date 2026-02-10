from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database.postgres_optimized import get_db
from models.user import Role
from utils.auth import get_current_user
from schemas.savings_group import (
    SavingsGroupCreate, 
    SavingsGroupUpdate, 
    SavingsGroupResponse, 
    AddGroupMemberRequest, 
    GroupMemberResponse
)
from service.savings_group import SavingsGroupService
from utils.response import success_response, error_response

router = APIRouter(prefix="/savings-groups", tags=["Savings Groups"])

def get_service(db: Session = Depends(get_db)) -> SavingsGroupService:
    return SavingsGroupService(db)

@router.post("/", response_model=SavingsGroupResponse)
async def create_group(
    data: SavingsGroupCreate,
    current_user: dict = Depends(get_current_user),
    service: SavingsGroupService = Depends(get_service)
):
    """Create a new savings group (Business Admin only)."""
    # Allow business-level actors: central Admins and on-business Agents
    if current_user["role"] not in [Role.ADMIN, Role.SUPER_ADMIN, Role.AGENT]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Only Admins or Agents assigned to a business can create groups"
        )
        
    try:
        group = service.create_group(data, current_user["user_id"])
        return group
    except HTTPException as e:
        raise e
    except Exception as e:
        # Log error
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[SavingsGroupResponse])
async def list_groups(
    current_user: dict = Depends(get_current_user),
    service: SavingsGroupService = Depends(get_service)
):
    """List all savings groups for the current user's business."""
    # If Admin, list business groups. If Member, maybe list groups they are in?
    # Logic in service.list_groups currently assumes Admin. 
    # Let's restrict to Admin for now or update service.
    
    # Permission check or logic delegation
    return service.list_groups(current_user["user_id"])

@router.get("/{group_id}", response_model=SavingsGroupResponse)
async def get_group(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    service: SavingsGroupService = Depends(get_service)
):
    """Get group details."""
    role = Role(current_user["role"]) if isinstance(current_user["role"], str) else current_user["role"]
    return service.get_group(group_id, current_user["user_id"], role)

@router.post("/{group_id}/members", response_model=dict)
async def add_member(
    group_id: int,
    request: AddGroupMemberRequest,
    current_user: dict = Depends(get_current_user),
    service: SavingsGroupService = Depends(get_service)
):
    """Add a member to the savings group (Business Admin only)."""
    # Allow both Admins and Agents to add members for their business' groups
    if current_user["role"] not in [Role.ADMIN, Role.SUPER_ADMIN, Role.AGENT]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admins or Agents assigned to a business can add members"
        )
        
    account = service.add_member(group_id, request, current_user["user_id"])
    return {
        "message": "Member added successfully",
        "savings_account_id": account.id,
        "tracking_number": account.tracking_number
    }

@router.get("/{group_id}/members", response_model=List[dict]) # Schemas update maybe needed for direct Account return
async def get_members(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    service: SavingsGroupService = Depends(get_service)
):
    """List members of a group."""
    members = service.get_group_members(group_id)
    # Transform to simple response
    result = []
    for m in members:
        result.append({
            "id": m.id,
            "customer_id": m.customer_id,
            "tracking_number": m.tracking_number,
            "joined_at": m.created_at,
            # Fetch user name? Maybe handled by frontend or need join.
            # For now returns basic info.
        })
    return result

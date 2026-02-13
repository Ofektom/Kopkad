from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from models.savings_group import SavingsGroup, GroupFrequency
from models.savings import SavingsAccount, SavingsType
from models.user import User
from models.business import Business, BusinessType

from schemas.savings_group import (
    SavingsGroupCreate,
    AddGroupMemberRequest,
    SavingsGroupResponse,
    CreateSavingsGroupResponse,
)

from store.repositories.savings_group import SavingsGroupRepository
from store.repositories.savings import SavingsRepository
from store.repositories.business import BusinessRepository
from store.repositories.user import UserRepository

from datetime import date
from dateutil.relativedelta import relativedelta
import uuid
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def _resolve_repo(repo, repo_cls, db: Session):
    return repo if repo is not None else repo_cls(db)


async def create_group(
    request: SavingsGroupCreate,
    current_user: dict,
    db: Session,
    *,
    group_repo: Optional[SavingsGroupRepository] = None,
    business_repo: Optional[BusinessRepository] = None,
    user_repo: Optional[UserRepository] = None,
    savings_repo: Optional[SavingsRepository] = None,
) -> CreateSavingsGroupResponse:
    logger.info("[SERVICE] create_group called")
    logger.info(f"[SERVICE] Received request data: {request.model_dump_json(indent=2)}")
    logger.info(f"[SERVICE] Current user: role={current_user.get('role')}, id={current_user.get('user_id')}")

    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)

    user_id = current_user["user_id"]
    role = current_user["role"]

    if role not in ["admin", "super_admin", "agent"]:
        logger.warning(f"[SERVICE] Unauthorized role attempt: {role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins, super admins or agents can create savings groups"
        )

    business = business_repo.get_by_admin_id(user_id) or business_repo.get_by_agent_id(user_id)
    if not business:
        logger.warning(f"[SERVICE] No business found for user {user_id}")
        raise HTTPException(status_code=400, detail="User is not associated with any business")

    if business.business_type != BusinessType.COOPERATIVE:
        logger.warning(f"[SERVICE] Business type is not COOPERATIVE: {business.business_type}")
        raise HTTPException(status_code=400, detail="Only cooperative businesses can create savings groups")

    member_ids = request.member_ids or []
    duration_months = request.duration_months

    group_data = request.model_dump(exclude={"member_ids", "duration_months"})
    group_data["business_id"] = business.id
    group_data["created_by_id"] = user_id

    if duration_months and "end_date" not in group_data:
        group_data["end_date"] = group_data["start_date"] + relativedelta(months=duration_months)

    logger.info(f"[SERVICE] Creating group with data: {group_data}")

    group = group_repo.create_group(group_data)
    logger.info(f"[SERVICE] Group created - ID: {group.id}, frequency: {group.frequency.value}")

    created_accounts = []
    for member_id in member_ids:
        try:
            req = AddGroupMemberRequest(user_id=member_id, start_date=group.start_date)
            logger.info(f"[SERVICE] Attempting to add member {member_id} to group {group.id}")
            account = await add_member_to_group(
                group_id=group.id,
                request=req,
                current_user=current_user,
                db=db,
                group_repo=group_repo,
                business_repo=business_repo,
                user_repo=user_repo,
                savings_repo=savings_repo,
            )
            created_accounts.append(account)
            logger.info(f"[SERVICE] Successfully added member {member_id}")
        except Exception as e:
            logger.warning(f"[SERVICE] Failed to add member {member_id} to group {group.id}: {str(e)}")
            continue

    response = CreateSavingsGroupResponse(
        message="Savings group created successfully",
        group=SavingsGroupResponse.from_orm(group),
        created_members_count=len(created_accounts)
    )
    logger.info(f"[SERVICE] Returning response: {response.model_dump_json(indent=2)}")

    return response


async def list_groups(
    current_user: dict,
    db: Session,
    name: Optional[str] = None,
    frequency: Optional[str] = None,
    is_active: Optional[bool] = True,
    search: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    *,
    group_repo: Optional[SavingsGroupRepository] = None,
    business_repo: Optional[BusinessRepository] = None,
) -> dict:
    logger.info(f"[SERVICE] list_groups called - params: limit={limit}, offset={offset}, frequency={frequency}")

    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)

    user_id = current_user["user_id"]
    role = current_user["role"]

    if role not in ["admin", "super_admin", "agent", "customer"]:
        logger.warning(f"[SERVICE] Unauthorized list attempt - role: {role}")
        raise HTTPException(status_code=403, detail="Not authorized to list savings groups")

    if role == "customer":
        # Customers can only see groups they are members of
        groups, total_count = group_repo.get_groups_for_member(
            member_id=user_id,
            limit=limit,
            skip=offset
        )
    else:
        # Admins/Agents see all groups for the business
        business = business_repo.get_by_admin_id(user_id) or business_repo.get_by_agent_id(user_id)
        if not business:
            logger.info(f"[SERVICE] No business found for user {user_id}")
            return {
                "groups": [],
                "total_count": 0,
                "limit": limit,
                "offset": offset,
                "message": "No business associated with user"
            }

        logger.info(f"[SERVICE] Listing groups for business {business.id}")

        groups, total_count = group_repo.get_groups_by_business(
            business_id=business.id,
            name=name,
            frequency=frequency,
            is_active=is_active,
            search=search,
            skip=offset,
            limit=limit,
        )

    response_data = []
    
    # Pre-fetch membership info if needed (optimization)
    # For now, we'll do it per group or assume get_groups_for_member attached it?
    # SQLAlchemy might not attach it easily unless we select it.
    # Let's check repository method or fetch manually.

    for group in groups:
        group_resp = SavingsGroupResponse.from_orm(group)
        
        # Determine relationship
        # If customer, they are definitely a member (based on get_groups_for_member)
        # We need their tracking number for this group.
        
        member_account = None
        # We can optimize this by fetching all memberships for this user and these groups
        # But for now, simple query:
        member_account = db.query(SavingsAccount).filter(
            SavingsAccount.group_id == group.id,
            SavingsAccount.customer_id == user_id
        ).first()

        if member_account:
            group_resp.user_relationship = {
                "tracking_number": member_account.tracking_number,
                "savings_account_id": member_account.id,
                "status": "active" # or check account status
            }
            
        response_data.append(group_resp)

    result = {
        "groups": response_data,
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "message": f"Retrieved {len(response_data)} of {total_count} savings groups"
    }
    logger.info(f"[SERVICE] Returning {len(response_data)} groups")
    return result


async def get_group(
    group_id: int,
    current_user: dict,
    db: Session,
    *,
    group_repo: Optional[SavingsGroupRepository] = None,
) -> SavingsGroupResponse:
    logger.info(f"[SERVICE] get_group - group_id: {group_id}")

    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)

    group = group_repo.get_active_group(group_id)
    if not group:
        logger.warning(f"[SERVICE] Group {group_id} not found or inactive")
        raise HTTPException(status_code=404, detail="Group not found or inactive")

    return SavingsGroupResponse.from_orm(group)


async def add_member_to_group(
    group_id: int,
    request: AddGroupMemberRequest,
    current_user: dict,
    db: Session,
    *,
    group_repo: Optional[SavingsGroupRepository] = None,
    business_repo: Optional[BusinessRepository] = None,
    user_repo: Optional[UserRepository] = None,
    savings_repo: Optional[SavingsRepository] = None,
) -> SavingsAccount:
    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)

    user_id = current_user["user_id"]
    role = current_user["role"]

    if role not in ["admin", "super_admin", "agent"]:
        raise HTTPException(status_code=403, detail="Not authorized to add members")

    group = group_repo.get_active_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found or inactive")

    business = business_repo.get_by_agent_id(user_id) or business_repo.get_by_admin_id(user_id)
    if not business or business.id != group.business_id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this group")

    user = user_repo.get_by_id(request.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Allow both CUSTOMER and AGENT roles to join savings groups
    allowed_roles = ["customer", "agent"]
    if user.role.lower() not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Only customers and agents can join savings groups (user role: {user.role})"
        )

    # Optional: ensure the user is associated with the same business (extra safety)
    # If your user_business table or business.agent_id already enforces this, skip
    user_businesses = business_repo.get_user_businesses_with_units(user.id)  # or your method
    if not any(b.id == group.business_id for b in user_businesses):
        raise HTTPException(status_code=403, detail="User does not belong to this cooperative")

    existing = db.query(SavingsAccount).filter(
        SavingsAccount.group_id == group_id,
        SavingsAccount.customer_id == request.user_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member of this group")

    tracking_number = str(uuid.uuid4())[:10].upper()

    start_date = request.start_date or group.start_date

    account = group_repo.add_member(
        group=group,
        user_id=request.user_id,
        tracking_number=tracking_number,
        start_date=start_date,
    )

    return account


async def get_group_members(
    group_id: int,
    current_user: dict,
    db: Session,
    *,
    group_repo: Optional[SavingsGroupRepository] = None,
) -> List[dict]:
    logger.info(f"[SERVICE] get_group_members - group_id: {group_id}")

    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)

    group = group_repo.get_active_group(group_id)
    if not group:
        logger.warning(f"[SERVICE] Group {group_id} not found or inactive")
        raise HTTPException(status_code=404, detail="Group not found or inactive")

    members = group_repo.get_members(group_id)

    result = [
        {
            "user_id": m.customer_id,
            "savings_account_id": m.id,
            "tracking_number": m.tracking_number,
            "joined_at": m.created_at,
            "status": "active"
        }
        for m in members
    ]

    logger.info(f"[SERVICE] Returning {len(result)} members for group {group_id}")
    return result


async def delete_group_service(
    group_id: int,
    current_user: dict,
    db: Session,
    *,
    group_repo: Optional[SavingsGroupRepository] = None,
    business_repo: Optional[BusinessRepository] = None,
) -> bool:
    logger.info(f"[SERVICE] delete_group_service called for group {group_id}")
    
    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)

    # Check authorization
    if current_user["role"] not in ["admin", "super_admin", "agent"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete groups")

    group = group_repo.get_active_group(group_id)
    if not group:
         raise HTTPException(status_code=404, detail="Group not found")

    # Verify ownership/business association
    if current_user["role"] == "agent":
         business = business_repo.get_by_agent_id(current_user["user_id"])
         if not business or business.id != group.business_id:
              raise HTTPException(status_code=403, detail="Group does not belong to your business")

    try:
        group_repo.delete_group(group_id)
        logger.info(f"[SERVICE] Group {group_id} deleted successfully")
        return True
    except ValueError as e:
        logger.warning(f"[SERVICE] Cannot delete group {group_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[SERVICE] Error deleting group {group_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during deletion")
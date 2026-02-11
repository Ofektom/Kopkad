from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from models.savings_group import SavingsGroup, GroupFrequency
from models.savings import SavingsAccount, SavingsType
from models.user import User
from models.business import Business, BusinessType
from schemas.savings_group import (
    SavingsGroupCreate,
    AddGroupMemberRequest,
    SavingsGroupResponse,
    PaginatedSavingsGroupsResponse,
)
from store.repositories.savings_group import (
    SavingsGroupRepository,
)

from store.repositories.savings import (
    SavingsRepository,
)

from store.repositories.business import (
    BusinessRepository,
)

from store.repositories.user import (
    UserRepository,
)
from datetime import date
from dateutil.relativedelta import relativedelta
import uuid
import logging

logger = logging.getLogger(__name__)

def _resolve_repo(repo, repo_cls, db: Session):
    return repo if repo is not None else repo_cls(db)


async def create_group(
    request: SavingsGroupCreate,
    current_user: dict,
    db: Session,
    *,
    group_repo: SavingsGroupRepository | None = None,
    business_repo: BusinessRepository | None = None,
    user_repo: UserRepository | None = None,
    savings_repo: SavingsRepository | None = None,
) -> Dict[str, Any]:
    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)

    user_id = current_user["user_id"]
    role = current_user["role"]

    if role not in ["admin", "super_admin", "agent"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins, super admins or agents can create savings groups"
        )

    business = business_repo.get_by_admin_id(user_id) or business_repo.get_by_agent_id(user_id)
    if not business:
        raise HTTPException(status_code=400, detail="User is not associated with any business")

    if business.business_type != BusinessType.COOPERATIVE:
        raise HTTPException(status_code=400, detail="Only cooperative businesses can create savings groups")

    member_ids = request.member_ids or []
    duration_months = request.duration_months

    group_data = request.model_dump(exclude={"member_ids", "duration_months"})
    group_data["business_id"] = business.id
    group_data["created_by_id"] = user_id

    if duration_months and not group_data.get("end_date"):
        group_data["end_date"] = group_data["start_date"] + relativedelta(months=duration_months)

    group = group_repo.create_group(group_data)

    created_accounts = []
    for member_id in member_ids:
        try:
            req = AddGroupMemberRequest(user_id=member_id, start_date=group.start_date)
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
        except Exception as e:
            logger.warning(f"Failed to auto-add member {member_id} to group {group.id}: {str(e)}")
            continue

    return {
        "message": "Savings group created successfully",
        "group": SavingsGroupResponse.from_orm(group).model_dump(),
        "created_members_count": len(created_accounts)
    }


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
    group_repo: SavingsGroupRepository | None = None,
    business_repo: BusinessRepository | None = None,
) -> Dict[str, Any]:
    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)

    user_id = current_user["user_id"]
    role = current_user["role"]

    if role not in ["admin", "super_admin", "agent"]:
        raise HTTPException(status_code=403, detail="Not authorized to list savings groups")

    business = business_repo.get_by_admin_id(user_id) or business_repo.get_by_agent_id(user_id)
    if not business:
        return {
            "groups": [],
            "total_count": 0,
            "limit": limit,
            "offset": offset,
            "message": "No business associated with user"
        }

    groups, total_count = group_repo.get_groups_by_business(
        business_id=business.id,
        name=name,
        frequency=frequency,
        is_active=is_active,
        search=search,
        skip=offset,
        limit=limit,
    )

    response_data = [
        SavingsGroupResponse.from_orm(group).model_dump()
        for group in groups
    ]

    return {
        "groups": response_data,
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "message": f"Retrieved {len(response_data)} of {total_count} savings groups"
    }


async def get_group(
    group_id: int,
    current_user: dict,
    db: Session,
    *,
    group_repo: SavingsGroupRepository | None = None,
) -> Dict[str, Any]:
    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)

    group = group_repo.get_active_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found or inactive")

    # Optional: add business authorization check here if needed

    return SavingsGroupResponse.from_orm(group).model_dump()


async def add_member_to_group(
    group_id: int,
    request: AddGroupMemberRequest,
    current_user: dict,
    db: Session,
    *,
    group_repo: SavingsGroupRepository | None = None,
    business_repo: BusinessRepository | None = None,
    user_repo: UserRepository | None = None,
    savings_repo: SavingsRepository | None = None,
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
    group_repo: SavingsGroupRepository | None = None,
) -> List[Dict[str, Any]]:
    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)

    group = group_repo.get_active_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found or inactive")

    # Optional: add authorization check

    members = group_repo.get_members(group_id)

    return [
        {
            "user_id": m.customer_id,
            "savings_account_id": m.id,
            "tracking_number": m.tracking_number,
            "joined_at": m.created_at,
            "status": "active"  # can be enhanced later with proper status logic
        }
        for m in members
    ]
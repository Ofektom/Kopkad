from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any
from dateutil.relativedelta import relativedelta

from datetime import date
import uuid
import logging

from models.savings_group import SavingsGroup, GroupFrequency
from models.savings import SavingsAccount, SavingsMarking
from models.user import User


from models.business import BusinessType

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


logger = logging.getLogger(__name__)


def _resolve_repo(repo, repo_cls, db: Session):
    return repo if repo is not None else repo_cls(db)


def _generate_group_grid_dates(
    start_date: date,
    frequency: GroupFrequency,
    limit: int,
    offset: int,
    end_date: Optional[date] = None
) -> List[date]:
    """
    Generate a list of dates based on frequency, handling pagination.
    """
    dates = []
    current_date = start_date
    
    # Skip to offset
    skipped = 0
    while skipped < offset:
        if end_date and current_date > end_date:
            break
            
        if frequency == GroupFrequency.WEEKLY:
            current_date += relativedelta(weeks=1)
        elif frequency == GroupFrequency.BI_WEEKLY:
            current_date += relativedelta(weeks=2)
        elif frequency == GroupFrequency.MONTHLY:
            current_date += relativedelta(months=1)
        elif frequency == GroupFrequency.QUARTERLY:
            current_date += relativedelta(months=3)
        skipped += 1

    # Collect dates up to limit
    collected = 0
    while collected < limit:
        if end_date and current_date > end_date:
            break
            
        dates.append(current_date)
        
        if frequency == GroupFrequency.WEEKLY:
            current_date += relativedelta(weeks=1)
        elif frequency == GroupFrequency.BI_WEEKLY:
            current_date += relativedelta(weeks=2)
        elif frequency == GroupFrequency.MONTHLY:
            current_date += relativedelta(months=1)
        elif frequency == GroupFrequency.QUARTERLY:
            current_date += relativedelta(months=3)
        collected += 1
        
    return dates


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

    if duration_months:
        group_data["end_date"] = group_data["start_date"] + relativedelta(months=duration_months)
    # If no duration_months, end_date remains null (open-ended)

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
    
    for group in groups:
        group_resp = SavingsGroupResponse.from_orm(group)
        
        member_account = None
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


async def get_group_grid_data(
    group_id: int,
    db: Session,
    date_page: int = 1,
    date_limit: int = 10
) -> Dict[str, Any]:
    """
    Fetch grid data: Members x Dates matrix.
    """
    # 1. Get Group
    group = db.query(SavingsGroup).filter(SavingsGroup.id == group_id).first()
    if not group:
        return None

    # 2. Determine Date Pagination
    offset = (date_page - 1) * date_limit
    
    # Ensure we have a reasonable end date for projection if not set
    # Default to 1 year from start if no end_date
    projection_end_date = group.end_date or (group.start_date + relativedelta(years=1))
    
    dates = _generate_group_grid_dates(
        start_date=group.start_date,
        frequency=group.frequency,
        limit=date_limit,
        offset=offset,
        end_date=projection_end_date
    )
    
    # Calculate total expected dates (approximate) to determine if there are more pages
    total_dates_approx = 0
    temp_date = group.start_date
    while temp_date <= projection_end_date:
        total_dates_approx += 1
        if group.frequency == GroupFrequency.WEEKLY:
            temp_date += relativedelta(weeks=1)
        elif group.frequency == GroupFrequency.BI_WEEKLY:
            temp_date += relativedelta(weeks=2)
        elif group.frequency == GroupFrequency.MONTHLY:
            temp_date += relativedelta(months=1)
        elif group.frequency == GroupFrequency.QUARTERLY:
            temp_date += relativedelta(months=3)
            
    has_next_page = (offset + len(dates)) < total_dates_approx

    # 3. Get Members (Savings Accounts linked to this group)
    savings_accounts = db.query(SavingsAccount).join(User, SavingsAccount.customer_id == User.id)\
        .filter(SavingsAccount.group_id == group_id)\
        .all()
        
    members_data = []
    markings_map = {} # {tracking_number: {date_str: status}}

    if dates:
        start_range = dates[0]
        end_range = dates[-1]

        # 4. Fetch Markings for all these accounts within the date range
        # We can do a single query if we collect all account IDs
        account_ids = [acc.id for acc in savings_accounts]
        
        if account_ids:
            markings = db.query(SavingsMarking)\
                .filter(
                    SavingsMarking.savings_account_id.in_(account_ids),
                    SavingsMarking.marked_date >= start_range,
                    SavingsMarking.marked_date <= end_range
                ).all()
                
            # Populate markings map
            for marking in markings:
                acc = next((a for a in savings_accounts if a.id == marking.savings_account_id), None)
                if acc:
                    if acc.tracking_number not in markings_map:
                        markings_map[acc.tracking_number] = {}
                    markings_map[acc.tracking_number][str(marking.marked_date)] = marking.status.value

    # Build Member List
    for acc in savings_accounts:
        user = db.query(User).filter(User.id == acc.customer_id).first()
        members_data.append({
            "user_id": user.id,
            "full_name": f"{user.first_name} {user.last_name}",
            "tracking_number": acc.tracking_number,
            "savings_account_id": acc.id
        })
        
        # Ensure map entry exists
        if acc.tracking_number not in markings_map:
            markings_map[acc.tracking_number] = {}

    return {
        "group_name": group.name,
        "contribution_amount": group.contribution_amount,
        "members": members_data,
        "dates": [d.isoformat() for d in dates],
        "markings": markings_map,
        "pagination": {
            "current_page": date_page,
            "limit": date_limit,
            "has_next": has_next_page,
            "total_dates_approx": total_dates_approx
        }
    }
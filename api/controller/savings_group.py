"""
Savings Group controller - provides FastAPI endpoints with repository injection.
"""
from typing import Optional, Dict, Any
import logging

from fastapi import Depends, Query, HTTPException
from sqlalchemy.orm import Session

import logging

from database.postgres_optimized import get_db
from utils.auth import get_current_user
from models.savings import SavingsAccount, SavingsMarking
from models.savings_group import SavingsGroup

from schemas.savings_group import (
    SavingsGroupCreate,
    AddGroupMemberRequest,
)
from service.savings_group import (
    create_group,
    list_groups,
    get_group,
    add_member_to_group,
    get_group_members,
    delete_group_service,
    get_group_grid_data,
    initiate_group_marking_payment,
    verify_group_marking_payment,
    get_group_savings_metrics,
)
from store.repositories.savings_group import SavingsGroupRepository
from store.repositories.savings import SavingsRepository
from store.repositories.business import BusinessRepository
from store.repositories.user import UserRepository

from utils.auth import get_current_user
from utils.dependencies import get_repository

logger = logging.getLogger(__name__)

from schemas.savings_group import SavingsGroupMarkingPaystackInit




async def get_group_markings_grid_controller(
    group_id: int,
    date_page: int = Query(1, ge=1, description="Page of dates"),
    date_limit: int = Query(10, ge=1, le=50, description="Number of dates per page"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get the markings grid for a savings group.
    - Full grid for admins/agents (managers)
    - Personal row only for customers/agent-members
    """
    logger.info(f"[GRID] Request for group {group_id} by user {current_user['user_id']} (role: {current_user['role']})")

    group = db.query(SavingsGroup).filter(SavingsGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found or inactive")

    user_id = current_user["user_id"]
    role = current_user["role"].lower()

    is_manager = role in ["admin", "super_admin", "agent"]
    member_account = db.query(SavingsAccount).filter(
        SavingsAccount.group_id == group_id,
        SavingsAccount.customer_id == user_id
    ).first()
    is_member = member_account is not None

    if not (is_manager or is_member):
        raise HTTPException(status_code=403, detail="You do not have permission to view this group's markings")

    grid_data = await get_group_grid_data(
        group_id=group_id,
        db=db,
        date_page=date_page,
        date_limit=date_limit
    )

    if not grid_data:
        raise HTTPException(status_code=404, detail="No markings data available")

    # Restrict to personal view if only member (not manager)
    if is_member and not is_manager:
        user_tracking = member_account.tracking_number
        filtered_members = [m for m in grid_data["members"] if m["tracking_number"] == user_tracking]
        filtered_markings = {user_tracking: grid_data["markings"].get(user_tracking, {})}

        grid_data["members"] = filtered_members
        grid_data["markings"] = filtered_markings
        grid_data["view_mode"] = "personal"  # optional frontend hint

    return grid_data


async def toggle_group_marking_controller(
    group_id: int,
    request: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Toggle or set marking status.
    - Managers can mark any member
    - Members can only mark their own row
    """
    logger.info(f"[MARKING] Toggle request for group {group_id} by user {current_user['user_id']}")

    required = {"savings_account_id", "date", "status"}
    missing = required - set(request.keys())
    if missing:
        raise HTTPException(422, detail=f"Missing required fields: {', '.join(missing)}")

    savings_account_id = request["savings_account_id"]
    date_str = request["date"]
    target_status = request["status"]

    if target_status not in ["paid", "pending", "not_started"]:
        raise HTTPException(422, detail="Status must be 'paid', 'pending' or 'not_started'")

    account = db.query(SavingsAccount).filter(
        SavingsAccount.id == savings_account_id,
        SavingsAccount.group_id == group_id
    ).first()

    if not account:
        raise HTTPException(404, detail="Savings account not found in this group")

    user_id = current_user["user_id"]
    role = current_user["role"].lower()

    is_manager = role in ["admin", "super_admin", "agent"]
    is_member = account.customer_id == user_id

    if not (is_manager or is_member):
        raise HTTPException(403, detail="Not authorized to mark contributions in this group")

    if is_member and not is_manager and account.customer_id != user_id:
        raise HTTPException(403, detail="You can only mark your own contributions")

    try:
        marking = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings_account_id,
            SavingsMarking.marked_date == date_str
        ).first()

        if marking:
            marking.status = target_status
            marking.marked_by_id = user_id
        else:
            if target_status == "paid":
                new_marking = SavingsMarking(
                    savings_account_id=savings_account_id,
                    marked_date=date_str,
                    amount=account.daily_amount or 0,
                    marked_by_id=user_id,
                    status=target_status,
                    payment_method="manual"
                )
                db.add(new_marking)
                marking = new_marking
            else:
                return {"message": "No change needed", "status": "not_started"}

        db.commit()
        db.refresh(marking)

        return {
            "message": f"Marked as {target_status}",
            "status": marking.status,
            "date": str(marking.marked_date),
            "savings_account_id": marking.savings_account_id
        }

    except Exception as e:
        db.rollback()
        logger.error(f"[MARKING] Failed: {str(e)}", exc_info=True)
        raise HTTPException(500, detail="Failed to update marking")


async def create_group_controller(
    request: SavingsGroupCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    group_repo: SavingsGroupRepository = Depends(get_repository(SavingsGroupRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
):
    logger.info("[CONTROLLER] create_group_controller - request received")
    logger.info(f"[CONTROLLER] Incoming payload: {request.model_dump_json(indent=2)}")

    try:
        result = await create_group(
            request=request,
            current_user=current_user,
            db=db,
            group_repo=group_repo,
            business_repo=business_repo,
            user_repo=user_repo,
            savings_repo=savings_repo,
        )
        logger.info("[CONTROLLER] Group creation successful")
        return result
    except Exception as e:
        logger.error(f"[CONTROLLER] Error in create_group_controller: {str(e)}", exc_info=True)
        raise


async def list_groups_controller(
    name: Optional[str] = Query(None, description="Filter by group name (partial match)"),
    frequency: Optional[str] = Query(None, description="Filter by frequency (weekly, bi-weekly, monthly, quarterly)"),
    is_active: Optional[bool] = Query(True, description="Show only active groups"),
    search: Optional[str] = Query(None, description="Search in name or description"),
    limit: int = Query(10, ge=1, le=100, description="Number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    group_repo: SavingsGroupRepository = Depends(get_repository(SavingsGroupRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    logger.info(f"[CONTROLLER] list_groups_controller - params: limit={limit}, offset={offset}, frequency={frequency}")
    return await list_groups(
        current_user=current_user,
        db=db,
        name=name,
        frequency=frequency,
        is_active=is_active,
        search=search,
        limit=limit,
        offset=offset,
        group_repo=group_repo,
        business_repo=business_repo,
    )


async def get_group_controller(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    group_repo: SavingsGroupRepository = Depends(get_repository(SavingsGroupRepository)),
):
    logger.info(f"[CONTROLLER] get_group_controller - group_id: {group_id}")
    return await get_group(
        group_id=group_id,
        current_user=current_user,
        db=db,
        group_repo=group_repo,
    )


async def delete_group_controller(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    group_repo: SavingsGroupRepository = Depends(get_repository(SavingsGroupRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    logger.info(f"[CONTROLLER] delete_group_controller - group_id: {group_id}")
    await delete_group_service(
        group_id=group_id,
        current_user=current_user,
        db=db,
        group_repo=group_repo,
        business_repo=business_repo,
    )
    return {"message": "Group deleted successfully"}


async def add_member_controller(
    group_id: int,
    request: AddGroupMemberRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    group_repo: SavingsGroupRepository = Depends(get_repository(SavingsGroupRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
):
    logger.info(f"[CONTROLLER] add_member_controller - group_id: {group_id}, user_id: {request.user_id}")
    account = await add_member_to_group(
        group_id=group_id,
        request=request,
        current_user=current_user,
        db=db,
        group_repo=group_repo,
        business_repo=business_repo,
        user_repo=user_repo,
        savings_repo=savings_repo,
    )
    return {
        "message": "Member added successfully",
        "savings_account_id": account.id,
        "tracking_number": account.tracking_number
    }


async def get_members_controller(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    group_repo: SavingsGroupRepository = Depends(get_repository(SavingsGroupRepository)),
):
    logger.info(f"[CONTROLLER] get_members_controller - group_id: {group_id}")
    return await get_group_members(
        group_id=group_id,
        current_user=current_user,
        db=db,
        group_repo=group_repo,
    )

async def init_group_paystack(
    group_id: int,
    request: SavingsGroupMarkingPaystackInit,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return await initiate_group_marking_payment(
        group_id, 
        request, 
        current_user, 
        db
    )


async def verify_group_paystack(
    reference: str,
    db: Session = Depends(get_db)
):
    return await verify_group_marking_payment(
        reference, 
        db
    )

async def get_group_metrics(
    group_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    group_repo: SavingsGroupRepository = Depends(get_repository(SavingsGroupRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
):
    return await get_group_savings_metrics(
        group_id=group_id,
        current_user=current_user,
        db=db,
        group_repo=group_repo,
        savings_repo=savings_repo
    )
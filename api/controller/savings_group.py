"""
Savings Group controller - provides FastAPI endpoints with repository injection.
"""
from typing import Optional

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from database.postgres_optimized import get_db
from schemas.savings_group import (
    SavingsGroupCreate,
    SavingsGroupResponse,
    AddGroupMemberRequest,
    PaginatedSavingsGroupsResponse,
)
from service.savings_group import (
    create_group,
    list_groups,
    get_group,
    add_member_to_group,
    get_group_members,
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
from utils.auth import get_current_user
from utils.dependencies import get_repository

"""
Savings Group controller - provides FastAPI endpoints with repository injection.
"""
from typing import Optional

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from database.postgres_optimized import get_db
from schemas.savings_group import (
    SavingsGroupCreate,
    SavingsGroupResponse,
    AddGroupMemberRequest,
    PaginatedSavingsGroupsResponse,
)
from service.savings_group import (
    create_group,
    list_groups,
    get_group,
    add_member_to_group,
    get_group_members,
)


import logging

logger = logging.getLogger(__name__)


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
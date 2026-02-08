"""
Business controller - exposes business endpoints with repository injection.
"""
from datetime import date
from typing import Optional

from fastapi import Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session

from database.postgres_optimized import get_db
from utils.auth import get_current_user
from utils.dependencies import get_repository

from schemas.business import (
    BusinessCreate,
    BusinessResponse,
    BusinessUpdate,
    CompleteRegistration,
    CustomerInvite,
    UnitCreate,
    UnitResponse,
    UnitUpdate,
)
from store.repositories import (
    BusinessRepository,
    PendingBusinessRequestRepository,
    UnitRepository,
    UserBusinessRepository,
    UserRepository,
    UserNotificationRepository,
)
from service.business import (
    accept_business_invitation,
    add_customer_to_business,
    complete_registration_service,
    create_business,
    create_unit,
    delete_business,
    delete_unit,
    get_all_unit_summary,
    get_all_units,
    get_business_summary,
    get_business_unit_summary,
    get_business_units,
    get_single_business,
    get_single_unit,
    get_unassigned_admin_businesses,
    get_user_businesses,
    get_user_units,
    reject_business_invitation,
    update_business,
    update_business_unit,
)


async def create_business_controller(
    request: BusinessCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
    notification_repo: UserNotificationRepository = Depends(
        get_repository(UserNotificationRepository)
    ),
):
    return await create_business(
        request=request,
        current_user=current_user,
        db=db,
        business_repo=business_repo,
        user_repo=user_repo,
        unit_repo=unit_repo,
        user_business_repo=user_business_repo,
        notification_repo=notification_repo,
    )


async def add_customer_controller(
    request: CustomerInvite,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
    pending_repo: PendingBusinessRequestRepository = Depends(
        get_repository(PendingBusinessRequestRepository)
    ),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
):
    return await add_customer_to_business(
        request=request,
        background_tasks=background_tasks,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        business_repo=business_repo,
        user_business_repo=user_business_repo,
        pending_repo=pending_repo,
        unit_repo=unit_repo,
    )


async def accept_invitation_controller(
    token: str = Query(...),
    db: Session = Depends(get_db),
    pending_repo: PendingBusinessRequestRepository = Depends(
        get_repository(PendingBusinessRequestRepository)
    ),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    return await accept_business_invitation(
        token=token,
        db=db,
        pending_repo=pending_repo,
        user_business_repo=user_business_repo,
        business_repo=business_repo,
    )


async def reject_invitation_controller(
    token: str = Query(...),
    db: Session = Depends(get_db),
    pending_repo: PendingBusinessRequestRepository = Depends(
        get_repository(PendingBusinessRequestRepository)
    ),
):
    return await reject_business_invitation(
        token=token,
        db=db,
        pending_repo=pending_repo,
    )

from schemas.business import CompleteRegistration
from service.business import complete_registration_service

async def complete_registration_controller(
    request: CompleteRegistration,
    db: Session = Depends(get_db),
    pending_repo: PendingBusinessRequestRepository = Depends(
        get_repository(PendingBusinessRequestRepository)
    ),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    return await complete_registration_service(
        token=request.token,
        pin=request.pin,
        password=request.pin, # Using PIN as password if needed, or ignoring
        full_name=request.full_name,
        db=db,
        pending_repo=pending_repo,
        user_repo=user_repo,
        user_business_repo=user_business_repo,
        business_repo=business_repo,
    )


async def get_user_businesses_controller(
    address: Optional[str] = Query(None, description="Filter by business address"),
    search: Optional[str] = Query(None, description="Search by business name, code, or address"),
    start_date: Optional[date] = Query(None, description="Filter by creation date start"),
    end_date: Optional[date] = Query(None, description="Filter by creation date end"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(8, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
):
    return await get_user_businesses(
        current_user=current_user,
        db=db,
        address=address,
        search=search,
        start_date=start_date,
        end_date=end_date,
        page=page,
        size=size,
        business_repo=business_repo,
        user_business_repo=user_business_repo,
    )


async def get_unassigned_admin_businesses_controller(
    current_user: dict = Depends(get_current_user),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    return await get_unassigned_admin_businesses(
        current_user=current_user,
        business_repo=business_repo,
    )


async def get_single_business_controller(
    business_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
):
    return await get_single_business(
        business_id=business_id,
        current_user=current_user,
        db=db,
        business_repo=business_repo,
        user_business_repo=user_business_repo,
    )


async def update_business_controller(
    business_id: int,
    request: BusinessUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    return await update_business(
        business_id=business_id,
        request=request,
        current_user=current_user,
        db=db,
        business_repo=business_repo,
    )


async def delete_business_controller(
    business_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
):
    return await delete_business(
        business_id=business_id,
        current_user=current_user,
        db=db,
        business_repo=business_repo,
        user_business_repo=user_business_repo,
        unit_repo=unit_repo,
    )


async def create_unit_controller(
    business_id: int,
    request: UnitCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
):
    return await create_unit(
        business_id=business_id,
        request=request,
        current_user=current_user,
        db=db,
        business_repo=business_repo,
        unit_repo=unit_repo,
    )


async def get_single_unit_controller(
    business_id: int,
    unit_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
):
    return await get_single_unit(
        business_id=business_id,
        unit_id=unit_id,
        current_user=current_user,
        db=db,
        business_repo=business_repo,
        unit_repo=unit_repo,
        user_business_repo=user_business_repo,
    )


async def get_all_units_controller(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(8, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search units by name or location"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
):
    return await get_all_units(
        current_user=current_user,
        db=db,
        page=page,
        size=size,
        search=search,
        unit_repo=unit_repo,
    )


async def get_business_units_controller(
    business_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(8, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search units by name or location"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
):
    return await get_business_units(
        business_id=business_id,
        current_user=current_user,
        db=db,
        page=page,
        size=size,
        search=search,
        business_repo=business_repo,
        unit_repo=unit_repo,
        user_business_repo=user_business_repo,
    )


async def get_user_units_controller(
    name: Optional[str] = Query(None, description="Filter by unit name"),
    location: Optional[str] = Query(None, description="Filter by unit location"),
    search: Optional[str] = Query(None, description="Search units by name or location"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(8, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
):
    return await get_user_units(
        current_user=current_user,
        db=db,
        name=name,
        location=location,
        search=search,
        page=page,
        size=size,
        unit_repo=unit_repo,
    )


async def update_business_unit_controller(
    unit_id: int,
    request: UnitUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
):
    return await update_business_unit(
        unit_id=unit_id,
        request=request,
        current_user=current_user,
        db=db,
        unit_repo=unit_repo,
    )


async def delete_unit_controller(
    unit_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
):
    return await delete_unit(
        unit_id=unit_id,
        current_user=current_user,
        db=db,
        unit_repo=unit_repo,
    )


async def get_total_business_count_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    return await get_business_summary(
        current_user=current_user,
        db=db,
        business_repo=business_repo,
    )


async def get_total_unit_count_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
):
    return await get_all_unit_summary(
        current_user=current_user,
        db=db,
        unit_repo=unit_repo,
    )


async def get_business_unit_count_controller(
    business_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
):
    return await get_business_unit_summary(
        business_id=business_id,
        current_user=current_user,
        db=db,
        business_repo=business_repo,
        unit_repo=unit_repo,
        user_business_repo=user_business_repo,
    )


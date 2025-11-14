"""
Savings controller - provides FastAPI endpoints with repository injection.
"""
from typing import Optional

from fastapi import Body, Depends, Query
from sqlalchemy.orm import Session

from database.postgres_optimized import get_db
from schemas.savings import (
    BulkMarkSavingsRequest,
    SavingsCreateDaily,
    SavingsCreateTarget,
    SavingsExtend,
    SavingsMarkingRequest,
    SavingsResponse,
    SavingsTargetCalculationResponse,
    SavingsUpdate,
)
from service.savings import (
    calculate_target_savings,
    confirm_bank_transfer,
    create_savings_daily,
    create_savings_target,
    delete_savings,
    end_savings_markings,
    extend_savings,
    get_all_savings,
    get_monthly_summary,
    get_savings_markings_by_tracking_number,
    get_savings_metrics,
    mark_savings_bulk,
    mark_savings_payment,
    update_savings,
    verify_savings_payment,
)
from store.repositories import (
    BusinessRepository,
    SavingsRepository,
    UnitRepository,
    UserBusinessRepository,
    UserRepository,
)
from utils.auth import get_current_user
from utils.dependencies import get_repository


async def create_daily_savings_controller(
    request: SavingsCreateDaily,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
):
    return await create_savings_daily(
        request=request,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        savings_repo=savings_repo,
        unit_repo=unit_repo,
    )


async def calculate_target_savings_controller(
    request: SavingsCreateTarget,
):
    return await calculate_target_savings(request)


async def create_target_savings_controller(
    request: SavingsCreateTarget,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
):
    return await create_savings_target(
        request=request,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        savings_repo=savings_repo,
    )


async def extend_savings_controller(
    request: SavingsExtend,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await extend_savings(
        request=request,
        current_user=current_user,
        db=db,
    )


async def update_savings_controller(
    savings_id: int,
    request: SavingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await update_savings(
        savings_id=savings_id,
        request=request,
        current_user=current_user,
        db=db,
    )


async def delete_savings_controller(
    savings_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
):
    return await delete_savings(
        savings_id=savings_id,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        savings_repo=savings_repo,
    )


async def get_all_savings_controller(
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    business_id: Optional[int] = Query(None, description="Filter by business ID"),
    unit_id: Optional[int] = Query(None, description="Filter by unit ID"),
    savings_type: Optional[str] = Query(None, description="Filter by savings type"),
    search: Optional[str] = Query(None, description="Search by tracking number or customer data"),
    limit: int = Query(10, ge=1, description="Number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
):
    return await get_all_savings(
        customer_id=customer_id,
        business_id=business_id,
        unit_id=unit_id,
        savings_type=savings_type,
        search=search,
        limit=limit,
        offset=offset,
        current_user=current_user,
        db=db,
        savings_repo=savings_repo,
        user_repo=user_repo,
        business_repo=business_repo,
        user_business_repo=user_business_repo,
        unit_repo=unit_repo,
    )


async def get_savings_markings_controller(
    tracking_number: str,
    db: Session = Depends(get_db),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
):
    return await get_savings_markings_by_tracking_number(
        tracking_number=tracking_number,
        db=db,
        savings_repo=savings_repo,
    )


async def get_savings_metrics_controller(
    tracking_number: Optional[str] = Query(None, description="Optional tracking number"),
    business_id: Optional[int] = Query(None, description="Optional business ID filter"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
):
    return await get_savings_metrics(
        user_id=current_user["user_id"],
        db=db,
        tracking_number=tracking_number,
        business_id=business_id,
        savings_repo=savings_repo,
        user_repo=user_repo,
    )


async def mark_savings_payment_controller(
    tracking_number: str,
    request: SavingsMarkingRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await mark_savings_payment(
        tracking_number=tracking_number,
        request=request,
        current_user=current_user,
        db=db,
    )


async def mark_savings_bulk_controller(
    request: BulkMarkSavingsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await mark_savings_bulk(
        request=request,
        current_user=current_user,
        db=db,
    )


async def end_savings_markings_controller(
    tracking_number: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await end_savings_markings(
        tracking_number=tracking_number,
        current_user=current_user,
        db=db,
    )


async def verify_payment_controller(
    reference: str,
    db: Session = Depends(get_db),
):
    return await verify_savings_payment(
        reference=reference,
        db=db,
    )


async def confirm_bank_transfer_controller(
    reference: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await confirm_bank_transfer(
        reference=reference,
        current_user=current_user,
        db=db,
    )


async def get_monthly_summary_controller(
    business_id: Optional[int] = Query(None, description="Optional business ID filter"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_monthly_summary(
        current_user=current_user,
        db=db,
        business_id=business_id,
    )


from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from schemas.savings import (
    SavingsCreateDaily,
    SavingsCreateTarget,
    SavingsResponse,
    SavingsMarkingRequest,
    SavingsMarkingResponse,
    SavingsUpdate,
    SavingsExtend,
    BulkMarkSavingsRequest,
    SavingsTargetCalculationResponse,
)
from service.savings import (
    create_savings_daily,
    create_savings_target,
    mark_savings_payment,
    update_savings,
    get_savings_markings_by_tracking_number,
    mark_savings_bulk,
    extend_savings,
    verify_savings_payment,
    calculate_target_savings,
    get_all_savings,
    delete_savings,
    get_savings_metrics,
    end_savings_markings,
    confirm_bank_transfer,
    get_monthly_summary,
)
from service.get_unpaid_savings import get_unpaid_completed_savings
from database.postgres_optimized import get_db
from utils.auth import get_current_user
from typing import List

savings_router = APIRouter(tags=["savings"], prefix="/savings")

@savings_router.post("/daily", response_model=SavingsResponse)
async def create_daily_savings(
    request: SavingsCreateDaily,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await create_savings_daily(request, current_user, db)

@savings_router.post("/target/calculate", response_model=SavingsTargetCalculationResponse)
async def calculate_target_savings_endpoint(
    request: SavingsCreateTarget,
):
    return await calculate_target_savings(request)

@savings_router.post("/target", response_model=SavingsResponse)
async def create_target_savings(
    request: SavingsCreateTarget,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await create_savings_target(request, current_user, db)

@savings_router.post("/extend", response_model=SavingsResponse)
async def extend_savings_endpoint(
    request: SavingsExtend,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await extend_savings(request, current_user, db)

@savings_router.put("/{savings_id}", response_model=SavingsResponse)
async def update_savings_endpoint(
    savings_id: int,
    request: SavingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await update_savings(savings_id, request, current_user, db)

@savings_router.delete("/{savings_id}", response_model=dict)
async def delete_savings_account(
    savings_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await delete_savings(savings_id, current_user, db)

@savings_router.get("/all", response_model=dict)
async def savings_list_route(
    customer_id: int = Query(None, description="Filter by customer ID (required for customer role)"),
    business_id: int = Query(None, description="Filter by business ID (required for admin role)"),
    unit_id: int = Query(None, description="Filter by unit ID"),
    savings_type: str = Query(None, description="Filter by savings type (DAILY or TARGET)"),
    limit: int = Query(10, ge=1, description="Number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db), 
):
    return await get_all_savings(customer_id, business_id, unit_id, savings_type, limit, offset, current_user, db)

@savings_router.get("/markings/{tracking_number}", response_model=dict)
async def get_savings_markings(
    tracking_number: str,
    db: Session = Depends(get_db),
):
    return await get_savings_markings_by_tracking_number(tracking_number, db)

@savings_router.get("/metrics", response_model=dict)
async def get_savings_metrics_endpoint(
    tracking_number: str = Query(None, description="Optional tracking number for specific savings account metrics"),
    business_id: int = Query(None, description="Optional business ID filter"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_savings_metrics(current_user["user_id"], db, tracking_number, business_id)

@savings_router.post("/mark/{tracking_number}", response_model=dict)
async def mark_savings(
    tracking_number: str,
    request: SavingsMarkingRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await mark_savings_payment(tracking_number, request, current_user, db)

@savings_router.post("/markings/bulk", response_model=dict)
async def mark_savings_bulk_endpoint(
    request: BulkMarkSavingsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await mark_savings_bulk(request, current_user, db)

@savings_router.post("/end_marking/{tracking_number}", response_model=dict)
async def end_savings_markings_endpoint(
    tracking_number: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await end_savings_markings(tracking_number, current_user, db)

@savings_router.get("/verify/{reference}", response_model=dict)
async def verify_payment(
    reference: str,
    db: Session = Depends(get_db),
):
    return await verify_savings_payment(reference, db)

@savings_router.post("/confirm_transfer/{reference}", response_model=dict)
async def confirm_bank_transfer_endpoint(
    reference: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await confirm_bank_transfer(reference, current_user, db)

@savings_router.get("/monthly-summary", response_model=dict)
async def get_monthly_summary_endpoint(
    business_id: int = Query(None, description="Optional business ID filter"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get monthly summary of savings and expenses for the current month, plus all-time totals"""
    return await get_monthly_summary(current_user, db)
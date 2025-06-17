from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from schemas.business import (
    BusinessCreate, 
    BusinessResponse, 
    BusinessUpdate, 
    CustomerInvite, 
    UnitCreate, 
    UnitResponse,
    UnitUpdate,
)
from service.business import (
    create_business,
    add_customer_to_business,
    accept_business_invitation,
    reject_business_invitation,
    get_user_businesses,
    get_single_business,
    update_business,
    delete_business,
    create_unit,
    get_business_units,
    get_all_units,
    update_business_unit,
    delete_unit,
    get_business_summary,
    get_all_unit_summary,
    get_business_unit_summary,
    get_user_units,
)
from database.postgres import get_db
from utils.auth import get_current_user
from typing import Optional, List
from datetime import date

business_router = APIRouter(tags=["Business"], prefix="/business")

@business_router.post("/create", response_model=BusinessResponse)
async def create_business_endpoint(
    request: BusinessCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await create_business(request, current_user, db)

@business_router.post("/add-customer", response_model=dict)
async def add_customer(
    request: CustomerInvite,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await add_customer_to_business(request, current_user, db)

@business_router.get("/accept-invitation")
async def accept_invitation(token: str = Query(...), db: Session = Depends(get_db)):
    return await accept_business_invitation(token, db)

@business_router.get("/reject-invitation")
async def reject_invitation(token: str = Query(...), db: Session = Depends(get_db)):
    return await reject_business_invitation(token, db)

@business_router.get("/list", response_model=List[BusinessResponse])
async def get_user_businesses_endpoint(
    address: Optional[str] = Query(None, description="Filter by business address"),
    start_date: Optional[date] = Query(None, description="Filter by creation date start"),
    end_date: Optional[date] = Query(None, description="Filter by creation date end"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(8, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return await get_user_businesses(
        current_user, db, address, start_date, end_date, page, size
    )

@business_router.get("/{business_id}", response_model=BusinessResponse)
async def get_single_business_endpoint(
    business_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_single_business(business_id, current_user, db)

@business_router.put("/{business_id}", response_model=BusinessResponse)
async def update_business_endpoint(
    business_id: int,
    request: BusinessUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await update_business(business_id, request, current_user, db)

@business_router.delete("/{business_id}")
async def delete_business_endpoint(
    business_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await delete_business(business_id, current_user, db)

@business_router.post("/{business_id}/units", response_model=UnitResponse)
async def create_unit_endpoint(
    business_id: int,
    request: UnitCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await create_unit(business_id, request, current_user, db)

@business_router.get("/units/all", response_model=List[UnitResponse])
async def get_all_units_endpoint(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(8, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_all_units(current_user, db, page, size)

@business_router.get("/{business_unique_code}/units", response_model=List[UnitResponse])
async def get_business_units_endpoint(
    business_unique_code: str,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(8, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_business_units(business_unique_code, current_user, db, page, size)

@business_router.get("/user/units/list", response_model=List[UnitResponse])  # New endpoint
async def get_user_units_endpoint(
    name: Optional[str] = Query(None, description="Filter by unit name"),
    location: Optional[str] = Query(None, description="Filter by unit location"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(8, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_user_units(current_user, db, name, location, page, size)

@business_router.put("/{unit_id}/units", response_model=UnitResponse)
async def update_unit_endpoint(
    unit_id: int,
    request: UnitUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await update_business_unit(unit_id, request, current_user, db)

@business_router.delete("/units/{unit_id}", response_model=dict)
async def delete_unit_endpoint(
    unit_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await delete_unit(unit_id, current_user, db)

@business_router.get("/summary/business-count", response_model=dict)
async def get_total_business_count_endpoint(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_business_summary(current_user, db)

@business_router.get("/summary/unit-count", response_model=dict)
async def get_total_unit_count_endpoint(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_all_unit_summary(current_user, db)

@business_router.get("/{business_id}/summary/unit-count", response_model=dict)
async def get_business_unit_count_endpoint(
    business_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_business_unit_summary(business_id, current_user, db)
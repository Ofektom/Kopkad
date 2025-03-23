from fastapi import APIRouter, Depends, Body, Query
from sqlalchemy.orm import Session
from schemas.business import BusinessCreate, BusinessResponse
from service.business import create_business, add_customer_to_business, accept_business_invitation, reject_business_invitation
from database.postgres import get_db
from utils.auth import get_current_user

business_router = APIRouter(tags=["Business"], prefix="/business")

@business_router.post("/create", response_model=BusinessResponse)
async def create_business_endpoint(
    request: BusinessCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return await create_business(request, current_user, db)

@business_router.post("/{business_unique_code}/add-customer")
async def add_customer(
    business_unique_code: str,
    customer_phone: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await add_customer_to_business(customer_phone, business_unique_code, current_user, db)

@business_router.get("/accept-invitation")
async def accept_invitation(token: str = Query(...), db: Session = Depends(get_db)):
    return await accept_business_invitation(token, db)

@business_router.get("/reject-invitation")
async def reject_invitation(token: str = Query(...), db: Session = Depends(get_db)):
    return await reject_business_invitation(token, db)

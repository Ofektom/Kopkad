from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from schemas.expenses import (
    ExpenseCardCreate,
    ExpenseCardResponse,
    ExpenseCreate,
    ExpenseResponse,
    TopUpRequest,
    ExpenseStatsResponse,
    FinancialAdviceResponse,
    FinancialAnalyticsResponse,
)
from service.expenses import (
    create_expense_card,
    get_expense_cards,
    record_expense,
    top_up_expense_card,
    get_expenses_by_card,
    update_expense_card,
    delete_expense_card,
    get_expense_stats,
    get_financial_advice,
    get_financial_analytics,
)
from database.postgres import get_db
from utils.auth import get_current_user
from typing import Optional
from datetime import date

expenses_router = APIRouter(tags=["expenses"], prefix="/expenses")

@expenses_router.post("/card", response_model=ExpenseCardResponse)
async def create_expense_card_endpoint(
    request: ExpenseCardCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await create_expense_card(request, current_user, db)

@expenses_router.get("/cards", response_model=dict)
async def get_expense_cards_endpoint(
    limit: int = Query(10, ge=1),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_expense_cards(limit, offset, current_user, db)

@expenses_router.post("/card/{card_id}/expense", response_model=ExpenseResponse)
async def record_expense_endpoint(
    card_id: int,
    request: ExpenseCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await record_expense(card_id, request, current_user, db)

@expenses_router.post("/card/{card_id}/topup", response_model=ExpenseCardResponse)
async def top_up_expense_card_endpoint(
    card_id: int,
    request: TopUpRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await top_up_expense_card(card_id, request, current_user, db)

@expenses_router.get("/card/{card_id}/expenses", response_model=dict)
async def get_expenses_by_card_endpoint(
    card_id: int,
    limit: int = Query(10, ge=1),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_expenses_by_card(card_id, limit, offset, current_user, db)

@expenses_router.put("/card/{card_id}", response_model=ExpenseCardResponse)
async def update_expense_card_endpoint(
    card_id: int,
    request: ExpenseCardCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await update_expense_card(card_id, request, current_user, db)

@expenses_router.delete("/card/{card_id}", response_model=dict)
async def delete_expense_card_endpoint(
    card_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await delete_expense_card(card_id, current_user, db)

@expenses_router.get("/stats", response_model=ExpenseStatsResponse)
async def get_expense_stats_endpoint(
    from_date: Optional[date] = Query(None, description="Start date for the stats period"),
    to_date: Optional[date] = Query(None, description="End date for the stats period"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_expense_stats(from_date, to_date, current_user, db)

@expenses_router.get("/advice", response_model=FinancialAdviceResponse)
async def get_financial_advice_endpoint(
    from_date: Optional[date] = Query(None, description="Start date for the advice period"),
    to_date: Optional[date] = Query(None, description="End date for the advice period"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_financial_advice(from_date, to_date, current_user, db)

@expenses_router.get("/analytics", response_model=FinancialAnalyticsResponse)
async def get_financial_analytics_endpoint(
    from_date: Optional[date] = Query(None, description="Start date for the analytics period"),
    to_date: Optional[date] = Query(None, description="End date for the analytics period"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await get_financial_analytics(from_date, to_date, current_user, db)
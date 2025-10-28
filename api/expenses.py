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
    ExpensePlannerRequest,
    ExpensePlannerResponse,
    EligibleSavingsResponse,
    ExpenseUpdate,
    CreatePlannerCardRequest,
    PlannerCardResponse,
    ActivatePlannerRequest,
    CompletePlannedItemRequest,
    PlannerProgressResponse,
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
    expense_planner,
    get_eligible_savings,
    get_all_expenses,
    update_expense,
    delete_expense,
    create_planner_card,
    activate_planner_card,
    complete_planned_item,
    get_planner_progress,
)
from database.postgres_optimized import get_db
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

@expenses_router.post("/planner", response_model=ExpensePlannerResponse)
async def expense_planner_endpoint(
    request: ExpensePlannerRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI-powered expense planner - analyze if capital is sufficient for planned expenses"""
    # Convert pydantic models to dicts for service function
    planned_expenses = [
        {
            'category': exp.category,
            'amount': exp.amount,
            'purpose': exp.purpose
        }
        for exp in request.planned_expenses
    ]
    return await expense_planner(request.capital, planned_expenses, current_user, db)

@expenses_router.get("/eligible-savings", response_model=dict)
async def get_eligible_savings_endpoint(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get list of completed savings accounts eligible for creating expense cards"""
    return await get_eligible_savings(current_user, db)

@expenses_router.get("/all", response_model=dict)
async def get_all_expenses_endpoint(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    category: Optional[str] = Query(None),
    min_amount: Optional[float] = Query(None),
    max_amount: Optional[float] = Query(None),
    search: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all expenses across all cards with advanced filtering"""
    from decimal import Decimal
    min_amt = Decimal(str(min_amount)) if min_amount is not None else None
    max_amt = Decimal(str(max_amount)) if max_amount is not None else None
    return await get_all_expenses(
        limit, offset, from_date, to_date, category, min_amt, max_amt, search, current_user, db
    )

@expenses_router.put("/{expense_id}", response_model=ExpenseResponse)
async def update_expense_endpoint(
    expense_id: int,
    request: ExpenseUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing expense"""
    updates = request.dict(exclude_unset=True)
    return await update_expense(expense_id, updates, current_user, db)

@expenses_router.delete("/{expense_id}", response_model=dict)
async def delete_expense_endpoint(
    expense_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an expense and refund the amount to card balance"""
    return await delete_expense(expense_id, current_user, db)

# ==================== PLANNER WORKFLOW ENDPOINTS ====================

@expenses_router.post("/planner/create", response_model=PlannerCardResponse)
async def create_planner_card_endpoint(
    request: CreatePlannerCardRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a draft expense card (planner) with planned expenses
    Returns the card + AI analysis of the budget
    """
    planned_expenses = [
        {
            'category': exp.category,
            'amount': exp.amount,
            'purpose': exp.purpose
        }
        for exp in request.planned_expenses
    ]
    return await create_planner_card(request.name, request.capital, planned_expenses, current_user, db)

@expenses_router.post("/planner/{card_id}/activate", response_model=ExpenseCardResponse)
async def activate_planner_card_endpoint(
    card_id: int,
    request: ActivatePlannerRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Activate a draft planner card - converts it from DRAFT to ACTIVE
    After activation, user can start checking off planned items
    """
    return await activate_planner_card(card_id, current_user, db)

@expenses_router.post("/expenses/{expense_id}/complete", response_model=ExpenseResponse)
async def complete_planned_item_endpoint(
    expense_id: int,
    request: CompletePlannedItemRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark a planned expense as completed (checklist)
    Optionally provide actual amount spent (if different from planned)
    """
    return await complete_planned_item(expense_id, request.actual_amount, current_user, db)

@expenses_router.get("/planner/{card_id}/progress", response_model=PlannerProgressResponse)
async def get_planner_progress_endpoint(
    card_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get progress tracking for a planner card
    Shows planned vs actual, completion status, variance by category
    """
    return await get_planner_progress(card_id, current_user, db)
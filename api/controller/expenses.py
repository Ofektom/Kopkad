"""
Expenses controller with repository-injected endpoints.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from database.postgres_optimized import get_db
from schemas.expenses import (
    ActivatePlannerRequest,
    CompletePlannedItemRequest,
    CreatePlannerCardRequest,
    ExpenseCardCreate,
    ExpenseCardResponse,
    ExpenseCreate,
    ExpensePlannerRequest,
    ExpensePlannerResponse,
    ExpenseResponse,
    ExpenseUpdate,
    FinancialAdviceResponse,
    FinancialAnalyticsResponse,
    PlannerCardResponse,
    PlannerProgressResponse,
    TopUpRequest,
)
from service.expenses import (
    activate_planner_card,
    complete_planned_item,
    create_expense_card,
    create_planner_card,
    delete_expense,
    delete_expense_card,
    expense_planner,
    get_all_expenses,
    get_eligible_savings,
    get_expense_cards,
    get_expense_metrics,
    get_expense_stats,
    get_financial_advice,
    get_financial_analytics,
    get_expenses_by_card,
    get_planner_progress,
    record_expense,
    top_up_expense_card,
    update_expense,
    update_expense_card,
)
from store.repositories import (
    ExpenseCardRepository,
    ExpenseRepository,
    SavingsRepository,
    UserRepository,
)
from utils.auth import get_current_user
from utils.dependencies import get_repository


async def create_expense_card_controller(
    request: ExpenseCardCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
):
    return await create_expense_card(
        request=request,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        savings_repo=savings_repo,
        expense_card_repo=expense_card_repo,
    )


async def get_expense_cards_controller(
    limit: int = Query(10, ge=1),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search cards by name or notes"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
):
    return await get_expense_cards(
        limit=limit,
        offset=offset,
        current_user=current_user,
        db=db,
        search=search,
        expense_card_repo=expense_card_repo,
    )


async def record_expense_controller(
    card_id: int,
    request: ExpenseCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
):
    return await record_expense(
        card_id=card_id,
        request=request,
        current_user=current_user,
        db=db,
        expense_card_repo=expense_card_repo,
        expense_repo=expense_repo,
    )


async def top_up_expense_card_controller(
    card_id: int,
    request: TopUpRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
):
    return await top_up_expense_card(
        card_id=card_id,
        request=request,
        current_user=current_user,
        db=db,
        expense_card_repo=expense_card_repo,
    )


async def get_expenses_by_card_controller(
    card_id: int,
    limit: int = Query(10, ge=1),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search expenses by description"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
):
    return await get_expenses_by_card(
        card_id=card_id,
        limit=limit,
        offset=offset,
        current_user=current_user,
        db=db,
        search=search,
        expense_card_repo=expense_card_repo,
        expense_repo=expense_repo,
    )


async def update_expense_card_controller(
    card_id: int,
    request: ExpenseCardCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
):
    return await update_expense_card(
        card_id=card_id,
        request=request,
        current_user=current_user,
        db=db,
        expense_card_repo=expense_card_repo,
        savings_repo=savings_repo,
    )


async def delete_expense_card_controller(
    card_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
):
    return await delete_expense_card(
        card_id=card_id,
        current_user=current_user,
        db=db,
        expense_card_repo=expense_card_repo,
    )


async def get_expense_metrics_controller(
    business_id: int = Query(None, description="Optional business ID filter"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
):
    return await get_expense_metrics(
        current_user=current_user,
        db=db,
        business_id=business_id,
        expense_card_repo=expense_card_repo,
        expense_repo=expense_repo,
        user_repo=user_repo,
    )


async def get_expense_stats_controller(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
):
    return await get_expense_stats(
        from_date=from_date,
        to_date=to_date,
        current_user=current_user,
        db=db,
        expense_card_repo=expense_card_repo,
        expense_repo=expense_repo,
    )


async def get_financial_advice_controller(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
):
    return await get_financial_advice(
        from_date=from_date,
        to_date=to_date,
        current_user=current_user,
        db=db,
        expense_repo=expense_repo,
        expense_card_repo=expense_card_repo,
    )


async def get_financial_analytics_controller(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
):
    return await get_financial_analytics(
        from_date=from_date,
        to_date=to_date,
        current_user=current_user,
        db=db,
        expense_repo=expense_repo,
        expense_card_repo=expense_card_repo,
    )


async def expense_planner_controller(
    request: ExpensePlannerRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
):
    planned_expenses = [
        {"category": exp.category, "amount": exp.amount, "purpose": exp.purpose}
        for exp in request.planned_expenses
    ]
    return await expense_planner(
        capital=request.capital,
        planned_expenses=planned_expenses,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
    )


async def get_eligible_savings_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
):
    return await get_eligible_savings(
        current_user=current_user,
        db=db,
        savings_repo=savings_repo,
        expense_card_repo=expense_card_repo,
    )


async def get_all_expenses_controller(
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
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
):
    min_amt = Decimal(str(min_amount)) if min_amount is not None else None
    max_amt = Decimal(str(max_amount)) if max_amount is not None else None
    return await get_all_expenses(
        limit=limit,
        offset=offset,
        from_date=from_date,
        to_date=to_date,
        category=category,
        min_amount=min_amt,
        max_amount=max_amt,
        search=search,
        current_user=current_user,
        db=db,
        expense_repo=expense_repo,
    )


async def update_expense_controller(
    expense_id: int,
    request: ExpenseUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
):
    updates = request.dict(exclude_unset=True)
    return await update_expense(
        expense_id=expense_id,
        updates=updates,
        current_user=current_user,
        db=db,
        expense_repo=expense_repo,
    )


async def delete_expense_controller(
    expense_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
):
    return await delete_expense(
        expense_id=expense_id,
        current_user=current_user,
        db=db,
        expense_repo=expense_repo,
    )


async def create_planner_card_controller(
    request: CreatePlannerCardRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
):
    planned_expenses = [
        {"category": exp.category, "amount": exp.amount, "purpose": exp.purpose}
        for exp in request.planned_expenses
    ]
    return await create_planner_card(
        name=request.name,
        capital=request.capital,
        planned_expenses=planned_expenses,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        expense_card_repo=expense_card_repo,
        expense_repo=expense_repo,
    )


async def activate_planner_card_controller(
    card_id: int,
    request: ActivatePlannerRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
):
    return await activate_planner_card(
        card_id=card_id,
        current_user=current_user,
        db=db,
        expense_card_repo=expense_card_repo,
    )


async def complete_planned_item_controller(
    expense_id: int,
    request: CompletePlannedItemRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
):
    return await complete_planned_item(
        expense_id=expense_id,
        actual_amount=request.actual_amount,
        current_user=current_user,
        db=db,
        expense_repo=expense_repo,
    )


async def get_planner_progress_controller(
    card_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    expense_card_repo: ExpenseCardRepository = Depends(
        get_repository(ExpenseCardRepository)
    ),
    expense_repo: ExpenseRepository = Depends(get_repository(ExpenseRepository)),
):
    return await get_planner_progress(
        card_id=card_id,
        current_user=current_user,
        db=db,
        expense_card_repo=expense_card_repo,
        expense_repo=expense_repo,
    )


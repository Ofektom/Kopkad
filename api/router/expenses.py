from fastapi import APIRouter

from api.controller.expenses import (
    activate_planner_card_controller,
    complete_planned_item_controller,
    create_expense_card_controller,
    create_planner_card_controller,
    delete_expense_card_controller,
    delete_expense_controller,
    expense_planner_controller,
    get_all_expenses_controller,
    get_eligible_savings_controller,
    get_expense_cards_controller,
    get_expense_metrics_controller,
    get_expense_stats_controller,
    get_expenses_by_card_controller,
    get_financial_advice_controller,
    get_financial_analytics_controller,
    get_planner_progress_controller,
    record_expense_controller,
    top_up_expense_card_controller,
    update_expense_card_controller,
    update_expense_controller,
)
from schemas.expenses import (
    ExpenseCardResponse,
    ExpensePlannerResponse,
    ExpenseResponse,
    ExpenseStatsResponse,
    FinancialAdviceResponse,
    FinancialAnalyticsResponse,
    PlannerCardResponse,
    PlannerProgressResponse,
)

expenses_router = APIRouter(prefix="/expenses", tags=["Expenses"])

expenses_router.add_api_route(
    "/card",
    endpoint=create_expense_card_controller,
    methods=["POST"],
    response_model=ExpenseCardResponse,
    summary="Create an expense card",
)

expenses_router.add_api_route(
    "/cards",
    endpoint=get_expense_cards_controller,
    methods=["GET"],
    response_model=dict,
    summary="List expense cards",
)

expenses_router.add_api_route(
    "/card/{card_id}/expense",
    endpoint=record_expense_controller,
    methods=["POST"],
    response_model=ExpenseResponse,
    summary="Record an expense on a card",
)

expenses_router.add_api_route(
    "/card/{card_id}/topup",
    endpoint=top_up_expense_card_controller,
    methods=["POST"],
    response_model=ExpenseCardResponse,
    summary="Top up an expense card",
)

expenses_router.add_api_route(
    "/card/{card_id}/expenses",
    endpoint=get_expenses_by_card_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get expenses for a specific card",
)

expenses_router.add_api_route(
    "/card/{card_id}",
    endpoint=update_expense_card_controller,
    methods=["PUT"],
    response_model=ExpenseCardResponse,
    summary="Update an expense card",
)

expenses_router.add_api_route(
    "/card/{card_id}",
    endpoint=delete_expense_card_controller,
    methods=["DELETE"],
    response_model=dict,
    summary="Delete an expense card",
)

expenses_router.add_api_route(
    "/metrics",
    endpoint=get_expense_metrics_controller,
    methods=["GET"],
    response_model=dict,
    summary="Retrieve expense metrics",
)

expenses_router.add_api_route(
    "/stats",
    endpoint=get_expense_stats_controller,
    methods=["GET"],
    response_model=ExpenseStatsResponse,
    summary="Get expense statistics",
)

expenses_router.add_api_route(
    "/advice",
    endpoint=get_financial_advice_controller,
    methods=["GET"],
    response_model=FinancialAdviceResponse,
    summary="Get financial advice",
)

expenses_router.add_api_route(
    "/analytics",
    endpoint=get_financial_analytics_controller,
    methods=["GET"],
    response_model=FinancialAnalyticsResponse,
    summary="Get financial analytics",
)

expenses_router.add_api_route(
    "/planner",
    endpoint=expense_planner_controller,
    methods=["POST"],
    response_model=ExpensePlannerResponse,
    summary="Run expense planner analysis",
)

expenses_router.add_api_route(
    "/eligible-savings",
    endpoint=get_eligible_savings_controller,
    methods=["GET"],
    response_model=dict,
    summary="List eligible savings for expense cards",
)

expenses_router.add_api_route(
    "/all",
    endpoint=get_all_expenses_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get all expenses with filters",
)

expenses_router.add_api_route(
    "/{expense_id}",
    endpoint=update_expense_controller,
    methods=["PUT"],
    response_model=ExpenseResponse,
    summary="Update an expense",
)

expenses_router.add_api_route(
    "/{expense_id}",
    endpoint=delete_expense_controller,
    methods=["DELETE"],
    response_model=dict,
    summary="Delete an expense",
)

expenses_router.add_api_route(
    "/planner/create",
    endpoint=create_planner_card_controller,
    methods=["POST"],
    response_model=PlannerCardResponse,
    summary="Create a planner card",
)

expenses_router.add_api_route(
    "/planner/{card_id}/activate",
    endpoint=activate_planner_card_controller,
    methods=["POST"],
    response_model=ExpenseCardResponse,
    summary="Activate a planner card",
)

expenses_router.add_api_route(
    "/expenses/{expense_id}/complete",
    endpoint=complete_planned_item_controller,
    methods=["POST"],
    response_model=ExpenseResponse,
    summary="Complete a planned expense item",
)

expenses_router.add_api_route(
    "/planner/{card_id}/progress",
    endpoint=get_planner_progress_controller,
    methods=["GET"],
    response_model=PlannerProgressResponse,
    summary="Get planner progress",
)


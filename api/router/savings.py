from fastapi import APIRouter

from api.controller.savings import (
    calculate_target_savings_controller,
    confirm_bank_transfer_controller,
    create_daily_savings_controller,
    create_target_savings_controller,
    delete_savings_controller,
    end_savings_markings_controller,
    extend_savings_controller,
    get_all_savings_controller,
    get_monthly_summary_controller,
    get_savings_markings_controller,
    get_savings_metrics_controller,
    mark_savings_bulk_controller,
    mark_savings_payment_controller,
    update_savings_controller,
    verify_payment_controller,
)
from schemas.savings import (
    SavingsMarkingResponse,
    SavingsResponse,
    SavingsTargetCalculationResponse,
)


savings_router = APIRouter(prefix="/savings", tags=["Savings"])

savings_router.add_api_route(
    "/daily",
    endpoint=create_daily_savings_controller,
    methods=["POST"],
    response_model=SavingsResponse,
    summary="Create daily savings account",
)

savings_router.add_api_route(
    "/target/calculate",
    endpoint=calculate_target_savings_controller,
    methods=["POST"],
    response_model=SavingsTargetCalculationResponse,
    summary="Calculate target savings projection",
)

savings_router.add_api_route(
    "/target",
    endpoint=create_target_savings_controller,
    methods=["POST"],
    response_model=SavingsResponse,
    summary="Create target savings account",
)

savings_router.add_api_route(
    "/extend",
    endpoint=extend_savings_controller,
    methods=["POST"],
    response_model=SavingsResponse,
    summary="Extend an existing savings account",
)

savings_router.add_api_route(
    "/{savings_id}",
    endpoint=update_savings_controller,
    methods=["PUT"],
    response_model=SavingsResponse,
    summary="Update savings account",
)

savings_router.add_api_route(
    "/{savings_id}",
    endpoint=delete_savings_controller,
    methods=["DELETE"],
    response_model=dict,
    summary="Delete savings account",
)

savings_router.add_api_route(
    "/all",
    endpoint=get_all_savings_controller,
    methods=["GET"],
    response_model=dict,
    summary="List savings accounts with filters",
)

savings_router.add_api_route(
    "/markings/{tracking_number}",
    endpoint=get_savings_markings_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get savings markings by tracking number",
)

savings_router.add_api_route(
    "/metrics",
    endpoint=get_savings_metrics_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get savings metrics overview",
)

savings_router.add_api_route(
    "/mark/{tracking_number}",
    endpoint=mark_savings_payment_controller,
    methods=["POST"],
    response_model=dict,
    summary="Mark savings payment",
)

savings_router.add_api_route(
    "/markings/bulk",
    endpoint=mark_savings_bulk_controller,
    methods=["POST"],
    response_model=dict,
    summary="Bulk mark savings payments",
)

savings_router.add_api_route(
    "/end_marking/{tracking_number}",
    endpoint=end_savings_markings_controller,
    methods=["POST"],
    response_model=dict,
    summary="Complete savings markings",
)

savings_router.add_api_route(
    "/verify/{reference}",
    endpoint=verify_payment_controller,
    methods=["GET"],
    response_model=dict,
    summary="Verify savings payment reference",
)

savings_router.add_api_route(
    "/confirm_transfer/{reference}",
    endpoint=confirm_bank_transfer_controller,
    methods=["POST"],
    response_model=dict,
    summary="Confirm bank transfer savings payout",
)

savings_router.add_api_route(
    "/monthly-summary",
    endpoint=get_monthly_summary_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get monthly savings summary",
)


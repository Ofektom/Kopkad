from fastapi import APIRouter

from api.controller.payments import (
    approve_payment_request_controller,
    cancel_payment_request_controller,
    create_account_details_controller,
    create_payment_account_controller,
    create_payment_request_controller,
    delete_account_details_controller,
    delete_payment_account_controller,
    get_commissions_controller,
    get_customer_payments_controller,
    get_payment_accounts_controller,
    get_payment_requests_controller,
    paystack_webhook_controller,
    reject_payment_request_controller,
    update_account_details_controller,
    update_payment_account_controller,
)
from schemas.payments import PaymentAccountResponse


payments_router = APIRouter(prefix="/payments", tags=["Payments"])

payments_router.add_api_route(
    "/webhook/paystack",
    endpoint=paystack_webhook_controller,
    methods=["POST"],
    include_in_schema=False,
)

payments_router.add_api_route(
    "/account",
    endpoint=create_payment_account_controller,
    methods=["POST"],
    response_model=dict,
    summary="Create a payment account",
)

payments_router.add_api_route(
    "/account-details",
    endpoint=create_account_details_controller,
    methods=["POST"],
    response_model=dict,
    summary="Add account details to a payment account",
)

payments_router.add_api_route(
    "/account-details/{account_details_id}",
    endpoint=update_account_details_controller,
    methods=["PUT"],
    response_model=dict,
    summary="Update payment account details",
)

payments_router.add_api_route(
    "/account/{payment_account_id}",
    endpoint=delete_payment_account_controller,
    methods=["DELETE"],
    response_model=dict,
    summary="Delete a payment account",
)

payments_router.add_api_route(
    "/accounts",
    endpoint=get_payment_accounts_controller,
    methods=["GET"],
    response_model=dict,
    summary="List payment accounts",
)

payments_router.add_api_route(
    "/account/{payment_account_id}",
    endpoint=update_payment_account_controller,
    methods=["PUT"],
    response_model=PaymentAccountResponse,
    summary="Update a payment account",
)

payments_router.add_api_route(
    "/account-details/{account_details_id}",
    endpoint=delete_account_details_controller,
    methods=["DELETE"],
    response_model=dict,
    summary="Delete account details",
)

payments_router.add_api_route(
    "/request",
    endpoint=create_payment_request_controller,
    methods=["POST"],
    response_model=dict,
    summary="Create a payment request",
)

payments_router.add_api_route(
    "/requests",
    endpoint=get_payment_requests_controller,
    methods=["GET"],
    response_model=dict,
    summary="List payment requests",
)

payments_router.add_api_route(
    "/request/{request_id}/approve",
    endpoint=approve_payment_request_controller,
    methods=["POST"],
    response_model=dict,
    summary="Approve a payment request",
)

payments_router.add_api_route(
    "/request/{request_id}/reject",
    endpoint=reject_payment_request_controller,
    methods=["POST"],
    response_model=dict,
    summary="Reject a payment request",
)

payments_router.add_api_route(
    "/request/{request_id}/cancel",
    endpoint=cancel_payment_request_controller,
    methods=["POST"],
    response_model=dict,
    summary="Cancel a payment request",
)

payments_router.add_api_route(
    "/commissions",
    endpoint=get_commissions_controller,
    methods=["GET"],
    response_model=dict,
    summary="Retrieve agent commissions",
)

payments_router.add_api_route(
    "/customer-payments",
    endpoint=get_customer_payments_controller,
    methods=["GET"],
    response_model=dict,
    summary="Retrieve customer payments",
)


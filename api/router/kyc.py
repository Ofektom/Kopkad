from fastapi import APIRouter
from api.controller.kyc import initiate_kyc_controller, complete_kyc_controller

kyc_router = APIRouter(prefix="/kyc", tags=["KYC — Identity Verification"])

kyc_router.add_api_route(
    "/verify",
    endpoint=initiate_kyc_controller,
    methods=["POST"],
    summary="Pre-signup biometric KYC (agents/sub-agents) — returns reference_token",
)

kyc_router.add_api_route(
    "/complete",
    endpoint=complete_kyc_controller,
    methods=["POST"],
    summary="Post-signup biometric KYC (customers) — updates kyc_status directly",
)

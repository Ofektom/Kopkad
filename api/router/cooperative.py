from fastapi import APIRouter
from api.controller.cooperative import add_contribution, get_my_contributions
from schemas.savings import SavingsMarkingResponse # Using generic response for now

cooperative_router = APIRouter(prefix="/cooperative", tags=["Cooperative"])

cooperative_router.add_api_route(
    "/contribution",
    endpoint=add_contribution,
    methods=["POST"],
    summary="Add contribution for a member (Admin)",
)

cooperative_router.add_api_route(
    "/member/contributions",
    endpoint=get_my_contributions,
    methods=["GET"],
    summary="Get my contributions (Member)",
)

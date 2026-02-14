from fastapi import APIRouter
from typing import List

from schemas.savings_group import (
    SavingsGroupResponse,
    CreateSavingsGroupResponse,
    PaginatedSavingsGroupsResponse,
    GroupMemberResponse
)
from api.controller.savings_group import (
    create_group_controller,
    list_groups_controller,
    get_group_controller,
    add_member_controller,
    get_members_controller,
    delete_group_controller,
    get_group_markings_grid_controller,
    toggle_group_marking_controller,
    init_group_paystack,
    verify_group_paystack,
)

savings_group_router = APIRouter(prefix="/savings-groups", tags=["Savings Groups"])


savings_group_router.add_api_route(
    "/",
    endpoint=create_group_controller,
    methods=["POST"],
    response_model=CreateSavingsGroupResponse,
    summary="Create a new savings group (Business Admin only)",
)

savings_group_router.add_api_route(
    "/",
    endpoint=list_groups_controller,
    methods=["GET"],
    response_model=PaginatedSavingsGroupsResponse,
    summary="List all savings groups for the current user's business",
)

savings_group_router.add_api_route(
    "/{group_id}",
    endpoint=get_group_controller,
    methods=["GET"],
    response_model=SavingsGroupResponse,
    summary="Get details of a specific savings group",
)
    
savings_group_router.add_api_route(
    "/{group_id}",
    endpoint=delete_group_controller,
    methods=["DELETE"],
    response_model=dict,
    summary="Delete a savings group (only if no paid contributions)",
)

savings_group_router.add_api_route(
    "/{group_id}/members",
    endpoint=add_member_controller,
    methods=["POST"],
    response_model=dict,
    summary="Add a member to a specific savings group (Business Admin only)",
)

savings_group_router.add_api_route(
    "/{group_id}/members",
    endpoint=get_members_controller,
    methods=["GET"],
    response_model=List[GroupMemberResponse],
    summary="List members of a specific savings group",
)


savings_group_router.add_api_route(
    "/{group_id}/grid",
    endpoint=get_group_markings_grid_controller,
    methods=["GET"],
    summary="Get savings group markings grid",
)

savings_group_router.add_api_route(
    "/{group_id}/markings",
    endpoint=toggle_group_marking_controller,
    methods=["POST"],
    summary="Toggle a marking for a group member",
)

savings_group_router.add_api_route(
    "/{group_id}/markings/paystack",
    endpoint=init_group_paystack,
    methods=["POST"],
    summary="Initiate Paystack payment for group markings"
)

savings_group_router.add_api_route(
    "/markings/paystack/verify/{reference}",
    endpoint=verify_group_paystack,
    methods=["GET"],
    summary="Verify Paystack payment for group markings"
)
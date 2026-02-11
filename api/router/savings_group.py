from fastapi import APIRouter
from typing import List

from schemas.savings_group import (
    SavingsGroupCreate,
    SavingsGroupResponse,
    CreateSavingsGroupResponse,
    PaginatedSavingsGroupsResponse,
    AddGroupMemberRequest,
    GroupMemberResponse
)
from api.controller.savings_group import (
    create_group_controller,
    list_groups_controller,
    get_group_controller,
    add_member_controller,
    get_members_controller,
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
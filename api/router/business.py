from fastapi import APIRouter, Query

from api.controller.business import (
    accept_invitation_controller,
    add_customer_controller,
    create_business_controller,
    create_unit_controller,
    delete_business_controller,
    delete_unit_controller,
    get_all_units_controller,
    get_business_unit_count_controller,
    get_business_units_controller,
    get_single_business_controller,
    get_single_unit_controller,
    get_total_business_count_controller,
    get_total_unit_count_controller,
    get_unassigned_admin_businesses_controller,
    get_user_businesses_controller,
    get_user_units_controller,
    reject_invitation_controller,
    update_business_controller,

    update_business_unit_controller,
    complete_registration_controller,
)
from schemas.business import (
    BusinessCreate,
    BusinessResponse,
    BusinessUpdate,
    CustomerInvite,
    UnitCreate,
    UnitResponse,
    UnitUpdate,
)


business_router = APIRouter(prefix="/business", tags=["Business"])

business_router.add_api_route(
    "/create",
    endpoint=create_business_controller,
    methods=["POST"],
    response_model=BusinessResponse,
    summary="Create a new business",
)

business_router.add_api_route(
    "/add-customer",
    endpoint=add_customer_controller,
    methods=["POST"],
    response_model=dict,
    summary="Invite an existing customer to a business",
)

business_router.add_api_route(
    "/accept-invitation",
    endpoint=accept_invitation_controller,
    methods=["GET"],
    summary="Accept business invitation via token",
)

business_router.add_api_route(
    "/reject-invitation",
    endpoint=reject_invitation_controller,
    methods=["GET"],
    summary="Reject business invitation via token",
)

business_router.add_api_route(
    "/complete-registration",
    endpoint=complete_registration_controller,
    methods=["POST"],
    summary="Complete registration for invited user (Set PIN/Name)",
)

business_router.add_api_route(
    "/list",
    endpoint=get_user_businesses_controller,
    methods=["GET"],
    response_model=list[BusinessResponse],
    summary="List businesses associated with the current user",
)

business_router.add_api_route(
    "/unassigned-admins",
    endpoint=get_unassigned_admin_businesses_controller,
    methods=["GET"],
    response_model=dict,
    summary="List businesses without assigned admins",
)

business_router.add_api_route(
    "/{business_id}",
    endpoint=get_single_business_controller,
    methods=["GET"],
    response_model=BusinessResponse,
    summary="Get single business details",
)

business_router.add_api_route(
    "/{business_id}",
    endpoint=update_business_controller,
    methods=["PUT"],
    response_model=BusinessResponse,
    summary="Update business details",
)

business_router.add_api_route(
    "/{business_id}",
    endpoint=delete_business_controller,
    methods=["DELETE"],
    summary="Delete a business",
)

business_router.add_api_route(
    "/{business_id}/units",
    endpoint=create_unit_controller,
    methods=["POST"],
    response_model=UnitResponse,
    summary="Create a new unit within a business",
)

business_router.add_api_route(
    "/{business_id}/units/{unit_id}",
    endpoint=get_single_unit_controller,
    methods=["GET"],
    response_model=UnitResponse,
    summary="Get a single unit within a business",
)

business_router.add_api_route(
    "/units/all",
    endpoint=get_all_units_controller,
    methods=["GET"],
    response_model=list[UnitResponse],
    summary="List all units (super admin only)",
)

business_router.add_api_route(
    "/{business_id}/units",
    endpoint=get_business_units_controller,
    methods=["GET"],
    response_model=list[UnitResponse],
    summary="List units within a specific business",
)

business_router.add_api_route(
    "/user/units/list",
    endpoint=get_user_units_controller,
    methods=["GET"],
    response_model=list[UnitResponse],
    summary="List units associated with the current user",
)

business_router.add_api_route(
    "/{business_id}/units/{unit_id}",
    endpoint=update_business_unit_controller,
    methods=["PUT"],
    response_model=UnitResponse,
    summary="Update a specific unit within a business (agent/admin/super_admin only)"
)

business_router.add_api_route(
    "/units/{unit_id}",
    endpoint=delete_unit_controller,
    methods=["DELETE"],
    response_model=dict,
    summary="Delete a unit",
)

business_router.add_api_route(
    "/summary/business-count",
    endpoint=get_total_business_count_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get total business count",
)

business_router.add_api_route(
    "/summary/unit-count",
    endpoint=get_total_unit_count_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get total unit count (super admin)",
)

business_router.add_api_route(
    "/{business_id}/summary/unit-count",
    endpoint=get_business_unit_count_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get unit count for a specific business",
)
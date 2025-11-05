"""
User router - following Showroom360 pattern.
Routers only register routes using add_api_route().
"""
from fastapi import APIRouter
from schemas.user import UserResponse
from api.controller.user import (
    signup_controller,
    signup_authenticated_controller,
    login_controller,
    oauth_callback_controller,
    refresh_token_controller,
    logout_controller,
    get_users_controller,
    get_business_users_controller,
    change_password_controller,
    toggle_user_status_controller,
    delete_user_controller,
    switch_business_controller,
    assign_admin_controller,
    get_admin_credentials_controller,
)

user_router = APIRouter(prefix="/auth", tags=["Authentication & User Management"])


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

user_router.add_api_route(
    "/signup",
    endpoint=signup_controller,
    methods=["POST"],
    response_model=UserResponse,
    summary="User signup (unauthenticated)",
)

user_router.add_api_route(
    "/signup-authenticated",
    endpoint=signup_authenticated_controller,
    methods=["POST"],
    response_model=UserResponse,
    summary="User signup (authenticated - for agents creating customers)",
)

user_router.add_api_route(
    "/login",
    endpoint=login_controller,
    methods=["POST"],
    response_model=UserResponse,
    summary="User login",
)

user_router.add_api_route(
    "/oauth/callback/{provider}",
    endpoint=oauth_callback_controller,
    methods=["GET"],
    response_model=UserResponse,
    summary="OAuth callback handler",
)

user_router.add_api_route(
    "/refresh",
    endpoint=refresh_token_controller,
    methods=["POST"],
    response_model=dict,
    summary="Refresh access token",
)

user_router.add_api_route(
    "/logout",
    endpoint=logout_controller,
    methods=["POST"],
    response_model=dict,
    summary="Logout current user",
)


# ============================================================================
# USER MANAGEMENT ROUTES
# ============================================================================

user_router.add_api_route(
    "/users",
    endpoint=get_users_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get all users with optional filters",
)

user_router.add_api_route(
    "/users/business/{business_id}",
    endpoint=get_business_users_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get users in a specific business",
)

user_router.add_api_route(
    "/users/change-password",
    endpoint=change_password_controller,
    methods=["POST"],
    response_model=dict,
    summary="Change user password",
)

user_router.add_api_route(
    "/users/{user_id}/status",
    endpoint=toggle_user_status_controller,
    methods=["PATCH"],
    response_model=dict,
    summary="Toggle user active status",
)

user_router.add_api_route(
    "/users/{user_id}",
    endpoint=delete_user_controller,
    methods=["DELETE"],
    response_model=dict,
    summary="Delete a user",
)

user_router.add_api_route(
    "/users/switch-business/{business_id}",
    endpoint=switch_business_controller,
    methods=["POST"],
    response_model=dict,
    summary="Switch user's active business",
)


# ============================================================================
# ADMIN MANAGEMENT ROUTES (Super Admin Only)
# ============================================================================

user_router.add_api_route(
    "/assign-admin",
    endpoint=assign_admin_controller,
    methods=["POST"],
    response_model=dict,
    summary="Assign admin to business (super_admin only)",
)

user_router.add_api_route(
    "/admin-credentials",
    endpoint=get_admin_credentials_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get all admin credentials (super_admin only)",
)


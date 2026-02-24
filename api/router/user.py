"""
User router - following Showroom360 pattern.
Routers only register routes using add_api_route().
"""
from fastapi import APIRouter
from typing import List
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
    get_current_user_info_controller,
    update_admin_details_controller,
    update_current_user_controller,
    forgot_password_controller,
    reset_password_controller,
    verify_reset_otp_controller,
    resend_reset_otp_controller,
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
    response_model=UserResponse,
    summary="Refresh access token",
)

user_router.add_api_route(
    "/logout",
    endpoint=logout_controller,
    methods=["POST"],
    response_model=dict,
    summary="Logout current user",
)

user_router.add_api_route(
    "/me",
    endpoint=get_current_user_info_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get current authenticated user's information",
)


# ============================================================================
# USER MANAGEMENT ROUTES
# ============================================================================

user_router.add_api_route(
    "/users",
    endpoint=get_users_controller,
    methods=["GET"],
    response_model=List[UserResponse],
    summary="Get all users with optional filters",
)

user_router.add_api_route(
    "/business/{business_id}/users",
    endpoint=get_business_users_controller,
    methods=["GET"],
    response_model=List[UserResponse],
    summary="Get users in a specific business",
)

user_router.add_api_route(
    "/change_password",
    endpoint=change_password_controller,
    methods=["POST"],
    response_model=UserResponse,
    summary="Change user password",
)

user_router.add_api_route(
    "/forgot-password",
    endpoint=forgot_password_controller,
    methods=["POST"],
    response_model=dict,
    summary="Request a password reset link",
)

user_router.add_api_route(
    "/reset-password",
    endpoint=reset_password_controller,
    methods=["POST"],
    response_model=dict,
    summary="Reset password using a valid token",
)

user_router.add_api_route(
    "/verify-reset-otp",
    endpoint=verify_reset_otp_controller,
    methods=["POST"],
    response_model=dict,
    summary="Verify reset OTP and get reset session",
)

user_router.add_api_route(
    "/resend-reset-otp",
    endpoint=resend_reset_otp_controller,
    methods=["POST"],
    response_model=dict,
    summary="Resend reset OTP for phone",
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
    "/switch-business",
    endpoint=switch_business_controller,
    methods=["POST"],
    response_model=UserResponse,
    summary="Switch user's active business",
)


user_router.add_api_route(
    "/me",
    endpoint=update_current_user_controller,
    methods=["PATCH"],
    response_model=UserResponse,
    summary="Update current authenticated user's profile (self-update)",
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

user_router.add_api_route(
    "/admin/{user_id}",
    endpoint=update_admin_details_controller,
    methods=["PATCH"],
    response_model=dict,
    summary="Update admin details (super_admin only)",
)


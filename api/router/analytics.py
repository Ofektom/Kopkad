"""
Analytics router - registers analytics endpoints.
"""
from fastapi import APIRouter

from api.controller.analytics import super_admin_dashboard_controller

analytics_router = APIRouter(prefix="/analytics", tags=["Analytics"])

analytics_router.add_api_route(
    "/super-admin/dashboard",
    endpoint=super_admin_dashboard_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get system-wide analytics for the super admin dashboard",
)



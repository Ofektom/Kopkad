from decimal import Decimal
from typing import Dict

from fastapi import status
from sqlalchemy.orm import Session

from schemas.analytics import (
    DashboardAnalyticsResponse,
    DashboardTotals,
    SavingsOverview,
    SavingsVolumeBreakdown,
    BusinessPerformanceMetrics,
    RecentUserSummary,
    UnitSummary,
    UnitCount,
    PaymentSummary,
    PaymentStatusMetric,
    DashboardCharts,
    ChartSeries,
    ChartPoint,
)
from store.enums import Role
from store.repositories import (
    UserRepository,
    BusinessRepository,
    SavingsRepository,
    UnitRepository,
    PaymentsRepository,
)
from utils.response import success_response, error_response

import logging

logger = logging.getLogger(__name__)


def _decimal_to_float(value: Decimal | float | int) -> float:
    """Helper to convert Decimals to float for JSON serialization."""
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0)


async def get_super_admin_dashboard(
    *,
    current_user: Dict,
    db: Session,
    user_repo: UserRepository,
    business_repo: BusinessRepository,
    savings_repo: SavingsRepository,
    unit_repo: UnitRepository,
    payments_repo: PaymentsRepository,
):
    """
    Assemble analytics overview for the super admin dashboard.
    """
    if current_user.get("role") != Role.SUPER_ADMIN.value:
        return error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Super admin access required",
        )

    logger.info(
        "Generating super admin analytics dashboard for user_id=%s",
        current_user.get("user_id"),
    )

    try:
        savings_metrics = savings_repo.get_system_savings_metrics()
    except Exception as exc:
        logger.warning("Failed to retrieve savings metrics: %s", exc)
        savings_metrics = {
            "total_accounts": 0,
            "accounts_by_type": {},
            "total_volume": 0,
            "volume_by_status": {},
        }

    try:
        business_metrics = business_repo.get_business_performance_metrics()
    except Exception as exc:
        logger.warning("Failed to retrieve business performance metrics: %s", exc)
        business_metrics = []

    try:
        user_counts_by_business = user_repo.get_business_user_counts()
    except Exception as exc:
        logger.warning("Failed to retrieve user counts by business: %s", exc)
        user_counts_by_business = {}

    try:
        unit_counts_by_business = unit_repo.count_units_by_business()
    except Exception as exc:
        logger.warning("Failed to retrieve unit counts by business: %s", exc)
        unit_counts_by_business = {}

    try:
        units_per_business = unit_repo.get_units_per_business()
    except Exception as exc:
        logger.warning("Failed to retrieve units per business: %s", exc)
        units_per_business = []

    try:
        role_counts = user_repo.count_users_by_role()
    except Exception as exc:
        logger.warning("Failed to retrieve role counts: %s", exc)
        role_counts = {}

    role_breakdown = {role.value: role_counts.get(role.value, 0) for role in Role}

    try:
        successful_payment_stats = payments_repo.get_successful_payment_stats()
    except Exception as exc:
        logger.warning("Failed to retrieve successful payment stats: %s", exc)
        successful_payment_stats = {"count": 0, "amount": 0.0}

    try:
        payment_status_metrics = payments_repo.get_status_summary()
    except Exception as exc:
        logger.warning("Failed to retrieve payment status summary: %s", exc)
        payment_status_metrics = []

    try:
        monthly_payment_volume = payments_repo.get_monthly_payment_volume(months=6)
    except Exception as exc:
        logger.warning("Failed to retrieve monthly payment volume: %s", exc)
        monthly_payment_volume = []

    try:
        total_payment_requests = payments_repo.count_total_requests()
    except Exception as exc:
        logger.warning("Failed to count payment requests: %s", exc)
        total_payment_requests = 0

    try:
        transfer_metrics = savings_repo.get_successful_transfer_metrics()
    except Exception as exc:
        logger.warning("Failed to retrieve transfer metrics: %s", exc)
        transfer_metrics = {"count": 0, "amount": 0.0}

    try:
        monthly_transfer_volume = savings_repo.get_monthly_transfer_volume(months=6)
    except Exception as exc:
        logger.warning("Failed to retrieve monthly transfer volume: %s", exc)
        monthly_transfer_volume = []

    try:
        total_users = user_repo.count_all_users()
    except Exception as exc:
        logger.warning("Failed to count users: %s", exc)
        total_users = 0

    try:
        active_users = user_repo.count_active_users()
    except Exception as exc:
        logger.warning("Failed to count active users: %s", exc)
        active_users = 0

    try:
        inactive_users = user_repo.count_inactive_users()
    except Exception as exc:
        logger.warning("Failed to count inactive users: %s", exc)
        inactive_users = 0

    try:
        total_businesses = business_repo.count()
    except Exception as exc:
        logger.warning("Failed to count businesses: %s", exc)
        total_businesses = 0

    try:
        total_units = unit_repo.count_all_units()
    except Exception as exc:
        logger.warning("Failed to count units: %s", exc)
        total_units = 0

    totals = DashboardTotals(
        total_users=total_users,
        active_users=active_users,
        inactive_users=inactive_users,
        total_businesses=total_businesses,
        total_units=total_units,
        total_savings_accounts=savings_metrics.get("total_accounts", 0),
        total_admins=role_counts.get(Role.ADMIN.value, 0),
        total_agents=role_counts.get(Role.AGENT.value, 0),
        total_sub_agents=role_counts.get(Role.SUB_AGENT.value, 0),
        total_customers=role_counts.get(Role.CUSTOMER.value, 0),
        total_payment_requests=total_payment_requests,
        successful_payment_requests=successful_payment_stats.get("count", 0),
        successful_transfers=transfer_metrics.get("count", 0),
    )

    volume_by_status = savings_metrics.get("volume_by_status", {})
    savings_overview = SavingsOverview(
        totals=SavingsVolumeBreakdown(
            total_volume=_decimal_to_float(savings_metrics.get("total_volume", 0)),
            paid_volume=_decimal_to_float(volume_by_status.get("paid", 0)),
            pending_volume=_decimal_to_float(volume_by_status.get("pending", 0)),
        ),
        accounts_by_type=savings_metrics.get("accounts_by_type", {}),
    )

    business_performance = [
        BusinessPerformanceMetrics(
            business_id=metric["business_id"],
            name=metric["name"],
            unique_code=metric["unique_code"],
            total_users=user_counts_by_business.get(metric["business_id"], 0),
            total_units=unit_counts_by_business.get(metric["business_id"], 0),
            total_savings_accounts=metric["total_savings_accounts"],
            total_volume=_decimal_to_float(metric["total_volume"]),
            paid_volume=_decimal_to_float(metric["paid_volume"]),
            pending_volume=_decimal_to_float(metric["pending_volume"]),
        )
        for metric in business_metrics
    ]

    unit_summary_items = []
    business_lookup = {metric["business_id"]: metric for metric in business_metrics}
    for info in business_metrics:
        unit_count = unit_counts_by_business.get(info["business_id"], 0)
        unit_summary_items.append(
            UnitCount(
                business_id=info["business_id"],
                name=info["name"],
                unique_code=info["unique_code"],
                unit_count=unit_count,
            )
        )

    units_with_data = {
        item["business_id"]: item for item in units_per_business
    }
    for business_id, data in units_with_data.items():
        if business_id not in business_lookup:
            unit_summary_items.append(
                UnitCount(
                    business_id=business_id,
                    name=data["name"],
                    unique_code=data["unique_code"],
                    unit_count=data["unit_count"],
                )
            )

    unit_summary = UnitSummary(
        total_units=total_units,
        units_by_business=sorted(
            unit_summary_items,
            key=lambda item: item.unit_count,
            reverse=True,
        ),
    )

    payment_summary = PaymentSummary(
        total_requests=total_payment_requests,
        status_metrics=[
            PaymentStatusMetric(
                status=item["status"],
                count=int(item["count"]),
                amount=float(item["amount"]),
            )
            for item in payment_status_metrics
        ],
        successful_payment_requests=successful_payment_stats.get("count", 0),
        successful_payment_amount=float(
            successful_payment_stats.get("amount", 0.0)
        ),
        successful_transfers=transfer_metrics.get("count", 0),
        successful_transfer_amount=float(transfer_metrics.get("amount", 0.0)),
    )

    try:
        user_growth_points = user_repo.get_monthly_user_growth(months=6)
    except Exception as exc:
        logger.warning("Failed to retrieve monthly user growth: %s", exc)
        user_growth_points = []

    charts = DashboardCharts(
        user_growth=[
            ChartSeries(
                id="User Signups",
                points=[
                    ChartPoint(label=point["label"], value=float(point["value"]))
                    for point in user_growth_points
                ],
            )
        ],
        payment_volume=[
            ChartSeries(
                id="Approved Payments",
                points=[
                    ChartPoint(label=item["label"], value=float(item["value"]))
                    for item in monthly_payment_volume
                ],
            )
        ],
        business_units=[
            ChartSeries(
                id="Units per Business",
                points=[
                    ChartPoint(
                        label=f"{item.name}",
                        value=float(item.unit_count),
                    )
                    for item in unit_summary.units_by_business[:10]
                ],
            )
        ],
        transfer_volume=[
            ChartSeries(
                id="Transfer Volume",
                points=[
                    ChartPoint(label=item["label"], value=float(item["value"]))
                    for item in monthly_transfer_volume
                ],
            )
        ],
    )

    recent_users = [
        RecentUserSummary.model_validate(user)
        for user in user_repo.get_recent_users(limit=5)
    ]

    response_payload = DashboardAnalyticsResponse(
        totals=totals,
        role_breakdown=role_breakdown,
        savings_overview=savings_overview,
        business_performance=business_performance,
        unit_summary=unit_summary,
        payment_summary=payment_summary,
        charts=charts,
        recent_users=recent_users,
    )

    return success_response(
        status_code=status.HTTP_200_OK,
        message="Super admin analytics loaded successfully",
        data=response_payload.model_dump(),
    )



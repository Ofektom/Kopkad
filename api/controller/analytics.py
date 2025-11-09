"""
Analytics controller - exposes dashboard endpoints for super admins.
"""
from fastapi import Depends
from sqlalchemy.orm import Session

from database.postgres_optimized import get_db
from service.analytics import get_super_admin_dashboard
from store.repositories import (
    UserRepository,
    BusinessRepository,
    SavingsRepository,
    UnitRepository,
    PaymentsRepository,
)
from utils.auth import get_current_user
from utils.dependencies import get_repository


async def super_admin_dashboard_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
    unit_repo: UnitRepository = Depends(get_repository(UnitRepository)),
    payments_repo: PaymentsRepository = Depends(get_repository(PaymentsRepository)),
):
    """Return analytics metrics for the super admin dashboard."""
    return await get_super_admin_dashboard(
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        business_repo=business_repo,
        savings_repo=savings_repo,
        unit_repo=unit_repo,
        payments_repo=payments_repo,
    )



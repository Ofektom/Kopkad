from fastapi import Depends
from sqlalchemy.orm import Session

from database.postgres_optimized import get_db
from schemas.user import KycVerifyRequest, KycCompleteRequest
from service.kyc import initiate_kyc, complete_kyc
from utils.auth_cached import get_current_user


async def initiate_kyc_controller(
    request: KycVerifyRequest,
    db: Session = Depends(get_db),
):
    """Pre-signup KYC — no authentication required."""
    return await initiate_kyc(request, db)


async def complete_kyc_controller(
    request: KycCompleteRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Post-signup KYC — requires authentication (customers from Settings)."""
    return await complete_kyc(request, current_user, db)

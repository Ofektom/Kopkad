"""
API endpoint for getting unpaid completed savings for payment requests
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from service.get_unpaid_savings import get_unpaid_completed_savings
from database.postgres_optimized import get_db
from utils.auth import get_current_user

unpaid_savings_router = APIRouter(tags=["savings"], prefix="/savings")

@unpaid_savings_router.get("/unpaid-completed", response_model=dict)
async def get_unpaid_completed_savings_endpoint(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get list of completed savings that haven't been paid out yet.
    For use in payment request functionality.
    
    Returns savings where:
    - marking_status == COMPLETED
    - No markings with status == PAID
    """
    return await get_unpaid_completed_savings(current_user, db)


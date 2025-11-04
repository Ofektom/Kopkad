"""
Service function to get completed but unpaid savings for payment requests
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from models.savings import SavingsAccount, SavingsMarking, SavingsStatus, MarkingStatus
from models.payments import PaymentRequest
from utils.response import success_response
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


async def get_unpaid_completed_savings(current_user: dict, db: Session):
    """
    Get list of completed savings accounts that haven't been paid out yet.
    For use in payment request functionality.
    
    Criteria:
    - savings_account.marking_status == COMPLETED
    - No savings_markings with status == PAID
    """
    
    # Get completed savings for this user
    completed_savings = db.query(SavingsAccount).filter(
        SavingsAccount.customer_id == current_user["user_id"],
        SavingsAccount.marking_status == MarkingStatus.COMPLETED
    ).all()
    
    results = []
    for savings in completed_savings:
        # Check if any marking has PAID status - exclude if so
        has_paid_marking = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings.id,
            SavingsMarking.status == SavingsStatus.PAID
        ).first()
        
        # Skip if already paid out
        if has_paid_marking:
            continue
        
        # Get all markings for calculation
        all_markings = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings.id
        ).order_by(SavingsMarking.marked_date).all()
        
        if not all_markings:
            continue
        
        # Calculate totals
        total_amount = sum(marking.amount for marking in all_markings)
        earliest_date = all_markings[0].marked_date
        latest_date = all_markings[-1].marked_date
        total_savings_days = (latest_date - earliest_date).days + 1
        
        # Calculate commission
        if savings.commission_days == 0:
            total_commission = Decimal(0)
        else:
            total_commission = savings.commission_amount * Decimal(total_savings_days / savings.commission_days)
            total_commission = total_commission.quantize(Decimal("0.01"))
        
        net_payout = total_amount - total_commission
        
        # Check payment request status
        payment_request = db.query(PaymentRequest).filter(
            PaymentRequest.savings_account_id == savings.id
        ).order_by(PaymentRequest.created_at.desc()).first()
        
        payment_request_status = payment_request.status.value if payment_request else None
        
        # Build response
        results.append({
            "id": savings.id,
            "tracking_number": savings.tracking_number,
            "savings_type": savings.savings_type.value,
            "total_amount": float(total_amount),
            "commission": float(total_commission),
            "net_payout": float(net_payout),
            "start_date": savings.start_date.isoformat() if savings.start_date else None,
            "completion_date": latest_date.isoformat() if latest_date else None,
            "payment_request_status": payment_request_status
        })
    
    logger.info(f"Found {len(results)} unpaid completed savings for user {current_user['user_id']}")
    return success_response(
        status_code=200,
        message="Unpaid completed savings retrieved successfully",
        data={"savings": results, "count": len(results)}
    )


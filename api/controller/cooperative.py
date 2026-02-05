from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime, timezone
from decimal import Decimal

from database.postgres_optimized import get_db
from models.user import User, Role, Permission
from models.business import Business, BusinessType
from models.savings import SavingsAccount, SavingsType, SavingsMarking, MarkingStatus, SavingsStatus, PaymentMethod
from utils.auth import get_current_user
from utils.response import success_response, error_response
from store.repositories import SavingsRepository, BusinessRepository, UserRepository
from schemas.savings import SavingsMarkingResponse, SavingsResponse
from pydantic import BaseModel

class CooperativeContribution(BaseModel):
    member_id: int
    amount: float
    contribution_date: date = date.today()
    notes: str | None = None

async def add_contribution(
    request: CooperativeContribution,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Admin adds a contribution for a member."""
    # Check Admin Role
    if current_user["role"] not in [Role.ADMIN, Role.SUPER_ADMIN]:
        return error_response(status_code=403, message="Only Admins can add contributions")

    # Check Business
    business_repo = BusinessRepository(db)
    if current_user["role"] == Role.ADMIN:
        business = business_repo.get_by_admin_id(current_user["user_id"])
        if not business or business.business_type != BusinessType.COOPERATIVE:
             return error_response(status_code=403, message="Only Cooperative Admins can perform this action")
        business_id = business.id
    else:
        # Super Admin needs to specify business? Or infer? 
        # For simplicity, we assume Super Admin acts on member's business request.member_id business? 
        # We need to find the member first.
        pass

    user_repo = UserRepository(db)
    member = user_repo.get_by_id(request.member_id)
    if not member:
        return error_response(status_code=404, message="Member not found")
        
    # Verify member is in the business
    # (Assuming we have business_id from Admin context)
    # If Super Admin, get business from member.
    
    # Get or Create Savings Account
    savings_repo = SavingsRepository(db)
    account = db.query(SavingsAccount).filter(
        SavingsAccount.customer_id == member.id,
        SavingsAccount.savings_type == SavingsType.COOPERATIVE
    ).first()
    
    if not account:
        # Create Account
        import uuid
        tracking_number = str(uuid.uuid4())[:8].upper()
        account = SavingsAccount(
            customer_id=member.id,
            business_id=business_id if 'business_id' in locals() else member.businesses[0].id, # Fallback
            tracking_number=tracking_number,
            savings_type=SavingsType.COOPERATIVE,
            daily_amount=0, # Variable
            duration_months=12,
            start_date=date.today(),
            commission_amount=0,
            created_by=current_user["user_id"],
            created_at=datetime.now(timezone.utc)
        )
        db.add(account)
        db.flush()
        
    # Create Marking
    marking = SavingsMarking(
        savings_account_id=account.id,
        marked_date=request.contribution_date,
        amount=request.amount,
        marked_by_id=current_user["user_id"],
        status=SavingsStatus.PAID,
        payment_method=PaymentMethod.CASH, # Default to CASH for manual entry
        created_at=datetime.now(timezone.utc)
    )
    db.add(marking)
    db.commit()
    
    return success_response(
        status_code=201, 
        message="Contribution added successfully",
        data={"id": marking.id, "amount": float(marking.amount)}
    )

async def get_my_contributions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Member views their own contributions."""
    savings_repo = SavingsRepository(db)
    
    # Get Cooperative Account
    account = db.query(SavingsAccount).filter(
        SavingsAccount.customer_id == current_user["user_id"],
        SavingsAccount.savings_type == SavingsType.COOPERATIVE
    ).first()
    
    if not account:
        return success_response(status_code=200, message="No contributions found", data=[])
        
    markings = db.query(SavingsMarking).filter(
        SavingsMarking.savings_account_id == account.id
    ).order_by(SavingsMarking.marked_date.desc()).all()
    
    data = [{
        "date": m.marked_date,
        "amount": float(m.amount),
        "status": m.status.value
    } for m in markings]
    
    return success_response(status_code=200, message="Contributions retrieved", data=data)

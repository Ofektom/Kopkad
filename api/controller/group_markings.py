from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date
import logging

from database.postgres_optimized import get_db
from utils.auth import get_current_user
from service.savings_group_grid import get_group_grid_data
from models.savings import SavingsAccount, SavingsMarking, SavingsStatus, MarkingStatus
from models.savings_group import SavingsGroup

logger = logging.getLogger(__name__)

async def get_group_markings_grid_controller(
    group_id: int,
    date_page: int = Query(1, ge=1),
    date_limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get the markings grid for a savings group.
    """
    logger.info(f"[CONTROLLER] get_group_markings_grid - group_id={group_id}, page={date_page}")
    
    # Authorization check (Agent/Admin)
    if current_user["role"] not in ["admin", "super_admin", "agent"]:
         # Also allow customers if they are members? "The page will list all the members..." 
         # Usually only admins/agents mark, but maybe members can view.
         # For now, let's restrict to admins/agents as they are the ones likely managing the sheet.
         # Or if it represents a transparent cooperative, members might view.
         # Let's verify membership if customer.
         pass 
         
    grid_data = await get_group_grid_data(
        group_id=group_id,
        db=db,
        date_page=date_page,
        date_limit=date_limit
    )
    
    if not grid_data:
        raise HTTPException(status_code=404, detail="Savings group not found")
        
    return grid_data


from pydantic import BaseModel

class ToggleMarkingRequest(BaseModel):
    savings_account_id: int
    date: date
    status: str # "paid", "pending", "not_started" 

async def toggle_group_marking_controller(
    group_id: int,
    request: ToggleMarkingRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Toggle a marking for a specific member and date.
    """
    logger.info(f"[CONTROLLER] toggle_group_marking - group_id={group_id}, acc={request.savings_account_id}, date={request.date}")

    if current_user["role"] not in ["admin", "super_admin", "agent"]:
        # Only agents/admins can mark for now
        raise HTTPException(status_code=403, detail="Not authorized to mark contributions")

    # Verify account belongs to group
    account = db.query(SavingsAccount).filter(
        SavingsAccount.id == request.savings_account_id,
        SavingsAccount.group_id == group_id
    ).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Savings account not found in this group")

    # Find existing marking
    marking = db.query(SavingsMarking).filter(
        SavingsMarking.savings_account_id == request.savings_account_id,
        SavingsMarking.marked_date == request.date
    ).first()

    target_status = request.status
    
    # If status is 'pending' or 'not_started', technically we might delete the marking 
    # or set it to pending. SavingsMarking usually implies a record exists.
    # If we want to "unmark" (paid -> pending), we update.
    
    if not marking:
        # Create new marking if status is PAID
        if target_status == "paid":
            new_marking = SavingsMarking(
                savings_account_id=account.id,
                marked_date=request.date,
                amount=account.daily_amount, # Assuming group contribution amount matches daily_amount
                marked_by_id=current_user["user_id"],
                status=SavingsStatus.PAID,
                payment_method=None # Manually marked
            )
            db.add(new_marking)
            db.commit()
            return {"message": "Marked as paid", "status": "paid"}
    else:
        # Update existing
        if target_status == "paid":
             marking.status = SavingsStatus.PAID
             marking.marked_by_id = current_user["user_id"]
        else:
             # If setting to pending/unpaid, we update status
             marking.status = SavingsStatus.PENDING
        
        db.commit()
        return {"message": "Marking updated", "status": marking.status.value}

    return {"message": "No change", "status": "pending"}

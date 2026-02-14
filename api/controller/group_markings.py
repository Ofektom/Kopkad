from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Dict, Any
from datetime import date
import logging

from database.postgres_optimized import get_db
from utils.auth import get_current_user
from service.savings_group_grid import get_group_grid_data
from models.savings import SavingsAccount, SavingsMarking
from models.savings_group import SavingsGroup

logger = logging.getLogger(__name__)


async def get_group_markings_grid_controller(
    group_id: int,
    date_page: int = Query(1, ge=1, description="Page of dates"),
    date_limit: int = Query(10, ge=1, le=50, description="Number of dates per page"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get the markings grid for a savings group.
    - Full grid for admins/agents (managers)
    - Personal row only for customers/agent-members
    """
    logger.info(f"[GRID] Request for group {group_id} by user {current_user['user_id']} (role: {current_user['role']})")

    group = db.query(SavingsGroup).filter(SavingsGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found or inactive")

    user_id = current_user["user_id"]
    role = current_user["role"].lower()

    is_manager = role in ["admin", "super_admin", "agent"]
    member_account = db.query(SavingsAccount).filter(
        SavingsAccount.group_id == group_id,
        SavingsAccount.customer_id == user_id
    ).first()
    is_member = member_account is not None

    if not (is_manager or is_member):
        raise HTTPException(status_code=403, detail="You do not have permission to view this group's markings")

    grid_data = await get_group_grid_data(
        group_id=group_id,
        db=db,
        date_page=date_page,
        date_limit=date_limit
    )

    if not grid_data:
        raise HTTPException(status_code=404, detail="No markings data available")

    # Restrict to personal view if only member (not manager)
    if is_member and not is_manager:
        user_tracking = member_account.tracking_number
        filtered_members = [m for m in grid_data["members"] if m["tracking_number"] == user_tracking]
        filtered_markings = {user_tracking: grid_data["markings"].get(user_tracking, {})}

        grid_data["members"] = filtered_members
        grid_data["markings"] = filtered_markings
        grid_data["view_mode"] = "personal"  # optional frontend hint

    return grid_data


async def toggle_group_marking_controller(
    group_id: int,
    request: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Toggle or set marking status.
    - Managers can mark any member
    - Members can only mark their own row
    """
    logger.info(f"[MARKING] Toggle request for group {group_id} by user {current_user['user_id']}")

    required = {"savings_account_id", "date", "status"}
    missing = required - set(request.keys())
    if missing:
        raise HTTPException(422, detail=f"Missing required fields: {', '.join(missing)}")

    savings_account_id = request["savings_account_id"]
    date_str = request["date"]
    target_status = request["status"]

    if target_status not in ["paid", "pending", "not_started"]:
        raise HTTPException(422, detail="Status must be 'paid', 'pending' or 'not_started'")

    account = db.query(SavingsAccount).filter(
        SavingsAccount.id == savings_account_id,
        SavingsAccount.group_id == group_id
    ).first()

    if not account:
        raise HTTPException(404, detail="Savings account not found in this group")

    user_id = current_user["user_id"]
    role = current_user["role"].lower()

    is_manager = role in ["admin", "super_admin", "agent"]
    is_member = account.customer_id == user_id

    if not (is_manager or is_member):
        raise HTTPException(403, detail="Not authorized to mark contributions in this group")

    if is_member and not is_manager and account.customer_id != user_id:
        raise HTTPException(403, detail="You can only mark your own contributions")

    try:
        marking = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings_account_id,
            SavingsMarking.marked_date == date_str
        ).first()

        if marking:
            marking.status = target_status
            marking.marked_by_id = user_id
        else:
            if target_status == "paid":
                new_marking = SavingsMarking(
                    savings_account_id=savings_account_id,
                    marked_date=date_str,
                    amount=account.daily_amount or 0,
                    marked_by_id=user_id,
                    status=target_status,
                    payment_method="manual"
                )
                db.add(new_marking)
                marking = new_marking
            else:
                return {"message": "No change needed", "status": "not_started"}

        db.commit()
        db.refresh(marking)

        return {
            "message": f"Marked as {target_status}",
            "status": marking.status,
            "date": str(marking.marked_date),
            "savings_account_id": marking.savings_account_id
        }

    except Exception as e:
        db.rollback()
        logger.error(f"[MARKING] Failed: {str(e)}", exc_info=True)
        raise HTTPException(500, detail="Failed to update marking")
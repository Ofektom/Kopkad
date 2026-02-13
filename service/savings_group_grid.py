from sqlalchemy.orm import Session
from datetime import date, timedelta
from typing import List, Dict, Optional, Any
from dateutil.relativedelta import relativedelta
import logging

from models.savings_group import SavingsGroup, GroupFrequency
from models.savings import SavingsAccount, SavingsMarking
from models.user import User

logger = logging.getLogger(__name__)

def generate_group_grid_dates(
    start_date: date,
    frequency: GroupFrequency,
    limit: int,
    offset: int,
    end_date: Optional[date] = None
) -> List[date]:
    """
    Generate a list of dates based on frequency, handling pagination.
    """
    dates = []
    current_date = start_date
    
    # Skip to offset
    skipped = 0
    while skipped < offset:
        if end_date and current_date > end_date:
            break
            
        if frequency == GroupFrequency.WEEKLY:
            current_date += relativedelta(weeks=1)
        elif frequency == GroupFrequency.BI_WEEKLY:
            current_date += relativedelta(weeks=2)
        elif frequency == GroupFrequency.MONTHLY:
            current_date += relativedelta(months=1)
        elif frequency == GroupFrequency.QUARTERLY:
            current_date += relativedelta(months=3)
        skipped += 1

    # Collect dates up to limit
    collected = 0
    while collected < limit:
        if end_date and current_date > end_date:
            break
            
        dates.append(current_date)
        
        if frequency == GroupFrequency.WEEKLY:
            current_date += relativedelta(weeks=1)
        elif frequency == GroupFrequency.BI_WEEKLY:
            current_date += relativedelta(weeks=2)
        elif frequency == GroupFrequency.MONTHLY:
            current_date += relativedelta(months=1)
        elif frequency == GroupFrequency.QUARTERLY:
            current_date += relativedelta(months=3)
        collected += 1
        
    return dates

async def get_group_grid_data(
    group_id: int,
    db: Session,
    date_page: int = 1,
    date_limit: int = 10
) -> Dict[str, Any]:
    """
    Fetch grid data: Members x Dates matrix.
    """
    # 1. Get Group
    group = db.query(SavingsGroup).filter(SavingsGroup.id == group_id).first()
    if not group:
        return None

    # 2. Determine Date Pagination
    offset = (date_page - 1) * date_limit
    
    # Ensure we have a reasonable end date for projection if not set
    # Default to 1 year from start if no end_date
    projection_end_date = group.end_date or (group.start_date + relativedelta(years=1))
    
    dates = generate_group_grid_dates(
        start_date=group.start_date,
        frequency=group.frequency,
        limit=date_limit,
        offset=offset,
        end_date=projection_end_date
    )
    
    # Calculate total expected dates (approximate) to determine if there are more pages
    total_dates_approx = 0
    temp_date = group.start_date
    while temp_date <= projection_end_date:
        total_dates_approx += 1
        if group.frequency == GroupFrequency.WEEKLY:
            temp_date += relativedelta(weeks=1)
        elif group.frequency == GroupFrequency.BI_WEEKLY:
            temp_date += relativedelta(weeks=2)
        elif group.frequency == GroupFrequency.MONTHLY:
            temp_date += relativedelta(months=1)
        elif group.frequency == GroupFrequency.QUARTERLY:
            temp_date += relativedelta(months=3)
            
    has_next_page = (offset + len(dates)) < total_dates_approx

    # 3. Get Members (Savings Accounts linked to this group)
    savings_accounts = db.query(SavingsAccount).join(User, SavingsAccount.customer_id == User.id)\
        .filter(SavingsAccount.group_id == group_id)\
        .all()
        
    members_data = []
    markings_map = {} # {tracking_number: {date_str: status}}

    if dates:
        start_range = dates[0]
        end_range = dates[-1]

        # 4. Fetch Markings for all these accounts within the date range
        # We can do a single query if we collect all account IDs
        account_ids = [acc.id for acc in savings_accounts]
        
        if account_ids:
            markings = db.query(SavingsMarking)\
                .filter(
                    SavingsMarking.savings_account_id.in_(account_ids),
                    SavingsMarking.marked_date >= start_range,
                    SavingsMarking.marked_date <= end_range
                ).all()
                
            # Populate markings map
            for marking in markings:
                acc = next((a for a in savings_accounts if a.id == marking.savings_account_id), None)
                if acc:
                    if acc.tracking_number not in markings_map:
                        markings_map[acc.tracking_number] = {}
                    markings_map[acc.tracking_number][str(marking.marked_date)] = marking.status.value

    # Build Member List
    for acc in savings_accounts:
        user = db.query(User).filter(User.id == acc.customer_id).first()
        members_data.append({
            "user_id": user.id,
            "full_name": f"{user.first_name} {user.last_name}",
            "tracking_number": acc.tracking_number,
            "savings_account_id": acc.id
        })
        
        # Ensure map entry exists
        if acc.tracking_number not in markings_map:
            markings_map[acc.tracking_number] = {}

    return {
        "group_name": group.name,
        "contribution_amount": group.contribution_amount,
        "members": members_data,
        "dates": [d.isoformat() for d in dates],
        "markings": markings_map,
        "pagination": {
            "current_page": date_page,
            "limit": date_limit,
            "has_next": has_next_page,
            "total_dates_approx": total_dates_approx
        }
    }

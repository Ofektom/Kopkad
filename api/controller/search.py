from typing import Dict

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from database.postgres_optimized import get_db
from service.search import universal_search
from utils.auth import get_current_user


async def universal_search_controller(
    q: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(5, ge=1, le=20, description="Maximum results per entity"),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Universal search across users, businesses, savings, and payment requests."""
    return await universal_search(
        term=q,
        limit=limit,
        current_user=current_user,
        db=db,
    )


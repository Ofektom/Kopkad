"""
User-Business association repository.
Handles operations on the user_business association table.
"""
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import insert, delete

from models.user_business import user_business


class UserBusinessRepository:
    """Repository for user_business association table"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def is_user_in_business(self, user_id: int, business_id: int) -> bool:
        """Check if user is already linked to a business"""
        query = (
            self.db.query(user_business)
            .filter(
                user_business.c.user_id == user_id,
                user_business.c.business_id == business_id,
            )
        )
        return self.db.execute(query.exists()).scalar()
    
    def link_user_to_business(self, user_id: int, business_id: int):
        """Create association between user and business"""
        if not self.is_user_in_business(user_id, business_id):
            self.db.execute(
                insert(user_business).values(
                    user_id=user_id,
                    business_id=business_id,
                )
            )
            self.db.flush()
    
    def unlink_user_from_business(self, user_id: int, business_id: Optional[int] = None):
        """Remove association between user and business"""
        query = delete(user_business).where(user_business.c.user_id == user_id)
        if business_id is not None:
            query = query.where(user_business.c.business_id == business_id)
        self.db.execute(query)
        self.db.flush()

    def unlink_user_from_all_businesses(self, user_id: int) -> None:
        """Remove all associations for the user."""
        self.db.execute(delete(user_business).where(user_business.c.user_id == user_id))
        self.db.flush()

    def get_business_ids_for_user(self, user_id: int) -> List[int]:
        """Return list of business IDs the user is linked to."""
        result = self.db.execute(
            select(user_business.c.business_id).where(user_business.c.user_id == user_id)
        )
        return [row[0] for row in result.fetchall()]


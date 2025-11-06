"""
User repository for user-related database operations.
"""
from typing import Optional, List, Tuple
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session, joinedload

from models.user import User, user_permissions
from models.business import Business
from models.user_business import user_business
from models.savings import SavingsAccount, SavingsMarking
from store.repositories.base import BaseRepository
from store.enums import Role


class UserRepository(BaseRepository[User]):
    """Repository for User model"""
    
    def __init__(self, db: Session):
        super().__init__(User, db)
    
    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        return self.find_one_by(email=email)
    
    def get_by_phone(self, phone_number: str) -> Optional[User]:
        """Get user by phone number"""
        return self.find_one_by(phone_number=phone_number)
    
    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        return self.find_one_by(username=username)
    
    def get_by_role(self, role: Role, skip: int = 0, limit: int = 100) -> List[User]:
        """Get all users by role"""
        return self.db.query(User).filter(User.role == role).offset(skip).limit(limit).all()
    
    def get_by_business_id(self, business_id: int, skip: int = 0, limit: int = 100) -> List[User]:
        """Get all users in a business"""
        return (
            self.db.query(User)
            .join(User.businesses)
            .filter(User.businesses.any(id=business_id))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_active_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        """Get all active users"""
        return self.find_by(is_active=True)[:limit]
    
    def get_with_businesses(self, user_id: int) -> Optional[User]:
        """Get user with businesses loaded"""
        return (
            self.db.query(User)
            .options(joinedload(User.businesses))
            .filter(User.id == user_id)
            .first()
        )
    
    def get_with_businesses_and_units(self, user_id: int) -> Optional[User]:
        """Get user with businesses and units loaded"""
        from models.business import Business, Unit
        return (
            self.db.query(User)
            .options(
                joinedload(User.businesses).joinedload(Business.units)
            )
            .filter(User.id == user_id)
            .first()
        )
    
    def update_password(self, user_id: int, hashed_password: str, updated_by: int | None = None) -> Optional[User]:
        """Update user password"""
        update_data = {
            "pin": hashed_password,
            "updated_at": datetime.now(timezone.utc),
        }
        if updated_by is not None:
            update_data["updated_by"] = updated_by
        return self.update(user_id, update_data)
    
    def update_active_business(self, user_id: int, business_id: int) -> Optional[User]:
        """Update user's active business"""
        return self.update(user_id, {"active_business_id": business_id})
    
    def toggle_active_status(self, user_id: int, is_active: bool) -> Optional[User]:
        """Toggle user active status"""
        return self.update(user_id, {"is_active": is_active})
    
    def increment_token_version(self, user_id: int) -> Optional[User]:
        """Increment token version (for logout)"""
        user = self.get_by_id(user_id)
        if user:
            user.token_version += 1
            self.db.flush()
        return user
    
    def create_user(self, user_data: dict) -> User:
        """Create a new user"""
        return self.create(user_data)
    
    def get_by_email_or_phone_or_username(self, email: str = None, phone: str = None, username: str = None) -> Optional[User]:
        """Get user by email, phone, or username (any match)"""
        query = self.db.query(User)
        conditions = []
        if email:
            conditions.append(User.email == email)
        if phone:
            conditions.append(User.phone_number == phone)
        if username:
            conditions.append(User.username == username)
        
        if not conditions:
            return None
        
        from sqlalchemy import or_
        return query.filter(or_(*conditions)).first()
    
    def user_exists(self, email: str = None, phone: str = None, username: str = None) -> bool:
        """Check if user exists by email, phone, or username"""
        return self.get_by_email_or_phone_or_username(email, phone, username) is not None
    
    def exists_by_phone(self, phone_number: str) -> bool:
        """Check if user exists by phone number"""
        return self.exists(phone_number=phone_number)
    
    def exists_by_username(self, username: str) -> bool:
        """Check if user exists by username"""
        return self.exists(username=username)
    
    def exists_by_email(self, email: str) -> bool:
        """Check if user exists by email"""
        return self.exists(email=email)
    
    def exists_by_email(self, email: str) -> bool:
        """Check if user exists by email"""
        return self.exists(email=email)
    
    def exists_by_username(self, username: str) -> bool:
        """Check if user exists by username"""
        return self.exists(username=username)
    
    def create_user(self, user_data: dict) -> User:
        """Create a new user (wrapper for create with better naming)"""
        return self.create(user_data)
    
    def update_user(self, user_id: int, user_data: dict) -> Optional[User]:
        """Update user (wrapper for update with better naming)"""
        return self.update(user_id, user_data)
    
    def add_permission(self, user_id: int, permission: str):
        """Add permission to user"""
        from sqlalchemy.sql import insert
        
        # Check if permission already exists
        existing = self.db.execute(
            user_permissions.select().where(
                user_permissions.c.user_id == user_id,
                user_permissions.c.permission == permission
            )
        ).first()
        
        if not existing:
            self.db.execute(
                insert(user_permissions).values(user_id=user_id, permission=permission)
            )
            self.db.flush()
    
    def add_business_association(self, user_id: int, business_id: int):
        """Associate user with business"""
        from sqlalchemy.sql import insert
        
        # Check if association already exists
        existing = self.db.execute(
            user_business.select().where(
                user_business.c.user_id == user_id,
                user_business.c.business_id == business_id
            )
        ).first()
        
        if not existing:
            self.db.execute(
                insert(user_business).values(user_id=user_id, business_id=business_id)
            )
            self.db.flush()

    # -------------------------------------------------------------------------
    # Extended query helpers
    # -------------------------------------------------------------------------

    def get_users_with_filters(
        self,
        *,
        limit: int,
        offset: int,
        role: Optional[str] = None,
        business_name: Optional[str] = None,
        unique_code: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[User], int]:
        """
        Retrieve users with optional filters.

        Returns:
            Tuple[List[User], int]: (users, total_count)
        """
        query = select(User)

        if role:
            query = query.filter(User.role == role)

        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        if business_name or unique_code:
            query = (
                query.join(user_business, User.id == user_business.c.user_id, isouter=True)
                .join(Business, Business.id == user_business.c.business_id, isouter=True)
            )
            if business_name:
                query = query.filter(Business.name.ilike(f"%{business_name}%"))
            if unique_code:
                query = query.filter(Business.unique_code == unique_code)

        # Avoid duplicates when joins are applied
        query = query.distinct()

        total = self.db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
        users = (
            self.db.execute(
                query.order_by(User.created_at.desc()).limit(limit).offset(offset)
            )
            .scalars()
            .all()
        )
        return users, total

    def get_business_users_with_filters(
        self,
        *,
        business_id: int,
        limit: int,
        offset: int,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        savings_type: Optional[str] = None,
        savings_status: Optional[str] = None,
        payment_method: Optional[str] = None,
    ) -> Tuple[List[User], int]:
        """
        Retrieve users linked to a specific business with optional filters.
        """
        query = (
            select(User)
            .join(user_business, User.id == user_business.c.user_id)
            .filter(user_business.c.business_id == business_id)
        )

        if role:
            query = query.filter(User.role == role)

        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        if savings_type or savings_status or payment_method:
            query = query.join(
                SavingsAccount,
                SavingsAccount.customer_id == User.id,
                isouter=True,
            )

        if savings_type:
            query = query.filter(SavingsAccount.savings_type == savings_type)

        if savings_status or payment_method:
            query = query.join(
                SavingsMarking,
                SavingsMarking.savings_account_id == SavingsAccount.id,
                isouter=True,
            )

        if savings_status:
            query = query.filter(SavingsMarking.status == savings_status)

        if payment_method:
            query = query.filter(SavingsMarking.payment_method == payment_method)

        query = query.distinct()

        total = self.db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
        users = (
            self.db.execute(
                query.order_by(User.created_at.desc()).limit(limit).offset(offset)
            )
            .scalars()
            .all()
        )
        return users, total

    def set_active_status(self, user_id: int, is_active: bool, updated_by: int) -> Optional[User]:
        """Set user's active status while tracking updater metadata."""
        user = self.get_by_id(user_id)
        if not user:
            return None

        user.is_active = is_active
        user.updated_at = datetime.now(timezone.utc)
        user.updated_by = updated_by
        self.db.flush()
        return user

    def delete_user_permissions(self, user_id: int) -> None:
        """Remove all permissions linked to a user."""
        self.db.execute(user_permissions.delete().where(user_permissions.c.user_id == user_id))
        self.db.flush()


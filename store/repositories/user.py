"""
User repository for user-related database operations.
"""
from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from models.user import User
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


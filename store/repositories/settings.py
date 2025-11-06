"""
Settings repository for user settings database operations.
"""
from typing import Optional
from sqlalchemy.orm import Session
from models.settings import Settings
from store.repositories.base import BaseRepository


class SettingsRepository(BaseRepository[Settings]):
    """Repository for Settings model"""
    
    def __init__(self, db: Session):
        super().__init__(Settings, db)
    
    def get_by_user_id(self, user_id: int) -> Optional[Settings]:
        """Get settings by user ID"""
        return self.find_one_by(user_id=user_id)
    
    def create_default_settings(self, user_id: int) -> Settings:
        """Create default settings for a user"""
        from store.enums import NotificationMethod
        from datetime import datetime, timezone
        
        return self.create({
            "user_id": user_id,
            "notification_method": NotificationMethod.BOTH.value,
            "created_at": datetime.now(timezone.utc)
        })
    
    def delete_by_user_id(self, user_id: int) -> bool:
        """Delete settings for a user"""
        settings = self.get_by_user_id(user_id)
        if settings:
            self.db.delete(settings)
            self.db.flush()
            return True
        return False


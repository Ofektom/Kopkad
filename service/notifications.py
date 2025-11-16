"""
Notification service for creating in-app notifications across the system.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from models.financial_advisor import NotificationType, NotificationPriority
from store.repositories import UserNotificationRepository, UserRepository, BusinessRepository
from utils.notification import create_notification
import logging

logger = logging.getLogger(__name__)


async def notify_user(
    user_id: int,
    notification_type: NotificationType,
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.MEDIUM,
    db: Session = None,
    notification_repo: UserNotificationRepository = None,
    related_entity_id: Optional[int] = None,
    related_entity_type: Optional[str] = None,
) -> bool:
    """
    Create a notification for a single user.
    
    Returns True if successful, False otherwise.
    """
    try:
        if notification_repo is None:
            if db is None:
                logger.error("Both db and notification_repo cannot be None")
                return False
            notification_repo = UserNotificationRepository(db)
        
        session = notification_repo.db
        
        notification_repo.create({
            "user_id": user_id,
            "notification_type": notification_type,
            "title": title,
            "message": message,
            "priority": priority,
            "is_read": False,
            "related_entity_id": related_entity_id,
            "related_entity_type": related_entity_type,
            "created_by": user_id,
            "created_at": datetime.now(timezone.utc),
        })
        session.commit()
        
        logger.info(f"Created notification '{title}' for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error creating notification for user {user_id}: {str(e)}", exc_info=True)
        if session:
            try:
                session.rollback()
            except Exception as rollback_error:
                logger.error(f"Error rolling back notification session: {str(rollback_error)}")
        return False


async def notify_multiple_users(
    user_ids: List[int],
    notification_type: NotificationType,
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.MEDIUM,
    db: Session = None,
    notification_repo: UserNotificationRepository = None,
    related_entity_id: Optional[int] = None,
    related_entity_type: Optional[str] = None,
) -> int:
    """
    Create notifications for multiple users.
    
    Returns the number of successful notifications created.
    """
    success_count = 0
    for user_id in user_ids:
        if await notify_user(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            db=db,
            notification_repo=notification_repo,
            related_entity_id=related_entity_id,
            related_entity_type=related_entity_type,
        ):
            success_count += 1
    
    return success_count


async def notify_business_admin(
    business_id: int,
    notification_type: NotificationType,
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.MEDIUM,
    db: Session = None,
    business_repo: BusinessRepository = None,
    notification_repo: UserNotificationRepository = None,
    related_entity_id: Optional[int] = None,
    related_entity_type: Optional[str] = None,
) -> bool:
    """
    Notify the admin of a business.
    
    Returns True if successful, False otherwise.
    """
    try:
        if business_repo is None:
            if db is None:
                logger.error("Both db and business_repo cannot be None")
                return False
            business_repo = BusinessRepository(db)
        
        business = business_repo.get_by_id(business_id)
        if not business or not business.admin_id:
            logger.warning(f"Business {business_id} not found or has no admin")
            return False
        
        return await notify_user(
            user_id=business.admin_id,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            db=db,
            notification_repo=notification_repo,
            related_entity_id=related_entity_id,
            related_entity_type=related_entity_type,
        )
    except Exception as e:
        logger.error(f"Error notifying business admin for business {business_id}: {str(e)}")
        return False


async def notify_super_admins(
    notification_type: NotificationType,
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.MEDIUM,
    db: Session = None,
    user_repo: UserRepository = None,
    notification_repo: UserNotificationRepository = None,
    related_entity_id: Optional[int] = None,
    related_entity_type: Optional[str] = None,
) -> int:
    """
    Notify all super admins in the system.
    
    Returns the number of successful notifications created.
    """
    try:
        if user_repo is None:
            if db is None:
                logger.error("Both db and user_repo cannot be None")
                return 0
            user_repo = UserRepository(db)
        
        from store.enums import Role
        super_admins = user_repo.get_by_role(Role.SUPER_ADMIN)
        super_admin_ids = [admin.id for admin in super_admins if admin.is_active]
        
        if not super_admin_ids:
            logger.warning("No active super admins found")
            return 0
        
        return await notify_multiple_users(
            user_ids=super_admin_ids,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            db=db,
            notification_repo=notification_repo,
            related_entity_id=related_entity_id,
            related_entity_type=related_entity_type,
        )
    except Exception as e:
        logger.error(f"Error notifying super admins: {str(e)}")
        return 0


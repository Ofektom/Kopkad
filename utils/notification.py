from sqlalchemy.orm import Session
from models.financial_advisor import UserNotification, NotificationType, NotificationPriority
from models.user import User
from utils.email_service import send_email
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


async def create_notification(
    user_id: int,
    notification_type: NotificationType,
    title: str,
    message: str,
    priority: NotificationPriority,
    db: Session,
    related_entity_id: int = None,
    related_entity_type: str = None
) -> UserNotification:
    """Create an in-app notification for a user."""
    try:
        notification = UserNotification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            is_read=False,
            related_entity_id=related_entity_id,
            related_entity_type=related_entity_type,
            created_by=user_id,
            created_at=datetime.now(timezone.utc)
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        
        logger.info(f"Created notification {notification.id} for user {user_id}")
        return notification
    except Exception as e:
        logger.error(f"Error creating notification: {str(e)}")
        db.rollback()
        raise


async def send_email_notification(
    user_id: int,
    subject: str,
    html_content: str,
    db: Session
):
    """Send an email notification to a user."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.email:
            logger.warning(f"User {user_id} not found or has no email")
            return False
        
        await send_email(
            to_email=user.email,
            subject=subject,
            html_content=html_content
        )
        
        logger.info(f"Sent email notification to user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error sending email notification: {str(e)}")
        return False


async def send_financial_alert(
    user_id: int,
    notification_type: NotificationType,
    title: str,
    message: str,
    priority: NotificationPriority,
    db: Session,
    send_email_too: bool = True,
    related_entity_id: int = None,
    related_entity_type: str = None
):
    """Unified method to send both in-app and email notifications."""
    try:
        # Create in-app notification
        notification = await create_notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            db=db,
            related_entity_id=related_entity_id,
            related_entity_type=related_entity_type
        )
        
        # Send email if requested and priority is medium or high
        if send_email_too and priority in [NotificationPriority.MEDIUM, NotificationPriority.HIGH]:
            # Get appropriate template
            html_content = generate_notification_content(notification_type, title, message)
            await send_email_notification(user_id, title, html_content, db)
        
        return notification
    except Exception as e:
        logger.error(f"Error sending financial alert: {str(e)}")
        raise


def generate_notification_content(
    notification_type: NotificationType,
    title: str,
    message: str
) -> str:
    """Generate HTML email content for notifications using templates."""
    # Base HTML template
    base_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
                border-radius: 10px 10px 0 0;
            }}
            .content {{
                background: #f9f9f9;
                padding: 30px;
                border-radius: 0 0 10px 10px;
            }}
            .alert-high {{
                border-left: 4px solid #e74c3c;
                padding-left: 15px;
            }}
            .alert-medium {{
                border-left: 4px solid #f39c12;
                padding-left: 15px;
            }}
            .alert-low {{
                border-left: 4px solid #3498db;
                padding-left: 15px;
            }}
            .cta-button {{
                display: inline-block;
                background: #667eea;
                color: white;
                padding: 12px 30px;
                text-decoration: none;
                border-radius: 5px;
                margin-top: 20px;
            }}
            .footer {{
                text-align: center;
                margin-top: 20px;
                color: #777;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Kopkad Financial Advisor</h1>
            <p>Your AI-powered financial assistant</p>
        </div>
        <div class="content">
            <h2>{title}</h2>
            <p>{message}</p>
            <a href="https://kopkad-frontend.vercel.app/dashboard" class="cta-button">View in Dashboard</a>
        </div>
        <div class="footer">
            <p>This is an automated message from Kopkad. Please do not reply to this email.</p>
            <p>&copy; 2025 Kopkad. All rights reserved.</p>
        </div>
    </body>
    </html>
    """
    
    return base_template


async def send_whatsapp_notification(to_phone: str, message: str):
    """Placeholder for WhatsApp Business API notification (requires BSP registration)."""
    print(f"WhatsApp notification placeholder: To {to_phone}: {message}")
    return {
        "status": "pending",
        "message": "WhatsApp integration suspended; register with a BSP like Wati or 360Dialog to enable.",
    }

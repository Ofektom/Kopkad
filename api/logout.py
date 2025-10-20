from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database.postgres import get_db
from utils.auth import get_current_user
from models.user import User
import logging

logger = logging.getLogger(__name__)

logout_router = APIRouter(prefix="/auth", tags=["Authentication"])

@logout_router.post("/logout")
async def logout_user(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Logout user by incrementing their token_version.
    This invalidates all existing JWT tokens for the user.
    """
    try:
        user_id = current_user["user_id"]
        
        # Get user from database
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            logger.warning(f"Logout attempt for non-existent user ID: {user_id}")
            return {
                "success": False,
                "message": "User not found"
            }
        
        # Increment token_version to invalidate all tokens
        user.token_version += 1
        db.commit()
        
        logger.info(f"User {user.username} (ID: {user_id}) logged out successfully. Token version: {user.token_version}")
        
        return {
            "success": True,
            "message": "Logged out successfully. All active sessions have been terminated.",
            "data": {
                "user_id": user_id,
                "username": user.username
            }
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error during logout for user {current_user.get('user_id')}: {str(e)}")
        return {
            "success": False,
            "message": f"Logout failed: {str(e)}"
        }


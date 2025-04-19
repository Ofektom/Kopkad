from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from schemas.settings import SettingsUpdate, SettingsResponse
from database.postgres import get_db
from utils.auth import get_current_user
from models.settings import Settings

settings_router = APIRouter(tags=["settings"], prefix="/settings")


@settings_router.put("/update", response_model=SettingsResponse)
async def update_settings(
    request: SettingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = (
        db.query(Settings).filter(Settings.user_id == current_user["user_id"]).first()
    )
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")
    if request.notification_method:
        settings.notification_method = request.notification_method
    db.commit()
    return settings

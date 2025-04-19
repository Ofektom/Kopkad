from pydantic import BaseModel
from models.settings import NotificationMethod
from typing import Optional


class SettingsUpdate(BaseModel):
    notification_method: Optional[NotificationMethod] = None


class SettingsResponse(BaseModel):
    id: int
    user_id: int
    notification_method: str

    class Config:
        from_attributes = True

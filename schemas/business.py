from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class BusinessCreate(BaseModel):
    name: str
    location: Optional[str] = None

class BusinessResponse(BaseModel):
    id: int
    name: str
    location: Optional[str]
    unique_code: str
    created_at: datetime
    delivery_status: str

    class Config:
        orm_mode = True
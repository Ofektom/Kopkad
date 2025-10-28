from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, timezone
from database.postgres_optimized import Base

class TokenBlocklist(Base):
    __tablename__ = "token_blocklist"
    
    id = Column(Integer, primary_key=True)
    token = Column(String(512), nullable=False, unique=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
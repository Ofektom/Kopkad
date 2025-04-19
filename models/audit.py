from sqlalchemy import Column, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from database.postgres import Base


class AuditMixin:
    __tablename__ = None  # Ensures it is treated as a mixin

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


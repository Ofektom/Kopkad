from sqlalchemy import Column, Integer, String, Boolean, ForeignKey,ForeignKey, DateTime
from models.audit import AuditMixin
from database.postgres import Base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class PendingBusinessRequest(Base):
    __tablename__ = "pending_business_requests"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    token = Column(String(length=36), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

class Business(Base, AuditMixin):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    location = Column(String(100), nullable=True)
    unique_code = Column(String(10), unique=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=True)
    users = relationship("User", secondary="user_business", back_populates="businesses")